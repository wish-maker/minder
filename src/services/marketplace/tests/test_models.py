# services/marketplace/tests/test_models.py
from datetime import datetime

import pytest
from pydantic import ValidationError

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
        "category_id": "550e8400-e29b-41d4-a716-446655440000",
    }

    plugin = PluginCreate(**data)

    assert plugin.name == "test-plugin"
    assert plugin.display_name == "Test Plugin"
    assert plugin.pricing_model == "free"


def test_plugin_response_model():
    """Test plugin response model"""
    data = {
        "id": "550e8400-e29b-41d4-a716-446655440001",
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

    assert plugin.id == "550e8400-e29b-41d4-a716-446655440001"
    assert plugin.name == "test-plugin"
    assert plugin.rating_average == 4.5


def test_license_create_model():
    """Test license creation model"""
    data = {
        "user_id": "550e8400-e29b-41d4-a716-446655440002",
        "plugin_id": "550e8400-e29b-41d4-a716-446655440003",
        "tier": "professional",
    }

    license_data = LicenseCreate(**data)

    assert license_data.user_id == "550e8400-e29b-41d4-a716-446655440002"
    assert license_data.tier == "professional"


def test_installation_response_model():
    """Test installation response model"""
    data = {
        "id": "550e8400-e29b-41d4-a716-446655440004",
        "user_id": "550e8400-e29b-41d4-a716-446655440005",
        "plugin_id": "550e8400-e29b-41d4-a716-446655440006",
        "version": "1.0.0",
        "status": "installed",
        "enabled": True,
        "config_json": None,
        "installed_at": datetime.now(),
        "last_updated_at": datetime.now(),
    }

    installation = InstallationResponse(**data)

    assert installation.id == "550e8400-e29b-41d4-a716-446655440004"
    assert installation.enabled is True


def test_invalid_email_rejected():
    """Test that invalid email addresses are rejected"""
    data = {
        "name": "test-plugin",
        "display_name": "Test Plugin",
        "description": "A test plugin",
        "author": "Test Author",
        "author_email": "invalid-email",  # Invalid email format
        "repository_url": "https://github.com/test/plugin.git",
        "distribution_type": "git",
        "pricing_model": "free",
        "category_id": "550e8400-e29b-41d4-a716-446655440000",
    }

    with pytest.raises(ValidationError) as exc_info:
        PluginCreate(**data)

    # Verify the error is about email validation
    errors = exc_info.value.errors()
    assert any("email" in str(error.get("loc", "")).lower() for error in errors)


def test_invalid_uuid_rejected():
    """Test that invalid UUIDs are rejected"""
    data = {
        "name": "test-plugin",
        "display_name": "Test Plugin",
        "description": "A test plugin",
        "author": "Test Author",
        "repository_url": "https://github.com/test/plugin.git",
        "distribution_type": "git",
        "pricing_model": "free",
        "category_id": "not-a-valid-uuid",  # Invalid UUID
    }

    with pytest.raises(ValidationError) as exc_info:
        PluginCreate(**data)

    # Verify the error is about UUID validation
    errors = exc_info.value.errors()
    assert any("category_id" in str(error.get("loc", "")) for error in errors)


def test_html_sanitization():
    """Test that HTML tags are properly escaped"""
    data = {
        "name": "test-plugin",
        "display_name": "<script>alert('xss')</script>Test Plugin",
        "description": "Description with <b>HTML</b> tags",
        "author": "Test Author",
        "repository_url": "https://github.com/test/plugin.git",
        "distribution_type": "git",
        "pricing_model": "free",
    }

    plugin = PluginCreate(**data)

    # Verify HTML tags are escaped
    assert "&lt;script&gt;" in plugin.display_name
    assert "<script>" not in plugin.display_name
    assert "&lt;b&gt;" in plugin.description
    assert "<b>" not in plugin.description
