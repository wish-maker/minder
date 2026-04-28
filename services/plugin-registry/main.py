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
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from pydantic import BaseModel

from config import settings

# Import authentication middleware
sys.path.insert(0, "/app/src")
# Import proxy router for microservices
from routes.plugins import ProxyRouter

# Import AI tool validator
from shared.ai.tool_validator import validate_ai_tools
from shared.auth.jwt_middleware import JWT_EXPIRATION_MINUTES, enforce_rate_limit, get_current_user

# Configure logging
logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL))
logger = logging.getLogger("minder.plugin-registry")

# Initialize FastAPI app
app = FastAPI(
    title="Minder Plugin Registry",
    description="Plugin discovery and lifecycle management",
    version="2.1.0",
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


class PluginInfo(BaseModel):
    """Plugin information"""

    name: str
    version: str
    description: str
    author: str
    status: str = "registered"  # registered, enabled, disabled, error
    enabled: bool = False  # Track if plugin is enabled
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
# Dynamic Proxy Router
# ============================================================================

# Initialize proxy router for microservices
proxy_router = ProxyRouter(services_db)

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
            version=manifest.get("version", "2.1.0"),
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

            # Auto-sync AI tools with marketplace
            await sync_plugin_ai_tools(plugin_name, plugin_dir)

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
        "version": "2.1.0",
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
# API Endpoints - Authentication
# ============================================================================


class LoginRequest(BaseModel):
    """Login request model"""

    username: str
    password: str


@app.post("/v1/auth/login")
async def login(request: LoginRequest):
    """
    Authenticate and get JWT token

    NOTE: This is a simplified authentication for demonstration.
    In production, integrate with proper user database and
    password hashing (bcrypt/argon2).
    """
    # TODO: Integrate with proper user database
    # For now, accept any non-empty credentials for testing
    if not request.username or not request.password:
        raise HTTPException(status_code=400, detail="Username and password required")

    # Simple validation (replace with proper authentication in production)
    if len(request.username) < 3 or len(request.password) < 8:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Create user payload
    user_payload = {
        "sub": request.username,
        "username": request.username,
        "role": "user",
    }  # user ID  # Default role

    # Assign admin role to specific users (configure as needed)
    admin_users = os.environ.get("ADMIN_USERS", "admin").split(",")
    if request.username in admin_users:
        user_payload["role"] = "admin"

    # Generate JWT token
    from shared.auth.jwt_middleware import create_user_token

    token = create_user_token(
        user_id=user_payload["sub"], username=request.username, role=user_payload["role"]
    )

    logger.info(f"User logged in: {request.username} ({user_payload['role']})")

    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": JWT_EXPIRATION_MINUTES * 60,
        "user": {"username": request.username, "role": user_payload["role"]},
    }


@app.get("/v1/auth/me")
async def get_current_user_info(current_user: Dict = Depends(get_current_user)):
    """Get current authenticated user information"""
    return {
        "username": current_user.get("username"),
        "role": current_user.get("role"),
        "user_id": current_user.get("sub"),
    }


# ============================================================================
# API Endpoints - Plugin Management
# ============================================================================


@app.get("/v1/plugins")
async def list_plugins():
    """List all registered plugins (public endpoint)"""
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
async def uninstall_plugin(plugin_name: str, current_user: Dict = Depends(get_current_user)):
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
async def enable_plugin(plugin_name: str, current_user: Dict = Depends(get_current_user)):
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
async def disable_plugin(plugin_name: str, current_user: Dict = Depends(get_current_user)):
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
@enforce_rate_limit(max_requests=10, window_minutes=1)
async def trigger_plugin_collection(
    plugin_name: str,
    background_tasks: BackgroundTasks,
    current_user: Dict = Depends(get_current_user),
):
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

    # Audit logging
    username = current_user.get("username", "unknown")
    user_role = current_user.get("role", "unknown")
    logger.info(
        f"Data collection triggered for plugin: {plugin_name} | "
        f"User: {username} ({user_role}) | "
        f"Timestamp: {datetime.utcnow().isoformat()}"
    )

    return {
        "message": f"Data collection triggered for {plugin_name}",
        "plugin": plugin_name,
        "status": "collecting",
        "triggered_by": username,
        "timestamp": datetime.utcnow().isoformat(),
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


@app.get("/v1/services/{service_name}/health")
async def check_service_health(service_name: str):
    """
    Check health of a registered microservice

    Performs health check on the registered service by calling its /health endpoint.
    Updates service health status in Redis.
    """
    try:
        health_data = await proxy_router.health_check_proxy(service_name)

        # Update health status in Redis
        redis_client.hset(
            f"service:{service_name}",
            mapping={
                "health_status": "healthy",
                "last_health_check": datetime.now().isoformat(),
            },
        )

        return {
            "service": service_name,
            "status": "healthy",
            "health_data": health_data,
            "checked_at": datetime.now().isoformat(),
        }

    except HTTPException:
        # Update unhealthy status in Redis
        redis_client.hset(
            f"service:{service_name}",
            mapping={
                "health_status": "unhealthy",
                "last_health_check": datetime.now().isoformat(),
            },
        )
        raise


# ============================================================================
# Dynamic Proxy Endpoints for Microservices
# ============================================================================


@app.api_route(
    "/v1/proxy/{service_name}/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"]
)
async def proxy_to_service(service_name: str, path: str, request: Request):
    """
    Dynamic proxy endpoint for plugin microservices

    Forwards HTTP requests to registered plugin microservices.
    This enables the API Gateway to route AI tool calls to appropriate services
    without hardcoding endpoints.

    Examples:
        GET  /v1/proxy/crypto/analysis?symbol=BTC
        POST /v1/proxy/news/collect
        GET  /v1/proxy/weather/analysis?location=Istanbul
    """
    # Build the full path for proxying
    proxy_path = f"/{path}"

    # Add query string if present
    if request.url.query:
        proxy_path = f"{proxy_path}?{request.url.query}"

    # Forward request to service
    return await proxy_router.forward_request(service_name, proxy_path, request)


@app.get("/v1/proxy")
async def list_proxyable_services():
    """
    List all services that can be proxied

    Returns information about registered microservices that are available
    for dynamic proxy routing.
    """
    proxyable_services = []

    for service_name, service in services_db.items():
        # Check if service is healthy
        health_status = redis_client.hget(f"service:{service_name}", "health_status") or "unknown"

        proxyable_services.append(
            {
                "service_name": service_name,
                "service_type": service.service_type,
                "health_status": health_status,
                "endpoint": f"http://{service.host}:{service.port}",
                "proxy_url": f"/v1/proxy/{service_name}",
                "metadata": service.metadata,
            }
        )

    return {
        "services": proxyable_services,
        "count": len(proxyable_services),
        "timestamp": datetime.now().isoformat(),
    }


# ============================================================================
# API Endpoints - AI Tools
# ============================================================================


@app.get("/v1/plugins/ai/tools")
async def get_all_ai_tools():
    """
    Aggregate AI tools from all plugins

    Returns OpenAI-compatible tool definitions from all active plugins.
    Each plugin declares its AI tools in manifest.yml.
    """
    all_tools = []

    for plugin_name, plugin_info in plugins_db.items():
        try:
            # Get plugin instance
            plugin_instance = plugin_instances.get(plugin_name)
            if not plugin_instance:
                logger.debug(f"Plugin instance not available: {plugin_name}")
                continue

            # Load plugin manifest
            manifest = await load_plugin_manifest(plugin_name)
            if not manifest:
                logger.debug(f"No manifest found for plugin: {plugin_name}")
                continue

            # Validate AI tools
            tools = validate_ai_tools(manifest)

            # Convert each tool to OpenAI function format
            for tool in tools:
                # Build parameters schema for OpenAI
                properties = {}
                required = []

                for param_name, param_def in tool.parameters.items():
                    properties[param_name] = {
                        "type": param_def.type.value,
                        "description": param_def.description,
                    }

                    if param_def.enum:
                        properties[param_name]["enum"] = param_def.enum

                    if param_def.default is not None:
                        properties[param_name]["default"] = param_def.default

                    if param_def.required:
                        required.append(param_name)

                # Format as OpenAI function
                openai_tool = {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": {
                            "type": "object",
                            "properties": properties,
                            "required": required,
                        },
                    },
                    "metadata": {
                        "plugin": plugin_name,
                        "endpoint": f"/v1/plugins/{plugin_name}{tool.endpoint}",
                        "method": tool.method,
                    },
                }

                all_tools.append(openai_tool)

        except Exception as e:
            logger.error(f"Failed to load AI tools from plugin {plugin_name}: {e}")
            continue

    return {"tools": all_tools}


@app.get("/v1/plugins/{plugin_name}/analysis")
async def get_plugin_analysis(
    plugin_name: str,
    symbol: str = None,
    limit: int = 10,
    location: str = "Istanbul",
    fund_type: str = "YATIRIM",
):
    """
    Generic analysis endpoint for all plugins

    This endpoint handles AI tool analysis requests by calling the appropriate
    plugin's analyze() method with the provided parameters.

    Called by OpenWebUI when LLM requests a plugin's AI tool.
    """
    global plugin_instances

    # Check if plugin exists and is enabled
    if plugin_name not in plugins_db:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_name}' not found")

    if not plugins_db[plugin_name].enabled:
        raise HTTPException(status_code=403, detail=f"Plugin '{plugin_name}' is not enabled")

    # Check if plugin instance is available
    if plugin_name not in plugin_instances:
        raise HTTPException(status_code=503, detail=f"Plugin '{plugin_name}' is not running")

    try:
        plugin_instance = plugin_instances[plugin_name]

        # Call plugin's analyze method
        # Note: The base analyze() method doesn't take parameters,
        # so we return the latest analysis results
        analysis_result = await plugin_instance.analyze()

        # Enhance with plugin-specific data if available
        if plugin_name == "crypto" and symbol:
            # Crypto-specific: get data for specific symbol
            if "metrics" in analysis_result and symbol in analysis_result["metrics"]:
                return {
                    "symbol": symbol,
                    **analysis_result["metrics"][symbol],
                    "timestamp": datetime.now().isoformat(),
                }
            else:
                raise HTTPException(status_code=404, detail=f"No data found for symbol {symbol}")

        elif plugin_name == "news":
            # News-specific: limit articles
            if "insights" in analysis_result:
                return {
                    "articles": analysis_result.get("metrics", {}).get("latest_articles", [])[
                        :limit
                    ],
                    "total": min(
                        limit, len(analysis_result.get("metrics", {}).get("latest_articles", []))
                    ),
                    "limit": limit,
                }

        elif plugin_name == "weather" and location:
            # Weather-specific: get data for location
            if "metrics" in analysis_result:
                weather_data = analysis_result["metrics"].get(
                    location,
                    {
                        "temperature": analysis_result["metrics"].get("avg_temp_c", 0),
                        "humidity": analysis_result["metrics"].get("avg_humidity_pct", 0),
                        "conditions": "unknown",
                    },
                )
                return {
                    "location": location,
                    "temperature": weather_data.get("temperature", 0),
                    "humidity": weather_data.get("humidity", 0),
                    "conditions": weather_data.get("conditions", "unknown"),
                    "timestamp": datetime.now().isoformat(),
                }

        elif plugin_name == "network":
            # Network-specific: return recent metrics
            if "metrics" in analysis_result:
                return {
                    "metrics": [
                        {
                            "timestamp": datetime.now().isoformat(),
                            "cpu_usage": analysis_result["metrics"].get("avg_cpu_usage_pct", 0),
                            "memory_usage": analysis_result["metrics"].get(
                                "avg_memory_usage_pct", 0
                            ),
                            "load_avg": analysis_result["metrics"].get("avg_load_avg", 0),
                        }
                    ],
                    "average_latency": analysis_result["metrics"].get("avg_load_avg", 0),
                    "limit": limit,
                }

        elif plugin_name == "tefas":
            # TEFAS-specific: return fund data
            if "metrics" in analysis_result and "top_funds" in analysis_result["metrics"]:
                funds = analysis_result["metrics"]["top_funds"][:limit]
                return {"funds": funds, "total": len(funds), "fund_type": fund_type, "limit": limit}

        # Default: return full analysis
        return analysis_result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Analysis error for plugin {plugin_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


async def load_plugin_manifest(plugin_name: str):
    """Load plugin manifest from disk"""
    try:
        plugins_path = Path(settings.PLUGINS_PATH)
        manifest_file = plugins_path / plugin_name / "manifest.yml"

        if not manifest_file.exists():
            # Try manifest.json as fallback
            manifest_file = plugins_path / plugin_name / "manifest.json"

        if not manifest_file.exists():
            return None

        import yaml

        with open(manifest_file, "r") as f:
            if manifest_file.suffix == ".yaml" or manifest_file.suffix == ".yml":
                return yaml.safe_load(f)
            else:
                import json

                return json.load(f)

    except Exception as e:
        logger.error(f"Failed to load manifest for {plugin_name}: {e}")
        return None


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

    # Auto-enable all plugins on startup
    await auto_enable_plugins()

    # Start health check loop
    asyncio.create_task(health_check_loop())

    # Start automatic data collection scheduler
    asyncio.create_task(data_collection_scheduler())

    logger.info(f"Loaded {len(plugins_db)} plugins")


async def auto_enable_plugins():
    """Automatically enable all plugins on startup"""
    global plugins_db

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
    global postgres_pool
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

        # Only allow updating columns that exist in the plugins table
        allowed_columns = {"status", "enabled", "health_status", "last_health_check"}
        valid_updates = {k: v for k, v in updates.items() if k in allowed_columns}

        if not valid_updates:
            return

        # Build SET clause dynamically
        set_clauses = []
        values = []
        for key, value in valid_updates.items():
            set_clauses.append(f"{key} = ${len(values) + 1}")
            values.append(value)

        values.append(plugin_name)  # For WHERE clause

        query = f"""  # nosec B608
            UPDATE plugins
            SET {', '.join(set_clauses)}
            WHERE name = ${len(values)}
        """

        await conn.execute(query, *values)
        logger.debug(f"Updated plugin {plugin_name} in database: {list(valid_updates.keys())}")

    except Exception as e:
        logger.error(f"Failed to update plugin {plugin_name} in database: {e}")


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
            logger.warning(f"Could not get/create marketplace plugin ID for {plugin_name}")
            return

        # Call marketplace sync API
        marketplace_url = os.environ.get("MARKETPLACE_URL", "http://marketplace:8002")

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{marketplace_url}/v1/marketplace/ai/sync",
                json={"plugin_name": plugin_name, "plugin_id": plugin_id, "manifest": manifest},
            )

            if response.status_code == 200:
                result = response.json()
                logger.info(
                    f"✅ Synced {result.get('tools_imported', 0)} AI tools for {plugin_name}"
                )
            else:
                logger.warning(f"Failed to sync AI tools for {plugin_name}: {response.status_code}")

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

        marketplace_url = os.environ.get("MARKETPLACE_URL", "http://minder-marketplace:8002")

        # Try to find existing plugin by name
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Search for existing plugin
            search_response = await client.get(
                f"{marketplace_url}/v1/marketplace/plugins/search", params={"q": plugin_name}
            )

            if search_response.status_code == 200:
                results = search_response.json()
                plugins = results.get("plugins", [])

                # Check if plugin with matching name exists
                for plugin in plugins:
                    if plugin.get("name") == plugin_name:
                        logger.debug(f"Found existing marketplace plugin: {plugin_name}")
                        return plugin.get("id")

            # Plugin doesn't exist, create it
            logger.info(f"Creating marketplace entry for plugin: {plugin_name}")

            # Create display_name from description (first sentence, max 200 chars)
            description = manifest.get("description", plugin_name)
            display_name = description.split(".")[0][:200] if description else plugin_name

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
