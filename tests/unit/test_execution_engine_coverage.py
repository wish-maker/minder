"""Unit tests filling execution_engine.py's remaining coverage gaps (71%).

The sibling suites already cover TemplateEngine's rendering rules, the
secretRef fail-closed contract, and _handle_store_vector's empty-embeddings
guard. This adds everything else: the HTTP client's lazy-create/reuse and
close() lifecycle, execute_webhook_trigger's unknown-action-type branch, the
whole Qdrant collection-check/create/upsert happy path and each of its
failure branches (Ollama non-200, collection-create failure, upsert
failure), and the get_execution_engine/set_execution_engine module-level
singleton.

Same load-by-path pattern as the sibling suites (execution_engine.py only
imports stdlib + httpx, no package-qualified imports needing sys.path
tricks).
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
    spec = importlib.util.spec_from_file_location("execution_engine_coverage", _MOD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


engine_mod = _load()
ExecutionEngine = engine_mod.ExecutionEngine


# --- HTTP client lifecycle ----------------------------------------------------


@pytest.mark.asyncio
async def test_get_http_client_creates_once_and_reuses():
    engine = ExecutionEngine()
    assert engine.http_client is None

    client1 = await engine._get_http_client()
    client2 = await engine._get_http_client()

    assert client1 is client2
    assert engine.http_client is client1
    await engine.close()


@pytest.mark.asyncio
async def test_close_resets_the_client_to_none():
    engine = ExecutionEngine()
    await engine._get_http_client()
    assert engine.http_client is not None

    await engine.close()

    assert engine.http_client is None


@pytest.mark.asyncio
async def test_close_is_a_noop_when_never_created():
    engine = ExecutionEngine()
    await engine.close()  # must not raise
    assert engine.http_client is None


# --- execute_webhook_trigger: unknown action type ----------------------------


@pytest.mark.asyncio
async def test_unknown_action_type_returns_a_clean_error_result():
    engine = ExecutionEngine()
    manifest = {
        "metadata": {"name": "weird-plugin"},
        "spec": {"action": {"type": "delete-everything"}},
    }

    result = await engine.execute_webhook_trigger(manifest, {})

    assert result["status"] == "error"
    assert result["plugin"] == "weird-plugin"
    assert "Unknown action type" in result["error"]


# --- _handle_store_vector: full happy path + failure branches ----------------


class _FakeResponse:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or str(self._payload)

    def json(self):
        return self._payload


class _RoutedFakeClient:
    """Routes GET/PUT/POST by URL suffix so a single fake can drive the whole
    embed -> collection-check -> (maybe create) -> upsert pipeline."""

    def __init__(self, *, embed=None, get=None, put_create=None, put_upsert=None):
        self._embed = embed or _FakeResponse(200, {"embeddings": [[0.1, 0.2, 0.3]]})
        self._get = get if get is not None else _FakeResponse(200, {})
        self._put_create = put_create or _FakeResponse(200, {})
        self._put_upsert = put_upsert or _FakeResponse(200, {})
        self.calls = []

    async def post(self, url, **kwargs):
        self.calls.append(("POST", url))
        return self._embed

    async def get(self, url, **kwargs):
        self.calls.append(("GET", url))
        return self._get

    async def put(self, url, **kwargs):
        self.calls.append(("PUT", url))
        if "/points" in url:
            return self._put_upsert
        return self._put_create


_MANIFEST = {
    "metadata": {"name": "vec-plugin"},
    "spec": {
        "action": {
            "store": {
                "collection": "notes",
                "embedModel": "all-minilm",
                "input": {
                    "text": "{{ .msg }}",
                    "metadata": {"source": "{{ .src }}"},
                },
            }
        }
    },
}


@pytest.mark.asyncio
async def test_store_vector_full_success_when_collection_already_exists():
    client = _RoutedFakeClient(get=_FakeResponse(200, {}))
    engine = ExecutionEngine()
    engine.http_client = client

    result = await engine._handle_store_vector(
        _MANIFEST, {"msg": "hello world", "src": "webhook"}
    )

    assert result["collection"] == "notes"
    assert result["text_length"] == len("hello world")
    assert result["metadata"] == {"source": "webhook"}
    assert result["embedding_dim"] == 3
    assert "point_id" in result
    # Collection existed (200) -> no PUT to the bare collection URL, only the
    # points upsert PUT.
    create_calls = [u for m, u in client.calls if m == "PUT" and "/points" not in u]
    assert create_calls == []


@pytest.mark.asyncio
async def test_store_vector_creates_collection_when_missing():
    client = _RoutedFakeClient(get=_FakeResponse(404, {}))
    engine = ExecutionEngine()
    engine.http_client = client

    result = await engine._handle_store_vector(_MANIFEST, {"msg": "hi", "src": "x"})

    assert result["collection"] == "notes"
    create_calls = [u for m, u in client.calls if m == "PUT" and "/points" not in u]
    assert len(create_calls) == 1
    assert create_calls[0].endswith("/collections/notes")


@pytest.mark.asyncio
async def test_store_vector_empty_rendered_text_raises_valueerror():
    manifest = {
        "metadata": {"name": "vec-plugin"},
        "spec": {
            "action": {
                "store": {
                    "collection": "notes",
                    "input": {"text": ""},
                }
            }
        },
    }
    engine = ExecutionEngine()
    engine.http_client = _RoutedFakeClient()

    with pytest.raises(ValueError, match="rendered to empty string"):
        await engine._handle_store_vector(manifest, {})


@pytest.mark.asyncio
async def test_store_vector_ollama_non_200_raises_valueerror():
    client = _RoutedFakeClient(embed=_FakeResponse(500, text="ollama down"))
    engine = ExecutionEngine()
    engine.http_client = client

    with pytest.raises(ValueError, match="Ollama embedding failed"):
        await engine._handle_store_vector(_MANIFEST, {"msg": "hi", "src": "x"})


@pytest.mark.asyncio
async def test_store_vector_collection_create_failure_raises_valueerror():
    client = _RoutedFakeClient(
        get=_FakeResponse(404, {}), put_create=_FakeResponse(500, text="qdrant error")
    )
    engine = ExecutionEngine()
    engine.http_client = client

    with pytest.raises(ValueError, match="Failed to create collection"):
        await engine._handle_store_vector(_MANIFEST, {"msg": "hi", "src": "x"})


@pytest.mark.asyncio
async def test_store_vector_upsert_failure_raises_valueerror():
    client = _RoutedFakeClient(put_upsert=_FakeResponse(500, text="upsert error"))
    engine = ExecutionEngine()
    engine.http_client = client

    with pytest.raises(ValueError, match="Qdrant upsert failed"):
        await engine._handle_store_vector(_MANIFEST, {"msg": "hi", "src": "x"})


@pytest.mark.asyncio
async def test_execute_webhook_trigger_end_to_end_success():
    """Exercises the full trigger -> store-vector pipeline through the public
    entry point, not just _handle_store_vector directly."""
    client = _RoutedFakeClient()
    engine = ExecutionEngine()
    engine.http_client = client
    manifest = {
        "metadata": {"name": "vec-plugin"},
        "spec": {
            "trigger": {"webhook": {}},
            "action": {
                "type": "store-vector",
                "store": {
                    "collection": "notes",
                    "input": {"text": "{{ .msg }}"},
                },
            },
        },
    }

    result = await engine.execute_webhook_trigger(manifest, {"msg": "hello"})

    assert result["status"] == "success"
    assert result["plugin"] == "vec-plugin"
    assert result["action"] == "store-vector"
    assert result["result"]["collection"] == "notes"


# --- singleton: get_execution_engine / set_execution_engine ------------------


def test_get_execution_engine_creates_and_reuses_the_singleton(monkeypatch):
    monkeypatch.setattr(engine_mod, "_execution_engine", None)

    first = engine_mod.get_execution_engine()
    second = engine_mod.get_execution_engine()

    assert first is second
    assert isinstance(first, ExecutionEngine)


def test_set_execution_engine_overrides_the_singleton(monkeypatch):
    monkeypatch.setattr(engine_mod, "_execution_engine", None)
    custom = ExecutionEngine(qdrant_url="http://custom-qdrant:6333")

    engine_mod.set_execution_engine(custom)

    assert engine_mod.get_execution_engine() is custom
