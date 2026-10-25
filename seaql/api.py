from fastapi import FastAPI, HTTPException, File, UploadFile
from pydantic import BaseModel
import uvicorn
from seaql.agent import run_agent
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool
from seaql.ingestion import import_csv
import os
import tempfile
import secrets
import time
from threading import Lock
from seaql.database import get_schema_json
from seaql.config import ROOT, DATA
from seaql.model import ModelServiceError, health
from seaql.starters import generate_starter_questions
from seaql.presentation import analysis as analyze_sql, preview as preview_sql

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

@app.middleware("http")
async def fresh_interface(request, call_next):
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store"
    return response


app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")


@app.post("/upload_db")
async def upload_db_endpoint(file: UploadFile = File(...)):
    """
    Accept SQLite or UTF-8 CSV; CSV becomes a queryable SQLite table.
    """
    filename = file.filename or ""
    if not filename.lower().endswith((".db", ".sqlite", ".sqlite3", ".csv")):
        raise HTTPException(
            status_code=400, detail="Choose a .csv, .db, .sqlite or .sqlite3 file."
        )

    upload_dir = str(DATA / "uploads")
    os.makedirs(upload_dir, exist_ok=True)

    suffix = os.path.splitext(filename)[1].lower()
    file_path = None
    converted_path = None

    try:
        with tempfile.NamedTemporaryFile(
            dir=upload_dir, suffix=suffix, delete=False
        ) as buffer:
            file_path = buffer.name
            while chunk := await file.read(1024 * 1024):
                buffer.write(chunk)

        metadata = {}
        if suffix == ".csv":
            with tempfile.NamedTemporaryFile(
                dir=upload_dir, suffix=".sqlite", delete=False
            ) as converted:
                converted_path = converted.name
            try:
                metadata = await run_in_threadpool(
                    import_csv, file_path, converted_path, filename
                )
            except ValueError as error:
                raise HTTPException(status_code=400, detail=str(error)) from error
            os.unlink(file_path)
            file_path = converted_path
        uri = f"sqlite:///{file_path}"
        inspected = await run_in_threadpool(get_schema_json, uri)
        if not inspected["success"]:
            raise HTTPException(
                status_code=400, detail="Upload is not a usable SQLite database."
            )
        return {
            "success": True,
            "db_uri": uri,
            "filename": os.path.basename(filename),
            **metadata,
        }
    except HTTPException:
        for path in {file_path, converted_path} - {None}:
            if os.path.exists(path):
                os.unlink(path)
        raise
    except Exception as e:
        for path in {file_path, converted_path} - {None}:
            if os.path.exists(path):
                os.unlink(path)
        raise HTTPException(
            status_code=500, detail="The uploaded file could not be processed."
        )


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
    clarification: bool = False
    truncated: bool = False
    model_id: str = "unknown"
    retry_count: int = 0
    columns: list = []
    row_count: int = 0
    chart_type: str = "auto"
    analysis: dict = {}
    tables_used: list = []
    steps: list = []


@app.get("/", response_class=HTMLResponse)
async def get_root():
    with open(ROOT / "static" / "index.html", "r") as f:
        return f.read()


@app.post("/connect")
def connect_endpoint(req: ConnectRequest):
    """
    Called when a user configures their database in the UI.
    Validates the selected SQLite database and reads its schema directly.
    """
    try:
        inspected = get_schema_json(req.db_uri)
        if not inspected["success"]:
            raise ValueError(inspected["error"])
        return {
            "success": True,
            "message": "SQLite database connected; schema read successfully.",
            "table_count": len(inspected["tables"]),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/schema")
def schema_endpoint(req: ConnectRequest):
    """
    Returns the structured JSON schema for the Database Explorer UI.
    """
    from seaql.database import get_schema_json

    result = get_schema_json(req.db_uri)
    if not result["success"]:
        raise HTTPException(
            status_code=400, detail=result.get("error", "Failed to fetch schema.")
        )
    return result


@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(req: ChatRequest):
    """
    Accepts a natural language query and returns the AI's response.
    """
    try:
        final_state = run_agent(req.query, req.tenant_id, req.db_uri)
        try:
            query_analysis = (
                analyze_sql(final_state["sql_query"])
                if final_state.get("sql_query")
                else {}
            )
        except Exception:
            query_analysis = {}

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
            clarification=final_state.get("clarification", False),
            truncated=final_state.get("truncated", False),
            model_id=final_state.get("model_id", "unknown"),
            retry_count=final_state.get("retry_count", 0),
            columns=list((final_state.get("execution_result") or [{}])[0]),
            row_count=len(final_state.get("execution_result") or []),
            analysis=query_analysis,
            tables_used=query_analysis.get("tables", []),
            steps=[
                "Read the database schema and business rules.",
                "Generated a query or clarification.",
            ]
            + (
                ["Executed the query and returned database records."]
                if final_state.get("execution_result") is not None
                else []
            ),
        )
    except ModelServiceError as e:
        if e.status_code == 429:
            raise HTTPException(
                status_code=429,
                detail="The model is temporarily rate limited. Please retry in about a minute.",
                headers={"Retry-After": "60"},
            ) from e
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        # Preserve the existing public-demo error contract for older provider adapters.
        if "429" in str(e) or "quota exceeded" in str(e).lower():
            raise HTTPException(
                status_code=429,
                detail="The model is temporarily rate limited. Please retry in about a minute.",
                headers={"Retry-After": "60"},
            ) from e
        raise HTTPException(status_code=500, detail="The query could not be completed.")


@app.post("/execute_approved")
def execute_approved_endpoint(req: ExecuteApprovedRequest):
    """
    Executes a previously drafted destructive query that has been manually approved.
    """
    from seaql.database import execute_sql

    try:
        with _approval_lock:
            pending = _pending_approvals.pop(req.approval_id, None)
        if not pending or pending["expires_at"] <= time.monotonic():
            raise HTTPException(
                status_code=404, detail="Approval expired or already used."
            )
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


class RunSQLRequest(BaseModel):
    sql: str
    db_uri: str


class PreviewRequest(BaseModel):
    sql: str
    db_uri: str


@app.post("/starter_questions")
def starter_questions_endpoint(req: ConnectRequest):
    schema = get_schema_json(req.db_uri)
    if not schema["success"]:
        raise HTTPException(status_code=400, detail=schema["error"])
    return {"success": True, "questions": generate_starter_questions(schema, limit=6)}


@app.post("/run_sql")
def run_sql_endpoint(req: RunSQLRequest):
    from seaql.database import classify_sql, execute_sql

    try:
        if classify_sql(req.sql) != "read":
            raise ValueError(
                "Only read queries can run here; data changes require a drafted approval."
            )
        result = execute_sql(req.sql, req.db_uri)
        if not result["success"]:
            raise ValueError(result["error"])
        rows = result["result"]
        return {
            **result,
            "result": rows,
            "columns": list(rows[0]) if rows else [],
            "row_count": len(rows),
            "truncated": result.get("truncated", False),
        }
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/preview_sql")
def preview_sql_endpoint(req: PreviewRequest):
    try:
        details, impact = preview_sql(req.sql, req.db_uri)
        return {"success": True, "analysis": details, "preview": impact}
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/health")
def health_endpoint():
    return {
        "status": "ok",
        "inference": health(),
        "schema_source": "direct_sqlite",
        "cache_enabled": False,
    }


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
