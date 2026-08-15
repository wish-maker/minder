"""Unit test for _handle_store_vector's embedding-response guard (plugin-registry).

The webhook store-vector path calls Ollama's /api/embed and read the first
embedding. A 200 response whose `embeddings` array is empty/missing (a malformed
Ollama reply) used to hit `[...][0]` and raise an opaque IndexError; it now raises a
clear ValueError, the same shape as the existing status-code guard.

execution_engine imports only stdlib + httpx, so it loads by path (hyphenated svc
dir) with no injection -- matches test_execution_engine_template.py's precedent.
"""

import importlib.util
from pathlib import Path

import pytest

_MOD = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "services"
    / "plugin-registry"
    / "core"
    / "execution_engine.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("execution_engine_store_vector", _MOD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ExecutionEngine = _load().ExecutionEngine


class _FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, embed_payload):
        self._embed_payload = embed_payload

    async def post(self, url, **kwargs):
        # Only the /api/embed call is exercised before the guard trips.
        return _FakeResponse(200, self._embed_payload)


_MANIFEST = {
    "metadata": {"name": "vec-plugin"},
    "spec": {
        "action": {
            "store": {
                "collection": "c1",
                "embedModel": "all-minilm",
                "input": {"text": "{{ .msg }}"},
            }
        }
    },
}


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [{"embeddings": []}, {}, {"embeddings": None}])
async def test_store_vector_empty_embeddings_raises_clear_valueerror(
    monkeypatch, payload
):
    engine = ExecutionEngine()

    async def _fake_get_http_client():
        return _FakeClient(payload)

    monkeypatch.setattr(engine, "_get_http_client", _fake_get_http_client)

    with pytest.raises(ValueError, match="no embeddings"):
        await engine._handle_store_vector(_MANIFEST, {"msg": "hello world"})
