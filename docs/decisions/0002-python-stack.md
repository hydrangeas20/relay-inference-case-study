# ADR-0002: Python for all first-party code

- **Status:** Accepted
- **Date:** 2026-09-27

## Context

The project needs a gateway, a queue worker, a load generator, evals and report generation. The target role strongly prefers Python, and the ML serving ecosystem (vLLM, eval tooling, plotting) is Python-first.

## Options considered

1. **Python throughout.** One language, matches the role and the ecosystem. The risk is a load generator that becomes the bottleneck at high request rates.
2. **Go load generator, Python elsewhere.** Faster client, but splits the codebase across two languages for one component.

## Decision

Python throughout: FastAPI for the gateway, `boto3` for the worker, `asyncio` + `httpx` for the load generator, Plotly for charts.

## Consequences

The load generator's own throughput has to be checked on every run. Methodology rule 4 makes a run invalid if achieved send rate falls short of intended or the generator's CPU saturates. If a single process can't keep up, the generator scales out to multiple processes before any other language is considered.
