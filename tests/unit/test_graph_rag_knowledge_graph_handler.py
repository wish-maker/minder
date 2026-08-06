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
    # routes/api.py imports EntityExtractor/GraphRetriever purely as type hints
    # (never instantiated internally) -- fake out their real modules so this
    # test doesn't need spacy/neo4j installed, matching the established
    # precedent of faking schemas.validator in the plugin-registry tests.
    fake_entity_extractor = ModuleType("core.entity_extractor")
    fake_entity_extractor.EntityExtractor = object
    fake_graph_retriever = ModuleType("core.graph_retriever")
    fake_graph_retriever.GraphRetriever = object
    sys.modules["core.entity_extractor"] = fake_entity_extractor
    sys.modules["core.graph_retriever"] = fake_graph_retriever

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

    def __init__(self, entity_ids, relationship_count=0, linked_count=None):
        self._entity_ids = entity_ids
        self._relationship_count = relationship_count
        self._linked_count = (
            linked_count if linked_count is not None else len(entity_ids)
        )
        self.linked_with = None

    async def create_document_node(self, **kwargs):
        return True

    async def create_entity_nodes(self, document_id, entities):
        return self._entity_ids

    async def create_relationship_nodes(self, document_id, relationships):
        return self._relationship_count

    async def link_document_to_entities(self, document_id, entity_ids):
        self.linked_with = entity_ids
        return self._linked_count


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
