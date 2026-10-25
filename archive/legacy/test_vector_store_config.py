"""Offline checks for explicit local mode and failed remote initialization."""
import os
os.environ['QDRANT_MODE'] = 'memory'
from types import SimpleNamespace
import pytest
import vector_store as module


def test_explicit_memory_ignores_cloud_credentials(monkeypatch):
    monkeypatch.setenv('QDRANT_MODE', 'memory')
    monkeypatch.setenv('QDRANT_URL', 'https://example.invalid')
    monkeypatch.setenv('QDRANT_API_KEY', 'not-a-key')
    monkeypatch.delenv('HF_TOKEN', raising=False)
    store=module.VectorStore()
    try:
        assert {c.name for c in store.client.get_collections().collections} == {'schema_metadata','semantic_cache'}
    finally:
        store.client.close()


def test_remote_failure_does_not_attempt_collection_creation(monkeypatch):
    calls=[]
    def fail():
        raise PermissionError('Forbidden')
    fake=SimpleNamespace(get_collections=fail,close=lambda:calls.append('close'),
                         create_collection=lambda **kw:calls.append('create'))
    monkeypatch.setenv('QDRANT_MODE','cloud')
    monkeypatch.setenv('QDRANT_URL','https://example.invalid')
    monkeypatch.setenv('QDRANT_API_KEY','not-a-key')
    monkeypatch.delenv('HF_TOKEN',raising=False)
    monkeypatch.setattr(module,'QdrantClient',lambda **kw:fake)
    with pytest.raises(RuntimeError,match='QDRANT_MODE=memory'):
        module.VectorStore()
    assert calls == ['close']
