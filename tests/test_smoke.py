#!/usr/bin/env python3
"""Offline smoke tests for the MaleCNS demo release.

These tests never fetch complete MaleCNS data, never start a server, and never
touch the source project. Run with:

    python3 -m unittest discover -s tests -t .
"""
from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(ROOT / "lib"))
import release_common as rc  # noqa: E402

FORBIDDEN_PATH_TOKENS = ["/Users/", "/Volumes/", "$HOME/Downloads", "Downloads/malecns"]
FORBIDDEN_KILL_TOKENS = ["pkill", "pgrep", "killall"]

SHELL_SCRIPTS = ["bootstrap.sh", "start.sh", "stop.sh", "scripts/run_demo.sh"]
TEXT_SUFFIXES = {".py", ".sh", ".md", ".json", ".cff", ".txt", ".js", ".css", ".html", ".yml", ".yaml"}

# This test file necessarily contains the forbidden tokens as scan patterns and
# as documentation of what is being checked, so it excludes itself.
SELF = "tests/test_smoke.py"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def iter_repo_files():
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith(".runtime/") or rel.startswith(".venv/"):
            continue
        if "__pycache__" in rel:
            continue
        yield rel, path


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((ROOT / "assets" / "manifest.json").read_text())
        self.assets = self.manifest["assets"]

    def test_manifest_ids_and_shape(self):
        self.assertEqual([a["id"] for a in self.assets], [f"A{i}" for i in range(1, 10)])
        for asset in self.assets:
            self.assertRegex(asset["sha256"], r"^[0-9a-f]{64}$", asset["id"])
            self.assertIsInstance(asset["size"], int)
            self.assertTrue(asset["target_path"])
            self.assertTrue(asset["required"])
            self.assertTrue(asset["license"])

    def test_manifest_matches_frozen_r1_expectations(self):
        frozen = json.loads((FIXTURES / "r1_frozen_expectations.json").read_text())["assets"]
        for asset in self.assets:
            expected = frozen[asset["id"]]
            self.assertEqual(asset["sha256"], expected["sha256"], asset["id"])
            self.assertEqual(asset["size"], expected["size"], asset["id"])
            self.assertEqual(asset["provenance_class"], expected["provenance_class"], asset["id"])

    def test_pending_assets_are_honest(self):
        by_id = {a["id"]: a for a in self.assets}
        for asset_id in ("A3", "A4", "A5"):
            asset = by_id[asset_id]
            self.assertEqual(asset["deployment"], "download")
            self.assertEqual(asset["url_status"], "pending_project_release")
            self.assertIsNone(asset["url"])
        for asset_id in ("A1", "A2", "A6"):
            by_id[asset_id].get("sha256")
            self.assertEqual(by_id[asset_id]["deployment"], "commit")
        for asset_id in ("A7", "A8", "A9"):
            self.assertEqual(by_id[asset_id]["deployment"], "commit_vendored")
            self.assertIn("MIT", by_id[asset_id]["license"])

    def test_committed_assets_verify_exactly(self):
        for asset in rc.required_assets(self.manifest):
            if asset["deployment"] == "download":
                continue
            state, detail = rc.check_asset_file(ROOT, asset)
            self.assertEqual(state, "ok", f"{asset['id']}: {detail}")


class DownloaderTests(unittest.TestCase):
    def test_downloader_reports_unresolved_without_starting_anything(self):
        proc = subprocess.run(
            [sys.executable, str(ROOT / "assets" / "download_assets.py"), "--check-only", "--only", "A3"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, rc.EXIT_ASSET_UNRESOLVED, proc.stdout + proc.stderr)
        self.assertIn("ASSET_URL_UNRESOLVED", proc.stderr)
        self.assertIn("A3", proc.stderr)
        self.assertIn("R7", proc.stderr)

    def test_verify_assets_reports_pending(self):
        proc = subprocess.run(
            [sys.executable, str(ROOT / "assets" / "verify_assets.py"), "--only", "A1,A3"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, rc.EXIT_ASSET_UNRESOLVED)
        self.assertIn("pending", proc.stdout)
        self.assertIn("ASSET_URL_UNRESOLVED", proc.stderr)

    def test_no_partial_files_left_behind(self):
        leftovers = list(ROOT.glob("**/*.part"))
        self.assertEqual(leftovers, [])


class RuntimeCodeTests(unittest.TestCase):
    def test_bridge_normalizes_fixture_events(self):
        bridge = load_module(ROOT / "bridge" / "activity_bridge_v1.py", "bridge_under_test")
        canonical = {1, 2, 3, 4}
        lines = [l for l in (FIXTURES / "sample_events.jsonl").read_text().splitlines() if l.strip()]

        first = json.loads(lines[0])
        activity = bridge.normalize_activity(first, canonical)
        self.assertEqual(activity["body_ids"], [1, 2, 3, 4])
        self.assertEqual(activity["schema"], bridge.SCHEMA_ACTIVITY)

        task = bridge.normalize_task(json.loads(lines[1]))
        self.assertEqual(task["phase"], "stimulus_a")
        self.assertEqual(task["payload"]["size_px"], 130)

        self.assertEqual(bridge.detect_event_type(json.loads(lines[2])), "activity")
        self.assertEqual(bridge.detect_event_type(json.loads(lines[3])), "task")

    def test_bridge_rejects_non_canonical_body_id(self):
        bridge = load_module(ROOT / "bridge" / "activity_bridge_v1.py", "bridge_under_test_2")
        with self.assertRaises(ValueError):
            bridge.normalize_activity(
                {"type": "activity", "t_ms": 1.0, "body_ids": [99], "values": [0.5]}, {1, 2}
            )

    def test_viewer_reads_newest_complete_json_line(self):
        viewer = load_module(ROOT / "viewer" / "server_viewer.py", "viewer_under_test")
        obj = viewer.latest_valid_json(FIXTURES / "sample_live.jsonl")
        self.assertEqual(obj["t_ms"], 2.0)
        self.assertEqual(obj["body_ids"], [2])
        self.assertEqual(viewer.latest_valid_json(FIXTURES / "does_not_exist.jsonl"), {})

    def test_viewer_presentation_unchanged(self):
        main_js = (ROOT / "viewer" / "web" / "main.js").read_text()
        self.assertIn("neuronGain=.65", main_js)
        self.assertIn("activityThreshold=.22", main_js)
        self.assertIn("decayActivity(.82)", main_js)

    def test_platform_web_close_button_uses_shutdown_endpoint(self):
        html = (ROOT / "platform" / "web" / "index.html").read_text()
        self.assertIn("/api/shutdown", html)
        server = (ROOT / "platform" / "server.py").read_text()
        self.assertIn("stop.sh", server)
        self.assertIn("/api/run-demo", server)

    def test_config_paths_are_repo_relative(self):
        paths = load_module(ROOT / "config" / "paths.py", "paths_under_test")
        self.assertEqual(paths.ROOT, ROOT)
        self.assertTrue(str(paths.RUNTIME_ROOT).endswith("/.runtime"))
        self.assertTrue(str(paths.CANONICAL_BODY_IDS).endswith("/data/canonical_body_ids.txt"))


class SafetyTests(unittest.TestCase):
    def test_shell_scripts_parse(self):
        for script in SHELL_SCRIPTS:
            proc = subprocess.run(["bash", "-n", str(ROOT / script)], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, f"{script}: {proc.stderr}")

    def test_no_pattern_based_process_termination(self):
        for rel, path in iter_repo_files():
            if rel == SELF:
                continue
            if path.suffix in {".py", ".sh", ".md"}:
                text = path.read_text(errors="ignore")
                for token in FORBIDDEN_KILL_TOKENS:
                    self.assertNotIn(token, text, f"{rel} contains forbidden token {token}")

    def test_stop_sh_signals_only_recorded_pids(self):
        text = (ROOT / "stop.sh").read_text()
        self.assertIn("pids", text)
        self.assertIn("owned_by_repo", text)
        self.assertNotIn("lsof", text)

    def test_no_foreign_or_absolute_developer_paths(self):
        for rel, path in iter_repo_files():
            if rel == SELF or path.suffix not in TEXT_SUFFIXES:
                continue
            text = path.read_text(errors="ignore")
            for token in FORBIDDEN_PATH_TOKENS:
                self.assertNotIn(token, text, f"{rel} contains forbidden path token {token}")

    def test_runtime_state_is_gitignored(self):
        ignore = (ROOT / ".gitignore").read_text()
        self.assertIn(".runtime/", ignore)
        self.assertIn(".venv/", ignore)
        for name in ("neurons_lines.bin", "brain_shell.bin", "vnc_shell.bin"):
            self.assertIn(name, ignore)

    def test_no_large_assets_or_source_symlinks(self):
        for rel, path in iter_repo_files():
            self.assertFalse(path.is_symlink(), f"{rel} is a symlink")
            size_mib = path.stat().st_size / (1024 * 1024)
            self.assertLess(size_mib, 10, f"{rel} is {size_mib:.1f} MiB (too large for this repo)")
        for name in ("neurons_lines.bin", "brain_shell.bin", "vnc_shell.bin"):
            self.assertFalse((ROOT / "viewer" / "web" / "assets" / name).exists(), name)

    def test_no_dynamics_content(self):
        marker = "dynamics" + "_v1"
        for rel, path in iter_repo_files():
            self.assertNotIn(marker, rel.lower(), rel)
            if rel == SELF:
                continue
            if path.suffix in {".py", ".sh", ".json", ".yaml", ".yml"}:
                self.assertNotIn(marker, path.read_text(errors="ignore").lower(), rel)
        for directory in ROOT.rglob(marker):
            self.fail(f"dynamics directory present: {directory}")

    def test_no_secrets_markers(self):
        pattern = re.compile(r"(BEGIN [A-Z ]*PRIVATE KEY|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16})")
        for rel, path in iter_repo_files():
            if path.suffix in TEXT_SUFFIXES:
                self.assertIsNone(pattern.search(path.read_text(errors="ignore")), rel)


class CleanRuntimeTests(unittest.TestCase):
    def test_clean_runtime_dry_run_and_apply(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / ".runtime" / "activity").mkdir(parents=True)
            (tmp_path / ".runtime" / "activity" / "live.jsonl").write_text("{}\n")
            dry = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "clean_runtime.py"), "--repo-root", str(tmp_path), "--dry-run"],
                capture_output=True, text=True,
            )
            self.assertEqual(dry.returncode, 0, dry.stderr)
            self.assertTrue((tmp_path / ".runtime" / "activity" / "live.jsonl").exists())
            apply = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "clean_runtime.py"), "--repo-root", str(tmp_path)],
                capture_output=True, text=True,
            )
            self.assertEqual(apply.returncode, 0, apply.stderr)
            self.assertFalse((tmp_path / ".runtime" / "activity").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
