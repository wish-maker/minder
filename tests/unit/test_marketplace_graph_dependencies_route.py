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


# --- GET /v1/graph/health ----------------------------------------------------
#
# Previously untested (0% coverage) and previously always returned 200 even
# when Neo4j was unreachable, plus leaked the raw unbounded exception text to
# the caller (CodeQL py/stack-trace-exposure). Now goes through
# shared.health.evaluate_dependencies, matching this service's own root
# /health -- a real 503 on failure, exception text truncated to 200 chars
# with the type name prefixed, same as every sibling service.


class _FakeResult:
    def __init__(self, record):
        self._record = record

    async def single(self):
        return self._record


class _FakeSession:
    def __init__(self, record=None, raises=None):
        self._record = record
        self._raises = raises

    async def run(self, query, *args, **kwargs):
        if self._raises:
            raise self._raises
        return _FakeResult(self._record)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeDriver:
    def __init__(self, session):
        self._session = session

    def session(self):
        return self._session


class _FakeNeo4jForHealth:
    def __init__(self, driver):
        self.driver = driver


def test_graph_health_check_healthy_when_probe_returns_expected_row(gd):
    driver = _FakeDriver(_FakeSession(record={"test": 1}))
    client = _client(gd, _FakeNeo4jForHealth(driver))
    r = client.get("/v1/graph/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "healthy"
    assert body["database"] == "neo4j"
    assert body["checks"]["neo4j"] == "healthy"


def test_graph_health_check_503_when_probe_row_is_unexpected(gd):
    driver = _FakeDriver(_FakeSession(record={"test": 0}))
    client = _client(gd, _FakeNeo4jForHealth(driver))
    r = client.get("/v1/graph/health")
    assert r.status_code == 503
    assert r.json()["status"] == "unhealthy"


def test_graph_health_check_503_when_probe_returns_no_record(gd):
    driver = _FakeDriver(_FakeSession(record=None))
    client = _client(gd, _FakeNeo4jForHealth(driver))
    r = client.get("/v1/graph/health")
    assert r.status_code == 503


def test_graph_health_check_503_and_masks_raw_exception_text(gd):
    secret_looking = "bolt://neo4j:hunter2@internal-host:7687 connection refused"
    driver = _FakeDriver(_FakeSession(raises=ConnectionError(secret_looking)))
    client = _client(gd, _FakeNeo4jForHealth(driver))
    r = client.get("/v1/graph/health")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "unhealthy"
    # Formatted as "ConnectionError: <message>" (truncated to 200 chars) by
    # shared.health.evaluate_dependencies -- not raw str(e) passthrough.
    assert body["checks"]["neo4j"].startswith("unhealthy: ConnectionError:")
    assert secret_looking in body["checks"]["neo4j"]  # present, but bounded/typed
