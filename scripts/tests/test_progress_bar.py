#!/usr/bin/env python3
"""Unit tests for `scripts/progress_bar.py` (`T677`)."""

from __future__ import annotations

import io
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from progress_bar import StepProgress, format_duration, format_progress_bar


class ProgressBarTests(unittest.TestCase):
    def test_format_duration(self) -> None:
        self.assertEqual(format_duration(0), "00:00s")
        self.assertEqual(format_duration(65.2), "01:05s")
        self.assertEqual(format_duration(3661), "01:01:01s")

    def test_format_progress_bar_bounds_and_output(self) -> None:
        line0 = format_progress_bar(0, 10, "starting", width=10, elapsed_sec=0.0, prefix="[test]")
        self.assertIn("[test] [ 0/10] [░░░░░░░░░░]   0% | 00:00s | starting", line0)

        line5 = format_progress_bar(5, 10, "halfway", width=10, elapsed_sec=12.4, prefix="[test]")
        self.assertIn("[test] [ 5/10] [█████░░░░░]  50% | 00:12s | halfway", line5)

        line10 = format_progress_bar(10, 10, "complete", width=10, elapsed_sec=25.0, prefix="[test]")
        self.assertIn("[test] [10/10] [██████████] 100% | 00:25s | complete", line10)

    def test_step_progress_writes_to_stream(self) -> None:
        buf = io.StringIO()
        prog = StepProgress(4, prefix="[wrapup]", width=8, stream=buf)
        prog.advance("step-1")
        prog.advance("step-2")
        prog.emit(4, "done")
        out = buf.getvalue().splitlines()
        self.assertEqual(len(out), 3)
        self.assertIn("[wrapup] [1/4] [██░░░░░░]  25%", out[0])
        self.assertIn("| step-1", out[0])
        self.assertIn("[wrapup] [2/4] [████░░░░]  50%", out[1])
        self.assertIn("[wrapup] [4/4] [████████] 100%", out[2])


if __name__ == "__main__":
    unittest.main()
