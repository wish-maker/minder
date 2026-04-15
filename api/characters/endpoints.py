"""
Character management endpoints
Handles AI character system management
"""

from fastapi import APIRouter, HTTPException
import logging

from ..models import CharacterCreateRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/characters", tags=["Characters"])


def setup_character_routes(router, character_engine):
    """Setup character routes with character engine reference"""

    @router.get("")
    async def list_characters():
        """List all characters"""
        if not character_engine:
            raise HTTPException(
                status_code=503, detail="Character engine not initialized"
            )

        return {"characters": character_engine.list_characters()}

    @router.post("")
    async def create_character(request: CharacterCreateRequest):
        """Create custom character"""
        if not character_engine:
            raise HTTPException(
                status_code=503, detail="Character engine not initialized"
            )

        try:
            from core.character_system import Personality, VoiceProfile

            personality = Personality(**request.personality)
            voice_profile = VoiceProfile(**request.voice_profile)

            character_engine.create_character(
                name=request.name,
                description=request.description,
                personality=personality,
                voice_profile=voice_profile,
                system_prompt=request.system_prompt,
            )

            return {"character": request.name, "status": "created"}

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return router
