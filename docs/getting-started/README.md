# Getting Started with Minder Platform

Welcome to Minder Platform! This section helps you get up and running quickly.

## Guides

### [Quick Start](quick-start.md)
**5 minutes** - Get Minder Platform running in minutes with a single command.

Perfect for:
- First-time users
- Quick evaluation
- Local development setup

### [Installation Guide](installation.md)
**15 minutes** - Detailed installation with all configuration options.

Covers:
- System requirements
- Prerequisites
- Step-by-step installation
- Environment configuration
- Verification steps

## What You'll Need

**Minimum Requirements:**
- Docker 20.10+
- Docker Compose 2.20+
- 8GB RAM (16GB recommended)
- 20GB free disk space

**Recommended for Production:**
- 16GB+ RAM
- 4 CPU cores
- 100GB+ SSD storage
- Stable internet connection

## Installation Methods

### Method 1: Automated (Recommended)
```bash
git clone https://github.com/wish-maker/minder.git
cd minder
./setup.sh
```

### Method 2: Manual
See [Installation Guide](installation.md) for detailed manual setup.

## Next Steps

After installation:

1. **Verify Setup**: Check service health
   ```bash
   ./scripts/health-check.sh
   ```

2. **Configure Security**: Change default passwords
   - See [Authentication Guide](../guides/authentication.md)

3. **Explore APIs**: Test the endpoints
   - API Gateway: http://localhost:8000
   - Plugin Registry: http://localhost:8001

4. **Read Documentation**: Explore other guides
   - [Development](../development/)
   - [Deployment](../deployment/)

## Troubleshooting

Having issues? Check:

- [Common Issues](../troubleshooting/common-issues.md)
- [Installation Troubleshooting](../troubleshooting/common-issues.md#installation)

## Getting Help

- 📧 Email: support@minder-platform.com
- 🐛 Issues: [GitHub Issues](https://github.com/wish-maker/minder/issues)
- 💬 Discussions: [GitHub Discussions](https://github.com/wish-maker/minder/discussions)
