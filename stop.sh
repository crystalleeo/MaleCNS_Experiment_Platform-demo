#!/usr/bin/env bash
# Safe release-local shutdown.
#
# Only PIDs recorded by THIS repository under .runtime/pids/ are signalled, and
# only after the live process command is confirmed to point into this repo. There
# are no pattern-based termination commands and no port-based blanket kills.
# Committed files, downloaded assets and experiment results are left untouched.
set +e

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="$HERE"
PIDS="$ROOT/.runtime/pids"
QUIET=0

for arg in "$@"; do
  case "$arg" in
    --quiet) QUIET=1 ;;
    -h|--help) echo "usage: ./stop.sh [--quiet]"; exit 0 ;;
  esac
done

say() { [[ "$QUIET" == "1" ]] || echo "$@"; }

# Give the /api/shutdown caller time to receive its JSON response first.
sleep "${MALECNS_STOP_DELAY:-0.6}"

owned_by_repo() { # pid
  local pid="$1" cmd
  [[ -n "$pid" ]] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  cmd="$(ps -p "$pid" -o command= 2>/dev/null || true)"
  case "$cmd" in *"$ROOT"*) return 0 ;; *) return 1 ;; esac
}

signal_pid() { # pid signal
  local pid="$1" sig="$2" pgid
  owned_by_repo "$pid" || return 0
  pgid="$(ps -p "$pid" -o pgid= 2>/dev/null | tr -d ' ')"
  if [[ -n "$pgid" ]] && [[ "$pgid" == "$pid" ]]; then
    # Process-group leader (demo runs are started with start_new_session=True):
    # terminate exactly that group so the adapter and its raw producer both stop.
    kill -"$sig" -"$pgid" 2>/dev/null
  else
    kill -"$sig" "$pid" 2>/dev/null
  fi
}

RECORDED=""

collect_and_term() { # pidfile-name
  local name="$1" pidfile="$PIDS/$1.pid" pid
  [[ -f "$pidfile" ]] || return 0
  pid="$(tr -d '[:space:]' < "$pidfile" 2>/dev/null || true)"
  rm -f "$pidfile"
  [[ -n "$pid" ]] || return 0
  if owned_by_repo "$pid"; then
    RECORDED="$RECORDED $name:$pid"
    say "[STOP] $name PID $pid"
    signal_pid "$pid" TERM
  else
    say "[SKIP] $name: recorded PID $pid is not a live process of this repo"
  fi
}

# R0 shutdown order: demo producers, bridge, viewer, platform last.
for component in demo_source demo bridge viewer platform; do
  collect_and_term "$component"
done

sleep 0.5

# Escalate only for PIDs that are still alive and still belong to this repo.
for entry in $RECORDED; do
  name="${entry%%:*}"
  pid="${entry##*:}"
  if owned_by_repo "$pid"; then
    say "[KILL] $name PID $pid did not exit on TERM"
    signal_pid "$pid" KILL
  fi
done

find "$PIDS" -name '*.pid' -type f -delete 2>/dev/null

say "MaleCNS demo stopped (release-local PIDs only). Runtime data under .runtime/ was left in place."
exit 0
