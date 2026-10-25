# RLY-4 predictions (written before any full-experiment result was read)

Committed while the first full run was in progress. A 6-request pilot had already run
to check the pipeline (shared trace, original vs fixed template, cache on); it's noted
here because it informed the predictions below. Pilot output is not part of the results.

## Question

Relay enabled prefix caching and TTFT didn't change. Is the per-request header at the top
of every prompt the reason, and how much TTFT does removing it recover?

## Hypothesis

H1. With the original template, the engine reuses almost no prompt tokens from its cache,
because every prompt differs from the request ID onward (within the first ~10 tokens).
With the header removed, follow-up requests in an editing session reuse nearly all of
the previous request's prompt.

## Predictions, and what would falsify them

| # | Prediction | Falsified if |
|---|---|---|
| P1 | Original template, cache on: cache share of prompt tokens < 2% | ≥ 5% |
| P2 | Fixed template, cache on, shared sessions: cache share > 60% (5 of every 6 requests are follow-ups that can reuse most of their prompt) | < 40% |
| P3 | Fixed template, cache on, shared sessions: median per-request TTFT ratio vs original < 0.5, and follow-ups < 0.3 | median ratio ≥ 0.8, or the change is inside run-to-run spread |
| P4 | Original template with cache on ≈ fixed template with cache off: median ratio within 0.9–1.1 ("we turned it on and nothing changed") | outside 0.8–1.25 |
| P5 | Fixed template with cache off: no TTFT gain vs original, so the gain needs the cache, not just a shorter prompt (the header is ~20 tokens of ~1,500) | median ratio < 0.9 |
| P6 | Negative control, no shared context: the fix saves only the system prompt (~90 tokens of ~1,500), so median TTFT ratio ≥ 0.85 | < 0.7 |

## Not predicted

p99 behaviour. With 48 requests per run, p99 is effectively the slowest request or
two, so it's reported but not used to accept or reject anything.
