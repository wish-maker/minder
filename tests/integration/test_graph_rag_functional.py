"""
Functional tests for the Graph-RAG service (spaCy NER + Neo4j knowledge graph).

Covers the four endpoints end-to-end against the live service on :8008:
extract, construct-graph, retrieve, entity-context. The entity-context case
guards a signature-mismatch bug (handler passed `entity_text`/`include_neighbors`
to a method expecting `entity_name`/`context_window`) fixed on 2026-07-10.

Skips automatically if the service is unreachable, so it never hangs.
"""

import os

import httpx
import pytest

GRAPH_RAG = os.environ.get("MINDER_GRAPH_RAG_URL", "http://localhost:8008")
TIMEOUT = 60.0

SAMPLE = (
    "Ada Lovelace worked with Charles Babbage on the Analytical Engine in London. "
    "She is regarded as the first computer programmer."
)


def _up() -> bool:
    try:
        return httpx.get(f"{GRAPH_RAG}/health", timeout=3.0).status_code == 200
    except Exception:
        return False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _up(), reason="graph-rag not reachable on localhost:8008"),
]


def test_extract_finds_entities():
    r = httpx.post(f"{GRAPH_RAG}/extract", json={"text": SAMPLE}, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    entities = r.json()["entities"]
    labels = {e["text"] for e in entities}
    assert "Ada Lovelace" in labels
    assert any(e["label"] == "PERSON" for e in entities)


def test_construct_graph_writes_nodes():
    r = httpx.post(
        f"{GRAPH_RAG}/construct-graph",
        json={"document_id": "test-graph-rag-func", "text": SAMPLE, "title": "t"},
        timeout=TIMEOUT,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["entity_count"] > 0


def test_retrieve_returns_related_entities():
    # Ensure the graph is populated first.
    httpx.post(
        f"{GRAPH_RAG}/construct-graph",
        json={"document_id": "test-graph-rag-func", "text": SAMPLE, "title": "t"},
        timeout=TIMEOUT,
    )
    r = httpx.post(
        f"{GRAPH_RAG}/retrieve",
        json={"query": "Who worked on the Analytical Engine?", "limit": 5},
        timeout=TIMEOUT,
    )
    assert r.status_code == 200, r.text
    assert r.json()["success"] is True


def test_entity_context_regression():
    """Regression: /entity-context used to 500 on a kwarg mismatch."""
    httpx.post(
        f"{GRAPH_RAG}/construct-graph",
        json={"document_id": "test-graph-rag-func", "text": SAMPLE, "title": "t"},
        timeout=TIMEOUT,
    )
    r = httpx.post(
        f"{GRAPH_RAG}/entity-context",
        json={"entity_text": "Ada Lovelace", "include_neighbors": True, "context_window": 3},
        timeout=TIMEOUT,
    )
    assert r.status_code == 200, r.text
    assert r.json()["success"] is True
