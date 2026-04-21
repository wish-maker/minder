"""
Minder API Gateway
Central entry point for all API requests
Handles authentication, rate limiting, request routing, and logging
"""

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import httpx
import redis
from jose import jwt
from datetime import datetime, timedelta
from typing import Dict
import logging
import time
import uuid

from config import settings

# Configure logging
logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL))
logger = logging.getLogger("minder.api-gateway")

# Initialize FastAPI app
app = FastAPI(
    title="Minder API Gateway",
    description="Central API Gateway for Minder Platform",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

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
    host=settings.REDIS_HOST, port=settings.REDIS_PORT, password=settings.REDIS_PASSWORD, decode_responses=True, db=0
)

# HTTP client for proxying requests (with connection pooling)
http_client = httpx.AsyncClient(
    limits=httpx.Limits(max_connections=100, max_keepalive_connections=20), timeout=httpx.Timeout(30.0, connect=10.0)
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

    response = await call_next(request)

    # Add request ID to response headers
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time"] = f"{(time.time() - request.state.start_time)*1000:.2f}ms"

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
    Health check endpoint
    Returns status of API Gateway and downstream services
    """
    health_status = {
        "service": "api-gateway",
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "2.0.0",
        "environment": settings.ENVIRONMENT,
        "checks": {},
    }

    # Check Redis connection
    try:
        redis_client.ping()
        health_status["checks"]["redis"] = "healthy"
    except Exception as e:
        health_status["checks"]["redis"] = f"unhealthy: {str(e)}"
        health_status["status"] = "degraded"

    # Check downstream services (optional - may slow down health check)
    for service_name, service_url in SERVICE_REGISTRY.items():
        try:
            response = await http_client.get(f"{service_url}/health", timeout=2.0)
            if response.status_code == 200:
                health_status["checks"][service_name] = "healthy"
            else:
                health_status["checks"][service_name] = f"unhealthy: status {response.status_code}"
                health_status["status"] = "degraded"
        except Exception as e:
            health_status["checks"][service_name] = f"unreachable: {str(e)}"
            health_status["status"] = "degraded"

    status_code = 200 if health_status["status"] == "healthy" else 503
    return JSONResponse(status_code=status_code, content=health_status)


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
    token_data = {"sub": payload.get("sub"), "username": payload.get("username"), "iat": datetime.utcnow()}
    access_token = create_jwt_token(token_data)

    return {"access_token": access_token, "token_type": "bearer", "expires_in": settings.JWT_EXPIRATION_MINUTES * 60}


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
            method=request.method, url=target_url, headers=headers, content=body, params=request.query_params
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
    """
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

    uvicorn.run(app, host="0.0.0.0", port=8000)
