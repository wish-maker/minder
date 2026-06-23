"""
Streaming Response Utilities for RAG Pipeline

Provides token-by-token streaming for better user experience.
"""

import json
import logging
from typing import AsyncGenerator

logger = logging.getLogger(__name__)


async def generate_streaming_response(
    ollama_manager,
    question: str,
    context: str,
    model: str,
    temperature: float,
    sources_count: int,
) -> AsyncGenerator[str, None]:
    """
    Generate streaming response token by token.

    Args:
        ollama_manager: Ollama manager instance
        question: User question
        context: Retrieved context
        model: LLM model name
        temperature: Generation temperature
        sources_count: Number of retrieved sources

    Yields:
        Server-Sent Events (SSE) formatted chunks
    """
    try:
        # Send initial metadata
        yield f"data: {json.dumps({'type': 'start', 'sources_count': sources_count})}\n\n"

        # Generate answer with streaming
        full_text = ""
        chunk_count = 0

        async for chunk in ollama_manager.generate_response_stream(
            prompt=question,
            context=context,
            model=model,
            temperature=temperature,
        ):
            if chunk:
                full_text += chunk
                chunk_count += 1

                # Send token chunk
                yield f"data: {json.dumps({'type': 'token', 'text': chunk, 'chunk_id': chunk_count})}\n\n"

                logger.debug(f"Streamed chunk {chunk_count}: {len(chunk)} chars")

        # Send completion signal
        yield f"data: {json.dumps({'type': 'done', 'total_chunks': chunk_count, 'total_length': len(full_text)})}\n\n"

        logger.info(
            f"✅ Streaming complete: {chunk_count} chunks, {len(full_text)} chars"
        )

    except Exception as e:
        logger.error(f"Streaming error: {e}")
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"


def calculate_confidence(sources: list) -> float:
    """
    Calculate confidence score based on retrieval scores.

    Args:
        sources: List of retrieved documents with scores

    Returns:
        Confidence score between 0.0 and 1.0
    """
    if not sources:
        return 0.5  # Low confidence when no sources found

    avg_score = sum(source.get("score", 0) for source in sources) / len(sources)
    # Normalize score to confidence range (0.5-0.95)
    confidence = min(0.5 + (avg_score * 0.45), 0.95)

    return confidence
