"""Functional tests for the Graph-RAG service (spaCy NER + Neo4j knowledge graph),
run against the real live-process harness (`live_stack`, #583 -- moved here from
tests/integration/ so these actually execute in CI against a real Neo4j instead
of always skipping for lack of a network-reachable service).

Covers the four endpoints end-to-end: extract, construct-graph, retrieve,
entity-context. The entity-context case guards a signature-mismatch bug (handler
passed `entity_text`/`include_neighbors` to a method expecting `entity_name`/
`context_window`) fixed on 2026-07-10.
"""

import os

import httpx
import pytest

SAMPLE = (
    "Ada Lovelace worked with Charles Babbage on the Analytical Engine in London. "
    "She is regarded as the first computer programmer."
)
TIMEOUT = 60.0


@pytest.fixture(scope="module")
def auth_token(live_stack):
    """A JWT for /construct-graph (the one graph-rag write endpoint here,
    Depends(get_current_user_or_service)) -- registers a throwaway user via
    the gateway once per module, same pattern as test_rag_pipeline_functional
    .py's auth_token. Used directly against graph-rag's own port: JWT
    verification is a stateless signature check against the shared
    JWT_SECRET, so a token minted via the gateway is valid at any service."""
    username = f"graphrag-{os.getpid()}"
    password = "TestPass123!"
    httpx.post(
        f"{live_stack.gateway_url}/v1/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": password,
        },
        timeout=20.0,
    )
    r = httpx.post(
        f"{live_stack.gateway_url}/v1/auth/login",
        json={"username": username, "password": password},
        timeout=20.0,
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _construct_graph(live_stack, auth_token):
    return httpx.post(
        f"{live_stack.graph_rag_url}/construct-graph",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"document_id": "test-graph-rag-func", "text": SAMPLE, "title": "t"},
        timeout=TIMEOUT,
    )


def test_extract_finds_entities(live_stack):
    r = httpx.post(
        f"{live_stack.graph_rag_url}/extract", json={"text": SAMPLE}, timeout=TIMEOUT
    )
    assert r.status_code == 200, r.text
    entities = r.json()["entities"]
    labels = {e["text"] for e in entities}
    assert "Ada Lovelace" in labels
    assert any(e["label"] == "PERSON" for e in entities)


def test_construct_graph_writes_nodes(live_stack, auth_token):
    r = _construct_graph(live_stack, auth_token)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["entity_count"] > 0


def test_retrieve_returns_related_entities(live_stack, auth_token):
    # Ensure the graph is populated first.
    setup = _construct_graph(live_stack, auth_token)
    assert setup.status_code == 200, setup.text
    r = httpx.post(
        f"{live_stack.graph_rag_url}/retrieve",
        json={"query": "Who worked on the Analytical Engine?", "limit": 5},
        timeout=TIMEOUT,
    )
    assert r.status_code == 200, r.text
    assert r.json()["success"] is True


def test_entity_context_regression(live_stack, auth_token):
    """Regression: /entity-context used to 500 on a kwarg mismatch."""
    setup = _construct_graph(live_stack, auth_token)
    assert setup.status_code == 200, setup.text
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
