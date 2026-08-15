"""Unit tests for rag-pipeline/domain/expansion/hyde.HyDEQueryExpander.

HyDE generates a hypothetical answer via the LLM and embeds it. The orchestration
— validation, the disabled short-circuit, and the graceful degrade-to-not-expanded
on generation/embedding failure — is pure control flow around an injected
`llm_manager`, so it's tested with a fake manager (no real LLM). Had zero coverage.

Loaded by-path (hyphenated service dir); pyproject sets asyncio_mode=auto, so the
async tests need no decorator.
"""

import importlib.util
from pathlib import Path

import pytest

_MOD = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "services"
    / "rag-pipeline"
    / "domain"
    / "expansion"
    / "hyde.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("rag_hyde", _MOD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


HyDEQueryExpander = _load().HyDEQueryExpander


class _FakeLLM:
    """Injected llm_manager double: canned text + embedding, or raise on demand."""

    def __init__(
        self, text="a hypothetical answer", embedding=None, raise_on=None, error=False
    ):
        self._text = text
        self._embedding = embedding if embedding is not None else [0.1, 0.2, 0.3]
        self._raise_on = raise_on or set()
        self._error = error

    async def generate_response(self, prompt, model, temperature=0.7):
        if "generate_response" in self._raise_on:
            raise RuntimeError("llm down")
        if self._error:
            # Mirrors OllamaManager.generate_response's real failure shape: never
            # raises, returns {"text": "Error generating response: ...", "error":
            # True} instead.
            return {"text": f"Error generating response: {self._text}", "error": True}
        return {"text": self._text}

    async def generate_embeddings(self, texts, model):
        if "generate_embeddings" in self._raise_on:
            raise RuntimeError("embed down")
        return [self._embedding for _ in texts]


# --- generate_hypothetical_answer -------------------------------------------


async def test_generate_answer_empty_query_raises():
    with pytest.raises(ValueError):
        await HyDEQueryExpander().generate_hypothetical_answer("", _FakeLLM())


async def test_generate_answer_returns_llm_text():
    out = await HyDEQueryExpander().generate_hypothetical_answer(
        "What is RAG?", _FakeLLM(text="RAG is retrieval augmented generation.")
    )
    assert out == "RAG is retrieval augmented generation."


async def test_generate_answer_swallows_llm_error_to_empty():
    out = await HyDEQueryExpander().generate_hypothetical_answer(
        "q", _FakeLLM(raise_on={"generate_response"})
    )
    assert out == ""


async def test_generate_answer_returns_empty_not_error_text_on_llm_error_flag():
    """generate_response's OTHER failure mode: it doesn't always raise -- it can
    return an "error": True dict with the failure message in "text" instead.
    Without checking that flag, the error string would flow through as a
    truthy "hypothetical answer" and get embedded/searched against verbatim
    instead of falling back to the raw question, silently poisoning retrieval."""
    out = await HyDEQueryExpander().generate_hypothetical_answer(
        "q", _FakeLLM(text="connection refused", error=True)
    )
    assert out == ""


# --- expand_query -----------------------------------------------------------


async def test_expand_empty_query_raises():
    with pytest.raises(ValueError):
        await HyDEQueryExpander().expand_query("", _FakeLLM())


async def test_expand_disabled_short_circuits():
    exp = HyDEQueryExpander()
    exp._enabled = False
    r = await exp.expand_query("q", _FakeLLM())
    assert r == {"expanded": False, "reason": "HyDE disabled"}


async def test_expand_success_returns_embedding_and_query():
    r = await HyDEQueryExpander().expand_query(
        "What is RAG?",
        _FakeLLM(text="An answer.", embedding=[1.0, 2.0]),
        query_embedding=[0.5],
    )
    assert r["expanded"] is True
    assert r["hypothetical_answer"] == "An answer."
    assert r["hypothetical_embedding"] == [1.0, 2.0]
    assert r["original_query"] == "What is RAG?"
    assert r["original_embedding"] == [0.5]


async def test_expand_not_expanded_when_answer_empty():
    # LLM generation failed -> empty hypothetical -> degrade, don't expand.
    r = await HyDEQueryExpander().expand_query(
        "q", _FakeLLM(raise_on={"generate_response"})
    )
    assert r["expanded"] is False
    assert "answer" in r["reason"].lower()


async def test_expand_not_expanded_when_embedding_fails():
    r = await HyDEQueryExpander().expand_query(
        "q", _FakeLLM(raise_on={"generate_embeddings"})
    )
    assert r["expanded"] is False
    assert "embedding" in r["reason"].lower()
