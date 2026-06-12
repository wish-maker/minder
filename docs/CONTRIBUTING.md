# Contributing to Minder

Thank you for your interest in contributing to Minder! This document provides guidelines and instructions for contributing to the platform.

## 🤝 How to Contribute

### Reporting Issues

**Before Creating an Issue**
1. Search existing issues to avoid duplicates
2. Check if the issue is already fixed in the latest version
3. Gather necessary information (logs, error messages, steps to reproduce)

**Creating an Issue**
1. Go to [GitHub Issues](https://github.com/wish-maker/minder/issues)
2. Use appropriate issue template
3. Provide clear description and steps to reproduce
4. Include relevant logs and environment information

**Issue Types**
- **Bug Report**: Error or unexpected behavior
- **Feature Request**: New functionality or enhancement
- **Documentation**: Improvements to documentation
- **Performance**: Performance-related issues
- **Security**: Security vulnerabilities (see Security section)

### Submitting Pull Requests

**Workflow**
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Write/update tests
5. Update documentation
6. Submit pull request

**Branch Naming**
```
feature/       - New features
bugfix/        - Bug fixes
hotfix/        - Critical bug fixes
refactor/      - Code refactoring
docs/          - Documentation changes
test/          - Test additions/updates
```

**Example Branch Names**
```
feature/plugin-marketplace
bugfix/rag-pipeline-memory-leak
docs/api-documentation-update
refactor/unified-error-handling
```

**Pull Request Process**
1. Update your branch with latest main
   ```bash
   git checkout main
   git pull origin main
   git checkout your-branch
   git rebase main
   ```

2. Ensure all tests pass
   ```bash
   docker compose -f docker-compose.test.yml run --rm pytest
   ```

3. Commit your changes
   ```bash
   git add .
   git commit -m "type: description"
   ```

4. Push to your fork
   ```bash
   git push origin your-branch
   ```

5. Create pull request on GitHub
   - Fill PR template completely
   - Link related issues
   - Request review from maintainers

## 📝 Code Standards

### Python Code Style

**Formatting**
- Use **Black** for code formatting
- Maximum line length: 100 characters
- Use **isort** for import sorting
- Follow PEP 8 guidelines

```bash
# Format code
black services/

# Sort imports
isort services/

# Check formatting
black --check services/
```

**Linting**
```bash
# Run linting
pylint services/

# Type checking
mypy services/
```

### Code Quality Standards

**Naming Conventions**
```python
# Variables and functions: snake_case
user_name = "John"
def calculate_metrics():

# Classes: PascalCase
class PluginManager:

# Constants: UPPER_SNAKE_CASE
MAX_RETRIES = 3
DEFAULT_TIMEOUT = 30

# Private members: single underscore
_internal_method = None
```

**Docstrings**
```python
def process_document(file_path: str, metadata: dict) -> dict:
    """
    Process a document for RAG ingestion.

    Args:
        file_path: Path to the document file
        metadata: Additional metadata for the document

    Returns:
        dict: Processing result with document ID and chunks

    Raises:
        ValueError: If file format is not supported
        IOError: If file cannot be read

    Example:
        >>> result = process_document("doc.pdf", {"author": "John"})
        >>> print(result["document_id"])
        'abc123'
    """
    pass
```

**Type Hints**
```python
from typing import List, Dict, Optional
from pydantic import BaseModel

class QueryRequest(BaseModel):
    """Request model for RAG queries."""
    query: str
    max_results: int = 5
    filters: Optional[Dict[str, str]] = None

def search_documents(query: str) -> List[Dict[str, str]]:
    """Search documents by query."""
    return []
```

### Error Handling

**Standardized Error Responses**
```python
from fastapi import HTTPException
from services.shared.errors import (
    ValidationError,
    NotFoundError,
    AuthenticationError
)

# Raise specific errors
raise ValidationError(
    field="email",
    message="Invalid email format"
)

raise NotFoundError(
    resource="plugin",
    id="plugin-123"
)

# In FastAPI routes
@router.get("/plugins/{plugin_id}")
async def get_plugin(plugin_id: str):
    if not plugin_exists(plugin_id):
        raise HTTPException(
            status_code=404,
            detail=f"Plugin {plugin_id} not found"
        )
    return plugin
```

**Logging Standards**
```python
import logging
from services.shared.logging import configure_logging

logger = logging.getLogger(__name__)

# Use appropriate log levels
logger.debug("Detailed debug information")
logger.info("Normal operation message")
logger.warning("Warning about potential issue")
logger.error("Error occurred", exc_info=True)
logger.critical("Critical system failure")

# Include context
logger.info("Processing document", doc_id="123", user_id="456")
```

## 🧪 Testing Standards

### Test Coverage

**Required Coverage**
- New code: **90%+** coverage
- Critical paths: **100%** coverage
- Existing code: Maintain or improve current coverage

**Running Tests**
```bash
# Run all tests
docker compose -f docker-compose.test.yml run --rm pytest

# Run specific test file
pytest tests/test_rag_pipeline.py

# Run with coverage
pytest --cov=services --cov-report=html

# View coverage report
open htmlcov/index.html
```

### Test Structure

**Test Organization**
```
tests/
├── unit/              # Unit tests
│   ├── test_api_gateway.py
│   ├── test_rag_pipeline.py
│   └── test_plugins.py
├── integration/       # Integration tests
│   ├── test_database.py
│   ├── test_redis.py
│   └── test_rabbitmq.py
└── e2e/              # End-to-end tests
    ├── test_document_flow.py
    └── test_plugin_lifecycle.py
```

**Test Example**
```python
import pytest
from httpx import AsyncClient
from services.api_gateway.main import app

@pytest.mark.asyncio
async def test_create_knowledge_base():
    """Test creating a knowledge base."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/knowledge-base",
            json={
                "name": "Test KB",
                "description": "Test knowledge base"
            },
            headers={"Authorization": "Bearer test-token"}
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test KB"
        assert "id" in data
```

### Test Best Practices

**Do's**
- Write tests before code (TDD when possible)
- Test edge cases and error conditions
- Use fixtures for common test data
- Mock external dependencies
- Keep tests independent and isolated
- Use descriptive test names

**Don'ts**
- Don't test implementation details
- Don't write fragile tests
- Don't ignore flaky tests
- Don't use production data
- Don't commit failing tests

## 📚 Documentation Standards

### Code Documentation

**README Requirements**
Each service should have:
- Purpose and functionality
- API endpoints
- Configuration options
- Environment variables
- Usage examples

**API Documentation**
- Use OpenAPI/Swagger for FastAPI
- Document all endpoints
- Include request/response examples
- Document authentication requirements
- Provide error response examples

### Documentation Updates

When contributing:
1. Update relevant documentation
2. Add examples for new features
3. Update API docs for API changes
4. Add migration guides for breaking changes
5. Update diagrams for architecture changes

## 🔒 Security

### Reporting Vulnerabilities

**For Security Issues**
- Do **NOT** create public issues
- Email: security@minder-platform.org
- Include details and reproduction steps
- Wait for confirmation before disclosing

**Security Best Practices**
- Never commit secrets or credentials
- Validate all user inputs
- Use parameterized queries
- Sanitize output
- Follow principle of least privilege
- Keep dependencies updated

### Code Review for Security

**Checklist**
- [ ] No hardcoded secrets
- [ ] Input validation on all endpoints
- [ ] SQL injection protection
- [ ] XSS protection
- [ ] CSRF protection
- [ ] Proper authentication/authorization
- [ ] Secure error messages (no sensitive data)

## 📋 Commit Messages

### Commit Message Format

```
type(scope): subject

body

footer
```

**Types**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Test additions/updates
- `chore`: Maintenance tasks
- `perf`: Performance improvements
- `ci`: CI/CD changes

**Examples**
```
feat(rag-pipeline): add PDF ingestion support

Implement PDF parsing and chunking for document ingestion.
Extracts text, metadata, and creates semantic chunks.

Closes #123

---

bugfix(api-gateway): fix rate limiting for authenticated users

Rate limiting was not correctly handling authenticated users,
causing all requests to be counted against a single limit.

Fixes #145
```

## 🎯 Development Workflow

### Setting Up Development Environment

```bash
# Clone repository
git clone https://github.com/wish-maker/minder.git
cd minder

# Create development branch
git checkout -b feature/your-feature

# Start development services
docker compose -f docker-compose.dev.yml up -d

# Install development dependencies
pip install -r requirements-dev.txt

# Run tests
pytest
```

### Pre-commit Hooks

Install pre-commit hooks:
```bash
pip install pre-commit
pre-commit install
```

Pre-commit will run:
- Black formatting
- isort import sorting
- pylint linting
- mypy type checking
- trailing whitespace check

### Development Commands

```bash
# Format code
black services/

# Sort imports
isort services/

# Run linting
pylint services/

# Type checking
mypy services/

# Run tests
pytest

# Run tests with coverage
pytest --cov=services
```

## 📊 Pull Request Review

### Review Criteria

**Code Quality**
- Follows coding standards
- Adequate test coverage
- No security issues
- Good documentation
- Performance considerations

**Functionality**
- Solves the intended problem
- No regressions
- Edge cases handled
- Error handling appropriate

**Documentation**
- Updated README files
- API docs updated
- Examples provided
- Migration guide (if breaking)

### Review Process

1. **Automated Checks**
   - All tests pass
   - Coverage threshold met
   - Linting passes
   - Type checking passes

2. **Peer Review**
   - At least one maintainer approval
   - All feedback addressed
   - No unresolved conflicts

3. **Integration Tests**
   - Run in development environment
   - Test with real data
   - Performance testing

4. **Final Approval**
   - Maintainer approves
   - Ready to merge

## 🏷️ License

By contributing, you agree that your contributions will be licensed under the **MIT License**.

## 📞 Getting Help

### Resources

- **Documentation**: [docs/README.md](docs/README.md)
- **Architecture Guide**: [docs/architecture/README.md](docs/architecture/README.md)
- **API Documentation**: [docs/guides/api.md](docs/guides/api.md)

### Communication

- **GitHub Issues**: For bugs and feature requests
- **GitHub Discussions**: For questions and ideas
- **Email**: maintainers@minder-platform.org

## 🙏 Recognition

Contributors will be:
- Listed in CONTRIBUTORS.md
- Mentioned in release notes
- Recognized in significant features

---

**Thank you for contributing to Minder!** 🎉

Every contribution, no matter how small, helps make Minder better for everyone.

---

**Last Updated:** 2026-06-11  
**Maintainer:** Minder Platform Team
