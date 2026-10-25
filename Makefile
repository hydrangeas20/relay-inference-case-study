.PHONY: help setup corpus trace up down logs run check lint format typecheck test clean

TRACE ?= traces/smoke.jsonl

help:  ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-10s %s\n", $$1, $$2}'

setup:  ## Install Python deps and build the code corpus
	uv sync --all-extras
	$(MAKE) corpus

corpus:  ## Fetch the pinned repos into data/corpus (verifies licenses and hashes)
	uv run relay-corpus

trace:  ## Regenerate the smoke trace (30 s at 4 rps, seed 1)
	uv run relay-trace --out traces/smoke.jsonl --duration 30 --rate 4 --seed 1

up:  ## Start the local stack
	docker compose up -d --build
	@echo "Floci:      http://localhost:4566"
	@echo "Simulator:  http://localhost:8000/v1"
	@echo "Gateway:    http://localhost:8080"
	@echo "Prometheus: http://localhost:9090"
	@echo "Grafana:    http://localhost:3000"

down:  ## Stop the local stack
	docker compose down

logs:  ## Follow logs from all services
	docker compose logs -f

run:  ## Replay a trace against the stack: make run TRACE=traces/smoke.jsonl
	docker compose run --rm loadgen relay-loadgen --trace $(TRACE)

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
