"""Regression guard for #405: internal-service write endpoints must reject
unauthenticated requests.

plugin-state-manager and model-management are bound 127.0.0.1-only with no
Traefik route, but their mutating (POST/PUT/DELETE/PATCH) endpoints had NO
application-level auth in the route handler itself -- reachable by any
container on minder-network or anyone with host access, no credential
required. Fixed by adding `Depends(get_current_user_or_service)` (accepts
either a user JWT or the internal X-Service-Token, same dependency api-
gateway/plugin-registry already use) to each mutating endpoint.

graph-rag and rag-pipeline got the identical fix but are covered in
test_graph_rag_knowledge_graph_handler.py / test_rag_pipeline_retrieval.py
instead of here -- both already own a from-scratch importer for their
service's `routes` package (working around real per-service dependencies:
graph-rag needs spacy faked out, rag-pipeline registers process-global
Prometheus metrics that collide on a second import), and this session's own
precedent (see those files' docstrings) is that a SECOND independent
fresh-import site for the same service crashes the whole pytest run --
confirmed live while writing this file.

These tests mount the REAL routers (not the underlying business-logic
functions, which existing tests already cover) in a throwaway app and
confirm: no credential -> 401 before the handler body ever runs; the
internal service token -> the auth gate itself passes (a further failure, if
any, comes from unmocked business logic, not from the dependency).
"""

import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared.auth.jwt_middleware import get_current_user_or_service

_SERVICES = Path(__file__).resolve().parents[2] / "src" / "services"

_SERVICE_TOKEN = "unit-test-service-token"


@pytest.fixture(autouse=True)
def _service_sync_token(monkeypatch):
    # get_current_user_or_service only honours X-Service-Token when
    # SERVICE_SYNC_TOKEN is set -- set it before any of the below imports run.
    monkeypatch.setenv("SERVICE_SYNC_TOKEN", _SERVICE_TOKEN)
    import shared.auth.jwt_middleware as jwt_mw

    monkeypatch.setattr(jwt_mw, "SERVICE_SYNC_TOKEN", _SERVICE_TOKEN)


def _fresh_import(service_dir: str, module_path: str):
    """Same pattern as test_plugin_registry_webhook_persistence.py: services
    share top-level module names (core/config/models/routes), so a prior
    service's same-named modules must be cleared before importing another's."""
    sys.path.insert(0, str(_SERVICES / service_dir))
    for stale in list(sys.modules):
        if stale.split(".")[0] in ("core", "config", "models", "routes", "domain"):
            del sys.modules[stale]
    return importlib.import_module(module_path)


def _app_with_router(router, prefix: str = "") -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix=prefix)
    # Exceptions from unmocked business logic (reached only once auth passes)
    # should surface as a real 500 response, not propagate and fail the test
    # for a reason unrelated to what's being checked here (the auth gate).
    return TestClient(app, raise_server_exceptions=False)


# ── plugin-state-manager ─────────────────────────────────────────────────────


def test_plugin_state_manager_enable_requires_auth():
    state = _fresh_import("plugin-state-manager", "routes.state")
    client = _app_with_router(state.router)
    resp = client.post("/state/news/enable", json={"reason": "test"})
    assert resp.status_code == 401


def test_plugin_state_manager_enable_accepts_service_token(monkeypatch):
    state = _fresh_import("plugin-state-manager", "routes.state")
    monkeypatch.setattr(
        state, "get_db_pool", MagicMock(side_effect=RuntimeError("no real db"))
    )
    client = _app_with_router(state.router)
    resp = client.post(
        "/state/news/enable",
        json={"reason": "test"},
        headers={"X-Service-Token": _SERVICE_TOKEN},
    )
    # Auth gate passed (not 401) -- the RuntimeError from the unmocked-DB stub
    # surfaces as a 500, proving we got past Depends() into the handler body.
    assert resp.status_code == 500


def test_plugin_state_manager_disable_requires_auth():
    state = _fresh_import("plugin-state-manager", "routes.state")
    client = _app_with_router(state.router)
    resp = client.post("/state/news/disable", json={"reason": "test"})
    assert resp.status_code == 401


def test_plugin_state_manager_update_config_requires_auth():
    state = _fresh_import("plugin-state-manager", "routes.state")
    client = _app_with_router(state.router)
    resp = client.patch("/state/news", json={"config": {}})
    assert resp.status_code == 401


def test_plugin_state_manager_license_update_requires_auth():
    licensing = _fresh_import("plugin-state-manager", "routes.licensing")
    client = _app_with_router(licensing.router)
    resp = client.patch(
        "/plugins/news/license", json={"license_tier": "pro", "license_key": "x"}
    )
    assert resp.status_code == 401


def test_plugin_state_manager_tool_execute_requires_auth():
    tools = _fresh_import("plugin-state-manager", "routes.tools")
    # tools.router has a bare "" GET route (list_all_tools) -- mounting at "/"
    # with no prefix makes FastAPI reject the combined empty path, unrelated
    # to what's under test here.
    client = _app_with_router(tools.router, prefix="/tools")
    resp = client.post("/tools/get_news/execute", json={"parameters": {}})
    assert resp.status_code == 401


def test_plugin_state_manager_tool_execute_uses_verified_identity_not_body(
    monkeypatch,
):
    """Found in a background audit: execute_tool_endpoint used to pass the
    client-supplied request.user_id straight to the license/tier check instead
    of the JWT identity FastAPI's own auth dependency already verified --
    inert today only because the tier lookup is hardcoded to "community"
    regardless of user_id (core/license.py's #47 stub), but a real per-user
    tier lookup keyed on this would let any authenticated caller evaluate the
    check as anyone else. Confirm the verified `sub` is what actually reaches
    execute_tool, even if a request body tries to smuggle a different
    identity in (ToolExecutionRequest no longer even has a user_id field, so
    this also confirms that extra key is silently ignored, not honored)."""
    tools = _fresh_import("plugin-state-manager", "routes.tools")
    captured = {}

    async def fake_execute_tool(tool_name, parameters, user_id):
        captured["user_id"] = user_id
        captured["tool_name"] = tool_name
        return {
            "tool_name": tool_name,
            "plugin_name": "news",
            "result": {},
            "execution_time": 0.01,
            "tier_required": "community",
        }

    monkeypatch.setattr(tools, "execute_tool", fake_execute_tool)
    client = _app_with_router(tools.router, prefix="/tools")

    resp = client.post(
        "/tools/get_news/execute",
        json={"parameters": {}, "user_id": "someone-else"},
        headers={"X-Service-Token": _SERVICE_TOKEN},
    )

    assert resp.status_code == 200, resp.text
    assert captured["user_id"] == "internal-service"  # the verified sub, not the body


# ── model-management ─────────────────────────────────────────────────────────


def test_model_management_register_requires_auth():
    models_api = _fresh_import("model-management", "routes.models_api")
    router = models_api.build_models_router(
        ollama_manager=MagicMock(), models={}, logger=MagicMock()
    )
    client = _app_with_router(router)
    resp = client.post("/v1/models", json={"model_id": "llama3.2:latest"})
    assert resp.status_code == 401


def test_model_management_delete_requires_auth():
    models_api = _fresh_import("model-management", "routes.models_api")
    router = models_api.build_models_router(
        ollama_manager=MagicMock(), models={}, logger=MagicMock()
    )
    client = _app_with_router(router)
    resp = client.delete("/v1/models/llama3.2:latest")
    assert resp.status_code == 401


def test_model_management_fine_tune_requires_auth():
    models_api = _fresh_import("model-management", "routes.models_api")
    router = models_api.build_models_router(
        ollama_manager=MagicMock(), models={}, logger=MagicMock()
    )
    client = _app_with_router(router)
    resp = client.post("/v1/models/fine-tune", json={"model_id": "llama3.2:latest"})
    assert resp.status_code == 401


# ── model-management: #474 -- a real (non-admin) user JWT must 403, not just
# require *a* token. require_role_or_service still preserves the #405 service-
# token bypass unconditionally (proven by the _accepts_service_token tests
# above); these prove the ADDED restriction on the user-JWT path.


def _app_with_non_admin_user(router):
    app = FastAPI()
    app.include_router(router)
    # require_role_or_service resolves the user via Depends(get_current_user_or_service)
    # -- a real nested FastAPI dependency -- so overriding THAT function (not the
    # get_current_user it calls internally as a plain function, not via Depends)
    # is what actually intercepts it.
    app.dependency_overrides[get_current_user_or_service] = lambda: {
        "sub": "1",
        "role": "user",
    }
    return TestClient(app, raise_server_exceptions=False)


def test_model_management_register_rejects_non_admin():
    models_api = _fresh_import("model-management", "routes.models_api")
    router = models_api.build_models_router(
        ollama_manager=MagicMock(), models={}, logger=MagicMock()
    )
    client = _app_with_non_admin_user(router)
    resp = client.post("/v1/models", json={"model_id": "llama3.2:latest"})
    assert resp.status_code == 403


def test_model_management_delete_rejects_non_admin():
    models_api = _fresh_import("model-management", "routes.models_api")
    router = models_api.build_models_router(
        ollama_manager=MagicMock(), models={}, logger=MagicMock()
    )
    client = _app_with_non_admin_user(router)
    resp = client.delete("/v1/models/llama3.2:latest")
    assert resp.status_code == 403


def test_model_management_fine_tune_rejects_non_admin():
    models_api = _fresh_import("model-management", "routes.models_api")
    router = models_api.build_models_router(
        ollama_manager=MagicMock(), models={}, logger=MagicMock()
    )
    client = _app_with_non_admin_user(router)
    resp = client.post("/v1/models/fine-tune", json={"model_id": "llama3.2:latest"})
    assert resp.status_code == 403


# ── marketplace: DELETE .../tools deactivates a plugin's AI tools platform-wide,
# for every user, not just the caller's own installation -- found reachable by
# any plain authenticated user, with nothing internally even calling it (dead-
# wired: not invoked from uninstall/disable anywhere in the codebase). Gated to
# require_role_or_service("admin") to match the same posture already used for
# other platform-wide destructive actions (model pull/delete, bundle disable).


def test_marketplace_deactivate_plugin_tools_requires_auth():
    # ai_tools.router already declares prefix="/v1/marketplace/ai" itself.
    ai_tools = _fresh_import("marketplace", "routes.ai_tools")
    client = _app_with_router(ai_tools.router)
    resp = client.delete(
        "/v1/marketplace/ai/plugins/11111111-1111-1111-1111-111111111111/tools"
    )
    assert resp.status_code == 401


def test_marketplace_deactivate_plugin_tools_rejects_non_admin():
    ai_tools = _fresh_import("marketplace", "routes.ai_tools")
    client = _app_with_non_admin_user(ai_tools.router)
    resp = client.delete(
        "/v1/marketplace/ai/plugins/11111111-1111-1111-1111-111111111111/tools"
    )
    assert resp.status_code == 403
