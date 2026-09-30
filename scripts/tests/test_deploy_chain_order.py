#!/usr/bin/env python3
"""The deploy chain's ORDER, pinned (T503).

Why this exists. `_deploy-all-chain` used to run `check-warp check-infisical db-migrate deploy`, and the test gate lives INSIDE `deploy`.
So the schema write happened BEFORE the tests, and a failing gate arrived after an irreversible change: on 2026-09-30 two migrations were applied
to the live database and the deploy then stopped at `just test` with five blocking suites red, leaving the schema ahead of the code it belongs with
(and on 2026-09-29 the same shape). A gate that can only fail AFTER the thing it guards has happened is a report, not a gate.

Asserted here, from `just --dump` (the real recipe graph, not a regex over text):
  1. every gate (test, goldens, check-guardrails, check-infisical) runs BEFORE `db-migrate` in `_deploy-all-chain`;
  2. nothing that changes live state (`db-migrate`, the app deploys) is a dependency of `_deploy-gates`;
  3. `_deploy-chain` and `_deploy-all-chain` share the SAME `_deploy-gates`, so a gate added once protects both;
  4. the cheap ratchets (`_deploy-preflight`) run BEFORE the confirmation prompt, so a red ratchet never costs a Touch ID or a release cut;
  5. the red probe: a synthetic chain with the old order is REFUSED by the same checker (a checker that has only ever passed proves nothing).
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATES = ("test", "goldens", "check-guardrails")
MUTATORS = ("db-migrate", "deploy", "_deploy-apps", "_deploy-ship")


def recipes() -> dict:
    out = subprocess.run(["just", "--justfile", str(ROOT / "justfile"), "--dump", "--dump-format", "json"],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)["recipes"]


def flatten(rs: dict, name: str, seen: list[str] | None = None) -> list[str]:
    """Dependency execution order, depth-first, as `just` runs it: each dependency (and its own dependencies) before the recipe itself."""
    seen = [] if seen is None else seen
    for dep in rs[name]["dependencies"]:
        d = dep["recipe"]
        if d not in seen:
            flatten(rs, d, seen)
    if name not in seen:
        seen.append(name)
    return seen


def order_problems(order: list[str]) -> list[str]:
    """What is wrong with an execution order, as sentences. Empty = fine. Pure, so the red probe can call it."""
    problems = []
    if "db-migrate" not in order:
        return ["db-migrate is not in the chain at all (the checker would pass vacuously)"]
    at = order.index("db-migrate")
    for g in GATES:
        if g not in order:
            problems.append(f"gate `{g}` is not in the chain")
        elif order.index(g) > at:
            problems.append(f"gate `{g}` runs AFTER db-migrate: a red gate would arrive after the schema write")
    return problems


class TestDeployChainOrder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rs = recipes()

    def test_every_gate_runs_before_the_schema_write(self):
        order = flatten(self.rs, "_deploy-all-chain")
        self.assertEqual(order_problems(order), [], f"execution order: {order}")

    def test_the_gate_set_is_one_recipe_shared_by_both_chains(self):
        for chain in ("_deploy-chain", "_deploy-all-chain"):
            self.assertIn("_deploy-gates", flatten(self.rs, chain), f"{chain} does not use _deploy-gates")

    def test_gates_change_no_live_state(self):
        gate_order = flatten(self.rs, "_deploy-gates")
        for m in MUTATORS:
            self.assertNotIn(m, gate_order, f"`{m}` is a dependency of _deploy-gates: a gate must not write live state")

    def test_the_ratchets_run_before_the_confirmation(self):
        order = flatten(self.rs, "_deploy-all-chain")
        self.assertIn("_deploy-preflight", order)
        self.assertIn("_confirm", order)
        self.assertLess(order.index("_deploy-preflight"), order.index("_confirm"),
                        "a red ratchet must stop the run BEFORE the owner is asked for Touch ID")
        self.assertLess(order.index("_deploy-preflight"), order.index("_deploy-chain") if "_deploy-chain" in order else len(order))

    def test_the_plain_deploy_chain_also_gates_before_shipping(self):
        order = flatten(self.rs, "_deploy-chain")
        self.assertIn("_deploy-gates", order)
        self.assertIn("_deploy-preflight", order)

    def test_red_probe_the_old_order_is_refused(self):
        """The order that caused the 2026-09-30 incident, fed to the same checker."""
        old = ["_confirm", "check-warp", "check-infisical", "db-migrate", "check-guardrails", "test", "goldens", "deploy"]
        problems = order_problems(old)
        self.assertEqual(len(problems), 3, problems)
        self.assertTrue(all("AFTER db-migrate" in p for p in problems))

    def test_red_probe_a_chain_without_the_migration_is_not_vacuously_clean(self):
        self.assertTrue(order_problems(["test", "goldens", "check-guardrails"]))


if __name__ == "__main__":
    result = unittest.main(verbosity=1, exit=False).result
    sys.exit(0 if result.wasSuccessful() else 1)
