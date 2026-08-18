"""
Functional tests for the rag-pipeline service, run against the real
live-process harness (`live_stack`, #437 -- moved here from tests/integration/
so these actually execute in CI instead of silently skipping for lack of a
network-reachable service).

Exercises the standard RAG path end-to-end (knowledge base -> upload -> pipeline ->
query) and checks the `method` field added when HyDE/Self-RAG/decision-engine were
wired in (#45). The query runs generation against the fake-Ollama stub, so it is
deterministic and fast.
"""

import io
import os

import httpx
import pytest


@pytest.fixture(scope="module")
def pipeline_id(live_stack, auth_token):
    """Create a KB, upload a small doc, and build a pipeline; return its id."""
    base = live_stack.rag_url
    headers = {"Authorization": f"Bearer {auth_token}"}
    # Canonical plural collection path (#144); the singular form still works as a
    # deprecated alias.
    kb = httpx.post(
        f"{base}/knowledge-bases",
        json={"name": f"test-func-{os.getpid()}", "description": "functional test"},
        headers=headers,
        timeout=20.0,
    )
    assert kb.status_code == 200, kb.text
    kb_id = kb.json()["id"]

    doc = io.BytesIO(
        b"The functional-test fact: the sentinel token is ZORBLAX-42. "
        b"Embeddings are stored in Qdrant and generation uses a local Llama model."
    )
    up = httpx.post(
        f"{base}/knowledge-bases/{kb_id}/upload",
        files={"file": ("fact.txt", doc, "text/plain")},
        headers=headers,
        timeout=60.0,
    )
    assert up.status_code == 200, up.text
    assert up.json()["vectors_created"] >= 1

    pl = httpx.post(
        f"{base}/pipeline",
        json={"name": f"test-pl-{os.getpid()}", "knowledge_base_ids": [kb_id]},
        headers=headers,
        timeout=20.0,
    )
    assert pl.status_code == 200, pl.text
    return pl.json()["pipeline_id"]


@pytest.fixture(scope="module")
def auth_token(live_stack):
    """A JWT for calling rag-pipeline's auth-gated DELETE routes directly against
    its own port (matching how this file calls every other route, #427's
    delete_document included) -- registers a throwaway user via the gateway once
    per module, same pattern as test_auth_regression.py."""
    username = f"ragtest-{os.getpid()}"
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


@pytest.fixture(scope="module")
def filter_pipeline_id(live_stack, auth_token):
    """A KB with two documents carrying distinct sentinel facts, dedicated to
    metadata_filter tests -- proves filtering actually excludes chunks from the
    non-matching document rather than just silently accepting the parameter."""
    base = live_stack.rag_url
    headers = {"Authorization": f"Bearer {auth_token}"}
    kb = httpx.post(
        f"{base}/knowledge-bases",
        json={
            "name": f"test-filter-{os.getpid()}",
            "description": "metadata filter test",
        },
        headers=headers,
        timeout=20.0,
    )
    assert kb.status_code == 200, kb.text
    kb_id = kb.json()["id"]

    up_a = httpx.post(
        f"{base}/knowledge-bases/{kb_id}/upload",
        files={
            "file": (
                "filter-doc-a.txt",
                io.BytesIO(b"Document A's sentinel token is FILTERALPHA-1."),
                "text/plain",
            )
        },
        headers=headers,
        timeout=60.0,
    )
    assert up_a.status_code == 200, up_a.text

    up_b = httpx.post(
        f"{base}/knowledge-bases/{kb_id}/upload",
        files={
            "file": (
                "filter-doc-b.txt",
                io.BytesIO(b"Document B's sentinel token is FILTERBETA-2."),
                "text/plain",
            )
        },
        headers=headers,
        timeout=60.0,
    )
    assert up_b.status_code == 200, up_b.text

    pl = httpx.post(
        f"{base}/pipeline",
        json={
            "name": f"test-filter-pl-{os.getpid()}",
            "knowledge_base_ids": [kb_id],
        },
        headers=headers,
        timeout=20.0,
    )
    assert pl.status_code == 200, pl.text
    return pl.json()["pipeline_id"]


def test_metadata_filter_excludes_non_matching_source_dense(
    live_stack, filter_pipeline_id, auth_token
):
    r = httpx.post(
        f"{live_stack.rag_url}/pipeline/{filter_pipeline_id}/query",
        json={
            "question": "What is the sentinel token?",
            "top_k": 5,
            "metadata_filter": {"source": "filter-doc-a.txt"},
        },
        headers={"Authorization": f"Bearer {auth_token}"},
        timeout=180.0,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sources"], "no sources returned"
    assert all(s["source"] == "filter-doc-a.txt" for s in body["sources"])
    assert body["method_details"]["metadata_filter"] == {"source": "filter-doc-a.txt"}


def test_metadata_filter_excludes_non_matching_source_hybrid(
    live_stack, filter_pipeline_id, auth_token
):
    r = httpx.post(
        f"{live_stack.rag_url}/pipeline/{filter_pipeline_id}/query",
        json={
            "question": "What is the sentinel token?",
            "top_k": 5,
            "hybrid": True,
            "metadata_filter": {"source": "filter-doc-b.txt"},
        },
        headers={"Authorization": f"Bearer {auth_token}"},
        timeout=180.0,
    )
    assert r.status_code == 200, r.text
    sources = r.json()["sources"]
    assert sources, "no sources returned"
    assert all(s["source"] == "filter-doc-b.txt" for s in sources)


@pytest.fixture
def doc_kb_id(live_stack, auth_token):
    """A fresh, empty KB dedicated to document list/delete tests (#427) -- kept
    separate from `pipeline_id`'s KB so deleting a document here can't affect
    the other tests that query against that KB's one known document."""
    kb = httpx.post(
        f"{live_stack.rag_url}/knowledge-bases",
        json={"name": f"test-docs-{os.getpid()}", "description": "document tests"},
        headers={"Authorization": f"Bearer {auth_token}"},
        timeout=20.0,
    )
    assert kb.status_code == 200, kb.text
    return kb.json()["id"]


def test_health_reports_ollama_available(live_stack):
    r = httpx.get(f"{live_stack.rag_url}/health", timeout=8.0)
    assert r.status_code == 200
    assert r.json().get("ollama_available") is True


def test_list_knowledge_bases(live_stack):
    # #501: list endpoints return the shared {items,total,limit,offset} envelope,
    # not a bare array -- so a client can tell whether more pages exist.
    r = httpx.get(f"{live_stack.rag_url}/knowledge-bases", timeout=10.0)
    assert r.status_code == 200
    body = r.json()
    assert set(body) >= {"items", "total", "limit", "offset"}
    assert isinstance(body["items"], list)
    assert body["total"] >= len(body["items"])


def test_list_pipelines_includes_created_pipeline(live_stack, pipeline_id):
    # #426: before this endpoint existed, a pipeline_id only ever existed in the
    # create response -- confirm it's actually recoverable via list.
    r = httpx.get(f"{live_stack.rag_url}/pipeline", timeout=10.0)
    assert r.status_code == 200
    ids = [p["id"] for p in r.json()["items"]]  # #501 envelope
    assert pipeline_id in ids


def test_get_pipeline_by_id(live_stack, pipeline_id):
    r = httpx.get(f"{live_stack.rag_url}/pipeline/{pipeline_id}", timeout=10.0)
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == pipeline_id
    assert body["knowledge_base_ids"]


def test_get_unknown_pipeline_404s(live_stack):
    r = httpx.get(f"{live_stack.rag_url}/pipeline/does-not-exist", timeout=10.0)
    assert r.status_code == 404


def test_standard_query_grounded(live_stack, pipeline_id, auth_token):
    r = httpx.post(
        f"{live_stack.rag_url}/pipeline/{pipeline_id}/query",
        json={"question": "What is the sentinel token?", "top_k": 3},
        headers={"Authorization": f"Bearer {auth_token}"},
        timeout=180.0,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["answer"], "empty answer"
    assert body["method"] == "standard"  # method field added in #45
    assert body["sources"], "no sources returned"


def test_invalid_method_rejected_with_422(live_stack, pipeline_id, auth_token):
    # An unknown method must fail loudly rather than silently running standard, so the
    # caller learns what they actually asked for (#138). 422 lists the valid values.
    r = httpx.post(
        f"{live_stack.rag_url}/pipeline/{pipeline_id}/query",
        json={"question": "What is the sentinel token?", "top_k": 2, "method": "bogus"},
        headers={"Authorization": f"Bearer {auth_token}"},
        timeout=180.0,
    )
    assert r.status_code == 422, r.text
    assert "valid values" in r.text.lower()


def test_retrieval_strategy_reported(live_stack, pipeline_id, auth_token):
    # A standard query reports the retrieval strategy it actually used (#138).
    r = httpx.post(
        f"{live_stack.rag_url}/pipeline/{pipeline_id}/query",
        json={"question": "What is the sentinel token?", "top_k": 2},
        headers={"Authorization": f"Bearer {auth_token}"},
        timeout=180.0,
    )
    assert r.status_code == 200, r.text
    assert r.json()["method_details"]["retrieval"] == "dense"


def test_upload_response_includes_document_id(live_stack, doc_kb_id, auth_token):
    doc = io.BytesIO(b"Doc A content for #427 document-list tests.")
    r = httpx.post(
        f"{live_stack.rag_url}/knowledge-bases/{doc_kb_id}/upload",
        files={"file": ("doc-a.txt", doc, "text/plain")},
        headers={"Authorization": f"Bearer {auth_token}"},
        timeout=60.0,
    )
    assert r.status_code == 200, r.text
    assert r.json()["document_id"]


def test_list_documents_groups_by_upload_not_by_chunk(
    live_stack, doc_kb_id, auth_token
):
    # Two separate uploads of the SAME filename must show as two distinct
    # documents (source alone can't disambiguate them -- document_id can, #427).
    for _ in range(2):
        doc = io.BytesIO(b"Repeated-filename upload content for #427.")
        up = httpx.post(
            f"{live_stack.rag_url}/knowledge-bases/{doc_kb_id}/upload",
            files={"file": ("same-name.txt", doc, "text/plain")},
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=60.0,
        )
        assert up.status_code == 200, up.text

    r = httpx.get(
        f"{live_stack.rag_url}/knowledge-bases/{doc_kb_id}/documents", timeout=10.0
    )
    assert r.status_code == 200, r.text
    docs = [d for d in r.json()["items"] if d["filename"] == "same-name.txt"]
    assert len(docs) == 2
    assert docs[0]["document_id"] != docs[1]["document_id"]
    assert all(d["chunk_count"] >= 1 for d in docs)


def test_delete_document_removes_it_and_updates_kb_counts(
    live_stack, doc_kb_id, auth_token
):
    doc = io.BytesIO(b"Doc to be deleted for #427 delete-document test.")
    up = httpx.post(
        f"{live_stack.rag_url}/knowledge-bases/{doc_kb_id}/upload",
        files={"file": ("delete-me.txt", doc, "text/plain")},
        headers={"Authorization": f"Bearer {auth_token}"},
        timeout=60.0,
    )
    assert up.status_code == 200, up.text
    document_id = up.json()["document_id"]

    kb_before = httpx.get(
        f"{live_stack.rag_url}/knowledge-bases/{doc_kb_id}", timeout=10.0
    ).json()

    d = httpx.delete(
        f"{live_stack.rag_url}/knowledge-bases/{doc_kb_id}/documents/{document_id}",
        headers={"Authorization": f"Bearer {auth_token}"},
        timeout=20.0,
    )
    assert d.status_code == 200, d.text

    kb_after = httpx.get(
        f"{live_stack.rag_url}/knowledge-bases/{doc_kb_id}", timeout=10.0
    ).json()
    assert kb_after["document_count"] == kb_before["document_count"] - 1
    assert kb_after["vector_count"] < kb_before["vector_count"]

    listing = httpx.get(
        f"{live_stack.rag_url}/knowledge-bases/{doc_kb_id}/documents", timeout=10.0
    )
    assert document_id not in [dd["document_id"] for dd in listing.json()["items"]]


def test_delete_unknown_document_404s(live_stack, doc_kb_id, auth_token):
    r = httpx.delete(
        f"{live_stack.rag_url}/knowledge-bases/{doc_kb_id}/documents/does-not-exist",
        headers={"Authorization": f"Bearer {auth_token}"},
        timeout=10.0,
    )
    assert r.status_code == 404


def test_delete_document_unknown_kb_404s(live_stack, auth_token):
    r = httpx.delete(
        f"{live_stack.rag_url}/knowledge-bases/does-not-exist/documents/does-not-exist",
        headers={"Authorization": f"Bearer {auth_token}"},
        timeout=10.0,
    )
    assert r.status_code == 404


def test_documents_endpoints_reachable_through_gateway(
    live_stack, doc_kb_id, auth_token
):
    # Regression test: api-gateway's /v1/rag/{path:path} proxy strips "v1/rag/" and
    # forwards the remainder VERBATIM (routes/proxy.py) -- it lands on the
    # UNVERSIONED path here, not /v1/..., so a route missing that deprecated alias
    # 404s through the gateway even though the direct /v1/... path (every other
    # test in this file) works fine. This exact bug shipped once (#427) because
    # nothing here had ever gone through the gateway before.
    doc = io.BytesIO(b"Gateway-path regression test content.")
    up = httpx.post(
        f"{live_stack.gateway_url}/v1/rag/knowledge-bases/{doc_kb_id}/upload",
        headers={"Authorization": f"Bearer {auth_token}"},
        files={"file": ("gateway-test.txt", doc, "text/plain")},
        timeout=60.0,
    )
    assert up.status_code == 200, up.text
    document_id = up.json()["document_id"]

    listing = httpx.get(
        f"{live_stack.gateway_url}/v1/rag/knowledge-bases/{doc_kb_id}/documents",
        timeout=10.0,
    )
    assert listing.status_code == 200, listing.text
    assert any(d["filename"] == "gateway-test.txt" for d in listing.json()["items"])

    d = httpx.delete(
        f"{live_stack.gateway_url}/v1/rag/knowledge-bases/{doc_kb_id}/documents/{document_id}",
        headers={"Authorization": f"Bearer {auth_token}"},
        timeout=20.0,
    )
    assert d.status_code == 200, d.text
