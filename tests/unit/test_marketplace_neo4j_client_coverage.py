"""Unit tests filling neo4j_client.py's remaining coverage gaps (60%).

test_marketplace_neo4j_dependency_types.py already locks in add_dependency's
relationship-type mapping, self-loop/cycle rejection, and the reader queries'
DEPENDS_ON usage. This adds everything else: _parse_neo4j_auth's two branches,
Neo4jClient.__init__'s settings-fallback branches + close(), create_plugin_node
(found + not-found), add_dependency's invalid-dependency_type ValueError,
find_conflicting_plugins, recommend_plugins, and get_neo4j_client's singleton
(create-once, reuse, and no-NEO4J_AUTH fallback).

Same isolated-import + fake-session pattern as the sibling suite.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

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
    def __init__(self, single_value=None, data_value=None):
        self._single_value = single_value
        self._data_value = data_value if data_value is not None else []

    async def single(self):
        return self._single_value

    async def data(self):
        return self._data_value


class _FakeSession:
    def __init__(self, capture=None, result=None):
        self._capture = capture if capture is not None else {}
        self._result = result if result is not None else _FakeResult()

    async def run(self, query, **kwargs):
        self._capture["query"] = query
        self._capture["kwargs"] = kwargs
        return self._result

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


# --- _parse_neo4j_auth -----------------------------------------------------------


def test_parse_neo4j_auth_splits_user_and_password():
    user, password = neo4j_client_mod._parse_neo4j_auth("admin/hunter2")
    assert (user, password) == ("admin", "hunter2")


def test_parse_neo4j_auth_splits_only_on_first_slash():
    user, password = neo4j_client_mod._parse_neo4j_auth("admin/hunter2/extra")
    assert (user, password) == ("admin", "hunter2/extra")


def test_parse_neo4j_auth_falls_back_to_neo4j_user_when_no_slash():
    user, password = neo4j_client_mod._parse_neo4j_auth("just-a-password")
    assert (user, password) == ("neo4j", "just-a-password")


# --- Neo4jClient.__init__ ---------------------------------------------------------


def test_init_uses_explicit_password_over_settings(monkeypatch):
    monkeypatch.setattr(
        neo4j_client_mod.settings, "NEO4J_AUTH", "neo4j/from-settings", raising=False
    )
    client = neo4j_client_mod.Neo4jClient(password="explicit-pass")
    assert client.driver is not None  # constructed without raising


def test_init_falls_back_to_settings_neo4j_auth_when_no_password(monkeypatch):
    monkeypatch.setattr(
        neo4j_client_mod.settings, "NEO4J_AUTH", "admin/from-settings", raising=False
    )
    captured = {}
    real_driver_factory = neo4j_client_mod.AsyncGraphDatabase.driver

    def capturing_driver(uri, auth):
        captured["auth"] = auth
        return real_driver_factory(uri, auth=auth)

    monkeypatch.setattr(neo4j_client_mod.AsyncGraphDatabase, "driver", capturing_driver)

    neo4j_client_mod.Neo4jClient(password="")

    assert captured["auth"] == ("admin", "from-settings")


def test_init_falls_back_to_default_password_when_no_settings_attr(monkeypatch):
    monkeypatch.delattr(neo4j_client_mod.settings, "NEO4J_AUTH", raising=False)
    captured = {}
    real_driver_factory = neo4j_client_mod.AsyncGraphDatabase.driver

    def capturing_driver(uri, auth):
        captured["auth"] = auth
        return real_driver_factory(uri, auth=auth)

    monkeypatch.setattr(neo4j_client_mod.AsyncGraphDatabase, "driver", capturing_driver)

    neo4j_client_mod.Neo4jClient(password="")

    assert captured["auth"] == ("neo4j", "secure_password_change_me")


@pytest.mark.asyncio
async def test_close_closes_the_underlying_driver():
    client = neo4j_client_mod.Neo4jClient(password="test")
    client.driver.close = AsyncMock()

    await client.close()

    client.driver.close.assert_awaited_once()


# --- create_plugin_node -----------------------------------------------------------


@pytest.mark.asyncio
async def test_create_plugin_node_returns_the_plugin_id_when_merged():
    client = neo4j_client_mod.Neo4jClient(password="test")
    capture = {}
    session = _FakeSession(
        capture, result=_FakeResult(single_value={"plugin_id": "weather"})
    )
    client.driver.session = MagicMock(return_value=session)

    result = await client.create_plugin_node({"id": "weather", "name": "Weather"})

    assert result == "weather"
    assert "MERGE (p:Plugin" in capture["query"]
    assert capture["kwargs"]["id"] == "weather"


@pytest.mark.asyncio
async def test_create_plugin_node_returns_none_when_no_record():
    client = neo4j_client_mod.Neo4jClient(password="test")
    session = _FakeSession(result=_FakeResult(single_value=None))
    client.driver.session = MagicMock(return_value=session)

    result = await client.create_plugin_node({"id": "weather"})

    assert result is None


# --- add_dependency: invalid dependency_type --------------------------------------


@pytest.mark.asyncio
async def test_add_dependency_rejects_unknown_dependency_type():
    client = neo4j_client_mod.Neo4jClient(password="test")
    ran = {"n": 0}

    class _CountingSession(_FakeSession):
        async def run(self, query, **kwargs):
            ran["n"] += 1
            return await super().run(query, **kwargs)

    client.driver.session = MagicMock(return_value=_CountingSession())

    with pytest.raises(ValueError, match="Invalid dependency_type"):
        await client.add_dependency("plugin-a", "plugin-b", "bogus_type")
    assert ran["n"] == 0  # rejected before touching the DB


# --- get_dependent_plugins (#748) -------------------------------------------------


@pytest.mark.asyncio
async def test_get_dependent_plugins_queries_the_reverse_depends_on_direction():
    client = neo4j_client_mod.Neo4jClient(password="test")
    capture = {}
    expected = [{"plugin_id": "network", "name": "Network", "type": "requires"}]
    session = _FakeSession(capture, result=_FakeResult(data_value=expected))
    client.driver.session = MagicMock(return_value=session)

    result = await client.get_dependent_plugins("telegraf")

    assert result == expected
    assert "(other:Plugin)-[r:DEPENDS_ON]->(p:Plugin" in capture["query"]
    assert capture["kwargs"] == {"plugin_id": "telegraf"}


# --- find_conflicting_plugins ------------------------------------------------------


@pytest.mark.asyncio
async def test_find_conflicting_plugins_queries_conflicts_with_and_returns_data():
    client = neo4j_client_mod.Neo4jClient(password="test")
    capture = {}
    expected = [{"plugin_id": "b", "name": "Beta", "reason": "port clash"}]
    session = _FakeSession(capture, result=_FakeResult(data_value=expected))
    client.driver.session = MagicMock(return_value=session)

    result = await client.find_conflicting_plugins("plugin-a")

    assert result == expected
    assert "[r:CONFLICTS_WITH]" in capture["query"]
    assert capture["kwargs"] == {"plugin_id": "plugin-a"}


# --- recommend_plugins ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_recommend_plugins_passes_installed_ids_and_limit():
    client = neo4j_client_mod.Neo4jClient(password="test")
    capture = {}
    expected = [{"plugin_id": "c", "name": "Gamma", "score": 3}]
    session = _FakeSession(capture, result=_FakeResult(data_value=expected))
    client.driver.session = MagicMock(return_value=session)

    result = await client.recommend_plugins(["a", "b"], limit=7)

    assert result == expected
    assert "[:DEPENDS_ON|RECOMMENDS]" in capture["query"]
    assert capture["kwargs"] == {"installed_ids": ["a", "b"], "limit": 7}


@pytest.mark.asyncio
async def test_recommend_plugins_defaults_limit_to_five():
    client = neo4j_client_mod.Neo4jClient(password="test")
    capture = {}
    client.driver.session = MagicMock(return_value=_FakeSession(capture))

    await client.recommend_plugins(["a"])

    assert capture["kwargs"]["limit"] == 5


# --- get_neo4j_client singleton -----------------------------------------------------


@pytest.mark.asyncio
async def test_get_neo4j_client_creates_and_reuses_the_singleton(monkeypatch):
    (mod,) = _isolated_import("core.neo4j_client")
    monkeypatch.setattr(mod, "_neo4j_client", None)
    monkeypatch.setattr(mod.settings, "NEO4J_URI", "bolt://custom:7687", raising=False)
    monkeypatch.setattr(mod.settings, "NEO4J_AUTH", "admin/pw123", raising=False)

    first = await mod.get_neo4j_client()
    second = await mod.get_neo4j_client()

    assert first is second  # singleton reused, not recreated


@pytest.mark.asyncio
async def test_get_neo4j_client_falls_back_when_no_neo4j_auth(monkeypatch):
    (mod,) = _isolated_import("core.neo4j_client")
    monkeypatch.setattr(mod, "_neo4j_client", None)
    monkeypatch.delattr(mod.settings, "NEO4J_AUTH", raising=False)

    client = await mod.get_neo4j_client()

    assert isinstance(client, mod.Neo4jClient)
