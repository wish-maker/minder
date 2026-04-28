"""
Unit tests for error handling module.
"""

import pytest

from src.shared.errors.errors import (
    AuthenticationError,
    AuthorizationError,
    DatabaseError,
    ExternalServiceError,
    InputValidationError,
    MinderError,
    RateLimitExceededError,
    ResourceNotFoundError,
    ServiceUnavailableError,
)


class TestMinderError:
    """Test MinderError base class"""

    def test_minder_error_creation(self):
        """Test creating MinderError"""
        error = MinderError(
            message="Test error",
            code="TEST_ERROR",
            status_code=500,
            details={"key": "value"},
        )

        assert error.message == "Test error"
        assert error.code == "TEST_ERROR"
        assert error.status_code == 500
        assert error.details == {"key": "value"}

    def test_minder_error_to_dict(self):
        """Test MinderError to_dict method"""
        error = MinderError(
            message="Test error",
            code="TEST_ERROR",
            status_code=500,
            details={"key": "value"},
        )

        error_dict = error.to_dict()

        assert error_dict["message"] == "Test error"
        assert error_dict["code"] == "TEST_ERROR"
        assert error_dict["status_code"] == 500
        assert error_dict["details"] == {"key": "value"}

    def test_minder_error_without_details(self):
        """Test MinderError without details"""
        error = MinderError(message="Test error", code="TEST_ERROR", status_code=500)

        assert error.details == {}


class TestAuthenticationError:
    """Test AuthenticationError"""

    def test_authentication_error_creation(self):
        """Test creating AuthenticationError"""
        error = AuthenticationError(message="Invalid credentials")

        assert error.message == "Invalid credentials"
        assert error.code == "AUTH_FAILED"
        assert error.status_code == 401

    def test_authentication_error_with_details(self):
        """Test AuthenticationError with details"""
        error = AuthenticationError(
            message="Invalid credentials", details={"attempt": 3}
        )

        assert error.details["attempt"] == 3


class TestAuthorizationError:
    """Test AuthorizationError"""

    def test_authorization_error_creation(self):
        """Test creating AuthorizationError"""
        error = AuthorizationError(message="Access denied")

        assert error.message == "Access denied"
        assert error.code == "PERMISSION_DENIED"
        assert error.status_code == 403

    def test_authorization_error_with_required_permission(self):
        """Test AuthorizationError with required_permission"""
        error = AuthorizationError(
            message="Access denied", details={"required_permission": "admin"}
        )

        assert error.details["required_permission"] == "admin"


class TestInputValidationError:
    """Test InputValidationError"""

    def test_validation_error_creation(self):
        """Test creating InputValidationError"""
        error = InputValidationError(message="Invalid input")

        assert error.message == "Invalid input"
        assert error.code == "VALIDATION_ERROR"
        assert error.status_code == 422

    def test_validation_error_with_field(self):
        """Test InputValidationError with field"""
        error = InputValidationError(message="Invalid input", field="email")

        assert error.details["field"] == "email"

    def test_validation_error_with_details(self):
        """Test InputValidationError with details"""
        error = InputValidationError(
            message="Invalid input", field="email", details={"format": "email"}
        )

        assert error.details["field"] == "email"
        assert error.details["format"] == "email"


class TestRateLimitExceededError:
    """Test RateLimitExceededError"""

    def test_rate_limit_error_creation(self):
        """Test creating RateLimitExceededError"""
        error = RateLimitExceededError(limit=100, window=60, reset_time=1234567890)

        assert error.message == "Rate limit exceeded: 100 requests per 60 seconds"
        assert error.code == "RATE_LIMIT_EXCEEDED"
        assert error.status_code == 429

    def test_rate_limit_error_details(self):
        """Test RateLimitExceededError details"""
        error = RateLimitExceededError(limit=100, window=60, reset_time=1234567890)

        assert error.details["limit"] == 100
        assert error.details["window"] == 60
        assert error.details["reset_time"] == 1234567890


class TestResourceNotFoundError:
    """Test ResourceNotFoundError"""

    def test_resource_not_found_error_creation(self):
        """Test creating ResourceNotFoundError"""
        error = ResourceNotFoundError(resource_type="Plugin", resource_id="test-plugin")

        assert error.message == "Plugin not found: test-plugin"
        assert error.code == "RESOURCE_NOT_FOUND"
        assert error.status_code == 404

    def test_resource_not_found_error_with_details(self):
        """Test ResourceNotFoundError with details"""
        error = ResourceNotFoundError(
            resource_type="Plugin",
            resource_id="test-plugin",
            details={"version": "1.0.0"},
        )

        assert error.details["version"] == "1.0.0"


class TestServiceUnavailableError:
    """Test ServiceUnavailableError"""

    def test_service_unavailable_error_creation(self):
        """Test creating ServiceUnavailableError"""
        error = ServiceUnavailableError(
            message="Service unavailable: Database"
        )

        assert error.message == "Service unavailable: Database"
        assert error.code == "SERVICE_UNAVAILABLE"
        assert error.status_code == 503

    def test_service_unavailable_error_details(self):
        """Test ServiceUnavailableError details"""
        error = ServiceUnavailableError(
            message="Service unavailable: Database", details={"reason": "Connection timeout"}
        )

        assert error.details["reason"] == "Connection timeout"


class TestDatabaseError:
    """Test DatabaseError"""

    def test_database_error_creation(self):
        """Test creating DatabaseError"""
        error = DatabaseError(message="Query failed")

        assert error.message == "Query failed"
        assert error.code == "DATABASE_ERROR"
        assert error.status_code == 500

    def test_database_error_with_details(self):
        """Test DatabaseError with details"""
        error = DatabaseError(
            message="Query failed", details={"query": "SELECT * FROM table"}
        )

        assert error.details["query"] == "SELECT * FROM table"


class TestExternalServiceError:
    """Test ExternalServiceError"""

    def test_external_service_error_creation(self):
        """Test creating ExternalServiceError"""
        error = ExternalServiceError(
            service_name="API", message="Timeout"
        )

        assert error.message == "Timeout"
        assert error.code == "EXTERNAL_SERVICE_ERROR"
        assert error.status_code == 502

    def test_external_service_error_details(self):
        """Test ExternalServiceError details"""
        error = ExternalServiceError(
            service_name="API", message="Timeout", details={"reason": "Timeout"}
        )

        assert error.details["service"] == "API"
        assert error.details["reason"] == "Timeout"


class TestErrorFormatting:
    """Test error formatting utilities"""

    def test_format_error_response_without_request_id(self):
        """Test formatting error response without request ID"""
        error = MinderError(
            message="Test error",
            code="TEST_ERROR",
            status_code=500,
            details={"key": "value"},
        )

        response = error.to_dict()

        assert response["code"] == "TEST_ERROR"
        assert response["message"] == "Test error"
        assert response["status_code"] == 500
        assert response["details"] == {"key": "value"}

    def test_format_error_response_with_request_id(self):
        """Test formatting error response with request ID"""
        error = MinderError(
            message="Test error",
            code="TEST_ERROR",
            status_code=500,
            details={"request_id": "test-123"},
        )

        response = error.to_dict()

        assert response["code"] == "TEST_ERROR"
        assert response["message"] == "Test error"
        assert response["status_code"] == 500
        assert response["details"]["request_id"] == "test-123"

    def test_format_error_response_without_details(self):
        """Test formatting error response without details"""
        error = MinderError(
            message="Test error",
            code="TEST_ERROR",
            status_code=500,
        )

        response = error.to_dict()

        assert response["code"] == "TEST_ERROR"
        assert response["message"] == "Test error"
        assert response["status_code"] == 500
        assert response["details"] == {}
