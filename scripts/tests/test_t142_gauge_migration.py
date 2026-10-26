#!/usr/bin/env python3
"""T142 verification suite — Gherkin -> Gauge migration across w0m repos."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import spec_systems_gate  # noqa: E402


class TestT142GaugeMigration(unittest.TestCase):
    def test_ac1_wom7ext_seven_specs_migrated(self) -> None:
        ext_specs = ROOT / "wom7ext" / "specs"
        expected = {
            "smoke.spec",
            "linkedin_cv.spec",
            "upwork_agency.spec",
            "upwork_agency_portfolio.spec",
            "upwork_job.spec",
            "upwork_portfolio.spec",
            "upwork_profile_cv.spec",
            "upwork_proposals.spec",
        }
        actual = {p.name for p in ext_specs.glob("*.spec")}
        self.assertTrue(expected.issubset(actual), f"Missing wom7ext specs: {expected - actual}")
        self.assertTrue((ROOT / "wom7ext" / "tests" / "extension_steps.ts").is_file())
        self.assertFalse((ROOT / "wom7ext" / "extension" / "tests" / "e2e" / "features").exists())

    def test_ac2_wom7mlx_three_specs_migrated_and_behave_removed(self) -> None:
        mlx_specs = ROOT / "wom7mlx" / "wom7mlx" / "specs"
        expected = {
            "003-mlx-rs-upgrade.spec",
            "004-logits-mismatch.spec",
            "multimodal_serving.spec",
        }
        actual = {p.name for p in mlx_specs.glob("*.spec")}
        self.assertTrue(expected.issubset(actual), f"Missing wom7mlx specs: {expected - actual}")
        self.assertEqual(list(mlx_specs.glob("*.feature")), [])
        jf = (ROOT / "wom7mlx" / "wom7mlx" / "justfile").read_text(encoding="utf-8")
        self.assertNotIn("python -m behave", jf)
        self.assertNotIn("python3 -m behave", jf)
        self.assertIn("gauge run", jf)

    def test_ac3_cucumber_removed_and_stacks_policy_wired(self) -> None:
        pkg = json.loads((ROOT / "wom7ext" / "extension" / "package.json").read_text(encoding="utf-8"))
        dev_deps = pkg.get("devDependencies", {})
        self.assertNotIn("@cucumber/cucumber", dev_deps)
        self.assertFalse((ROOT / "wom7ext" / "extension" / "cucumber.cjs").exists())
        stacks = json.loads((ROOT / "project" / "policies" / "stacks-policy.json").read_text(encoding="utf-8"))
        ext_cmds = stacks["stacks"]["ext"]["commands"]
        self.assertEqual(ext_cmds.get("test"), "test")

    def test_ac5_and_ac6_w0m_spec_and_generic_sdlc_set(self) -> None:
        w0m_spec = (ROOT / "wom7skills" / "skills" / "w0m" / "w0m-spec" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Gauge", w0m_spec)
        generic_doc = (ROOT / "wom7skills" / "GENERIC-SDLC-SET.md").read_text(encoding="utf-8")
        self.assertIn("Gherkin (`*.feature`", generic_doc)
        self.assertIn("client/customer repos", generic_doc)

    def test_ac7_spec_systems_gate_blocks_new_gherkin(self) -> None:
        self.assertEqual(spec_systems_gate.gherkin_in_w0m(), [])
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp)
            (fake / "wom7web" / "specs").mkdir(parents=True)
            (fake / "wom7web" / "specs" / "ok.spec").write_text("# Spec\n## Scenario\n* Step\n", encoding="utf-8")
            (fake / "wom7ext").mkdir(parents=True)
            stray = fake / "wom7ext" / "regression.feature"
            stray.write_text("Feature: stray\n", encoding="utf-8")
            orig = spec_systems_gate.ESTATE
            try:
                spec_systems_gate.ESTATE = fake
                found = spec_systems_gate.gherkin_in_w0m()
                self.assertEqual(len(found), 1)
                self.assertEqual(found[0].name, "regression.feature")
            finally:
                spec_systems_gate.ESTATE = orig


if __name__ == "__main__":
    unittest.main()
