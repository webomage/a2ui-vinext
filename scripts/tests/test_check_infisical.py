#!/usr/bin/env python3
"""Tests for scripts/check_infisical.py (T429).

Drives the checker against a FAKE `infisical` CLI (a shell stub whose stderr/exit are set per test),
so no real session, network or secret is touched. RED-first: the no-link case is the 2026-09-23
incident that the old recipe misreported as "session expired".
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_infisical.py"

REAL_NO_LINK = "Please either run infisical init to connect to a project or pass in project id with --projectId flag"
REAL_WRONG_ID = ('error: failed to fetch secrets for path "/": CallGetRawSecretsV3 Unsuccessful response '
                 "[status-code=404] [message=\"Project with ID '0000' not found during bot lookup. "
                 'Are you sure you are using the correct project ID?"]')


class CheckInfisicalTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.work = self.tmp / "work"  # no .infisical.json anywhere above it inside tmp
        self.work.mkdir()
        self.fake = self.tmp / "infisical"

    def make_fake(self, stderr: str, code: int):
        msg = self.tmp / "stderr.txt"  # a file, so no shell quoting of the message is needed
        msg.write_text(stderr + "\n")
        self.fake.write_text(f"#!/bin/sh\ncat '{msg}' >&2\nexit {code}\n")
        self.fake.chmod(self.fake.stat().st_mode | stat.S_IEXEC)

    def run_check(self, *args: str, cwd: Path | None = None):
        env = {**os.environ, "W0M_INFISICAL_BIN": str(self.fake)}
        return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd or self.work,
                              env=env, capture_output=True, text=True)

    def test_red_no_link_and_no_project_id_is_not_reported_as_login(self):
        self.make_fake("should not be called", 0)
        r = self.run_check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("project link missing", r.stdout)
        self.assertIn("NOT a login problem", r.stdout)
        self.assertNotIn("expired", r.stdout)

    def test_cli_asks_for_init_is_classified_no_link(self):
        self.make_fake(REAL_NO_LINK, 1)
        r = self.run_check("--project-id", "x")
        self.assertEqual(r.returncode, 1)
        self.assertIn("project link missing", r.stdout)
        self.assertIn("infisical init", r.stdout)  # the real CLI line is shown

    def test_wrong_project_id(self):
        self.make_fake(REAL_WRONG_ID, 1)
        r = self.run_check("--project-id", "0000")
        self.assertEqual(r.returncode, 1)
        self.assertIn("project id is wrong", r.stdout)

    def test_expired_session_is_auth(self):
        self.make_fake("Your login session has expired, please run [infisical login]", 1)
        r = self.run_check("--project-id", "x")
        self.assertEqual(r.returncode, 1)
        self.assertIn("session invalid/expired", r.stdout)
        self.assertIn("infisical login", r.stdout)

    def test_other_error_shows_first_stderr_line_only(self):
        self.make_fake("boom: something unexpected\nsecond line must not print", 3)
        r = self.run_check("--project-id", "x")
        self.assertEqual(r.returncode, 1)
        self.assertIn("does not recognise", r.stdout)
        self.assertIn("boom: something unexpected", r.stdout)
        self.assertNotIn("second line", r.stdout)

    def test_success_with_link_file_found_in_parent(self):
        (self.tmp / ".infisical.json").write_text('{"workspaceId": "x"}')
        self.make_fake("2026-09-23 INF Injecting 105 Infisical secrets into your application process", 0)
        r = self.run_check()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("authenticated", r.stdout)

    def test_missing_cli(self):
        env = {**os.environ, "W0M_INFISICAL_BIN": str(self.tmp / "nope")}
        r = subprocess.run([sys.executable, str(SCRIPT), "--project-id", "x"], cwd=self.work,
                           env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("CLI not found", r.stdout)

    def test_update_banner_on_success_triggers_auto_upgrade(self):
        marker = self.tmp / "upgraded.txt"
        self.make_fake(
            "2026-10-21 INF Injecting 107 Infisical secrets into your application process\n"
            "A new release of infisical is available: 0.44.1 -> 0.44.3\n"
            "To update, run: sudo apt-get update && sudo apt-get install infisical",
            0,
        )
        env = {
            **os.environ,
            "W0M_INFISICAL_BIN": str(self.fake),
            "W0M_INFISICAL_UPGRADE_CMD": f"printf 'upgraded' > '{marker}'",
        }
        r = subprocess.run([sys.executable, str(SCRIPT), "--project-id", "x"], cwd=self.work,
                           env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("0.44.1 -> 0.44.3", r.stdout)
        self.assertIn("auto-upgraded", r.stdout)
        self.assertTrue(marker.is_file(), "expected auto-upgrade command to run when update banner is printed")


class RootJustfileProjectIdTest(unittest.TestCase):
    """Every `infisical run` in the root justfile passes the single explicit project id (T429 AC2)."""

    def test_every_root_infisical_run_passes_project_id(self):
        text = (ROOT / "justfile").read_text()
        runs = [ln for ln in text.splitlines() if "infisical run" in ln and not ln.lstrip().startswith("#")]
        self.assertGreater(len(runs), 10)
        missing = [ln.strip() for ln in runs if "--projectId={{ infisical_project_id }}" not in ln]
        self.assertEqual(missing, [], f"infisical run without explicit project id: {missing}")

    def test_project_id_variable_declared_once(self):
        text = (ROOT / "justfile").read_text()
        self.assertEqual(text.count("infisical_project_id :="), 1)


class _GlyphResult(unittest.TextTestResult):
    """One ✅/❌ line per test, so run_suites.count_checks() can count this suite (T224 ratchet)."""

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
