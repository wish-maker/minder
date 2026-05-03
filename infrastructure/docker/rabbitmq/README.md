# RabbitMQ Configuration - Minder Platform

**Version:** 3.13-management
**Purpose:** Message Queue for asynchronous inter-service communication

---

## Overview

RabbitMQ provides reliable asynchronous messaging between Minder microservices:

- **Plugin Tasks**: API Gateway → Plugin Registry task distribution
- **Event Broadcasting**: Pub/sub pattern for system-wide events
- **Dead Letter Queues**: Error handling and failed message processing

---

## Configuration Files

### rabbitmq.conf

Main RabbitMQ configuration file with:
- Memory and disk limits
- Authentication settings
- Management plugin configuration
- Performance tuning
- Default queue type (quorum for durability)

### definitions.json

Pre-configured RabbitMQ objects:
- **Users**: minder (administrator)
- **Exchanges**: plugin.tasks (direct), minder.events (topic)
- **Queues**: plugin.{crypto,network,news,tefas,weather} + DLQs
- **Bindings**: Plugin-specific routing keys
- **Policies**: Max length (10K), DLQ expiry (7 days)

---

## Exchanges

### 1. plugin.tasks (Direct Exchange)
- **Type**: direct
- **Purpose**: Point-to-point plugin task distribution
- **Routing keys**: plugin.{crypto,network,news,tefas,weather}

**Usage:**
```python
producer.publish_message(
    exchange_name="plugin.tasks",
    routing_key="plugin.crypto",
    message={"action": "collect"}
)
```

### 2. minder.events (Topic Exchange)
- **Type**: topic
- **Purpose**: Pub/sub for system-wide events
- **Routing patterns**: plugin.* (all plugin events)

**Usage:**
```python
producer.publish_event(
    event_type="plugin.status.changed",
    event_data={"plugin": "crypto", "status": "healthy"}
)
```

---

## Queues

### Plugin Queues
Each plugin has its own queue with Dead Letter Queue:

| Queue | Type | Purpose | DLQ |
|-------|------|---------|-----|
| plugin.crypto | quorum | Crypto plugin tasks | plugin.crypto.dlq |
| plugin.network | quorum | Network plugin tasks | plugin.network.dlq |
| plugin.news | quorum | News plugin tasks | plugin.news.dlq |
| plugin.tefas | quorum | TEFAS plugin tasks | plugin.tefas.dlq |
| plugin.weather | quorum | Weather plugin tasks | plugin.weather.dlq |

### Queue Features
- **Durability**: True (survives broker restart)
- **Queue Type**: Quorum (replicated, fault-tolerant)
- **Dead Letter Exchange**: Failed messages route to DLQ
- **Max Length**: 10,000 messages (policy)

---

## Policies

### queue-max-length
- **Pattern**: `plugin\.`
- **Limit**: 10,000 messages
- **Action**: Messages rejected when queue is full

### dlq-expiry
- **Pattern**: `.*\.dlq`
- **TTL**: 604,800,000ms (7 days)
- **Action**: DLQ messages expire after 7 days

---

## Access

### AMQP Port
- **Port**: 5672
- **Protocol**: AMQP 0-9-1
- **Usage**: Application connections

### Management UI
- **URL**: http://localhost:15672
- **Username**: minder
- **Password**: (RABBITMQ_PASSWORD from .env)

### Management Features
- Queue monitoring (depth, rates)
- Message browsing
- Connection management
- Policy configuration
- User and permission management

---

## Operations

### Start RabbitMQ
```bash
docker compose -f infrastructure/docker/docker-compose.yml up -d rabbitmq
```

### Check Status
```bash
docker ps | grep rabbitmq
curl -u minder:${RABBITMQ_PASSWORD} http://localhost:15672/api/overview
```

### View Queues
```bash
curl -u minder:${RABBITMQ_PASSWORD} http://localhost:15672/api/queues
```

### View Messages
```bash
# Get messages from plugin.crypto queue
curl -u minder:${RABBITMQ_PASSWORD} \
  http://localhost:15672/api/queues/%2F/plugin.crypto/get
```

### Purge Queue
```bash
# Delete all messages from plugin.crypto queue
curl -u minder:${RABBITMQ_PASSWORD} \
  -X DELETE \
  http://localhost:15672/api/queues/%2F/plugin.crypto/contents
```

---

## Integration with Minder Services

### API Gateway (Producer)
```python
from examples.rabbitmq_example import RabbitMQProducer, RabbitMQConfig

config = RabbitMQConfig(
    host="rabbitmq",
    username="minder",
    password=os.getenv("RABBITMQ_PASSWORD")
)

producer = RabbitMQProducer(config)
producer.connect()

# Publish plugin task
producer.publish_plugin_task("crypto", {
    "action": "collect",
    "since": "2026-05-01T00:00:00Z"
})
```

### Plugin Registry (Consumer)
```python
from examples.rabbitmq_example import RabbitMQConsumer, RabbitMQConfig

config = RabbitMQConfig(
    host="rabbitmq",
    username="minder",
    password=os.getenv("RABBITMQ_PASSWORD")
)

consumer = RabbitMQConsumer(config)
consumer.connect()
consumer.set_qos(prefetch_count=1)

def process_task(ch, method, properties, data):
    plugin_name = data.get("plugin")
    task = data.get("task")
    # Execute plugin task
    logger.info(f"Processing task for plugin: {plugin_name}")

consumer.consume_plugin_tasks("crypto", process_task)
```

---

## Monitoring

### Prometheus Metrics (Future)
RabbitMQ Prometheus plugin for metrics:
- Queue depth
- Message rates (publish/ack/deliver)
- Connection count
- Channel count

### Grafana Dashboards (Future)
- Queue depth trends
- Message throughput
- Consumer lag
- DLQ message count

---

## Troubleshooting

### Queue Building Up
```bash
# Check queue depth
curl -u minder:${RABBITMQ_PASSWORD} \
  http://localhost:15672/api/queues/%2F/plugin.crypto

# Check consumer count
# If 0, consumers are not running or not connected properly
```

### Messages in DLQ
```bash
# Check DLQ messages
curl -u minder:${RABBITMQ_PASSWORD} \
  http://localhost:15672/api/queues/%2F/plugin.crypto.dlq

# Analyze failure reason
# Common causes:
# - Plugin execution failed
# - Database connection error
# - Invalid message format
```

### Connection Refused
```bash
# Check RabbitMQ is running
docker ps | grep rabbitmq

# Check logs
docker logs minder-rabbitmq

# Verify password
echo $RABBITMQ_PASSWORD
```

---

## Security

### Production Hardening
- ✅ Strong password (RABBITMQ_PASSWORD in .env)
- ✅ Default user (guest) disabled
- ✅ Management UI accessible only via Traefik/Authelia
- ⏳ TLS/SSL for AMQP connections (future)
- ⏳ LDAP authentication integration (future)
- ⏳ Network segmentation (future)

### Password Generation
```bash
openssl rand -base64 32
```

---

## Performance Tuning

### Current Settings
- **Memory watermark**: 40% of RAM
- **Disk limit**: 50MB minimum free space
- **Heartbeat**: 60 seconds
- **Channel max**: 2048
- **Connection max**: Unlimited

### Optimization Tips
1. **Queue Type**: Quorum queues for durability, classic for performance
2. **Prefetch Count**: Set to 1 for fair dispatch, higher for throughput
3. **Message Size**: Keep messages under 128KB for optimal performance
4. **Consumer Count**: Multiple consumers per queue for parallel processing

---

## Backup and Restore

### Export Definitions
```bash
curl -u minder:${RABBITMQ_PASSWORD} \
  http://localhost:15672/api/definitions > rabbitmq-backup.json
```

### Import Definitions
```bash
curl -u minder:${RABBITMQ_PASSWORD} \
  -X POST \
  -H "content-type:application/json" \
  -d @rabbitmq-backup.json \
  http://localhost:15672/api/definitions
```

---

## References

- [RabbitMQ Documentation](https://www.rabbitmq.com/docs)
- [Management Plugin](https://www.rabbitmq.com/management.html)
- [Configuration Guide](https://www.rabbitmq.com/configure.html)
- [Queue Types](https://www.rabbitmq.com/queues.html)

---

**Last Updated:** 2026-05-02
**Maintained by:** Minder Platform Team
