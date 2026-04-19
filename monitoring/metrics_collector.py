"""
Minder Metrics Collector
Aggregates metrics from various sources and exports to monitoring systems
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles

logger = logging.getLogger(__name__)


class MetricsCollector:
    """
    Collects and exports metrics from various sources

    Supports:
    - File-based metrics export (JSON)
    - Real-time metrics aggregation
    - Custom metric definitions
    - Historical data retention
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.enabled = config.get("monitoring", {}).get("enabled", True)

        # Metrics storage
        self.metrics_buffer = []
        self.max_buffer_size = config.get("monitoring", {}).get("max_buffer_size", 10000)

        # Export configuration
        self.export_path = Path(config.get("monitoring", {}).get("export_path", "/var/log/minder/metrics"))
        self.export_interval = config.get("monitoring", {}).get("export_interval", 60)  # seconds

        self._export_task = None
        self.is_running = False

    async def start(self):
        """Start metrics collector"""
        if not self.enabled:
            logger.info("Metrics collector disabled")
            return

        # Ensure export directory exists
        self.export_path.mkdir(parents=True, exist_ok=True)

        logger.info("Starting metrics collector...")
        self.is_running = True
        self._export_task = asyncio.create_task(self._export_loop())
        logger.info("✓ Metrics collector started")

    async def stop(self):
        """Stop metrics collector"""
        if self._export_task:
            self._export_task.cancel()
            try:
                await self._export_task
            except asyncio.CancelledError:
                pass

        # Final export
        await self.export_metrics()

        self.is_running = False
        logger.info("✓ Metrics collector stopped")

    async def _export_loop(self):
        """Periodic metrics export loop"""
        while self.is_running:
            try:
                await asyncio.sleep(self.export_interval)
                await self.export_metrics()
            except Exception as e:
                logger.error(f"Error in export loop: {e}")

    async def collect_metric(self, metric: Dict[str, Any]):
        """Collect a single metric"""
        if not self.enabled:
            return

        # Add timestamp
        metric["collected_at"] = datetime.now().isoformat()

        # Add to buffer
        self.metrics_buffer.append(metric)

        # Check buffer size
        if len(self.metrics_buffer) >= self.max_buffer_size:
            logger.warning(f"Metrics buffer full ({len(self.metrics_buffer)}), triggering export")
            await self.export_metrics()

    async def collect_metrics(self, metrics: List[Dict[str, Any]]):
        """Collect multiple metrics"""
        for metric in metrics:
            await self.collect_metric(metric)

    async def export_metrics(self):
        """Export metrics to file"""
        if not self.metrics_buffer:
            return

        try:
            # Create export filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            export_file = self.export_path / f"metrics_{timestamp}.json"

            # Write metrics to file
            async with aiofiles.open(export_file, "w") as f:
                await f.write(json.dumps(self.metrics_buffer, indent=2))

            logger.info(f"✓ Exported {len(self.metrics_buffer)} metrics to {export_file}")

            # Clear buffer
            self.metrics_buffer.clear()

        except Exception as e:
            logger.error(f"Failed to export metrics: {e}")

    async def get_metrics_summary(self) -> Dict[str, Any]:
        """Get summary of collected metrics"""
        return {
            "buffer_size": len(self.metrics_buffer),
            "max_buffer_size": self.max_buffer_size,
            "export_path": str(self.export_path),
            "export_interval_seconds": self.export_interval,
            "is_running": self.is_running,
            "last_export": self._get_last_export_time(),
        }

    def _get_last_export_time(self) -> Optional[str]:
        """Get timestamp of last export"""
        try:
            if not self.export_path.exists():
                return None

            # List all metrics files
            metrics_files = sorted(self.export_path.glob("metrics_*.json"), reverse=True)

            if not metrics_files:
                return None

            # Extract timestamp from filename
            latest_file = metrics_files[0]
            timestamp_str = latest_file.stem.replace("metrics_", "")

            # Parse and format timestamp
            try:
                dt = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                return dt.isoformat()
            except Exception:
                return latest_file.name

        except Exception as e:
            logger.error(f"Error getting last export time: {e}")
            return None

    def get_export_files(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get list of recent export files"""
        try:
            if not self.export_path.exists():
                return []

            # List all metrics files sorted by modification time
            metrics_files = sorted(
                self.export_path.glob("metrics_*.json"),
                key=lambda f: f.stat().st_mtime,
                reverse=True,
            )[:limit]

            return [
                {
                    "filename": f.name,
                    "path": str(f),
                    "size_bytes": f.stat().st_size,
                    "modified_time": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                }
                for f in metrics_files
            ]

        except Exception as e:
            logger.error(f"Error getting export files: {e}")
            return []
