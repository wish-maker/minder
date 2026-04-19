from pathlib import Path
from typing import Optional, Dict, Any
import yaml
import os
import logging

logger = logging.getLogger(__name__)


class BaseConfig:
    """Base configuration class for all services"""

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or Path("/app/config.yaml")
        self.config_data: Dict[str, Any] = {}
        if self.config_path.exists():
            self._load_config()

    def _load_config(self):
        """Load YAML configuration"""
        try:
            with open(self.config_path) as f:
                self.config_data = yaml.safe_load(f) or {}
        except FileNotFoundError:
            logger.warning(f"Config file not found: {self.config_path}")
            self.config_data = {}
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in config file {self.config_path}: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """Get config value with env override"""
        # Check environment variable first
        env_key = key.upper().replace(".", "_")
        if env_key in os.environ:
            return os.environ[env_key]

        # Check config file
        keys = key.split(".")
        value = self.config_data
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        return value if value is not None else default

    @property
    def postgres_url(self) -> str:
        """Get PostgreSQL connection URL"""
        host = self.get("database.host", "postgres")
        port = self.get("database.port", 5432)
        user = self.get("database.user", "postgres")
        password = self.get("database.password", "postgres")
        return f"postgresql://{user}:{password}@{host}:{port}"

    @property
    def redis_url(self) -> str:
        """Get Redis connection URL"""
        host = self.get("redis.host", "redis")
        port = self.get("redis.port", 6379)
        return f"redis://{host}:{port}"
