"""
Chat endpoints
Handles AI chat interface with Ollama integration
"""
from fastapi import APIRouter, HTTPException, Request, Depends
import logging
import httpx
import json

from ..models import ChatRequest
from ..auth import get_current_user_optional
from ..middleware import expensive_limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["AI Chat"])


def setup_chat_routes(router, kernel, character_engine):
    """Setup chat routes with kernel and character engine references"""

    @router.post("")
    @expensive_limiter.limit("10/minute")  # Expensive operation (AI)
    async def chat(
        request: Request,
        chat_request: ChatRequest,
        current_user: dict = Depends(get_current_user_optional)
    ):
        """Chat with Minder AI - Rate limited"""
        if not kernel:
            raise HTTPException(
                status_code=503,
                detail="Kernel not initialized"
            )

        try:
            # Get character
            character_name = chat_request.character or "finbot"
            character = character_engine.get_character(character_name)
            if not character:
                character = character_engine.presets['finbot']

            # Query plugins for context
            plugin_results = await kernel.query_plugins(chat_request.message)

            # Generate AI response using Ollama
            response = await _generate_ai_response(
                chat_request.message,
                plugin_results,
                character
            )

            return {
                "response": response,
                "character": character.name,
                "plugins_used": [r['plugin'] for r in plugin_results],
                "model": "ollama"
            }

        except Exception as e:
            logger.error(f"Chat error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    return router


async def _generate_ai_response(
    message: str,
    plugin_results: list,
    character
) -> str:
    """Generate AI response using Ollama"""

    # Build context from plugins
    context_parts = []
    if plugin_results:
        for result in plugin_results:
            plugin_name = result.get('plugin', 'unknown')
            data = result.get('data', {})
            if data:
                json_str = json.dumps(data, ensure_ascii=False)[:200]
                context_parts.append(f"{plugin_name}: {json_str}")

    # Build system prompt
    system_prompt = (
        character.system_prompt if hasattr(character, 'system_prompt')
        else (
            "Sen Minder adlı yapay zeka bir asistansın. "
            "Türkçe konuşuyorsun. "
            "Kullanıcıya yardımcı ol, bilgileri net ve açık şekilde sun."
        )
    )

    # Build user prompt
    user_prompt = f"Kullanıcı mesajı: {message}\n"
    if context_parts:
        user_prompt += "\nEklenti bilgileri:\n" + "\n".join(context_parts)

    try:
        # Call Ollama API
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "http://ollama:11434/api/generate",
                json={
                    "model": "llama3.2",
                    "prompt": user_prompt,
                    "system": system_prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.7,
                        "num_ctx": 2048
                    }
                }
            )

            if response.status_code == 200:
                result = response.json()
                ai_response = result.get('response', '')
                if ai_response:
                    return ai_response.strip()
                else:
                    logger.warning("Ollama returned empty response")
                    return "Üzgünüm, şu an yanıt veremiyorum."
            else:
                logger.error(f"Ollama API error: {response.status_code}")
                return "AI servisi şu an kullanılamıyor."

    except Exception as e:
        logger.error(f"Ollama connection error: {e}")
        # Fallback to simple response
        if plugin_results:
            plugins_used = ", ".join([r['plugin'] for r in plugin_results])
            return (
                f"Minder olarak {plugins_used} eklentilerinden "
                f"bilgiler topladım. Size nasıl yardımcı olabilirim?"
            )

        return (
            "Minder olarak size nasıl yardımcı olabilirim? "
            "Fon analizi, network monitoring veya başka bir konu hakkında "
            "bilgi alabilirsiniz."
        )
