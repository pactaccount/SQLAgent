import os
from sqlalchemy import create_engine, inspect
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
from langchain_huggingface import HuggingFaceEndpointEmbeddings
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
        if qdrant_url and qdrant_api_key:
            self.client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)
        else:
            self.client = QdrantClient(":memory:")
        
        # Use Hugging Face API to prevent OOM errors on limited RAM servers
        hf_token = os.getenv("HF_TOKEN")
        self.encoder = HuggingFaceEndpointEmbeddings(
            model="sentence-transformers/all-MiniLM-L6-v2",
            huggingfacehub_api_token=hf_token
        ) if hf_token else None
        
        self.vector_size = 384  # Dimension for all-MiniLM-L6-v2
        
        self._init_collections()

    def _init_collections(self):
        try:
            collections = [c.name for c in self.client.get_collections().collections]
        except Exception:
            collections = []
            
        if "schema_metadata" not in collections:
            self.client.create_collection(
                collection_name="schema_metadata",
                vectors_config=VectorParams(size=self.vector_size, distance=Distance.COSINE)
            )
        if "semantic_cache" not in collections:
            self.client.create_collection(
                collection_name="semantic_cache",
                vectors_config=VectorParams(size=self.vector_size, distance=Distance.COSINE)
            )

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
            
        if not schema_docs or not self.encoder:
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
            
        self.client.upsert(
            collection_name="schema_metadata",
            points=points
        )
        print(f"Loaded {len(points)} table schemas into Qdrant for {tenant_id}.")

    def search_schema(self, query: str, tenant_id: str, k: int = 5):
        """Searches for top k relevant table schemas for a given query, filtered by tenant."""
        if not self.encoder:
            return []
        query_vector = self.encoder.embed_query(query)
        
        try:
            results = self.client.search(
                collection_name="schema_metadata",
                query_vector=query_vector,
                limit=k,
                query_filter=Filter(
                    must=[FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))]
                )
            )
            return [hit.payload["document"] for hit in results]
        except Exception:
            return []

    def semantic_cache_check(self, query: str, tenant_id: str, threshold: float = 0.95):
        """Checks if a highly similar query exists in the cache for this tenant."""
        if not self.encoder:
            return None
        query_vector = self.encoder.embed_query(query)
        
        try:
            results = self.client.search(
                collection_name="semantic_cache",
                query_vector=query_vector,
                limit=1,
                query_filter=Filter(
                    must=[FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))]
                )
            )
            
            # Qdrant Cosine distance returns similarity score where 1.0 is exact match.
            if results and results[0].score >= threshold:
                payload = results[0].payload
                return {
                    "answer": payload.get("answer", ""),
                    "sql": payload.get("sql", "")
                }
        except Exception:
            pass
            
        return None

    def semantic_cache_set(self, query: str, answer: str, sql: str, tenant_id: str):
        """Saves a query and its successful response to the cache for a tenant."""
        if not self.encoder:
            return
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

# Global instance
vector_store = VectorStore()
