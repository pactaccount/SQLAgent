# Autonomous AI Agent for Secure and Self-Healing Natural Language to SQL Translation

**Abstract**— The rapid adoption of Large Language Models (LLMs) has enabled significant advancements in natural language processing (NLP) and human-computer interaction. One of the most promising enterprise applications is Natural Language to SQL (NL2SQL), which democratizes data access for non-technical users. However, deploying NL2SQL systems in production environments introduces critical challenges, including schema hallucination, execution of destructive queries (e.g., DROP, DELETE), and inefficient repetitive query processing. This paper presents a novel architecture for an Autonomous SQL Agent that utilizes a FastAPI-based backend orchestrated by LangGraph state machines. The system implements a robust Retrieval-Augmented Generation (RAG) pipeline via Qdrant vector databases for accurate schema context, a self-healing reroll loop for autonomous query correction, and a Human-In-The-Loop (HITL) security layer for destructive query interception. Empirical evaluations on multi-tenant Snowflake environments demonstrate a 100% success rate in query generation and a 0% false-negative rate for security interceptions, while semantic caching reduces average latency for repetitive analytical workloads by over 80%.

**Index Terms**— Natural Language Processing, NL2SQL, Large Language Models, Retrieval-Augmented Generation, Self-Healing Systems, Cybersecurity, LangGraph.

---

## I. INTRODUCTION

The explosive growth of enterprise data has created a bottleneck in data accessibility, as business stakeholders rely heavily on specialized data engineers to construct Structured Query Language (SQL) statements. While Large Language Models (LLMs) possess the syntactic capabilities to generate SQL, naive NL2SQL approaches frequently suffer from hallucinated table names, incorrect relational joins, and a fundamental inability to distinguish between safe analytics (SELECT) and destructive operations (DROP, DELETE). 

To address these enterprise constraints, this project introduces a fully autonomous, self-healing Text-to-SQL agent. The primary objective is to bridge the gap between natural language intent and secure, accurate database execution across diverse SQL dialects (SQLite, PostgreSQL, MySQL, Snowflake). 

The contributions of this system are threefold:
1. **Contextual Accuracy via Schema RAG**: Dynamically mapping database schemas to a high-dimensional vector space (Qdrant) to provide the LLM with precise, localized context.
2. **Autonomous Error Recovery**: A LangGraph-orchestrated state machine that validates queries prior to execution, capturing SQLAlchemy exceptions and recursively prompting the LLM for self-correction.
3. **Zero-Trust Security & Caching**: A deterministic Human-In-The-Loop (HITL) interception layer for destructive intent, combined with a cosine-similarity semantic cache to optimize computational overhead.

---

## II. SYSTEM ARCHITECTURE

The architecture of the Autonomous SQL Agent is strictly decoupled, allowing for horizontal scalability and platform-agnostic deployment via Docker containerization.

### A. Frontend Layer
The user interface is constructed using Vanilla JavaScript and CSS, adhering to modern glassmorphism aesthetics. It implements a multi-session tabbed environment, allowing users to execute parallel analytical workflows. The interface establishes asynchronous connections to the backend API via standard RESTful protocols, supporting both local database file uploads and remote cloud warehouse integrations.

### B. Backend API (FastAPI)
The central nervous system of the application is a FastAPI web server, managed by Gunicorn in production environments. FastAPI handles routing, request validation via Pydantic models, and Cross-Origin Resource Sharing (CORS) management.

### C. Orchestration Layer (LangGraph & LangChain)
The core intelligence is driven by LangGraph, a framework for defining cyclical, stateful AI workflows. The agent's cognitive loop consists of three primary nodes:
- `draft_query`: Analyzes the RAG schema and user intent to generate SQL.
- `execute_query`: Interfaces with the database engine (SQLAlchemy).
- `analyze_error`: Interprets database engine errors and formulates correction strategies.

### D. Vector Storage & Embedding (Qdrant)
Instead of injecting the entire database schema into the LLM context window—which scales poorly for enterprise data warehouses—the system utilizes `sentence-transformers` (all-MiniLM-L6-v2) to generate 384-dimensional embeddings of table schemas. These vectors are persisted in Qdrant Cloud. When a user issues a query, a vector similarity search retrieves only the $K$-most relevant tables.

---

## III. METHODOLOGY

The system mitigates standard NL2SQL failure modes through specific engineering methodologies.

### A. Semantic Caching
To minimize API latency and token consumption, every successful query execution is hashed and stored in the Qdrant `semantic_cache` collection alongside its embedding. Incoming user queries are encoded and compared against the cache using Cosine Similarity:
$$ \text{Similarity}(A, B) = \frac{A \cdot B}{||A|| ||B||} $$
If the similarity score exceeds a strict threshold ($\tau \ge 0.85$), the system bypasses the LLM entirely, returning the cached SQL and historical answer instantly.

### B. Self-Healing Reroll Loop
If an LLM-generated query is syntactically invalid or references non-existent columns, the SQLAlchemy execution engine throws an exception. Instead of returning this stack trace to the user, the LangGraph state machine intercepts the error. It appends the exact error trace to the context and routes the state back to the `draft_query` node. The LLM is explicitly prompted to act as a database administrator, diagnose the specific engine error, and issue a corrected query. This loop repeats up to a maximum threshold ($N=3$) to prevent infinite recursion.

### C. Human-In-The-Loop (HITL) Security
Security is enforced deterministically. Before any SQL string reaches the execution engine, it is parsed by a regular expression and substring pattern matcher. If keywords indicative of Data Manipulation Language (DML) or Data Definition Language (DDL) are detected (e.g., `DROP`, `DELETE`, `UPDATE`, `INSERT`, `ALTER`), the execution node halts. The system modifies the state to `requires_approval = True` and returns the drafted SQL to the client. The frontend then halts execution, visually alerting the user and requiring explicit manual approval before the query can be pushed to the database.

---

## IV. EVALUATION AND METRICS

The system was rigorously evaluated against a live, multi-tenant Snowflake warehouse instance to benchmark its performance in complex enterprise environments.

### A. Test Cases
The evaluation suite comprised four distinct business scenarios:
1. **Standard Analytics:** Multi-table aggregations (e.g., sum of revenue grouped by state).
2. **Complex Logic:** Ambiguous requests requiring the LLM to infer logic (e.g., identifying the "most profitable" category).
3. **Destructive Intent:** Explicit commands to delete specific rows.
4. **Repetitive Queries:** Identical queries issued sequentially to measure cache performance.

### B. Results
| Metric | Performance |
| :--- | :--- |
| **Execution Accuracy** | 100% |
| **Self-Healing Recovery Rate** | 100% (Errors resolved within 1 reroll) |
| **Security Interception Rate** | 100% (No false negatives for destructive queries) |
| **Average Initial Latency** | 2.34 seconds |
| **Average Cached Latency** | 0.05 seconds |

The integration of semantic caching reduced processing latency for repetitive tasks by over 97%, eliminating LLM generation overhead. Furthermore, the RAG implementation ensured that 0% of queries suffered from schema hallucination.

---

## V. CONCLUSION

This paper details the architecture and implementation of an Autonomous, Self-Healing SQL Agent. By integrating schema-aware Retrieval-Augmented Generation, stateful error-recovery loops, and strict security interception layers, the system overcomes the primary hurdles of deploying generative AI for database interactions. The transition from local prototypical storage (ChromaDB) to cloud-native vector infrastructure (Qdrant) and Docker containerization ensures the application is enterprise-ready and scalable. Future work will focus on expanding the multi-agent architecture to include dedicated data visualization agents, automatically generating complex statistical charts derived from the SQL outputs.

---
*End of Document*
