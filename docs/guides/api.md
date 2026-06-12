# Minder Platform - API Documentation

Comprehensive API documentation for all Minder platform services.

## 📚 Service APIs

### Core Services

#### 1. API Gateway (`http://localhost:8000`)

Central entry point for all API requests.

**Base URL:** `http://localhost:8000`

**Endpoints:**

##### Health Check
```http
GET /health
```

**Response:**
```json
{
  "service": "api-gateway",
  "status": "healthy",
  "version": "2.0.0",
  "timestamp": "2025-01-11T10:00:00Z",
  "dependencies": [
    {
      "name": "redis",
      "status": "healthy",
      "url": "redis://redis:6379",
      "response_time_ms": 2.5
    },
    {
      "name": "plugin_registry",
      "status": "healthy",
      "url": "http://minder-plugin-registry:8001",
      "response_time_ms": 15.3
    }
  ]
}
```

##### Authentication
```http
POST /v1/auth/login
Content-Type: application/json

{
  "username": "admin",
  "password": "admin"
}
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

---

#### 2. Plugin Marketplace (`http://localhost:8002`)

Plugin marketplace and licensing system.

**Base URL:** `http://localhost:8002`

##### Health Check
```http
GET /health
```

**Response:**
```json
{
  "service": "marketplace",
  "status": "healthy",
  "version": "1.0.0",
  "environment": "development"
}
```

##### List Plugins
```http
GET /plugins?page=1&page_size=10&sort_by=name&sort_order=asc
```

**Query Parameters:**
- `page` (optional): Page number (default: 1)
- `page_size` (optional): Items per page (default: 10, max: 100)
- `sort_by` (optional): Field to sort by
- `sort_order` (optional): Sort order (asc, desc)

**Response:**
```json
{
  "items": [
    {
      "id": "plugin-123",
      "name": "My Plugin",
      "version": "1.0.0",
      "description": "A sample plugin",
      "author": "Developer",
      "status": "active"
    }
  ],
  "total": 100,
  "page": 1,
  "page_size": 10,
  "total_pages": 10,
  "success": true
}
```

##### Install Plugin
```http
POST /plugins/install
Content-Type: application/json
Authorization: Bearer <token>

{
  "source": "git",
  "url": "https://github.com/user/plugin.git",
  "manifest": {
    "name": "my-plugin",
    "version": "1.0.0"
  }
}
```

**Response:**
```json
{
  "id": "plugin-123",
  "created_at": "2025-01-11T10:00:00Z",
  "success": true,
  "message": "Plugin installed successfully"
}
```

---

#### 3. Plugin Registry (`http://localhost:8001`)

Plugin discovery and lifecycle management.

**Base URL:** `http://localhost:8001`

##### Health Check
```http
GET /health
```

**Response:**
```json
{
  "service": "plugin-registry",
  "status": "healthy",
  "version": "2.0.0",
  "checks": {
    "plugins_loaded": 5
  }
}
```

##### List Plugins
```http
GET /v1/plugins
```

**Response:**
```json
[
  {
    "name": "my-plugin",
    "version": "1.0.0",
    "description": "A plugin",
    "author": "Developer",
    "enabled": true,
    "health_status": "healthy"
  }
]
```

##### Enable Plugin
```http
POST /v1/plugins/{plugin_name}/enable
Authorization: Bearer <token>
```

**Response:**
```json
{
  "message": "Plugin enabled",
  "plugin_name": "my-plugin"
}
```

---

#### 4. Plugin State Manager (`http://localhost:8003`)

Central plugin management and AI tools execution.

**Base URL:** `http://localhost:8003`

##### Health Check
```http
GET /health
```

**Response:**
```json
{
  "service": "Plugin State Manager",
  "version": "2.1.0",
  "status": "healthy",
  "checks": {
    "database": "connected"
  }
}
```

##### List Active Plugins
```http
GET /v1/plugins?status=active
```

**Response:**
```json
[
  {
    "name": "plugin-1",
    "state": "ACTIVE",
    "last_execution": "2025-01-11T09:30:00Z",
    "execution_count": 150
  }
]
```

---

### AI Services

#### 5. RAG Pipeline (`http://localhost:8004`)

Production RAG Pipeline with Clean Architecture.

**Base URL:** `http://localhost:8004`

##### Health Check
```http
GET /health
```

**Response:**
```json
{
  "service": "rag-pipeline",
  "status": "healthy",
  "version": "2.0.0",
  "checks": {
    "ollama": "available",
    "qdrant": "connected",
    "knowledge_base_service": "initialized",
    "retrieval_service": "initialized"
  }
}
```

##### Query Knowledge Base
```http
POST /query
Content-Type: application/json

{
  "query": "What is machine learning?",
  "knowledge_base_id": "kb-123",
  "max_results": 5,
  "filters": {
    "category": "AI"
  }
}
```

**Response:**
```json
{
  "query": "What is machine learning?",
  "results": [
    {
      "content": "Machine learning is...",
      "score": 0.95,
      "metadata": {
        "source": "document-1",
        "page": 15
      }
    }
  ],
  "execution_time_ms": 150.5
}
```

##### Ingest Document
```http
POST /ingest
Content-Type: multipart/form-data

file: <document_file>
knowledge_base_id: kb-123
```

**Response:**
```json
{
  "success": true,
  "document_id": "doc-456",
  "chunks_created": 15,
  "message": "Document ingested successfully"
}
```

---

#### 6. Model Management (`http://localhost:8005`)

Model management and fine-tuning service.

**Base URL:** `http://localhost:8005`

##### Health Check
```http
GET /health
```

##### List Models
```http
GET /models
```

**Response:**
```json
[
  {
    "id": "model-123",
    "name": "llama3.2",
    "type": "local",
    "provider": "ollama",
    "size": "4.7GB",
    "status": "loaded"
  }
]
```

---

#### 7. Model Fine-Tuning (`http://localhost:8007`)

Production ML model fine-tuning with Ollama.

**Base URL:** `http://localhost:8007`

##### Health Check
```http
GET /health
```

##### Start Fine-Tuning Job
```http
POST /jobs
Content-Type: application/json

{
  "base_model": "llama3.2",
  "training_data": ["kb-123", "kb-456"],
  "output_name": "my-finetuned-model",
  "hyperparameters": {
    "epochs": 3,
    "learning_rate": 0.001
  }
}
```

**Response:**
```json
{
  "job_id": "job-789",
  "status": "queued",
  "message": "Fine-tuning job created"
}
```

---

### Supporting Services

#### 8. TTS/STT Service (`http://localhost:8006`)

Text-to-Speech and Speech-to-Text service.

**Base URL:** `http://localhost:8006`

##### Health Check
```http
GET /health
```

**Response:**
```json
{
  "service": "tts-stt",
  "status": "healthy",
  "version": "1.0.0",
  "checks": {
    "tts": "available",
    "stt": "available",
    "supported_languages": "10"
  }
}
```

##### Text-to-Speech
```http
POST /tts
Content-Type: application/json

{
  "text": "Hello, world!",
  "language": "en",
  "slow": false
}
```

**Response:** Audio file (audio/mpeg)

##### Speech-to-Text
```http
POST /stt
Content-Type: multipart/form-data

audio: <audio_file>
language: en-US
```

**Response:**
```json
{
  "text": "Hello, world!",
  "language": "en-US",
  "confidence": 0.95
}
```

---

#### 9. Graph-RAG Service (`http://localhost:8009`)

Entity extraction and knowledge graph construction.

**Base URL:** `http://localhost:8009`

##### Health Check
```http
GET /health
```

**Response:**
```json
{
  "service": "graph-rag",
  "status": "healthy",
  "version": "1.0.0",
  "checks": {
    "entity_extractor": "initialized",
    "graph_constructor": "initialized",
    "graph_retriever": "initialized",
    "neo4j": "bolt://neo4j:7687",
    "spacy_model": "en_core_web_sm"
  }
}
```

##### Extract Entities
```http
POST /entities/extract
Content-Type: application/json

{
  "text": "Apple Inc. was founded by Steve Jobs in Cupertino, California.",
  "model": "en_core_web_sm"
}
```

**Response:**
```json
{
  "entities": [
    {
      "text": "Apple Inc.",
      "label": "ORG",
      "confidence": 0.98
    },
    {
      "text": "Steve Jobs",
      "label": "PERSON",
      "confidence": 0.95
    }
  ]
}
```

---

## 🔒 Authentication

Most services require JWT authentication for write operations.

### Get Token
```http
POST /v1/auth/login
Content-Type: application/json

{
  "username": "admin",
  "password": "admin"
}
```

### Use Token
```http
GET /protected-endpoint
Authorization: Bearer <your_token>
```

---

## 📝 Common Response Formats

### Success Response
```json
{
  "success": true,
  "message": "Operation completed",
  "data": { ... },
  "timestamp": "2025-01-11T10:00:00Z"
}
```

### Error Response
```json
{
  "success": false,
  "error": "Error type",
  "detail": { ... },
  "timestamp": "2025-01-11T10:00:00Z"
}
```

### Paginated Response
```json
{
  "items": [ ... ],
  "total": 100,
  "page": 1,
  "page_size": 10,
  "total_pages": 10,
  "success": true
}
```

---

## 🧪 Testing APIs

### Using cURL

```bash
# Health check
curl http://localhost:8000/health

# Login
curl -X POST http://localhost:8000/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin"}'

# List plugins (with token)
curl http://localhost:8002/plugins \
  -H "Authorization: Bearer <token>"

# Query RAG
curl -X POST http://localhost:8004/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What is AI?", "knowledge_base_id": "kb-123"}'
```

### Using Python

```python
import httpx

# Health check
response = httpx.get("http://localhost:8000/health")
print(response.json())

# Login
response = httpx.post(
    "http://localhost:8000/v1/auth/login",
    json={"username": "admin", "password": "admin"}
)
token = response.json()["access_token"]

# Use token
headers = {"Authorization": f"Bearer {token}"}
response = httpx.get(
    "http://localhost:8002/plugins",
    headers=headers
)
print(response.json())
```

---

## 📊 Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Created |
| 400 | Bad Request |
| 401 | Unauthorized |
| 403 | Forbidden |
| 404 | Not Found |
| 429 | Rate Limited |
| 500 | Internal Server Error |
| 503 | Service Unavailable |

---

## 🔄 Rate Limiting

Most services implement rate limiting:

- **Default:** 100 requests per minute
- **Burst:** 10 requests per second
- **Headers:**
  - `X-RateLimit-Limit`: 100
  - `X-RateLimit-Remaining`: 95
  - `X-RateLimit-Reset`: 1234567890

---

## 📖 More Information

- [Shared Components README](../services/shared/README.md)
- [Code Quality Improvements](../docs/CODE_QUALITY_IMPROVEMENTS.md)
- [Architecture Documentation](../docs/architecture/)

---

**Last Updated:** 2025-01-11  
**API Version:** 1.0.0
