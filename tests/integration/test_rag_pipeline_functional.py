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
GATEWAY = os.environ.get("MINDER_GATEWAY_URL", "http://localhost:8000")


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
    # Canonical plural collection path (#144); the singular form still works as a
    # deprecated alias.
    kb = httpx.post(
        f"{BASE}/knowledge-bases",
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
        f"{BASE}/knowledge-bases/{kb_id}/upload",
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


@pytest.fixture(scope="module")
def auth_token():
    """A JWT for calling rag-pipeline's auth-gated DELETE routes directly against
    its own port (matching how this file calls every other route, #427's
    delete_document included) -- registers a throwaway user via the gateway once
    per module, same pattern as test_auth_regression.py."""
    username = f"ragtest-{os.getpid()}"
    password = "TestPass123!"
    httpx.post(
        f"{GATEWAY}/v1/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": password,
        },
        timeout=20.0,
    )
    r = httpx.post(
        f"{GATEWAY}/v1/auth/login",
        json={"username": username, "password": password},
        timeout=20.0,
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture
def doc_kb_id():
    """A fresh, empty KB dedicated to document list/delete tests (#427) -- kept
    separate from `pipeline_id`'s KB so deleting a document here can't affect
    the other tests that query against that KB's one known document."""
    kb = httpx.post(
        f"{BASE}/knowledge-bases",
        json={"name": f"test-docs-{os.getpid()}", "description": "document tests"},
        timeout=20.0,
    )
    assert kb.status_code == 200, kb.text
    return kb.json()["id"]


def test_health_reports_ollama_available():
    r = httpx.get(f"{BASE}/health", timeout=8.0)
    assert r.status_code == 200
    assert r.json().get("ollama_available") is True


def test_list_knowledge_bases():
    r = httpx.get(f"{BASE}/knowledge-bases", timeout=10.0)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_list_pipelines_includes_created_pipeline(pipeline_id):
    # #426: before this endpoint existed, a pipeline_id only ever existed in the
    # create response -- confirm it's actually recoverable via list.
    r = httpx.get(f"{BASE}/pipeline", timeout=10.0)
    assert r.status_code == 200
    ids = [p["id"] for p in r.json()]
    assert pipeline_id in ids


def test_get_pipeline_by_id(pipeline_id):
    r = httpx.get(f"{BASE}/pipeline/{pipeline_id}", timeout=10.0)
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == pipeline_id
    assert body["knowledge_base_ids"]


def test_get_unknown_pipeline_404s():
    r = httpx.get(f"{BASE}/pipeline/does-not-exist", timeout=10.0)
    assert r.status_code == 404


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


def test_invalid_method_rejected_with_422(pipeline_id):
    # An unknown method must fail loudly rather than silently running standard, so the
    # caller learns what they actually asked for (#138). 422 lists the valid values.
    r = httpx.post(
        f"{BASE}/pipeline/{pipeline_id}/query",
        json={"question": "What is the sentinel token?", "top_k": 2, "method": "bogus"},
        timeout=180.0,
    )
    assert r.status_code == 422, r.text
    assert "valid values" in r.text.lower()


def test_retrieval_strategy_reported(pipeline_id):
    # A standard query reports the retrieval strategy it actually used (#138).
    r = httpx.post(
        f"{BASE}/pipeline/{pipeline_id}/query",
        json={"question": "What is the sentinel token?", "top_k": 2},
        timeout=180.0,
    )
    assert r.status_code == 200, r.text
    assert r.json()["method_details"]["retrieval"] == "dense"


def test_upload_response_includes_document_id(doc_kb_id):
    doc = io.BytesIO(b"Doc A content for #427 document-list tests.")
    r = httpx.post(
        f"{BASE}/knowledge-bases/{doc_kb_id}/upload",
        files={"file": ("doc-a.txt", doc, "text/plain")},
        timeout=60.0,
    )
    assert r.status_code == 200, r.text
    assert r.json()["document_id"]


def test_list_documents_groups_by_upload_not_by_chunk(doc_kb_id):
    # Two separate uploads of the SAME filename must show as two distinct
    # documents (source alone can't disambiguate them -- document_id can, #427).
    for _ in range(2):
        doc = io.BytesIO(b"Repeated-filename upload content for #427.")
        up = httpx.post(
            f"{BASE}/knowledge-bases/{doc_kb_id}/upload",
            files={"file": ("same-name.txt", doc, "text/plain")},
            timeout=60.0,
        )
        assert up.status_code == 200, up.text

    r = httpx.get(f"{BASE}/knowledge-bases/{doc_kb_id}/documents", timeout=10.0)
    assert r.status_code == 200, r.text
    docs = [d for d in r.json() if d["filename"] == "same-name.txt"]
    assert len(docs) == 2
    assert docs[0]["document_id"] != docs[1]["document_id"]
    assert all(d["chunk_count"] >= 1 for d in docs)


def test_delete_document_removes_it_and_updates_kb_counts(doc_kb_id, auth_token):
    doc = io.BytesIO(b"Doc to be deleted for #427 delete-document test.")
    up = httpx.post(
        f"{BASE}/knowledge-bases/{doc_kb_id}/upload",
        files={"file": ("delete-me.txt", doc, "text/plain")},
        timeout=60.0,
    )
    assert up.status_code == 200, up.text
    document_id = up.json()["document_id"]

    kb_before = httpx.get(f"{BASE}/knowledge-bases/{doc_kb_id}", timeout=10.0).json()

    d = httpx.delete(
        f"{BASE}/knowledge-bases/{doc_kb_id}/documents/{document_id}",
        headers={"Authorization": f"Bearer {auth_token}"},
        timeout=20.0,
    )
    assert d.status_code == 200, d.text

    kb_after = httpx.get(f"{BASE}/knowledge-bases/{doc_kb_id}", timeout=10.0).json()
    assert kb_after["document_count"] == kb_before["document_count"] - 1
    assert kb_after["vector_count"] < kb_before["vector_count"]

    listing = httpx.get(f"{BASE}/knowledge-bases/{doc_kb_id}/documents", timeout=10.0)
    assert document_id not in [dd["document_id"] for dd in listing.json()]


def test_delete_unknown_document_404s(doc_kb_id, auth_token):
    r = httpx.delete(
        f"{BASE}/knowledge-bases/{doc_kb_id}/documents/does-not-exist",
        headers={"Authorization": f"Bearer {auth_token}"},
        timeout=10.0,
    )
    assert r.status_code == 404


def test_delete_document_unknown_kb_404s(auth_token):
    r = httpx.delete(
        f"{BASE}/knowledge-bases/does-not-exist/documents/does-not-exist",
        headers={"Authorization": f"Bearer {auth_token}"},
        timeout=10.0,
    )
    assert r.status_code == 404


def test_documents_endpoints_reachable_through_gateway(doc_kb_id, auth_token):
    # Regression test: api-gateway's /v1/rag/{path:path} proxy strips "v1/rag/" and
    # forwards the remainder VERBATIM (routes/proxy.py) -- it lands on the
    # UNVERSIONED path here, not /v1/..., so a route missing that deprecated alias
    # 404s through the gateway even though the direct /v1/... path (every other
    # test in this file) works fine. This exact bug shipped once (#427) because
    # nothing here had ever gone through the gateway before.
    doc = io.BytesIO(b"Gateway-path regression test content.")
    up = httpx.post(
        f"{GATEWAY}/v1/rag/knowledge-bases/{doc_kb_id}/upload",
        headers={"Authorization": f"Bearer {auth_token}"},
        files={"file": ("gateway-test.txt", doc, "text/plain")},
        timeout=60.0,
    )
    assert up.status_code == 200, up.text
    document_id = up.json()["document_id"]

    listing = httpx.get(
        f"{GATEWAY}/v1/rag/knowledge-bases/{doc_kb_id}/documents", timeout=10.0
    )
    assert listing.status_code == 200, listing.text
    assert any(d["filename"] == "gateway-test.txt" for d in listing.json())

    d = httpx.delete(
        f"{GATEWAY}/v1/rag/knowledge-bases/{doc_kb_id}/documents/{document_id}",
        headers={"Authorization": f"Bearer {auth_token}"},
        timeout=20.0,
    )
    assert d.status_code == 200, d.text
