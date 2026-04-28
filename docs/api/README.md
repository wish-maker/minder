# API Documentation

Complete API reference for Minder Platform services.

## API Reference

### [API Reference](reference.md)
**Complete** - Full API documentation for all services.

Covers:
- Authentication
- Endpoints
- Request/response formats
- Error handling
- Rate limiting
- Examples

## Core APIs

### API Gateway (Port 8000)
**Base URL**: `http://localhost:8000`

Main entry point for all API requests.

Features:
- Request routing
- Authentication
- Rate limiting
- Request validation

### Plugin Registry (Port 8001)
**Base URL**: `http://localhost:8001`

Plugin discovery and lifecycle management.

Endpoints:
- `POST /api/v1/plugins/register` - Register plugin
- `GET /api/v1/plugins` - List plugins
- `GET /api/v1/plugins/{id}` - Get plugin details
- `PUT /api/v1/plugins/{id}` - Update plugin
- `DELETE /api/v1/plugins/{id}` - Delete plugin

### Marketplace (Port 8002)
**Base URL**: `http://localhost:8002`

Plugin marketplace and licensing.

Endpoints:
- `GET /api/v1/marketplace/plugins` - List marketplace plugins
- `POST /api/v1/marketplace/purchase` - Purchase plugin
- `GET /api/v1/marketplace/licenses` - List licenses

### State Manager (Port 8003)
**Base URL**: `http://localhost:8003`

Plugin state and AI tool execution.

Endpoints:
- `GET /api/v1/state/plugins/{id}` - Get plugin state
- `POST /api/v1/state/plugins/{id}/execute` - Execute plugin
- `GET /api/v1/state/plugins/{id}/status` - Get execution status

### AI Services (Port 8004)
**Base URL**: `http://localhost:8004`

RAG pipeline and embeddings.

Endpoints:
- `POST /api/v1/rag/query` - RAG query
- `POST /api/v1/embeddings` - Generate embeddings
- `GET /api/v1/rag/collections` - List collections

### Model Management (Port 8005)
**Base URL**: `http://localhost:8005`

Model versioning and fine-tuning.

Endpoints:
- `GET /api/v1/models` - List models
- `POST /api/v1/models` - Register model
- `POST /api/v1/models/{id}/fine-tune` - Fine-tune model

## Authentication

### JWT Authentication
All API endpoints require JWT authentication (except `/health`).

**Request Header:**
```
Authorization: Bearer <token>
```

**Example:**
```bash
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/plugins
```

### Authelia SSO
When using Authelia SSO:
1. Authenticate with Authelia
2. Receive session cookie
3. API requests are automatically authenticated

## Rate Limiting

API endpoints are rate-limited:
- **Default**: 100 requests per minute
- **Burst**: 50 requests

**Response Headers:**
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1234567890
```

## Error Handling

### Error Response Format
```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human readable error message",
    "details": {}
  }
}
```

### Common Error Codes
- `400` - Bad Request (invalid input)
- `401` - Unauthorized (authentication required)
- `403` - Forbidden (insufficient permissions)
- `404` - Not Found (resource doesn't exist)
- `429` - Too Many Requests (rate limit exceeded)
- `500` - Internal Server Error

## Quick Examples

### List Plugins
```bash
curl http://localhost:8001/api/v1/plugins
```

### Register Plugin
```bash
curl -X POST http://localhost:8001/api/v1/plugins/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-plugin",
    "version": "1.0.0",
    "description": "My awesome plugin"
  }'
```

### RAG Query
```bash
curl -X POST http://localhost:8004/api/v1/rag/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is the capital of France?",
    "collection": "knowledge-base"
  }'
```

## Interactive Documentation

### Swagger UI
When services are running, access interactive API documentation:
- API Gateway: http://localhost:8000/docs
- Plugin Registry: http://localhost:8001/docs
- Marketplace: http://localhost:8002/docs

### API Testing Tools
- **Postman** - Import API collection
- **curl** - Command-line testing
- **HTTPie** - User-friendly CLI

## Additional Resources

- [Authentication Guide](../guides/authentication.md) - Setup authentication
- [Development Guide](../development/development.md) - API development
- [Troubleshooting](../troubleshooting/common-issues.md) - Common issues
