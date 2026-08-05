"""Real multi-service E2E harness (#318).

Starts real `uvicorn` subprocesses for api-gateway, plugin-registry, and
rag-pipeline bound to `127.0.0.1`, wired to each other via the same env vars
`docker-compose.yml` uses (just `localhost` instead of `minder-<service>`
hostnames), against real Postgres/Redis/Qdrant and a deterministic fake-Ollama
stub (`fake_ollama.py`). No Docker, no image builds — just real sockets, real
FastAPI apps, real routing code.

Every service's `main.py`/`config.py` does `sys.path.insert(0, "/app/src")`
(plugin-registry additionally `/app/plugins`, `/app/services/plugin-registry`)
— container-absolute paths that don't exist on a bare checkout. This harness
symlinks them once so no service code needs to change.
"""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SERVICES = _REPO_ROOT / "src" / "services"

# Real Postgres/Redis/Qdrant connection info — matches ci.yml's e2e-tests
# service-container env exactly (or, run locally, whatever a developer has
# started with the same credentials; see tests/e2e/README.md).
DB_HOST = os.environ.get("E2E_DB_HOST", "127.0.0.1")
DB_PORT = os.environ.get("E2E_DB_PORT", "5432")
DB_USER = os.environ.get("E2E_DB_USER", "postgres")
DB_PASSWORD = os.environ.get("E2E_DB_PASSWORD", "test_password")
DB_NAME = os.environ.get("E2E_DB_NAME", "minder_test")
REDIS_HOST = os.environ.get("E2E_REDIS_HOST", "127.0.0.1")
REDIS_PORT = os.environ.get("E2E_REDIS_PORT", "6379")
REDIS_PASSWORD = os.environ.get("E2E_REDIS_PASSWORD", "test_password")
QDRANT_HOST = os.environ.get("E2E_QDRANT_HOST", "127.0.0.1")
QDRANT_PORT = os.environ.get("E2E_QDRANT_PORT", "6333")

JWT_SECRET = "e2e-test-jwt-secret"

OLLAMA_PORT = 11434
GATEWAY_PORT = 8000
REGISTRY_PORT = 8001
RAG_PORT = 8004

STARTUP_TIMEOUT_S = 60


def _ensure_app_symlinks():
    """Create /app/{src,plugins,services/plugin-registry} -> the real repo
    paths, matching the container layout every service's sys.path.insert
    hardcodes. Idempotent — safe to call every test session."""
    app = Path("/app")
    app.mkdir(exist_ok=True)
    links = {
        app / "src": _REPO_ROOT / "src",
        app / "plugins": _REPO_ROOT / "src" / "plugins",
    }
    for link, target in links.items():
        if link.is_symlink() or link.exists():
            continue
        link.symlink_to(target)
    (app / "services").mkdir(exist_ok=True)
    registry_link = app / "services" / "plugin-registry"
    if not registry_link.is_symlink() and not registry_link.exists():
        registry_link.symlink_to(_SERVICES / "plugin-registry")
    # plugin-registry's PLUGINS_DATA_PATH default (/app/plugins-data) needs to
    # be a real, writable directory (not part of the checkout).
    (app / "plugins-data").mkdir(exist_ok=True)


def _wait_for_port(port: int, timeout_s: float) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.2)
    raise TimeoutError(f"nothing listening on 127.0.0.1:{port} after {timeout_s}s")


def _wait_for_health(
    base_url: str, timeout_s: float, proc: subprocess.Popen = None
) -> None:
    deadline = time.monotonic() + timeout_s
    last_error = None
    while time.monotonic() < deadline:
        if proc is not None and proc.poll() is not None:
            out = proc.stdout.read() if proc.stdout else ""
            raise RuntimeError(
                f"{base_url}: process exited early (code {proc.returncode}) before "
                f"becoming healthy. Output:\n{out}"
            )
        try:
            resp = httpx.get(f"{base_url}/health", timeout=2.0)
            if resp.status_code in (200, 503):  # 503 = degraded, still "up"
                return
        except Exception as e:  # noqa: BLE001 - genuinely want to retry any error
            last_error = e
        time.sleep(0.3)
    # Still alive but never became healthy — kill it first so reading stdout
    # (which blocks until the pipe closes) doesn't hang forever.
    if proc is not None:
        proc.terminate()
        proc.wait(timeout=5)
    out = proc.stdout.read() if proc is not None and proc.stdout else ""
    raise TimeoutError(
        f"{base_url}/health never became reachable after {timeout_s}s: {last_error}\n"
        f"Process output so far:\n{out}"
    )


def _spawn_uvicorn(service_dir: Path, port: int, env: dict) -> subprocess.Popen:
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=str(service_dir),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return proc


def _common_env(extra: dict) -> dict:
    env = os.environ.copy()
    env.update(
        {
            "DB_HOST": DB_HOST,
            "DB_PORT": DB_PORT,
            "DB_USER": DB_USER,
            "DB_PASSWORD": DB_PASSWORD,
            "DB_NAME": DB_NAME,
            "REDIS_HOST": REDIS_HOST,
            "REDIS_PORT": REDIS_PORT,
            "REDIS_PASSWORD": REDIS_PASSWORD,
            "JWT_SECRET": JWT_SECRET,
            "ENVIRONMENT": "test",
            "LOG_LEVEL": "WARNING",
            "PYTHONPATH": str(_REPO_ROOT / "src"),
        }
    )
    env.update(extra)
    return env


class LiveStack:
    def __init__(self, gateway_url, registry_url, rag_url, ollama_url):
        self.gateway_url = gateway_url
        self.registry_url = registry_url
        self.rag_url = rag_url
        self.ollama_url = ollama_url

    def reset_ollama(self):
        httpx.post(f"{self.ollama_url}/_control/reset", timeout=5.0)

    def queue_chat_responses(self, responses):
        httpx.post(
            f"{self.ollama_url}/_control/chat_responses",
            json={"responses": responses},
            timeout=5.0,
        )

    def queue_generate_responses(self, responses):
        httpx.post(
            f"{self.ollama_url}/_control/generate_responses",
            json={"responses": responses},
            timeout=5.0,
        )


@pytest.fixture(scope="session")
def live_stack():
    _ensure_app_symlinks()

    procs = []
    try:
        # Fake Ollama first — the real services probe it at startup.
        ollama_proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "fake_ollama:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(OLLAMA_PORT),
            ],
            cwd=str(Path(__file__).parent),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        procs.append(("fake-ollama", ollama_proc))
        _wait_for_port(OLLAMA_PORT, STARTUP_TIMEOUT_S)

        ollama_url = f"http://127.0.0.1:{OLLAMA_PORT}"

        registry_env = _common_env(
            {
                "OLLAMA_HOST": ollama_url,
                "PLUGINS_PATH": "/app/plugins",
                "PLUGINS_DATA_PATH": "/app/plugins-data",
            }
        )
        registry_proc = _spawn_uvicorn(
            _SERVICES / "plugin-registry", REGISTRY_PORT, registry_env
        )
        procs.append(("plugin-registry", registry_proc))

        registry_url = f"http://127.0.0.1:{REGISTRY_PORT}"
        _wait_for_health(registry_url, STARTUP_TIMEOUT_S, registry_proc)

        rag_env = _common_env(
            {
                "OLLAMA_HOST": ollama_url,
                "OLLAMA_BASE_URL": ollama_url,
                "QDRANT_HOST": QDRANT_HOST,
                "QDRANT_PORT": QDRANT_PORT,
                "MODEL_MANAGEMENT_URL": "http://127.0.0.1:1/unused",
            }
        )
        rag_proc = _spawn_uvicorn(_SERVICES / "rag-pipeline", RAG_PORT, rag_env)
        procs.append(("rag-pipeline", rag_proc))

        rag_url = f"http://127.0.0.1:{RAG_PORT}"
        _wait_for_health(rag_url, STARTUP_TIMEOUT_S, rag_proc)

        gateway_env = _common_env(
            {
                "OLLAMA_BASE_URL": ollama_url,
                "PLUGIN_REGISTRY_URL": registry_url,
                "RAG_PIPELINE_URL": rag_url,
                "MODEL_MANAGEMENT_URL": "http://127.0.0.1:1/unused",
            }
        )
        gateway_proc = _spawn_uvicorn(
            _SERVICES / "api-gateway", GATEWAY_PORT, gateway_env
        )
        procs.append(("api-gateway", gateway_proc))

        gateway_url = f"http://127.0.0.1:{GATEWAY_PORT}"
        _wait_for_health(gateway_url, STARTUP_TIMEOUT_S, gateway_proc)

        yield LiveStack(gateway_url, registry_url, rag_url, ollama_url)
    finally:
        for name, proc in reversed(procs):
            proc.terminate()
        for name, proc in reversed(procs):
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)


@pytest.fixture(autouse=True)
def _reset_fake_ollama(live_stack):
    """Every test starts with an empty scripted-response queue."""
    live_stack.reset_ollama()
    yield
