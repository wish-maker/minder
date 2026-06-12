"""
Minder AI Services (Unified) - Configuration
Combines RAG Pipeline, Model Management, and TTS/STT
"""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings"""

    # Database
    database_url: str = "postgresql://minder:minder@postgres:5432/minder"

    # Redis
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 0

    # Ollama
    ollama_host: str = "http://ollama:11434"
    ollama_embedding_model: str = "nomic-embed-text"
    ollama_llm_model: str = "llama3.2"

    # Qdrant (Vector DB)
    qdrant_host: str = "qdrant"
    qdrant_port: int = 6333

    # API Settings
    api_title: str = "Minder AI Services (Unified)"
    api_version: str = "2.1.0"
    environment: str = "production"

    # CORS
    cors_origins: list = ["http://localhost:3000", "http://localhost:8080"]

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()
