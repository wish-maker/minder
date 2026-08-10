"""Unit tests for rag-pipeline/rag/text_utils.extract_text_from_file.

Regression for a real bug: a .txt/.md upload decoded with plain "utf-8"
turns a leading UTF-8 BOM (bytes EF BB BF -- written by Windows Notepad's
"UTF-8" save option and PowerShell's `Out-File -Encoding utf8`) into a
literal U+FEFF character. Nothing downstream (chunking, embedding, storage,
retrieval) ever strips it, so it survived all the way into the first
chunk's stored text and back out through the RAG query API's source
citation. Confirmed live on hantal: a PowerShell-written .txt upload came
back from `/v1/rag/pipeline/{id}/query` with a mangled prefix on the first
source's text. "utf-8-sig" decodes identically to "utf-8" when no BOM is
present, so this is a strict improvement with no behavior change for the
common (non-BOM) case.

The module is stdlib-only aside from pypdf/langchain imports done lazily
inside the function bodies, so it loads by-path with no fakes needed for
the .txt/.md branch under test.
"""

import importlib.util
from pathlib import Path

import pytest

_MOD = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "services"
    / "rag-pipeline"
    / "rag"
    / "text_utils.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("rag_text_utils", _MOD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


extract_text_from_file = _load().extract_text_from_file


@pytest.mark.asyncio
async def test_txt_upload_strips_leading_utf8_bom():
    content = b"\xef\xbb\xbfMinder is an AI platform."
    text = await extract_text_from_file(content, "verify_doc.txt")
    assert text == "Minder is an AI platform."
    assert "﻿" not in text


@pytest.mark.asyncio
async def test_md_upload_strips_leading_utf8_bom():
    content = b"\xef\xbb\xbf# Heading\n"
    text = await extract_text_from_file(content, "notes.md")
    assert not text.startswith("﻿")


@pytest.mark.asyncio
async def test_txt_upload_without_bom_is_unaffected():
    content = "Plain text, no BOM.".encode("utf-8")
    text = await extract_text_from_file(content, "plain.txt")
    assert text == "Plain text, no BOM."


@pytest.mark.asyncio
async def test_unknown_extension_also_strips_bom_via_utf8_fallback():
    content = b"\xef\xbb\xbfsome content"
    text = await extract_text_from_file(content, "notes.log")
    assert text == "some content"
