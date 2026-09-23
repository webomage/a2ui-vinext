#!/usr/bin/env python3
"""Tests for scripts/deploy_function.py (T431). Never deploys: validation and --dry-run only."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "deploy_function.py"
BASE = ["--project-ref", "pqbbjgeapylcengbuvee", "--infisical-project-id", "x"]


def run(*args: str):
    return subprocess.run([sys.executable, str(SCRIPT), *args, *BASE], capture_output=True, text=True)


class DeployFunctionTest(unittest.TestCase):
    def test_list_matches_function_dirs(self):
        names = run("--list").stdout.split()
        self.assertIn("get-bot-status", names)
        self.assertNotIn("_shared", names)
        self.assertNotIn("node_modules", names)
        self.assertGreater(len(names), 40)

    def test_unknown_name_fails_closed_with_suggestion(self):
        r = run("get-bot-statsu", "--dry-run")
        self.assertEqual(r.returncode, 1)
        self.assertIn("did you mean: get-bot-status", r.stdout)
        self.assertIn("Nothing was deployed", r.stdout)

    def test_one_bad_name_blocks_the_whole_batch(self):
        r = run("get-bot-status", "no-such-fn", "--dry-run")
        self.assertEqual(r.returncode, 1)
        self.assertNotIn("DRY RUN", r.stdout)

    def test_no_names_fails(self):
        self.assertEqual(run("--dry-run").returncode, 1)

    def test_duplicate_fails(self):
        self.assertEqual(run("hume-token", "hume-token", "--dry-run").returncode, 1)

    def test_dry_run_builds_one_multi_function_command_with_project_id(self):
        r = run("get-bot-status", "hume-token", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("--projectId=x", r.stdout)
        self.assertIn("functions deploy get-bot-status hume-token --use-api", r.stdout)
        self.assertNotIn("DEPLOY_VERSION", r.stdout)  # a partial redeploy is not a release

    def test_no_per_function_recipes_remain_in_wom7api(self):
        text = (ROOT / "wom7api" / "justfile").read_text()
        left = re.findall(r"supabase functions deploy [a-z0-9-]+ --use-api", text)
        self.assertEqual(left, [], "per-function deploy lines must go through `just deploy-function`")

    def test_root_recipe_is_confirm_gated(self):
        text = (ROOT / "justfile").read_text()
        self.assertIn('deploy-function +names: (_confirm "deploy-function")', text)

    def test_root_justfile_exports_db_migrations_for_config_toml(self):
        # config.toml's env(W0M_DB_MIGRATIONS) has no default; unset = ProjectConfigParseError on
        # every supabase command. The first real `just deploy-function` died on exactly this.
        text = (ROOT / "justfile").read_text()
        self.assertIn("export W0M_DB_MIGRATIONS := env_var_or_default('W0M_DB_MIGRATIONS', 'true')", text)
        r = subprocess.run(["just", "--justfile", str(ROOT / "justfile"), "--evaluate", "W0M_DB_MIGRATIONS"],
                           capture_output=True, text=True,
                           env={k: v for k, v in os.environ.items() if k != "W0M_DB_MIGRATIONS"})
        self.assertEqual(r.stdout.strip(), "true", r.stderr)


class _GlyphResult(unittest.TextTestResult):
    """One ✅/❌ line per test, so run_suites.count_checks() can count this suite."""

    def addSuccess(self, test):
        super().addSuccess(test)
        print(f"✅ {test._testMethodName}")

    def addFailure(self, test, err):
        super().addFailure(test, err)
        print(f"❌ {test._testMethodName}")

    def addError(self, test, err):
        super().addError(test, err)
        print(f"❌ {test._testMethodName} (error)")


if __name__ == "__main__":
    unittest.main(testRunner=unittest.TextTestRunner(resultclass=_GlyphResult, verbosity=0))
