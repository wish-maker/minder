#!/usr/bin/env python3
"""
Integration Tests for TEFAS Module v3.0 - Complete Borsapy Integration

Tests all phases of the borsapy integration:
- Phase 1: Foundation (unified API, config, database schema)
- Phase 2: Risk Metrics Collector
- Phase 3: Asset Allocation & Tax Collectors
- Phase 4: Module Integration
- Phase 5: End-to-end Testing
"""

import sys
import unittest
import pandas as pd

# Add minder to path
sys.path.insert(0, "/root/minder")

from plugins.tefas.collectors.risk_metrics_collector import RiskMetricsCollector  # noqa: E402
from plugins.tefas.collectors.allocation_collector import AllocationCollector  # noqa: E402
from plugins.tefas.collectors.tax_collector import TaxCollector  # noqa: E402
from plugins.tefas.unified_data_api import TEFAS_CRAWLER_AVAILABLE  # noqa: E402


class TestPhase2RiskMetrics(unittest.TestCase):
    """Test Phase 2: Risk Metrics Collector"""

    def setUp(self):
        """Set up test fixtures"""
        self.db_config = {
            "host": "localhost",
            "port": 5432,
            "database": "minder_tefas",
            "user": "postgres",
            "password": "",
        }
        self.collector = RiskMetricsCollector(self.db_config)

    def test_collector_initialization(self):
        """Test collector initializes correctly"""
        self.assertIsNotNone(self.collector)
        self.assertEqual(self.collector.stats["funds_processed"], 0)

    def test_validate_metrics_good_data(self):
        """Test validation passes for good data"""
        metrics = {
            "sharpe_ratio": 1.5,
            "sortino_ratio": 2.0,
            "max_drawdown": -15.5,
            "annualized_volatility": 12.3,
            "annualized_return": 25.0,
        }

        score = self.collector._validate_metrics(metrics)
        self.assertGreater(score, 0.5)

    def test_validate_metrics_bad_data(self):
        """Test validation fails for bad data"""
        metrics = {
            "sharpe_ratio": 50.0,  # Abnormally high
            "max_drawdown": 10.0,  # Should be negative
            "annualized_volatility": -5.0,  # Should be positive
        }

        score = self.collector._validate_metrics(metrics)
        self.assertLess(score, 0.5)


class TestPhase3AllocationTax(unittest.TestCase):
    """Test Phase 3: Asset Allocation & Tax Collectors"""

    def setUp(self):
        """Set up test fixtures"""
        self.db_config = {
            "host": "localhost",
            "port": 5432,
            "database": "minder_tefas",
            "user": "postgres",
            "password": "",
        }

    def test_allocation_collector_initialization(self):
        """Test allocation collector initializes"""
        collector = AllocationCollector(self.db_config)
        self.assertIsNotNone(collector)

    def test_tax_collector_initialization(self):
        """Test tax collector initializes"""
        collector = TaxCollector(self.db_config)
        self.assertIsNotNone(collector)

    def test_validate_tax_rate(self):
        """Test tax rate validation"""
        collector = TaxCollector(self.db_config)

        # Valid tax rates
        self.assertTrue(collector._validate_tax_rate(0.0))
        self.assertTrue(collector._validate_tax_rate(0.175))
        self.assertTrue(collector._validate_tax_rate(0.20))

        # Invalid tax rates
        self.assertFalse(collector._validate_tax_rate(-0.1))
        self.assertFalse(collector._validate_tax_rate(1.5))
        self.assertFalse(collector._validate_tax_rate(None))

    def test_validate_allocation_row(self):
        """Test allocation row validation"""
        collector = AllocationCollector(self.db_config)

        # Valid row
        valid_row = pd.Series({"weight": 0.35, "asset_type": "Hisse", "asset_name": "Garanti"})
        self.assertTrue(collector._validate_allocation_row(valid_row))

        # Invalid weight
        invalid_row = pd.Series({"weight": 1.5, "asset_type": "Hisse", "asset_name": "Test"})  # Over 100%
        self.assertFalse(collector._validate_allocation_row(invalid_row))


class TestPhase4ModuleIntegration(unittest.TestCase):
    """Test Phase 4: Module Integration"""

    def test_module_v3_initialization(self):
        """Test TEFAS module v3 initializes"""
        if not TEFAS_CRAWLER_AVAILABLE:
            self.skipTest("tefas-crawler not available")

        from plugins.tefas.tefas_module_v3 import TefasModuleV3

        config = {
            "database": {
                "host": "localhost",
                "port": 5432,
                "database": "minder_tefas",
                "user": "postgres",
                "password": "",
            },
            "tefas": {"historical_start_date": "2020-01-01", "batch_days": 30},
        }

        module = TefasModuleV3(config)
        self.assertIsNotNone(module)

    def test_feature_flags(self):
        """Test feature flags control collector initialization"""
        if not TEFAS_CRAWLER_AVAILABLE:
            self.skipTest("tefas-crawler not available")

        from plugins.tefas.tefas_module_v3 import TefasModuleV3

        config = {
            "database": {
                "host": "localhost",
                "port": 5432,
                "database": "minder_tefas",
                "user": "postgres",
                "password": "",
            }
        }

        # All features disabled
        module = TefasModuleV3(config)
        self.assertIsNone(module.risk_collector)
        self.assertIsNone(module.allocation_collector)
        self.assertIsNone(module.tax_collector)


class TestPhase5EndToEnd(unittest.TestCase):
    """Test Phase 5: End-to-end Integration"""

    def test_config_loading(self):
        """Test configuration file loading"""
        import yaml
        from pathlib import Path

        config_path = Path("/root/minder/config/tefas_config.yml")
        self.assertTrue(config_path.exists())

        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        # Verify required sections
        self.assertIn("data_sources", config)
        self.assertIn("features", config)
        self.assertIn("cache", config)

    def test_database_schema_readiness(self):
        """Test database migration script is ready"""
        from pathlib import Path

        migration_path = Path("/root/minder/migrations/001_create_borsapy_tables.sql")
        self.assertTrue(migration_path.exists())

        # Read and check for key tables
        with open(migration_path, "r") as f:
            sql_content = f.read()

        required_tables = ["tefas_fund_metadata", "tefas_risk_metrics", "tefas_allocation", "tefas_tax_rates"]

        for table in required_tables:
            self.assertIn(table, sql_content.lower())

    def test_backward_compatibility(self):
        """Test backward compatibility with v2.0"""
        if not TEFAS_CRAWLER_AVAILABLE:
            self.skipTest("tefas-crawler not available")

        # v2.0 methods should still exist
        from plugins.tefas.tefas_module_v3 import TefasModuleV3

        config = {
            "database": {
                "host": "localhost",
                "port": 5432,
                "database": "minder_tefas",
                "user": "postgres",
                "password": "",
            }
        }

        module = TefasModuleV3(config)

        # Check v2.0 methods exist
        self.assertTrue(hasattr(module, "train_ai"))
        self.assertTrue(hasattr(module, "index_knowledge"))
        self.assertTrue(hasattr(module, "get_correlations"))
        self.assertTrue(hasattr(module, "get_anomalies"))
        self.assertTrue(hasattr(module, "query"))


def run_integration_tests():
    """Run all integration tests"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestPhase2RiskMetrics))
    suite.addTests(loader.loadTestsFromTestCase(TestPhase3AllocationTax))
    suite.addTests(loader.loadTestsFromTestCase(TestPhase4ModuleIntegration))
    suite.addTests(loader.loadTestsFromTestCase(TestPhase5EndToEnd))

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result


if __name__ == "__main__":
    result = run_integration_tests()

    # Print summary
    print("\n" + "=" * 70)
    print("INTEGRATION TEST SUMMARY")
    print("=" * 70)
    print(f"Tests run: {result.testsRun}")
    print(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Skipped: {len(result.skipped)}")

    if result.wasSuccessful():
        print("\n✅ ALL INTEGRATION TESTS PASSED")
    else:
        print("\n⚠️  SOME INTEGRATION TESTS FAILED")

    print("=" * 70)
