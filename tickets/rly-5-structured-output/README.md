# RLY-5: "Tool calls return broken JSON under load"

| | |
|---|---|
| **Theme** | Structured output |
| **Status** | Planned |
| **Results source** | `gpu` |

## Customer complaint

> "The agent randomly fails. It's worse at busy times."

## Root cause (planted)

Valid JSON is only *requested* in the prompt, not enforced. Under load, tight output limits and client timeouts truncate responses mid-object, so failures rise with traffic.

## Reproduce

1. Run agent chat traffic at increasing concurrency.
2. Validate every tool call against its JSON schema and record failure rate and failure type (malformed, truncated, schema-violating).

## Fix

- Enforce the schema with structured-output (guided) decoding.
- Set output limits and timeouts sized to the actual tool-call length distribution.

## Acceptance criteria

- [ ] Invalid tool-call rate vs. concurrency, before and after.
- [ ] Failures categorized by type.
- [ ] The latency overhead of guided decoding is measured and reported, not assumed away.

## Proof

Failure rate vs. concurrency, before/after, plus the latency cost of the fix.

## Connects to

Guided decoding's overhead has to fit inside the latency budget freed up by RLY-1 and RLY-4.

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
