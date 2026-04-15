"""
Pydantic models for API requests and responses
"""

from pydantic import BaseModel, field_validator
from typing import Dict, List, Any, Optional
from .security import InputSanitizer


class ChatRequest(BaseModel):
    """Chat request model"""

    message: str
    character: Optional[str] = None
    voice_mode: bool = False

    @field_validator("message")
    @classmethod
    def validate_message(cls, v):
        """Validate and sanitize chat message"""
        # Check for security issues
        is_valid, error_msg = InputSanitizer.validate_input(v)
        if not is_valid:
            raise ValueError(error_msg)

        # Sanitize input
        return InputSanitizer.sanitize_string(v, max_length=5000)

    @field_validator("character")
    @classmethod
    def validate_character(cls, v):
        """Validate character name"""
        if v is None:
            return v

        # Check for security issues
        is_valid, error_msg = InputSanitizer.validate_input(
            v, check_sql=False, check_xss=False
        )
        if not is_valid:
            raise ValueError(error_msg)

        # Sanitize input
        return InputSanitizer.sanitize_string(v, max_length=50)


class PipelineRequest(BaseModel):
    """Pipeline execution request model"""

    module: str
    pipeline: Optional[List[str]] = None

    @field_validator("module")
    @classmethod
    def validate_module(cls, v):
        """Validate module name"""
        # Check for security issues
        is_valid, error_msg = InputSanitizer.validate_input(
            v, check_sql=False, check_xss=False
        )
        if not is_valid:
            raise ValueError(error_msg)

        # Sanitize input
        return InputSanitizer.sanitize_string(v, max_length=100)

    @field_validator("pipeline")
    @classmethod
    def validate_pipeline(cls, v):
        """Validate pipeline steps"""
        if v is None:
            return v

        # Sanitize all pipeline steps
        sanitized = []
        for step in v:
            if step is None:
                continue
            # Check for security issues
            is_valid, error_msg = InputSanitizer.validate_input(
                step, check_sql=False, check_xss=False
            )
            if not is_valid:
                raise ValueError(error_msg)
            # Sanitize input
            sanitized.append(
                InputSanitizer.sanitize_string(step, max_length=100)
            )

        return sanitized


class CharacterCreateRequest(BaseModel):
    """Character creation request model"""

    name: str
    description: str
    personality: Dict[str, float]
    voice_profile: Dict[str, Any]
    system_prompt: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        """Validate character name"""
        is_valid, error_msg = InputSanitizer.validate_input(
            v, check_sql=False, check_xss=False
        )
        if not is_valid:
            raise ValueError(error_msg)

        return InputSanitizer.sanitize_string(v, max_length=100)

    @field_validator("description")
    @classmethod
    def validate_description(cls, v):
        """Validate character description"""
        is_valid, error_msg = InputSanitizer.validate_input(v)
        if not is_valid:
            raise ValueError(error_msg)

        return InputSanitizer.sanitize_string(v, max_length=1000)

    @field_validator("system_prompt")
    @classmethod
    def validate_system_prompt(cls, v):
        """Validate system prompt"""
        is_valid, error_msg = InputSanitizer.validate_input(v)
        if not is_valid:
            raise ValueError(error_msg)

        return InputSanitizer.sanitize_string(v, max_length=5000)
