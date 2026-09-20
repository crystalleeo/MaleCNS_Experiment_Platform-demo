#!/usr/bin/env python3
"""
Non-scientific synchronization demo only.
Writes task events + random canonical activity into .runtime/activity/source_raw.jsonl.

This does NOT implement MaleCNS dynamics.
It exists only to verify the formal bridge and split-screen platform.
"""
from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IDS_FILE = ROOT / "data" / "canonical_body_ids.txt"  # asset A1 (CC BY 4.0)
SOURCE = ROOT / ".runtime" / "activity" / "source_raw.jsonl"


def write_event(f, event):
    f.write(json.dumps(event, separators=(",", ":")) + "\n")
    f.flush()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=6)
    parser.add_argument("--active", type=int, default=600)
    parser.add_argument("--fps", type=int, default=10)
    args = parser.parse_args()

    ids = [
        int(x.strip())
        for x in IDS_FILE.read_text(encoding="utf-8").splitlines()
        if x.strip()
    ]
    if len(ids) != 165_122:
        raise RuntimeError(f"expected 165122 canonical ids, got {len(ids)}")

    SOURCE.parent.mkdir(parents=True, exist_ok=True)
    SOURCE.write_text("", encoding="utf-8")

    rng = random.Random(20260919)
    t0 = time.perf_counter()

    def t_ms():
        return (time.perf_counter() - t0) * 1000.0

    def task(f, trial, phase, duration_ms, **payload):
        event = {
            "schema": "malecns.experiment.v1",
            "type": "task",
            "t_ms": t_ms(),
            "trial": trial,
            "condition": "sync_demo",
            "phase": phase,
            "payload": {"trial_duration_ms": 4300, **payload},
        }
        write_event(f, event)

        end = time.perf_counter() + duration_ms / 1000.0
        dt = 1.0 / args.fps
        next_frame = time.perf_counter()

        while time.perf_counter() < end:
            now = time.perf_counter()
            if now >= next_frame:
                selected = rng.sample(ids, args.active)
                values = [rng.uniform(0.15, 1.0) for _ in selected]
                write_event(f, {
                    "schema": "malecns.experiment.v1",
                    "type": "activity",
                    "t_ms": t_ms(),
                    "trial": trial,
                    "condition": "sync_demo",
                    "phase": phase,
                    "body_ids": selected,
                    "values": values,
                })
                next_frame += dt
            else:
                time.sleep(min(0.002, next_frame - now))

    print("MaleCNS synchronized platform demo")
    print(f"trials={args.trials} active/frame={args.active} fps={args.fps}")
    print(f"writing {SOURCE}")

    with SOURCE.open("a", encoding="utf-8", buffering=1) as f:
        write_event(f, {
            "type": "task", "t_ms": t_ms(), "trial": 0,
            "condition": "sync_demo", "phase": "message",
            "payload": {"text": "Synchronized task × brain activity demo"}
        })
        time.sleep(1.0)

        for trial in range(1, args.trials + 1):
            task(f, trial, "fixation", 800)
            task(f, trial, "cue", 500, direction="right")
            task(f, trial, "stimulus_a", 650, kind="visual_A", size_px=130)
            task(f, trial, "blank", 700)
            task(f, trial, "stimulus_b", 650, kind="visual_B", size_px=185)
            task(f, trial, "response", 1000, text="Response window")

        write_event(f, {
            "type": "task", "t_ms": t_ms(), "trial": args.trials,
            "condition": "sync_demo", "phase": "message",
            "payload": {"text": "Demo complete"}
        })

    print("DONE")


if __name__ == "__main__":
    main()

