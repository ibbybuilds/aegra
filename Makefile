.PHONY: help install dev-install setup-hooks format lint type-check security test test-api test-cli test-cov clean run ci-check

help:
	@echo "Available commands:"
	@echo "  make install       - Install production dependencies"
	@echo "  make dev-install   - Install all dependencies + git hooks"
	@echo "  make setup-hooks   - Reinstall git hooks (if needed)"
	@echo "  make format        - Format code with ruff"
	@echo "  make lint          - Lint code with ruff"
	@echo "  make type-check    - Run mypy type checking"
	@echo "  make security      - Run security checks with bandit"
	@echo "  make test          - Run all tests"
	@echo "  make test-api      - Run aegra-api tests only"
	@echo "  make test-cli      - Run aegra-cli tests only"
	@echo "  make test-cov      - Run tests with coverage"
	@echo "  make ci-check      - Run all CI checks locally"
	@echo "  make clean         - Clean cache files"
	@echo "  make run           - Run the server"

install:
	uv sync --all-packages --no-dev

dev-install:
	uv sync --all-packages
	@uv run pre-commit install
	@uv run pre-commit install --hook-type commit-msg
	@echo ""
	@echo "Done! Dependencies installed and git hooks set up."

setup-hooks:
	uv run pre-commit install
	uv run pre-commit install --hook-type commit-msg
	@echo ""
	@echo "Git hooks reinstalled!"

format:
	uv run ruff format .
	uv run ruff check --fix .

lint:
	uv run ruff check .

type-check:
	uv run mypy libs/aegra-api/src/ libs/aegra-cli/src/

security:
	uv run bandit -c pyproject.toml -r libs/aegra-api/src/ libs/aegra-cli/src/

test: test-api test-cli

test-api:
	uv run --package aegra-api pytest libs/aegra-api/tests/

test-cli:
	uv run --package aegra-cli pytest libs/aegra-cli/tests/

test-cov:
	uv run --package aegra-api pytest libs/aegra-api/tests/ --cov=libs/aegra-api/src --cov-report=html --cov-report=term
	uv run --package aegra-cli pytest libs/aegra-cli/tests/ --cov=libs/aegra-cli/src --cov-report=term

ci-check: format lint
	-uv run mypy libs/aegra-api/src/ libs/aegra-cli/src/
	-uv run bandit -c pyproject.toml -r libs/aegra-api/src/ libs/aegra-cli/src/
	$(MAKE) test
	@echo ""
	@echo "All CI checks completed! (mypy and bandit are non-blocking)"

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov 2>/dev/null || true

run:
	uv run --package aegra-api uvicorn aegra_api.main:app --reload
