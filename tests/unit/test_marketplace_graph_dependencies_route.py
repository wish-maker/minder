"""Unit tests for marketplace's routes/graph_dependencies.py -- 0% coverage per
`coverage run` despite the underlying Neo4jClient methods (add_dependency,
get_dependency_chain, find_conflicting_plugins, recommend_plugins) already
being tested. This locks down the route layer itself: auth gating
(get_current_user_or_service for the internal-sync-friendly write, plain
get_current_user for recommendations), response shaping, and the
success/False/ValueError/generic-exception -> status-code mapping.

marketplace is a hyphenated service dir sharing top-level module names
(core/config/models/routes) with every other service in this shared pytest
process -- loaded via the same fresh-import-with-eviction precedent as
test_internal_write_endpoints_require_auth.py.
"""

import importlib
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared.auth.jwt_middleware import get_current_user, get_current_user_or_service

_SERVICES = Path(__file__).resolve().parents[2] / "src" / "services"


def _fresh_import():
    sys.path.insert(0, str(_SERVICES / "marketplace"))
    for stale in list(sys.modules):
        if stale.split(".")[0] in ("core", "config", "models", "routes"):
            del sys.modules[stale]
    return importlib.import_module("routes.graph_dependencies")


@pytest.fixture
def gd():
    return _fresh_import()


class _FakeNeo4j:
    def __init__(
        self,
        dependencies=None,
        conflicts=None,
        recommendations=None,
        add_result=True,
        raises=None,
    ):
        self._dependencies = dependencies or []
        self._conflicts = conflicts or []
        self._recommendations = recommendations or []
        self._add_result = add_result
        self._raises = raises

    async def get_dependency_chain(self, plugin_id):
        if self._raises:
            raise self._raises
        return self._dependencies

    async def add_dependency(self, plugin_id, depends_on, dep_type, **kwargs):
        if self._raises:
            raise self._raises
        return self._add_result

    async def find_conflicting_plugins(self, plugin_id):
        if self._raises:
            raise self._raises
        return self._conflicts

    async def recommend_plugins(self, installed_plugins, limit):
        if self._raises:
            raise self._raises
        return self._recommendations


def _client(gd, neo4j, *, as_user=True, as_service=False):
    app = FastAPI()
    app.include_router(gd.router)
    app.dependency_overrides[gd.get_neo4j_client] = lambda: neo4j
    if as_user:
        app.dependency_overrides[get_current_user] = lambda: {
            "sub": "u1",
            "username": "u1",
        }
    if as_user or as_service:
        app.dependency_overrides[get_current_user_or_service] = lambda: {
            "sub": "u1",
            "username": "u1",
        }
    return TestClient(app, raise_server_exceptions=False)


# --- GET /v1/graph/dependencies/{plugin_id} ---------------------------------


def test_get_dependencies_returns_chain_and_count(gd):
    client = _client(gd, _FakeNeo4j(dependencies=[{"plugin_id": "b", "depth": 1}]))
    r = client.get("/v1/graph/dependencies/a")
    assert r.status_code == 200
    body = r.json()
    assert body["plugin_id"] == "a"
    assert body["total_count"] == 1
    assert body["dependencies"] == [{"plugin_id": "b", "depth": 1}]


def test_get_dependencies_generic_error_is_500(gd):
    client = _client(gd, _FakeNeo4j(raises=RuntimeError("boom")))
    r = client.get("/v1/graph/dependencies/a")
    assert r.status_code == 500


def test_get_dependencies_connectivity_error_is_503(gd):
    client = _client(gd, _FakeNeo4j(raises=ConnectionError("db down")))
    r = client.get("/v1/graph/dependencies/a")
    assert r.status_code == 503


# --- POST /v1/graph/dependencies --------------------------------------------


def test_add_dependency_requires_auth(gd):
    client = _client(gd, _FakeNeo4j(), as_user=False, as_service=False)
    r = client.post(
        "/v1/graph/dependencies", params={"plugin_id": "a", "depends_on": "b"}
    )
    assert r.status_code == 401


def test_add_dependency_succeeds(gd):
    client = _client(gd, _FakeNeo4j(add_result=True))
    r = client.post(
        "/v1/graph/dependencies", params={"plugin_id": "a", "depends_on": "b"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body == {
        "status": "success",
        "plugin_id": "a",
        "depends_on": "b",
        "type": "requires",
    }


def test_add_dependency_false_result_is_400(gd):
    client = _client(gd, _FakeNeo4j(add_result=False))
    r = client.post(
        "/v1/graph/dependencies", params={"plugin_id": "a", "depends_on": "b"}
    )
    assert r.status_code == 400


def test_add_dependency_value_error_is_400(gd):
    client = _client(gd, _FakeNeo4j(raises=ValueError("cannot depend on itself")))
    r = client.post(
        "/v1/graph/dependencies", params={"plugin_id": "a", "depends_on": "a"}
    )
    assert r.status_code == 400
    assert "cannot depend on itself" in r.json()["detail"]


def test_add_dependency_generic_error_is_500(gd):
    client = _client(gd, _FakeNeo4j(raises=RuntimeError("boom")))
    r = client.post(
        "/v1/graph/dependencies", params={"plugin_id": "a", "depends_on": "b"}
    )
    assert r.status_code == 500


def test_add_dependency_rejects_an_invalid_dependency_type(gd):
    client = _client(gd, _FakeNeo4j())
    r = client.post(
        "/v1/graph/dependencies",
        params={"plugin_id": "a", "depends_on": "b", "dependency_type": "not-a-type"},
    )
    assert r.status_code == 422


# --- GET /v1/graph/conflicts/{plugin_id} ------------------------------------


def test_get_conflicts_returns_list_and_count(gd):
    client = _client(gd, _FakeNeo4j(conflicts=[{"plugin_id": "c"}]))
    r = client.get("/v1/graph/conflicts/a")
    assert r.status_code == 200
    body = r.json()
    assert body["conflict_count"] == 1
    assert body["conflicts"] == [{"plugin_id": "c"}]


def test_get_conflicts_generic_error_is_500(gd):
    client = _client(gd, _FakeNeo4j(raises=RuntimeError("boom")))
    r = client.get("/v1/graph/conflicts/a")
    assert r.status_code == 500


# --- POST /v1/graph/recommendations -----------------------------------------


def test_recommendations_requires_auth(gd):
    client = _client(gd, _FakeNeo4j(), as_user=False)
    r = client.post("/v1/graph/recommendations", json=["a", "b"])
    assert r.status_code == 401


def test_recommendations_returns_list_and_count(gd):
    client = _client(gd, _FakeNeo4j(recommendations=[{"plugin_id": "x", "score": 0.9}]))
    r = client.post("/v1/graph/recommendations", json=["a", "b"])
    assert r.status_code == 200
    body = r.json()
    assert body["installed_plugins"] == ["a", "b"]
    assert body["count"] == 1
    assert body["recommendations"] == [{"plugin_id": "x", "score": 0.9}]


def test_recommendations_generic_error_is_500(gd):
    client = _client(gd, _FakeNeo4j(raises=RuntimeError("boom")))
    r = client.post("/v1/graph/recommendations", json=["a"])
    assert r.status_code == 500
