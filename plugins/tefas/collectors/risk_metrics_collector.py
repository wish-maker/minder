"""
Risk Metrics Collector for TEFAS Module v3.0

Collects risk-adjusted performance metrics from borsapy:
- Sharpe ratio (risk-adjusted return)
- Sortino ratio (downside risk)
- Maximum drawdown (peak-to-trough decline)
- Annualized volatility
- Annualized return
- Calmar ratio (return/max drawdown)

Data is stored in tefas_risk_metrics table with support for
multiple time periods (1y, 3y, 5y).
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger("minder.tefas.collectors.risk_metrics")


class RiskMetricsCollector:
    """
    Collector for fund risk metrics from borsapy

    Responsibilities:
    1. Fetch risk metrics from borsapy API
    2. Validate data quality
    3. Store to PostgreSQL tefas_risk_metrics table
    4. Track collection statistics
    """

    def __init__(self, db_config: Dict[str, Any]):
        """
        Initialize risk metrics collector

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
        self,
        api,
        fund_codes: Optional[List[str]] = None,
        periods: Optional[List[str]] = None,
    ) -> Dict[str, int]:
        """
        Collect risk metrics for specified funds and periods

        Args:
            api: UnifiedDataAPI instance
            fund_codes: List of fund codes (None = all discovered funds)
            periods: List of periods (None = ['1y', '3y'])

        Returns:
            Dict with collection statistics
        """
        self.logger.info("📊 Starting risk metrics collection...")
        self.stats["start_time"] = datetime.now()

        # Default periods
        if periods is None:
            periods = ["1y", "3y"]

        # Discover funds if not provided
        if fund_codes is None:
            discovered = api.discover_funds()
            fund_codes = []
            for funds in discovered.values():
                fund_codes.extend(list(funds))
            self.logger.info(f"Discovered {len(fund_codes)} funds")

        # Collect for each fund and period
        for fund_code in fund_codes:
            for period in periods:
                try:
                    self._collect_fund_period(api, fund_code, period)
                    self.stats["funds_processed"] += 1

                except Exception as e:
                    self.logger.error(f"Error collecting {fund_code} ({period}): {e}")
                    self.stats["errors"] += 1

        self.stats["end_time"] = datetime.now()
        duration = (self.stats["end_time"] - self.stats["start_time"]).total_seconds()

        self.logger.info(
            f"✅ Risk metrics collection complete: "
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

    def _collect_fund_period(self, api, fund_code: str, period: str) -> bool:
        """
        Collect risk metrics for a single fund and period

        Args:
            api: UnifiedDataAPI instance
            fund_code: Fund code
            period: Time period ('1y', '3y', '5y')

        Returns:
            True if successful, False otherwise
        """
        # Fetch risk metrics from borsapy
        metrics_data = api.get_risk_metrics(fund_code, period)

        if metrics_data is None:
            self.logger.warning(f"No risk metrics for {fund_code} ({period})")
            return False

        # Validate data quality
        quality_score = self._validate_metrics(metrics_data)
        if quality_score < 0.5:
            self.logger.warning(f"Low quality score {quality_score:.2f} for {fund_code} ({period})")
            return False

        # Store to database
        return self._store_metrics(fund_code, period, metrics_data)

    def _validate_metrics(self, metrics: Dict[str, Any]) -> float:
        """
        Validate risk metrics data quality

        Args:
            metrics: Risk metrics dict

        Returns:
            Quality score between 0.0 (bad) and 1.0 (good)
        """
        score = 1.0

        # Check for required fields
        if metrics.get("sharpe_ratio") is None:
            score -= 0.2

        if metrics.get("max_drawdown") is None:
            score -= 0.2

        # Check for reasonable values
        sharpe = metrics.get("sharpe_ratio", 0)
        if sharpe > 10 or sharpe < -10:  # Abnormal
            score -= 0.3  # Increased penalty

        max_dd = metrics.get("max_drawdown", 0)
        if max_dd > 0 or max_dd < -100:  # Max drawdown should be negative
            score -= 0.3  # Increased penalty

        volatility = metrics.get("annualized_volatility", 0)
        if volatility < 0 or volatility > 200:  # Should be positive and reasonable
            score -= 0.3  # Increased penalty

        return max(0.0, score)

    def _store_metrics(self, fund_code: str, period: str, metrics: Dict[str, Any]) -> bool:
        """
        Store risk metrics to database

        Args:
            fund_code: Fund code
            period: Time period
            metrics: Risk metrics dict

        Returns:
            True if successful, False otherwise
        """
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()

            # Check if record exists
            cursor.execute(
                """
                SELECT id FROM tefas_risk_metrics
                WHERE fund_code = %s AND period = %s
                """,
                (fund_code, period),
            )

            existing = cursor.fetchone()

            # Extract metrics
            sharpe = metrics.get("sharpe_ratio")
            sortino = metrics.get("sortino_ratio")
            max_dd = metrics.get("max_drawdown")
            volatility = metrics.get("annualized_volatility")
            annual_return = metrics.get("annualized_return")
            calmar = metrics.get("calmar_ratio")
            var_95 = metrics.get("var_95")

            if existing:
                # Update existing record
                cursor.execute(
                    """
                    UPDATE tefas_risk_metrics
                    SET sharpe_ratio = %s,
                        sortino_ratio = %s,
                        max_drawdown = %s,
                        annualized_volatility = %s,
                        annualized_return = %s,
                        calmar_ratio = %s,
                        var_95 = %s,
                        calculated_at = %s
                    WHERE fund_code = %s AND period = %s
                    """,
                    (
                        sharpe,
                        sortino,
                        max_dd,
                        volatility,
                        annual_return,
                        calmar,
                        var_95,
                        datetime.now(),
                        fund_code,
                        period,
                    ),
                )
                self.stats["records_updated"] += 1
            else:
                # Insert new record
                cursor.execute(
                    """
                    INSERT INTO tefas_risk_metrics (
                        fund_code, period,
                        sharpe_ratio, sortino_ratio, max_drawdown,
                        annualized_volatility, annualized_return,
                        calmar_ratio, var_95, calculated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        fund_code,
                        period,
                        sharpe,
                        sortino,
                        max_dd,
                        volatility,
                        annual_return,
                        calmar,
                        var_95,
                        datetime.now(),
                    ),
                )
                self.stats["records_collected"] += 1

            conn.commit()
            conn.close()

            return True

        except Exception as e:
            self.logger.error(f"Database error storing metrics for {fund_code}: {e}")
            return False

    def get_top_funds_by_sharpe(
        self, period: str = "1y", limit: int = 10, min_data_points: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get top performing funds by Sharpe ratio

        Args:
            period: Time period
            limit: Number of funds to return
            min_data_points: Minimum data points required

        Returns:
            List of fund dicts with risk metrics
        """
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            cursor.execute(
                """
                SELECT
                    m.fund_code,
                    m.title,
                    r.period,
                    r.sharpe_ratio,
                    r.sortino_ratio,
                    r.max_drawdown,
                    r.annualized_return,
                    r.calmar_ratio,
                    r.calculated_at
                FROM tefas_risk_metrics r
                JOIN tefas_fund_metadata m ON r.fund_code = m.fund_code
                WHERE r.period = %s
                    AND r.sharpe_ratio IS NOT NULL
                ORDER BY r.sharpe_ratio DESC
                LIMIT %s
                """,
                (period, limit),
            )

            results = cursor.fetchall()
            conn.close()

            return [dict(row) for row in results]

        except Exception as e:
            self.logger.error(f"Error fetching top funds: {e}")
            return []

    def get_fund_risk_summary(self, fund_code: str) -> Optional[Dict[str, Any]]:
        """
        Get risk summary for a specific fund across all periods

        Args:
            fund_code: Fund code

        Returns:
            Dict with risk summary or None
        """
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            cursor.execute(
                """
                SELECT
                    fund_code,
                    period,
                    sharpe_ratio,
                    sortino_ratio,
                    max_drawdown,
                    annualized_volatility,
                    annualized_return,
                    calculated_at
                FROM tefas_risk_metrics
                WHERE fund_code = %s
                ORDER BY period
                """,
                (fund_code,),
            )

            results = cursor.fetchall()
            conn.close()

            if not results:
                return None

            return {
                "fund_code": fund_code,
                "metrics": {row["period"]: dict(row) for row in results},
                "periods_available": len(results),
            }

        except Exception as e:
            self.logger.error(f"Error fetching risk summary for {fund_code}: {e}")
            return None
