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
        request_cls = importlib.import_module("models.schemas").KnowledgeGraphRequest
        return module, request_cls
    finally:
        sys.path[:] = saved_path
        for name in _COLLISION_PRONE_NAMES:
            for key in list(sys.modules):
                if key == name or key.startswith(name + "."):
                    sys.modules.pop(key, None)
        sys.modules.update(saved_modules)


_api, KnowledgeGraphRequest = _isolated_import("routes.api")
construct_knowledge_graph_handler = _api.construct_knowledge_graph_handler


class _FakeExtractor:
    def __init__(self, entities, relationships):
        self._entities = entities
        self._relationships = relationships

    def extract_entities(self, text, extract_relationships):
        return {"entities": self._entities, "relationships": self._relationships}


class _FakeConstructor:
    """entity_ids/linked_count/relationship_count are pre-scripted -- this
    stands in for create_document_node/create_entity_nodes/
    create_relationship_nodes/link_document_to_entities."""

    def __init__(self, entity_ids, relationship_count=0, linked_count=None, stats=None):
        self._entity_ids = entity_ids
        self._relationship_count = relationship_count
        self._linked_count = (
            linked_count if linked_count is not None else len(entity_ids)
        )
        self.linked_with = None
        self._stats = stats

    async def create_document_node(self, **kwargs):
        return True

    async def create_entity_nodes(self, document_id, entities):
        return self._entity_ids

    async def create_relationship_nodes(self, document_id, relationships):
        return self._relationship_count

    async def link_document_to_entities(self, document_id, entity_ids):
        self.linked_with = entity_ids
        return self._linked_count

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
async def test_entity_count_reflects_created_when_some_entities_fail_to_write():
    """3 entities extracted, only 1 actually written to Neo4j (2 failed) --
    entity_count must report 1, not 3, and the response must still be a
    non-crashing success (partial writes are a real, expected Neo4j failure
    mode, not a hard error)."""
    extractor = _FakeExtractor(
        entities=[
            {"text": "Acme Corp", "label": "ORG"},
            {"text": "Jane Doe", "label": "PERSON"},
            {"text": "Springfield", "label": "GPE"},
        ],
        relationships=[],
    )
    constructor = _FakeConstructor(entity_ids=["Acme Corp"])  # only 1 of 3 survived

    result = await construct_knowledge_graph_handler(_request(), extractor, constructor)

    assert result.success is True
    assert result.entity_count == 1  # NOT 3
    # link_document_to_entities must only be asked to link the entities that
    # actually exist in Neo4j, not the full extracted list.
    assert constructor.linked_with == ["Acme Corp"]


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
