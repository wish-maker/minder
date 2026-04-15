# Minder CI/CD Pipeline

## Overview

This repository uses GitHub Actions for continuous integration and deployment.

## Workflows

### 1. Test Workflow (`.github/workflows/test.yml`)

**Triggers**: Push to main/develop, Pull Requests

**Jobs**:
- **Unit Tests**: Runs all pytest tests
- **Code Coverage**: Generates coverage reports
- **Linting**: Python code quality checks
- **Security Scan**: Bandit security analysis
- **Vulnerability Scan**: Safety dependency checks

### 2. Build Workflow

**Triggers**: Push to main branch (after tests pass)

**Jobs**:
- **Docker Build**: Builds container image
- **Image Push**: Pushes to Docker Hub
- **Security Scan**: Trivy vulnerability scanner

### 3. Deploy Workflow

**Triggers**: Successful build on main branch

**Jobs**:
- **Production Deployment**: Deploys to production environment
- **Notifications**: Sends deployment status notifications

## Setup Required

### GitHub Secrets

Configure these secrets in your repository settings:

```
DOCKER_USERNAME=your_dockerhub_username
DOCKER_PASSWORD=your_dockerhub_token
```

### Docker Hub

1. Create account at https://hub.docker.com
2. Create repository `minderproject/minder-api`
3. Generate access token
4. Add token to GitHub Secrets

## Local Testing

Test CI/CD pipeline locally:

```bash
# Run tests
pytest tests/ -v --cov=.

# Run linting
flake8 . --count --show-source --statistics

# Security scan
pip install bandit
bandit -r api/ -f json

# Vulnerability scan
pip install safety
safety check
```

## Monitoring

- **Test Results**: GitHub Actions tab
- **Coverage Reports**: Codecov
- **Security Reports: Actions artifacts
- **Deployment Logs**: Workflow runs

## Troubleshooting

**Tests failing locally?**
```bash
pip install -r requirements.txt
pytest tests/ -v
```

**Docker build failing?**
```bash
docker build -t minder-api:test .
```

**Deployment issues?**
Check workflow logs in GitHub Actions tab.
