.PHONY: help setup up down logs check lint format typecheck test clean

help:  ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-10s %s\n", $$1, $$2}'

setup:  ## Install Python dependencies into .venv
	uv sync --all-extras

up:  ## Start the local stack (Floci, simulator, Prometheus, Grafana)
	docker compose up -d
	@echo "Floci:      http://localhost:4566"
	@echo "Simulator:  http://localhost:8000/v1"
	@echo "Prometheus: http://localhost:9090"
	@echo "Grafana:    http://localhost:3000"

down:  ## Stop the local stack
	docker compose down

logs:  ## Follow logs from all services
	docker compose logs -f

check: lint typecheck test  ## Run lint, type checks and tests

lint:  ## Lint and check formatting
	uv run ruff check .
	uv run ruff format --check .

format:  ## Auto-format code
	uv run ruff check --fix .
	uv run ruff format .

typecheck:  ## Static type checks
	uv run mypy

test:  ## Run tests
	uv run pytest

clean:  ## Remove local caches
	rm -rf .venv .pytest_cache .ruff_cache .mypy_cache
