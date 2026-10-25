"""The public demo must not expose provider traceback on quota exhaustion."""

from fastapi.testclient import TestClient

import seaql.api as app_module


def test_chat_reports_model_quota_as_retryable(monkeypatch):
    def exhausted(*_args, **_kwargs):
        raise RuntimeError("Gemini 429 quota exceeded")

    monkeypatch.setattr(app_module, "run_agent", exhausted)
    response = TestClient(app_module.app).post(
        "/chat",
        json={
            "query": "How many artists?",
            "tenant_id": "test",
            "db_uri": "sqlite:///test.db",
        },
    )
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"
    assert "rate limited" in response.json()["detail"]
    assert "Gemini" not in response.text
