"""Unit tests filling routes/api.py's remaining coverage gaps (76%).

test_graph_rag_knowledge_graph_handler.py already covers construct_knowledge_graph_
handler's #351 entity-count logic, the auth gate on the two mutating routes, graph
stats/documents' happy/503 paths, and retrieve_with_graph_handler/get_entity_context_
handler's dedup/neighbor-filtering logic. Left uncovered: every handler's generic-
exception->backend_http_error branch (most handlers only had their happy path or
HTTPException path tested, never a raw exception from the collaborator), the entire
delete_document_graph_handler (0% -- no test file touches it), the entire
graph_search_handler (0% -- exposed but never wired to a test), and several of
build_graph_router's own route-wrapper lines (only reachable by actually invoking
the route through a TestClient, not by calling the handler function directly).

Same _isolated_import/fake-core-submodules pattern as the sibling file (spacy/neo4j
aren't installed everywhere this test suite runs).
"""

import sys
from pathlib import Path
from types import ModuleType

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

_SERVICE_DIR = Path(__file__).resolve().parents[2] / "src" / "services" / "graph-rag"
_COLLISION_PRONE_NAMES = ("core", "routes", "models")


def _isolated_import(module_path: str):
    saved_path = list(sys.path)
    saved_modules = {}
    for name in _COLLISION_PRONE_NAMES:
        for key in list(sys.modules):
            if key == name or key.startswith(name + "."):
                saved_modules[key] = sys.modules.pop(key)

    sys.path.insert(0, str(_SERVICE_DIR))
    fake_entity_extractor = ModuleType("core.entity_extractor")
    fake_entity_extractor.EntityExtractor = object
    fake_graph_retriever = ModuleType("core.graph_retriever")
    fake_graph_retriever.GraphRetriever = object
    fake_graph_constructor = ModuleType("core.graph_constructor")
    fake_graph_constructor.KnowledgeGraphConstructor = object
    sys.modules["core.entity_extractor"] = fake_entity_extractor
    sys.modules["core.graph_retriever"] = fake_graph_retriever
    sys.modules["core.graph_constructor"] = fake_graph_constructor

    import importlib

    try:
        module = importlib.import_module(module_path)
        schemas = importlib.import_module("models.schemas")
        return module, schemas
    finally:
        sys.path[:] = saved_path
        for name in _COLLISION_PRONE_NAMES:
            for key in list(sys.modules):
                if key == name or key.startswith(name + "."):
                    sys.modules.pop(key, None)
        sys.modules.update(saved_modules)


_api, _schemas = _isolated_import("routes.api")
KnowledgeGraphRequest = _schemas.KnowledgeGraphRequest
GraphRetrievalRequest = _schemas.GraphRetrievalRequest
EntityContextRequest = _schemas.EntityContextRequest
GraphSearchRequest = _schemas.GraphSearchRequest


class _FakeExtractor:
    def __init__(self, entities=None, relationships=None, error=None):
        self._entities = entities or []
        self._relationships = relationships or []
        self._error = error

    def extract_entities(self, text, extract_relationships=True):
        if self._error:
            raise self._error
        return {
            "entities": self._entities,
            "relationships": self._relationships,
            "entity_count": len(self._entities),
            "relationship_count": len(self._relationships),
        }


class _FakeConstructor:
    def __init__(
        self,
        entity_ids=None,
        mentions_count=None,
        delete_result=None,
        delete_error=None,
    ):
        entity_ids = entity_ids or []
        self._entity_ids = entity_ids
        self._mentions_count = (
            mentions_count if mentions_count is not None else len(entity_ids)
        )
        self._delete_result = delete_result
        self._delete_error = delete_error
        self.deleted_document_id = None

    async def construct_graph(self, document_id, entities, relationships, **kwargs):
        return {
            "entity_count": len(self._entity_ids),
            "relationship_count": 0,
            "mentions_count": self._mentions_count,
        }

    async def delete_document(self, document_id, owner_id):
        if self._delete_error:
            raise self._delete_error
        self.deleted_document_id = document_id
        return self._delete_result or {
            "entities_deleted": 2,
            "relationships_deleted": 1,
        }

    async def list_documents(self, owner_id):
        return []


class _FakeRetriever:
    def __init__(self, related=None, context_result=None, error=None, entities=None):
        self._related = related or []
        self._context_result = context_result
        self._error = error
        self._entities = entities or []

    async def find_related_entities(self, entity_name, owner_id, max_depth, limit):
        if self._error:
            raise self._error
        return self._related

    async def get_entity_context(self, entity_name, owner_id, context_window):
        if self._error:
            raise self._error
        return self._context_result

    async def graph_search(self, query, owner_id, limit):
        if self._error:
            raise self._error
        return self._entities


def _kg_request():
    return KnowledgeGraphRequest(document_id="doc-1", text="Some text about Acme Corp.")


# ── extract_entities_handler: exception branch ────────────────────────────────


@pytest.mark.asyncio
async def test_extract_entities_handler_maps_extractor_error_to_backend_error():
    extractor = _FakeExtractor(error=RuntimeError("spaCy model not loaded"))

    with pytest.raises(HTTPException) as exc:
        await _api.extract_entities_handler(
            _schemas.EntityExtractionRequest(text="hi"), extractor
        )

    assert exc.value.status_code == 500


# ── construct_knowledge_graph_handler: partial-mentions warning branch ────────


@pytest.mark.asyncio
async def test_construct_handler_warns_when_not_every_entity_gets_linked(caplog):
    extractor = _FakeExtractor(entities=[{"text": "Acme Corp", "label": "ORG"}])
    constructor = _FakeConstructor(
        entity_ids=["Acme Corp", "Jane Doe"], mentions_count=1
    )

    result = await _api.construct_knowledge_graph_handler(
        _kg_request(), "owner-x", extractor, constructor
    )

    assert result.success is True
    assert any("Only linked 1/2" in r.message for r in caplog.records)


# ── delete_document_graph_handler: entirely untested before this file ─────────


@pytest.mark.asyncio
async def test_delete_document_graph_handler_503_when_constructor_missing():
    with pytest.raises(HTTPException) as exc:
        await _api.delete_document_graph_handler("doc-1", "owner-x", None)
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_delete_document_graph_handler_success():
    constructor = _FakeConstructor(
        delete_result={"entities_deleted": 3, "relationships_deleted": 2}
    )

    result = await _api.delete_document_graph_handler("doc-1", "owner-x", constructor)

    assert result == {
        "success": True,
        "document_id": "doc-1",
        "entities_deleted": 3,
        "relationships_deleted": 2,
    }
    assert constructor.deleted_document_id == "doc-1"


@pytest.mark.asyncio
async def test_delete_document_graph_handler_maps_backend_error():
    constructor = _FakeConstructor(delete_error=ConnectionRefusedError("neo4j down"))

    with pytest.raises(HTTPException) as exc:
        await _api.delete_document_graph_handler("doc-1", "owner-x", constructor)
    assert exc.value.status_code == 503


# ── list_graph_documents_handler: exception branch ────────────────────────────


@pytest.mark.asyncio
async def test_list_graph_documents_handler_maps_backend_error(monkeypatch):
    constructor = _FakeConstructor()

    async def boom(owner_id):
        raise ConnectionRefusedError("neo4j down")

    monkeypatch.setattr(constructor, "list_documents", boom)

    with pytest.raises(HTTPException) as exc:
        await _api.list_graph_documents_handler("owner-x", constructor)
    assert exc.value.status_code == 503


# ── retrieve_with_graph_handler: exception branch ─────────────────────────────


@pytest.mark.asyncio
async def test_retrieve_with_graph_handler_maps_backend_error():
    extractor = _FakeExtractor(entities=[{"text": "Acme"}])
    retriever = _FakeRetriever(error=ConnectionRefusedError("neo4j down"))

    with pytest.raises(HTTPException) as exc:
        await _api.retrieve_with_graph_handler(
            GraphRetrievalRequest(query="who is Acme?"), "owner-x", extractor, retriever
        )
    assert exc.value.status_code == 503


# ── get_entity_context_handler: generic (non-HTTPException) error branch ──────


@pytest.mark.asyncio
async def test_get_entity_context_handler_maps_generic_error_to_backend_error():
    retriever = _FakeRetriever(error=ConnectionRefusedError("neo4j down"))

    with pytest.raises(HTTPException) as exc:
        await _api.get_entity_context_handler(
            EntityContextRequest(entity_text="Acme"), "owner-x", retriever
        )
    assert exc.value.status_code == 503


# ── graph_search_handler: entirely untested before this file ──────────────────


@pytest.mark.asyncio
async def test_graph_search_handler_returns_matching_entities():
    retriever = _FakeRetriever(entities=[{"text": "Acme Corp", "label": "ORG"}])

    result = await _api.graph_search_handler(
        GraphSearchRequest(query="acme"), "owner-x", retriever
    )

    assert result.success is True
    assert result.entity_count == 1
    assert result.entities[0]["text"] == "Acme Corp"


@pytest.mark.asyncio
async def test_graph_search_handler_maps_backend_error():
    retriever = _FakeRetriever(error=ConnectionRefusedError("neo4j down"))

    with pytest.raises(HTTPException) as exc:
        await _api.graph_search_handler(
            GraphSearchRequest(query="acme"), "owner-x", retriever
        )
    assert exc.value.status_code == 503


# ── route-wrapper wiring lines (only reachable through an actual request) ─────


def _authed_client(constructor=None, retriever=None, extractor=None):
    router = _api.build_graph_router(
        entity_extractor=extractor or _FakeExtractor(),
        graph_constructor=constructor or _FakeConstructor(),
        graph_retriever=retriever or _FakeRetriever(),
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[_api.get_current_user_or_service] = lambda: {"sub": "t"}
    return TestClient(app, raise_server_exceptions=False)


def test_construct_knowledge_graph_route_invokes_handler():
    client = _authed_client(
        constructor=_FakeConstructor(entity_ids=["Acme Corp"]),
        extractor=_FakeExtractor(entities=[{"text": "Acme Corp", "label": "ORG"}]),
    )

    resp = client.post(
        "/v1/construct-graph", json={"document_id": "doc-1", "text": "Acme Corp"}
    )

    assert resp.status_code == 200
    assert resp.json()["entity_count"] == 1


def test_delete_document_graph_route_invokes_handler():
    client = _authed_client(constructor=_FakeConstructor(delete_result={}))

    resp = client.delete("/v1/graph/document/doc-1")

    assert resp.status_code == 200
    assert resp.json()["document_id"] == "doc-1"


def test_retrieve_route_invokes_handler():
    client = _authed_client()

    resp = client.post("/v1/retrieve", json={"query": "hello"})

    assert resp.status_code == 200
    assert resp.json()["entity_count"] == 0


def test_entity_context_route_invokes_handler():
    client = _authed_client(
        retriever=_FakeRetriever(
            context_result={
                "entity": {"text": "Acme", "label": "ORG"},
                "related_entities": [],
                "documents": [],
                "context_window": 3,
            }
        )
    )

    resp = client.post("/v1/entity-context", json={"entity_text": "Acme"})

    assert resp.status_code == 200


def test_graph_search_route_invokes_handler():
    client = _authed_client(
        retriever=_FakeRetriever(entities=[{"text": "Acme", "label": "ORG"}])
    )

    resp = client.post("/v1/graph/search", json={"query": "acme"})

    assert resp.status_code == 200
    assert resp.json()["entity_count"] == 1


# ── #782: the caller's identity (sub) is threaded to the graph layer as the
# owner scope on every graph-touching route, so one tenant can never read or
# mutate another's graph. These assert the route passes the AUTHENTICATED sub
# (not a client-supplied value) through as owner_id.


class _OwnerRecordingConstructor(_FakeConstructor):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.seen_owner = None

    async def construct_graph(
        self, document_id, owner_id, entities, relationships, **kw
    ):
        self.seen_owner = owner_id
        return await super().construct_graph(document_id, entities, relationships, **kw)

    async def delete_document(self, document_id, owner_id):
        self.seen_owner = owner_id
        return await super().delete_document(document_id, owner_id)

    async def list_documents(self, owner_id):
        self.seen_owner = owner_id
        return await super().list_documents(owner_id)


def _client_as(sub, constructor=None, retriever=None, extractor=None):
    router = _api.build_graph_router(
        entity_extractor=extractor or _FakeExtractor(),
        graph_constructor=constructor or _FakeConstructor(),
        graph_retriever=retriever or _FakeRetriever(),
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[_api.get_current_user_or_service] = lambda: {"sub": sub}
    return TestClient(app, raise_server_exceptions=False)


def test_construct_route_scopes_to_authenticated_owner():
    constructor = _OwnerRecordingConstructor(entity_ids=["Acme Corp"])
    client = _client_as(
        "alice",
        constructor=constructor,
        extractor=_FakeExtractor(entities=[{"text": "Acme Corp", "label": "ORG"}]),
    )
    resp = client.post(
        "/v1/construct-graph", json={"document_id": "doc-1", "text": "Acme Corp"}
    )
    assert resp.status_code == 200
    assert constructor.seen_owner == "alice"  # the JWT sub, not a body field


def test_delete_and_list_routes_scope_to_authenticated_owner():
    constructor = _OwnerRecordingConstructor(delete_result={})
    client = _client_as("bob", constructor=constructor)

    assert client.delete("/v1/graph/document/doc-1").status_code == 200
    assert constructor.seen_owner == "bob"

    assert client.get("/v1/graph/documents").status_code == 200
    assert constructor.seen_owner == "bob"


def test_graph_read_routes_require_auth():
    # #782 made the previously-open reads (stats/documents/retrieve/entity-context/
    # search) JWT-required, since per-tenant scoping needs to know the tenant.
    router = _api.build_graph_router(
        entity_extractor=_FakeExtractor(),
        graph_constructor=_FakeConstructor(),
        graph_retriever=_FakeRetriever(),
    )
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/v1/graph/stats").status_code == 401
    assert client.get("/v1/graph/documents").status_code == 401
    assert client.post("/v1/retrieve", json={"query": "x"}).status_code == 401
    assert (
        client.post("/v1/entity-context", json={"entity_text": "x"}).status_code == 401
    )
    assert client.post("/v1/graph/search", json={"query": "x"}).status_code == 401
