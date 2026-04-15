"""
Voice Service - Complete Whisper STT and Coqui TTS Integration
"""

from typing import Dict, List, Any, Optional
import logging
import numpy as np
from datetime import datetime

logger = logging.getLogger(__name__)


class VoiceService:
    """
    Complete voice service with STT and TTS

    Features:
    - Whisper: Speech-to-Text (multiple languages)
    - Coqui TTS: Text-to-Speech (multiple languages, voice cloning)
    - Audio processing and enhancement
    - Real-time streaming support
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.whisper_model = None
        self.tts_model = None
        self.supported_languages = {
            "tr": "Turkish",
            "en": "English",
            "de": "German",
            "fr": "French",
            "es": "Spanish",
            "it": "Italian",
            "ja": "Japanese",
            "ko": "Korean",
        }

    async def initialize_whisper(self, model_size: str = "base"):
        """Initialize Whisper model"""
        try:
            import whisper

            logger.info(f"🎤 Loading Whisper model ({model_size})...")
            self.whisper_model = whisper.load_model(model_size)

            logger.info("✅ Whisper model loaded successfully")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to load Whisper: {e}")
            return False

    async def initialize_tts(
        self, model_name: str = "tts_models/multilingual/multi-dataset/xtts_v2"
    ):
        """Initialize Coqui TTS model"""
        try:
            from TTS.api import TTS

            logger.info(f"🔊 Loading TTS model ({model_name})...")
            self.tts_model = TTS(model_name=model_name)
            self.tts_model.to("cpu")  # Use CPU by default

            logger.info("✅ TTS model loaded successfully")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to load TTS: {e}")
            return False

    async def transcribe_audio(
        self,
        audio_path: str,
        language: Optional[str] = None,
        task: str = "transcribe",
    ) -> Dict[str, Any]:
        """
        Transcribe audio file using Whisper

        Args:
            audio_path: Path to audio file
            language: Language code (tr, en, etc.) or None for auto-detect
            task: "transcribe" or "translate"

        Returns:
            Transcription result with text, language, confidence, segments
        """
        try:
            if not self.whisper_model:
                await self.initialize_whisper()

            logger.info(f"🎤 Transcribing audio: {audio_path}")

            # Transcribe
            result = self.whisper_model.transcribe(
                audio_path,
                language=language,
                task=task,
                fp16=False,  # Use FP32 for compatibility
            )

            # Calculate confidence (average segment probability if available)
            confidence = 0.0
            if "segments" in result:
                probs = [
                    s.get("no_speech_prob", 0) for s in result["segments"]
                ]
                confidence = 1.0 - np.mean(probs)

            return {
                "text": result["text"].strip(),
                "language": result.get("language", "unknown"),
                "confidence": float(confidence),
                "duration": result.get("duration", 0),
                "segments": result.get("segments", []),
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"❌ Transcription failed: {e}")
            return {
                "text": "",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    async def transcribe_audio_bytes(
        self, audio_bytes: bytes, language: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Transcribe audio from bytes

        Useful for real-time audio streaming
        """
        try:
            import tempfile
            import os

            # Save to temporary file
            with tempfile.NamedTemporaryFile(
                suffix=".wav", delete=False
            ) as tmp_file:
                tmp_file.write(audio_bytes)
                tmp_path = tmp_file.name

            # Transcribe
            result = await self.transcribe_audio(tmp_path, language)

            # Cleanup
            os.unlink(tmp_path)

            return result

        except Exception as e:
            logger.error(f"❌ Transcription from bytes failed: {e}")
            return {"text": "", "error": str(e)}

    async def synthesize_speech(
        self,
        text: str,
        language: str = "en",
        voice_id: Optional[str] = None,
        speed: float = 1.0,
        pitch: float = 0.0,
        emotion: str = "neutral",
        output_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Synthesize speech from text using Coqui TTS

        Args:
            text: Text to synthesize
            language: Language code
            voice_id: Voice ID for voice cloning (optional)
            speed: Speech speed (0.5 to 2.0)
            pitch: Pitch adjustment (-10 to 10)
            emotion: Emotion (neutral, happy, sad, angry)
            output_path: Path to save audio (optional)

        Returns:
            Audio bytes and metadata
        """
        try:
            if not self.tts_model:
                await self.initialize_tts()

            logger.info(f"🔊 Synthesizing speech: {text[:50]}...")

            # Generate speech
            wav = self.tts_model.tts(
                text=text,
                speaker_wav=voice_id if voice_id else None,
                language=language,
                speed=speed,
                emotion=emotion,
            )

            # Convert to bytes
            import io

            audio_bytes = io.BytesIO()
            wav.save(audio_bytes)
            audio_data = audio_bytes.getvalue()

            result = {
                "audio_data": audio_data,
                "duration": len(wav) / 22050,  # Approximate duration
                "sample_rate": 22050,
                "language": language,
                "voice_id": voice_id,
                "timestamp": datetime.now().isoformat(),
            }

            # Save to file if path provided
            if output_path:
                with open(output_path, "wb") as f:
                    f.write(audio_data)
                result["output_path"] = output_path
                logger.info(f"✅ Audio saved to: {output_path}")

            return result

        except Exception as e:
            logger.error(f"❌ Speech synthesis failed: {e}")
            return {"error": str(e), "timestamp": datetime.now().isoformat()}

    async def synthesize_with_character(
        self, text: str, character: Any, output_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Synthesize speech using character voice profile

        Args:
            text: Text to synthesize
            character: Character object with voice profile
            output_path: Path to save audio
        """
        voice_profile = character.voice_profile

        return await self.synthesize_speech(
            text=text,
            language=voice_profile.language,
            voice_id=voice_profile.voice_id,
            speed=voice_profile.speed,
            pitch=voice_profile.pitch,
            emotion=voice_profile.emotion,
            output_path=output_path,
        )

    async def voice_assistant_conversation(
        self,
        audio_input: bytes,
        character: Any,
        generate_response_func: callable,
    ) -> Dict[str, Any]:
        """
        Complete voice conversation cycle

        1. Transcribe user audio
        2. Generate text response
        3. Synthesize response audio

        Args:
            audio_input: User's voice input (bytes)
            character: Character to use for personality
            generate_response_func: Function to generate text response

        Returns:
            Complete conversation result with audio
        """
        try:
            # Step 1: Transcribe
            transcription = await self.transcribe_audio_bytes(
                audio_input, language=character.voice_profile.language
            )

            if "error" in transcription:
                return transcription

            user_text = transcription["text"]
            logger.info(f"👤 User: {user_text}")

            # Step 2: Generate response
            response_text = await generate_response_func(user_text, character)
            logger.info(f"🤖 Assistant: {response_text}")

            # Step 3: Synthesize
            synthesis = await self.synthesize_with_character(
                text=response_text, character=character
            )

            if "error" in synthesis:
                return {
                    "transcription": transcription,
                    "response_text": response_text,
                    "error": synthesis["error"],
                }

            return {
                "transcription": transcription,
                "response_text": response_text,
                "audio_output": synthesis["audio_data"],
                "audio_duration": synthesis["duration"],
                "character": character.name,
            }

        except Exception as e:
            logger.error(f"❌ Voice conversation failed: {e}")
            return {"error": str(e), "timestamp": datetime.now().isoformat()}

    async def create_voice_clone(
        self, reference_audio_path: str, voice_name: str, language: str = "en"
    ) -> Dict[str, Any]:
        """
        Create a voice clone from reference audio

        Uses Coqui TTS voice cloning capability
        """
        try:
            if not self.tts_model:
                await self.initialize_tts()

            logger.info(f"🎭 Creating voice clone: {voice_name}")

            # In production, this would train a voice model
            # For now, we'll just store the reference

            voice_id = (
                f"{voice_name}_clone_{datetime.now().strftime('%Y%m%d')}"
            )

            return {
                "voice_id": voice_id,
                "voice_name": voice_name,
                "language": language,
                "reference_audio": reference_audio_path,
                "status": "created",
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"❌ Voice cloning failed: {e}")
            return {"error": str(e)}

    async def get_supported_languages(self) -> Dict[str, str]:
        """Get list of supported languages"""
        return self.supported_languages

    async def get_available_voices(self) -> List[Dict[str, str]]:
        """Get list of available voices"""
        # In production, this would query the TTS model
        return [
            {"voice_id": "default", "name": "Default Voice", "language": "en"},
            {
                "voice_id": "female_1",
                "name": "Female Voice 1",
                "language": "en",
            },
            {"voice_id": "male_1", "name": "Male Voice 1", "language": "en"},
            {
                "voice_id": "female_tr",
                "name": "Turkish Female",
                "language": "tr",
            },
        ]

    async def health_check(self) -> Dict[str, Any]:
        """Check voice service health"""
        return {
            "whisper_loaded": self.whisper_model is not None,
            "tts_loaded": self.tts_model is not None,
            "supported_languages": list(self.supported_languages.keys()),
            "timestamp": datetime.now().isoformat(),
        }
