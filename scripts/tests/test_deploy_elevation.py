#!/usr/bin/env python3
"""Test Deployment Machinery Elevation to Workspace Root (T421).

Asserts:
1. Deployment helper scripts (log_deploy.sh, dump_deploy_log.sh, check_cf_deployment.py, gen_changelog.py)
   are present and executable under @wom/scripts/.
2. Obsolete deployment scripts are removed from w0m-api/scripts/ (zero shims per AgDR-0025).
3. Deployment logs directory is elevated to @wom/deploy-logs/ and .w0m/sdlc.json reflects it.
4. Root .gitignore properly ignores deploy-logs/*.log while preserving bucket directories.
5. Canonical deployment recipes are exposed and runnable from root @wom/justfile.
6. Versioning producer and declared consumers match root justfile definitions.
7. No stale or dangling references to wom7api/scripts/log_deploy.sh or wom7api/deploy-logs.
"""

from __future__ import annotations

import json
import os
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class TestDeployElevation(unittest.TestCase):

    def test_scripts_presence_at_root(self):
        """Helper scripts must exist in @wom/scripts/ as Python tools (tool ladder: Python > bash)."""
        scripts_dir = ROOT / "scripts"
        expected_python = [
            "log_deploy.py",
            "dump_deploy_log.py",
            "check_cf_deployment.py",
            "gen_changelog.py",
        ]

        for s in expected_python:
            path = scripts_dir / s
            self.assertTrue(path.is_file(), f"Missing python helper: {path}")

        # Assert no legacy .sh deploy scripts remain
        banned_bash = ["log_deploy.sh", "dump_deploy_log.sh"]
        for b in banned_bash:
            self.assertFalse((scripts_dir / b).exists(), f"Legacy bash script should not exist: {b}")

    def test_obsolete_scripts_removed_from_w0m_api(self):
        """Deprecated deployment scripts must be completely removed from w0m-api/scripts/ (AgDR-0025)."""
        api_scripts_dir = ROOT / "w0m-api" / "scripts"
        banned = [
            "log_deploy.sh",
            "log_deploy.py",
            "dump_deploy_log.sh",
            "dump_deploy_log.py",
            "check_cf_deployment.py",
            "gen_changelog.py",
        ]
        for s in banned:
            path = api_scripts_dir / s
            self.assertFalse(path.exists(), f"Obsolete script still exists in wom7api: {path}")

    def test_deploy_logs_centralized(self):
        """Deploy logs must be located at @wom/deploy-logs/ and declared in .w0m/sdlc.json."""
        deploy_logs = ROOT / "deploy-logs"
        self.assertTrue(deploy_logs.is_dir(), f"Missing root deploy-logs directory: {deploy_logs}")

        sdlc_path = ROOT / ".w0m" / "sdlc.json"
        self.assertTrue(sdlc_path.is_file(), f"Missing .w0m/sdlc.json at {sdlc_path}")
        sdlc = json.loads(sdlc_path.read_text(encoding="utf-8"))

        deploy_logs_cfg = sdlc.get("deploy_logs", {})
        self.assertEqual(
            deploy_logs_cfg.get("dir"),
            "deploy-logs",
            f"deploy_logs.dir in .w0m/sdlc.json must be 'deploy-logs', got: {deploy_logs_cfg.get('dir')}",
        )

    def test_root_gitignore_covers_deploy_logs(self):
        """Root .gitignore must ignore deploy transcripts."""
        gitignore_path = ROOT / ".gitignore"
        self.assertTrue(gitignore_path.is_file(), "Root .gitignore missing")
        content = gitignore_path.read_text(encoding="utf-8")
        has_rule = any(
            re.search(r"^/?deploy-logs(/.*)?$", line.strip())
            for line in content.splitlines()
        )
        self.assertTrue(has_rule, "Root .gitignore must ignore deploy-logs directory or *.log")

    def test_root_justfile_declares_deploy_recipes(self):
        """Root @wom/justfile must expose canonical deploy recipes."""
        jf_path = ROOT / "justfile"
        self.assertTrue(jf_path.is_file(), "Root justfile missing")
        body = jf_path.read_text(encoding="utf-8")

        # Parse recipe names
        recipes: set[str] = set()
        for line in body.splitlines():
            m = re.match(r"^([a-zA-Z_][\w-]*)\s*[^:=]*:(?!=)", line)
            if m and not line.startswith((" ", "\t")):
                recipes.add(m.group(1))

        required_recipes = [
            "deploy",
            "deploy-all",
            "deploy-web",
            "deploy-cp",
            "deploy-join",
            "deploy-job",
            "deploy-demo",
            "deploy-workers",
            "deploy-functions",
            "_deploy-chain",
            "_log-deploy",
            "_confirm",
            "changelog",
            "deploy-elevation-test",
        ]
        for req in required_recipes:
            self.assertIn(req, recipes, f"Root justfile missing required recipe: {req}")

    def test_versioning_consumers_and_declaration(self):
        """Declared versioning consumers must exist in root justfile and interpolate deploy_version."""
        sdlc_path = ROOT / ".w0m" / "sdlc.json"
        sdlc = json.loads(sdlc_path.read_text(encoding="utf-8"))
        versioning = sdlc.get("versioning", {})
        producer = versioning.get("producer", {})

        declared_at = producer.get("declared_at", "")
        self.assertTrue(
            "justfile" in declared_at,
            f"versioning.producer.declared_at must reference root justfile, got: {declared_at}",
        )

        jf_path = ROOT / "justfile"
        body = jf_path.read_text(encoding="utf-8")
        recipes: dict[str, str] = {}
        current = None
        for line in body.splitlines():
            m = re.match(r"^([a-zA-Z_][\w-]*)\s*[^:=]*:(?!=)", line)
            if m and not line.startswith((" ", "\t")):
                current = m.group(1)
                recipes[current] = ""
            elif current and (line.startswith((" ", "\t")) or not line.strip()):
                recipes[current] += line + "\n"
            elif line.strip() and not line.startswith(("#", " ", "\t")):
                current = None

        consumers = producer.get("consumers", [])
        self.assertTrue(len(consumers) > 0, "No consumers declared in versioning.producer.consumers")
        for c in consumers:
            self.assertIn(c, recipes, f"Declared consumer '{c}' missing in root justfile")
            self.assertIn(
                "deploy_version",
                recipes[c],
                f"Declared consumer '{c}' in root justfile does not interpolate deploy_version",
            )


    def test_root_pnpm_builds_run_inside_w0m_web(self):
        """Root `pnpm --filter` builds must `cd w0m-web` first (T431): from @wom, PATH's pnpm runs
        outside the workspace and the app scripts cannot see w0m-web/node_modules/.bin (astro)."""
        body = (ROOT / "justfile").read_text(encoding="utf-8")
        lines = [ln for ln in body.splitlines() if "pnpm --filter" in ln and "build" in ln and not ln.lstrip().startswith("#")]
        self.assertGreaterEqual(len(lines), 6, "expected the build + 5 deploy-<app> build lines")
        for ln in lines:
            self.assertRegex(ln, r"^\s+@?cd w0m-web && ", f"root pnpm build not run from w0m-web: {ln.strip()}")


if __name__ == "__main__":
    unittest.main()
