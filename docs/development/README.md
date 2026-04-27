# 💻 Development Guide

Comprehensive guide for developers working on the Minder Platform.

---

## 📖 Documentation Structure

### Core Guides
- **[Plugin Development](PLUGIN_DEVELOPMENT.md)** - How to create custom plugins
- **[Code Style Guide](CODE_STYLE_GUIDE.md)** - Coding conventions and standards
- **[Contributing](CONTRIBUTING.md)** - Contribution guidelines and process

### Architecture
- **[Architecture Overview](../architecture/README.md)** - System design
- **[Plugin System](../architecture/plugin-system.md)** - Plugin architecture details

### Testing
- **[Test Guide](../test-reports/README.md)** - Testing procedures

---

## 🚀 Getting Started

### Prerequisites
- Docker 24.0+
- Docker Compose 2.20+
- Python 3.11+
- Git 2.30+

### Setup
```bash
git clone https://github.com/wish-maker/minder.git
cd minder
./install.sh
```

---

## 📝 Plugin Development

**[Plugin Development Guide](PLUGIN_DEVELOPMENT.md)** covers:
- Plugin structure and requirements
- Module interface implementation
- Data collection and analysis
- Plugin configuration
- Testing and deployment

---

## 🎯 Contribution Workflow

1. **Fork and Clone**
   ```bash
   git clone https://github.com/your-username/minder.git
   cd minder
   ```

2. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Make Changes**
   - Follow [Code Style Guide](CODE_STYLE_GUIDE.md)
   - Write tests for new features
   - Update documentation

4. **Test Locally**
   ```bash
   docker compose up -d
   docker compose logs -f
   ```

5. **Commit and Push**
   ```bash
   git add .
   git commit -m "feat: description of changes"
   git push origin your-branch
   ```

6. **Create Pull Request**
   - Follow [Contributing Guidelines](CONTRIBUTING.md)
   - Reference related issues

---

## 📚 Related Documentation

- **[Architecture](../architecture/README.md)** - System design and components
- **[API Reference](../api/README.md)** - API documentation
- **[Deployment](../deployment/README.md)** - Production deployment

---

## 🤝 Getting Help

- **GitHub Issues:** https://github.com/wish-maker/minder/issues
- **Discord:** (to be added)
- **Documentation:** /root/minder/docs/

---

**Last Updated:** 2026-04-19
