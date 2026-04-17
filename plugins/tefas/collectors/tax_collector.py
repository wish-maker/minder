"""
Tax Rates Collector for TEFAS Module v3.0

Collects withholding tax rates by fund category from borsapy:
- Tax categories (degisken_karma_doviz, pay_senedi_yogun, etc.)
- Withholding tax rates (0.175 = %17.5)
- Effective dates
- Regulatory references

Data is stored in tefas_tax_rates table with time-series support
for tracking tax rate changes over time.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger("minder.tefas.collectors.tax")


class TaxCollector:
    """
    Collector for fund withholding tax rates from borsapy

    Responsibilities:
    1. Fetch tax rates from borsapy API
    2. Validate data quality (0-1 range)
    3. Store to PostgreSQL tefas_tax_rates table
    4. Track collection statistics
    """

    def __init__(self, db_config: Dict[str, Any]):
        """
        Initialize tax collector

        Args:
            db_config: Database connection config
        """
        self.db_config = db_config
        self.logger = logger

        # Collection statistics
        self.stats = {
            "funds_processed": 0,
            "records_collected": 0,
            "records_updated": 0,
            "errors": 0,
            "start_time": None,
            "end_time": None,
        }

    def collect(
        self, api, fund_codes: Optional[List[str]] = None, effective_date: Optional[str] = None
    ) -> Dict[str, int]:
        """
        Collect tax rates for specified funds

        Args:
            api: UnifiedDataAPI instance
            fund_codes: List of fund codes (None = all discovered funds)
            effective_date: Date for tax rate (None = today)

        Returns:
            Dict with collection statistics
        """
        self.logger.info("📊 Starting tax rates collection...")
        self.stats["start_time"] = datetime.now()

        # Default to today
        if effective_date is None:
            effective_date = datetime.now().strftime("%Y-%m-%d")

        # Discover funds if not provided
        if fund_codes is None:
            discovered = api.discover_funds()
            fund_codes = []
            for funds in discovered.values():
                fund_codes.extend(list(funds))
            self.logger.info(f"Discovered {len(fund_codes)} funds")

        # Collect for each fund
        for fund_code in fund_codes:
            try:
                self._collect_fund_tax_rate(api, fund_code, effective_date)
                self.stats["funds_processed"] += 1

            except Exception as e:
                self.logger.error(f"Error collecting tax rate for {fund_code}: {e}")
                self.stats["errors"] += 1

        self.stats["end_time"] = datetime.now()
        duration = (self.stats["end_time"] - self.stats["start_time"]).total_seconds()

        self.logger.info(
            f"✅ Tax rates collection complete: "
            f"{self.stats['records_collected']} collected, "
            f"{self.stats['records_updated']} updated, "
            f"{self.stats['errors']} errors "
            f"({duration:.1f}s)"
        )

        return {
            "records_collected": self.stats["records_collected"],
            "records_updated": self.stats["records_updated"],
            "errors": self.stats["errors"],
        }

    def _collect_fund_tax_rate(self, api, fund_code: str, effective_date: str) -> bool:
        """
        Collect tax rate for a single fund

        Args:
            api: UnifiedDataAPI instance
            fund_code: Fund code
            effective_date: Effective date

        Returns:
            True if successful, False otherwise
        """
        # Get tax category first
        tax_category = api.get_tax_category(fund_code)

        if tax_category is None:
            self.logger.debug(f"No tax category for {fund_code}")
            return False

        # Get tax rate
        tax_rate = api.get_tax_rate(fund_code, effective_date)

        if tax_rate is None:
            self.logger.debug(f"No tax rate for {fund_code} on {effective_date}")
            return False

        # Validate
        if not self._validate_tax_rate(tax_rate):
            self.logger.warning(f"Invalid tax rate {tax_rate} for {fund_code}")
            return False

        # Store to database
        return self._store_tax_rate(fund_code, tax_category, effective_date, tax_rate)

    def _validate_tax_rate(self, rate: float) -> bool:
        """
        Validate tax rate value

        Args:
            rate: Tax rate (decimal, e.g., 0.175 for 17.5%)

        Returns:
            True if valid, False otherwise
        """
        # Tax rate should be between 0 and 1
        if rate is None or rate < 0 or rate > 1:
            return False

        return True

    def _store_tax_rate(self, fund_code: str, tax_category: str, effective_date: str, rate: float) -> bool:
        """
        Store tax rate to database

        Args:
            fund_code: Fund code
            tax_category: Tax category
            effective_date: Effective date
            rate: Tax rate

        Returns:
            True if successful, False otherwise
        """
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()

            # Check if exists
            cursor.execute(
                """
                SELECT id FROM tefas_tax_rates
                WHERE fund_code = %s AND effective_date = %s
                """,
                (fund_code, effective_date),
            )

            existing = cursor.fetchone()

            if existing:
                # Update
                cursor.execute(
                    """
                    UPDATE tefas_tax_rates
                    SET tax_category = %s, rate = %s, updated_at = %s
                    WHERE id = %s
                    """,
                    (tax_category, rate, datetime.now(), existing[0]),
                )
                self.stats["records_updated"] += 1
            else:
                # Insert
                cursor.execute(
                    """
                    INSERT INTO tefas_tax_rates (
                        fund_code, tax_category, effective_date, rate, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (fund_code, tax_category, effective_date, rate, datetime.now(), datetime.now()),
                )
                self.stats["records_collected"] += 1

            conn.commit()
            conn.close()

            return True

        except Exception as e:
            self.logger.error(f"Database error storing tax rate for {fund_code}: {e}")
            return False

    def get_tax_summary(self, effective_date: Optional[str] = None) -> Dict[str, Any]:
        """
        Get tax summary by category

        Args:
            effective_date: Effective date (None = latest)

        Returns:
            Dict with tax summary
        """
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            if effective_date:
                cursor.execute(
                    """
                    SELECT
                        tax_category,
                        AVG(rate) as avg_rate,
                        MIN(rate) as min_rate,
                        MAX(rate) as max_rate,
                        COUNT(*) as fund_count
                    FROM tefas_tax_rates
                    WHERE effective_date <= %s
                    GROUP BY tax_category
                    ORDER BY tax_category
                    """,
                    (effective_date,),
                )
            else:
                cursor.execute(
                    """
                    SELECT
                        tax_category,
                        AVG(rate) as avg_rate,
                        MIN(rate) as min_rate,
                        MAX(rate) as max_rate,
                        COUNT(*) as fund_count
                    FROM tefas_tax_rates
                    GROUP BY tax_category
                    ORDER BY tax_category
                    """
                )

            results = cursor.fetchall()
            conn.close()

            return {"summary": [dict(row) for row in results], "categories": len(results)}

        except Exception as e:
            self.logger.error(f"Error fetching tax summary: {e}")
            return {}

    def get_fund_tax_rate(self, fund_code: str, date: str) -> Optional[float]:
        """
        Get tax rate for a specific fund on a specific date

        Args:
            fund_code: Fund code
            date: Date

        Returns:
            Tax rate or None
        """
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT rate
                FROM tefas_tax_rates
                WHERE fund_code = %s AND effective_date <= %s
                ORDER BY effective_date DESC
                LIMIT 1
                """,
                (fund_code, date),
            )

            result = cursor.fetchone()
            conn.close()

            return result[0] if result else None

        except Exception as e:
            self.logger.error(f"Error fetching tax rate for {fund_code}: {e}")
            return None

    def get_tax_categories(self) -> List[str]:
        """
        Get all unique tax categories

        Returns:
            List of tax categories
        """
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT DISTINCT tax_category
                FROM tefas_tax_rates
                ORDER BY tax_category
                """
            )

            results = cursor.fetchall()
            conn.close()

            return [row[0] for row in results if row[0]]

        except Exception as e:
            self.logger.error(f"Error fetching tax categories: {e}")
            return []
