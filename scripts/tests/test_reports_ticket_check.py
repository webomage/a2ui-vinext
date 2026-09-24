#!/usr/bin/env python3
"""Red probes for reports_ticket_check.py (T428): ticket-first reports."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "reports_ticket_check.py"


def estate(reports: dict[str, str], tickets: list[str]) -> Path:
    root = Path(tempfile.mkdtemp(prefix="rtc-"))
    (root / ".agents" / "reports").mkdir(parents=True)
    (root / ".tasks").mkdir()
    for name, body in reports.items():
        (root / ".agents" / "reports" / name).write_text(body)
    for t in tickets:
        (root / ".tasks" / f"{t}.md").write_text(f"---\nid: {t}\n---\n")
    return root


def run(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), "--root", str(root)],
                          capture_output=True, text=True)


class ReportsTicketCheck(unittest.TestCase):

    def test_ticket_in_filename_passes(self):
        self.assertEqual(run(estate({"2026-09-24-t12-x.md": "# x\n"}, ["T12"])).returncode, 0)

    def test_ticket_in_header_passes(self):
        r = run(estate({"2026-09-24-proposal.md": "# p\n\n**Status:** tickets T12–T14 created\n"}, ["T12"]))
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_no_ticket_fails_and_names_the_file(self):
        r = run(estate({"2026-09-24-orphan.md": "# research before any ticket\n"}, ["T12"]))
        self.assertEqual(r.returncode, 1)
        self.assertIn("2026-09-24-orphan.md: cites no ticket", r.stdout)

    def test_a_ticket_that_does_not_exist_fails(self):
        r = run(estate({"2026-09-24-t99-x.md": "# x\n"}, ["T12"]))
        self.assertEqual(r.returncode, 1)
        self.assertIn("cites T99, none of which exist", r.stdout)

    def test_a_citation_below_the_header_does_not_count(self):
        body = "# x\n" + "prose\n" * 20 + "see T12\n"
        self.assertEqual(run(estate({"2026-09-24-late.md": body}, ["T12"])).returncode, 1)

    def test_empty_folder_is_unmeasured_not_clean(self):
        r = run(estate({}, ["T12"]))
        self.assertEqual(r.returncode, 2)
        self.assertIn("cannot measure", r.stdout)


if __name__ == "__main__":
    unittest.main()
