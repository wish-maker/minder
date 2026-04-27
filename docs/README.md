# 📚 Minder Platform Documentation

**Modular RAG platform with microservices architecture, plugin system, and real-time data collection.**

> **Status:** 72% Production Ready | **Version:** 2.0.0 | **Last Updated:** 2026-04-19

---

## 🚀 Quick Navigation

### For New Users
1. **[Getting Started](getting-started/QUICK_START.md)** - One-minute setup guide
2. **[API Reference](api/README.md)** - Interactive API documentation
3. **[Available Plugins](architecture/plugin-system.md)** - Built-in plugin list

### For Developers
1. **[Architecture Overview](architecture/README.md)** - System design and components
2. **[Plugin Development](development/PLUGIN_DEVELOPMENT.md)** - How to create plugins
3. **[Code Standards](development/CODE_STYLE_GUIDE.md)** - Coding conventions
4. **[Contributing](development/CONTRIBUTING.md)** - Contribution guidelines

### For Operators
1. **[Deployment Guide](deployment/README.md)** - Production deployment
2. **[Security Guide](guides/SECURITY_SETUP_GUIDE.md)** - Security configuration
3. **[Troubleshooting](troubleshooting/README.md)** - Common issues
4. **[Monitoring](deployment/monitoring.md)** - Prometheus + Grafana setup

---

## 📋 Documentation Structure

```
docs/
├── README.md (this file)                      # Documentation index
│
├── getting-started/                          # User guides for beginners
│   ├── QUICK_START.md                        # Quick start guide
│   └── installation.md                       # Detailed installation
│
├── guides/                                   # User-facing guides
│   ├── API_AUTHENTICATION_GUIDE.md           # JWT auth
│   ├── SECURITY_SETUP_GUIDE.md               # Security configuration
│   ├── OPENWEBUI_INTEGRATION_GUIDE.md        # AI integration
│   └── README.md                             # Guides index
│
├── api/                                      # API documentation
│   ├── README.md                             # API overview
│   ├── API_REFERENCE.md                      # Complete API docs
│   └── authentication/                       # Auth endpoints
│
├── architecture/                             # Architecture docs
│   ├── README.md                             # Architecture overview
│   ├── overview.md                           # System design
│   ├── plugin-system.md                      # Plugin architecture
│   ├── current-status.md                     # Current state
│   └── roadmap.md                            # Development roadmap
│
├── development/                              # Developer guides
│   ├── README.md                             # Dev guide index
│   ├── PLUGIN_DEVELOPMENT.md                 # Plugin development
│   ├── CODE_STYLE_GUIDE.md                   # Coding standards
│   └── CONTRIBUTING.md                       # Contribution guidelines
│
├── deployment/                               # Deployment guides
│   ├── README.md                             # Deployment overview
│   ├── DEPLOYMENT_GUIDE.md                   # Deployment guide
│   └── monitoring.md                         # Monitoring setup
│
├── troubleshooting/                          # Problem solving
│   ├── README.md                             # Troubleshooting index
│   ├── common-issues.md                      # Common problems
│   └── emergency-procedures.md               # Emergency procedures
│
├── references/                               # Reference materials
│   ├── README.md                             # Reference index
│   ├── ISSUES.md                             # Known issues
│   ├── sessions.md                           # Work session logs
│   └── test-reports/                         # Test reports
│       ├── system-test-2026-04-23.md
│       └── ...
│
└── test-results/                             # Test results (archived)
    ├── SYSTEM_TEST_2026_04_23.md
    └── ...

```

---

## 🎯 Finding What You Need

### I want to...

| Goal | Documentation |
|------|---------------|
| **Install and run Minder** | [Getting Started](getting-started/QUICK_START.md) |
| **Understand the system** | [Architecture Overview](architecture/README.md) |
| **Build a plugin** | [Plugin Development](development/PLUGIN_DEVELOPMENT.md) |
| **Deploy to production** | [Deployment Guide](deployment/README.md) |
| **Configure authentication** | [Security Guide](guides/SECURITY_SETUP_GUIDE.md) |
| **Check API endpoints** | [API Reference](api/README.md) |
| **Troubleshoot issues** | [Troubleshooting](troubleshooting/README.md) |
| **View current status** | [Current Status](architecture/current-status.md) |
| **Find known issues** | [Known Issues](references/ISSUES.md) |

---

## 📖 API Documentation

Interactive API documentation is available at:
- **Local:** http://localhost:8000/docs (after installation)
- **Online:** (to be added)

---

## 🔍 Recent Changes

### 2026-04-19
- ✅ Organized documentation into logical sections
- ✅ Created comprehensive navigation structure
- ✅ Created missing guides and indexes
- ✅ Organized test reports and references
- ✅ Added troubleshooting section

### 2026-04-23
- ✅ Added JWT Authentication documentation
- ✅ Added Security Setup Guide
- ✅ Created Plugin Development Guide
- ✅ Added Code Style Guide
- ✅ Completed API Reference
- ✅ Added Current Status and Roadmap

---

## 🤝 Contributing Documentation

We welcome documentation improvements! To contribute:

1. Check [CONTRIBUTING.md](development/CONTRIBUTING.md)
2. Follow [Code Style Guide](development/CODE_STYLE_GUIDE.md)
3. Update relevant documentation files
4. Add tests for new documentation
5. Submit a pull request

---

## 📞 Support

- **GitHub Issues:** https://github.com/wish-maker/minder/issues
- **Documentation:** /root/minder/docs/
- **Status Dashboard:** http://localhost:3000 (Grafana)

---

## 📝 License

This documentation is licensed under the MIT License.

---

**Made with ❤️ by the Minder Team**
