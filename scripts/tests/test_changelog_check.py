#!/usr/bin/env python3
"""Red probes for changelog_check.py (T436): Public disclosure guardrails & PII redaction."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "changelog_check.py"


def run_check(path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--path", str(path)],
        capture_output=True,
        text=True,
    )


class ChangelogCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="cl-check-"))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_clean_changelog_passes(self):
        cl = self.tmp_dir / "CHANGELOG.md"
        cl.write_text(
            "# Changelog\n\n"
            "## 2026.09.24-1790226662\n"
            "_First deployed: 2026-09-24 05:25:26_\n\n"
            "### Features\n"
            "- Add public-safe changelog generator ([T436](file:///.tasks/T436.md))\n\n"
            "### Fixes\n"
            "- Resolve memory leak in edge runner\n\n"
            "| Service | Commit | Deployed at |\n"
            "|---|---|---|\n"
            "| release | `b8f0de0` | 2026-09-24 05:25:26 |\n"
        )
        r = run_check(cl)
        self.assertEqual(r.returncode, 0, f"Expected 0, got {r.returncode}: {r.stderr or r.stdout}")
        self.assertIn("changelog-check passed", r.stdout)

    def test_email_address_fails(self):
        cl = self.tmp_dir / "CHANGELOG.md"
        cl.write_text(
            "# Changelog\n\n"
            "## 2026.09.24-1790226662\n"
            "| Service | Commit | Actor | Deployed at |\n"
            "| release | `b8f0de0` | casualuser@gmail.com | 2026-09-24 05:25:26 |\n"
        )
        r = run_check(cl)
        self.assertEqual(r.returncode, 1)
        self.assertIn("EMAIL", r.stdout)
        self.assertIn("casualuser@gmail.com", r.stdout)

    def test_confidential_client_marker_fails(self):
        cl = self.tmp_dir / "CHANGELOG.md"
        cl.write_text(
            "# Changelog\n\n"
            "## 2026.09.24-1790226662\n"
            "- Internal fix for CONFIDENTIAL-CLIENT-DATA\n"
        )
        r = run_check(cl)
        self.assertEqual(r.returncode, 1)
        self.assertIn("CONFIDENTIAL", r.stdout)

    def test_secret_token_marker_fails(self):
        cl = self.tmp_dir / "CHANGELOG.md"
        cl.write_text(
            "# Changelog\n\n"
            "## 2026.09.24-1790226662\n"
            "- Update SUPABASE_SERVICE_ROLE_KEY rotation\n"
        )
        r = run_check(cl)
        self.assertEqual(r.returncode, 1)
        self.assertIn("SECRET_TOKEN", r.stdout)

    def test_nonexistent_file_fails_closed(self):
        missing = self.tmp_dir / "NONEXISTENT.md"
        r = run_check(missing)
        self.assertEqual(r.returncode, 2)
        self.assertIn("does not exist", r.stderr or r.stdout)


if __name__ == "__main__":
    unittest.main()
