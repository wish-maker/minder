"""Unit tests for rag-pipeline's PostgreSQL persistence layer
(repositories/pg_client.py, 13% coverage -- nothing in this file had ANY
dedicated test before; the little "coverage" that existed came only from other
test files short-circuiting through `if not conn: return False` via a mocked
get_pg_connection, never exercising a single real query-building/row-shaping
line.

Adds direct coverage of get_pg_connection's pool lifecycle (creation-once,
concurrent double-checked locking, creation failure), initialize_schema, and
every CRUD function's success/no-connection/exception branches, plus
load_*_from_postgres's row -> dict shaping (JSON parsing, array fallback,
malformed-JSON tolerance, datetime formatting).

Same sys.path + stale-cache-clear pattern as test_rag_pipeline_retrieval.py
(conftest.py loads every service's main.py into ONE shared pytest process, so
"config" is already cached as some OTHER service's module tree by the time
this file imports rag-pipeline's own).
"""

import asyncio
import importlib
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

_SERVICE_DIR = Path(__file__).resolve().parents[2] / "src" / "services" / "rag-pipeline"
_COLLISION_PRONE_NAMES = ("config", "repositories")


def _fresh_import():
    saved_path = list(sys.path)
    saved_modules = {}
    for name in _COLLISION_PRONE_NAMES:
        for key in list(sys.modules):
            if key == name or key.startswith(name + "."):
                saved_modules[key] = sys.modules.pop(key)

    sys.path.insert(0, str(_SERVICE_DIR))
    import os

    os.environ.setdefault("DB_PASSWORD", "test")
    os.environ.setdefault("REDIS_PASSWORD", "test")
    os.environ.setdefault("JWT_SECRET", "test")
    try:
        return importlib.import_module("repositories.pg_client")
    finally:
        sys.path[:] = saved_path
        for name in _COLLISION_PRONE_NAMES:
            for key in list(sys.modules):
                if key == name or key.startswith(name + "."):
                    sys.modules.pop(key, None)
        sys.modules.update(saved_modules)


pgc = _fresh_import()


@pytest.fixture(autouse=True)
def _reset_pool():
    pgc.pg_pool = None
    yield
    pgc.pg_pool = None


class _FakeAcquireCtx:
    def __init__(self, connection):
        self._connection = connection

    async def __aenter__(self):
        return self._connection

    async def __aexit__(self, *exc_info):
        return False


class _FakeConnection:
    def __init__(self, fetch_result=None, execute_error=None, fetch_error=None):
        self.executed = []
        self.fetch_result = fetch_result if fetch_result is not None else []
        self.execute_error = execute_error
        self.fetch_error = fetch_error

    async def execute(self, query, *args):
        if self.execute_error:
            raise self.execute_error
        self.executed.append((query, args))

    async def fetch(self, query, *args):
        if self.fetch_error:
            raise self.fetch_error
        return self.fetch_result


class _FakePool:
    def __init__(self, connection):
        self._connection = connection

    def acquire(self):
        return _FakeAcquireCtx(self._connection)


def _patch_conn(monkeypatch, connection):
    monkeypatch.setattr(
        pgc, "get_pg_connection", AsyncMock(return_value=_FakePool(connection))
    )
    return connection


def _patch_no_conn(monkeypatch):
    monkeypatch.setattr(pgc, "get_pg_connection", AsyncMock(return_value=None))


# ── get_pg_connection: availability + pool lifecycle ──────────────────────────


@pytest.mark.asyncio
async def test_get_pg_connection_returns_none_when_asyncpg_unavailable(monkeypatch):
    monkeypatch.setattr(pgc, "ASYNCPG_AVAILABLE", False)

    assert await pgc.get_pg_connection() is None


@pytest.mark.asyncio
async def test_get_pg_connection_creates_once_and_reuses(monkeypatch):
    import shared.db.pool as real_pool_mod

    sentinel_pool = object()
    create_spy = AsyncMock(return_value=sentinel_pool)
    monkeypatch.setattr(real_pool_mod, "create_pg_pool", create_spy)

    first = await pgc.get_pg_connection()
    second = await pgc.get_pg_connection()

    assert first is sentinel_pool
    assert second is sentinel_pool
    create_spy.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_pg_connection_wraps_and_reraises_creation_failure(monkeypatch):
    import shared.db.pool as real_pool_mod

    async def boom(**kwargs):
        raise ConnectionError("db unreachable")

    monkeypatch.setattr(real_pool_mod, "create_pg_pool", boom)

    with pytest.raises(ConnectionError):
        await pgc.get_pg_connection()

    assert pgc.pg_pool is None


@pytest.mark.asyncio
async def test_get_pg_connection_concurrent_first_callers_create_only_one_pool(
    monkeypatch,
):
    import shared.db.pool as real_pool_mod

    sentinel_pool = object()
    call_count = {"n": 0}
    started = asyncio.Event()
    proceed = asyncio.Event()

    async def slow_create_pg_pool(**kwargs):
        call_count["n"] += 1
        started.set()
        await proceed.wait()
        return sentinel_pool

    monkeypatch.setattr(real_pool_mod, "create_pg_pool", slow_create_pg_pool)

    task1 = asyncio.create_task(pgc.get_pg_connection())
    await started.wait()
    task2 = asyncio.create_task(pgc.get_pg_connection())
    await asyncio.sleep(0)
    proceed.set()

    result1 = await task1
    result2 = await task2

    assert result1 is sentinel_pool
    assert result2 is sentinel_pool
    assert call_count["n"] == 1


# ── initialize_schema ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_initialize_schema_false_when_no_connection(monkeypatch):
    _patch_no_conn(monkeypatch)

    assert await pgc.initialize_schema() is False


@pytest.mark.asyncio
async def test_initialize_schema_success(monkeypatch):
    import shared.db.schema as real_schema_mod

    _patch_conn(monkeypatch, _FakeConnection())
    apply_spy = AsyncMock()
    monkeypatch.setattr(real_schema_mod, "apply_schema", apply_spy)

    assert await pgc.initialize_schema() is True
    apply_spy.assert_awaited_once()


@pytest.mark.asyncio
async def test_initialize_schema_false_on_exception(monkeypatch):
    import shared.db.schema as real_schema_mod

    _patch_conn(monkeypatch, _FakeConnection())
    monkeypatch.setattr(
        real_schema_mod, "apply_schema", AsyncMock(side_effect=RuntimeError("boom"))
    )

    assert await pgc.initialize_schema() is False


# ── save_kb_to_postgres ────────────────────────────────────────────────────────

_KB_DATA = {
    "name": "docs",
    "description": "d",
    "embedding_model": "e",
    "llm_model": "l",
    "chunk_size": 500,
    "chunk_overlap": 50,
    "document_count": 3,
    "vector_count": 10,
}


@pytest.mark.asyncio
async def test_save_kb_false_when_no_connection(monkeypatch):
    _patch_no_conn(monkeypatch)
    assert await pgc.save_kb_to_postgres("kb-1", _KB_DATA) is False


@pytest.mark.asyncio
async def test_save_kb_success_executes_upsert(monkeypatch):
    connection = _patch_conn(monkeypatch, _FakeConnection())

    assert await pgc.save_kb_to_postgres("kb-1", _KB_DATA) is True
    (query, args) = connection.executed[0]
    assert "INSERT INTO knowledge_bases" in query
    assert args[0] == "kb-1"
    assert args[1] == "docs"


@pytest.mark.asyncio
async def test_save_kb_false_on_exception(monkeypatch):
    _patch_conn(monkeypatch, _FakeConnection(execute_error=RuntimeError("db down")))
    assert await pgc.save_kb_to_postgres("kb-1", _KB_DATA) is False


# ── delete_kb_from_postgres / delete_pipeline_from_postgres ───────────────────


@pytest.mark.asyncio
async def test_delete_kb_false_when_no_connection(monkeypatch):
    _patch_no_conn(monkeypatch)
    assert await pgc.delete_kb_from_postgres("kb-1") is False


@pytest.mark.asyncio
async def test_delete_kb_success(monkeypatch):
    connection = _patch_conn(monkeypatch, _FakeConnection())
    assert await pgc.delete_kb_from_postgres("kb-1") is True
    assert connection.executed[0][1] == ("kb-1",)


@pytest.mark.asyncio
async def test_delete_kb_false_on_exception(monkeypatch):
    _patch_conn(monkeypatch, _FakeConnection(execute_error=RuntimeError("boom")))
    assert await pgc.delete_kb_from_postgres("kb-1") is False


@pytest.mark.asyncio
async def test_delete_pipeline_false_when_no_connection(monkeypatch):
    _patch_no_conn(monkeypatch)
    assert await pgc.delete_pipeline_from_postgres("p-1") is False


@pytest.mark.asyncio
async def test_delete_pipeline_success(monkeypatch):
    connection = _patch_conn(monkeypatch, _FakeConnection())
    assert await pgc.delete_pipeline_from_postgres("p-1") is True
    assert connection.executed[0][1] == ("p-1",)


@pytest.mark.asyncio
async def test_delete_pipeline_false_on_exception(monkeypatch):
    _patch_conn(monkeypatch, _FakeConnection(execute_error=RuntimeError("boom")))
    assert await pgc.delete_pipeline_from_postgres("p-1") is False


# ── load_kb_from_postgres ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_load_kbs_empty_when_no_connection(monkeypatch):
    _patch_no_conn(monkeypatch)
    assert await pgc.load_kb_from_postgres() == {}


@pytest.mark.asyncio
async def test_load_kbs_shapes_rows_into_dicts(monkeypatch):
    class _FakeDatetime:
        def isoformat(self):
            return "2026-08-18T00:00:00+00:00"

    row = {
        "id": "kb-1",
        "name": "docs",
        "description": "d",
        "embedding_model": "e",
        "llm_model": "l",
        "chunk_size": 500,
        "chunk_overlap": 50,
        "chunking_strategy": "basic",
        "parent_size": 2000,
        "document_count": 3,
        "vector_count": 10,
        "owner_id": "alice",
        "visibility": "private",
        "created_at": _FakeDatetime(),
    }
    _patch_conn(monkeypatch, _FakeConnection(fetch_result=[row]))

    result = await pgc.load_kb_from_postgres()

    assert result["kb-1"]["name"] == "docs"
    assert result["kb-1"]["owner_id"] == "alice"
    assert result["kb-1"]["visibility"] == "private"
    assert result["kb-1"]["persisted"] is True
    assert result["kb-1"]["created_at"] == "2026-08-18T00:00:00+00:00"


@pytest.mark.asyncio
async def test_load_kbs_handles_null_created_at(monkeypatch):
    row = {
        "id": "kb-1",
        "name": "docs",
        "description": "d",
        "embedding_model": "e",
        "llm_model": "l",
        "chunk_size": 500,
        "chunk_overlap": 50,
        "chunking_strategy": "basic",
        "parent_size": 2000,
        "document_count": 3,
        "vector_count": 10,
        "owner_id": None,
        "visibility": "private",
        "created_at": None,
    }
    _patch_conn(monkeypatch, _FakeConnection(fetch_result=[row]))

    result = await pgc.load_kb_from_postgres()

    assert result["kb-1"]["created_at"] is None


@pytest.mark.asyncio
async def test_load_kbs_empty_on_exception(monkeypatch):
    _patch_conn(monkeypatch, _FakeConnection(fetch_error=RuntimeError("boom")))
    assert await pgc.load_kb_from_postgres() == {}


# ── save_pipeline_to_postgres ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_save_pipeline_false_when_no_connection(monkeypatch):
    _patch_no_conn(monkeypatch)
    data = {"name": "p", "knowledge_base_ids": ["kb-1"]}
    assert await pgc.save_pipeline_to_postgres("p-1", data) is False


@pytest.mark.asyncio
async def test_save_pipeline_serializes_kb_id_list_as_json(monkeypatch):
    import json as json_mod

    connection = _patch_conn(monkeypatch, _FakeConnection())
    data = {"name": "p", "knowledge_base_ids": ["kb-1", "kb-2"]}

    assert await pgc.save_pipeline_to_postgres("p-1", data) is True
    args = connection.executed[0][1]
    assert json_mod.loads(args[2]) == ["kb-1", "kb-2"]


@pytest.mark.asyncio
async def test_save_pipeline_stringifies_non_list_kb_ids(monkeypatch):
    connection = _patch_conn(monkeypatch, _FakeConnection())
    data = {"name": "p", "knowledge_base_ids": "kb-1"}

    await pgc.save_pipeline_to_postgres("p-1", data)
    args = connection.executed[0][1]
    assert args[2] == "kb-1"


@pytest.mark.asyncio
async def test_save_pipeline_false_on_exception(monkeypatch):
    _patch_conn(monkeypatch, _FakeConnection(execute_error=RuntimeError("boom")))
    data = {"name": "p", "knowledge_base_ids": []}
    assert await pgc.save_pipeline_to_postgres("p-1", data) is False


# ── load_pipelines_from_postgres ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_load_pipelines_empty_when_no_connection(monkeypatch):
    _patch_no_conn(monkeypatch)
    assert await pgc.load_pipelines_from_postgres() == {}


@pytest.mark.asyncio
async def test_load_pipelines_parses_json_kb_ids_and_configs(monkeypatch):
    class _FakeDatetime:
        def isoformat(self):
            return "2026-08-18T00:00:00+00:00"

    row = {
        "id": "p-1",
        "name": "pipe",
        "knowledge_base_ids": '["kb-1", "kb-2"]',
        "retrieval_config": '{"top_k": 5}',
        "generation_config": '{"temp": 0.7}',
        "owner_user_id": "alice",
        "created_at": _FakeDatetime(),
    }
    _patch_conn(monkeypatch, _FakeConnection(fetch_result=[row]))

    result = await pgc.load_pipelines_from_postgres()

    assert result["p-1"]["knowledge_base_ids"] == ["kb-1", "kb-2"]
    assert result["p-1"]["retrieval_config"] == {"top_k": 5}
    assert result["p-1"]["generation_config"] == {"temp": 0.7}
    assert result["p-1"]["owner_user_id"] == "alice"  # #943
    assert result["p-1"]["created_at"] == "2026-08-18T00:00:00+00:00"


@pytest.mark.asyncio
async def test_load_pipelines_falls_back_to_array_type_kb_ids(monkeypatch):
    row = {
        "id": "p-1",
        "name": "pipe",
        "knowledge_base_ids": ["kb-1", "kb-2"],  # real PG array, not a JSON string
        "retrieval_config": None,
        "generation_config": None,
        "owner_user_id": None,
        "created_at": None,
    }
    _patch_conn(monkeypatch, _FakeConnection(fetch_result=[row]))

    result = await pgc.load_pipelines_from_postgres()

    assert result["p-1"]["knowledge_base_ids"] == ["kb-1", "kb-2"]
    assert result["p-1"]["retrieval_config"] == {}
    assert result["p-1"]["generation_config"] == {}


@pytest.mark.asyncio
async def test_load_pipelines_tolerates_malformed_kb_ids_json(monkeypatch):
    row = {
        "id": "p-1",
        "name": "pipe",
        "knowledge_base_ids": "not valid json",
        "retrieval_config": None,
        "generation_config": None,
        "owner_user_id": None,
        "created_at": None,
    }
    _patch_conn(monkeypatch, _FakeConnection(fetch_result=[row]))

    result = await pgc.load_pipelines_from_postgres()

    assert result["p-1"]["knowledge_base_ids"] == []


@pytest.mark.asyncio
async def test_load_pipelines_empty_kb_ids_is_empty_list(monkeypatch):
    row = {
        "id": "p-1",
        "name": "pipe",
        "knowledge_base_ids": None,
        "retrieval_config": None,
        "generation_config": None,
        "owner_user_id": None,
        "created_at": None,
    }
    _patch_conn(monkeypatch, _FakeConnection(fetch_result=[row]))

    result = await pgc.load_pipelines_from_postgres()

    assert result["p-1"]["knowledge_base_ids"] == []


@pytest.mark.asyncio
async def test_load_pipelines_empty_on_exception(monkeypatch):
    _patch_conn(monkeypatch, _FakeConnection(fetch_error=RuntimeError("boom")))
    assert await pgc.load_pipelines_from_postgres() == {}


# ── save_session_to_postgres ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_save_session_false_when_no_connection(monkeypatch):
    _patch_no_conn(monkeypatch)
    assert await pgc.save_session_to_postgres("s-1", {}) is False


@pytest.mark.asyncio
async def test_save_session_success(monkeypatch):
    connection = _patch_conn(monkeypatch, _FakeConnection())

    result = await pgc.save_session_to_postgres(
        "s-1", {"user_id": "u1", "pipeline_id": "p-1", "message_count": 2}
    )

    assert result is True
    args = connection.executed[0][1]
    assert args[0] == "s-1"
    assert args[1] == "u1"
    assert args[3] == 2


@pytest.mark.asyncio
async def test_save_session_false_on_exception(monkeypatch):
    _patch_conn(monkeypatch, _FakeConnection(execute_error=RuntimeError("boom")))
    assert await pgc.save_session_to_postgres("s-1", {}) is False


# ── save_conversation_turn_to_postgres ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_save_conversation_turn_false_when_no_connection(monkeypatch):
    _patch_no_conn(monkeypatch)
    assert await pgc.save_conversation_turn_to_postgres("s-1", "t-1", "q", "a") is False


@pytest.mark.asyncio
async def test_save_conversation_turn_success_with_optional_fields(monkeypatch):
    connection = _patch_conn(monkeypatch, _FakeConnection())

    result = await pgc.save_conversation_turn_to_postgres(
        "s-1",
        "t-1",
        "question",
        "answer",
        sources=[{"doc": "d1"}],
        confidence=0.9,
        embedding=[0.1, 0.2],
    )

    assert result is True
    args = connection.executed[0][1]
    assert args[0] == "s-1" and args[1] == "t-1"
    assert args[5] == 0.9
    assert args[6] == [0.1, 0.2]


@pytest.mark.asyncio
async def test_save_conversation_turn_false_on_exception(monkeypatch):
    _patch_conn(monkeypatch, _FakeConnection(execute_error=RuntimeError("boom")))
    assert await pgc.save_conversation_turn_to_postgres("s-1", "t-1", "q", "a") is False
