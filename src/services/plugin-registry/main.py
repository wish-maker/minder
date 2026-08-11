"""
Minder Plugin Registry Service
Manages plugin discovery, lifecycle, health monitoring, and service registration

Thin composition root: the actual work lives in the `core/` package
(state / database / plugin_loader / webhooks / marketplace_sync / monitoring) and
the `routes/` package. This module wires them together — lifespan orchestration,
shared request-metrics setup + a couple of domain metrics, service-level
endpoints, and router inclusion.
"""

import asyncio
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse

from config import settings

# Auth middleware + shared packages live under /app/src; plugin modules under
# /app/plugins. Insert before importing the routes package (which pulls in
# shared.auth) and before plugin discovery.
sys.path.insert(0, "/app/src")
sys.path.insert(0, "/app/plugins")

from core.database import (  # noqa: E402
    create_plugins_table_if_not_exists,
    get_postgres_connection,
    load_plugin_config,
    load_plugins_from_database,
    save_plugin_config,
    update_plugin_in_database,
)
from core.monitoring import (  # noqa: E402
    auto_enable_plugins,
    data_collection_scheduler,
    health_check_loop,
    load_services_from_redis,
)
from core.plugin_loader import load_plugins_from_disk  # noqa: E402
from core.state import (  # noqa: E402
    plugin_instances,
    plugin_manifests,
    plugins_db,
    redis_client,
    services_db,
    webhook_routes,
)
from core.webhooks import (  # noqa: E402
    handle_webhook_request,
    register_all_webhooks_on_startup,
    register_plugin_webhook,
)
from routes.ai_tools import build_ai_tools_router  # noqa: E402
from routes.bundles import build_bundles_router  # noqa: E402
from routes.containers import build_containers_router  # noqa: E402
from routes.plugins import build_plugins_router  # noqa: E402
from routes.proxy import ProxyRouter  # noqa: E402
from routes.services import build_services_router  # noqa: E402

from shared.auth.jwt_middleware import get_current_user  # noqa: E402
from shared.errors import install_global_exception_handler  # noqa: E402
from shared.health import DependencyCheck, evaluate_dependencies  # noqa: E402
from shared.log import setup_logging  # noqa: E402
from shared.metrics import setup_metrics  # noqa: E402

# Configure logging
logger = setup_logging("plugin-registry", level=settings.LOG_LEVEL)

# Proxy router for dynamic microservice routing (shares the services cache)
proxy_router = ProxyRouter(services_db)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB/Redis/plugins/webhooks on startup; tear them down on shutdown."""
    # ----- Startup -----
    logger.info("Plugin Registry starting...")
    logger.info(f"Plugins path: {settings.PLUGINS_PATH}")

    # Initialize PostgreSQL connection
    await get_postgres_connection()

    # Create plugins table if not exists (CRITICAL: prevents startup failures)
    await create_plugins_table_if_not_exists()

    # Load services from Redis into memory (CRITICAL: prevents service loss on restart)
    await load_services_from_redis()

    # Load plugins from database
    await load_plugins_from_database()

    # Load plugins from disk (sync with database)
    await load_plugins_from_disk()

    # Initialize execution engine
    from core.execution_engine import ExecutionEngine, set_execution_engine

    engine = ExecutionEngine()
    set_execution_engine(engine)
    logger.info("Execution engine initialized")

    # Register all webhook routes from disk (RESTART-SAFE)
    await register_all_webhooks_on_startup()
    logger.info(f"Webhook routes registered: {list(webhook_routes.keys())}")

    # Auto-enable all plugins on startup
    await auto_enable_plugins()

    # Start health check loop
    asyncio.create_task(health_check_loop())

    # Start automatic data collection scheduler
    asyncio.create_task(data_collection_scheduler())

    logger.info(
        f"✅ Startup: {len(plugins_db)} plugins, "
        f"{len(services_db)} services, {len(webhook_routes)} webhooks"
    )

    yield

    # ----- Shutdown -----
    logger.info("Plugin Registry shutting down...")

    # Close PostgreSQL connection
    from core.database import postgres_pool

    if postgres_pool:
        await postgres_pool.close()

    # Shutdown all plugin instances
    for plugin_name, plugin_instance in plugin_instances.items():
        try:
            await plugin_instance.shutdown()
        except Exception as e:
            logger.error(f"Error shutting down {plugin_name}: {e}")

    # Close proxy router HTTP client
    try:
        await proxy_router.close()
        logger.info("✅ Proxy router closed")
    except Exception as e:
        logger.error(f"Error closing proxy router: {e}")

    # Close execution engine
    try:
        from core.execution_engine import get_execution_engine

        engine = get_execution_engine()
        await engine.close()
        logger.info("✅ Execution engine closed")
    except Exception as e:
        logger.error(f"Error closing execution engine: {e}")

    redis_client.close()


app = FastAPI(
    title="Minder Plugin Registry",
    description="Plugin discovery and lifecycle management",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Prometheus metrics: request-tracking middleware + /metrics endpoint (shared.metrics).
# HTTP request metrics come from setup_metrics; no domain counters here — the two that
# used to be declared (plugins_total, health_check_failures_total) were never
# incremented anywhere, so they always read 0 (misleading). Removed (#49).
setup_metrics(app)

install_global_exception_handler(
    app, logger, is_development=settings.ENVIRONMENT == "development"
)

# ============================================================================
# Routers — service discovery / dynamic proxy + AI-tool aggregation
# (included before the service-level endpoints below to preserve route order)
# ============================================================================

app.include_router(
    build_services_router(
        services_db=services_db,
        redis_client=redis_client,
        proxy_router=proxy_router,
        logger=logger,
    )
)

app.include_router(
    build_ai_tools_router(
        plugins_db=plugins_db,
        plugin_instances=plugin_instances,
        logger=logger,
    )
)

app.include_router(build_bundles_router(settings=settings, logger=logger))
app.include_router(build_containers_router(settings=settings))


# ============================================================================
# API Endpoints — service level (health / metrics / webhook maintenance)
# ============================================================================


@app.get("/health")
async def health_check():
    """Health check — 503 when Postgres or Redis (both required) is unreachable."""

    async def _postgres():
        pool = await get_postgres_connection()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")

    def _redis():
        # redis_client is a sync client; ping() is a brief blocking call.
        redis_client.ping()

    status, code, checks = await evaluate_dependencies(
        [
            DependencyCheck("postgres", _postgres, critical=True),
            DependencyCheck("redis", _redis, critical=True),
        ]
    )
    return JSONResponse(
        status_code=code,
        content={
            "service": "plugin-registry",
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": app.version,
            "environment": settings.ENVIRONMENT,
            "plugins_loaded": len(plugins_db),
            "services_registered": len(services_db),
            "checks": checks,
        },
    )


@app.post("/v1/force-webhooks", tags=["Webhooks"])
@app.post("/force-webhooks", include_in_schema=False)  # deprecated unversioned alias
async def force_webhooks(current_user: dict = Depends(get_current_user)):
    """
    Force webhook re-registration from persisted manifests (PostgreSQL, #269).

    Manual trigger for the same restore-on-startup path register_all_webhooks_on_startup
    runs at boot -- was previously a "/tmp/*-manifest.yml" restart-safety workaround.

    JWT-gated like every other mutation in this service; the unversioned
    ``/force-webhooks`` path is kept as a hidden deprecated alias.
    """
    await register_all_webhooks_on_startup()
    return {
        "message": f"Registered {len(webhook_routes)} webhook(s)",
        "webhooks": list(webhook_routes.keys()),
    }


# Plugin CRUD/lifecycle endpoints (routes/plugins.py). Included last so the
# main-owned helpers it injects (update_plugin_in_database, register_plugin_webhook,
# handle_webhook_request) are already imported, and so route order matches history.
app.include_router(
    build_plugins_router(
        plugins_db=plugins_db,
        plugin_instances=plugin_instances,
        plugin_manifests=plugin_manifests,
        webhook_routes=webhook_routes,
        redis_client=redis_client,
        update_plugin_in_database=update_plugin_in_database,
        load_plugin_config=load_plugin_config,
        save_plugin_config=save_plugin_config,
        register_plugin_webhook=register_plugin_webhook,
        handle_webhook_request=handle_webhook_request,
        logger=logger,
    )
)


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)  # nosec B104
