"""
API Gateway Auth E2E Test - Simple Direct Test

Run this with: python test_auth_e2e_simple.py
"""

import asyncio
import os
import sys

# Path setup
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src/services/api-gateway"))

# Test database settings
os.environ["POSTGRES_HOST"] = "localhost"
os.environ["POSTGRES_PORT"] = "5432"
os.environ["POSTGRES_USER"] = "postgres"
os.environ["POSTGRES_PASSWORD"] = "testpass"
os.environ["POSTGRES_DB"] = "minder_test"
os.environ["JWT_SECRET"] = "test_jwt_secret"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["JWT_EXPIRATION_MINUTES"] = "60"


async def test_auth_flow():
    """Test complete auth flow with real PostgreSQL"""
    print("=" * 60)
    print("API GATEWAY AUTH E2E TEST")
    print("=" * 60)

    # 1. Connect to PostgreSQL
    print("\n[1] Connecting to PostgreSQL...")
    try:
        import asyncpg
        from modules.auth import init_users_table

        pool = await asyncpg.create_pool(
            host="localhost",
            port=5432,
            user="postgres",
            password="testpass",
            database="minder_test",
            min_size=1,
            max_size=5
        )

        # Test connection
        async with pool.acquire() as conn:
            result = await conn.fetchval("SELECT 1")
            print(f"    [OK] PostgreSQL connected: {result}")
            await conn.execute("DROP TABLE IF EXISTS users CASCADE")
            print("    [OK] Cleaned any existing users table")

        # Initialize users table
        await init_users_table()
        print("    [OK] Users table initialized")

    except Exception as e:
        print(f"    [FAIL] PostgreSQL connection failed: {e}")
        print("    Hint: Make sure test-postgres container is running:")
        print("           docker run -d --name test-postgres -p 5432:5432 \\")
        print("           -e POSTGRES_PASSWORD=testpass postgres:16")
        return

    # 2. Import app and create client
    print("\n[2] Starting API Gateway...")
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    try:
        from main import app
        print("    [OK] API Gateway loaded")
    except Exception as e:
        print(f"    [FAIL] Could not load API Gateway: {e}")
        return

    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")

    # 3. Test: Create user
    print("\n[3] Test: Create User")
    try:
        response = await client.post("/v1/auth/register", json={
            "username": "e2euser",
            "email": "e2e@example.com",
            "password": "E2EPass123!"
        })

        if response.status_code == 200:
            print(f"    [OK] User created: {response.json()['user']['username']}")
        else:
            print(f"    [FAIL] User creation failed: {response.status_code}")
            return
    except Exception as e:
        print(f"    [FAIL] User creation error: {e}")
        return

    # 4. Test: Login with correct password
    print("\n[4] Test: Login with Correct Password")
    try:
        response = await client.post("/v1/auth/login", json={
            "username": "e2euser",
            "password": "E2EPass123!"
        })

        if response.status_code == 200:
            data = response.json()
            token = data["access_token"]
            print(f"    [OK] Login successful, JWT token received")
            print(f"    Token length: {len(token)} chars")
            print(f"    Token preview: {token[:50]}...")
        else:
            print(f"    [FAIL] Login failed: {response.status_code} - {response.text}")
            return
    except Exception as e:
        print(f"    [FAIL] Login error: {e}")
        return

    # 5. Test: Login with wrong password
    print("\n[5] Test: Login with Wrong Password")
    try:
        response = await client.post("/v1/auth/login", json={
            "username": "e2euser",
            "password": "WrongPassword123!"
        })

        if response.status_code == 401:
            print(f"    [OK] Wrong password rejected: {response.json()['detail']}")
        else:
            print(f"    [FAIL] Expected 401, got {response.status_code}")
            return
    except Exception as e:
        print(f"    [FAIL] Wrong password test error: {e}")
        return

    # 6. Test: Duplicate username
    print("\n[6] Test: Duplicate Username Rejection")
    try:
        response = await client.post("/v1/auth/register", json={
            "username": "e2euser",  # Already exists
            "email": "different@example.com",
            "password": "AnotherPass123!"
        })

        if response.status_code == 400:
            print(f"    [OK] Duplicate rejected: {response.json()['detail']}")
        else:
            print(f"    [FAIL] Expected 400, got {response.status_code}")
            return
    except Exception as e:
        print(f"    [FAIL] Duplicate test error: {e}")
        return

    # 7. Test: Verify JWT token
    print("\n[7] Test: Verify JWT Token")
    try:
        from modules.auth import verify_jwt_token
        payload = verify_jwt_token(token)
        print(f"    [OK] JWT verified, user: {payload['username']}")
    except Exception as e:
        print(f"    [FAIL] JWT verification error: {e}")
        return

    # Cleanup
    try:
        async with pool.acquire() as conn:
            await conn.execute("DROP TABLE IF EXISTS users CASCADE")
        await pool.close()
        print("\n    [OK] Database cleaned up")
    except:
        pass

    print("\n" + "=" * 60)
    print("E2E TEST RESULTS: ALL TESTS PASSED")
    print("=" * 60)
    print("[OK] User creation: WORKING")
    print("[OK] Login with correct password: WORKING")
    print("[OK] Login with wrong password: REJECTED")
    print("[OK] Duplicate username: REJECTED")
    print("[OK] JWT token verification: WORKING")
    print("\nAuth implementation is FULLY FUNCTIONAL with PostgreSQL!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_auth_flow())
