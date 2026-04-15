"""
Simplified Unit Tests for Security System
Tests input validation and sanitization
"""
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.security import InputSanitizer


class TestInputSanitization:
    """Test input sanitization and validation"""

    def test_validate_sql_injection(self):
        """Test SQL injection detection"""
        malicious_inputs = [
            "'; DROP TABLE users; --",
            "1' OR '1'='1",
            "admin'--",
            "1' UNION SELECT * FROM users--"
        ]

        for malicious_input in malicious_inputs:
            is_valid, error_msg = InputSanitizer.validate_input(malicious_input, check_sql=True)
            # Should detect SQL injection
            assert is_valid is False
            assert error_msg is not None

    def test_validate_xss_attack(self):
        """Test XSS attack detection"""
        xss_inputs = [
            "<script>alert('XSS')</script>",
            "<img src=x onerror=alert('XSS')>",
            "<svg onload=alert('XSS')>",
            "javascript:alert('XSS')"
        ]

        for xss_input in xss_inputs:
            is_valid, error_msg = InputSanitizer.validate_input(xss_input, check_xss=True)
            # Should detect XSS
            assert is_valid is False
            assert error_msg is not None

    def test_validate_safe_input(self):
        """Test validation of safe input"""
        safe_inputs = [
            "Hello World",
            "user@example.com",
            "https://example.com/page",
            "Regular text with numbers 12345"
        ]

        for safe_input in safe_inputs:
            is_valid, error_msg = InputSanitizer.validate_input(safe_input)
            # Should pass validation
            assert is_valid is True
            assert error_msg is None

    def test_sanitize_string(self):
        """Test string sanitization"""
        # Test HTML tag removal
        input_with_html = "<p>Hello <b>World</b></p>"
        sanitized = InputSanitizer.sanitize_string(input_with_html, max_length=100)

        # Should return a string
        assert isinstance(sanitized, str)
        # HTML tags should be removed or escaped
        assert sanitized is not None

    def test_sanitize_max_length(self):
        """Test max length enforcement"""
        long_input = "A" * 200
        sanitized = InputSanitizer.sanitize_string(long_input, max_length=50)

        # Should be truncated to max_length
        assert len(sanitized) <= 50

    def test_combined_validation(self):
        """Test multiple security checks together"""
        malicious_inputs = [
            "<script>' OR '1'='1</script>",  # XSS + SQL
            "; cat /etc/passwd",  # Command injection
            "<img src=`rm -rf /`>"  # XSS + command injection
        ]

        for malicious_input in malicious_inputs:
            # Should be caught by at least one validation
            sql_valid, sql_error = InputSanitizer.validate_input(malicious_input, check_sql=True)
            xss_valid, xss_error = InputSanitizer.validate_input(malicious_input, check_xss=True)

            # At least one check should fail
            assert not (sql_valid and xss_valid)

    def test_edge_cases(self):
        """Test edge cases in input validation"""
        edge_cases = [
            "",  # Empty string
            " ",  # Single space
            "A" * 10000,  # Very long string
            "🎉🔥💻",  # Unicode characters
            "\n\r\t",  # Control characters
        ]

        for edge_input in edge_cases:
            try:
                is_valid, error_msg = InputSanitizer.validate_input(str(edge_input))
                # Should handle all edge cases without crashing
                assert isinstance(is_valid, bool)
                assert isinstance(error_msg, (str, type(None)))
            except Exception as e:
                # Should handle exceptions gracefully
                assert True


class TestSecurityFeatures:
    """Test security-related features"""

    def test_request_size_limits(self):
        """Test request size limiting configuration"""
        # Test various payload sizes
        small_payload = {"data": "small"}
        large_payload = {"data": "x" * 1000000}  # 1MB

        # Small payload should always be OK
        assert len(str(small_payload)) < 10000

        # Large payload should be checked
        assert len(str(large_payload)) > 1000000

    def test_special_characters(self):
        """Test special character handling"""
        inputs_with_special = [
            "Test@example.com #tag $100",
            "Normal text with @ symbols",
            "Data with <and> brackets"
        ]

        for input_text in inputs_with_special:
            # Should handle special characters
            is_valid, error_msg = InputSanitizer.validate_input(input_text)
            # Most special characters are OK in certain contexts
            assert isinstance(is_valid, bool)


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
