#!/usr/bin/env python3
"""MaleCNS viewer static host + live-activity API (port 9205).

Copied from the accepted V5 chain (v5_hybrid/server_v5_hybrid.py). The only
changes are repo-relative runtime paths: this release reads the live activity
stream from .runtime/activity/live.jsonl instead of the source project's
activity/ directory. The accepted rendering behaviour (main.js, colours, lines,
gain .65, threshold .22, decay .82, 10 FPS, 1200 visible neurons, 40 active per
frame) is untouched.
"""
from __future__ import annotations

import argparse
import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
WEB = HERE / "web"
LIVE = PROJECT / ".runtime" / "activity" / "live.jsonl"


def latest_valid_json(path: Path):
    """Read the newest complete valid JSON object from a JSONL file.

    Read from disk on every request. Do not cache a file handle, byte offset,
    inode, mtime, or previous frame. This makes truncation/rewrite-safe demos.
    """
    try:
        if not path.exists() or path.stat().st_size == 0:
            return {}

        # Activity frames are small enough that a tail window is ample.
        # Increase geometrically if the last complete JSON line is not found.
        size = path.stat().st_size
        window = min(size, 1024 * 1024)

        while True:
            with path.open("rb") as f:
                f.seek(max(0, size - window))
                data = f.read()

            for raw in reversed(data.splitlines()):
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw.decode("utf-8"))
                    if isinstance(obj, dict):
                        return obj
                except Exception:
                    continue

            if window >= size:
                return {}
            window = min(size, window * 4)
    except Exception:
        return {}


class Handler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def end_headers(self):
        # The Viewer is a live visualization; stale browser cache is undesirable.
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/activity":
            obj = latest_valid_json(LIVE)
            payload = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        return super().do_GET()

    def log_message(self, fmt, *args):
        # Keep log useful without flooding from 10 Hz activity polling.
        if urlparse(self.path).path != "/api/activity":
            super().log_message(fmt, *args)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9205)
    ap.add_argument("--bind", default="127.0.0.1")
    args = ap.parse_args()

    handler = partial(Handler, directory=str(WEB))
    httpd = ThreadingHTTPServer((args.bind, args.port), handler)

    print(f"MaleCNS viewer: http://{args.bind}:{args.port}")
    print(f"web root: {WEB}")
    print(f"activity source: {LIVE}")
    print("activity API: fresh tail read on every request; no cache")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
