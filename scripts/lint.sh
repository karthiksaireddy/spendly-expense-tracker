#!/bin/bash
# Lint script: Run black and flake8 on Python files
# This can be used as a pre-commit hook or run manually

set -e

echo "Running black (code formatter)..."
black app.py database/ tests/ skills/ mcp/ --check --diff || {
    echo "❌ Black found formatting issues. Run 'black app.py database/ tests/ skills/ mcp/' to auto-fix."
    exit 1
}

echo "✅ Black formatting check passed."

echo "Running flake8 (linter)..."
flake8 app.py database/ tests/ skills/ mcp/ --max-line-length=88 --extend-ignore=E203,W503 || {
    echo "❌ Flake8 found linting issues."
    exit 1
}

echo "✅ Flake8 linting check passed."

echo "All linting checks passed! ✅"
