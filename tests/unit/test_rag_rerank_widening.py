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


# --- rerank._llm_rerank / rerank.apply --------------------------------------


class _RankingOllama:
    """Returns a fixed ranking string, e.g. "2,0,1", from generate_response."""

    def __init__(self, text):
        self._text = text

    async def generate_response(self, *a, **k):
        return {"text": self._text}


class _RaisingOllama:
    async def generate_response(self, *a, **k):
        raise RuntimeError("ollama unreachable")


@pytest.mark.asyncio
async def test_llm_rerank_reorders_by_model_ranking():
    sources = [{"text": "a"}, {"text": "b"}, {"text": "c"}]
    ordered = await rerank_mod._llm_rerank(
        "q", sources, _RankingOllama("2,0,1"), "llama3.2"
    )
    assert [s["text"] for s in ordered] == ["c", "a", "b"]


@pytest.mark.asyncio
async def test_llm_rerank_appends_indices_the_model_dropped():
    # Model only ranks index 1 -- the other two must still appear, in their
    # original order, appended after it (nothing the model omits is lost).
    sources = [{"text": "a"}, {"text": "b"}, {"text": "c"}]
    ordered = await rerank_mod._llm_rerank(
        "q", sources, _RankingOllama("1"), "llama3.2"
    )
    assert [s["text"] for s in ordered] == ["b", "a", "c"]


@pytest.mark.asyncio
async def test_llm_rerank_ignores_out_of_range_and_duplicate_indices():
    sources = [{"text": "a"}, {"text": "b"}]
    ordered = await rerank_mod._llm_rerank(
        "q", sources, _RankingOllama("5,0,0,1"), "llama3.2"
    )
    assert [s["text"] for s in ordered] == ["a", "b"]


@pytest.mark.asyncio
async def test_llm_rerank_returns_none_when_no_sources_to_rank():
    result = await rerank_mod._llm_rerank("q", [], _RankingOllama(""), "llama3.2")
    assert result is None


@pytest.mark.asyncio
async def test_llm_rerank_returns_none_on_generation_failure():
    sources = [{"text": "a"}, {"text": "b"}]
    result = await rerank_mod._llm_rerank("q", sources, _RaisingOllama(), "llama3.2")
    assert result is None


@pytest.mark.asyncio
async def test_apply_returns_unchanged_when_fewer_than_two_sources():
    ctx = {"sources": [{"text": "a"}]}
    result, details = await rerank_mod.apply(
        "q", ctx, None, _RankingOllama("0"), "llama3.2"
    )
    assert result is ctx
    assert details == {}


@pytest.mark.asyncio
async def test_apply_returns_unchanged_when_no_sources_key():
    ctx = {}
    result, details = await rerank_mod.apply(
        "q", ctx, None, _RankingOllama("0"), "llama3.2"
    )
    assert result is ctx
    assert details == {}


class _FakeCrossEncoderReranker:
    def __init__(self):
        self.model = True

    def rerank(self, question, sources, top_k):
        return [(sources[1], 0.9), (sources[0], 0.5)]


@pytest.mark.asyncio
async def test_apply_prefers_cross_encoder_when_model_available():
    ctx = {"context": "a\n\nb", "sources": [{"text": "a"}, {"text": "b"}]}
    result, details = await rerank_mod.apply(
        "q", ctx, _FakeCrossEncoderReranker(), _RankingOllama("0,1"), "llama3.2"
    )
    assert details == {"reranker": "cross_encoder"}
    assert [s["text"] for s in result["sources"]] == ["b", "a"]
    assert result["context"] == "b\n\na"


class _UnavailableCrossEncoderReranker:
    """`.model` lazily loads and returns False when sentence-transformers/torch
    isn't installed -- apply() must fall back to the LLM path in that case."""

    model = False


@pytest.mark.asyncio
async def test_apply_falls_back_to_llm_when_cross_encoder_model_unavailable():
    ctx = {"context": "a\n\nb", "sources": [{"text": "a"}, {"text": "b"}]}
    result, details = await rerank_mod.apply(
        "q", ctx, _UnavailableCrossEncoderReranker(), _RankingOllama("1,0"), "llama3.2"
    )
    assert details == {"reranker": "llm"}
    assert [s["text"] for s in result["sources"]] == ["b", "a"]


@pytest.mark.asyncio
async def test_apply_returns_unchanged_when_llm_rerank_fails():
    ctx = {"context": "a\n\nb", "sources": [{"text": "a"}, {"text": "b"}]}
    result, details = await rerank_mod.apply(
        "q", ctx, None, _RaisingOllama(), "llama3.2"
    )
    assert result is ctx
    assert details == {}
