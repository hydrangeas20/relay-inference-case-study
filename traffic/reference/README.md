# Reference data derived from Azure's public LLM inference trace

These files are derived from the **Azure LLM inference trace 2024** (code service, one-week sample, 10–16 May 2024), licensed under [CC-BY 4.0](https://github.com/Azure/AzurePublicDataset/blob/master/LICENSE).

> Jovan Stojkovic, Chaojie Zhang, Íñigo Goiri, Josep Torrellas, Esha Choukse. "[DynamoLLM: Designing LLM Inference Clusters for Performance and Energy Efficiency](https://arxiv.org/abs/2408.00741)", HPCA 2025. Data: https://github.com/Azure/AzurePublicDataset

All four files come from the **training days only** (Fri 10 – Tue 14 May 2024). Thursday is reserved for validation and Wednesday for the holdout ([ADR-0005](../../docs/decisions/0005-traffic-model-revision.md)). The generating script never parses rows from those days.

| File | Contents | How it's used |
|---|---|---|
| `azure_code_hourly.csv` | Requests per hour, training days | Checks the envelope's peak/trough ratio (decision 1C) |
| `azure_code_burstiness.json` | Rate-band curves, candidates C1 and C2, band-holdout fits and tolerances; timestamps re-randomised within 250 ms | Drives arrival burstiness (decision 2C) |
| `azure_code_clustering.json` | Cluster sizes and within-cluster gaps from raw timestamps | The `--clustered` sensitivity variant only |
| `azure_code_sizes.csv` | 20,000 sampled (context, generated) token pairs | Completion request sizes (decision 3B) |

Changes from the original: restricted to the training days, aggregated to hourly counts, summarised into fitted models, and randomly subsampled (seed 20240510). To regenerate, download the original (~690 MB) with `uv run python analysis/azure_download.py`, which checks its SHA-256, then run `uv run python analysis/azure_traffic.py`. See `analysis/README.md`.

Azure's trace is from a different product and user base than Relay. It's used for traffic *character* (shape, burstiness, sizes), not for Relay's volume or timing, which are assumptions in `traffic/relay.toml`.
