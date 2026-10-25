# Question for the Azure public dataset maintainers

**Status:** drafted 2026-09-28, not yet sent. Phase 2 doesn't wait for a reply (ADR-0005, D2).
**To:** azurepublicdataset@service.microsoft.com

---

**Subject:** TIMESTAMP semantics in AzureLLMInferenceTrace_code_1week.csv (2024)

Hello,

We're using the AzureLLMInferenceTrace_code_1week.csv (2024) trace to model request arrival patterns, and would appreciate clarification on the TIMESTAMP field. Across the whole week, arrivals within each 250 ms interval almost never fall in the final ~50 ms (0.013% of 16.8M rows), and in busy hours about 45% of consecutive requests arrive within 1 ms of each other.

1. At what point is TIMESTAMP recorded: client send, frontend or load-balancer receipt, scheduler admission, or elsewhere?
2. How was the "subset of invocations" selected, and could the selection or any post-processing (merging services, batched log writes, time-slot sampling) produce periodic structure?
3. Are all timestamps from a single clock source?

Thank you. We cite the DynamoLLM paper and the dataset per its CC-BY terms.

---

## Reply log

_None yet._
