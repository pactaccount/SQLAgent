from types import SimpleNamespace
import pytest
import seaql.model as gateway


def test_api_uses_configured_key_and_model(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "test-secret")
    monkeypatch.setenv("NVIDIA_MODEL", "test-model")
    seen = {}

    def post(url, **kwargs):
        seen.update(url=url, **kwargs)
        return SimpleNamespace(
            ok=True,
            json=lambda: {
                "choices": [
                    {
                        "message": {
                            "content": '{"action":"clarify","question":"Which year?"}'
                        }
                    }
                ],
                "model": "served-model",
            },
        )

    monkeypatch.setattr(gateway.requests, "post", post)
    text, model = gateway.complete([{"role": "user", "content": "test"}])
    assert model == "served-model"
    assert seen["headers"]["Authorization"] == "Bearer test-secret"
    assert seen["json"]["model"] == "test-model"
    assert "extra_body" not in seen["json"]


@pytest.mark.parametrize("status", [401, 403, 404, 429, 503])
def test_provider_errors_are_redacted(monkeypatch, status):
    monkeypatch.setenv("NVIDIA_API_KEY", "test-secret")
    monkeypatch.setattr(
        gateway.requests,
        "post",
        lambda *a, **k: SimpleNamespace(
            ok=False, status_code=status, text="secret-body"
        ),
    )
    with pytest.raises(gateway.ModelServiceError) as error:
        gateway.complete([])
    assert error.value.status_code == status
    assert "secret" not in str(error.value)
