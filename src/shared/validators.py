"""
Common input validators for Minder services.
Provides comprehensive validation functions for user inputs.
"""

import re
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field, HttpUrl, field_validator


class ValidationError(Exception):
    """Raised when input validation fails"""

    pass


def validate_plugin_name(name: str) -> str:
    """
    Validate plugin name.

    Args:
        name: Plugin name to validate

    Returns:
        Validated plugin name

    Raises:
        ValidationError: If name is invalid
    """
    if not name or not isinstance(name, str):
        raise ValidationError("Plugin name is required")

    if len(name) < 3 or len(name) > 50:
        raise ValidationError("Plugin name must be 3-50 characters")

    # Only alphanumeric, hyphens, and underscores
    if not re.match(r"^[a-zA-Z0-9_-]+$", name):
        raise ValidationError(
            "Plugin name can only contain letters, numbers, hyphens, and underscores"
        )

    return name


def validate_email(email: str) -> str:
    """
    Validate email address.

    Args:
        email: Email address to validate

    Returns:
        Validated email

    Raises:
        ValidationError: If email is invalid
    """
    if not email or not isinstance(email, str):
        raise ValidationError("Email is required")

    # Basic email validation
    if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
        raise ValidationError("Invalid email format")

    if len(email) > 254:
        raise ValidationError("Email is too long")

    return email


def validate_url(url: str, allow_local: bool = False) -> str:
    """
    Validate URL.

    Args:
        url: URL to validate
        allow_local: Whether to allow localhost URLs

    Returns:
        Validated URL

    Raises:
        ValidationError: If URL is invalid
    """
    if not url or not isinstance(url, str):
        raise ValidationError("URL is required")

    # Basic URL validation
    if not re.match(r"^https?://", url):
        raise ValidationError("URL must start with http:// or https://")

    if not allow_local and ("localhost" in url or "127.0.0.1" in url):
        raise ValidationError("Localhost URLs not allowed")

    if len(url) > 2048:
        raise ValidationError("URL is too long")

    return url


def validate_description(description: str, max_length: int = 1000) -> str:
    """
    Validate description text.

    Args:
        description: Description to validate
        max_length: Maximum allowed length

    Returns:
        Validated description

    Raises:
        ValidationError: If description is invalid
    """
    if description is None:
        return ""

    if not isinstance(description, str):
        raise ValidationError("Description must be a string")

    if len(description) > max_length:
        raise ValidationError(f"Description is too long (max {max_length} characters)")

    return description.strip()


def validate_plugin_version(version: str) -> str:
    """
    Validate plugin version (semantic versioning).

    Args:
        version: Version string to validate

    Returns:
        Validated version

    Raises:
        ValidationError: If version is invalid
    """
    if not version or not isinstance(version, str):
        raise ValidationError("Version is required")

    # Semantic versioning pattern: X.Y.Z where X, Y, Z are integers
    if not re.match(r"^\d+\.\d+\.\d+(?:-[a-zA-Z0-9.-]+)?$", version):
        raise ValidationError("Version must follow semantic versioning (e.g., 1.0.0)")

    return version


def validate_query_string(query: str, max_length: int = 100) -> str:
    """
    Validate search/query string.

    Args:
        query: Query string to validate
        max_length: Maximum allowed length

    Returns:
        Validated query string

    Raises:
        ValidationError: If query is invalid
    """
    if not query or not isinstance(query, str):
        raise ValidationError("Query is required")

    if len(query) > max_length:
        raise ValidationError(f"Query is too long (max {max_length} characters)")

    # Remove potentially dangerous characters
    sanitized = re.sub(r'[<>"\';]', "", query)

    if not sanitized:
        raise ValidationError("Query cannot be empty after sanitization")

    return sanitized.strip()


def validate_pagination(page: int, page_size: int, max_page_size: int = 100) -> tuple:
    """
    Validate pagination parameters.

    Args:
        page: Page number (1-based)
        page_size: Number of items per page
        max_page_size: Maximum allowed page size

    Returns:
        Tuple of (validated_page, validated_page_size)

    Raises:
        ValidationError: If pagination params are invalid
    """
    if not isinstance(page, int) or page < 1:
        raise ValidationError("Page number must be a positive integer")

    if not isinstance(page_size, int) or page_size < 1:
        raise ValidationError("Page size must be a positive integer")

    if page_size > max_page_size:
        raise ValidationError(f"Page size cannot exceed {max_page_size}")

    return page, page_size


def validate_sort_field(field: str, allowed_fields: List[str]) -> str:
    """
    Validate sort field.

    Args:
        field: Sort field to validate
        allowed_fields: List of allowed sort fields

    Returns:
        Validated sort field

    Raises:
        ValidationError: If sort field is invalid
    """
    if not field or not isinstance(field, str):
        raise ValidationError("Sort field is required")

    if field not in allowed_fields:
        raise ValidationError(f"Sort field must be one of: {', '.join(allowed_fields)}")

    return field


def validate_sort_order(order: str) -> str:
    """
    Validate sort order.

    Args:
        order: Sort order (asc or desc)

    Returns:
        Validated sort order

    Raises:
        ValidationError: If sort order is invalid
    """
    if not order or not isinstance(order, str):
        raise ValidationError("Sort order is required")

    order = order.lower()
    if order not in ("asc", "desc"):
        raise ValidationError("Sort order must be 'asc' or 'desc'")

    return order


# Pydantic models for common validations


class PaginationParams(BaseModel):
    """Pagination parameters"""

    page: int = Field(ge=1, default=1, description="Page number (1-based)")
    page_size: int = Field(ge=1, le=100, default=20, description="Items per page")


class SortParams(BaseModel):
    """Sort parameters"""

    sort_by: Optional[str] = Field(None, description="Field to sort by")
    sort_order: Optional[str] = Field("asc", description="Sort order (asc or desc)")

    @field_validator("sort_order")
    @classmethod
    def validate_sort_order(cls, v):
        if v and v.lower() not in ("asc", "desc"):
            raise ValueError('sort_order must be "asc" or "desc"')
        return v.lower() if v else "asc"


class SearchParams(BaseModel):
    """Search parameters"""

    query: str = Field(..., min_length=1, max_length=100, description="Search query")
    page: int = Field(ge=1, default=1)
    page_size: int = Field(ge=1, le=100, default=20)


class PluginValidationRequest(BaseModel):
    """Plugin validation request"""

    name: str = Field(..., min_length=3, max_length=50, description="Plugin name")
    version: str = Field(
        ..., pattern=r"^\d+\.\d+\.\d+(?:-[a-zA-Z0-9.-]+)?$", description="Plugin version"
    )
    description: Optional[str] = Field(None, max_length=1000, description="Plugin description")
    author_email: Optional[EmailStr] = Field(None, description="Author email")
    homepage_url: Optional[HttpUrl] = Field(None, description="Plugin homepage URL")

    @field_validator("name")
    @classmethod
    def validate_plugin_name(cls, v):
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError(
                "Plugin name can only contain letters, numbers, hyphens, and underscores"
            )
        return v


class ValidationErrorResponse(BaseModel):
    """Validation error response"""

    error: str = Field(..., description="Error message")
    field: Optional[str] = Field(None, description="Field that caused the error")
    code: str = Field(..., description="Error code")


# Common validation decorators
def validate_plugin_input(func):
    """Decorator to validate plugin-related input"""

    def wrapper(*args, **kwargs):
        # Add validation logic here
        return func(*args, **kwargs)

    return wrapper


def sanitize_user_input(input_str: str) -> str:
    """
    Sanitize user input to prevent XSS and injection attacks.

    Args:
        input_str: Input string to sanitize

    Returns:
        Sanitized string
    """
    if not input_str or not isinstance(input_str, str):
        return ""

    # Remove HTML tags
    sanitized = re.sub(r"<[^>]+>", "", input_str)

    # Remove potentially dangerous characters
    sanitized = re.sub(r'[<>"\';]', "", sanitized)

    # Remove excessive whitespace
    sanitized = " ".join(sanitized.split())

    return sanitized.strip()


def validate_json_schema(schema: dict) -> dict:
    """
    Validate JSON schema.

    Args:
        schema: JSON schema to validate

    Returns:
        Validated schema

    Raises:
        ValidationError: If schema is invalid
    """
    if not isinstance(schema, dict):
        raise ValidationError("Schema must be a dictionary")

    required_keys = ["type", "properties"]
    for key in required_keys:
        if key not in schema:
            raise ValidationError(f"Schema missing required key: {key}")

    return schema
