"""
Unit tests for shared response models
"""
import pytest
from datetime import datetime
from pydantic import ValidationError

from services.shared.models.responses import (
    HealthCheckResponse,
    DetailedHealthCheck,
    ServiceDependency,
    SuccessResponse,
    ErrorResponse,
    PaginatedResponse,
    CreateResponse,
    UpdateResponse,
    DeleteResponse,
    BatchOperationResponse,
)


class TestHealthCheckResponse:
    """Test HealthCheckResponse model"""

    def test_health_check_basic(self):
        """Test basic health check response"""
        response = HealthCheckResponse(
            service="test-service",
            status="healthy",
            version="1.0.0"
        )

        assert response.service == "test-service"
        assert response.status == "healthy"
        assert response.version == "1.0.0"
        assert response.environment == "development"  # default
        assert isinstance(response.timestamp, datetime)

    def test_health_check_with_environment(self):
        """Test health check with custom environment"""
        response = HealthCheckResponse(
            service="test-service",
            status="healthy",
            version="1.0.0",
            environment="production"
        )

        assert response.environment == "production"

    def test_health_check_with_checks(self):
        """Test health check with additional checks"""
        response = HealthCheckResponse(
            service="test-service",
            status="healthy",
            version="1.0.0",
            checks={"database": "connected", "redis": "connected"}
        )

        assert response.checks == {"database": "connected", "redis": "connected"}

    def test_health_check_status_validation(self):
        """Test status field validation"""
        # Valid statuses
        for status in ["healthy", "unhealthy", "degraded"]:
            response = HealthCheckResponse(
                service="test-service",
                status=status,
                version="1.0.0"
            )
            assert response.status == status

        # Invalid status
        with pytest.raises(ValidationError):
            HealthCheckResponse(
                service="test-service",
                status="invalid",
                version="1.0.0"
            )


class TestServiceDependency:
    """Test ServiceDependency model"""

    def test_service_dependency_basic(self):
        """Test basic service dependency"""
        dep = ServiceDependency(
            name="redis",
            status="healthy"
        )

        assert dep.name == "redis"
        assert dep.status == "healthy"
        assert dep.url is None
        assert dep.response_time_ms is None

    def test_service_dependency_with_url(self):
        """Test service dependency with URL"""
        dep = ServiceDependency(
            name="postgres",
            status="healthy",
            url="postgres://localhost:5432"
        )

        assert dep.url == "postgres://localhost:5432"

    def test_service_dependency_with_response_time(self):
        """Test service dependency with response time"""
        dep = ServiceDependency(
            name="redis",
            status="healthy",
            response_time_ms=5.5
        )

        assert dep.response_time_ms == 5.5


class TestDetailedHealthCheck:
    """Test DetailedHealthCheck model"""

    def test_detailed_health_check_basic(self):
        """Test basic detailed health check"""
        deps = [
            ServiceDependency(name="redis", status="healthy"),
            ServiceDependency(name="postgres", status="healthy")
        ]

        response = DetailedHealthCheck(
            service="api-gateway",
            status="healthy",
            version="2.0.0",
            dependencies=deps
        )

        assert response.service == "api-gateway"
        assert len(response.dependencies) == 2
        assert isinstance(response.timestamp, datetime)


class TestSuccessResponse:
    """Test SuccessResponse model"""

    def test_success_response_basic(self):
        """Test basic success response"""
        response = SuccessResponse[str](
            message="Operation successful",
            data="test data"
        )

        assert response.success is True
        assert response.message == "Operation successful"
        assert response.data == "test data"

    def test_success_response_without_data(self):
        """Test success response without data field"""
        response = SuccessResponse(
            message="Operation successful"
        )

        assert response.success is True
        assert response.message == "Operation successful"
        assert response.data is None

    def test_success_response_with_dict_data(self):
        """Test success response with dictionary data"""
        data = {"id": 123, "name": "test"}

        response = SuccessResponse[dict](
            message="Item created",
            data=data
        )

        assert response.data == data


class TestErrorResponse:
    """Test ErrorResponse model"""

    def test_error_response_basic(self):
        """Test basic error response"""
        response = ErrorResponse(
            error="Validation failed"
        )

        assert response.success is False
        assert response.error == "Validation failed"
        assert response.detail is None

    def test_error_response_with_detail(self):
        """Test error response with detail"""
        response = ErrorResponse(
            error="Validation failed",
            detail={"field": "email", "message": "Invalid email format"}
        )

        assert response.detail == {"field": "email", "message": "Invalid email format"}


class TestPaginatedResponse:
    """Test PaginatedResponse model"""

    def test_paginated_response_basic(self):
        """Test basic paginated response"""
        items = [{"id": 1}, {"id": 2}]

        response = PaginatedResponse.create(
            items=items,
            total=10,
            page=1,
            page_size=2
        )

        assert response.items == items
        assert response.total == 10
        assert response.page == 1
        assert response.page_size == 2
        assert response.total_pages == 5

    def test_paginated_response_factory(self):
        """Test PaginatedResponse.create factory method"""
        items = list(range(15))  # 15 items

        # Page 1
        response = PaginatedResponse.create(
            items=items[:10],
            total=15,
            page=1,
            page_size=10
        )

        assert len(response.items) == 10
        assert response.total_pages == 2

    def test_paginated_response_last_page(self):
        """Test paginated response on last page"""
        items = [{"id": 5}]

        response = PaginatedResponse.create(
            items=items,
            total=5,
            page=1,
            page_size=5
        )

        assert response.total_pages == 1

    def test_paginated_response_empty(self):
        """Test paginated response with no items"""
        response = PaginatedResponse.create(
            items=[],
            total=0,
            page=1,
            page_size=10
        )

        assert response.items == []
        assert response.total == 0
        assert response.total_pages == 1


class TestCreateResponse:
    """Test CreateResponse model"""

    def test_create_response(self):
        """Test resource creation response"""
        response = CreateResponse(id="new-resource-123")

        assert response.id == "new-resource-123"
        assert response.success is True
        assert response.message == "Resource created successfully"
        assert isinstance(response.created_at, datetime)


class TestUpdateResponse:
    """Test UpdateResponse model"""

    def test_update_response(self):
        """Test resource update response"""
        response = UpdateResponse(
            id="resource-123",
            changes={"status": "updated"}
        )

        assert response.id == "resource-123"
        assert response.changes == {"status": "updated"}
        assert isinstance(response.updated_at, datetime)


class TestDeleteResponse:
    """Test DeleteResponse model"""

    def test_delete_response(self):
        """Test resource deletion response"""
        response = DeleteResponse(id="resource-123")

        assert response.id == "resource-123"
        assert response.success is True
        assert response.message == "Resource deleted successfully"
        assert isinstance(response.deleted_at, datetime)


class TestBatchOperationResponse:
    """Test BatchOperationResponse model"""

    def test_batch_operation_success(self):
        """Test batch operation with some failures"""
        response = BatchOperationResponse(
            operation="batch_create",
            total=10,
            successful=8,
            failed=2,
            errors=[
                {"item": 3, "error": "Validation failed"},
                {"item": 7, "error": "Duplicate key"}
            ]
        )

        assert response.operation == "batch_create"
        assert response.total == 10
        assert response.successful == 8
        assert response.failed == 2
        assert len(response.errors) == 2
        assert isinstance(response.timestamp, datetime)

    def test_batch_operation_all_success(self):
        """Test batch operation with all successes"""
        response = BatchOperationResponse(
            operation="batch_delete",
            total=5,
            successful=5,
            failed=0
        )

        assert response.successful == 5
        assert response.failed == 0
        assert response.errors is None
