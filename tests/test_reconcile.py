import numpy as np
from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest

from relay.gateway.app import LATENCY_BUCKETS
from relay.loadgen.reconcile import Reconciliation, reconcile

BUCKETS = (0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0)


class Exposition:
    """Builds Prometheus text for a server and a gateway, as they'd be scraped."""

    def __init__(self, gateway_buckets: tuple[float, ...] = BUCKETS) -> None:
        self.server = CollectorRegistry()
        self.gateway = CollectorRegistry()
        self.server_ttft = Histogram(
            "vllm:time_to_first_token_seconds", "t", buckets=BUCKETS, registry=self.server
        )
        self.server_ok = Counter("vllm:request_success", "ok", registry=self.server)
        self.gw_ttft = Histogram(
            "relay_gateway_upstream_ttft_seconds",
            "t",
            ["workload"],
            buckets=gateway_buckets,
            registry=self.gateway,
        )

    def observe(self, server_s: float, gateway_s: float, workload: str = "completion") -> None:
        self.server_ttft.observe(server_s)
        self.server_ok.inc()
        self.gw_ttft.labels(workload).observe(gateway_s)

    def texts(self) -> tuple[str, str]:
        return generate_latest(self.server).decode(), generate_latest(self.gateway).decode()


def test_nested_layers_are_consistent() -> None:
    e = Exposition()
    before = e.texts()
    for i in range(50):
        e.observe(0.030 + i * 0.0002, 0.032 + i * 0.0002)
    after = e.texts()
    client = [0.035 + i * 0.0002 for i in range(50)]
    r = reconcile(client, 50, before[0], after[0], before[1], after[1])
    assert r.status == "consistent", r.problems
    assert [layer.name for layer in r.layers] == ["server", "gateway", "client"]


def test_client_faster_than_server_is_inconsistent() -> None:
    e = Exposition()
    before = e.texts()
    for _ in range(50):
        e.observe(0.4, 0.41)
    after = e.texts()
    r = reconcile([0.01] * 50, 50, before[0], after[0], before[1], after[1])
    assert r.status == "inconsistent"
    assert any("client" in p for p in r.problems)


def test_only_delta_since_before_scrape_is_used() -> None:
    e = Exposition()
    for _ in range(100):
        e.observe(0.9, 0.9)  # earlier traffic, before the run
    before = e.texts()
    for _ in range(20):
        e.observe(0.015, 0.016)
    after = e.texts()
    r = reconcile([0.018] * 20, 20, before[0], after[0], before[1], after[1])
    assert r.status == "consistent", r.problems
    assert r.layers[0].count == 20


def test_missing_server_requests_is_a_problem() -> None:
    e = Exposition()
    before = e.texts()
    for _ in range(10):
        e.observe(0.02, 0.021)
    after = e.texts()
    r = reconcile([0.03] * 12, 12, before[0], after[0], before[1], after[1])
    assert r.status == "inconsistent"


def test_extra_server_requests_is_a_note_not_a_problem() -> None:
    e = Exposition()
    before = e.texts()
    for _ in range(12):
        e.observe(0.02, 0.021)
    after = e.texts()
    r = reconcile([0.03] * 10, 10, before[0], after[0], before[1], after[1])
    assert r.status == "consistent"
    assert r.notes


def test_no_metrics_is_unavailable() -> None:
    r = reconcile([0.03] * 10, 10, None, None, None, None)
    assert r.status == "unavailable"


def _run(server: list[float], gateway: list[float], client: list[float]) -> Reconciliation:
    e = Exposition(gateway_buckets=LATENCY_BUCKETS)
    before = e.texts()
    for s, g in zip(server, gateway, strict=True):
        e.observe(s, g)
    after = e.texts()
    return reconcile(client, len(client), before[0], after[0], before[1], after[1])


def test_one_slow_request_that_nested_correctly_is_consistent() -> None:
    # The CI failure's shape: 37 requests, one delayed ~45 ms (e.g. a runner stall)
    # inside the gateway's interval. Every request has client >= gateway, but the
    # gateway's histogram p99 (90.8 ms, interpolated in its 75-100 ms bucket) exceeded
    # the client's exact p99 (64 ms) by more than the bucket width.
    gateway = [0.0335 + i * 0.00007 for i in range(36)] + [0.077]
    client = [g + 0.002 for g in gateway[:35]] + [0.038, 0.0787]
    assert all(c >= g for c, g in zip(client, gateway, strict=True))
    r = _run([g - 0.001 for g in gateway], gateway, client)
    layers = {layer.name: layer for layer in r.layers}
    assert layers["gateway"].quantiles["p99"] > layers["client"].quantiles["p99"] + 0.025
    assert r.status == "consistent", r.problems


def test_client_faster_than_gateway_in_the_tail_is_inconsistent() -> None:
    # One client TTFT is below every gateway TTFT: impossible under nesting. The
    # quantiles can't see it (p50/p95/p99 barely move); the bucket counts can.
    gateway = [0.034] * 37
    client = [0.036] * 36 + [0.020]
    r = _run([0.033] * 37, gateway, client)
    assert r.status == "inconsistent"
    assert any("client" in p and "gateway" in p for p in r.problems)


def test_per_request_nesting_is_never_flagged() -> None:
    # Whatever the latency distribution or sample size, server <= gateway <= client per
    # request must reconcile. Heavy-tailed stalls land in random layers.
    rng = np.random.default_rng(0)
    for _ in range(200):
        n = int(rng.integers(5, 80))
        server = 0.03 + rng.exponential(0.002, n)
        gateway = server + rng.exponential(0.001, n)
        client = gateway + 0.001 + rng.exponential(0.001, n)
        stall = rng.uniform(0.02, 0.4, n) * (rng.random(n) < 0.1)
        layer = rng.integers(0, 3, n)  # stall inside server, gateway-only or client-only span
        server = server + stall * (layer == 0)
        gateway = gateway + stall * (layer <= 1)
        client = client + stall
        r = _run(server.tolist(), gateway.tolist(), client.tolist())
        assert r.status == "consistent", r.problems
