#!/usr/bin/env python3
"""Resolve and verify the release assets declared in assets/manifest.json.

Rules implemented here (R2/R3 contract):

* read the manifest, never invent a URL;
* download only when the target file is absent or fails its hash/size check;
* stream the download into ``<target>.part`` and verify SHA256 before an atomic
  rename onto the target;
* when a project-derived asset has no published stable URL yet, fail
  deterministically with an actionable ``ASSET_URL_UNRESOLVED`` message naming
  the asset. No local-source fallback, symlink, implicit copy, or guessed URL is
  permitted.
"""
from __future__ import annotations

import argparse
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))

import release_common as rc  # noqa: E402

DOWNLOAD_TIMEOUT = 60
CHUNK = 1 << 20


def log(verbose: bool, message: str) -> None:
    if verbose:
        print(message, flush=True)


def download_asset(root: Path, asset: dict, verbose: bool = False) -> int:
    """Download one asset. Returns an rc.EXIT_* code."""
    asset_id = asset.get("id", "?")
    target = rc.asset_target(root, asset)
    url = asset.get("url")
    expected = str(asset.get("sha256", "")).lower()
    expected_size = asset.get("size")

    if not url:
        print(rc.unresolved_url_error(asset), file=sys.stderr)
        return rc.EXIT_ASSET_UNRESOLVED

    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")

    try:
        part.unlink(missing_ok=True)
    except OSError as exc:
        print(f"ASSET_IO_ERROR: cannot clear stale partial file {part}: {exc}", file=sys.stderr)
        return rc.EXIT_FAIL

    print(f"[download] {asset_id} <- {url}", flush=True)
    request = urllib.request.Request(url, headers={"User-Agent": "malecns-demo-bootstrap/0.1"})

    try:
        with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT) as response:
            status = getattr(response, "status", 200)
            if status != 200:
                print(
                    f"ASSET_HTTP_ERROR: asset {asset_id} ({target.name}) returned HTTP {status} for {url}",
                    file=sys.stderr,
                )
                return rc.EXIT_FAIL
            import hashlib

            digest = hashlib.sha256()
            written = 0
            with part.open("wb") as handle:
                while True:
                    block = response.read(CHUNK)
                    if not block:
                        break
                    handle.write(block)
                    digest.update(block)
                    written += len(block)
    except urllib.error.HTTPError as exc:
        part.unlink(missing_ok=True)
        print(
            f"ASSET_HTTP_ERROR: asset {asset_id} ({target.name}) failed with HTTP {exc.code} "
            f"{exc.reason} for {url}",
            file=sys.stderr,
        )
        return rc.EXIT_FAIL
    except urllib.error.URLError as exc:
        part.unlink(missing_ok=True)
        print(
            f"ASSET_NETWORK_ERROR: asset {asset_id} ({target.name}) could not be fetched from {url}: {exc.reason}",
            file=sys.stderr,
        )
        return rc.EXIT_FAIL
    except PermissionError as exc:
        part.unlink(missing_ok=True)
        print(
            f"ASSET_PERMISSION_ERROR: cannot write {part}: {exc}. Check directory permissions.",
            file=sys.stderr,
        )
        return rc.EXIT_FAIL
    except OSError as exc:
        part.unlink(missing_ok=True)
        print(
            f"ASSET_DISK_ERROR: writing {part} failed: {exc}. Check free disk space and permissions.",
            file=sys.stderr,
        )
        return rc.EXIT_FAIL

    actual = digest.hexdigest()
    if expected and actual != expected:
        part.unlink(missing_ok=True)
        print(
            f"ASSET_CHECKSUM_MISMATCH: asset {asset_id} ({target.name}) downloaded from {url}\n"
            f"  expected sha256: {expected}\n"
            f"  actual sha256  : {actual}\n"
            f"  action         : the release asset changed or the URL is wrong; do not launch. "
            f"Report this and re-attach the frozen asset.",
            file=sys.stderr,
        )
        return rc.EXIT_ASSET_CORRUPT

    if isinstance(expected_size, int) and written != expected_size:
        part.unlink(missing_ok=True)
        print(
            f"ASSET_SIZE_MISMATCH: asset {asset_id} ({target.name}) is {written} bytes, expected {expected_size}",
            file=sys.stderr,
        )
        return rc.EXIT_ASSET_CORRUPT

    try:
        os.replace(part, target)
    except OSError as exc:
        part.unlink(missing_ok=True)
        print(f"ASSET_IO_ERROR: cannot move {part} -> {target}: {exc}", file=sys.stderr)
        return rc.EXIT_FAIL

    print(f"[ok] {asset_id} {target.name} ({rc.fmt_bytes(written)}) sha256 verified", flush=True)
    return rc.EXIT_OK


def resolve_all(root: Path, only: set[str] | None, check_only: bool, verbose: bool) -> int:
    manifest = rc.load_manifest(root)
    worst = rc.EXIT_OK
    for asset in rc.required_assets(manifest):
        if only and asset.get("id") not in only:
            continue
        state, detail = rc.check_asset_file(root, asset)
        asset_id = asset.get("id", "?")

        if state == "ok":
            log(verbose, f"[ok] {asset_id} {detail}")
            continue

        if state == "corrupt":
            print(
                f"ASSET_CORRUPT: asset {asset_id} ({asset.get('name')}) failed verification: {detail}",
                file=sys.stderr,
            )
            if check_only or asset.get("deployment") != "download":
                worst = max(worst, rc.EXIT_ASSET_CORRUPT)
                continue
            print(f"[repair] re-downloading {asset_id} because the local copy is corrupt", flush=True)
            code = download_asset(root, asset, verbose)
            worst = max(worst, code)
            continue

        if state == "missing":
            print(
                f"ASSET_MISSING: asset {asset_id} ({asset.get('name')}) is required but absent: {detail}\n"
                f"  action: this is a committed release file; re-clone the repository or restore the file.",
                file=sys.stderr,
            )
            worst = max(worst, rc.EXIT_ASSET_MISSING)
            continue

        # state == "unresolved": not downloaded yet
        if check_only:
            print(f"[pending] {asset_id} {detail}", flush=True)
            if asset.get("url"):
                print(f"         url: {asset['url']}", flush=True)
            else:
                print(rc.unresolved_url_error(asset), file=sys.stderr)
            worst = max(worst, rc.EXIT_ASSET_UNRESOLVED)
            continue

        code = download_asset(root, asset, verbose)
        worst = max(worst, code)
        if code == rc.EXIT_OK:
            state2, detail2 = rc.check_asset_file(root, asset)
            if state2 != "ok":
                print(f"ASSET_VERIFY_FAILED: {asset_id} after download: {detail2}", file=sys.stderr)
                worst = max(worst, rc.EXIT_ASSET_CORRUPT)
    return worst


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=None, help="override the repository root (testing)")
    parser.add_argument("--only", default=None, help="comma-separated asset ids to process")
    parser.add_argument("--check-only", action="store_true", help="report without downloading")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    root = Path(args.repo_root).resolve() if args.repo_root else rc.repo_root()
    only = set(x.strip() for x in args.only.split(",")) if args.only else None
    return resolve_all(root, only, args.check_only, args.verbose)


if __name__ == "__main__":
    sys.exit(main())
