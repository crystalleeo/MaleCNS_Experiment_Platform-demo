#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path

# Release-repo paths. The source chain hard-coded a foreign developer home root
# here; this is the strictly-required repo-relative path fix documented in
# README.md and assets/manifest.json.
ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime"
ACT = RUNTIME / "activity"
PIDS = RUNTIME / "pids"
RAW = ACT / "source_raw.jsonl"
OUT = ACT / "source.jsonl"
VISIBLE_META = ROOT / "viewer" / "web" / "assets" / "neurons.json"
RAW_DEMO = ROOT / "demo" / "demo_sync_source_raw.py"
PYTHON = ROOT / ".venv" / "bin" / "python3"
SOURCE_PID = PIDS / "demo_source.pid"

ACTIVE_VISIBLE = 40
SEED = 20260920

meta = json.loads(VISIBLE_META.read_text())
visible_ids = meta.get("body_ids") or meta.get("bodyIds") or meta.get("ids")
if not isinstance(visible_ids, list) or not visible_ids:
    raise RuntimeError("Viewer neurons.json has no body_ids")

visible_ids = [int(x) for x in visible_ids]
rng = random.Random(SEED)

# Match the pre-migration demo cadence:
# select a fresh visible neuron set for EVERY activity frame.
# This restores the fast spatial flicker while keeping only 40 visible neurons.
frame_rng = random.Random(SEED)

def group_for_frame() -> list[int]:
    return frame_rng.sample(visible_ids, min(ACTIVE_VISIBLE, len(visible_ids)))

def transform_activity(obj: dict) -> dict:
    # Support both flat activity records and payload-enveloped activity records.
    holder = obj
    payload_mode = False
    if isinstance(obj.get("payload"), dict):
        p = obj["payload"]
        if "body_ids" in p and ("values" in p or "activity" in p or "activities" in p):
            holder = p
            payload_mode = True

    if "body_ids" not in holder:
        return obj

    vals = holder.get("values", holder.get("activity", holder.get("activities")))
    if not isinstance(vals, list):
        return obj

    # Keep trial/phase metadata untouched, but refresh the visible set every frame.
    ids = group_for_frame()

    # Keep the original temporal amplitude profile. Use strongest values so
    # visible lines are obvious, but preserve trial/phase timing unchanged.
    numeric = []
    for v in vals:
        try:
            numeric.append(float(v))
        except Exception:
            pass
    numeric.sort(reverse=True)

    if numeric:
        chosen = numeric[:len(ids)]
        if len(chosen) < len(ids):
            chosen.extend([chosen[-1]] * (len(ids)-len(chosen)))
        # Ensure demonstration remains visible with current Viewer threshold .22.
        chosen = [max(0.30, min(1.0, v)) for v in chosen]
    else:
        chosen = [0.75] * len(ids)

    holder["body_ids"] = ids
    if "values" in holder:
        holder["values"] = chosen
    elif "activity" in holder:
        holder["activity"] = chosen
    else:
        holder["activities"] = chosen

    # Add non-breaking metadata useful for audits; platform ignores unknown keys.
    holder["viewer_demo_active"] = len(ids)
    holder["viewer_demo_visible_only"] = True
    return obj

def is_activity(obj: dict) -> bool:
    if "body_ids" in obj and any(k in obj for k in ("values","activity","activities")):
        return True
    p=obj.get("payload")
    return isinstance(p,dict) and "body_ids" in p and any(k in p for k in ("values","activity","activities"))

ACT.mkdir(parents=True,exist_ok=True)
PIDS.mkdir(parents=True,exist_ok=True)
RAW.write_text("")
OUT.write_text("")

print("MaleCNS Platform synchronized adapter demo")
print(f"visible neurons={len(visible_ids)} active visible/frame={ACTIVE_VISIBLE}")
print("task/control events: preserved exactly")
print(f"raw producer: {RAW_DEMO}")
print(f"raw stream:   {RAW}")
print(f"bridge input: {OUT}")
sys.stdout.flush()

PYTHON_BIN = str(PYTHON) if PYTHON.exists() else sys.executable
proc = subprocess.Popen(
    [PYTHON_BIN, str(RAW_DEMO)],
    cwd=str(ROOT),
)
# Record only this demo's own child PID so stop.sh can terminate exactly this run.
try:
    SOURCE_PID.write_text(str(proc.pid), encoding="utf-8")
except OSError as exc:
    print(f"[warn] could not record demo_source pid: {exc}", file=sys.stderr)

activity_count=0
task_count=0
pos=0

with OUT.open("a",encoding="utf-8",buffering=1) as fout:
    while True:
        progressed=False
        if RAW.exists():
            with RAW.open("r",encoding="utf-8",errors="ignore") as fin:
                fin.seek(pos)
                while True:
                    line=fin.readline()
                    if not line:
                        pos=fin.tell()
                        break
                    progressed=True
                    try:
                        obj=json.loads(line)
                    except Exception:
                        continue
                    if not isinstance(obj,dict):
                        continue

                    if is_activity(obj):
                        obj=transform_activity(obj)
                        activity_count += 1
                    else:
                        # Critical: do not modify experiment/task payload.
                        task_count += 1

                    fout.write(json.dumps(obj,ensure_ascii=False,separators=(",",":"))+"\n")
                    fout.flush()

        if proc.poll() is not None:
            # Drain once more after producer exits.
            if not progressed:
                if RAW.exists():
                    with RAW.open("r",encoding="utf-8",errors="ignore") as fin:
                        fin.seek(pos)
                        rest=fin.readlines()
                    if rest:
                        continue
                break

        if not progressed:
            time.sleep(0.02)

try:
    rc=proc.wait()
finally:
    SOURCE_PID.unlink(missing_ok=True)
print(f"DONE raw_rc={rc} activity_events={activity_count} task/control_events={task_count}")
if rc != 0:
    raise SystemExit(rc)
