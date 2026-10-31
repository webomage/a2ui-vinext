#!/usr/bin/env python3
"""Unit & integration tests for `scripts/ast_grep_check.py` (T589)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import ast_grep_check  # noqa: E402


class TestAstGrepCheck(unittest.TestCase):
    def test_config_and_rules_exist(self) -> None:
        self.assertTrue(ast_grep_check.DEFAULT_CONFIG.exists(), "sgconfig.yml must exist at root")
        rule_ids = ast_grep_check.load_rule_ids()
        self.assertIn("w0m-no-env-fallback-chain", rule_ids)
        self.assertIn("w0m-no-eval-call-ts", rule_ids)
        self.assertIn("w0m-no-bare-except-pass-py", rule_ids)

    def test_detects_violations_in_temp_fixtures(self) -> None:
        if not ast_grep_check.find_ast_grep_binary():
            self.skipTest("ast-grep binary not installed")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bad_ts = tmp_path / "bad.ts"
            bad_ts.write_text(
                "const key = process.env.A || process.env.B || process.env.C;\n"
                "const out = eval('2 + 2');\n",
                encoding="utf-8",
            )
            bad_py = tmp_path / "bad.py"
            bad_py.write_text(
                "def run():\n"
                "    try:\n"
                "        x = 1\n"
                "    except:\n"
                "        pass\n",
                encoding="utf-8",
            )

            report = ast_grep_check.run_ast_grep_scan([tmp_path])
            matched_rules = {f["ruleId"] for f in report["findings"]}
            self.assertIn("w0m-no-env-fallback-chain", matched_rules)
            self.assertIn("w0m-no-eval-call-ts", matched_rules)
            self.assertIn("w0m-no-bare-except-pass-py", matched_rules)
            self.assertFalse(report["ok"], "eval() error severity must mark report ok=False")

    def test_clean_fixtures_pass(self) -> None:
        if not ast_grep_check.find_ast_grep_binary():
            self.skipTest("ast-grep binary not installed")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            good_ts = tmp_path / "good.ts"
            good_ts.write_text(
                "export const apiUrl = process.env.PUBLIC_SUPABASE_URL;\n",
                encoding="utf-8",
            )
            good_py = tmp_path / "good.py"
            good_py.write_text(
                "def safe():\n"
                "    try:\n"
                "        return 42\n"
                "    except ValueError as exc:\n"
                "        raise RuntimeError(str(exc)) from exc\n",
                encoding="utf-8",
            )

            report = ast_grep_check.run_ast_grep_scan([tmp_path])
            self.assertTrue(report["ok"])
            self.assertEqual(report["findings"], [])


if __name__ == "__main__":
    unittest.main()
