# Minder - Modular RAG Platform

> **Minder** is a modular Retrieval-Augmented Generation (RAG) platform that enables cross-database correlation and AI-powered insights across diverse data sources.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/release/python-3110/)

## 🎯 Overview

Minder is a comprehensive, modular AI platform where each domain operates as an independent plugin that can:

- **Collect data** from its own sources
- **Analyze** patterns and generate insights
- **Train AI models** on domain-specific data
- **Index knowledge** for RAG queries
- **Correlate** with other plugins across databases

## 🏗️ Architecture

### Jellyfin-Style Plugin System

```
┌─────────────────────────────────────────────────────┐
│                   Minder Kernel                      │
│  - Plugin Registry & Lifecycle                      │
│  - Event Bus (Pub/Sub)                              │
│  - Knowledge Graph                                  │
│  - Correlation Engine                               │
│  - Plugin Store (GitHub Integration)                │
└─────────────────────────────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
   ┌────▼────┐      ┌───▼────┐       ┌───▼────┐
   │  TEFAS  │      │ Network │       │ Weather │
   │ Plugin  │      │ Plugin  │       │ Plugin  │
   └─────────┘      └─────────┘       └─────────┘
        │                 │                 │
   ┌────▼────┐      ┌───▼────┐       ┌───▼────┐
   │  Crypto │      │  News  │       │ Custom  │
   │ Plugin  │      │ Plugin  │       │ Plugin  │
   └─────────┘      └─────────┘       └─────────┘
```

### Plugin Interface

All plugins implement `BaseModule` with these methods:

```python
class BaseModule(ABC):
    async def register() -> ModuleMetadata
    async def collect_data() -> Dict[str, int]
    async def analyze() -> Dict[str, Any]
    async def train_ai() -> Dict[str, Any]
    async def index_knowledge() -> Dict[str, int]
    async def get_correlations() -> List[Dict]
    async def get_anomalies() -> List[Dict]
```

## 🚀 Features

### ✅ Core Capabilities

- **Hot-swappable plugins**: Add/remove plugins without kernel restart
- **Cross-plugin correlation**: Discover relationships between different data sources
- **Event-driven architecture**: Pub/sub messaging for real-time updates
- **Knowledge graph**: Entity resolution and relationship inference
- **Parallel processing**: Multi-plugin data collection and analysis
- **GitHub integration**: Install plugins from any git repository

### 🏪 Plugin Store

Jellyfin-style plugin management:
- Install plugins from GitHub repositories
- Version control and automatic updates
- 3rd party plugin support
- Plugin validation and security scanning
- Community plugin index

### 🎤 Voice Interface

- **STT**: Whisper (OpenAI) for speech recognition
- **TTS**: Coqui XTTS v2 for natural voice synthesis
- **Languages**: Turkish, English, German, French, Spanish, Italian
- **Voice cloning**: Custom voice profiles for each character

### 🤖 Character System

Pre-built personalities:

- **FinBot** (Turkish): Professional financial assistant
- **SysBot** (English): Technical system administrator
- **ResearchBot** (English): Academic research assistant
- **BossBot** (Turkish): Executive decision support

## 📦 Included Plugins

### TEFAS Plugin
- **Data Sources**: TEFAS API, PostgreSQL
- **Capabilities**: Real-time fund data, historical analysis (2020+), return calculation, volatility analysis, performance metrics, risk assessment
- **Correlations**: Network latency, weather patterns, market sentiment

### Network Plugin
- **Data Sources**: InfluxDB, NetFlow
- **Capabilities**: Performance monitoring, anomaly detection, intrusion detection, traffic analysis
- **Correlations**: Trading volumes, system capacity

### Weather Plugin
- **Data Sources**: OpenWeatherMap API
- **Capabilities**: Weather data collection, forecast analysis, seasonal pattern detection
- **Correlations**: Market sentiment, fund flows

### Crypto Plugin
- **Data Sources**: CoinGecko, Binance
- **Capabilities**: Price tracking, volume analysis, sentiment analysis

### News Plugin
- **Data Sources**: Reuters, Bloomberg, Anadolu
- **Capabilities**: News aggregation, sentiment analysis, trend detection

## 🛠️ Installation

### Prerequisites

- Docker & Docker Compose
- NVIDIA GPU (optional, for Ollama)
- 8GB+ RAM recommended

### Quick Start

```bash
# Clone repository
git clone https://github.com/yourusername/minder.git
cd minder

# Build and start with Docker
docker-compose up -d

# Check status
curl http://localhost:8000/health

# Open OpenWebUI
open http://localhost:3000
```

## 📡 API Usage

### Chat with Minder

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Hangi fonları önerirsin?",
    "character": "finbot"
  }'
```

### List Plugins

```bash
curl http://localhost:8000/plugins
```

### Plugin Store Operations

```bash
# Search plugins
curl http://localhost:8000/plugins/store/search?q=finance

# Install from GitHub
curl -X POST http://localhost:8000/plugins/store/install \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url": "https://github.com/username/minder-plugin",
    "branch": "main"
  }'

# List installed plugins
curl http://localhost:8000/plugins/store/installed
```

### Run Pipeline

```bash
curl -X POST http://localhost:8000/plugins/tefas/pipeline \
  -H "Content-Type: application/json" \
  -d '{
    "plugin": "tefas",
    "pipeline": ["collect", "analyze", "train"]
  }'
```

### Get Correlations

```bash
curl http://localhost:8000/correlations
```

## 🧩 Creating Custom Plugins

### 1. Create Plugin Structure

```bash
mkdir my-plugin
cd my-plugin
cat > plugin.yml << EOF
name: my-plugin
version: 1.0.0
description: My custom Minder plugin
author: Your Name
repository: https://github.com/username/my-plugin
EOF
```

### 2. Implement Plugin Class

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

    # Implement other methods...
```

### 3. Deploy to GitHub

```bash
git init
git add .
git commit -m "Initial plugin"
git remote add origin https://github.com/username/my-plugin
git push -u origin main
```

### 4. Install to Minder

```bash
curl -X POST http://localhost:8000/plugins/store/install \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url": "https://github.com/username/my-plugin"
  }'
```

## 📊 Monitoring

- **Grafana**: http://localhost:3002 (admin/minder123)
- **OpenWebUI**: http://localhost:3000
- **API Health**: http://localhost:8000/health

## 🔬 Cross-Plugin Correlation Examples

### Financial Risk Analysis
```
TEFAS Returns ↔ Network Latency ↔ Weather Events
└── Discover: Trading system delays during storms correlate with price slippage
```

### Capacity Planning
```
Network Throughput ↔ Trading Volume ↔ Crypto Market Activity
└── Predict: Bandwidth needs during market rallies
```

### Research Validation
```
News Sentiment ↔ Fund Flows ↔ Weather Patterns
└── Validate: Bad weather → negative news → fund outflows
```

## 🗺️ Roadmap

- [ ] Mobile app with voice interface
- [ ] Telegram bot integration
- [ ] Real-time alert system
- [ ] Advanced anomaly detection (AutoML)
- [ ] Multi-language support expansion
- [ ] Voice cloning marketplace
- [ ] Custom plugin builder UI
- [ ] Community plugin marketplace

## 📄 License

MIT License - see LICENSE file for details

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### Plugin Development

1. Fork the repository
2. Create your plugin following the [Plugin Development Guide](PLUGIN_DEVELOPMENT.md)
3. Submit your plugin to our community index

## 📧 Contact

- **Author**: Minder AI
- **Email**: contact@minder.ai
- **Website**: https://minder.ai
- **GitHub**: https://github.com/minder-ai/minder

---

**Built with ❤️ for the AI community**
