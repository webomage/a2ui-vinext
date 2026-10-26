#!/usr/bin/env python3
"""Unit tests for scripts/sync_manifest_versions.py (T391)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

# Add root scripts to path
SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import sync_manifest_versions


class TestSyncManifestVersions(unittest.TestCase):
    def test_version_regex(self) -> None:
        self.assertTrue(sync_manifest_versions.is_valid_version("2026.09.18-1789776786"))
        self.assertTrue(sync_manifest_versions.is_valid_version("2026.02.26-1772088006"))
        self.assertFalse(sync_manifest_versions.is_valid_version("1.0.0"))
        self.assertFalse(sync_manifest_versions.is_valid_version("v2026.09.18-1789776786"))
        self.assertFalse(sync_manifest_versions.is_valid_version("2026-09-18"))

    def test_check_manifests_parity(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            f1 = td / "app1" / "package.json"
            f2 = td / "app2" / "package.json"
            f1.parent.mkdir()
            f2.parent.mkdir()

            f1.write_text(json.dumps({"name": "app1", "version": "2026.09.18-1789776786"}, indent=2) + "\n")
            f2.write_text(json.dumps({"name": "app2", "version": "2026.09.18-1789776786"}, indent=2) + "\n")

            skews, ver = sync_manifest_versions.check_manifest_files([f1, f2])
            self.assertEqual(len(skews), 0)
            self.assertEqual(ver, "2026.09.18-1789776786")

    def test_check_manifests_skew(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            f1 = td / "app1" / "package.json"
            f2 = td / "app2" / "package.json"
            f1.parent.mkdir()
            f2.parent.mkdir()

            f1.write_text(json.dumps({"name": "app1", "version": "2026.09.18-1789776786"}, indent=2) + "\n")
            f2.write_text(json.dumps({"name": "app2", "version": "1.0.0"}, indent=2) + "\n")

            skews, ver = sync_manifest_versions.check_manifest_files([f1, f2])
            self.assertGreater(len(skews), 0)
            self.assertTrue(any("1.0.0" in s for s in skews))

    def test_apply_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            f = td / "package.json"
            f.write_text(json.dumps({"name": "demo", "version": "1.0.0", "private": True}, indent=2) + "\n")

            target_version = "2026.09.18-1789776786"
            updated = sync_manifest_versions.apply_version_to_files([f], target_version)
            self.assertEqual(len(updated), 1)

            data = json.loads(f.read_text())
            self.assertEqual(data["version"], target_version)
            self.assertEqual(data["name"], "demo")
            self.assertEqual(data["private"], True)

    def test_apply_invalid_version_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            f = td / "package.json"
            f.write_text(json.dumps({"name": "demo", "version": "1.0.0"}, indent=2) + "\n")

            with self.assertRaises(ValueError):
                sync_manifest_versions.apply_version_to_files([f], "invalid.semver.1")


if __name__ == "__main__":
    unittest.main()
