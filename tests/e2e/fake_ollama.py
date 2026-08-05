"""Deterministic fake Ollama server for the real-process E2E harness.

Real Ollama (image pull + model pull + inference) is the slow, flaky,
non-deterministic part of what rag-pipeline/api-gateway call — we own the code
that *calls* it, not the model's output quality. This stub implements just the
three endpoints the `ollama` Python client / api-gateway's raw httpx calls
actually hit (confirmed against the installed `ollama` package source):

- `GET /api/tags`     — OllamaManager._test_connection()/ensure_model() list
                        available models; returning names that match whatever
                        the tests reference means `ensure_model` never tries to
                        pull (no /api/pull endpoint needed).
- `POST /api/embeddings` — AsyncClient.embeddings() (rag-pipeline). Returns a
                        fixed-length deterministic vector (matches
                        EMBEDDING_DIMENSIONS["nomic-embed-text"] = 768 in
                        rag-pipeline/config.py) so real Qdrant upsert/search
                        gets a real, consistent vector to index/match against.
- `POST /api/chat`    — AsyncClient.chat() (rag-pipeline) / raw httpx (api-
                        gateway's _ollama_chat). Pops the next response a test
                        pre-loaded via `/_control/chat_responses`; falls back
                        to a plain assistant reply if the queue is empty so
                        tests that don't care about the exact wording don't
                        need to set anything up.

Control endpoints (`/_control/*`) are this stub's own API, not part of
Ollama's — tests use them to script exactly what the "model" says next.
"""

from collections import deque
from typing import Any, Dict, List

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

_chat_queue: deque = deque()

EMBED_DIM = 768
_FIXED_EMBEDDING = [0.01 * (i % 100) for i in range(EMBED_DIM)]

_KNOWN_MODELS = [
    "nomic-embed-text:latest",
    "llama3.2:latest",
    "command-r:latest",
    "qwen2.5-coder:latest",
]


class ChatResponsesBody(BaseModel):
    responses: List[Dict[str, Any]]


@app.get("/api/tags")
async def tags():
    return {"models": [{"name": name} for name in _KNOWN_MODELS]}


@app.post("/api/embeddings")
async def embeddings(body: Dict[str, Any]):
    return {"embedding": _FIXED_EMBEDDING}


@app.post("/api/embed")
async def embed(body: Dict[str, Any]):
    # Some callers use the newer plural-response /api/embed shape directly.
    return {"embeddings": [_FIXED_EMBEDDING]}


@app.post("/api/chat")
async def chat(body: Dict[str, Any]):
    if _chat_queue:
        return _chat_queue.popleft()
    return {
        "model": body.get("model", "test-model"),
        "message": {"role": "assistant", "content": "OK"},
        "done": True,
    }


@app.post("/_control/chat_responses")
async def queue_chat_responses(body: ChatResponsesBody):
    """Push scripted /api/chat responses (FIFO) for the next N calls."""
    for r in body.responses:
        _chat_queue.append(r)
    return {"queued": len(body.responses)}


@app.post("/_control/reset")
async def reset():
    _chat_queue.clear()
    return {"ok": True}
