"""Unit tests for the bundle control-plane (scripts/setup/bundles.py).

Pure logic — bundles.state.json enable semantics, the claim-graph refcount + orphan
detection, and that enable/disable/reconcile funnel through `docker compose` with
notify-then-optional-stop teardown. No Docker and no live state: a tmp state file
plus a recording compose stub. (`bundle` is python-only new logic, not a bash port,
so a unit test is the right tool where the parity gate doesn't apply.)
"""

import json

import pytest

from scripts.setup import bundles

# monitoring's claimed services (exclusive to it), and every claimed service —
# both sorted, the order enable/reconcile emit them.
MON = tuple(sorted(bundles.BUNDLES["monitoring"]["claims"]))
ALL = tuple(sorted({s for b in bundles.BUNDLES for s in bundles.BUNDLES[b]["claims"]}))


@pytest.fixture
def statefile(tmp_path, monkeypatch):
    """A throwaway bundles.state.json wired into the module's STATE_FILE."""
    p = tmp_path / "bundles.state.json"
    monkeypatch.setattr(bundles, "STATE_FILE", p)
    monkeypatch.setattr(bundles.config, "DRY_RUN", False)
    return p


@pytest.fixture
def rec_compose(monkeypatch):
    """Record docker.compose(*args) calls instead of shelling out."""
    calls: list[tuple] = []
    monkeypatch.setattr(bundles.docker, "compose", lambda *a: calls.append(a) or 0)
    return calls


# ── bundles.state.json enable semantics ────────────────────────────────────
def test_is_enabled_absent_defaults_true(statefile):
    assert not statefile.exists()  # missing file → everything enabled
    assert bundles.is_enabled("monitoring") is True


def test_is_enabled_explicit_off(statefile):
    statefile.write_text(
        json.dumps({"monitoring": {"enabled": False}}), encoding="utf-8"
    )
    assert bundles.is_enabled("monitoring") is False


def test_is_enabled_corrupt_file_defaults_true(statefile):
    statefile.write_text("{not valid json", encoding="utf-8")
    assert bundles.is_enabled("monitoring") is True


def test_set_enabled_writes_json(statefile):
    bundles._set_enabled("monitoring", False)
    assert json.loads(statefile.read_text())["monitoring"]["enabled"] is False


def test_set_enabled_merges_without_clobbering_others(statefile):
    statefile.write_text(json.dumps({"other": {"enabled": False}}), encoding="utf-8")
    bundles._set_enabled("monitoring", True)
    data = json.loads(statefile.read_text())
    assert data["monitoring"]["enabled"] is True
    assert data["other"]["enabled"] is False  # untouched


def test_set_enabled_dry_run_does_not_write(statefile, monkeypatch):
    monkeypatch.setattr(bundles.config, "DRY_RUN", True)
    bundles._set_enabled("monitoring", False)
    assert not statefile.exists()  # preview only — no mutation


# ── claim-graph refcount / orphan detection (the "brain") ──────────────────
def test_claimants_only_from_enabled_bundles():
    assert bundles._claimants("influxdb", {"monitoring"}) == {"monitoring"}
    assert bundles._claimants("influxdb", set()) == set()


def test_orphans_after_disable_are_all_monitoring_services(statefile):
    # nothing else claims monitoring's services → all become orphans.
    assert bundles._orphans_after("monitoring") == list(MON)


def test_monitoring_claims_the_observability_stack():
    claims = bundles.BUNDLES["monitoring"]["claims"]
    for svc in ("influxdb", "telegraf", "grafana", "prometheus", "node-exporter"):
        assert svc in claims


def test_orphaned_services_none_when_all_enabled(statefile):
    assert bundles.orphaned_services() == []  # start/restart → nothing to converge


def test_orphaned_services_when_a_bundle_is_disabled(statefile):
    statefile.write_text(
        json.dumps({"monitoring": {"enabled": False}}), encoding="utf-8"
    )
    assert bundles.orphaned_services() == list(MON)  # start/restart would stop these


# ── enable / disable / reconcile funnel through compose ────────────────────
def test_enable_sets_state_and_ups_all_claims(statefile, rec_compose):
    assert bundles.enable("monitoring") == 0
    assert json.loads(statefile.read_text())["monitoring"]["enabled"] is True
    assert rec_compose == [("up", "-d", *MON)]


def test_disable_default_notifies_without_stopping(statefile, rec_compose):
    assert bundles.disable("monitoring") == 0
    assert json.loads(statefile.read_text())["monitoring"]["enabled"] is False
    assert rec_compose == []  # nothing stopped without --stop-orphans


def test_disable_stop_orphans_stops_all_orphaned(statefile, rec_compose):
    assert bundles.disable("monitoring", stop_orphans=True) == 0
    assert rec_compose == [("stop", *MON)]


def test_reconcile_all_enabled_ups_everything(statefile, rec_compose):
    # no state file → every bundle enabled → up all claimed services.
    assert bundles.reconcile() == 0
    assert rec_compose == [("up", "-d", *ALL)]


def test_reconcile_monitoring_disabled_reports_without_stopping(statefile, rec_compose):
    statefile.write_text(
        json.dumps({"monitoring": {"enabled": False}}), encoding="utf-8"
    )
    assert bundles.reconcile() == 0
    ups = [c for c in rec_compose if c[0] == "up"]
    expected_up = tuple(sorted(set(ALL) - set(MON)))  # everything except monitoring
    assert ups == [("up", "-d", *expected_up)]
    assert not any(c[0] == "stop" for c in rec_compose)  # orphans reported, not stopped


def test_reconcile_monitoring_disabled_stop_orphans(statefile, rec_compose):
    statefile.write_text(
        json.dumps({"monitoring": {"enabled": False}}), encoding="utf-8"
    )
    assert bundles.reconcile(stop_orphans=True) == 0
    stops = [c for c in rec_compose if c[0] == "stop"]
    assert stops == [("stop", *MON)]  # monitoring services are exclusive → all orphan


# ── service_active (what `start` filters each group by) + core guard ───────
def test_core_services_always_active(statefile):
    statefile.write_text(json.dumps({"core": {"enabled": False}}), encoding="utf-8")
    assert bundles.is_enabled("core") is True  # core can never be off
    assert bundles.service_active("postgres") is True


def test_service_active_follows_its_bundle(statefile):
    assert bundles.service_active("qdrant") is True  # rag enabled (absent → enabled)
    statefile.write_text(json.dumps({"rag": {"enabled": False}}), encoding="utf-8")
    assert bundles.service_active("qdrant") is False  # rag off → qdrant not active


def test_core_bundle_cannot_be_disabled(statefile):
    assert bundles.run("disable", "core") == 1


# ── install profiles (seed_profile) ────────────────────────────────────────
def test_seed_profile_standard_enables_ai_disables_ops(statefile):
    assert bundles.seed_profile("standard") is True
    data = json.loads(statefile.read_text())
    assert (
        data["inference"]["enabled"]
        and data["rag"]["enabled"]
        and data["chat"]["enabled"]
    )
    assert not data["monitoring"]["enabled"]
    assert not data["graph-rag"]["enabled"] and not data["voice"]["enabled"]


def test_seed_profile_minimal_disables_all_optional(statefile):
    assert bundles.seed_profile("minimal") is True
    data = json.loads(statefile.read_text())
    assert all(not v["enabled"] for v in data.values())


def test_seed_profile_full_enables_all_optional(statefile):
    assert bundles.seed_profile("full") is True
    data = json.loads(statefile.read_text())
    assert all(v["enabled"] for v in data.values())


def test_seed_profile_skips_when_state_exists(statefile):
    statefile.write_text(
        json.dumps({"monitoring": {"enabled": True}}), encoding="utf-8"
    )
    assert bundles.seed_profile("minimal") is False  # never clobber user choices
    assert json.loads(statefile.read_text())["monitoring"]["enabled"] is True


def test_seed_profile_dry_run_no_write(statefile, monkeypatch):
    monkeypatch.setattr(bundles.config, "DRY_RUN", True)
    assert bundles.seed_profile("standard") is False
    assert not statefile.exists()


# ── dispatch guards ────────────────────────────────────────────────────────
def test_run_rejects_unknown_action(statefile):
    assert bundles.run("frobnicate", "monitoring") == 1


def test_run_rejects_unknown_bundle(statefile):
    assert bundles.run("enable", "nope") == 1


def test_run_enable_requires_a_name(statefile):
    assert bundles.run("enable", "") == 1
