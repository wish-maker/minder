# Development Documentation

Welcome to the Minder Platform development documentation. This section covers everything you need to know about contributing to and extending the platform.

## Quick Start

### Prerequisites
- Python 3.11+
- Docker 20.10+
- Docker Compose 2.20+
- Git
- VS Code or PyCharm (recommended)

### Setup Development Environment
```bash
# Clone repository
git clone https://github.com/your-org/minder.git
cd minder

# Start services
./setup.sh

# Run tests
pytest tests/unit/ -v
```

## Development Guides

### [Development Guide](development.md)
**Essential** - Complete development workflow.

Covers:
- Local development setup
- Service development
- Testing workflow
- Code quality tools
- Git workflow
- Best practices

### [Code Style Guide](code-style.md)
**Reference** - Coding standards and conventions.

Covers:
- PEP 8 compliance
- Type hints
- Documentation standards
- Naming conventions
- Code organization

### [Testing Guide](testing.md)
**Essential** - Testing practices and strategies.

Covers:
- Unit testing
- Integration testing
- Test coverage
- Performance testing
- CI/CD

### [Plugin Development](plugin-development.md)
**Advanced** - Building custom plugins.

Covers:
- Plugin architecture
- Plugin lifecycle
- API hooks
- Deployment
- Examples

## Architecture

### System Architecture
See [Architecture Documentation](../architecture/) for:
- High-level design
- Microservices architecture
- Service communication
- Data flow

### API Reference
See [API Documentation](../api/) for:
- Endpoint documentation
- Request/response formats
- Authentication
- Examples

## Development Workflow

### 1. Feature Development
```bash
# Create feature branch
git checkout -b feature/new-feature

# Make changes
# ... code changes ...

# Test changes
pytest tests/unit/ -v

# Commit changes
git add .
git commit -m "Add new feature"
```

### 2. Service Development
See [Development Guide](development.md#service-development) for:
- Adding new services
- Service templates
- Best practices

### 3. Testing
```bash
# Unit tests
pytest tests/unit/ -v

# Integration tests
pytest tests/integration/ -v

# With coverage
pytest tests/ --cov=src --cov-report=html
```

### 4. Code Quality
```bash
# Type checking
mypy src/

# Linting
ruff check src/

# Format code
ruff format src/
```

## Project Structure

```
minder/
├── services/           # Microservices
│   ├── api-gateway/
│   ├── plugin-registry/
│   └── ...
├── src/shared/        # Shared utilities
├── tests/             # Test suite
└── scripts/           # Utility scripts
```

See [Project Structure](../architecture/project-structure.md) for details.

## Contributing

We welcome contributions! Please:

1. Read [CONTRIBUTING.md](../../CONTRIBUTING.md)
2. Check [Code Style Guide](code-style.md)
3. Write tests for new features
4. Update documentation
5. Submit pull request

## Getting Help

- 📖 [Architecture Docs](../architecture/)
- 🔌 [API Reference](../api/)
- 🐛 [Troubleshooting](../troubleshooting/)
- 💬 [GitHub Discussions](https://github.com/your-org/minder/discussions)
