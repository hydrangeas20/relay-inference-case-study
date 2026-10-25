"""Reconcile client-side and server-side TTFT (decision 3C).

Three layers measure time to first token, each nested inside the next:

  server  vllm:time_to_first_token_seconds        (inference server, histogram)
  gateway relay_gateway_upstream_ttft_seconds     (gateway -> server, histogram)
  client  per-request timings from the load gen   (user-perceived, exact samples)

An outer layer includes everything an inner layer measures, so at every quantile
outer >= inner, allowing for the inner histogram's bucket width. A violation means
some measurement is wrong. The request count seen by the server must also match
what the client sent, or other traffic polluted the server-side numbers.

This module reports disagreements; it doesn't invalidate the run. What to do about
a disagreement is recorded in docs/decisions/0003 as an open question.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from prometheus_client.parser import text_string_to_metric_families

from relay.loadgen.stats import bucket_width_at, histogram_quantile, percentiles

SERVER_TTFT = "vllm:time_to_first_token_seconds"
SERVER_SUCCESS = "vllm:request_success_total"
GATEWAY_TTFT = "relay_gateway_upstream_ttft_seconds"
QUANTILES = (0.50, 0.95, 0.99)

Buckets = dict[float, float]  # upper bound -> cumulative count


def histogram_buckets(text: str, metric: str, labels: dict[str, set[str]] | None = None) -> Buckets:
    """Cumulative buckets of a histogram, summed across all label sets that match `labels`."""
    out: Buckets = {}
    for family in text_string_to_metric_families(text):
        for sample in family.samples:
            if sample.name != f"{metric}_bucket":
                continue
            if labels and any(sample.labels.get(k) not in v for k, v in labels.items()):
                continue
            bound = float(sample.labels["le"])
            out[bound] = out.get(bound, 0.0) + sample.value
    return out


def counter_total(text: str, metric: str) -> float | None:
    total: float | None = None
    for family in text_string_to_metric_families(text):
        for sample in family.samples:
            if sample.name == metric:
                total = (total or 0.0) + sample.value
    return total


def diff(after: Buckets, before: Buckets) -> list[tuple[float, float]]:
    return sorted((b, after[b] - before.get(b, 0.0)) for b in after)


@dataclass
class Layer:
    name: str
    count: float | None
    quantiles: dict[str, float | None]
    resolution_s: dict[str, float | None] = field(default_factory=dict)


@dataclass
class Reconciliation:
    status: str  # "consistent" | "inconsistent" | "unavailable"
    layers: list[Layer]
    problems: list[str]
    notes: list[str] = field(default_factory=list)


def _histogram_layer(name: str, buckets: list[tuple[float, float]]) -> Layer | None:
    if not buckets or not any(math.isinf(b) for b, _ in buckets):
        return None
    total = dict(buckets)[math.inf]
    qs: dict[str, float | None] = {}
    res: dict[str, float | None] = {}
    bounds = [b for b, _ in buckets]
    for q in QUANTILES:
        key = f"p{q * 100:g}"
        value = histogram_quantile(q, buckets)
        qs[key] = value
        res[key] = bucket_width_at(value, bounds) if value is not None else None
    return Layer(name=name, count=total, quantiles=qs, resolution_s=res)


def reconcile(
    client_ttft_s: Sequence[float],
    client_streamed: int,
    server_before: str | None,
    server_after: str | None,
    gateway_before: str | None,
    gateway_after: str | None,
) -> Reconciliation:
    pcts = percentiles(client_ttft_s, [q * 100 for q in QUANTILES])
    client = Layer("client", float(len(client_ttft_s)), pcts, {k: 0.0 for k in pcts})
    problems: list[str] = []
    notes: list[str] = []

    gateway = server = None
    if gateway_before is not None and gateway_after is not None:
        streaming = {"workload": {"completion", "agent"}}
        gateway = _histogram_layer(
            "gateway",
            diff(
                histogram_buckets(gateway_after, GATEWAY_TTFT, streaming),
                histogram_buckets(gateway_before, GATEWAY_TTFT, streaming),
            ),
        )
    if server_before is not None and server_after is not None:
        server = _histogram_layer(
            "server",
            diff(
                histogram_buckets(server_after, SERVER_TTFT),
                histogram_buckets(server_before, SERVER_TTFT),
            ),
        )
        before_n = counter_total(server_before, SERVER_SUCCESS)
        after_n = counter_total(server_after, SERVER_SUCCESS)
        if before_n is not None and after_n is not None:
            served = after_n - before_n
            if served < client_streamed:
                problems.append(
                    f"server completed {served:.0f} requests but the client streamed "
                    f"{client_streamed} successfully"
                )
            elif served > client_streamed:
                notes.append(
                    f"server completed {served:.0f} requests vs {client_streamed} streamed by the "
                    "client; the extra are other traffic (e.g. indexing embeddings), so "
                    "server-side histograms may include requests the client didn't time"
                )

    ordered: Iterable[Layer] = [x for x in (server, gateway) if x is not None]
    layers = [*ordered, client]
    if len(layers) == 1:
        return Reconciliation("unavailable", layers, [], ["no server or gateway metrics captured"])

    for inner, outer in zip(layers, layers[1:], strict=False):
        for key, inner_v in inner.quantiles.items():
            outer_v = outer.quantiles.get(key)
            if inner_v is None or outer_v is None:
                continue
            tolerance = inner.resolution_s.get(key) or 0.0
            if outer_v + tolerance < inner_v:
                problems.append(
                    f"{outer.name} {key} {outer_v * 1000:.1f} ms is below {inner.name} "
                    f"{key} {inner_v * 1000:.1f} ms (tolerance {tolerance * 1000:.1f} ms)"
                )
    status = "inconsistent" if problems else "consistent"
    return Reconciliation(status, layers, problems, notes)
