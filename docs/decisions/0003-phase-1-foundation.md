# ADR-0003: Phase 1 foundation choices

- **Status:** Accepted
- **Date:** 2026-09-28
- **Decided by:** hydrangeas20

Seven decisions shaped the Phase 1 foundation. Each lists the options that were on the table, the choice, and what it commits us to. The **Why** lines are the engineer's reasoning and are left for the engineer to write.

> **Note (2026-10-25):** the six **Why (retrospective)** lines below were added after the decisions were made. They are explanations inferred from the implementation and approved by hydrangeas20 on 2026-10-25. They are not a contemporaneous record of the original reasoning. The decisions, options and consequences above each line are unchanged.

## 1. What is the gateway? → B. Relay-shaped API

- **A. Thin proxy:** forwards OpenAI-format requests and adds metrics. Prompt building lives in the load generator.
- **B. Relay-shaped API** ✅: `/v1/complete` and `/v1/agent` accept editor context and build prompts server-side from Relay's templates.

**Consequences:** Relay's prompt template lives in Relay's code (`relay/gateway/templates.py`), which is where RLY-4's bug belongs. The load generator sends what an editor would send, not model prompts.

**Why (retrospective):** Prompt construction is part of the system under test. Building prompts in the gateway puts template behaviour, including the per-request header RLY-4 investigates, in Relay's code path, where a template change can be measured against identical client traffic. A thin proxy would have moved prompt building into the load generator, outside the system being measured. *(Grounded in `gateway/templates.py` and the `prompts.py` docstring.)*

## 2. Streaming → A. Stream end to end through the gateway

- **A. Through the gateway** ✅: Server-Sent Events pass through the gateway unchanged.
- **B. Direct for benchmarks:** the load generator calls the inference server directly.

**Consequences:** client-side TTFT includes gateway overhead, as users experience it. The gateway must not buffer, and its own overhead becomes something we measure (see decision 3).

**Why (retrospective):** Users reach the model through Relay's API, so TTFT is measured on that path. Streaming through the gateway includes its overhead in client TTFT, and the gateway's own upstream TTFT histogram makes that overhead measurable rather than hidden. Calling the server directly would time a path no user takes. *(Grounded in `gateway/app.py`: `relay_stream`, `relay_gateway_upstream_ttft_seconds`.)*

## 3. Where is latency measured? → C. Both, reconciled

- **A. Client side only.**
- **B. Server side only.**
- **C. Both, with a reconciliation check** ✅.

**Consequences:** three nested TTFT measurements are compared on every run: server (`vllm:time_to_first_token_seconds`), gateway (`relay_gateway_upstream_ttft_seconds`) and client (per-request). An outer layer must never be faster than an inner one, beyond the inner histogram's bucket width. The server's completed-request count must be at least what the client streamed.

**Why (retrospective):** Each layer fails differently: client timings absorb the generator's own delays, and server-side histograms are coarse and can include other traffic. Comparing whichever layers are available on a run, and checking that timings nest and request counts agree within the available measurement resolution, turns silent measurement errors into reported problems. Not every inference server exports a server-side TTFT metric; where none exists, the check covers the layers that do. *(Grounded in the `loadgen/reconcile.py` docstring.)*

## 4. How is traffic generated? → B. Pre-generated trace files

- **A. On the fly with a seed.**
- **B. Pre-generated traces** ✅: JSONL files listing every request's send time, workload and inputs.

**Consequences:** before/after comparisons replay a byte-identical file, identified by its SHA-256. Traces reference corpus files by path and offset rather than embedding text, and record the corpus SHA-256, so replaying against a different corpus fails.

**Why (retrospective):** Before/after comparisons must replay identical traffic. A hash-identified trace file makes that checkable rather than assumed, lets payloads be built before the clock starts so building can't delay sends, and makes runs reproducible from committed inputs. Known cost: day traces don't yet fit in memory (ADR-0004 Q11). *(Grounded in `traces/io.py` and `loadgen/runner.py`, `START_LEAD_S`.)*

## 5. What's inside the prompts? → B. Real code

- **A. Synthetic filler.**
- **B. Real code from an open-source dataset** ✅.
- **C. Synthetic now, real later.**

**Follow-up: where the code comes from → B. Pinned GitHub repos.** The other options were a Hugging Face dataset or Python-only PyPI packages.

**Consequences:** `corpus/repos.toml` pins eight permissively licensed repos (Python, JavaScript, Go, Rust, Java, TypeScript, Elixir, Haskell) to exact commits, each with the SHA-256 of its reviewed license file. `make corpus` refuses to build if a license file differs. The code itself isn't committed; `corpus/corpus.lock.json` records every file's hash. Elixir and Haskell give RLY-6 its less-common-language slices.

**Why (retrospective):** Token counts, and how much of a prompt repeats or is rare, depend on real code; filler text tokenizes differently and has no language mix. Pinned commits with license and per-file hashes keep the corpus reproducible and license-reviewed, and the language spread, including Elixir and Haskell, gives RLY-6 rare-language slices. *(Grounded in `corpus/fetch.py`, `corpus/repos.toml`, `corpus/corpus.lock.json`.)*

## 6. Worker concurrency → B. Bounded concurrency now

- **A. Sequential for now.**
- **B. Bounded concurrency now** ✅: `WORKER_MAX_IN_FLIGHT` jobs at once.

**Consequences:** the worker only receives as many messages as it has free slots, so it never holds messages it can't start. RLY-7's "before" state is a shared deployment with bounded concurrency, not a naive sequential worker.

**Why (retrospective):** A sequential worker would make RLY-7's "before" state an unrealistically weak baseline, flattering any isolation fix. Receiving only as many queue messages as there are free slots also avoids holding messages past their visibility timeout. *(Grounded in the `worker.py` docstring.)*

## 7. License → none

The repository has no license, so all rights are reserved. `pyproject.toml` no longer declares one.

---

## Open questions for the engineer

These came up while implementing and need a decision. Until decided, the code uses the default shown.

| # | Question | Current default | Where |
|---|---|---|---|
| Q1 | At what generator CPU level is a run invalid? | p95 ≥ 90% of one core | `loadgen/selfcheck.py` |
| Q2 | What happens when reconciliation finds a disagreement? | Reported in the summary; the run stays valid | `loadgen/reconcile.py` |
| Q3 | How large a client-vs-server TTFT gap is acceptable? | Not judged; gap is reported | `loadgen/reconcile.py` |
| Q4 | Should the completion prompt use the editor's suffix (fill-in-the-middle)? | Accepted but unused until the model is chosen in Phase 3 | `gateway/templates.py` |
| Q5 | How are output tokens counted? | Streamed chunks and characters are recorded; true token counts wait for a tokenizer (Phase 3) | `loadgen/runner.py` |
| Q6 | How many failed attempts before an indexing job is dropped? | 5, then recorded as `failed` | `worker.py` |
| Q7 | The traffic shape (constant-rate Poisson, 80/15/5 mix, length ranges) | Placeholders until Phase 2's traffic model | `traces/generate.py` |
