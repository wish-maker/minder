#!/bin/bash
# scripts/setup-pre-commit.sh

echo "🔧 Setting up pre-commit hooks..."

# Install pre-commit
pip install pre-commit

# Install hooks
pre-commit install

# Run initial check
echo "🏃 Running initial pre-commit check..."
pre-commit run --all-files

echo "✅ Pre-commit hooks installed successfully!"
echo "📝 Hooks will run automatically on: git commit"
