# Minder Platform - API Documentation

**Version:** 1.0.0
**Last Updated:** 2026-05-02
**Base URL:** `http://localhost:8000`
**Services:** 24 microservices (24 healthy, 100% operational)

---

## Overview

The Minder Platform provides RESTful APIs through a central API Gateway. All external requests go through Traefik reverse proxy, then Authelia for SSO/2FA, then to the API Gateway which handles authentication, rate limiting, routing, and logging.

**API Architecture:**
```
Client → Traefik (80/443) → Authelia (9091 SSO/2FA) → API Gateway (8000)
                                                          → Plugin Registry (8001)
                                                          → Marketplace (8002)
                                                          → State Manager (8003)
                                                          → AI Services (8004)
                                                          → Model Management (8005)
                                                          → TTS/STT Service (8006)
                                                          → Model Fine-tuning (8007)
```

**Current Status:**
- ✅ All core APIs (8000-8007) healthy and responding
- ✅ Authelia authentication operational
- ✅ Traefik reverse proxy fully functional
- ✅ Redis master authentication fixed
- ✅ Automatic AI model downloads enabled
- 🧪 115 API tests passing (98% coverage, 2 skipped)

---

## Quick Start

### Interactive Documentation

**Swagger UI (Recommended):**
```
http://localhost:8000/docs
```

**ReDoc:**
```
http://localhost:8000/redoc
```

**OpenAPI Spec:**
```
http://localhost:8000/openapi.json
```

### Testing APIs

**Using curl:**
```bash
# Health check
curl http://localhost:8000/health

# List plugins
curl http://localhost:8000/v1/plugins

# Get specific plugin info
curl http://localhost:8000/v1/plugins/crypto
```

**Using Python:**
```python
import httpx

async def get_plugins():
    async with httpx.AsyncClient() as client:
        response = await client.get("http://localhost:8000/v1/plugins")
        return response.json()
```

---

## Core Endpoints

### 1. Health Check

Check API Gateway health and dependency status.

**Endpoint:** `GET /health`

**Authentication:** Not required

**Response:**
```json
{
  "service": "api-gateway",
  "status": "degraded",
  "timestamp": "2026-04-23T13:00:00.000000",
  "version": "1.0.0",
  "environment": "development",
  "phase": 1,
  "checks": {
    "redis": "healthy",
    "plugin_registry": "healthy",
    "rag_pipeline": "unreachable: connection refused",
    "model_management": "unreachable: connection refused"
  },
  "message": "Phase 1 active - Phase 2 services not started"
}
```

**Status Values:**
- `healthy`: All services operational
- `degraded`: Some services unavailable (partial functionality)
- `unhealthy`: Critical services unavailable

**Example:**
```bash
curl -s http://localhost:8000/health | jq '.status'
# Output: "degraded"
```

---

### 2. List All Plugins

Retrieve list of all loaded plugins with their status.

**Endpoint:** `GET /v1/plugins`

**Authentication:** Not required (development)

**Response:**
```json
{
  "count": 5,
  "plugins": [
    {
      "name": "crypto",
      "version": "1.0.0",
      "status": "registered",
      "health_status": "healthy",
      "description": "Cryptocurrency data collection and analysis",
      "author": "Minder",
      "capabilities": [
        "crypto_data_collection",
        "price_analysis",
        "market_correlation"
      ]
    },
    {
      "name": "network",
      "version": "1.0.0",
      "status": "registered",
      "health_status": "healthy",
      "description": "Network performance monitoring and security analysis",
      "author": "Minder",
      "capabilities": [
        "network_monitoring",
        "performance_tracking",
        "security_analysis"
      ]
    }
  ]
}
```

**Plugin Status Values:**
- `registered`: Plugin loaded and available
- `initialized`: Plugin initialized and ready
- `running`: Plugin actively processing
- `error`: Plugin encountered error

**Example:**
```bash
# Get all plugins
curl -s http://localhost:8000/v1/plugins | jq '.plugins[].name'

# Get only healthy plugins
curl -s http://localhost:8000/v1/plugins | jq '.plugins[] | select(.health_status == "healthy") | .name'

# Count plugins by status
curl -s http://localhost:8000/v1/plugins | jq '.plugins | group_by(.status) | map({status: .[0].status, count: length})'
```

---

### 3. Get Plugin Details

Retrieve detailed information about a specific plugin.

**Endpoint:** `GET /v1/plugins/{plugin_name}`

**Authentication:** Not required (development)

**Path Parameters:**
- `plugin_name` (string, required): Name of the plugin (crypto, network, news, tefas, weather)

**Response:**
```json
{
  "name": "crypto",
  "version": "1.0.0",
  "status": "registered",
  "health_status": "healthy",
  "description": "Cryptocurrency data collection and analysis",
  "author": "Minder",
  "capabilities": [
    "crypto_data_collection",
    "price_analysis",
    "market_correlation"
  ],
  "data_sources": ["CoinGecko API"],
  "databases": ["postgresql", "influxdb"],
  "metadata": {
    "last_collection": "2026-04-23T12:30:00Z",
    "total_records": 1500,
    "collection_frequency": "hourly"
  }
}
```

**Error Response:**
```json
{
  "detail": "Plugin 'invalid_name' not found"
}
```

**Example:**
```bash
# Get crypto plugin details
curl -s http://localhost:8000/v1/plugins/crypto | jq '.'

# Check plugin health
curl -s http://localhost:8000/v1/plugins/crypto | jq '.health_status'

# Get plugin capabilities
curl -s http://localhost:8000/v1/plugins/crypto | jq '.capabilities[]'
```

---

### 4. Trigger Plugin Data Collection

Manually trigger data collection for a specific plugin.

**Endpoint:** `POST /v1/plugins/{plugin_name}/collect`

**Authentication:** Not required (development)

**Path Parameters:**
- `plugin_name` (string, required): Name of the plugin

**Request Body:**
```json
{
  "since": "2026-04-23T10:00:00Z"
}
```

**Parameters:**
- `since` (ISO 8601 datetime, optional): Start date for data collection

**Response:**
```json
{
  "success": true,
  "plugin": "crypto",
  "records_collected": 10,
  "records_updated": 5,
  "errors": 0,
  "duration_seconds": 2.5,
  "timestamp": "2026-04-23T13:00:00Z"
}
```

**Error Response:**
```json
{
  "success": false,
  "error": "Plugin 'invalid_name' not found",
  "timestamp": "2026-04-23T13:00:00Z"
}
```

**Example:**
```bash
# Trigger collection for all data
curl -X POST http://localhost:8000/v1/plugins/crypto/collect | jq '.'

# Trigger collection for last 24 hours
curl -X POST http://localhost:8000/v1/plugins/weather/collect \
  -H "Content-Type: application/json" \
  -d '{"since": "2026-04-22T13:00:00Z"}' | jq '.'

# Trigger collection for all plugins
for plugin in crypto network news tefas weather; do
  echo "Collecting $plugin..."
  curl -X POST http://localhost:8000/v1/plugins/$plugin/collect | jq '.records_collected'
done
```

---

### 5. Get Plugin Analysis Results

Retrieve analysis results from a plugin.

**Endpoint:** `GET /v1/plugins/{plugin_name}/analyze`

**Authentication:** Not required (development)

**Path Parameters:**
- `plugin_name` (string, required): Name of the plugin

**Query Parameters:**
- `since` (ISO 8601 datetime, optional): Start date for analysis

**Response:**
```json
{
  "plugin": "weather",
  "timestamp": "2026-04-23T13:00:00Z",
  "metrics": {
    "avg_temp_c": 18.5,
    "avg_humidity_pct": 65.2,
    "avg_pressure_hpa": 1013.5,
    "avg_wind_speed_kmh": 12.3
  },
  "patterns": [
    {
      "type": "seasonal",
      "description": "Temperature follows seasonal pattern",
      "confidence": 0.85
    }
  ],
  "insights": [
    "Weather data collected successfully",
    "Average temperature: 18.5°C",
    "Humidity levels within normal range"
  ]
}
```

**Example:**
```bash
# Get analysis results
curl -s http://localhost:8000/v1/plugins/weather/analyze | jq '.'

# Get specific metric
curl -s http://localhost:8000/v1/plugins/weather/analyze | jq '.metrics.avg_temp_c'

# Get insights only
curl -s http://localhost:8000/v1/plugins/weather/analyze | jq '.insights[]'
```

---

## Plugin Registry API

### Base URL
```
http://localhost:8001
```

### Endpoints

#### 1. Registry Health Check

**Endpoint:** `GET /health`

**Response:**
```json
{
  "service": "plugin-registry",
  "status": "healthy",
  "timestamp": "2026-04-23T13:00:00.000000",
  "version": "1.0.0",
  "environment": "development",
  "plugins_loaded": 5,
  "services_registered": 0
}
```

#### 2. Get All Plugins (Direct)

**Endpoint:** `GET /v1/plugins`

**Response:** Same as API Gateway endpoint

---

## Error Handling

### Standard Error Response Format

```json
{
  "detail": "Error message describing what went wrong",
  "error_code": "SPECIFIC_ERROR_CODE",
  "timestamp": "2026-04-23T13:00:00Z",
  "request_id": "uuid-of-request"
}
```

### Common HTTP Status Codes

| Status | Meaning | Example |
|--------|---------|---------|
| 200 | Success | Plugin retrieved successfully |
| 400 | Bad Request | Invalid plugin name in path |
| 404 | Not Found | Plugin does not exist |
| 500 | Internal Server Error | Plugin collection failed |

### Error Examples

**Plugin Not Found (404):**
```json
{
  "detail": "Plugin 'nonexistent' not found. Available plugins: crypto, network, news, tefas, weather"
}
```

**Invalid Request (400):**
```json
{
  "detail": "Invalid date format. Use ISO 8601 format (e.g., 2026-04-23T10:00:00Z)"
}
```

**Internal Error (500):**
```json
{
  "detail": "Failed to collect data from external API. Connection timeout after 30 seconds",
  "error_code": "COLLECTION_FAILED"
}
```

---

## Authentication & Authorization

### Current Status (Development)

**Authentication:** Disabled
**Authorization:** Disabled
**Rate Limiting:** Disabled

### Production Implementation (Planned)

**JWT Authentication:**
```bash
# Login request
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "secret"}'

# Response
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 3600
}

# Use token
curl -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..." \
  http://localhost:8000/v1/plugins
```

---

## Rate Limiting

### Current Status (Development)

**Rate Limiting:** Disabled

### Production Configuration

**Planned Limits:**
- 60 requests per minute per IP
- 100 burst requests
- Configurable per endpoint

**Rate Limit Headers:**
```http
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1713873600
```

---

## Data Models

### Plugin Object

```typescript
interface Plugin {
  name: string;              // Unique plugin identifier
  version: string;           // Semantic version
  status: string;            // registered | initialized | running | error
  health_status: string;     // healthy | unhealthy | degraded
  description: string;       // Plugin description
  author: string;            // Plugin author
  capabilities: string[];    // List of capabilities
  data_sources: string[];    // Data source names
  databases: string[];       // Database names
  metadata?: {
    last_collection?: string;   // ISO 8601 timestamp
    total_records?: number;     // Total records collected
    collection_frequency?: string; // "hourly" | "daily"
  };
}
```

### Collection Result

```typescript
interface CollectionResult {
  success: boolean;
  plugin: string;
  records_collected: number;
  records_updated: number;
  errors: number;
  duration_seconds: number;
  timestamp: string;          // ISO 8601 timestamp
}
```

### Analysis Result

```typescript
interface AnalysisResult {
  plugin: string;
  timestamp: string;          // ISO 8601 timestamp
  metrics: Record<string, number>;
  patterns: Array<{
    type: string;
    description: string;
    confidence?: number;
  }>;
  insights: string[];
}
```

---

## WebSocket API (Planned)

### Real-time Data Streaming

**Endpoint:** `WS /v1/stream/{plugin_name}`

**Example:**
```javascript
const ws = new WebSocket('ws://localhost:8000/v1/stream/crypto');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Price update:', data);
};

// Response format
{
  "plugin": "crypto",
  "data": {
    "btc_price": 45230.50,
    "eth_price": 2845.30
  },
  "timestamp": "2026-04-23T13:00:00Z"
}
```

---

## Plugin Development

### Creating a New Plugin

**1. Create plugin structure:**
```
src/plugins/myplugin/
├── __init__.py
├── plugin.py          # Main plugin class
├── manifest.yml       # Plugin metadata
└── utils/             # Helper modules
    └── __init__.py
```

**2. Implement plugin interface:**
```python
from src.core.interface import BaseModule, ModuleMetadata

class MyPlugin(BaseModule):
    async def register(self) -> ModuleMetadata:
        return ModuleMetadata(
            name="myplugin",
            version="1.0.0",
            description="My custom plugin",
            author="Your Name",
            capabilities=["custom_capability"],
        )

    async def collect_data(self) -> Dict[str, int]:
        # Implementation
        pass
```

**3. Add to Plugin Registry:**
The plugin will be automatically discovered and loaded.

### Plugin API Reference

See [PLUGIN_DEVELOPMENT.md](PLUGIN_DEVELOPMENT.md) for detailed plugin development guide.

---

## Monitoring & Metrics

### Prometheus Metrics

**Metrics Endpoint:** `GET /metrics`

**Available Metrics:**
- `http_requests_total` - Total HTTP requests
- `http_request_duration_seconds` - Request latency
- `http_requests_in_progress` - Current requests

**Example:**
```bash
# Get metrics
curl -s http://localhost:8000/metrics | grep http_requests_total

# Output
http_requests_total{method="GET",endpoint="/v1/plugins",status="200"} 156
```

---

## SDK Examples

### Python SDK

```python
from minder_client import MinderClient

# Initialize client
client = MinderClient(base_url="http://localhost:8000")

# List plugins
plugins = await client.list_plugins()
print(f"Loaded {plugins.count} plugins")

# Collect data
result = await client.collect_data("crypto")
print(f"Collected {result.records_collected} records")

# Get analysis
analysis = await client.get_analysis("weather")
print(f"Average temp: {analysis.metrics.avg_temp_c}°C")
```

### JavaScript SDK

```javascript
import { MinderClient } from '@minder/sdk';

const client = new MinderClient('http://localhost:8000');

// List plugins
const plugins = await client.plugins.list();
console.log(`Loaded ${plugins.count} plugins`);

// Collect data
const result = await client.plugins.collect('crypto');
console.log(`Collected ${result.records_collected} records`);
```

---

## Changelog


### Version 1.0.0 (2026-05-02)
- Initial release
- Basic CRUD operations for plugins
- Health check endpoints
- Added security layer (Traefik + Authelia SSO/2FA)
- Expanded to 32 services (24 healthy, 100% success rate)
- RabbitMQ 3.13-management integrated for async messaging
- Plugin task distribution via RabbitMQ (API Gateway → Plugin Registry)
- Event broadcasting with pub/sub pattern
- Dead Letter Queue (DLQ) for error handling
- RabbitMQ Management UI at http://localhost:15672
- Improved test coverage to 98% (115 tests passing, 2 skipped)
- Added automatic AI model downloads (llama3.2 + nomic-embed-text)
- Added realistic startup timeline (~9 minutes)
- Updated all documentation to match real project status
- Added Redis master authentication fix
- Improved health check responses
- Added comprehensive API documentation
- Standardized error response format
- Professional project cleanup (765MB, zero cache files)
- Setup.sh v1.0.0 enterprise rewrite (14 commands, 66 functions, 1894 lines)
- Doctor command for deep diagnostics
- Advanced backup system (multi-database support)
- Shell access for container debugging
- Migration support for database schemas
- JSON output for CI/CD integration
- Smart version management with registry queries

---

## Support

**Documentation:**
- [Plugin Development Guide](PLUGIN_DEVELOPMENT.md)
- [Architecture Documentation](architecture.md)
- [Code Style Guide](CODE_STYLE_GUIDE.md)

**Issues:**
- Report bugs: [GitHub Issues](https://github.com/yourusername/minder/issues)
- Feature requests: [GitHub Discussions](https://github.com/yourusername/minder/discussions)

**Contact:**
- Email: support@minder.ai
- Discord: [Minder Community](https://discord.gg/minder)
