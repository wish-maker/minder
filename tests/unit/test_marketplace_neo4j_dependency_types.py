"""Unit test for a relationship-type mismatch between Neo4jClient.add_dependency
(the only writer of plugin-dependency edges) and every reader
(get_plugin_dependencies, get_dependency_chain, recommend_plugins) (#37).

Found live: add_dependency mapped "requires"/"suggests" to their own literal
relationship names (REQUIRES/SUGGESTS), but every reader queries
:DEPENDS_ON / :RECOMMENDS specifically. A real dependency (e.g. "network
requires telegraf") could be written via POST /v1/graph/dependencies and
would never show up anywhere -- the "Dependencies & conflicts" panel already
shipped on Available Plugins cards had been silently non-functional since
it was built, independent of whether anything ever populated it.

Isolated-import pattern matches test_marketplace_install_plugin.py.
Neo4jClient.__init__ constructs a real `neo4j.AsyncGraphDatabase.driver(...)`,
which is lazy (no network I/O until a session actually runs a query) -- safe
to instantiate directly, then swap `.session` for a fake that captures the
query string instead of hitting a real database.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_SERVICE_DIR = Path(__file__).resolve().parents[2] / "src" / "services" / "marketplace"
_COLLISION_PRONE_NAMES = ("core", "routes", "models", "config")


def _isolated_import(*module_paths: str):
    saved_path = list(sys.path)
    saved_modules = {}
    for name in _COLLISION_PRONE_NAMES:
        for key in list(sys.modules):
            if key == name or key.startswith(name + "."):
                saved_modules[key] = sys.modules.pop(key)
    sys.path.insert(0, str(_SERVICE_DIR))
    import os

    os.environ.setdefault("DB_PASSWORD", "test")
    os.environ.setdefault("REDIS_PASSWORD", "test")
    os.environ.setdefault("JWT_SECRET", "test")
    os.environ.setdefault("NEO4J_AUTH", "neo4j/test")

    import importlib

    try:
        return [importlib.import_module(p) for p in module_paths]
    finally:
        sys.path[:] = saved_path
        for name in _COLLISION_PRONE_NAMES:
            for key in list(sys.modules):
                if key == name or key.startswith(name + "."):
                    sys.modules.pop(key, None)
        sys.modules.update(saved_modules)


(neo4j_client_mod,) = _isolated_import("core.neo4j_client")


class _FakeResult:
    async def single(self):
        return {"true": True}


class _FakeSession:
    def __init__(self, capture):
        self._capture = capture

    async def run(self, query, **kwargs):
        self._capture["query"] = query
        self._capture["kwargs"] = kwargs
        return _FakeResult()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "dependency_type,expected_rel_type",
    [
        ("requires", "DEPENDS_ON"),
        ("suggests", "RECOMMENDS"),
        ("conflicts_with", "CONFLICTS_WITH"),
    ],
)
async def test_add_dependency_uses_the_relationship_type_readers_expect(
    dependency_type, expected_rel_type
):
    client = neo4j_client_mod.Neo4jClient(password="test")
    capture = {}
    client.driver.session = MagicMock(return_value=_FakeSession(capture))

    ok = await client.add_dependency(
        "plugin-a",
        "plugin-b",
        dependency_type,
        plugin_name="network",
        depends_on_name="telegraf",
    )

    assert ok is True
    assert f"[r:{expected_rel_type}]" in capture["query"]
    # MERGE, not MATCH -- found live: nothing anywhere ever calls
    # create_plugin_node, so a MATCH-only query silently returned False for
    # every real call (neither Plugin node existed yet).
    assert "MERGE (p1:Plugin" in capture["query"]
    assert "MERGE (p2:Plugin" in capture["query"]
    assert "MATCH (p1:Plugin" not in capture["query"]
    assert capture["kwargs"]["plugin_name"] == "network"
    assert capture["kwargs"]["depends_on_name"] == "telegraf"


@pytest.mark.asyncio
async def test_get_plugin_dependencies_and_get_dependency_chain_query_depends_on():
    """Locks in the reader side too -- if either ever changes independently
    of add_dependency's mapping above, this drifts back into the same silent
    mismatch."""
    client = neo4j_client_mod.Neo4jClient(password="test")
    capture = {}

    class _FakeDataResult:
        async def data(self):
            return []

    class _FakeDataSession(_FakeSession):
        async def run(self, query, **kwargs):
            capture["query"] = query
            return _FakeDataResult()

    client.driver.session = MagicMock(return_value=_FakeDataSession(capture))

    await client.get_plugin_dependencies("plugin-a")
    assert "[r:DEPENDS_ON]" in capture["query"]

    await client.get_dependency_chain("plugin-a")
    assert "[:DEPENDS_ON*]" in capture["query"]
