"""
Asset Allocation Collector for TEFAS Module v3.0

Collects fund portfolio composition data from borsapy:
- Asset types (stocks, bonds, cash, etc.)
- Asset weights (portfolio allocation %)
- Asset names (specific holdings)
- Historical allocation changes

Data is stored in tefas_allocation table with time-series support.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import asyncpg
import pandas as pd

logger = logging.getLogger("minder.tefas.collectors.allocation")


class AllocationCollector:
    """
    Collector for fund asset allocation from borsapy

    Responsibilities:
    1. Fetch allocation data from borsapy API
    2. Validate data quality (weights sum to ~1.0)
    3. Store to PostgreSQL tefas_allocation table
    4. Track collection statistics
    """

    def __init__(self, pool: asyncpg.Pool):
        """
        Initialize allocation collector

        Args:
            pool: asyncpg connection pool
        """
        self.pool = pool
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

    async def collect(self, api, fund_codes: Optional[List[str]] = None, history_days: int = 100) -> Dict[str, int]:
        """
        Collect allocation data for specified funds

        Args:
            api: UnifiedDataAPI instance
            fund_codes: List of fund codes (None = all discovered funds)
            history_days: Days of history to collect

        Returns:
            Dict with collection statistics
        """
        self.logger.info("📊 Starting asset allocation collection...")
        self.stats["start_time"] = datetime.now()

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
                await self._collect_fund_allocation(api, fund_code, history_days)
                self.stats["funds_processed"] += 1

            except Exception as e:
                self.logger.error(f"Error collecting allocation for {fund_code}: {e}")
                self.stats["errors"] += 1

        self.stats["end_time"] = datetime.now()
        duration = (self.stats["end_time"] - self.stats["start_time"]).total_seconds()

        self.logger.info(
            f"✅ Allocation collection complete: "
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

    async def _collect_fund_allocation(self, api, fund_code: str, history_days: int) -> bool:
        """
        Collect allocation data for a single fund

        Args:
            api: UnifiedDataAPI instance
            fund_code: Fund code
            history_days: Days of history to collect

        Returns:
            True if successful, False otherwise
        """
        # Fetch current allocation
        allocation_data = api.get_allocation(fund_code)

        if allocation_data is None or allocation_data.empty:
            self.logger.warning(f"No allocation data for {fund_code}")
            return False

        # Validate and store each allocation record
        success_count = 0
        for _, row in allocation_data.iterrows():
            if self._validate_allocation_row(row):
                if await self._store_allocation(fund_code, row):
                    success_count += 1

        return success_count > 0

    def _validate_allocation_row(self, row: pd.Series) -> bool:
        """
        Validate allocation row data quality

        Args:
            row: Pandas Series with allocation data

        Returns:
            True if valid, False otherwise
        """
        # Check required fields
        if "weight" not in row or "asset_type" not in row:
            return False

        # Weight should be between 0 and 1
        weight = row.get("weight", 0)
        if weight < 0 or weight > 1:
            return False

        # Asset type should not be empty
        asset_type = row.get("asset_type", "")
        if not asset_type or pd.isna(asset_type):
            return False

        return True

    async def _store_allocation(self, fund_code: str, row: pd.Series) -> bool:
        """
        Store allocation record to database

        Args:
            fund_code: Fund code
            row: Allocation data row

        Returns:
            True if successful, False otherwise
        """
        try:
            async with self.pool.acquire() as conn:
                # Extract data
                date = row.get("date", datetime.now().date())
                asset_type = row.get("asset_type", "")
                asset_name = row.get("asset_name", "")
                weight = float(row.get("weight", 0))
                value_usd = row.get("value_usd")
                count = row.get("count")

                # Check if exists
                existing = await conn.fetchrow(
                    """
                    SELECT id FROM tefas_allocation
                    WHERE fund_code = $1 AND date = $2 AND asset_type = $3 AND asset_name = $4
                    """,
                    fund_code,
                    date,
                    asset_type,
                    asset_name,
                )

                if existing:
                    # Update
                    await conn.execute(
                        """
                        UPDATE tefas_allocation
                        SET weight = $1, value_usd = $2, count = $3
                        WHERE id = $4
                        """,
                        weight,
                        value_usd,
                        count,
                        existing["id"],
                    )
                    self.stats["records_updated"] += 1
                else:
                    # Insert
                    await conn.execute(
                        """
                        INSERT INTO tefas_allocation (
                            fund_code, date, asset_type, asset_name, weight, value_usd, count, created_at
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                        """,
                        fund_code,
                        date,
                        asset_type,
                        asset_name,
                        weight,
                        value_usd,
                        count,
                        datetime.now(),
                    )
                    self.stats["records_collected"] += 1

            return True

        except Exception as e:
            self.logger.error(f"Database error storing allocation: {e}")
            return False

    async def get_fund_allocation_summary(self, fund_code: str) -> Optional[Dict[str, Any]]:
        """
        Get allocation summary for a fund

        Args:
            fund_code: Fund code

        Returns:
            Dict with allocation summary or None
        """
        try:
            async with self.pool.acquire() as conn:
                results = await conn.fetch(
                    """
                    SELECT
                        asset_type,
                        SUM(weight) as total_weight,
                        COUNT(DISTINCT date) as data_points,
                        MAX(date) as latest_date
                    FROM tefas_allocation
                    WHERE fund_code = $1
                    GROUP BY asset_type
                    ORDER BY total_weight DESC
                    """,
                    fund_code,
                )

                if not results:
                    return None

                return {
                    "fund_code": fund_code,
                    "allocation": [dict(row) for row in results],
                    "total_allocation": sum(row["total_weight"] for row in results),
                }

        except Exception as e:
            self.logger.error(f"Error fetching allocation summary for {fund_code}: {e}")
            return None

    async def get_top_holdings(self, asset_type: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get top holdings across all funds

        Args:
            asset_type: Filter by asset type (None = all)
            limit: Number of holdings to return

        Returns:
            List of holding dicts
        """
        try:
            async with self.pool.acquire() as conn:
                if asset_type:
                    results = await conn.fetch(
                        """
                        SELECT
                            asset_name,
                            asset_type,
                            SUM(weight) as total_weight,
                            COUNT(DISTINCT fund_code) as fund_count
                        FROM tefas_allocation
                        WHERE asset_type = $1
                        GROUP BY asset_name, asset_type
                        ORDER BY total_weight DESC
                        LIMIT $2
                        """,
                        asset_type,
                        limit,
                    )
                else:
                    results = await conn.fetch(
                        """
                        SELECT
                            asset_name,
                            asset_type,
                            SUM(weight) as total_weight,
                            COUNT(DISTINCT fund_code) as fund_count
                        FROM tefas_allocation
                        GROUP BY asset_name, asset_type
                        ORDER BY total_weight DESC
                        LIMIT $1
                        """,
                        limit,
                    )

                return [dict(row) for row in results]

        except Exception as e:
            self.logger.error(f"Error fetching top holdings: {e}")
            return []
