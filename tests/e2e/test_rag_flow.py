"""Real E2E coverage for the RAG document flow (#318 phase 3/5): create a
knowledge base -> upload a document -> query it -> cleanup, against a REAL
Qdrant instance (real `create_collection`/`upsert`/`query_points`/
`delete_collection` calls, #310's qdrant-client bump territory) and the
fake-Ollama stub for embeddings/generation (deterministic, no real model
needed -- see fake_ollama.py's docstring for why).
"""

import uuid

import httpx


def _upload_file(rag_url: str, kb_id: str, text: str, filename: str = "test.txt"):
    boundary = uuid.uuid4().hex
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: text/plain\r\n\r\n"
        f"{text}\r\n"
        f"--{boundary}--\r\n"
    ).encode()
    return httpx.post(
        f"{rag_url}/knowledge-bases/{kb_id}/upload",
        content=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        timeout=30.0,
    )


def test_full_rag_roundtrip(live_stack):
    live_stack.queue_generate_responses(
        [{"response": "Minder is a modular AI platform.", "done": True}]
    )

    create_resp = httpx.post(
        f"{live_stack.rag_url}/knowledge-bases",
        json={"name": "e2e-rag-flow-test"},
        timeout=15.0,
    )
    assert create_resp.status_code == 200
    kb = create_resp.json()
    kb_id = kb["id"]
    assert kb["vector_count"] == 0

    try:
        upload_resp = _upload_file(
            live_stack.rag_url,
            kb_id,
            "Minder is a modular AI platform with plugin-based data sources.",
        )
        assert upload_resp.status_code == 200
        upload_body = upload_resp.json()
        assert upload_body["vectors_created"] >= 1
        assert upload_body["chunks_processed"] >= 1

        pipeline_resp = httpx.post(
            f"{live_stack.rag_url}/pipeline",
            json={"name": "e2e-rag-flow-pipeline", "knowledge_base_ids": [kb_id]},
            timeout=15.0,
        )
        assert pipeline_resp.status_code == 200
        pipeline_id = pipeline_resp.json()["pipeline_id"]

        try:
            query_resp = httpx.post(
                f"{live_stack.rag_url}/pipeline/{pipeline_id}/query",
                json={"question": "What is Minder?"},
                timeout=30.0,
            )
            assert query_resp.status_code == 200
            query_body = query_resp.json()
            assert query_body["answer"] == "Minder is a modular AI platform."
            assert len(query_body["sources"]) >= 1
        finally:
            httpx.delete(f"{live_stack.rag_url}/pipeline/{pipeline_id}", timeout=15.0)
    finally:
        httpx.delete(f"{live_stack.rag_url}/knowledge-bases/{kb_id}", timeout=15.0)


def test_query_nonexistent_pipeline_404(live_stack):
    resp = httpx.post(
        f"{live_stack.rag_url}/pipeline/does-not-exist/query",
        json={"question": "anything"},
        timeout=15.0,
    )
    assert resp.status_code == 404


def test_create_pipeline_with_empty_kb_list_rejected(live_stack):
    """#210 HIGH-2 regression, at the real HTTP boundary this time (unit-tested
    already in tests/unit/test_rag_pipeline_model.py) -- an empty
    knowledge_base_ids must 422, not persist a pipeline that 500s on every query."""
    resp = httpx.post(
        f"{live_stack.rag_url}/pipeline",
        json={"name": "e2e-empty-kb-pipeline", "knowledge_base_ids": []},
        timeout=15.0,
    )
    assert resp.status_code == 422
