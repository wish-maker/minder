"""Regression guard for #197: a service whose container is NOT running must count
as unhealthy.

Before the fix, `run_health_checks` recorded and printed "error" (container not
running) results but never counted them — only `warn` (reachable-but-starting) fed
the summary and the exposed signal. So a heavy install that left a depends_on
service "Created" reported "N/N endpoints healthy 🎉" and a clean exit over a
down service. Now errors are counted: the return is non-zero and the summary says
so.

No Docker/network: container_running, _http_ok and bundles/config are stubbed.
capfd (not capsys) because log._emit writes to sys.stdout.buffer.
"""

import pytest

from scripts.setup import health


@pytest.fixture
def two_services(monkeypatch):
    """A minimal SERVICE_PORTS with one Core API service that's up and one that
    the test can knock down. The Monitoring/AI loops iterate a fixed name list,
    but none are in SERVICE_PORTS here → they're skipped."""
    monkeypatch.setattr(health.bundles, "service_active", lambda name: True)
    monkeypatch.setattr(health.config, "API_SERVICES", ["api-gateway", "graph-rag"])
    monkeypatch.setattr(
        health.config,
        "SERVICE_PORTS",
        {"api-gateway": "8000", "graph-rag": "8008"},
    )
    monkeypatch.setattr(health, "_http_ok", lambda url: True)


def test_down_container_counts_as_unhealthy(monkeypatch, two_services, capfd):
    # graph-rag "Created"/not running; api-gateway up + healthy.
    monkeypatch.setattr(
        health.docker, "container_running", lambda name: name != "graph-rag"
    )
    rc = health.run_health_checks()
    out = capfd.readouterr().out
    assert rc == 1  # the down service is counted (was 0 → false "healthy" before)
    assert "not running" in out  # summary distinguishes down from still-starting
    assert "🎉" not in out  # must NOT claim all-healthy over a down container


def test_all_up_is_clean(monkeypatch, two_services, capfd):
    monkeypatch.setattr(health.docker, "container_running", lambda name: True)
    rc = health.run_health_checks()
    out = capfd.readouterr().out
    assert rc == 0
    assert "🎉" in out


def test_json_reports_error_count(monkeypatch, two_services, capfd):
    monkeypatch.setattr(
        health.docker, "container_running", lambda name: name != "graph-rag"
    )
    rc = health.run_health_checks(json_mode=True)
    out = capfd.readouterr().out
    assert rc == 1
    assert '"error": 1' in out
    assert '"ok": 1' in out


def test_tts_stt_is_not_host_health_checked():
    """#714: tts-stt's host :8006 was moved to the profile-gated failover router,
    so nothing publishes it on the host in the default deployment. Host-checking it
    only ever produced a false ⚠ — it must stay OUT of SERVICE_PORTS, like the
    other Traefik/internal-only services (openwebui/rabbitmq/authelia/minio/jaeger)."""
    from scripts.setup import config

    for internal_only in (
        "tts-stt",
        "openwebui",
        "rabbitmq",
        "authelia",
        "minio",
        "jaeger",
    ):
        assert internal_only not in config.SERVICE_PORTS, internal_only
    # The seven host-published core APIs stay checked.
    for core in (
        "api-gateway",
        "plugin-registry",
        "marketplace",
        "plugin-state-manager",
        "rag-pipeline",
        "model-management",
        "graph-rag",
    ):
        assert core in config.SERVICE_PORTS, core
