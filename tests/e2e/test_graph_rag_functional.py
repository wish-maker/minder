"""Functional tests for the Graph-RAG service (spaCy NER + Neo4j knowledge graph),
run against the real live-process harness (`live_stack`, #583 -- moved here from
tests/integration/ so these actually execute in CI against a real Neo4j instead
of always skipping for lack of a network-reachable service).

Covers the four endpoints end-to-end: extract, construct-graph, retrieve,
entity-context. The entity-context case guards a signature-mismatch bug (handler
passed `entity_text`/`include_neighbors` to a method expecting `entity_name`/
`context_window`) fixed on 2026-07-10.
"""

import httpx

SAMPLE = (
    "Ada Lovelace worked with Charles Babbage on the Analytical Engine in London. "
    "She is regarded as the first computer programmer."
)
TIMEOUT = 60.0


def test_extract_finds_entities(live_stack):
    r = httpx.post(
        f"{live_stack.graph_rag_url}/extract", json={"text": SAMPLE}, timeout=TIMEOUT
    )
    assert r.status_code == 200, r.text
    entities = r.json()["entities"]
    labels = {e["text"] for e in entities}
    assert "Ada Lovelace" in labels
    assert any(e["label"] == "PERSON" for e in entities)


def test_construct_graph_writes_nodes(live_stack):
    r = httpx.post(
        f"{live_stack.graph_rag_url}/construct-graph",
        json={"document_id": "test-graph-rag-func", "text": SAMPLE, "title": "t"},
        timeout=TIMEOUT,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["entity_count"] > 0


def test_retrieve_returns_related_entities(live_stack):
    # Ensure the graph is populated first.
    httpx.post(
        f"{live_stack.graph_rag_url}/construct-graph",
        json={"document_id": "test-graph-rag-func", "text": SAMPLE, "title": "t"},
        timeout=TIMEOUT,
    )
    r = httpx.post(
        f"{live_stack.graph_rag_url}/retrieve",
        json={"query": "Who worked on the Analytical Engine?", "limit": 5},
        timeout=TIMEOUT,
    )
    assert r.status_code == 200, r.text
    assert r.json()["success"] is True


def test_entity_context_regression(live_stack):
    """Regression: /entity-context used to 500 on a kwarg mismatch."""
    httpx.post(
        f"{live_stack.graph_rag_url}/construct-graph",
        json={"document_id": "test-graph-rag-func", "text": SAMPLE, "title": "t"},
        timeout=TIMEOUT,
    )
    r = httpx.post(
        f"{live_stack.graph_rag_url}/entity-context",
        json={
            "entity_text": "Ada Lovelace",
            "include_neighbors": True,
            "context_window": 3,
        },
        timeout=TIMEOUT,
    )
    assert r.status_code == 200, r.text
    assert r.json()["success"] is True
