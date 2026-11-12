#!/usr/bin/env python3
"""Unit and red-probe tests for `scripts/skill_spector_check.py` (T726 AC1)."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
from typing import Any
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import skill_spector_check as ssc  # noqa: E402


class TestSkillSpectorCheck(unittest.TestCase):
    def test_stage_clean_skill_tree_strips_node_modules_and_git(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tp = Path(tmp)
            src = tp / "mmd-validate"
            (src / "node_modules" / "pkg").mkdir(parents=True)
            (src / ".git").mkdir(parents=True)
            (src / "SKILL.md").write_text("---\nname: mmd-validate\ndescription: test\n---\n# Test\n", encoding="utf-8")
            (src / "validate.mjs").write_text("console.log('ok');\n", encoding="utf-8")
            (src / "node_modules" / "pkg" / "index.js").write_text("throw new Error('bloat');\n", encoding="utf-8")
            (src / ".git" / "HEAD").write_text("ref: refs/heads/beta\n", encoding="utf-8")

            digest, fcount = ssc.compute_skill_tree_sha256(src)
            self.assertEqual(fcount, 2)
            self.assertEqual(len(digest), 64)

            dst = tp / "staged"
            copied = ssc.stage_clean_skill_tree(src, dst)
            self.assertEqual(copied, 2)
            self.assertTrue((dst / "SKILL.md").is_file())
            self.assertTrue((dst / "validate.mjs").is_file())
            self.assertFalse((dst / "node_modules").exists())
            self.assertFalse((dst / ".git").exists())

    def test_summarize_payload_fails_closed_on_sc9_exclusion_even_if_low_severity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tp = Path(tmp)
            payload: dict[str, Any] = {
                "execution_successful": True,
                "risk_assessment": {"score": 5, "severity": "LOW", "recommendation": "APPROVE"},
                "issues": [
                    {
                        "id": "SC9",
                        "severity": "MEDIUM",
                        "category": "Supply Chain",
                        "location": {"file": "w0m-prs/SKILL.md", "start_line": 1},
                        "finding": "excluded_from_analysis",
                    }
                ],
                "suppressed_count": 0,
            }
            summary = ssc.summarize_skillspector_payload(payload, target=tp, scanner_binary="skillspector")
            self.assertFalse(summary["passed"])
            self.assertEqual(summary["verdict"], "REJECT")
            self.assertEqual(summary["sc9_excluded_count"], 1)

    def test_deep_scan_deduplicates_trees_caches_clean_skills_and_rejects_offenders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tp = Path(tmp)
            estate = tp / "w0m"
            s1 = estate / "w0m-skills" / "skills" / "alpha"
            s1_dup = estate / ".agents" / "skills" / "alpha"
            s2 = estate / "w0m-skills" / "skills" / "bravo"
            for d in (s1, s1_dup, s2):
                d.mkdir(parents=True)
            (s1 / "SKILL.md").write_text("---\nname: alpha\n---\nClean\n", encoding="utf-8")
            (s1_dup / "SKILL.md").write_text("---\nname: alpha\n---\nClean\n", encoding="utf-8")
            (s2 / "SKILL.md").write_text("---\nname: bravo\n---\nClean\n", encoding="utf-8")

            calls: list[Path] = []

            def fake_scanner(stage_root: Path, *, baseline: Path | None = None, recursive: bool = False) -> dict[str, Any]:
                calls.append(stage_root)
                return {
                    "passed": True,
                    "execution_successful": True,
                    "suppressed_count": 1,
                    "active_issues_count": 0,
                    "sc9_excluded_count": 0,
                    "critical_or_high_count": 0,
                    "unsuppressed_high_or_critical": [],
                }

            cache_file = tp / "cache.json"
            r1 = ssc.run_estate_deep_scan(estate_root=estate, cache_file=cache_file, scanner_fn=fake_scanner)
            self.assertTrue(r1["passed"])
            self.assertEqual(r1["total_unique_skills"], 2)  # alpha deduplicated!
            self.assertEqual(r1["cached_skills"], 0)
            self.assertEqual(r1["scanned_skills"], 2)
            self.assertEqual(len(calls), 1)

            # Warm second run hits cache in 0 scanner calls
            r2 = ssc.run_estate_deep_scan(estate_root=estate, cache_file=cache_file, scanner_fn=fake_scanner)
            self.assertTrue(r2["passed"])
            self.assertEqual(r2["cached_skills"], 2)
            self.assertEqual(r2["scanned_skills"], 0)
            self.assertEqual(len(calls), 1)

            # Mutate bravo -> only bravo rescans, and if scanner flags HIGH, bravo is NOT cached and run fails
            (s2 / "SKILL.md").write_text("---\nname: bravo\n---\nTampered\n", encoding="utf-8")

            def failing_scanner(stage_root: Path, *, baseline: Path | None = None, recursive: bool = False) -> dict[str, Any]:
                calls.append(stage_root)
                return {
                    "passed": False,
                    "execution_successful": True,
                    "suppressed_count": 0,
                    "active_issues_count": 1,
                    "sc9_excluded_count": 0,
                    "critical_or_high_count": 1,
                    "unsuppressed_high_or_critical": [
                        {
                            "id": "EA1",
                            "severity": "CRITICAL",
                            "category": "Execution",
                            "file": "bravo/SKILL.md",
                            "line": 3,
                            "finding": "malicious exec",
                        }
                    ],
                }

            r3 = ssc.run_estate_deep_scan(estate_root=estate, cache_file=cache_file, scanner_fn=failing_scanner)
            self.assertFalse(r3["passed"])
            self.assertEqual(r3["cached_skills"], 1)
            self.assertEqual(r3["scanned_skills"], 1)
            self.assertEqual(r3["critical_or_high_count"], 1)


if __name__ == "__main__":
    unittest.main()
