# Minder Platform - Code Examples

This directory contains practical examples for integrating with Minder platform services.

## RabbitMQ Examples

**File:** `rabbitmq_example.py`

**Purpose:** Demonstrates how to use RabbitMQ for asynchronous messaging between microservices.

**Examples included:**

1. **Basic Producer/Consumer** - Simple direct exchange pattern
2. **Plugin Task Distribution** - API Gateway → Plugin Registry messaging
3. **Event Broadcasting** - Pub/sub pattern with topic exchanges
4. **Dead Letter Queue** - Error handling and failed message processing

**Setup:**

```bash
# Install dependencies
pip install -r requirements.txt

# Set RabbitMQ password in .env
echo "RABBITMQ_PASSWORD=$(openssl rand -base64 32)" >> infrastructure/docker/.env

# Start RabbitMQ
docker compose -f infrastructure/docker/docker-compose.yml up -d rabbitmq

# Run examples
python rabbitmq_example.py
```

**Integration with Minder services:**

- **API Gateway** publishes plugin tasks to RabbitMQ
- **Plugin Registry** consumes tasks and executes plugin operations
- **Event broadcasting** for real-time status updates
- **Dead Letter Queue** for failed task handling

**Access:**

- AMQP port: 5672
- Management UI: http://localhost:15672
- Credentials: minder / (RABBITMQ_PASSWORD from .env)

**Documentation:**

See [Operations Guide - Message Queue](../docs/operations/README.md#message-queue-new) for detailed usage instructions.

---

## License

MIT License - See [LICENSE](../LICENSE) for details.
