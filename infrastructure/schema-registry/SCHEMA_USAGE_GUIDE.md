# Schema Registry Usage Guide

## Quick Start

### 1. Start the Schema Registry

```bash
cd /root/minder
docker compose -f infrastructure/docker/docker-compose.yml up -d schema-registry
```

### 2. Verify Installation

```bash
./infrastructure/schema-registry/verify-schema-registry.sh
```

### 3. Access the UI

Open your browser: http://localhost:8082

## Registering Schemas

### Using the Web UI

1. Navigate to http://localhost:8082
2. Click "Create Artifact"
3. Enter artifact ID (e.g., `PluginRegistered`)
4. Select type: `AVRO`
5. Paste or upload your Avro schema
6. Click "Create"

### Using the REST API

#### Register a Schema

```bash
curl -X POST http://localhost:8082/apis/registry/v2/groups/minder/artifacts \
  -H "Content-Type: application/vnd.schemaregistry.v1+json" \
  -d '{
    "artifactId": "PluginRegistered",
    "artifactType": "AVRO",
    "version": "1",
    "content": "{\"type\":\"record\",\"name\":\"PluginRegistered\",\"namespace\":\"minder.events\",\"fields\":[{\"name\":\"eventId\",\"type\":\"string\"},{\"name\":\"timestamp\",\"type\":\"long\"},{\"name\":\"pluginId\",\"type\":\"string\"},{\"name\":\"pluginName\",\"type\":\"string\"}]}"
  }'
```

#### Get Latest Schema

```bash
curl http://localhost:8082/apis/registry/v2/groups/minder/artifacts/PluginRegistered
```

#### Get Specific Version

```bash
curl http://localhost:8082/apis/registry/v2/groups/minder/artifacts/PluginRegistered/versions/1
```

#### List All Artifacts

```bash
curl http://localhost:8082/apis/registry/v2/groups/minder/artifacts
```

#### Update Schema (Create New Version)

```bash
curl -X POST http://localhost:8082/apis/registry/v2/groups/minder/artifacts/PluginRegistered/versions \
  -H "Content-Type: application/vnd.schemaregistry.v1+json" \
  -d '{
    "artifactType": "AVRO",
    "content": "{\"type\":\"record\",\"name\":\"PluginRegistered\",\"namespace\":\"minder.events\",\"fields\":[{\"name\":\"eventId\",\"type\":\"string\"},{\"name\":\"timestamp\",\"type\":\"long\"},{\"name\":\"pluginId\",\"type\":\"string\"},{\"name\":\"pluginName\",\"type\":\"string\"},{\"name\":\"newField\",\"type\":[\"null\",\"string\"],\"default\":null}]}"
  }'
```

## Schema Evolution

### Compatibility Rules

The Schema Registry enforces compatibility rules to ensure safe schema evolution:

- **BACKWARD** (default): New schemas must be readable by old consumers
  - ✅ Adding optional fields with default values
  - ✅ Removing fields (if they have default values)
  - ❌ Changing field types
  - ❌ Making required fields optional

- **FORWARD**: Old schemas must be readable by new consumers
  - ✅ Adding optional fields
  - ❌ Removing fields

- **FULL**: Both backward and forward compatible
  - ✅ Adding optional fields with default values
  - ❌ Removing fields
  - ❌ Changing field types

- **NONE**: No compatibility checking (not recommended)

### Example: Safe Schema Evolution

#### Original Schema (v1)
```json
{
  "type": "record",
  "name": "PluginRegistered",
  "fields": [
    {"name": "eventId", "type": "string"},
    {"name": "pluginId", "type": "string"}
  ]
}
```

#### Updated Schema (v2) - Backward Compatible
```json
{
  "type": "record",
  "name": "PluginRegistered",
  "fields": [
    {"name": "eventId", "type": "string"},
    {"name": "pluginId", "type": "string"},
    {"name": "description", "type": ["null", "string"], "default": null}
  ]
}
```

## Testing Schemas

### Validate Schema Syntax

```bash
# Using Avro tools
java -jar avro-tools.jar compile schema PluginRegistered.avsc /tmp/test

# Using Python
python3 -c "
import json
from avro import schema
with open('PluginRegistered.avsc', 'r') as f:
    s = schema.parse(f.read())
    print('Schema is valid!')
"
```

### Test Compatibility

```bash
# Test if new schema is compatible with old version
curl -X POST http://localhost:8082/apis/registry/v2/groups/minder/artifacts/PluginRegistered/check \
  -H "Content-Type: application/vnd.schemaregistry.v1+json" \
  -d '{
    "artifactType": "AVRO",
    "content": "<new-schema-json>"
  }'
```

## Integration with Services

### Python Example

```python
from confluent_kafka import SchemaRegistry
from confluent_kafka.schema_registry.avro import AvroSerializer

# Configure schema registry client
conf = {'url': 'http://localhost:8082'}
schema_registry_client = SchemaRegistry(conf)

# Get schema
subject = 'PluginRegistered'
schema = schema_registry_client.get_latest_version(subject)

# Serialize data
avro_serializer = AvroSerializer(schema.schema_str)
serialized_data = avro_serializer(data, schema.schema_id)
```

### Node.js Example

```javascript
const { SchemaRegistry } = require('@kafkajs/confluent-schema-registry');

const registry = new SchemaRegistry({
  host: 'http://localhost:8082'
});

// Register schema
const { id } = await registry.register({
  type: SchemaRegistry.Type.AVRO,
  schema: JSON.stringify(schemaDefinition)
});

// Encode data
const encoded = await registry.encode(id, payload);

// Decode data
const decoded = await registry.decode(encoded);
```

## Best Practices

1. **Use Semantic Versioning**: Tag schemas with versions (e.g., v1.0.0, v1.1.0)
2. **Document Changes**: Maintain a changelog for schema evolution
3. **Test Compatibility**: Always test compatibility before deploying
4. **Use Namespaces**: Organize schemas by domain (e.g., `minder.events.plugins`)
5. **Add Documentation**: Include `doc` fields in Avro schemas
6. **Default Values**: Always provide defaults for new fields
7. **Avoid Breaking Changes**: Prefer additive changes over destructive ones

## Troubleshooting

### Schema Registry Not Starting

```bash
# Check logs
docker logs minder-schema-registry

# Verify PostgreSQL connection
docker exec -it minder-schema-registry cat /opt/apicurio/config/application.properties
```

### Compatibility Errors

```bash
# Get compatibility rules
curl http://localhost:8082/apis/registry/v2/groups/minder/config/compatibility

# Update compatibility level
curl -X PUT http://localhost:8082/apis/registry/v2/groups/minder/config/compatibility \
  -H "Content-Type: application/json" \
  -d '"BACKWARD"'
```

### Health Check

```bash
curl http://localhost:8082/health
curl http://localhost:8082/metrics
```

## Next Steps

- Register your first event schema
- Set up schema validation in your services
- Implement event producers and consumers
- Configure schema evolution rules for your domain
