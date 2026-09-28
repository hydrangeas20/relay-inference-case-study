"""Prompt-size fidelity test (preregistration §8, as amended by Amendment 1, A1.3).

Usage: uv run python analysis/validate_prompt_fidelity.py

Generates the preregistered evaluation trace, sends every completion through Relay's
gateway (in-process, against a fake inference server), records the built prompt size
the gateway reports (X-Relay-Prompt-Chars, MEASURED), and compares built sizes of
representable targets with the training-derived Azure size sample.

Representability is judged per request (A1.3): request i is included if its target is
at least m_i, its own structural minimum. The reference is the matched mixture of Azure
CDFs conditioned on >= m_i. Structurally unrepresentable targets are kept, flagged and
reported separately. Needs the code corpus (make corpus), not the raw Azure trace.

Writes analysis/results/validation-prompt-fidelity-amended.json. The first result
(global 636-character cutoff, observed before the amendment) stays in
validation-prompt-fidelity.json and is never overwritten; this script also recomputes
it from the same deterministic trace as a reproduction check.
"""

from __future__ import annotations

import asyncio
import csv
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx
import numpy as np

from relay import prompts
from relay.config import get_settings
from relay.corpus.manifest import load_lock
from relay.corpus.store import load_corpus
from relay.gateway.app import PROMPT_CHARS_HEADER, create_app
from relay.traces.schema import CompletionRequest
from relay.traffic.check import (
    ks_critical,
    ks_mixture_statistic,
    ks_statistic,
    prompt_size_report,
)
from relay.traffic.generate import (
    MIN_PREFIX_CHARS,
    TraceSpec,
    generate_traffic,
    template_overhead_chars,
)
from relay.traffic.model import load_model

import validation_config as cfg

sys.path.insert(0, "tests")
from fakes import FakeConfig, create_fake_inference  # noqa: E402

ORIGINAL = Path("analysis/results/validation-prompt-fidelity.json")  # never written here
OUT = Path("analysis/results/validation-prompt-fidelity-amended.json")


async def measure(payloads: list[dict[str, object]]) -> tuple[dict[str, int], dict[str, int]]:
    settings = get_settings().model_copy(update={"inference_base_url": "http://inference/v1"})
    fake = create_fake_inference(FakeConfig(ttft_s=0.0, itl_s=0.0, chunks=1))
    app = create_app(settings, transport=httpx.ASGITransport(app=fake))
    built: dict[str, int] = {}
    rejected: dict[str, int] = {}  # request_id -> HTTP status, for requests the gateway refused
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://gw") as c:
        for p in payloads:
            r = await c.post("/v1/complete", json=p)
            if r.status_code == 200:
                built[str(p["request_id"])] = int(r.headers[PROMPT_CHARS_HEADER])
            else:
                rejected[str(p["request_id"])] = r.status_code
    return built, rejected


def main() -> None:
    settings = get_settings()
    model = load_model(settings.traffic_model)
    corpus = load_corpus(load_lock(settings.corpus_lock), settings.corpus_dir)
    f = cfg.FIDELITY_TRACE
    h, m = str(f["start"]).split(":")
    spec = TraceSpec(kind="window", peak_rps=float(f["peak_rps"]), seed=int(f["seed"]),
                     start_utc_s=int(h) * 3600 + int(m) * 60, duration_s=float(f["minutes"]) * 60,
                     scenario="edge")  # fmt: skip
    header, requests = generate_traffic(model, corpus, spec)
    comps = [r for r in requests if isinstance(r, CompletionRequest)]
    built, rejected = asyncio.run(measure([prompts.completion_payload(r, corpus) for r in comps]))
    comps = [r for r in comps if r.req_id in built]
    report = prompt_size_report(comps, built, model.chars_per_token)

    cpt = model.chars_per_token
    # A1.3 step 1: each request's own structural minimum (no context files, minimum prefix).
    m = {r.req_id: template_overhead_chars(r.req_id, corpus.get(r.file.repo, r.file.path), [])
         + MIN_PREFIX_CHARS for r in comps}  # fmt: skip
    target_chars = {r.req_id: round(r.target_prompt_tokens * cpt) for r in comps}
    inc = [r for r in comps if target_chars[r.req_id] >= m[r.req_id]]
    below = [r for r in comps if target_chars[r.req_id] < m[r.req_id]]
    flag_mismatch = sum(r.below_template_minimum != (r in below) for r in comps)
    with Path(settings.traffic_model.parent / "reference" / "azure_code_sizes.csv").open() as fh:
        azure_tok = np.array([int(x["context_tokens"]) for x in csv.DictReader(fh)], dtype=float)
    azure_chars = np.round(azure_tok * cpt)

    # A1.3 steps 4-5: matched-mixture reference, in characters (the conditioning's units).
    built_chars = np.array([built[r.req_id] for r in inc], dtype=float)
    bounds = np.array([m[r.req_id] for r in inc], dtype=float)
    d = ks_mixture_statistic(built_chars, azure_chars, bounds)
    m_ref = int(np.sum(azure_chars >= bounds.min()))
    crit = ks_critical(len(built_chars), m_ref)
    ratio = np.array([built[r.req_id] / target_chars[r.req_id] for r in inc])

    # Reproduction of the original (pre-amendment) global-cutoff computation.
    t_global = max(m.values())
    rep = [r for r in comps if target_chars[r.req_id] >= t_global]
    d0 = ks_statistic(np.array([built[r.req_id] / cpt for r in rep]),
                      azure_tok[azure_chars >= t_global])  # fmt: skip
    original = json.loads(ORIGINAL.read_text())

    result = {
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "procedure": "preregistration §8 as amended by Amendment 1 (A1.3): per-request "
        "representability, matched-mixture reference",
        "trace": {"spec_id": header.spec_id, "generator_sha256": header.generator_sha256,
                  "traffic_model_sha256": header.traffic_model_sha256, **cfg.FIDELITY_TRACE},
        "chars_per_token": cpt,
        "completions_generated": report.completions + len(rejected),
        "rejected_by_gateway": {"count": len(rejected), "statuses": sorted(set(rejected.values())),
                                "note": "excluded from all size statistics below"},
        "completions": report.completions,
        "per_request_minimum_chars_range": [min(m.values()), max(m.values())],
        "included_representable": len(inc),
        "generator_flag_disagreements": flag_mismatch,
        "ks": {"statistic": round(d, 5), "critical_5pct": round(crit, 5),
               "n_built": len(inc), "m_azure_at_or_above_smallest_minimum": m_ref,
               "passed": d < crit},
        "built_vs_expected_mismatches": report.expected_mismatch,
        "included_built_vs_target_ratio_quantiles_1_50_99": np.percentile(ratio, [1, 50, 99]).round(4).tolist(),
        "included_min_ratio": round(float(ratio.min()), 4),
        "included_more_than_0.5pct_short": int(np.sum(ratio < 0.995)),
        "structurally_unrepresentable": {
            "count": len(below),
            "fraction_of_all_targets": round(len(below) / len(comps), 5),
            "target_tokens_quantiles_10_50_90": np.percentile([r.target_prompt_tokens for r in below], [10, 50, 90]).tolist(),
            "built_tokens_quantiles_10_50_90": np.percentile([built[r.req_id] / cpt for r in below], [10, 50, 90]).round(1).tolist(),
            "inflation_quantiles_10_50_90": np.percentile([built[r.req_id] / target_chars[r.req_id] for r in below], [10, 50, 90]).round(3).tolist(),
        },
        "original_result": {
            "file": str(ORIGINAL),
            "observed_before_amendment": True,
            "ks": original["ks"],
            "T_chars": original["T_chars"],
            "reproduced_now": {"T_chars": t_global, "n_built": len(rep),
                               "statistic": round(d0, 5),
                               "matches_original": t_global == original["T_chars"]
                               and len(rep) == original["ks"]["n_built"]
                               and round(d0, 5) == original["ks"]["statistic"]},
            "targets_included_now_but_excluded_by_T": len(inc) - len(rep),
        },
    }  # fmt: skip
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
