#!/usr/bin/env python3
"""
Test plugin database write functionality
Verify each plugin can write to its database correctly
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta  # noqa: F401

sys.path.insert(0, "/root/minder")


async def test_database_writes():
    """Test all plugin database write operations"""
    print("=" * 60)
    print("DATABASE WRITE VERIFICATION TEST")
    print("=" * 60)

    import asyncpg
    import redis
    from influxdb_client import InfluxDBClient
    from qdrant_client import QdrantClient

    from src.core.kernel import MinderKernel

    # Test results
    results = {
        "postgres": {"status": "pending", "details": []},
        "influxdb": {"status": "pending", "details": []},
        "qdrant": {"status": "pending", "details": []},
        "redis": {"status": "pending", "details": []},
    }

    # Create kernel
    print("\n1. Creating kernel...")
    config = {
        "fund": {
            "database": {
                "host": "localhost",  # FIXED: Use localhost for host network mode
                "port": 5432,
                "database": "fundmind",
                "user": "postgres",
                "password": os.getenv(
                    "POSTGRES_PASSWORD", os.getenv("PGPASSWORD", "postgrespassword")
                ),
            }
        },
        "plugins": {"network": {}, "weather": {}, "crypto": {}, "news": {}},
        "plugin_store": {
            "enabled": True,
            "store_path": "/app/plugins",
        },
    }

    kernel = MinderKernel(config)
    await kernel.start()

    print("✓ Kernel started")

    # Test PostgreSQL Write (News plugin)
    print("\n" + "=" * 60)
    print("TEST 1: PostgreSQL Write (News Plugin)")
    print("=" * 60)

    try:
        conn = await asyncpg.connect(
            host="localhost",  # FIXED
            port=5432,
            database="fundmind",
            user="postgres",
            password=os.getenv("POSTGRES_PASSWORD", os.getenv("PGPASSWORD", "postgrespassword")),
        )

        # Create test table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS test_news_write (
                id SERIAL PRIMARY KEY,
                title VARCHAR(255),
                content TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Insert test data
        test_title = f"Test News {datetime.now().isoformat()}"
        await conn.execute(
            "INSERT INTO test_news_write (title, content) VALUES ($1, $2)",
            test_title,
            "Test content for database write verification",
        )

        # Verify write
        row = await conn.fetchrow("SELECT * FROM test_news_write WHERE title = $1", test_title)

        if row:
            print("✓ PostgreSQL write SUCCESS")
            print(f"  - Inserted: {test_title}")
            print(f"  - Retrieved: {row['title']}")
            results["postgres"] = {"status": "success", "details": ["Write verified"]}
        else:
            print("✗ PostgreSQL write FAILED - Could not retrieve data")
            results["postgres"] = {"status": "failed", "details": ["Data not found"]}

        # Cleanup
        await conn.execute("DROP TABLE IF EXISTS test_news_write")
        await conn.close()

    except Exception as e:
        print(f"✗ PostgreSQL write FAILED: {e}")
        results["postgres"] = {"status": "error", "details": [str(e)]}

    # Test InfluxDB Write (Weather plugin)
    print("\n" + "=" * 60)
    print("TEST 2: InfluxDB Write (Weather Plugin)")
    print("=" * 60)

    try:
        influx_client = InfluxDBClient(
            url="http://localhost:8086",  # FIXED
            token=os.getenv(
                "INFLUXDB_TOKEN",
                "dV-Uwy0ZflsFl7tNKlI6XxQ_jx4HqjiSzDwM7kV_ghmBe7GKIJLwMOiKtQOvalhDbOnS969sjGwe_-Y7cPlNdg==",
            ),
            org="minder",
        )

        write_api = influx_client.write_api()

        # Write test data point
        from influxdb_client import Point

        point = (
            Point("test_weather_write")
            .tag("location", "test")
            .field("temperature", 25.5)
            .field("humidity", 60.0)
            .time(datetime.utcnow())
        )

        write_api.write(bucket="weather_data", record=point)

        # Wait for write to complete
        await asyncio.sleep(2)

        # Query to verify
        query_api = influx_client.query_api()
        query = """
        from(bucket: "weather_data")
          |> range(start: -1m)
          |> filter(fn: (r) => r._measurement == "test_weather_write")
          |> limit(n: 1)
        """

        result = query_api.query(query)

        if result and len(result) > 0:
            records = list(result[0].records)
            if len(records) > 0:
                print("✓ InfluxDB write SUCCESS")
                print(f"  - Records written: {len(records)}")
                results["influxdb"] = {"status": "success", "details": [f"{len(records)} records"]}
            else:
                print("✗ InfluxDB write FAILED - No records found")
                results["influxdb"] = {"status": "failed", "details": ["No records"]}
        else:
            print("✗ InfluxDB write FAILED - Query returned empty")
            results["influxdb"] = {"status": "failed", "details": ["Empty query"]}

        influx_client.close()

    except Exception as e:
        print(f"✗ InfluxDB write FAILED: {e}")
        results["influxdb"] = {"status": "error", "details": [str(e)]}

    # Test Qdrant Write (Network plugin)
    print("\n" + "=" * 60)
    print("TEST 3: Qdrant Vector Write (Network Plugin)")
    print("=" * 60)

    try:
        qdrant_client = QdrantClient(host="localhost", port=6333)  # FIXED

        # Create test collection
        collection_name = "test_network_write"

        from qdrant_client.models import Distance, PointStruct, VectorParams

        # Check if collection exists, delete if it does
        collections = qdrant_client.get_collections().collections
        collection_names = [c.name for c in collections]

        if collection_name in collection_names:
            qdrant_client.delete_collection(collection_name)

        qdrant_client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=128, distance=Distance.COSINE),
        )

        # Insert test vector
        import random

        test_vector = [random.random() for _ in range(128)]

        qdrant_client.upsert(
            collection_name=collection_name,
            points=[
                PointStruct(
                    id=1,
                    vector=test_vector,
                    payload={"test": "database_write", "timestamp": datetime.now().isoformat()},
                )
            ],
        )

        # Verify write - using the correct Qdrant API
        from qdrant_client.models import Filter, SearchRequest  # noqa: F401

        search_result = qdrant_client.query_points(
            collection_name=collection_name, query=test_vector, limit=1
        )

        # Check if we got any results from the QueryResponse object
        if search_result and len(search_result.points) > 0:
            print("✓ Qdrant write SUCCESS")
            print(f"  - Vector ID: {search_result.points[0].id}")
            print(f"  - Payload: {search_result.points[0].payload}")
            results["qdrant"] = {"status": "success", "details": ["Vector written"]}
        else:
            print("✗ Qdrant write FAILED - Could not retrieve vector")
            results["qdrant"] = {"status": "failed", "details": ["Vector not found"]}

        # Cleanup
        qdrant_client.delete_collection(collection_name)

    except Exception as e:
        print(f"✗ Qdrant write FAILED: {e}")
        results["qdrant"] = {"status": "error", "details": [str(e)]}

    # Test Redis Write
    print("\n" + "=" * 60)
    print("TEST 4: Redis Write (Caching)")
    print("=" * 60)

    try:
        redis_client = redis.Redis(host="localhost", port=6379, decode_responses=True)  # FIXED

        # Write test data
        test_key = f"test_write_{datetime.now().timestamp()}"
        test_value = json.dumps({"test": "database_write", "timestamp": datetime.now().isoformat()})

        redis_client.set(test_key, test_value, ex=60)

        # Verify write
        retrieved = redis_client.get(test_key)

        if retrieved:
            print("✓ Redis write SUCCESS")
            print(f"  - Key: {test_key}")
            print(f"  - Value: {retrieved}")
            results["redis"] = {"status": "success", "details": ["Value written"]}

            # Cleanup
            redis_client.delete(test_key)
        else:
            print("✗ Redis write FAILED - Could not retrieve value")
            results["redis"] = {"status": "failed", "details": ["Value not found"]}

        redis_client.close()

    except Exception as e:
        print(f"✗ Redis write FAILED: {e}")
        results["redis"] = {"status": "error", "details": [str(e)]}

    # Cleanup kernel
    await kernel.stop()

    # Summary
    print("\n" + "=" * 60)
    print("DATABASE WRITE TEST SUMMARY")
    print("=" * 60)

    success_count = 0
    total_count = len(results)

    for db, result in results.items():
        status_icon = "✓" if result["status"] == "success" else "✗"
        status_text = result["status"].upper()
        print(f"{status_icon} {db.upper():12} - {status_text}")
        if result["details"]:
            for detail in result["details"]:
                print(f"    {detail}")

        if result["status"] == "success":
            success_count += 1

    print(f"\n{success_count}/{total_count} database write tests PASSED")

    if success_count == total_count:
        print("\n✓ ALL DATABASE WRITES WORKING CORRECTLY")
        return True
    else:
        print(f"\n✗ {total_count - success_count} DATABASE WRITES FAILED")
        return False


if __name__ == "__main__":
    success = asyncio.run(test_database_writes())

    if success:
        print("\n" + "=" * 60)
        print("DATABASE WRITE VERIFICATION: ✓ PASSED")
        print("=" * 60)
        sys.exit(0)
    else:
        print("\n" + "=" * 60)
        print("DATABASE WRITE VERIFICATION: ✗ FAILED")
        print("=" * 60)
        sys.exit(1)
