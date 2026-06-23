"""
Minder Plugin Registry Service - Modular Architecture

Manages plugin discovery, lifecycle, health monitoring, and service registration.
This refactored version uses core modules for database and plugin loading.
"""

import asyncio
import logging
import sys
from datetime import datetime
from typing import Dict, Optional

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest
from pydantic import BaseModel

# Add paths for module imports
sys.path.insert(0, "/app/src")
sys.path.insert(0, "/app/plugins")

# Import core modules
from core.database import initialize_connection_pool
from core.plugin_loader import load_plugins_from_disk

# Import existing routes

# Import shared utilities
from shared.auth.jwt_middleware import get_current_user

# Import config
from config import settings

# Configure logging
logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL))
logger = logging.getLogger("minder.plugin-registry")

# ============================================================================
# Global State
# ============================================================================

# Plugin storage
plugins: Dict[str, Dict] = {}

# ============================================================================
# Pydantic Models
# ============================================================================


class PluginInfo(BaseModel):
    """Basic plugin information"""

    name: str
    version: str
    description: str
    author: Optional[str] = None
    enabled: bool = True


class ServiceRegistration(BaseModel):
    """Service registration request"""

    name: str
    url: str
    health_check_url: Optional[str] = None


class PluginInstallationRequest(BaseModel):
    """Plugin installation request"""

    source: str  # "git" or "file"
    url: Optional[str] = None
    manifest: Optional[Dict] = None


class LoginRequest(BaseModel):
    """Login request"""

    username: str
    password: str


# ============================================================================
# FastAPI App
# ============================================================================

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
active_plugins_total = Gauge("active_plugins_total", "Number of active plugins")
plugin_health_status = Gauge("plugin_health_status", "Plugin health status", ["plugin"])

# ============================================================================
# Startup/Shutdown Events
# ============================================================================


@app.on_event("startup")
async def startup_event():
    """Initialize on startup"""
    logger.info("🚀 Starting Plugin Registry service...")

    # Initialize database connection pool
    try:
        await initialize_connection_pool()
        logger.info("✅ Database connection initialized")
    except Exception as e:
        logger.warning(f"⚠️ Database initialization failed: {e}")

    # Load plugins from disk
    try:
        global plugins
        plugins = await load_plugins_from_disk()
        logger.info(f"✅ Loaded {len(plugins)} plugins from disk")
    except Exception as e:
        logger.warning(f"⚠️ Failed to load plugins: {e}")
        plugins = {}

    # Start health check loop
    asyncio.create_task(health_check_loop())


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Shutting down Plugin Registry service...")
    from core.database import close_postgres_connection

    await close_postgres_connection()


# ============================================================================
# Health Check Loop
# ============================================================================


async def health_check_loop():
    """Background health check loop for all plugins"""
    while True:
        try:
            for plugin_name, plugin_data in plugins.items():
                if plugin_data.get("enabled", True):
                    # Perform health check
                    health_status = await check_plugin_health(plugin_name)
                    plugin_data["health_status"] = health_status

                    # Update Prometheus metric
                    plugin_health_status.labels(plugin=plugin_name).set(
                        1 if health_status == "healthy" else 0
                    )

            await asyncio.sleep(60)  # Check every minute
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning(f"Health check loop error: {e}")
            await asyncio.sleep(60)


async def check_plugin_health(plugin_name: str) -> str:
    """Check health of a specific plugin"""
    # This would implement actual health check logic
    # For now, return healthy if plugin exists
    return "healthy" if plugin_name in plugins else "unknown"


# ============================================================================
# Health & Metrics Endpoints
# ============================================================================


@app.get("/health")
async def health_check():
    """Service health check endpoint"""
    return {
        "service": "plugin-registry",
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": app.version,
        "plugins_loaded": len(plugins),
    }


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ============================================================================
# Request Tracking Middleware
# ============================================================================


@app.middleware("http")
async def track_requests(request: Request, call_next):
    """Track requests for metrics"""
    import time

    start_time = time.time()

    response = await call_next(request)

    # Update metrics
    duration = time.time() - start_time
    http_requests_total.labels(
        method=request.method, endpoint=request.url.path, status=response.status_code
    ).inc()

    return response


# ============================================================================
# Authentication Endpoints
# ============================================================================


@app.post("/login")
async def login(request: LoginRequest):
    """Login endpoint for authentication"""
    username = request.username
    password = request.password

    # For demo purposes, accept admin/admin
    if username == "admin" and password == "admin":
        return {
            "access_token": "demo_token",
            "token_type": "bearer",
            "expires_in": 3600,
        }

    raise HTTPException(status_code=401, detail="Invalid credentials")


@app.get("/user/info")
async def get_current_user_info(current_user: Dict = Depends(get_current_user)):
    """Get current user information"""
    return {
        "user": current_user.get("username", "unknown"),
        "role": current_user.get("role", "user"),
    }


# ============================================================================
# Plugin List Endpoints
# ============================================================================


@app.get("/plugins", redirect_slash=False)
async def list_plugins_redirect():
    """List plugins (with redirect for /)"""
    return RedirectResponse(url="/v1/plugins")


@app.get("/v1/plugins")
async def list_plugins():
    """List all registered plugins"""
    return list(plugins.values())


@app.get("/v1/plugins/{plugin_name}")
async def get_plugin(plugin_name: str):
    """Get specific plugin information"""
    if plugin_name not in plugins:
        raise HTTPException(status_code=404, detail=f"Plugin {plugin_name} not found")

    return plugins[plugin_name]


# ============================================================================
# Plugin Lifecycle Endpoints
# ============================================================================


@app.post("/v1/plugins/install")
async def install_plugin(
    request: PluginInstallationRequest, background_tasks: BackgroundTasks
):
    """Install a new plugin"""
    plugin_name = f"plugin_{datetime.now().timestamp()}"

    # Create plugin entry
    plugins[plugin_name] = {
        "name": plugin_name,
        "version": "1.0.0",
        "description": f"Plugin from {request.source}",
        "enabled": True,
        "installed_at": datetime.now().isoformat(),
    }

    logger.info(f"✅ Plugin installed: {plugin_name}")
    return {"message": "Plugin installed successfully", "plugin_name": plugin_name}


@app.delete("/v1/plugins/{plugin_name}")
async def uninstall_plugin(
    plugin_name: str, current_user: Dict = Depends(get_current_user)
):
    """Uninstall a plugin"""
    if plugin_name not in plugins:
        raise HTTPException(status_code=404, detail=f"Plugin {plugin_name} not found")

    del plugins[plugin_name]

    logger.info(f"✅ Plugin uninstalled: {plugin_name}")
    return {"message": "Plugin uninstalled successfully", "plugin_name": plugin_name}


@app.post("/v1/plugins/{plugin_name}/enable")
async def enable_plugin(
    plugin_name: str, current_user: Dict = Depends(get_current_user)
):
    """Enable a plugin"""
    if plugin_name not in plugins:
        raise HTTPException(status_code=404, detail=f"Plugin {plugin_name} not found")

    plugins[plugin_name]["enabled"] = True

    logger.info(f"✅ Plugin enabled: {plugin_name}")
    return {"message": "Plugin enabled", "plugin_name": plugin_name}


@app.post("/v1/plugins/{plugin_name}/disable")
async def disable_plugin(
    plugin_name: str, current_user: Dict = Depends(get_current_user)
):
    """Disable a plugin"""
    if plugin_name not in plugins:
        raise HTTPException(status_code=404, detail=f"Plugin {plugin_name} not found")

    plugins[plugin_name]["enabled"] = False

    logger.info(f"✅ Plugin disabled: {plugin_name}")
    return {"message": "Plugin disabled", "plugin_name": plugin_name}


# ============================================================================
# Plugin Health Endpoints
# ============================================================================


@app.get("/v1/plugins/{plugin_name}/health")
async def get_plugin_health(plugin_name: str):
    """Get plugin health status"""
    if plugin_name not in plugins:
        raise HTTPException(status_code=404, detail=f"Plugin {plugin_name} not found")

    health_status = await check_plugin_health(plugin_name)

    return {
        "plugin": plugin_name,
        "health_status": health_status,
        "enabled": plugins[plugin_name].get("enabled", True),
    }


@app.post("/v1/plugins/{plugin_name}/collect")
async def trigger_plugin_collection(plugin_name: str):
    """Trigger data collection for a plugin"""
    if plugin_name not in plugins:
        raise HTTPException(status_code=404, detail=f"Plugin {plugin_name} not found")

    # This would implement actual data collection logic
    logger.info(f"🔄 Triggered collection for plugin: {plugin_name}")

    return {
        "message": "Collection triggered",
        "plugin": plugin_name,
        "timestamp": datetime.now().isoformat(),
    }


# ============================================================================
# Root Endpoint
# ============================================================================


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Minder Plugin Registry",
        "version": app.version,
        "plugins": len(plugins),
        "docs": "/docs",
    }


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
