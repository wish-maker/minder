"""
Shared utilities package
Common utility functions and helpers for Minder services
"""

# Import utility modules
from .redis_client import (
    create_redis_client,
    create_redis_client_from_settings,
)

from .cors import (
    add_cors_middleware,
    add_cors_from_string,
)

from .service_urls import (
    ServiceURLs,
    get_service_url,
    get_endpoint,
)

from .validation import (
    sanitize_string,
    validate_identifier,
    validate_email,
    validate_url,
    validate_json,
    sanitize_filename,
    validate_port,
    validate_sql_identifier,
    SafeIdentifier,
    SafeEmail,
    SafeURL,
)

__all__ = [
    # Redis utilities
    "create_redis_client",
    "create_redis_client_from_settings",
    # CORS utilities
    "add_cors_middleware",
    "add_cors_from_string",
    # Service URL utilities
    "ServiceURLs",
    "get_service_url",
    "get_endpoint",
    # Validation utilities
    "sanitize_string",
    "validate_identifier",
    "validate_email",
    "validate_url",
    "validate_json",
    "sanitize_filename",
    "validate_port",
    "validate_sql_identifier",
    "SafeIdentifier",
    "SafeEmail",
    "SafeURL",
]
