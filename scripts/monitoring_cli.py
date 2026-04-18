#!/usr/bin/env python3
"""
Minder Monitoring CLI Tool
Command-line interface for monitoring and metrics
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from monitoring.performance_monitor import PerformanceMonitor
from monitoring.metrics_collector import MetricsCollector
import json


async def show_system_metrics():
    """Display current system metrics"""
    config = {
        "monitoring": {
            "enabled": True,
        }
    }

    monitor = PerformanceMonitor(config)
    await monitor.start()

    # Wait for some data collection
    await asyncio.sleep(2)

    metrics = monitor.get_system_metrics()

    print("=" * 60)
    print("SYSTEM METRICS")
    print("=" * 60)
    print(f"Timestamp: {metrics['timestamp']}")
    print(f"\nCPU Usage:")
    print(f"  Current: {metrics['cpu']['current_percent']:.1f}%")
    print(f"  Average: {metrics['cpu']['average_percent']:.1f}%")
    print(f"  Status: {metrics['cpu']['status']}")
    print(f"\nMemory Usage:")
    print(f"  Current: {metrics['memory']['current_percent']:.1f}%")
    print(f"  Average: {metrics['memory']['average_percent']:.1f}%")
    print(f"  Available: {metrics['memory']['available_mb']:.0f} MB")
    print(f"  Status: {metrics['memory']['status']}")
    print(f"\nUptime: {metrics['uptime_seconds']:.0f} seconds")

    await monitor.stop()


async def show_api_metrics():
    """Display API performance metrics"""
    config = {
        "monitoring": {
            "enabled": True,
        }
    }

    monitor = PerformanceMonitor(config)

    # Simulate some API calls
    monitor.record_api_response("/api/plugins", 150, 200)
    monitor.record_api_response("/api/plugins", 200, 200)
    monitor.record_api_response("/api/plugins/crypto", 450, 200)
    monitor.record_api_response("/api/plugins/tefas", 3000, 200)
    monitor.record_api_response("/api/health", 50, 200)
    monitor.record_api_response("/api/plugins", 8000, 500)  # Slow/error

    metrics = monitor.get_api_metrics()

    print("=" * 60)
    print("API PERFORMANCE METRICS")
    print("=" * 60)
    print(f"Total Requests: {metrics['total_requests']}")
    print(f"Average Response Time: {metrics['avg_response_time_ms']:.0f}ms")
    print(f"Min Response Time: {metrics['min_response_time_ms']:.0f}ms")
    print(f"Max Response Time: {metrics['max_response_time_ms']:.0f}ms")
    print(f"P95 Response Time: {metrics['p95_response_time_ms']:.0f}ms")
    print(f"P99 Response Time: {metrics['p99_response_time_ms']:.0f}ms")
    print(f"Error Rate: {metrics['error_rate']:.1%}")


async def show_plugin_metrics():
    """Display plugin execution metrics"""
    config = {
        "monitoring": {
            "enabled": True,
        }
    }

    monitor = PerformanceMonitor(config)

    # Simulate plugin executions
    monitor.record_plugin_execution("weather", "collect_data", 1500, True)
    monitor.record_plugin_execution("weather", "analyze", 800, True)
    monitor.record_plugin_execution("crypto", "collect_data", 2200, True)
    monitor.record_plugin_execution("crypto", "analyze", 400, True)
    monitor.record_plugin_execution("tefas", "collect_data", 5000, False)  # Failed
    monitor.record_plugin_execution("news", "collect_data", 1200, True)

    metrics = monitor.get_plugin_metrics()

    print("=" * 60)
    print("PLUGIN EXECUTION METRICS")
    print("=" * 60)

    for plugin_name, plugin_metrics in metrics.items():
        print(f"\n{plugin_name.upper()}:")
        print(f"  Total Operations: {plugin_metrics['total_operations']}")
        print(f"  Success Rate: {plugin_metrics['success_rate']:.1%}")
        print(f"  Avg Duration: {plugin_metrics['avg_duration_ms']:.0f}ms")
        print(f"  Errors: {plugin_metrics['error_count']}")


async def show_all_metrics():
    """Display comprehensive metrics summary"""
    config = {
        "monitoring": {
            "enabled": True,
        }
    }

    monitor = PerformanceMonitor(config)
    await monitor.start()

    # Wait for data collection
    await asyncio.sleep(2)

    # Add sample data
    monitor.record_api_response("/api/test", 250, 200)
    monitor.record_plugin_execution("test", "test_op", 500, True)

    metrics = monitor.get_all_metrics()

    print("=" * 60)
    print("COMPREHENSIVE METRICS SUMMARY")
    print("=" * 60)
    print(json.dumps(metrics, indent=2))

    await monitor.stop()


async def main():
    """Main CLI entry point"""
    if len(sys.argv) < 2:
        print("Usage: python monitoring_cli.py <command>")
        print("\nCommands:")
        print("  system      - Show system metrics")
        print("  api         - Show API metrics")
        print("  plugins     - Show plugin metrics")
        print("  all         - Show all metrics")
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == "system":
        await show_system_metrics()
    elif command == "api":
        await show_api_metrics()
    elif command == "plugins":
        await show_plugin_metrics()
    elif command == "all":
        await show_all_metrics()
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
