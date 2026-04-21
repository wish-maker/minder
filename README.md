# Minder

**Modular RAG Platform** - Cross-database correlation and AI-powered insights with plugin architecture

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

## 🚀 Quick Start

```bash
# Clone repository
git clone https://github.com/wish-maker/minder.git
cd minder

# Start infrastructure
cd infrastructure/docker
docker compose up -d

# Create plugin databases
for db in weather_db news_db crypto_db network_db tefas_db; do
  docker exec postgres psql -U postgres -c "CREATE DATABASE $db;"
done

# Start core service
cd ../..
docker compose -f infrastructure/docker/docker-compose.yml up -d core-service

# Check status
curl http://localhost:8001/health
```

## 📁 Project Structure

```
minder/
├── README.md                    # This file
├── pyproject.toml               # Python project config
├── requirements.txt              # Python dependencies
├── .gitignore                   # Git ignore rules
├── src/                         # Source code
│   ├── core/                   # Core framework
│   │   ├── kernel.py           # Main orchestrator
│   │   ├── registry.py         # Plugin registry
│   │   ├── event_bus.py        # Event system
│   │   ├── plugin_loader.py    # Plugin loading
│   │   └── ...                 # Other core modules
│   ├── plugins/                # Plugin implementations
│   │   ├── weather/            # Weather data collection
│   │   ├── news/               # News aggregation
│   │   ├── crypto/             # Cryptocurrency tracking
│   │   ├── network/            # System monitoring
│   │   └── tefas/              # Turkish fund data
│   ├── services/               # Microservices
│   │   └── core-service/       # Core API service
│   └── shared/                 # Shared utilities
├── tests/                      # Test suite
│   ├── unit/                   # Unit tests
│   ├── integration/            # Integration tests
│   └── fixtures/               # Test fixtures
├── infrastructure/             # Infrastructure
│   ├── docker/                 # Docker configurations
│   │   └── docker-compose.yml
│   ├── prometheus/             # Monitoring configs
│   ├── grafana/                # Dashboards
│   └── nginx/                   # Reverse proxy
├── config/                     # Configuration files
├── migrations/                 # Database migrations
└── docs/                       # Documentation
```

## 📊 Available Plugins

### 1. Weather Plugin
- **Port:** 8010
- **Database:** weather_db
- **Capabilities:** Weather data collection, forecasting
- **Status:** Ready (requires database setup)

### 2. News Plugin
- **Port:** 8011
- **Database:** news_db
- **Capabilities:** News aggregation, sentiment analysis
- **Status:** Ready (requires database setup)

### 3. Crypto Plugin
- **Port:** 8012
- **Database:** crypto_db
- **Capabilities:** Cryptocurrency price tracking
- **Status:** Ready (requires database setup)

### 4. Network Plugin
- **Port:** 8013
- **Database:** network_db
- **Capabilities:** System monitoring, network analysis
- **Status:** Ready (requires database setup)

### 5. TEFAS Plugin
- **Port:** 8014
- **Database:** tefas_db
- **Capabilities:** Turkish fund data collection
- **Status:** Ready (requires database setup and dependencies)

## 🔌 Core API Endpoints

### Health Check
```bash
curl http://localhost:8001/health
```

### List Plugins
```bash
curl http://localhost:8001/plugins
```

### System Status
```bash
curl http://localhost:8001/system/status
```

### Plugin Management
```bash
# Enable plugin
curl -X POST http://localhost:8001/plugins/{plugin_name}/enable

# Disable plugin
curl -X POST http://localhost:8001/plugins/{plugin_name}/disable

# Run pipeline
curl -X POST http://localhost:8001/plugins/{plugin_name}/pipeline \
  -H "Content-Type: application/json" \
  -d '{"pipeline": ["collect", "analyze"]}'
```

## 🧪 Testing

### Run All Tests
```bash
pytest tests/
```

### Run Unit Tests
```bash
pytest tests/unit/
```

### Run Integration Tests
```bash
pytest tests/integration/
```

### Run Tests with Coverage
```bash
pytest tests/ --cov=src --cov-report=html
```

## 🔧 Development

### Start Development Server
```bash
# Using pip install
pip install -e .

# Start development server
python -m uvicorn src.services.core-service.main:app --reload
```

### Code Quality
```bash
# Format code
black src/ tests/

# Lint code
ruff check src/ tests/

# Type checking
mypy src/
```

## 🐳 Deployment

### Start All Services
```bash
cd infrastructure/docker
docker compose up -d
```

### View Logs
```bash
# Core service logs
docker logs minder-core-service -f

# All services logs
docker compose logs -f
```

### Stop Services
```bash
docker compose down
```

## 📖 Documentation

Full documentation is available in the `docs/` directory:
- [Architecture Guide](docs/ARCHITECTURE.md)
- [Plugin Development](docs/PLUGIN_DEVELOPMENT.md)
- [Deployment Guide](docs/DEPLOYMENT.md)
- [API Documentation](docs/API.md)

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Follow the [Code Style Guide](docs/CONTRIBUTING.md)
4. Commit your changes (`git commit -m 'Add amazing feature'`)
5. Push to the branch (`git push origin feature/amazing-feature`)
6. Open a Pull Request

## 📝 License

MIT License - see LICENSE file for details

## 🔗 Links

- **Documentation:** [docs/](docs/)
- **API Docs:** http://localhost:8001/docs
- **Health Check:** http://localhost:8001/health
- **System Status:** http://localhost:8001/system/status

---

**Status:** ✅ Production Ready | **Version:** 2.0.0 | **Last Updated:** 2026-04-21