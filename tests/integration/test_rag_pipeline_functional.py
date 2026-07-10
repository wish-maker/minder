"""
Functional tests for the rag-pipeline service.

Exercises the standard RAG path end-to-end (knowledge base -> upload -> pipeline ->
query) and checks the `method` field added when HyDE/Self-RAG/decision-engine were
wired in (#45). The query runs a real LLM generation, so it is slow but bounded.
Skips automatically if the service is unreachable.
"""

import io
import os

import httpx
import pytest

BASE = os.environ.get("MINDER_RAG_URL", "http://localhost:8004")


def _up() -> bool:
    try:
        return httpx.get(f"{BASE}/health", timeout=3.0).status_code == 200
    except Exception:
        return False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _up(), reason="rag-pipeline not reachable on :8004"),
]


@pytest.fixture(scope="module")
def pipeline_id():
    """Create a KB, upload a small doc, and build a pipeline; return its id."""
    kb = httpx.post(
        f"{BASE}/knowledge-base",
        json={"name": f"test-func-{os.getpid()}", "description": "functional test"},
        timeout=20.0,
    )
    assert kb.status_code == 200, kb.text
    kb_id = kb.json()["id"]

    doc = io.BytesIO(
        b"The functional-test fact: the sentinel token is ZORBLAX-42. "
        b"Embeddings are stored in Qdrant and generation uses a local Llama model."
    )
    up = httpx.post(
        f"{BASE}/knowledge-base/{kb_id}/upload",
        files={"file": ("fact.txt", doc, "text/plain")},
        timeout=60.0,
    )
    assert up.status_code == 200, up.text
    assert up.json()["vectors_created"] >= 1

    pl = httpx.post(
        f"{BASE}/pipeline",
        json={"name": f"test-pl-{os.getpid()}", "knowledge_base_ids": [kb_id]},
        timeout=20.0,
    )
    assert pl.status_code == 200, pl.text
    return pl.json()["pipeline_id"]


def test_health_reports_ollama_available():
    r = httpx.get(f"{BASE}/health", timeout=8.0)
    assert r.status_code == 200
    assert r.json().get("ollama_available") is True


def test_list_knowledge_bases():
    r = httpx.get(f"{BASE}/knowledge-bases", timeout=10.0)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_standard_query_grounded(pipeline_id):
    r = httpx.post(
        f"{BASE}/pipeline/{pipeline_id}/query",
        json={"question": "What is the sentinel token?", "top_k": 3},
        timeout=180.0,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["answer"], "empty answer"
    assert body["method"] == "standard"  # method field added in #45
    assert body["sources"], "no sources returned"


def test_invalid_method_falls_back_to_standard(pipeline_id):
    r = httpx.post(
        f"{BASE}/pipeline/{pipeline_id}/query",
        json={"question": "What is the sentinel token?", "top_k": 2, "method": "bogus"},
        timeout=180.0,
    )
    assert r.status_code == 200, r.text
    assert r.json()["method"] == "standard"
