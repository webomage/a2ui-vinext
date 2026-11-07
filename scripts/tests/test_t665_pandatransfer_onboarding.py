#!/usr/bin/env python3
"""Offline regression suite for T665: PandaTransfer Client, Pre-Magic-Link Lead & Engagement Onboarding."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "w0m-web" / "project" / "scripts"))
import engagements_hats_verify as ehv  # noqa: E402


class TestT665PandaTransferOnboarding(unittest.TestCase):
    def test_clients_policy_declares_pandatransfer_and_automation_health_tiers(self) -> None:
        policy_path = ROOT / "project" / "policies" / "clients-policy.json"
        data = json.loads(policy_path.read_text(encoding="utf-8"))
        projects = {p["id"]: p for p in data["projects"]}

        self.assertIn("pandatransfer", projects)
        pt = projects["pandatransfer"]
        self.assertEqual(pt["role"], "managed")
        self.assertEqual(pt["root"], "../../!proj/pandatransfer")
        self.assertEqual(pt["org_slug"], "pandatransfer")
        self.assertEqual(pt["project_slug"], "pandatransfer")
        self.assertEqual(pt["vcs"]["repo"], "webomage/pandatransfer")
        self.assertEqual(pt["vcs"]["default_branch"], "main")
        self.assertEqual(pt["knowledge_hub"]["engagement_public_id"], "eg-pandatransfer")
        self.assertEqual(pt["knowledge_hub"]["r2_prefix"], "engagements/eg-pandatransfer")

        for tier_name in ("half-managed", "self-managed"):
            surfaces = data["tiers"][tier_name]["contract_surfaces"]
            self.assertIn("automation_health", surfaces)
            self.assertEqual(surfaces["automation_health"]["status"], "out")

    def test_vault_corpus_audience_separation_and_admin_registry(self) -> None:
        vault_dir = ROOT / "w0m-web" / "projects" / "pandatransfer" / "vault"
        for rel in (
            "index.md",
            "guides/user-guide.md",
            "guides/obsidian-sync-guide.md",
            "mocs/architecture.md",
            "mocs/requirements.md",
            "mocs/deliverables.md",
            "tech/architecture-and-stack.md",
        ):
            self.assertTrue((vault_dir / rel).is_file(), f"missing pandatransfer/vault/{rel}")

        idx_text = (vault_dir / "index.md").read_text(encoding="utf-8")
        tech_text = (vault_dir / "tech" / "architecture-and-stack.md").read_text(encoding="utf-8")
        self.assertIn("audience: client", idx_text)
        self.assertIn("audience: tech", tech_text)

        vaults_astro = (
            ROOT / "w0m-web" / "apps" / "cp" / "src" / "pages" / "admin" / "vaults.astro"
        ).read_text(encoding="utf-8")
        self.assertIn('id: "pandatransfer"', vaults_astro)

    def test_pre_magic_link_migration_invariants_and_engagements_hats_judge(self) -> None:
        mig = (
            ROOT
            / "w0m-api"
            / "supabase"
            / "migrations"
            / "20261106200000_t665_pandatransfer_client_onboarding.sql"
        )
        self.assertTrue(mig.is_file())
        sql = mig.read_text(encoding="utf-8")

        self.assertNotIn("insert into auth.users", sql.lower())
        for token in (
            "'pandatransfer'",
            "'pandatransferusa@gmail.com'",
            "'https://pandatransfer.io'",
            "'eg-pandatransfer'",
            "'t665:pandatransfer'",
            "converted_user_id",
            "9dd04d15-1160-4045-8c56-0dff51e077ba",
            '"project_type": "infra_maintenance"',
            "'webomage'",
            "'https://github.com/webomage/pandatransfer'",
            "'engagements/eg-pandatransfer'",
            "'pm'",
            "'tech-lead'",
            "'dev'",
        ):
            self.assertIn(token, sql)

        # Pre-magic-link state (0 active client hats on pandatransfer yet) passes judge cleanly
        simulated_pre_invite = (
            ehv.GOOD
            + "PROJ|pandatransfer|c6650011-6650-4000-8000-000000000001|webomage|webomage\n"
            + "PHAT|c6650101-6650|pandatransfer|c6650011-6650-4000-8000-000000000001|c6650011-6650-4000-8000-000000000001|webomage|webomage\n"
        )
        code_pre, report_pre = ehv.judge(simulated_pre_invite)
        self.assertEqual(code_pre, 0, "\n".join(report_pre))

        # Post-magic-link state (after ClientManager `grant access` creates client hat on eg-pandatransfer)
        simulated_post_invite = (
            simulated_pre_invite
            + "CHAT|c6650201-6650|pandatransferusa@gmail.com|c6650011-6650-4000-8000-000000000001|pandatransfer\n"
        )
        code_post, report_post = ehv.judge(simulated_post_invite)
        self.assertEqual(code_post, 0, "\n".join(report_post))


if __name__ == "__main__":
    unittest.main()
