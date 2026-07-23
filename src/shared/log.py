"""Shared logging setup — one place for the ``minder.<service>`` logger convention.

Replaces the identical ``logging.basicConfig(...)`` + ``getLogger("minder.<svc>")``
two-liner duplicated across service mains (issue #49). Behaviour-preserving: same
root level (from LOG_LEVEL / the passed value) and the same ``minder.<name>`` logger.

Named ``log`` (not ``logging``) so it never shadows the stdlib module.
"""

import logging
import os


def setup_logging(service_name: str, level: str = None) -> logging.Logger:
    """Configure root logging and return the service's ``minder.<name>`` logger.

    Args:
        service_name: short service name (e.g. "api-gateway") → ``minder.api-gateway``.
        level: explicit level name (e.g. settings.LOG_LEVEL). Defaults to the
            ``LOG_LEVEL`` env var, then INFO. Unknown names fall back to INFO.
    """
    level_name = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    logging.basicConfig(level=getattr(logging, level_name, logging.INFO))
    return logging.getLogger(f"minder.{service_name}")
