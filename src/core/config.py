"""
Minder Configuration Management
Version: 1.0.0

Single source of truth for all Minder configuration.
Uses Pydantic for validation and type safety.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings


class DatabaseConfig(BaseModel):
    """Database connection configuration"""

    host: str = "localhost"
    port: int = 5432
    user: str = "postgres"
    password: str = ""  # Load from environment

    # Model-specific databases
    fundmind_db: str = "fundmind"
    news_db: str = "minder_news"
    weather_db: str = "minder_weather"
    crypto_db: str = "minder_crypto"
    network_db: str = "minder_network"


class InfluxDBConfig(BaseModel):
    """InfluxDB configuration"""

    host: str = "influxdb"
    port: int = 8086
    database: str = "minder"
    username: str = "minder"
    password: str = "minder123"


class QdrantConfig(BaseModel):
    """Qdrant vector database configuration"""

    host: str = "qdrant"
    port: int = 6333
    collection_prefix: str = "minder"


class RedisConfig(BaseModel):
    """Redis configuration"""

    host: str = "localhost"
    port: int = 6379
    db: int = 0


class PluginConfig(BaseModel):
    """Base plugin configuration"""

    enabled: bool = True
    priority: str = "medium"  # high, medium, low
    health_check_interval: int = 300  # seconds
    failure_threshold: int = 3
    auto_restart: bool = True


class TefasPluginConfig(PluginConfig):
    """TEFAS plugin specific configuration"""

    historical_start_date: str = "2020-01-01"
    batch_days: int = 30
    fund_types: List[str] = ["YAT", "EMK", "BYF"]


class NetworkPluginConfig(PluginConfig):
    """Network plugin specific configuration"""

    interfaces: List[str] = ["eth0", "wlan0"]
    collection_interval: int = 60


class WeatherPluginConfig(PluginConfig):
    """Weather plugin specific configuration"""

    api_source: str = "open-meteo"
    locations: List[str] = ["Istanbul", "Ankara", "Izmir"]


class CryptoPluginConfig(PluginConfig):
    """Crypto plugin specific configuration"""

    symbols: List[str] = ["BTC", "ETH", "USDT", "BNB", "XRP"]
    cache_ttl: int = 300  # 5 minutes


class NewsPluginConfig(PluginConfig):
    """News plugin specific configuration"""

    sources: List[str] = ["bbc", "guardian", "npr"]
    max_articles: int = 10


class PluginsConfig(BaseModel):
    """All plugins configuration"""

    tefas: TefasPluginConfig = Field(default_factory=TefasPluginConfig)
    network: NetworkPluginConfig = Field(default_factory=NetworkPluginConfig)
    weather: WeatherPluginConfig = Field(default_factory=WeatherPluginConfig)
    crypto: CryptoPluginConfig = Field(default_factory=CryptoPluginConfig)
    news: NewsPluginConfig = Field(default_factory=NewsPluginConfig)

    # Activation policy
    activation_strategy: str = "gradual"  # gradual, immediate, manual
    startup_timeout: int = 60  # seconds


class SecurityConfig(BaseModel):
    """Security configuration"""

    jwt_secret_key: str = ""  # Load from environment (min 32 chars)
    jwt_expire_minutes: int = 30

    # Rate limiting
    rate_limit_enabled: bool = True
    rate_limit_local: str = "unlimited"
    rate_limit_vpn: int = 200  # requests/hour
    rate_limit_public: int = 50  # requests/hour

    # Network detection
    local_network_cidr: str = "192.168.68.0/24"
    tailscale_cidr: str = "100.64.0.0/10"
    trust_local_network: bool = True
    trust_vpn_network: bool = True

    # CORS
    allowed_origins: List[str] = [
        "http://localhost:3000",
        "http://192.168.68.*",
        "http://100.*.*.*",
    ]

    @field_validator("jwt_secret_key")
    def validate_jwt_secret(cls, v):
        if len(v) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters")
        return v


class PluginStoreConfig(BaseModel):
    """Plugin store configuration"""

    enabled: bool = True
    store_path: str = "/var/lib/minder/plugins"
    index_url: str = (
        "https://raw.githubusercontent.com/minder-plugins/plugin-index/main/plugins.json"
    )
    github_token: str = ""  # Optional

    # Security
    require_signature: bool = False
    allow_unsigned: bool = True
    scan_for_malware: bool = False

    # Auto-update
    auto_update: bool = False
    update_interval: int = 86400  # 24 hours


class LoggingConfig(BaseModel):
    """Logging configuration"""

    level: str = "INFO"
    file: str = "/var/log/minder/minder.log"
    rotation: str = "daily"
    retention: int = 30  # days


class PerformanceConfig(BaseModel):
    """Performance configuration"""

    max_workers: int = 4
    batch_size: int = 100
    cache_ttl: int = 3600  # 1 hour
    max_event_history: int = 10000


class VoiceConfig(BaseModel):
    """Voice interface configuration"""

    enabled: bool = True
    stt_model: str = "whisper-medium"
    tts_model: str = "tts_models/multilingual/multi-dataset/xtts_v2"
    default_language: str = "tr"
    supported_languages: List[str] = ["tr", "en", "de", "fr", "es", "it"]


class CharacterConfig(BaseModel):
    """Character system configuration"""

    default: str = "finbot"
    custom_characters_path: str = "/var/lib/minder/characters"


class OpenWebUIConfig(BaseModel):
    """OpenWebUI integration configuration"""

    enabled: bool = True
    api_url: str = "http://openwebui:8080"
    agent_endpoint: str = "/api/agents/minder"


class MinderConfig(BaseSettings):
    """
    Main Minder Configuration

    Single source of truth for all configuration.
    Loads from config.yaml and environment variables.
    """

    # Kernel settings
    name: str = "minder"
    version: str = "1.0.0"
    environment: str = "production"

    # Databases
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    influxdb: InfluxDBConfig = Field(default_factory=InfluxDBConfig)
    qdrant: QdrantConfig = Field(default_factory=QdrantConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)

    # Plugins
    plugins: PluginsConfig = Field(default_factory=PluginsConfig)

    # Features
    voice: VoiceConfig = Field(default_factory=VoiceConfig)
    character: CharacterConfig = Field(default_factory=CharacterConfig)
    openwebui: OpenWebUIConfig = Field(default_factory=OpenWebUIConfig)

    # System
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    plugin_store: PluginStoreConfig = Field(default_factory=PluginStoreConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    performance: PerformanceConfig = Field(default_factory=PerformanceConfig)

    class Config:
        env_file = ".env"
        env_nested_delimiter = "__"
        case_sensitive = False

    @classmethod
    def load_yaml(cls, yaml_path: Path = None) -> "MinderConfig":
        """
        Load configuration from YAML file

        Args:
            yaml_path: Path to config.yaml (default: /root/minder/config/root/config.yaml)

        Returns:
            MinderConfig instance
        """
        if yaml_path is None:
            yaml_path = Path("/root/minder/config/root/config.yaml")

        if not yaml_path.exists():
            # Return default config if file doesn't exist
            return cls()

        import yaml

        with open(yaml_path) as f:
            yaml_data = yaml.safe_load(f)

        # Flatten nested structure for environment variable override
        # e.g., database.host -> DATABASE__HOST
        return cls(**yaml_data)

    def get_database_config(self, db_name: str) -> Dict[str, Any]:
        """
        Get database configuration for specific database

        Args:
            db_name: Name of database (fundmind, news, weather, crypto, network)

        Returns:
            Database connection parameters
        """
        db_mapping = {
            "fundmind": self.database.fundmind_db,
            "news": self.database.news_db,
            "weather": self.database.weather_db,
            "crypto": self.database.crypto_db,
            "network": self.database.network_db,
        }

        return {
            "host": self.database.host,
            "port": self.database.port,
            "database": db_mapping.get(db_name, db_name),
            "user": self.database.user,
            "password": self.database.password,
        }


# Global config instance
_config: Optional[MinderConfig] = None


def get_config() -> MinderConfig:
    """Get global configuration instance"""
    global _config
    if _config is None:
        _config = MinderConfig.load_yaml()
    return _config


def reload_config() -> MinderConfig:
    """Reload configuration from file"""
    global _config
    _config = MinderConfig.load_yaml()
    return _config
