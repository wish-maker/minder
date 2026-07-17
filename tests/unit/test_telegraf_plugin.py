"""Unit tests for the telegraf config-manager plugin (src/plugins/telegraf).

Pure-logic coverage — managed-region parsing, TOML validation, marker guards — with
a temp config file. No Docker: reload=False keeps every call off the docker socket.
"""

import asyncio

import pytest

from plugins.telegraf import TelegrafPlugin

_MARKERS = (
    "# >>> minder telegraf-plugin managed >>>\n"
    "# <<< minder telegraf-plugin managed <<<\n"
)
_BASE = '[agent]\n  interval = "10s"\n\n' + _MARKERS


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    p = tmp_path / "telegraf.conf"
    p.write_text(_BASE, encoding="utf-8")
    monkeypatch.setenv("TELEGRAF_CONFIG_PATH", str(p))
    return p


def test_register_and_health(cfg):
    pl = TelegrafPlugin({})
    md = asyncio.run(pl.register())
    assert md.name == "telegraf"
    assert "config-management" in md.capabilities
    assert asyncio.run(pl.health_check())["healthy"] is True


def test_empty_region_lists_no_inputs(cfg):
    pl = TelegrafPlugin({})
    assert pl._markers_present() is True
    assert pl.list_managed_inputs() == []


def test_set_managed_region_writes_and_parses(cfg):
    pl = TelegrafPlugin({})
    asyncio.run(
        pl.set_managed_region(
            "[[inputs.internal]]\n  collect_memstats = false", reload=False
        )
    )
    assert pl.list_managed_inputs() == ["internal"]
    # config outside the managed region is preserved
    assert "[agent]" in cfg.read_text(encoding="utf-8")


def test_bad_toml_rejected_without_writing(cfg):
    pl = TelegrafPlugin({})
    before = cfg.read_text(encoding="utf-8")
    with pytest.raises(ValueError):
        asyncio.run(pl.set_managed_region("[[x]] bad !!!", reload=False))
    assert cfg.read_text(encoding="utf-8") == before  # untouched — telegraf protected


def test_clear_restores_empty_region(cfg):
    pl = TelegrafPlugin({})
    asyncio.run(pl.set_managed_region("[[inputs.internal]]", reload=False))
    asyncio.run(pl.clear_managed_region(reload=False))
    assert pl.list_managed_inputs() == []


def test_missing_markers_are_guarded(tmp_path, monkeypatch):
    p = tmp_path / "telegraf.conf"
    p.write_text("[agent]\n", encoding="utf-8")  # no managed markers
    monkeypatch.setenv("TELEGRAF_CONFIG_PATH", str(p))
    pl = TelegrafPlugin({})
    assert pl._markers_present() is False
    assert pl.list_managed_inputs() == []
    with pytest.raises(RuntimeError):
        asyncio.run(pl.set_managed_region("[[inputs.internal]]", reload=False))


def test_actions_whitelist_is_read_only_safe(cfg):
    # ACTIONS must expose only the intended write/reload methods.
    assert TelegrafPlugin.ACTIONS == frozenset(
        {"set_managed_region", "clear_managed_region", "reload"}
    )
