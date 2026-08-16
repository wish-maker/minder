"""Unit tests for plugin-registry's core/plugin_loader.py (load_plugin_from_module).

Found in a background audit: plugins_db[plugin_name]/plugin_instances[plugin_name]
were mutated BEFORE update_plugin_in_database persisted -- the exact same ordering
bug already found and fixed this session in core/monitoring.py's
auto_enable_plugins (#351). update_plugin_in_database re-raises on failure (also
#351), so a DB hiccup during load left the plugin instance live in
plugin_instances (reachable by health checks/data collection/actions) with
nothing to show for it in the database -- silently dropped on the next restart's
reload from DB, or worse, live and untracked until the process dies. The fix
persists first and calls the already-register()ed/initialize()d instance's
shutdown() before propagating the failure, so nothing leaks as an untracked
live object.

Loaded via sys.path + a stale-cache clear, matching
test_plugin_registry_monitoring.py's precedent. load_plugin_from_module does a
real `importlib.import_module(f"plugins.{plugin_name}")` -- pre-registering a
fake module in sys.modules under that exact name lets import_module return it
straight from the cache with no real plugins/ package needed on disk.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

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


def _fake_metadata():
    return SimpleNamespace(
        name="testplugin",
        version="1.0.0",
        description="A test plugin",
        author="tester",
        dependencies=[],
        capabilities=[],
        data_sources=[],
        databases=[],
        registered_at=datetime.now(timezone.utc),
    )


class _FakePlugin:
    """Duck-typed plugin instance -- register/initialize/shutdown, matching the
    real plugin contract (src/plugins/_contract.py)."""

    def __init__(self, config):
        self.config = config
        self.shutdown_called = False

    async def register(self):
        return _fake_metadata()

    async def initialize(self):
        pass

    async def shutdown(self):
        self.shutdown_called = True


@pytest.fixture
def plugin_loader(monkeypatch):
    mod = _fresh_import("core.plugin_loader")
    fake_plugins_pkg = ModuleType("plugins")
    fake_plugin_module = ModuleType("plugins.testplugin")
    fake_plugin_module.__all__ = ["_FakePlugin"]
    fake_plugin_module._FakePlugin = _FakePlugin
    sys.modules["plugins"] = fake_plugins_pkg
    sys.modules["plugins.testplugin"] = fake_plugin_module

    # Best-effort side calls this test isn't exercising -- no-op them so a
    # missing DB/Redis/marketplace connection doesn't fail the test for an
    # unrelated reason.
    monkeypatch.setattr(mod, "load_plugin_config", AsyncMock(return_value={}))
    monkeypatch.setattr(mod.cfgmod, "apply_effective", lambda *a, **k: None)
    monkeypatch.setattr(mod, "sync_plugin_ai_tools", AsyncMock(return_value=None))

    try:
        yield mod
    finally:
        sys.modules.pop("plugins", None)
        sys.modules.pop("plugins.testplugin", None)


async def test_load_plugin_persists_before_registering_in_memory(
    plugin_loader, monkeypatch
):
    calls = []

    async def fake_update(name, **kwargs):
        calls.append(name)

    monkeypatch.setattr(plugin_loader, "update_plugin_in_database", fake_update)

    await plugin_loader.load_plugin_from_module(Path("testplugin"))

    assert calls == ["testplugin"]
    assert "testplugin" in plugin_loader.plugins_db
    assert "testplugin" in plugin_loader.plugin_instances


async def test_load_plugin_db_failure_does_not_register_in_memory(
    plugin_loader, monkeypatch
):
    """Regression guard: a DB failure here used to leave the plugin instance
    live in plugin_instances (reachable by health checks/data collection)
    with nothing persisted -- the two silently out of sync."""

    async def fake_update(name, **kwargs):
        raise RuntimeError("db connection lost")

    monkeypatch.setattr(plugin_loader, "update_plugin_in_database", fake_update)

    # load_plugin_from_module's own outer try/except logs and swallows --
    # confirmed by the absence of in-memory registration, not a raised exception.
    await plugin_loader.load_plugin_from_module(Path("testplugin"))

    assert "testplugin" not in plugin_loader.plugins_db
    assert "testplugin" not in plugin_loader.plugin_instances


async def test_load_plugin_shuts_down_instance_on_db_failure(
    plugin_loader, monkeypatch
):
    """The already-register()ed/initialize()d instance must be shut back down
    on a persist failure, not leaked as an untracked live object."""
    created_instances = []
    orig_init = _FakePlugin.__init__

    def _tracking_init(self, config):
        orig_init(self, config)
        created_instances.append(self)

    monkeypatch.setattr(_FakePlugin, "__init__", _tracking_init)

    async def fake_update(name, **kwargs):
        raise RuntimeError("db connection lost")

    monkeypatch.setattr(plugin_loader, "update_plugin_in_database", fake_update)

    await plugin_loader.load_plugin_from_module(Path("testplugin"))

    assert len(created_instances) == 1
    assert created_instances[0].shutdown_called is True


async def test_load_plugin_survives_a_config_apply_failure(plugin_loader, monkeypatch):
    """apply_effective (per-plugin centrally-managed config, #34) failing is a
    non-fatal degradation -- the plugin must still end up registered, not have
    the whole load aborted over a config-push hiccup."""

    async def fake_update(name, **kwargs):
        pass

    monkeypatch.setattr(plugin_loader, "update_plugin_in_database", fake_update)
    monkeypatch.setattr(
        plugin_loader.cfgmod,
        "apply_effective",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("bad config")),
    )

    await plugin_loader.load_plugin_from_module(Path("testplugin"))

    assert "testplugin" in plugin_loader.plugins_db
    assert "testplugin" in plugin_loader.plugin_instances


async def test_load_plugin_falls_back_to_a_register_method_when_no_dunder_all(
    plugin_loader,
):
    """Without __all__, the loader scans dir(module) for a class exposing
    register() that's actually DEFINED in this module (attr.__module__ ==
    module.__name__) -- not just imported into it. A module re-exporting some
    unrelated imported class with its own register()-shaped API (or the fake
    plugin class imported from elsewhere) must not be mistaken for the real
    plugin class."""
    fake_plugin_module = ModuleType("plugins.noall")
    # An imported class that happens to expose register() too -- must be
    # skipped precisely because its __module__ isn't "plugins.noall".
    fake_plugin_module.ImportedLookalike = _FakePlugin

    class RealPlugin:
        def __init__(self, config):
            self.config = config

        async def register(self):
            return _fake_metadata()

        async def initialize(self):
            pass

        async def shutdown(self):
            pass

    RealPlugin.__module__ = "plugins.noall"
    fake_plugin_module.RealPlugin = RealPlugin
    sys.modules["plugins.noall"] = fake_plugin_module

    async def fake_update(name, **kwargs):
        pass

    try:
        # Re-target update_plugin_in_database without going through the
        # module-scoped monkeypatch fixture (this test builds its own module).
        import unittest.mock as mock

        with mock.patch.object(plugin_loader, "update_plugin_in_database", fake_update):
            await plugin_loader.load_plugin_from_module(Path("noall"))
        # Registered under the directory name (not metadata.name) -- proves
        # RealPlugin, not ImportedLookalike, was the class actually picked.
        assert "noall" in plugin_loader.plugins_db
        assert isinstance(plugin_loader.plugin_instances["noall"], RealPlugin)
    finally:
        sys.modules.pop("plugins.noall", None)
        plugin_loader.plugins_db.pop("noall", None)
        plugin_loader.plugin_instances.pop("noall", None)


class TestLoadPluginsFromDisk:
    """load_plugins_from_disk (module-directory discovery), isolated from
    load_plugin_from_module -- monkeypatched to a call-recorder so these tests
    only lock down which directories get considered a plugin, not the load
    itself (already covered above)."""

    def _fresh(self, monkeypatch, plugins_path):
        mod = _fresh_import("core.plugin_loader")
        monkeypatch.setattr(mod.settings, "PLUGINS_PATH", str(plugins_path))
        return mod

    async def test_missing_plugins_path_is_a_noop(self, monkeypatch, tmp_path):
        mod = self._fresh(monkeypatch, tmp_path / "does-not-exist")
        calls = []
        monkeypatch.setattr(
            mod, "load_plugin_from_module", lambda d: calls.append(d.name)
        )

        await mod.load_plugins_from_disk()

        assert calls == []

    async def test_skips_non_directory_entries(self, monkeypatch, tmp_path):
        (tmp_path / "not_a_plugin.txt").write_text("hello")
        mod = self._fresh(monkeypatch, tmp_path)
        calls = []
        monkeypatch.setattr(
            mod, "load_plugin_from_module", lambda d: calls.append(d.name)
        )

        await mod.load_plugins_from_disk()

        assert calls == []

    async def test_skips_a_directory_with_no_init_py(self, monkeypatch, tmp_path):
        (tmp_path / "incomplete_plugin").mkdir()
        mod = self._fresh(monkeypatch, tmp_path)
        calls = []
        monkeypatch.setattr(
            mod, "load_plugin_from_module", lambda d: calls.append(d.name)
        )

        await mod.load_plugins_from_disk()

        assert calls == []

    async def test_loads_a_directory_with_an_init_py(self, monkeypatch, tmp_path):
        plugin_dir = tmp_path / "weather"
        plugin_dir.mkdir()
        (plugin_dir / "__init__.py").write_text("")
        mod = self._fresh(monkeypatch, tmp_path)
        calls = []

        async def fake_load(d):
            calls.append(d.name)

        monkeypatch.setattr(mod, "load_plugin_from_module", fake_load)

        await mod.load_plugins_from_disk()

        assert calls == ["weather"]
