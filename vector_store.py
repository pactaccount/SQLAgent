import os
import re
from sqlalchemy import create_engine, inspect
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
from embeddings import build_embeddings, VECTOR_SIZE
import uuid

def extract_schema_metadata(db_uri: str):
    """
    Connects to the database using SQLAlchemy and extracts the schema for each table.
    Returns a list of dictionaries containing table metadata.
    """
    engine = create_engine(db_uri)
    inspector = inspect(engine)
    
    tables = inspector.get_table_names()
    schema_docs = []
    
    for table_name in tables:
        # Get column info
        columns = inspector.get_columns(table_name)
        column_defs = [f"{col['name']} ({str(col['type'])})" for col in columns]
        
        # Get foreign key info
        fks = inspector.get_foreign_keys(table_name)
        fk_defs = [f"{fk['constrained_columns']} -> {fk['referred_table']}.{fk['referred_columns']}" for fk in fks]
        
        doc_content = f"Table: {table_name}\n"
        doc_content += f"Columns: {', '.join(column_defs)}\n"
        if fk_defs:
            doc_content += f"Foreign Keys: {', '.join(fk_defs)}\n"
            
        schema_docs.append({
            "table_name": table_name,
            "document": doc_content,
        })
        
    return schema_docs

class VectorStore:
    def __init__(self):
        qdrant_url = os.getenv("QDRANT_URL")
        qdrant_api_key = os.getenv("QDRANT_API_KEY")

        # Use cloud if credentials exist, otherwise fallback to local memory
        self.client = None
        self.using_cloud = False
        if qdrant_url and qdrant_api_key:
            try:
                self.client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)
                # Force a round-trip so a bad URL or key is discovered here
                # rather than on the first user request.
                self.client.get_collections()
                self.using_cloud = True
            except Exception as exc:
                print(f"[VectorStore] Qdrant Cloud unavailable ({exc}); using in-memory store.")
                self.client = QdrantClient(":memory:")

        if self.client is None:
            self.client = QdrantClient(":memory:")

        # Use the hosted Hugging Face encoder when it is available, and fall
        # back to a local one when it is not. The app must work either way.
        hf_token = os.getenv("HF_TOKEN")
        self.encoder = build_embeddings(hf_token)

        self.vector_size = VECTOR_SIZE  # Dimension for all-MiniLM-L6-v2

        self._init_collections()

    def _init_collections(self):
        try:
            collections = [c.name for c in self.client.get_collections().collections]
        except Exception:
            collections = []

        for name in ("schema_metadata", "semantic_cache"):
            if name not in collections:
                try:
                    self.client.create_collection(
                        collection_name=name,
                        vectors_config=VectorParams(size=self.vector_size, distance=Distance.COSINE)
                    )
                except Exception as exc:
                    print(f"[VectorStore] Could not create collection '{name}': {exc}")

    def init_schema_rag(self, db_uri: str, tenant_id: str):
        """Extracts schema from db and loads it into Qdrant for a specific tenant."""
        print(f"Initializing Schema Vector Store for Tenant: {tenant_id}...")
        
        # Delete old schema for this tenant
        try:
            self.client.delete(
                collection_name="schema_metadata",
                points_selector=Filter(
                    must=[FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))]
                )
            )
        except Exception:
            pass
            
        schema_docs = extract_schema_metadata(db_uri)

        if not schema_docs:
            return

        points = []
        for doc in schema_docs:
            vector = self.encoder.embed_query(doc["document"])
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{tenant_id}_{doc['table_name']}"))
            payload = {
                "type": "schema",
                "table": doc["table_name"],
                "tenant_id": tenant_id,
                "document": doc["document"]
            }
            points.append(PointStruct(id=point_id, vector=vector, payload=payload))

        try:
            self.client.upsert(
                collection_name="schema_metadata",
                points=points
            )
            print(f"Loaded {len(points)} table schemas into Qdrant for {tenant_id}.")
        except Exception as exc:
            print(f"[VectorStore] Could not store schema for {tenant_id}: {exc}")

    def _query(self, collection: str, vector: list, limit: int, tenant_id: str):
        """
        Run a filtered vector search.

        Qdrant renamed `search` to `query_points` in its 1.10+ client, and
        removed the old name. This calls whichever the installed client
        provides, so the semantic cache and schema retrieval work on both
        old and new clients.
        """
        query_filter = Filter(
            must=[FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))]
        )

        if hasattr(self.client, "query_points"):
            response = self.client.query_points(
                collection_name=collection,
                query=vector,
                limit=limit,
                query_filter=query_filter,
            )
            return list(response.points)

        # Older clients: search() returns the points directly.
        return list(self.client.search(
            collection_name=collection,
            query_vector=vector,
            limit=limit,
            query_filter=query_filter,
        ))

    def search_schema(self, query: str, tenant_id: str, k: int = 5):
        """Searches for top k relevant table schemas for a given query, filtered by tenant."""
        try:
            query_vector = self.encoder.embed_query(query)

            results = self._query(
                "schema_metadata", query_vector, k, tenant_id
            )
            documents = [hit.payload["document"] for hit in results]
            if documents:
                return documents
        except Exception:
            pass

        # The vector search failed or found nothing. Fall back to a keyword
        # match over the same collection, so a working index is still used.
        return self._keyword_search_schema(query, tenant_id, k)

    def _keyword_search_schema(self, query: str, tenant_id: str, k: int = 5):
        """Rank the tenant's tables by how many query words they contain."""
        try:
            points, _ = self.client.scroll(
                collection_name="schema_metadata",
                scroll_filter=Filter(
                    must=[FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))]
                ),
                limit=200,
                with_payload=True,
            )
        except Exception:
            return []

        words = {w for w in re.findall(r"[a-z0-9]+", (query or "").lower()) if len(w) > 2}
        if not words:
            return []

        scored = []
        for point in points:
            payload = point.payload or {}
            document = (payload.get("document") or "").lower()
            table = (payload.get("table") or "").lower()
            score = sum(1 for word in words if word in document or word in table)
            if score:
                scored.append((score, payload.get("document", "")))

        # Most relevant first; ties keep the original order.
        scored.sort(key=lambda pair: -pair[0])
        return [document for _, document in scored[:k]]

    def semantic_cache_check(self, query: str, tenant_id: str, threshold: float = 0.95):
        """Checks if a highly similar query exists in the cache for this tenant."""
        try:
            query_vector = self.encoder.embed_query(query)

            results = self._query("semantic_cache", query_vector, 1, tenant_id)

            # Qdrant Cosine distance returns similarity score where 1.0 is exact match.
            if results and results[0].score >= threshold:
                payload = results[0].payload
                return {
                    "answer": payload.get("answer", ""),
                    "sql": payload.get("sql", "")
                }
        except Exception as exc:
            print(f"[VectorStore] Semantic cache lookup failed: {exc}")

        return None

    def semantic_cache_set(self, query: str, answer: str, sql: str, tenant_id: str):
        """Saves a query and its successful response to the cache for a tenant."""
        try:
            vector = self.encoder.embed_query(query)
            point_id = str(uuid.uuid4())
            payload = {
                "sql": sql,
                "query": query,
                "answer": answer,
                "tenant_id": tenant_id
            }

            self.client.upsert(
                collection_name="semantic_cache",
                points=[PointStruct(id=point_id, vector=vector, payload=payload)]
            )
        except Exception as exc:
            print(f"[VectorStore] Could not write to the semantic cache: {exc}")

# Global instance
vector_store = VectorStore()
