#!/usr/bin/env python3
"""
Minder Data Verification System
Version: 1.0.0
Description: Verifies data collection, database integrity, and plugin health
"""

import asyncio
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

import psycopg2
from pydantic import BaseModel

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class VerificationResult(BaseModel):
    """Verification result for a component"""
    name: str
    status: str  # "pass", "warn", "fail"
    message: str
    details: Dict[str, Any] = {}
    timestamp: datetime = datetime.now()


class DataVerifier:
    """Main data verification system"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.results: List[VerificationResult] = []

        # Database config
        self.db_config = {
            "host": config.get("database", {}).get("host", "localhost"),
            "port": config.get("database", {}).get("port", 5432),
            "user": config.get("database", {}).get("user", "postgres"),
            "password": config.get("database", {}).get("password", ""),
        }

    def add_result(self, name: str, status: str, message: str, details: Dict[str, Any] = None):
        """Add a verification result"""
        result = VerificationResult(
            name=name,
            status=status,
            message=message,
            details=details or {},
        )
        self.results.append(result)
        return result

    async def verify_all(self) -> Dict[str, Any]:
        """Run all verifications"""
        logger.info("🔍 Starting Minder Data Verification...")

        # 1. Database connectivity
        await self._verify_database_connectivity()

        # 2. Table structure
        await self._verify_table_structure()

        # 3. Data freshness
        await self._verify_data_freshness()

        # 4. Data quality
        await self._verify_data_quality()

        # 5. Plugin configuration
        await self._verify_plugin_config()

        # Generate summary
        return self._generate_summary()

    async def _verify_database_connectivity(self):
        """Verify all databases are accessible"""
        logger.info("📊 Verifying database connectivity...")

        databases = {
            "fundmind": "TEFAS fund data",
            "minder_news": "News articles",
            "minder_weather": "Weather data",
            "minder_crypto": "Crypto prices",
            "minder_network": "Network metrics",
        }

        for db_name, description in databases.items():
            try:
                conn = psycopg2.connect(
                    dbname=db_name,
                    **self.db_config
                )
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.close()
                conn.close()

                self.add_result(
                    name=f"Database: {db_name}",
                    status="pass",
                    message=f"{description} database accessible",
                    details={"database": db_name}
                )

            except Exception as e:
                self.add_result(
                    name=f"Database: {db_name}",
                    status="fail",
                    message=f"Cannot connect: {str(e)}",
                    details={"database": db_name, "error": str(e)}
                )

    async def _verify_table_structure(self):
        """Verify all required tables exist"""
        logger.info("📋 Verifying table structure...")

        tables = {
            "fundmind": ["tefas_fund_data"],
            "minder_news": ["news_articles"],
            "minder_weather": ["weather_data"],
            "minder_crypto": ["crypto_data"],
            "minder_network": ["network_metrics"],
        }

        for db_name, expected_tables in tables.items():
            try:
                conn = psycopg2.connect(dbname=db_name, **self.db_config)
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                    AND table_type = 'BASE TABLE'
                """)
                existing_tables = {row[0] for row in cursor.fetchall()}

                conn.close()

                missing_tables = set(expected_tables) - existing_tables

                if missing_tables:
                    self.add_result(
                        name=f"Tables: {db_name}",
                        status="fail",
                        message=f"Missing tables: {', '.join(missing_tables)}",
                        details={"database": db_name, "missing": list(missing_tables)}
                    )
                else:
                    self.add_result(
                        name=f"Tables: {db_name}",
                        status="pass",
                        message=f"All {len(expected_tables)} tables exist",
                        details={"database": db_name, "tables": list(existing_tables)}
                    )

            except Exception as e:
                self.add_result(
                    name=f"Tables: {db_name}",
                    status="fail",
                    message=f"Error checking tables: {str(e)}",
                    details={"database": db_name, "error": str(e)}
                )

    async def _verify_data_freshness(self):
        """Verify data is being collected recently"""
        logger.info("🕐 Verifying data freshness...")

        queries = {
            "fundmind": {
                "table": "tefas_fund_data",
                "name": "TEFAS funds",
                "max_age_hours": 48  # TEFAS data may be older
            },
            "minder_news": {
                "table": "news_articles",
                "name": "News articles",
                "max_age_hours": 24
            },
            "minder_weather": {
                "table": "weather_data",
                "name": "Weather data",
                "max_age_hours": 2  # Weather should be very recent
            },
            "minder_crypto": {
                "table": "crypto_data",
                "name": "Crypto prices",
                "max_age_hours": 1  # Crypto should be very recent
            },
            "minder_network": {
                "table": "network_metrics",
                "name": "Network metrics",
                "max_age_hours": 1  # Network metrics should be recent
            },
        }

        for db_name, query_info in queries.items():
            try:
                conn = psycopg2.connect(dbname=db_name, **self.db_config)
                cursor = conn.cursor()

                # Get latest timestamp
                cursor.execute(f"""
                    SELECT
                        COUNT(*) as total_records,
                        MAX(timestamp) as latest_timestamp
                    FROM {query_info['table']}
                """)

                row = cursor.fetchone()
                total_records = row[0]
                latest_timestamp = row[1]

                conn.close()

                if total_records == 0:
                    self.add_result(
                        name=f"Freshness: {query_info['name']}",
                        status="warn",
                        message="No data collected yet",
                        details={
                            "database": db_name,
                            "table": query_info['table'],
                            "records": 0
                        }
                    )
                    continue

                # Calculate age
                if latest_timestamp:
                    age = datetime.now() - latest_timestamp
                    age_hours = age.total_seconds() / 3600

                    if age_hours <= query_info['max_age_hours']:
                        self.add_result(
                            name=f"Freshness: {query_info['name']}",
                            status="pass",
                            message=f"Data is fresh ({age_hours:.1f} hours old)",
                            details={
                                "database": db_name,
                                "table": query_info['table'],
                                "records": total_records,
                                "age_hours": round(age_hours, 1)
                            }
                        )
                    else:
                        self.add_result(
                            name=f"Freshness: {query_info['name']}",
                            status="warn",
                            message=f"Data is stale ({age_hours:.1f} hours old)",
                            details={
                                "database": db_name,
                                "table": query_info['table'],
                                "records": total_records,
                                "age_hours": round(age_hours, 1),
                                "max_age_hours": query_info['max_age_hours']
                            }
                        )
                else:
                    self.add_result(
                        name=f"Freshness: {query_info['name']}",
                        status="fail",
                        message="No timestamp data available",
                        details={
                            "database": db_name,
                            "table": query_info['table'],
                            "records": total_records
                        }
                    )

            except Exception as e:
                self.add_result(
                    name=f"Freshness: {query_info['name']}",
                    status="fail",
                    message=f"Error checking freshness: {str(e)}",
                    details={"database": db_name, "error": str(e)}
                )

    async def _verify_data_quality(self):
        """Verify data quality (no nulls, valid ranges, etc.)"""
        logger.info("✅ Verifying data quality...")

        # Check for NULL values in critical fields
        quality_checks = {
            "fundmind": {
                "table": "tefas_fund_data",
                "critical_fields": ["code", "date", "price"],
                "name": "TEFAS data"
            },
            "minder_news": {
                "table": "news_articles",
                "critical_fields": ["title", "source"],
                "name": "News data"
            },
            "minder_weather": {
                "table": "weather_data",
                "critical_fields": ["location", "temperature_c"],
                "name": "Weather data"
            },
            "minder_crypto": {
                "table": "crypto_data",
                "critical_fields": ["symbol", "price"],
                "name": "Crypto data"
            },
        }

        for db_name, check_info in quality_checks.items():
            try:
                conn = psycopg2.connect(dbname=db_name, **self.db_config)
                cursor = conn.cursor()

                for field in check_info['critical_fields']:
                    cursor.execute(f"""
                        SELECT COUNT(*)
                        FROM {check_info['table']}
                        WHERE {field} IS NULL
                    """)

                    null_count = cursor.fetchone()[0]

                    if null_count > 0:
                        self.add_result(
                            name=f"Quality: {check_info['name']}.{field}",
                            status="warn",
                            message=f"{null_count} NULL values found",
                            details={
                                "database": db_name,
                                "table": check_info['table'],
                                "field": field,
                                "null_count": null_count
                            }
                        )

                conn.close()

                # If we got here without warnings, mark as pass
                if not any(r.name.startswith(f"Quality: {check_info['name']}") for r in self.results):
                    self.add_result(
                        name=f"Quality: {check_info['name']}",
                        status="pass",
                        message="All critical fields have valid data",
                        details={
                            "database": db_name,
                            "table": check_info['table']
                        }
                    )

            except Exception as e:
                self.add_result(
                    name=f"Quality: {check_info['name']}",
                    status="fail",
                    message=f"Error checking quality: {str(e)}",
                    details={"database": db_name, "error": str(e)}
                )

    async def _verify_plugin_config(self):
        """Verify plugin configuration is correct"""
        logger.info("⚙️  Verifying plugin configuration...")

        # Check if config files exist
        config_files = [
            "/root/minder/config.yaml",
            "/root/minder/.env",
        ]

        for config_file in config_files:
            if Path(config_file).exists():
                self.add_result(
                    name=f"Config: {Path(config_file).name}",
                    status="pass",
                    message="Configuration file exists",
                    details={"file": config_file}
                )
            else:
                self.add_result(
                    name=f"Config: {Path(config_file).name}",
                    status="warn",
                    message="Configuration file missing",
                    details={"file": config_file}
                )

    def _generate_summary(self) -> Dict[str, Any]:
        """Generate verification summary"""
        total = len(self.results)
        passed = sum(1 for r in self.results if r.status == "pass")
        warned = sum(1 for r in self.results if r.status == "warn")
        failed = sum(1 for r in self.results if r.status == "fail")

        overall_status = "pass" if failed == 0 else "fail" if warned == 0 else "warn"

        summary = {
            "overall_status": overall_status,
            "total_checks": total,
            "passed": passed,
            "warned": warned,
            "failed": failed,
            "results": [r.dict() for r in self.results],
            "timestamp": datetime.now().isoformat()
        }

        return summary


def print_summary(summary: Dict[str, Any]):
    """Print verification summary"""
    status_colors = {
        "pass": "\033[92m✓\033[0m",  # Green
        "warn": "\033[93m⚠\033[0m",  # Yellow
        "fail": "\033[91m✗\033[0m",  # Red
    }

    print("\n" + "=" * 60)
    print("MINDER DATA VERIFICATION REPORT")
    print("=" * 60)
    print(f"Timestamp: {summary['timestamp']}")
    print(f"Overall Status: {summary['overall_status'].upper()}")
    print(f"\nSummary:")
    print(f"  Total Checks: {summary['total_checks']}")
    print(f"  Passed: {summary['passed']}")
    print(f"  Warnings: {summary['warned']}")
    print(f"  Failed: {summary['failed']}")
    print("\nDetailed Results:")
    print("-" * 60)

    for result in summary['results']:
        status_icon = status_colors.get(result['status'], "?")
        print(f"{status_icon} {result['name']}: {result['message']}")

    print("=" * 60)

    # Print recommendations
    if summary['failed'] > 0:
        print("\n🚨 CRITICAL ISSUES FOUND:")
        print("  1. Check database connectivity")
        print("  2. Run: ./scripts/database/01_init_databases.sh")
        print("  3. Verify plugin configuration")
    elif summary['warned'] > 0:
        print("\n⚠️  WARNINGS:")
        print("  1. Data may be stale - check collection jobs")
        print("  2. Review plugin logs: docker-compose logs -f minder")
        print("  3. Run data collection manually if needed")
    else:
        print("\n✅ ALL CHECKS PASSED!")
        print("  System is healthy and data is being collected.")


async def main():
    """Main entry point"""
    # Load config
    import yaml

    config_path = Path("/root/minder/config.yaml")
    if not config_path.exists():
        logger.error("config.yaml not found")
        sys.exit(1)

    with open(config_path) as f:
        config = yaml.safe_load(f)

    # Override password from environment
    import os
    db_password = os.getenv("POSTGRES_PASSWORD")
    if db_password:
        config["database"]["password"] = db_password

    # Run verification
    verifier = DataVerifier(config)
    summary = await verifier.verify_all()

    # Print results
    print_summary(summary)

    # Exit with appropriate code
    if summary['failed'] > 0:
        sys.exit(1)
    elif summary['warned'] > 0:
        sys.exit(2)
    else:
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
