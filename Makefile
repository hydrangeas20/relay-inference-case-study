.PHONY: help setup corpus trace traffic-check up down logs run check lint format typecheck test clean rly4-traces rly4-model rly4-run rly4-report

TRACE ?= traces/smoke.jsonl

help:  ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-10s %s\n", $$1, $$2}'

setup:  ## Install Python deps and build the code corpus
	uv sync --all-extras
	$(MAKE) corpus

corpus:  ## Fetch the pinned repos into data/corpus (verifies licenses and hashes)
	uv run relay-corpus

trace:  ## Regenerate the smoke trace (30 s at 4 rps, seed 1)
	uv run relay-trace constant --duration 30 --rate 4 --seed 1 --out traces/smoke.jsonl

traffic-check:  ## Check the traffic model against the Azure reference data
	uv run python -m relay.traffic.report

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

# --- RLY-4: prefix caching on a real llama.cpp server (CPU). See tickets/rly-4-prefix-caching.
RLY4_TRACE_ARGS = --sessions 8 --per-session 6 --rate 0.25 --max-tokens 8 --first-cursor 6000 --seed 4

rly4-traces:  ## Regenerate the RLY-4 session traces (shared + independent control)
	uv run relay-trace-sessions $(RLY4_TRACE_ARGS) --out traces/rly4-shared.jsonl
	uv run relay-trace-sessions $(RLY4_TRACE_ARGS) --independent --out traces/rly4-independent.jsonl

rly4-model:  ## Build the synthetic-weight Qwen2 test model (needs LLAMA_CPP=<llama.cpp checkout>)
	PYTHONPATH=$(LLAMA_CPP)/gguf-py uv run python tickets/rly-4-prefix-caching/make_model.py \
		--vocab $(LLAMA_CPP)/models/ggml-vocab-qwen2.gguf --out models/relay-rly4-qwen2-synthetic.gguf

rly4-run:  ## Run the RLY-4 experiment (needs LLAMA_SERVER=<llama-server binary>); REPS=3
	tickets/rly-4-prefix-caching/run_experiment.sh $(or $(REPS),3)

rly4-report:  ## Summarize RLY-4 results into results/rly-4/report.{json,md}
	uv run python tickets/rly-4-prefix-caching/analyze.py results/rly-4
