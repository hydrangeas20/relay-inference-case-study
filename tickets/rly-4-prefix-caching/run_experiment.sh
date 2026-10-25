#!/usr/bin/env bash
# RLY-4 experiment: replay identical traces against a real llama.cpp server (CPU),
# changing one thing per configuration. Results are tagged source=cpu.
#
#   LLAMA_SERVER=/path/to/llama-server MODEL=models/relay-rly4-qwen2-synthetic.gguf \
#     tickets/rly-4-prefix-caching/run_experiment.sh [REPS]
#
# Each run starts a fresh server, so no run inherits another run's KV cache. The server
# is pinned to CPU 0 with one thread; gateway and load generator share CPU 1, so the
# client side can't steal compute from prefill (and the self-check would catch it if it
# fell behind).
set -euo pipefail

REPS="${1:-3}"
LLAMA_SERVER="${LLAMA_SERVER:?set LLAMA_SERVER to the llama-server binary}"
MODEL="${MODEL:-models/relay-rly4-qwen2-synthetic.gguf}"
OUT="${OUT:-results/rly-4}"
SERVER_PORT=8081
GATEWAY_PORT=8080
SERVER_CPU="${SERVER_CPU:-0}"
CLIENT_CPU="${CLIENT_CPU:-1}"

# name | trace | gateway template | server prompt-cache flag
CONFIGS=(
  "shared-original-cache|traces/rly4-shared.jsonl|original|--cache-prompt"
  "shared-metadata-cache|traces/rly4-shared.jsonl|metadata|--cache-prompt"
  "shared-metadata-nocache|traces/rly4-shared.jsonl|metadata|--no-cache-prompt"
  "independent-original-cache|traces/rly4-independent.jsonl|original|--cache-prompt"
  "independent-metadata-cache|traces/rly4-independent.jsonl|metadata|--cache-prompt"
)

wait_for() {  # url, seconds
  for _ in $(seq 1 "$2"); do curl -sf "$1" >/dev/null 2>&1 && return 0; sleep 1; done
  echo "timed out waiting for $1" >&2; return 1
}

SERVER_PID=""; GATEWAY_PID=""
stop_all() {
  [ -n "$GATEWAY_PID" ] && kill "$GATEWAY_PID" 2>/dev/null && wait "$GATEWAY_PID" 2>/dev/null || true
  [ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null && wait "$SERVER_PID" 2>/dev/null || true
  SERVER_PID=""; GATEWAY_PID=""
}
trap stop_all EXIT

mkdir -p "$OUT"
for rep in $(seq 1 "$REPS"); do
  for cfg in "${CONFIGS[@]}"; do
    IFS='|' read -r name trace template cacheflag <<<"$cfg"
    dir="$OUT/$name"; mkdir -p "$dir/server"
    tag="rep${rep}"
    server_cmd=(taskset -c "$SERVER_CPU" "$LLAMA_SERVER" -m "$MODEL" --host 127.0.0.1
      --port "$SERVER_PORT" -c 4096 -np 1 -t 1 -tb 1 --metrics "$cacheflag")
    "${server_cmd[@]}" >"$dir/server/$tag.log" 2>&1 &
    SERVER_PID=$!
    wait_for "http://127.0.0.1:$SERVER_PORT/health" 120

    PROMPT_TEMPLATE="$template" INFERENCE_BACKEND=cpu \
    INFERENCE_BASE_URL="http://127.0.0.1:$SERVER_PORT/v1" \
    INFERENCE_METRICS_URL="http://127.0.0.1:$SERVER_PORT/metrics" \
    GATEWAY_PORT="$GATEWAY_PORT" \
      taskset -c "$CLIENT_CPU" uv run --no-sync relay-gateway >"$dir/server/$tag.gateway.log" 2>&1 &
    GATEWAY_PID=$!
    wait_for "http://127.0.0.1:$GATEWAY_PORT/healthz" 60

    printf '%s\n' "${server_cmd[*]}" >"$dir/server/$tag.cmd"
    curl -s "http://127.0.0.1:$SERVER_PORT/metrics" >"$dir/server/$tag.metrics.before.txt"
    echo "== $name $tag (template=$template, $cacheflag)"
    INFERENCE_BACKEND=cpu GATEWAY_URL="http://127.0.0.1:$GATEWAY_PORT" \
    INFERENCE_BASE_URL="http://127.0.0.1:$SERVER_PORT/v1" \
    INFERENCE_METRICS_URL="http://127.0.0.1:$SERVER_PORT/metrics" \
      taskset -c "$CLIENT_CPU" uv run --no-sync relay-loadgen --trace "$trace" --out-dir "$dir" \
      || echo "   run marked INVALID (kept and reported, never dropped silently)"
    curl -s "http://127.0.0.1:$SERVER_PORT/metrics" >"$dir/server/$tag.metrics.after.txt"
    stop_all
  done
done
