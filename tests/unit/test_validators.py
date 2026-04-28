"""
Unit tests for shared validators module.
Comprehensive validation tests for all validator functions.
"""

import pytest
import pytest_asyncio
from pydantic import ValidationError as PydanticValidationError

from src.shared.validators import (
    validate_plugin_name,
    validate_email,
    validate_url,
    validate_description,
    validate_plugin_version,
    validate_query_string,
    validate_pagination,
    validate_sort_field,
    validate_sort_order,
    sanitize_user_input,
    PaginationParams,
    SortParams,
    SearchParams,
    PluginValidationRequest,
    ValidationError as MinderValidationError
)


class TestValidatePluginName:
    """Test plugin name validation"""

    def test_valid_plugin_names(self):
        """Test valid plugin names"""
        valid_names = [
            "my-plugin",
            "my_plugin",
            "myplugin",
            "MyPlugin",
            "plugin-123",
            "plugin_v1"
        ]

        for name in valid_names:
            result = validate_plugin_name(name)
            assert result == name

    def test_invalid_plugin_names(self):
        """Test invalid plugin names"""
        invalid_names = [
            "",  # Empty
            "ab",  # Too short
            "a" * 51,  # Too long
            "plugin with spaces",  # Spaces
            "plugin!",  # Special chars
            "plugin@home",  # @ symbol
            "plugin/name",  # / symbol
            "plugin\\name",  # backslash
        ]

        for name in invalid_names:
            with pytest.raises(MinderValidationError):
                validate_plugin_name(name)

    def test_non_string_plugin_name(self):
        """Test non-string plugin name"""
        with pytest.raises(MinderValidationError):
            validate_plugin_name(None)

        with pytest.raises(MinderValidationError):
            validate_plugin_name(123)


class TestValidateEmail:
    """Test email validation"""

    def test_valid_emails(self):
        """Test valid email addresses"""
        valid_emails = [
            "test@example.com",
            "user.name@example.com",
            "user+tag@example.com",
            "user123@example.co.uk",
            "user-name@example-domain.com"
        ]

        for email in valid_emails:
            result = validate_email(email)
            assert result == email

    def test_invalid_emails(self):
        """Test invalid email addresses"""
        invalid_emails = [
            "",  # Empty
            "not-an-email",  # No @
            "@example.com",  # No local part
            "user@",  # No domain
            "user@.com",  # Invalid domain
            "user @example.com",  # Space
            "a" * 255,  # Too long
        ]

        for email in invalid_emails:
            with pytest.raises(MinderValidationError):
                validate_email(email)


class TestValidateUrl:
    """Test URL validation"""

    def test_valid_urls(self):
        """Test valid URLs"""
        valid_urls = [
            "http://example.com",
            "https://example.com",
            "https://example.com/path",
            "https://example.com:8080",
            "https://user:pass@example.com"
        ]

        for url in valid_urls:
            result = validate_url(url)
            assert result == url

    def test_invalid_urls(self):
        """Test invalid URLs"""
        invalid_urls = [
            "",  # Empty
            "not-a-url",  # No protocol
            "ftp://example.com",  # Wrong protocol
            "http://localhost",  # Localhost by default
            "a" * 2050,  # Too long
        ]

        for url in invalid_urls:
            with pytest.raises(MinderValidationError):
                validate_url(url)

    def test_allow_localhost(self):
        """Test allowing localhost"""
        result = validate_url("http://localhost:8080", allow_local=True)
        assert result == "http://localhost:8080"


class TestValidateDescription:
    """Test description validation"""

    def test_valid_descriptions(self):
        """Test valid descriptions"""
        valid_descriptions = [
            "",
            "A test plugin",
            "This is a longer description with multiple words and punctuation.",
            "a" * 1000  # Exactly max length
        ]

        for desc in valid_descriptions:
            result = validate_description(desc)
            assert result == desc

    def test_invalid_descriptions(self):
        """Test invalid descriptions"""
        invalid_descriptions = [
            "a" * 1001,  # Too long
        ]

        for desc in invalid_descriptions:
            with pytest.raises(MinderValidationError):
                validate_description(desc)

    def test_description_trimming(self):
        """Test description trimming"""
        desc = "  A test description  "
        result = validate_description(desc)
        assert result == "A test description"


class TestValidatePluginVersion:
    """Test plugin version validation"""

    def test_valid_versions(self):
        """Test valid semantic versions"""
        valid_versions = [
            "1.0.0",
            "2.1.3",
            "10.20.30",
            "1.0.0-alpha",
            "1.0.0-beta.1",
            "1.0.0-rc.1",
            "2.0.0-dev"
        ]

        for version in valid_versions:
            result = validate_plugin_version(version)
            assert result == version

    def test_invalid_versions(self):
        """Test invalid semantic versions"""
        invalid_versions = [
            "",  # Empty
            "1.0",  # Missing patch
            "1",  # Missing minor and patch
            "v1.0.0",  # Leading v
            "1.0.0.0",  # Too many parts
            "1.x.0",  # Non-numeric
            "a.b.c"  # All letters
        ]

        for version in invalid_versions:
            with pytest.raises(MinderValidationError):
                validate_plugin_version(version)


class TestValidateQueryString:
    """Test query string validation"""

    def test_valid_queries(self):
        """Test valid query strings"""
        valid_queries = [
            "test",
            "test query",
            "test-query",
            "test_query",
            "search for something",
            "a" * 100  # Exactly max length
        ]

        for query in valid_queries:
            result = validate_query_string(query)
            assert isinstance(result, str)

    def test_invalid_queries(self):
        """Test invalid query strings"""
        invalid_queries = [
            "",  # Empty
            "a" * 101,  # Too long
        ]

        for query in invalid_queries:
            with pytest.raises(MinderValidationError):
                validate_query_string(query)

    def test_query_sanitization(self):
        """Test query sanitization"""
        query = "test<script>alert('xss')</script>query"
        result = validate_query_string(query)
        assert "<script>" not in result
        assert "'" not in result


class TestValidatePagination:
    """Test pagination validation"""

    def test_valid_pagination(self):
        """Test valid pagination parameters"""
        valid_cases = [
            (1, 10),
            (1, 100),
            (10, 20),
            (100, 50)
        ]

        for page, page_size in valid_cases:
            result_page, result_size = validate_pagination(page, page_size)
            assert result_page == page
            assert result_size == page_size

    def test_invalid_pagination(self):
        """Test invalid pagination parameters"""
        invalid_cases = [
            (0, 10),  # Invalid page
            (-1, 10),  # Negative page
            (1, 0),  # Invalid page size
            (1, -10),  # Negative page size
            (1, 101),  # Too large page size
        ]

        for page, page_size in invalid_cases:
            with pytest.raises(MinderValidationError):
                validate_pagination(page, page_size)

    def test_custom_max_page_size(self):
        """Test custom max page size"""
        result_page, result_size = validate_pagination(1, 200, max_page_size=200)
        assert result_size == 200


class TestValidateSortField:
    """Test sort field validation"""

    def test_valid_sort_field(self):
        """Test valid sort fields"""
        allowed_fields = ["name", "created_at", "updated_at"]

        for field in allowed_fields:
            result = validate_sort_field(field, allowed_fields)
            assert result == field

    def test_invalid_sort_field(self):
        """Test invalid sort fields"""
        allowed_fields = ["name", "created_at", "updated_at"]

        with pytest.raises(MinderValidationError):
            validate_sort_field("invalid_field", allowed_fields)


class TestValidateSortOrder:
    """Test sort order validation"""

    def test_valid_sort_orders(self):
        """Test valid sort orders"""
        valid_orders = ["asc", "desc", "ASC", "DESC"]

        for order in valid_orders:
            result = validate_sort_order(order)
            assert result in ["asc", "desc"]

    def test_invalid_sort_order(self):
        """Test invalid sort orders"""
        invalid_orders = ["", "up", "down", "ascending"]

        for order in invalid_orders:
            with pytest.raises(MinderValidationError):
                validate_sort_order(order)


class TestSanitizeUserInput:
    """Test user input sanitization"""

    def test_html_tag_removal(self):
        """Test HTML tag removal"""
        input_str = "<script>alert('xss')</script>Hello"
        result = sanitize_user_input(input_str)
        assert "<script>" not in result
        assert "Hello" in result

    def test_special_char_removal(self):
        """Test special character removal"""
        input_str = "test\"string';<>"
        result = sanitize_user_input(input_str)
        assert '"' not in result
        assert "'" not in result
        assert "<" not in result
        assert ">" not in result

    def test_whitespace_normalization(self):
        """Test whitespace normalization"""
        input_str = "test   string\n\nwith\ttabs"
        result = sanitize_user_input(input_str)
        assert result == "test string with tabs"

    def test_empty_input(self):
        """Test empty input"""
        assert sanitize_user_input(None) == ""
        assert sanitize_user_input("") == ""

    def test_non_string_input(self):
        """Test non-string input"""
        assert sanitize_user_input(123) == ""


class TestPydanticModels:
    """Test Pydantic validation models"""

    def test_pagination_params(self):
        """Test PaginationParams model"""
        params = PaginationParams(page=1, page_size=20)
        assert params.page == 1
        assert params.page_size == 20

        # Test defaults
        params = PaginationParams()
        assert params.page == 1
        assert params.page_size == 20

    def test_pagination_params_validation(self):
        """Test PaginationParams validation"""
        with pytest.raises(PydanticValidationError):
            PaginationParams(page=0)  # Invalid page

        with pytest.raises(PydanticValidationError):
            PaginationParams(page_size=0)  # Invalid page size

        with pytest.raises(PydanticValidationError):
            PaginationParams(page_size=101)  # Too large

    def test_sort_params(self):
        """Test SortParams model"""
        params = SortParams(sort_by="name", sort_order="desc")
        assert params.sort_by == "name"
        assert params.sort_order == "desc"

    def test_sort_params_validation(self):
        """Test SortParams validation"""
        with pytest.raises(PydanticValidationError):
            SortParams(sort_order="invalid")  # Invalid order

    def test_search_params(self):
        """Test SearchParams model"""
        params = SearchParams(query="test", page=1, page_size=20)
        assert params.query == "test"
        assert params.page == 1
        assert params.page_size == 20

    def test_search_params_validation(self):
        """Test SearchParams validation"""
        with pytest.raises(PydanticValidationError):
            SearchParams(query="")  # Empty query

        with pytest.raises(PydanticValidationError):
            SearchParams(query="a" * 101)  # Too long

    def test_plugin_validation_request(self):
        """Test PluginValidationRequest model"""
        request = PluginValidationRequest(
            name="test-plugin",
            version="1.0.0",
            description="Test plugin",
            author_email="test@example.com",
            homepage_url="https://example.com"
        )
        assert request.name == "test-plugin"
        assert request.version == "1.0.0"

    def test_plugin_validation_request_validation(self):
        """Test PluginValidationRequest validation"""
        with pytest.raises(PydanticValidationError):
            PluginValidationRequest(
                name="test plugin!",  # Invalid name
                version="1.0.0"
            )

        with pytest.raises(PydanticValidationError):
            PluginValidationRequest(
                name="test-plugin",
                version="1.0"  # Invalid version
            )

        with pytest.raises(PydanticValidationError):
            PluginValidationRequest(
                name="test-plugin",
                version="1.0.0",
                author_email="invalid-email"  # Invalid email
            )


# Performance tests
class TestValidatorPerformance:
    """Test validator performance"""

    # NOTE: These tests are skipped because the benchmark fixture
    # is not defined in conftest.py. To enable performance tests,
    # add a benchmark fixture to conftest.py.

    @pytest.mark.skip(reason="Benchmark fixture not available - add benchmark fixture to conftest.py")
    @pytest.mark.slow
    def test_plugin_name_validation_performance(self, benchmark):
        """Test plugin name validation performance"""
        def validate():
            validate_plugin_name("test-plugin-123")

        benchmark(validate)

    @pytest.mark.skip(reason="Benchmark fixture not available - add benchmark fixture to conftest.py")
    @pytest.mark.slow
    def test_email_validation_performance(self, benchmark):
        """Test email validation performance"""
        def validate():
            validate_email("test@example.com")

        benchmark(validate)

    @pytest.mark.skip(reason="Benchmark fixture not available - add benchmark fixture to conftest.py")
    @pytest.mark.slow
    def test_sanitization_performance(self, benchmark):
        """Test sanitization performance"""
        def sanitize():
            sanitize_user_input("<script>alert('xss')</script>test")

        benchmark(sanitize)


# Edge case tests
class TestValidatorEdgeCases:
    """Test validator edge cases"""

    def test_plugin_name_with_numbers(self):
        """Test plugin name with numbers"""
        result = validate_plugin_name("plugin123")
        assert result == "plugin123"

    def test_plugin_name_with_mixed_case(self):
        """Test plugin name with mixed case"""
        result = validate_plugin_name("TestPlugin")
        assert result == "TestPlugin"

    def test_email_with_subdomains(self):
        """Test email with subdomains"""
        result = validate_email("user@sub.domain.example.com")
        assert result == "user@sub.domain.example.com"

    def test_url_with_query_params(self):
        """Test URL with query parameters"""
        result = validate_url("https://example.com?param=value")
        assert "param=value" in result

    def test_query_with_unicode(self):
        """Test query with unicode characters"""
        result = validate_query_string("test çşğı")
        assert "çşğı" in result

    def test_sanitization_preserves_safe_content(self):
        """Test sanitization preserves safe content"""
        input_str = "Hello World! This is a test."
        result = sanitize_user_input(input_str)
        assert "Hello World" in result
        assert "test" in result
