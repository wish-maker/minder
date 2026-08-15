"""Unit tests for marketplace's AI-tools manifest importer (#351).

#351: import_ai_tools_from_manifest() used to return success=True
unconditionally, even when every tool in the manifest failed to import
(imported_count == 0, errors full). The /sync route returned this dict as-is
with HTTP 200, so a total DB-write failure read as a clean sync at every
layer -- including plugin-registry's caller, which only checks the HTTP
status code.

No DB: the asyncpg connection is stubbed.
"""

import pytest

from services.marketplace.core.ai_tools_importer import import_ai_tools_from_manifest


class _FakeConn:
    def __init__(self, fetchrow_result=None, execute_error=None):
        self._fetchrow_result = fetchrow_result
        self._execute_error = execute_error
        self.execute_calls = 0

    async def fetchrow(self, *a, **k):
        return self._fetchrow_result

    async def execute(self, *a, **k):
        self.execute_calls += 1
        if self._execute_error:
            raise self._execute_error


@pytest.mark.asyncio
async def test_success_true_when_every_tool_imports_cleanly():
    conn = _FakeConn()
    manifest = {"ai_tools": [{"name": "get_price"}, {"name": "get_forecast"}]}

    result = await import_ai_tools_from_manifest(conn, "plugin-1", manifest)

    assert result["success"] is True
    assert result["tools_imported"] == 2
    assert result["errors"] == []


@pytest.mark.asyncio
async def test_success_false_when_every_tool_fails():
    conn = _FakeConn(execute_error=RuntimeError("db write failed"))
    manifest = {"ai_tools": [{"name": "get_price"}]}

    result = await import_ai_tools_from_manifest(conn, "plugin-1", manifest)

    assert result["success"] is False
    assert result["tools_imported"] == 0
    assert result["errors"]


@pytest.mark.asyncio
async def test_success_false_on_partial_failure():
    """Even one failure among several tools must flip success to False --
    a caller only checking `success` must not miss a partial write failure."""
    calls = {"n": 0}

    class _PartialFailConn(_FakeConn):
        async def execute(self, *a, **k):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("db write failed")

    conn = _PartialFailConn()
    manifest = {
        "ai_tools": [
            {"name": "get_price"},
            {"name": "get_forecast"},
            {"name": "get_news"},
        ]
    }

    result = await import_ai_tools_from_manifest(conn, "plugin-1", manifest)

    assert result["success"] is False
    assert result["tools_imported"] == 2
    assert len(result["errors"]) == 1


@pytest.mark.asyncio
async def test_success_true_when_manifest_has_no_ai_tools_section():
    conn = _FakeConn()
    result = await import_ai_tools_from_manifest(conn, "plugin-1", {})
    assert result["success"] is True
    assert result["tools_imported"] == 0


class _StatefulConn:
    """Models one plugin's existing marketplace_ai_tools rows (name -> active)
    so the stale-tool-deactivation UPDATE has real rows to act against."""

    def __init__(self, existing_active_tool_names):
        self.active = {name: True for name in existing_active_tool_names}
        self.deactivate_calls = 0

    async def fetchrow(self, *a, **k):
        return None  # every synced tool takes the INSERT branch

    async def execute(self, query, *args):
        if "NOT (tool_name = ANY" in query:
            self.deactivate_calls += 1
            _plugin_id, synced_names = args
            stale = [n for n, on in self.active.items() if on and n not in synced_names]
            for n in stale:
                self.active[n] = False
            return f"UPDATE {len(stale)}"
        return "INSERT 0 1"


@pytest.mark.asyncio
async def test_tool_dropped_from_manifest_is_deactivated_not_left_active_forever():
    """A plugin author renaming/removing a tool must not leave the old row
    active=TRUE forever -- sync was previously purely additive, so a stale
    tool kept being served as live by GET /v1/marketplace/ai/tools."""
    conn = _StatefulConn(existing_active_tool_names=["get_price", "old_forecast_tool"])
    manifest = {"ai_tools": [{"name": "get_price"}]}  # old_forecast_tool dropped

    result = await import_ai_tools_from_manifest(conn, "plugin-1", manifest)

    assert result["success"] is True
    assert result["tools_deactivated"] == 1
    assert conn.active["old_forecast_tool"] is False
    assert conn.active["get_price"] is True
    assert conn.deactivate_calls == 1


@pytest.mark.asyncio
async def test_stale_deactivation_skipped_when_sync_had_errors():
    """A tool that merely FAILED to sync this round (still present in the
    manifest, just a transient error) must not be mistaken for one removed
    from it and deactivated alongside genuinely-stale tools."""
    conn = _StatefulConn(existing_active_tool_names=["get_price", "flaky_tool"])

    class _FlakyOnSecond(_StatefulConn):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self._n = 0

        async def execute(self, query, *args):
            if "NOT (tool_name = ANY" in query:
                return await super().execute(query, *args)
            self._n += 1
            if self._n == 2:
                raise RuntimeError("db write failed")
            return "INSERT 0 1"

    conn = _FlakyOnSecond(existing_active_tool_names=["get_price", "flaky_tool"])
    manifest = {"ai_tools": [{"name": "get_price"}, {"name": "flaky_tool"}]}

    result = await import_ai_tools_from_manifest(conn, "plugin-1", manifest)

    assert result["success"] is False
    assert result["tools_deactivated"] == 0
    assert conn.deactivate_calls == 0
    assert conn.active["flaky_tool"] is True  # never touched, sync just errored
