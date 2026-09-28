# Architecture

## Components

| Component | Tech | Responsibility |
|---|---|---|
| Load generator | Python, `asyncio` + `httpx` | Generates open-loop traffic from Relay's traffic model; records per-request timings |
| Gateway | Python, FastAPI | Relay's interactive API (completions, agent chat); forwards to the inference endpoint; exposes metrics |
| Worker | Python, `boto3` | Pulls indexing jobs from SQS, calls the embedding endpoint, writes to DynamoDB |
| Inference: real | vLLM on a rented GPU | Ground-truth performance and all quality evals |
| Inference: simulated | llm-d-inference-sim | OpenAI-compatible stand-in, calibrated to real measurements, for scale tests |
| Customer AWS | Floci | Emulated S3, SQS, DynamoDB at `localhost:4566` |
| Metrics | Prometheus + Grafana | Live operational dashboard |
| Reporting | Python + Plotly | Generates the case study site from `results/` |

## Key design decisions

- **One switch between real and simulated inference.** The gateway and worker read `INFERENCE_BASE_URL`. The simulator and vLLM both speak the OpenAI API and both expose vLLM-style Prometheus metrics, so dashboards and code are identical in both modes.
- **Customer AWS is plumbing only.** Floci hosts the queue, storage and results table. No inference runs in Floci.
- **Results are files.** Every experiment writes `results/*.json`. The site, charts and report are built from those files, so they can't drift from the data.

See [`decisions/`](decisions/) for the reasoning behind each choice.

## Request paths

**Interactive (completions, agent chat)**

```
load generator → gateway → inference endpoint (vLLM or simulator)
```

**Batch (repo indexing)**

```
load generator → SQS (Floci) → worker → embedding endpoint → DynamoDB (Floci)
```
