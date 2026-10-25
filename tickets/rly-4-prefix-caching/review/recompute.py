"""Independent recomputation of the RLY-4 findings (review of PR #3).

Deliberately shares no code with analyze.py and imports nothing from `relay`. It reads
only the committed raw evidence:

  results/rly-4/<config>/raw/<run_id>.jsonl          per-request client records
  results/rly-4/<config>/<run_id>.summary.json        used ONLY for the CPU self-check
                                                      input and run identity
  results/rly-4/<config>/server/repN.metrics.*.txt    llama.cpp Prometheus counters

and recomputes run validity (send lag, rate), cache share from two independent
telemetry sources, TTFT percentiles under three different aggregations, paired
per-request ratios with a session-cluster bootstrap, server busy time, prompt and
output token counts, and a sensitivity analysis that includes invalid runs
(labelled non-inferential).

  python3 tickets/rly-4-prefix-caching/review/recompute.py results/rly-4

Writes recompute-output.json next to this script; never writes into results/.
"""

from __future__ import annotations

import json
import math
import random
import statistics
import sys
from pathlib import Path
from typing import Any

CONFIGS = [
    "shared-original-cache",
    "shared-metadata-cache",
    "shared-metadata-nocache",
    "independent-original-cache",
    "independent-metadata-cache",
]
LAG_LIMIT_S = 0.010
RATE_LIMIT = 0.02
CPU_LIMIT = 90.0
PLANNED_REPS = 3  # the run plan before any result was read: 3 repetitions per configuration


def pct(values: list[float], q: float) -> float:
    """Linear-interpolation percentile (same definition as numpy's default)."""
    s = sorted(values)
    if not s:
        return math.nan
    k = (len(s) - 1) * q / 100.0
    lo = math.floor(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def counter(text: str, name: str) -> float:
    for line in text.splitlines():
        if line.startswith(name + " "):
            return float(line.split()[1])
    raise KeyError(name)


def rate(times: list[float]) -> float:
    return (len(times) - 1) / (max(times) - min(times))


def load(root: Path, cfg: str) -> list[dict[str, Any]]:
    d = root / cfg
    summaries = sorted(
        (json.loads(p.read_text()) for p in d.glob("*.summary.json")),
        key=lambda s: s["run_id"],
    )
    runs = []
    for rep, s in enumerate(summaries, start=1):
        raw = [json.loads(x) for x in (d / "raw" / f"{s['run_id']}.jsonl").read_text().splitlines()]
        before = (d / "server" / f"rep{rep}.metrics.before.txt").read_text()
        after = (d / "server" / f"rep{rep}.metrics.after.txt").read_text()
        lags = [r["actual_send_s"] - r["intended_send_s"] for r in raw]
        shortfall = 1 - rate([r["actual_send_s"] for r in raw]) / rate(
            [r["intended_send_s"] for r in raw]
        )
        cpu_p95 = s["self_check"]["cpu_pct"]["p95"]
        lag_p99 = pct(lags, 99)
        valid = lag_p99 <= LAG_LIMIT_S and shortfall <= RATE_LIMIT and cpu_p95 < CPU_LIMIT
        ok = [r for r in raw if r["status"] == "ok"]
        t = [r["server_timings"] for r in ok]
        start = min(r["actual_send_s"] for r in raw)
        end = max(r["actual_send_s"] + r["e2e_s"] for r in raw)
        runs.append(
            {
                "cfg": cfg,
                "rep": rep,
                "run_id": s["run_id"],
                "valid": valid,
                "summary_valid": s["valid"],
                "lag_p99_ms": lag_p99 * 1000,
                "shortfall": shortfall,
                "cpu_p95": cpu_p95,
                "n": len(raw),
                "errors": len(raw) - len(ok),
                "ttft": {r["req_id"]: r["ttft_s"] for r in ok},
                "e2e": {r["req_id"]: r["e2e_s"] for r in ok},
                "prompt_chars": {r["req_id"]: r["prompt_chars"] for r in ok},
                "prompt_tokens": {
                    r["req_id"]: r["server_timings"]["cache_n"] + r["server_timings"]["prompt_n"]
                    for r in ok
                },
                "prompt_n": {r["req_id"]: r["server_timings"]["prompt_n"] for r in ok},
                "prompt_ms": {r["req_id"]: r["server_timings"]["prompt_ms"] for r in ok},
                "cache_n": {r["req_id"]: r["server_timings"]["cache_n"] for r in ok},
                "predicted_n": [x["predicted_n"] for x in t],
                # Source 1: per-request timings in the final SSE chunk.
                "share_timings": sum(x["cache_n"] for x in t)
                / sum(x["cache_n"] + x["prompt_n"] for x in t),
                # Source 2: server Prometheus counters, after minus before.
                "metrics_cached": counter(after, "llamacpp:prompt_tokens_cached_total")
                - counter(before, "llamacpp:prompt_tokens_cached_total"),
                "metrics_evaluated": counter(after, "llamacpp:prompt_tokens_total")
                - counter(before, "llamacpp:prompt_tokens_total"),
                "busy": sum(x["prompt_ms"] + x["predicted_ms"] for x in t) / 1000 / (end - start),
            }
        )
    for r in runs:
        r["share_metrics"] = r["metrics_cached"] / (r["metrics_cached"] + r["metrics_evaluated"])
        r["p50"] = pct(list(r["ttft"].values()), 50)
        r["p95"] = pct(list(r["ttft"].values()), 95)
        r["p99"] = pct(list(r["ttft"].values()), 99)
    return runs


def per_request_median(runs: list[dict[str, Any]], key: str = "ttft") -> dict[str, float]:
    ids = runs[0][key].keys()
    return {i: statistics.median(r[key][i] for r in runs) for i in ids}


def paired(base: list[dict[str, Any]], treat: list[dict[str, Any]]) -> dict[str, float]:
    b, t = per_request_median(base), per_request_median(treat)
    ratios = {i: t[i] / b[i] for i in b}
    follow = [v for i, v in ratios.items() if not i.endswith("-00")]
    first = [v for i, v in ratios.items() if i.endswith("-00")]
    return {
        "median_ratio": statistics.median(ratios.values()),
        "follow_ups": statistics.median(follow),
        "first": statistics.median(first),
        "faster": sum(v < 1 for v in ratios.values()) / len(ratios),
        "ci": session_bootstrap(ratios),
    }


def session_bootstrap(ratios: dict[str, float], n: int = 10_000) -> tuple[float, float]:
    """95% CI for the median paired ratio, resampling whole sessions (requests in a session
    share a file and a cache history, so they aren't independent)."""
    sessions: dict[str, list[float]] = {}
    for i, v in ratios.items():
        sessions.setdefault(i.split("-")[0], []).append(v)
    keys = sorted(sessions)
    rng = random.Random(4)
    meds = []
    for _ in range(n):
        sample = [v for k in (rng.choice(keys) for _ in keys) for v in sessions[k]]
        meds.append(statistics.median(sample))
    return pct(meds, 2.5), pct(meds, 97.5)


def main() -> None:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "results/rly-4")
    allruns = {c: load(root, c) for c in CONFIGS}
    out: dict[str, Any] = {"runs": [], "conditions": {}, "pairs": {}}

    print("== Runs (validity recomputed from raw send times; CPU from summary)")
    for c in CONFIGS:
        for r in allruns[c]:
            agree = "agrees" if r["valid"] == r["summary_valid"] else "DISAGREES"
            print(
                f"{c:28s} rep{r['rep']} {'VALID  ' if r['valid'] else 'INVALID'} "
                f"lag_p99={r['lag_p99_ms']:5.1f}ms shortfall={r['shortfall']:+.4f} "
                f"cpu_p95={r['cpu_p95']:.0f}% errors={r['errors']} ({agree} with summary)"
            )
            out["runs"].append({k: v for k, v in r.items() if not isinstance(v, dict | list)})

    print("\n== Conditions (valid runs only)")
    hdr = (
        "condition                    runs  medRunP50  pooledP50  medRunP95  pooledP95  "
        "share(metrics)  share(timings)  busy   out_tokens"
    )
    print(hdr)
    for c in CONFIGS:
        v = [r for r in allruns[c] if r["valid"]]
        pooled = [x for r in v for x in r["ttft"].values()]
        outs = sorted({x for r in v for x in r["predicted_n"]})
        cond = {
            "valid_runs": len(v),
            "runs": len(allruns[c]),
            "median_run_p50": statistics.median(r["p50"] for r in v),
            "pooled_p50": pct(pooled, 50),
            "median_run_p95": statistics.median(r["p95"] for r in v),
            "pooled_p95": pct(pooled, 95),
            "share_metrics": statistics.median(r["share_metrics"] for r in v),
            "share_timings": statistics.median(r["share_timings"] for r in v),
            "busy": statistics.median(r["busy"] for r in v),
            "output_tokens_seen": outs,
        }
        out["conditions"][c] = cond
        print(
            f"{c:28s} {len(v)}/{len(allruns[c])}  {cond['median_run_p50'] * 1000:9.0f}  "
            f"{cond['pooled_p50'] * 1000:9.0f}  {cond['median_run_p95'] * 1000:9.0f}  "
            f"{cond['pooled_p95'] * 1000:9.0f}  {cond['share_metrics']:14.4f}  "
            f"{cond['share_timings']:14.4f}  {cond['busy']:.3f}  {outs}"
        )

    o, m = out["conditions"]["shared-original-cache"], out["conditions"]["shared-metadata-cache"]
    print("\n== The headline speed-up, three ways")
    print(f"ratio of median per-run p50s : {o['median_run_p50'] / m['median_run_p50']:.2f}x")
    print(f"ratio of pooled p50s         : {o['pooled_p50'] / m['pooled_p50']:.2f}x")
    print(f"ratio of median per-run p95s : {o['median_run_p95'] / m['median_run_p95']:.2f}x")

    print("\n== Paired per-request comparisons (median TTFT per request across runs)")
    pairs = [
        ("fix", "shared-original-cache", "shared-metadata-cache"),
        ("cache_delivers_gain", "shared-metadata-nocache", "shared-metadata-cache"),
        ("P4 original+cache / fixed+nocache", "shared-metadata-nocache", "shared-original-cache"),
        ("P5 fixed+nocache / original+cache", "shared-original-cache", "shared-metadata-nocache"),
        ("negative_control", "independent-original-cache", "independent-metadata-cache"),
    ]
    for label, b, t in pairs:
        for scope, sel in (
            ("valid, all reps", lambda r: r["valid"]),
            ("valid, planned reps 1-3 only", lambda r: r["valid"] and r["rep"] <= PLANNED_REPS),
            ("ALL runs incl. invalid (non-inferential)", lambda r: True),
        ):
            bb = [r for r in allruns[b] if sel(r)]
            tt = [r for r in allruns[t] if sel(r)]
            if not bb or not tt:
                continue
            p = paired(bb, tt)
            out["pairs"][f"{label} | {scope}"] = p
            print(
                f"{label:36s} [{scope:40s}] n_runs={len(bb)}/{len(tt)} "
                f"median={p['median_ratio']:.3f} CI95(session)={p['ci'][0]:.3f}-{p['ci'][1]:.3f} "
                f"follow={p['follow_ups']:.3f} first={p['first']:.3f} faster={p['faster']:.0%}"
            )

    print("\n== Queue-free view: server-side prefill time (prompt_ms), valid runs")
    for c in CONFIGS:
        v = [r for r in allruns[c] if r["valid"]]
        allms = [x for r in v for x in r["prompt_ms"].values()]
        full = [
            r["prompt_ms"][i] / r["prompt_n"][i]
            for r in v
            for i in r["prompt_ms"]
            if r["cache_n"][i] < 20
        ]
        print(
            f"{c:28s} prefill ms median {statistics.median(allms):7.0f}   "
            f"uncached prefill ms/token median {statistics.median(full):.3f} (n={len(full)})"
        )
    fixv = [r for r in allruns["shared-metadata-cache"] if r["valid"]]
    origv = [r for r in allruns["shared-original-cache"] if r["valid"]]
    pm_o, pm_f = per_request_median(origv, "prompt_ms"), per_request_median(fixv, "prompt_ms")
    print(
        "paired prefill-time ratio, fix vs original (median over requests): "
        f"{statistics.median(pm_f[i] / pm_o[i] for i in pm_o):.3f}"
    )

    print("\n== Request-level checks (shared trace, rep 1 of each condition)")
    orig = allruns["shared-original-cache"][0]
    fix = allruns["shared-metadata-cache"][0]
    nocache = allruns["shared-metadata-nocache"][0]
    dchars = [orig["prompt_chars"][i] - fix["prompt_chars"][i] for i in orig["prompt_chars"]]
    dtok = [orig["prompt_tokens"][i] - fix["prompt_tokens"][i] for i in orig["prompt_tokens"]]
    same_fix_nocache = all(
        fix["prompt_tokens"][i] == nocache["prompt_tokens"][i] for i in fix["prompt_tokens"]
    )
    print(f"prompt chars, original minus fixed: min {min(dchars)} max {max(dchars)}")
    print(f"prompt tokens, original minus fixed: min {min(dtok)} max {max(dtok)}")
    print(f"fixed vs cache-off prompts identical in token count: {same_fix_nocache}")
    toks = list(orig["prompt_tokens"].values())
    print(
        f"original prompt tokens: min {min(toks):.0f} "
        f"median {statistics.median(toks):.0f} max {max(toks):.0f}"
    )
    print(f"original cache_n per request: {sorted(set(orig['cache_n'].values()))}")
    fu = [v for i, v in fix["prompt_n"].items() if not i.endswith("-00")]
    print(
        f"fixed, follow-up prompt_n (tokens evaluated): min {min(fu):.0f} "
        f"median {statistics.median(fu):.0f} max {max(fu):.0f}"
    )
    cons = all(
        abs(r["metrics_cached"] - sum(r["cache_n"].values())) < 0.5
        and abs(r["metrics_evaluated"] - sum(r["prompt_n"].values())) < 0.5
        for c in CONFIGS
        for r in allruns[c]
    )
    print(f"server counters == sum of per-request timings in every run: {cons}")

    dest = Path(__file__).with_name("recompute-output.json")
    dest.write_text(json.dumps(out, indent=2, default=str) + "\n")


if __name__ == "__main__":
    main()
