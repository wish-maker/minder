# services/marketplace/tests/test_models.py
from datetime import datetime

from services.marketplace.models.installation import InstallationResponse
from services.marketplace.models.license import LicenseCreate
from services.marketplace.models.plugin import PluginCreate, PluginResponse


def test_plugin_create_model():
    """Test plugin creation model"""
    data = {
        "name": "test-plugin",
        "display_name": "Test Plugin",
        "description": "A test plugin",
        "author": "Test Author",
        "repository_url": "https://github.com/test/plugin.git",
        "distribution_type": "git",
        "pricing_model": "free",
        "category_id": "test-category-id",
    }

    plugin = PluginCreate(**data)

    assert plugin.name == "test-plugin"
    assert plugin.display_name == "Test Plugin"
    assert plugin.pricing_model == "free"


def test_plugin_response_model():
    """Test plugin response model"""
    data = {
        "id": "test-id",
        "name": "test-plugin",
        "display_name": "Test Plugin",
        "description": "A test plugin",
        "author": "Test Author",
        "author_email": "test@example.com",
        "repository_url": "https://github.com/test/plugin.git",
        "distribution_type": "git",
        "docker_image": None,
        "current_version": "1.0.0",
        "pricing_model": "free",
        "base_tier": "community",
        "status": "approved",
        "featured": False,
        "download_count": 100,
        "rating_average": 4.5,
        "rating_count": 20,
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
        "published_at": None,
        "developer_id": None,
        "category_id": None,
    }

    plugin = PluginResponse(**data)

    assert plugin.id == "test-id"
    assert plugin.name == "test-plugin"
    assert plugin.rating_average == 4.5


def test_license_create_model():
    """Test license creation model"""
    data = {"user_id": "user-id", "plugin_id": "plugin-id", "tier": "professional"}

    license_data = LicenseCreate(**data)

    assert license_data.user_id == "user-id"
    assert license_data.tier == "professional"


def test_installation_response_model():
    """Test installation response model"""
    data = {
        "id": "installation-id",
        "user_id": "user-id",
        "plugin_id": "plugin-id",
        "version": "1.0.0",
        "status": "installed",
        "enabled": True,
        "config_json": None,
        "installed_at": datetime.now(),
        "last_updated_at": datetime.now(),
    }

    installation = InstallationResponse(**data)

    assert installation.id == "installation-id"
    assert installation.enabled is True
