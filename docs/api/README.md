# 📡 API Documentation

Complete API reference for the Minder Platform.

---

## 📖 Quick Links

- **[API Reference](API_REFERENCE.md)** - Complete API documentation
- **[Authentication Guide](../guides/API_AUTHENTICATION_GUIDE.md)** - JWT authentication
- **[OpenWebUI Integration](../guides/OPENWEBUI_INTEGRATION_GUIDE.md)** - AI integration

---

## 🚀 Interactive Documentation

**Local:**
- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

---

## 📚 API Sections

### Authentication
- **[Login](../api/API_REFERENCE.md#post-v1authlogin)** - Authenticate and get access token

### Plugins
- **[List Plugins](../api/API_REFERENCE.md#get-v1plugins)** - Get all available plugins
- **[Get Plugin](../api/API_REFERENCE.md#get-v1pluginspluginid)** - Get specific plugin details
- **[Collect Data](../api/API_REFERENCE.md#post-v1pluginspluginidcollect)** - Collect data from plugin
- **[Analyze Data](../api/API_REFERENCE.md#post-v1pluginspluginidanalyze)** - Analyze collected data

### Monitoring
- **[Health Check](../api/API_REFERENCE.md#get-health)** - Check system health
- **[Metrics](../api/API_REFERENCE.md#get-metrics)** - Get Prometheus metrics

---

## 🔧 Quick Start

### 1. Get an Access Token

```bash
curl -X POST http://localhost:8000/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"your_password"}'
```

### 2. Use the Token

```bash
TOKEN="your_access_token_here"

curl -X POST http://localhost:8000/v1/plugins/crypto/collect \
  -H "Authorization: Bearer $TOKEN"
```

---

## 📖 API Endpoints

See [API_REFERENCE.md](API_REFERENCE.md) for complete endpoint documentation.

---

## 🤝 Contributing

- Follow [Code Style Guide](../development/CODE_STYLE_GUIDE.md)
- Add example requests/responses
- Update this README

---

**Last Updated:** 2026-04-19
