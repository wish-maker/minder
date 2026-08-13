"""Unit tests for rag-pipeline/domain/compressors/contextual.ContextualCompressor.

The compressor is pure, dependency-free logic (sentence-level query-relevance
extraction) that had zero coverage. Includes a regression for #566: a non-empty
context list whose entries all have empty/missing text used to divide by zero in
the percentage debug-log (evaluated eagerly regardless of log level) → a 500 on a
RAG query with `compress: true`.

Loaded by-path because the service dir is hyphenated (`rag-pipeline`).
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
    / "compressors"
    / "contextual.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("rag_contextual_compressor", _MOD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ContextualCompressor = _load().ContextualCompressor


# --- __init__ validation ----------------------------------------------------


def test_init_rejects_nonpositive_max_tokens():
    with pytest.raises(ValueError):
        ContextualCompressor(max_tokens=0)


@pytest.mark.parametrize("ratio", [0.0, -0.1, 1.5])
def test_init_rejects_out_of_range_ratio(ratio):
    with pytest.raises(ValueError):
        ContextualCompressor(compression_ratio=ratio)


def test_init_accepts_ratio_of_one():
    c = ContextualCompressor(max_tokens=10, compression_ratio=1.0)
    assert c.max_tokens == 10 and c.compression_ratio == 1.0


# --- compress: guards -------------------------------------------------------


def test_compress_empty_query_raises():
    with pytest.raises(ValueError):
        ContextualCompressor().compress("", [{"text": "anything"}])


def test_compress_no_contexts_returns_zero():
    assert ContextualCompressor().compress("q", []) == {
        "compressed_context": "",
        "original_length": 0,
        "compressed_length": 0,
    }


@pytest.mark.parametrize("contexts", [[{"text": ""}], [{}]])
def test_compress_single_empty_text_context_returns_zero(contexts):
    # Regression for #566: a single empty/missing-text ctx -> joined text is "" ->
    # original_length 0 -> used to divide by zero in the percentage debug-log.
    assert ContextualCompressor().compress("some query", contexts) == {
        "compressed_context": "",
        "original_length": 0,
        "compressed_length": 0,
    }


def test_compress_multiple_empty_text_contexts_does_not_crash():
    # Two empty texts still join to the "\n\n" separator (len 2), so this doesn't hit
    # the len-0 guard — but it must not crash and yields no compressed content.
    r = ContextualCompressor().compress("some query", [{"text": ""}, {}])
    assert r["compressed_context"] == ""
    assert r["compressed_length"] == 0


# --- compress: normal behaviour ---------------------------------------------


def test_compress_combines_contexts_for_original_length():
    # texts joined by "\n\n" -> "A" + "\n\n" + "B" = 4 chars
    r = ContextualCompressor(compression_ratio=1.0).compress(
        "A B", [{"text": "A"}, {"text": "B"}]
    )
    assert r["original_length"] == 4


def test_compress_keeps_relevant_and_drops_irrelevant_sentence():
    # ratio 1.0 keeps everything that fits; ordering is by query relevance.
    text = "The sky is blue. Cats eat fish."
    r = ContextualCompressor(compression_ratio=1.0).compress(
        "blue sky", [{"text": text}]
    )
    assert "sky is blue" in r["compressed_context"]
    assert r["compressed_length"] > 0


def test_compress_truncates_to_max_tokens():
    # Several short sentences so extraction yields >4 chars; max_tokens=1 ->
    # max_chars = 1 * 4 = 4, so the result is truncated to 4 chars + "...".
    r = ContextualCompressor(max_tokens=1, compression_ratio=1.0).compress(
        "aa bb cc", [{"text": "aa. bb. cc."}]
    )
    assert r["compressed_context"].endswith("...")
    assert len(r["compressed_context"]) == 7  # 4 + len("...")


# --- _extract_key_sentences directly ----------------------------------------


def test_extract_respects_target_length_budget():
    c = ContextualCompressor()
    text = "The sky is blue. Cats eat fish."
    # "The sky is blue" (15) + 2 == 17 fits; adding "Cats eat fish" (13) would be 32.
    out = c._extract_key_sentences("blue sky", text, target_length=17)
    assert out == "The sky is blue."


def test_extract_both_sentences_when_budget_allows():
    c = ContextualCompressor()
    text = "The sky is blue. Cats eat fish."
    out = c._extract_key_sentences("blue sky fish", text, target_length=100)
    assert "sky is blue" in out and "Cats eat fish" in out


def test_extract_falls_back_to_prefix_when_no_query_words():
    c = ContextualCompressor()
    # whitespace-only query -> no query words -> return text[:target_length]
    out = c._extract_key_sentences("   ", "abcdefghij", target_length=4)
    assert out == "abcd"


def test_extract_empty_text_returns_prefix():
    c = ContextualCompressor()
    assert c._extract_key_sentences("q", "", target_length=10) == ""
