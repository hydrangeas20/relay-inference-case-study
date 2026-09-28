# Instructions for coding agents

AI coding agents may be used to accelerate implementation, but the engineer owns the system and its conclusions. These rules apply to every change.

## Engineering ownership

Your job is increasingly becoming less “type every line yourself” and more “understand the system well enough to specify, evaluate, debug, modify, and take responsibility for the code.”

That is especially true for forward-deployed and AI engineering work. Agents can write code, generate tests, add instrumentation, refactor implementations, and automate repetitive work. They must not replace the engineering reasoning this case study is designed to demonstrate.

The human engineer owns:

- problem decomposition and requirements;
- hypotheses and experimental design;
- architectural and technical decisions;
- interpretation of telemetry and experimental results;
- review and understanding of agent-generated changes;
- validation, trade-offs, and final technical conclusions.

Do not outsource incident diagnosis to an agent. Use the agent as an implementation accelerator inside a human-led investigation.

### Example workflow

Suppose RLY-3 shows TTFT deteriorating under concurrency:

1. The engineer inspects the metrics and observes that queueing begins around concurrency 40.
2. The engineer forms a hypothesis about batching or scheduling behavior.
3. The agent may implement additional instrumentation or a controlled configuration experiment requested by the engineer.
4. The engineer reviews the diff and must understand what changed and why before running it.
5. The engineer runs the experiment and interprets the evidence.
6. If the hypothesis is incomplete, the engineer revises it—for example, by investigating KV-cache pressure.
7. The agent may implement the next targeted experiment or instrumentation change.
8. The engineer reviews, tests, compares results, and reaches the final conclusion.

The standard is not “did a human manually type the code?” The standard is: **can the engineer explain, review, debug, modify, test, and defend the important code and every material technical decision?**

## Before writing code

1. Read the ticket's `README.md` in `tickets/`. Its **acceptance criteria are the spec**. If a criterion is ambiguous or seems wrong, stop and ask rather than guessing.
2. Read [`docs/methodology.md`](docs/methodology.md). Measurement code that breaks a methodology rule is wrong even if it runs.
3. If the change involves a real design choice (a library, a data format, an algorithm, a tradeoff), propose it as an ADR in `docs/decisions/` using the template, and wait for approval.

## Writing code

- Python 3.11+, type-annotated, passing `make check` (ruff, mypy strict, pytest).
- Shared code goes in `src/relay/`. Ticket-specific experiment scripts go in that ticket's folder.
- Configuration comes from environment variables via `pydantic-settings`. No hard-coded endpoints, credentials or model names.
- The inference endpoint is always `INFERENCE_BASE_URL`. Never write code that only works against the real GPU or only against the simulator.
- AWS clients take their endpoint from `AWS_ENDPOINT_URL` so they work against Floci and real AWS unchanged.
- Keep it simple. Prefer the standard library and existing dependencies. Adding a dependency requires a reason in the PR.

## Measurements

- Every experiment writes its results to `results/` in the Phase 2 schema, including the `source` tag (`gpu`, `sim`, `projection`, `floci`).
- Load generation is open-loop and self-checking (methodology rule 4). Never report results from a run that failed its self-check.
- Before/after comparisons replay the same traffic trace with the same seed.
- Never invent, round optimistically, or hand-edit a result. If a run fails, report the failure.

## Tests

- Unit tests for logic (traffic generation, statistics, schema validation, cost calculations).
- Statistical code (percentiles, confidence intervals) is tested against known inputs.
- Tests must not need a GPU, network access or running containers. Integration tests that need the Docker stack are marked `@pytest.mark.integration`.

## Pull requests

- One ticket, or one clearly scoped piece of a ticket, per PR.
- Fill in the PR template, including which acceptance criteria this PR satisfies.
- Explain anything a reviewer would need to defend in an interview: why this approach, what the alternatives were, and what could make the result misleading.
