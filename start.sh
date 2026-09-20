#!/usr/bin/env bash
# Start the accepted V5 demo chain in R0 order: viewer 9205, bridge, platform 9215.
# Only this repository's own PIDs are recorded. The experiment itself is NOT
# started here: the 9215 UI button (运行试验) triggers scripts/run_demo.sh.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="$HERE"
PY="$ROOT/.venv/bin/python3"
RUNTIME="$ROOT/.runtime"
PIDS="$RUNTIME/pids"
LOGS="$RUNTIME/logs"
OPEN_BROWSER=1

for arg in "$@"; do
  case "$arg" in
    --no-open) OPEN_BROWSER=0 ;;
    -h|--help) echo "usage: ./start.sh [--no-open]"; exit 0 ;;
    *) echo "ERROR: unknown argument: $arg" >&2; exit 2 ;;
  esac
done

die() { echo "ERROR: $*" >&2; exit 1; }

mkdir -p "$PIDS" "$LOGS" "$RUNTIME/activity"

[[ -x "$PY" ]] || die "missing $PY — run ./bootstrap.sh first (creates a repo-local .venv)"

echo "============================================================"
echo "MaleCNS Experiment Platform demo — start"
echo "repo: $ROOT"
echo "============================================================"

# --- asset gate -------------------------------------------------------------
set +e
"$PY" "$ROOT/assets/download_assets.py" --repo-root "$ROOT"
ASSET_RC=$?
set -e
if [[ "$ASSET_RC" -ne 0 ]]; then
  echo "ERROR: required assets are not resolvable (exit $ASSET_RC); not starting any server" >&2
  exit "$ASSET_RC"
fi

# --- helpers ----------------------------------------------------------------
component_running() { # pidfile-name ; echoes owned, live PID on stdout
  local pidfile="$PIDS/$1" pid cmd
  [[ -f "$pidfile" ]] || return 1
  pid="$(tr -d '[:space:]' < "$pidfile" 2>/dev/null || true)"
  [[ -n "$pid" ]] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  cmd="$(ps -p "$pid" -o command= 2>/dev/null || true)"
  case "$cmd" in *"$ROOT"*) echo "$pid"; return 0 ;; *) return 1 ;; esac
}

port_owner_is_repo() { # port pidfile-name
  local port="$1" pidfile="$PIDS/$2" owners pid
  owners="$(lsof -nP -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  [[ -z "$owners" ]] && return 1
  for pid in $owners; do
    case "$(ps -p "$pid" -o command= 2>/dev/null || true)" in
      *"$ROOT"*) ;;
      *) return 2 ;;
    esac
  done
  return 0
}

wait_http() { # url label tries
  local url="$1" label="$2" tries="${3:-60}" i
  for i in $(seq 1 "$tries"); do
    if curl -fsS --max-time 2 "$url" >/dev/null 2>&1; then return 0; fi
    sleep 0.1
  done
  echo "ERROR: $label did not answer at $url" >&2
  return 1
}

# --- 1) viewer 9205 ---------------------------------------------------------
if VIEWER_PID="$(component_running viewer.pid)"; then
  echo "[OK] viewer already running PID $VIEWER_PID"
else
  if port_owner_is_repo 9205 viewer.pid; then
    :
  else
    rc=$?
    if [[ "$rc" == "2" ]]; then
      echo "ERROR: port 9205 is held by another process:" >&2
      lsof -nP -iTCP:9205 -sTCP:LISTEN >&2 || true
      exit 7
    fi
  fi
  echo "[START] viewer on 9205"
  rm -f "$PIDS/viewer.pid"
  (
    cd "$ROOT/viewer"
    nohup "$PY" "$ROOT/viewer/server_viewer.py" --port 9205 >>"$LOGS/viewer.log" 2>&1 &
    echo $! > "$PIDS/viewer.pid"
  )
  wait_http "http://127.0.0.1:9205/" "viewer" || { tail -50 "$LOGS/viewer.log" >&2 || true; exit 3; }
  echo "[OK] viewer PID $(cat "$PIDS/viewer.pid")"
fi

# --- 2) activity bridge -----------------------------------------------------
if BRIDGE_PID="$(component_running bridge.pid)"; then
  echo "[OK] activity bridge already running PID $BRIDGE_PID"
else
  echo "[START] activity bridge"
  rm -f "$PIDS/bridge.pid"
  (
    cd "$ROOT"
    nohup "$PY" "$ROOT/bridge/activity_bridge_v1.py" >>"$LOGS/bridge.log" 2>&1 &
    echo $! > "$PIDS/bridge.pid"
  )
  sleep 1
  BRIDGE_PID="$(cat "$PIDS/bridge.pid")"
  kill -0 "$BRIDGE_PID" 2>/dev/null || { echo "ERROR: bridge exited; log follows:" >&2; tail -50 "$LOGS/bridge.log" >&2 || true; exit 4; }
  echo "[OK] bridge PID $BRIDGE_PID"
fi

# --- 3) experiment platform 9215 -------------------------------------------
if PLATFORM_PID="$(component_running platform.pid)"; then
  echo "[OK] platform already running PID $PLATFORM_PID"
else
  if port_owner_is_repo 9215 platform.pid; then
    :
  else
    rc=$?
    if [[ "$rc" == "2" ]]; then
      echo "ERROR: port 9215 is held by another process:" >&2
      lsof -nP -iTCP:9215 -sTCP:LISTEN >&2 || true
      exit 7
    fi
  fi
  echo "[START] experiment platform on 9215"
  rm -f "$PIDS/platform.pid"
  (
    cd "$ROOT/platform"
    nohup "$PY" "$ROOT/platform/server.py" --port 9215 >>"$LOGS/platform.log" 2>&1 &
    echo $! > "$PIDS/platform.pid"
  )
  wait_http "http://127.0.0.1:9215/api/config" "platform" || { tail -50 "$LOGS/platform.log" >&2 || true; exit 6; }
  echo "[OK] platform PID $(cat "$PIDS/platform.pid")"
fi

PLATFORM_URL="http://127.0.0.1:9215"
echo
echo "Viewer:   http://127.0.0.1:9205"
echo "Platform: $PLATFORM_URL"
echo "Runtime:  $RUNTIME"
echo
echo "The experiment is NOT running yet. Press 运行试验 in the 9215 UI (or run"
echo "scripts/run_demo.sh) to start the synchronized demo. Stop with ./stop.sh."

if [[ "$OPEN_BROWSER" == "1" ]] && [[ "$(uname -s)" == "Darwin" ]] && command -v open >/dev/null 2>&1; then
  open "$PLATFORM_URL" || echo "note: could not open $PLATFORM_URL automatically; open it manually."
else
  echo
  echo "Open this URL in a browser: $PLATFORM_URL"
fi
