# src/shared/projections/base_projection_handler.py

import abc
import json
import logging

import pika

logger = logging.getLogger(__name__)


class BaseProjectionHandler(abc.ABC):
    """Base class for projection handlers"""

    def __init__(self, rabbitmq_url: str):
        self.rabbitmq_url = rabbitmq_url
        self._connection = None
        self._channel = None

    def start(self):
        """Start consuming events"""
        self._connection = pika.BlockingConnection(pika.URLParameters(self.rabbitmq_url))
        self._channel = self._connection.channel()

        # Declare exchange
        self._channel.exchange_declare(exchange="domain_events", exchange_type="topic", durable=True)

        # Declare queue
        queue_name = f"{self.__class__.__name__}_queue"
        self._channel.queue_declare(queue=queue_name, durable=True)

        # Bind to routing keys
        for routing_key in self.routing_keys:
            self._channel.queue_bind(exchange="domain_events", queue=queue_name, routing_key=routing_key)

        # Consume
        self._channel.basic_consume(queue=queue_name, on_message_callback=self._on_message, auto_ack=False)

        logger.info(f"Started {self.__class__.__name__}")
        self._channel.start_consuming()

    def _on_message(self, channel, method, properties, body):
        """Handle incoming message"""
        try:
            message = json.loads(body)
            event_data = message.get("payload", {})
            event_type = message.get("event_type")
            is_replay = message.get("is_replay", False)

            # Call event handler
            handler_name = f"_handle_{event_type.lower()}"
            handler = getattr(self, handler_name, None)
            if handler:
                handler(event_data, is_replay)

            channel.basic_ack(delivery_tag=method.delivery_tag)

        except Exception as e:
            logger.error(f"Error processing message: {e}")
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
