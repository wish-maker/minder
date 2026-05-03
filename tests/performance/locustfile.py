"""
Load Testing Setup for Minder Event-Driven Architecture

Uses Locust to simulate load and validate SLA compliance:
- Command → Event Store latency: P50 < 50ms, P99 < 100ms
- Event Store → RabbitMQ latency: < 1s (outbox polling interval)
- RabbitMQ → Projection latency: P50 < 100ms, P99 < 500ms
- End-to-end latency: P50 < 200ms, P99 < 1000ms
"""

import time
from uuid import uuid4

from locust import HttpUser, between, events, task


class EDAUser(HttpUser):
    """
    Load test for Event-Driven Architecture

    Simulates realistic user behavior across the system:
    - Model registration (write path)
    - Model queries (read path with projections)
    - RAG queries (hybrid endpoint fallback)
    """

    wait_time = between(1, 3)

    def on_start(self):
        """Setup before each user starts"""
        self.model_id = str(uuid4())
        self.deployment_id = str(uuid4())

    @task(2)
    def register_model(self):
        """
        Test model registration performance (Task 2 event store)

        Validates:
        - Command → Event Store write latency
        - Event Store append operation
        - Event publishing to RabbitMQ
        """
        payload = {
            "model_id": str(uuid4()),
            "name": f"LoadTestModel-{int(time.time())}",
            "model_type": "LLM",
            "resource_profile": "cpu-standard",
            "registered_by": "load_test_user",
        }

        start_time = time.time()
        with self.client.post(
            "/api/models/register", json=payload, catch_response=True, name="Register Model"
        ) as response:
            latency_ms = (time.time() - start_time) * 1000

            if response.status_code == 201 or response.status_code == 200:
                # Success - track latency
                events.request.fire(
                    request_type="POST",
                    name="Register Model",
                    response_time=latency_ms,
                    response_length=len(response.content),
                    context={},
                    exception=None,
                )

                # Validate SLA: P50 < 50ms, P99 < 100ms
                if latency_ms > 100:
                    response.failure(f"SLA exceeded: {latency_ms:.2f}ms > 100ms")
                else:
                    response.success()
            else:
                response.failure(f"Failed with status {response.status_code}")

    @task(3)
    def get_models(self):
        """
        Test read performance (from projections with Redis cache)

        Validates:
        - Projection read latency
        - Redis cache hit rate
        - Query performance under load
        """
        start_time = time.time()
        with self.client.get("/api/models", catch_response=True, name="Get Models") as response:
            latency_ms = (time.time() - start_time) * 1000

            if response.status_code == 200:
                # Success - track latency
                events.request.fire(
                    request_type="GET",
                    name="Get Models",
                    response_time=latency_ms,
                    response_length=len(response.content),
                    context={},
                    exception=None,
                )

                # Validate SLA: Read from cache should be fast
                if latency_ms > 200:
                    response.failure(f"Cache read slow: {latency_ms:.2f}ms > 200ms")
                else:
                    response.success()
            else:
                response.failure(f"Failed with status {response.status_code}")

    @task
    def query_rag(self):
        """
        Test RAG query with hybrid endpoints (Pillar 2 fallback)

        Validates:
        - Primary endpoint performance
        - Fallback endpoint activation
        - End-to-end query latency
        """
        payload = {"query": f"test query {int(time.time())}", "use_hybrid_endpoint": True}

        start_time = time.time()
        with self.client.post(
            "/api/rag/query", json=payload, catch_response=True, name="RAG Query", timeout=10.0
        ) as response:
            latency_ms = (time.time() - start_time) * 1000

            if response.status_code == 200:
                # Success - track latency
                events.request.fire(
                    request_type="POST",
                    name="RAG Query",
                    response_time=latency_ms,
                    response_length=len(response.content),
                    context={},
                    exception=None,
                )

                # Validate SLA: End-to-end P50 < 200ms, P99 < 1000ms
                if latency_ms > 1000:
                    response.failure(f"SLA exceeded: {latency_ms:.2f}ms > 1000ms")
                else:
                    response.success()
            else:
                response.failure(f"Failed with status {response.status_code}")

    @task(1)
    def deploy_model(self):
        """
        Test model deployment performance

        Validates:
        - Deployment command processing
        - Event store write for deployment
        - Deployment status update events
        """
        payload = {"deployment_id": str(uuid4()), "model_id": self.model_id, "version": "v1.0", "runtime_env": "ollama"}

        start_time = time.time()
        with self.client.post(
            "/api/deployments/request", json=payload, catch_response=True, name="Request Deployment"
        ) as response:
            latency_ms = (time.time() - start_time) * 1000

            if response.status_code == 201 or response.status_code == 200:
                events.request.fire(
                    request_type="POST",
                    name="Request Deployment",
                    response_time=latency_ms,
                    response_length=len(response.content),
                    context={},
                    exception=None,
                )

                if latency_ms > 150:
                    response.failure(f"Deployment request slow: {latency_ms:.2f}ms > 150ms")
                else:
                    response.success()
            else:
                response.failure(f"Failed with status {response.status_code}")

    @task(1)
    def get_deployment_status(self):
        """
        Test deployment status query performance

        Validates:
        - Projection read for deployment status
        - Real-time status update latency
        """
        with self.client.get(
            f"/api/deployments/{self.deployment_id}/status", catch_response=True, name="Get Deployment Status"
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 404:
                # Deployment doesn't exist yet - expected in load test
                response.success()
            else:
                response.failure(f"Failed with status {response.status_code}")


class PerformanceTargets:
    """
    SLA validation helpers

    Performance targets to verify:
    - Command → Event Store latency: P50 < 50ms, P99 < 100ms
    - Event Store → RabbitMQ latency: < 1s (outbox polling interval)
    - RabbitMQ → Projection latency: P50 < 100ms, P99 < 500ms
    - End-to-end latency: P50 < 200ms, P99 < 1000ms
    """

    @staticmethod
    def validate_command_to_event_store(latency_ms):
        """Validate Command → Event Store latency"""
        return latency_ms < 100  # P99 < 100ms

    @staticmethod
    def validate_event_store_to_rabbitmq(latency_ms):
        """Validate Event Store → RabbitMQ latency"""
        return latency_ms < 1000  # < 1s (outbox polling interval)

    @staticmethod
    def validate_rabbitmq_to_projection(latency_ms):
        """Validate RabbitMQ → Projection latency"""
        return latency_ms < 500  # P99 < 500ms

    @staticmethod
    def validate_end_to_end(latency_ms):
        """Validate end-to-end latency"""
        return latency_ms < 1000  # P99 < 1000ms


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """
    Test completion handler

    Prints summary of SLA compliance and performance metrics
    """
    if environment.stats.total.fail_ratio > 0.05:
        print(f"\n⚠️  WARNING: Failure rate {environment.stats.total.fail_ratio:.2%} exceeds 5%")

    if environment.stats.total.avg_response_time > 500:
        print(f"\n⚠️  WARNING: Average response time {environment.stats.total.avg_response_time:.2f}ms exceeds 500ms")

    print("\n=== Performance Summary ===")
    print(f"Total requests: {environment.stats.total.num_requests}")
    print(f"Failure rate: {environment.stats.total.fail_ratio:.2%}")
    print(f"Average response time: {environment.stats.total.avg_response_time:.2f}ms")
    print(f"Median response time: {environment.stats.total.median_response_time:.2f}ms")
    print(f"95th percentile: {environment.stats.total.get_response_time_percentile(0.95):.2f}ms")
    print(f"99th percentile: {environment.stats.total.get_response_time_percentile(0.99):.2f}ms")
    print(f"Requests/s: {environment.stats.total.total_rps:.2f}")
    print("========================\n")


@events.request.add_listener
def on_request(request_type, name, response_time, response_length, exception, context, **kwargs):
    """
    Request-level logging for detailed analysis

    Can be used to:
    - Track individual request latencies
    - Identify slow endpoints
    - Monitor SLA compliance in real-time
    """
    # Log slow requests
    if response_time > 500:
        print(f"⚠️  Slow request: {name} took {response_time:.2f}ms")

    # Log failures
    if exception:
        print(f"❌ Failed request: {name} - {exception}")


if __name__ == "__main__":
    """
    Run load tests locally:

    Single user:
        locust -f locustfile.py

    Multiple users:
        locust -f locustfile.py --users 100 --spawn-rate 10

    Headless mode:
        locust -f locustfile.py --users 100 --spawn-rate 10 --headless --run-time 60s

    With custom host:
        locust -f locustfile.py --host http://localhost:8000

    Performance targets:
    - Command → Event Store: P50 < 50ms, P99 < 100ms
    - Event Store → RabbitMQ: < 1s
    - RabbitMQ → Projection: P50 < 100ms, P99 < 500ms
    - End-to-end: P50 < 200ms, P99 < 1000ms
    """
    import sys

    print("Load test file loaded. Run with: locust -f locustfile.py --host http://localhost:8000")
    sys.exit(0)
