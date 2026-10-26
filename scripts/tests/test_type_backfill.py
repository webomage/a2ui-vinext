#!/usr/bin/env python3
"""Tests for `type_backfill.py` (`T434` AC5/AC7/AC9)."""

from __future__ import annotations

import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from system_one import DecisionUnavailableError, clear_fixture_responses, register_fixture_response  # noqa: E402
from type_backfill import (  # noqa: E402
    TYPE_RULES,
    classify,
    classify_regex,
    infer_type,
    main as type_backfill_main,
)


class TestTypeBackfill(unittest.TestCase):
    def tearDown(self) -> None:
        clear_fixture_responses()

    def test_legacy_regex_rules_preserved_for_offline_heuristic(self) -> None:
        self.assertIn("bug", TYPE_RULES)
        self.assertIn("feature", TYPE_RULES)
        self.assertIn("task", TYPE_RULES)

        t_bug, score_bug = classify(
            "Gate is broken and silently reports success on drift",
            "The check fails open and never fires.",
        )
        self.assertEqual(t_bug, "bug")
        self.assertGreaterEqual(score_bug, 6)

        t_task, _ = classify_regex(
            "Audit and inventory the undeclared governance suites",
            "Evaluate conformance and write it down.",
        )
        self.assertEqual(t_task, "task")

        got, score_val, src = infer_type(
            "Gate is broken and silently reports success on drift",
            "The check fails open.",
            offline_heuristic=True,
        )
        self.assertEqual(got, "bug")
        self.assertGreaterEqual(score_val, 6.0)
        self.assertEqual(src, "offline-heuristic")

    def test_primary_infer_type_uses_system_one_decide(self) -> None:
        register_fixture_response(
            "T777",
            value="feature",
            confidence=0.88,
            probabilities={"bug": 0.04, "feature": 0.88, "task": 0.08},
        )
        got, conf, src = infer_type(
            "Repos are a first-class entity",
            "Add public.project_repos table.",
            ticket_id="T777",
            provider="deterministic-fixture",
        )
        self.assertEqual(got, "feature")
        self.assertAlmostEqual(conf, 0.88)
        self.assertIn("system_one:deterministic-fixture", src)

    def test_require_provider_without_provider_reports_unmeasurable_never_regex(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(DecisionUnavailableError) as ctx:
                infer_type(
                    "Gate is broken and silently reports success",
                    "Even though regex would match bug, System One must not fall back.",
                    require_provider=True,
                )
            self.assertIn("UNMEASURABLE:", str(ctx.exception))

        with tempfile.TemporaryDirectory() as tmp:
            tdir = Path(tmp)
            (tdir / "T1.md").write_text(
                '---\nid: T1\ntitle: "Gate is broken and silently fails"\ntype: bug\n---\nBody\n',
                encoding="utf-8",
            )
            buf = io.StringIO()
            with patch.dict(os.environ, {}, clear=True), patch("sys.stdout", buf):
                rc = type_backfill_main(["--require-provider", "--tickets-dir", str(tdir)])
            self.assertEqual(rc, 0)
            self.assertIn("UNMEASURABLE:", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
