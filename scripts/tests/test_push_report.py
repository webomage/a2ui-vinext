#!/usr/bin/env python3
"""Unit tests for project/scripts/push_report.py (T390)."""

from __future__ import annotations

import io
import sys
import tempfile
import unittest
from pathlib import Path

# Add project/scripts to path
SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import push_report


class TestPushReport(unittest.TestCase):
    def test_empty_log(self) -> None:
        findings = push_report.parse_log_text("")
        self.assertEqual(findings, {})
        output = push_report.format_report(findings)
        self.assertEqual(output, "")

    def test_clean_log(self) -> None:
        clean_text = """
⏳ [w0m-web] Pre-push: type checks (astro check)...
Result (5 files): 
- 0 errors
- 0 warnings
- 0 hints
⏳ [w0m-web] Pre-push: w0m audit (scoped drift + openspec)...
  ✅ PASS  [git] working tree — clean
  ✅ PASS  [spec] spec-drift gate — clean
✅ [w0m-web] Pre-push checks passed.
"""
        findings = push_report.parse_log_text(clean_text)
        self.assertEqual(findings, {})
        output = push_report.format_report(findings)
        self.assertEqual(output, "")

    def test_astro_check_warnings(self) -> None:
        log_text = """
src/pages/jobs/[id].astro:15:9 - warning ts(6133): 'res' is declared but its value is never read.
15   const res = await fetch(`${JOBS_API}?limit=1&page=1`);
src/pages/jobs/[id].astro:11:5 - warning ts(6133): 'error' is declared but its value is never read.
11 let error = '';
Result (7 files): 
- 0 errors
- 0 warnings
- 2 hints
"""
        findings = push_report.parse_log_text(log_text)
        self.assertIn("astro-check", findings)
        self.assertEqual(len(findings["astro-check"]), 3)
        self.assertTrue(any("res" in item for item in findings["astro-check"]))
        self.assertTrue(any("error" in item for item in findings["astro-check"]))
        self.assertTrue(any("2 hint(s) reported" in item for item in findings["astro-check"]))

    def test_astro_check_ts_and_svelte_hints(self) -> None:
        log_text = """
src/pages/api/admin/impersonate.ts:192:13 - warning ts(6385): 'supabase' is deprecated.
src/components/profile/ConnectedIdentities.svelte:45:10 - hint ts(6133): 'token' is declared but its value is never read.
src/components/common/Header.tsx:12:5 - warning ts(6133): 'unused' is declared but its value is never read.
"""
        findings = push_report.parse_log_text(log_text)
        self.assertIn("astro-check", findings)
        self.assertEqual(len(findings["astro-check"]), 3)
        self.assertTrue(any("impersonate.ts" in item and "'supabase' is deprecated" in item for item in findings["astro-check"]))
        self.assertTrue(any("ConnectedIdentities.svelte" in item and "'token' is declared" in item for item in findings["astro-check"]))
        self.assertTrue(any("Header.tsx" in item and "'unused' is declared" in item for item in findings["astro-check"]))

    def test_astro_check_summary_hints_zero_vs_nonzero(self) -> None:
        zero_log = """
Result (194 files): 
- 0 errors
- 0 warnings
- 0 hints
"""
        findings_zero = push_report.parse_log_text(zero_log)
        self.assertEqual(findings_zero, {})

        nonzero_log = """
Result (194 files): 
- 0 errors
- 0 warnings
- 17 hints
"""
        findings_nonzero = push_report.parse_log_text(nonzero_log)
        self.assertIn("astro-check", findings_nonzero)
        self.assertEqual(len(findings_nonzero["astro-check"]), 1)
        self.assertIn("astro check: 17 hint(s) reported across 194 files", findings_nonzero["astro-check"][0])

    def test_audit_and_security_warnings(self) -> None:
        log_text = """
  ⚠️  WARN  [git] branch beta — 1 ahead / 0 behind origin
  ⚠️  WARN  [security] reputation-staleness — last confirmed 15d ago (>7d) — check Search Console
  ℹ️  INFO  [security] safe-browsing — set SAFE_BROWSING_API_KEY for an authoritative check
"""
        findings = push_report.parse_log_text(log_text)
        self.assertIn("audit-security", findings)
        self.assertTrue(any("reputation-staleness" in item for item in findings["audit-security"]))
        self.assertTrue(any("safe-browsing" in item for item in findings["audit-security"]))

    def test_deps_and_cli_tools(self) -> None:
        log_text = """
  ⚠  advisory @supabase/supabase-js: w0m-ext @ ^2.87.1 (target ^2.110.7) — 23 minors behind
  ⚠  1 CLI tool update(s) available (1 auto): gcloud
     `just tools-upgrade --apply` (auto subset)
"""
        findings = push_report.parse_log_text(log_text)
        self.assertIn("dependencies", findings)
        self.assertIn("cli-tools", findings)
        self.assertTrue(any("@supabase/supabase-js" in item for item in findings["dependencies"]))
        self.assertTrue(any("gcloud" in item for item in findings["cli-tools"]))

    def test_tech_debt_and_state_capacity(self) -> None:
        log_text = """
  ⚪ UNOWNED — no LIVE ticket in the Tracked cell: 17
       D1  only reference is T194 (done)
  ℹ  ⚠️ STATE.md 628/900 lines (70%) · 73,345/81,920 bytes (90%) — run `just state-rotate` before adding more
  ⚠  this push adds 2 TODO/FIXME/HACK marker(s)
"""
        findings = push_report.parse_log_text(log_text)
        self.assertIn("tech-debt", findings)
        self.assertIn("state-surface", findings)
        self.assertTrue(any("17 unowned" in item for item in findings["tech-debt"]))
        self.assertTrue(any("adds 2 TODO" in item for item in findings["tech-debt"]))
        self.assertTrue(any("90% bytes" in item or "state-rotate" in item for item in findings["state-surface"]))

    def test_ratchets_and_hooks(self) -> None:
        log_text = """
  ·  join: 12 errors, at baseline
  ℹ  web/typecheck (pre-push) wired from ANOTHER repo: w0m-ext/.pre-commit-config.yaml
"""
        findings = push_report.parse_log_text(log_text)
        self.assertIn("ratchets", findings)
        self.assertIn("hooks", findings)
        self.assertTrue(any("join: 12 errors" in item for item in findings["ratchets"]))
        self.assertTrue(any("w0m-ext/.pre-commit-config.yaml" in item for item in findings["hooks"]))

    def test_format_report_banner(self) -> None:
        findings = {
            "astro-check": ["src/pages/jobs/[id].astro: unused 'res', 'error'"],
            "dependencies": ["@supabase/supabase-js: w0m-ext @ ^2.87.1 (23 minors behind)"],
        }
        report = push_report.format_report(findings)
        self.assertIn("PRE-PUSH FINAL REPORT", report)
        self.assertIn("[astro-check]", report)
        self.assertIn("[dependencies]", report)
        self.assertIn("2 Informative Finding(s)", report)


if __name__ == "__main__":
    unittest.main()
