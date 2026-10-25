# ADR-0007: A real engine on CPU for RLY-4, and how Relay's request header leaves the prompt

- **Status:** Proposed. Implemented in the RLY-4 PR for the engineer's review; the decisions below are open to reversal before merge.
- **Date:** 2026-10-25

## Context

RLY-4 asks why enabling prefix caching didn't lower Relay's time to first token (TTFT). Answering it needs a backend that really caches: one that keeps KV state from earlier prompts and skips prefill for a matching prefix.

What was available:

- **No GPU.** The sandbox has 2 CPU cores and 7 GB RAM.
- **No Docker images.** Docker Hub and GHCR are unreachable.
- **No pretrained weights.** Hugging Face is blocked.
- **The simulator doesn't cache.** In llm-d-inference-sim v0.9.0, a nonzero `time-to-first-token` makes it ignore `prefill-time-per-token`, so TTFT doesn't depend on prompt length. Its prefix-cache flag is ignored unless `--enable-kvcache` is set, and that needs a tokenizer sidecar.

A simulator result for RLY-4 would only show the simulator's latency model. It wouldn't be evidence about caching.

## Decisions

### 1. Engine: llama.cpp `llama-server` on CPU, tagged `cpu`

- Built from source at a recorded commit. The run manifest records the build string from the server's `/props`.
- It is a real inference engine with a real prefix cache:
  - Each slot keeps the KV state of its last prompt.
  - A new prompt reuses the longest matching token prefix.
  - Every response reports `cache_n` (tokens reused) and `prompt_n` (tokens evaluated).
  - Its Prometheus counters report the same totals.
- Results get a new source tag, `cpu`: a real engine, but CPU latency. A `cpu` number is never presented as GPU or vLLM latency.

### 2. Model: Qwen2 architecture, seeded random weights, real Qwen2 tokenizer

- **Weights:** `tickets/rly-4-prefix-caching/make_model.py` builds the model deterministically. The SHA-256 of the file is recorded in every manifest.
- **Tokenizer:** copied from llama.cpp's `ggml-vocab-qwen2.gguf`, the vocabulary Qwen2.5-Coder uses. Prompt token counts are therefore real.
- **Why random weights are acceptable here:** prefill work and cache reuse depend on architecture, tokenizer and token sequence, not on learned weight values.
- **What follows from that:** outputs are meaningless, so no RLY-4 result says anything about completion quality.
- **Size:** small (512 hidden, 8 layers), chosen so one 48-request run finishes in a few minutes on one CPU thread. Absolute latencies don't transfer to Relay's 7B model on a GPU, where prefill is far faster. What transfers is the share of prompt tokens a fix lets the engine skip.

### 3. The fix: remove the per-request header from the prompt (`PROMPT_TEMPLATE=metadata`)

- **What changes:** the header leaves the prompt. The gateway sends the request ID upstream as `X-Request-Id` instead.
- **Why not move the header to the end** (the ticket's first suggestion): an inline-completion prompt ends at the user's cursor. Text appended after the code would sit between the code and the completion the model is asked to write.
- **The baseline stays:** `PROMPT_TEMPLATE=original` remains the default and is byte-for-byte Relay's template.

### 4. Workload: editing sessions

- **Shared trace:** each session is one file, sent from the start of the file up to a cursor that advances 80–240 characters per request.
- **Independent control:** the same arrival times and cursors, but a different file for every request. It shows how much of the gain depends on context actually repeating.

### 5. Validity

- **Fresh server per run,** so no run inherits a warm cache.
- **CPU pinning:** the server runs on one core, and the gateway and load generator on the other.
- **Send-lag gate:** every run passes the load generator's self-check, including the new send-lag p99 limit of 10 ms.

## Consequences

- **Scope of the evidence.** RLY-4's result is evidence about the mechanism on a real engine. It isn't a GPU latency claim, and it isn't a capacity or cost claim.
- **On a GPU:** prefill is faster, so absolute savings are smaller in milliseconds. The fraction of prefill skipped is the same. That fraction needs re-measuring on vLLM before it goes into the capacity plan.
- **One server, one slot.** The experiment doesn't model many users competing for cache space, eviction, or routing across replicas. Those are separate questions; prefix-aware routing is one.
- **Reproducing it** needs a llama.cpp checkout to build the server and the model. Neither is committed: the model is about 350 MB, and the binary depends on the platform.
