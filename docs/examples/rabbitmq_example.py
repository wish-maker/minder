#!/usr/bin/env python3
"""
RabbitMQ Message Queue Examples for Minder Platform

This file demonstrates how to use RabbitMQ for asynchronous messaging
between microservices in the Minder platform.

Examples included:
1. Basic producer/consumer pattern
2. Plugin task distribution (API Gateway → Plugin Registry)
3. Event broadcasting (pub/sub pattern)
4. Dead Letter Queue (DLQ) handling

License: MPL-2.0
"""

import json
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

import pika

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ExchangeType(Enum):
    """RabbitMQ exchange types"""

    DIRECT = "direct"
    TOPIC = "topic"
    FANOUT = "fanout"
    HEADERS = "headers"


@dataclass
class RabbitMQConfig:
    """RabbitMQ connection configuration"""

    host: str = "localhost"
    port: int = 5672
    username: str = "minder"
    password: str = "CHANGE_ME"  # nosec B106
    virtual_host: str = "/"
    heartbeat: int = 600
    blocked_connection_timeout: int = 300


class RabbitMQProducer:
    """
    RabbitMQ message producer for publishing messages to exchanges

    Usage:
        producer = RabbitMQProducer(config)
        producer.publish_plugin_task("crypto", {"action": "collect"})
    """

    def __init__(self, config: RabbitMQConfig):
        self.config = config
        self._connection: Optional[pika.BlockingConnection] = None
        self._channel: Optional[pika.adapters.blocking_connection.BlockingChannel] = None

    def connect(self) -> None:
        """Establish connection to RabbitMQ"""
        credentials = pika.PlainCredentials(self.config.username, self.config.password)
        parameters = pika.ConnectionParameters(
            host=self.config.host,
            port=self.config.port,
            virtual_host=self.config.virtual_host,
            credentials=credentials,
            heartbeat=self.config.heartbeat,
            blocked_connection_timeout=self.config.blocked_connection_timeout,
        )
        self._connection = pika.BlockingConnection(parameters)
        self._channel = self._connection.channel()
        logger.info("Connected to RabbitMQ")

    def close(self) -> None:
        """Close connection to RabbitMQ"""
        if self._connection and not self._connection.is_closed:
            self._connection.close()
            logger.info("Closed RabbitMQ connection")

    def declare_exchange(
        self,
        exchange_name: str,
        exchange_type: ExchangeType = ExchangeType.DIRECT,
        durable: bool = True,
    ) -> None:
        """
        Declare an exchange

        Args:
            exchange_name: Name of the exchange
            exchange_type: Type of exchange (direct, topic, fanout, headers)
            durable: Survive broker restart
        """
        self._channel.exchange_declare(
            exchange=exchange_name,
            exchange_type=exchange_type.value,
            durable=durable,
        )
        logger.info(f"Declared exchange: {exchange_name} ({exchange_type.value})")

    def declare_queue(
        self,
        queue_name: str,
        durable: bool = True,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Declare a queue

        Args:
            queue_name: Name of the queue
            durable: Survive broker restart
            arguments: Additional queue arguments (e.g., DLQ)
        """
        self._channel.queue_declare(
            queue=queue_name,
            durable=durable,
            arguments=arguments,
        )
        logger.info(f"Declared queue: {queue_name}")

    def bind_queue(
        self,
        queue_name: str,
        exchange_name: str,
        routing_key: str,
    ) -> None:
        """
        Bind a queue to an exchange with a routing key

        Args:
            queue_name: Name of the queue
            exchange_name: Name of the exchange
            routing_key: Routing key for binding
        """
        self._channel.queue_bind(
            queue=queue_name,
            exchange=exchange_name,
            routing_key=routing_key,
        )
        logger.info(f"Bound queue {queue_name} to exchange {exchange_name} with routing key: {routing_key}")

    def publish_message(
        self,
        exchange_name: str,
        routing_key: str,
        message: Dict[str, Any],
        delivery_mode: int = 2,  # 1=non-persistent, 2=persistent
    ) -> None:
        """
        Publish a message to an exchange

        Args:
            exchange_name: Name of the exchange
            routing_key: Routing key for message routing
            message: Message body (will be JSON serialized)
            delivery_mode: 1=non-persistent, 2=persistent
        """
        self._channel.basic_publish(
            exchange=exchange_name,
            routing_key=routing_key,
            body=json.dumps(message),
            properties=pika.BasicProperties(
                delivery_mode=delivery_mode,
                content_type="application/json",
            ),
        )
        logger.info(f"Published message to {exchange_name} with routing key: {routing_key}")

    def publish_plugin_task(
        self,
        plugin_name: str,
        task_data: Dict[str, Any],
    ) -> None:
        """
        Publish a plugin task to the plugin registry exchange

        Example:
            producer.publish_plugin_task("crypto", {
                "action": "collect",
                "since": "2026-05-01T00:00:00Z"
            })

        Args:
            plugin_name: Name of the target plugin
            task_data: Task data (action, parameters, etc.)
        """
        message = {
            "plugin": plugin_name,
            "task": task_data,
            "timestamp": "2026-05-02T12:00:00Z",  # Use ISO format
        }
        self.publish_message(
            exchange_name="plugin.tasks",
            routing_key=f"plugin.{plugin_name}",
            message=message,
        )

    def publish_event(
        self,
        event_type: str,
        event_data: Dict[str, Any],
    ) -> None:
        """
        Publish an event to the events exchange (topic exchange)

        Example:
            producer.publish_event("plugin.status.changed", {
                "plugin": "crypto",
                "status": "healthy"
            })

        Args:
            event_type: Type of event (e.g., "plugin.status.changed")
            event_data: Event data
        """
        message = {
            "event_type": event_type,
            "data": event_data,
            "timestamp": "2026-05-02T12:00:00Z",
        }
        self.publish_message(
            exchange_name="minder.events",
            routing_key=event_type,
            message=message,
        )


class RabbitMQConsumer:
    """
    RabbitMQ message consumer for processing messages from queues

    Usage:
        def callback(ch, method, properties, body):
            data = json.loads(body)
            print(f"Received: {data}")

        consumer = RabbitMQConsumer(config)
        consumer.consume_queue("plugin.crypto", callback)
    """

    def __init__(self, config: RabbitMQConfig):
        self.config = config
        self._connection: Optional[pika.BlockingConnection] = None
        self._channel: Optional[pika.adapters.blocking_connection.BlockingChannel] = None

    def connect(self) -> None:
        """Establish connection to RabbitMQ"""
        credentials = pika.PlainCredentials(self.config.username, self.config.password)
        parameters = pika.ConnectionParameters(
            host=self.config.host,
            port=self.config.port,
            virtual_host=self.config.virtual_host,
            credentials=credentials,
            heartbeat=self.config.heartbeat,
            blocked_connection_timeout=self.config.blocked_connection_timeout,
        )
        self._connection = pika.BlockingConnection(parameters)
        self._channel = self._connection.channel()
        logger.info("Connected to RabbitMQ")

    def close(self) -> None:
        """Close connection to RabbitMQ"""
        if self._connection and not self._connection.is_closed:
            self._connection.close()
            logger.info("Closed RabbitMQ connection")

    def set_qos(self, prefetch_count: int = 1) -> None:
        """
        Set Quality of Service (QoS) prefetch count

        Args:
            prefetch_count: Number of unacknowledged messages to allow
        """
        self._channel.basic_qos(prefetch_count=prefetch_count)
        logger.info(f"Set QoS prefetch count to: {prefetch_count}")

    def consume_queue(
        self,
        queue_name: str,
        callback: callable,
        auto_ack: bool = False,
    ) -> None:
        """
        Start consuming messages from a queue

        Args:
            queue_name: Name of the queue to consume from
            callback: Function to call for each message (ch, method, properties, body)
            auto_ack: Automatically acknowledge messages (not recommended)
        """

        def wrapper(ch, method, properties, body):
            try:
                data = json.loads(body.decode("utf-8"))
                callback(ch, method, properties, data)
                if not auto_ack:
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                logger.info(f"Processed message from queue: {queue_name}")
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                if not auto_ack:
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

        self._channel.basic_consume(
            queue=queue_name,
            on_message_callback=wrapper,
            auto_ack=auto_ack,
        )
        logger.info(f"Started consuming from queue: {queue_name}")
        self._channel.start_consuming()

    def consume_plugin_tasks(
        self,
        plugin_name: str,
        callback: callable,
    ) -> None:
        """
        Consume plugin-specific tasks from the plugin tasks exchange

        Example callback:
            def process_plugin_task(ch, method, properties, data):
                print(f"Processing task for plugin: {data['plugin']}")
                print(f"Task: {data['task']}")

        Args:
            plugin_name: Name of the plugin to consume tasks for
            callback: Function to call for each task
        """
        queue_name = f"plugin.{plugin_name}"
        self.consume_queue(queue_name, callback)


# =============================================================================
# Example Usage
# =============================================================================


def example_1_basic_producer_consumer():
    """
    Example 1: Basic producer/consumer pattern

    Demonstrates:
    - Direct exchange
    - Queue declaration
    - Basic message publishing and consuming
    """
    print("=" * 60)
    print("Example 1: Basic Producer/Consumer")
    print("=" * 60)

    config = RabbitMQConfig(
        username="minder",
        password="CHANGE_ME",  # nosec B106
    )

    # Producer
    producer = RabbitMQProducer(config)
    producer.connect()

    # Declare exchange and queue
    producer.declare_exchange("example.exchange", ExchangeType.DIRECT)
    producer.declare_queue("example.queue")
    producer.bind_queue("example.queue", "example.exchange", "example.key")

    # Publish message
    producer.publish_message(
        exchange_name="example.exchange",
        routing_key="example.key",
        message={"hello": "world", "value": 42},
    )
    producer.close()

    print("✅ Published message to example.exchange")


def example_2_plugin_task_distribution():
    """
    Example 2: Plugin task distribution (API Gateway → Plugin Registry)

    Demonstrates:
    - Direct exchange for point-to-point messaging
    - Plugin-specific routing keys
    - Task data serialization
    """
    print("=" * 60)
    print("Example 2: Plugin Task Distribution")
    print("=" * 60)

    config = RabbitMQConfig(
        username="minder",
        password="CHANGE_ME",  # nosec B106
    )

    # Producer (API Gateway)
    producer = RabbitMQProducer(config)
    producer.connect()

    # Declare plugin tasks exchange
    producer.declare_exchange("plugin.tasks", ExchangeType.DIRECT)

    # Declare and bind queues for each plugin
    for plugin in ["crypto", "network", "news", "tefas", "weather"]:
        queue_name = f"plugin.{plugin}"
        producer.declare_queue(queue_name)
        producer.bind_queue(queue_name, "plugin.tasks", f"plugin.{plugin}")

    # Publish tasks to plugins
    producer.publish_plugin_task(
        "crypto",
        {
            "action": "collect",
            "since": "2026-05-01T00:00:00Z",
        },
    )

    producer.publish_plugin_task(
        "weather",
        {
            "action": "collect",
            "location": "Istanbul",
        },
    )

    producer.close()

    print("✅ Published plugin tasks to plugin.tasks exchange")


def example_3_event_broadcasting():
    """
    Example 3: Event broadcasting (pub/sub pattern)

    Demonstrates:
    - Topic exchange for pub/sub messaging
    - Wildcard routing keys
    - Multiple consumers for different event patterns
    """
    print("=" * 60)
    print("Example 3: Event Broadcasting (Pub/Sub)")
    print("=" * 60)

    config = RabbitMQConfig(
        username="minder",
        password="CHANGE_ME",  # nosec B106
    )

    # Producer
    producer = RabbitMQProducer(config)
    producer.connect()

    # Declare events exchange (topic)
    producer.declare_exchange("minder.events", ExchangeType.TOPIC)

    # Declare and bind queues with different routing patterns
    producer.declare_queue("plugin.events")
    producer.bind_queue("plugin.events", "minder.events", "plugin.*")

    producer.declare_queue("all.events")
    producer.bind_queue("all.events", "minder.events", "#")

    # Publish events
    producer.publish_event(
        "plugin.status.changed",
        {
            "plugin": "crypto",
            "status": "healthy",
        },
    )

    producer.publish_event(
        "plugin.data.collected",
        {
            "plugin": "weather",
            "records": 10,
        },
    )

    producer.close()

    print("✅ Published events to minder.events exchange")


def example_4_dead_letter_queue():
    """
    Example 4: Dead Letter Queue (DLQ) handling

    Demonstrates:
    - DLQ declaration and configuration
    - Message rejection and requeuing
    - Failed message handling
    """
    print("=" * 60)
    print("Example 4: Dead Letter Queue (DLQ)")
    print("=" * 60)

    config = RabbitMQConfig(
        username="minder",
        password="CHANGE_ME",  # nosec B106
    )

    # Producer
    producer = RabbitMQProducer(config)
    producer.connect()

    # Declare DLQ
    producer.declare_queue("tasks.dlq")

    # Declare main queue with DLQ argument
    producer.declare_queue(
        "tasks.queue",
        arguments={
            "x-dead-letter-exchange": "",
            "x-dead-letter-routing-key": "tasks.dlq",
        },
    )

    # Publish message that might fail
    producer.publish_message(
        exchange_name="",
        routing_key="tasks.queue",
        message={"task": "risky_operation", "data": None},
    )

    producer.close()

    print("✅ Published message to DLQ-enabled queue")


# =============================================================================
# Integration Example for Minder Services
# =============================================================================


def api_gateway_plugin_task_producer():
    """
    API Gateway: Publish plugin tasks to RabbitMQ

    This would be integrated into the API Gateway service to offload
    plugin data collection tasks to the Plugin Registry service.
    """
    config = RabbitMQConfig(
        host="rabbitmq",  # Docker service name
        username="minder",
        password=os.getenv("RABBITMQ_PASSWORD", "CHANGE_ME"),
    )

    producer = RabbitMQProducer(config)
    producer.connect()

    # Declare plugin tasks exchange
    producer.declare_exchange("plugin.tasks", ExchangeType.DIRECT)

    # API Gateway receives request: POST /v1/plugins/crypto/collect
    # Instead of processing synchronously, publish to RabbitMQ
    producer.publish_plugin_task(
        "crypto",
        {
            "action": "collect",
            "since": "2026-05-01T00:00:00Z",
            "request_id": "uuid-here",
        },
    )

    producer.close()


def plugin_registry_task_consumer():
    """
    Plugin Registry: Consume plugin tasks from RabbitMQ

    This would be integrated into the Plugin Registry service to process
    plugin data collection tasks asynchronously.
    """

    def process_plugin_task(ch, method, properties, data):
        plugin_name = data.get("plugin")
        task = data.get("task")

        logger.info(f"Processing task for plugin: {plugin_name}")
        logger.info(f"Task data: {task}")

        # Execute plugin data collection
        # This would call the actual plugin's collect_data() method
        # result = await plugin.collect_data()

        # Task completed successfully
        logger.info(f"✅ Task completed for plugin: {plugin_name}")

    config = RabbitMQConfig(
        host="rabbitmq",
        username="minder",
        password=os.getenv("RABBITMQ_PASSWORD", "CHANGE_ME"),
    )

    consumer = RabbitMQConsumer(config)
    consumer.connect()
    consumer.set_qos(prefetch_count=1)  # Process one task at a time

    # Consume tasks for specific plugin
    consumer.consume_plugin_tasks("crypto", process_plugin_task)


if __name__ == "__main__":
    import os

    print("RabbitMQ Examples for Minder Platform")
    print("=" * 60)

    # Run examples
    example_1_basic_producer_consumer()
    example_2_plugin_task_distribution()
    example_3_event_broadcasting()
    example_4_dead_letter_queue()

    print("\n" + "=" * 60)
    print("All examples completed successfully!")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Install pika: pip install pika")
    print("2. Update RABBITMQ_PASSWORD in .env file")
    print("3. Start RabbitMQ: docker compose up -d rabbitmq")
    print("4. Run integration examples:")
    print("   - api_gateway_plugin_task_producer()")
    print("   - plugin_registry_task_consumer()")
