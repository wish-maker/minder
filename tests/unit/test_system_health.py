#!/usr/bin/env python3
"""
Minder System Health Check
Comprehensive system test to verify all components
"""

from typing import Dict

import requests

BASE_URL = "http://localhost:8000"


def test_container_health() -> Dict[str, bool]:
    """Test all container health"""
    print("\n🐋 Container Health")
    print("=" * 60)

    import subprocess

    result = subprocess.run(
        ["docker", "ps", "--format", "table {{.Names}}\t{{.Status}}"],
        capture_output=True,
        text=True,
    )

    print(result.stdout)

    # Check if minder-api is healthy
    if "minder-api" in result.stdout and "healthy" in result.stdout:
        print("✅ All containers healthy")
        return {"containers": True}
    else:
        print("❌ Some containers unhealthy")
        return {"containers": False}


def test_api_endpoints() -> Dict[str, bool]:
    """Test all API endpoints"""
    print("\n🌐 API Endpoints")
    print("=" * 60)

    results = {}

    # Root endpoint
    try:
        response = requests.get(f"{BASE_URL}/")
        if response.status_code == 200:
            print("✅ GET /")
            results["root"] = True
        else:
            print(f"❌ GET / - Status: {response.status_code}")
            results["root"] = False
    except Exception as e:
        print(f"❌ GET / - Error: {e}")
        results["root"] = False

    # Health endpoint
    try:
        response = requests.get(f"{BASE_URL}/health")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ GET /health - Status: {data['status']}")
            print(
                f"   Plugins: {data['system']['plugins']['ready']}/"
                f"{data['system']['plugins']['total']} ready"
            )
            results["health"] = True
        else:
            print(f"❌ GET /health - Status: {response.status_code}")
            results["health"] = False
    except Exception as e:
        print(f"❌ GET /health - Error: {e}")
        results["health"] = False

    # Plugins endpoint
    try:
        response = requests.get(f"{BASE_URL}/plugins")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ GET /plugins - {data['total']} plugins " f"({data['enabled']} enabled)")
            results["plugins"] = True
        else:
            print(f"❌ GET /plugins - Status: {response.status_code}")
            results["plugins"] = False
    except Exception as e:
        print(f"❌ GET /plugins - Error: {e}")
        results["plugins"] = False

    return results


def test_plugin_management() -> Dict[str, bool]:
    """Test plugin enable/disable"""
    print("\n🔌 Plugin Management")
    print("=" * 60)

    results = {}

    # Disable weather plugin
    try:
        response = requests.post(f"{BASE_URL}/plugins/weather/disable")
        if response.status_code == 200:
            print("✅ POST /plugins/weather/disable")
            results["disable"] = True
        else:
            print(f"❌ POST /plugins/weather/disable - " f"Status: {response.status_code}")
            results["disable"] = False
    except Exception as e:
        print(f"❌ POST /plugins/weather/disable - Error: {e}")
        results["disable"] = False

    # Enable weather plugin
    try:
        response = requests.post(f"{BASE_URL}/plugins/weather/enable")
        if response.status_code == 200:
            print("✅ POST /plugins/weather/enable")
            results["enable"] = True
        else:
            print(f"❌ POST /plugins/weather/enable - " f"Status: {response.status_code}")
            results["enable"] = False
    except Exception as e:
        print(f"❌ POST /plugins/weather/enable - Error: {e}")
        results["enable"] = False

    return results


def test_database_connections() -> Dict[str, bool]:
    """Test database connections"""
    print("\n💾 Database Connections")
    print("=" * 60)

    results = {}
    import subprocess

    # PostgreSQL
    try:
        result = subprocess.run(
            ["docker", "exec", "postgres", "pg_isready", "-U", "postgres"],
            capture_output=True,
            text=True,
        )
        if "accepting connections" in result.stdout:
            print("✅ PostgreSQL - accepting connections")
            results["postgres"] = True
        else:
            print(f"❌ PostgreSQL - {result.stdout}")
            results["postgres"] = False
    except Exception as e:
        print(f"❌ PostgreSQL - Error: {e}")
        results["postgres"] = False

    # Redis
    try:
        result = subprocess.run(
            ["docker", "exec", "redis", "redis-cli", "ping"],
            capture_output=True,
            text=True,
        )
        if "PONG" in result.stdout:
            print("✅ Redis - PONG")
            results["redis"] = True
        else:
            print(f"❌ Redis - {result.stdout}")
            results["redis"] = False
    except Exception as e:
        print(f"❌ Redis - Error: {e}")
        results["redis"] = False

    # Qdrant
    try:
        response = requests.get("http://localhost:6333/collections")
        if response.status_code == 200:
            print("✅ Qdrant - API responding")
            results["qdrant"] = True
        else:
            print(f"❌ Qdrant - Status: {response.status_code}")
            results["qdrant"] = False
    except Exception as e:
        print(f"❌ Qdrant - Error: {e}")
        results["qdrant"] = False

    # InfluxDB
    try:
        response = requests.get("http://localhost:8086/health")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ InfluxDB - {data['message']}")
            results["influxdb"] = True
        else:
            print(f"❌ InfluxDB - Status: {response.status_code}")
            results["influxdb"] = False
    except Exception as e:
        print(f"❌ InfluxDB - Error: {e}")
        results["influxdb"] = False

    return results


def test_plugin_status() -> Dict[str, bool]:
    """Test individual plugin status"""
    print("\n🔍 Plugin Status")
    print("=" * 60)

    try:
        response = requests.get(f"{BASE_URL}/health")
        data = response.json()

        plugins = data["system"]["plugins"]["details"]
        ready_count = data["system"]["plugins"]["ready"]
        total_count = data["system"]["plugins"]["total"]

        print(f"📊 Plugins: {ready_count}/{total_count} ready\n")

        for plugin in plugins:
            status_icon = "✅" if plugin["status"] == "ready" else "❌"
            print(f"  {status_icon} {plugin['name']:12} - " f"{plugin['metadata']['description']}")

        return {
            "plugin_status": ready_count == total_count,
            "ready_count": ready_count,
            "total_count": total_count,
        }
    except Exception as e:
        print(f"❌ Error getting plugin status: {e}")
        return {"plugin_status": False}


def main():
    print("🧪 Minder System Health Check")
    print("=" * 60)
    print("Comprehensive system test\n")

    all_results = {}

    # Test container health
    all_results.update(test_container_health())

    # Test API endpoints
    all_results.update(test_api_endpoints())

    # Test plugin management
    all_results.update(test_plugin_management())

    # Test database connections
    all_results.update(test_database_connections())

    # Test plugin status
    all_results.update(test_plugin_status())

    # Summary
    print("\n" + "=" * 60)
    print("📊 Test Summary")
    print("=" * 60)

    total_tests = len(all_results)
    passed_tests = sum(1 for v in all_results.values() if v)

    for test_name, result in all_results.items():
        if isinstance(result, bool):
            status_icon = "✅" if result else "❌"
            print(f"{status_icon} {test_name}")

    print(f"\n🎯 Results: {passed_tests}/{total_tests} tests passed")

    if passed_tests == total_tests:
        print("🎉 All tests passed! System is healthy.")
        return 0
    else:
        print("⚠️  Some tests failed. Check logs for details.")
        return 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
