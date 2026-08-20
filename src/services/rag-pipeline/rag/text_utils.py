"""Text extraction and chunking helpers for document ingestion.

Extraction is a modular registry (#900), not a hardcoded if/elif: each
supported structured content type registers a detector (real magic-byte /
content sniffing, not a trusted filename extension) plus its extraction
function via `@register_extractor`. Adding a new supported format later is
one registration, not a change to the dispatch logic in
`extract_text_from_file`.

Before this, anything that wasn't `.pdf`/`.txt`/`.md` fell back to a
`latin-1` decode -- which never raises (every byte sequence is valid
latin-1), so arbitrary binary content (a PNG, confirmed live) was silently
"extracted" as garbage and embedded into a knowledge base with no warning.
`extract_text_from_file` now raises `UnsupportedContentError` when nothing
registered genuinely matches the content; callers turn that into a clean
415 instead of chunking/embedding noise.
"""

from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple


class UnsupportedContentError(ValueError):
    """Raised when uploaded content doesn't match any registered, genuinely
    detected structured format (#900) -- the caller (ingestion.py) turns
    this into a clean 415 rather than silently latin-1-decoding arbitrary
    binary content into a knowledge base."""


@dataclass(frozen=True)
class _Extractor:
    name: str
    extensions: Tuple[str, ...]
    magic_bytes: Tuple[bytes, ...]
    extract: Callable[[bytes], str]
    # Custom detector for formats a fixed magic-byte prefix can't express
    # (e.g. "genuinely text" sniffing). Receives (content, filename).
    is_match: Optional[Callable[[bytes, str], bool]] = None


_EXTRACTORS: List[_Extractor] = []


def register_extractor(
    name: str,
    extensions: Tuple[str, ...] = (),
    magic_bytes: Tuple[bytes, ...] = (),
    is_match: Optional[Callable[[bytes, str], bool]] = None,
):
    """Decorator registering an extraction function for a structured content
    type (#900).

    `extensions` are informational only (surfaced in error messages / future
    tooling) -- matching is by real content, never by trusting the filename
    alone. Exactly one of `magic_bytes` or `is_match` should do the real
    detection work for a given extractor; `is_match` takes precedence when
    both are given.
    """

    def decorator(fn: Callable[[bytes], str]) -> Callable[[bytes], str]:
        _EXTRACTORS.append(
            _Extractor(
                name=name,
                extensions=tuple(extensions),
                magic_bytes=tuple(magic_bytes),
                extract=fn,
                is_match=is_match,
            )
        )
        return fn

    return decorator


def _matches(extractor: _Extractor, content: bytes, filename: str) -> bool:
    if extractor.is_match is not None:
        return extractor.is_match(content, filename)
    return any(content.startswith(prefix) for prefix in extractor.magic_bytes)


def _looks_like_text(content: bytes, _filename: str) -> bool:
    """Genuine "is this actually text" sniffing, not just "doesn't crash on
    decode" -- latin-1 never raises (every byte sequence is valid latin-1),
    which is exactly why the old fallback silently accepted binary content.
    Requires a clean UTF-8(-sig) decode AND an overwhelmingly printable
    result -- real text/markdown clears this easily; a PNG/JPEG/etc. either
    fails the UTF-8 decode outright or decodes into mostly non-printable
    characters.
    """
    if not content:
        return True
    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return False
    if not decoded:
        return True
    non_printable = sum(1 for ch in decoded if not (ch.isprintable() or ch in "\n\r\t"))
    return (non_printable / len(decoded)) < 0.01


@register_extractor(name="pdf", extensions=(".pdf",), magic_bytes=(b"%PDF-",))
def _extract_pdf(content: bytes) -> str:
    import io

    from pypdf import PdfReader

    pdf_file = io.BytesIO(content)
    reader = PdfReader(pdf_file)
    text = ""
    for page in reader.pages:
        text += page.extract_text()
    return text


@register_extractor(name="text", extensions=(".txt", ".md"), is_match=_looks_like_text)
def _extract_text(content: bytes) -> str:
    # "utf-8-sig" strips a leading BOM if present (e.g. files saved by
    # Windows Notepad or PowerShell's `Out-File -Encoding utf8`) and decodes
    # identically to "utf-8" otherwise. Plain "utf-8" turned the BOM into a
    # literal U+FEFF character that survived chunking, embedding, and
    # retrieval -- polluting the first chunk of every such document all the
    # way to the API response.
    return content.decode("utf-8-sig")


async def extract_text_from_file(content: bytes, filename: str) -> str:
    """Extract text from `content` via the first registered extractor whose
    detector genuinely matches (#900) -- real content sniffing, not a
    trusted filename extension (a `.pdf`-named file with no real `%PDF-`
    header is rejected, not blindly decoded).

    Raises UnsupportedContentError if nothing registered matches.
    """
    for extractor in _EXTRACTORS:
        if _matches(extractor, content, filename):
            return extractor.extract(content)
    raise UnsupportedContentError(
        f"Unsupported or unrecognized content in {filename!r} -- no "
        "structured extractor matched this file's actual content."
    )


def chunk_text(text: str, chunk_size: int = 512, chunk_overlap: int = 50) -> List[str]:
    """Chunk text into smaller pieces"""
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    chunks = text_splitter.split_text(text)
    return chunks
