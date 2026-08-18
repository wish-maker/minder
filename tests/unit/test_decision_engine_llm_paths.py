"""Unit tests for AgentDecisionEngine's LLM-calling paths (rag-pipeline/domain/
decision_engine.py, 78% coverage).

test_decision_engine_heuristics.py only ever calls _fallback_analysis/
_heuristic_decision directly -- the actual analyze_query/decide_pipeline methods
(which call Ollama via httpx, parse its JSON response, and fall back to the
heuristics on any failure) were entirely untested: neither the success path nor
the except-Exception-falls-back-to-heuristic path had ever executed.

httpx.AsyncClient is imported locally inside each method (`import httpx`), which
resolves to the real, already-imported httpx module -- so patching the real
module's AsyncClient attribute (not a sys.modules fake) is sufficient and
matches how the method actually looks it up.
"""

import importlib.util
from pathlib import Path

import httpx
import pytest

_MOD = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "services"
    / "rag-pipeline"
    / "domain"
    / "decision_engine.py"
)


def _load():
    spec = importlib.util.spec_from_file_location(
        "decision_engine_llm_under_test", _MOD
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


de = _load()
Engine = de.AgentDecisionEngine
Complexity = de.QueryComplexity
Strategy = de.RetrievalStrategy


class _FakeResponse:
    def __init__(self, json_data, http_error=None):
        self._json_data = json_data
        self._http_error = http_error

    def raise_for_status(self):
        if self._http_error:
            raise self._http_error

    def json(self):
        return self._json_data


class _FakeAsyncClient:
    def __init__(self, response=None, post_error=None):
        self._response = response
        self._post_error = post_error
        self.posted_urls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def post(self, url, json):
        self.posted_urls.append(url)
        if self._post_error:
            raise self._post_error
        return self._response


def _patch_client(monkeypatch, **kwargs):
    fake = _FakeAsyncClient(**kwargs)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_: fake)
    return fake


def _analysis(complexity=Complexity.MODERATE, confidence=0.8):
    return de.QueryAnalysis(
        original_query="q",
        complexity=complexity,
        keywords=[],
        entities=[],
        intent="factual",
        confidence=confidence,
    )


# ── analyze_query: success path ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_analyze_query_parses_llm_response_into_query_analysis(monkeypatch):
    _patch_client(
        monkeypatch,
        response=_FakeResponse(
            {
                "response": (
                    '{"complexity": "complex", "keywords": ["rag", "vector"], '
                    '"entities": ["Acme"], "intent": "analytical", '
                    '"requires_external": true, "confidence": 0.9}'
                )
            }
        ),
    )

    result = await Engine().analyze_query("how does hybrid retrieval work at Acme")

    assert result.complexity is Complexity.COMPLEX
    assert result.keywords == ["rag", "vector"]
    assert result.entities == ["Acme"]
    assert result.intent == "analytical"
    assert result.requires_external is True
    assert result.confidence == 0.9


# ── analyze_query: falls back to heuristics on any failure ───────────────────


@pytest.mark.asyncio
async def test_analyze_query_falls_back_on_http_error(monkeypatch):
    _patch_client(
        monkeypatch,
        response=_FakeResponse(
            {}, http_error=httpx.HTTPStatusError("500", request=None, response=None)
        ),
    )

    result = await Engine().analyze_query("what is rag")  # 3 words -> SIMPLE

    assert result.complexity is Complexity.SIMPLE
    assert result.confidence == 0.6  # _fallback_analysis's own fixed value


@pytest.mark.asyncio
async def test_analyze_query_falls_back_on_malformed_json(monkeypatch):
    _patch_client(monkeypatch, response=_FakeResponse({"response": "not json"}))

    result = await Engine().analyze_query("what is rag")

    assert result.complexity is Complexity.SIMPLE  # fallback ran, not the LLM path


@pytest.mark.asyncio
async def test_analyze_query_falls_back_on_connection_error(monkeypatch):
    _patch_client(monkeypatch, post_error=ConnectionError("ollama unreachable"))

    result = await Engine().analyze_query("what is rag")

    assert result.confidence == 0.6


# ── decide_pipeline: success path ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_decide_pipeline_parses_llm_decision_and_records_history(monkeypatch):
    _patch_client(
        monkeypatch,
        response=_FakeResponse(
            {
                "response": (
                    '{"retrieval_strategy": "decomposition", "top_k": 18, '
                    '"similarity_threshold": 0.85, "use_reranking": true, '
                    '"use_query_expansion": true, "use_hyde": false, '
                    '"use_self_rag": true, "chunking_strategy": "recursive", '
                    '"reasoning_required": true}'
                )
            }
        ),
    )
    engine = Engine()
    analysis = _analysis(Complexity.COMPLEX)

    decision = await engine.decide_pipeline(analysis)

    assert decision.retrieval_strategy is Strategy.DECOMPOSITION
    assert decision.top_k == 18
    assert decision.similarity_threshold == 0.85
    assert decision.use_self_rag is True
    assert decision.chunking_strategy == "recursive"
    assert len(engine.decision_history) == 1
    assert engine.decision_history[0]["query"] == "q"


# ── decide_pipeline: falls back to the heuristic on any failure ──────────────


@pytest.mark.asyncio
async def test_decide_pipeline_falls_back_on_http_error(monkeypatch):
    _patch_client(
        monkeypatch,
        response=_FakeResponse(
            {}, http_error=httpx.HTTPStatusError("500", request=None, response=None)
        ),
    )
    engine = Engine()

    decision = await engine.decide_pipeline(_analysis(Complexity.SIMPLE))

    assert (
        decision.retrieval_strategy is Strategy.BASIC
    )  # _heuristic_decision's SIMPLE path
    assert decision.top_k == 5
    assert engine.decision_history == []  # fallback path never records history


@pytest.mark.asyncio
async def test_decide_pipeline_falls_back_on_malformed_json(monkeypatch):
    _patch_client(monkeypatch, response=_FakeResponse({"response": "not json"}))
    engine = Engine()

    decision = await engine.decide_pipeline(_analysis(Complexity.COMPLEX))

    assert decision.retrieval_strategy is Strategy.HIERARCHICAL
    assert engine.decision_history == []
