from fastapi import FastAPI, HTTPException, File, UploadFile
from pydantic import BaseModel
import uvicorn
from agent import run_agent
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import os
import shutil
from vector_store import vector_store
from starter_questions import generate_starter_questions
from sql_analysis import classify_query, preview_impact

from urllib.parse import urlparse, urlunparse

app = FastAPI(title="Self-Healing Text-to-SQL Agent API")

frontend_url = os.getenv("FRONTEND_URL", "*")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_url] if frontend_url != "*" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if not os.path.exists("static"):
    os.makedirs("static")
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.post("/upload_db")
async def upload_db_endpoint(file: UploadFile = File(...)):
    """
    Handles file uploads for local SQLite databases.
    Saves them to the server's temp directory and returns a valid SQLAlchemy URI.
    """
    if not file.filename.endswith(('.db', '.sqlite', '.sqlite3')):
         raise HTTPException(status_code=400, detail="Only .db and .sqlite files are allowed.")

    upload_dir = "/tmp/sql_agent_uploads"
    os.makedirs(upload_dir, exist_ok=True)

    # Use the server-generated name, never the client's, so an upload cannot
    # overwrite another user's file or escape the upload directory.
    file_path = os.path.join(upload_dir, os.path.basename(file.filename))

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        uri = f"sqlite:///{file_path}"
        return {"success": True, "db_uri": uri, "filename": file.filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class ConnectRequest(BaseModel):
    tenant_id: str
    db_uri: str

class ChatRequest(BaseModel):
    query: str
    tenant_id: str
    db_uri: str

class ExecuteApprovedRequest(BaseModel):
    sql: str
    tenant_id: str
    db_uri: str

class PreviewRequest(BaseModel):
    sql: str
    db_uri: str

class RunSQLRequest(BaseModel):
    sql: str
    db_uri: str
    limit: int = 200

class ChatResponse(BaseModel):
    simple_answer: str
    sql_query: str
    execution_result: list = []
    error_traces: list
    cached: bool
    requires_approval: bool
    insight: str = ""
    sql_explanation: str = ""
    chart_type: str = "none"
    columns: list = []
    row_count: int = 0
    truncated: bool = False
    analysis: dict = {}
    follow_ups: list = []
    tables_used: list = []
    steps: list = []
    confidence: dict = {}

@app.get("/", response_class=HTMLResponse)
async def get_root():
    with open("static/index.html", "r") as f:
        return f.read()

@app.post("/connect")
def connect_endpoint(req: ConnectRequest):
    """
    Called when a user configures their database in the UI.
    Initializes the schema into ChromaDB for their specific tenant.
    """
    try:
        vector_store.init_schema_rag(req.db_uri, req.tenant_id)
        return {"success": True, "message": "Database connected and schema indexed successfully."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/schema")
def schema_endpoint(req: ConnectRequest):
    """
    Returns the structured JSON schema for the Database Explorer UI.
    """
    from tools import get_schema_json
    result = get_schema_json(req.db_uri)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to fetch schema."))
    return result

@app.post("/starter_questions")
def starter_questions_endpoint(req: ConnectRequest):
    """
    Returns starter questions generated from the connected database's own schema,
    so a new user always has something meaningful to ask.
    """
    from tools import get_schema_json
    result = get_schema_json(req.db_uri)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to fetch schema."))
    return {"success": True, "questions": generate_starter_questions(result, limit=6)}

@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(req: ChatRequest):
    """
    Accepts a natural language query and returns the AI's response.
    """
    try:
        final_state = run_agent(req.query, req.tenant_id, req.db_uri)

        return ChatResponse(
            simple_answer=final_state.get("final_answer", ""),
            sql_query=final_state.get("sql_query", ""),
            execution_result=final_state.get("execution_result") or [],
            error_traces=final_state.get("error_traces", []),
            cached=final_state.get("cached_result", False),
            requires_approval=final_state.get("requires_approval", False),
            insight=final_state.get("insight", ""),
            sql_explanation=final_state.get("sql_explanation", ""),
            chart_type=final_state.get("chart_type", "none"),
            columns=final_state.get("columns", []),
            row_count=final_state.get("row_count", 0),
            truncated=final_state.get("truncated", False),
            analysis=final_state.get("analysis", {}),
            follow_ups=final_state.get("follow_ups", []),
            tables_used=final_state.get("tables_used", []),
            steps=final_state.get("steps", []),
            confidence=final_state.get("confidence", {}),
        )
    except Exception as e:
         raise HTTPException(status_code=500, detail=str(e))

@app.post("/preview_sql")
def preview_sql_endpoint(req: PreviewRequest):
    """
    Classifies a SQL statement and estimates how many rows it would change,
    without running it. Used by the approval dialog.
    """
    try:
        analysis = classify_query(req.sql)
        preview = preview_impact(req.sql, req.db_uri)
        return {"success": True, "analysis": analysis, "preview": preview}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/run_sql")
def run_sql_endpoint(req: RunSQLRequest):
    """
    Runs a read-only SQL statement typed or edited by the user in the SQL panel.
    Mutating statements are refused here - they go through /execute_approved.
    """
    from tools import get_row_preview
    try:
        limit = max(1, min(int(req.limit), 1000))
        result = get_row_preview(req.sql, req.db_uri, limit=limit)
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result.get("error", "Query failed."))
        return result
    except HTTPException:
        raise
    except Exception as e:
         raise HTTPException(status_code=500, detail=str(e))

@app.post("/execute_approved")
def execute_approved_endpoint(req: ExecuteApprovedRequest):
    """
    Executes a previously drafted destructive query that has been manually approved.
    """
    from tools import execute_sql
    try:
        # bypass_approval=True
        res = execute_sql(req.sql, req.db_uri, bypass_approval=True)
        if not res["success"]:
            raise HTTPException(status_code=400, detail=res["error"])
        return res
    except HTTPException:
        raise
    except Exception as e:
         raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
