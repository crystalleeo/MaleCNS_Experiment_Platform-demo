#!/usr/bin/env bash
# MaleCNS Experiment Platform demo — bootstrap (idempotent, macOS-first).
#
# Does exactly this, in order:
#   1. environment checks (macOS, Python, git, curl)
#   2. asset resolution gate (fails deterministically with ASSET_URL_UNRESOLVED
#      if a required project-derived asset has no published stable URL yet)
#   3. repo-local .venv creation + minimal dependency install (no sudo, no global pip)
#   4. asset verification + preflight healthcheck (imports, writable runtime dirs)
#
# It never starts a server, never downloads complete MaleCNS data, and never
# touches a source project or a developer machine path.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="$HERE"
VENV="$ROOT/.venv"
PY="$VENV/bin/python3"
SYSTEM_PY="${MALECNS_SYSTEM_PYTHON:-python3}"
START_AFTER=0

for arg in "$@"; do
  case "$arg" in
    --start) START_AFTER=1 ;;
    -h|--help) echo "usage: ./bootstrap.sh [--start]"; exit 0 ;;
    *) echo "ERROR: unknown argument: $arg" >&2; exit 2 ;;
  esac
done

say() { echo "$@"; }
die() { echo "ERROR: $*" >&2; exit 1; }

say "============================================================"
say "MaleCNS Experiment Platform demo — bootstrap"
say "repo: $ROOT"
say "============================================================"

# --- 1) environment ---------------------------------------------------------
command -v "$SYSTEM_PY" >/dev/null 2>&1 || die "python3 not found; install Python 3.10+ first"
"$SYSTEM_PY" "$ROOT/scripts/check_environment.py" || die "environment check failed"

# --- 2) asset gate (stdlib only; runs before any install so the failure is
#        deterministic and offline-safe) --------------------------------------
say
say "[1/4] resolving required release assets"
set +e
"$SYSTEM_PY" "$ROOT/assets/download_assets.py" --repo-root "$ROOT"
ASSET_RC=$?
set -e
if [[ "$ASSET_RC" -ne 0 ]]; then
  say ""
  if [[ "$ASSET_RC" -eq 3 ]]; then
    say "R3 BLOCKED: a required project-derived release asset has no stable URL yet."
    say "  The asset manifest records url_status=\"pending_project_release\" (A3/A4/A5)."
    say "  R7 will attach the stable release URL; bootstrap then completes unchanged."
  fi
  die "cannot resolve required assets (exit $ASSET_RC); nothing was started"
fi

# --- 3) repo-local virtualenv + minimal dependencies ------------------------
say
say "[2/4] preparing repo-local virtualenv (.venv)"
if [[ ! -x "$PY" ]]; then
  "$SYSTEM_PY" -m venv "$VENV" || die "python -m venv failed for $VENV"
  say "      created $VENV"
else
  say "      reusing $VENV"
fi

say "[3/4] installing minimal demo dependencies (repo-local, no sudo)"
"$PY" -m pip install --disable-pip-version-check --quiet -r "$ROOT/requirements.txt" \
  || die "pip install failed; check network access or a local wheel cache"
say "      dependencies installed: numpy, pyarrow, fastapi, uvicorn"

# --- 4) verification --------------------------------------------------------
say
say "[4/4] verifying assets and preflight healthcheck"
"$PY" "$ROOT/assets/verify_assets.py" --repo-root "$ROOT" || die "asset verification failed"
"$PY" "$ROOT/scripts/healthcheck.py" --repo-root "$ROOT" --skip-ports \
  || die "preflight healthcheck failed"

say
say "Bootstrap complete."

if [[ "$START_AFTER" == "1" ]]; then
  say "Starting release-local processes (assets resolved): viewer 9205, bridge, platform 9215"
  exec "$ROOT/start.sh"
fi

say "Next steps:"
say "  ./start.sh     # viewer 9205 + bridge + platform 9215 (experiment stays idle)"
say "  open http://127.0.0.1:9215 and press 运行试验 to run the synchronized demo"
say "  ./stop.sh      # release-local shutdown"
say "  (or run ./bootstrap.sh --start next time to bootstrap and start in one step)"
