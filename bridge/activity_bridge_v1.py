#!/usr/bin/env python3
"""
MaleCNS v1.0 experiment/activity bridge.

Input (append-only JSONL):
  .runtime/activity/source.jsonl

Accepted event types:
1) Activity
   {
     "type": "activity",
     "t_ms": 123.4,
     "body_ids": [ ... ],
     "values": [ ... ],
     "trial": 1,
     "condition": "cue"
   }

2) Task
   {
     "type": "task",
     "t_ms": 100.0,
     "trial": 1,
     "phase": "stimulus",
     "payload": {...}
   }

Outputs (release-repo runtime directory, gitignored):
  .runtime/activity/live.jsonl       -> Viewer 9205 activity stream
  .runtime/activity/task_live.jsonl  -> synchronized experiment UI stream
  .runtime/activity/task_state.json  -> latest task state snapshot

Rules:
- canonical universe is frozen MaleCNS v1.0 (165,122 Traced neurons)
- engine may use model_index internally, but this boundary accepts bodyId only
- official neurotransmitter labels are untouched here
"""
from __future__ import annotations

import argparse
import json
import math
import os
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CANONICAL_IDS_FILE = ROOT / "data" / "canonical_body_ids.txt"  # release-repo path for asset A1

SCHEMA_ACTIVITY = "malecns.activity.v1"
SCHEMA_TASK = "malecns.task.v1"
SCHEMA_BUS = "malecns.experiment.v1"


def load_canonical_ids() -> set[int]:
    if not CANONICAL_IDS_FILE.exists():
        raise FileNotFoundError(f"Missing canonical body IDs: {CANONICAL_IDS_FILE}")
    ids = {
        int(line.strip())
        for line in CANONICAL_IDS_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    if len(ids) != 165_122:
        raise RuntimeError(
            f"Canonical universe mismatch: expected 165,122, got {len(ids):,}"
        )
    return ids


def atomic_write_json(path: Path, obj: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(obj, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    os.replace(tmp, path)


def parse_time_ms(payload: dict[str, Any]) -> float:
    value = payload.get("t_ms")
    if value is None:
        return time.time_ns() / 1_000_000.0
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("t_ms must be finite")
    return value


def normalize_activity(payload: dict[str, Any], canonical: set[int]) -> dict[str, Any]:
    body_ids = payload.get("body_ids")
    values = payload.get("values")
    if not isinstance(body_ids, list) or not isinstance(values, list):
        raise ValueError("activity requires list body_ids and values")
    if len(body_ids) != len(values):
        raise ValueError(
            f"body_ids/values mismatch: {len(body_ids)} != {len(values)}"
        )

    clean_ids: list[int] = []
    clean_values: list[float] = []
    seen = set()

    for raw_id, raw_value in zip(body_ids, values):
        body_id = int(raw_id)
        if body_id not in canonical:
            raise ValueError(f"non-canonical bodyId: {body_id}")
        if body_id in seen:
            raise ValueError(f"duplicate bodyId in frame: {body_id}")
        seen.add(body_id)

        value = float(raw_value)
        if not math.isfinite(value):
            raise ValueError(f"non-finite activity for bodyId {body_id}")
        clean_ids.append(body_id)
        clean_values.append(value)

    out: dict[str, Any] = {
        "schema": SCHEMA_ACTIVITY,
        "t_ms": parse_time_ms(payload),
        "body_ids": clean_ids,
        "values": clean_values,
    }
    for key in ("session", "trial", "condition", "phase", "stimulus"):
        if key in payload:
            out[key] = payload[key]
    return out


def normalize_task(payload: dict[str, Any]) -> dict[str, Any]:
    phase = str(payload.get("phase", "")).strip()
    if not phase:
        raise ValueError("task event requires phase")

    task_payload = payload.get("payload", {})
    if task_payload is None:
        task_payload = {}
    if not isinstance(task_payload, dict):
        raise ValueError("task payload must be an object")

    out: dict[str, Any] = {
        "schema": SCHEMA_TASK,
        "t_ms": parse_time_ms(payload),
        "phase": phase,
        "payload": task_payload,
    }
    for key in ("session", "trial", "condition", "stimulus"):
        if key in payload:
            out[key] = payload[key]
    return out


def detect_event_type(payload: dict[str, Any]) -> str:
    event_type = str(payload.get("type", "")).lower().strip()
    if event_type in {"activity", "task"}:
        return event_type
    # Backwards-compatible with the existing live generator.
    if "body_ids" in payload and "values" in payload:
        return "activity"
    if "phase" in payload:
        return "task"
    raise ValueError("cannot determine event type")


def follow_jsonl(path: Path, from_end: bool = False):
    while not path.exists():
        print(f"[bridge] waiting for source: {path}")
        time.sleep(0.25)

    with path.open("r", encoding="utf-8") as f:
        if from_end:
            f.seek(0, os.SEEK_END)

        inode = path.stat().st_ino
        while True:
            line = f.readline()
            if line:
                line = line.strip()
                if line:
                    yield line
                continue

            # Handle source truncation/recreation between sessions.
            try:
                st = path.stat()
                if st.st_ino != inode or st.st_size < f.tell():
                    f.close()
                    with path.open("r", encoding="utf-8") as nf:
                        inode = path.stat().st_ino
                        for new_line in nf:
                            new_line = new_line.strip()
                            if new_line:
                                yield new_line
                    f = path.open("r", encoding="utf-8")
                    f.seek(0, os.SEEK_END)
            except FileNotFoundError:
                pass
            time.sleep(0.005)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=".runtime/activity/source.jsonl")
    parser.add_argument("--activity-output", default=".runtime/activity/live.jsonl")
    parser.add_argument("--task-output", default=".runtime/activity/task_live.jsonl")
    parser.add_argument("--task-state", default=".runtime/activity/task_state.json")
    parser.add_argument("--from-end", action="store_true")
    args = parser.parse_args()

    source = ROOT / args.source
    activity_output = ROOT / args.activity_output
    task_output = ROOT / args.task_output
    task_state = ROOT / args.task_state

    for p in (source, activity_output, task_output, task_state):
        p.parent.mkdir(parents=True, exist_ok=True)

    canonical = load_canonical_ids()

    print("=" * 72)
    print("MaleCNS v1.0 formal experiment bridge")
    print("=" * 72)
    print(f"canonical neurons : {len(canonical):,}")
    print(f"source            : {source}")
    print(f"activity -> viewer: {activity_output}")
    print(f"task -> platform  : {task_output}")
    print(f"task snapshot     : {task_state}")
    print("=" * 72)

    activity_n = 0
    task_n = 0
    rejected = 0

    with activity_output.open("a", encoding="utf-8", buffering=1) as fa, \
         task_output.open("a", encoding="utf-8", buffering=1) as ft:

        for raw in follow_jsonl(source, from_end=args.from_end):
            try:
                payload = json.loads(raw)
                if not isinstance(payload, dict):
                    raise ValueError("event must be a JSON object")

                event_type = detect_event_type(payload)

                if event_type == "activity":
                    frame = normalize_activity(payload, canonical)
                    fa.write(json.dumps(frame, ensure_ascii=False, separators=(",", ":")) + "\n")
                    fa.flush()
                    activity_n += 1
                    if activity_n % 100 == 0:
                        print(
                            f"[activity] frames={activity_n:,} "
                            f"active={len(frame['body_ids']):,} "
                            f"t={frame['t_ms']:.1f} ms rejected={rejected}"
                        )

                else:
                    event = normalize_task(payload)
                    ft.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
                    ft.flush()
                    atomic_write_json(task_state, event)
                    task_n += 1
                    print(
                        f"[task] #{task_n} t={event['t_ms']:.1f} ms "
                        f"trial={event.get('trial', '-')} phase={event['phase']}"
                    )

            except Exception as exc:
                rejected += 1
                print(f"[REJECT {rejected}] {exc}")


if __name__ == "__main__":
    main()

