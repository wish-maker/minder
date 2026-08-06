"""Unit tests for the shared CORS helper's env-string parsing.

add_cors_from_string() previously had zero callers (dead code) while api-gateway and
marketplace each hand-rolled the identical "split env string, or fall back to a
default list" ternary inline. Gave it a `default_origins` param and wired both
services to it instead, removing the duplication. These tests guard that parsing.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from shared.utils.cors import add_cors_from_string


def _installed_origins(app: FastAPI):
    for middleware in app.user_middleware:
        if middleware.cls is CORSMiddleware:
            return middleware.kwargs["allow_origins"]
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
