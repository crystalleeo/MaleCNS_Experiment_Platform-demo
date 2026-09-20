#!/usr/bin/env python3
"""Check that this machine can run the MaleCNS demo release (macOS-first).

Checks: macOS, Python >= 3.10, git, curl. No sudo, no global pip, no network.
Use --ci on Linux CI runners where the macOS requirement does not apply.
"""
from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
import release_common as rc  # noqa: E402

MIN_PYTHON = (3, 10)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ci", action="store_true", help="allow non-macOS hosts (CI)")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args()

    checks: list[dict] = []

    def add(name: str, ok: bool, detail: str, required: bool = True) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail, "required": required})

    system = platform.system()
    add(
        "macOS",
        system == "Darwin" or args.ci,
        f"platform={system}" + ("" if system == "Darwin" else " (allowed by --ci)"),
        required=not args.ci,
    )

    version = sys.version_info
    add(
        "python>=3.10",
        version >= MIN_PYTHON,
        f"python={platform.python_version()} ({sys.executable})",
    )

    for tool in ("git", "curl"):
        path = shutil.which(tool)
        add(tool, path is not None, path or "not found on PATH")

    git_version = ""
    if shutil.which("git"):
        git_version = subprocess.run(
            ["git", "--version"], capture_output=True, text=True, check=False
        ).stdout.strip()
    add("git --version", bool(git_version), git_version or "unavailable", required=False)

    failed = [c for c in checks if c["required"] and not c["ok"]]
    if args.json:
        print(json.dumps({"ok": not failed, "checks": checks}, indent=2))
    else:
        for c in checks:
            mark = "ok  " if c["ok"] else ("FAIL" if c["required"] else "warn")
            print(f"[{mark}] {c['name']}: {c['detail']}")
        if failed:
            print(f"\nEnvironment check failed: {', '.join(c['name'] for c in failed)}", file=sys.stderr)
        else:
            print("\nEnvironment check passed.")
    return rc.EXIT_OK if not failed else rc.EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main())
