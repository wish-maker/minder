# Contributing to Minder

Thank you for your interest in contributing to Minder! This document provides guidelines and instructions for contributing.

## Code of Conduct

- Be respectful and inclusive
- Provide constructive feedback
- Focus on what is best for the community
- Show empathy towards other community members

## How to Contribute

### Reporting Bugs

Before creating bug reports, please check existing issues to avoid duplicates. When creating a bug report, include:

- **Title**: Clear and descriptive
- **Description**: Detailed explanation of the problem
- **Reproduction Steps**: Steps to reproduce the issue
- **Expected Behavior**: What you expected to happen
- **Actual Behavior**: What actually happened
- **Environment**: OS, Python version, dependencies
- **Logs**: Relevant error messages or logs

### Suggesting Enhancements

Enhancement suggestions are tracked as GitHub issues. When suggesting an enhancement:

- Use a clear and descriptive title
- Provide a detailed description of the suggested enhancement
- Explain why this enhancement would be useful
- List some examples of how this feature would be used

### Pull Requests

1. **Fork the repository** and create your branch from `main`
2. **Make your changes** with clear commit messages
3. **Write tests** for new functionality
4. **Ensure all tests pass**: `pytest tests/`
5. **Update documentation** as needed
6. **Submit a pull request** with a clear description

#### Development Setup

```bash
# Clone your fork
git clone https://github.com/yourusername/minder.git
cd minder

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run tests
pytest tests/ -v

# Start development server
docker-compose up -d
```

#### Coding Standards

- Follow PEP 8 style guidelines
- Write docstrings for functions and classes
- Keep functions focused and modular
- Add type hints where appropriate
- Write tests for new features (aim for >80% coverage)

#### Commit Message Format

```
type(scope): subject

body

footer
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

Example:
```
feat(auth): add OAuth2 authentication

Implement OAuth2 authentication flow with support for
Google and GitHub providers.

Closes #123
```

### Plugin Development

Minder's plugin system allows developers to extend functionality:

1. **Create Plugin Structure**:
```bash
mkdir plugins/my-plugin
cd plugins/my-plugin
```

2. **Implement BaseModule**:
```python
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
        # Implementation
        pass
```

3. **Test Your Plugin**:
```bash
pytest tests/test_my_plugin.py -v
```

4. **Submit for Review**:
- Fork the repository
- Create a feature branch
- Make your changes
- Submit a pull request

See [PLUGIN_DEVELOPMENT.md](docs/PLUGIN_DEVELOPMENT.md) for detailed plugin development guide.

## Testing

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_auth.py -v

# Run with coverage
pytest tests/ --cov=. --cov-report=html
```

### Test Structure

- `tests/test_auth.py`: Authentication tests
- `tests/test_security.py`: Security middleware tests
- `tests/test_plugin_store.py`: Plugin system tests
- `tests/test_*_simple.py`: Simplified test versions

## Documentation

### Improving Documentation

Documentation is crucial for project success. When improving docs:

- Keep language clear and concise
- Include code examples
- Update diagrams if needed
- Follow existing documentation style

### Documentation Files

- `README.md`: Project overview and quick start
- `docs/ARCHITECTURE.md`: System architecture
- `docs/PLUGIN_DEVELOPMENT.md`: Plugin development guide
- `docs/MODULE_MANAGEMENT.md`: Module management

## Getting Help

- **GitHub Issues**: For bugs and feature requests
- **GitHub Discussions**: For questions and ideas
- **Documentation**: Check docs/ folder first

## License

By contributing to Minder, you agree that your contributions will be licensed under the MIT License.

## Recognition

Contributors will be recognized in the CONTRIBUTORS.md file. Thank you for your contributions!

---

**Happy Contributing! 🚀**
