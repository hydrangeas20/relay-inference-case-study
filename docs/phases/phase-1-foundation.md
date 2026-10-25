# Phase 1: Foundation

**Goal:** one request flows end to end through each path, with timings recorded and metrics in Prometheus:

- load generator → gateway → inference (completion and agent chat, streamed)
- load generator → SQS (Floci) → worker → inference (embeddings) → DynamoDB (Floci)

Decisions: [ADR-0003](../decisions/0003-phase-1-foundation.md).

## Acceptance criteria

### Corpus
- [x] Repos pinned to full commit SHAs, permissive licenses only
- [x] Build refuses to proceed if a license file differs from the reviewed hash
- [x] Every file's SHA-256 recorded in `corpus/corpus.lock.json`; loading fails on any mismatch

### Traces
- [x] Same inputs and seed produce a byte-identical trace
- [x] Header records seed, parameters and corpus SHA-256; replay fails against a different corpus
- [x] Requests sorted by send time; count checked against the header

### Gateway
- [x] `/v1/complete` and `/v1/agent` build prompts from Relay's templates
- [x] Responses stream through without buffering
- [x] Metrics: requests by workload and status, duration, upstream TTFT, in-flight
- [x] Upstream errors return 502 and are counted by status

### Worker
- [x] Never more than `WORKER_MAX_IN_FLIGHT` jobs at once; only receives messages it can start
- [x] Successful jobs are recorded in DynamoDB and deleted from the queue
- [x] Failed jobs stay on the queue for retry, and are recorded as failed after 5 attempts
- [x] Queue and table created idempotently at stack startup

### Load generator
- [x] Open-loop: sends on schedule regardless of outstanding requests
- [x] Payloads built before the clock starts
- [x] Self-check: run invalid if achieved rate is > 2% short or generator CPU p95 ≥ 90%
- [x] Reconciliation of server, gateway and client TTFT, with request-count check
- [x] Writes per-request raw records and a summary tagged with its `source`

### Stack
- [x] Gateway, worker, bootstrap and load generator run as containers in Docker Compose
- [x] Prometheus scrapes the simulator, gateway and worker
- [ ] **Verified with `make up` + `make run` on a machine with Docker** (not yet done; see below)

## Verification status

Verified: `make check` (ruff, mypy strict, 53 tests). The tests include a real-socket end-to-end run (load generator → gateway → a fake OpenAI-compatible server) that produces a valid run whose three TTFT layers reconcile, and a worker test against mocked SQS and DynamoDB.

Not yet verified: the Docker stack itself. The environment used to build this couldn't pull images from Docker Hub or GHCR, so Floci and the simulator haven't run with this code. The first `make up` on a real machine is the check.
