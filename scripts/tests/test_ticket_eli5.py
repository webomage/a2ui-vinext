#!/usr/bin/env python3
"""T568 — Unit tests for `scripts/ticket_eli5.py` (`just eli5 T*`)."""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import tasks_query as tq  # noqa: E402
import ticket_eli5 as te  # noqa: E402


class TestTicketEli5(unittest.TestCase):
    def test_single_id_and_bare_number_lookup(self) -> None:
        self.assertEqual(te.normalize_selectors(["T57"]), ["T57"])
        self.assertEqual(te.normalize_selectors(["57"]), ["T57"])
        self.assertEqual(te.normalize_selectors(["T57,T9"]), ["T57", "T9"])
        self.assertEqual(te.normalize_selectors([".tasks/T57.md"]), ["T57"])

        tickets = tq.load()
        matched, unknown = te.select_tickets(tickets, ["T57", "9"])
        self.assertEqual(unknown, [])
        self.assertEqual([t["id"] for t in matched], ["T57", "T9"])

    def test_unquoted_bash_root_glob_recovery(self) -> None:
        """When a user runs unquoted `just eli5 T*` in `@wom` root, bash expands `T*` to
        `TASKS.md TECH-DEBT.md`. `normalize_selectors` must recover `['T*']`.
        """
        self.assertEqual(te.normalize_selectors(["TASKS.md", "TECH-DEBT.md"]), ["T*"])
        self.assertEqual(te.normalize_selectors(["TASKS.md"]), ["T*"])
        self.assertEqual(te.normalize_selectors([]), ["T*"])

    def test_wildcard_prefix_selection_and_filters(self) -> None:
        tickets = tq.load()
        matched_open, unknown = te.select_tickets(tickets, ["T*"], area="ai")
        self.assertEqual(unknown, [])
        for t in matched_open:
            self.assertEqual(t.get("area"), "ai")
            self.assertTrue(t.get("open"))

        matched_all, unknown_all = te.select_tickets(tickets, ["T5*"], area="ai", include_all=True)
        self.assertEqual(unknown_all, [])
        ids_all = [t["id"] for t in matched_all]
        self.assertIn("T57", ids_all)
        self.assertIn("T500", ids_all)

    def test_unknown_ticket_returns_error(self) -> None:
        tickets = tq.load()
        matched, unknown = te.select_tickets(tickets, ["T99999"])
        self.assertEqual(matched, [])
        self.assertEqual(unknown, ["T99999"])
        rc = te.main(["T99999"])
        self.assertEqual(rc, 1)

    def test_every_open_ticket_produces_single_paragraph_eli5(self) -> None:
        tickets = [t for t in tq.load() if t.get("open")]
        self.assertGreater(len(tickets), 0)
        for t in tickets:
            para = te.synthesize_eli5_paragraph(t)
            self.assertTrue(para, f"{t['id']} produced empty ELI5")
            self.assertNotIn("\n", para, f"{t['id']} ELI5 must be a single paragraph without newlines")
            self.assertGreaterEqual(len(para), 60, f"{t['id']} ELI5 is unexpectedly short: {para!r}")

    def test_frontmatter_and_section_override_synthesis(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p_fm = pathlib.Path(tmp) / "T901.md"
            p_fm.write_text(
                "---\nid: T901\ntitle: \"Demo\"\nstatus: queued\neli5: \"Custom frontmatter ELI5 explanation.\"\n---\n# T901\n",
                encoding="utf-8",
            )
            fake_t = {"id": "T901", "title": "Demo", "status": "queued", "open": True}
            self.assertEqual(
                te.synthesize_eli5_paragraph(fake_t, ticket_path=p_fm),
                "Custom frontmatter ELI5 explanation.",
            )

            p_sec = pathlib.Path(tmp) / "T902.md"
            p_sec.write_text(
                "---\nid: T902\ntitle: \"Demo 2\"\nstatus: queued\n---\n# T902\n\n## ELI5\n\nSimple section explanation.\nWrapped second line.\n\n## Summary\nOther text.\n",
                encoding="utf-8",
            )
            fake_t2 = {"id": "T902", "title": "Demo 2", "status": "queued", "open": True}
            self.assertEqual(
                te.synthesize_eli5_paragraph(fake_t2, ticket_path=p_sec),
                "Simple section explanation. Wrapped second line.",
            )

    def test_cli_json_and_tasks_query_delegation(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "tasks_query.py"), "eli5", "T57", "--json"],
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(proc.stdout)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], "T57")
        self.assertIn("Intent Router", data[0]["eli5"])


if __name__ == "__main__":
    unittest.main()
