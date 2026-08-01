"""Map caught backend exceptions to sanitized HTTP errors.

A backend being unreachable (Neo4j/Postgres/Redis/Qdrant down, an HTTP dependency
refusing the connection, DNS failing) is an *operational* condition, not a bug in
the service that caught it. Such failures should surface as **503** with a clear
"a backend is unreachable, retry" message — never as a 500, and never leaking the
driver's raw exception string to the caller. Everything else becomes a generic,
sanitized **500** (the real cause is logged by the caller, not returned).

Usage — keep the caller's own context log, then hand the exception here:

    except Exception as e:
        logger.error(f"Failed to construct graph for {doc_id}: {e}")
        raise backend_http_error(e, "Knowledge graph construction")
"""

from fastapi import HTTPException

# Substrings that mark a connectivity / backend-unreachable failure. We match on the
# exception's module+class name plus its message rather than importing every driver's
# exception types — that keeps `shared` free of the heavy/optional client deps
# (neo4j, qdrant, asyncpg, redis, httpx) and still catches them all.
_CONNECTIVITY_MARKERS = (
    "serviceunavailable",  # neo4j.exceptions.ServiceUnavailable
    "connecterror",  # httpx.ConnectError
    "connecttimeout",  # httpx.ConnectTimeout
    "connectionerror",  # builtin / redis.ConnectionError
    "connectionrefused",  # builtin ConnectionRefusedError
    "connectionreset",  # builtin ConnectionResetError
    "connection refused",
    "connection reset",
    "cannot connect",
    "timed out",
    "timeout",
    "no route to host",
    "network is unreachable",
    "name or service not known",
    "temporary failure in name resolution",
    "pool is closed",
    "server closed the connection",
)


def is_connectivity_error(exc: BaseException) -> bool:
    """True if `exc` looks like a backend being unreachable (vs a genuine bug)."""
    haystack = f"{type(exc).__module__}.{type(exc).__name__} {exc}".lower()
    return any(marker in haystack for marker in _CONNECTIVITY_MARKERS)


def backend_http_error(exc: BaseException, operation: str) -> HTTPException:
    """Turn a caught backend exception into a sanitized HTTPException.

    - Connectivity failure  → 503 "<operation> failed: a required backend is
      unreachable. Retry once it is healthy." (retryable, no internal detail).
    - Anything else         → 500 "<operation> failed. See the service logs for
      details." (generic; the raw `str(exc)` is never returned to the caller).

    `operation` is a short human label for what was being attempted, e.g.
    "Knowledge graph construction", "Tool execution", "Text-to-speech".
    """
    if is_connectivity_error(exc):
        return HTTPException(
            status_code=503,
            detail=f"{operation} failed: a required backend is unreachable. "
            "Retry once it is healthy.",
        )
    return HTTPException(
        status_code=500,
        detail=f"{operation} failed. See the service logs for details.",
    )
