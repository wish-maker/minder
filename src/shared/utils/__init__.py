"""
Shared utilities package
Common utility functions and helpers for Minder services

Submodules (redis_client, cors) are imported directly by consumers
(e.g. `from shared.utils.cors import add_cors_middleware`), not re-exported
here. Eagerly importing redis_client used to force every service that only
needs CORS to have the `redis` pip package installed, which broke
marketplace/plugin-state-manager once `redis` was correctly identified as an
unused direct dependency for them (#331) — those services don't call
create_redis_client at all, only add_cors_middleware.
"""
