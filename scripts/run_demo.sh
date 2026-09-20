#!/usr/bin/env bash
# Start the synchronized demo producer (the 9215 UI button runs this).
# The demo is never started automatically by start.sh.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="$(cd "$HERE/.." && pwd -P)"
PY="$ROOT/.venv/bin/python3"
RUNTIME="$ROOT/.runtime"
PIDS="$RUNTIME/pids"
LOGS="$RUNTIME/logs"
PIDFILE="$PIDS/demo.pid"

mkdir -p "$PIDS" "$LOGS" "$RUNTIME/activity"

[[ -x "$PY" ]] || { echo "ERROR: missing $PY — run ./bootstrap.sh first" >&2; exit 1; }

if [[ -f "$PIDFILE" ]]; then
  pid="$(tr -d '[:space:]' < "$PIDFILE" 2>/dev/null || true)"
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    cmd="$(ps -p "$pid" -o command= 2>/dev/null || true)"
    case "$cmd" in
      *"$ROOT"*) echo "[OK] demo already running PID $pid"; exit 0 ;;
    esac
  fi
  rm -f "$PIDFILE"
fi

echo "[START] synchronized demo adapter"
echo "        raw producer:   demo/demo_sync_source_raw.py"
echo "        bridge input:   .runtime/activity/source.jsonl"
echo "        viewer frames:  1200 visible neurons, 40 active/frame, 10 FPS"

printf '%s' "$$" > "$PIDFILE"
trap 'rm -f "$PIDFILE"' EXIT

cd "$ROOT"
"$PY" "$ROOT/demo/demo_sync_platform_adapter.py"
