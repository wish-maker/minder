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
UnsupportedContentError = _mod.UnsupportedContentError
register_extractor = _mod.register_extractor


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
async def test_invalid_utf8_binary_content_is_rejected_not_latin1_decoded():
    """#900: this used to silently fall back to a latin-1 decode (which never
    raises -- every byte sequence is valid latin-1), turning arbitrary binary
    content into "successfully extracted" garbage. \xe9 alone is an incomplete
    UTF-8 multi-byte sequence -- genuinely not text -- and must now be
    rejected outright rather than decoded into something that merely looks
    plausible ("café")."""
    content = b"caf\xe9"
    with pytest.raises(UnsupportedContentError):
        await extract_text_from_file(content, "notes.dat")


@pytest.mark.asyncio
async def test_real_binary_content_png_is_rejected_not_embedded_as_garbage():
    """#900 live repro: a real PNG header was silently accepted (200),
    chunked into one garbage chunk, and embedded into a knowledge base with
    no warning. Must now be rejected."""
    content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    with pytest.raises(UnsupportedContentError):
        await extract_text_from_file(content, "image.png")


@pytest.mark.asyncio
async def test_pdf_extension_with_fake_magic_bytes_is_rejected():
    """A `.pdf`-named file with no real PDF header, and whose bytes also
    aren't genuine text, must not be trusted by extension alone -- detection
    is by real content, not the filename."""
    content = b"\x00\x01\xfe\xff\x02\x00\xff\x10" * 4
    with pytest.raises(UnsupportedContentError):
        await extract_text_from_file(content, "fake.pdf")


@pytest.mark.asyncio
async def test_pdf_extension_with_genuinely_text_content_is_accepted_as_text():
    """Detection is by real content, not the filename -- a `.pdf`-named file
    whose bytes are actually plain text is accepted (as text), not rejected
    just because its extension lied."""
    text = await extract_text_from_file(b"just plain text", "mislabeled.pdf")
    assert text == "just plain text"


@pytest.mark.asyncio
async def test_registry_is_extensible_without_touching_the_dispatch_function():
    """Structural proof of #900's modularity requirement: a brand-new format
    can be supported by registering one extractor, with zero changes to
    extract_text_from_file itself."""
    marker = b"\xf0\x9f\xa6\x84MADEUP-FORMAT\x00"

    @register_extractor(name="madeup", magic_bytes=(marker,))
    def _extract_madeup(content: bytes) -> str:
        return "decoded by the newly-registered extractor"

    try:
        text = await extract_text_from_file(marker + b"payload", "thing.madeup")
        assert text == "decoded by the newly-registered extractor"
    finally:
        _mod._EXTRACTORS.remove(next(e for e in _mod._EXTRACTORS if e.name == "madeup"))


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

    # Must carry a real PDF magic-byte prefix (#900: detection is by content,
    # not filename) -- the actual body past the header is irrelevant since
    # PdfReader itself is mocked below.
    text = await extract_text_from_file(b"%PDF-1.4 irrelevant-bytes", "doc.pdf")

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
