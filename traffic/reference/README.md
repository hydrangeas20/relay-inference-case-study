# Reference data derived from Azure's public LLM inference trace

These files are derived from the **Azure LLM inference trace 2024** (code service, one-week sample, 10–16 May 2024), licensed under [CC-BY 4.0](https://github.com/Azure/AzurePublicDataset/blob/master/LICENSE).

> Jovan Stojkovic, Chaojie Zhang, Íñigo Goiri, Josep Torrellas, Esha Choukse. "[DynamoLLM: Designing LLM Inference Clusters for Performance and Energy Efficiency](https://arxiv.org/abs/2408.00741)", HPCA 2025. Data: https://github.com/Azure/AzurePublicDataset

| File | Contents | How it's used |
|---|---|---|
| `azure_code_hourly.csv` | Requests per hour for the week | Checks the envelope's peak/trough ratio (decision 1C) |
| `azure_code_burstiness.json` | Short-timescale rate fluctuation, fitted | Drives arrival burstiness (decision 2C) |
| `azure_code_sizes.csv` | 20,000 sampled (context, generated) token pairs | Completion request sizes (decision 3B) |

Changes from the original: aggregated to hourly counts, summarised into a fitted model, and randomly subsampled (seed 20240510). Regenerate with `uv run python analysis/azure_traffic.py`, which downloads the original (~690 MB).

Azure's trace is from a different product and user base than Relay. It's used for traffic *character* (shape, burstiness, sizes), not for Relay's volume or timing, which are assumptions in `traffic/relay.toml`.
