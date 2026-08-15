"""Unit tests for rag-pipeline/domain/pipelines/corrective_rag.CorrectiveRAGPipeline.

CRAG is pure LLM-graded orchestration (no retrieval/generation of its own): it grades
whether retrieved context answers the question and rewrites the query when it's weak.
The grade-parsing, score mapping, and rewrite guards are deterministic given a fake
llm_manager, and had zero coverage.

Loaded by-path (hyphenated service dir); pyproject sets asyncio_mode=auto.
"""

import importlib.util
from pathlib import Path

_MOD = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "services"
    / "rag-pipeline"
    / "domain"
    / "pipelines"
    / "corrective_rag.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("rag_corrective", _MOD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CorrectiveRAGPipeline = _load().CorrectiveRAGPipeline


class _FakeLLM:
    def __init__(self, text, error=False):
        self._text = text
        self.calls = 0
        self._error = error

    async def generate_response(self, **kwargs):
        self.calls += 1
        if self._error:
            # Mirrors OllamaManager.generate_response's real failure shape: never
            # raises, returns {"text": "Error generating response: ...", "error":
            # True} instead.
            return {"text": self._text, "error": True}
        return {"text": self._text}


# --- grade_context ----------------------------------------------------------


async def test_grade_empty_context_is_incorrect_without_calling_llm():
    llm = _FakeLLM("CORRECT")
    r = await CorrectiveRAGPipeline().grade_context("q", "   ", llm, "m")
    assert r == {"grade": "incorrect", "score": 0.0}
    assert llm.calls == 0  # short-circuits before the LLM


async def test_grade_correct_maps_to_score_one():
    r = await CorrectiveRAGPipeline().grade_context(
        "q", "ctx", _FakeLLM("CORRECT"), "m"
    )
    assert r == {"grade": "correct", "score": 1.0}


async def test_grade_ambiguous_maps_to_half():
    r = await CorrectiveRAGPipeline().grade_context(
        "q", "ctx", _FakeLLM("AMBIGUOUS"), "m"
    )
    assert r == {"grade": "ambiguous", "score": 0.5}


async def test_grade_incorrect_maps_to_zero():
    r = await CorrectiveRAGPipeline().grade_context(
        "q", "ctx", _FakeLLM("INCORRECT"), "m"
    )
    assert r == {"grade": "incorrect", "score": 0.0}


async def test_grade_unrecognized_defaults_to_ambiguous():
    r = await CorrectiveRAGPipeline().grade_context("q", "ctx", _FakeLLM("banana"), "m")
    assert r == {"grade": "ambiguous", "score": 0.5}


async def test_grade_tolerates_extra_text_around_keyword():
    r = await CorrectiveRAGPipeline().grade_context(
        "q", "ctx", _FakeLLM("Grade: CORRECT."), "m"
    )
    assert r["grade"] == "correct"


# --- rewrite_query ----------------------------------------------------------


async def test_rewrite_returns_stripped_query():
    r = await CorrectiveRAGPipeline().rewrite_query(
        "How do I do X?", _FakeLLM('  "focused x query"  '), "m"
    )
    assert r == "focused x query"


async def test_rewrite_empty_result_returns_empty():
    r = await CorrectiveRAGPipeline().rewrite_query("q", _FakeLLM("   "), "m")
    assert r == ""


async def test_rewrite_overlong_result_rejected():
    r = await CorrectiveRAGPipeline().rewrite_query("q", _FakeLLM("x" * 501), "m")
    assert r == ""


async def test_rewrite_returns_empty_not_error_text_on_llm_error_flag():
    """generate_response's error dict shape ({"text": "...", "error": True}) is
    short enough to pass the len<=500 guard -- without checking the flag, it
    would be returned as the "refined query" and get re-embedded/re-retrieved
    against verbatim instead of degrading to no rewrite."""
    r = await CorrectiveRAGPipeline().rewrite_query(
        "q", _FakeLLM("connection refused", error=True), "m"
    )
    assert r == ""


# --- correct() wrapper: still_insufficient signal (#661) --------------------
# rag/methods/corrective.py's correct() is a thin orchestration wrapper (grade ->
# maybe rewrite+re-retrieve). When the grade is poor and correction can't find
# anything better, it now flags details["still_insufficient"] so the runner can
# surface an honest "low-confidence" degraded note instead of silently answering
# from context CRAG itself judged insufficient.

_METHODS_MOD = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "services"
    / "rag-pipeline"
    / "rag"
    / "methods"
    / "corrective.py"
)


def _load_methods():
    spec = importlib.util.spec_from_file_location(
        "rag_corrective_methods", _METHODS_MOD
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


corrective_method = _load_methods()


class _FakePipeline:
    def __init__(self, grade, refined="a refined query"):
        self._grade = grade
        self._refined = refined

    async def grade_context(self, question, context, ollama_manager, model):
        return {"grade": self._grade, "score": 0.0}

    async def rewrite_query(self, question, ollama_manager, model):
        return self._refined


def _retrieve_factory(sources):
    async def retrieve(pipeline, query, top_k):
        return {"context": "ctx" if sources else "", "sources": sources}

    return retrieve


_ORIG = {"context": "original", "sources": [{"text": "orig"}]}


async def test_correct_flags_insufficient_when_incorrect_and_no_rewrite():
    pipe = _FakePipeline("incorrect", refined="")  # rewrite yields nothing
    result, details = await corrective_method.correct(
        "q", _ORIG, pipe, _retrieve_factory([]), {}, 3, None, "m"
    )
    assert result is _ORIG  # kept the original, uncorrected
    assert details["still_insufficient"] is True
    assert details["corrected"] is False


async def test_correct_flags_insufficient_when_reretrieval_empty():
    pipe = _FakePipeline("incorrect", refined="a refined query")
    result, details = await corrective_method.correct(
        "q", _ORIG, pipe, _retrieve_factory([]), {}, 3, None, "m"
    )
    assert result is _ORIG
    assert details["still_insufficient"] is True


async def test_correct_no_insufficient_flag_when_correction_succeeds():
    pipe = _FakePipeline("incorrect", refined="a refined query")
    better = [{"text": "much better"}]
    result, details = await corrective_method.correct(
        "q", _ORIG, pipe, _retrieve_factory(better), {}, 3, None, "m"
    )
    assert details["corrected"] is True
    assert "still_insufficient" not in details
    assert result["sources"] == better


async def test_correct_no_insufficient_flag_when_grade_good():
    pipe = _FakePipeline("correct")
    result, details = await corrective_method.correct(
        "q", _ORIG, pipe, _retrieve_factory([]), {}, 3, None, "m"
    )
    assert "still_insufficient" not in details
    assert result is _ORIG
