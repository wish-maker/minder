"""Unit tests for scripts/setup/health.py's remaining surface -- _server_ip,
_http_ok, run_health_checks' branches beyond the #197 down-container regression
(test_setup_health.py), and download_ollama_models. No real Docker/network:
socket/urllib/docker/time are all mocked.
"""

import urllib.error

import pytest

from scripts.setup import health

# ── _server_ip ─────────────────────────────────────────────────────────────────


def test_server_ip_returns_resolved_hostname(monkeypatch):
    monkeypatch.setattr(health.socket, "gethostname", lambda: "myhost")
    monkeypatch.setattr(health.socket, "gethostbyname", lambda name: "192.168.1.50")
    assert health._server_ip() == "192.168.1.50"


def test_server_ip_falls_back_to_localhost_on_oserror(monkeypatch):
    monkeypatch.setattr(health.socket, "gethostname", lambda: "myhost")

    def _raise(name):
        raise OSError("no resolution")

    monkeypatch.setattr(health.socket, "gethostbyname", _raise)
    assert health._server_ip() == "localhost"


def test_server_ip_falls_back_to_localhost_on_empty_result(monkeypatch):
    monkeypatch.setattr(health.socket, "gethostname", lambda: "myhost")
    monkeypatch.setattr(health.socket, "gethostbyname", lambda name: "")
    assert health._server_ip() == "localhost"


# ── _http_ok ───────────────────────────────────────────────────────────────────


class _FakeResponse:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_http_ok_true_on_2xx(monkeypatch):
    monkeypatch.setattr(
        health.urllib.request, "urlopen", lambda url, timeout=None: _FakeResponse(200)
    )
    assert health._http_ok("http://x/health") is True


def test_http_ok_false_on_non_2xx(monkeypatch):
    monkeypatch.setattr(
        health.urllib.request, "urlopen", lambda url, timeout=None: _FakeResponse(404)
    )
    assert health._http_ok("http://x/health") is False


def test_http_ok_false_on_exception(monkeypatch):
    def _raise(url, timeout=None):
        raise urllib.error.URLError("refused")

    monkeypatch.setattr(health.urllib.request, "urlopen", _raise)
    assert health._http_ok("http://x/health") is False


# ── run_health_checks: per-endpoint branches ──────────────────────────────────


@pytest.fixture
def _one_service(monkeypatch):
    monkeypatch.setattr(health.bundles, "service_active", lambda name: True)
    monkeypatch.setattr(health.config, "API_SERVICES", ["api-gateway"])
    monkeypatch.setattr(health.config, "SERVICE_PORTS", {"api-gateway": "8000"})
    monkeypatch.setattr(health.docker, "container_running", lambda name: True)


def test_skips_a_service_whose_bundle_is_inactive(monkeypatch, capfd):
    monkeypatch.setattr(health.bundles, "service_active", lambda name: False)
    monkeypatch.setattr(health.config, "API_SERVICES", ["api-gateway"])
    monkeypatch.setattr(health.config, "SERVICE_PORTS", {"api-gateway": "8000"})
    monkeypatch.setattr(
        health.docker,
        "container_running",
        lambda name: (_ for _ in ()).throw(AssertionError),
    )

    rc = health.run_health_checks()

    assert rc == 0
    out = capfd.readouterr().out
    assert "api-gateway" not in out


def test_bare_port_spec_defaults_health_path(monkeypatch, _one_service):
    captured = {}
    monkeypatch.setattr(
        health, "_http_ok", lambda url: captured.setdefault("url", url) or True
    )

    health.run_health_checks()

    assert captured["url"] == "http://127.0.0.1:8000/health"


def test_explicit_path_spec_is_used_verbatim(monkeypatch):
    monkeypatch.setattr(health.bundles, "service_active", lambda name: True)
    monkeypatch.setattr(health.config, "API_SERVICES", ["marketplace"])
    monkeypatch.setattr(
        health.config, "SERVICE_PORTS", {"marketplace": "8002/api/health"}
    )
    monkeypatch.setattr(health.docker, "container_running", lambda name: True)
    captured = {}
    monkeypatch.setattr(
        health, "_http_ok", lambda url: captured.setdefault("url", url) or True
    )

    health.run_health_checks()

    assert captured["url"] == "http://127.0.0.1:8002/api/health"


def test_http_check_warns_when_unreachable(monkeypatch, _one_service, capfd):
    monkeypatch.setattr(health, "_http_ok", lambda url: False)

    rc = health.run_health_checks()

    out = capfd.readouterr().out
    assert rc == 1
    assert "not yet reachable" in out


def test_http_check_warns_with_color_on(monkeypatch, _one_service, capfd):
    monkeypatch.setattr(health, "_http_ok", lambda url: False)
    monkeypatch.setattr(health.log, "_colors_on", lambda: True)

    health.run_health_checks()

    out = capfd.readouterr().out
    assert health.log._YELLOW in out


def test_http_check_ok_with_color_on(monkeypatch, _one_service, capfd):
    monkeypatch.setattr(health, "_http_ok", lambda url: True)
    monkeypatch.setattr(health.log, "_colors_on", lambda: True)

    health.run_health_checks()

    out = capfd.readouterr().out
    assert health.log._GREEN in out


def test_container_not_running_with_color_on(monkeypatch, capfd):
    monkeypatch.setattr(health.bundles, "service_active", lambda name: True)
    monkeypatch.setattr(health.config, "API_SERVICES", ["api-gateway"])
    monkeypatch.setattr(health.config, "SERVICE_PORTS", {"api-gateway": "8000"})
    monkeypatch.setattr(health.docker, "container_running", lambda name: False)
    monkeypatch.setattr(health.log, "_colors_on", lambda: True)

    rc = health.run_health_checks()

    out = capfd.readouterr().out
    assert rc == 1
    assert health.log._RED in out
    assert "not running" in out


def test_influxdb_uses_tcp_check_ok(monkeypatch, capfd):
    monkeypatch.setattr(health.bundles, "service_active", lambda name: True)
    monkeypatch.setattr(health.config, "API_SERVICES", [])
    monkeypatch.setattr(health.config, "SERVICE_PORTS", {"influxdb": "8086"})
    monkeypatch.setattr(health.docker, "container_running", lambda name: True)
    monkeypatch.setattr(health.docker, "tcp_open", lambda host, port: True)
    monkeypatch.setattr(
        health, "_http_ok", lambda url: (_ for _ in ()).throw(AssertionError)
    )

    rc = health.run_health_checks()

    out = capfd.readouterr().out
    assert rc == 0
    assert "TCP port check" in out


def test_influxdb_tcp_check_ok_with_color_on(monkeypatch, capfd):
    monkeypatch.setattr(health.bundles, "service_active", lambda name: True)
    monkeypatch.setattr(health.config, "API_SERVICES", [])
    monkeypatch.setattr(health.config, "SERVICE_PORTS", {"influxdb": "8086"})
    monkeypatch.setattr(health.docker, "container_running", lambda name: True)
    monkeypatch.setattr(health.docker, "tcp_open", lambda host, port: True)
    monkeypatch.setattr(health.log, "_colors_on", lambda: True)

    rc = health.run_health_checks()

    out = capfd.readouterr().out
    assert rc == 0
    assert health.log._GREEN in out
    assert "TCP port check" in out


def test_influxdb_tcp_check_warns_with_color_on(monkeypatch, capfd):
    monkeypatch.setattr(health.bundles, "service_active", lambda name: True)
    monkeypatch.setattr(health.config, "API_SERVICES", [])
    monkeypatch.setattr(health.config, "SERVICE_PORTS", {"influxdb": "8086"})
    monkeypatch.setattr(health.docker, "container_running", lambda name: True)
    monkeypatch.setattr(health.docker, "tcp_open", lambda host, port: False)
    monkeypatch.setattr(health.log, "_colors_on", lambda: True)

    rc = health.run_health_checks()

    out = capfd.readouterr().out
    assert rc == 1
    assert health.log._YELLOW in out


def test_monitoring_ai_and_client_groups_are_checked(monkeypatch, capfd):
    monkeypatch.setattr(health.bundles, "service_active", lambda name: True)
    monkeypatch.setattr(health.config, "API_SERVICES", [])
    monkeypatch.setattr(
        health.config,
        "SERVICE_PORTS",
        {
            "prometheus": "9090",
            "openwebui": "8090",
            "client": "8009",
        },
    )
    monkeypatch.setattr(health.docker, "container_running", lambda name: True)
    monkeypatch.setattr(health, "_http_ok", lambda url: True)

    rc = health.run_health_checks()

    out = capfd.readouterr().out
    assert rc == 0
    assert "prometheus" in out
    assert "openwebui" in out
    assert "client" in out
    assert "Monitoring" in out
    assert "AI Services" in out
    assert "Client" in out


# ── run_health_checks: JSON mode ──────────────────────────────────────────────


def test_json_mode_emits_valid_shaped_output(monkeypatch, _one_service, capfd):
    monkeypatch.setattr(health, "_http_ok", lambda url: True)

    rc = health.run_health_checks(json_mode=True)

    out = capfd.readouterr().out
    assert rc == 0
    assert '"ok": 1' in out
    assert '"name":"api-gateway"' in out
    assert '"status":"ok"' in out


def test_json_mode_multiple_services_comma_separated(monkeypatch, capfd):
    monkeypatch.setattr(health.bundles, "service_active", lambda name: True)
    monkeypatch.setattr(health.config, "API_SERVICES", ["api-gateway", "graph-rag"])
    monkeypatch.setattr(
        health.config,
        "SERVICE_PORTS",
        {"api-gateway": "8000", "graph-rag": "8008"},
    )
    monkeypatch.setattr(health.docker, "container_running", lambda name: True)
    monkeypatch.setattr(health, "_http_ok", lambda url: True)

    health.run_health_checks(json_mode=True)

    out = capfd.readouterr().out
    assert out.count('"name":') == 2
    assert "}," in out  # comma separates the two service entries


# ── run_health_checks: text-mode summary ──────────────────────────────────────


def test_text_summary_all_healthy(monkeypatch, _one_service, capfd):
    monkeypatch.setattr(health, "_http_ok", lambda url: True)

    rc = health.run_health_checks()

    out = capfd.readouterr().out
    assert rc == 0
    assert "1/1 endpoints healthy" in out
    assert "🎉" in out


def test_text_summary_distinguishes_down_from_starting(monkeypatch, capfd):
    monkeypatch.setattr(health.bundles, "service_active", lambda name: True)
    monkeypatch.setattr(health.config, "API_SERVICES", ["api-gateway", "graph-rag"])
    monkeypatch.setattr(
        health.config,
        "SERVICE_PORTS",
        {"api-gateway": "8000", "graph-rag": "8008"},
    )
    monkeypatch.setattr(
        health.docker, "container_running", lambda name: name == "graph-rag"
    )
    monkeypatch.setattr(health, "_http_ok", lambda url: False)

    health.run_health_checks()

    out = capfd.readouterr().out
    assert "1 not running" in out
    assert "1 still starting" in out
    assert "Re-check:" in out


# ── download_ollama_models ─────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _no_sleep_or_spinner(monkeypatch):
    monkeypatch.setattr(health.time, "sleep", lambda secs: None)
    monkeypatch.setattr(health.log, "spinner_start", lambda *a, **k: None)
    monkeypatch.setattr(health.log, "spinner_stop", lambda: None)


def test_download_ollama_models_skips_in_external_mode(monkeypatch, capfd):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
    monkeypatch.setattr(
        health.docker, "cmd_ok", lambda argv: (_ for _ in ()).throw(AssertionError)
    )

    health.download_ollama_models()

    out = capfd.readouterr().out
    assert "External Ollama mode" in out


def test_download_ollama_models_warns_when_ollama_never_becomes_ready(
    monkeypatch, capfd
):
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.setattr(health.env, "get", lambda key: "")
    monkeypatch.setattr(health.config, "TIMEOUT_OLLAMA", 3)
    monkeypatch.setattr(health.docker, "cmd_ok", lambda argv: False)

    health.download_ollama_models()

    out = capfd.readouterr().out
    assert "did not start within 3s" in out


def test_download_ollama_models_skips_when_automatic_pull_disabled(monkeypatch, capfd):
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.setattr(health.docker, "cmd_ok", lambda argv: True)
    monkeypatch.setattr(
        health.env,
        "get",
        lambda key: "false" if key == "OLLAMA_AUTOMATIC_PULL" else "",
    )

    health.download_ollama_models()

    out = capfd.readouterr().out
    assert "OLLAMA_AUTOMATIC_PULL=false" in out


def test_download_ollama_models_pulls_default_models_and_reports_success(
    monkeypatch, capfd
):
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.setattr(health.docker, "cmd_ok", lambda argv: True)
    monkeypatch.setattr(health.env, "get", lambda key: "")
    monkeypatch.setattr(health.docker, "run", lambda *args, **kw: 0)
    monkeypatch.setattr(
        health.docker,
        "capture",
        lambda argv: "NAME\nllama3.2\nnomic-embed-text\n",
    )

    health.download_ollama_models()

    out = capfd.readouterr().out
    assert "llama3.2" in out
    assert "nomic-embed-text" in out
    assert "2 model(s) available" in out


def test_download_ollama_models_uses_custom_model_list(monkeypatch, capfd):
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.setattr(health.docker, "cmd_ok", lambda argv: True)
    monkeypatch.setattr(
        health.env,
        "get",
        lambda key: "mistral, ,phi3" if key == "OLLAMA_MODELS" else "",
    )
    pulled = []
    monkeypatch.setattr(
        health.docker,
        "run",
        lambda *args, **kw: pulled.append(args) or 0,
    )
    monkeypatch.setattr(health.docker, "capture", lambda argv: "NAME\n")

    health.download_ollama_models()

    pulled_models = [
        args[7] for args in pulled
    ]  # timeout 300 docker exec <name> ollama pull <model>
    assert pulled_models == ["mistral", "phi3"]


def test_download_ollama_models_warns_on_pull_failure(monkeypatch, capfd):
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.setattr(health.docker, "cmd_ok", lambda argv: True)
    monkeypatch.setattr(
        health.env,
        "get",
        lambda key: "llama3.2" if key == "OLLAMA_MODELS" else "",
    )
    monkeypatch.setattr(health.docker, "run", lambda *args, **kw: 1)
    monkeypatch.setattr(health.docker, "capture", lambda argv: "NAME\n")

    health.download_ollama_models()

    out = capfd.readouterr().out
    assert "llama3.2 — failed or timed out" in out
