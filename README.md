# Self-Healing Text-to-SQL Agent

An autonomous, self-healing Text-to-SQL agent built with Python, LangGraph, LiteLLM, ChromaDB, and SQLite.

## Architecture

```mermaid
graph TD
    %% Nodes
    User(("User"))
    
    subgraph Phase2 ["Phase 2: FastAPI Layer"]
        API["FastAPI /chat Endpoint"]
    end

    subgraph Phase1 ["Phase 1: LangGraph Agent & Data Layer"]
        Cache["Semantic Cache Check"]
        RAG["Schema Inspector RAG"]
        Generator["SQL Generator LiteLLM"]
        Executor["Safe SQL Executor"]
        Synthesis["Response Synthesis"]
        
        VectorDB[("ChromaDB Vector Store")]
        SQLite[("Chinook SQLite DB")]
    end
    
    subgraph Phase3 ["Phase 3: 3D Frontend UI"]
        UI["3D Web App React/Three.js"]
    end

    %% Flow
    User -->|"Question"| UI
    UI -->|"JSON"| API
    API --> Cache
    Cache -->|"Miss"| RAG
    Cache -.->|"Hit"| Synthesis
    RAG <-->|"Query"| VectorDB
    RAG --> Generator --> Executor
    Executor -->|"SQL"| SQLite
    SQLite -->|"Success"| Synthesis
    SQLite -->|"Error"| Executor
    Executor -->|"Error Trace"| Generator
    Synthesis --> API --> UI --> User
```

## Setup Instructions

1. **Clone and Setup Virtual Environment:**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

2. **Download the Database:**
```bash
curl -L https://raw.githubusercontent.com/lerocha/chinook-database/master/ChinookDatabase/DataSources/Chinook_Sqlite.sqlite -o chinook.db
```

3. **Configure API Keys:**
Duplicate `.env.template` to `.env` and add your `GEMINI_API_KEY`.

4. **Run the Automated Tests:**
```bash
pytest test_agent.py -v
```

5. **Start the API Server:**
```bash
uvicorn app:app --reload
```
