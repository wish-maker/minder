"""Text extraction and chunking helpers for document ingestion."""

from typing import List


async def extract_text_from_file(content: bytes, filename: str) -> str:
    """Extract text from file based on type"""
    import io

    from pypdf import PdfReader

    if filename.endswith(".pdf"):
        pdf_file = io.BytesIO(content)
        reader = PdfReader(pdf_file)
        text = ""
        for page in reader.pages:
            text += page.extract_text()
        return text
    elif filename.endswith(".txt") or filename.endswith(".md"):
        # "utf-8-sig" strips a leading BOM if present (e.g. files saved by
        # Windows Notepad or PowerShell's `Out-File -Encoding utf8`) and
        # decodes identically to "utf-8" otherwise. Plain "utf-8" turned the
        # BOM into a literal U+FEFF character that survived chunking,
        # embedding, and retrieval -- polluting the first chunk of every
        # such document all the way to the API response.
        return content.decode("utf-8-sig")
    else:
        # Default: try UTF-8 decode
        try:
            return content.decode("utf-8-sig")
        except UnicodeDecodeError:
            return content.decode("latin-1")


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
