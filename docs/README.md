# Minder Platform - Documentation

This directory contains all documentation for the Minder platform.

## 📚 Documentation Structure

### 🚀 Getting Started (`getting-started/`)
- [Installation](getting-started/installation.md) - System installation via `setup.sh`
- [Quick Start](quickstart.md) - Get started fast
- [AI Setup](getting-started/ai-setup.md) - Ollama model configuration (internal/external)
- [RAG Methods](rag-methods.md) - Retrieval-augmented generation methods
- [External Services Guide](external-services-guide.md) - Pointing at external backends

### 🏗️ Architecture (`architecture/`)
- [Overview](architecture/overview.md) - Platform architecture
- [Microservices](architecture/microservices.md) - Service structure
- [Plugin System](architecture/plugins.md) - Plugin architecture
- [Service Bundles](architecture/bundles.md) - Capability control-plane (enable/disable service groups)
- [Project Structure](architecture/project-structure.md) - Code organization
- [Roadmap](architecture/roadmap.md) - Future plans

### 💻 Development (`development/`)
- [Development Guide](development/development.md) - Development environment
- [Testing](development/testing.md) - Test strategies
- [Plugin Development](development/plugin-development.md) - Writing plugins
- [Code Style](development/code-style.md) - Coding standards

### 🚀 Deployment (`deployment/`)
- [Production Deployment](deployment/production.md) - Production deployment
- [Hardware Optimization](deployment/hardware-optimization.md) - Performance
- [Monitoring](deployment/monitoring.md) - Monitoring setup
- [Docker Upgrade Runbook](deployment/docker-upgrade-runbook.md) - Image version upgrades
- [Infrastructure Backup Strategy](deployment/infrastructure-backup-strategy.md) - Backup & restore

### 🔧 Operations (`operations/`)
- [Service Access Guide](operations/service-access.md) - Daily operations and service access
- [Security Architecture](operations/security-architecture.md) - Security model
- [PostgreSQL Migration Guide](operations/postgresql-migration-guide.md) - Database migrations

### 🔒 Security & Guides (`guides/`)
- [Authentication](guides/authentication.md) - Authelia SSO
- [Security Setup](guides/security-setup.md) - Security best practices
- [Performance Tuning](guides/performance.md) - Performance guidance

### 🐛 Troubleshooting (`troubleshooting/`)
- [Common Issues](troubleshooting/common-issues.md) - Common problems
- [Emergency Procedures](troubleshooting/emergency-procedures.md) - Crisis management

### 🔌 API Reference (`api/`)
- [API Documentation](api/reference.md) - Endpoints

---

## 🎯 Quick Navigation

### For Users
- Start here: [Installation Guide](getting-started/installation.md)
- Learn basics: [Quick Start](quickstart.md)
- Get help: [Troubleshooting](troubleshooting/common-issues.md)

### For Developers
- Setup dev environment: [Development Guide](development/development.md)
- Write plugins: [Plugin Development](development/plugin-development.md)
- Code standards: [Code Style](development/code-style.md)
- API docs: [API Reference](api/reference.md)

### For Operators
- Deploy to production: [Production Deployment](deployment/production.md)
- Daily operations: [Service Access Guide](operations/service-access.md)
- Monitor system: [Monitoring](deployment/monitoring.md)
- Security setup: [Security Setup](guides/security-setup.md)

---

## 📊 Current System Status

**Platform Version:** 1.0.0
**Services:** 31 containers defined; `setup.sh install` seeds the **standard** bundle profile (core + inference + rag + chat), monitoring/graph-rag/voice opt-in (`--profile full` = all 31); 3 have no healthcheck by design
**Environment:** Development (production hardening not yet applied)
**Host:** Raspberry Pi 4 (ARM)

---

**Last Updated:** 2026-07-17
**Language:** English
