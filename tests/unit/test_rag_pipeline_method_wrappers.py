"""Unit tests for rag-pipeline's small `rag/methods/*.py` wrappers: decision.py
(auto-routing via the decision engine), compress.py (contextual compression),
hyde.py (HyDE query rewriting), and self_rag.py (Self-RAG generation).

Each one shares the same shape -- an optional collaborator (engine/compressor/
expander/pipeline) is None-guarded, real work happens in a try/except that
never lets a failure propagate (falls back to the caller's default behavior
instead) -- and each had only 23-38% coverage per `coverage run`, meaning the
actual success- and exception-fallback branches were never directly exercised
(only indirectly, via whatever `rag.runner` integration tests happened to hit).

rag-pipeline is a hyphenated service dir, so its modules are loaded by path
with the collision-prone package names snapshotted/restored (same precedent
as test_rag_rerank_widening.py).
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


decision_mod, compress_mod, hyde_mod, self_rag_mod = _isolated_import(
    "rag.methods.decision",
    "rag.methods.compress",
    "rag.methods.hyde",
    "rag.methods.self_rag",
)


# --- decision.route ---------------------------------------------------------


class _Enum:
    def __init__(self, value):
        self.value = value


class _Analysis:
    def __init__(self, complexity, intent):
        self.complexity = complexity
        self.intent = intent


class _Decision:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class _Engine:
    def __init__(self, analysis=None, decision=None, raises=None):
        self._analysis = analysis
        self._decision = decision
        self._raises = raises

    async def analyze_query(self, question):
        if self._raises:
            raise self._raises
        return self._analysis

    async def decide_pipeline(self, analysis):
        return self._decision


@pytest.mark.asyncio
async def test_route_returns_defaults_when_engine_is_none():
    result = await decision_mod.route("q", None)
    assert result == (False, False, {})


@pytest.mark.asyncio
async def test_route_falls_back_to_defaults_on_engine_exception():
    engine = _Engine(raises=RuntimeError("boom"))
    result = await decision_mod.route("q", engine)
    assert result == (False, False, {})


@pytest.mark.asyncio
async def test_route_assembles_details_from_the_decision():
    analysis = _Analysis(complexity=_Enum("moderate"), intent="factual")
    decision = _Decision(
        use_hyde=True,
        use_self_rag=False,
        retrieval_strategy=_Enum("hybrid"),
        top_k=8,
        use_reranking=True,
        use_query_expansion=False,
    )
    engine = _Engine(analysis=analysis, decision=decision)

    use_hyde, use_self_rag, details = await decision_mod.route("q", engine)

    assert use_hyde is True
    assert use_self_rag is False
    assert details == {
        "complexity": "moderate",
        "intent": "factual",
        "use_hyde": True,
        "use_self_rag": False,
        "retrieval_strategy": "hybrid",
        "top_k": 8,
        "use_reranking": True,
        "use_query_expansion": False,
    }


@pytest.mark.asyncio
async def test_route_handles_a_missing_retrieval_strategy():
    analysis = _Analysis(complexity=_Enum("simple"), intent="chitchat")
    decision = _Decision(use_hyde=False, use_self_rag=False, retrieval_strategy=None)
    engine = _Engine(analysis=analysis, decision=decision)

    _, _, details = await decision_mod.route("q", engine)

    assert details["retrieval_strategy"] is None


# --- compress.apply -----------------------------------------------------------


class _Compressor:
    def __init__(self, result=None, raises=None):
        self._result = result
        self._raises = raises

    def compress(self, question, sources):
        if self._raises:
            raise self._raises
        return self._result


def test_apply_returns_unchanged_when_compressor_is_none():
    context_result = {"context": "full text", "sources": [{"text": "a"}]}
    result, details = compress_mod.apply("q", context_result, None)
    assert result is context_result
    assert details == {}


def test_apply_returns_unchanged_when_no_sources():
    context_result = {"context": "full text", "sources": []}
    result, details = compress_mod.apply("q", context_result, _Compressor())
    assert result is context_result
    assert details == {}


def test_apply_falls_back_on_compressor_exception():
    context_result = {"context": "full text", "sources": [{"text": "a"}]}
    compressor = _Compressor(raises=RuntimeError("boom"))
    result, details = compress_mod.apply("q", context_result, compressor)
    assert result is context_result
    assert details == {}


def test_apply_falls_back_when_no_compressed_context_returned():
    context_result = {"context": "full text", "sources": [{"text": "a"}]}
    compressor = _Compressor(result={"compressed_context": None})
    result, details = compress_mod.apply("q", context_result, compressor)
    assert result is context_result
    assert details == {}


def test_apply_returns_compressed_context_and_size_details():
    context_result = {"context": "full text", "sources": [{"text": "a"}]}
    compressor = _Compressor(
        result={
            "compressed_context": "short text",
            "original_length": 100,
            "compressed_length": 20,
        }
    )
    result, details = compress_mod.apply("q", context_result, compressor)
    assert result == {"context": "short text", "sources": [{"text": "a"}]}
    assert details == {"compressor": {"original_length": 100, "compressed_length": 20}}


# --- hyde.rewrite_query --------------------------------------------------------


class _Expander:
    def __init__(self, answer=None, raises=None):
        self._answer = answer
        self._raises = raises

    async def generate_hypothetical_answer(self, question, ollama_manager, model):
        if self._raises:
            raise self._raises
        return self._answer


@pytest.mark.asyncio
async def test_rewrite_query_returns_none_when_expander_is_none():
    result = await hyde_mod.rewrite_query("q", None, object(), "model")
    assert result is None


@pytest.mark.asyncio
async def test_rewrite_query_returns_none_on_exception():
    expander = _Expander(raises=RuntimeError("boom"))
    result = await hyde_mod.rewrite_query("q", expander, object(), "model")
    assert result is None


@pytest.mark.asyncio
async def test_rewrite_query_returns_none_for_an_empty_answer():
    expander = _Expander(answer="")
    result = await hyde_mod.rewrite_query("q", expander, object(), "model")
    assert result is None


@pytest.mark.asyncio
async def test_rewrite_query_returns_the_hypothetical_answer():
    expander = _Expander(answer="Acme makes widgets.")
    result = await hyde_mod.rewrite_query("q", expander, object(), "model")
    assert result == "Acme makes widgets."


# --- self_rag.generate ----------------------------------------------------------


class _Pipeline:
    def __init__(self, result=None, raises=None):
        self._result = result
        self._raises = raises

    async def generate_with_self_refinement(
        self, question, context, sources, llm_manager, model
    ):
        if self._raises:
            raise self._raises
        return self._result


@pytest.mark.asyncio
async def test_generate_returns_none_and_empty_quality_when_pipeline_is_none():
    answer, quality = await self_rag_mod.generate(
        None, "q", "ctx", ["src"], object(), "model"
    )
    assert (answer, quality) == (None, {})


@pytest.mark.asyncio
async def test_generate_falls_back_on_pipeline_exception():
    pipeline = _Pipeline(raises=RuntimeError("boom"))
    answer, quality = await self_rag_mod.generate(
        pipeline, "q", "ctx", ["src"], object(), "model"
    )
    assert (answer, quality) == (None, {})


@pytest.mark.asyncio
async def test_generate_treats_an_empty_answer_as_none_but_keeps_quality():
    pipeline = _Pipeline(result={"answer": "", "quality": {"score": 0.4}})
    answer, quality = await self_rag_mod.generate(
        pipeline, "q", "ctx", ["src"], object(), "model"
    )
    assert answer is None
    assert quality == {"score": 0.4}


@pytest.mark.asyncio
async def test_generate_returns_the_answer_and_quality():
    pipeline = _Pipeline(
        result={"answer": "42.", "quality": {"score": 0.9, "iterations": 2}}
    )
    answer, quality = await self_rag_mod.generate(
        pipeline, "q", "ctx", ["src"], object(), "model"
    )
    assert answer == "42."
    assert quality == {"score": 0.9, "iterations": 2}
