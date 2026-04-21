from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import uvicorn
import os
import asyncio
from shared.models.common import HealthResponse, ServiceStatus
from shared.config.base import BaseConfig
from shared.utils.logging import setup_logger
from shared.database.postgres import PostgresHelper
from shared.database.redis import RedisHelper

# Configuration
SERVICE_NAME = os.getenv("SERVICE_NAME", "template-service")
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8000"))
config = BaseConfig()
logger = setup_logger(SERVICE_NAME)

# Initialize FastAPI
app = FastAPI(
    title=SERVICE_NAME.replace("-", " ").title(),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Database connections (will be initialized on startup)
postgres: PostgresHelper = None
redis: RedisHelper = None

@app.on_event("startup")
async def startup():
    """Initialize service connections"""
    global postgres, redis

    logger.info(f"Starting {SERVICE_NAME}...")

    # Connect to PostgreSQL
    postgres = PostgresHelper(
        dsn=config.postgres_url,
        schema=os.getenv("DB_SCHEMA", "public")
    )
    await postgres.connect()
    await postgres.init_schema()

    # Connect to Redis
    redis = RedisHelper(url=config.redis_url)
    await redis.connect()

    logger.info(f"{SERVICE_NAME} started successfully")

@app.on_event("shutdown")
async def shutdown():
    """Cleanup service connections"""
    global postgres, redis

    logger.info(f"Shutting down {SERVICE_NAME}...")

    if postgres:
        await postgres.disconnect()

    if redis:
        await redis.disconnect()

    logger.info(f"{SERVICE_NAME} shutdown complete")

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        service=SERVICE_NAME,
        status=ServiceStatus.HEALTHY,
        uptime_seconds=0.0,  # TODO: implement uptime tracking
        details={"version": "1.0.0"}
    )

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": SERVICE_NAME,
        "status": "running",
        "docs": "/docs"
    }

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=SERVICE_PORT,
        reload=os.getenv("ENVIRONMENT") == "development",
        log_level="info"
    )
