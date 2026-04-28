"""
Minder API Gateway
Central entry point for all API requests
Handles authentication, rate limiting, request routing, and logging
"""

import logging
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict

import httpx
import redis
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from jose import jwt
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

# Import AI integration router
from routes.ai import router as ai_router

from config import settings

# Configure logging
logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL))
logger = logging.getLogger("minder.api-gateway")

# Initialize FastAPI app
app = FastAPI(
    title="Minder API Gateway",
    description="Central API Gateway for Minder Platform",
    version="2.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Include AI integration router
app.include_router(ai_router)

# ============================================================================
# Prometheus Metrics
# ============================================================================

# HTTP request metrics
http_requests_total = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "endpoint", "status"]
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds", "HTTP request latency", ["method", "endpoint"]
)

http_requests_in_progress = Gauge(
    "http_requests_in_progress", "HTTP requests currently in progress", ["method", "endpoint"]
)

# Service health metrics
service_health_up = Gauge("service_health_up", "Service health status (1=up, 0=down)", ["service"])

active_plugins_gauge = Gauge("active_plugins_total", "Number of active plugins")

# ============================================================================
# Middleware Configuration
# ============================================================================

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure properly for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# Infrastructure Clients
# ============================================================================

# Redis client for rate limiting and caching
redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    password=settings.REDIS_PASSWORD,
    decode_responses=True,
    db=0,
)

# HTTP client for proxying requests (with connection pooling)
http_client = httpx.AsyncClient(
    limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
    timeout=httpx.Timeout(30.0, connect=10.0),
)

# Service registry
SERVICE_REGISTRY = {
    "plugin_registry": settings.PLUGIN_REGISTRY_URL,
    "rag_pipeline": settings.RAG_PIPELINE_URL,
    "model_management": settings.MODEL_MANAGEMENT_URL,
}

# ============================================================================
# Request ID Middleware
# ============================================================================


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Add unique request ID to each request for distributed tracing"""
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id
    request.state.start_time = time.time()

    # Update metrics
    endpoint = request.url.path
    method = request.method
    http_requests_in_progress.labels(method=method, endpoint=endpoint).inc()

    response = await call_next(request)

    # Calculate request duration
    duration = time.time() - request.state.start_time

    # Update metrics
    http_requests_in_progress.labels(method=method, endpoint=endpoint).dec()
    http_requests_total.labels(method=method, endpoint=endpoint, status=response.status_code).inc()
    http_request_duration_seconds.labels(method=method, endpoint=endpoint).observe(duration)

    # Add request ID to response headers
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time"] = f"{duration*1000:.2f}ms"

    return response


# ============================================================================
# Rate Limiting Middleware
# ============================================================================

if settings.RATE_LIMIT_ENABLED:
    from slowapi import Limiter
    from slowapi.util import get_remote_address

    limiter = Limiter(key_func=get_remote_address)
    app.state.limiter = limiter

    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        """Apply rate limiting based on user IP or JWT token"""
        # Skip rate limiting for health checks
        if request.url.path == "/health":
            return await call_next(request)

        # Get identifier (JWT token subject or IP address)
        identifier = get_remote_address(request)

        # Check rate limit in Redis
        key = f"ratelimit:{identifier}"
        current = redis_client.get(key)

        if current is None:
            # First request in window
            redis_client.setex(key, 60, 1)
        else:
            count = int(current)
            if count >= settings.RATE_LIMIT_PER_MINUTE:
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "Rate limit exceeded",
                        "limit": settings.RATE_LIMIT_PER_MINUTE,
                        "window": "60 seconds",
                    },
                )
            redis_client.incr(key)

        return await call_next(request)


# ============================================================================
# Health Check
# ============================================================================


@app.get("/health")
async def health_check():
    """
    Health check endpoint with phase-aware downstream service status
    """
    health_status = {
        "service": "api-gateway",
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "2.1.0",
        "environment": settings.ENVIRONMENT,
        "phase": settings.MINDER_PHASE,
        "checks": {},
    }

    # Define critical services for each phase
    PHASE_1_SERVICES = ["redis", "plugin_registry"]
    PHASE_2_SERVICES = ["rag_pipeline", "model_management"]

    # All services to check
    ALL_SERVICES = {
        "redis": ("redis", lambda: redis_client.ping()),
        "plugin_registry": (
            settings.PLUGIN_REGISTRY_URL,
            lambda: http_client.get(f"{settings.PLUGIN_REGISTRY_URL}/health", timeout=5.0),
        ),
        "rag_pipeline": (
            settings.RAG_PIPELINE_URL,
            lambda: http_client.get(f"{settings.RAG_PIPELINE_URL}/health", timeout=5.0),
        ),
        "model_management": (
            settings.MODEL_MANAGEMENT_URL,
            lambda: http_client.get(f"{settings.MODEL_MANAGEMENT_URL}/health", timeout=5.0),
        ),
    }

    # Determine which services are critical for current phase
    if settings.MINDER_PHASE == 1:
        critical_services = PHASE_1_SERVICES
    elif settings.MINDER_PHASE >= 2:
        critical_services = PHASE_1_SERVICES + PHASE_2_SERVICES
    else:
        critical_services = PHASE_1_SERVICES

    # In Phase 1, only check critical services to avoid "degraded" status
    services_to_check = (
        {k: v for k, v in ALL_SERVICES.items() if k in critical_services}
        if settings.MINDER_PHASE == 1
        else ALL_SERVICES
    )

    # Check only services relevant to current phase
    critical_unhealthy = False
    optional_unhealthy = False

    for service_name, (service_url, check_func) in services_to_check.items():
        try:
            if service_name == "redis":
                # Redis check
                check_func()
                health_status["checks"][service_name] = "healthy"
            else:
                # HTTP service check
                response = await check_func()
                if response.status_code == 200:
                    health_status["checks"][service_name] = "healthy"
                else:
                    health_status["checks"][
                        service_name
                    ] = f"unhealthy: HTTP {response.status_code}"
                    if service_name in critical_services:
                        critical_unhealthy = True
                    else:
                        optional_unhealthy = True
        except Exception as e:
            # Provide meaningful error messages
            error_type = type(e).__name__
            if error_type == "ReadTimeout":
                error_msg = "timeout after 5.0s"
            elif error_type == "ConnectError":
                error_msg = "connection refused"
            elif error_type == "ConnectTimeout":
                error_msg = "connection timeout"
            else:
                error_msg = str(e) if str(e) else error_type

            health_status["checks"][service_name] = f"unreachable: {error_msg}"
            if service_name in critical_services:
                critical_unhealthy = True
            else:
                optional_unhealthy = True

    # Determine overall status based on critical services
    if critical_unhealthy:
        health_status["status"] = "unhealthy"
        status_code = 503
    elif optional_unhealthy:
        # Only degraded if optional services are unhealthy
        health_status["status"] = "degraded"
        health_status["message"] = (
            f"Phase {settings.MINDER_PHASE} active - Phase 2 services not started"
        )
        status_code = 200  # Degraded is still functional, return 200
    else:
        health_status["status"] = "healthy"
        status_code = 200

    return JSONResponse(status_code=status_code, content=health_status)


@app.get("/metrics")
async def metrics():
    """
    Prometheus metrics endpoint
    """
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ============================================================================
# JWT Authentication
# ============================================================================


def create_jwt_token(data: Dict) -> str:
    """Create JWT access token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=settings.JWT_EXPIRATION_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def verify_jwt_token(token: str) -> Dict:
    """Verify and decode JWT token"""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


# Optional: Authentication dependency for protected routes
async def get_current_user(request: Request):
    """Get current user from JWT token (if present)"""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None

    token = auth_header.split(" ")[1]
    payload = verify_jwt_token(token)
    return payload


# ============================================================================
# Authentication Endpoints
# ============================================================================


@app.post("/v1/auth/login")
async def login(request: Request):
    """
    Login endpoint - accepts username/password, returns JWT token
    TODO: Integrate with real user database
    """
    body = await request.json()
    username = body.get("username")
    password = body.get("password")

    # TODO: Real authentication against database
    # For now, accept any non-empty username/password
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password required")

    # Create JWT token
    token_data = {"sub": username, "username": username, "iat": datetime.utcnow()}
    access_token = create_jwt_token(token_data)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": settings.JWT_EXPIRATION_MINUTES * 60,
        "user": {"username": username},
    }


@app.post("/v1/auth/refresh")
async def refresh_token(request: Request):
    """
    Refresh JWT token
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token required")

    token = auth_header.split(" ")[1]
    payload = verify_jwt_token(token)

    # Create new token
    token_data = {
        "sub": payload.get("sub"),
        "username": payload.get("username"),
        "iat": datetime.utcnow(),
    }
    access_token = create_jwt_token(token_data)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": settings.JWT_EXPIRATION_MINUTES * 60,
    }


# ============================================================================
# Request Proxying
# ============================================================================


async def proxy_request(service_url: str, path: str, request: Request):
    """
    Proxy request to downstream service
    """
    # Build target URL (handle trailing slash properly)
    if path:
        target_url = f"{service_url}/{path}"
    else:
        target_url = service_url

    # Get request body
    body = await request.body()

    # Build headers (excluding hop-by-hop headers)
    headers = dict(request.headers)
    headers.pop("host", None)
    headers.pop("connection", None)
    headers["X-Forwarded-For"] = request.client.host
    headers["X-Request-ID"] = request.state.request_id

    # Proxy request
    try:
        response = await http_client.request(
            method=request.method,
            url=target_url,
            headers=headers,
            content=body,
            params=request.query_params,
        )

        return JSONResponse(
            status_code=response.status_code,
            content=response.json() if response.content else None,
            headers=dict(response.headers),
        )

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Downstream service timeout")
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Downstream service unreachable")
    except Exception as e:
        logger.error(f"Proxy error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal proxy error")


# ============================================================================
# API Routes - Plugin Registry
# ============================================================================


@app.get("/v1/plugins")
async def list_plugins(request: Request):
    """Proxy GET /v1/plugins to Plugin Registry"""
    service_url = SERVICE_REGISTRY.get("plugin_registry")
    return await proxy_request(service_url, "v1/plugins", request)


@app.api_route("/v1/plugins/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy_to_plugin_registry(path: str, request: Request):
    """
    Proxy all /v1/plugins/* requests to Plugin Registry service
    Authentication required for POST/PUT/DELETE/PATCH methods
    """
    # Require authentication for write operations
    if request.method in ["POST", "PUT", "DELETE", "PATCH"]:
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Authentication required")

        token = auth_header.split(" ")[1]
        try:
            payload = verify_jwt_token(token)
            # Add user info to headers for downstream services
            request.state.user = payload
        except HTTPException:
            raise

    service_url = SERVICE_REGISTRY.get("plugin_registry")
    return await proxy_request(service_url, f"v1/plugins/{path}", request)


# ============================================================================
# API Routes - RAG Pipeline
# ============================================================================


@app.api_route("/v1/rag/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy_to_rag_pipeline(path: str, request: Request):
    """
    Proxy all /v1/rag/* requests to RAG Pipeline service
    """
    service_url = SERVICE_REGISTRY.get("rag_pipeline")
    return await proxy_request(service_url, f"rag/{path}", request)


# ============================================================================
# API Routes - Model Management
# ============================================================================


@app.api_route("/v1/models/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy_to_model_management(path: str, request: Request):
    """
    Proxy all /v1/models/* requests to Model Management service
    """
    service_url = SERVICE_REGISTRY.get("model_management")
    return await proxy_request(service_url, f"models/{path}", request)


# ============================================================================
# Startup/Shutdown Events
# ============================================================================


@app.on_event("startup")
async def startup_event():
    """Initialize connections on startup"""
    logger.info("API Gateway starting...")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Service Registry: {SERVICE_REGISTRY}")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("API Gateway shutting down...")
    await http_client.aclose()
    redis_client.close()


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)  # nosec: B104
