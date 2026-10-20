import pytest
from fastapi.testclient import TestClient
from app import app
from tools import execute_sql, get_schema_json
from agent import run_agent
import os

client = TestClient(app)

TEST_DATABASES = [
    ("sqlite", "sqlite:///chinook.db", "test_sqlite_tenant")
]

# Only test Snowflake if credentials are provided in the environment (for CI/CD security)
sf_uri = os.getenv("SNOWFLAKE_URI")
if sf_uri:
    TEST_DATABASES.append(("snowflake", sf_uri, "test_sf_tenant"))


def get_test_table(db_uri):
    """Helper to dynamically fetch a valid table name from the db for testing."""
    schema = get_schema_json(db_uri)
    if schema.get("success") and len(schema.get("tables", [])) > 0:
        return schema["tables"][0]["name"]
    return "UNKNOWN_TABLE"

@pytest.mark.parametrize("db_type, db_uri, tenant_id", TEST_DATABASES)
def test_read_only_execution(db_type, db_uri, tenant_id):
    """Test tools.py execute_sql for a safe SELECT query dynamically."""
    table = get_test_table(db_uri)
    query = f'SELECT * FROM "{table}" LIMIT 3'
    # For SQLite we don't strictly need quotes, but Snowflake prefers uppercase or quotes.
    # Actually, Snowflake defaults to uppercase if unquoted. Let's just use the exact name without quotes first.
    query = f"SELECT * FROM {table} LIMIT 3"
    
    result = execute_sql(query, db_uri)
    
    assert result["success"] is True
    assert result["requires_approval"] is False
    assert len(result["result"]) <= 3

@pytest.mark.parametrize("db_type, db_uri, tenant_id", TEST_DATABASES)
def test_hitl_interception(db_type, db_uri, tenant_id):
    """Test tools.py execute_sql intercepts destructive queries."""
    table = get_test_table(db_uri)
    query = f"DELETE FROM {table}"
    result = execute_sql(query, db_uri)
    
    assert result["success"] is True
    assert result["requires_approval"] is True
    assert result["result"] is None
    assert "flagged" in result["message"].lower()

@pytest.mark.parametrize("db_type, db_uri, tenant_id", TEST_DATABASES)
def test_fastapi_endpoints(db_type, db_uri, tenant_id):
    """Test the FastAPI endpoints dynamically across all DBs."""
    # Test 1: /connect
    res_connect = client.post("/connect", json={"tenant_id": tenant_id, "db_uri": db_uri})
    assert res_connect.status_code == 200
    assert res_connect.json()["success"] is True
    
    # Test 2: /schema
    res_schema = client.post("/schema", json={"tenant_id": tenant_id, "db_uri": db_uri})
    assert res_schema.status_code == 200
    schema_data = res_schema.json()
    assert schema_data["success"] is True
    assert len(schema_data["tables"]) > 0
    
    # Test 3: /chat (Read-only)
    table = schema_data["tables"][0]["name"]
    res_chat = client.post("/chat", json={"query": f"Count the number of rows in the {table} table", "tenant_id": tenant_id, "db_uri": db_uri})
    assert res_chat.status_code == 200
    chat_data = res_chat.json()
    assert chat_data["requires_approval"] is False

@pytest.mark.parametrize("db_type, db_uri, tenant_id", TEST_DATABASES)
def test_run_agent_flow(db_type, db_uri, tenant_id):
    """Test the full agent state machine dynamically."""
    table = get_test_table(db_uri)
    query = f"Select all rows from {table} limit 1"
    state = run_agent(query, tenant_id, db_uri)
    
    assert state["requires_approval"] is False
    assert state["execution_result"] is not None

@pytest.mark.parametrize("db_type, db_uri, tenant_id", TEST_DATABASES)
def test_agent_hitl_flow(db_type, db_uri, tenant_id):
    """
    Test the agent correctly flags destructive requests dynamically.

    This one runs against the deterministic mock so the test does not depend
    on the model choosing a particular destructive phrasing.
    """
    import mock_llm

    table = get_test_table(db_uri)
    query = f"Drop the table {table}"

    original = mock_llm.mock_sql
    mock_llm.mock_sql = lambda q: f"DROP TABLE {table}"
    try:
        state = run_agent(query, tenant_id, db_uri)
    finally:
        mock_llm.mock_sql = original

    assert state["requires_approval"] is True
    assert "DROP" in state["sql_query"].upper()


@pytest.mark.parametrize("db_type, db_uri, tenant_id", TEST_DATABASES)
def test_preview_sql_does_not_change_anything(db_type, db_uri, tenant_id):
    """The impact preview is read-only, and it reports what would change."""
    table = get_test_table(db_uri)

    res = client.post("/preview_sql", json={
        "sql": f"DELETE FROM {table} WHERE 1 = 0",
        "db_uri": db_uri,
    })
    assert res.status_code == 200

    payload = res.json()
    assert payload["success"] is True
    assert payload["analysis"]["is_mutating"] is True
    assert payload["analysis"]["type"] == "DELETE"
    assert payload["preview"]["estimated_rows"] == 0


@pytest.mark.parametrize("db_type, db_uri, tenant_id", TEST_DATABASES)
def test_starter_questions_endpoint(db_type, db_uri, tenant_id):
    """The starter questions come from the database's own schema."""
    res = client.post("/starter_questions", json={"tenant_id": tenant_id, "db_uri": db_uri})
    assert res.status_code == 200

    questions = res.json()["questions"]
    assert len(questions) > 0
    assert all(q["question"].endswith("?") for q in questions)


@pytest.mark.parametrize("db_type, db_uri, tenant_id", TEST_DATABASES)
def test_run_sql_refuses_a_mutation(db_type, db_uri, tenant_id):
    """The manual SQL runner only runs reads."""
    table = get_test_table(db_uri)

    res = client.post("/run_sql", json={
        "sql": f"DELETE FROM {table}",
        "db_uri": db_uri,
    })
    assert res.status_code == 400
    assert "changes data" in res.json()["detail"].lower()


@pytest.mark.parametrize("db_type, db_uri, tenant_id", TEST_DATABASES)
def test_run_sql_returns_rows(db_type, db_uri, tenant_id):
    """A read written by hand comes back with columns and rows."""
    table = get_test_table(db_uri)

    res = client.post("/run_sql", json={
        "sql": f'SELECT * FROM "{table}" LIMIT 3',
        "db_uri": db_uri,
        "limit": 3,
    })
    assert res.status_code == 200

    payload = res.json()
    assert payload["success"] is True
    assert len(payload["result"]) <= 3
    assert payload["columns"]
