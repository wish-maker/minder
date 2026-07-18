"""Unit tests for the plugin container-lifecycle control-plane
(scripts/setup/plugins.py).

Pure logic — .env flag semantics, the consumer-graph refcount + orphan detection,
and that enable/disable/reconcile funnel through `docker compose` with notify-then-
optional-stop teardown. No Docker and no live .env: a tmp .env plus a recording
compose stub. (`plugin` is python-only new logic, not a bash port, so a unit test
is the right tool where the parity gate doesn't apply.)
"""

import pytest

from scripts.setup import plugins


@pytest.fixture
def envfile(tmp_path, monkeypatch):
    """A throwaway .env wired into both readers: env.get (env module's ENV_FILE)
    and plugins._set_flag (plugins.ENV_FILE)."""
    p = tmp_path / ".env"
    p.write_text("", encoding="utf-8")
    monkeypatch.setattr(plugins.env, "ENV_FILE", p)
    monkeypatch.setattr(plugins, "ENV_FILE", p)
    monkeypatch.setattr(plugins.config, "DRY_RUN", False)
    return p


@pytest.fixture
def rec_compose(monkeypatch):
    """Record docker.compose(*args) calls instead of shelling out."""
    calls: list[tuple] = []
    monkeypatch.setattr(plugins.docker, "compose", lambda *a: calls.append(a) or 0)
    return calls


# ── .env flag semantics ───────────────────────────────────────────────────
def test_is_enabled_absent_defaults_true(envfile):
    assert plugins.is_enabled("telegraf") is True


def test_is_enabled_explicit_off(envfile):
    envfile.write_text("PLUGIN_TELEGRAF_ENABLED=0\n", encoding="utf-8")
    assert plugins.is_enabled("telegraf") is False


def test_set_flag_appends_when_absent(envfile):
    plugins._set_flag("telegraf", False)
    assert "PLUGIN_TELEGRAF_ENABLED=0" in envfile.read_text()


def test_set_flag_replaces_and_leaves_other_lines(envfile):
    envfile.write_text("A=1\nPLUGIN_TELEGRAF_ENABLED=1\nB=2\n", encoding="utf-8")
    plugins._set_flag("telegraf", False)
    text = envfile.read_text()
    assert "PLUGIN_TELEGRAF_ENABLED=0" in text
    assert "PLUGIN_TELEGRAF_ENABLED=1" not in text
    assert "A=1" in text and "B=2" in text  # untouched


def test_set_flag_dry_run_does_not_write(envfile, monkeypatch):
    monkeypatch.setattr(plugins.config, "DRY_RUN", True)
    plugins._set_flag("telegraf", False)
    assert envfile.read_text() == ""  # preview only — no mutation


# ── consumer-graph refcount / orphan detection (the "brain") ───────────────
def test_consumers_counts_core_and_plugins():
    # influxdb has a standing core consumer (grafana) → never orphaned.
    assert plugins._consumers("influxdb", set()) == {"grafana"}
    assert plugins._consumers("influxdb", {"telegraf"}) == {"telegraf", "grafana"}
    # telegraf (the container) has no core consumer → orphaned once no plugin needs it.
    assert plugins._consumers("telegraf", set()) == set()
    assert plugins._consumers("telegraf", {"telegraf"}) == {"telegraf"}


def test_orphans_after_disable_keeps_core_shared(envfile):
    # Disabling the only plugin: telegraf (container) orphans, influxdb does NOT
    # (grafana still consumes it) — derived from the graph, not a hardcoded list.
    assert plugins._orphans_after("telegraf") == ["telegraf"]


def test_influxdb_has_a_core_consumer():
    assert "grafana" in plugins.CORE_CONSUMERS.get("influxdb", ())


# ── enable / disable / reconcile funnel through compose ────────────────────
def test_enable_sets_flag_and_ups_deps(envfile, rec_compose):
    assert plugins.enable("telegraf") == 0
    assert "PLUGIN_TELEGRAF_ENABLED=1" in envfile.read_text()
    assert rec_compose == [("up", "-d", "influxdb", "telegraf")]


def test_disable_default_notifies_without_stopping(envfile, rec_compose):
    # notify-then-optional-stop: default leaves orphans running, no compose call.
    assert plugins.disable("telegraf") == 0
    assert "PLUGIN_TELEGRAF_ENABLED=0" in envfile.read_text()
    assert rec_compose == []  # nothing stopped without --stop-orphans


def test_disable_stop_orphans_stops_only_orphaned(envfile, rec_compose):
    assert plugins.disable("telegraf", stop_orphans=True) == 0
    # telegraf orphaned → stopped; influxdb kept (grafana consumer).
    assert rec_compose == [("stop", "telegraf")]


def test_reconcile_enabled_ups_only(monkeypatch, rec_compose):
    monkeypatch.setattr(plugins, "is_enabled", lambda n: True)
    assert plugins.reconcile() == 0
    assert rec_compose == [("up", "-d", "influxdb", "telegraf")]


def test_reconcile_disabled_reports_orphans_without_stopping(monkeypatch, rec_compose):
    monkeypatch.setattr(plugins, "is_enabled", lambda n: False)
    assert plugins.reconcile() == 0
    assert rec_compose == []  # orphan reported, not stopped


def test_reconcile_disabled_stop_orphans(monkeypatch, rec_compose):
    monkeypatch.setattr(plugins, "is_enabled", lambda n: False)
    assert plugins.reconcile(stop_orphans=True) == 0
    assert rec_compose == [("stop", "telegraf")]


# ── dispatch guards ────────────────────────────────────────────────────────
def test_run_rejects_unknown_action(envfile):
    assert plugins.run("frobnicate", "telegraf") == 1


def test_run_rejects_unknown_plugin(envfile):
    assert plugins.run("enable", "nope") == 1


def test_run_enable_requires_a_name(envfile):
    assert plugins.run("enable", "") == 1
