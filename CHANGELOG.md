# Changelog

All notable changes to Minder will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-04-15

### Added
- Initial release of Minder Modular RAG Platform
- JWT authentication system with bcrypt password hashing
- Role-based access control (admin/user/readonly)
- Network-aware rate limiting with Redis backend
- Security middleware with CORS and security headers
- Plugin system with hot-swappable modules
- Cross-plugin correlation engine
- Event-driven architecture (Pub/Sub)
- Knowledge graph with entity resolution
- Voice interface (Whisper STT, Coqui XTTS v2 TTS)
- Character system with pre-built personalities
- Plugin Store with GitHub integration
- OpenWebUI integration

### Plugins
- TEFAS: Turkish fund data analysis
- Network: Performance monitoring and anomaly detection
- Weather: Open-Meteo API integration
- Crypto: CoinGecko and Binance integration
- News: Multi-source aggregation

### Documentation
- Complete README with architecture diagrams
- API usage examples
- Plugin development guide
- Deployment instructions

### Security
- Input validation and sanitization
- SQL injection protection
- XSS protection
- Path traversal protection

### Testing
- Comprehensive test suite (54 passing tests)
- API endpoint verification
- Database integration tests
- Security middleware tests

## [Unreleased]

### Planned
- Mobile app with voice interface
- Telegram bot integration
- Real-time alert system
- Advanced anomaly detection (AutoML)
- Multi-language support expansion
