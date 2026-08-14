"""Unit tests for rag-pipeline/domain/pipelines/self_rag.SelfRAGPipeline.

Self-RAG runs an iterative generate→evaluate→refine loop. The control flow — the
validation, the evaluator-absent single-pass (the common Pi path, #138), threshold
met on the first pass, hallucination-driven context reduction across iterations, and
the max-iterations exhaustion — is deterministic given a fake llm_manager and a fake
evaluator. Had zero coverage.

The real evaluator is loaded via `from domain.quality_evaluator import ...`, which
isn't importable in the by-path one-process harness — so `_load_evaluator` naturally
lands in its except branch and `evaluator` stays None (the evaluator-absent path).
For the with-evaluator paths we inject a fake and pre-set `_evaluator_loaded`.

Loaded by-path (hyphenated service dir); pyproject sets asyncio_mode=auto.
"""

import importlib.util
import threading
from pathlib import Path

import pytest

_MOD = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "services"
    / "rag-pipeline"
    / "domain"
    / "pipelines"
    / "self_rag.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("rag_self_rag", _MOD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SelfRAGPipeline = _load().SelfRAGPipeline

_SOURCES = [{"text": "s1"}, {"text": "s2"}, {"text": "s3"}]


class _FakeLLM:
    """Returns a canned answer per call (cycles through `answers`)."""

    def __init__(self, answers=("answer",)):
        self._answers = list(answers)
        self.calls = 0

    async def generate_response(self, **kwargs):
        a = self._answers[min(self.calls, len(self._answers) - 1)]
        self.calls += 1
        return {"text": a}


class _FakeEvaluator:
    """Returns a canned quality dict per evaluate call (cycles through `qualities`)."""

    def __init__(self, qualities):
        self._q = list(qualities)
        self.calls = 0

    def evaluate_answer_quality(self, **kwargs):
        q = self._q[min(self.calls, len(self._q) - 1)]
        self.calls += 1
        return q


def _with_evaluator(pipe, evaluator):
    pipe.evaluator = evaluator
    pipe._evaluator_loaded = True  # stop _load_evaluator from overwriting it
    return pipe


# --- __init__ validation ----------------------------------------------------


def test_init_rejects_nonpositive_iterations():
    with pytest.raises(ValueError):
        SelfRAGPipeline(max_iterations=0)


@pytest.mark.parametrize("thr", [-0.1, 1.1])
def test_init_rejects_out_of_range_threshold(thr):
    with pytest.raises(ValueError):
        SelfRAGPipeline(quality_threshold=thr)


# --- validation -------------------------------------------------------------


async def test_empty_question_raises():
    with pytest.raises(ValueError):
        await SelfRAGPipeline().generate_with_self_refinement(
            "", "ctx", _SOURCES, _FakeLLM()
        )


async def test_empty_context_raises():
    with pytest.raises(ValueError):
        await SelfRAGPipeline().generate_with_self_refinement(
            "q", "", _SOURCES, _FakeLLM()
        )


# --- evaluator-absent single pass (common Pi path, #138) --------------------


async def test_evaluator_absent_single_pass_reports_not_evaluated():
    # Force the evaluator-absent state (on a bare host _load_evaluator would fail to
    # import sentence-transformers; here the module IS importable via the test
    # sys.path, so pin evaluator=None + _evaluator_loaded to model the Pi path).
    pipe = _with_evaluator(SelfRAGPipeline(max_iterations=3), None)
    llm = _FakeLLM(["only answer"])
    r = await pipe.generate_with_self_refinement("q", "ctx", _SOURCES, llm)
    assert r["answer"] == "only answer"
    assert llm.calls == 1  # single generation, no refinement
    assert r["quality"]["evaluated"] is False
    assert r["quality"]["threshold_met"] is None  # never measured, not False
    assert r["quality"]["refined"] is False
    assert r["quality"]["iterations"] == 1


# --- with evaluator ---------------------------------------------------------


async def test_threshold_met_on_first_pass():
    pipe = _with_evaluator(
        SelfRAGPipeline(max_iterations=3, quality_threshold=0.7),
        _FakeEvaluator([{"overall_quality": 0.9}]),
    )
    llm = _FakeLLM(["good"])
    r = await pipe.generate_with_self_refinement("q", "ctx", _SOURCES, llm)
    assert r["quality"]["evaluated"] is True
    assert r["quality"]["threshold_met"] is True
    assert r["quality"]["iterations"] == 1
    assert r["quality"]["refined"] is False
    assert llm.calls == 1


async def test_evaluate_answer_quality_runs_off_the_event_loop():
    """evaluate_answer_quality does synchronous transformer encode/BERTScore work
    (plus a multi-second model load on first use) -- it must run via
    asyncio.to_thread so one Self-RAG query can't stall every other in-flight
    request on the service."""
    main_thread_id = threading.get_ident()
    seen_thread_ids = []

    class _ThreadSpyEvaluator(_FakeEvaluator):
        def evaluate_answer_quality(self, **kwargs):
            seen_thread_ids.append(threading.get_ident())
            return super().evaluate_answer_quality(**kwargs)

    pipe = _with_evaluator(
        SelfRAGPipeline(max_iterations=1, quality_threshold=0.7),
        _ThreadSpyEvaluator([{"overall_quality": 0.9}]),
    )
    await pipe.generate_with_self_refinement("q", "ctx", _SOURCES, _FakeLLM(["good"]))

    assert seen_thread_ids  # the evaluator actually ran
    assert all(tid != main_thread_id for tid in seen_thread_ids)


async def test_low_quality_runs_to_max_iterations():
    pipe = _with_evaluator(
        SelfRAGPipeline(max_iterations=2, quality_threshold=0.9),
        _FakeEvaluator([{"overall_quality": 0.1}, {"overall_quality": 0.2}]),
    )
    llm = _FakeLLM(["a1", "a2"])
    r = await pipe.generate_with_self_refinement("q", "ctx", _SOURCES, llm)
    assert r["quality"]["evaluated"] is True
    assert r["quality"]["threshold_met"] is False
    assert r["quality"]["iterations"] == 2
    assert r["quality"]["refined"] is True
    assert llm.calls == 2


async def test_hallucination_reduces_context_then_meets_threshold():
    # iter1: low + hallucination -> reduce context to top-2 sources; iter2: high -> met
    pipe = _with_evaluator(
        SelfRAGPipeline(max_iterations=2, quality_threshold=0.7),
        _FakeEvaluator(
            [
                {"overall_quality": 0.2, "hallucination": {"is_hallucination": True}},
                {"overall_quality": 0.95},
            ]
        ),
    )
    llm = _FakeLLM(["first", "second"])
    r = await pipe.generate_with_self_refinement("q", "ctx", _SOURCES, llm)
    assert r["answer"] == "second"
    assert r["quality"]["threshold_met"] is True
    assert r["quality"]["iterations"] == 2
    assert r["quality"]["refined"] is True


async def test_evaluation_exception_breaks_after_first():
    class _Boom:
        def evaluate_answer_quality(self, **kwargs):
            raise RuntimeError("evaluator blew up")

    pipe = _with_evaluator(SelfRAGPipeline(max_iterations=3), _Boom())
    llm = _FakeLLM(["a1", "a2", "a3"])
    r = await pipe.generate_with_self_refinement("q", "ctx", _SOURCES, llm)
    # The evaluator ran (evaluated stays False since the exception fires before the
    # evaluated=True line) and the loop breaks -> a single generation.
    assert r["answer"] == "a1"
    assert llm.calls == 1
    assert r["quality"]["iterations"] == 1
