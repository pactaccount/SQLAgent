from fastapi import FastAPI, HTTPException, File, UploadFile
from pydantic import BaseModel
import uvicorn
from agent import run_agent
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import os
import tempfile
import secrets
import time
from threading import Lock
from vector_store import vector_store

# A reviewed statement is stored server-side and can be executed once within ten minutes.
# This is a demo review gate, not an authorization boundary for untrusted databases.
_pending_approvals = {}
_approval_lock = Lock()
APPROVAL_TTL_SECONDS = 600

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
    filename = file.filename or ""
    if not filename.lower().endswith(('.db', '.sqlite', '.sqlite3')):
         raise HTTPException(status_code=400, detail="Only .db and .sqlite files are allowed.")
         
    upload_dir = os.path.join(tempfile.gettempdir(), "sql_agent_uploads")
    os.makedirs(upload_dir, exist_ok=True)
    
    suffix = os.path.splitext(filename)[1].lower()
    file_path = None
    
    try:
        with tempfile.NamedTemporaryFile(dir=upload_dir, suffix=suffix, delete=False) as buffer:
            file_path = buffer.name
            size = 0
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > 25 * 1024 * 1024:
                    raise HTTPException(status_code=413, detail="Database upload exceeds 25 MB.")
                buffer.write(chunk)
            
        uri = f"sqlite:///{file_path}"
        return {"success": True, "db_uri": uri, "filename": os.path.basename(filename)}
    except HTTPException:
        if file_path:
            os.unlink(file_path)
        raise
    except Exception as e:
        if file_path:
            os.unlink(file_path)
        raise HTTPException(status_code=500, detail=str(e))

class ConnectRequest(BaseModel):
    tenant_id: str
    db_uri: str

class ChatRequest(BaseModel):
    query: str
    tenant_id: str
    db_uri: str

class ExecuteApprovedRequest(BaseModel):
    approval_id: str

class ChatResponse(BaseModel):
    simple_answer: str
    sql_query: str
    execution_result: list = []
    error_traces: list
    cached: bool
    requires_approval: bool
    approval_id: str | None = None

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

@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(req: ChatRequest):
    """
    Accepts a natural language query and returns the AI's response.
    """
    try:
        final_state = run_agent(req.query, req.tenant_id, req.db_uri)
        
        approval_id = None
        if final_state.get("requires_approval"):
            approval_id = secrets.token_urlsafe(32)
            with _approval_lock:
                now = time.monotonic()
                for key, pending in list(_pending_approvals.items()):
                    if pending["expires_at"] <= now:
                        del _pending_approvals[key]
                _pending_approvals[approval_id] = {
                    "sql": final_state["sql_query"],
                    "db_uri": req.db_uri,
                    "expires_at": now + APPROVAL_TTL_SECONDS,
                }
        return ChatResponse(
            simple_answer=final_state.get("final_answer", ""),
            sql_query=final_state.get("sql_query", ""),
            execution_result=final_state.get("execution_result") or [],
            error_traces=final_state.get("error_traces", []),
            cached=final_state.get("cached_result", False),
            requires_approval=final_state.get("requires_approval", False),
            approval_id=approval_id,
        )
    except Exception as e:
         raise HTTPException(status_code=500, detail=str(e))

@app.post("/execute_approved")
def execute_approved_endpoint(req: ExecuteApprovedRequest):
    """
    Executes a previously drafted destructive query that has been manually approved.
    """
    from tools import execute_sql
    try:
        with _approval_lock:
            pending = _pending_approvals.pop(req.approval_id, None)
        if not pending or pending["expires_at"] <= time.monotonic():
            raise HTTPException(status_code=404, detail="Approval expired or already used.")
        res = execute_sql(pending["sql"], pending["db_uri"], bypass_approval=True)
        if not res["success"]:
            raise HTTPException(status_code=400, detail=res["error"])
        return res
    except HTTPException:
        raise

@app.post("/reject_approved")
def reject_approved_endpoint(req: ExecuteApprovedRequest):
    with _approval_lock:
        removed = _pending_approvals.pop(req.approval_id, None)
    if not removed:
        raise HTTPException(status_code=404, detail="Approval expired or already used.")
    return {"success": True}

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
