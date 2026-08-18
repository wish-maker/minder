"""Unit tests for scripts/setup/lifecycle.py (start_services, wait_for_services,
_reconcile_created) -- previously only verified non-destructively under DRY_RUN
plus the gate's docker shim (real waits/health made instant). Every docker/
bundles/env/time call is mocked; config's service tuples are shrunk to small
deterministic values so call assertions don't depend on the real service list.
"""

import os

import pytest

from scripts.setup import lifecycle


@pytest.fixture(autouse=True)
def _small_config(monkeypatch):
    monkeypatch.setattr(lifecycle.config, "SECURITY_SERVICES", ("traefik", "authelia"))
    monkeypatch.setattr(lifecycle.config, "CORE_SERVICES", ("postgres", "redis"))
    monkeypatch.setattr(lifecycle.config, "API_SERVICES", ("api-gateway",))
    monkeypatch.setattr(lifecycle.config, "MONITORING_SERVICES", ("jaeger",))
    monkeypatch.setattr(lifecycle.config, "AI_SERVICES", ("openwebui", "tts-stt"))
    monkeypatch.setattr(lifecycle.config, "EXPORTER_SERVICES", ("node-exporter",))
    monkeypatch.setattr(lifecycle.config, "TIMEOUT_SERVICES", 90)
    monkeypatch.setattr(lifecycle.config, "TIMEOUT_MONITORING", 120)
    monkeypatch.setattr(lifecycle.config, "TIMEOUT_AI", 130)
    monkeypatch.setattr(lifecycle.config, "DRY_RUN", False)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(lifecycle.time, "sleep", lambda secs: None)


@pytest.fixture(autouse=True)
def _clean_env_vars(monkeypatch):
    for key in (
        "OLLAMA_BASE_URL",
        "OLLAMA_FAILOVER_PRIMARY",
        "TTS_STT_BASE_URL",
        "TTS_STT_FAILOVER_PRIMARY",
        "COMPOSE_PROFILES",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(lifecycle.env, "get", lambda key: "")


@pytest.fixture(autouse=True)
def _all_bundles_active(monkeypatch):
    monkeypatch.setattr(lifecycle.bundles, "service_active", lambda svc: True)
    monkeypatch.setattr(lifecycle.bundles, "is_enabled", lambda name: True)
    monkeypatch.setattr(lifecycle.bundles, "orphaned_services", lambda: [])


@pytest.fixture
def rec_compose(monkeypatch):
    calls = []
    monkeypatch.setattr(
        lifecycle.docker, "compose", lambda *args: calls.append(("compose", args)) or 0
    )
    monkeypatch.setattr(
        lifecycle.docker,
        "compose_monitoring",
        lambda *args: calls.append(("compose_monitoring", args)) or 0,
    )
    return calls


# ── start_services: ollama mode ───────────────────────────────────────────────


def test_default_internal_ollama_and_tts_stt_activates_both_profiles(
    rec_compose, monkeypatch
):
    lifecycle.start_services()

    assert set(os.environ["COMPOSE_PROFILES"].split(",")) == {
        "internal-ollama",
        "internal-tts-stt",
    }


def test_external_ollama_url_skips_internal_ollama_profile(monkeypatch, rec_compose):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")

    lifecycle.start_services()

    profiles = os.environ.get("COMPOSE_PROFILES", "")
    assert "internal-ollama" not in profiles.split(",")


def test_ollama_failover_mode_activates_router_profile_and_explicit_bringup(
    monkeypatch, rec_compose
):
    monkeypatch.setenv("OLLAMA_FAILOVER_PRIMARY", "http://gpu-node:11434")

    lifecycle.start_services()

    profiles = set(os.environ["COMPOSE_PROFILES"].split(","))
    assert {"internal-ollama", "ollama-router"} <= profiles
    assert ("compose", ("up", "-d", "ollama")) in rec_compose
    assert ("compose", ("up", "-d", "ollama-router")) in rec_compose


def test_no_bundle_claims_ollama_skips_internal_ollama_profile(
    monkeypatch, rec_compose
):
    monkeypatch.setattr(
        lifecycle.bundles, "service_active", lambda svc: svc != "ollama"
    )

    lifecycle.start_services()

    profiles = os.environ.get("COMPOSE_PROFILES", "").split(",")
    assert "internal-ollama" not in profiles
    assert "internal-tts-stt" in profiles


# ── start_services: tts-stt mode (mirrors ollama) ─────────────────────────────


def test_external_tts_stt_url_skips_internal_tts_stt_profile(monkeypatch, rec_compose):
    monkeypatch.setenv("TTS_STT_BASE_URL", "http://host.docker.internal:8006")

    lifecycle.start_services()

    profiles = os.environ.get("COMPOSE_PROFILES", "").split(",")
    assert "internal-tts-stt" not in profiles


def test_tts_stt_failover_mode_brings_up_backup_and_router_explicitly(
    monkeypatch, rec_compose
):
    monkeypatch.setenv("TTS_STT_FAILOVER_PRIMARY", "http://gpu-node:8006")

    lifecycle.start_services()

    assert ("compose", ("up", "-d", "tts-stt")) in rec_compose
    assert ("compose", ("up", "-d", "tts-stt-router")) in rec_compose


def test_no_bundle_claims_tts_stt_skips_internal_tts_stt_profile(
    monkeypatch, rec_compose
):
    monkeypatch.setattr(
        lifecycle.bundles, "service_active", lambda svc: svc != "tts-stt"
    )

    lifecycle.start_services()

    profiles = os.environ.get("COMPOSE_PROFILES", "").split(",")
    assert "internal-tts-stt" not in profiles


def test_no_active_profiles_pops_compose_profiles_env_var(monkeypatch, rec_compose):
    monkeypatch.setenv("COMPOSE_PROFILES", "leftover-from-a-previous-run")
    monkeypatch.setattr(
        lifecycle.bundles,
        "service_active",
        lambda svc: svc not in ("ollama", "tts-stt"),
    )

    lifecycle.start_services()

    assert "COMPOSE_PROFILES" not in os.environ


# ── start_services: group dispatch ────────────────────────────────────────────


def test_dispatches_security_and_core_groups(rec_compose):
    lifecycle.start_services()

    assert ("compose", ("up", "-d", "traefik", "authelia")) in rec_compose
    assert ("compose", ("up", "-d", "postgres", "redis")) in rec_compose


def test_core_group_filters_to_active_services_only(monkeypatch, rec_compose):
    monkeypatch.setattr(lifecycle.bundles, "service_active", lambda svc: svc != "redis")

    lifecycle.start_services()

    assert ("compose", ("up", "-d", "postgres")) in rec_compose
    assert not any(args == ("up", "-d", "postgres", "redis") for _, args in rec_compose)


def test_waits_for_rabbitmq_healthy(monkeypatch, rec_compose):
    calls = []
    monkeypatch.setattr(
        lifecycle.docker,
        "wait_healthy",
        lambda svc, timeout: calls.append((svc, timeout)),
    )

    lifecycle.start_services()

    assert ("rabbitmq", lifecycle.config.TIMEOUT_SERVICES) in calls


def test_dispatches_api_services_group(rec_compose):
    lifecycle.start_services()
    assert ("compose", ("up", "-d", "api-gateway")) in rec_compose


def test_monitoring_enabled_dispatches_all_monitoring_groups(rec_compose):
    lifecycle.start_services()

    assert ("compose", ("up", "-d", "influxdb", "telegraf")) in rec_compose
    assert (
        "compose_monitoring",
        ("up", "-d", "prometheus", "grafana", "alertmanager"),
    ) in rec_compose
    assert ("compose", ("up", "-d", "jaeger")) in rec_compose
    assert ("compose_monitoring", ("up", "-d", "node-exporter")) in rec_compose


def test_monitoring_disabled_skips_monitoring_and_exporters(monkeypatch, rec_compose):
    monkeypatch.setattr(
        lifecycle.bundles, "is_enabled", lambda name: name != "monitoring"
    )

    lifecycle.start_services()

    assert not any(name == "compose_monitoring" for name, _ in rec_compose)
    assert not any(
        args == ("up", "-d", "influxdb", "telegraf") for _, args in rec_compose
    )


def test_ai_services_dispatched_when_bundle_active(rec_compose):
    lifecycle.start_services()
    assert ("compose", ("up", "-d", "openwebui", "tts-stt")) in rec_compose


def test_ai_services_skipped_when_no_bundle_claims_them(monkeypatch, rec_compose):
    monkeypatch.setattr(lifecycle.bundles, "service_active", lambda svc: False)

    lifecycle.start_services()

    assert not any(
        set(args[2:]) & {"openwebui", "tts-stt"}
        for name, args in rec_compose
        if name == "compose"
    )


def test_orphaned_services_are_stopped(monkeypatch, rec_compose):
    monkeypatch.setattr(
        lifecycle.bundles, "orphaned_services", lambda: ["grafana", "prometheus"]
    )

    lifecycle.start_services()

    assert ("compose", ("stop", "grafana", "prometheus")) in rec_compose


def test_no_orphans_no_stop_call(rec_compose):
    lifecycle.start_services()
    assert not any(args and args[0] == "stop" for _, args in rec_compose)


# ── _reconcile_created ─────────────────────────────────────────────────────────


def test_reconcile_created_noop_under_dry_run(monkeypatch):
    monkeypatch.setattr(lifecycle.config, "DRY_RUN", True)
    monkeypatch.setattr(
        lifecycle.docker,
        "created_services",
        lambda: (_ for _ in ()).throw(AssertionError("should not be called")),
    )

    lifecycle._reconcile_created()  # must not raise


def test_reconcile_created_brings_up_active_created_services(monkeypatch, capfd):
    monkeypatch.setattr(
        lifecycle.docker, "created_services", lambda: ["graph-rag", "marketplace"]
    )
    monkeypatch.setattr(
        lifecycle.bundles, "service_active", lambda svc: svc == "graph-rag"
    )
    calls = []
    monkeypatch.setattr(
        lifecycle.docker, "compose", lambda *args: calls.append(args) or 0
    )

    lifecycle._reconcile_created()

    out = capfd.readouterr().out
    assert "Recovering 1 service(s)" in out
    assert ("up", "-d", "graph-rag") in calls
    assert ("up", "-d", "marketplace") not in calls


def test_reconcile_created_noop_when_nothing_created(monkeypatch, capfd):
    monkeypatch.setattr(lifecycle.docker, "created_services", lambda: [])
    monkeypatch.setattr(
        lifecycle.docker,
        "compose",
        lambda *a: (_ for _ in ()).throw(AssertionError("should not be called")),
    )

    lifecycle._reconcile_created()

    assert "Recovering" not in capfd.readouterr().out


# ── wait_for_services ───────────────────────────────────────────────────────────


def test_wait_for_services_waits_each_group_with_the_right_timeout(monkeypatch):
    calls = []
    monkeypatch.setattr(
        lifecycle.docker,
        "wait_healthy",
        lambda svc, timeout: calls.append((svc, timeout)),
    )
    monkeypatch.setattr(lifecycle.docker, "created_services", lambda: [])

    lifecycle.wait_for_services()

    assert ("postgres", 90) in calls
    assert ("redis", 90) in calls
    assert ("api-gateway", 90) in calls
    assert ("jaeger", 120) in calls
    assert ("openwebui", 130) in calls
    assert ("tts-stt", 130) in calls


def test_wait_for_services_skips_inactive_services(monkeypatch):
    monkeypatch.setattr(lifecycle.bundles, "service_active", lambda svc: svc != "redis")
    calls = []
    monkeypatch.setattr(
        lifecycle.docker,
        "wait_healthy",
        lambda svc, timeout: calls.append(svc),
    )
    monkeypatch.setattr(lifecycle.docker, "created_services", lambda: [])

    lifecycle.wait_for_services()

    assert "redis" not in calls
    assert "postgres" in calls


def test_wait_for_services_reconciles_created_twice(monkeypatch):
    monkeypatch.setattr(lifecycle.docker, "wait_healthy", lambda svc, timeout: None)
    reconcile_calls = []
    monkeypatch.setattr(
        lifecycle, "_reconcile_created", lambda: reconcile_calls.append(1)
    )

    lifecycle.wait_for_services()

    assert len(reconcile_calls) == 2
