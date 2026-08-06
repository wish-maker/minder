"""
CORS configuration utility - Standardized CORS setup across services
"""

from typing import List, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def add_cors_middleware(
    app: FastAPI,
    allowed_origins: Optional[List[str]] = None,
    allow_credentials: bool = True,
    allow_methods: Optional[List[str]] = None,
    allow_headers: Optional[List[str]] = None,
) -> None:
    """
    Add CORS middleware to FastAPI app with standard configuration

    Args:
        app: FastAPI application instance
        allowed_origins: List of allowed origins (default: localhost development ports)
        allow_credentials: Allow cookies/authentication (default: True)
        allow_methods: HTTP methods to allow (default: all)
        allow_headers: HTTP headers to allow (default: all)

    Example:
        >>> add_cors_middleware(app, allowed_origins=["http://localhost:3000"])
    """
    if allowed_origins is None:
        # Default development origins
        allowed_origins = [
            "http://localhost:3000",
            "http://localhost:3001",
            "http://localhost:3002",
            "http://localhost:8000",
            "http://localhost:8001",
            "http://localhost:8002",
            "http://localhost:8080",
        ]

    if allow_methods is None:
        allow_methods = ["*"]

    if allow_headers is None:
        allow_headers = ["*"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=allow_credentials,
        allow_methods=allow_methods,
        allow_headers=allow_headers,
    )


def add_cors_from_string(
    app: FastAPI,
    cors_origins_str: Optional[str],
    default_origins: Optional[List[str]] = None,
) -> None:
    """
    Add CORS middleware from a comma-separated string of origins, falling back to
    ``default_origins`` (or ``add_cors_middleware``'s own dev-origins default) when
    ``cors_origins_str`` is unset/empty.

    Args:
        app: FastAPI application instance
        cors_origins_str: Comma-separated list of origins, or None/empty for the fallback
        default_origins: Origins to use when cors_origins_str is unset/empty
            (default: add_cors_middleware's built-in dev-origins list)

    Example:
        >>> add_cors_from_string(app, settings.CORS_ALLOWED_ORIGINS, default_origins=["*"])
    """
    allowed_origins: Optional[List[str]]
    if cors_origins_str:
        allowed_origins = [origin.strip() for origin in cors_origins_str.split(",")]
    else:
        allowed_origins = default_origins
    add_cors_middleware(app, allowed_origins=allowed_origins)
