"""
Unit tests for CORS utilities
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.shared.utils.cors import (
    add_cors_middleware,
    add_cors_from_string,
)


class TestAddCORSMiddleware:
    """Test add_cors_middleware function"""

    def test_add_cors_with_default_origins(self):
        """Test CORS middleware with default origins"""
        app = FastAPI()

        @app.get("/test")
        async def test_endpoint():
            return {"message": "test"}

        add_cors_middleware(app)

        client = TestClient(app)

        # Test preflight request
        response = client.options(
            "/test",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            }
        )

        assert response.status_code == 200
        assert "access-control-allow-origin" in response.headers

    def test_add_cors_with_custom_origins(self):
        """Test CORS middleware with custom origins"""
        app = FastAPI()

        @app.get("/test")
        async def test_endpoint():
            return {"message": "test"}

        add_cors_middleware(
            app,
            allowed_origins=["http://example.com", "https://example.com"]
        )

        client = TestClient(app)

        # Test preflight from allowed origin
        response = client.options(
            "/test",
            headers={
                "Origin": "http://example.com",
                "Access-Control-Request-Method": "GET",
            }
        )

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "http://example.com"

    def test_add_cors_with_credentials(self):
        """Test CORS middleware with credentials enabled"""
        app = FastAPI()

        @app.get("/test")
        async def test_endpoint():
            return {"message": "test"}

        add_cors_middleware(
            app,
            allowed_origins=["http://localhost:3000"],
            allow_credentials=True
        )

        client = TestClient(app)

        response = client.options(
            "/test",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            }
        )

        assert response.status_code == 200
        assert response.headers.get("access-control-allow-credentials") == "true"

    def test_add_cors_with_custom_methods(self):
        """Test CORS middleware with custom methods"""
        app = FastAPI()

        @app.get("/test")
        async def test_endpoint():
            return {"message": "test"}

        add_cors_middleware(
            app,
            allowed_origins=["http://localhost:3000"],
            allow_methods=["GET", "POST"]
        )

        client = TestClient(app)

        response = client.options(
            "/test",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            }
        )

        assert response.status_code == 200
        assert "get" in response.headers.get("access-control-allow-methods", "").lower()

    def test_add_cors_with_custom_headers(self):
        """Test CORS middleware with custom headers"""
        app = FastAPI()

        @app.get("/test")
        async def test_endpoint():
            return {"message": "test"}

        add_cors_middleware(
            app,
            allowed_origins=["http://localhost:3000"],
            allow_headers=["Content-Type", "Authorization"]
        )

        client = TestClient(app)

        response = client.options(
            "/test",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Content-Type, Authorization",
            }
        )

        assert response.status_code == 200

    def test_add_cors_blocks_disallowed_origin(self):
        """Test CORS middleware blocks disallowed origin"""
        app = FastAPI()

        @app.get("/test")
        async def test_endpoint():
            return {"message": "test"}

        add_cors_middleware(
            app,
            allowed_origins=["http://localhost:3000"]
        )

        client = TestClient(app)

        # Test request from disallowed origin
        response = client.get(
            "/test",
            headers={"Origin": "http://evil.com"}
        )

        # Request should succeed but no CORS headers
        assert response.status_code == 200
        assert "access-control-allow-origin" not in response.headers


class TestAddCORSFromString:
    """Test add_cors_from_string function"""

    def test_add_cors_from_single_string(self):
        """Test CORS from comma-separated string with single origin"""
        app = FastAPI()

        @app.get("/test")
        async def test_endpoint():
            return {"message": "test"}

        add_cors_from_string(app, "http://localhost:3000")

        client = TestClient(app)

        response = client.options(
            "/test",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            }
        )

        assert response.status_code == 200
        assert "access-control-allow-origin" in response.headers

    def test_add_cors_from_multiple_origins(self):
        """Test CORS from comma-separated string with multiple origins"""
        app = FastAPI()

        @app.get("/test")
        async def test_endpoint():
            return {"message": "test"}

        add_cors_from_string(
            app,
            "http://localhost:3000,http://localhost:8000,https://example.com"
        )

        client = TestClient(app)

        # Test each origin
        for origin in ["http://localhost:3000", "http://localhost:8000", "https://example.com"]:
            response = client.options(
                "/test",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "GET",
                }
            )

            assert response.status_code == 200
            assert "access-control-allow-origin" in response.headers

    def test_add_cors_from_string_with_spaces(self):
        """Test CORS from string with extra spaces"""
        app = FastAPI()

        @app.get("/test")
        async def test_endpoint():
            return {"message": "test"}

        add_cors_from_string(app, " http://localhost:3000 , http://localhost:8000 ")

        client = TestClient(app)

        response = client.options(
            "/test",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            }
        )

        assert response.status_code == 200

    def test_add_cors_from_empty_string(self):
        """Test CORS from empty string (should use defaults)"""
        app = FastAPI()

        @app.get("/test")
        async def test_endpoint():
            return {"message": "test"}

        add_cors_from_string(app, "")

        client = TestClient(app)

        # Should use default origins
        response = client.options(
            "/test",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            }
        )

        assert response.status_code == 200
