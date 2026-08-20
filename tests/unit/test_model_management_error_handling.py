"""Unit tests for model-management's error handling (#357).

#357: every route in models_api.py caught a generic Exception and returned
`HTTPException(503, detail=f"Failed to X: {str(e)}")` -- leaking the raw
driver/ollama exception string to the API client, and always using 503 even
for a genuine bug (not just "backend unreachable"). Switched to
shared.errors.backend_http_error, which classifies connectivity failures as
503 with a sanitized message and everything else as 500 -- never returning
str(e) to the caller.

Loaded via sys.path + a stale-cache clear (conftest.py loads every service's
main.py into ONE shared pytest process) -- matching this session's
established precedent.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from shared.auth.jwt_middleware import _rate_limit_store

_SERVICE_DIR = (
    Path(__file__).resolve().parents[2] / "src" / "services" / "model-management"
)


@pytest.fixture(autouse=True)
def _reset_rate_limit_store():
    """#746 added @enforce_rate_limit to test_model, which keys its in-memory
    store on user+path -- several tests below call the same path as the same
    fake user, so without this a later test could spuriously inherit an
    earlier test's count and trip the 429 it isn't testing for."""
    _rate_limit_store.clear()
    yield
    _rate_limit_store.clear()


_COLLISION_PRONE_NAMES = ("core", "routes", "models", "config")


def _isolated_import(module_path: str):
    saved_path = list(sys.path)
    saved_modules = {}
    for name in _COLLISION_PRONE_NAMES:
        for key in list(sys.modules):
            if key == name or key.startswith(name + "."):
                saved_modules[key] = sys.modules.pop(key)

    sys.path.insert(0, str(_SERVICE_DIR))
    import importlib

    try:
        return importlib.import_module(module_path)
    finally:
        sys.path[:] = saved_path
        for name in _COLLISION_PRONE_NAMES:
            for key in list(sys.modules):
                if key == name or key.startswith(name + "."):
                    sys.modules.pop(key, None)
        sys.modules.update(saved_modules)


class _NoopLogger:
    def info(self, *a, **k):
        pass

    def warning(self, *a, **k):
        pass

    def error(self, *a, **k):
        pass


def _client(ollama_manager, *, as_admin=False, authenticated=True):
    models_api = _isolated_import("routes.models_api")
    app = FastAPI()
    app.include_router(
        models_api.build_models_router(
            ollama_manager=ollama_manager, models={}, logger=_NoopLogger()
        )
    )
    if as_admin:
        from shared.auth.jwt_middleware import get_current_user_or_service

        app.dependency_overrides[get_current_user_or_service] = lambda: {
            "sub": "test-admin",
            "role": "admin",
        }
    # #746: test_model now requires ANY authenticated user (not admin-only), via
    # a plain get_current_user dependency -- overridden by default so every
    # pre-existing test_model test (written before #746, none of which pass
    # as_admin) keeps exercising the same 404/200/500 behavior it always did,
    # just now as a logged-in regular user instead of an anonymous caller.
    # authenticated=False leaves it un-overridden so a real (missing) auth
    # header actually 401s, for the new unauthenticated-rejection test below.
    if authenticated:
        from shared.auth.jwt_middleware import get_current_user

        app.dependency_overrides[get_current_user] = lambda: {
            "sub": "test-user",
            "username": "test-user",
            "role": "user",
        }
    return TestClient(app, raise_server_exceptions=False)


def test_connectivity_failure_returns_503_without_leaking_exception_text():
    secret_looking_detail = (
        "postgresql://minder:s3cr3t-password@10.0.0.5:5432/minder is unreachable"
    )
    ollama_manager = type(
        "M",
        (),
        {"list_models": AsyncMock(side_effect=ConnectionError(secret_looking_detail))},
    )()

    r = _client(ollama_manager).get("/models")

    assert r.status_code == 503
    assert secret_looking_detail not in r.text
    assert "unreachable" in r.json()["detail"].lower()


def test_generic_bug_returns_500_without_leaking_exception_text():
    ollama_manager = type(
        "M",
        (),
        {"list_models": AsyncMock(side_effect=KeyError("some_internal_field"))},
    )()

    r = _client(ollama_manager).get("/models")

    assert r.status_code == 500
    assert "some_internal_field" not in r.text


def test_list_models_success_path_unaffected():
    ollama_manager = type(
        "M",
        (),
        {
            "list_models": AsyncMock(
                return_value=[{"model": "llama3.2:latest", "size": 123}]
            )
        },
    )()

    r = _client(ollama_manager).get("/models")

    assert r.status_code == 200
    # #519: returns the shared {items,total,limit,offset} envelope, not a bare
    # array — the model at items[0] is the one Ollama reported.
    body = r.json()
    assert set(body) == {"items", "total", "limit", "offset"}
    assert body["total"] == 1
    assert body["items"][0]["id"] == "llama3.2:latest"


def test_list_models_envelope_paginates_and_reports_total():
    ollama_manager = type(
        "M",
        (),
        {
            "list_models": AsyncMock(
                return_value=[{"model": f"m{i}:latest", "size": 1} for i in range(5)]
            )
        },
    )()

    r = _client(ollama_manager).get("/models?limit=2&offset=1")

    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 5  # pre-slice total, not the page length
    assert body["limit"] == 2
    assert body["offset"] == 1
    assert [m["id"] for m in body["items"]] == ["m1:latest", "m2:latest"]


def test_test_unknown_model_is_404_not_503(monkeypatch):
    # #532: testing a model that isn't pulled must be a clean 404 (like
    # get/delete), not a 503 that leaks ollama's own "not found" message.
    ollama_manager = type(
        "M",
        (),
        {
            "list_models": AsyncMock(return_value=[{"model": "llama3.2:latest"}]),
            "test_model": AsyncMock(
                side_effect=AssertionError("must not reach ollama for an unknown model")
            ),
        },
    )()

    r = _client(ollama_manager).post(
        "/models/no-such-model/test", json={"prompt": "hi"}
    )

    assert r.status_code == 404
    assert r.json()["detail"] == "Model 'no-such-model' not found"


def test_pull_empty_model_id_rejected_at_the_edge():
    # #532: an empty model_id must fail request-body validation (→ 422 at the
    # edge) rather than passing through and failing deep in the ollama client's
    # own PullRequest, which surfaced as a 503 leaking that internal error.
    # Asserted at the model level (the endpoint itself is auth-gated).
    import pydantic

    models_api = _isolated_import("routes.models_api")
    with pytest.raises(pydantic.ValidationError):
        models_api.ModelPullRequest(model_id="")
    # a non-empty id is still accepted
    assert models_api.ModelPullRequest(model_id="llama3.2").model_id == "llama3.2"


@pytest.mark.parametrize(
    "model_id",
    [
        "llama3.2:latest",  # plain name:tag -- the colon is a tag separator, not a port
        "jimscard/whiterabbit-neo:latest",  # real namespaced community model, must stay allowed
        "qwen2.5-coder:32b",
    ],
)
def test_pull_default_library_model_ids_are_allowed(model_id):
    """#679-b: only a CUSTOM REGISTRY HOST should be rejected -- a plain name
    or a namespace under the default Ollama library must keep working."""
    models_api = _isolated_import("routes.models_api")
    assert models_api.ModelPullRequest(model_id=model_id).model_id == model_id


@pytest.mark.parametrize(
    "model_id",
    [
        "registry.example.com/library/llama3.2",  # domain in the first segment
        "myregistry:5000/model",  # explicit port in the first segment
        "localhost:11434/model",
        "localhost/model",
    ],
)
def test_pull_custom_registry_host_rejected_at_the_edge(model_id):
    """#679-b: block pulls from a custom OCI registry host -- no legitimate
    use of one exists anywhere in this codebase/docs today, so this is the
    simplest safe default rather than an allowlist."""
    import pydantic

    models_api = _isolated_import("routes.models_api")
    with pytest.raises(pydantic.ValidationError, match="custom registry host"):
        models_api.ModelPullRequest(model_id=model_id)


# --- register_model (POST /v1/models) ----------------------------------------


def test_register_model_already_exists_is_200_not_201():
    ollama_manager = type(
        "M",
        (),
        {
            "list_models": AsyncMock(return_value=[{"model": "llama3.2:latest"}]),
            "pull_model": AsyncMock(
                side_effect=AssertionError("must not pull an already-existing model")
            ),
        },
    )()

    r = _client(ollama_manager, as_admin=True).post(
        "/v1/models", json={"model_id": "llama3.2:latest"}
    )

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "already_exists"
    assert body["model"] == "llama3.2:latest"


def test_register_model_fresh_pull_is_201():
    ollama_manager = type(
        "M",
        (),
        {
            "list_models": AsyncMock(return_value=[]),
            "pull_model": AsyncMock(return_value={"status": "success"}),
        },
    )()

    r = _client(ollama_manager, as_admin=True).post(
        "/v1/models", json={"model_id": "llama3.2:latest"}
    )

    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "pulled"
    assert body["details"] == {"status": "success"}


def test_register_model_requires_admin():
    ollama_manager = type("M", (), {"list_models": AsyncMock(return_value=[])})()

    r = _client(ollama_manager, as_admin=False).post(
        "/v1/models", json={"model_id": "llama3.2:latest"}
    )

    assert r.status_code in (401, 403)


# --- get_model (GET /v1/models/{model_id}) -----------------------------------


def test_get_model_unknown_is_404():
    ollama_manager = type("M", (), {"list_models": AsyncMock(return_value=[])})()

    r = _client(ollama_manager).get("/v1/models/no-such-model")

    assert r.status_code == 404


def test_get_model_returns_details_and_promoted_capabilities():
    ollama_manager = type(
        "M",
        (),
        {
            "list_models": AsyncMock(return_value=[{"model": "llama3.2:latest"}]),
            "show_model": AsyncMock(
                return_value={
                    "capabilities": ["completion", "tools"],
                    "family": "llama",
                }
            ),
        },
    )()

    r = _client(ollama_manager).get("/v1/models/llama3.2:latest")

    assert r.status_code == 200
    body = r.json()
    assert body["capabilities"] == ["completion", "tools"]
    assert body["details"]["family"] == "llama"
    assert body["status"] == "ready"


def test_get_model_defaults_capabilities_to_empty_list_when_absent():
    ollama_manager = type(
        "M",
        (),
        {
            "list_models": AsyncMock(return_value=[{"model": "llama3.2:latest"}]),
            "show_model": AsyncMock(return_value={"family": "llama"}),
        },
    )()

    r = _client(ollama_manager).get("/v1/models/llama3.2:latest")

    assert r.json()["capabilities"] == []


# --- delete_model (DELETE /v1/models/{model_id}) -----------------------------


def test_delete_model_unknown_is_404():
    ollama_manager = type(
        "M",
        (),
        {
            "list_models": AsyncMock(return_value=[]),
            "delete_model": AsyncMock(
                side_effect=AssertionError("must not delete an unknown model")
            ),
        },
    )()

    r = _client(ollama_manager, as_admin=True).delete("/v1/models/no-such-model")

    assert r.status_code == 404


def test_delete_model_success():
    ollama_manager = type(
        "M",
        (),
        {
            "list_models": AsyncMock(return_value=[{"model": "llama3.2:latest"}]),
            "delete_model": AsyncMock(return_value={"status": "success"}),
        },
    )()

    r = _client(ollama_manager, as_admin=True).delete("/v1/models/llama3.2:latest")

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "deleted"
    assert body["model"] == "llama3.2:latest"


def test_delete_model_requires_admin():
    ollama_manager = type("M", (), {"list_models": AsyncMock(return_value=[])})()

    r = _client(ollama_manager, as_admin=False).delete("/v1/models/llama3.2:latest")

    assert r.status_code in (401, 403)


# --- #895: model_id tag normalization -----------------------------------------
# Ollama canonicalizes an untagged pull ("all-minilm") to "all-minilm:latest" in
# its own store; get/delete/test/register's existing-check all used to compare
# the caller's raw model_id against the list with exact string equality, so a
# model pulled without an explicit tag became unreachable by the name it was
# pulled with.


def test_get_model_resolves_a_bare_name_to_its_tagged_entry():
    ollama_manager = type(
        "M",
        (),
        {
            "list_models": AsyncMock(return_value=[{"model": "all-minilm:latest"}]),
            "show_model": AsyncMock(return_value={"family": "minilm"}),
        },
    )()

    r = _client(ollama_manager).get("/v1/models/all-minilm")

    assert r.status_code == 200
    assert r.json()["details"]["family"] == "minilm"


def test_delete_model_resolves_a_bare_name_to_its_tagged_entry():
    ollama_manager = type(
        "M",
        (),
        {
            "list_models": AsyncMock(return_value=[{"model": "all-minilm:latest"}]),
            "delete_model": AsyncMock(return_value={"status": "success"}),
        },
    )()

    r = _client(ollama_manager, as_admin=True).delete("/v1/models/all-minilm")

    assert r.status_code == 200


def test_test_model_resolves_a_bare_name_to_its_tagged_entry():
    ollama_manager = type(
        "M",
        (),
        {
            "list_models": AsyncMock(return_value=[{"model": "all-minilm:latest"}]),
            "test_model": AsyncMock(
                return_value={
                    "model": "all-minilm",
                    "response": "ok",
                    "status": "success",
                }
            ),
        },
    )()

    r = _client(ollama_manager).post(
        "/v1/models/all-minilm/test", json={"prompt": "hi"}
    )

    assert r.status_code == 200


def test_register_model_bare_name_already_exists_is_200_not_re_pulled():
    ollama_manager = type(
        "M",
        (),
        {
            "list_models": AsyncMock(return_value=[{"model": "all-minilm:latest"}]),
            "pull_model": AsyncMock(
                side_effect=AssertionError("must not re-pull an already-existing model")
            ),
        },
    )()

    r = _client(ollama_manager, as_admin=True).post(
        "/v1/models", json={"model_id": "all-minilm"}
    )

    assert r.status_code == 200
    assert r.json()["status"] == "already_exists"


def test_get_model_does_not_mangle_an_already_tagged_id():
    """A model_id that already carries a tag must never get ":latest" appended
    on top of it -- "foo:v2" must match only "foo:v2", not be turned into
    "foo:v2:latest" and fail to match anything."""
    ollama_manager = type(
        "M",
        (),
        {
            "list_models": AsyncMock(return_value=[{"model": "foo:v2"}]),
            "show_model": AsyncMock(return_value={}),
        },
    )()

    r = _client(ollama_manager).get("/v1/models/foo:v2")

    assert r.status_code == 200


def test_get_model_a_bare_name_does_not_match_a_differently_tagged_entry():
    """Normalizing must not become overly permissive -- a bare "foo" lookup
    should resolve to "foo:latest" specifically, not match an unrelated
    "foo:v2" entry that happens to share the same base name."""
    ollama_manager = type(
        "M",
        (),
        {"list_models": AsyncMock(return_value=[{"model": "foo:v2"}])},
    )()

    r = _client(ollama_manager).get("/v1/models/foo")

    assert r.status_code == 404


# --- test_model success path (POST /v1/models/{model_id}/test) --------------


def test_test_model_success_returns_result_verbatim():
    ollama_manager = type(
        "M",
        (),
        {
            "list_models": AsyncMock(return_value=[{"model": "llama3.2:latest"}]),
            "test_model": AsyncMock(
                return_value={
                    "model": "llama3.2:latest",
                    "prompt": "hi",
                    "response": "hello!",
                    "status": "success",
                }
            ),
        },
    )()

    r = _client(ollama_manager).post(
        "/v1/models/llama3.2:latest/test", json={"prompt": "hi"}
    )

    assert r.status_code == 200
    assert r.json()["response"] == "hello!"


def test_test_model_requires_auth():
    # #746: test_model used to have no auth dependency at all -- an
    # unauthenticated caller must now be rejected before ever reaching ollama.
    ollama_manager = type(
        "M",
        (),
        {
            "list_models": AsyncMock(
                side_effect=AssertionError("must not reach ollama when unauthenticated")
            ),
            "test_model": AsyncMock(
                side_effect=AssertionError("must not reach ollama when unauthenticated")
            ),
        },
    )()

    r = _client(ollama_manager, authenticated=False).post(
        "/v1/models/llama3.2:latest/test", json={"prompt": "hi"}
    )

    assert r.status_code == 401


def test_test_model_is_rate_limited_per_user():
    # #746: no more than 5 test-generations per user per minute. The 6th call
    # in the same window must 429 without ever reaching ollama.
    ollama_manager = type(
        "M",
        (),
        {
            "list_models": AsyncMock(return_value=[{"model": "llama3.2:latest"}]),
            "test_model": AsyncMock(
                return_value={
                    "model": "llama3.2:latest",
                    "prompt": "hi",
                    "response": "hello!",
                    "status": "success",
                }
            ),
        },
    )()
    client = _client(ollama_manager)

    for _ in range(5):
        r = client.post("/v1/models/llama3.2:latest/test", json={"prompt": "hi"})
        assert r.status_code == 200

    r = client.post("/v1/models/llama3.2:latest/test", json={"prompt": "hi"})
    assert r.status_code == 429


# --- Unimplemented stubs (501) ------------------------------------------------


def test_set_model_constraints_is_501():
    ollama_manager = type("M", (), {})()
    r = _client(ollama_manager).post(
        "/v1/models/llama3.2:latest/constraints",
        json={
            "rate_limit": 10,
            "cost_limit": 1.0,
            "allowed_users": ["alice"],
            "content_filtering": True,
            "max_tokens": 100,
        },
    )
    assert r.status_code == 501


def test_get_model_metrics_is_501():
    ollama_manager = type("M", (), {})()
    r = _client(ollama_manager).get("/v1/models/llama3.2:latest/metrics")
    assert r.status_code == 501


def test_fine_tune_model_is_501():
    ollama_manager = type("M", (), {})()
    r = _client(ollama_manager, as_admin=True).post(
        "/v1/models/fine-tune",
        json={"base_model": "llama3.2:latest"},
    )
    assert r.status_code == 501


# ── register_model / get_model / delete_model / test_model's own generic ─────
# -exception branches -- only list_models' had a test above; each of these
# four routes has the identical try/except HTTPException-reraise/generic
# -Exception->backend_http_error pattern, and none of the others had ever
# hit it.


def test_register_model_generic_failure_returns_500_without_leaking():
    ollama_manager = type(
        "M",
        (),
        {"list_models": AsyncMock(side_effect=KeyError("some_internal_field"))},
    )()

    r = _client(ollama_manager, as_admin=True).post(
        "/v1/models", json={"model_id": "llama3.2:latest"}
    )

    assert r.status_code == 500
    assert "some_internal_field" not in r.text


def test_get_model_generic_failure_returns_500_without_leaking():
    ollama_manager = type(
        "M",
        (),
        {"list_models": AsyncMock(side_effect=KeyError("some_internal_field"))},
    )()

    r = _client(ollama_manager).get("/v1/models/llama3.2:latest")

    assert r.status_code == 500
    assert "some_internal_field" not in r.text


def test_delete_model_generic_failure_returns_500_without_leaking():
    ollama_manager = type(
        "M",
        (),
        {"list_models": AsyncMock(side_effect=KeyError("some_internal_field"))},
    )()

    r = _client(ollama_manager, as_admin=True).delete("/v1/models/llama3.2:latest")

    assert r.status_code == 500
    assert "some_internal_field" not in r.text


def test_test_model_generic_failure_returns_500_without_leaking():
    ollama_manager = type(
        "M",
        (),
        {"list_models": AsyncMock(side_effect=KeyError("some_internal_field"))},
    )()

    r = _client(ollama_manager).post(
        "/v1/models/llama3.2:latest/test", json={"prompt": "hi"}
    )

    assert r.status_code == 500
    assert "some_internal_field" not in r.text


# ── list_models / register_model: HTTPException reraised unchanged, not ─────
# remapped by the generic-Exception handler (HTTPException IS an Exception,
# so without the `except HTTPException: raise` guard it would fall through
# and get masked into a different status).


def test_list_models_reraises_an_httpexception_unchanged():
    ollama_manager = type(
        "M",
        (),
        {
            "list_models": AsyncMock(
                side_effect=HTTPException(status_code=418, detail="teapot")
            )
        },
    )()

    r = _client(ollama_manager).get("/v1/models")

    assert r.status_code == 418
    assert r.json()["detail"] == "teapot"


def test_register_model_reraises_an_httpexception_unchanged():
    ollama_manager = type(
        "M",
        (),
        {
            "list_models": AsyncMock(
                side_effect=HTTPException(status_code=418, detail="teapot")
            )
        },
    )()

    r = _client(ollama_manager, as_admin=True).post(
        "/v1/models", json={"model_id": "llama3.2:latest"}
    )

    assert r.status_code == 418
    assert r.json()["detail"] == "teapot"
