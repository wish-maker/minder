"""
Minder Plugin Registry Service
Manages plugin discovery, lifecycle, health monitoring, and service registration
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Dict, List, Optional
import redis
import logging
import asyncio
import os
from datetime import datetime
from pathlib import Path
import sys
import json
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Response

from config import settings

# Add src to path for imports
sys.path.insert(0, "/app/src")

# Configure logging
logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL))
logger = logging.getLogger("minder.plugin-registry")

# Initialize FastAPI app
app = FastAPI(
    title="Minder Plugin Registry",
    description="Plugin discovery and lifecycle management",
    version="2.0.0",
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
    "plugins_total", "Total number of plugins", ["status"]  # registered, enabled, disabled, error
)

health_check_failures_total = Counter(
    "health_check_failures_total", "Total health check failures", ["plugin"]
)

# ============================================================================
# Data Models
# ============================================================================


class PluginInfo(BaseModel):
    """Plugin information"""

    name: str
    version: str
    description: str
    author: str
    status: str  # registered, enabled, disabled, error
    dependencies: List[str] = []
    capabilities: List[str] = []
    data_sources: List[str] = []
    databases: List[str] = []
    registered_at: str
    health_status: str = "unknown"
    last_health_check: Optional[str] = None


class ServiceRegistration(BaseModel):
    """Service registration for service discovery"""

    service_name: str
    service_type: str
    host: str
    port: int
    health_check_url: str = "/health"
    metadata: Dict = {}


class PluginInstallationRequest(BaseModel):
    """Request to install 3rd party plugin"""

    repository: str
    branch: str = "main"
    version: Optional[str] = None


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
import asyncpg

postgres_pool = None


async def get_postgres_connection():
    """Get PostgreSQL connection from pool"""
    global postgres_pool
    if postgres_pool is None:
        postgres_pool = await asyncpg.create_pool(
            host=(
                settings.POSTGRES_HOST if hasattr(settings, "POSTGRES_HOST") else "minder-postgres"
            ),
            port=settings.POSTGRES_PORT if hasattr(settings, "POSTGRES_PORT") else 5432,
            user=settings.POSTGRES_USER if hasattr(settings, "POSTGRES_USER") else "minder",
            password=(
                settings.POSTGRES_PASSWORD
                if hasattr(settings, "POSTGRES_PASSWORD")
                else "dev_password_change_me"
            ),
            database=settings.POSTGRES_DB if hasattr(settings, "POSTGRES_DB") else "minder",
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

        # Look for plugin manifest or main module
        manifest_file = plugin_dir / "manifest.json"
        main_module = plugin_dir / "__init__.py"

        if manifest_file.exists():
            await load_plugin_from_manifest(manifest_file)
        elif main_module.exists():
            await load_plugin_from_module(plugin_dir)


async def load_plugin_from_manifest(manifest_path: Path):
    """Load plugin from manifest.json file"""
    try:
        with open(manifest_path, "r") as f:
            manifest = json.load(f)

        plugin_name = manifest.get("name")
        if not plugin_name:
            logger.error(f"Manifest missing 'name' field: {manifest_path}")
            return

        # TODO: Load plugin module and call register()
        # For now, just store metadata
        plugin_info = PluginInfo(
            name=plugin_name,
            version=manifest.get("version", "1.0.0"),
            description=manifest.get("description", ""),
            author=manifest.get("author", ""),
            status="registered",
            dependencies=manifest.get("dependencies", []),
            capabilities=manifest.get("capabilities", []),
            data_sources=manifest.get("data_sources", []),
            databases=manifest.get("databases", []),
            registered_at=datetime.now().isoformat(),
        )

        plugins_db[plugin_name] = plugin_info
        logger.info(f"Loaded plugin: {plugin_name}")

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
                if isinstance(attr, type) and issubclass(attr, BaseModule) and attr != BaseModule:
                    plugin_class = attr
                    break

        if plugin_class:
            # Create plugin configuration with proper database host
            plugin_config = {
                "database": {
                    "host": "minder-postgres",
                    "port": 5432,
                    "user": "minder",
                    "password": os.environ.get("POSTGRES_PASSWORD", "dev_password_change_me"),
                    "database": "minder",
                },
                "redis": {
                    "host": "minder-redis",
                    "port": 6379,
                    "password": os.environ.get("REDIS_PASSWORD", "dev_password_change_me"),
                    "db": 0,
                },
                "influxdb": {
                    "enabled": True,
                    "host": "minder-influxdb",
                    "port": 8086,
                    "token": os.environ.get(
                        "INFLUXDB_TOKEN", "minder-super-secret-token-change-me-in-production"
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
                f"Loaded and registered plugin: {plugin_name} (status: {plugin_instance.status.value})"
            )

    except Exception as e:
        logger.error(f"Failed to load plugin from {plugin_dir}: {e}")


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
                    plugin_info.health_status = "healthy" if health.get("healthy") else "unhealthy"
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
        "version": "2.0.0",
        "environment": settings.ENVIRONMENT,
        "plugins_loaded": len(plugins_db),
        "services_registered": len(services_db),
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
    http_requests_total.labels(method=method, endpoint=endpoint, status=response.status_code).inc()
    http_request_duration_seconds.labels(method=method, endpoint=endpoint).observe(duration)

    return response


# ============================================================================
# API Endpoints - Plugin Management
# ============================================================================


@app.get("/v1/plugins")
async def list_plugins():
    """List all registered plugins"""
    return {"plugins": list(plugins_db.values()), "count": len(plugins_db)}


@app.get("/v1/plugins/{plugin_name}")
async def get_plugin(plugin_name: str):
    """Get plugin details"""
    plugin = plugins_db.get(plugin_name)
    if not plugin:
        raise HTTPException(status_code=404, detail="Plugin not found")
    return plugin


@app.post("/v1/plugins/install")
async def install_plugin(request: PluginInstallationRequest, background_tasks: BackgroundTasks):
    """
    Install 3rd party plugin from repository
    TODO: Implement git clone + plugin loading
    """
    # For now, return not implemented
    raise HTTPException(status_code=501, detail="Plugin installation not yet implemented")


@app.delete("/v1/plugins/{plugin_name}")
async def uninstall_plugin(plugin_name: str):
    """Uninstall a plugin"""
    if plugin_name not in plugins_db:
        raise HTTPException(status_code=404, detail="Plugin not found")

    # Unload plugin
    if plugin_name in plugin_instances:
        await plugin_instances[plugin_name].shutdown()
        del plugin_instances[plugin_name]

    del plugins_db[plugin_name]
    redis_client.delete(f"plugin:{plugin_name}")

    return {"message": f"Plugin {plugin_name} uninstalled"}


@app.post("/v1/plugins/{plugin_name}/enable")
async def enable_plugin(plugin_name: str):
    """Enable a plugin"""
    plugin = plugins_db.get(plugin_name)
    if not plugin:
        raise HTTPException(status_code=404, detail="Plugin not found")

    plugin.status = "enabled"

    # Update plugin instance status to READY for health check
    if plugin_name in plugin_instances:
        from src.core.interface import ModuleStatus

        plugin_instances[plugin_name].status = ModuleStatus.READY

    # Persist to database
    await update_plugin_in_database(plugin_name, status="enabled", enabled=True)

    return {"message": f"Plugin {plugin_name} enabled"}


@app.post("/v1/plugins/{plugin_name}/disable")
async def disable_plugin(plugin_name: str):
    """Disable a plugin"""
    plugin = plugins_db.get(plugin_name)
    if not plugin:
        raise HTTPException(status_code=404, detail="Plugin not found")

    plugin.status = "disabled"

    # Update plugin instance status to REGISTERED for health check
    if plugin_name in plugin_instances:
        from src.core.interface import ModuleStatus

        plugin_instances[plugin_name].status = ModuleStatus.REGISTERED

    # Persist to database
    await update_plugin_in_database(plugin_name, status="disabled", enabled=False)

    return {"message": f"Plugin {plugin_name} disabled"}


@app.get("/v1/plugins/{plugin_name}/health")
async def get_plugin_health(plugin_name: str):
    """Get plugin health status"""
    plugin = plugins_db.get(plugin_name)
    if not plugin:
        raise HTTPException(status_code=404, detail="Plugin not found")

    plugin_instance = plugin_instances.get(plugin_name)
    if not plugin_instance:
        return {
            "name": plugin_name,
            "health_status": plugin.health_status,
            "last_health_check": plugin.last_health_check,
            "message": "Plugin instance not available",
        }

    health = await plugin_instance.health_check()
    return health


@app.post("/v1/plugins/{plugin_name}/collect")
async def trigger_plugin_collection(plugin_name: str, background_tasks: BackgroundTasks):
    """
    Manually trigger data collection for a plugin

    This endpoint initiates an asynchronous data collection task for the specified plugin.
    The collection runs in the background, allowing the API to respond immediately.

    Args:
        plugin_name: Name of the plugin to trigger collection for

    Returns:
        Confirmation message with collection status

    Raises:
        HTTPException 404: If plugin is not found
        HTTPException 400: If plugin is not enabled
    """
    # Check if plugin exists
    plugin = plugins_db.get(plugin_name)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_name}' not found")

    # Check if plugin is enabled
    if plugin.status != "enabled":
        raise HTTPException(
            status_code=400,
            detail=f"Plugin '{plugin_name}' is not enabled. Current status: {plugin.status}",
        )

    # Get plugin instance
    plugin_instance = plugin_instances.get(plugin_name)
    if not plugin_instance:
        raise HTTPException(
            status_code=500,
            detail=f"Plugin '{plugin_name}' instance not available",
        )

    # Trigger collection in background
    background_tasks.add_task(plugin_instance.collect_data)

    logger.info(f"Data collection triggered for plugin: {plugin_name}")

    return {
        "message": f"Data collection triggered for {plugin_name}",
        "plugin": plugin_name,
        "status": "collecting",
        "note": "Collection runs in background. Check /health endpoint for results.",
    }


# ============================================================================
# API Endpoints - Service Discovery
# ============================================================================


@app.post("/v1/services/register")
async def register_service(service: ServiceRegistration):
    """Register a service for service discovery"""
    services_db[service.service_name] = service

    # Store in Redis for other services to discover
    redis_client.hset(
        f"service:{service.service_name}",
        mapping={
            "service_type": service.service_type,
            "host": service.host,
            "port": service.port,
            "health_check_url": service.health_check_url,
            "registered_at": datetime.now().isoformat(),
            "metadata": json.dumps(service.metadata),
        },
    )

    logger.info(f"Service registered: {service.service_name}")

    return {"message": f"Service {service.service_name} registered", "service": service.dict()}


@app.get("/v1/services")
async def list_services():
    """List all registered services"""
    return {"services": list(services_db.values()), "count": len(services_db)}


@app.get("/v1/services/{service_name}")
async def get_service(service_name: str):
    """Get service details"""
    service = services_db.get(service_name)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    return service


@app.delete("/v1/services/{service_name}")
async def unregister_service(service_name: str):
    """Unregister a service"""
    if service_name not in services_db:
        raise HTTPException(status_code=404, detail="Service not found")

    del services_db[service_name]
    redis_client.delete(f"service:{service_name}")

    return {"message": f"Service {service_name} unregistered"}


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

    # Load plugins from database
    await load_plugins_from_database()

    # Load plugins from disk (sync with database)
    await load_plugins_from_disk()

    # Start health check loop
    asyncio.create_task(health_check_loop())

    logger.info(f"Loaded {len(plugins_db)} plugins")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Plugin Registry shutting down...")

    # Close PostgreSQL connection
    global postgres_pool
    if postgres_pool:
        await postgres_pool.close()

    # Shutdown all plugin instances
    for plugin_name, plugin_instance in plugin_instances.items():
        try:
            await plugin_instance.shutdown()
        except Exception as e:
            logger.error(f"Error shutting down {plugin_name}: {e}")

    redis_client.close()


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)

# ============================================================================
# Database Operations
# ============================================================================


async def load_plugins_from_database():
    """Load plugins from PostgreSQL database into memory cache"""
    global plugins_db

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
                registered_at=row["registered_at"].isoformat() if row["registered_at"] else None,
                health_status=row["health_status"] or "unknown",
                last_health_check=(
                    row["last_health_check"].isoformat() if row["last_health_check"] else None
                ),
            )
            plugins_db[row["name"]] = plugin_info

        logger.info(f"Loaded {len(plugins_db)} plugins from database")

    except Exception as e:
        logger.error(f"Failed to load plugins from database: {e}")


async def update_plugin_in_database(plugin_name: str, **updates):
    """Update plugin in database"""
    try:
        conn = await get_postgres_connection()

        # Build SET clause dynamically
        set_clauses = []
        values = []
        for key, value in updates.items():
            set_clauses.append(f"{key} = ${len(values) + 1}")
            values.append(value)

        values.append(plugin_name)  # For WHERE clause

        query = f"""
            UPDATE plugins
            SET {', '.join(set_clauses)}, updated_at = NOW()
            WHERE name = ${len(values)}
        """

        await conn.execute(query, *values)
        logger.debug(f"Updated plugin {plugin_name} in database: {list(updates.keys())}")

    except Exception as e:
        logger.error(f"Failed to update plugin {plugin_name} in database: {e}")
