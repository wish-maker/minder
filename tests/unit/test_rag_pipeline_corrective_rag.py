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
    def __init__(self, text):
        self._text = text
        self.calls = 0

    async def generate_response(self, **kwargs):
        self.calls += 1
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
