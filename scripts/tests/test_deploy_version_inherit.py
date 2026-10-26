#!/usr/bin/env python3
"""ONE deploy version across nested `just` processes (T431 run 7).

deploy-all spawns several `just` processes (root → `wom7api/justfile supabase-redeploy-all` → root
`deploy-functions`). `deploy_version` was a bare backtick, which runs once per PROCESS, so each hop
re-ran `date`: the functions were stamped 11 minutes after the apps and the transcript was named after
a version `deploy_log` never recorded. The fix exports the version from the outermost invocation.

The load-bearing probe reproduces the chain's shape without deploying anything: an outer `just`
spawns an inner one a second later (`--command` runs with the justfile's exports, exactly as a recipe
line does), and both must report the same version.
"""
from __future__ import annotations

import os
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSION_RE = re.compile(r"^\d{4}\.\d{2}\.\d{2}-\d{9,10}$")


def just(*args: str, env: dict | None = None) -> str:
    e = {k: v for k, v in os.environ.items() if not k.startswith("W0M_DEPLOY_")}
    e.update(env or {})
    return subprocess.run(["just", *args], cwd=ROOT, env=e, capture_output=True, text=True,
                          check=True).stdout.strip()


class DeployVersionInherit(unittest.TestCase):

    def test_nested_just_inherits_the_outer_version(self):
        out = just("--justfile", "justfile", "--command", "sh", "-c",
                   'echo "$W0M_DEPLOY_VERSION"; sleep 1.2; just --justfile wom7api/justfile --evaluate deploy_version').split("\n")
        outer, inner = out[0].strip(), out[-1].strip()
        self.assertRegex(outer, VERSION_RE)
        self.assertEqual(outer, inner, "a nested `just` minted its own version — the run-7 split")

    def test_both_justfiles_honour_an_inherited_version(self):
        v = "2026.01.01-1767225600"
        for jf in ("justfile", "wom7api/justfile"):
            self.assertEqual(just("--justfile", jf, "--evaluate", "deploy_version",
                                  env={"W0M_DEPLOY_VERSION": v}), v, jf)

    def test_a_standalone_run_still_mints_a_valid_version(self):
        for jf in ("justfile", "wom7api/justfile"):
            self.assertRegex(just("--justfile", jf, "--evaluate", "deploy_version"), VERSION_RE)


if __name__ == "__main__":
    unittest.main()
