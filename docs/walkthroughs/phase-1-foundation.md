# Foundation walkthrough: Phase 1, the system every ticket runs on

**This is infrastructure, not a customer ticket.** It answers no RLY complaint on its own. It's the measurable system that RLY-4 and every planned ticket run on.

- **Implementation PR:** [#1](https://github.com/hydrangeas20/relay-inference-case-study/pull/1), merged in [`763e9eb`](https://github.com/hydrangeas20/relay-inference-case-study/commit/763e9eb0dc6bf4aa6ee950b67f432273c57f99cd).
- **Main commit:** [`c9d7761`](https://github.com/hydrangeas20/relay-inference-case-study/commit/c9d7761ab58dfbaba6461ca54b1b173666e461fa).
- **Decisions:** [ADR-0003](../decisions/0003-phase-1-foundation.md). Its "Why" lines are labelled *retrospective*: they were added later, in [`22231d6`](https://github.com/hydrangeas20/relay-inference-case-study/commit/22231d6f9c48bd577cd5bc95e9cd141ccee787af), as explanations inferred from the implementation.
- **Spec and acceptance criteria:** [phase-1-foundation.md](../phases/phase-1-foundation.md).

## What problem it solves

Every inference claim in this project needs three things:
- **traffic that can be replayed exactly**, so before/after comparisons use identical inputs;
- **a path that looks like Relay's** (editor → Relay's API → model), so measurements reflect what users wait for;
- **measurements that check themselves**, so a slow client or a broken metric can't pass as a result.

Phase 1 builds that.

## What was built, and where to read it

| Component | What it does | Code | Tests |
| --- | --- | --- | --- |
| Gateway | Relay's `/v1/complete` and `/v1/agent`. Builds prompts from Relay's templates, streams Server-Sent Events, exposes metrics | [`src/relay/gateway/`](../../src/relay/gateway/) | [`tests/test_gateway.py`](../../tests/test_gateway.py) |
| Load generator | Replays traces open-loop, measures client TTFT, self-checks its schedule and CPU | [`src/relay/loadgen/runner.py`](../../src/relay/loadgen/runner.py), [`selfcheck.py`](../../src/relay/loadgen/selfcheck.py) | [`tests/test_stats_and_selfcheck.py`](../../tests/test_stats_and_selfcheck.py) |
| TTFT reconciliation | Compares the timing layers available on a run (client, gateway, server where exported) and their request counts | [`src/relay/loadgen/reconcile.py`](../../src/relay/loadgen/reconcile.py) | [`tests/test_reconcile.py`](../../tests/test_reconcile.py) |
| Indexing worker | Pulls jobs from SQS with bounded concurrency, embeds chunks, records results in DynamoDB | [`src/relay/worker.py`](../../src/relay/worker.py), [`src/relay/aws.py`](../../src/relay/aws.py) | [`tests/test_worker.py`](../../tests/test_worker.py) |
| Code corpus | Real code from 8 pinned, license-checked repositories, with a hash for every file | [`src/relay/corpus/`](../../src/relay/corpus/), [`corpus/`](../../corpus/) | [`tests/test_corpus.py`](../../tests/test_corpus.py) |
| Traces | Seeded, sorted, hash-identified request files; replay fails against a different corpus | [`src/relay/traces/`](../../src/relay/traces/) | [`tests/test_traces.py`](../../tests/test_traces.py) |
| Local stack | Simulator, Floci (AWS emulator), Prometheus, Grafana, gateway, worker | [`docker-compose.yml`](../../docker-compose.yml), [`Dockerfile`](../../Dockerfile) | Stack smoke workflow (below) |

**End-to-end test:** [`tests/test_end_to_end.py`](../../tests/test_end_to_end.py) replays a trace over real sockets: load generator → gateway → a fake OpenAI-compatible server. It checks that every request succeeds and that the timing layers reconcile.

## How it was verified

- **At merge:** PR #1 passed lint, strict type checks and 53 tests.
- **Docker stack, later:** the stack couldn't be started where PR #1 was built. It was first started end to end by the [Stack smoke workflow](../../.github/workflows/stack.yml), which PR #3 added. That workflow runs on a clean GitHub runner, replays the smoke trace, and checks that every indexing job is processed.
- **Without Docker:** [`scripts/verify_local_stack.sh`](../../scripts/verify_local_stack.sh) ran the gateway, the worker and the load generator over real sockets against llama.cpp and an AWS API emulator. Its records are in [`results/phase1-verification/`](../../results/phase1-verification/). That run checks plumbing, not latency: its own load-generator run was marked invalid on 2 shared cores.

## Limitations

- **No Phase 1 performance numbers.** It produced no performance results of its own. The simulator's latencies are placeholders, not calibrated.
- **Open questions.** Q1–Q7 in ADR-0003 still use their documented defaults.
- **Day-long traces can't be replayed yet.** The load generator builds every payload in memory first (ADR-0004 Q11).
