#!/usr/bin/env python3
"""Tests for scripts/diagram_view.py (T211 AC4, AC6).

Verifies zero-width browser viewer generation, diagram discovery,
and fail-closed error handling for missing tickets and corrupt files.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "diagram_view.py"


def run_diagram_view(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    base_env = dict(os.environ)
    if env:
        base_env.update(env)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=base_env,
    )


class DiagramViewTest(unittest.TestCase):
    def test_missing_argument_fails(self):
        r = run_diagram_view()
        self.assertEqual(r.returncode, 1)
        self.assertIn("Missing target argument", r.stderr)

    def test_nonexistent_ticket_fails_closed(self):
        r = run_diagram_view("T99999", "--no-open")
        self.assertEqual(r.returncode, 1)
        self.assertIn("Ticket T99999 does not exist", r.stderr)

    def test_ticket_without_diagram_fails_closed(self):
        # T1 is a known ticket that has no .mmd diagram
        r = run_diagram_view("T1", "--no-open")
        self.assertEqual(r.returncode, 1)
        self.assertIn("No .mmd diagrams found for ticket T1", r.stderr)

    def test_nonexistent_file_path_fails(self):
        r = run_diagram_view("nonexistent/path/diagram.mmd", "--no-open")
        self.assertEqual(r.returncode, 1)
        self.assertIn("File not found", r.stderr)

    def test_empty_diagram_file_fails(self):
        with tempfile.NamedTemporaryFile(suffix=".mmd", mode="w", delete=False) as f:
            f.write("   \n\n  ")
            empty_path = f.name
        try:
            r = run_diagram_view(empty_path, "--no-open")
            self.assertEqual(r.returncode, 1)
            self.assertIn("empty", r.stderr.lower())
        finally:
            if os.path.exists(empty_path):
                os.unlink(empty_path)

    def test_valid_mmd_file_renders_html(self):
        with tempfile.NamedTemporaryFile(suffix=".mmd", mode="w", delete=False) as f:
            f.write("graph TD\n  Start --> Finish\n")
            mmd_path = f.name
        with tempfile.NamedTemporaryFile(suffix=".html", mode="w", delete=False) as out_f:
            out_path = out_f.name

        try:
            r = run_diagram_view(mmd_path, "--no-open", "--output", out_path)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn(f"Generated diagram preview at {Path(out_path).resolve()}", r.stdout)

            html = Path(out_path).read_text(encoding="utf-8")
            self.assertIn("<!DOCTYPE html>", html)
            self.assertIn("mermaid.initialize", html)
            self.assertIn("#020617", html)  # slate-950 canvas
            self.assertIn("Start --> Finish", html)
            self.assertIn("zoomIn()", html)
            self.assertIn("zoomOut()", html)
            self.assertIn("resetZoom()", html)
        finally:
            for p in (mmd_path, out_path):
                if os.path.exists(p):
                    os.unlink(p)

    def test_ticket_id_normalization(self):
        # Test that passing numeric id '1' normalizes to 'T1'
        r = run_diagram_view("1", "--no-open")
        self.assertEqual(r.returncode, 1)
        self.assertIn("No .mmd diagrams found for ticket T1", r.stderr)


if __name__ == "__main__":
    unittest.main()
