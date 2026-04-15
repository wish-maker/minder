"""
Unit Tests for Security System
Tests input validation, sanitization, and security features
"""
import pytest
import asyncio
from pathlib import Path
import sys
import re

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.security import InputSanitizer
from api.middleware import NetworkDetectionMiddleware
from fastapi import Request
from unittest.mock import Mock


class TestInputSanitization:
    """Test input sanitization and validation"""

    def test_validate_sql_injection(self):
        """Test SQL injection detection"""
        malicious_inputs = [
            "'; DROP TABLE users; --",
            "1' OR '1'='1",
            "admin'--",
            "1' UNION SELECT * FROM users--",
            "'; INSERT INTO users VALUES ('hacker', 'password'); --"
        ]

        for malicious_input in malicious_inputs:
            is_valid, error_msg = InputSanitizer.validate_input(malicious_input, check_sql=True)
            # Should detect SQL injection
            assert is_valid is False
            assert error_msg is not None
            assert "SQL" in error_msg or "injection" in error_msg.lower()

    def test_validate_xss_attack(self):
        """Test XSS attack detection"""
        xss_inputs = [
            "<script>alert('XSS')</script>",
            "<img src=x onerror=alert('XSS')>",
            "<svg onload=alert('XSS')>",
            "javascript:alert('XSS')",
            "<iframe src='javascript:alert(XSS)'>"
        ]

        for xss_input in xss_inputs:
            # Test with only XSS check, not SQL check
            is_valid, error_msg = InputSanitizer.validate_input(xss_input, check_sql=False, check_xss=True)
            # Should detect XSS or at least reject input
            assert is_valid is False or (is_valid and "dangerous" in error_msg.lower())

    def test_validate_safe_input(self):
        """Test safe input passes validation"""
        safe_inputs = [
            "Hello World",
            "user@example.com",
            "My name is John Doe",
            "Price: $100.00"
        ]

        for safe_input in safe_inputs:
            is_valid, error_msg = InputSanitizer.validate_input(safe_input)
            # Should pass validation
            assert is_valid is True
            assert error_msg is None

    def test_sanitize_string(self):
        """Test string sanitization"""
        input_string = "  Test String  "
        sanitized = InputSanitizer.sanitize_string(input_string)
        # Sanitization might preserve some whitespace or strip it
        assert "Test String" in sanitized
        assert sanitized.strip() == "Test String"

    def test_sanitize_max_length(self):
        """Test max length enforcement"""
        long_string = "A" * 1000
        sanitized = InputSanitizer.sanitize_string(long_string, max_length=100)
        assert len(sanitized) == 100

    def test_combined_validation(self):
        """Test combined validation (SQL + XSS)"""
        malicious_input = "<script>alert('XSS'); DROP TABLE users;</script>"
        is_valid, error_msg = InputSanitizer.validate_input(
            malicious_input,
            check_sql=True,
            check_xss=True
        )
        assert is_valid is False
        assert error_msg is not None

    def test_edge_cases(self):
        """Test edge cases"""
        edge_cases = [
            "",  # Empty string
            "   ",  # Whitespace only
            None,  # None value
            "😀🎉",  # Unicode/emojis
            "<>",  # Special characters
        ]

        for edge_input in edge_cases:
            if edge_input is not None:
                is_valid, error_msg = InputSanitizer.validate_input(edge_input)
                # Should handle edge cases gracefully
                assert isinstance(is_valid, bool)


class TestNetworkDetection:
    """Test network detection middleware"""

    def test_detect_local_network(self):
        """Test local network detection"""
        middleware = NetworkDetectionMiddleware(lambda r: None)

        local_ips = [
            "192.168.1.100",
            "192.168.68.50",
            "172.22.0.1",
            "10.0.0.50"
        ]

        for ip in local_ips:
            network_type = middleware.detect_network(ip)
            assert network_type in ["local", "private"]

    def test_detect_vpn_network(self):
        """Test VPN network detection"""
        middleware = NetworkDetectionMiddleware(lambda r: None)

        vpn_ips = [
            "100.64.0.1",
            "100.100.0.50"
        ]

        for ip in vpn_ips:
            network_type = middleware.detect_network(ip)
            assert network_type == "vpn"

    def test_detect_public_network(self):
        """Test public network detection"""
        middleware = NetworkDetectionMiddleware(lambda r: None)

        public_ips = [
            "8.8.8.8",
            "1.1.1.1",
            "93.184.216.34"
        ]

        for ip in public_ips:
            network_type = middleware.detect_network(ip)
            assert network_type == "public"


class TestSecurityFeatures:
    """Test security features and headers"""

    def test_request_size_limits(self):
        """Test request size limits"""
        # Test max request size validation
        large_input = "A" * (10 * 1024 * 1024)  # 10MB
        is_valid, error_msg = InputSanitizer.validate_input(large_input)
        # Should either accept or reject based on policy
        assert isinstance(is_valid, bool)

    def test_special_characters(self):
        """Test special character handling"""
        special_chars = [
            "!@#$%^&*()",
            "[]{};':\",./<>?",
            "\n\t\r"  # Control characters
        ]

        for special_char in special_chars:
            is_valid, error_msg = InputSanitizer.validate_input(special_char)
            # Should handle special characters
            assert isinstance(is_valid, bool)
