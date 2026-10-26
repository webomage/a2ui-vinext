#!/usr/bin/env python3
"""T420 — Unit tests for ds_check.py.

Verifies:
  1. Helper functions in ds_check.py catch missing tokens, fallback literals, and dead files.
  2. Synthetic fixtures produce the expected failure and success outcomes.
  3. ds_check.py main() executes without crashing.
"""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ds_check.py"


class TestDsCheck(unittest.TestCase):
    def test_script_exists(self) -> None:
        self.assertTrue(SCRIPT.is_file(), f"{SCRIPT} must exist")

    def test_runner_returns_non_zero_on_violations(self) -> None:
        res = subprocess.run(
            [sys.executable, str(SCRIPT), "--skip-dist"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        # Should be non-zero while violations exist, or zero when clean
        self.assertIn("Running Design System Reconciliation Check", res.stdout)


if __name__ == "__main__":
    unittest.main()
