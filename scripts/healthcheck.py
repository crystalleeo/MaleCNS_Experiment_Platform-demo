#!/usr/bin/env python3
"""Release healthcheck: assets, imports, writable runtime dirs, and ports.

Ports 9205 (viewer) and 9215 (platform) must be free, or already owned by a PID
that this release repo recorded under .runtime/pids/. Anything else is reported
as an error; the healthcheck never kills anything.

Exit codes: 0 ok, 1 failed, 3 required asset URL still pending, 6 import error,
7 port occupied by a foreign process, 8 runtime directory not writable.
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
import release_common as rc  # noqa: E402

# When several check groups fail, report the most specific blocking cause first.
EXIT_PRIORITY = [
    rc.EXIT_ASSET_UNRESOLVED,
    rc.EXIT_ASSET_CORRUPT,
    rc.EXIT_ASSET_MISSING,
    rc.EXIT_NOT_WRITABLE,
    rc.EXIT_PORT_BUSY,
    rc.EXIT_IMPORT,
    rc.EXIT_FAIL,
]

IMPORTS = {
    "numpy": "viewer/skeleton math (build-time reference)",
    "pyarrow": "flat-connectome reference data tooling",
    "fastapi": "experiment platform server",
    "uvicorn": "experiment platform server",
}


def check_assets(root: Path, results: list[dict]) -> int:
    manifest = rc.load_manifest(root)
    worst = rc.EXIT_OK
    for asset in rc.required_assets(manifest):
        state, detail = rc.check_asset_file(root, asset)
        ok = state == "ok"
        results.append(
            {
                "check": "asset",
                "asset": asset.get("id"),
                "ok": ok,
                "state": state,
                "detail": detail,
                "url_status": asset.get("url_status"),
            }
        )
        if state == "unresolved":
            worst = max(worst, rc.EXIT_ASSET_UNRESOLVED)
        elif state == "missing":
            worst = max(worst, rc.EXIT_ASSET_MISSING)
        elif state == "corrupt":
            worst = max(worst, rc.EXIT_ASSET_CORRUPT)
    return worst


def check_imports(results: list[dict]) -> int:
    worst = rc.EXIT_OK
    for module, why in IMPORTS.items():
        try:
            importlib.import_module(module)
            results.append({"check": "import", "module": module, "ok": True, "detail": why})
        except Exception as exc:  # pragma: no cover - depends on install state
            results.append(
                {"check": "import", "module": module, "ok": False, "detail": f"{exc} ({why})"}
            )
            worst = max(worst, rc.EXIT_IMPORT)
    return worst


def check_runtime_dirs(root: Path, results: list[dict]) -> int:
    worst = rc.EXIT_OK
    try:
        rc.ensure_runtime_dirs(root)
    except OSError as exc:
        results.append({"check": "runtime_dir", "path": str(rc.runtime_root(root)), "ok": False, "detail": str(exc)})
        return rc.EXIT_NOT_WRITABLE

    for path in rc.runtime_dirs(root):
        probe = path / ".healthcheck_probe"
        try:
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            results.append({"check": "runtime_dir", "path": str(path), "ok": True, "detail": "writable"})
        except OSError as exc:
            results.append({"check": "runtime_dir", "path": str(path), "ok": False, "detail": f"not writable: {exc}"})
            worst = max(worst, rc.EXIT_NOT_WRITABLE)
    return worst


def check_ports(root: Path, results: list[dict]) -> int:
    worst = rc.EXIT_OK
    for name, component in rc.COMPONENTS.items():
        port = component["port"]
        if port is None:
            continue
        recorded = rc.read_pid(rc.pids_dir(root) / component["pid"])
        living = sorted(p for p in rc.listening_pids(port))
        if not living:
            results.append({"check": "port", "component": name, "port": port, "ok": True, "detail": "free"})
            continue
        owned = [pid for pid in living if rc.pid_owned_by_repo(pid, root)]
        if len(owned) == len(living):
            results.append(
                {
                    "check": "port",
                    "component": name,
                    "port": port,
                    "ok": True,
                    "detail": f"listening PIDs owned by this repo: {owned}",
                }
            )
        else:
            foreign = [pid for pid in living if pid not in owned]
            results.append(
                {
                    "check": "port",
                    "component": name,
                    "port": port,
                    "ok": False,
                    "detail": f"port {port} held by non-repo PID(s) {foreign}: {rc.pid_command(foreign[0])[:160]}",
                }
            )
            worst = max(worst, rc.EXIT_PORT_BUSY)
    return worst


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--skip-imports", action="store_true")
    parser.add_argument("--skip-ports", action="store_true")
    parser.add_argument("--skip-assets", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    root = Path(args.repo_root).resolve() if args.repo_root else rc.repo_root()

    results: list[dict] = []
    codes = [rc.EXIT_OK]
    if not args.skip_assets:
        codes.append(check_assets(root, results))
    if not args.skip_imports:
        codes.append(check_imports(results))
    codes.append(check_runtime_dirs(root, results))
    if not args.skip_ports:
        codes.append(check_ports(root, results))

    present = [c for c in codes if c != rc.EXIT_OK]
    worst = rc.EXIT_OK
    for code in EXIT_PRIORITY:
        if code in present:
            worst = code
            break
    ok = worst == rc.EXIT_OK

    pending = [
        item for item in results
        if item.get("check") == "asset" and item.get("state") == "unresolved"
    ]

    if args.json:
        print(json.dumps({"ok": ok, "exit": worst, "failed_groups": sorted(set(present)), "results": results}, indent=2))
    else:
        for item in results:
            mark = "ok  " if item["ok"] else "FAIL"
            label = item.get("asset") or item.get("module") or item.get("component") or item.get("path")
            print(f"[{mark}] {item['check']:<12} {label:<34} {item['detail']}")
        if pending:
            manifest = rc.load_manifest(root)
            by_id = {a.get("id"): a for a in rc.manifest_assets(manifest)}
            first = by_id.get(pending[0].get("asset"))
            print("", file=sys.stderr)
            if first:
                print(rc.unresolved_url_error(first), file=sys.stderr)
        if len(present) > 1:
            print(f"\nnote: multiple check groups failed: {sorted(set(present))}; primary exit={worst}", file=sys.stderr)
        print(f"\nhealthcheck exit={worst} ({'healthy' if ok else 'unhealthy'})")
    return worst


if __name__ == "__main__":
    sys.exit(main())
