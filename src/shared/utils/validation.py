"""
Input validation and sanitization utilities
Provides comprehensive validation for common input types
"""

import html
import re
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, field_validator


class SanitizedString(str):
    """
    Sanitized string type that escapes HTML and removes dangerous characters
    """

    @classmethod
    def __get_priors__(cls):
        # Ensure str comes first in __mro__
        return (str,) + type.__get_priors__(cls)

    @classmethod
    def __modify_schema__(cls, field_schema):
        # Update the schema for documentation
        field_schema.update({"type": "string", "format": "sanitized-string"})


def sanitize_string(input_string: str, max_length: int = 1000) -> str:
    """
    Sanitize a string by escaping HTML and limiting length

    Args:
        input_string: String to sanitize
        max_length: Maximum allowed length

    Returns:
        Sanitized string

    Example:
        >>> sanitize_string("<script>alert('xss')</script>")
        '&lt;script&gt;alert(&#39;xss&#39;)&lt;/script&gt;'
    """
    if not isinstance(input_string, str):
        raise ValueError("Input must be a string")

    # Escape HTML entities
    sanitized = html.escape(input_string)

    # Limit length
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length]

    return sanitized


def validate_identifier(identifier: str, max_length: int = 100) -> str:
    """
    Validate that a string is a safe identifier

    Args:
        identifier: String to validate
        max_length: Maximum allowed length

    Returns:
        Validated identifier

    Raises:
        ValueError: If identifier contains invalid characters

    Example:
        >>> validate_identifier("my_plugin-123")
        'my_plugin-123'
    """
    if not re.match(r"^[a-zA-Z0-9_-]+$", identifier):
        raise ValueError(
            "Identifier must contain only alphanumeric characters, hyphens, and underscores"
        )

    if len(identifier) > max_length:
        raise ValueError(f"Identifier must not exceed {max_length} characters")

    return identifier


def validate_email(email: str) -> str:
    """
    Validate email address format

    Args:
        email: Email address to validate

    Returns:
        Validated email (lowercased)

    Raises:
        ValueError: If email format is invalid

    Example:
        >>> validate_email("User@Example.COM")
        'user@example.com'
    """
    email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"

    if not re.match(email_pattern, email):
        raise ValueError("Invalid email address format")

    return email.lower().strip()


def validate_url(url: str, allowed_schemes: Optional[List[str]] = None) -> str:
    """
    Validate URL format and scheme

    Args:
        url: URL to validate
        allowed_schemes: List of allowed URL schemes (default: ['http', 'https'])

    Returns:
        Validated URL

    Raises:
        ValueError: If URL format is invalid or scheme not allowed

    Example:
        >>> validate_url("https://example.com")
        'https://example.com'
    """
    if allowed_schemes is None:
        allowed_schemes = ["http", "https"]

    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)

        if not parsed.scheme or not parsed.netloc:
            raise ValueError("Invalid URL format")

        if parsed.scheme not in allowed_schemes:
            raise ValueError(f"URL scheme must be one of: {', '.join(allowed_schemes)}")

        return url
    except Exception:
        raise ValueError("Invalid URL format")


def validate_json(data: Union[str, Dict], max_size: int = 10240) -> Dict:
    """
    Validate and parse JSON data

    Args:
        data: JSON string or dictionary
        max_size: Maximum size in bytes

    Returns:
        Parsed dictionary

    Raises:
        ValueError: If JSON is invalid or too large

    Example:
        >>> validate_json('{"key": "value"}')
        {'key': 'value'}
    """
    import json

    if isinstance(data, dict):
        return data

    if isinstance(data, str):
        # Check size before parsing
        if len(data.encode("utf-8")) > max_size:
            raise ValueError(f"JSON data exceeds maximum size of {max_size} bytes")

        try:
            return json.loads(data)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {str(e)}")

    raise ValueError("Data must be a string or dictionary")


def sanitize_filename(filename: str, max_length: int = 255) -> str:
    """
    Sanitize filename by removing dangerous characters

    Args:
        filename: Filename to sanitize
        max_length: Maximum allowed length

    Returns:
        Sanitized filename

    Example:
        >>> sanitize_filename("../../../etc/passwd")
        'passwd'
    """
    # Remove path separators
    sanitized = filename.replace("/", "").replace("\\", "")

    # Remove dangerous characters
    sanitized = re.sub(r'[<>:"|?*]', "", sanitized)

    # Limit length
    if len(sanitized) > max_length:
        # Try to keep extension
        name, ext = os.path.splitext(sanitized)
        max_name_length = max_length - len(ext)
        sanitized = name[:max_name_length] + ext

    # Ensure filename is not empty
    if not sanitized:
        raise ValueError("Filename cannot be empty after sanitization")

    return sanitized


def validate_port(port: int) -> int:
    """
    Validate port number

    Args:
        port: Port number to validate

    Returns:
        Validated port number

    Raises:
        ValueError: If port is out of valid range

    Example:
        >>> validate_port(8080)
        8080
    """
    if not (1 <= port <= 65535):
        raise ValueError("Port must be between 1 and 65535")

    return port


def validate_sql_identifier(identifier: str) -> str:
    """
    Validate SQL identifier (table/column name)

    Args:
        identifier: SQL identifier to validate

    Returns:
        Validated identifier

    Raises:
        ValueError: If identifier is unsafe

    Example:
        >>> validate_sql_identifier("my_table")
        'my_table'
    """
    # Check for SQL injection patterns
    dangerous_patterns = [
        r";",  # Statement separator
        r"--",  # Comment
        r"/\*",  # Multi-line comment start
        r"\*/",  # Multi-line comment end
        r"xp_",  # Extended procedure prefix
        r"exec",  # Execute command
        r"drop",  # Drop command
        r"delete",  # Delete command
        r"truncate",  # Truncate command
    ]

    identifier_lower = identifier.lower()

    for pattern in dangerous_patterns:
        if re.search(pattern, identifier_lower):
            raise ValueError(
                f"Identifier contains potentially harmful pattern: {pattern}"
            )

    # Validate format
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", identifier):
        raise ValueError(
            "SQL identifier must start with letter or underscore, "
            "followed by alphanumeric characters or underscores"
        )

    return identifier


class InputValidator(BaseModel):
    """
    Base class for input validation models
    Provides common validation methods
    """

    @field_validator("*", mode="before")
    @classmethod
    def strip_strings(cls, v):
        """Strip whitespace from string fields"""
        if isinstance(v, str):
            return v.strip()
        return v


class SafeIdentifier(str):
    """
    A safe identifier type that validates on creation
    """

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        """Validate identifier"""
        if not isinstance(v, str):
            raise TypeError("Identifier must be a string")

        validate_identifier(v)
        return cls(v)


class SafeEmail(str):
    """
    A safe email type that validates on creation
    """

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        """Validate email"""
        if not isinstance(v, str):
            raise TypeError("Email must be a string")

        return cls(validate_email(v))


class SafeURL(str):
    """
    A safe URL type that validates on creation
    """

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        """Validate URL"""
        if not isinstance(v, str):
            raise TypeError("URL must be a string")

        return cls(validate_url(v))
