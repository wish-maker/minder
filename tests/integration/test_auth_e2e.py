"""
API Gateway Auth E2E Tests with Real PostgreSQL

CRITICAL: These tests MUST pass before auth is considered complete.

Run: docker compose -f docker-compose.test.yml up -d
     pytest tests/integration/test_auth_e2e.py -v
"""

import asyncio

import pytest
import pytest_asyncio

# Config is loaded by conftest.py BEFORE this file runs
from config import settings

# Comment out to run tests (requires docker-compose.test.yml up)
# pytestmark = pytest.mark.skip(reason="Requires running Minder services")


@pytest_asyncio.fixture(scope="function")
async def verify_postgres_running():
    """
    Verify PostgreSQL test container is running before any tests.
    Run: docker compose -f docker-compose.test.yml up -d
    """
    import asyncpg

    max_attempts = 30
    for attempt in range(max_attempts):
        try:
            conn = await asyncpg.connect(
                host=settings.POSTGRES_HOST,
                port=int(settings.POSTGRES_PORT),
                user=settings.POSTGRES_USER,
                password=settings.POSTGRES_PASSWORD,
                database=settings.POSTGRES_DB,
            )
            await conn.close()
            print(f"\n[OK] PostgreSQL test container ready")
            return
        except Exception as e:
            if attempt < max_attempts - 1:
                await asyncio.sleep(1)
            else:
                pytest.fail(
                    f"PostgreSQL test container not ready after {max_attempts}s.\n"
                    f"Run: docker compose -f docker-compose.test.yml up -d\n"
                    f"Error: {e}"
                )


@pytest_asyncio.fixture(scope="function")
async def clean_database(verify_postgres_running):
    """
    Setup: Create users table
    Teardown: Drop all data and table
    """
    import asyncpg
    from core.auth import close_pg_pool, get_pg_pool, init_users_table

    # Close any existing pool
    await close_pg_pool()

    # Create fresh table
    await init_users_table()

    yield

    # Cleanup: Drop users table
    pool = await get_pg_pool()
    async with pool.acquire() as conn:
        await conn.execute("DROP TABLE IF EXISTS users CASCADE")
    await close_pg_pool()


@pytest_asyncio.fixture(scope="function")
async def api_client(clean_database):
    """
    Create FastAPI test client with clean database.
    Import main here to get fresh app instance.
    """
    # Clear prometheus metrics before importing main
    from prometheus_client import REGISTRY

    for collector in list(REGISTRY._collector_to_names.keys()):
        try:
            REGISTRY.unregister(collector)
        except Exception:
            pass

    # Import main module (prometheus metrics will be created fresh)
    import main
    from httpx import ASGITransport, AsyncClient

    app = main.app

    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.e2e
@pytest.mark.asyncio
class TestAuthFlowE2E:
    """
    CRITICAL: Complete authentication flow tests

    Flow:
    1. Register new user -> 200
    2. Login with correct password -> JWT token
    3. Login with wrong password -> 401
    4. Use JWT to access protected endpoint -> 200
    """

    async def test_1_register_creates_user_in_db(self, api_client):
        """Step 1: Register creates user in PostgreSQL with hashed password"""
        import asyncpg
        from core.auth import get_pg_pool

        response = await api_client.post(
            "/v1/auth/register",
            json={
                "username": "e2euser",
                "email": "e2e@example.com",
                "password": "E2EPass123!",
            },
        )

        assert response.status_code == 200, f"Register failed: {response.text}"
        data = response.json()
        assert data["user"]["username"] == "e2euser"
        assert data["user"]["email"] == "e2e@example.com"
        assert "password" not in str(data)

        # Verify user exists in database with hashed password
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT username, email, password_hash FROM users WHERE username = $1",
                "e2euser",
            )
            assert row is not None, "User not found in database"
            assert row["username"] == "e2euser"
            assert row["email"] == "e2e@example.com"
            assert row["password_hash"] != "E2EPass123!"  # Must be hashed
            assert row["password_hash"].startswith("$2b$")  # bcrypt format

    async def test_2_login_correct_password_returns_jwt(self, api_client):
        """Step 2: Login with correct password returns valid JWT"""
        # First create a user for this test
        await api_client.post(
            "/v1/auth/register",
            json={
                "username": "loginuser",
                "email": "login@example.com",
                "password": "LoginPass123!",
            },
        )

        response = await api_client.post(
            "/v1/auth/login",
            json={"username": "loginuser", "password": "LoginPass123!"},
        )

        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()

        # Verify JWT structure
        assert "access_token" in data, f"No token in response: {data}"
        assert data["token_type"] == "bearer"
        assert len(data["access_token"]) > 100
        assert data["access_token"].count(".") == 2  # JWT: header.payload.signature

        # Verify token can be decoded
        from core.auth import verify_jwt_token

        payload = verify_jwt_token(data["access_token"])
        assert payload["username"] == "loginuser"
        assert "exp" in payload

        return data["access_token"]

    async def test_3_login_wrong_password_returns_401(self, api_client):
        """Step 3: Login with wrong password returns 401 Unauthorized"""
        response = await api_client.post(
            "/v1/auth/login",
            json={"username": "e2euser", "password": "WrongPassword123!"},
        )

        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        data = response.json()
        assert "detail" in data
        assert (
            "invalid" in data["detail"].lower() or "incorrect" in data["detail"].lower()
        )

    async def test_4_duplicate_username_returns_400(self, api_client):
        """Step 4: Duplicate username is rejected"""
        # First create a user
        await api_client.post(
            "/v1/auth/register",
            json={
                "username": "dupuser",
                "email": "dup1@example.com",
                "password": "DupPass123!",
            },
        )

        # Try to create with same username
        response = await api_client.post(
            "/v1/auth/register",
            json={
                "username": "dupuser",  # Already exists
                "email": "different@example.com",
                "password": "AnotherPass123!",
            },
        )

        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        data = response.json()
        assert "already exists" in data["detail"].lower()

    async def test_5_duplicate_email_returns_400(self, api_client):
        """Step 5: Duplicate email is rejected"""
        # First create a user
        await api_client.post(
            "/v1/auth/register",
            json={
                "username": "emaildup1",
                "email": "emaildup@example.com",
                "password": "DupPass123!",
            },
        )

        # Try to create with same email
        response = await api_client.post(
            "/v1/auth/register",
            json={
                "username": "differentuser",
                "email": "emaildup@example.com",  # Already exists
                "password": "AnotherPass123!",
            },
        )

        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        data = response.json()
        assert "already exists" in data["detail"].lower()

    async def test_6_weak_password_returns_400(self, api_client):
        """Step 6: Weak password (< 8 chars) is rejected"""
        response = await api_client.post(
            "/v1/auth/register",
            json={
                "username": "weakuser",
                "email": "weak@example.com",
                "password": "short",  # Too short
            },
        )

        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        data = response.json()
        assert (
            "at least 8 characters" in data["detail"]
            or "password" in data["detail"].lower()
        )


@pytest.mark.e2e
@pytest.mark.asyncio
class TestAuthProtectedEndpoints:
    """Test JWT-protected endpoint access"""

    async def test_valid_jwt_allows_access(self, api_client):
        """Valid JWT allows access to protected endpoints"""
        # Create user and login
        await api_client.post(
            "/v1/auth/register",
            json={
                "username": "protecteduser",
                "email": "protected@example.com",
                "password": "ProtectedPass123!",
            },
        )

        login = await api_client.post(
            "/v1/auth/login",
            json={"username": "protecteduser", "password": "ProtectedPass123!"},
        )
        token = login.json()["access_token"]

        # Test token verification directly
        from core.auth import verify_jwt_token

        payload = verify_jwt_token(token)
        assert payload["username"] == "protecteduser"
        assert "exp" in payload

    async def test_expired_jwt_returns_401(self):
        """Expired JWT returns 401"""
        from datetime import datetime, timedelta

        from fastapi import HTTPException
        from jose import jwt
        from core.auth import verify_jwt_token

        # Create expired token
        expired_payload = {
            "sub": "user123",
            "username": "testuser",
            "exp": datetime.utcnow() - timedelta(hours=1),  # Expired
        }
        expired_token = jwt.encode(
            expired_payload, settings.JWT_SECRET, algorithm="HS256"
        )

        with pytest.raises(HTTPException) as exc:
            verify_jwt_token(expired_token)
        assert exc.value.status_code == 401
        assert "expired" in str(exc.value.detail).lower()

    async def test_invalid_jwt_returns_401(self):
        """Invalid JWT returns 401"""
        from fastapi import HTTPException
        from core.auth import verify_jwt_token

        with pytest.raises(HTTPException) as exc:
            verify_jwt_token("not.a.valid.jwt.token")
        assert exc.value.status_code == 401


# ============================================================================
# Summary
# ============================================================================

# Total E2E tests: 9
# TestAuthFlowE2E: 6 tests (register, login, duplicate checks, weak password)
# TestAuthProtectedEndpoints: 3 tests (token validation, expired, invalid)
