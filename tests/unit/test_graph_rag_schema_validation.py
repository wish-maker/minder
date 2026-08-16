"""Unit tests for graph-rag request-schema edge validation (#538).

Constructing a knowledge graph from an empty `document_id`/`text` (or extracting
from empty text) is a meaningless no-op that used to 200 with "0 entities". These
lock the `min_length=1` guards that reject it at the edge. schemas.py imports
only stdlib + pydantic, so it loads cleanly by path (avoids the shared-conftest
`models`/`core` name collision).
"""

import importlib.util
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

_MOD_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "services"
    / "graph-rag"
    / "models"
    / "schemas.py"
)

_spec = importlib.util.spec_from_file_location(
    "_graph_rag_schemas_under_test", _MOD_PATH
)
_schemas = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _schemas
_spec.loader.exec_module(_schemas)


def test_construct_rejects_empty_document_id():
    with pytest.raises(ValidationError):
        _schemas.KnowledgeGraphRequest(document_id="", text="hello")


def test_construct_rejects_empty_text():
    with pytest.raises(ValidationError):
        _schemas.KnowledgeGraphRequest(document_id="doc-1", text="")


def test_construct_accepts_real_document():
    req = _schemas.KnowledgeGraphRequest(document_id="doc-1", text="Marie Curie")
    assert req.document_id == "doc-1"
    # #668: omitted title/source/metadata now default to None (not ""/"unknown"/{})
    # so construct_graph can COALESCE them to previously-stored values on re-POST
    # instead of blanking them.
    assert req.title is None
    assert req.source is None
    assert req.metadata is None


def test_extract_rejects_empty_text():
    with pytest.raises(ValidationError):
        _schemas.EntityExtractionRequest(text="")


def test_search_inputs_still_allow_empty():
    # empty search is a valid no-op (returns no results) — must NOT be rejected
    assert _schemas.GraphRetrievalRequest(query="").query == ""
    assert _schemas.EntityContextRequest(entity_text="").entity_text == ""
