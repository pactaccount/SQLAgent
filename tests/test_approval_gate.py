"""Offline contract tests for the demo's review gate."""

from fastapi.testclient import TestClient

import seaql.api as service


def test_approved_statement_is_server_owned_and_single_use(monkeypatch):
    executed = []
    monkeypatch.setattr(
        service,
        "run_agent",
        lambda *_: {
            "final_answer": "Review this statement",
            "sql_query": "DELETE FROM orders WHERE id = 1",
            "execution_result": [],
            "error_traces": [],
            "cached_result": False,
            "requires_approval": True,
        },
    )
    monkeypatch.setattr(
        "seaql.database.execute_sql",
        lambda sql, uri, bypass_approval=False: (
            executed.append((sql, uri, bypass_approval))
            or {"success": True, "result": [{"rows_affected": 1}]}
        ),
    )
    client = TestClient(service.app)
    response = client.post(
        "/chat",
        json={
            "query": "remove order 1",
            "tenant_id": "demo",
            "db_uri": "sqlite:///demo.db",
        },
    )
    approval_id = response.json()["approval_id"]
    assert approval_id
    assert (
        client.post(
            "/execute_approved",
            json={"sql": "DROP TABLE orders", "db_uri": "sqlite:///other.db"},
        ).status_code
        == 422
    )
    assert (
        client.post("/execute_approved", json={"approval_id": approval_id}).status_code
        == 200
    )
    assert executed == [("DELETE FROM orders WHERE id = 1", "sqlite:///demo.db", True)]
    assert (
        client.post("/execute_approved", json={"approval_id": approval_id}).status_code
        == 404
    )


def test_rejected_statement_cannot_execute(monkeypatch):
    monkeypatch.setattr(
        service,
        "run_agent",
        lambda *_: {
            "sql_query": "DELETE FROM orders",
            "requires_approval": True,
        },
    )
    client = TestClient(service.app)
    approval_id = client.post(
        "/chat",
        json={
            "query": "remove all",
            "tenant_id": "demo",
            "db_uri": "sqlite:///demo.db",
        },
    ).json()["approval_id"]
    assert (
        client.post("/reject_approved", json={"approval_id": approval_id}).status_code
        == 200
    )
    assert (
        client.post("/execute_approved", json={"approval_id": approval_id}).status_code
        == 404
    )
