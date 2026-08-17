"""Unit tests filling ai_tools_importer.py's remaining coverage gaps (71%).

test_marketplace_ai_tools_importer.py already locks in the success/error
flag contract (#351), the required-flag persistence fix (#676), and the
stale-tool deactivation reconciliation. This adds everything else:
ai_tools' dict-format and invalid-type branches, a tool missing its 'name'
field, a non-dict param_def being skipped, enum/default persisted into the
schema, an invalid tool_type falling back to "analysis", the UPDATE branch
for an already-existing tool, deactivate_plugin_ai_tools called directly
(not just through the route layer), and sync_plugin_tools's own success/
exception paths.

Same direct-import pattern as the sibling suite (no core/config/routes
collision for this module -- it only imports shared.models.tiers and
core.database, both safe).
"""

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from services.marketplace.core.ai_tools_importer import (
    deactivate_plugin_ai_tools,
    import_ai_tools_from_manifest,
)

_SERVICE_DIR = Path(__file__).resolve().parents[2] / "src" / "services" / "marketplace"
_COLLISION_PRONE_NAMES = ("core", "routes", "models", "config")


def _isolated_import(*module_paths: str):
    """sync_plugin_tools does `from core.database import get_pool` INSIDE its
    own body -- a bare 'core' import that, in the normal test session, may
    already be bound (by conftest.py's own service-loading fixtures) to a
    DIFFERENT service's core module (conftest.py's own comment: "whichever
    service loads first ... wins that name for the rest of the session").
    Evict any stale bare-named modules and put ONLY marketplace's own
    directory on sys.path first, so `core.database` unambiguously resolves
    to marketplace's own module -- matching the pattern already established
    for this exact class of gotcha in test_marketplace_ai_tools_routes_coverage.py."""
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
    os.environ.setdefault("NEO4J_AUTH", "neo4j/test")

    import importlib

    try:
        return [importlib.import_module(p) for p in module_paths]
    finally:
        sys.path[:] = saved_path
        for name in _COLLISION_PRONE_NAMES:
            for key in list(sys.modules):
                if key == name or key.startswith(name + "."):
                    sys.modules.pop(key, None)
        sys.modules.update(saved_modules)


class _FakeConn:
    def __init__(self, fetchrow_result=None, execute_error=None, execute_result=None):
        self._fetchrow_result = fetchrow_result
        self._execute_error = execute_error
        self._execute_result = execute_result
        self.execute_calls = []

    async def fetchrow(self, *a, **k):
        return self._fetchrow_result

    async def execute(self, *a, **k):
        self.execute_calls.append((a, k))
        if self._execute_error:
            raise self._execute_error
        return self._execute_result


# --- ai_tools section shape handling ---------------------------------------


@pytest.mark.asyncio
async def test_ai_tools_dict_format_reads_the_tools_key():
    conn = _FakeConn()
    manifest = {"ai_tools": {"tools": [{"name": "get_price"}]}}

    result = await import_ai_tools_from_manifest(conn, "plugin-1", manifest)

    assert result["success"] is True
    assert result["tools_imported"] == 1


@pytest.mark.asyncio
async def test_ai_tools_dict_format_with_no_tools_key_imports_nothing():
    conn = _FakeConn()
    manifest = {"ai_tools": {}}

    result = await import_ai_tools_from_manifest(conn, "plugin-1", manifest)

    assert result["success"] is True
    assert result["tools_imported"] == 0


@pytest.mark.asyncio
async def test_ai_tools_invalid_type_returns_a_clean_error():
    conn = _FakeConn()
    manifest = {"ai_tools": "not-a-list-or-dict"}

    result = await import_ai_tools_from_manifest(conn, "plugin-1", manifest)

    assert result["success"] is False
    assert "must be a list or dict" in result["error"]


# --- per-tool validation -----------------------------------------------------


@pytest.mark.asyncio
async def test_tool_missing_name_is_recorded_as_an_error_and_skipped():
    conn = _FakeConn()
    manifest = {"ai_tools": [{"description": "no name here"}]}

    result = await import_ai_tools_from_manifest(conn, "plugin-1", manifest)

    assert result["success"] is False
    assert result["tools_imported"] == 0
    assert "missing 'name'" in result["errors"][0]
    assert conn.execute_calls == []  # never reached a write


# --- parameter schema construction -------------------------------------------


class _CaptureConn(_FakeConn):
    def __init__(self, **k):
        super().__init__(**k)
        self.calls = []

    async def execute(self, query, *args):
        self.calls.append((query, args))
        return "INSERT 0 1"


def _insert_params_schema(conn):
    insert_call = next(
        q for q in conn.calls if "INSERT INTO marketplace_ai_tools" in q[0]
    )
    return json.loads(insert_call[1][8])


@pytest.mark.asyncio
async def test_non_dict_param_def_is_skipped():
    conn = _CaptureConn()
    manifest = {
        "ai_tools": [
            {
                "name": "lookup",
                "parameters": {"weird": "not-a-dict", "target": {"type": "string"}},
            }
        ]
    }

    result = await import_ai_tools_from_manifest(conn, "plugin-1", manifest)

    assert result["success"] is True
    schema = _insert_params_schema(conn)
    assert "weird" not in schema
    assert "target" in schema


@pytest.mark.asyncio
async def test_enum_and_default_are_persisted_into_the_schema():
    conn = _CaptureConn()
    manifest = {
        "ai_tools": [
            {
                "name": "lookup",
                "parameters": {
                    "unit": {
                        "type": "string",
                        "enum": ["celsius", "fahrenheit"],
                        "default": "celsius",
                    }
                },
            }
        ]
    }

    result = await import_ai_tools_from_manifest(conn, "plugin-1", manifest)

    assert result["success"] is True
    schema = _insert_params_schema(conn)
    assert schema["unit"]["enum"] == ["celsius", "fahrenheit"]
    assert schema["unit"]["default"] == "celsius"


@pytest.mark.asyncio
async def test_invalid_tool_type_falls_back_to_analysis():
    conn = _CaptureConn()
    manifest = {"ai_tools": [{"name": "lookup", "type": "not-a-real-type"}]}

    result = await import_ai_tools_from_manifest(conn, "plugin-1", manifest)

    assert result["success"] is True
    insert_call = next(
        q for q in conn.calls if "INSERT INTO marketplace_ai_tools" in q[0]
    )
    tool_type = insert_call[1][4]  # 5th positional arg on the INSERT
    assert tool_type == "analysis"


# --- UPDATE branch for an already-existing tool ------------------------------


@pytest.mark.asyncio
async def test_existing_tool_is_updated_not_reinserted():
    conn = _CaptureConn(fetchrow_result={"id": "existing-uuid"})
    manifest = {"ai_tools": [{"name": "lookup", "description": "refreshed"}]}

    result = await import_ai_tools_from_manifest(conn, "plugin-1", manifest)

    assert result["success"] is True
    assert result["tools_imported"] == 1
    queries = [q for q, _ in conn.calls]
    assert any("UPDATE marketplace_ai_tools" in q for q in queries)
    assert not any("INSERT INTO marketplace_ai_tools" in q for q in queries)
    update_call = next(q for q in conn.calls if "UPDATE marketplace_ai_tools" in q[0])
    assert update_call[1][-1] == "existing-uuid"  # WHERE id = $9


# --- deactivate_plugin_ai_tools (direct, not through the route layer) -------


@pytest.mark.asyncio
async def test_deactivate_plugin_ai_tools_returns_the_parsed_count():
    conn = _FakeConn(execute_result="UPDATE 4")

    result = await deactivate_plugin_ai_tools(conn, "plugin-1")

    assert result == {"success": True, "tools_deactivated": 4}


@pytest.mark.asyncio
async def test_deactivate_plugin_ai_tools_defaults_to_zero_on_empty_result():
    conn = _FakeConn(execute_result=None)

    result = await deactivate_plugin_ai_tools(conn, "plugin-1")

    assert result == {"success": True, "tools_deactivated": 0}


# --- sync_plugin_tools (the public entry point) -------------------------------


class _FakeAcquireCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


class _FakePool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _FakeAcquireCtx(self._conn)


def _inject_fake_database_module(monkeypatch, get_pool_fn):
    """sync_plugin_tools's `from core.database import get_pool` is a LAZY
    import inside the function body -- by the time the test calls the
    function, _isolated_import's own cleanup has already evicted the real
    'core.database' from sys.modules, so a plain monkeypatch.setattr on a
    module reference obtained earlier never reaches the lookup the function
    actually performs at call time. Inject a minimal fake module directly
    into sys.modules instead, so the lazy import resolves to it via the
    import system's own sys.modules-cache short-circuit (same technique as
    test_marketplace_ai_tools_routes_coverage.py's _patch_lazy_importer)."""
    import types

    fake_core = types.ModuleType("core")
    fake_database = types.ModuleType("core.database")
    fake_database.get_pool = get_pool_fn
    monkeypatch.setitem(sys.modules, "core", fake_core)
    monkeypatch.setitem(sys.modules, "core.database", fake_database)


@pytest.mark.asyncio
async def test_sync_plugin_tools_returns_the_import_result(monkeypatch):
    (importer_mod,) = _isolated_import("core.ai_tools_importer")
    conn = _FakeConn()
    pool = _FakePool(conn)
    _inject_fake_database_module(monkeypatch, AsyncMock(return_value=pool))

    result = await importer_mod.sync_plugin_tools(
        "weather", "plugin-1", {"ai_tools": [{"name": "get_forecast"}]}
    )

    assert result["success"] is True
    assert result["tools_imported"] == 1


@pytest.mark.asyncio
async def test_sync_plugin_tools_masks_a_pool_acquisition_failure(monkeypatch):
    (importer_mod,) = _isolated_import("core.ai_tools_importer")

    async def boom():
        raise ConnectionError("db unreachable")

    _inject_fake_database_module(monkeypatch, boom)

    result = await importer_mod.sync_plugin_tools(
        "weather", "plugin-1", {"ai_tools": []}
    )

    assert result["success"] is False
    assert result["tools_imported"] == 0
    assert "db unreachable" in result["error"]
