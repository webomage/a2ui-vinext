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
    def test_ac1_w0m_ext_seven_specs_migrated(self) -> None:
        ext_specs = ROOT / "w0m-ext" / "specs"
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
        self.assertTrue(expected.issubset(actual), f"Missing w0m-ext specs: {expected - actual}")
        self.assertTrue((ROOT / "w0m-ext" / "tests" / "extension_steps.ts").is_file())
        self.assertFalse((ROOT / "w0m-ext" / "extension" / "tests" / "e2e" / "features").exists())

    def test_ac2_w0m_mlx_three_specs_migrated_and_behave_removed(self) -> None:
        mlx_specs = ROOT / "w0m-mlx" / "w0m-mlx" / "specs"
        expected = {
            "003-mlx-rs-upgrade.spec",
            "004-logits-mismatch.spec",
            "multimodal_serving.spec",
        }
        actual = {p.name for p in mlx_specs.glob("*.spec")}
        self.assertTrue(expected.issubset(actual), f"Missing w0m-mlx specs: {expected - actual}")
        self.assertEqual(list(mlx_specs.glob("*.feature")), [])
        jf = (ROOT / "w0m-mlx" / "w0m-mlx" / "justfile").read_text(encoding="utf-8")
        self.assertNotIn("python -m behave", jf)
        self.assertNotIn("python3 -m behave", jf)
        self.assertIn("gauge run", jf)

    def test_ac3_cucumber_removed_and_stacks_policy_wired(self) -> None:
        pkg = json.loads((ROOT / "w0m-ext" / "extension" / "package.json").read_text(encoding="utf-8"))
        dev_deps = pkg.get("devDependencies", {})
        self.assertNotIn("@cucumber/cucumber", dev_deps)
        self.assertFalse((ROOT / "w0m-ext" / "extension" / "cucumber.cjs").exists())
        stacks = json.loads((ROOT / "project" / "policies" / "stacks-policy.json").read_text(encoding="utf-8"))
        ext_cmds = stacks["stacks"]["ext"]["commands"]
        self.assertEqual(ext_cmds.get("test"), "test")

    def test_ac5_and_ac6_w0m_spec_and_generic_sdlc_set(self) -> None:
        w0m_spec = (ROOT / "w0m-skills" / "skills" / "w0m" / "w0m-spec" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Gauge", w0m_spec)
        generic_doc = (ROOT / "w0m-skills" / "GENERIC-SDLC-SET.md").read_text(encoding="utf-8")
        self.assertIn("Gherkin (`*.feature`", generic_doc)
        self.assertIn("client/customer repos", generic_doc)

    def test_ac7_spec_systems_gate_blocks_new_gherkin(self) -> None:
        self.assertEqual(spec_systems_gate.gherkin_in_w0m(), [])
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp)
            (fake / "w0m-web" / "specs").mkdir(parents=True)
            (fake / "w0m-web" / "specs" / "ok.spec").write_text("# Spec\n## Scenario\n* Step\n", encoding="utf-8")
            (fake / "w0m-ext").mkdir(parents=True)
            stray = fake / "w0m-ext" / "regression.feature"
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
