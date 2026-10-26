#!/usr/bin/env python3
"""The `prepush` tier of the suite registry (T503).

`just test` runs 211 suites in ~8 minutes and only at deploy time, so a failure in a suite that takes half a second was discovered after a release cut,
a Touch ID and eight minutes of other suites (2026-09-30: spec-standard, ac-recipe-check, ds-conformance and state all failed that way). A suite that is
deterministic and finishes in under a few seconds can run where the change is made. `"prepush": true` in project/test-suites.json marks one; `run_suites.py
--prepush` runs exactly those, and the pre-push hook and the deploy pre-flight both call it, so the two cannot drift apart.

Asserted: selection is by the flag only; a flagged suite must be offline and blocking (an advisory suite cannot gate a push, a live one cannot run offline);
the real registry flags the ratchets that failed on 2026-09-30; and the runner does not wipe the full run's raw logs.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("run_suites", ROOT / "scripts" / "run_suites.py")
assert spec is not None and spec.loader is not None
rs = importlib.util.module_from_spec(spec)
sys.modules["run_suites"] = rs
spec.loader.exec_module(rs)

S = [
    {"name": "a", "recipe": "a-test", "tier": "offline", "blocking": True, "prepush": True},
    {"name": "b", "recipe": "b-test", "tier": "offline", "blocking": True},
    {"name": "c", "recipe": "c-test", "tier": "live", "blocking": True},
    {"name": "d", "recipe": "d-test", "tier": "offline", "blocking": True, "prepush": False},
]


class TestSelection(unittest.TestCase):
    def test_prepush_selects_only_flagged_suites(self):
        self.assertEqual([s["name"] for s in rs.select_suites(S, "offline", prepush=True)], ["a"])

    def test_the_normal_tiers_are_unchanged(self):
        self.assertEqual([s["name"] for s in rs.select_suites(S, "offline")], ["a", "b", "d"])
        self.assertEqual([s["name"] for s in rs.select_suites(S, "all")], ["a", "b", "c", "d"])
        self.assertEqual([s["name"] for s in rs.select_suites(S, "live")], ["c"])

    def test_a_flagged_suite_that_is_not_offline_is_a_problem(self):
        bad = [{"name": "x", "recipe": "x", "tier": "live", "blocking": True, "prepush": True}]
        self.assertTrue(any("offline" in p for p in rs.prepush_problems(bad)))

    def test_a_flagged_suite_that_is_advisory_is_a_problem(self):
        bad = [{"name": "x", "recipe": "x", "tier": "offline", "blocking": False, "prepush": True}]
        self.assertTrue(any("blocking" in p for p in rs.prepush_problems(bad)))

    def test_a_clean_registry_has_no_problems(self):
        self.assertEqual(rs.prepush_problems(S), [])

    def test_the_flag_must_be_a_real_boolean(self):
        bad = [{"name": "x", "recipe": "x", "tier": "offline", "blocking": True, "prepush": "yes"}]
        self.assertTrue(rs.prepush_problems(bad))


class TestRealRegistry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.suites = json.loads((ROOT / "wom7web" / "project" / "test-suites.json").read_text())["suites"]

    def test_the_real_registry_is_valid(self):
        self.assertEqual(rs.prepush_problems(self.suites), [])

    def test_the_ratchets_that_failed_a_deploy_are_flagged(self):
        flagged = {s["name"] for s in rs.select_suites(self.suites, "offline", prepush=True)}
        for name in ("spec-standard-gate", "ac-recipe-check", "ds-conformance-selftest", "suites-drift"):
            self.assertIn(name, flagged, f"{name} failed a deploy on 2026-09-30 / 2026-10-06 and is not in the prepush tier")

    def test_the_prepush_tier_stays_small(self):
        n = len(rs.select_suites(self.suites, "offline", prepush=True))
        self.assertLessEqual(n, 15, f"{n} suites in the prepush tier: it exists to be fast, so it is not where every suite goes")


class TestRunnerHygiene(unittest.TestCase):
    def test_a_prepush_run_does_not_write_the_full_run_raw_logs(self):
        src = (ROOT / "scripts" / "run_suites.py").read_text()
        self.assertIn("if not args.prepush:", src, "the prepush path must skip the raw-log dump, which deletes the previous full run's logs")


if __name__ == "__main__":
    result = unittest.main(verbosity=1, exit=False).result
    sys.exit(0 if result.wasSuccessful() else 1)
