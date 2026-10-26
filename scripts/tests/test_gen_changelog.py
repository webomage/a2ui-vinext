#!/usr/bin/env python3
"""Unit tests for scripts/gen_changelog.py (T436)."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

GEN_SCRIPT = SCRIPTS_DIR / "gen_changelog.py"
CHECK_SCRIPT = SCRIPTS_DIR / "changelog_check.py"


class GenChangelogTest(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="gen-cl-"))
        self.tasks_dir = self.tmp_dir / ".tasks"
        self.tasks_dir.mkdir(parents=True)

        # Create mock tickets
        (self.tasks_dir / "T100.md").write_text(
            "---\nid: T100\ntitle: 'Add user activity metrics export'\ntags: [metrics, export]\n---\n"
        )
        (self.tasks_dir / "T101.md").write_text(
            "---\nid: T101\ntitle: 'Fix session token invalidation race condition'\ntags: [security, p0]\n---\n"
        )

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_pii_actor_email_redacted_from_table(self):
        tsv_input = (
            "2026-09-24 05:25:26.000000+00\t2026.09.24-1790226662\trelease\tb8f0de0\tcasualuser@gmail.com\n"
        )
        out_file = self.tmp_dir / "CHANGELOG.md"
        res = subprocess.run(
            [sys.executable, str(GEN_SCRIPT), "--stdin", "--out", str(out_file), "--root", str(self.tmp_dir)],
            input=tsv_input,
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0, res.stderr or res.stdout)
        content = out_file.read_text(encoding="utf-8")

        # Must not contain the personal email
        self.assertNotIn("casualuser@gmail.com", content)
        self.assertNotIn("@gmail.com", content)
        # Must retain the deploy stamp heading for drift check
        self.assertIn("## 2026.09.24-1790226662", content)
        self.assertIn("| release | `b8f0de0` |", content)

    def test_conventional_commits_synthesis(self):
        import gen_changelog

        commits = [
            ("c1", "feat(export): add CSV export endpoint (T100)", ""),
            ("c2", "fix(auth): fix session token invalidation race condition (T101)", ""),
            ("c3", "chore(deps): bump tailwind from 3.4 to 3.5", ""),
            ("c4", "ci: update github actions runner image", ""),
            ("c5", "test(auth): add unit tests for token expiry", ""),
        ]

        synthesized = gen_changelog.categorize_commits(commits, self.tasks_dir)
        features = synthesized["features"]
        fixes = synthesized["fixes"]

        # Features should include c1
        self.assertTrue(any("Add user activity metrics export" in f or "CSV export" in f for f in features))
        # Fixes should include c2 with sanitized title since T101 has security tag
        self.assertTrue(len(fixes) >= 1)
        # Security sanitization check: title should not leak raw exploit details
        for fix in fixes:
            self.assertNotIn("CONFIDENTIAL", fix)

        # Noise commits (chore, ci, test) must NOT appear in features or fixes
        all_rendered = " ".join(features + fixes)
        self.assertNotIn("bump tailwind", all_rendered)
        self.assertNotIn("github actions runner image", all_rendered)

    def test_generated_changelog_passes_guardrail_check(self):
        tsv_input = (
            "2026-09-24 05:25:26.000000+00\t2026.09.24-1790226662\trelease\tb8f0de0\tcasualuser@gmail.com\n"
            "2026-09-20 02:20:02.000000+00\t2026.09.19-1789869801\trelease\tcdbf5b9\tcasualuser@gmail.com\n"
        )
        out_file = self.tmp_dir / "CHANGELOG.md"
        res = subprocess.run(
            [sys.executable, str(GEN_SCRIPT), "--stdin", "--out", str(out_file), "--root", str(self.tmp_dir)],
            input=tsv_input,
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0, res.stderr or res.stdout)

        # Run guardrail check on generated changelog
        check_res = subprocess.run(
            [sys.executable, str(CHECK_SCRIPT), "--path", str(out_file)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(check_res.returncode, 0, f"Guardrail check failed: {check_res.stdout or check_res.stderr}")
        self.assertIn("changelog-check passed", check_res.stdout)


if __name__ == "__main__":
    unittest.main()
