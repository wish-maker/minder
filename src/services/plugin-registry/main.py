"""
Minder Plugin Registry Service
Manages plugin discovery, lifecycle, health monitoring, and service registration
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import redis
import yaml
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from pydantic import BaseModel

from config import settings

# Import authentication middleware
sys.path.insert(0, "/app/src")
sys.path.insert(0, "/app/plugins")  # Add plugins directory to path for direct imports
# Import proxy router for microservices
from routes.plugins import ProxyRouter  # noqa: E402
from routes.plugins_api import build_plugins_router  # noqa: E402

# Import AI tool validator
from shared.ai.tool_validator import validate_ai_tools  # noqa: E402
from shared.auth.jwt_middleware import (  # noqa: E402
    enforce_rate_limit,
    get_current_user,
)

# Configure logging
logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL))
logger = logging.getLogger("minder.plugin-registry")

# Initialize FastAPI app
app = FastAPI(
    title="Minder Plugin Registry",
    description="Plugin discovery and lifecycle management",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ============================================================================
# Prometheus Metrics
# ============================================================================

http_requests_total = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "endpoint", "status"]
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds", "HTTP request latency", ["method", "endpoint"]
)

plugins_total = Gauge(
    "plugins_total", "Total number of plugins", ["status"]
)  # registered, enabled, disabled, error

health_check_failures_total = Counter(
    "health_check_failures_total", "Total health check failures", ["plugin"]
)

# ============================================================================
# Data Models
# ============================================================================


from models import (  # noqa: E402
    PluginInfo,
    PluginInstallationRequest,
    ServiceRegistration,
)


# ============================================================================
# Infrastructure Clients
# ============================================================================

# Redis client for service discovery and caching
redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    password=settings.REDIS_PASSWORD,
    decode_responses=True,
    db=0,
)

# PostgreSQL client for plugin persistence
import asyncpg  # noqa: E402

postgres_pool = None


async def get_postgres_connection():
    """Get PostgreSQL connection from pool"""
    global postgres_pool
    if postgres_pool is None:
        postgres_pool = await asyncpg.create_pool(
            host=(
                settings.POSTGRES_HOST
                if hasattr(settings, "POSTGRES_HOST")
                else "minder-postgres"
            ),
            port=settings.POSTGRES_PORT if hasattr(settings, "POSTGRES_PORT") else 5432,
            user=(
                settings.POSTGRES_USER
                if hasattr(settings, "POSTGRES_USER")
                else "minder"
            ),
            password=(
                settings.POSTGRES_PASSWORD
                if hasattr(settings, "POSTGRES_PASSWORD")
                else "dev_password_change_me"
            ),
            database=(
                settings.POSTGRES_DB if hasattr(settings, "POSTGRES_DB") else "minder"
            ),
            min_size=2,
            max_size=10,
        )
    return postgres_pool


# ============================================================================
# Plugin Storage
# ============================================================================

plugins_db: Dict[str, PluginInfo] = {}  # In-memory cache
plugin_instances: Dict[str, any] = {}
services_db: Dict[str, ServiceRegistration] = {}

# ============================================================================
# Dynamic Proxy Router
# ============================================================================

# Initialize proxy router for microservices
proxy_router = ProxyRouter(services_db)

# Service-discovery + dynamic-proxy endpoints live in routes/services.py (deps injected).
from routes.services import build_services_router  # noqa: E402

app.include_router(
    build_services_router(
        services_db=services_db,
        redis_client=redis_client,
        proxy_router=proxy_router,
        logger=logger,
    )
)

# AI-tool aggregation + generic plugin analysis endpoints (deps injected).
from routes.ai_tools import build_ai_tools_router  # noqa: E402

app.include_router(
    build_ai_tools_router(
        plugins_db=plugins_db,
        plugin_instances=plugin_instances,
        logger=logger,
    )
)

# ============================================================================
# Plugin Loading
# ============================================================================


async def load_plugins_from_disk():
    """Load all plugins from PLUGINS_PATH"""
    plugins_path = Path(settings.PLUGINS_PATH)

    if not plugins_path.exists():
        logger.warning(f"Plugins path does not exist: {plugins_path}")
        return

    for plugin_dir in plugins_path.iterdir():
        if not plugin_dir.is_dir():
            continue

        # Look for plugin manifest (JSON or YAML) FIRST, then main module
        manifest_json = plugin_dir / "manifest.json"
        manifest_yml = plugin_dir / "manifest.yml"
        manifest_yaml = plugin_dir / "manifest.yaml"
        main_module = plugin_dir / "__init__.py"

        # Prefer manifest files over __init__.py
        if manifest_json.exists():
            await load_plugin_from_manifest(manifest_json, "json")
        elif manifest_yml.exists():
            await load_plugin_from_manifest(manifest_yml, "yaml")
        elif manifest_yaml.exists():
            await load_plugin_from_manifest(manifest_yaml, "yaml")
        elif main_module.exists():
            await load_plugin_from_module(plugin_dir)


async def load_plugin_from_manifest(manifest_path: Path, manifest_type: str = "json"):
    """Load plugin from manifest file (JSON or YAML)"""
    try:
        with open(manifest_path, "r") as f:
            if manifest_type == "json":
                manifest = json.load(f)
            else:  # yaml or yml
                manifest = yaml.safe_load(f)

        plugin_name = manifest.get("name")
        if not plugin_name:
            logger.error(f"Manifest missing 'name' field: {manifest_path}")
            return

        # Extract dependencies if present (handle both list and dict formats)
        dependencies_data = manifest.get("dependencies", {})
        if isinstance(dependencies_data, dict):
            dependencies_list = dependencies_data.get("python", [])
        else:
            dependencies_list = (
                dependencies_data if isinstance(dependencies_data, list) else []
            )

        # TODO: Load plugin module and call register()
        # For now, just store metadata
        plugin_info = PluginInfo(
            name=plugin_name,
            version=manifest.get("version", "1.0.0"),
            description=manifest.get("description", ""),
            author=manifest.get("author", ""),
            status="registered",
            dependencies=dependencies_list,
            capabilities=manifest.get("capabilities", []),
            data_sources=manifest.get("data_sources", []),
            databases=manifest.get("databases", []),
            registered_at=datetime.now().isoformat(),
        )

        plugins_db[plugin_name] = plugin_info
        logger.info(f"Loaded plugin: {plugin_name} (version {plugin_info.version})")

        # Persist to database
        await update_plugin_in_database(
            plugin_name,
            version=plugin_info.version,
            description=plugin_info.description,
            author=plugin_info.author,
            dependencies=(
                json.dumps(plugin_info.dependencies)
                if plugin_info.dependencies
                else None
            ),
            capabilities=(
                json.dumps(plugin_info.capabilities)
                if plugin_info.capabilities
                else None
            ),
            data_sources=(
                json.dumps(plugin_info.data_sources)
                if plugin_info.data_sources
                else None
            ),
            databases=(
                json.dumps(plugin_info.databases) if plugin_info.databases else None
            ),
        )

        # Auto-sync AI tools with marketplace
        await sync_plugin_ai_tools(plugin_name, manifest_path.parent)

    except Exception as e:
        logger.error(f"Failed to load plugin from {manifest_path}: {e}")


async def load_plugin_from_module(plugin_dir: Path):
    """Load plugin from Python module directory"""
    plugin_name = plugin_dir.name

    try:
        # Import plugin module using importlib
        import importlib

        # Build module path: plugins.{plugin_name}
        # (/app/src is in sys.path, so we import from plugins subdir)
        module_path = f"plugins.{plugin_name}"

        module = importlib.import_module(module_path)

        # Look for Plugin class in __all__ or module attributes
        plugin_class = None
        if hasattr(module, "__all__"):
            for attr_name in module.__all__:
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and hasattr(attr, "__bases__"):
                    plugin_class = attr
                    break

        if not plugin_class:
            # Fallback: search for BaseModule subclass
            from src.core.interface import BaseModule

            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, BaseModule)
                    and attr != BaseModule
                ):
                    plugin_class = attr
                    break

        if plugin_class:
            # Create plugin configuration with proper database host
            plugin_config = {
                "database": {
                    "host": "minder-postgres",
                    "port": 5432,
                    "user": "minder",
                    "password": os.environ.get(
                        "POSTGRES_PASSWORD", "dev_password_change_me"
                    ),
                    "database": "minder",
                },
                "redis": {
                    "host": "minder-redis",
                    "port": 6379,
                    "password": os.environ.get(
                        "REDIS_PASSWORD", "dev_password_change_me"
                    ),
                    "db": 0,
                },
                "influxdb": {
                    "enabled": True,
                    "host": "minder-influxdb",
                    "port": 8086,
                    "token": os.environ.get(
                        "INFLUXDB_TOKEN",
                        "minder-super-secret-token-change-me-in-production",
                    ),
                    "org": "minder",
                    "bucket": "minder-metrics",
                },
            }

            # Instantiate and register plugin
            plugin_instance = plugin_class(plugin_config)
            metadata = await plugin_instance.register()

            # Initialize plugin to set status to READY
            await plugin_instance.initialize()

            plugin_info = PluginInfo(
                name=metadata.name,
                version=metadata.version,
                description=metadata.description,
                author=metadata.author,
                status="registered",  # Will be updated by health check
                dependencies=metadata.dependencies,
                capabilities=metadata.capabilities,
                data_sources=metadata.data_sources,
                databases=metadata.databases,
                registered_at=metadata.registered_at.isoformat(),
            )

            plugins_db[plugin_name] = plugin_info
            plugin_instances[plugin_name] = plugin_instance

            logger.info(
                f"Loaded and registered plugin: {plugin_name} (version {plugin_info.version})"
            )

            # Persist to database
            await update_plugin_in_database(
                plugin_name,
                version=plugin_info.version,
                description=plugin_info.description,
                author=plugin_info.author,
                dependencies=(
                    json.dumps(plugin_info.dependencies)
                    if plugin_info.dependencies
                    else None
                ),
                capabilities=(
                    json.dumps(plugin_info.capabilities)
                    if plugin_info.capabilities
                    else None
                ),
                data_sources=(
                    json.dumps(plugin_info.data_sources)
                    if plugin_info.data_sources
                    else None
                ),
                databases=(
                    json.dumps(plugin_info.databases) if plugin_info.databases else None
                ),
            )

            # Auto-sync AI tools with marketplace
            await sync_plugin_ai_tools(plugin_name, plugin_dir)

    except Exception as e:
        logger.error(f"Failed to load plugin from {plugin_dir}: {e}")


# ============================================================================
# Webhook Route Management (MVP)
# ============================================================================

# Store webhook routes: {path: plugin_name}
webhook_routes: Dict[str, str] = {}
# Store loaded manifests: {plugin_name: manifest}
plugin_manifests: Dict[str, Dict] = {}


async def register_plugin_webhook(plugin_name: str, manifest: Dict):
    """
    Register webhook route for plugin.

    Args:
        plugin_name: Plugin name
        manifest: Plugin manifest

    SECURITY: Webhook routes are fixed paths from manifest.
    NO dynamic code execution.
    """
    trigger = manifest.get("spec", {}).get("trigger", {})
    if trigger.get("type") != "webhook":
        return

    webhook_config = trigger.get("webhook", {})
    webhook_path = webhook_config.get("path")

    if not webhook_path:
        logger.warning(f"Plugin {plugin_name} has no webhook path")
        return

    # Store route mapping (prefix with /webhook/ for endpoint matching)
    full_webhook_path = f"/webhook{webhook_path}"
    webhook_routes[full_webhook_path] = plugin_name
    plugin_manifests[plugin_name] = manifest

    logger.info(f"Registered webhook route: {full_webhook_path} -> {plugin_name}")


async def handle_webhook_request(webhook_path: str, request: Request) -> Dict:
    """
    Handle incoming webhook request.

    Args:
        webhook_path: Webhook path
        request: FastAPI request

    Returns:
        Response from execution engine
    """
    # Find plugin for this webhook
    plugin_name = webhook_routes.get(webhook_path)

    if not plugin_name:
        raise HTTPException(
            status_code=404, detail=f"No webhook registered at {webhook_path}"
        )

    # Get manifest
    manifest = plugin_manifests.get(plugin_name)

    if not manifest:
        raise HTTPException(
            status_code=500, detail=f"Plugin {plugin_name} manifest not loaded"
        )

    # Get webhook data
    try:
        if request.headers.get("content-type", "").startswith("application/json"):
            webhook_data = await request.json()
        else:
            # Form data
            form_data = await request.form()
            webhook_data = dict(form_data)
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Failed to parse webhook data: {e}"
        )

    # Validate secret if configured
    webhook_config = manifest.get("spec", {}).get("trigger", {}).get("webhook", {})
    secret_ref = webhook_config.get("secretRef")

    if secret_ref:
        # TODO: Validate against secrets store
        pass

    # Execute using execution engine
    import sys

    sys.path.insert(0, "/app/services/plugin-registry")
    from core.execution_engine import get_execution_engine

    engine = get_execution_engine()

    result = await engine.execute_webhook_trigger(manifest, webhook_data)

    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("error"))

    return {
        "message": "Webhook processed successfully",
        "plugin": plugin_name,
        "result": result.get("result", {}),
    }


async def register_all_webhooks_on_startup():
    """
    Register all webhook routes on startup.

    Called during startup to restore webhook routes from database.
    Ensures restart-safety.

    MVP: Loads from in-memory plugin_manifests populated by install endpoint.
    TODO: Load from PostgreSQL and restore all manifests.
    """
    # Clear existing routes
    webhook_routes.clear()

    # MVP: For now, just register webhooks from already-loaded manifests
    # In production, would load all manifests from PostgreSQL here
    for plugin_name, manifest in list(plugin_manifests.items()):
        await register_plugin_webhook(plugin_name, manifest)

    # TEMP: Load manifests from /tmp for testing (MVP restart-safety workaround)
    import glob

    import yaml

    manifest_files = glob.glob("/tmp/*-manifest.yml")
    logger.info(f"DEBUG: Found {len(manifest_files)} manifest files in /tmp")
    logger.info(
        f"DEBUG: plugins_db has {len(plugins_db)} plugins: {list(plugins_db.keys())}"
    )

    for manifest_file in manifest_files:
        try:
            logger.info(f"DEBUG: Loading manifest from {manifest_file}")
            with open(manifest_file, "r") as f:
                manifest = yaml.safe_load(f)
            plugin_name = manifest.get("metadata", {}).get("name")
            logger.info(
                f"DEBUG: Plugin name: {plugin_name}, in plugins_db: {plugin_name in plugins_db}"
            )
            if plugin_name and plugin_name in plugins_db:
                plugin_manifests[plugin_name] = manifest
                await register_plugin_webhook(plugin_name, manifest)
                logger.info(f"Loaded manifest from {manifest_file} for {plugin_name}")
        except Exception as e:
            logger.warning(f"Failed to load manifest from {manifest_file}: {e}")

    logger.info(f"Restored {len(webhook_routes)} webhook routes on startup")


# ============================================================================
# Health Monitoring
# ============================================================================


async def health_check_loop():
    """Background task to monitor plugin health"""
    while True:
        for plugin_name, plugin_instance in plugin_instances.items():
            try:
                health = await plugin_instance.health_check()
                plugin_info = plugins_db.get(plugin_name)

                if plugin_info:
                    plugin_info.health_status = (
                        "healthy" if health.get("healthy") else "unhealthy"
                    )
                    last_check_dt = datetime.now()
                    plugin_info.last_health_check = last_check_dt.isoformat()

                    # Update in Redis for service discovery
                    redis_client.hset(
                        f"plugin:{plugin_name}",
                        mapping={
                            "health_status": plugin_info.health_status,
                            "last_health_check": plugin_info.last_health_check,
                        },
                    )

                    # Update in PostgreSQL for persistence (pass datetime object, not string)
                    await update_plugin_in_database(
                        plugin_name,
                        health_status=plugin_info.health_status,
                        last_health_check=last_check_dt,
                    )

            except Exception as e:
                logger.error(f"Health check failed for {plugin_name}: {e}")
                if plugin_name in plugins_db:
                    plugins_db[plugin_name].health_status = "error"

        await asyncio.sleep(settings.HEALTH_CHECK_INTERVAL_SECONDS)


# ============================================================================
# API Endpoints - Health
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
    import glob

    import yaml

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


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ============================================================================
# Request Tracking Middleware
# ============================================================================


@app.middleware("http")
async def track_requests(request, call_next):
    """Track HTTP requests for metrics"""
    import time

    start_time = time.time()
    endpoint = request.url.path
    method = request.method

    response = await call_next(request)

    # Update metrics
    duration = time.time() - start_time
    http_requests_total.labels(
        method=method, endpoint=endpoint, status=response.status_code
    ).inc()
    http_request_duration_seconds.labels(method=method, endpoint=endpoint).observe(
        duration
    )

    return response


# ============================================================================
# Startup/Shutdown Events
# ============================================================================


@app.on_event("startup")
async def startup_event():
    """Initialize on startup"""
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
    import sys

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


async def auto_enable_plugins():
    """Automatically enable all plugins on startup"""
    logger.info("Auto-enabling all plugins...")

    for plugin_name, plugin_info in plugins_db.items():
        try:
            # Update in-memory status
            plugin_info.enabled = True
            plugin_info.status = "enabled"

            # Update in database
            await update_plugin_in_database(plugin_name, enabled=True, status="enabled")

            logger.info(f"✅ Auto-enabled plugin: {plugin_name}")
        except Exception as e:
            logger.error(f"❌ Failed to auto-enable {plugin_name}: {e}")


async def data_collection_scheduler():
    """Automatically trigger data collection for all enabled plugins every hour"""
    while True:
        try:
            # Wait 1 hour (3600 seconds)
            await asyncio.sleep(3600)

            logger.info("🔄 Scheduled data collection starting...")

            # Collect data from all enabled plugins
            for plugin_name, plugin_info in plugins_db.items():
                if plugin_info.enabled and plugin_name in plugin_instances:
                    try:
                        plugin_instance = plugin_instances[plugin_name]

                        # Trigger data collection
                        result = await plugin_instance.collect_data()

                        logger.info(
                            f"✅ {plugin_name}: {result.get('records_collected', 0)} records collected"
                        )
                    except Exception as e:
                        logger.error(f"❌ {plugin_name}: Collection failed - {e}")

            logger.info("✅ Scheduled data collection complete")

        except Exception as e:
            logger.error(f"❌ Data collection scheduler error: {e}")
            # Wait 5 minutes before retry
            await asyncio.sleep(300)


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Plugin Registry shutting down...")

    # Close PostgreSQL connection
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
        import sys

        sys.path.insert(0, "/app/services/plugin-registry")
        from core.execution_engine import get_execution_engine

        engine = get_execution_engine()
        await engine.close()
        logger.info("✅ Execution engine closed")
    except Exception as e:
        logger.error(f"Error closing execution engine: {e}")

    redis_client.close()


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)  # nosec B104

# ============================================================================
# Database Operations
# ============================================================================


async def create_plugins_table_if_not_exists():
    """Create plugins table if it doesn't exist"""
    try:
        pool = await get_postgres_connection()

        create_table_query = """
            CREATE TABLE IF NOT EXISTS plugins (
                name VARCHAR(255) PRIMARY KEY,
                version VARCHAR(50) NOT NULL DEFAULT '1.0.0',
                description TEXT,
                author VARCHAR(255),
                status VARCHAR(50) NOT NULL DEFAULT 'registered',
                enabled BOOLEAN NOT NULL DEFAULT FALSE,
                dependencies TEXT,
                capabilities JSONB,
                data_sources JSONB,
                databases JSONB,
                health_status VARCHAR(50) DEFAULT 'unknown',
                last_health_check TIMESTAMP WITH TIME ZONE,
                registered_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """

        async with pool.acquire() as conn:
            await conn.execute(create_table_query)

        logger.info("✅ Plugins table verified/created in PostgreSQL")

    except Exception as e:
        logger.error(f"❌ Failed to create plugins table: {e}")
        raise


async def load_services_from_redis():
    """Load registered services from Redis into memory cache"""
    global services_db  # noqa: F824

    try:
        # Get all service keys from Redis
        service_keys = redis_client.keys("service:*")

        if not service_keys:
            logger.info("No services found in Redis")
            return

        loaded_count = 0

        for service_key in service_keys:
            try:
                # Extract service name from key (format: service:service_name)
                service_name = service_key.replace("service:", "")

                # Get service data from Redis hash
                service_data = redis_client.hgetall(service_key)

                if not service_data:
                    logger.warning(f"Service data empty for {service_name}")
                    continue

                # Parse service data
                service_registration = ServiceRegistration(
                    service_name=service_name,
                    service_type=service_data.get("service_type", "unknown"),
                    host=service_data.get("host", "unknown"),
                    port=int(service_data.get("port", 0)),
                    health_check_url=service_data.get("health_check_url", "/health"),
                    metadata=json.loads(service_data.get("metadata", "{}")),
                )

                services_db[service_name] = service_registration
                loaded_count += 1

            except Exception as e:
                logger.error(f"Failed to load service {service_key}: {e}")

        logger.info(f"✅ Loaded {loaded_count} services from Redis into memory")

    except Exception as e:
        logger.error(f"❌ Failed to load services from Redis: {e}")
        raise


async def load_plugins_from_database():
    """Load plugins from PostgreSQL database into memory cache"""
    global plugins_db  # noqa: F824

    try:
        conn = await get_postgres_connection()

        query = """
            SELECT name, version, description, author, status, enabled,
                   capabilities, data_sources, databases, health_status,
                   last_health_check, registered_at
            FROM plugins
            ORDER BY name
        """

        rows = await conn.fetch(query)

        for row in rows:
            plugin_info = PluginInfo(
                name=row["name"],
                version=row["version"],
                description=row["description"],
                author=row["author"],
                status=row["status"],
                enabled=row["enabled"],
                capabilities=row["capabilities"] or [],
                data_sources=row["data_sources"] or [],
                databases=row["databases"] or [],
                registered_at=(
                    row["registered_at"].isoformat() if row["registered_at"] else None
                ),
                health_status=row["health_status"] or "unknown",
                last_health_check=(
                    row["last_health_check"].isoformat()
                    if row["last_health_check"]
                    else None
                ),
            )
            plugins_db[row["name"]] = plugin_info

        logger.info(f"✅ Loaded {len(plugins_db)} plugins from database")

    except Exception as e:
        logger.error(f"❌ Failed to load plugins from database: {e}")
        # Don't raise - allow startup to continue with empty plugins_db


async def update_plugin_in_database(plugin_name: str, **updates):
    """Update plugin in database (INSERT if not exists, UPDATE if exists)"""
    pool = await get_postgres_connection()

    try:
        # Only allow updating columns that exist in the plugins table
        allowed_columns = {
            "status",
            "enabled",
            "health_status",
            "last_health_check",
            "version",
            "description",
            "author",
            "dependencies",
            "capabilities",
            "data_sources",
            "databases",
        }
        valid_updates = {k: v for k, v in updates.items() if k in allowed_columns}

        if not valid_updates:
            return

        # Build parameter lists in correct order
        insert_columns = ["name"] + list(valid_updates.keys())
        insert_values = [f"${i+1}" for i in range(len(insert_columns))]

        # Build UPDATE clause for ON CONFLICT
        update_clauses = [f"{col} = EXCLUDED.{col}" for col in valid_updates.keys()]

        # Build values list (plugin_name first, then updates)
        values = [plugin_name] + list(valid_updates.values())

        # nosec B608 - SQL injection protected by allowed_columns whitelist
        # Use INSERT ... ON CONFLICT for UPSERT
        query = f"""
            INSERT INTO plugins ({', '.join(insert_columns)})
            VALUES ({', '.join(insert_values)})
            ON CONFLICT (name) DO UPDATE
              SET {', '.join(update_clauses)}
        """

        async with pool.acquire() as conn:
            await conn.execute(query, *values)
        logger.debug(
            f"Upserted plugin {plugin_name} in database: {list(valid_updates.keys())}"
        )

    except Exception as e:
        logger.error(f"Failed to update plugin {plugin_name} in database: {e}")
        import traceback

        logger.error(f"Traceback: {traceback.format_exc()}")


async def sync_plugin_ai_tools(plugin_name: str, plugin_dir: Path):
    """
    Automatically sync AI tools from plugin manifest to marketplace

    This function is called when a plugin is loaded to automatically
    register its AI tools in the marketplace database.

    Args:
        plugin_name: Name of the plugin
        plugin_dir: Path to plugin directory
    """
    try:
        import httpx

        # Load plugin manifest
        manifest_file = plugin_dir / "manifest.yml"
        if not manifest_file.exists():
            manifest_file = plugin_dir / "manifest.json"

        if not manifest_file.exists():
            logger.debug(f"No manifest found for plugin {plugin_name}")
            return

        # Load manifest
        import yaml

        with open(manifest_file, "r") as f:
            if manifest_file.suffix in [".yaml", ".yml"]:
                manifest = yaml.safe_load(f)
            else:
                import json

                manifest = json.load(f)

        # Check if plugin has AI tools
        if "ai_tools" not in manifest:
            logger.debug(f"No AI tools defined in manifest for {plugin_name}")
            return

        # Get or create plugin in marketplace
        plugin_id = await get_or_create_marketplace_plugin(plugin_name, manifest)

        if not plugin_id:
            logger.warning(
                f"Could not get/create marketplace plugin ID for {plugin_name}"
            )
            return

        # Call marketplace sync API
        marketplace_url = os.environ.get("MARKETPLACE_URL", "http://marketplace:8002")

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{marketplace_url}/v1/marketplace/ai/sync",
                json={
                    "plugin_name": plugin_name,
                    "plugin_id": plugin_id,
                    "manifest": manifest,
                },
            )

            if response.status_code == 200:
                result = response.json()
                logger.info(
                    f"✅ Synced {result.get('tools_imported', 0)} AI tools for {plugin_name}"
                )
            else:
                logger.warning(
                    f"Failed to sync AI tools for {plugin_name}: {response.status_code}"
                )

    except Exception as e:
        logger.error(f"Error syncing AI tools for {plugin_name}: {e}")


async def get_or_create_marketplace_plugin(plugin_name: str, manifest: dict) -> str:
    """
    Get existing plugin ID from marketplace or create a new entry

    Args:
        plugin_name: Name of the plugin
        manifest: Plugin manifest dictionary

    Returns:
        Plugin UUID or None if failed
    """
    try:
        import httpx

        marketplace_url = os.environ.get(
            "MARKETPLACE_URL", "http://minder-marketplace:8002"
        )

        # Try to find existing plugin by name
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Search for existing plugin
            search_response = await client.get(
                f"{marketplace_url}/v1/marketplace/plugins/search",
                params={"q": plugin_name},
            )

            if search_response.status_code == 200:
                results = search_response.json()
                plugins = results.get("plugins", [])

                # Check if plugin with matching name exists
                for plugin in plugins:
                    if plugin.get("name") == plugin_name:
                        logger.debug(
                            f"Found existing marketplace plugin: {plugin_name}"
                        )
                        return plugin.get("id")

            # Plugin doesn't exist, create it
            logger.info(f"Creating marketplace entry for plugin: {plugin_name}")

            # Create display_name from description (first sentence, max 200 chars)
            description = manifest.get("description", plugin_name)
            display_name = (
                description.split(".")[0][:200] if description else plugin_name
            )

            # Build plugin data - only include repository_url if it's a valid URL
            plugin_data = {
                "name": plugin_name,
                "display_name": display_name,
                "description": description,
                "author": manifest.get("author", "Unknown"),
                "pricing_model": "free",
                "base_tier": "community",
                "status": "approved",
            }

            # Only include repository_url if it exists and is not empty
            repository = manifest.get("repository")
            if repository and repository.strip():
                plugin_data["repository_url"] = repository

            create_response = await client.post(
                f"{marketplace_url}/v1/marketplace/plugins", json=plugin_data
            )

            if create_response.status_code in [200, 201]:
                plugin_data = create_response.json()
                logger.info(
                    f"Created marketplace plugin entry: {plugin_name} -> {plugin_data.get('id')}"
                )
                return plugin_data.get("id")
            else:
                logger.warning(
                    f"Failed to create marketplace plugin: {create_response.status_code}"
                )
                logger.warning(f"Response: {create_response.text}")
                return None

    except Exception as e:
        logger.error(f"Error getting/creating marketplace plugin: {e}")
        return None



# Plugin CRUD/lifecycle endpoints (routes/plugins_api.py). Included at module end so
# the main-owned helpers it injects (update_plugin_in_database, register_plugin_webhook,
# handle_webhook_request) are already defined.
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
