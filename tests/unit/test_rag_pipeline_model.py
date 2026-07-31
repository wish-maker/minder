"""Unit tests for RAGPipelineCreate validation (#210 HIGH-2).

A pipeline created with an empty ``knowledge_base_ids`` used to persist fine and
then 500 (IndexError on ``knowledge_base_ids[0]``) on every query. The model now
requires at least one KB → rejected at the edge (422) instead.

rag-pipeline is a hyphenated service dir and its models module does
``from config import ...`` at import; a fake ``config`` is injected and restored so
another service's equally named top-level ``config`` isn't poisoned (the #142 gotcha).
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest
from pydantic import ValidationError

_MODELS = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "services"
    / "rag-pipeline"
    / "models"
    / "__init__.py"
)


@pytest.fixture
def rp_models():
    saved = sys.modules.get("config")
    fake = ModuleType("config")
    fake.DEFAULT_EMBEDDING_MODEL = "embed-model"
    fake.DEFAULT_LLM_MODEL = "llm-model"
    sys.modules["config"] = fake
    try:
        spec = importlib.util.spec_from_file_location("rp_models", _MODELS)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        yield mod
    finally:
        if saved is not None:
            sys.modules["config"] = saved
        else:
            sys.modules.pop("config", None)


def test_empty_knowledge_base_ids_rejected(rp_models):
    with pytest.raises(ValidationError):
        rp_models.RAGPipelineCreate(name="x", knowledge_base_ids=[])


def test_non_empty_knowledge_base_ids_accepted(rp_models):
    pipe = rp_models.RAGPipelineCreate(name="x", knowledge_base_ids=["kb1", "kb2"])
    assert pipe.knowledge_base_ids == ["kb1", "kb2"]
