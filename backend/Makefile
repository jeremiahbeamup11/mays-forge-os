# Mays Forge OS — Backend Makefile
#
# Common development commands. Run `make help` to see all available targets.
# Note: Makefiles require TABS for indentation, not spaces. If you edit this
# and commands stop working, check your editor isn't converting tabs to spaces.

.PHONY: help install dev test test-watch lint format typecheck check clean

# Default target — run when you just type `make`
help:
	@echo ""
	@echo "  Mays Forge OS Backend — Available Commands"
	@echo "  =========================================="
	@echo ""
	@echo "  make install      Install/sync dependencies from pyproject.toml"
	@echo "  make dev          Run the development server with auto-reload"
	@echo "  make test         Run the test suite"
	@echo "  make test-watch   Run tests in watch mode (reruns on file changes)"
	@echo "  make lint         Run ruff linter"
	@echo "  make format       Run ruff formatter"
	@echo "  make typecheck    Run mypy type checker"
	@echo "  make check        Run all checks (lint + format + typecheck + test)"
	@echo "  make clean        Remove caches and build artifacts"
	@echo ""

install:
	uv sync --all-groups

dev:
	uv run uvicorn app.main:app --reload

test:
	uv run pytest -v

test-watch:
	uv run pytest -v --looponfail

lint:
	uv run ruff check app tests

format:
	uv run ruff format app tests

typecheck:
	uv run mypy app

check: lint format typecheck test
	@echo ""
	@echo "  ✓ All checks passed."
	@echo ""

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
	@echo "Cleaned caches and build artifacts."
