#!/usr/bin/env python3
"""Unit tests for scripts/cloud_compute_check.py (T305)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import cloud_compute_check as ccc  # noqa: E402


class TestCloudComputeCheck(unittest.TestCase):
    def test_estate_cloud_compute_contract_passes(self) -> None:
        report = ccc.evaluate_cloud_compute()
        self.assertTrue(
            report.ok, f"Expected cloud_compute_check to pass on estate, got: {report.errors}"
        )
        self.assertEqual(report.surfaces_checked, 4)
        self.assertEqual(report.governed_count, 3)
        self.assertEqual(report.retired_count, 1)
        self.assertEqual(
            report.surfaces["claude-code-web-w0m"]["status"],
            "retired-unused-or-unlinked",
        )

    def test_fails_when_cloud_compute_block_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sdlc = root / "sdlc.json"
            sdlc.write_text(json.dumps({"project": "w0m"}), encoding="utf-8")
            report = ccc.evaluate_cloud_compute(
                sdlc_path=sdlc,
                estate_root=root,
                justfile_path=root / "justfile",
                expected_disk_surfaces={},
            )
            self.assertFalse(report.ok)
            self.assertTrue(any("Missing `cloud_compute`" in e for e in report.errors))

    def test_fails_on_undeclared_disk_surface_or_missing_spend_monitor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "w0m-cf").mkdir(parents=True)
            (root / "w0m-cf" / "wrangler.toml").write_text("name = 'w0m-cf'\n", encoding="utf-8")
            justfile = root / "justfile"
            justfile.write_text("deploy-workers:\n    @echo ok\n", encoding="utf-8")
            sdlc = root / "sdlc.json"
            sdlc.write_text(
                json.dumps(
                    {
                        "cloud_compute": {
                            "surfaces": {
                                "claude-code-web-w0m": {
                                    "status": "retired-unused-or-unlinked",
                                    "owner": "casualuser",
                                    "cost_ceiling_usd": 0,
                                    "rationale": "Retired unused web environment.",
                                }
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            report = ccc.evaluate_cloud_compute(
                sdlc_path=sdlc,
                estate_root=root,
                justfile_path=justfile,
                expected_disk_surfaces={
                    "cloudflare-workers-w0m-cf": "w0m-cf/wrangler.toml"
                },
            )
            self.assertFalse(report.ok)
            self.assertTrue(
                any("Undeclared remote compute surface on disk" in e for e in report.errors)
            )


if __name__ == "__main__":
    unittest.main()
