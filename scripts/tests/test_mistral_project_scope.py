#!/usr/bin/env python3
"""Unit tests for `scripts/mistral_project_scope.py` (`T677`)."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mistral_project_scope import (
    build_obsidian_acp_profile,
    email_for_project,
    get_project_scope,
    inspect_infisical_status,
    load_project_scopes,
    resolve_project_mistral_key_from_env,
    secret_key_for_project,
    validate_project_data_access,
)


class MistralProjectScopeTests(unittest.TestCase):
    def test_loads_all_enabled_projects_with_unique_emails_and_secret_keys(self) -> None:
        scopes = load_project_scopes()
        ids = {s.project_id for s in scopes}
        self.assertIn("w0m", ids)
        self.assertIn("artemio", ids)
        self.assertIn("servicios777", ids)
        self.assertIn("solar", ids)
        self.assertIn("k7", ids)

        emails = [s.account_email for s in scopes]
        keys = [s.infisical_secret_key for s in scopes]
        self.assertEqual(len(emails), len(set(emails)))
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(email_for_project("artemio"), "artemio@webomage.com")
        self.assertEqual(secret_key_for_project("artemio"), "MISTRAL_API_KEY_ARTEMIO")

    def test_enforces_strict_private_project_data_scope_and_blocks_cross_tenant_paths(self) -> None:
        artemio = get_project_scope("artemio")
        solar = get_project_scope("solar")

        # Valid note inside artemio's own vault
        ok_note, reason_note = validate_project_data_access(
            artemio, "w0m-web/projects/artemio/vault/notes/menu-pricing.md"
        )
        self.assertTrue(ok_note, reason_note)

        # Denied prefix (.obsidian / internal / inbox) inside artemio's vault -> blocked
        ok_obs, _ = validate_project_data_access(
            artemio, "w0m-web/projects/artemio/vault/.obsidian/plugins/data.json"
        )
        self.assertFalse(ok_obs)

        ok_inbox, _ = validate_project_data_access(
            artemio, "w0m-web/projects/artemio/vault/inbox/raw-drop.md"
        )
        self.assertFalse(ok_inbox)

        # Cross-project read (artemio trying to read solar or w0m vault) -> hard blocked
        ok_cross, reason_cross = validate_project_data_access(
            artemio, "w0m-web/projects/solar/vault/notes/architecture.md"
        )
        self.assertFalse(ok_cross)
        self.assertIn("cross-project data access denied", reason_cross)

        # Path traversal attempt -> hard blocked
        ok_trav, _ = validate_project_data_access(
            solar, "w0m-web/projects/solar/vault/../artemio/vault/index.md"
        )
        self.assertFalse(ok_trav)

    def test_isolates_tenant_mistral_keys_without_leaking_global_key_to_client_projects(self) -> None:
        w0m_scope = get_project_scope("w0m")
        artemio_scope = get_project_scope("artemio")

        global_key_name = "_".join(("MISTRAL", "API", "KEY"))
        artemio_key_name = secret_key_for_project("artemio")
        env_only_global = {global_key_name: "stub"}
        # w0m can use global MISTRAL_API_KEY if MISTRAL_API_KEY_W0M is not yet set
        w0m_val, w0m_src = resolve_project_mistral_key_from_env(w0m_scope, env_only_global)
        self.assertEqual(w0m_val, "stub")
        self.assertEqual(w0m_src, global_key_name)

        # Client project (`artemio`) MUST NOT fall back to global `MISTRAL_API_KEY`
        art_val, art_src = resolve_project_mistral_key_from_env(artemio_scope, env_only_global)
        self.assertIsNone(art_val)
        self.assertIn(f"missing {artemio_key_name}", art_src)

        # Once `MISTRAL_API_KEY_ARTEMIO` is provisioned, it resolves cleanly with redacted fingerprint
        env_with_artemio = {
            global_key_name: "stub",
            artemio_key_name: "stub2",
        }
        art_val2, art_src2 = resolve_project_mistral_key_from_env(artemio_scope, env_with_artemio)
        self.assertEqual(art_val2, "stub2")
        self.assertEqual(art_src2, artemio_key_name)

        rows = inspect_infisical_status([w0m_scope, artemio_scope], env_map_override=env_with_artemio)
        by_id = {r["project_id"]: r for r in rows}
        self.assertEqual(by_id["artemio"]["status"], "ACTIVE_DEDICATED")
        self.assertTrue(by_id["artemio"]["fingerprint"].startswith("sha256:"))
        self.assertNotIn("stub2", str(rows))

    def test_builds_obsidian_acp_profile_locked_to_project_vault_and_key(self) -> None:
        solar = get_project_scope("solar")
        prof = build_obsidian_acp_profile(solar, infisical_env="beta")
        self.assertEqual(prof["account_email"], "solar@webomage.com")
        self.assertEqual(prof["infisical_secret_key"], "MISTRAL_API_KEY_SOLAR")
        self.assertFalse(prof["private_data_scope"]["cross_project_access"])
        self.assertFalse(prof["private_data_scope"]["allow_global_key_fallback"])
        acp_cfg = prof["obsidian_acp_client"]
        self.assertTrue(acp_cfg["cwd"].endswith("w0m-web/projects/solar/vault"))
        self.assertIn("MISTRAL_API_KEY_SOLAR", " ".join(acp_cfg["args"]))


if __name__ == "__main__":
    unittest.main()
