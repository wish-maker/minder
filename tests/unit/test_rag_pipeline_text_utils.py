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


_mod = _load()
extract_text_from_file = _mod.extract_text_from_file
chunk_text = _mod.chunk_text


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


@pytest.mark.asyncio
async def test_unknown_extension_falls_back_to_latin_1_on_invalid_utf8():
    # \xe9 alone is an incomplete UTF-8 multi-byte sequence (invalid), but a
    # perfectly valid single latin-1 byte (=> U+00E9, "é").
    content = b"caf\xe9"
    text = await extract_text_from_file(content, "notes.dat")
    assert text == "café"


@pytest.mark.asyncio
async def test_pdf_extraction_concatenates_text_across_all_pages(monkeypatch):
    """The pypdf import is local to the function body -- monkeypatch the real
    top-level `pypdf` package's PdfReader with a duck-typed fake so this
    exercises the real per-page concatenation loop without needing to hand-
    construct a PDF with actual extractable text content."""
    pytest.importorskip("pypdf")

    class _FakePage:
        def __init__(self, text):
            self._text = text

        def extract_text(self):
            return self._text

    class _FakeReader:
        def __init__(self, file_obj):
            self.pages = [_FakePage("Page one. "), _FakePage("Page two.")]

    monkeypatch.setattr("pypdf.PdfReader", _FakeReader)

    text = await extract_text_from_file(b"irrelevant-bytes", "doc.pdf")

    assert text == "Page one. Page two."


def test_chunk_text_splits_long_text_into_multiple_chunks():
    pytest.importorskip("langchain_text_splitters")
    long_text = "\n\n".join(f"Paragraph {i}. " * 20 for i in range(5))

    chunks = chunk_text(long_text, chunk_size=200, chunk_overlap=20)

    assert len(chunks) > 1
    assert all(len(c) <= 200 for c in chunks)
    assert all(c.strip() for c in chunks)


def test_chunk_text_short_text_returns_a_single_chunk():
    pytest.importorskip("langchain_text_splitters")
    short_text = "Just one short sentence."

    chunks = chunk_text(short_text, chunk_size=512, chunk_overlap=50)

    assert chunks == [short_text]
