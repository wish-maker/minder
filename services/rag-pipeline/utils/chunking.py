"""
Text Chunking Utilities

Shared text chunking functionality used across multiple components.
Eliminates code duplication and provides consistent chunking behavior.

This is a utility module for shared text processing.
"""

import logging
from typing import List

logger = logging.getLogger(__name__)

# Optional dependency handling
try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    RecursiveCharacterTextSplitter = None
    logging.warning("langchain-text-splitters not available. Install with: pip install langchain-text-splitters")


def chunk_text(
    text: str,
    chunk_size: int = 512,
    chunk_overlap: int = 50
) -> List[str]:
    """
    Chunk text into smaller pieces for processing

    Uses RecursiveCharacterTextSplitter from langchain for intelligent
    text splitting that maintains context while respecting chunk boundaries.

    Args:
        text: Input text to chunk
        chunk_size: Maximum chunk size in characters
        chunk_overlap: Overlap between chunks for context continuity

    Returns:
        List of text chunks

    Raises:
        ValueError: If text or parameters invalid
        RuntimeError: If langchain not available

    Example:
        >>> chunks = chunk_text("Long document text...", chunk_size=100, chunk_overlap=20)
        >>> print(f"Generated {len(chunks)} chunks")
        Generated 15 chunks
    """
    if not text:
        raise ValueError("text cannot be empty")

    if chunk_size <= 0:
        raise ValueError(f"chunk_size must be positive, got {chunk_size}")

    if chunk_overlap < 0:
        raise ValueError(f"chunk_overlap must be non-negative, got {chunk_overlap}")

    if chunk_overlap >= chunk_size:
        raise ValueError(f"chunk_overlap must be less than chunk_size, got {chunk_overlap} >= {chunk_size}")

    if not LANGCHAIN_AVAILABLE:
        raise RuntimeError("langchain-text-splitters not available. Install with: pip install langchain-text-splitters")

    try:
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

        chunks = text_splitter.split_text(text)

        logger.debug(f"✅ Chunked text into {len(chunks)} chunks (size={chunk_size}, overlap={chunk_overlap})")

        return chunks

    except Exception as e:
        logger.error(f"❌ Chunking failed: {e}")
        raise


def chunk_text_fallback(
    text: str,
    chunk_size: int = 512,
    chunk_overlap: int = 50
) -> List[str]:
    """
    Fallback chunking without langchain dependency

    Simple character-based chunking when langchain is unavailable.
    Maintains overlap between chunks for context continuity.

    Args:
        text: Input text to chunk
        chunk_size: Maximum chunk size in characters
        chunk_overlap: Overlap between chunks

    Returns:
        List of text chunks

    Raises:
        ValueError: If text or parameters invalid

    Note:
        This is a simplified fallback. For production use, install langchain.
    """
    if not text:
        raise ValueError("text cannot be empty")

    if chunk_size <= 0:
        raise ValueError(f"chunk_size must be positive, got {chunk_size}")

    if chunk_overlap < 0:
        raise ValueError(f"chunk_overlap must be non-negative, got {chunk_overlap}")

    if chunk_overlap >= chunk_size:
        raise ValueError(f"chunk_overlap must be less than chunk_size, got {chunk_overlap} >= {chunk_size}")

    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)

        # Move start position with overlap
        start = end - chunk_overlap

        # Prevent infinite loop with small chunks
        if start <= 0:
            start = end

    logger.debug(f"✅ Chunked text into {len(chunks)} chunks (fallback method)")

    return chunks
