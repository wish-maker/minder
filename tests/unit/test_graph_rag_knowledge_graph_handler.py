"""Unit tests for graph-rag's construct_knowledge_graph_handler (#351).

#351: entity_count used to report len(extraction_result["entities"]) -- the
*extracted* count -- even though create_entity_nodes only returns the entity
IDs actually written to Neo4j. A partial Neo4j write (some entities fail to
create) still returned success=True with an inflated entity_count.
KnowledgeGraphResponse.entity_count is documented as "Number of entities
created," not "number extracted."

construct_knowledge_graph_handler takes plain objects directly (no FastAPI
app/router needed) -- fake entity_extractor/graph_constructor stand in for
the real EntityExtractor/KnowledgeGraphConstructor.
"""

import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

_SERVICE_DIR = Path(__file__).resolve().parents[2] / "src" / "services" / "graph-rag"


_COLLISION_PRONE_NAMES = ("core", "routes", "models")


def _isolated_import(module_path: str):
    """conftest.py loads every service's main.py into ONE shared pytest
    process, so "core"/"models"/"routes" are already cached as some OTHER
    service's package by the time this file imports. Evict them, import this
    service's own module tree, grab what's needed, then RESTORE whatever was
    cached before -- a one-way clear (like the read-actions test's own
    `_fresh_import`) leaks a poisoned "models"/"core"/"routes" into every
    later-collected test file in this same pytest process (confirmed: broke
    test_marketplace_pagination.py's `from models.plugin import ...`, which
    collects after this file alphabetically)."""
    saved_path = list(sys.path)
    saved_modules = {}
    for name in _COLLISION_PRONE_NAMES:
        for key in list(sys.modules):
            if key == name or key.startswith(name + "."):
                saved_modules[key] = sys.modules.pop(key)

    sys.path.insert(0, str(_SERVICE_DIR))
    # routes/api.py imports EntityExtractor/GraphRetriever/
    # KnowledgeGraphConstructor purely as type hints (never instantiated
    # internally) -- fake out their real modules so this test doesn't need
    # spacy/neo4j installed, matching the established precedent of faking
    # schemas.validator in the plugin-registry tests. Confirmed live on the
    # Pi host: its system Python has neo4j installed but not spacy, and vice
    # versa elsewhere -- don't assume either is present.
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
construct_knowledge_graph_handler = _api.construct_knowledge_graph_handler
retrieve_with_graph_handler = _api.retrieve_with_graph_handler
get_entity_context_handler = _api.get_entity_context_handler


class _FakeExtractor:
    def __init__(self, entities, relationships):
        self._entities = entities
        self._relationships = relationships

    def extract_entities(self, text, extract_relationships):
        return {"entities": self._entities, "relationships": self._relationships}


class _FakeConstructor:
    """Stands in for the real KnowledgeGraphConstructor. `construct_graph` is now
    a single transactional call (#668); its committed counts are pre-scripted.
    `entity_ids` is the set of entities the (atomic) construct actually committed;
    `mentions_count` defaults to len(entity_ids) (each committed entity links)."""

    def __init__(
        self,
        entity_ids,
        relationship_count=0,
        mentions_count=None,
        stats=None,
        documents=None,
        construct_error=None,
    ):
        self._entity_ids = entity_ids
        self._relationship_count = relationship_count
        self._mentions_count = (
            mentions_count if mentions_count is not None else len(entity_ids)
        )
        self.constructed_with = None
        self._construct_error = construct_error
        self._stats = stats
        self._documents = documents

    async def construct_graph(
        self,
        document_id,
        entities,
        relationships,
        title=None,
        source=None,
        metadata=None,
    ):
        if self._construct_error:
            raise self._construct_error
        self.constructed_with = {
            "document_id": document_id,
            "entities": entities,
            "relationships": relationships,
            "title": title,
            "source": source,
            "metadata": metadata,
        }
        return {
            "entity_count": len(self._entity_ids),
            "relationship_count": self._relationship_count,
            "mentions_count": self._mentions_count,
        }

    async def get_graph_statistics(self):
        if isinstance(self._stats, Exception):
            raise self._stats
        return self._stats or {
            "nodes": 5,
            "relationships": 3,
            "documents": 1,
            "entities": 4,
            "entity_types": {"ORG": 2, "PERSON": 2},
        }

    async def list_documents(self):
        if isinstance(self._documents, Exception):
            raise self._documents
        return self._documents if self._documents is not None else []


def _request():
    return KnowledgeGraphRequest(document_id="doc-1", text="Some text about Acme Corp.")


@pytest.mark.asyncio
async def test_entity_count_reflects_created_not_extracted_on_full_success():
    extractor = _FakeExtractor(
        entities=[{"text": "Acme Corp", "label": "ORG"}], relationships=[]
    )
    constructor = _FakeConstructor(entity_ids=["Acme Corp"])

    result = await construct_knowledge_graph_handler(_request(), extractor, constructor)

    assert result.success is True
    assert result.entity_count == 1


@pytest.mark.asyncio
async def test_entity_count_reflects_committed_count_from_construct():
    """The reported entity_count is exactly what construct_graph committed (the
    atomic transaction's result), not the extracted count — #351's spirit, now
    trivially true because the transaction either commits everything or nothing."""
    extractor = _FakeExtractor(
        entities=[
            {"text": "Acme Corp", "label": "ORG"},
            {"text": "Jane Doe", "label": "PERSON"},
            {"text": "Springfield", "label": "GPE"},
        ],
        relationships=[],
    )
    # construct_graph committed 2 of the 3 (e.g. one deduped by #669 upstream).
    constructor = _FakeConstructor(entity_ids=["Acme Corp", "Jane Doe"])

    result = await construct_knowledge_graph_handler(_request(), extractor, constructor)

    assert result.success is True
    assert result.entity_count == 2
    # The full extraction is handed to the single transactional call.
    assert len(constructor.constructed_with["entities"]) == 3


@pytest.mark.asyncio
async def test_construct_failure_aborts_instead_of_reporting_partial_success():
    """#668: the write is now atomic — a mid-construct Neo4j failure must surface
    as an error, not a success reporting a half-built graph. backend_http_error
    maps a connectivity failure to 503."""
    from fastapi import HTTPException

    extractor = _FakeExtractor(
        entities=[{"text": "Acme Corp", "label": "ORG"}], relationships=[]
    )
    constructor = _FakeConstructor(
        entity_ids=[], construct_error=ConnectionRefusedError("neo4j down")
    )

    with pytest.raises(HTTPException) as exc:
        await construct_knowledge_graph_handler(_request(), extractor, constructor)
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_zero_entities_created_reports_zero_not_extracted_count():
    extractor = _FakeExtractor(
        entities=[{"text": "Acme Corp", "label": "ORG"}], relationships=[]
    )
    constructor = _FakeConstructor(entity_ids=[])  # every entity write failed

    result = await construct_knowledge_graph_handler(_request(), extractor, constructor)

    assert result.success is True
    assert result.entity_count == 0


# ── #405: write endpoints must require auth ──────────────────────────────────
# construct_knowledge_graph and delete_document_graph (the two mutating routes
# in build_graph_router) had NO application-level auth at all -- graph-rag is
# bound 127.0.0.1-only with no Traefik route AND isn't proxied through
# api-gateway (confirmed: zero references to "graph-rag"/"8008" anywhere in
# api-gateway), so there was no auth check anywhere in the request path.
# Reuses this file's already-faked _api import (routes.api needs a second,
# independent fresh-import site to avoid the spacy/neo4j dependency this file
# already worked around, and this session's own precedent is that duplicate
# fresh-import sites for the same service collide across test files).

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def _graph_router_client():
    router = _api.build_graph_router(
        entity_extractor=_FakeExtractor(entities=[], relationships=[]),
        graph_constructor=_FakeConstructor(entity_ids=[]),
        graph_retriever=object(),
    )
    app = FastAPI()
    app.include_router(router)
    return TestClient(app, raise_server_exceptions=False)


def test_construct_graph_requires_auth():
    client = _graph_router_client()
    resp = client.post(
        "/v1/construct-graph", json={"text": "hello", "document_id": "d1"}
    )
    assert resp.status_code == 401


def test_delete_document_graph_requires_auth():
    client = _graph_router_client()
    resp = client.delete("/v1/graph/document/d1")
    assert resp.status_code == 401


def test_extract_entities_is_unaffected():
    """Sanity check the fix is scoped to mutating endpoints -- /v1/extract is
    a read-like POST (no persistent mutation) and must stay ungated."""
    extractor = MagicMock()
    extractor.extract_entities.return_value = {
        "entities": [],
        "relationships": [],
        "entity_count": 0,
        "relationship_count": 0,
    }
    router = _api.build_graph_router(
        entity_extractor=extractor,
        graph_constructor=_FakeConstructor(entity_ids=[]),
        graph_retriever=object(),
    )
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.post("/v1/extract", json={"text": "hello"})
    assert resp.status_code == 200


# ── graph overview: GET /v1/graph/stats (a read — open, like the other GETs) ──


@pytest.mark.asyncio
async def test_graph_stats_handler_returns_overview():
    constructor = _FakeConstructor(
        entity_ids=[],
        stats={
            "nodes": 7,
            "relationships": 4,
            "documents": 2,
            "entities": 5,
            "entity_types": {"PERSON": 3, "ORG": 2},
        },
    )
    result = await _api.get_graph_stats_handler(constructor)
    assert result.success is True
    assert result.nodes == 7 and result.relationships == 4
    assert result.documents == 2 and result.entities == 5
    assert result.entity_types == {"PERSON": 3, "ORG": 2}


@pytest.mark.asyncio
async def test_graph_stats_handler_503_when_constructor_missing():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await _api.get_graph_stats_handler(None)
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_graph_stats_handler_maps_backend_error():
    from fastapi import HTTPException

    constructor = _FakeConstructor(
        entity_ids=[], stats=ConnectionRefusedError("neo4j down")
    )
    with pytest.raises(HTTPException) as exc:
        await _api.get_graph_stats_handler(constructor)
    # backend_http_error maps a connectivity failure to 503, not a raw 500.
    assert exc.value.status_code == 503


def test_graph_stats_endpoint_is_open_read():
    # A GET read is ungated (Authelia's job, #15) — unlike the mutating routes.
    client = _graph_router_client()
    resp = client.get("/v1/graph/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert (
        set(["nodes", "relationships", "documents", "entities", "entity_types"])
        <= body.keys()
    )


# ── graph documents: GET /v1/graph/documents (browse what's built) ────────────


@pytest.mark.asyncio
async def test_list_documents_handler_returns_documents_and_count():
    docs = [
        {
            "id": "d1",
            "title": "Notes",
            "source": "client",
            "created_at": "2026-08-13T00:00:00Z",
            "entity_count": 3,
        },
        {
            "id": "d2",
            "title": None,
            "source": None,
            "created_at": None,
            "entity_count": 0,
        },
    ]
    result = await _api.list_graph_documents_handler(
        _FakeConstructor(entity_ids=[], documents=docs)
    )
    assert result.success is True
    assert result.count == 2
    assert [d.id for d in result.documents] == ["d1", "d2"]
    assert result.documents[0].entity_count == 3


@pytest.mark.asyncio
async def test_list_documents_handler_empty_is_zero_count():
    result = await _api.list_graph_documents_handler(
        _FakeConstructor(entity_ids=[], documents=[])
    )
    assert result.success is True
    assert result.count == 0
    assert result.documents == []


@pytest.mark.asyncio
async def test_list_documents_handler_503_when_constructor_missing():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await _api.list_graph_documents_handler(None)
    assert exc.value.status_code == 503


def test_list_documents_endpoint_is_open_read():
    client = _graph_router_client()
    resp = client.get("/v1/graph/documents")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert "documents" in body and "count" in body


# ── retrieve_with_graph_handler / get_entity_context_handler ─────────────────
# Both had ZERO direct test coverage (confirmed via `coverage`: routes/api.py's
# lines 164-223 / 230-257 never executed by any unit test) despite being the
# actual /v1/retrieve and /v1/entity-context endpoint handlers.


class _FakeQueryExtractor:
    def __init__(self, entities):
        self._entities = entities

    def extract_entities(self, text):
        return {"entity_count": len(self._entities), "entities": self._entities}


class _FakeRetrieverForQuery:
    def __init__(self, related_by_entity=None, context_result=None):
        self._related_by_entity = related_by_entity or {}
        self._context_result = context_result
        self.find_related_calls = []

    async def find_related_entities(self, entity_name, max_depth, limit):
        self.find_related_calls.append(entity_name)
        return self._related_by_entity.get(entity_name, [])

    async def get_entity_context(self, entity_name, context_window):
        return self._context_result


@pytest.mark.asyncio
async def test_retrieve_with_graph_handler_returns_empty_when_no_entities_extracted():
    extractor = _FakeQueryExtractor(entities=[])
    retriever = _FakeRetrieverForQuery()

    result = await retrieve_with_graph_handler(
        GraphRetrievalRequest(query="nothing here"), extractor, retriever
    )

    assert result.success is True
    assert result.entity_count == 0
    assert result.related_entities == []
    assert retriever.find_related_calls == []  # never searches the graph


@pytest.mark.asyncio
async def test_retrieve_with_graph_handler_dedupes_across_search_terms():
    """Two extracted entities ("Apple", "Tesla") both relate to "Musk" --
    the same related entity must appear once in the final list, not twice."""
    extractor = _FakeQueryExtractor(entities=[{"text": "Apple"}, {"text": "Tesla"}])
    retriever = _FakeRetrieverForQuery(
        related_by_entity={
            "Apple": [{"text": "Musk", "label": "PERSON"}],
            "Tesla": [
                {"text": "Musk", "label": "PERSON"},
                {"text": "Model 3", "label": "PRODUCT"},
            ],
        }
    )

    result = await retrieve_with_graph_handler(
        GraphRetrievalRequest(query="who runs Apple and Tesla?"), extractor, retriever
    )

    assert result.entity_count == 2
    texts = [e["text"] for e in result.related_entities]
    assert texts.count("Musk") == 1
    assert "Model 3" in texts


@pytest.mark.asyncio
async def test_retrieve_with_graph_handler_limits_to_top_5_search_terms():
    entities = [{"text": f"Entity{i}"} for i in range(7)]
    extractor = _FakeQueryExtractor(entities=entities)
    retriever = _FakeRetrieverForQuery()

    await retrieve_with_graph_handler(
        GraphRetrievalRequest(query="seven things"), extractor, retriever
    )

    assert retriever.find_related_calls == [f"Entity{i}" for i in range(5)]


@pytest.mark.asyncio
async def test_get_entity_context_handler_404_when_entity_not_found():
    from fastapi import HTTPException

    retriever = _FakeRetrieverForQuery(context_result={"error": "Entity not found"})

    with pytest.raises(HTTPException) as exc:
        await get_entity_context_handler(
            EntityContextRequest(entity_text="nope"), retriever
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_entity_context_handler_drops_related_when_include_neighbors_false():
    retriever = _FakeRetrieverForQuery(
        context_result={
            "entity": {"text": "Acme", "label": "ORG"},
            "related_entities": [{"text": "Alice", "label": "PERSON"}],
            "documents": [{"doc_id": "d1", "title": "t"}],
            "context_window": 3,
        }
    )

    result = await get_entity_context_handler(
        EntityContextRequest(entity_text="Acme", include_neighbors=False), retriever
    )

    assert result.entity == {"text": "Acme", "label": "ORG"}
    assert result.related_entities == []  # dropped, not just empty by chance
    assert result.documents == [{"doc_id": "d1", "title": "t"}]


@pytest.mark.asyncio
async def test_get_entity_context_handler_includes_related_by_default():
    retriever = _FakeRetrieverForQuery(
        context_result={
            "entity": {"text": "Acme", "label": "ORG"},
            "related_entities": [{"text": "Alice", "label": "PERSON"}],
            "documents": [],
            "context_window": 3,
        }
    )

    result = await get_entity_context_handler(
        EntityContextRequest(entity_text="Acme"), retriever
    )

    assert result.related_entities == [{"text": "Alice", "label": "PERSON"}]
