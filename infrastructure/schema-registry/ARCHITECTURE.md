# Event-Driven Architecture with Schema Registry

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Event-Driven Architecture                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────┐         ┌──────────────┐         ┌──────────────┐   │
│  │   Service A  │         │   Service B  │         │   Service C  │   │
│  │  (Producer)  │         │  (Consumer)  │         │  (Consumer)  │   │
│  └──────┬───────┘         └──────▲───────┘         └──────▲───────┘   │
│         │                        │                        │            │
│         │                        │                        │            │
│         │                        │                        │            │
│         │                        │                        │            │
│         │                        │                        │            │
│         │                        │                        │            │
│         │         ┌──────────────┴────────────────────────┴──────┐    │
│         │         │                                             │    │
│         │         │         ┌──────────────────┐                │    │
│         │         │         │  Schema Registry │                │    │
│         │         │         │   (Apicurio)     │                │    │
│         │         │         │                  │                │    │
│         │         │         │ - Schema Storage │                │    │
│         │         │         │ - Validation     │                │    │
│         │         │         │ - Evolution      │                │    │
│         │         │         │ - Compatibility  │                │    │
│         │         │         └──────────────────┘                │    │
│         │         │                  │                          │    │
│         │         │                  │                          │    │
│         │         │                  ▼                          │    │
│         │         │         ┌──────────────────┐                │    │
│         │         └────────▶│   RabbitMQ       │◀───────────────┘    │
│         │                   │  (Message       │                      │
│         │                   │   Broker)       │                      │
│         │                   │                  │                      │
│         └──────────────────▶│  Event Streams  │                      │
│                             └──────────────────┘                      │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Component Relationships

### Schema Registry Flow

```
┌────────────────┐
│ Service        │
│ (Producer)     │
└────────┬───────┘
         │
         │ 1. Fetch Schema
         ▼
┌────────────────┐
│ Schema         │◀──────┐
│ Registry       │       │
│                │       │
│ - Get Schema   │       │
│ - Validate     │       │
│ - Version      │       │
└────────┬───────┘       │
         │               │
         │ 2. Serialize  │
         ▼               │
┌────────────────┐       │
│ Avro Serializer│       │
└────────┬───────┘       │
         │               │
         │ 3. Publish    │
         ▼               │
┌────────────────┐       │
│ RabbitMQ       │       │
└────────┬───────┘       │
         │               │
         │ 4. Consume    │
         ▼               │
┌────────────────┐       │
│ Service        │       │
│ (Consumer)     │       │
└────────┬───────┘       │
         │               │
         │ 5. Fetch      │
         │    Schema     │
         ▼               │
┌────────────────┐       │
│ Schema         │───────┘
│ Registry       │
└────────┬───────┘
         │
         │ 6. Deserialize
         ▼
┌────────────────┐
│ Avro           │
│ Deserializer   │
└────────────────┘
```

## Event Flow

### 1. Publishing Events

```
Service                    Schema Registry              RabbitMQ
   │                              │                        │
   │  1. Get Schema               │                        │
   │─────────────────────────────▶│                        │
   │                              │                        │
   │  2. Return Schema + ID       │                        │
   │◀─────────────────────────────│                        │
   │                              │                        │
   │  3. Validate & Serialize     │                        │
   │  (using Schema ID)           │                        │
   │                              │                        │
   │  4. Publish Event            │                        │
   │───────────────────────────────────────────────────────▶│
   │                              │                        │
   │                              │                        │
```

### 2. Consuming Events

```
Service                    Schema Registry              RabbitMQ
   │                              │                        │
   │  1. Consume Event            │                        │
   │◀──────────────────────────────────────────────────────│
   │                              │                        │
   │  2. Get Schema by ID         │                        │
   │─────────────────────────────▶│                        │
   │                              │                        │
   │  3. Return Schema            │                        │
   │◀─────────────────────────────│                        │
   │                              │                        │
   │  4. Deserialize & Validate   │                        │
   │  (using Schema)              │                        │
   │                              │                        │
```

## Schema Evolution

### Backward Compatibility

```
Version 1                    Version 2
┌─────────────────┐         ┌─────────────────┐
│ eventId         │         │ eventId         │
│ timestamp       │         │ timestamp       │
│ pluginId        │         │ pluginId        │
│ pluginName      │         │ pluginName      │
└─────────────────┘         │ description     │ (NEW - Optional)
                            └─────────────────┘

✅ Old consumers can read new events (ignore unknown fields)
✅ New consumers can read old events (use default for missing field)
```

### Breaking Changes (Avoid)

```
Version 1                    Version 2
┌─────────────────┐         ┌─────────────────┐
│ eventId         │         │ eventId         │
│ timestamp       │         │ timestamp       │
│ pluginId        │         │ pluginId        │  (CHANGED - String to Int)
│ pluginName      │         │ pluginName      │
└─────────────────┘         └─────────────────┘

❌ Type change breaks compatibility
❌ Requires new schema version
❌ Both versions must coexist during migration
```

## Benefits

### Type Safety
- **Compile-time validation**: Schemas validated at registration time
- **Runtime validation**: Events validated against schemas during serialization/deserialization
- **No data corruption**: Invalid events rejected before entering the system

### Evolution
- **Safe changes**: Compatibility rules prevent breaking changes
- **Versioning**: Multiple schema versions coexist
- **Gradual migration**: Services update at their own pace

### Documentation
- **Self-documenting**: Schemas serve as API documentation
- **Central repository**: Single source of truth for event contracts
- **Version history**: Track all changes to event schemas

### Performance
- **Binary format**: Avro is compact and fast
- **Schema caching**: Clients cache schemas for performance
- **No reflection**: Pre-compiled serializers/deserializers

## Integration Points

### Services
```
┌────────────────────────────────────────────────────────┐
│                                                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐│
│  │ Plugin       │  │ State        │  │ Model        ││
│  │ Registry     │  │ Manager      │  │ Management   ││
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘│
│         │                 │                 │          │
│         └─────────────────┴─────────────────┘          │
│                           │                            │
│                           ▼                            │
│                  ┌────────────────┐                    │
│                  │ Schema         │                    │
│                  │ Registry       │                    │
│                  └────────────────┘                    │
│                                                        │
└────────────────────────────────────────────────────────┘
```

### Data Flow

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ Plugin       │────▶│ RabbitMQ     │────▶│ State        │
│ Registry     │     │              │     │ Manager      │
│ (Producer)   │     │              │     │ (Consumer)   │
└──────────────┘     └──────────────┘     └──────────────┘
      │                                        │
      │                                        │
      └────────────┬───────────────────────────┘
                   │
                   ▼
            ┌──────────────┐
            │ Schema       │
            │ Registry     │
            │ (Validation) │
            └──────────────┘
```

## Migration Strategy

### Phase 1: Setup (Current)
- ✅ Deploy Schema Registry
- ✅ Configure infrastructure
- ✅ Define core event schemas
- ✅ Create documentation

### Phase 2: Integration
- ⏳ Update services to use schemas
- ⏳ Implement event producers
- ⏳ Implement event consumers
- ⏳ Add validation

### Phase 3: Migration
- ⏳ Migrate existing events
- ⏳ Update legacy services
- ⏳ Remove HTTP endpoints
- ⏳ Complete EDA transition

## Monitoring

### Key Metrics
- Schema registration rate
- Schema validation failures
- Event serialization errors
- API response times
- Storage usage

### Health Checks
```bash
# Schema Registry health
curl http://localhost:8082/health

# RabbitMQ health
curl http://localhost:15672/api/healthchecks

# Service health
curl http://localhost:8001/health
```

## Security

### Authentication
- Service-to-service authentication
- API key management
- Role-based access control

### Authorization
- Read-only access for consumers
- Write access for producers
- Admin access for schema management

### Network Security
- Internal network isolation
- TLS encryption
- Firewall rules

## Next Steps

1. **Register Core Schemas**
   - PluginRegistered
   - PluginStateChanged
   - ModelDeployed
   - StateUpdated

2. **Update Services**
   - Add schema registry clients
   - Implement serialization
   - Add error handling

3. **Testing**
   - Unit tests for schemas
   - Integration tests for events
   - Performance testing

4. **Documentation**
   - API documentation
   - Event catalog
   - Migration guides
