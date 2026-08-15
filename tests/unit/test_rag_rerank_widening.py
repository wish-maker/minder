"""Unit tests for rag-pipeline rerank candidate widening (#660).

A reranker can only reorder the candidate pool it is handed. Retrieval used to
truncate to exactly ``top_k`` BEFORE reranking, so the reranker only ever reshuffled
the same ``top_k`` items first-pass scoring already picked -- it could never promote a
relevant document ranked just outside ``top_k``. The runner now fetches
``top_k * RERANK_CANDIDATE_MULTIPLIER`` candidates when reranking will run, then trims
back to ``top_k`` after the rerank.

Two things are locked here: (1) ``rerank.truncate`` (pure), and (2) ``run_query``'s
end-to-end widening/truncation behaviour, asserting the exact ``top_k`` handed to the
retriever and the final source count.

rag-pipeline is a hyphenated service dir, so its modules are loaded by path with the
collision-prone package names snapshotted/restored (same precedent as the psm and
marketplace unit tests).
"""

import sys
from pathlib import Path

import pytest

_RAG = Path(__file__).resolve().parents[2] / "src" / "services" / "rag-pipeline"
_COLLISION_PRONE_NAMES = ("core", "models", "config", "rag", "domain", "repositories")


def _isolated_import(*module_paths: str):
    saved_path = list(sys.path)
    saved_modules = {}
    for name in _COLLISION_PRONE_NAMES:
        for key in list(sys.modules):
            if key == name or key.startswith(name + "."):
                saved_modules[key] = sys.modules.pop(key)
    sys.path.insert(0, str(_RAG))
    import os

    os.environ.setdefault("DB_PASSWORD", "test")
    os.environ.setdefault("REDIS_PASSWORD", "test")
    os.environ.setdefault("JWT_SECRET", "test")

    import importlib

    try:
        return [importlib.import_module(p) for p in module_paths]
    finally:
        sys.path[:] = saved_path
        for name in _COLLISION_PRONE_NAMES:
            for key in list(sys.modules):
                if key == name or key.startswith(name + "."):
                    sys.modules.pop(key, None)
        sys.modules.update(saved_modules)


runner, rerank_mod, config_mod = _isolated_import(
    "rag.runner", "rag.methods.rerank", "config"
)


# --- rerank.truncate -------------------------------------------------------


def test_truncate_trims_and_rebuilds_context():
    ctx = {
        "context": "a\n\nb\n\nc",
        "sources": [
            {"text": "a", "score": 0.9},
            {"text": "b", "score": 0.8},
            {"text": "c", "score": 0.7},
        ],
    }
    out = rerank_mod.truncate(ctx, 2)
    assert [s["text"] for s in out["sources"]] == ["a", "b"]
    assert out["context"] == "a\n\nb"


def test_truncate_noop_when_already_small():
    ctx = {"context": "a", "sources": [{"text": "a"}]}
    assert rerank_mod.truncate(ctx, 5) is ctx


def test_truncate_none_top_k_is_noop():
    ctx = {"context": "a", "sources": [{"text": "a"}]}
    assert rerank_mod.truncate(ctx, None) is ctx


# --- run_query widening ----------------------------------------------------


class _FakeOllama:
    """Enough of the ollama manager for the LLM-rerank fallback + generation."""

    async def generate_response(self, *a, **k):
        return {"text": "final answer", "model": "llama3.2", "tokens_used": 3}


class _Request:
    def __init__(self, top_k, rerank):
        self.question = "what is x?"
        self.top_k = top_k
        self.method = "standard"
        self.rerank = rerank
        self.compress = False
        self.conversation_id = None


def _make_components(capture):
    async def retrieve(pipeline, query, top_k):
        # Return exactly as many candidates as asked for, so the widened fetch and
        # the post-rerank truncation are both observable.
        capture["fetch_k"] = top_k
        return {
            "context": "\n\n".join(f"doc{i}" for i in range(top_k)),
            "sources": [
                {"text": f"doc{i}", "score": 1.0 - i * 0.001} for i in range(top_k)
            ],
        }

    return runner.RagComponents(ollama_manager=_FakeOllama(), retrieve=retrieve)


@pytest.mark.asyncio
async def test_rerank_widens_fetch_then_truncates_to_top_k():
    capture = {}
    components = _make_components(capture)
    multiplier = config_mod.settings.RERANK_CANDIDATE_MULTIPLIER

    result = await runner.run_query(
        pipeline={"knowledge_base_ids": ["kb1"]},
        pipeline_id="pipe1",
        request=_Request(top_k=5, rerank=True),
        llm_model="llama3.2",
        generation_config=None,
        components=components,
    )

    # Retrieval was widened to top_k * multiplier...
    assert capture["fetch_k"] == 5 * multiplier
    # ...and the final result is trimmed back to the requested top_k.
    assert len(result["sources"]) == 5


@pytest.mark.asyncio
async def test_no_rerank_fetches_exactly_top_k():
    capture = {}
    components = _make_components(capture)

    result = await runner.run_query(
        pipeline={"knowledge_base_ids": ["kb1"]},
        pipeline_id="pipe1",
        request=_Request(top_k=5, rerank=False),
        llm_model="llama3.2",
        generation_config=None,
        components=components,
    )

    # No widening on the common path -- fetch_k collapses to top_k.
    assert capture["fetch_k"] == 5
    assert len(result["sources"]) == 5
