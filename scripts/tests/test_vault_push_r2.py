#!/usr/bin/env python3
"""Unit tests for `scripts/vault_push_r2.py` (T580 AC2 & AC5)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import vault_push_r2 as vpr  # noqa: E402


class TestVaultPushR2(unittest.TestCase):
    def test_discovers_all_four_declared_engagement_vaults(self) -> None:
        vaults = vpr.discover_engagement_vaults()
        by_eg = {v["engagement_public_id"]: v for v in vaults}
        self.assertIn("eg-1945", by_eg)
        self.assertIn("eg-artemio-quiero-comer", by_eg)
        self.assertIn("eg-servicios777", by_eg)
        self.assertIn("eg-personaje0", by_eg)

        for eg_id, meta in by_eg.items():
            self.assertEqual(meta["r2_bucket"], "wom-engagement-vaults")
            self.assertEqual(meta["r2_prefix"], f"engagements/{eg_id}")
            files = vpr.collect_vault_files(meta)
            rel_paths = {rel for rel, _, _ in files}
            self.assertIn("index.md", rel_paths, f"{eg_id} missing index.md")
            self.assertIn("mocs/architecture.md", rel_paths, f"{eg_id} missing mocs/architecture.md")
            self.assertIn(".obsidian/app.json", rel_paths, f"{eg_id} missing .obsidian/app.json")

    def test_client_safe_filter_blocks_inbox_plugins_and_internal_urls(self) -> None:
        allowed = ["index.md", "mocs/", "notes/", "sources/", "claims/"]
        denied = ["inbox/", ".obsidian/", "internal/", ".w0m/", "openspec/"]

        self.assertTrue(
            vpr.is_client_safe_vault_file("index.md", b"# Safe Index", allowed, denied)
        )
        self.assertTrue(
            vpr.is_client_safe_vault_file(".obsidian/app.json", b"{}", allowed, denied)
        )
        self.assertFalse(
            vpr.is_client_safe_vault_file(
                ".obsidian/plugins/remotely-save/data.json", b"{}", allowed, denied
            )
        )
        self.assertFalse(
            vpr.is_client_safe_vault_file("inbox/raw-drop.md", b"# Drop", allowed, denied)
        )
        self.assertFalse(
            vpr.is_client_safe_vault_file(
                "notes/leak.md",
                b"Admin link: https://cp.w0m.xyz/admin/vaults",
                allowed,
                denied,
            )
        )


if __name__ == "__main__":
    unittest.main()
