"""Repo-relative paths for the MaleCNS demo release.

Adapted from the source project's config/paths.py: the source version defaulted
to ``data/MaleCNS-v1.0`` under a developer machine root and exported
``MALECNS_*`` variables from config/paths.sh. This release variant defaults to
paths inside this repository and keeps every value overridable by environment
variable. No value points at a developer home directory, an external volume, or
the source project.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(os.environ.get("MALECNS_ROOT", Path(__file__).resolve().parents[1])).resolve()

# Runtime state (gitignored) lives under .runtime/
RUNTIME_ROOT = Path(os.environ.get("MALECNS_RUNTIME_ROOT", ROOT / ".runtime")).resolve()
ACTIVITY_DIR = Path(os.environ.get("MALECNS_ACTIVITY_DIR", RUNTIME_ROOT / "activity")).resolve()
PIDS_DIR = Path(os.environ.get("MALECNS_PIDS_DIR", RUNTIME_ROOT / "pids")).resolve()
LOGS_DIR = Path(os.environ.get("MALECNS_LOGS_DIR", RUNTIME_ROOT / "logs")).resolve()

# Committed derived data (asset A1: MaleCNS canonical universe, CC BY 4.0)
DATA_DIR = Path(os.environ.get("MALECNS_DATA_DIR", ROOT / "data")).resolve()
CANONICAL_BODY_IDS = Path(
    os.environ.get("MALECNS_CANONICAL_BODY_IDS", DATA_DIR / "canonical_body_ids.txt")
).resolve()

# Viewer web root (committed assets A2, A6, A7-A9; downloaded assets A3-A5)
VIEWER_WEB = Path(os.environ.get("MALECNS_VIEWER_WEB", ROOT / "viewer" / "web")).resolve()
VIEWER_ASSETS = VIEWER_WEB / "assets"

VIEWER_PORT = int(os.environ.get("MALECNS_VIEWER_PORT", "9205"))
PLATFORM_PORT = int(os.environ.get("MALECNS_PLATFORM_PORT", "9215"))
BIND_HOST = os.environ.get("MALECNS_BIND_HOST", "127.0.0.1")

ACCEPTED_PRESENTATION = {
    "neuron_gain": 0.65,
    "activity_threshold": 0.22,
    "activity_decay": 0.82,
    "fps": 10,
    "visible_neurons": 1200,
    "active_visible_per_frame": 40,
    "layout": 9215,
}
