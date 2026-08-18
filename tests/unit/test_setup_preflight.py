"""Unit tests for scripts/setup/preflight.py's validators.

Only ever exercised indirectly, via `preflight.check_prerequisites` being
monkeypatched to a no-op in test_setup_install.py -- every function in this
module (check_prerequisites, validate_gpu_environment,
validate_ai_compute_mode, validate_compute_resource_profile, and the
_capture/_free_gb/_busy_ports helpers) had zero direct coverage.

subprocess.run, shutil.which/disk_usage, docker.cmd_ok/tcp_open, env.get, and
log.* are all monkeypatched -- no real Docker/network/subprocess calls.
capfd (not capsys) because log writes to sys.stdout.buffer, matching
test_setup_health.py/test_setup_doctor_run.py's established convention.
"""

import pytest

from scripts.setup import preflight

# The functions under test write directly to os.environ (not via a mockable
# seam) -- save/restore every key any of them can set, so this file never
# leaks state into other test files sharing the same process's os.environ.
_MUTATED_ENV_KEYS = (
    "GPU_AVAILABLE",
    "AI_ENDPOINT_STRATEGY",
    "AI_LOCAL_OLLAMA_URL",
    "AI_LAN_OLLAMA_URL",
    "AI_ENABLE_FALLBACK",
    "AI_FALLBACK_TIMEOUT_MS",
    "COMPUTE_CPU_LIMIT",
    "COMPUTE_MEMORY_LIMIT",
)


@pytest.fixture(autouse=True)
def _restore_mutated_env():
    saved = {k: preflight.os.environ.get(k) for k in _MUTATED_ENV_KEYS}
    yield
    for k, v in saved.items():
        if v is None:
            preflight.os.environ.pop(k, None)
        else:
            preflight.os.environ[k] = v


# ── _capture ─────────────────────────────────────────────────────────────────


class _FakeCompleted:
    def __init__(self, returncode=0, stdout=""):
        self.returncode = returncode
        self.stdout = stdout


def test_capture_returns_stdout_on_success(monkeypatch):
    monkeypatch.setattr(
        preflight.subprocess,
        "run",
        lambda *a, **k: _FakeCompleted(0, "Docker version 24.0.0\n"),
    )
    assert preflight._capture(["docker", "--version"]) == "Docker version 24.0.0\n"


def test_capture_returns_empty_on_nonzero_exit(monkeypatch):
    monkeypatch.setattr(
        preflight.subprocess, "run", lambda *a, **k: _FakeCompleted(1, "error")
    )
    assert preflight._capture(["docker", "--version"]) == ""


def test_capture_returns_empty_on_oserror(monkeypatch):
    def _boom(*a, **k):
        raise OSError("not found")

    monkeypatch.setattr(preflight.subprocess, "run", _boom)
    assert preflight._capture(["docker", "--version"]) == ""


# ── _free_gb ─────────────────────────────────────────────────────────────────


def test_free_gb_computes_from_disk_usage(monkeypatch):
    monkeypatch.setattr(
        preflight.shutil,
        "disk_usage",
        lambda path: type("U", (), {"free": 20 * 1024**3})(),
    )
    assert preflight._free_gb("/") == 20


def test_free_gb_oserror_defaults_to_999(monkeypatch):
    def _boom(path):
        raise OSError("no such device")

    monkeypatch.setattr(preflight.shutil, "disk_usage", _boom)
    assert preflight._free_gb("/") == 999


# ── _busy_ports ────────────────────────────────────────────────────────────────


def test_busy_ports_flags_open_ports_not_owned_by_minder(monkeypatch):
    monkeypatch.setattr(
        preflight.subprocess,
        "run",
        lambda *a, **k: _FakeCompleted(0, "0.0.0.0:5432->5432/tcp"),
    )
    monkeypatch.setattr(
        preflight.docker, "tcp_open", lambda host, port, timeout=1: port in (5432, 6379)
    )
    busy = preflight._busy_ports()
    # 5432 is published by Minder (":5432->" present) -- not busy; 6379 isn't.
    assert busy == ["6379"]


def test_busy_ports_empty_when_docker_ps_fails(monkeypatch):
    def _boom(*a, **k):
        raise OSError("docker not found")

    monkeypatch.setattr(preflight.subprocess, "run", _boom)
    monkeypatch.setattr(
        preflight.docker, "tcp_open", lambda host, port, timeout=1: False
    )
    assert preflight._busy_ports() == []


# ── check_prerequisites ────────────────────────────────────────────────────────


@pytest.fixture
def healthy_prereqs(monkeypatch, tmp_path):
    """A fully satisfied baseline: docker/compose/daemon/openssl/curl all
    present, compose file exists, plenty of disk, no busy ports."""
    monkeypatch.setattr(preflight.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(preflight.docker, "cmd_ok", lambda argv: True)
    monkeypatch.setattr(
        preflight, "_capture", lambda argv: "Docker version 24.0.0, build abc"
    )
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text("services: {}\n")
    monkeypatch.setattr(preflight.config, "COMPOSE_FILE", compose_file)
    monkeypatch.setattr(preflight, "_free_gb", lambda path: 50)
    monkeypatch.setattr(preflight, "_busy_ports", lambda: [])
    monkeypatch.setattr(preflight.config, "SCRIPT_DIR", tmp_path)
    monkeypatch.setattr(preflight.config, "SKIP_VERSION_CHECK", False)


def test_all_prerequisites_satisfied(healthy_prereqs, capfd):
    preflight.check_prerequisites()  # must not raise
    out = capfd.readouterr().out
    assert "All prerequisites satisfied" in out


def test_missing_docker_raises_systemexit(healthy_prereqs, monkeypatch, capfd):
    monkeypatch.setattr(
        preflight.shutil,
        "which",
        lambda name: None if name == "docker" else "/usr/bin/x",
    )
    with pytest.raises(SystemExit) as exc:
        preflight.check_prerequisites()
    assert exc.value.code == 1
    out = capfd.readouterr().out
    assert "Docker not installed" in out


def test_missing_compose_v2_raises_systemexit(healthy_prereqs, monkeypatch):
    monkeypatch.setattr(
        preflight.docker,
        "cmd_ok",
        lambda argv: argv != ["docker", "compose", "version"],
    )
    with pytest.raises(SystemExit):
        preflight.check_prerequisites()


def test_docker_daemon_not_running_raises_systemexit(
    healthy_prereqs, monkeypatch, capfd
):
    monkeypatch.setattr(
        preflight.docker, "cmd_ok", lambda argv: argv != ["docker", "info"]
    )
    with pytest.raises(SystemExit):
        preflight.check_prerequisites()
    out = capfd.readouterr().out
    assert "Docker daemon is not running" in out


def test_missing_openssl_warns_but_does_not_fail(healthy_prereqs, monkeypatch, capfd):
    monkeypatch.setattr(
        preflight.shutil,
        "which",
        lambda name: None if name == "openssl" else "/usr/bin/x",
    )
    preflight.check_prerequisites()  # must not raise
    out = capfd.readouterr().out
    assert "openssl not found" in out


def test_missing_curl_warns_and_skips_version_check(
    healthy_prereqs, monkeypatch, capfd
):
    monkeypatch.setattr(
        preflight.shutil, "which", lambda name: None if name == "curl" else "/usr/bin/x"
    )
    preflight.check_prerequisites()
    out = capfd.readouterr().out
    assert "curl not found" in out
    assert preflight.config.SKIP_VERSION_CHECK is True


def test_missing_compose_file_raises_systemexit(healthy_prereqs, monkeypatch, tmp_path):
    monkeypatch.setattr(preflight.config, "COMPOSE_FILE", tmp_path / "nope.yml")
    with pytest.raises(SystemExit):
        preflight.check_prerequisites()


def test_low_disk_warns_but_does_not_fail(healthy_prereqs, monkeypatch, capfd):
    monkeypatch.setattr(preflight, "_free_gb", lambda path: 5)
    preflight.check_prerequisites()
    out = capfd.readouterr().out
    assert "Low disk space" in out


def test_busy_ports_warns_but_does_not_fail(healthy_prereqs, monkeypatch, capfd):
    monkeypatch.setattr(preflight, "_busy_ports", lambda: ["5432", "6379"])
    preflight.check_prerequisites()
    out = capfd.readouterr().out
    assert "Ports already in use" in out
    assert "5432" in out and "6379" in out


# ── validate_gpu_environment ───────────────────────────────────────────────────


def test_gpu_environment_falls_back_to_cpu_without_nvidia_toolkit(monkeypatch, capfd):
    monkeypatch.setattr(preflight.docker, "cmd_ok", lambda argv: False)
    preflight.validate_gpu_environment()
    out = capfd.readouterr().out
    assert "NVIDIA Container Toolkit not found" in out
    assert preflight.os.environ["GPU_AVAILABLE"] == "false"


def test_gpu_environment_falls_back_to_cpu_with_zero_gpus(monkeypatch, capfd):
    monkeypatch.setattr(preflight.docker, "cmd_ok", lambda argv: True)
    monkeypatch.setattr(preflight, "_capture", lambda argv: "0\n")
    preflight.validate_gpu_environment()
    out = capfd.readouterr().out
    assert "No NVIDIA GPUs detected" in out
    assert preflight.os.environ["GPU_AVAILABLE"] == "false"


def test_gpu_environment_reports_detected_gpu(monkeypatch, capfd):
    monkeypatch.setattr(preflight.docker, "cmd_ok", lambda argv: True)
    responses = {
        "count": "1\n",
        "name": "NVIDIA GeForce RTX 4090\n",
        "memory.total": "24576 MiB\n",
    }

    def _fake_capture(argv):
        for key, val in responses.items():
            if key in " ".join(argv):
                return val
        return ""

    monkeypatch.setattr(preflight, "_capture", _fake_capture)
    preflight.validate_gpu_environment()
    out = capfd.readouterr().out
    assert "GPUs detected: 1" in out
    assert "RTX 4090" in out
    assert preflight.os.environ["GPU_AVAILABLE"] == "true"


def test_gpu_environment_unparseable_count_proceeds_as_nonzero(monkeypatch, capfd):
    monkeypatch.setattr(preflight.docker, "cmd_ok", lambda argv: True)
    monkeypatch.setattr(preflight, "_capture", lambda argv: "garbage")
    preflight.validate_gpu_environment()
    out = capfd.readouterr().out
    # An unparseable count is NOT treated as zero -- proceeds to report GPUs.
    assert "GPUs detected: garbage" in out
    assert preflight.os.environ["GPU_AVAILABLE"] == "true"


# ── validate_ai_compute_mode ───────────────────────────────────────────────────


def test_ai_compute_mode_defaults_to_internal(monkeypatch):
    monkeypatch.setattr(preflight.env, "get", lambda key: "")
    rc = preflight.validate_ai_compute_mode()
    assert rc == 0
    assert preflight.os.environ["AI_ENDPOINT_STRATEGY"] == "local"
    assert preflight.os.environ["AI_ENABLE_FALLBACK"] == "false"


def test_ai_compute_mode_external_requires_url(monkeypatch, capfd):
    monkeypatch.setattr(
        preflight.env,
        "get",
        lambda key: "external" if key == "AI_COMPUTE_MODE" else "",
    )
    rc = preflight.validate_ai_compute_mode()
    assert rc == 1
    out = capfd.readouterr().out
    assert "requires EXTERNAL_GPU_NODE_URL" in out


def test_ai_compute_mode_external_with_url(monkeypatch):
    monkeypatch.setattr(
        preflight.env,
        "get",
        lambda key: {
            "AI_COMPUTE_MODE": "external",
            "EXTERNAL_GPU_NODE_URL": "http://gpu.example.com:11434",
        }.get(key, ""),
    )
    rc = preflight.validate_ai_compute_mode()
    assert rc == 0
    assert preflight.os.environ["AI_ENDPOINT_STRATEGY"] == "external"
    assert preflight.os.environ["AI_LAN_OLLAMA_URL"] == "http://gpu.example.com:11434"


def test_ai_compute_mode_hybrid_without_url_falls_back_to_local(monkeypatch, capfd):
    monkeypatch.setattr(
        preflight.env,
        "get",
        lambda key: "hybrid" if key == "AI_COMPUTE_MODE" else "",
    )
    rc = preflight.validate_ai_compute_mode()
    assert rc == 0
    out = capfd.readouterr().out
    assert "recommended EXTERNAL_GPU_NODE_URL" in out
    assert preflight.os.environ["AI_LAN_OLLAMA_URL"] == "http://minder-ollama:11434"


def test_ai_compute_mode_hybrid_with_url(monkeypatch):
    monkeypatch.setattr(
        preflight.env,
        "get",
        lambda key: {
            "AI_COMPUTE_MODE": "hybrid",
            "EXTERNAL_GPU_NODE_URL": "http://gpu.example.com:11434",
        }.get(key, ""),
    )
    rc = preflight.validate_ai_compute_mode()
    assert rc == 0
    assert preflight.os.environ["AI_ENABLE_FALLBACK"] == "true"
    assert preflight.os.environ["AI_FALLBACK_TIMEOUT_MS"] == "5000"


def test_ai_compute_mode_invalid_value(monkeypatch, capfd):
    monkeypatch.setattr(
        preflight.env,
        "get",
        lambda key: "quantum" if key == "AI_COMPUTE_MODE" else "",
    )
    rc = preflight.validate_ai_compute_mode()
    assert rc == 1
    out = capfd.readouterr().out
    assert "Invalid AI_COMPUTE_MODE: quantum" in out


# ── validate_compute_resource_profile ─────────────────────────────────────────


@pytest.mark.parametrize(
    "profile,cpu,mem",
    [
        ("low", "1.0", "2g"),
        ("medium", "2.0", "4g"),
        ("high", "4.0", "8g"),
        ("enterprise", "8.0", "16g"),
    ],
)
def test_resource_profile_sets_expected_limits(monkeypatch, profile, cpu, mem):
    monkeypatch.setattr(preflight.env, "get", lambda key: profile)
    rc = preflight.validate_compute_resource_profile()
    assert rc == 0
    assert preflight.os.environ["COMPUTE_CPU_LIMIT"] == cpu
    assert preflight.os.environ["COMPUTE_MEMORY_LIMIT"] == mem


def test_resource_profile_defaults_to_medium(monkeypatch):
    monkeypatch.setattr(preflight.env, "get", lambda key: "")
    rc = preflight.validate_compute_resource_profile()
    assert rc == 0
    assert preflight.os.environ["COMPUTE_CPU_LIMIT"] == "2.0"


def test_enterprise_profile_reports_gpu_enabled_when_available(monkeypatch, capfd):
    monkeypatch.setattr(preflight.env, "get", lambda key: "enterprise")
    monkeypatch.setitem(preflight.os.environ, "GPU_AVAILABLE", "true")
    preflight.validate_compute_resource_profile()
    out = capfd.readouterr().out
    assert "GPU acceleration: ENABLED" in out


def test_enterprise_profile_warns_when_gpu_unavailable(monkeypatch, capfd):
    monkeypatch.setattr(preflight.env, "get", lambda key: "enterprise")
    monkeypatch.setitem(preflight.os.environ, "GPU_AVAILABLE", "false")
    preflight.validate_compute_resource_profile()
    out = capfd.readouterr().out
    assert "GPU acceleration: DISABLED" in out


def test_resource_profile_invalid_value(monkeypatch, capfd):
    monkeypatch.setattr(preflight.env, "get", lambda key: "ultra")
    rc = preflight.validate_compute_resource_profile()
    assert rc == 1
    out = capfd.readouterr().out
    assert "Invalid COMPUTE_RESOURCE_PROFILE: ultra" in out
