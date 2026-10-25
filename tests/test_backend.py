from fastapi.testclient import TestClient
import seaql.api as service
import seaql.database as tools
from seaql.model import ModelServiceError


def test_schema_and_connect_without_qdrant(database):
    client = TestClient(service.app)
    payload = {"tenant_id": "test", "db_uri": database}
    connected = client.post("/connect", json=payload)
    assert connected.status_code == 200
    assert connected.json()["table_count"] == 1
    assert client.post("/schema", json=payload).json()["tables"][0]["name"] == "orders"
    assert client.get("/").status_code == 200
    assert client.get("/health").json()["schema_source"] == "direct_sqlite"


def test_api_runs_actual_graph(monkeypatch, database):
    monkeypatch.setattr(
        "seaql.agent.complete",
        lambda messages: (
            '{"action":"sql","sql":"SELECT COUNT(*) AS count FROM orders"}',
            "test-model",
        ),
    )
    r = TestClient(service.app).post(
        "/chat", json={"query": "count", "tenant_id": "test", "db_uri": database}
    )
    assert r.status_code == 200
    assert r.json()["execution_result"] == [{"count": 3}]
    assert r.json()["model_id"] == "test-model"


def test_provider_error_returns_service_error(monkeypatch, database):
    def fail(*args):
        raise ModelServiceError("Model provider returned HTTP 429.", 429)

    monkeypatch.setattr(service, "run_agent", fail)
    r = TestClient(service.app).post(
        "/chat", json={"query": "count", "tenant_id": "test", "db_uri": database}
    )
    assert r.status_code == 429 and "rate limited" in r.json()["detail"]


def test_invalid_database_upload_is_rejected():
    r = TestClient(service.app).post(
        "/upload_db",
        files={
            "file": ("invalid.sqlite", b"not a database", "application/octet-stream")
        },
    )
    assert r.status_code == 400


def test_valid_upload(database):
    path = tools.database_path(database)
    r = TestClient(service.app).post(
        "/upload_db",
        files={
            "file": ("sample.sqlite", path.read_bytes(), "application/octet-stream")
        },
    )
    assert r.status_code == 200
    uploaded = tools.database_path(r.json()["db_uri"])
    try:
        assert tools.get_schema_json(r.json()["db_uri"])["success"]
    finally:
        uploaded.unlink()


def test_row_cap_is_marked(monkeypatch, database):
    monkeypatch.setattr(tools, "MAX_ROWS", 2)
    result = tools.execute_sql("SELECT * FROM orders", database)
    assert result["success"] and result["truncated"] and len(result["result"]) == 2


def test_existing_interface_endpoints(database):
    client = TestClient(service.app)
    request = {"tenant_id": "test", "db_uri": database}
    assert client.post("/starter_questions", json=request).json()["questions"]
    read = client.post(
        "/run_sql", json={"sql": "SELECT * FROM orders", "db_uri": database, "limit": 2}
    )
    assert (
        read.status_code == 200
        and read.json()["row_count"] == 2
        and read.json()["truncated"]
    )
    blocked = client.post(
        "/run_sql", json={"sql": "DELETE FROM orders", "db_uri": database}
    )
    assert blocked.status_code == 400
    preview = client.post(
        "/preview_sql",
        json={
            "sql": "DELETE FROM orders WHERE order_status='canceled'",
            "db_uri": database,
        },
    )
    assert (
        preview.status_code == 200 and preview.json()["preview"]["estimated_rows"] == 1
    )
    assert tools.execute_sql("SELECT COUNT(*) AS n FROM orders", database)[
        "result"
    ] == [{"n": 3}]
