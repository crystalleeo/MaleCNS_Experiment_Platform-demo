#!/usr/bin/env python3
"""MaleCNS Experiment Platform server (port 9215).

Copied from the accepted V5 chain (experiment_platform_v5/server.py). Adapted
only where the R3 contract requires it:

* repo-relative paths (no developer-machine or source-project root);
* runtime task streams read/written under .runtime/activity/;
* the experiment launcher runs this repo's scripts/run_demo.sh (still triggered
  by the 9215 UI button, never started automatically);
* the shutdown endpoint runs this repo's safe release-local stop.sh, which only
  terminates PIDs recorded by this repository. The JSON response is unchanged.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parents[1]
WEB = Path(__file__).resolve().parent / "web"
RUNTIME = ROOT / ".runtime"
ACTIVITY = RUNTIME / "activity"
LOGS = RUNTIME / "logs"
TASK_LIVE = ACTIVITY / "task_live.jsonl"
TASK_STATE = ACTIVITY / "task_state.json"

VIEWER_URL = os.environ.get("MALECNS_VIEWER_URL", "http://127.0.0.1:9205")
DEMO_RUNNER = ROOT / "scripts" / "run_demo.sh"
SHUTDOWN_HELPER = ROOT / "stop.sh"

app = FastAPI(title="MaleCNS Experiment Platform", version="1.0")
app.mount("/assets", StaticFiles(directory=str(WEB)), name="assets")


@app.get("/")
async def root():
    return FileResponse(WEB / "index.html")


@app.get("/api/config")
async def config():
    return {
        "schema": "malecns.experiment.platform.v1",
        "viewer_url": VIEWER_URL,
        "task_stream": "/api/task/stream",
        "task_state": "/api/task/state",
    }


@app.get("/api/task/state")
async def task_state():
    if not TASK_STATE.exists():
        return JSONResponse({"phase": "idle", "t_ms": 0, "payload": {}})
    try:
        return JSONResponse(json.loads(TASK_STATE.read_text(encoding="utf-8")))
    except Exception:
        return JSONResponse({"phase": "idle", "t_ms": 0, "payload": {}})


async def task_event_generator():
    TASK_LIVE.parent.mkdir(parents=True, exist_ok=True)
    TASK_LIVE.touch(exist_ok=True)

    with TASK_LIVE.open("r", encoding="utf-8") as f:
        # New connections receive current state via /api/task/state, then only new events here.
        f.seek(0, os.SEEK_END)
        while True:
            line = f.readline()
            if line:
                line = line.strip()
                if line:
                    yield f"data: {line}\n\n"
            else:
                yield ": keepalive\n\n"
                await asyncio.sleep(0.05)


@app.get("/api/task/stream")
async def task_stream():
    return StreamingResponse(
        task_event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# --- in-platform experiment launcher (UI button only; never auto-started) ---
_demo_process = None


@app.post("/api/run-demo")
async def run_demo_from_platform():
    global _demo_process

    if _demo_process is not None and _demo_process.poll() is None:
        return {
            "ok": True,
            "already_running": True,
            "pid": _demo_process.pid,
        }

    if not DEMO_RUNNER.exists():
        return JSONResponse(
            {"ok": False, "error": f"missing runner: {DEMO_RUNNER}"},
            status_code=500,
        )

    LOGS.mkdir(parents=True, exist_ok=True)
    log_f = (LOGS / "demo_launch.log").open("ab", buffering=0)

    _demo_process = subprocess.Popen(
        ["/bin/bash", str(DEMO_RUNNER)],
        cwd=str(ROOT),
        stdout=log_f,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )

    return {
        "ok": True,
        "already_running": False,
        "pid": _demo_process.pid,
    }


# --- platform shutdown endpoint ---
@app.post("/api/shutdown")
async def shutdown_platform():
    if not SHUTDOWN_HELPER.exists():
        return JSONResponse(
            {"ok": False, "error": f"missing shutdown helper: {SHUTDOWN_HELPER}"},
            status_code=500,
        )

    subprocess.Popen(
        ["/bin/bash", str(SHUTDOWN_HELPER)],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )

    return {
        "ok": True,
        "message": "MaleCNS platform is shutting down",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9215)
    args = parser.parse_args()
    ACTIVITY.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
