# Minder

**Modular RAG Platform** - Cross-database correlation and AI-powered insights

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/release/python-3110/)
[![GitHub](https://img.shields.io/badge/GitHub-wish--maker-blue.svg)](https://github.com/wish-maker/minder)

## 🎯 Overview

Minder is a comprehensive, modular AI platform that enables cross-database correlation and AI-powered insights across diverse data sources. Each domain operates as an independent plugin that can collect data, analyze patterns, train AI models, index knowledge, and correlate with other plugins.

## ✨ Features

### Core Capabilities
- **Hot-swappable plugins**: Add/remove plugins without kernel restart
- **Cross-plugin correlation**: Discover relationships between different data sources
- **Event-driven architecture**: Pub/sub messaging for real-time updates
- **Knowledge graph**: Entity resolution and relationship inference
- **Plugin Store**: Install plugins from GitHub repositories
- **Voice interface**: Whisper STT + Coqui XTTS v2 TTS
- **Character system**: Pre-built AI personalities (FinBot, SysBot, etc.)

### Security
- JWT authentication with bcrypt password hashing
- Role-based access control (admin/user/readonly)
- Network-aware rate limiting (Redis backend)
- CORS & security headers
- Input validation & sanitization

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Minder Kernel                      │
│  - Plugin Registry & Lifecycle                      │
│  - Event Bus (Pub/Sub)                              │
│  - Knowledge Graph                                  │
│  - Correlation Engine                               │
└─────────────────────────────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
   ┌────▼────┐      ┌───▼────┐       ┌───▼────┐
   │  TEFAS  │      │ Network │       │ Weather │
   │ Plugin  │      │ Plugin  │       │ Plugin  │
   └─────────┘      └─────────┘       └─────────┘
```

## 📦 Included Plugins

| Plugin | Description | Data Sources |
|--------|-------------|--------------|
| **TEFAS** | Turkish fund analysis | TEFAS API, PostgreSQL |
| **Network** | Performance monitoring | InfluxDB, NetFlow |
| **Weather** | Weather data collection | Open-Meteo API |
| **Crypto** | Cryptocurrency tracking | CoinGecko, Binance |
| **News** | News aggregation | Reuters, Bloomberg, Anadolu |

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose
- 8GB+ RAM recommended
- NVIDIA GPU (optional, for Ollama)

### Installation

```bash
# Clone repository
git clone https://github.com/wish-maker/minder.git
cd minder

# Start with Docker
docker-compose up -d

# Check status
curl http://localhost:8000/health

# Open OpenWebUI
open http://localhost:3000
```

### Environment Variables

```bash
cp .env.example .env
# Edit .env with your configuration
```

Key variables:
- `JWT_SECRET_KEY`: Secret key for JWT tokens
- `POSTGRES_PASSWORD`: PostgreSQL password
- `REDIS_HOST`: Redis server host

## 📡 API Usage

### Authentication

```bash
# Login
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}'
```

### Plugin Management

```bash
# List plugins
curl http://localhost:8000/plugins

# Run pipeline
curl -X POST http://localhost:8000/plugins/tefas/pipeline \
  -H "Content-Type: application/json" \
  -d '{"pipeline": ["collect", "analyze", "train"]}'

# Get correlations
curl http://localhost:8000/correlations
```

### Chat Interface

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Hangi fonları önerirsin?",
    "character": "finbot"
  }'
```

## 🧩 Creating Plugins

### Plugin Structure

```bash
mkdir my-plugin
cd my-plugin
cat > plugin.yml << EOF
name: my-plugin
version: 1.0.0
description: My custom Minder plugin
author: Your Name
EOF
```

### Implementation

```python
# my_plugin.py
from core.module_interface import BaseModule, ModuleMetadata

class MyPlugin(BaseModule):
    async def register(self) -> ModuleMetadata:
        return ModuleMetadata(
            name="my-plugin",
            version="1.0.0",
            description="My custom plugin",
            author="Your Name"
        )

    async def collect_data(self, since=None):
        # Your data collection logic
        return {'records_collected': 100}
```

See [Plugin Development Guide](docs/development/module-development.md) for details.

## 📊 Monitoring

- **API Health**: http://localhost:8000/health
- **OpenWebUI**: http://localhost:3000
- **Grafana**: http://localhost:3002 (admin/minder123)

## 🧪 Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific test
pytest tests/test_auth.py -v

# Check coverage
pytest tests/ --cov=. --cov-report=html
```

## 📚 Documentation

- [Architecture](docs/architecture.md)
- [Plugin Development](docs/development/module-development.md)
- [Module Management](docs/guides/module-management.md)
- [API Reference](docs/api/)

## 🗺️ Roadmap

- [ ] Mobile app with voice interface
- [ ] Telegram bot integration
- [ ] Real-time alert system
- [ ] Advanced anomaly detection (AutoML)
- [ ] Multi-language support expansion
- [ ] Voice cloning marketplace
- [ ] Custom plugin builder UI

## 🤝 Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for details.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see [LICENSE](LICENSE) for details.

## 📧 Contact

- **Organization**: [wish-maker](https://github.com/wish-maker)
- **Repository**: [minder](https://github.com/wish-maker/minder)

---

**Built with ❤️ for the AI community**
