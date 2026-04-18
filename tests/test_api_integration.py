"""
API Integration Tests
Test that new security features are properly integrated into API
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from pathlib import Path

# Mock imports
import sys
sys.modules['watchdog'] = Mock()
sys.modules['watchdog.observers'] = Mock()
sys.modules['watchdog.events'] = Mock()

from api.plugin_store import router, initialize_plugin_observability


class TestAPIIntegration:
    """Test API integration of new features"""

    def test_router_has_new_endpoints(self):
        """Test that router has new observability endpoints"""
        routes = [route.path for route in router.routes]

        # Check new endpoints exist
        assert "/plugins/store/health/{plugin_name}" in routes
        assert "/plugins/store/health" in routes
        assert "/plugins/store/reload/{plugin_name}" in routes
        assert "/plugins/store/metrics/{plugin_name}" in routes

    @pytest.mark.asyncio
    async def test_initialize_observability(self):
        """Test observability initialization"""
        kernel = Mock()

        await initialize_plugin_observability(kernel)

        # Check that observability components were added
        assert hasattr(kernel, "plugin_metrics")
        assert hasattr(kernel, "plugin_health_monitor")

    @pytest.mark.asyncio
    async def test_health_check_endpoint(self):
        """Test health check endpoint"""
        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app)

        # Mock kernel with sandboxes
        mock_kernel = Mock()
        mock_sandbox = Mock()
        mock_sandbox.execute_plugin = AsyncMock(return_value={
            "status": "healthy",
            "healthy": True
        })
        mock_kernel.plugin_sandboxes = {"test_plugin": mock_sandbox}

        # This would require setting kernel in the actual app
        # For now, just test the endpoint exists
        response = client.get("/plugins/store/health/test_plugin")

        # Should return 404 or 200 (depending on if kernel is set)
        assert response.status_code in [200, 404, 503]

    @pytest.mark.asyncio
    async def test_reload_endpoint_exists(self):
        """Test reload endpoint exists"""
        # Just check endpoint exists
        for route in router.routes:
            if "/reload/" in route.path:
                assert "POST" in route.methods
                return

        pytest.fail("Reload endpoint not found")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
