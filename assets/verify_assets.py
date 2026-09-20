#!/usr/bin/env python3
"""Verify presence, size and exact SHA256 of every asset in assets/manifest.json.

Exit codes:
  0  all required assets verified
  3  a required project-derived asset has no published URL yet (pending release)
  4  a committed asset is missing
  5  an asset is present but fails its size/SHA256 check
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))

import release_common as rc  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--only", default=None)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    root = Path(args.repo_root).resolve() if args.repo_root else rc.repo_root()
    only = set(x.strip() for x in args.only.split(",")) if args.only else None
    manifest = rc.load_manifest(root)

    worst = rc.EXIT_OK
    pending: list[str] = []
    for asset in rc.required_assets(manifest):
        if only and asset.get("id") not in only:
            continue
        state, detail = rc.check_asset_file(root, asset)
        asset_id = asset.get("id", "?")
        name = asset.get("name", "?")
        if state == "ok":
            if not args.quiet:
                print(f"[ok]       {asset_id} {name} sha256 verified")
        elif state == "unresolved":
            pending.append(asset_id)
            print(
                f"[pending]  {asset_id} {name} not downloaded "
                f"(url_status={asset.get('url_status')})"
            )
            worst = max(worst, rc.EXIT_ASSET_UNRESOLVED)
        elif state == "missing":
            print(f"[missing]  {asset_id} {name}: {detail}", file=sys.stderr)
            worst = max(worst, rc.EXIT_ASSET_MISSING)
        else:
            print(f"[corrupt]  {asset_id} {name}: {detail}", file=sys.stderr)
            worst = max(worst, rc.EXIT_ASSET_CORRUPT)

    if pending:
        pending_assets = {a.get("id"): a for a in rc.manifest_assets(manifest)}
        first = pending_assets.get(pending[0])
        if first:
            print("", file=sys.stderr)
            print(rc.unresolved_url_error(first), file=sys.stderr)

    if worst == rc.EXIT_OK:
        print(f"\nAll required assets verified against assets/manifest.json ({root})")
    else:
        print(f"\nAsset verification failed (exit {worst}) for {root}", file=sys.stderr)
    return worst


if __name__ == "__main__":
    sys.exit(main())
