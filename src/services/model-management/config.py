"""Centralized settings for the Model Management service.

Single source of truth for the service's environment configuration, replacing the
`os.getenv` calls that were previously scattered across main.py and core/. This
service talks only to Ollama (no DB/Redis/JWT), so it uses a plain BaseSettings
rather than shared.config.MinderBaseSettings — adopting the base would force the
required DB_PASSWORD/REDIS_PASSWORD/JWT_SECRET secrets it does not use.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    # Ollama runtime host. Empty/remote handling matches the platform's
    # OLLAMA_HOST convention (see docs); default targets the internal container.
    OLLAMA_HOST: str = "http://ollama:11434"
    # Caps concurrent `POST /v1/models` pulls (#679): each pull can be many GB
    # with zero disk-space check, so unbounded concurrent pulls race to fill
    # the shared Ollama volume and can take down inference for everyone. 1
    # serializes pulls entirely -- the simplest safe default when custom
    # registries/multi-pull throughput aren't an established need.
    MAX_CONCURRENT_MODEL_PULLS: int = 1

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
