# Schema Registry Quick Reference

## Endpoints

### Health & Monitoring
- **Health**: `GET /health`
- **Metrics**: `GET /metrics`
- **Info**: `GET /`

### Registry API v2
- **Base URL**: `/apis/registry/v2`
- **Artifacts**: `/groups/{group}/artifacts`
- **Versions**: `/groups/{group}/artifacts/{artifact}/versions`
- **Rules**: `/groups/{group}/artifacts/{artifact}/rules`

## Common Operations

### Register Schema
```bash
POST /apis/registry/v2/groups/minder/artifacts
Content-Type: application/vnd.schemaregistry.v1+json

{
  "artifactId": "PluginRegistered",
  "artifactType": "AVRO",
  "content": "{...}"
}
```

### Get Schema
```bash
GET /apis/registry/v2/groups/minder/artifacts/PluginRegistered
```

### List Artifacts
```bash
GET /apis/registry/v2/groups/minder/artifacts
```

### Update Schema
```bash
POST /apis/registry/v2/groups/minder/artifacts/PluginRegistered/versions
Content-Type: application/vnd.schemaregistry.v1+json

{
  "artifactType": "AVRO",
  "content": "{...}"
}
```

### Delete Schema
```bash
DELETE /apis/registry/v2/groups/minder/artifacts/PluginRegistered
```

### Check Compatibility
```bash
POST /apis/registry/v2/groups/minder/artifacts/PluginRegistered/check
Content-Type: application/vnd.schemaregistry.v1+json

{
  "artifactType": "AVRO",
  "content": "{...}"
}
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SCHEMA_REGISTRY_HOST` | `schema-registry:8081` | Internal service address |
| `SCHEMA_REGISTRY_URL` | `http://localhost:8082` | External access URL |

## Docker Commands

```bash
# Start service
docker compose -f infrastructure/docker/docker-compose.yml up -d schema-registry

# Stop service
docker compose -f infrastructure/docker/docker-compose.yml stop schema-registry

# View logs
docker logs -f minder-schema-registry

# Restart service
docker compose -f infrastructure/docker/docker-compose.yml restart schema-registry

# Remove service
docker compose -f infrastructure/docker/docker-compose.yml down -v
```

## Compatibility Levels

- **BACKWARD**: New schemas readable by old consumers (default)
- **FORWARD**: Old schemas readable by new consumers
- **FULL**: Both backward and forward
- **NONE**: No compatibility checking

## Configuration Files

- **Service Config**: `infrastructure/schema-registry/schema-registry-config.yml`
- **Docker Compose**: `infrastructure/docker/docker-compose.yml`
- **Environment**: `infrastructure/docker/.env`

## Schema Storage

Schemas are stored in PostgreSQL:
- **Database**: `minder`
- **Tables**: `subject`, `artifact`, `artifact_version`

## Example Schemas

Location: `infrastructure/schema-registry/examples/`
- `PluginRegistered.avsc` - Plugin registration event
- `PluginStateChanged.avsc` - Plugin state change event

## Documentation

- **README**: `infrastructure/schema-registry/README.md`
- **Usage Guide**: `infrastructure/schema-registry/SCHEMA_USAGE_GUIDE.md`
- **Quick Ref**: `infrastructure/schema-registry/QUICK_REFERENCE.md` (this file)

## Troubleshooting

### Check if service is running
```bash
curl http://localhost:8082/health
```

### View all artifacts
```bash
curl http://localhost:8082/apis/registry/v2/groups/minder/artifacts
```

### Check logs
```bash
docker logs minder-schema-registry
```

### Restart service
```bash
docker compose -f infrastructure/docker/docker-compose.yml restart schema-registry
```

## Next Steps

1. Register your first schema
2. Configure services to use schema registry
3. Implement event producers
4. Implement event consumers
5. Set up monitoring and alerts
