"""Unit tests for scripts/setup/docker.py's helpers -- run()'s dry-run gate,
the container-introspection functions, and the wait/poll loops. The narrow
#351 pg_isready-TCP regression test already lives in test_setup_docker.py;
this file covers everything else. No real Docker/network calls: subprocess/
socket/time are all mocked.
"""

import pytest

from scripts.setup import docker


@pytest.fixture(autouse=True)
def _no_dry_run(monkeypatch):
    monkeypatch.setattr(docker.config, "DRY_RUN", False)


class _FakeCompleted:
    def __init__(self, returncode=0, stdout=""):
        self.returncode = returncode
        self.stdout = stdout


# ── run() ──────────────────────────────────────────────────────────────────────


def test_run_dry_run_prints_newline_joined_args_and_skips_subprocess(
    monkeypatch, capfd
):
    monkeypatch.setattr(docker.config, "DRY_RUN", True)
    monkeypatch.setattr(
        docker.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError)
    )

    rc = docker.run("docker", "ps", "-a")

    out = capfd.readouterr().out
    assert rc == 0
    assert "[dry-run] docker\nps\n-a" in out


def test_run_dry_run_quiet_is_silent(monkeypatch, capfd):
    monkeypatch.setattr(docker.config, "DRY_RUN", True)
    monkeypatch.setattr(
        docker.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError)
    )

    rc = docker.run("docker", "ps", quiet=True)

    assert rc == 0
    assert capfd.readouterr().out == ""


def test_run_real_mode_executes_and_returns_returncode(monkeypatch):
    captured = {}

    def _fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return _FakeCompleted(returncode=7)

    monkeypatch.setattr(docker.subprocess, "run", _fake_run)

    rc = docker.run("docker", "ps")

    assert rc == 7
    assert captured["argv"] == ["docker", "ps"]
    assert captured["kwargs"] == {}


def test_run_real_mode_quiet_discards_output(monkeypatch):
    captured = {}

    def _fake_run(argv, **kwargs):
        captured["kwargs"] = kwargs
        return _FakeCompleted(returncode=0)

    monkeypatch.setattr(docker.subprocess, "run", _fake_run)

    docker.run("docker", "ps", quiet=True)

    assert captured["kwargs"]["stdout"] == docker.subprocess.DEVNULL
    assert captured["kwargs"]["stderr"] == docker.subprocess.DEVNULL


# ── container_name / _names / running_names / container_running ─────────────


def test_container_name_prefixes_service():
    assert (
        docker.container_name("api-gateway")
        == f"{docker.config.CONTAINER_PREFIX}-api-gateway"
    )


def test_names_returns_lines(monkeypatch):
    monkeypatch.setattr(
        docker.subprocess,
        "run",
        lambda argv, **kw: _FakeCompleted(stdout="minder-a\nminder-b\n"),
    )
    assert docker._names() == ["minder-a", "minder-b"]


def test_names_all_containers_inserts_dash_a(monkeypatch):
    captured = {}

    def _fake_run(argv, **kw):
        captured["argv"] = argv
        return _FakeCompleted(stdout="")

    monkeypatch.setattr(docker.subprocess, "run", _fake_run)

    docker._names(all_containers=True)

    assert captured["argv"] == ["docker", "ps", "-a", "--format", "{{.Names}}"]


def test_names_returns_empty_on_oserror(monkeypatch):
    def _raise(argv, **kw):
        raise OSError("boom")

    monkeypatch.setattr(docker.subprocess, "run", _raise)
    assert docker._names() == []


def test_running_names_delegates_to_names(monkeypatch):
    monkeypatch.setattr(docker, "_names", lambda **kw: ["minder-x"])
    assert docker.running_names() == ["minder-x"]


def test_container_running_true_when_present(monkeypatch):
    monkeypatch.setattr(docker, "_names", lambda **kw: [docker.container_name("redis")])
    assert docker.container_running("redis") is True


def test_container_running_false_when_absent(monkeypatch):
    monkeypatch.setattr(docker, "_names", lambda **kw: [])
    assert docker.container_running("redis") is False


# ── created_services ─────────────────────────────────────────────────────────


def test_created_services_strips_prefix_and_filters(monkeypatch):
    monkeypatch.setattr(
        docker,
        "capture",
        lambda argv: "minder-graph-rag\nother-thing\nminder-marketplace\n",
    )
    assert docker.created_services() == ["graph-rag", "marketplace"]


def test_created_services_empty_when_nothing_matches(monkeypatch):
    monkeypatch.setattr(docker, "capture", lambda argv: "unrelated\n")
    assert docker.created_services() == []


# ── capture / cmd_ok ───────────────────────────────────────────────────────────


def test_capture_returns_stdout(monkeypatch):
    monkeypatch.setattr(
        docker.subprocess, "run", lambda argv, **kw: _FakeCompleted(stdout="hello\n")
    )
    assert docker.capture(["echo", "hi"]) == "hello\n"


def test_capture_returns_empty_on_oserror(monkeypatch):
    def _raise(argv, **kw):
        raise OSError("boom")

    monkeypatch.setattr(docker.subprocess, "run", _raise)
    assert docker.capture(["docker", "ps"]) == ""


def test_cmd_ok_true_on_zero_returncode(monkeypatch):
    monkeypatch.setattr(
        docker.subprocess, "run", lambda argv, **kw: _FakeCompleted(returncode=0)
    )
    assert docker.cmd_ok(["true"]) is True


def test_cmd_ok_false_on_nonzero_returncode(monkeypatch):
    monkeypatch.setattr(
        docker.subprocess, "run", lambda argv, **kw: _FakeCompleted(returncode=1)
    )
    assert docker.cmd_ok(["false"]) is False


def test_cmd_ok_false_on_oserror(monkeypatch):
    def _raise(argv, **kw):
        raise OSError("boom")

    monkeypatch.setattr(docker.subprocess, "run", _raise)
    assert docker.cmd_ok(["nonexistent"]) is False


# ── tcp_open ───────────────────────────────────────────────────────────────────


def test_tcp_open_true_when_connection_succeeds(monkeypatch):
    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        docker.socket, "create_connection", lambda addr, timeout=None: _Ctx()
    )
    assert docker.tcp_open("127.0.0.1", 8000) is True


def test_tcp_open_false_on_oserror(monkeypatch):
    def _raise(addr, timeout=None):
        raise OSError("refused")

    monkeypatch.setattr(docker.socket, "create_connection", _raise)
    assert docker.tcp_open("127.0.0.1", 8000) is False


# ── has_healthcheck ────────────────────────────────────────────────────────────


def test_has_healthcheck_true(monkeypatch):
    monkeypatch.setattr(
        docker.subprocess,
        "run",
        lambda argv, **kw: _FakeCompleted(returncode=0, stdout="yes\n"),
    )
    assert docker.has_healthcheck("api-gateway") is True


def test_has_healthcheck_false_when_stdout_not_yes(monkeypatch):
    monkeypatch.setattr(
        docker.subprocess,
        "run",
        lambda argv, **kw: _FakeCompleted(returncode=0, stdout=""),
    )
    assert docker.has_healthcheck("otel-collector") is False


def test_has_healthcheck_false_on_nonzero_returncode(monkeypatch):
    monkeypatch.setattr(
        docker.subprocess,
        "run",
        lambda argv, **kw: _FakeCompleted(returncode=1, stdout="yes\n"),
    )
    assert docker.has_healthcheck("ghost") is False


def test_has_healthcheck_false_on_oserror(monkeypatch):
    def _raise(argv, **kw):
        raise OSError("boom")

    monkeypatch.setattr(docker.subprocess, "run", _raise)
    assert docker.has_healthcheck("ghost") is False


# ── container_exists / container_health ───────────────────────────────────────


def test_container_exists_true(monkeypatch):
    monkeypatch.setattr(docker, "_names", lambda **kw: [docker.container_name("redis")])
    assert docker.container_exists("redis") is True


def test_container_health_returns_status(monkeypatch):
    monkeypatch.setattr(
        docker.subprocess,
        "run",
        lambda argv, **kw: _FakeCompleted(returncode=0, stdout="healthy\n"),
    )
    assert docker.container_health("api-gateway") == "healthy"


def test_container_health_na_on_nonzero_returncode(monkeypatch):
    monkeypatch.setattr(
        docker.subprocess,
        "run",
        lambda argv, **kw: _FakeCompleted(returncode=1, stdout=""),
    )
    assert docker.container_health("ghost") == "n/a"


def test_container_health_na_on_empty_stdout(monkeypatch):
    monkeypatch.setattr(
        docker.subprocess,
        "run",
        lambda argv, **kw: _FakeCompleted(returncode=0, stdout="  \n"),
    )
    assert docker.container_health("otel-collector") == "n/a"


def test_container_health_na_on_oserror(monkeypatch):
    def _raise(argv, **kw):
        raise OSError("boom")

    monkeypatch.setattr(docker.subprocess, "run", _raise)
    assert docker.container_health("ghost") == "n/a"


# ── network_exists / volume_exists ─────────────────────────────────────────────


def test_network_exists_true(monkeypatch):
    monkeypatch.setattr(
        docker.subprocess,
        "run",
        lambda argv, **kw: _FakeCompleted(stdout="bridge\nminder-net\n"),
    )
    assert docker.network_exists("minder-net") is True


def test_network_exists_false(monkeypatch):
    monkeypatch.setattr(
        docker.subprocess, "run", lambda argv, **kw: _FakeCompleted(stdout="bridge\n")
    )
    assert docker.network_exists("minder-net") is False


def test_network_exists_false_on_oserror(monkeypatch):
    def _raise(argv, **kw):
        raise OSError("boom")

    monkeypatch.setattr(docker.subprocess, "run", _raise)
    assert docker.network_exists("minder-net") is False


def test_volume_exists_true(monkeypatch):
    monkeypatch.setattr(
        docker.subprocess,
        "run",
        lambda argv, **kw: _FakeCompleted(stdout="minder-pgdata\n"),
    )
    assert docker.volume_exists("minder-pgdata") is True


def test_volume_exists_false_on_oserror(monkeypatch):
    def _raise(argv, **kw):
        raise OSError("boom")

    monkeypatch.setattr(docker.subprocess, "run", _raise)
    assert docker.volume_exists("minder-pgdata") is False


# ── wait_healthy ───────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _no_spinner_or_sleep(monkeypatch):
    monkeypatch.setattr(docker.log, "spinner_start", lambda *a, **k: None)
    monkeypatch.setattr(docker.log, "spinner_stop", lambda: None)
    monkeypatch.setattr(docker.time, "sleep", lambda secs: None)


def test_wait_healthy_returns_true_immediately_when_healthy(monkeypatch, capfd):
    monkeypatch.setattr(docker, "container_health", lambda svc: "healthy")

    assert docker.wait_healthy("api-gateway", timeout=90) is True
    assert "is healthy" in capfd.readouterr().out


def test_wait_healthy_returns_true_when_no_healthcheck_defined(monkeypatch, capfd):
    monkeypatch.setattr(docker, "container_health", lambda svc: "n/a")
    monkeypatch.setattr(docker, "has_healthcheck", lambda svc: False)

    assert docker.wait_healthy("otel-collector", timeout=90) is True
    assert "no healthcheck defined" in capfd.readouterr().out


def test_wait_healthy_times_out_and_warns(monkeypatch, capfd):
    monkeypatch.setattr(docker, "container_health", lambda svc: "starting")
    monkeypatch.setattr(docker, "has_healthcheck", lambda svc: True)

    assert docker.wait_healthy("rag-pipeline", timeout=3) is False
    out = capfd.readouterr().out
    assert "not healthy after 3s" in out
    assert "starting" in out


# ── wait_postgres_ready ────────────────────────────────────────────────────────


def test_wait_postgres_ready_false_on_oserror(monkeypatch, capfd):
    def _raise(argv, **kw):
        raise OSError("docker not found")

    monkeypatch.setattr(docker.subprocess, "run", _raise)

    assert docker.wait_postgres_ready(timeout=2) is False
    assert "did not become ready" in capfd.readouterr().out


def test_wait_postgres_ready_false_after_timeout(monkeypatch, capfd):
    monkeypatch.setattr(
        docker.subprocess, "run", lambda argv, **kw: _FakeCompleted(returncode=1)
    )

    assert docker.wait_postgres_ready(timeout=4) is False
    out = capfd.readouterr().out
    assert "did not become ready within 4s" in out


# ── wait_port ──────────────────────────────────────────────────────────────────


def test_wait_port_true_when_connection_succeeds(monkeypatch):
    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        docker.socket, "create_connection", lambda addr, timeout=None: _Ctx()
    )
    assert docker.wait_port("127.0.0.1", 5432, timeout=10) is True


def test_wait_port_false_after_timeout(monkeypatch):
    def _raise(addr, timeout=None):
        raise OSError("refused")

    monkeypatch.setattr(docker.socket, "create_connection", _raise)
    assert docker.wait_port("127.0.0.1", 5432, timeout=4) is False


# ── compose_services ───────────────────────────────────────────────────────────


def test_compose_services_strips_and_drops_blank_lines(monkeypatch):
    monkeypatch.setattr(
        docker, "capture", lambda argv: "postgres\n\n  redis  \napi-gateway\n"
    )
    assert docker.compose_services() == ["postgres", "redis", "api-gateway"]


def test_compose_services_empty_when_capture_fails(monkeypatch):
    monkeypatch.setattr(docker, "capture", lambda argv: "")
    assert docker.compose_services() == []


# ── compose / compose_monitoring / compose_all ────────────────────────────────


def test_compose_passes_compose_file_and_args(monkeypatch):
    captured = {}
    monkeypatch.setattr(docker, "run", lambda *args: captured.setdefault("args", args))

    docker.compose("up", "-d")

    assert captured["args"] == (
        "docker",
        "compose",
        "-f",
        docker.config.COMPOSE_FILE,
        "up",
        "-d",
    )


def test_compose_monitoring_adds_monitoring_profile(monkeypatch):
    captured = {}
    monkeypatch.setattr(docker, "run", lambda *args: captured.setdefault("args", args))

    docker.compose_monitoring("up", "-d", "grafana")

    assert captured["args"] == (
        "docker",
        "compose",
        "-f",
        docker.config.COMPOSE_FILE,
        "--profile",
        "monitoring",
        "up",
        "-d",
        "grafana",
    )


def test_compose_all_activates_every_teardown_profile(monkeypatch):
    captured = {}
    monkeypatch.setattr(docker, "run", lambda *args: captured.setdefault("args", args))

    docker.compose_all("down", "-v")

    args = captured["args"]
    assert args[:4] == ("docker", "compose", "-f", docker.config.COMPOSE_FILE)
    for profile in (
        "monitoring",
        "internal-ollama",
        "ollama-router",
        "internal-tts-stt",
        "tts-stt-router",
    ):
        assert profile in args
    assert args[-2:] == ("down", "-v")
