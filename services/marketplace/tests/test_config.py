# services/marketplace/tests/test_config.py
import os


def test_config_loads_from_environment():
    """Test that configuration loads from environment variables"""
    # Set environment variables
    os.environ["MARKETPLACE_HOST"] = "0.0.0.0"
    os.environ["MARKETPLACE_PORT"] = "8002"
    os.environ["MARKETPLACE_DATABASE_HOST"] = "minder-postgres"
    os.environ["MARKETPLACE_REDIS_HOST"] = "minder-redis"

    # Import config
    from services.marketplace.config import settings

    # Verify settings
    assert settings.MARKETPLACE_HOST == "0.0.0.0"
    assert settings.MARKETPLACE_PORT == 8002
    assert settings.MARKETPLACE_DATABASE_HOST == "minder-postgres"
    assert settings.MARKETPLACE_REDIS_HOST == "minder-redis"
    assert settings.LOG_LEVEL == "INFO"
    assert settings.ENVIRONMENT == "development"


def test_config_has_required_defaults():
    """Test that configuration has sensible defaults"""
    from services.marketplace.config import settings

    # Required settings should have defaults
    assert hasattr(settings, "MARKETPLACE_HOST")
    assert hasattr(settings, "MARKETPLACE_PORT")
    assert hasattr(settings, "MARKETPLACE_DATABASE_HOST")
    assert hasattr(settings, "MARKETPLACE_REDIS_HOST")
    assert hasattr(settings, "LICENSE_SECRET")
