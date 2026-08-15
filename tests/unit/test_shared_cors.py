"""Unit tests for the shared CORS helper's env-string parsing.

add_cors_from_string() previously had zero callers (dead code) while api-gateway and
marketplace each hand-rolled the identical "split env string, or fall back to a
default list" ternary inline. Gave it a `default_origins` param and wired both
services to it instead, removing the duplication. These tests guard that parsing.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from shared.utils.cors import add_cors_from_string, add_cors_middleware


def _installed_origins(app: FastAPI):
    for middleware in app.user_middleware:
        if middleware.cls is CORSMiddleware:
            return middleware.kwargs["allow_origins"]
    raise AssertionError("CORSMiddleware was not installed")


def _installed_kwargs(app: FastAPI):
    for middleware in app.user_middleware:
        if middleware.cls is CORSMiddleware:
            return middleware.kwargs
    raise AssertionError("CORSMiddleware was not installed")


def test_parses_comma_separated_string():
    app = FastAPI()
    add_cors_from_string(app, "http://a.test,http://b.test")
    assert _installed_origins(app) == ["http://a.test", "http://b.test"]


def test_strips_whitespace_around_entries():
    app = FastAPI()
    add_cors_from_string(app, "http://a.test, http://b.test , http://c.test")
    assert _installed_origins(app) == [
        "http://a.test",
        "http://b.test",
        "http://c.test",
    ]


def test_empty_string_falls_back_to_default_origins():
    app = FastAPI()
    add_cors_from_string(app, "", default_origins=["http://dev.test"])
    assert _installed_origins(app) == ["http://dev.test"]


def test_none_falls_back_to_default_origins():
    app = FastAPI()
    add_cors_from_string(app, None, default_origins=["*"])
    assert _installed_origins(app) == ["*"]


def test_unset_with_no_default_falls_back_to_add_cors_middleware_default():
    app = FastAPI()
    add_cors_from_string(app, None)
    origins = _installed_origins(app)
    assert "http://localhost:3000" in origins  # add_cors_middleware's own dev default


# --- wildcard-origin + credentials refusal -----------------------------------
#
# Found in a background audit: Starlette's CORSMiddleware doesn't send a
# literal `*` when allow_credentials=True is paired with a wildcard origin --
# it reflects the request's actual Origin header back explicitly plus
# Access-Control-Allow-Credentials: true. That lets any arbitrary site's JS
# issue a credentialed cross-origin request and have the browser attach/read
# back cookies -- a footgun baked into infrastructure every service reuses.


def test_wildcard_origin_forces_credentials_off():
    app = FastAPI()
    add_cors_middleware(app, allowed_origins=["*"], allow_credentials=True)
    kwargs = _installed_kwargs(app)
    assert kwargs["allow_origins"] == ["*"]
    assert kwargs["allow_credentials"] is False


def test_explicit_origins_with_credentials_still_allowed():
    app = FastAPI()
    add_cors_middleware(app, allowed_origins=["http://a.test"], allow_credentials=True)
    kwargs = _installed_kwargs(app)
    assert kwargs["allow_credentials"] is True


def test_add_cors_from_string_wildcard_default_forces_credentials_off():
    """api-gateway's actual default (CORS_ALLOWED_ORIGINS="*", #config.py) --
    confirm the refusal applies through this call path too, not just the
    lower-level add_cors_middleware."""
    app = FastAPI()
    add_cors_from_string(app, None, default_origins=["*"])
    kwargs = _installed_kwargs(app)
    assert kwargs["allow_origins"] == ["*"]
    assert kwargs["allow_credentials"] is False
