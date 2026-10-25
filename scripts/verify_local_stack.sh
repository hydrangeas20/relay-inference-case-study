#!/usr/bin/env bash
# Phase 1 verification without Docker: run every Relay process for real, over real
# sockets, against real local backends, and record what happened.
#
#   interactive  load generator -> gateway -> llama-server (/v1/completions, /v1/chat/completions)
#   batch        load generator -> SQS -> worker -> llama-server (/v1/embeddings) -> DynamoDB
#
# AWS is moto's standalone server (an AWS API emulator), standing in for Floci, which
# needs Docker. Inference is llama.cpp with the RLY-4 synthetic-weight model: this checks
# plumbing, not speed or output quality.
#
#   LLAMA_SERVER=/path/to/llama-server scripts/verify_local_stack.sh
set -euo pipefail

LLAMA_SERVER="${LLAMA_SERVER:?set LLAMA_SERVER to the llama-server binary}"
MODEL="${MODEL:-models/relay-rly4-qwen2-synthetic.gguf}"
OUT="${OUT:-results/phase1-verification}"
mkdir -p "$OUT/logs"

PIDS=()
cleanup() { for p in "${PIDS[@]}"; do kill "$p" 2>/dev/null || true; done; wait 2>/dev/null || true; }
trap cleanup EXIT

wait_for() {
  for _ in $(seq 1 "$2"); do curl -s -o /dev/null "$1" && return 0; sleep 1; done
  echo "timed out waiting for $1" >&2; return 1
}

export AWS_ENDPOINT_URL=http://127.0.0.1:4566 AWS_REGION=us-east-1
export AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test
export GATEWAY_URL=http://127.0.0.1:8080 GATEWAY_PORT=8080 INFERENCE_BACKEND=cpu

uv run --with "moto[server]>=5.0" moto_server -H 127.0.0.1 -p 4566 >"$OUT/logs/moto.log" 2>&1 &
PIDS+=($!)
"$LLAMA_SERVER" -m "$MODEL" --host 127.0.0.1 --port 8081 -c 8192 -np 2 -t 2 --metrics \
  >"$OUT/logs/llama-generate.log" 2>&1 &
PIDS+=($!)
"$LLAMA_SERVER" -m "$MODEL" --host 127.0.0.1 --port 8082 -c 4096 -t 2 --embeddings \
  --pooling mean >"$OUT/logs/llama-embed.log" 2>&1 &
PIDS+=($!)
wait_for http://127.0.0.1:4566 60
wait_for http://127.0.0.1:8081/health 120
wait_for http://127.0.0.1:8082/health 120

uv run --no-sync relay-bootstrap

INFERENCE_BASE_URL=http://127.0.0.1:8081/v1 INFERENCE_METRICS_URL=http://127.0.0.1:8081/metrics \
  uv run --no-sync relay-gateway >"$OUT/logs/gateway.log" 2>&1 &
PIDS+=($!)
INFERENCE_BASE_URL=http://127.0.0.1:8082/v1 WORKER_POLL_WAIT_S=1 \
  uv run --no-sync relay-worker >"$OUT/logs/worker.log" 2>&1 &
PIDS+=($!)
wait_for http://127.0.0.1:8080/healthz 60
wait_for http://127.0.0.1:9101/metrics 60

# A mixed trace: completions, agent chat and indexing jobs, at a rate one CPU can serve.
# The default 80/15/5 mix can draw no indexing job in a short trace, so the mix is set
# here to guarantee all three paths are exercised.
uv run --no-sync python - "$OUT/mixed.jsonl" <<'PY'
import sys
from pathlib import Path
from relay.config import get_settings
from relay.corpus.manifest import load_lock
from relay.corpus.store import load_corpus
from relay.traces.generate import GeneratorParams, build_header, generate
from relay.traces.io import write_trace
s = get_settings(); corpus = load_corpus(load_lock(s.corpus_lock), s.corpus_dir)
params = GeneratorParams(duration_s=60, rate_rps=0.4, seed=11,
                         mix={"completion": 0.5, "agent": 0.25, "indexing": 0.25})
reqs = generate(corpus, params)
print("wrote", write_trace(Path(sys.argv[1]), build_header(corpus, params, len(reqs)), reqs))
PY

status=0
INFERENCE_BASE_URL=http://127.0.0.1:8081/v1 INFERENCE_METRICS_URL=http://127.0.0.1:8081/metrics \
  uv run --no-sync relay-loadgen --trace "$OUT/mixed.jsonl" --out-dir "$OUT" || status=$?

# Let the worker drain the queue, then record what reached DynamoDB.
for _ in $(seq 1 120); do
  left=$(uv run --no-sync python -c "
from relay import aws; from relay.config import get_settings
s=get_settings(); q=aws.client('sqs',s)
a=q.get_queue_attributes(QueueUrl=aws.queue_url(q,s),AttributeNames=['ApproximateNumberOfMessages','ApproximateNumberOfMessagesNotVisible'])['Attributes']
print(int(a['ApproximateNumberOfMessages'])+int(a['ApproximateNumberOfMessagesNotVisible']))")
  [ "$left" = "0" ] && break; sleep 1
done
uv run --no-sync python - "$OUT" <<'EOF'
import json, sys, urllib.request
from pathlib import Path
from relay import aws
from relay.config import get_settings
out = Path(sys.argv[1]); s = get_settings()
items = aws.client("dynamodb", s).scan(TableName=s.results_table_name)["Items"]
statuses: dict[str, int] = {}
for it in items:
    statuses[it["status"]["S"]] = statuses.get(it["status"]["S"], 0) + 1
worker = [l for l in urllib.request.urlopen("http://127.0.0.1:9101/metrics").read().decode().splitlines()
          if l.startswith("relay_worker_jobs_total") or l.startswith("relay_worker_chunks_total")]
trace_jobs = sum(1 for l in (out / "mixed.jsonl").read_text().splitlines()[1:] if '"indexing"' in l)
report = {"indexing_jobs_in_trace": trace_jobs, "dynamodb_items_by_status": statuses,
          "worker_metrics": worker}
(out / "batch-path.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
EOF
exit "$status"
