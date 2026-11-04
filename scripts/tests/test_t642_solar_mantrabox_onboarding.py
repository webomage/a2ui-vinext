#!/usr/bin/env python3
"""Offline regression suite for T642: Solar & MantraBox (@mob) Client & Engagement Onboarding."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "w0m-web" / "project" / "scripts"))
import engagements_hats_verify as ehv  # noqa: E402


class TestT642SolarMantraboxOnboarding(unittest.TestCase):
    def test_clients_policy_declares_solar_and_mantrabox_for_aleksei(self) -> None:
        policy_path = ROOT / "project" / "policies" / "clients-policy.json"
        data = json.loads(policy_path.read_text(encoding="utf-8"))
        projects = {p["id"]: p for p in data["projects"]}

        self.assertNotIn("mob", projects, "legacy umbrella 'mob' entry must be split into solar & mantrabox")
        self.assertIn("solar", projects)
        self.assertIn("mantrabox", projects)

        solar = projects["solar"]
        self.assertEqual(solar["org_slug"], "aleksei-tcelishchev")
        self.assertEqual(solar["project_slug"], "solar")
        self.assertEqual(solar["canonical_repo"], "solar")
        self.assertEqual(solar["knowledge_hub"]["engagement_public_id"], "eg-solar")
        self.assertEqual(solar["knowledge_hub"]["r2_prefix"], "engagements/eg-solar")
        self.assertEqual(
            set(solar["repos"].keys()),
            {"solar", "solar-apple", "solar-flutter", "solar-google"},
        )

        mantrabox = projects["mantrabox"]
        self.assertEqual(mantrabox["org_slug"], "aleksei-tcelishchev")
        self.assertEqual(mantrabox["project_slug"], "mantrabox")
        self.assertEqual(mantrabox["canonical_repo"], "mantrabox")
        self.assertEqual(mantrabox["knowledge_hub"]["engagement_public_id"], "eg-mantrabox")
        self.assertEqual(mantrabox["knowledge_hub"]["r2_prefix"], "engagements/eg-mantrabox")
        self.assertEqual(
            set(mantrabox["repos"].keys()),
            {"mantrabox", "mantrabox-flutter", "mantrabox-slint"},
        )

    def test_vault_corpora_and_audience_separation(self) -> None:
        for slug in ("solar", "mantrabox"):
            vault_dir = ROOT / "w0m-web" / "projects" / slug / "vault"
            self.assertTrue((vault_dir / "index.md").is_file(), f"missing {slug}/vault/index.md")
            self.assertTrue((vault_dir / "guides" / "user-guide.md").is_file())
            self.assertTrue((vault_dir / "guides" / "obsidian-sync-guide.md").is_file())
            self.assertTrue((vault_dir / "mocs" / "architecture.md").is_file())
            self.assertTrue((vault_dir / "tech" / "architecture-and-stack.md").is_file())

            idx_text = (vault_dir / "index.md").read_text(encoding="utf-8")
            tech_text = (vault_dir / "tech" / "architecture-and-stack.md").read_text(encoding="utf-8")
            self.assertIn("audience: client", idx_text)
            self.assertIn("audience: tech", tech_text)

    def test_migration_invariants_and_engagements_hats_judge(self) -> None:
        mig = (
            ROOT
            / "w0m-api"
            / "supabase"
            / "migrations"
            / "20261104170000_t642_aleksei_solar_mantrabox_engagements.sql"
        )
        self.assertTrue(mig.is_file())
        sql = mig.read_text(encoding="utf-8")

        for token in (
            "'aleksei-tcelishchev'",
            "'company'",
            "'eg-solar'",
            "'eg-mantrabox'",
            "9dd04d15-1160-4045-8c56-0dff51e077ba",
            '"project_type": "indie"',
            "'engagements/eg-solar'",
            "'engagements/eg-mantrabox'",
            "'pm'",
            "'tech-lead'",
            "'dev'",
        ):
            self.assertIn(token, sql)

        simulated = (
            ehv.GOOD
            + "PROJ|solar|c6420011-6420-4000-8000-000000000001|webomage|webomage\n"
            + "PROJ|mantrabox|c6420012-6420-4000-8000-000000000002|webomage|webomage\n"
            + "PHAT|c6420101-6420|solar|c6420011-6420-4000-8000-000000000001|c6420011-6420-4000-8000-000000000001|webomage|webomage\n"
            + "PHAT|c6420102-6420|mantrabox|c6420012-6420-4000-8000-000000000002|c6420012-6420-4000-8000-000000000002|webomage|webomage\n"
            + "CHAT|c6420201-6420|aleksei@webomage.com|c6420011-6420-4000-8000-000000000001|aleksei-tcelishchev\n"
            + "CHAT|c6420202-6420|aleksei@webomage.com|c6420012-6420-4000-8000-000000000002|aleksei-tcelishchev\n"
        )
        code, report = ehv.judge(simulated)
        self.assertEqual(code, 0, "\n".join(report))


if __name__ == "__main__":
    unittest.main()
