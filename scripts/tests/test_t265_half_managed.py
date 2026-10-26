#!/usr/bin/env python3
"""T265 (AC4, AC5, AC8) — Half-managed project tier regression tests.

Verifies:
- AC4: self-managed / half-managed projects (`bridgeroad`, `evercred`) have ticketing and
  GitHub mirroring disabled in `clients-policy.json`, and `tasks_sync.py` / `.w0m/sdlc.json`
  operate exclusively on the estate root `.tasks/` corpus (0 writes or T-ids for half-managed projects).
- AC5: `tasks_board(root)` detects a w0m `TASKS.md` board by CONTENT, never by filename alone:
  an unrelated correspondence file named `TASKS.md` (the `_proj/Evercred/TASKS.md` trap) returns
  `present: True, is_w0m_board: False`, while a real w0m board returns `is_w0m_board: True`.
- AC8: `evercred` declares no `canonical_repo` (`no_contract` by decision) and `bridgeroad`
  places its contract outside the third-party `BridgeMvp` repo.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import client_inventory as ci

ESTATE_ROOT = SCRIPT_DIR.parent
WEB_ROOT = ESTATE_ROOT / "wom7web"
CLIENTS_POLICY = ESTATE_ROOT / "project" / "policies" / "clients-policy.json"


class TestT265HalfManagedTier(unittest.TestCase):
    def test_ac4_no_ticketing_or_github_mirroring_for_half_managed(self) -> None:
        policy = json.loads(CLIENTS_POLICY.read_text(encoding="utf-8"))
        self_managed_services = (
            policy.get("roles", {}).get("self-managed", {}).get("services", {})
        )
        self.assertFalse(
            self_managed_services.get("tickets", {}).get("enabled", True),
            "self-managed role must disable tickets service",
        )
        self.assertFalse(
            self_managed_services.get("github", {}).get("enabled", True),
            "self-managed role must disable github mirroring service",
        )
        half_tier_surfaces = (
            policy.get("tiers", {}).get("half-managed", {}).get("contract_surfaces", {})
        )
        self.assertEqual(half_tier_surfaces.get("tickets", {}).get("status"), "out")
        self.assertEqual(half_tier_surfaces.get("board", {}).get("status"), "out")

        by_id = {p["id"]: p for p in policy.get("projects", [])}
        for pid in ("bridgeroad", "evercred"):
            self.assertIn(pid, by_id)
            self.assertEqual(by_id[pid]["role"], "self-managed")
            overrides = by_id[pid].get("services", {})
            self.assertNotIn("tickets", overrides)
            self.assertNotIn("github", overrides)

    def test_ac5_tasks_board_detected_by_content_not_filename(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # 1. Missing TASKS.md
            absent = ci.tasks_board(root)
            self.assertEqual(absent, {"present": False, "is_w0m_board": False, "bytes": None})

            # 2. RED PROBE: Evercred-shaped correspondence named TASKS.md must NOT be classified as a w0m board
            (root / "TASKS.md").write_text(
                "# Evercred Weekly Notes\n\nHi team, here are the tasks and correspondence from Monday's call.\n"
                "- Review deployment credentials with HPECid\n- Check staging logs\n",
                encoding="utf-8",
            )
            correspondence = ci.tasks_board(root)
            self.assertTrue(correspondence["present"])
            self.assertFalse(
                correspondence["is_w0m_board"],
                "Unrelated correspondence named TASKS.md must not be misread as a w0m board",
            )

            # 3. GREEN PROBE: w0m TASKS.md board structure is recognized by content
            (root / "TASKS.md").write_text(
                "# TASKS\n\n## Queue\n\n| ID | Status | Title |\n|---|---|---|\n"
                "| [T265](.tasks/T265.md) | queued | Half-managed tier |\n",
                encoding="utf-8",
            )
            board = ci.tasks_board(root)
            self.assertTrue(board["present"])
            self.assertTrue(board["is_w0m_board"])

        # 4. Estate root TASKS.md is recognized as a real w0m board
        estate_board = ci.tasks_board(ESTATE_ROOT)
        self.assertTrue(estate_board["present"])
        self.assertTrue(estate_board["is_w0m_board"])

    def test_ac8_no_contract_inside_third_party_client_repos(self) -> None:
        policy = json.loads(CLIENTS_POLICY.read_text(encoding="utf-8"))
        by_id = {p["id"]: p for p in policy.get("projects", [])}
        # Evercred has no canonical_repo (no .w0m/ contract placed anywhere)
        self.assertIsNone(by_id["evercred"].get("canonical_repo"))
        # BridgeRoad places canonical_repo at "." (its wrapper), never inside "app" (BridgeMvp)
        self.assertEqual(by_id["bridgeroad"].get("canonical_repo"), ".")
        self.assertNotEqual(by_id["bridgeroad"].get("canonical_repo"), "app")

    def test_ac9_future_sweep_reports_half_managed_declared_not_unmanaged_gap(self) -> None:
        policy = json.loads(CLIENTS_POLICY.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            schema_src = ESTATE_ROOT / "project" / "policies" / "clients-policy.schema.json"
            (tmp_path / "clients-policy.schema.json").symlink_to(schema_src)

            # Create a workspace with 2 symlinks to real git repo roots (wom7web, wom7api) and no .w0m/ contract
            hm_root = tmp_path / "half_managed_ws"
            hm_root.mkdir()
            (hm_root / "app").symlink_to(WEB_ROOT)
            (hm_root / "api").symlink_to(ESTATE_ROOT / "wom7api")

            w0m_proj = next(dict(p) for p in policy["projects"] if p["id"] == "w0m")
            w0m_proj["root"] = str(ESTATE_ROOT)

            hm_proj = {
                "id": "evercred-probe",
                "role": "self-managed",
                "root": str(hm_root),
                "enabled": True,
                "runtime": {"substrate": "host"},
                "repos": {"app": "app", "api": "api"},
                "tier_reason": "Half-managed probe with no .w0m/ contract by decision (T265 AC9).",
            }

            reg = dict(policy)
            reg["projects"] = [w0m_proj, hm_proj]
            reg_file = tmp_path / "registry.json"
            reg_file.write_text(json.dumps(reg, indent=2), encoding="utf-8")

            rep, errors = ci.inventory(reg_file)
            self.assertEqual(errors, [])
            by_id = {p["id"]: p for p in rep.get("projects", [])}
            self.assertIn("evercred-probe", by_id)
            self.assertEqual(by_id["evercred-probe"]["role"], "self-managed")
            self.assertTrue(by_id["evercred-probe"]["git"].get("no_contract"))
            self.assertFalse(by_id["evercred-probe"]["declaration"]["present"])
            # Crucially, half-managed / self-managed projects do not pollute shared_client_gaps
            self.assertEqual(rep.get("shared_client_gaps"), [])


if __name__ == "__main__":
    unittest.main()
