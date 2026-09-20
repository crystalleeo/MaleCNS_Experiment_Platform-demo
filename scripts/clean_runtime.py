#!/usr/bin/env python3
"""Remove runtime state written by this release repo under .runtime/.

Never touches committed files, downloaded assets, or .venv/. Use --dry-run to
list what would be removed.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
import release_common as rc  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--all", action="store_true", help="remove the whole .runtime directory")
    args = parser.parse_args()

    root = Path(args.repo_root).resolve() if args.repo_root else rc.repo_root()
    runtime = rc.runtime_root(root)

    if not runtime.exists():
        print(f"runtime dir absent: {runtime}")
        return rc.EXIT_OK

    targets = [runtime] if args.all else rc.runtime_dirs(root)
    for target in targets:
        if not target.exists():
            continue
        if args.dry_run:
            print(f"[dry-run] would remove {target}")
            continue
        try:
            shutil.rmtree(target)
            print(f"[removed] {target}")
        except OSError as exc:
            print(f"ERROR: cannot remove {target}: {exc}", file=sys.stderr)
            return rc.EXIT_FAIL

    print("runtime state cleaned (committed files and downloaded assets untouched)")
    return rc.EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
