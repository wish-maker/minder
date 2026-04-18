# Minder

**Modular RAG Platform** - Cross-database correlation and AI-powered insights

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-65%2F66%20passing-brightgreen.svg)](https://github.com/wish-maker/minder)
[![GitHub](https://img.shields.io/badge/GitHub-wish--maker-blue.svg)](https://github.com/wish-maker/minder)
[![Version](https://img.shields.io/badge/version-1.0.0--stable-green.svg)](https://github.com/wish-maker/minder)

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

Required variables:
- `POSTGRES_PASSWORD`: PostgreSQL database password
- `JWT_SECRET_KEY`: Secret key for JWT tokens (min 32 chars)
- `POSTGRES_HOST`: Database host (default: postgres)
- `POSTGRES_PORT`: Database port (default: 5432)

**⚠️ Security**: Do NOT use default passwords in production!

Generate secure passwords:
```bash
openssl rand -hex 32  # For JWT_SECRET_KEY
openssl rand -base64 24  # For database passwords
```

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


## ✅ System Status

**Last Verified**: April 18, 2026

### Production Readiness: v1.0.0 (Stable)
- **Test Coverage**: 65/66 tests passing (98.5%)
- **Active Plugins**: 5/5 healthy (all v1.0.0)
- **Database Management**: Complete (setup, backup, restore, cleanup)
- **Data Verification**: System operational
- **Documentation**: Updated and accurate

### Plugin Status
| Plugin | Version | Status | Data Source |
|--------|---------|--------|-------------|
| **TEFAS** | 1.0.0 | ✅ Healthy | borsapy 0.8.4, tefas-crawler 0.5.0 |
| **Network** | 1.0.0 | ✅ Healthy | System metrics (psutil) |
| **Weather** | 1.0.0 | ✅ Healthy | Open-Meteo API (free) |
| **Crypto** | 1.0.0 | ✅ Healthy | Binance, CoinGecko, Kraken |
| **News** | 1.0.0 | ✅ Healthy | BBC, Guardian, NPR RSS |

### Dependencies
- **Python**: 3.13
- **borsapy**: 0.8.4 (Turkish financial data)
- **tefas-crawler**: 0.5.0 (Turkish fund data)
- **ollama**: >=0.3.0 (LLM integration)
- **httpx**: >=0.25.2,<0.28.0 (HTTP client)

## 📊 Monitoring

- **API Health**: http://localhost:8000/health
- **OpenWebUI**: http://localhost:3000
- **Grafana**: http://localhost:3002 (admin/minder123)
- **Data Verification**: `./scripts/verify_system.py`

## 🧪 Testing

### Current Test Status (April 18, 2026)
✅ **65/66 tests passing (98.5% success rate)**
- Authentication & Security: 15/15 passing
- API Endpoints: 12/12 passing
- Plugin Management: 15/15 passing
- System Health: 5/5 passing
- Data Verification: 18/18 passing

### Running Tests
```bash
# Run all tests
pytest tests/ -v

# Run specific test
pytest tests/test_auth.py -v

# Check coverage
pytest tests/ --cov=. --cov-report=html

# Verify system health
./scripts/verify_system.py
```
## 📚 Documentation

- [Architecture](docs/architecture.md)
- [Plugin Development](docs/development/module-development.md)
- [Module Management](docs/guides/module-management.md)
- [API Reference](docs/api/)

## 🗺️ Roadmap

### Version 1.0.0 (Current - Stable)
- ✅ Core plugin system working
- ✅ Database management complete
- ✅ Data verification system operational
- ✅ Backup/restore procedures tested
- ✅ Documentation updated

### Version 1.1.0 (Planned)
- [ ] Connection pooling for databases
- [ ] Automated data collection scheduling
- [ ] Performance optimization (async I/O)
- [ ] Enhanced monitoring dashboards

### Version 2.0.0 (Future)
- [ ] Mobile app with voice interface
- [ ] Telegram bot integration
- [ ] Real-time alert system
- [ ] Advanced anomaly detection (AutoML)
- [ ] Multi-language support expansion

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
