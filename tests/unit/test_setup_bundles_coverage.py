"""Additional unit tests for scripts/setup/bundles.py's remaining branches --
test_setup_bundles.py already covers the state-file enable semantics, the
claim-graph refcount/orphan logic, enable/disable/reconcile's compose calls,
external binding, and _load_claims' missing-compose-file error. This file
covers everything else still untested at 76%: _plugin_manifest_texts and
_load_claims' plugin-manifest-merge paths, reset_state, the enable()
already-disabled-then-enabled success message, disable()'s "kept" and
"no orphans" branches, reconcile()'s "nothing to do" branch, status(), and
run()'s status/reconcile/enable/disable dispatch. No Docker: docker.compose/
container_running/container_health are stubbed.
"""

import json
from pathlib import Path

import pytest

from scripts.setup import bundles


@pytest.fixture
def statefile(tmp_path, monkeypatch):
    p = tmp_path / "bundles.state.json"
    monkeypatch.setattr(bundles, "STATE_FILE", p)
    monkeypatch.setattr(bundles.config, "DRY_RUN", False)
    return p


@pytest.fixture
def rec_compose(monkeypatch):
    calls = []
    monkeypatch.setattr(bundles.docker, "compose", lambda *a: calls.append(a) or 0)
    return calls


@pytest.fixture(autouse=True)
def _no_ambient_external(monkeypatch):
    monkeypatch.setattr(bundles.env, "get", lambda key: "")
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)


# ── _plugin_manifest_texts ─────────────────────────────────────────────────────


def test_plugin_manifest_texts_empty_when_plugins_dir_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(bundles.config, "PLUGINS_DIR", tmp_path / "does-not-exist")
    assert bundles._plugin_manifest_texts() == []


def test_plugin_manifest_texts_reads_existing_manifests(monkeypatch, tmp_path):
    plugin_dir = tmp_path / "myplugin"
    plugin_dir.mkdir()
    (plugin_dir / "manifest.yml").write_text("bundle: extra\n", encoding="utf-8")
    monkeypatch.setattr(bundles.config, "PLUGINS_DIR", tmp_path)

    texts = bundles._plugin_manifest_texts()

    assert texts == ["bundle: extra\n"]


def test_plugin_manifest_texts_tolerates_an_unreadable_manifest(monkeypatch, tmp_path):
    good_dir = tmp_path / "good"
    good_dir.mkdir()
    (good_dir / "manifest.yml").write_text("bundle: good\n", encoding="utf-8")
    bad_dir = tmp_path / "bad"
    bad_dir.mkdir()
    bad_manifest = bad_dir / "manifest.yml"
    bad_manifest.write_text("bundle: bad\n", encoding="utf-8")
    monkeypatch.setattr(bundles.config, "PLUGINS_DIR", tmp_path)

    real_read_text = Path.read_text

    def _maybe_raise(self, *a, **k):
        if self == bad_manifest:
            raise OSError("permission denied")
        return real_read_text(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", _maybe_raise)

    texts = bundles._plugin_manifest_texts()

    assert texts == ["bundle: good\n"]


# ── _load_claims: plugin-manifest merge + the "no core label" error ──────────


def test_load_claims_raises_when_core_label_absent(monkeypatch, tmp_path):
    compose = tmp_path / "docker-compose.yml"
    compose.write_text(
        "services:\n  api:\n    labels:\n      - minder.bundle=inference\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(bundles.config, "COMPOSE_FILE", compose)
    monkeypatch.setattr(bundles.config, "PLUGINS_DIR", tmp_path / "no-plugins")

    with pytest.raises(RuntimeError, match="No minder.bundle labels found"):
        bundles._load_claims()


def test_load_claims_merges_a_plugin_declared_bundle(monkeypatch, tmp_path):
    compose = tmp_path / "docker-compose.yml"
    compose.write_text(
        "services:\n  postgres:\n    labels:\n      - minder.bundle=core\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(bundles.config, "COMPOSE_FILE", compose)
    plugin_dir = tmp_path / "plugins" / "myplugin"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "manifest.yml").write_text(
        "bundle: extra-feature\nclaims:\n  - service: myservice\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(bundles.config, "PLUGINS_DIR", tmp_path / "plugins")

    claims = bundles._load_claims()

    assert claims["extra-feature"] == ("myservice",)
    assert claims["core"] == ("postgres",)


def test_load_claims_dedupes_a_service_claimed_by_both_sources(monkeypatch, tmp_path):
    compose = tmp_path / "docker-compose.yml"
    compose.write_text(
        "services:\n"
        "  postgres:\n"
        "    labels:\n"
        "      - minder.bundle=core\n"
        "  qdrant:\n"
        "    labels:\n"
        "      - minder.bundle=rag\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(bundles.config, "COMPOSE_FILE", compose)
    plugin_dir = tmp_path / "plugins" / "myplugin"
    plugin_dir.mkdir(parents=True)
    # Same "rag" bundle, same "qdrant" service the compose label already claims.
    (plugin_dir / "manifest.yml").write_text(
        "bundle: rag\nclaims:\n  - service: qdrant\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(bundles.config, "PLUGINS_DIR", tmp_path / "plugins")

    claims = bundles._load_claims()

    assert claims["rag"] == ("qdrant",)  # not ("qdrant", "qdrant")


# ── reset_state ────────────────────────────────────────────────────────────────


def test_reset_state_noop_when_dry_run(statefile, monkeypatch):
    statefile.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(bundles.config, "DRY_RUN", True)

    assert bundles.reset_state() is False
    assert statefile.exists()


def test_reset_state_noop_when_file_absent(statefile):
    assert not statefile.exists()
    assert bundles.reset_state() is False


def test_reset_state_deletes_the_file(statefile):
    statefile.write_text("{}", encoding="utf-8")

    assert bundles.reset_state() is True
    assert not statefile.exists()


# ── enable(): the already-disabled-then-enabled success message ──────────────


def test_enable_from_disabled_reports_success(statefile, rec_compose):
    statefile.write_text(
        json.dumps({"monitoring": {"enabled": False}}), encoding="utf-8"
    )

    assert bundles.enable("monitoring") == 0

    assert json.loads(statefile.read_text())["monitoring"]["enabled"] is True


def test_enable_already_enabled_reports_info_not_success(
    statefile, rec_compose, monkeypatch
):
    infos, succs = [], []
    monkeypatch.setattr(bundles.log, "info", lambda m: infos.append(m))
    monkeypatch.setattr(bundles.log, "success", lambda m: succs.append(m))

    bundles.enable("monitoring")  # already enabled by default (absent state file)

    assert any("already enabled" in m for m in infos)
    assert not any("→ enabled" in m for m in succs)


def test_enable_from_disabled_emits_success_not_info(
    statefile, rec_compose, monkeypatch
):
    statefile.write_text(
        json.dumps({"monitoring": {"enabled": False}}), encoding="utf-8"
    )
    infos, succs = [], []
    monkeypatch.setattr(bundles.log, "info", lambda m: infos.append(m))
    monkeypatch.setattr(bundles.log, "success", lambda m: succs.append(m))

    bundles.enable("monitoring")

    assert any("→ enabled" in m for m in succs)
    assert not any("already enabled" in m for m in infos)


# ── disable(): "kept" and "no orphaned services" branches ─────────────────────


def test_disable_reports_kept_services_still_claimed_elsewhere(monkeypatch):
    """monitoring and inference both (fictionally) claim 'shared-svc'; disabling
    monitoring must report it as kept, not orphaned, while its exclusive
    service is still reported orphaned."""
    monkeypatch.setattr(
        bundles,
        "BUNDLES",
        {
            "core": {"claims": ("postgres",)},
            "monitoring": {"claims": ("grafana", "shared-svc")},
            "inference": {"claims": ("shared-svc",)},
        },
    )
    monkeypatch.setattr(
        bundles, "_CLAIMS", {k: v["claims"] for k, v in bundles.BUNDLES.items()}
    )
    details = []
    monkeypatch.setattr(bundles.log, "detail", lambda m: details.append(m))
    monkeypatch.setattr(bundles.log, "success", lambda m: None)
    monkeypatch.setattr(bundles.log, "warn", lambda m: None)

    bundles.disable("monitoring")

    assert any("Kept" in d and "shared-svc" in d for d in details)


def test_disable_reports_no_orphans_when_everything_still_claimed(monkeypatch):
    monkeypatch.setattr(
        bundles,
        "BUNDLES",
        {
            "core": {"claims": ("postgres",)},
            "monitoring": {"claims": ("shared-svc",)},
            "inference": {"claims": ("shared-svc",)},
        },
    )
    monkeypatch.setattr(
        bundles, "_CLAIMS", {k: v["claims"] for k, v in bundles.BUNDLES.items()}
    )
    infos = []
    monkeypatch.setattr(bundles.log, "info", lambda m: infos.append(m))
    monkeypatch.setattr(bundles.log, "success", lambda m: None)

    rc = bundles.disable("monitoring")

    assert rc == 0
    assert any("No orphaned services" in i for i in infos)


# ── reconcile(): "nothing to do" branch ────────────────────────────────────────


def test_reconcile_reports_nothing_to_do_when_no_claims_and_no_orphans(monkeypatch):
    monkeypatch.setattr(bundles, "_enabled_bundles", lambda exclude=None: set())
    monkeypatch.setattr(bundles, "orphaned_services", lambda: [])
    infos = []
    monkeypatch.setattr(bundles.log, "info", lambda m: infos.append(m))
    monkeypatch.setattr(bundles.log, "success", lambda m: None)

    rc = bundles.reconcile()

    assert rc == 0
    assert any("Nothing to do" in i for i in infos)


# ── status() ───────────────────────────────────────────────────────────────────


def test_status_reports_healthy_claimed_service(statefile, monkeypatch):
    monkeypatch.setattr(bundles, "BUNDLES", {"core": {"claims": ("postgres",)}})
    monkeypatch.setattr(bundles.docker, "container_running", lambda s: True)
    monkeypatch.setattr(bundles.docker, "container_health", lambda s: "healthy")
    details = []
    monkeypatch.setattr(bundles.log, "detail", lambda m: details.append(m))
    monkeypatch.setattr(bundles.log, "info", lambda m: None)

    rc = bundles.status()

    assert rc == 0
    assert any("✓" in d and "postgres" in d and "healthy" in d for d in details)


def test_status_flags_drift_for_claimed_but_stopped_service(statefile, monkeypatch):
    monkeypatch.setattr(bundles, "BUNDLES", {"core": {"claims": ("postgres",)}})
    monkeypatch.setattr(bundles.docker, "container_running", lambda s: False)
    monkeypatch.setattr(
        bundles.docker,
        "container_health",
        lambda s: (_ for _ in ()).throw(AssertionError),
    )
    details = []
    monkeypatch.setattr(bundles.log, "detail", lambda m: details.append(m))
    monkeypatch.setattr(bundles.log, "info", lambda m: None)

    bundles.status()

    assert any("!" in d and "stopped" in d for d in details)


def test_status_flags_drift_for_unclaimed_but_running_service(monkeypatch):
    monkeypatch.setattr(
        bundles,
        "BUNDLES",
        {"monitoring": {"claims": ("grafana",)}},
    )
    monkeypatch.setattr(bundles, "_enabled_bundles", lambda exclude=None: set())
    monkeypatch.setattr(bundles.docker, "container_running", lambda s: True)
    monkeypatch.setattr(bundles.docker, "container_health", lambda s: "healthy")
    details = []
    monkeypatch.setattr(bundles.log, "detail", lambda m: details.append(m))
    monkeypatch.setattr(bundles.log, "info", lambda m: None)

    bundles.status()

    line = [d for d in details if "grafana" in d][0]
    assert "!" in line
    assert "orphaned" in line


def test_status_shows_unclaimed_and_stopped_as_neutral(monkeypatch):
    monkeypatch.setattr(bundles, "BUNDLES", {"monitoring": {"claims": ("grafana",)}})
    monkeypatch.setattr(bundles, "_enabled_bundles", lambda exclude=None: set())
    monkeypatch.setattr(bundles.docker, "container_running", lambda s: False)
    details = []
    monkeypatch.setattr(bundles.log, "detail", lambda m: details.append(m))
    monkeypatch.setattr(bundles.log, "info", lambda m: None)

    bundles.status()

    line = [d for d in details if "grafana" in d][0]
    assert "·" in line
    assert "orphaned" in line


def test_status_shows_external_binding_not_running_as_neutral(monkeypatch):
    monkeypatch.setattr(bundles, "BUNDLES", {"inference": {"claims": ("ollama",)}})
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://gpu-node:11434")
    monkeypatch.setattr(bundles.docker, "container_running", lambda s: False)
    details = []
    monkeypatch.setattr(bundles.log, "detail", lambda m: details.append(m))
    monkeypatch.setattr(bundles.log, "info", lambda m: None)

    bundles.status()

    line = [d for d in details if "ollama" in d][0]
    assert "⇄" in line
    assert "external → http://gpu-node:11434" in line


def test_status_shows_external_binding_running_as_drift(monkeypatch):
    monkeypatch.setattr(bundles, "BUNDLES", {"inference": {"claims": ("ollama",)}})
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://gpu-node:11434")
    monkeypatch.setattr(bundles.docker, "container_running", lambda s: True)
    monkeypatch.setattr(bundles.docker, "container_health", lambda s: "healthy")
    details = []
    monkeypatch.setattr(bundles.log, "detail", lambda m: details.append(m))
    monkeypatch.setattr(bundles.log, "info", lambda m: None)

    bundles.status()

    line = [d for d in details if "ollama" in d][0]
    assert "!" in line
    assert "external →" in line


# ── run(): status/reconcile/enable/disable dispatch ───────────────────────────


def test_run_status_dispatches_to_status(monkeypatch):
    monkeypatch.setattr(bundles, "status", lambda: 42)
    assert bundles.run("status") == 42


def test_run_reconcile_dispatches_with_stop_orphans(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        bundles,
        "reconcile",
        lambda stop_orphans=False: captured.setdefault("stop_orphans", stop_orphans)
        or 0,
    )

    bundles.run("reconcile", stop_orphans=True)

    assert captured["stop_orphans"] is True


def test_run_enable_dispatches_to_enable(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        bundles, "enable", lambda name: captured.setdefault("name", name) or 0
    )

    bundles.run("enable", "monitoring")

    assert captured["name"] == "monitoring"


def test_run_disable_dispatches_with_stop_orphans(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        bundles,
        "disable",
        lambda name, stop_orphans=False: captured.update(
            name=name, stop_orphans=stop_orphans
        )
        or 0,
    )

    bundles.run("disable", "monitoring", stop_orphans=True)

    assert captured == {"name": "monitoring", "stop_orphans": True}
