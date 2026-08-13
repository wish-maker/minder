"""Unit tests for shared.config.base_settings.MinderBaseSettings.

MinderBaseSettings makes DB_PASSWORD / REDIS_PASSWORD / JWT_SECRET REQUIRED (no
defaults) + rejects empty strings, so adopting it hardens a service against booting
with a placeholder secret (#49/#223). That guarantee was only exercised indirectly
via each service's conftest; these test it directly.

`_env_file=None` disables .env discovery so a stray .env in the working directory
can't supply a value; init kwargs override the ambient environment.
"""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from shared.config.base_settings import MinderBaseSettings  # noqa: E402

_SECRETS = dict(DB_PASSWORD="dbpw", REDIS_PASSWORD="rpw", JWT_SECRET="jwtsecret")


def test_loads_with_all_secrets_and_sane_defaults():
    s = MinderBaseSettings(_env_file=None, **_SECRETS)
    assert s.DB_PASSWORD == "dbpw"
    # Non-secret defaults come through unchanged.
    assert s.DB_PORT == 5432
    assert s.REDIS_PORT == 6379
    assert s.JWT_ALGORITHM == "HS256"
    assert s.JWT_EXPIRATION_MINUTES == 60
    assert s.ENVIRONMENT == "development"
    assert s.OLLAMA_HOST == "http://ollama:11434"
    assert s.GRAPH_RAG_URL.endswith(":8008")


def test_missing_required_secret_raises(monkeypatch):
    # Clear any ambient secret so the field is genuinely absent, then omit JWT_SECRET.
    for key in ("DB_PASSWORD", "REDIS_PASSWORD", "JWT_SECRET"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(ValidationError) as exc:
        MinderBaseSettings(_env_file=None, DB_PASSWORD="x", REDIS_PASSWORD="x")
    assert "JWT_SECRET" in str(exc.value)


@pytest.mark.parametrize("field", ["DB_PASSWORD", "REDIS_PASSWORD", "JWT_SECRET"])
def test_empty_secret_rejected(field):
    # An explicitly-empty secret (init kwarg overrides env) trips the validator.
    kwargs = {**_SECRETS, field: ""}
    with pytest.raises(ValidationError) as exc:
        MinderBaseSettings(_env_file=None, **kwargs)
    assert field in str(exc.value)


def test_extra_service_specific_fields_are_allowed():
    # model_config extra="allow" — a subclassing service's own field passes through.
    s = MinderBaseSettings(_env_file=None, SERVICE_SPECIFIC="value", **_SECRETS)
    assert s.SERVICE_SPECIFIC == "value"


def test_env_overrides_default(monkeypatch):
    monkeypatch.setenv("DB_PORT", "6000")
    monkeypatch.setenv("ENVIRONMENT", "production")
    s = MinderBaseSettings(_env_file=None, **_SECRETS)
    assert s.DB_PORT == 6000
    assert s.ENVIRONMENT == "production"
