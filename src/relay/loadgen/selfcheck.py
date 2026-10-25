"""Is the load generator itself the bottleneck? (methodology rule 4)

A run is invalid if the generator couldn't send requests on schedule. Two checks:

1. Rate: achieved send rate must be within RATE_SHORTFALL_LIMIT of the intended rate.
2. CPU: the generator is a single asyncio thread, so its CPU use is measured as a
   percentage of one core. If p95 CPU reaches CPU_SATURATION_PCT, the event loop
   was saturated and send times can't be trusted.

Send lag (actual minus intended send time) is reported for every run but doesn't
decide validity on its own.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from relay.loadgen.stats import percentiles

RATE_SHORTFALL_LIMIT = 0.02  # methodology rule 4
CPU_SATURATION_PCT = 90.0  # percent of one core; see docs/decisions/0003


@dataclass
class SelfCheck:
    valid: bool
    reasons: list[str] = field(default_factory=list)
    intended_rate_rps: float | None = None
    achieved_rate_rps: float | None = None
    rate_shortfall: float | None = None
    cpu_pct: dict[str, float | None] = field(default_factory=dict)
    send_lag_s: dict[str, float | None] = field(default_factory=dict)


def _rate(times: Sequence[float]) -> float | None:
    if len(times) < 2:
        return None
    span = max(times) - min(times)
    return (len(times) - 1) / span if span > 0 else None


def check(
    intended_send: Sequence[float],
    actual_send: Sequence[float],
    cpu_samples_pct: Sequence[float],
) -> SelfCheck:
    if len(intended_send) != len(actual_send):
        raise ValueError("intended and actual send times must align")
    result = SelfCheck(valid=True)
    result.intended_rate_rps = _rate(intended_send)
    result.achieved_rate_rps = _rate(actual_send)
    result.send_lag_s = percentiles(
        [a - i for i, a in zip(intended_send, actual_send, strict=True)]
    )
    result.cpu_pct = percentiles(cpu_samples_pct)

    if result.intended_rate_rps and result.achieved_rate_rps:
        shortfall = 1.0 - result.achieved_rate_rps / result.intended_rate_rps
        result.rate_shortfall = shortfall
        if shortfall > RATE_SHORTFALL_LIMIT:
            result.valid = False
            result.reasons.append(
                f"achieved rate {result.achieved_rate_rps:.2f} rps is {shortfall:.1%} below "
                f"intended {result.intended_rate_rps:.2f} rps (limit {RATE_SHORTFALL_LIMIT:.0%})"
            )
    else:
        result.reasons.append("too few requests to check send rate")

    cpu_p95 = result.cpu_pct.get("p95")
    if cpu_p95 is None:
        result.valid = False
        result.reasons.append("no CPU samples recorded; can't rule out a saturated generator")
    elif cpu_p95 >= CPU_SATURATION_PCT:
        result.valid = False
        result.reasons.append(
            f"generator CPU p95 {cpu_p95:.0f}% of one core (limit {CPU_SATURATION_PCT:.0f}%)"
        )
    return result
