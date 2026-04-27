"""
Load testing and performance measurement utilities.
Comprehensive load testing framework for Minder services.
"""

import asyncio
import time
import statistics
from typing import List, Dict, Any, Callable, Optional
from dataclasses import dataclass, field
from enum import Enum
import logging
import aiohttp
import psutil
import tracemalloc

logger = logging.getLogger("minder.load_testing")


class TestPhase(Enum):
    """Load testing phases"""
    WARMUP = "warmup"
    RAMP_UP = "ramp_up"
    SUSTAINED_LOAD = "sustained_load"
    RAMP_DOWN = "ramp_down"
    COOLDOWN = "cooldown"


@dataclass
class RequestResult:
    """Represents a single request result"""
    success: bool
    status_code: Optional[int] = None
    response_time_ms: float = 0.0
    error: Optional[str] = None
    response_size_bytes: int = 0


@dataclass
class LoadTestStats:
    """Statistics from load test"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    success_rate: float = 0.0
    avg_response_time_ms: float = 0.0
    min_response_time_ms: float = float('inf')
    max_response_time_ms: float = 0.0
    p50_response_time_ms: float = 0.0
    p95_response_time_ms: float = 0.0
    p99_response_time_ms: float = 0.0
    requests_per_second: float = 0.0
    avg_memory_mb: float = 0.0
    max_memory_mb: float = 0.0
    avg_cpu_percent: float = 0.0
    max_cpu_percent: float = 0.0


@dataclass
class PhaseConfig:
    """Configuration for a load test phase"""
    phase: TestPhase
    duration_seconds: int
    concurrent_users: int
    requests_per_second: float = 0.0


class LoadTester:
    """
    Load testing framework for Minder services.
    Supports multiple test phases and detailed metrics collection.
    """

    def __init__(
        self,
        base_url: str,
        max_concurrent_users: int = 100,
        timeout: float = 30.0
    ):
        """
        Initialize load tester.

        Args:
            base_url: Base URL of the service to test
            max_concurrent_users: Maximum number of concurrent users
            timeout: Request timeout in seconds
        """
        self.base_url = base_url
        self.max_concurrent_users = max_concurrent_users
        self.timeout = timeout
        self.results: List[RequestResult] = []

        # Resource monitoring
        self.process = psutil.Process()
        tracemalloc.start()

    async def make_request(
        self,
        session: aiohttp.ClientSession,
        method: str = "GET",
        endpoint: str = "/",
        headers: Dict[str, str] = None,
        data: Any = None,
        json: Dict[str, Any] = None
    ) -> RequestResult:
        """
        Make a single HTTP request.

        Args:
            session: aiohttp session
            method: HTTP method
            endpoint: API endpoint
            headers: Request headers
            data: Request data
            json: Request JSON data

        Returns:
            RequestResult with request metrics
        """
        url = self.base_url + endpoint
        start_time = time.time()

        try:
            if method == "GET":
                async with session.get(
                    url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    response_time = (time.time() - start_time) * 1000
                    response_size = len(await response.read())

                    return RequestResult(
                        success=response.status < 400,
                        status_code=response.status,
                        response_time_ms=response_time,
                        response_size_bytes=response_size
                    )

            elif method == "POST":
                async with session.post(
                    url,
                    headers=headers,
                    data=data,
                    json=json,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    response_time = (time.time() - start_time) * 1000
                    response_size = len(await response.read())

                    return RequestResult(
                        success=response.status < 400,
                        status_code=response.status,
                        response_time_ms=response_time,
                        response_size_bytes=response_size
                    )

        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return RequestResult(
                success=False,
                response_time_ms=response_time,
                error=str(e)
            )

    async def run_user_scenario(
        self,
        session: aiohttp.ClientSession,
        scenario: Callable[[aiohttp.ClientSession], Any],
        requests_count: int = 10,
        delay_between_requests: float = 0.1
    ) -> List[RequestResult]:
        """
        Run a user scenario with multiple requests.

        Args:
            session: aiohttp session
            scenario: Function that defines the user scenario
            requests_count: Number of requests to make
            delay_between_requests: Delay between requests in seconds

        Returns:
            List of request results
        """
        results = []

        for i in range(requests_count):
            result = await scenario(session)
            results.append(result)

            if delay_between_requests > 0:
                await asyncio.sleep(delay_between_requests)

        return results

    async def run_phase(
        self,
        phase: TestPhase,
        duration_seconds: int,
        concurrent_users: int,
        requests_per_user: int = 10,
        scenario: Callable[[aiohttp.ClientSession], Any] = None
    ) -> LoadTestStats:
        """
        Run a load test phase.

        Args:
            phase: Test phase
            duration_seconds: Duration of the phase
            concurrent_users: Number of concurrent users
            requests_per_user: Requests per user
            scenario: User scenario function

        Returns:
            LoadTestStats with phase statistics
        """
        logger.info(f"Starting phase: {phase.value} ({duration_seconds}s, {concurrent_users} users)")

        # Start resource monitoring
        memory_samples = []
        cpu_samples = []
        monitoring_task = asyncio.create_task(
            self._monitor_resources(duration_seconds, memory_samples, cpu_samples)
        )

        # Create session and run requests
        async with aiohttp.ClientSession() as session:
            # Create concurrent user tasks
            tasks = []

            for i in range(concurrent_users):
                if scenario:
                    task = asyncio.create_task(
                        self.run_user_scenario(
                            session,
                            scenario,
                            requests_count=requests_per_user,
                            delay_between_requests=0.0
                        )
                    )
                else:
                    # Default scenario: simple GET requests
                    task = asyncio.create_task(
                        self.run_user_scenario(
                            session,
                            lambda s: self.make_request(s, method="GET", endpoint="/"),
                            requests_count=requests_per_user,
                            delay_between_requests=0.0
                        )
                    )
                tasks.append(task)

            # Wait for all tasks to complete
            phase_results = await asyncio.gather(*tasks)

            # Flatten results
            self.results.extend([result for user_results in phase_results for result in user_results])

        # Stop resource monitoring
        monitoring_task.cancel()
        try:
            await monitoring_task
        except asyncio.CancelledError:
            pass

        # Calculate statistics
        stats = self._calculate_stats(self.results, memory_samples, cpu_samples, duration_seconds)

        logger.info(f"Phase {phase.value} completed: {stats.success_rate:.2f}% success, "
                   f"{stats.avg_response_time_ms:.2f}ms avg")

        return stats

    async def _monitor_resources(
        self,
        duration_seconds: int,
        memory_samples: List[float],
        cpu_samples: List[float]
    ):
        """
        Monitor system resources during test.

        Args:
            duration_seconds: Duration to monitor
            memory_samples: List to store memory samples
            cpu_samples: List to store CPU samples
        """
        try:
            while True:
                # Memory
                memory_info = self.process.memory_info()
                memory_mb = memory_info.rss / (1024 * 1024)
                memory_samples.append(memory_mb)

                # CPU
                cpu_percent = self.process.cpu_percent()
                cpu_samples.append(cpu_percent)

                await asyncio.sleep(1)

        except asyncio.CancelledError:
            pass

    def _calculate_stats(
        self,
        results: List[RequestResult],
        memory_samples: List[float],
        cpu_samples: List[float],
        duration_seconds: int
    ) -> LoadTestStats:
        """
        Calculate statistics from results.

        Args:
            results: List of request results
            memory_samples: Memory usage samples
            cpu_samples: CPU usage samples
            duration_seconds: Test duration

        Returns:
            LoadTestStats with calculated statistics
        """
        if not results:
            return LoadTestStats()

        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]

        response_times = [r.response_time_ms for r in successful] if successful else []

        stats = LoadTestStats(
            total_requests=len(results),
            successful_requests=len(successful),
            failed_requests=len(failed),
            success_rate=len(successful) / len(results) * 100 if results else 0
        )

        if response_times:
            stats.avg_response_time_ms = statistics.mean(response_times)
            stats.min_response_time_ms = min(response_times)
            stats.max_response_time_ms = max(response_times)

            # Percentiles
            sorted_times = sorted(response_times)
            stats.p50_response_time_ms = sorted_times[int(len(sorted_times) * 0.5)]
            stats.p95_response_time_ms = sorted_times[int(len(sorted_times) * 0.95)]
            stats.p99_response_time_ms = sorted_times[int(len(sorted_times) * 0.99)]

        stats.requests_per_second = len(results) / duration_seconds if duration_seconds > 0 else 0

        if memory_samples:
            stats.avg_memory_mb = statistics.mean(memory_samples)
            stats.max_memory_mb = max(memory_samples)

        if cpu_samples:
            stats.avg_cpu_percent = statistics.mean(cpu_samples)
            stats.max_cpu_percent = max(cpu_samples)

        return stats

    async def run_load_test(
        self,
        phases: List[PhaseConfig],
        scenario: Callable[[aiohttp.ClientSession], Any] = None
    ) -> Dict[TestPhase, LoadTestStats]:
        """
        Run complete load test with multiple phases.

        Args:
            phases: List of phase configurations
            scenario: User scenario function

        Returns:
            Dictionary mapping phases to statistics
        """
        logger.info(f"Starting load test with {len(phases)} phases")

        results = {}

        for phase_config in phases:
            stats = await self.run_phase(
                phase=phase_config.phase,
                duration_seconds=phase_config.duration_seconds,
                concurrent_users=phase_config.concurrent_users,
                requests_per_user=10,
                scenario=scenario
            )

            results[phase_config.phase] = stats

            # Brief pause between phases
            await asyncio.sleep(5)

        logger.info("Load test completed")

        # Generate report
        self._generate_report(results)

        return results

    def _generate_report(self, results: Dict[TestPhase, LoadTestStats]):
        """
        Generate and log load test report.

        Args:
            results: Dictionary of phase statistics
        """
        logger.info("\n" + "="*80)
        logger.info("LOAD TEST REPORT")
        logger.info("="*80)

        for phase, stats in results.items():
            logger.info(f"\nPhase: {phase.value}")
            logger.info("-" * 40)
            logger.info(f"Total Requests: {stats.total_requests}")
            logger.info(f"Successful: {stats.successful_requests} ({stats.success_rate:.2f}%)")
            logger.info(f"Failed: {stats.failed_requests}")
            logger.info(f"Requests/sec: {stats.requests_per_second:.2f}")
            logger.info(f"\nResponse Times:")
            logger.info(f"  Average: {stats.avg_response_time_ms:.2f} ms")
            logger.info(f"  Min: {stats.min_response_time_ms:.2f} ms")
            logger.info(f"  Max: {stats.max_response_time_ms:.2f} ms")
            logger.info(f"  P50: {stats.p50_response_time_ms:.2f} ms")
            logger.info(f"  P95: {stats.p95_response_time_ms:.2f} ms")
            logger.info(f"  P99: {stats.p99_response_time_ms:.2f} ms")
            logger.info(f"\nResource Usage:")
            logger.info(f"  Memory: {stats.avg_memory_mb:.2f} MB (max: {stats.max_memory_mb:.2f} MB)")
            logger.info(f"  CPU: {stats.avg_cpu_percent:.2f}% (max: {stats.max_cpu_percent:.2f}%)")

        logger.info("\n" + "="*80)


class PerformanceProfiler:
    """
    Performance profiler for code optimization.
    """

    def __init__(self):
        self.snapshots = []

    def snapshot(self, name: str = "unnamed") -> Dict[str, Any]:
        """
        Take a performance snapshot.

        Args:
            name: Name for the snapshot

        Returns:
            Dictionary with performance metrics
        """
        snapshot = {
            "name": name,
            "timestamp": time.time(),
            "memory_mb": psutil.Process().memory_info().rss / (1024 * 1024),
            "cpu_percent": psutil.Process().cpu_percent(),
            "threads": psutil.Process().num_threads()
        }

        # Memory profiling
        if tracemalloc.is_tracing():
            snapshot["memory_traces"] = tracemalloc.get_traced_memory()
            snapshot["memory_blocks"] = tracemalloc.get_tracemalloc_memory_blocks()

        self.snapshots.append(snapshot)
        return snapshot

    def compare(self, snapshot1: str, snapshot2: str) -> Dict[str, float]:
        """
        Compare two snapshots.

        Args:
            snapshot1: Name of first snapshot
            snapshot2: Name of second snapshot

        Returns:
            Dictionary with differences
        """
        snap1 = next((s for s in self.snapshots if s["name"] == snapshot1), None)
        snap2 = next((s for s in self.snapshots if s["name"] == snapshot2), None)

        if not snap1 or not snap2:
            raise ValueError("One or both snapshots not found")

        diff = {
            "time_delta_ms": (snap2["timestamp"] - snap1["timestamp"]) * 1000,
            "memory_delta_mb": snap2["memory_mb"] - snap1["memory_mb"],
            "cpu_delta_percent": snap2["cpu_percent"] - snap1["cpu_percent"]
        }

        return diff

    def get_memory_leak_candidates(self) -> List[Dict[str, Any]]:
        """
        Analyze snapshots for potential memory leaks.

        Returns:
            List of potential memory leak candidates
        """
        candidates = []

        for i in range(len(self.snapshots) - 1):
            snap1 = self.snapshots[i]
            snap2 = self.snapshots[i + 1]

            memory_increase = snap2["memory_mb"] - snap1["memory_mb"]

            # Consider significant increase
            if memory_increase > 10:  # 10 MB increase
                candidates.append({
                    "from_snapshot": snap1["name"],
                    "to_snapshot": snap2["name"],
                    "memory_increase_mb": memory_increase,
                    "memory_percent_increase": (memory_increase / snap1["memory_mb"]) * 100
                })

        return candidates


# Performance test presets

class PerformanceTestPresets:
    """Common performance test configurations"""

    # Quick smoke test
    SMOKE_TEST = [
        PhaseConfig(
            phase=TestPhase.WARMUP,
            duration_seconds=30,
            concurrent_users=5
        )
    ]

    # Basic load test
    BASIC_LOAD = [
        PhaseConfig(
            phase=TestPhase.WARMUP,
            duration_seconds=30,
            concurrent_users=10
        ),
        PhaseConfig(
            phase=TestPhase.RAMP_UP,
            duration_seconds=60,
            concurrent_users=50
        ),
        PhaseConfig(
            phase=TestPhase.SUSTAINED_LOAD,
            duration_seconds=300,
            concurrent_users=100
        ),
        PhaseConfig(
            phase=TestPhase.RAMP_DOWN,
            duration_seconds=60,
            concurrent_users=10
        ),
        PhaseConfig(
            phase=TestPhase.COOLDOWN,
            duration_seconds=30,
            concurrent_users=5
        )
    ]

    # Stress test
    STRESS_TEST = [
        PhaseConfig(
            phase=TestPhase.WARMUP,
            duration_seconds=30,
            concurrent_users=10
        ),
        PhaseConfig(
            phase=TestPhase.RAMP_UP,
            duration_seconds=60,
            concurrent_users=200
        ),
        PhaseConfig(
            phase=TestPhase.SUSTAINED_LOAD,
            duration_seconds=300,
            concurrent_users=500
        ),
        PhaseConfig(
            phase=TestPhase.COOLDOWN,
            duration_seconds=60,
            concurrent_users=5
        )
    ]

    # Soak test (long duration)
    SOAK_TEST = [
        PhaseConfig(
            phase=TestPhase.WARMUP,
            duration_seconds=60,
            concurrent_users=10
        ),
        PhaseConfig(
            phase=TestPhase.SUSTAINED_LOAD,
            duration_seconds=3600,  # 1 hour
            concurrent_users=50
        ),
        PhaseConfig(
            phase=TestPhase.COOLDOWN,
            duration_seconds=60,
            concurrent_users=5
        )
    ]


# Performance metrics

class PerformanceMetrics:
    """Standard performance metrics for Minder"""

    # Response time thresholds (ms)
    EXCELLENT_RESPONSE_TIME = 100
    GOOD_RESPONSE_TIME = 300
    ACCEPTABLE_RESPONSE_TIME = 1000
    POOR_RESPONSE_TIME = 3000

    # Success rate thresholds (%)
    EXCELLENT_SUCCESS_RATE = 99.9
    GOOD_SUCCESS_RATE = 99.0
    ACCEPTABLE_SUCCESS_RATE = 95.0

    # Resource thresholds
    MAX_MEMORY_MB = 2048  # 2GB
    MAX_CPU_PERCENT = 80.0

    @classmethod
    def evaluate_response_time(cls, response_time_ms: float) -> str:
        """Evaluate response time performance"""
        if response_time_ms <= cls.EXCELLENT_RESPONSE_TIME:
            return "EXCELLENT"
        elif response_time_ms <= cls.GOOD_RESPONSE_TIME:
            return "GOOD"
        elif response_time_ms <= cls.ACCEPTABLE_RESPONSE_TIME:
            return "ACCEPTABLE"
        else:
            return "POOR"

    @classmethod
    def evaluate_success_rate(cls, success_rate: float) -> str:
        """Evaluate success rate performance"""
        if success_rate >= cls.EXCELLENT_SUCCESS_RATE:
            return "EXCELLENT"
        elif success_rate >= cls.GOOD_SUCCESS_RATE:
            return "GOOD"
        elif success_rate >= cls.ACCEPTABLE_SUCCESS_RATE:
            return "ACCEPTABLE"
        else:
            return "POOR"

    @classmethod
    def get_performance_grade(cls, stats: LoadTestStats) -> str:
        """Get overall performance grade"""
        response_grade = cls.evaluate_response_time(stats.p95_response_time_ms)
        success_grade = cls.evaluate_success_rate(stats.success_rate)

        if response_grade == "EXCELLENT" and success_grade == "EXCELLENT":
            return "A+"
        elif response_grade in ["EXCELLENT", "GOOD"] and success_grade in ["EXCELLENT", "GOOD"]:
            return "A"
        elif response_grade in ["GOOD", "ACCEPTABLE"] and success_grade in ["GOOD", "ACCEPTABLE"]:
            return "B"
        elif response_grade == "ACCEPTABLE" and success_grade == "ACCEPTABLE":
            return "C"
        else:
            return "D"
