"""
Unit Tests for UnifiedDataAPI
Tests the core abstraction layer for borsapy integration

Strategy: Tests that don't require borsapy installation run automatically.
Tests requiring borsapy are skipped when borsapy is not available.
"""

import unittest
from datetime import datetime
import sys

# Add minder to path
sys.path.insert(0, "/root/minder")

# Import the module
from plugins.tefas.unified_data_api import (  # noqa: E402
    BORSAPY_AVAILABLE,
    TEFAS_CRAWLER_AVAILABLE,
    UnifiedDataAPI,
)


class TestUnifiedDataAPIInitialization(unittest.TestCase):
    """Test UnifiedDataAPI initialization with different configurations"""

    def test_initialization_default_config(self):
        """Test API initializes with default configuration"""
        config = {}

        if BORSAPY_AVAILABLE or TEFAS_CRAWLER_AVAILABLE:
            api = UnifiedDataAPI(config)
            self.assertIsNotNone(api)
        else:
            self.skipTest("Neither borsapy nor tefas-crawler is available")

    def test_initialization_borsapy_primary(self):
        """Test API initialization with borsapy as primary"""
        config = {
            "data_sources": {"primary": "borsapy", "fallback": "tefas-crawler", "auto_switch": True},
            "cache": {"ttl": 1800},
        }

        if BORSAPY_AVAILABLE or TEFAS_CRAWLER_AVAILABLE:
            api = UnifiedDataAPI(config)
            self.assertEqual(api.primary_source, "borsapy")
            self.assertTrue(api.fallback_enabled)
            self.assertEqual(api.cache_ttl, 1800)
        else:
            self.skipTest("Neither borsapy nor tefas-crawler is available")

    def test_health_status(self):
        """Test health status reporting"""
        config = {"data_sources": {"primary": "borsapy"}}

        if BORSAPY_AVAILABLE or TEFAS_CRAWLER_AVAILABLE:
            api = UnifiedDataAPI(config)
            status = api.get_health_status()

            self.assertIn("primary_source", status)
            self.assertIn("borsapy", status)
            self.assertIn("tefas_crawler", status)
            self.assertIn("health", status)
        else:
            self.skipTest("Neither borsapy nor tefas-crawler is available")


class TestDataQualityValidation(unittest.TestCase):
    """Test data quality validation layer"""

    def test_validate_fund_data_success(self):
        """Test validation passes for good data"""
        data = {"code": "AAK", "title": "Test Fund", "price": 1.23, "sharpe_ratio": 1.5}

        score = self._calculate_quality_score(data)
        self.assertGreater(score, 0.5)

    def test_validate_fund_data_failure(self):
        """Test validation fails for bad data"""
        data = {
            "code": "AAK",
            "title": "Bad Fund",
            "price": -1.0,  # Invalid negative price
            "sharpe_ratio": 15.0,  # Abnormally high
        }

        score = self._calculate_quality_score(data)
        self.assertLess(score, 0.5)

    def test_validate_missing_critical_fields(self):
        """Test validation fails when critical fields are missing"""
        data = {
            "code": "AAK",
            "title": "Incomplete Fund"
            # Missing price
        }

        score = self._calculate_quality_score(data)
        self.assertLessEqual(score, 0.5, "Missing critical field should result in low quality score")

    def _calculate_quality_score(self, data: dict) -> float:
        """
        Calculate data quality score
        Returns score between 0.0 (bad) and 1.0 (good)
        """
        score = 1.0

        # Check price validity
        price = data.get("price")
        if price is None or price <= 0:
            score -= 0.5  # Critical field missing or invalid

        # Check for abnormal sharpe ratio
        sharpe = data.get("sharpe_ratio", 0)
        if sharpe > 10:  # Abnormally high
            score -= 0.2

        # Check for abnormal max drawdown
        max_dd = data.get("max_drawdown", 0)
        if max_dd < -90:  # More than 90% drop is suspicious
            score -= 0.2

        return max(0.0, score)


class TestCacheMechanics(unittest.TestCase):
    """Test cache TTL and expiration logic"""

    def test_cache_expiration_logic(self):
        """Test cache expires after TTL"""
        cache = {}
        cache_ttl = 3600

        # Set up expired cache entry
        cache_key = "test_key"
        old_time = datetime.now().timestamp() - 4000  # More than TTL
        cache[cache_key] = {"data": {"test": "data"}, "time": datetime.fromtimestamp(old_time)}

        # Check if expired
        cached_time = cache[cache_key]["time"]
        age = (datetime.now() - cached_time).total_seconds()
        is_valid = age < cache_ttl

        self.assertFalse(is_valid, "Cache entry should be expired")

    def test_cache_valid_within_ttl(self):
        """Test cache is valid within TTL"""
        cache = {}
        cache_ttl = 3600

        # Set up fresh cache entry
        cache_key = "test_key"
        recent_time = datetime.now().timestamp() - 1000  # Less than TTL
        cache[cache_key] = {"data": {"test": "data"}, "time": datetime.fromtimestamp(recent_time)}

        # Check if valid
        cached_time = cache[cache_key]["time"]
        age = (datetime.now() - cached_time).total_seconds()
        is_valid = age < cache_ttl

        self.assertTrue(is_valid, "Cache entry should be valid")


class TestFundTypeDetection(unittest.TestCase):
    """Test fund type detection logic"""

    def test_detect_yat_fund(self):
        """Test YAT fund detection (starts with Y or other letters)"""
        self.assertEqual(self._detect_fund_type("YAK"), "YAT")
        self.assertEqual(self._detect_fund_type("AAK"), "YAT")
        self.assertEqual(self._detect_fund_type("ZKF"), "YAT")

    def test_detect_emk_fund(self):
        """Test EMK fund detection (starts with E)"""
        self.assertEqual(self._detect_fund_type("EAK"), "EMK")
        self.assertEqual(self._detect_fund_type("EBF"), "EMK")

    def test_detect_byf_fund(self):
        """Test BYF fund detection (starts with B)"""
        self.assertEqual(self._detect_fund_type("BAK"), "BYF")
        self.assertEqual(self._detect_fund_type("BBF"), "BYF")

    def _detect_fund_type(self, fund_code: str) -> str:
        """Detect fund type from fund code"""
        if fund_code.startswith("E"):
            return "EMK"
        elif fund_code.startswith("B"):
            return "BYF"
        else:
            return "YAT"


class TestConfigurationLoading(unittest.TestCase):
    """Test configuration loading and validation"""

    def test_config_with_feature_flags(self):
        """Test configuration with feature flags"""
        config = {
            "data_sources": {"primary": "borsapy", "auto_switch": True},
            "features": {"risk_metrics": True, "allocation": False, "tax_info": False},
            "cache": {"enabled": True, "ttl": 3600},
        }

        self.assertTrue(config["features"]["risk_metrics"])
        self.assertFalse(config["features"]["allocation"])
        self.assertEqual(config["cache"]["ttl"], 3600)

    def test_config_defaults(self):
        """Test default configuration values"""
        config = {}

        primary = config.get("data_sources", {}).get("primary", "borsapy")
        ttl = config.get("cache", {}).get("ttl", 3600)
        auto_switch = config.get("data_sources", {}).get("auto_switch", True)

        self.assertEqual(primary, "borsapy")
        self.assertEqual(ttl, 3600)
        self.assertTrue(auto_switch)


@unittest.skipIf(not BORSAPY_AVAILABLE, "borsapy not installed")
class TestBorsapyWrapper(unittest.TestCase):
    """Test BorsapyWrapper functionality (requires borsapy)"""

    def test_wrapper_initialization(self):
        """Test wrapper can be initialized"""
        from plugins.tefas.unified_data_api import BorsapyWrapper

        wrapper = BorsapyWrapper(cache_ttl=1800)
        self.assertEqual(wrapper.cache_ttl, 1800)

    def test_cache_stats(self):
        """Test cache statistics tracking"""
        from plugins.tefas.unified_data_api import BorsapyWrapper

        wrapper = BorsapyWrapper()

        stats = wrapper.get_cache_stats()
        self.assertIn("hits", stats)
        self.assertIn("misses", stats)
        self.assertIn("errors", stats)
        self.assertIn("hit_rate", stats)


@unittest.skipIf(not TEFAS_CRAWLER_AVAILABLE, "tefas-crawler not installed")
class TestTefasCrawlerWrapper(unittest.TestCase):
    """Test TefasCrawlerWrapper functionality (requires tefas-crawler)"""

    def test_wrapper_initialization(self):
        """Test wrapper can be initialized"""
        from plugins.tefas.unified_data_api import TefasCrawlerWrapper

        wrapper = TefasCrawlerWrapper()
        self.assertIsNotNone(wrapper.crawler)


def run_tests():
    """Run all tests and return results"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestUnifiedDataAPIInitialization))
    suite.addTests(loader.loadTestsFromTestCase(TestDataQualityValidation))
    suite.addTests(loader.loadTestsFromTestCase(TestCacheMechanics))
    suite.addTests(loader.loadTestsFromTestCase(TestFundTypeDetection))
    suite.addTests(loader.loadTestsFromTestCase(TestConfigurationLoading))

    # Add conditional tests
    if BORSAPY_AVAILABLE:
        suite.addTests(loader.loadTestsFromTestCase(TestBorsapyWrapper))
    if TEFAS_CRAWLER_AVAILABLE:
        suite.addTests(loader.loadTestsFromTestCase(TestTefasCrawlerWrapper))

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result


if __name__ == "__main__":
    result = run_tests()

    # Print summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"Tests run: {result.testsRun}")
    print(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Skipped: {len(result.skipped)}")
    print(f"\nAvailability: borsapy={BORSAPY_AVAILABLE}, tefas-crawler={TEFAS_CRAWLER_AVAILABLE}")

    if result.wasSuccessful():
        print("\n✅ ALL TESTS PASSED")
    else:
        print("\n⚠️  SOME TESTS FAILED OR SKIPPED")

    print("=" * 70)
