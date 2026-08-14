"""Unit test for the plugin-registry read-only bundles endpoint (#65 item 2).

The route file is loaded by path (not via `import routes.bundles`) so it doesn't bind
the top-level `routes` package name, which several services share in one pytest process.
It takes `settings` as a param and only imports `shared.bundle_graph`, so it loads
cleanly in isolation.
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


def _load_route_module():
    spec = importlib.util.spec_from_file_location("registry_bundles_route", _ROUTE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_COMPOSE = """\
services:
  ollama:
    labels:
    - minder.bundle=inference,rag,chat
  qdrant:
    labels: [minder.bundle=rag]
  traefik:
    labels: [minder.bundle=core]
  tts-stt:
    labels: [minder.bundle=voice]
"""


def _client(tmp_path, *, state):
    compose = tmp_path / "docker-compose.yml"
    compose.write_text(_COMPOSE, encoding="utf-8")
    state_path = tmp_path / "bundles.state.json"
    if state is not None:
        state_path.write_text(json.dumps(state), encoding="utf-8")
    settings = SimpleNamespace(
        BUNDLES_COMPOSE_PATH=str(compose),
        BUNDLES_STATE_PATH=str(state_path),
    )
    app = FastAPI()
    app.include_router(
        _load_route_module().build_bundles_router(settings=settings, logger=None)
    )
    return TestClient(app)


def test_no_state_file_everything_enabled(tmp_path):
    r = _client(tmp_path, state=None).get("/v1/bundles")
    assert r.status_code == 200
    body = r.json()
    assert all(b["enabled"] for b in body["bundles"])
    assert body["orphaned"] == []
    assert body["count"] == 5  # core/inference/rag/chat/voice


def test_disabled_bundle_orphans_its_exclusive_service(tmp_path):
    r = _client(tmp_path, state={"voice": {"enabled": False}}).get("/v1/bundles")
    body = r.json()
    voice = next(b for b in body["bundles"] if b["name"] == "voice")
    assert voice["enabled"] is False
    assert voice["services"][0] == {
        "name": "tts-stt",
        "active": False,
        "claimants": [],
        "image": None,  # fixture compose has no image: line for any service
    }
    assert body["orphaned"] == ["tts-stt"]
    # ollama stays active — still claimed by inference/rag/chat
    ollama = next(
        s for b in body["bundles"] for s in b["services"] if s["name"] == "ollama"
    )
    assert ollama["active"] is True


def test_missing_compose_returns_503(tmp_path):
    settings = SimpleNamespace(
        BUNDLES_COMPOSE_PATH=str(tmp_path / "gone.yml"),
        BUNDLES_STATE_PATH=str(tmp_path / "state.json"),
    )
    app = FastAPI()
    app.include_router(
        _load_route_module().build_bundles_router(settings=settings, logger=None)
    )
    r = TestClient(app).get("/v1/bundles")
    assert r.status_code == 503


def test_core_reported_as_core(tmp_path):
    body = _client(tmp_path, state=None).get("/v1/bundles").json()
    core = next(b for b in body["bundles"] if b["name"] == "core")
    assert core["core"] is True
    assert core["enabled"] is True


def test_service_image_included_when_pinned(tmp_path):
    compose = tmp_path / "docker-compose.yml"
    compose.write_text(
        """\
services:
  ollama:
    image: ollama/ollama:0.32.6
    labels:
    - minder.bundle=inference
  custom-built:
    labels:
    - minder.bundle=inference
  traefik:
    labels: [minder.bundle=core]
""",
        encoding="utf-8",
    )
    settings = SimpleNamespace(
        BUNDLES_COMPOSE_PATH=str(compose),
        BUNDLES_STATE_PATH=str(tmp_path / "bundles.state.json"),
    )
    app = FastAPI()
    app.include_router(
        _load_route_module().build_bundles_router(settings=settings, logger=None)
    )
    body = TestClient(app).get("/v1/bundles").json()
    services = {s["name"]: s for b in body["bundles"] for s in b["services"]}
    assert services["ollama"]["image"] == "ollama/ollama:0.32.6"
    # a locally-built service with no image: key reports None, not an error
    assert services["custom-built"]["image"] is None
