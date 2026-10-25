"""Reconcile client-side and server-side TTFT (decision 3C).

Three layers measure time to first token, each nested inside the next:

  server  vllm:time_to_first_token_seconds        (inference server, histogram)
  gateway relay_gateway_upstream_ttft_seconds     (gateway -> server, histogram)
  client  per-request timings from the load gen   (user-perceived, exact samples)

An outer layer's interval contains the inner layer's interval for the same request,
so per request outer >= inner. Only the client has per-request samples; the other
layers are histograms. What per-request nesting implies for them, exactly and at any
sample size, is stochastic dominance at every bucket bound both layers share:

  count(outer <= b) <= count(inner <= b)

(the inner layer may also hold extra requests, e.g. other traffic, which only raise
its counts). The client's exact samples are counted at the inner histogram's bounds.
A violation means some measurement is wrong.

Quantiles are reported for reading but are not compared: a Prometheus-style
histogram estimate interpolates inside a bucket and can land anywhere in it, and
with a few dozen requests a p99 is decided by the slowest one or two, so comparing
p99 against p99 flags runs in which every request nested correctly.

The request count seen by the server must also match what the client sent, or
other traffic polluted the server-side numbers.

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


def _counts_at(values: Sequence[float], bounds: Iterable[float]) -> Buckets:
    """Cumulative counts of exact samples at histogram bounds (`le` semantics: v <= bound)."""
    return {b: float(sum(1 for v in values if v <= b)) for b in bounds}


def _dominance_problem(
    inner: str, inner_cum: Buckets, outer: str, outer_cum: Buckets
) -> str | None:
    """Report bounds where the outer layer has more requests at or below them than the inner."""
    bad = [b for b in sorted(set(inner_cum) & set(outer_cum)) if outer_cum[b] > inner_cum[b]]
    if not bad:
        return None
    b = bad[0]
    where = "in total" if math.isinf(b) else f"at or below {b * 1000:g} ms"
    return (
        f"{outer} has {outer_cum[b]:.0f} requests {where} but {inner} only {inner_cum[b]:.0f}; "
        f"per request {outer} >= {inner}, so this can't happen "
        f"({len(bad)} bound(s) violated, first shown)"
    )


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
    cumulative: dict[str, Buckets] = {}
    if gateway_before is not None and gateway_after is not None:
        streaming = {"workload": {"completion", "agent"}}
        gw_buckets = diff(
            histogram_buckets(gateway_after, GATEWAY_TTFT, streaming),
            histogram_buckets(gateway_before, GATEWAY_TTFT, streaming),
        )
        gateway = _histogram_layer("gateway", gw_buckets)
        cumulative["gateway"] = dict(gw_buckets)
    if server_before is not None and server_after is not None:
        srv_buckets = diff(
            histogram_buckets(server_after, SERVER_TTFT),
            histogram_buckets(server_before, SERVER_TTFT),
        )
        server = _histogram_layer("server", srv_buckets)
        cumulative["server"] = dict(srv_buckets)
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
        inner_cum = cumulative[inner.name]
        outer_cum = (
            _counts_at(client_ttft_s, inner_cum) if outer is client else cumulative[outer.name]
        )
        if not any(math.isfinite(b) for b in set(inner_cum) & set(outer_cum)):
            notes.append(f"{inner.name} and {outer.name} histograms share no bucket bounds")
        problem = _dominance_problem(inner.name, inner_cum, outer.name, outer_cum)
        if problem:
            problems.append(problem)
    status = "inconsistent" if problems else "consistent"
    return Reconciliation(status, layers, problems, notes)
