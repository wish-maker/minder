"""Unit tests for RAG generation-model resolution (rag-pipeline/rag/model_selection).

Regression for the bug where a KB's stored ``llm_model`` was ignored at query time
(the query always fell back to the platform default because the pipeline never
captured it). Precedence: per-query override → pipeline → first KB → default.

The module is stdlib-only, so it loads by-path with no fakes.
"""

import importlib.util
from pathlib import Path

_MOD = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "services"
    / "rag-pipeline"
    / "rag"
    / "model_selection.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("rag_model_selection", _MOD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


resolve = _load().resolve_llm_model

_KBS = {
    "kb-strong": {"llm_model": "command-r"},
    "kb-default": {"llm_model": "llama3.2"},
    "kb-nomodel": {},  # older KB row without the field
}


def _pipe(kb_ids, llm_model=None):
    p = {"knowledge_base_ids": kb_ids}
    if llm_model is not None:
        p["llm_model"] = llm_model
    return p


def test_kb_llm_model_is_honored_not_default():
    # The core bug: a KB configured for a stronger model must actually be used.
    assert resolve(None, _pipe(["kb-strong"]), _KBS, "llama3.2") == "command-r"


def test_per_query_override_wins_over_kb():
    assert (
        resolve("qwen2.5-coder:32b", _pipe(["kb-strong"]), _KBS, "llama3.2")
        == "qwen2.5-coder:32b"
    )


def test_pipeline_setting_beats_kb_but_loses_to_override():
    assert resolve(None, _pipe(["kb-strong"], "mistral"), _KBS, "llama3.2") == "mistral"
    assert resolve("phi4", _pipe(["kb-strong"], "mistral"), _KBS, "llama3.2") == "phi4"


def test_uses_first_kb_when_multiple():
    assert (
        resolve(None, _pipe(["kb-strong", "kb-default"]), _KBS, "llama3.2")
        == "command-r"
    )


def test_falls_back_to_default_when_kb_has_no_model():
    assert resolve(None, _pipe(["kb-nomodel"]), _KBS, "llama3.2") == "llama3.2"


def test_falls_back_to_default_when_kb_unknown_or_empty():
    assert resolve(None, _pipe(["missing-kb"]), _KBS, "llama3.2") == "llama3.2"
    assert resolve(None, _pipe([]), _KBS, "llama3.2") == "llama3.2"
