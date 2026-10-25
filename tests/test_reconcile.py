from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest

from relay.loadgen.reconcile import reconcile

BUCKETS = (0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0)


class Exposition:
    """Builds Prometheus text for a server and a gateway, as they'd be scraped."""

    def __init__(self) -> None:
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
            buckets=BUCKETS,
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
