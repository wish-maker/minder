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
import glob
import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime

import yaml
from fastapi import FastAPI
from prometheus_client import Counter, Gauge

from config import settings

# Auth middleware + shared packages live under /app/src; plugin modules under
# /app/plugins. Insert before importing the routes package (which pulls in
# shared.auth) and before plugin discovery.
sys.path.insert(0, "/app/src")
sys.path.insert(0, "/app/plugins")

from core.database import (  # noqa: E402
    create_plugins_table_if_not_exists,
    get_postgres_connection,
    load_plugins_from_database,
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
from routes.plugins import build_plugins_router  # noqa: E402
from routes.proxy import ProxyRouter  # noqa: E402
from routes.services import build_services_router  # noqa: E402

from shared.metrics import setup_metrics  # noqa: E402

# Configure logging
logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL))
logger = logging.getLogger("minder.plugin-registry")

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
    sys.path.insert(0, "/app/services/plugin-registry")
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
        sys.path.insert(0, "/app/services/plugin-registry")
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

# Prometheus metrics: request-tracking middleware + /metrics endpoint
setup_metrics(app)

# ============================================================================
# Prometheus Metrics (domain-specific; HTTP request metrics from shared.metrics)
# ============================================================================

plugins_total = Gauge(
    "plugins_total", "Total number of plugins", ["status"]
)  # registered, enabled, disabled, error

health_check_failures_total = Counter(
    "health_check_failures_total", "Total health check failures", ["plugin"]
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


# ============================================================================
# API Endpoints — service level (health / metrics / webhook maintenance)
# ============================================================================


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "service": "plugin-registry",
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": app.version,
        "environment": settings.ENVIRONMENT,
        "plugins_loaded": len(plugins_db),
        "services_registered": len(services_db),
    }


@app.post("/force-webhooks")
async def force_webhooks():
    """
    Force webhook registration from /tmp manifest files.
    Workaround for MVP restart-safety issue.
    """
    count = 0
    for manifest_file in glob.glob("/tmp/*-manifest.yml"):
        try:
            with open(manifest_file, "r") as f:
                manifest = yaml.safe_load(f)
            plugin_name = manifest.get("metadata", {}).get("name")
            if plugin_name and plugin_name in plugins_db:
                plugin_manifests[plugin_name] = manifest
                await register_plugin_webhook(plugin_name, manifest)
                logger.info(f"Loaded manifest from {manifest_file} for {plugin_name}")
                count += 1
        except Exception as e:
            logger.warning(f"Failed to load manifest from {manifest_file}: {e}")

    return {
        "message": f"Registered {count} webhook(s)",
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
