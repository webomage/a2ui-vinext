#!/usr/bin/env python3
"""Unit and regression tests for `scripts/epic_completeness.py` and `T355` (AC1–AC8)."""
from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import epic_completeness as ec  # noqa: E402
import tasks_query as tq  # noqa: E402
import ticket_schema_check as tsc  # noqa: E402


class TestEpicCompletenessT355(unittest.TestCase):
    def test_ac1_all_roadmap_headers_carry_canonical_3_level_tags(self) -> None:
        by_tag, untagged, duplicates = ec.parse_roadmap_headers()
        self.assertGreaterEqual(len(by_tag), 34)
        self.assertEqual(untagged, [], f"Untagged ROADMAP headers: {untagged}")
        self.assertEqual(duplicates, [], f"Duplicate ROADMAP tags: {duplicates}")
        for tag, info in by_tag.items():
            self.assertEqual(len(tq.tag_family(tag)), 3, f"{tag} is not a 3-level tag")
            self.assertTrue(info["section"].isdigit())

    def test_ac2_epic_key_derives_rollup_via_tag_family(self) -> None:
        self.assertEqual(tq.epic_key("sdlc_tooling_platform"), "sdlc_tooling_platform")
        self.assertEqual(tq.epic_key("client_alfa_features"), "client_alfa_features")
        # Subsection tag under `sdlc_tooling` rolls up to `sdlc_tooling_platform`
        self.assertEqual(tq.epic_key("sdlc_tooling_skills"), "sdlc_tooling_platform")
        self.assertEqual(tq.epic_key("sdlc_tooling_platform — child of T149"), "sdlc_tooling_platform")
        # Legacy synthetic fixture fallback stays intact
        self.assertEqual(tq.epic_key("ROADMAP §13.2 — skills"), "ROADMAP §13")

    def test_ac3_ac4_epic_completeness_gates_missing_noncanonical_and_untagged(self) -> None:
        with tempfile.TemporaryDirectory(prefix="t355-ec-") as td:
            tmp = Path(td)
            rm = tmp / "ROADMAP.md"
            rm.write_text(
                "# Roadmap\n\n"
                "## 1. Specs Missing `sdlc_spec_missing`\n"
                "## 2. Tooling Platform `sdlc_tooling_platform`\n",
                encoding="utf-8",
            )
            tdir = tmp / ".tasks"
            tdir.mkdir()
            (tdir / "T1.md").write_text(
                '---\nid: T1\nstatus: queued\nepic: "sdlc_spec_missing"\n---\n# T1\n',
                encoding="utf-8",
            )
            (tdir / "T2.md").write_text(
                '---\nid: T2\nstatus: done\nepic: "sdlc_tooling_platform"\n---\n# T2\n',
                encoding="utf-8",
            )
            errs, details = ec.check_epic_completeness(tickets_dir=tdir, roadmap_path=rm)
            self.assertEqual(errs, [])
            self.assertEqual(details["total_tickets"], 2)

            # RED 1: ticket with empty epic
            (tdir / "T3.md").write_text(
                '---\nid: T3\nstatus: queued\nepic: ""\n---\n# T3\n',
                encoding="utf-8",
            )
            errs_empty, _ = ec.check_epic_completeness(tickets_dir=tdir, roadmap_path=rm)
            self.assertTrue(any("empty `epic:`" in e for e in errs_empty))

            # RED 2: ticket with non-canonical epic
            (tdir / "T3.md").write_text(
                '---\nid: T3\nstatus: queued\nepic: "ROADMAP §99"\n---\n# T3\n',
                encoding="utf-8",
            )
            errs_bad, _ = ec.check_epic_completeness(tickets_dir=tdir, roadmap_path=rm)
            self.assertTrue(any("not a canonical 3-level tag" in e for e in errs_bad))

            # RED 3: untagged ROADMAP section header
            (tdir / "T3.md").unlink()
            rm.write_text(
                "# Roadmap\n\n"
                "## 1. Specs Missing `sdlc_spec_missing`\n"
                "## 2. Untagged Section Title\n",
                encoding="utf-8",
            )
            errs_untagged, _ = ec.check_epic_completeness(tickets_dir=tdir, roadmap_path=rm)
            self.assertTrue(any("missing a trailing canonical" in e for e in errs_untagged))

    def test_ac6_template_shows_canonical_3_level_tag_example(self) -> None:
        tpl = (SCRIPTS_DIR.parent / "project" / "templates" / "ticket.md").read_text(encoding="utf-8")
        self.assertIn("sdlc_tooling_platform", tpl)

    def test_ac8_cmd_overview_merges_epic_and_tag_family_into_one_block(self) -> None:
        tickets = tq.load()
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = tq.cmd_overview(tickets, 5)
        out = buf.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("── by EPIC & TAG FAMILY — 1→3 deep", out)
        self.assertNotIn("by EPIC, rolled up to ROADMAP", out)
        self.assertIn("sdlc_tooling_platform", out)


if __name__ == "__main__":
    unittest.main()
