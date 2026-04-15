"""
Minder Character System
Customizable AI personalities for voice interactions
"""
from typing import Dict, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
import json
import logging

logger = logging.getLogger(__name__)

@dataclass
class VoiceProfile:
    """Voice characteristics for TTS"""
    language: str = 'en'
    voice_id: Optional[str] = None
    speed: float = 1.0
    pitch: float = 0.0
    emotion: str = 'neutral'
    accent: Optional[str] = None

@dataclass
class Personality:
    """Personality traits"""
    friendliness: float = 0.7
    formality: float = 0.5
    humor: float = 0.3
    expertise: str = 'professional'
    empathy: float = 0.6
    proactivity: float = 0.5

@dataclass
class Character:
    """AI character configuration"""
    name: str
    description: str
    personality: Personality = field(default_factory=Personality)
    voice_profile: VoiceProfile = field(default_factory=VoiceProfile)
    system_prompt: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    is_active: bool = True

class CharacterEngine:
    """
    Manages AI character personalities

    Provides:
    - Character presets
    - Custom character creation
    - Voice profile management
    - Personality injection into prompts
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.characters: Dict[str, Character] = {}
        self.presets = self._load_presets()

    def _load_presets(self) -> Dict[str, Character]:

        return {
            'finbot': Character(
                name='FinBot',
                description='Professional financial assistant',
                personality=Personality(
                    friendliness=0.7,
                    formality=0.8,
                    humor=0.2,
                    expertise='professional',
                    empathy=0.5,
                    proactivity=0.7
                ),
                voice_profile=VoiceProfile(
                    language='tr',
                    speed=1.0,
                    pitch=0.0,
                    emotion='neutral'
                ),
                system_prompt="""You are FinBot, a professional financial assistant for Turkish investors.

Your role:
- Provide investment recommendations based on Modern Portfolio Theory
- Explain financial concepts clearly
- Highlight risks without being alarmist
- Be proactive in suggesting portfolio optimizations

Tone: Professional but approachable, analytical, risk-conscious
Language: Turkish (primary), English (secondary)
"""
            ),

            'sysbot': Character(
                name='SysBot',
                description='Technical system administrator',
                personality=Personality(
                    friendliness=0.5,
                    formality=0.6,
                    humor=0.4,
                    expertise='professional',
                    empathy=0.3,
                    proactivity=0.8
                ),
                voice_profile=VoiceProfile(
                    language='en',
                    speed=1.2,
                    pitch=-2.0,
                    emotion='neutral'
                ),
                system_prompt="""You are SysBot, a technical system administrator.

Your role:
- Monitor system health and performance
- Alert to issues proactively
- Provide technical diagnostics
- Suggest optimizations

Tone: Direct, technical, efficient, slightly dry humor
Language: English
"""
            ),

            'researchbot': Character(
                name='ResearchBot',
                description='Academic research assistant',
                personality=Personality(
                    friendliness=0.6,
                    formality=0.9,
                    humor=0.1,
                    expertise='academic',
                    empathy=0.4,
                    proactivity=0.6
                ),
                voice_profile=VoiceProfile(
                    language='en',
                    speed=0.9,
                    pitch=2.0,
                    emotion='neutral'
                ),
                system_prompt="""You are ResearchBot, an academic research assistant.

Your role:
- Help analyze data and find patterns
- Provide citations and references
- Suggest research methodologies
- Maintain scientific rigor

Tone: Academic, precise, thorough, cautious about claims
Language: English (primary), Turkish (secondary)
"""
            ),

            'bossbot': Character(
                name='BossBot',
                description='Executive decision support',
                personality=Personality(
                    friendliness=0.8,
                    formality=0.7,
                    humor=0.5,
                    expertise='professional',
                    empathy=0.7,
                    proactivity=0.9
                ),
                voice_profile=VoiceProfile(
                    language='tr',
                    speed=0.95,
                    pitch=-1.0,
                    emotion='confident'
                ),
                system_prompt="""You are BossBot, an executive decision support assistant.

Your role:
- Provide high-level summaries and insights
- Focus on strategic implications
- Synthesize information from multiple sources
- Be direct and decisive

Tone: Confident, strategic, executive-friendly, slightly informal
Language: Turkish (primary), English (secondary)
"""
            )
        }

    def get_character(self, name: str) -> Optional[Character]:
        if name in self.presets:
            return self.presets[name]
        return self.characters.get(name)

    def create_character(
        self,
        name: str,
        description: str,
        personality: Personality,
        voice_profile: VoiceProfile,
        system_prompt: str
    ) -> Character:

        character = Character(
            name=name,
            description=description,
            personality=personality,
            voice_profile=voice_profile,
            system_prompt=system_prompt
        )

        self.characters[name] = character
        logger.info(f"✅ Created custom character: {name}")

        return character

    def inject_personality(
        self,
        base_prompt: str,
        character: Character
    ) -> str:

        personality_guide = f"""

Personality Guidelines for {character.name}:
- Friendliness: {character.personality.friendliness*100}/100
- Formality: {character.personality.formality*100}/100
- Humor: {character.personality.humor*100}/100
- Expertise Level: {character.personality.expertise}
- Empathy: {character.personality.empathy*100}/100
- Proactivity: {character.personality.proactivity*100}/100

Voice Characteristics:
- Language: {character.voice_profile.language}
- Speed: {character.voice_profile.speed}x
- Emotion: {character.voice_profile.emotion}

Remember: {character.description}
"""

        return character.system_prompt + personality_guide + "\n\n" + base_prompt

    def list_characters(self) -> Dict[str, Dict[str, Any]]:

        all_chars = {**self.presets, **self.characters}

        return {
            name: {
                'name': char.name,
                'description': char.description,
                'personality': char.personality.__dict__,
                'voice_profile': char.voice_profile.__dict__,
                'is_preset': name in self.presets
            }
            for name, char in all_chars.items()
        }
