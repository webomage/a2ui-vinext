#!/usr/bin/env python3
"""Unit tests for T171 Sandbox Cohort Runner, Capability Red-Probe & Policy Binding."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from t171_sandbox_cohort_runner import (  # noqa: E402
    DENIED_SANDBOX_CREDENTIALS,
    build_sandbox_capability_env,
    build_sandbox_image_manifest,
    evaluate_stop_condition,
    prove_abort_clean_worktree,
    prove_capability_boundary_red_probe,
    verify_tools_policy_binding,
)


class TestT171SandboxCohortRunner(unittest.TestCase):
    def test_ac4_sandbox_capability_env_strips_all_denied_credentials(self) -> None:
        fake_env = {k: "secret-val" for k in DENIED_SANDBOX_CREDENTIALS}
        fake_env["PATH"] = "/usr/bin:/bin"
        cleaned = build_sandbox_capability_env(fake_env)
        for forbidden in DENIED_SANDBOX_CREDENTIALS:
            self.assertNotIn(forbidden, cleaned)
        self.assertEqual(cleaned["WOM_SANDBOX_CAPABILITY_MODE"], "restricted")
        self.assertEqual(cleaned["CLAUDECODE"], "1")

    def test_ac4_red_probe_fails_closed(self) -> None:
        res = prove_capability_boundary_red_probe()
        self.assertTrue(res["ok"])
        self.assertNotEqual(res["returncode"], 0)
        self.assertEqual(res["stripped_credentials_count"], len(DENIED_SANDBOX_CREDENTIALS))

    def test_ac4b_tools_policy_binding_detects_drift(self) -> None:
        manifest = build_sandbox_image_manifest()
        self.assertEqual(manifest["schema"], "w0m.sandbox.image-manifest.v1")
        self.assertIn("headroom", manifest["tools"])
        self.assertIn("serena", manifest["tools"])

        clean_check = verify_tools_policy_binding()
        self.assertTrue(clean_check["ok"])
        self.assertEqual(clean_check["drifts"], [])

        drifted_check = verify_tools_policy_binding(candidate_overrides={"headroom": "0.1.0"})
        self.assertFalse(drifted_check["ok"])
        self.assertTrue(any("headroom" in d for d in drifted_check["drifts"]))

    def test_ac3_stop_condition_halts_when_zero_tokens_removed(self) -> None:
        routed = [
            {
                "task_id": "n1-routed-1",
                "mode": "routed",
                "routed": True,
                "proxy_counter_delta": 1,
                "tokens": {"input": 20, "output": 24, "total": 44, "removed_by_proxy": 0},
                "wall_clock_ms": 4.0,
                "outcome": "completed",
            }
        ]
        direct = [
            {
                "task_id": "n1-direct-1",
                "mode": "direct",
                "routed": False,
                "proxy_counter_delta": 0,
                "tokens": {"input": 20, "output": 24, "total": 44, "removed_by_proxy": 0},
                "wall_clock_ms": 2.0,
                "outcome": "completed",
            }
        ]
        verdict = evaluate_stop_condition(routed, direct)
        self.assertTrue(verdict["routing_verified"])
        self.assertTrue(verdict["stop_condition_triggered"])
        self.assertFalse(verdict["scale_fleet_approved"])
        self.assertEqual(verdict["recommended_concurrency_ceiling"], 1)

    def test_ac7_abort_leaves_clean_git_worktree(self) -> None:
        res = prove_abort_clean_worktree()
        self.assertTrue(res["ok"])
        self.assertTrue(res["dirty_before_abort"])
        self.assertEqual(res["status_after_abort"], "")
        self.assertTrue(res["worktree_clean"])


if __name__ == "__main__":
    unittest.main()
