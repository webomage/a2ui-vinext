#!/usr/bin/env python3
"""T302 — Unit tests and red probes for `preflight.py` estate-vs-client boundary guard.

Verifies:
  - AC1 & AC4: Both `preflight.py` docstring and `AGENTS.md` document the standing rule that
    estate gates must never depend on client workspaces and that client checks belong in the
    client's own `-w0m` workspace under the same `just` recipe names.
  - AC2: `check_estate_preflight_client_boundary()` passes on live `FULL_CHILDREN` and fails
    closed when a row references `_proj/`, a `clients-policy.json` root (`_self/1945`,
    `_proj/bridgeroad`), or an absolute path under a client workspace.
  - AC3: Red probe injects a `vm-image` row reaching into `_proj/bridgeroad` into `FULL_CHILDREN`,
    observes `check_boundary()` / `check_estate_preflight_client_boundary()` fail closed, and
    restores `FULL_CHILDREN`.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import preflight  # noqa: E402


class TestPreflightClientBoundary(unittest.TestCase):
    def test_ac1_and_ac4_standing_rule_documented_in_preflight_and_agents_md(self) -> None:
        doc = preflight.__doc__ or ""
        self.assertIn("ESTATE vs CLIENT BOUNDARY RULE (T302", doc)
        self.assertIn("bridgeroad-w0m", doc)
        self.assertIn("relocation", doc)

        agents_md = (preflight.ESTATE / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("Estate gates never depend on client workspaces; client checks live in `<client>-w0m` (T302)", agents_md)
        self.assertIn("check_estate_preflight_client_boundary()", agents_md)

    def test_ac2_live_full_children_pass_client_boundary(self) -> None:
        violations = preflight.check_estate_preflight_client_boundary()
        self.assertEqual(violations, [])
        res = preflight.check_boundary()
        self.assertTrue(res["ok"])

    def test_ac2_and_ac3_red_probe_bridgeroad_row_blocks_then_recovers(self) -> None:
        saved = list(preflight.FULL_CHILDREN)
        try:
            preflight.FULL_CHILDREN.append(
                (
                    "vm-image",
                    ["python3", "../_proj/bridgeroad/scripts/vm_staleness.py"],
                    60,
                    "BridgeRoad VM image staleness",
                )
            )
            violations = preflight.check_estate_preflight_client_boundary()
            self.assertEqual(len(violations), 1)
            self.assertIn("vm-image", violations[0])
            self.assertIn("_proj/bridgeroad", violations[0])
            self.assertIn("<client>-w0m", violations[0])

            res = preflight.check_boundary()
            self.assertFalse(res["ok"])
            self.assertEqual(len(res["detail"]), 1)
        finally:
            preflight.FULL_CHILDREN[:] = saved

        self.assertEqual(preflight.check_estate_preflight_client_boundary(), [])

    def test_ac2_blocks_clients_policy_roots_and_absolute_client_paths(self) -> None:
        abs_bridgeroad = str((Path.home() / "Projects" / "_proj" / "bridgeroad" / "check.py").resolve())
        custom_rows = [
            ("ok-row", ["just", "toolset-status"], 300, "estate check"),
            ("client-rel", ["python3", "../../_self/1945/scripts/check.py"], 60, "1945 check"),
            ("client-abs", ["python3", abs_bridgeroad], 60, "BridgeRoad abs check"),
        ]
        violations = preflight.check_estate_preflight_client_boundary(rows=custom_rows)
        self.assertEqual(len(violations), 2)
        self.assertTrue(any("client-rel" in v and "1945" in v for v in violations))
        self.assertTrue(any("client-abs" in v and "bridgeroad" in v for v in violations))

    def test_ac2_empty_rows_refuses_vacuous_pass(self) -> None:
        with self.assertRaises(preflight.Finding):
            preflight.check_estate_preflight_client_boundary(rows=[])


if __name__ == "__main__":
    unittest.main()
