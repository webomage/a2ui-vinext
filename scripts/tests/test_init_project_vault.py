#!/usr/bin/env python3
"""Tests for project vault initialization tooling (T371 AC2)."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

# Add project/scripts to path
import sys
HERE = Path(__file__).resolve().parent
SCRIPTS_DIR = HERE.parent
sys.path.insert(0, str(SCRIPTS_DIR))

import init_project_vault


class TestInitProjectVault(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp())
        self.clients_policy = self.tmp_dir / "clients-policy.json"
        policy_data = {
            "projects": [
                {
                    "id": "test-client",
                    "role": "client",
                    "root": "projects/test-client"
                },
                {
                    "id": "artemio",
                    "role": "client",
                    "root": "../../_self/delivery/artemioquierocomer.mx"
                }
            ]
        }
        self.clients_policy.write_text(json.dumps(policy_data, indent=2))

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_init_creates_karpathy_structure(self):
        target_root = self.tmp_dir / "projects" / "test-client" / "vault"
        res = init_project_vault.init_vault(
            project_id="test-client",
            policy_file=self.clients_policy,
            vault_dir=target_root
        )
        self.assertEqual(res, 0)
        self.assertTrue(target_root.is_dir())
        self.assertTrue((target_root / "index.md").is_file())
        self.assertTrue((target_root / "inbox").is_dir())
        self.assertTrue((target_root / "sources").is_dir())
        self.assertTrue((target_root / "claims").is_dir())
        self.assertTrue((target_root / "notes").is_dir())
        self.assertTrue((target_root / "mocs").is_dir())
        self.assertTrue((target_root / "assets").is_dir())
        self.assertTrue((target_root / ".obsidian").is_dir())
        self.assertTrue((target_root / ".obsidian" / "app.json").is_file())

        content = (target_root / "index.md").read_text()
        self.assertIn("project: test-client", content)
        self.assertIn("[[mocs/", content)

    def test_init_is_idempotent(self):
        target_root = self.tmp_dir / "projects" / "test-client" / "vault"
        init_project_vault.init_vault(
            project_id="test-client",
            policy_file=self.clients_policy,
            vault_dir=target_root
        )
        custom_note = target_root / "notes" / "custom.md"
        custom_note.write_text("# My Custom Note")

        # Run init second time
        res = init_project_vault.init_vault(
            project_id="test-client",
            policy_file=self.clients_policy,
            vault_dir=target_root
        )
        self.assertEqual(res, 0)
        self.assertEqual(custom_note.read_text(), "# My Custom Note")

    def test_init_rejects_unknown_project(self):
        target_root = self.tmp_dir / "projects" / "unknown-proj" / "vault"
        res = init_project_vault.init_vault(
            project_id="unknown-proj",
            policy_file=self.clients_policy,
            vault_dir=target_root
        )
        self.assertEqual(res, 1)
        self.assertFalse(target_root.exists())


if __name__ == "__main__":
    unittest.main()
