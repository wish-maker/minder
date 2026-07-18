"""Unit tests for the plugin container-lifecycle control-plane
(scripts/setup/plugins.py).

Pure logic only — .env flag semantics, the owned/shared refcount partition, and
that every mutating action funnels through `docker compose`. No Docker and no live
.env: a tmp .env plus a recording compose stub. (The setup CLI is otherwise
verified by the bash-parity gate, but `plugin` is python-only new logic, not a
port, so a unit test is the right tool.)
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


def test_is_enabled_explicit_on(envfile):
    envfile.write_text("PLUGIN_TELEGRAF_ENABLED=1\n", encoding="utf-8")
    assert plugins.is_enabled("telegraf") is True


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


# ── owned/shared refcount partition ────────────────────────────────────────
def test_partition_all_enabled_brings_up_owned_and_shared(monkeypatch):
    monkeypatch.setattr(plugins, "is_enabled", lambda n: True)
    up, down = plugins._partition()
    assert up == {"telegraf", "influxdb"}
    assert down == set()


def test_partition_disabled_stops_owned_keeps_core_shared(monkeypatch):
    monkeypatch.setattr(plugins, "is_enabled", lambda n: False)
    up, down = plugins._partition()
    assert up == set()
    assert down == {"telegraf"}          # owned → torn down
    assert "influxdb" not in down         # core-shared datastore → never torn down


def test_influxdb_is_core_shared():
    # Guard the invariant the partition relies on.
    assert "influxdb" in plugins.CORE_SHARED


# ── reconcile / enable / disable funnel through compose ─────────────────────
def test_reconcile_enabled_ups_only(monkeypatch, rec_compose):
    monkeypatch.setattr(plugins, "is_enabled", lambda n: True)
    assert plugins.reconcile() == 0
    assert rec_compose == [("up", "-d", "influxdb", "telegraf")]


def test_reconcile_disabled_stops_only(monkeypatch, rec_compose):
    monkeypatch.setattr(plugins, "is_enabled", lambda n: False)
    assert plugins.reconcile() == 0
    assert rec_compose == [("stop", "telegraf")]


def test_enable_sets_flag_and_ups(envfile, rec_compose):
    assert plugins.enable("telegraf") == 0
    assert "PLUGIN_TELEGRAF_ENABLED=1" in envfile.read_text()
    assert rec_compose == [("up", "-d", "influxdb", "telegraf")]


def test_disable_stops_owned_keeps_shared(envfile, rec_compose):
    assert plugins.disable("telegraf") == 0
    assert "PLUGIN_TELEGRAF_ENABLED=0" in envfile.read_text()
    assert rec_compose == [("stop", "telegraf")]  # influxdb (shared) left running


# ── dispatch guards ────────────────────────────────────────────────────────
def test_run_rejects_unknown_action(envfile):
    assert plugins.run("frobnicate", "telegraf") == 1


def test_run_rejects_unknown_plugin(envfile):
    assert plugins.run("enable", "nope") == 1


def test_run_enable_requires_a_name(envfile):
    assert plugins.run("enable", "") == 1
