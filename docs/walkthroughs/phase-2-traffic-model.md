# Foundation walkthrough: Phase 2, the traffic model

**This is infrastructure, not a customer ticket, and its central model is not validated.** It builds Relay's synthetic traffic and records an attempt to validate it. That attempt has not passed out-of-sample validation.

- **Implementation PR:** [#2](https://github.com/hydrangeas20/relay-inference-case-study/pull/2), merged in [`edf17a0`](https://github.com/hydrangeas20/relay-inference-case-study/commit/edf17a0e7ef4f42fea6f1dc06d481802767ef642).
- **Later documentation commits:**
  - [`6eed338`](https://github.com/hydrangeas20/relay-inference-case-study/commit/6eed338ee6fbe2fc47293433898f285b1965429b): status correction;
  - [`4071faa`](https://github.com/hydrangeas20/relay-inference-case-study/commit/4071faa77f4e89610b99e01b69ad9a0ff1c1af48): ADR-0004's retrospective rationale.
- **Decisions:** [ADR-0004](../decisions/0004-traffic-model.md), [ADR-0005](../decisions/0005-traffic-model-revision.md), [ADR-0006](../decisions/0006-reconciliation-check.md).
- **Status document:** [phase-2-traffic-model.md](../phases/phase-2-traffic-model.md).

## What problem it addresses

Capacity and tail latency depend on how bursty traffic is, not only on its average rate. Phase 2 fitted Relay's synthetic traffic to Azure's public 2024 code-service trace, then tried to show the fit reproduces queueing behaviour on held-out data. Azure is used for the traffic's character; Relay's volume and timing stay labelled assumptions:
- a daily shape;
- rate-dependent burstiness;
- realistic prompt sizes.

## What was built, and where to read it

| Part | Code or data | Tests |
| --- | --- | --- |
| Daily envelope, rate-dependent burstiness, trace generation | [`src/relay/traffic/`](../../src/relay/traffic/) | [`tests/test_traffic.py`](../../tests/test_traffic.py), [`tests/test_burstiness.py`](../../tests/test_burstiness.py) |
| Relay's assumptions, each labelled | [`traffic/relay.toml`](../../traffic/relay.toml) | — |
| Azure-derived reference data (training days only) | [`traffic/reference/`](../../traffic/reference/) | — |
| Trace format v3 and content-addressed identity | [`src/relay/traces/identity.py`](../../src/relay/traces/identity.py) | [`tests/test_trace_identity.py`](../../tests/test_trace_identity.py) |
| Prompt sizes built to target with the gateway's template | [`src/relay/traffic/generate.py`](../../src/relay/traffic/generate.py) | [`tests/test_prompt_fidelity.py`](../../tests/test_prompt_fidelity.py) |
| Preregistered validation tooling and the holdout guard | [`analysis/`](../../analysis/) | [`tests/test_cycle2_validation.py`](../../tests/test_cycle2_validation.py), [`tests/test_holdout_guard.py`](../../tests/test_holdout_guard.py) |

## Validation history (as recorded, unchanged)

| Step | Outcome | Record |
| --- | --- | --- |
| Cycle 1: Thursday validation | **Failed.** Both candidates overestimated queue p99 by about 1.3–1.5x; no candidate passed | [phase-2-preregistration.md](../validation/phase-2-preregistration.md), [queueing diagnosis](../validation/phase-2-queueing-diagnosis.md) |
| Cycle 2: validation rule | Frozen on 2026-10-05. It can't detect biases near 1.15x | [Cycle 2 preregistration](../validation/phase-2-cycle-2-preregistration.md), [criterion audit](../validation/phase-2-cycle-2-criterion-audit.md) |
| Cycle 2: Candidate D | **Internal PASS on development data** (3 of 4 gating folds). This isn't out-of-sample evidence or a match to Azure | [Candidate ledger](../validation/phase-2-cycle-2-candidate-ledger.md), [`analysis/results/cycle2/candidate-d/`](../../analysis/results/cycle2/candidate-d/) |
| Cycle 2: Candidates A and B | Not authorised. Amendment 4 is a draft | [Amendment 4 draft](../validation/phase-2-cycle-2-amendment-4-draft.md) |
| Section 8 selection | Not made. `traffic/relay.toml` still names Cycle 1's C1 | [`traffic/relay.toml`](../../traffic/relay.toml) |
| Wednesday holdout | Never read | [Candidate ledger](../validation/phase-2-cycle-2-candidate-ledger.md) |

## What this means for the rest of the project

- **RLY-4 doesn't use the burstiness model.** Its traces use Poisson arrivals.
- **Burstiness enters later results only as a labelled sensitivity input.** Any capacity or tail-latency claim built on it carries the validator's resolution limits.

## Limitations

- **Not validated out of sample.** Choosing the model in ADR-0004 is not a validation claim.
- **Relay's demand is assumed.** Daily users, active hours and requests per hour are assumptions, and the 2M-user scenario has not been load-tested.
- **Day-long traces can't be replayed yet** (ADR-0004 Q11).
