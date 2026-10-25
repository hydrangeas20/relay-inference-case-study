"""Summarize the RLY-4 runs into results/rly-4/report.json and report.md.

Every number in the RLY-4 write-up and the README comes from this script's output,
which reads only the files the runs wrote: summaries, per-request raw records and the
server's Prometheus counters scraped before and after each run.

  uv run python tickets/rly-4-prefix-caching/analyze.py results/rly-4

Invalid runs are listed and excluded from the aggregates, never dropped silently.
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path
from typing import Any

CONFIG_ORDER = [
    "shared-original-cache",
    "shared-metadata-cache",
    "shared-metadata-nocache",
    "independent-original-cache",
    "independent-metadata-cache",
]
LABELS = {
    "shared-original-cache": "Sessions · original template · cache on (Relay today)",
    "shared-metadata-cache": "Sessions · fixed template · cache on (the fix)",
    "shared-metadata-nocache": "Sessions · fixed template · cache off (control)",
    "independent-original-cache": "No shared context · original · cache on (negative control)",
    "independent-metadata-cache": "No shared context · fixed · cache on (negative control)",
}
# (baseline, treatment, question)
PAIRS = [
    ("shared-original-cache", "shared-metadata-cache", "Does the template fix cut TTFT?"),
    (
        "shared-metadata-nocache",
        "shared-metadata-cache",
        "Is the prefix cache what delivers the gain?",
    ),
    (
        "shared-metadata-nocache",
        "shared-original-cache",
        "Did turning the cache on do anything with the original template?",
    ),
    (
        "independent-original-cache",
        "independent-metadata-cache",
        "Does the fix help when context doesn't repeat? (negative control)",
    ),
]


def _counter(text: str, name: str) -> float | None:
    for line in text.splitlines():
        if line.startswith(name + " "):
            return float(line.split()[1])
    return None


def _pct(values: list[float], q: float) -> float:
    s = sorted(values)
    k = (len(s) - 1) * q / 100
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def load_runs(root: Path, config: str) -> list[dict[str, Any]]:
    cdir = root / config
    summaries = sorted(
        (json.loads(p.read_text()) for p in cdir.glob("*.summary.json")),
        key=lambda s: s["created_at"],
    )
    runs = []
    for rep, s in enumerate(summaries, start=1):
        raw = [json.loads(line) for line in (cdir / "raw" / f"{s['run_id']}.jsonl").open()]
        before = (cdir / "server" / f"rep{rep}.metrics.before.txt").read_text()
        after = (cdir / "server" / f"rep{rep}.metrics.after.txt").read_text()
        ok = [r for r in raw if r["status"] == "ok"]
        timed = [r["server_timings"] for r in ok if r.get("server_timings")]
        busy_ms = sum(t.get("prompt_ms", 0) + t.get("predicted_ms", 0) for t in timed)
        span = max(r["actual_send_s"] + (r["e2e_s"] or 0) for r in raw) - min(
            r["actual_send_s"] for r in raw
        )
        evaluated = (_counter(after, "llamacpp:prompt_tokens_total") or 0) - (
            _counter(before, "llamacpp:prompt_tokens_total") or 0
        )
        cached = (_counter(after, "llamacpp:prompt_tokens_cached_total") or 0) - (
            _counter(before, "llamacpp:prompt_tokens_cached_total") or 0
        )
        w = s["workloads"]["completion"]
        runs.append(
            {
                "rep": rep,
                "run_id": s["run_id"],
                "valid": s["valid"],
                "invalid_reasons": s["self_check"]["reasons"] if not s["valid"] else [],
                "reconciliation": (s.get("reconciliation") or {}).get("status"),
                "commit": s["manifest"]["git"]["commit"],
                "dirty": s["manifest"]["git"]["dirty"],
                "template": s["manifest"]["gateway"]["prompt_template"],
                "sent": w["sent"],
                "ok": w["ok"],
                "errors": w["errors"],
                "ttft_s": w["ttft_s"],
                "e2e_s": w["e2e_s"],
                "send_lag_p99_ms": s["self_check"]["send_lag_s"]["p99"] * 1000,
                "server_cached_fraction_timings": w["server_timings"]["cached_fraction"],
                "server_prompt_ms_p50": w["server_timings"]["prompt_ms"]["p50"],
                "server_tokens_evaluated_metrics": evaluated,
                "server_tokens_cached_metrics": cached,
                "server_cached_fraction_metrics": cached / (cached + evaluated)
                if cached + evaluated
                else None,
                "server_busy_fraction": busy_ms / 1000 / span if span else None,
                "achieved_rps": w["sent"] / span if span else None,
                "per_request": {r["req_id"]: r for r in raw},
            }
        )
    return runs


def aggregate(runs: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [r for r in runs if r["valid"]]
    out: dict[str, Any] = {"runs": len(runs), "valid_runs": len(valid)}
    if not valid:
        return out

    def spread(get: Any) -> dict[str, float]:
        vals = [get(r) for r in valid]
        return {"median": statistics.median(vals), "min": min(vals), "max": max(vals)}

    for q in ("p50", "p95", "p99"):
        out[f"ttft_{q}_s"] = spread(lambda r, q=q: r["ttft_s"][q])
    out["e2e_p50_s"] = spread(lambda r: r["e2e_s"]["p50"])
    out["cached_fraction"] = spread(lambda r: r["server_cached_fraction_metrics"])
    out["server_prompt_ms_p50"] = spread(lambda r: r["server_prompt_ms_p50"])
    out["server_busy_fraction"] = spread(lambda r: r["server_busy_fraction"])
    out["errors"] = sum(r["sent"] - r["ok"] for r in valid)
    return out


def paired(base: list[dict[str, Any]], treat: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Same trace, same req_ids: compare each request's median TTFT across valid reps."""
    bv, tv = [r for r in base if r["valid"]], [r for r in treat if r["valid"]]
    if not bv or not tv:
        return None

    def med(runs: list[dict[str, Any]], rid: str) -> float | None:
        vals = [r["per_request"][rid]["ttft_s"] for r in runs]
        vals = [v for v in vals if v is not None]
        return statistics.median(vals) if vals else None

    rows = []
    for rid in sorted(bv[0]["per_request"]):
        b, t = med(bv, rid), med(tv, rid)
        if b and t:
            rows.append((rid, b, t))

    def summarize(sel: list[tuple[str, float, float]]) -> dict[str, Any]:
        ratios = [t / b for _, b, t in sel]
        return {
            "n": len(sel),
            "median_ratio": statistics.median(ratios),
            "ratio_p10": _pct(ratios, 10),
            "ratio_p90": _pct(ratios, 90),
            "faster_fraction": sum(t < b for _, b, t in sel) / len(sel),
            "median_saving_s": statistics.median([b - t for _, b, t in sel]),
        }

    first = [x for x in rows if x[0].endswith("-00")]
    follow = [x for x in rows if not x[0].endswith("-00")]
    return {
        "all": summarize(rows),
        "first_in_session": summarize(first) if first else None,
        "follow_ups": summarize(follow) if follow else None,
    }


def _fmt_s(x: dict[str, float]) -> str:
    return f"{x['median'] * 1000:,.0f} ({x['min'] * 1000:,.0f}–{x['max'] * 1000:,.0f})"


def _fmt_frac(x: dict[str, float]) -> str:
    return f"{x['median']:.1%} ({x['min']:.1%}–{x['max']:.1%})"


def render(report: dict[str, Any]) -> str:
    lines = [
        "# RLY-4 results (generated by tickets/rly-4-prefix-caching/analyze.py)",
        "",
        "Source: `cpu`. llama.cpp `llama-server` on one CPU thread, synthetic-weight "
        "Qwen2-architecture model. Not GPU or vLLM latency; no quality claim.",
        "",
        "Values: median across valid runs (min–max across runs). TTFT and E2E are "
        "client-measured, in ms. Cache share = prompt tokens served from the KV cache, "
        "from the server's own counters.",
        "",
        "| Configuration | Valid runs | TTFT p50 | TTFT p95 | TTFT p99 | E2E p50 | "
        "Cache share | Server busy | Errors |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for name in CONFIG_ORDER:
        a = report["configs"].get(name)
        if not a or not a["aggregate"].get("valid_runs"):
            continue
        g = a["aggregate"]
        lines.append(
            f"| {LABELS[name]} | {g['valid_runs']}/{g['runs']} | {_fmt_s(g['ttft_p50_s'])} | "
            f"{_fmt_s(g['ttft_p95_s'])} | {_fmt_s(g['ttft_p99_s'])} | {_fmt_s(g['e2e_p50_s'])} | "
            f"{_fmt_frac(g['cached_fraction'])} | {_fmt_frac(g['server_busy_fraction'])} | "
            f"{g['errors']} |"
        )
    lines += [
        "",
        "## Paired comparisons (same requests, median TTFT per request across runs)",
        "",
        "| Question | Requests | Median TTFT ratio (p10–p90) | Faster | "
        "Follow-ups only: median ratio |",
        "| --- | --- | --- | --- | --- |",
    ]
    for p in report["pairs"]:
        r = p["result"]
        if r is None:
            continue
        al, fu = r["all"], r["follow_ups"]
        lines.append(
            f"| {p['question']} | {al['n']} | {al['median_ratio']:.2f} "
            f"({al['ratio_p10']:.2f}–{al['ratio_p90']:.2f}) | {al['faster_fraction']:.0%} | "
            f"{fu['median_ratio']:.2f} |"
        )
    invalid = [
        (n, r["rep"], r["invalid_reasons"])
        for n, c in report["configs"].items()
        for r in c["runs"]
        if not r["valid"]
    ]
    lines += ["", "## Invalid runs", ""]
    lines += [f"- {n} rep {rep}: {'; '.join(why)}" for n, rep, why in invalid] or ["None."]
    commits = sorted(
        {(r["commit"], r["dirty"]) for c in report["configs"].values() for r in c["runs"]}
    )
    lines += ["", f"Code: {', '.join(f'{c} (dirty={d})' for c, d in commits)}", ""]
    return "\n".join(lines)


def main() -> None:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "results/rly-4")
    configs: dict[str, Any] = {}
    for name in CONFIG_ORDER:
        if (root / name).is_dir():
            runs = load_runs(root, name)
            configs[name] = {"runs": runs, "aggregate": aggregate(runs)}
    pairs = [
        {
            "baseline": b,
            "treatment": t,
            "question": q,
            "result": paired(configs[b]["runs"], configs[t]["runs"])
            if b in configs and t in configs
            else None,
        }
        for b, t, q in PAIRS
    ]
    report = {"configs": configs, "pairs": pairs}
    slim = {
        "configs": {
            n: {
                "aggregate": c["aggregate"],
                "runs": [{k: v for k, v in r.items() if k != "per_request"} for r in c["runs"]],
            }
            for n, c in configs.items()
        },
        "pairs": pairs,
    }
    (root / "report.json").write_text(json.dumps(slim, indent=2) + "\n")
    md = render(report)
    (root / "report.md").write_text(md)
    print(md)


if __name__ == "__main__":
    main()
