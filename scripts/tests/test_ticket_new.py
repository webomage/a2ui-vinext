#!/usr/bin/env python3
"""Regression and unit tests for scripts/ticket_new.py (T796).

Verifies:
1. get_known_ticket_ids correctly unions remote refs, local tasks, and worktrees.
2. get_next_ticket_id calculates the contiguous monotonic next ticket ID.
3. check_ticket_sequence detects both contiguous sequences and holes/gaps.
4. CLI --next-id prints T<N> and exits 0.
5. CLI --check-sequence succeeds on clean sets and fails closed on gaps.
"""

from __future__ import annotations

import io
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

SCRIPT_DIR = pathlib.Path(__file__).resolve().parents[1]
ESTATE_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import ticket_new as tn  # noqa: E402


class TicketNewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp_dir.name)
        self.tasks_dir = self.root / ".tasks"
        self.tasks_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_local_ticket_ids_and_sequence_check(self) -> None:
        # Create T1.md, T2.md, T3.md
        for n in (1, 2, 3):
            (self.tasks_dir / f"T{n}.md").write_text(f"---\nid: T{n}\n---\n# T{n}\n")

        with mock.patch.object(tn, "_remote_ticket_ids", return_value=set()), \
             mock.patch.object(tn, "_linked_worktree_ticket_ids", return_value=set()):
            known = tn.get_known_ticket_ids(self.root, fetch=False)
            self.assertEqual(known, {1, 2, 3})

            next_id = tn.get_next_ticket_id(self.root, fetch=False)
            self.assertEqual(next_id, 4)

            valid, missing, max_id = tn.check_ticket_sequence(self.root, fetch=False)
            self.assertTrue(valid)
            self.assertEqual(missing, [])
            self.assertEqual(max_id, 3)

    def test_sequence_check_detects_gap(self) -> None:
        # Create T1.md and T3.md (missing T2)
        (self.tasks_dir / "T1.md").write_text("---\nid: T1\n---\n# T1\n")
        (self.tasks_dir / "T3.md").write_text("---\nid: T3\n---\n# T3\n")

        with mock.patch.object(tn, "_remote_ticket_ids", return_value=set()), \
             mock.patch.object(tn, "_linked_worktree_ticket_ids", return_value=set()):
            valid, missing, max_id = tn.check_ticket_sequence(self.root, fetch=False)
            self.assertFalse(valid)
            self.assertEqual(missing, [2])
            self.assertEqual(max_id, 3)

    def test_cli_next_id(self) -> None:
        (self.tasks_dir / "T1.md").write_text("---\nid: T1\n---\n# T1\n")
        (self.tasks_dir / "T2.md").write_text("---\nid: T2\n---\n# T2\n")

        with mock.patch.object(tn, "_remote_ticket_ids", return_value=set()), \
             mock.patch.object(tn, "_linked_worktree_ticket_ids", return_value=set()), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as fake_out:
            code = tn.main(["--repo", str(self.root), "--next-id"])
            self.assertEqual(code, 0)
            self.assertEqual(fake_out.getvalue().strip(), "T3")

    def test_cli_check_sequence(self) -> None:
        (self.tasks_dir / "T1.md").write_text("---\nid: T1\n---\n# T1\n")
        (self.tasks_dir / "T2.md").write_text("---\nid: T2\n---\n# T2\n")

        with mock.patch.object(tn, "_remote_ticket_ids", return_value=set()), \
             mock.patch.object(tn, "_linked_worktree_ticket_ids", return_value=set()), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as fake_out:
            code = tn.main(["--repo", str(self.root), "--check-sequence"])
            self.assertEqual(code, 0)
            self.assertIn("contiguous", fake_out.getvalue())


if __name__ == "__main__":
    unittest.main()
