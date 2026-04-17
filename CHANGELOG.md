# Changelog

All notable changes to Minder will be documented in this file.

## [2.0.0] - 2026-04-17

### Added
- Comprehensive test suite with 12 integration tests (100% passing)
- System verification and health check endpoints
- Prometheus metrics with singleton pattern (fixes duplicate registry issues)
- Professional documentation structure
- Verified system status tracking

### Changed
- **UPGRADED**: Python 3.11 → 3.13
- **UPDATED**: borsapy to version 0.8.4 (per user request)
- **UPDATED**: tefas-crawler to version 0.5.0 (PyPI compatibility)
- **UPDATED**: ollama to >=0.3.0 (httpx 0.27+ compatibility)
- **UPDATED**: httpx upper bound to <0.28.0 (dependency resolution)
- **FIXED**: FastAPI router inclusion in system endpoints
- **FIXED**: Alertmanager YAML syntax errors
- **IMPROVED**: Docker image optimization (794MB final size)

### Fixed
- Prometheus Counter duplicate registration error (ValueError: Duplicated timeseries)
- Python dependency conflicts between borsapy, ollama, and httpx
- Alertmanager configuration YAML syntax error (line 51)
- Docker image cleanup (removed ~13GB of old images)
- Plugin health validation on startup

### Test Results
- Phase 2: Risk Metrics (3/3) ✅
- Phase 3: Allocation & Tax (3/3) ✅
- Phase 4: Module Integration (2/2) ✅
- Phase 5: End-to-End (4/4) ✅

### Active Plugins (Verified)
- **news**: News aggregation from Reuters, Bloomberg, Anadolu
- **network**: Performance monitoring with InfluxDB
- **weather**: Weather data collection from Open-Meteo API
- **tefas**: Turkish fund analysis (working with borsapy 0.8.4)

### Known Issues
- Crypto plugin has "No module named 'minder'" error (non-critical)
- TEFAS plugin shows dependency warning (functional despite warning)

## [1.0.0] - Initial Release

### Features
- Modular RAG platform architecture
- Plugin system with hot-swappable capabilities
- JWT authentication with bcrypt
- Network-aware rate limiting
- Event-driven architecture
- Knowledge graph and correlation engine
- Voice interface with Whisper STT and Coqui XTTS v2 TTS
- Character system (FinBot, SysBot)
- Plugin store with GitHub integration
- Multi-database support (PostgreSQL, InfluxDB, Qdrant, Redis)
- OpenWebUI integration
- Grafana dashboards
- Prometheus metrics
