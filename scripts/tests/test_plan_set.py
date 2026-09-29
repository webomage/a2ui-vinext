#!/usr/bin/env python3
"""Unit tests for scripts/plan_set.py (T335). Every refusal path has a probe that must fire."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import plan_set  # noqa: E402

ROADMAP = """# Roadmap

## 1. Alpha Platform (P1, added 2026-01-01)
text
## 2. Beta Platform Hardening (P0, added 2026-01-02)
text
## 3. Gamma Security Work (P2)
### 3.1 not a top-level epic
## 4. Security Hardening Extras
"""

TICKETS = [
    {"id": "T1", "epic": "ROADMAP §2", "open": True, "status": "in-progress", "score": 5},
    {"id": "T2", "epic": "ROADMAP §2 — sub", "open": True, "status": "queued", "score": 3},
    {"id": "T3", "epic": "ROADMAP §1", "open": True, "status": "queued", "score": 1},
]


class PlanSetTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="plan-set-"))
        (self.tmp / ".w0m").mkdir()
        self.roadmap = self.tmp / "ROADMAP.md"
        self.roadmap.write_text(ROADMAP, encoding="utf-8")
        self.conf = self.tmp / ".w0m" / "sdlc.json"
        self.conf.write_text(json.dumps({"other": {"keep": "é"}, "current_plan": {
            "name": "Old", "roadmap": "ROADMAP.md §1", "active_stage": "s", "stages": [{"id": "s", "tickets": ["T3"]}],
        }}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        self.hist = self.tmp / ".w0m" / "plan-history.jsonl"
        self.epics = plan_set.read_epics(self.roadmap)

    def run_set(self, query, reason="because", dry=False):
        return plan_set.cmd_set(self.conf, self.hist, self.epics, TICKETS, query, reason, dry)

    def plan(self):
        return json.loads(self.conf.read_text(encoding="utf-8"))["current_plan"]

    # --- listing / resolving -------------------------------------------------
    def test_reads_only_numbered_top_level_sections_with_priority(self):
        self.assertEqual([e["n"] for e in self.epics], [1, 2, 3, 4])
        self.assertEqual(self.epics[1]["priority"], "P0")
        self.assertEqual(self.epics[1]["name"], "Beta Platform Hardening")  # parenthetical tail stripped

    def test_resolve_by_number_section_sign_and_words(self):
        for q in ("2", "§2", "ROADMAP §2", "ROADMAP.md §2"):
            self.assertEqual([e["n"] for e in plan_set.resolve(q, self.epics)], [2], q)
        self.assertEqual([e["n"] for e in plan_set.resolve("beta hardening", self.epics)], [2])

    # --- AC1: refuse zero / many -------------------------------------------------
    def test_zero_matches_writes_nothing(self):
        before = self.conf.read_text(encoding="utf-8")
        self.assertEqual(self.run_set("nonexistent"), 1)
        self.assertEqual(self.run_set("99"), 1)
        self.assertEqual(self.conf.read_text(encoding="utf-8"), before)
        self.assertFalse(self.hist.exists())

    def test_ambiguous_match_writes_nothing(self):
        before = self.conf.read_text(encoding="utf-8")
        self.assertEqual(self.run_set("security"), 1)  # Gamma Security Work + Security Hardening Extras
        self.assertEqual(self.run_set("hardening"), 1)  # Beta + Extras
        self.assertEqual(self.conf.read_text(encoding="utf-8"), before)

    # --- AC2: mechanical write with a required reason -----------------------------
    def test_reason_is_required(self):
        before = self.conf.read_text(encoding="utf-8")
        self.assertEqual(self.run_set("2", reason=""), 2)
        self.assertEqual(self.run_set("2", reason="   "), 2)
        self.assertEqual(self.conf.read_text(encoding="utf-8"), before)

    def test_unique_match_writes_plan_history_and_keeps_everything_else(self):
        self.assertEqual(self.run_set("2", reason="focus"), 0)
        p = self.plan()
        self.assertEqual((p["name"], p["roadmap"]), ("Beta Platform Hardening", "ROADMAP.md §2"))
        self.assertEqual(p["active_stage"], "wip")
        self.assertEqual([t for s in p["stages"] for t in s["tickets"]], ["T1", "T2"])  # only §2's tickets
        self.assertEqual(p["_set"]["reason"], "focus")
        self.assertEqual(json.loads(self.conf.read_text(encoding="utf-8"))["other"], {"keep": "é"})
        entry = json.loads(self.hist.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(entry["previous"]["name"], "Old")  # the swapped-out plan is kept, not lost

    def test_dry_run_writes_nothing(self):
        before = self.conf.read_text(encoding="utf-8")
        self.assertEqual(self.run_set("2", dry=True), 0)
        self.assertEqual(self.conf.read_text(encoding="utf-8"), before)

    def test_epic_without_tickets_is_refused(self):
        before = self.conf.read_text(encoding="utf-8")
        with self.assertRaises(SystemExit):
            self.run_set("3")  # no ticket rolls up to §3
        self.assertEqual(self.conf.read_text(encoding="utf-8"), before)

    # --- AC3: hand-edits are red ---------------------------------------------------
    def test_verify_passes_after_set_and_fails_after_hand_edit(self):
        self.run_set("2")
        self.assertEqual(plan_set.verify_plan(json.loads(self.conf.read_text(encoding="utf-8")), self.epics), [])
        conf = json.loads(self.conf.read_text(encoding="utf-8"))
        conf["current_plan"]["name"] = "Hand edited"
        self.assertTrue(any("edited by hand" in p for p in plan_set.verify_plan(conf, self.epics)))
        conf = json.loads(self.conf.read_text(encoding="utf-8"))
        conf["current_plan"]["roadmap"] = "ROADMAP.md §1"
        self.assertTrue(any("edited by hand" in p for p in plan_set.verify_plan(conf, self.epics)))

    def test_verify_fails_when_roadmap_section_does_not_exist_or_is_unparseable(self):
        for ref in ("ROADMAP.md §99", "nothing here", ""):
            conf = {"current_plan": {"name": "x", "roadmap": ref}}
            conf["current_plan"]["_set"] = {"fingerprint": plan_set.fingerprint(conf["current_plan"])}
            problems = plan_set.verify_plan(conf, self.epics)
            self.assertTrue(problems, ref)
            self.assertTrue(any("ROADMAP" in p for p in problems), ref)

    def test_verify_fails_without_a_stamp_and_passes_with_no_plan_declared(self):
        self.assertTrue(any("not set through" in p for p in plan_set.verify_plan(json.loads(self.conf.read_text()), self.epics)))
        self.assertEqual(plan_set.verify_plan({}, self.epics), [])  # no plan is a legitimate state

    def test_adopt_stamps_without_touching_stages_and_refuses_a_dangling_roadmap(self):
        stages_before = self.plan()["stages"]
        self.assertEqual(plan_set.cmd_adopt(self.conf, self.hist, self.epics, "bootstrap"), 0)
        self.assertEqual(self.plan()["stages"], stages_before)
        self.assertEqual(plan_set.verify_plan(json.loads(self.conf.read_text(encoding="utf-8")), self.epics), [])
        conf = json.loads(self.conf.read_text(encoding="utf-8"))
        conf["current_plan"]["roadmap"] = "ROADMAP.md §99"
        self.conf.write_text(json.dumps(conf), encoding="utf-8")
        self.assertEqual(plan_set.cmd_adopt(self.conf, self.hist, self.epics, "again"), 1)
        self.assertEqual(plan_set.cmd_adopt(self.conf, self.hist, self.epics, ""), 2)

    def test_save_roundtrips_the_config_byte_for_byte(self):
        before = self.conf.read_text(encoding="utf-8")
        plan_set.save_conf(self.conf, plan_set.load_conf(self.conf))
        self.assertEqual(self.conf.read_text(encoding="utf-8"), before)


if __name__ == "__main__":
    unittest.main(verbosity=1)
