"""Unit tests for rag-pipeline's rag/runner.run_query orchestration.

run_query is the query-orchestration core: method selection, HyDE/corrective/
rerank/compress branching, conversation context load/store, Self-RAG vs
standard generation, and the method_details/degraded bookkeeping surfaced to
clients (#138/#139). Previously only exercised narrowly (rerank widening in
test_rag_rerank_widening.py) and via its method-wrapper helpers in isolation
(test_rag_pipeline_method_wrappers.py) -- the orchestration itself (which
branches run, in what order, and how details/degraded/effective_method get
assembled) had no dedicated coverage.

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


(runner,) = _isolated_import("rag.runner")


class _Request:
    def __init__(
        self,
        question="what is x?",
        top_k=3,
        method="standard",
        rerank=False,
        compress=False,
        conversation_id=None,
    ):
        self.question = question
        self.top_k = top_k
        self.method = method
        self.rerank = rerank
        self.compress = compress
        self.conversation_id = conversation_id


class _FakeOllama:
    def __init__(self, text="final answer", model="llama3.2", tokens=3, error=None):
        self._text = text
        self._model = model
        self._tokens = tokens
        self._error = error
        self.last_context = None

    async def generate_response(self, prompt, context, **kwargs):
        self.last_context = context
        if self._error:
            return {"error": True, "text": self._error}
        return {"text": self._text, "model": self._model, "tokens_used": self._tokens}


def _retrieve(sources=None, context=None):
    sources = sources if sources is not None else [{"text": "doc0", "score": 0.9}]
    context = (
        context
        if context is not None
        else "\n\n".join(s.get("text", "") for s in sources)
    )

    async def retrieve(pipeline, query, top_k):
        return {"context": context, "sources": [dict(s) for s in sources]}

    return retrieve


def _components(**overrides):
    defaults = dict(ollama_manager=_FakeOllama(), retrieve=_retrieve())
    defaults.update(overrides)
    return runner.RagComponents(**defaults)


async def _run(components, request=None, generation_config=None):
    return await runner.run_query(
        pipeline={"knowledge_base_ids": ["kb1"]},
        pipeline_id="pipe1",
        request=request or _Request(),
        llm_model="llama3.2",
        generation_config=generation_config,
        components=components,
    )


# --- method validation -------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_method_falls_back_to_standard():
    result = await _run(_components(), _Request(method="not-a-real-method"))
    assert result["method"] == "standard"


# --- auto mode -----------------------------------------------------------------


class _FakeAnalysis:
    complexity = "simple"
    intent = "lookup"


class _FakeDecision:
    def __init__(
        self,
        use_hyde=False,
        use_self_rag=False,
        retrieval_strategy=None,
        top_k=None,
        use_reranking=False,
    ):
        self.use_hyde = use_hyde
        self.use_self_rag = use_self_rag
        self.retrieval_strategy = retrieval_strategy
        self.top_k = top_k
        self.use_reranking = use_reranking


class _FakeDecisionEngine:
    def __init__(self, decision):
        self._decision = decision

    async def analyze_query(self, question):
        return _FakeAnalysis()

    async def decide_pipeline(self, analysis):
        return self._decision


@pytest.mark.asyncio
async def test_auto_mode_applies_decision_top_k_and_flags_non_dense_strategy():
    decision = _FakeDecision(top_k=2, use_reranking=True, retrieval_strategy="hybrid")
    components = _components(decision_engine=_FakeDecisionEngine(decision))

    result = await _run(components, _Request(method="auto", top_k=5))

    assert result["method"] == "auto"
    details = result["method_details"]
    assert details["decision"]["applied"]["top_k"] == 2
    assert any("retrieval_strategy" in d for d in details["degraded"])


@pytest.mark.asyncio
async def test_auto_mode_degrades_when_decision_engine_missing():
    result = await _run(_components(decision_engine=None), _Request(method="auto"))

    assert result["method"] == "auto"
    assert any("engine unavailable" in d for d in result["method_details"]["degraded"])


# --- HyDE ------------------------------------------------------------------


class _FakeHydeExpander:
    def __init__(self, hypothetical):
        self._hyp = hypothetical

    async def generate_hypothetical_answer(self, question, ollama_manager, model):
        return self._hyp


@pytest.mark.asyncio
async def test_hyde_mode_rewrites_query_and_records_details():
    captured = {}

    async def retrieve(pipeline, query, top_k):
        captured["query"] = query
        return {"context": "doc", "sources": [{"text": "doc", "score": 0.5}]}

    components = _components(
        hyde_expander=_FakeHydeExpander("a hypothetical answer"), retrieve=retrieve
    )

    result = await _run(components, _Request(method="hyde"))

    assert captured["query"] == "a hypothetical answer"
    assert result["method"] == "hyde"
    assert result["method_details"]["hyde"]["hypothetical_chars"] == len(
        "a hypothetical answer"
    )


@pytest.mark.asyncio
async def test_hyde_mode_falls_back_to_standard_when_rewrite_is_empty():
    components = _components(hyde_expander=_FakeHydeExpander(""))

    result = await _run(components, _Request(method="hyde"))

    assert result["method"] == "standard"
    assert any(
        "expander unavailable" in d for d in result["method_details"]["degraded"]
    )


# --- Corrective RAG ----------------------------------------------------------


class _FakeCorrectivePipeline:
    def __init__(self, grade="incorrect", refined=None):
        self._grade = grade
        self._refined = refined

    async def grade_context(self, question, context, ollama_manager, model):
        return {"grade": self._grade, "score": 0.2}

    async def rewrite_query(self, question, ollama_manager, model):
        return self._refined


@pytest.mark.asyncio
async def test_corrective_mode_flags_still_insufficient_when_no_better_result():
    components = _components(
        corrective_pipeline=_FakeCorrectivePipeline(grade="incorrect", refined=None)
    )

    result = await _run(components, _Request(method="corrective"))

    assert result["method"] == "corrective"
    assert result["method_details"]["corrective"]["still_insufficient"] is True
    assert any("insufficient" in d for d in result["method_details"]["degraded"])


@pytest.mark.asyncio
async def test_corrective_mode_reports_standard_when_pipeline_unavailable():
    components = _components(corrective_pipeline=None)

    result = await _run(components, _Request(method="corrective"))

    # Grading never actually ran -- must not claim "corrective" happened.
    assert result["method"] == "standard"
    assert any(
        "pipeline unavailable" in d for d in result["method_details"]["degraded"]
    )


# --- RAPTOR ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_raptor_method_is_reported_honestly():
    result = await _run(_components(), _Request(method="raptor"))
    assert result["method"] == "raptor"


# --- Contextual compression --------------------------------------------------


class _FakeCompressor:
    def compress(self, question, sources):
        return {
            "compressed_context": "short ctx",
            "original_length": 100,
            "compressed_length": 10,
        }


@pytest.mark.asyncio
async def test_compress_flag_shrinks_context_and_records_details():
    components = _components(compressor=_FakeCompressor())

    result = await _run(components, _Request(compress=True))

    assert result["method_details"]["compressor"]["compressed_length"] == 10


# --- Conversation context -----------------------------------------------------


class _FakeConversationRepo:
    def __init__(self, context="a previous turn"):
        self._context = context
        self.stored = []

    async def build_context(self, user_id, conversation_id, max_turns):
        return self._context

    async def store_turn(self, **kwargs):
        self.stored.append(kwargs)


@pytest.mark.asyncio
async def test_conversation_context_is_prepended_and_turn_is_stored():
    ollama = _FakeOllama()
    repo = _FakeConversationRepo("a previous turn")
    components = _components(ollama_manager=ollama, conversation_repository=repo)

    await _run(components, _Request(conversation_id="conv1"))

    assert "Previous conversation:\na previous turn" in ollama.last_context
    assert len(repo.stored) == 1
    assert repo.stored[0]["conversation_id"] == "conv1"


class _RaisingConversationRepo:
    async def build_context(self, **kwargs):
        raise RuntimeError("db down")

    async def store_turn(self, **kwargs):
        raise RuntimeError("db down")


@pytest.mark.asyncio
async def test_conversation_repo_failures_are_swallowed_not_raised():
    components = _components(conversation_repository=_RaisingConversationRepo())

    result = await _run(components, _Request(conversation_id="conv1"))

    # Both build_context and store_turn raised -- run_query must still complete.
    assert result["answer"] is not None


# --- Self-RAG ------------------------------------------------------------------


class _FakeSelfRagPipeline:
    def __init__(self, answer="refined answer", quality=None):
        self._answer = answer
        self._quality = quality or {}

    async def generate_with_self_refinement(self, **kwargs):
        return {"answer": self._answer, "quality": self._quality}


@pytest.mark.asyncio
async def test_self_rag_success_without_evaluator_is_flagged_degraded():
    components = _components(
        self_rag_pipeline=_FakeSelfRagPipeline(quality={"evaluated": False})
    )

    result = await _run(components, _Request(method="self_rag"))

    assert result["method"] == "self_rag"
    assert result["answer"] == "refined answer"
    assert any(
        "quality evaluator unavailable" in d
        for d in result["method_details"]["degraded"]
    )


@pytest.mark.asyncio
async def test_self_rag_success_with_evaluator_is_not_flagged_degraded():
    components = _components(
        self_rag_pipeline=_FakeSelfRagPipeline(
            quality={"evaluated": True, "score": 0.9}
        )
    )

    result = await _run(components, _Request(method="self_rag"))

    assert result["method"] == "self_rag"
    assert "degraded" not in (result["method_details"] or {})


@pytest.mark.asyncio
async def test_self_rag_falls_back_to_standard_when_answer_is_empty():
    components = _components(self_rag_pipeline=_FakeSelfRagPipeline(answer=""))

    result = await _run(components, _Request(method="self_rag"))

    assert result["method"] == "standard"
    assert any(
        "pipeline unavailable or errored" in d
        for d in result["method_details"]["degraded"]
    )


# --- Generation errors / timer ------------------------------------------------


@pytest.mark.asyncio
async def test_generation_error_raised_when_ollama_reports_error():
    components = _components(ollama_manager=_FakeOllama(error="model not found"))

    with pytest.raises(runner.GenerationError, match="model not found"):
        await _run(components)


@pytest.mark.asyncio
async def test_gen_timer_is_used_to_time_generation_when_provided():
    calls = []

    class _FakeTimerCtx:
        def __enter__(self):
            calls.append("enter")
            return self

        def __exit__(self, *a):
            calls.append("exit")
            return False

    class _FakeLabels:
        def time(self):
            return _FakeTimerCtx()

    class _FakeHistogram:
        def labels(self, model):
            calls.append(("labels", model))
            return _FakeLabels()

    components = _components(gen_timer=_FakeHistogram())

    await _run(components)

    assert ("labels", "llama3.2") in calls
    assert calls.count("enter") == 1
    assert calls.count("exit") == 1


# --- Confidence ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_confidence_is_the_mean_of_numeric_source_scores_only():
    sources = [
        {"text": "a", "score": 0.8},
        {"text": "b", "score": "not-a-number"},
        {"text": "c", "score": 0.4},
    ]
    components = _components(retrieve=_retrieve(sources=sources))

    result = await _run(components)

    assert result["confidence"] == round((0.8 + 0.4) / 2, 3)


@pytest.mark.asyncio
async def test_confidence_is_zero_when_no_source_has_a_numeric_score():
    components = _components(retrieve=_retrieve(sources=[{"text": "a"}]))

    result = await _run(components)

    assert result["confidence"] == 0.0
