"""Audit of the scale chain, its sensitivity, and request sizes.

Usage: uv run python analysis/audit_scale_and_sizes.py

Independently recomputes (from traffic/relay.toml, without Relay's model code) the
chain: daily users x active hours x requests/hour -> requests/day -> weekday shape ->
smooth-curve peak rps, and its sensitivity to each first-order assumption. Summarises
the committed Azure size sample (training days). No raw Azure data needed.
"""

from __future__ import annotations

import copy
import csv
import json
import tomllib
from pathlib import Path

import numpy as np

CONFIG = Path("traffic/relay.toml")


def peak_rps(cfg: dict) -> dict[str, float]:  # type: ignore[type-arg]
    t = np.arange(0, 86_400, 1.0) / 3600
    bump = np.zeros_like(t)
    for r in cfg["envelope"]["region"]:
        d = (t - r["center_utc_h"] + 12) % 24 - 12
        bump += r["share"] * np.exp(-0.5 * (d / r["width_h"]) ** 2)
    floor = cfg["envelope"]["floor"]
    shape = floor + (1 - floor) * bump / bump.max()
    u, rt = cfg["users"], cfg["rates"]
    per_day = (
        u["daily_active"]
        * u["active_hours_per_day"]
        * (rt["completions_per_active_hour"] + rt["agent_turns_per_active_hour"])
    )
    hourly = shape.reshape(24, 3600).mean(axis=1)
    return {
        "requests_per_day": per_day,
        "mean_rps": per_day / 86_400,
        "peak_to_mean": 1 / shape.mean(),
        "peak_rps": per_day / 86_400 / shape.mean(),
        "peak_time_utc_h": float(t[bump.argmax()]),
        "hourly_peak_to_trough": float(hourly.max() / hourly.min()),
    }


def main() -> None:
    cfg = tomllib.loads(CONFIG.read_text())
    base = peak_rps(cfg)
    sens: dict[str, list[tuple[float, float]]] = {}

    def vary(label: str, path: tuple[str, ...], values: list[float]) -> None:
        rows = []
        for v in values:
            c = copy.deepcopy(cfg)
            node = c
            for k in path[:-1]:
                node = node[k]
            node[path[-1]] = v
            rows.append((v, round(peak_rps(c)["peak_rps"])))
        sens[label] = rows

    vary("completions_per_active_hour", ("rates", "completions_per_active_hour"), [30, 60, 90])
    vary("agent_turns_per_active_hour", ("rates", "agent_turns_per_active_hour"), [2, 4, 8])
    vary("active_hours_per_day", ("users", "active_hours_per_day"), [2, 4, 6])
    vary("daily_active", ("users", "daily_active"), [200_000, 400_000, 800_000])
    vary("envelope_floor", ("envelope", "floor"), [0.05, 0.10, 0.15])
    with Path(cfg["sizes"]["completion_reference"]).open() as f:
        rows = [(int(r["context_tokens"]), int(r["generated_tokens"])) for r in csv.DictReader(f)]
    ctx = np.array([r[0] for r in rows])
    gen = np.array([r[1] for r in rows])
    q = [10, 25, 50, 75, 90, 95, 99]
    print(json.dumps({
        "chain": base,
        "sensitivity_peak_rps": sens,
        "size_sample": {"n": len(rows),
                        "prompt_tokens_percentiles": dict(zip(q, np.percentile(ctx, q).tolist(), strict=True)),
                        "output_tokens_percentiles": dict(zip(q, np.percentile(gen, q).tolist(), strict=True))},
    }, indent=1))  # fmt: skip


if __name__ == "__main__":
    main()
