# Schema Registry Infrastructure

## Overview

Apicurio Registry for event schema management with Avro serialization.

## Purpose

- Central repository for all event schemas
- Schema evolution with compatibility rules
- Type-safe event contracts
- Kafka-style SerDe (Serialization/Deserialization)

## Architecture

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────┐
│ Microservices   │────▶│ Schema       │────▶│ Avro Schemas│
│ (Producers/     │     │ Registry     │     │ (Event      │
│  Consumers)     │     │ (Apicurio)   │     │  Contracts) │
└─────────────────┘     └──────────────┘     └─────────────┘
                              │
                              ▼
                       Compatibility
                       Validation
```

## Usage

### Register a Schema

```bash
curl -X POST http://localhost:8082/apis/registry/v2/groups/minder.artifacts/PluginRegistered \
  -H "Content-Type: application/vnd.schemaregistry.v1+json" \
  -d '{"type": "avro", "artifactType": "AVRO", "artifactId": "PluginRegistered"}'
```

### Get Latest Schema

```bash
curl http://localhost:8082/apis/registry/v2/groups/minder.artifacts/PluginRegistered
```

## Environment Variables

- `SCHEMA_REGISTRY_HOST` - Schema Registry service address (default: schema-registry:8080)
- `SCHEMA_REGISTRY_URL` - Public URL (default: http://localhost:8082)

## Compatibility Rules

- **BACKWARD** (default): New schemas must be readable by old consumers
- **FORWARD**: Old schemas must be readable by new consumers
- **FULL**: Both backward and forward compatible
- **NONE**: No compatibility checking

## Storage

Schemas stored in PostgreSQL for persistence:
- Database: `schema_registry`
- Table: `subject` (schema metadata)
- Table: `artifact` (schema versions)

## Monitoring

- Health: `http://localhost:8082/health`
- Metrics: `http://localhost:8082/metrics`
- UI: `http://localhost:8082` (Apicurio Console)
