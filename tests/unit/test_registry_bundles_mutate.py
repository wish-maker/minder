"""Unit tests for the plugin-registry MUTATING bundle endpoints (#65 item 2, PR2):
enable / disable / reconcile.

Verifies they (a) persist intent to bundles.state.json, (b) orchestrate the right
services via an injected container-ops fake (start on enable, stop orphans on disable),
(c) report never-materialised services as `pending_create`, (d) reject disabling core,
(e) 404 unknown bundles, and (f) require auth. The route is loaded by path (shared
`routes` package name) exactly like the read-only test.
"""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

_ROUTE = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "services"
    / "plugin-registry"
    / "routes"
    / "bundles.py"
)

_COMPOSE = """\
services:
  traefik:
    labels: [minder.bundle=core]
  ollama:
    labels:
    - minder.bundle=inference,rag,chat
  qdrant:
    labels: [minder.bundle=rag]
  tts-stt:
    labels: [minder.bundle=voice]
"""


def _load_route_module():
    spec = importlib.util.spec_from_file_location("registry_bundles_route", _ROUTE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeOps:
    """Records start/stop; a service in `existing` reports 'changed', else 'absent'."""

    def __init__(self, existing):
        self.existing = set(existing)
        self.started = []
        self.stopped = []

    async def start(self, svc):
        self.started.append(svc)
        return "changed" if svc in self.existing else "absent"

    async def stop(self, svc):
        self.stopped.append(svc)
        return "changed" if svc in self.existing else "absent"


def _client(tmp_path, *, state, ops, auth=True):
    compose = tmp_path / "docker-compose.yml"
    compose.write_text(_COMPOSE, encoding="utf-8")
    state_path = tmp_path / "bundles.state.json"
    if state is not None:
        state_path.write_text(json.dumps(state), encoding="utf-8")
    settings = SimpleNamespace(
        BUNDLES_COMPOSE_PATH=str(compose),
        BUNDLES_STATE_PATH=str(state_path),
        CONTAINER_PREFIX="minder",
    )
    mod = _load_route_module()
    logger = SimpleNamespace(info=lambda *a, **k: None)
    app = FastAPI()
    app.include_router(
        mod.build_bundles_router(settings=settings, logger=logger, container_ops=ops)
    )
    if auth:
        app.dependency_overrides[mod.get_current_user] = lambda: {"sub": "tester"}
    return TestClient(app, raise_server_exceptions=True), state_path


def _read_state(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_enable_persists_intent_and_starts_active_services(tmp_path):
    ops = FakeOps(existing={"tts-stt"})  # voice container exists but is stopped
    client, state_path = _client(tmp_path, state={"voice": {"enabled": False}}, ops=ops)
    r = client.post("/v1/bundles/voice/enable")
    assert r.status_code == 200
    body = r.json()
    assert body == {
        "bundle": "voice",
        "enabled": True,
        "started": ["tts-stt"],
        "already_running": [],
        "pending_create": [],
        "errors": [],
    }
    assert ops.started == ["tts-stt"]
    assert _read_state(state_path)["voice"] == {"enabled": True}  # intent persisted


def test_enable_reports_never_created_service_as_pending(tmp_path):
    ops = FakeOps(existing=set())  # nothing materialised (bundle off since install)
    client, _ = _client(tmp_path, state={"voice": {"enabled": False}}, ops=ops)
    body = client.post("/v1/bundles/voice/enable").json()
    assert body["started"] == []
    assert body["pending_create"] == ["tts-stt"]


def test_disable_persists_and_stops_only_orphans(tmp_path):
    # Disabling voice orphans tts-stt (exclusive). ollama stays (inference/rag/chat).
    ops = FakeOps(existing={"tts-stt", "ollama"})
    client, state_path = _client(tmp_path, state=None, ops=ops)
    body = client.post("/v1/bundles/voice/disable").json()
    assert body["enabled"] is False
    assert body["orphaned"] == ["tts-stt"]
    assert body["stopped"] == ["tts-stt"]
    assert ops.stopped == ["tts-stt"]  # ollama NOT stopped
    assert _read_state(state_path)["voice"] == {"enabled": False}


def test_disable_core_rejected(tmp_path):
    client, _ = _client(tmp_path, state=None, ops=FakeOps(existing=set()))
    assert client.post("/v1/bundles/core/disable").status_code == 409


def test_enable_unknown_bundle_404(tmp_path):
    client, _ = _client(tmp_path, state=None, ops=FakeOps(existing=set()))
    assert client.post("/v1/bundles/nope/enable").status_code == 404


def test_reconcile_starts_active_and_stops_orphans(tmp_path):
    ops = FakeOps(existing={"tts-stt", "ollama", "qdrant", "traefik"})
    client, _ = _client(tmp_path, state={"voice": {"enabled": False}}, ops=ops)
    body = client.post("/v1/bundles/reconcile").json()
    assert "tts-stt" in body["stopped"]  # orphaned by disabled voice
    assert set(body["started"]) >= {"ollama", "qdrant", "traefik"}  # active ones


def test_mutating_endpoints_require_auth(tmp_path):
    client, _ = _client(tmp_path, state=None, ops=FakeOps(existing=set()), auth=False)
    # No auth override + no token → get_current_user rejects.
    assert client.post("/v1/bundles/voice/disable").status_code in (401, 403)
