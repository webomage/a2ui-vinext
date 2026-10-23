#!/usr/bin/env python3
"""Unit tests for scripts/gh_identity_select.py (T306)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import gh_identity_select as gis  # noqa: E402


class TestGhIdentitySelect(unittest.TestCase):
    def setUp(self) -> None:
        gis.provision_work_dirs()

    def test_verify_all_four_identities_and_offices_and_bridgeroad(self) -> None:
        report = gis.verify_identities()
        self.assertTrue(
            report.ok, f"Expected verify_identities to pass, got: {report.errors}"
        )
        self.assertEqual(
            set(report.identities.keys()),
            {"aleksei-personal", "elena-personal", "aleksei-work", "elena-work"},
        )
        self.assertTrue(report.offices_verified)
        self.assertTrue(report.bridgeroad_roles_verified)
        self.assertTrue(report.no_private_keys_verified)
        ssh_keys = {info["ssh_key"] for info in report.identities.values()}
        gh_dirs = {info["gh_config_dir"] for info in report.identities.values()}
        self.assertEqual(len(ssh_keys), 4, "All 4 identities must have distinct SSH keys")
        self.assertEqual(len(gh_dirs), 4, "All 4 identities must have distinct GH_CONFIG_DIRs")
        self.assertTrue(report.identities["aleksei-personal"]["gh_hosts_authenticated"])
        self.assertTrue(report.identities["aleksei-work"]["gh_hosts_authenticated"])

    def test_select_each_of_four_identities(self) -> None:
        expected = {
            "aleksei-personal": ("casualuser@gmail.com", "gh-w0m"),
            "elena-personal": ("elenashatalova.it@gmail.com", "gh-elena"),
            "aleksei-work": ("aleksei@webomage.com", "gh-aleksei-work"),
            "elena-work": ("elena@webomage.com", "gh-elena-work"),
        }
        for key, (email, gh_dir_suffix) in expected.items():
            sel = gis.select_identity(identity_key=key)
            env = sel.to_env_exports()
            self.assertEqual(env["W0M_IDENTITY_KEY"], key)
            self.assertEqual(env["GIT_AUTHOR_EMAIL"], email)
            self.assertTrue(env["GH_CONFIG_DIR"].endswith(gh_dir_suffix))
            self.assertIn("IdentitiesOnly=yes", env["GIT_SSH_COMMAND"])

    def test_select_by_project_and_operator_for_bridgeroad(self) -> None:
        aleksei_sel = gis.select_identity(project_id="bridgeroad", operator="aleksei")
        self.assertEqual(aleksei_sel.identity_key, "aleksei-personal")

        elena_sel = gis.select_identity(project_id="bridgeroad", operator="elena")
        self.assertEqual(elena_sel.identity_key, "elena-personal")


if __name__ == "__main__":
    unittest.main()
