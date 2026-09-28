"""Preregistered prompt-size fidelity test (docs/validation/phase-2-preregistration.md §8).

Usage: uv run python analysis/validate_prompt_fidelity.py

Generates the preregistered evaluation trace, sends every completion through Relay's
gateway (in-process, against a fake inference server), records the built prompt size
the gateway reports (X-Relay-Prompt-Chars, MEASURED), and compares built sizes of
representable targets with the training-derived Azure size sample. Targets below the
template minimum are kept, flagged and reported separately; they are excluded from
the pass/fail test. Needs the code corpus (make corpus), not the raw Azure trace.
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
from relay.traffic.check import ks_critical, ks_statistic, prompt_size_report
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

OUT = Path("analysis/results/validation-prompt-fidelity.json")


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
    # A common truncation point T for both samples: the largest per-request template
    # minimum in the trace. Every target at or above T is representable for any request,
    # so conditioning both sides on ">= T" compares like with like.
    per_request_min = [
        template_overhead_chars(r.req_id, corpus.get(r.file.repo, r.file.path), [])
        + MIN_PREFIX_CHARS
        for r in comps
    ]
    min_chars = max(per_request_min)
    rep = [r for r in comps if round(r.target_prompt_tokens * cpt) >= min_chars]
    assert not any(r.below_template_minimum for r in rep)
    built_tok = np.array([built[r.req_id] / cpt for r in rep])
    with Path(settings.traffic_model.parent / "reference" / "azure_code_sizes.csv").open() as fh:
        azure = np.array([int(x["context_tokens"]) for x in csv.DictReader(fh)], dtype=float)
    azure_rep = azure[np.round(azure * cpt) >= min_chars]
    d = ks_statistic(built_tok, azure_rep)
    crit = ks_critical(len(built_tok), len(azure_rep))
    below = [r for r in comps if r.below_template_minimum]
    result = {
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "trace": {"spec_id": header.spec_id, "generator_sha256": header.generator_sha256,
                  "traffic_model_sha256": header.traffic_model_sha256, **cfg.FIDELITY_TRACE},
        "chars_per_token": cpt,
        "completions_generated": report.completions + len(rejected),
        "rejected_by_gateway": {
            "count": len(rejected),
            "statuses": sorted(set(rejected.values())),
            "note": "excluded from all size statistics below",
        },
        "completions": report.completions,
        "conditioning": "both samples restricted to targets >= T, the largest per-request "
        "template minimum in the trace",
        "T_chars": min_chars,
        "T_tokens": round(min_chars / cpt, 1),
        "per_request_minimum_chars_range": [min(per_request_min), max(per_request_min)],
        "representable_at_or_above_T": len(rep),
        "ks": {"statistic": round(d, 5), "critical_5pct": round(crit, 5),
               "n_built": len(built_tok), "n_azure": len(azure_rep), "passed": d < crit},
        "built_vs_expected_mismatches": report.expected_mismatch,
        "below_minimum": {
            "count": len(below),
            "fraction_of_all_targets": round(report.below_minimum_fraction, 5),
            "target_tokens_quantiles_10_50_90": np.percentile([r.target_prompt_tokens for r in below], [10, 50, 90]).tolist() if below else [],
            "built_tokens_quantiles_10_50_90": np.percentile([built[r.req_id] / cpt for r in below], [10, 50, 90]).round(1).tolist() if below else [],
            "inflation_quantiles_10_50_90": np.percentile(report.below_minimum_inflation, [10, 50, 90]).round(3).tolist() if below else [],
        },
        "representable_built_vs_target_ratio_quantiles_1_50_99": np.percentile(
            [built[r.req_id] / (r.target_prompt_tokens * cpt) for r in rep], [1, 50, 99]).round(4).tolist(),
    }  # fmt: skip
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
