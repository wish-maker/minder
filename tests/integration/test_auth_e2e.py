"""
API Gateway Auth E2E Tests with Real PostgreSQL

CRITICAL: These tests MUST pass before auth is considered complete.

Run: docker compose -f docker/docker-compose.test.yml up -d
     pytest tests/integration/test_auth_e2e.py -v
"""

import asyncio

import pytest
import pytest_asyncio

# Config is loaded by conftest.py BEFORE this file runs
from config import settings

# Comment out to run tests (requires docker/docker-compose.test.yml up)
# pytestmark = pytest.mark.skip(reason="Requires running Minder services")


@pytest_asyncio.fixture(scope="function")
async def verify_postgres_running():
    """
    Verify PostgreSQL test container is running before any tests.
    Run: docker compose -f docker/docker-compose.test.yml up -d
    """
    import asyncpg

    max_attempts = 30
    for attempt in range(max_attempts):
        try:
            conn = await asyncpg.connect(
                host=settings.DB_HOST,
                port=int(settings.DB_PORT),
                user=settings.DB_USER,
                password=settings.DB_PASSWORD,
                database=settings.DB_NAME,
            )
            await conn.close()
            print("\n[OK] PostgreSQL test container ready")
            return
        except Exception as e:
            if attempt < max_attempts - 1:
                await asyncio.sleep(1)
            else:
                pytest.fail(
                    f"PostgreSQL test container not ready after {max_attempts}s.\n"
                    f"Run: docker compose -f docker/docker-compose.test.yml up -d\n"
                    f"Error: {e}"
                )


@pytest_asyncio.fixture(scope="function")
async def clean_database(verify_postgres_running):
    """
    Setup: Create users table
    Teardown: Drop all data and table
    """
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
    1. Register new user -> 201
    2. Login with correct password -> JWT token
    3. Login with wrong password -> 401
    4. Use JWT to access protected endpoint -> 200
    """

    async def test_1_register_creates_user_in_db(self, api_client):
        """Step 1: Register creates user in PostgreSQL with hashed password"""
        from core.auth import get_pg_pool

        response = await api_client.post(
            "/v1/auth/register",
            json={
                "username": "e2euser",
                "email": "e2e@example.com",
                "password": "E2EPass123!",
            },
        )

        assert response.status_code == 201, f"Register failed: {response.text}"
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

    async def test_4_duplicate_username_returns_409(self, api_client):
        """Step 4: Duplicate username is rejected with 409 Conflict (#146)"""
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

        assert response.status_code == 409, f"Expected 409, got {response.status_code}"
        data = response.json()
        assert "already exists" in data["detail"].lower()

    async def test_5_duplicate_email_returns_409(self, api_client):
        """Step 5: Duplicate email is rejected with 409 Conflict (#146)"""
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

        assert response.status_code == 409, f"Expected 409, got {response.status_code}"
        data = response.json()
        assert "already exists" in data["detail"].lower()

    async def test_6_weak_password_returns_422(self, api_client):
        """Step 6: Weak password (< 8 chars) is rejected with 422 (#146)"""
        response = await api_client.post(
            "/v1/auth/register",
            json={
                "username": "weakuser",
                "email": "weak@example.com",
                "password": "short",  # Too short
            },
        )

        # Pydantic field validation → 422 (detail is a list of error objects).
        assert response.status_code == 422, f"Expected 422, got {response.status_code}"
        assert "password" in response.text.lower()

    async def test_7_refresh_preserves_role_and_email_claims(self, api_client):
        """POST /v1/auth/refresh must carry `role`/`email` forward from the
        presented token, not just `sub`/`username`.

        Before this fix, refresh minted a new token with only sub/username/iat,
        silently dropping role. Since every authorization check does
        `user.get("role") not in roles` (shared/auth/jwt_middleware.py), a
        missing role is None -- never in any allowed-roles list -- so an admin
        who refreshes before expiry (the intended, routine use of this
        endpoint) got quietly downgraded to 403 on every admin-only route
        until they logged out and back in.
        """
        await api_client.post(
            "/v1/auth/register",
            json={
                "username": "refreshuser",
                "email": "refresh@example.com",
                "password": "RefreshPass123!",
            },
        )
        login = await api_client.post(
            "/v1/auth/login",
            json={"username": "refreshuser", "password": "RefreshPass123!"},
        )
        assert login.status_code == 200, login.text
        original_token = login.json()["access_token"]

        from core.auth import verify_jwt_token

        original_payload = verify_jwt_token(original_token)

        refreshed = await api_client.post(
            "/v1/auth/refresh",
            headers={"Authorization": f"Bearer {original_token}"},
        )
        assert refreshed.status_code == 200, refreshed.text
        refreshed_payload = verify_jwt_token(refreshed.json()["access_token"])

        assert refreshed_payload["role"] == original_payload["role"]
        assert refreshed_payload["email"] == original_payload["email"]
        assert refreshed_payload["username"] == original_payload["username"]


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

        from core.auth import verify_jwt_token
        from fastapi import HTTPException
        from jose import jwt

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
        from core.auth import verify_jwt_token
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            verify_jwt_token("not.a.valid.jwt.token")
        assert exc.value.status_code == 401


@pytest.mark.e2e
@pytest.mark.asyncio
class TestOidcAccountLinking:
    """get_or_create_oidc_user's "link an existing local account" branch.

    First-time SSO login for a username that already exists locally
    (authelia_subject IS NULL) must pick up the caller's current Authelia
    group membership immediately, not only on a later login. Before this
    fix, this branch linked authelia_subject but left `role` untouched, so a
    user promoted to Authelia's admins group got a role="user" JWT for their
    entire first SSO session -- only their *second* SSO login (hitting the
    sibling "already linked" branch, which does sync role) picked it up.
    """

    async def test_first_time_link_picks_up_admin_group(self, clean_database):
        from core.auth import create_user, get_or_create_oidc_user

        local_user = await create_user(
            username="localadmin",
            email="localadmin@example.com",
            password="LocalPass123!",
        )
        assert local_user["role"] == "user"

        linked = await get_or_create_oidc_user(
            authelia_subject="authelia-subject-localadmin",
            username="localadmin",
            email="localadmin@example.com",
            groups=["admins"],
        )

        assert linked["role"] == "admin"

    async def test_first_time_link_without_admin_group_stays_user(self, clean_database):
        from core.auth import create_user, get_or_create_oidc_user

        await create_user(
            username="localuser",
            email="localuser@example.com",
            password="LocalPass123!",
        )

        linked = await get_or_create_oidc_user(
            authelia_subject="authelia-subject-localuser",
            username="localuser",
            email="localuser@example.com",
            groups=["everyone"],
        )

        assert linked["role"] == "user"


# ============================================================================
# Summary
# ============================================================================

# Total E2E tests: 12
# TestAuthFlowE2E: 7 tests (register, login, duplicate checks, weak password, refresh)
# TestAuthProtectedEndpoints: 3 tests (token validation, expired, invalid)
# TestOidcAccountLinking: 2 tests (first-time SSO link picks up current Authelia role)
