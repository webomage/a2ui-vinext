#!/usr/bin/env python3
"""Unit tests and RED probes for T152 — OpenCode Config Generator, Parity Check & MLX Offload Guard."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ESTATE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ESTATE_ROOT / "scripts"))

import opencode_config as oc  # noqa: E402


class TestOpenCodeConfig(unittest.TestCase):
    def test_canonical_config_is_strict_json_and_healthy(self) -> None:
        ok, report = oc.check_health(ESTATE_ROOT)
        self.assertTrue(ok, f"Expected healthy OpenCode config, got errors: {report['errors']}")
        self.assertEqual(report["enumerated"]["runtimes"], "2/2 (claude, opencode)")
        self.assertEqual(report["enumerated"]["opencode_commands"], "11/11")

    def test_red_probe_trailing_comma_in_opencode_json_fails_closed(self) -> None:
        bad_json = '{\n  "instructions": [\n    "AGENTS.md",\n    "CLAUDE.md",\n  ]\n}\n'
        cfg, errors = oc.validate_opencode_config_text(bad_json, root=ESTATE_ROOT)
        self.assertIsNone(cfg)
        self.assertTrue(any("trailing comma" in e or "not valid strict JSON" in e for e in errors))

    def test_red_probe_localhost_in_mcp_or_wrong_graphify_cmd_fails_closed(self) -> None:
        cfg = oc.build_canonical_opencode_config()
        cfg["mcp"]["wom7md"]["url"] = "http://localhost:3001/mcp"
        cfg["mcp"]["graphify"]["command"] = ["graphify", "mcp", "serve"]
        _, errors = oc.validate_opencode_config_text(json.dumps(cfg), root=ESTATE_ROOT)
        self.assertTrue(any("localhost" in e for e in errors), f"Expected localhost error in {errors}")
        self.assertTrue(any("graphify-mcp" in e for e in errors), f"Expected graphify-mcp error in {errors}")

    def test_red_probe_mlx_tool_call_guard_fails_closed_on_tools_or_fabricated_tags(self) -> None:
        # Allowed text-only task with tools=None succeeds
        res = oc.validate_mlx_offload_request(task_type="summarize", tools=None)
        self.assertTrue(res["ok"])
        self.assertEqual(res["routed_model"], oc.SMALL_MLX_MODEL)

        # Passing non-empty tools raises ToolCallUnsupportedError (closes fail-open fabrication)
        with self.assertRaises(oc.ToolCallUnsupportedError):
            oc.validate_mlx_offload_request(
                task_type="summarize",
                tools=[{"type": "function", "function": {"name": "get_weather"}}],
            )

        # Synthetic <call:get_weather/> token in output raises ToolCallUnsupportedError
        with self.assertRaises(oc.ToolCallUnsupportedError):
            oc.validate_mlx_offload_request(
                task_type="summarize",
                tools=None,
                response_text="<call:get_weather/>The weather in Paris is 21C.",
            )

        # Agentic / non-text-only task type raises ToolCallUnsupportedError
        with self.assertRaises(oc.ToolCallUnsupportedError):
            oc.validate_mlx_offload_request(task_type="agentic-build", tools=None)

    def test_red_probe_agents_md_missing_non_negotiable_fails_parity(self) -> None:
        incomplete_md = "# Agent Rules\n- Never `--no-verify`.\n"
        errs = oc.validate_agents_md_parity(incomplete_md, "test-AGENTS.md")
        self.assertTrue(any("no_co_authored_by" in e for e in errs))
        self.assertTrue(any("skills_governance" in e for e in errs))

    def test_static_command_resolution_start_to_spec(self) -> None:
        trace = oc.drive_ticket_lifecycle_in_opencode("T152", stages=("start", "spec"), root=ESTATE_ROOT)
        self.assertTrue(trace["ok"])
        self.assertEqual(len(trace["stages"]), 2)
        self.assertEqual(trace["stages"][0]["stage"], "start")
        self.assertEqual(trace["stages"][0]["next_gate"], "spec")
        self.assertEqual(trace["stages"][1]["stage"], "spec")
        self.assertEqual(trace["stages"][1]["next_gate"], "build")

    def test_live_mcp_and_mlx_probe_surface(self) -> None:
        res = oc.probe_live_mcp_and_mlx(root=ESTATE_ROOT, sync_home=False)
        self.assertTrue(res["ok"])
        self.assertEqual(res["ac3_sdlc_gates"]["stages_verified"], "10/10")
        self.assertTrue(res["ac5_mlx_offload"]["tool_call_guard_closed"])
        self.assertIn("codegraph", res["ac7_mcp_probes"])
        self.assertIn("wom7md", res["ac7_mcp_probes"])
        self.assertTrue(res["ac7_mcp_probes"]["wom7md"]["ipv4_bound"])


if __name__ == "__main__":
    unittest.main()
