"""Shared helpers for the MaleCNS Experiment Platform demo release repo.

Every path in this repository is derived from the location of this file, so the
release works from any clone directory and never depends on a developer machine,
an external volume, a downloads directory, or the source project.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

# --- exit codes (stable contract for scripts and CI) -------------------------
EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2
EXIT_ASSET_UNRESOLVED = 3
EXIT_ASSET_MISSING = 4
EXIT_ASSET_CORRUPT = 5
EXIT_IMPORT = 6
EXIT_PORT_BUSY = 7
EXIT_NOT_WRITABLE = 8

VIEWER_PORT = 9205
PLATFORM_PORT = 9215

COMPONENTS = {
    "viewer": {
        "pid": "viewer.pid",
        "log": "viewer.log",
        "port": VIEWER_PORT,
        "script": "viewer/server_viewer.py",
        "url": f"http://127.0.0.1:{VIEWER_PORT}/",
    },
    "bridge": {
        "pid": "bridge.pid",
        "log": "bridge.log",
        "port": None,
        "script": "bridge/activity_bridge_v1.py",
        "url": None,
    },
    "platform": {
        "pid": "platform.pid",
        "log": "platform.log",
        "port": PLATFORM_PORT,
        "script": "platform/server.py",
        "url": f"http://127.0.0.1:{PLATFORM_PORT}/",
    },
    "demo": {
        "pid": "demo.pid",
        "log": "demo.log",
        "port": None,
        "script": "demo/demo_sync_platform_adapter.py",
        "url": None,
    },
    "demo_source": {
        "pid": "demo_source.pid",
        "log": "demo.log",
        "port": None,
        "script": "demo/demo_sync_source_raw.py",
        "url": None,
    },
}

RUN_COMPONENT_ORDER = ["demo_source", "demo", "bridge", "viewer", "platform"]


# --- layout -----------------------------------------------------------------

def repo_root() -> Path:
    """Repository root, derived from this file's own location."""
    root = Path(__file__).resolve().parent.parent
    if not (root / "assets" / "manifest.json").is_file():
        raise RuntimeError(
            f"release repo root not found from {__file__}: {root}/assets/manifest.json is missing"
        )
    return root


def runtime_root(root: Path | None = None) -> Path:
    return (root or repo_root()) / ".runtime"


def activity_dir(root: Path | None = None) -> Path:
    return runtime_root(root) / "activity"


def pids_dir(root: Path | None = None) -> Path:
    return runtime_root(root) / "pids"


def logs_dir(root: Path | None = None) -> Path:
    return runtime_root(root) / "logs"


def runtime_dirs(root: Path | None = None) -> list[Path]:
    base = runtime_root(root)
    return [base, activity_dir(root), pids_dir(root), logs_dir(root)]


def ensure_runtime_dirs(root: Path | None = None) -> None:
    for path in runtime_dirs(root):
        path.mkdir(parents=True, exist_ok=True)


# --- manifest ---------------------------------------------------------------

def load_manifest(root: Path | None = None) -> dict[str, Any]:
    root = root or repo_root()
    path = root / "assets" / "manifest.json"
    with path.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    if not isinstance(manifest, dict) or "assets" not in manifest:
        raise ValueError(f"{path} is not a valid asset manifest (missing 'assets')")
    return manifest


def manifest_assets(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    assets = manifest.get("assets")
    if not isinstance(assets, list) or not assets:
        raise ValueError("asset manifest has no assets")
    return assets


def required_assets(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [a for a in manifest_assets(manifest) if a.get("required", True)]


def asset_target(root: Path, asset: dict[str, Any]) -> Path:
    return root / asset["target_path"]


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(chunk), b""):
            digest.update(block)
    return digest.hexdigest()


def check_asset_file(root: Path, asset: dict[str, Any]) -> tuple[str, str]:
    """Return (state, detail) for one manifest asset.

    state in: "ok", "missing", "corrupt", "unresolved"
    """
    target = asset_target(root, asset)
    if not target.is_file():
        if asset.get("deployment") == "download":
            return "unresolved", f"not downloaded yet ({target})"
        return "missing", f"missing committed file ({target})"

    expected = str(asset.get("sha256", "")).lower()
    actual = sha256_file(target)
    if expected and actual != expected:
        return "corrupt", f"sha256 {actual} != expected {expected} ({target})"

    expected_size = asset.get("size")
    if isinstance(expected_size, int) and target.stat().st_size != expected_size:
        return "corrupt", (
            f"size {target.stat().st_size} != expected {expected_size} ({target})"
        )
    return "ok", str(target)


def unresolved_url_error(asset: dict[str, Any]) -> str:
    """Actionable message for a derived asset whose stable URL is not published."""
    asset_id = asset.get("id", "?")
    name = asset.get("name") or Path(asset.get("target_path", "")).name
    url_status = asset.get("url_status", "missing")
    expected = asset.get("sha256", "?")
    target = asset.get("target_path", "?")
    return (
        f"ASSET_URL_UNRESOLVED: asset {asset_id} ({name}) has no downloadable URL.\n"
        f"  manifest      : assets/manifest.json\n"
        f"  target        : {target}\n"
        f"  expected sha256: {expected}\n"
        f"  url_status    : \"{url_status}\"\n"
        f"  reason        : this project-derived release asset is frozen by hash, but the\n"
        f"                  stable project release URL does not exist yet. R7 will attach the\n"
        f"                  stable release URL for A3/A4/A5.\n"
        f"  action        : do NOT guess a URL and do NOT copy from a local source project\n"
        f"                  (no symlink or implicit fallback is permitted). Wait for the\n"
        f"                  authorized project release, then set this asset's \"url\" in\n"
        f"                  assets/manifest.json (keep the frozen sha256) and re-run ./bootstrap.sh"
    )


def pending_download_assets(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        a
        for a in manifest_assets(manifest)
        if a.get("deployment") == "download"
        and (not a.get("url") or a.get("url_status") == "pending_project_release")
    ]


# --- processes --------------------------------------------------------------

def read_pid(path: Path) -> int | None:
    try:
        raw = path.read_text(encoding="utf-8").strip()
        return int(raw) if raw else None
    except (OSError, ValueError):
        return None


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def pid_command(pid: int) -> str:
    try:
        out = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            check=False,
        )
        return out.stdout.strip()
    except OSError:
        return ""


def pid_owned_by_repo(pid: int, root: Path | None = None) -> bool:
    """True only if this PID's command line points into this release repo."""
    root = (root or repo_root()).resolve()
    command = pid_command(pid)
    if not command:
        return False
    return str(root) in command


def listening_pids(port: int) -> list[int]:
    try:
        out = subprocess.run(
            ["lsof", "-nP", f"-tiTCP:{port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return []
    pids = []
    for line in out.stdout.split():
        try:
            pids.append(int(line))
        except ValueError:
            continue
    return pids


def fmt_bytes(count: int) -> str:
    value = float(count)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} GiB"


def main_unused() -> None:  # pragma: no cover - placeholder for import safety
    sys.stderr.write("release_common is a library, not an entry point\n")
