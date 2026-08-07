# services/marketplace/tests/test_config.py
import sys


def test_config_loads_from_environment(monkeypatch):
    """Test that configuration loads from environment variables.

    #357: this used to mutate os.environ directly (no cleanup) -- DB_HOST/
    REDIS_HOST leaked "minder-postgres"/"minder-redis" (docker-compose
    hostnames, unresolvable outside that network) into every later test in
    the same pytest session, causing real DNS failures in tests/integration/
    (test_auth_e2e.py, test_marketplace_main.py, and any test building a
    fresh Settings/redis client afterward). monkeypatch.setenv() restores
    the prior values automatically when this test ends.

    Also: `services.marketplace.config` may already be cached in
    sys.modules by the time this runs (test_marketplace_ai_tools_importer.py
    collects first, alphabetically, and imports
    services.marketplace.core.ai_tools_importer) -- a plain `import` then
    silently returns the STALE cached `settings` object built from whatever
    env vars were live at that earlier, unrelated import, so this test's own
    env changes would have no effect on the assertions below. Evict it first
    to force a genuinely fresh construction, then restore whatever was
    cached before so this test doesn't leak the reverse problem onto
    whichever test runs next.
    """
    monkeypatch.setenv("MARKETPLACE_HOST", "0.0.0.0")
    monkeypatch.setenv("MARKETPLACE_PORT", "8002")
    monkeypatch.setenv("DB_HOST", "minder-postgres")
    monkeypatch.setenv("REDIS_HOST", "minder-redis")

    saved = {
        key: sys.modules.pop(key)
        for key in list(sys.modules)
        if key == "services.marketplace.config"
    }
    try:
        from services.marketplace.config import settings

        # Verify settings
        assert settings.MARKETPLACE_HOST == "0.0.0.0"
        assert settings.MARKETPLACE_PORT == 8002
        assert settings.DB_HOST == "minder-postgres"
        assert settings.REDIS_HOST == "minder-redis"
        assert settings.LOG_LEVEL == "INFO"
        assert settings.ENVIRONMENT == "development"
    finally:
        sys.modules.pop("services.marketplace.config", None)
        sys.modules.update(saved)


def test_config_has_required_defaults():
    """Test that configuration has sensible defaults"""
    from services.marketplace.config import settings

    # Required settings should have defaults
    assert hasattr(settings, "MARKETPLACE_HOST")
    assert hasattr(settings, "MARKETPLACE_PORT")
    assert hasattr(settings, "DB_HOST")
    assert hasattr(settings, "REDIS_HOST")
    assert hasattr(settings, "LICENSE_SECRET")
