#!/usr/bin/env python3
"""Tests for scripts/progress.py (T507)."""
from __future__ import annotations

import io
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROGRESS_SCRIPT = ROOT / "scripts" / "progress.py"

sys.path.insert(0, str(ROOT / "scripts"))
from progress import ProgressBar, format_bar


class TestProgressBar(unittest.TestCase):

    def test_format_bar_plain(self):
        bar = format_bar(step=1, total=2, label="Test step", width=10, color=False)
        self.assertIn("[ 1/2 ]", bar)
        self.assertIn("50%", bar)
        self.assertIn("Test step", bar)
        self.assertEqual(bar.count("█"), 5)
        self.assertEqual(bar.count("░"), 5)

    def test_format_bar_bounds_clamping(self):
        # Underflow
        bar_under = format_bar(step=-5, total=10, label="Under", width=10, color=False)
        self.assertIn("[ 0/10]", bar_under)
        self.assertIn("0%", bar_under)

        # Overflow
        bar_over = format_bar(step=15, total=10, label="Over", width=10, color=False)
        self.assertIn("[10/10]", bar_over)
        self.assertIn("100%", bar_over)

    def test_format_bar_with_elapsed(self):
        bar = format_bar(step=2, total=2, label="Done", width=10, elapsed=12.34, color=False)
        self.assertIn("(12.3s)", bar)

    def test_format_bar_color(self):
        bar = format_bar(step=1, total=2, label="Color test", width=10, color=True)
        self.assertIn("\033[", bar)  # ANSI escape sequence
        self.assertIn("Color test", bar)

    def test_progress_bar_class_streaming(self):
        stream = io.StringIO()
        pb = ProgressBar(total=3, title="Deploy Steps", width=10, stream=stream)
        pb.step("Compiling web")
        pb.step("Compiling cp")
        pb.finish("All apps built")

        output = stream.getvalue()
        self.assertIn("Compiling web", output)
        self.assertIn("Compiling cp", output)
        self.assertIn("All apps built", output)
        self.assertIn("▶", output)
        self.assertIn("✅", output)

    def test_cli_execution(self):
        cmd = [
            sys.executable,
            str(PROGRESS_SCRIPT),
            "--step", "3",
            "--total", "6",
            "--label", "Building packages",
            "--no-color",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        self.assertIn("[ 3/6 ]", res.stdout)
        self.assertIn("50%", res.stdout)
        self.assertIn("Building packages", res.stdout)


if __name__ == "__main__":
    unittest.main()
