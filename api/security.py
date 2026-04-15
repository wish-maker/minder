"""
Security Utilities Module
Input validation, sanitization, and protection against common attacks
"""

from pydantic import validator
import re
import html
import logging
from typing import Any, Optional, List
from pathlib import Path

logger = logging.getLogger(__name__)


class InputSanitizer:
    """Input sanitization utilities for security"""

    # SQL injection patterns
    SQL_INJECTION_PATTERNS = [
        r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|UNION)\b)",
        r"(--|#|\/\*|\*\/)",  # SQL comments
        r"(\bor\b\s+\d+\s*=\s*\d+)",  # Bypass attempts
        r"(\band\b\s+\d+\s*=\s*\d+)",
        r"(\;|\')",  # Statement separators
        r"(\bxp_cmdshell\b|\bexec\b)",  # Command execution
        r"(\bwaitfor\b\s+delay\b)",  # Time-based evasion
    ]

    # XSS attack patterns
    XSS_PATTERNS = [
        r"<script[^>]*>.*?</script>",
        r"javascript:",
        r"on\w+\s*=",  # Event handlers (onclick, onerror, etc.)
        r"<iframe[^>]*>",
        r"<embed[^>]*>",
        r"<object[^>]*>",
        r"vbscript:",
        r"<![CDATA[.*?]]>",
    ]

    # Path traversal patterns
    PATH_TRAVERSAL_PATTERNS = [
        r"\.\./",
        r"\.\./",
        r"\.\.\\",
        r"%2e%2e",
        r"~",
        r"/etc/passwd",
        r"/proc/",
        r"\\windows\\system32",
    ]

    # Command injection patterns
    COMMAND_INJECTION_PATTERNS = [
        r";",
        r"\|",
        r"&",
        r"\$\(",
        r"`",
        r"\$\{",
        r"\n",
        r"\r",
    ]

    @classmethod
    def sanitize_string(
        cls, input_string: str, max_length: int = 10000
    ) -> str:
        """
        Comprehensive string sanitization

        Args:
            input_string: String to sanitize
            max_length: Maximum allowed length

        Returns:
            Sanitized string
        """
        if not input_string:
            return ""

        # Convert to string if not already
        if not isinstance(input_string, str):
            input_string = str(input_string)

        # Truncate if too long
        if len(input_string) > max_length:
            logger.warning(
                f"Input truncated from {len(input_string)} to {max_length} characters"
            )
            input_string = input_string[:max_length]

        # Remove null bytes
        input_string = input_string.replace("\x00", "")

        # HTML entity encoding (XSS protection)
        input_string = html.escape(input_string)

        return input_string

    @classmethod
    def check_sql_injection(cls, input_string: str) -> bool:
        """
        Check for SQL injection patterns

        Args:
            input_string: String to check

        Returns:
            True if injection detected, False otherwise
        """
        if not input_string:
            return False

        input_upper = input_string.upper()

        for pattern in cls.SQL_INJECTION_PATTERNS:
            if re.search(pattern, input_upper, re.IGNORECASE | re.MULTILINE):
                logger.warning(
                    f"SQL injection detected: {input_string[:100]}..."
                )
                return True

        return False

    @classmethod
    def check_xss(cls, input_string: str) -> bool:
        """
        Check for XSS attack patterns

        Args:
            input_string: String to check

        Returns:
            True if XSS detected, False otherwise
        """
        if not input_string:
            return False

        for pattern in cls.XSS_PATTERNS:
            if re.search(pattern, input_string, re.IGNORECASE | re.DOTALL):
                logger.warning(f"XSS attack detected: {input_string[:100]}...")
                return True

        return False

    @classmethod
    def check_path_traversal(cls, input_string: str) -> bool:
        """
        Check for path traversal attacks

        Args:
            input_string: String to check

        Returns:
            True if path traversal detected, False otherwise
        """
        if not input_string:
            return False

        for pattern in cls.PATH_TRAVERSAL_PATTERNS:
            if re.search(pattern, input_string, re.IGNORECASE):
                logger.warning(
                    f"Path traversal detected: {input_string[:100]}..."
                )
                return True

        return False

    @classmethod
    def check_command_injection(cls, input_string: str) -> bool:
        """
        Check for command injection patterns

        Args:
            input_string: String to check

        Returns:
            True if command injection detected, False otherwise
        """
        if not input_string:
            return False

        for pattern in cls.COMMAND_INJECTION_PATTERNS:
            if re.search(pattern, input_string):
                logger.warning(
                    f"Command injection detected: {input_string[:100]}..."
                )
                return True

        return False

    @classmethod
    def validate_file_path(
        cls, file_path: str, allowed_dirs: Optional[List[str]] = None
    ) -> bool:
        """
        Validate file path is safe and within allowed directories

        Args:
            file_path: Path to validate
            allowed_dirs: List of allowed base directories

        Returns:
            True if path is safe, False otherwise
        """
        try:
            # Resolve to absolute path
            resolved_path = Path(file_path).resolve()

            # Check for path traversal
            if cls.check_path_traversal(file_path):
                return False

            # Check against allowed directories
            if allowed_dirs:
                resolved_str = str(resolved_path)
                for allowed_dir in allowed_dirs:
                    allowed_path = Path(allowed_dir).resolve()
                    if resolved_str.startswith(str(allowed_path)):
                        return True
                return False

            return True

        except Exception as e:
            logger.error(f"Path validation error: {e}")
            return False

    @classmethod
    def sanitize_dict(cls, data: dict, max_length: int = 10000) -> dict:
        """
        Sanitize all string values in a dictionary

        Args:
            data: Dictionary to sanitize
            max_length: Maximum string length

        Returns:
            Sanitized dictionary
        """
        sanitized = {}

        for key, value in data.items():
            if isinstance(value, str):
                sanitized[key] = cls.sanitize_string(value, max_length)
            elif isinstance(value, dict):
                sanitized[key] = cls.sanitize_dict(value, max_length)
            elif isinstance(value, list):
                sanitized[key] = [
                    (
                        cls.sanitize_string(item, max_length)
                        if isinstance(item, str)
                        else item
                    )
                    for item in value
                ]
            else:
                sanitized[key] = value

        return sanitized

    @classmethod
    def validate_input(
        cls,
        input_value: Any,
        check_sql: bool = True,
        check_xss: bool = True,
        check_cmd: bool = True,
    ) -> tuple[bool, Optional[str]]:
        """
        Comprehensive input validation

        Args:
            input_value: Value to validate
            check_sql: Check for SQL injection
            check_xss: Check for XSS
            check_cmd: Check for command injection

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not input_value:
            return True, None

        # Convert to string for checking
        input_str = str(input_value)

        # Check SQL injection
        if check_sql and cls.check_sql_injection(input_str):
            return False, "Input contains potentially dangerous SQL patterns"

        # Check XSS
        if check_xss and cls.check_xss(input_str):
            return (
                False,
                "Input contains potentially dangerous script patterns",
            )

        # Check command injection
        if check_cmd and cls.check_command_injection(input_str):
            return (
                False,
                "Input contains potentially dangerous command patterns",
            )

        return True, None


# Pydantic validators


def add_security_validators(model_class):
    """
    Decorator to add security validators to Pydantic models

    Usage:
        @add_security_validators
        class MyModel(BaseModel):
            field_name: str
    """

    @validator("*", pre=True)
    def validate_all_fields(cls, v, field):
        """Validate all fields for security issues"""
        if v is None:
            return v

        # Skip non-string fields
        if not isinstance(v, str):
            return v

        # Check for security issues
        is_valid, error_msg = InputSanitizer.validate_input(v)
        if not is_valid:
            raise ValueError(error_msg)

        # Sanitize the input
        return InputSanitizer.sanitize_string(v)

    # Add validator to model
    model_class.__validators__["validate_security"] = validate_all_fields

    return model_class


def sanitize_form_input(data: dict) -> dict:
    """
    Sanitize form input data (for POST/PUT requests)

    Args:
        data: Form data dictionary

    Returns:
        Sanitized dictionary
    """
    return InputSanitizer.sanitize_dict(data)


def validate_json_input(
    data: dict, required_fields: Optional[List[str]] = None
) -> tuple[bool, Optional[str]]:
    """
    Validate JSON input data

    Args:
        data: JSON data dictionary
        required_fields: List of required field names

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(data, dict):
        return False, "Invalid JSON format"

    # Check required fields
    if required_fields:
        missing_fields = [
            field for field in required_fields if field not in data
        ]
        if missing_fields:
            return (
                False,
                f"Missing required fields: {', '.join(missing_fields)}",
            )

    # Validate all string fields
    for key, value in data.items():
        if isinstance(value, str):
            is_valid, error_msg = InputSanitizer.validate_input(value)
            if not is_valid:
                return False, f"Field '{key}': {error_msg}"

    return True, None
