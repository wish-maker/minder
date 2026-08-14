"""Unit tests for plugin-registry's background loops (core/monitoring.py).

health_check_loop/data_collection_scheduler/auto_enable_plugins had zero direct
test coverage -- found via a coverage audit, not a reported bug. Each is a
`while True` background task with real, documented behavior worth locking in:
health_check_loop snapshots `plugin_instances.items()` into a `list()` specifically
to survive a concurrent plugin uninstall during iteration (its own comment explains
why), and all three isolate a single plugin's failure so it doesn't take down
monitoring/collection/enablement for every other plugin.

Loaded via sys.path + a stale-cache clear, matching test_plugin_registry_webhook_
persistence.py's precedent: monitoring.py does `from core.database import
update_plugin_in_database` and `from core.state import ...`, package-qualified
imports that need the real plugin-registry package tree on sys.path.

Each `while True` loop is run for exactly one real iteration by patching
`asyncio.sleep` to succeed once then raise a sentinel exception -- the loop's
own `await asyncio.sleep(...)` call is what stops it, so the test observes
real production control flow, not a truncated/refactored copy of it.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

_SERVICE_DIR = (
    Path(__file__).resolve().parents[2] / "src" / "services" / "plugin-registry"
)


def _fresh_import(module_path: str):
    sys.path.insert(0, str(_SERVICE_DIR))
    for stale in list(sys.modules):
        if (
            stale == "core"
            or stale.startswith("core.")
            or stale in ("config", "models")
        ):
            del sys.modules[stale]
    import importlib

    return importlib.import_module(module_path)


monitoring = _fresh_import("core.monitoring")


class _StopTestLoop(Exception):
    """Sentinel raised by the fake sleep to end a `while True` loop after N
    real iterations, without touching the loop's own source."""


def _sleep_after(n_ok_calls: int):
    calls = {"n": 0}

    async def fake_sleep(*_a, **_k):
        calls["n"] += 1
        if calls["n"] > n_ok_calls:
            raise _StopTestLoop()

    return fake_sleep


class _Plugin:
    """Minimal stand-in for a live plugin instance -- health_check_loop/
    data_collection_scheduler only ever call these two methods on it."""

    def __init__(self, health=None, health_error=None, collect_error=None, records=3):
        self._health = health if health is not None else {"healthy": True}
        self._health_error = health_error
        self._collect_error = collect_error
        self._records = records
        self.health_check_calls = 0
        self.collect_calls = 0

    async def health_check(self):
        self.health_check_calls += 1
        if self._health_error:
            raise self._health_error
        return self._health

    async def collect_data(self):
        self.collect_calls += 1
        if self._collect_error:
            raise self._collect_error
        return {"records_collected": self._records}


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    monitoring.plugins_db.clear()
    monitoring.plugin_instances.clear()
    monkeypatch.setattr(monitoring, "redis_client", MagicMock())
    monkeypatch.setattr(monitoring, "update_plugin_in_database", AsyncMock())
    yield
    monitoring.plugins_db.clear()
    monitoring.plugin_instances.clear()


def _plugin_info(status="registered"):
    from types import SimpleNamespace

    return SimpleNamespace(health_status=None, last_health_check=None, status=status)


async def test_health_check_loop_marks_healthy_plugin(monkeypatch):
    plugin = _Plugin(health={"healthy": True})
    info = _plugin_info()
    monitoring.plugin_instances["weather"] = plugin
    monitoring.plugins_db["weather"] = info
    monkeypatch.setattr(monitoring.asyncio, "sleep", _sleep_after(0))

    with pytest.raises(_StopTestLoop):
        await monitoring.health_check_loop()

    assert plugin.health_check_calls == 1
    assert info.health_status == "healthy"
    assert info.last_health_check is not None
    monitoring.update_plugin_in_database.assert_awaited_once()


async def test_health_check_loop_marks_unhealthy_plugin(monkeypatch):
    plugin = _Plugin(health={"healthy": False})
    info = _plugin_info()
    monitoring.plugin_instances["weather"] = plugin
    monitoring.plugins_db["weather"] = info
    monkeypatch.setattr(monitoring.asyncio, "sleep", _sleep_after(0))

    with pytest.raises(_StopTestLoop):
        await monitoring.health_check_loop()

    assert info.health_status == "unhealthy"


async def test_health_check_loop_isolates_one_plugin_failure(monkeypatch):
    # A failing health_check() for one plugin must not stop the others from
    # being checked in the same pass, and must land as "error" not a crash.
    failing = _Plugin(health_error=RuntimeError("boom"))
    healthy = _Plugin(health={"healthy": True})
    monitoring.plugin_instances["broken"] = failing
    monitoring.plugin_instances["fine"] = healthy
    monitoring.plugins_db["broken"] = _plugin_info()
    monitoring.plugins_db["fine"] = _plugin_info()
    monkeypatch.setattr(monitoring.asyncio, "sleep", _sleep_after(0))

    with pytest.raises(_StopTestLoop):
        await monitoring.health_check_loop()

    assert monitoring.plugins_db["broken"].health_status == "error"
    assert monitoring.plugins_db["fine"].health_status == "healthy"
    assert healthy.health_check_calls == 1  # the other plugin still ran


async def test_data_collection_scheduler_isolates_one_plugin_failure(monkeypatch):
    failing = _Plugin(collect_error=RuntimeError("collector down"))
    healthy = _Plugin(records=7)
    monitoring.plugin_instances["broken"] = failing
    monitoring.plugin_instances["fine"] = healthy
    monitoring.plugins_db["broken"] = _plugin_info(status="enabled")
    monitoring.plugins_db["broken"].enabled = True
    monitoring.plugins_db["fine"] = _plugin_info(status="enabled")
    monitoring.plugins_db["fine"].enabled = True
    # First sleep (the initial `await asyncio.sleep(3600)`) must succeed so the
    # collection body actually runs; the second call ends the loop.
    monkeypatch.setattr(monitoring.asyncio, "sleep", _sleep_after(1))

    with pytest.raises(_StopTestLoop):
        await monitoring.data_collection_scheduler()

    assert failing.collect_calls == 1
    assert healthy.collect_calls == 1  # ran despite the other plugin's failure


async def test_data_collection_scheduler_skips_disabled_plugins(monkeypatch):
    plugin = _Plugin()
    monitoring.plugin_instances["weather"] = plugin
    info = _plugin_info(status="disabled")
    info.enabled = False
    monitoring.plugins_db["weather"] = info
    monkeypatch.setattr(monitoring.asyncio, "sleep", _sleep_after(1))

    with pytest.raises(_StopTestLoop):
        await monitoring.data_collection_scheduler()

    assert plugin.collect_calls == 0


async def test_auto_enable_plugins_isolates_one_persist_failure():
    ok_info = _plugin_info()
    ok_info.enabled = False
    bad_info = _plugin_info()
    bad_info.enabled = False
    monitoring.plugins_db["ok"] = ok_info
    monitoring.plugins_db["bad"] = bad_info

    async def fake_update(name, **kwargs):
        if name == "bad":
            raise RuntimeError("db down")

    monitoring.update_plugin_in_database.side_effect = fake_update

    await monitoring.auto_enable_plugins()

    # The successfully-persisted plugin is marked enabled in-memory...
    assert ok_info.enabled is True
    assert ok_info.status == "enabled"
    # ...but the one whose DB persist failed must NOT be -- mirrors #351's fix
    # to routes/plugins.py's enable_plugin (persist before mutating in-memory
    # state), so a failed auto-enable at startup can't leave the in-memory
    # cache claiming "enabled" for a plugin the database never recorded.
    assert bad_info.enabled is False
    assert bad_info.status != "enabled"
