# RLY-2: "Users hit 30-second waits every morning"

| | |
|---|---|
| **Theme** | Cold starts and autoscaling |
| **Status** | Planned |
| **Results source** | `sim`, `gpu` (cold start timing) |

## Customer complaint

> "The first requests of the day hang, then it's fine."

## Root cause (planted)

Deployments scale to zero overnight. The first morning requests trigger a cold start, which pulls and loads gigabytes of model weights while users wait.

## Reproduce

1. Measure a real cold start on the GPU: container start, weight download, weight load, first token.
2. Model the autoscaler against the simulator, starting from zero replicas.
3. Replay the morning traffic ramp and record wait times for the first users.

## Fix

- Keep a minimum replica count during business hours.
- Pre-warm ahead of the known morning peak on a schedule.
- Reduce weight load time (weight caching, faster storage, smaller quantized weights).

## Acceptance criteria

- [ ] Cold start broken into phases with measured durations.
- [ ] Morning-ramp timeline before and after: traffic, replicas, user wait time.
- [ ] An explicit cost of idle replicas vs. cost of user waits, and a recommended policy.

## Proof

Timeline of traffic, replica count and user wait. A slider trades idle GPU cost against user waits.

## Connects to

Minimum replicas cost money, which pulls directly against RLY-3's budget. The tradeoff is made explicitly.

---

## Findings

*Filled in once the ticket has been worked. Every number links to its file in `results/`.*

### Diagnosis

### What changed

### Before / after

| Metric | Before | After | Source |
|---|---|---|---|

### Recommendation to Relay

### What I'd do with more time
