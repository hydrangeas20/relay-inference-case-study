# Client brief: Relay

> Relay is fictional. The traffic patterns, workloads and failure modes are modelled on what AI products at this scale commonly run into.

## The company

Relay is an AI coding assistant, a Series B startup that's scaling quickly.

- **Users:** 2M registered, about 400K daily active.
- **Geography:** concentrated in North America and Europe. Traffic peaks on weekday mornings as time zones come online and is close to idle overnight.
- **Stack:** Relay's application runs on AWS. Model inference runs on dedicated GPU deployments behind an OpenAI-compatible API.

## Why they're engaging us

- Relay launches a **team plan in six weeks**, which is expected to **double traffic**.
- The current deployment is **already missing latency targets** at peak.
- The **GPU bill is Relay's second-largest expense** after payroll, and it's growing faster than revenue.

## Engagement goal

Hit the SLOs below at launch-scale traffic, cut cost per request by **at least 50%**, and show **no measurable drop in quality**.

## Workloads

### 1. Inline completions
- **What:** code suggestions as the user types.
- **Model:** fine-tuned ~7B open-weight code model.
- **Shape:** very high request volume, short outputs (tens of tokens), long prompts (system prompt plus surrounding code, often thousands of tokens).
- **What matters:** time to first token. Users feel every millisecond, and a slow suggestion is a useless one.

### 2. Agent chat
- **What:** answers questions about the user's codebase and calls tools (search repo, read file, run tests) through JSON tool calls.
- **Model:** the same base model as completions.
- **Shape:** lower volume, longer outputs, multi-turn.
- **What matters:** valid structured output (a malformed tool call breaks the whole turn) and end-to-end latency.

### 3. Repo indexing
- **What:** nightly embedding of users' repositories for retrieval.
- **Model:** small open-weight embedding model.
- **Shape:** large batch jobs arriving through a queue.
- **What matters:** throughput and cost. Latency is irrelevant, as long as the job finishes before the morning peak.

> Specific model choices are made in Phase 3 and recorded as an ADR, based on the current best open-weight options at the time.

## SLOs

| SLO | Target | Measured on |
|---|---|---|
| Completions p95 TTFT at peak | < 300 ms | Real GPU (per-GPU), simulator (at scale) |
| Agent chat invalid tool-call rate at peak concurrency | < 0.5% | Real GPU |
| Nightly indexing | Done before 06:00 ET, no interactive impact | Simulator + Floci |
| Completion quality | Within 1 point of FP16 baseline | Real GPU |
| Cost per 1K requests at launch-scale traffic | ≥ 50% reduction | Capacity model |

These are initial targets. Once the baseline has been measured, they'll be revised if needed, and the revision will be recorded as a decision. Agreeing on realistic targets with the customer is part of the job.

## Out of scope

- Training or fine-tuning the models. Relay supplies its model; this engagement is about serving it.
- Relay's application code outside the inference path.
- Multi-region deployment.
