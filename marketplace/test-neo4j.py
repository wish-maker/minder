"""
Test Neo4j Integration for Minder Plugin Marketplace
"""

import asyncio
import os
import sys

# Add services directory to path
sys.path.insert(0, "/root/minder")

from services.marketplace.core.neo4j_client import Neo4jClient


async def test_neo4j():
    """Test Neo4j connection and basic operations"""

    print("Testing Neo4j Integration...")

    # Create client
    client = Neo4jClient(uri="bolt://localhost:7687", user="neo4j", password="neo4j_test_password_change_me")

    try:
        # Test 1: Create plugin nodes
        print("\n1. Creating plugin nodes...")

        plugin1 = {
            "id": "test-plugin-1",
            "name": "test-plugin-1",
            "display_name": "Test Plugin 1",
            "description": "Test plugin for Neo4j",
            "category": "testing",
            "base_tier": "community",
            "pricing_model": "free",
        }

        plugin2 = {
            "id": "test-plugin-2",
            "name": "test-plugin-2",
            "display_name": "Test Plugin 2",
            "description": "Another test plugin",
            "category": "testing",
            "base_tier": "community",
            "pricing_model": "free",
        }

        plugin1_id = await client.create_plugin_node(plugin1)
        print(f"   Created plugin: {plugin1_id}")

        plugin2_id = await client.create_plugin_node(plugin2)
        print(f"   Created plugin: {plugin2_id}")

        # Test 2: Add dependency
        print("\n2. Adding dependency relationship...")
        success = await client.add_dependency(
            plugin_id="test-plugin-1", depends_on_plugin_id="test-plugin-2", dependency_type="requires"
        )
        print(f"   Dependency added: {success}")

        # Test 3: Get dependencies
        print("\n3. Getting plugin dependencies...")
        dependencies = await client.get_plugin_dependencies("test-plugin-1")
        print(f"   Dependencies found: {len(dependencies)}")
        for dep in dependencies:
            print(f"   - {dep}")

        # Test 4: Get recommendations
        print("\n4. Getting recommendations...")
        recommendations = await client.recommend_plugins(installed_plugin_ids=["test-plugin-2"], limit=5)
        print(f"   Recommendations: {len(recommendations)}")
        for rec in recommendations:
            print(f"   - {rec}")

        print("\n✅ All Neo4j tests passed!")

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback

        traceback.print_exc()

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(test_neo4j())
