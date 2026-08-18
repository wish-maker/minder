"""Unit tests for MarketplaceSettings' NEO4J_AUTH field validator.

check_neo4j_auth's `raise ValueError` branch (an explicitly empty string, as
opposed to the field simply being absent -- pydantic's own required-field
check already covers that case) had never been exercised.

Loaded via spec_from_file_location with a unique module name (not "config")
so it never collides with the "config" module name every other service's
own config.py shares in this shared pytest process.
"""

import importlib.util
import os
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

_SERVICE_DIR = Path(__file__).resolve().parents[2] / "src" / "services" / "marketplace"
_CONFIG_FILE = _SERVICE_DIR / "config.py"


def _load_marketplace_settings_class():
    saved_path = list(sys.path)
    sys.path.insert(0, str(_SERVICE_DIR))
    # The module's own `settings = MarketplaceSettings()` singleton (built from
    # the real environment) executes at import time -- these are only needed to
    # get past THAT construction; the tests below build their own instances
    # with explicit kwargs regardless.
    os.environ.setdefault("DB_PASSWORD", "test")
    os.environ.setdefault("REDIS_PASSWORD", "test")
    os.environ.setdefault("JWT_SECRET", "test")
    os.environ.setdefault("NEO4J_AUTH", "neo4j/test")
    try:
        spec = importlib.util.spec_from_file_location(
            "marketplace_config_under_test", _CONFIG_FILE
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.MarketplaceSettings
    finally:
        sys.path[:] = saved_path


MarketplaceSettings = _load_marketplace_settings_class()

_SECRETS = dict(
    DB_PASSWORD="dbpw",
    REDIS_PASSWORD="rpw",
    JWT_SECRET="jwtsecret",
)


def test_rejects_an_explicitly_empty_neo4j_auth():
    with pytest.raises(ValidationError) as exc:
        MarketplaceSettings(_env_file=None, NEO4J_AUTH="", **_SECRETS)
    assert "NEO4J_AUTH must be set" in str(exc.value)


def test_accepts_a_valid_neo4j_auth():
    s = MarketplaceSettings(_env_file=None, NEO4J_AUTH="neo4j/password", **_SECRETS)
    assert s.NEO4J_AUTH == "neo4j/password"
