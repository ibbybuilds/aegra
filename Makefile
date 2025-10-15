.PHONY: help install dev-install setup-hooks format lint type-check security test test-cov clean run ci-check

help:
	@echo "Available commands:"
	@echo "  make install       - Install production dependencies"
	@echo "  make dev-install   - Install dev dependencies + git hooks"
	@echo "  make setup-hooks   - Reinstall git hooks (if needed)"
	@echo "  make format        - Format code with ruff"
	@echo "  make lint          - Lint code with ruff"
	@echo "  make type-check    - Run mypy type checking"
	@echo "  make security      - Run security checks with bandit"
	@echo "  make test          - Run tests"
	@echo "  make test-cov      - Run tests with coverage"
	@echo "  make ci-check      - Run all CI checks locally"
	@echo "  make clean         - Clean cache files"

install:
	uv sync --no-dev

dev-install:
	uv sync
	@uv run pre-commit install
	@uv run pre-commit install --hook-type commit-msg
	@echo ""
	@echo "✅ Dependencies installed!"
	@echo "✅ Git hooks installed!"
	@echo "🚀 You're ready to develop!"

setup-hooks:
	uv run pre-commit install
	uv run pre-commit install --hook-type commit-msg
	@echo ""
	@echo "✅ Git hooks reinstalled!"
	@echo "📝 Your commits will now be checked automatically"

format:
	uv run ruff format .
	uv run ruff check --fix .

lint:
	uv run ruff check .

type-check:
	uv run mypy src/

security:
	uv run bandit -c pyproject.toml -r src/

test:
	uv run pytest

test-cov:
	uv run pytest --cov=src --cov-report=html --cov-report=term

ci-check: format lint type-check security test
	@echo ""
	@echo "✅ All CI checks passed!"

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov 2>/dev/null || true
