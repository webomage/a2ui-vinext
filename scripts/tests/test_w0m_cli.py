#!/usr/bin/env python3
"""Unit tests for T598 — Unified `w0m` CLI (`scripts/w0m_cli.py`)."""

from __future__ import annotations

import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import w0m_cli  # noqa: E402


class TestW0mCli(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="w0m-cli-test-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

    def test_derive_orca_project_id(self) -> None:
        self.assertEqual(
            w0m_cli.derive_orca_project_id("git@github.com:webomage/w0m.git"),
            "github:webomage/w0m",
        )
        self.assertEqual(
            w0m_cli.derive_orca_project_id("https://github.com/casualuser/bridgeroad-w0m.git"),
            "github:casualuser/bridgeroad-w0m",
        )
        self.assertEqual(
            w0m_cli.derive_orca_project_id("git@gitlab.com:acme/platform.git"),
            "git:gitlab.com/acme/platform",
        )
        self.assertEqual(
            w0m_cli.derive_orca_project_id("", fallback_id="pandatransfer"),
            "repo:pandatransfer",
        )

    def test_skill_list_and_search(self) -> None:
        proj = self.tmp / "sample-proj"
        (proj / ".w0m").mkdir(parents=True, exist_ok=True)
        (proj / ".w0m" / "skills.json").write_text(
            json.dumps(
                {
                    "project": "sample-proj",
                    "skills": {
                        "w0m-sdlc-start": {"provider": "w0m-native", "version": "1.0.0"},
                        "svelte-5": {"provider": "skills.sh", "version": "0.2.0"},
                    },
                    "exclude": {"legacy-skill": "deprecated"},
                    "auto_recommend": True,
                }
            ),
            encoding="utf-8",
        )
        (proj / ".w0m" / "skills.lock.json").write_text(
            json.dumps(
                {
                    "lockfileVersion": 1,
                    "generatedAt": "2026-11-01T00:00:00Z",
                    "skills": {
                        "w0m-sdlc-start": {
                            "provider": "w0m-native",
                            "resolved": "1.0.0",
                            "scope": "project",
                            "path": ".agents/skills/w0m-sdlc-start",
                            "integrity": "sha256-abcdef1234567890",
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        data = w0m_cli.skill_list_data(proj, include_registry=False)
        self.assertEqual(data["project"], "sample-proj")
        self.assertEqual(data["declared_count"], 2)
        self.assertEqual(data["locked_count"], 1)
        self.assertEqual(data["excluded_count"], 1)
        by_name = {s["name"]: s for s in data["skills"]}
        self.assertTrue(by_name["w0m-sdlc-start"]["locked"])
        self.assertFalse(by_name["svelte-5"]["locked"])

        # Search canonical skills registry
        matches = w0m_cli.skill_search_data("sdlc")
        self.assertTrue(any("sdlc" in m["name"] for m in matches))

    def test_project_list_and_link_remote(self) -> None:
        repo_dir = self.tmp / "pandatransfer"
        repo_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-q", str(repo_dir)], check=True)
        (repo_dir / ".w0m").mkdir(parents=True, exist_ok=True)
        (repo_dir / ".w0m" / "skills.json").write_text(
            json.dumps({"project": "pandatransfer", "skills": {"w0m": {"provider": "w0m-native", "version": "*"}}}),
            encoding="utf-8",
        )

        policy_file = self.tmp / "clients-policy.json"
        policy_file.write_text(
            json.dumps(
                {
                    "project": "w0m",
                    "projects": [
                        {
                            "id": "pandatransfer",
                            "role": "self-managed",
                            "root": "pandatransfer",
                            "enabled": True,
                            "runtime": {"substrate": "host"},
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        rows = w0m_cli.project_list_data(estate_root=self.tmp, policy_path=policy_file, extra_proj_Root=self.tmp / "none")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], "pandatransfer")
        self.assertEqual(rows[0]["orca_project_id"], "repo:pandatransfer")
        self.assertEqual(rows[0]["skills_count"], 1)

        linked = w0m_cli.link_project_remote(
            "pandatransfer",
            "git@github.com:webomage/pandatransfer.git",
            estate_root=self.tmp,
            policy_path=policy_file,
        )
        self.assertEqual(linked["orca_project_id"], "github:webomage/pandatransfer")

    def test_install_w0m_shim_and_cli_help(self) -> None:
        bin_dir = self.tmp / "bin"
        shim = w0m_cli.install_w0m_shim(bin_dir)
        self.assertTrue(shim.is_file())
        self.assertIn("w0m_cli.py", shim.read_text(encoding="utf-8"))

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = w0m_cli.main(["--help"])
        self.assertEqual(rc, 0)
        self.assertIn("Unified CLI for Skills, Projects", buf.getvalue())

        cat_buf = io.StringIO()
        with redirect_stdout(cat_buf):
            rc_cat = w0m_cli.main(["catalog", "list", "--kind", "System", "--json"])
        self.assertEqual(rc_cat, 0)
        cat_data = json.loads(cat_buf.getvalue())
        self.assertGreaterEqual(cat_data["count"], 1)

    def test_track_and_automation_commands(self) -> None:
        trk_buf = io.StringIO()
        with redirect_stdout(trk_buf):
            rc_trk = w0m_cli.main(["track", "show", "track-c", "--json"])
        self.assertEqual(rc_trk, 0)
        trk_data = json.loads(trk_buf.getvalue())
        self.assertEqual(trk_data["id"], "track-c")
        self.assertEqual(trk_data["agent_id"], "agy:agy-orca")
        self.assertEqual(trk_data["host_id"], "local")
        self.assertIn("T597", trk_data["tickets"])

        auto_buf = io.StringIO()
        with redirect_stdout(auto_buf):
            rc_auto = w0m_cli.main(["automation", "templates", "--json"])
        self.assertEqual(rc_auto, 0)
        auto_data = json.loads(auto_buf.getvalue())
        self.assertGreaterEqual(auto_data["count"], 4)
        ids = {t["id"] for t in auto_data["templates"]}
        self.assertIn("in-triage-watch", ids)
        self.assertIn("prs-review-watch", ids)
        self.assertIn("beta-drift-watch", ids)
        self.assertIn("catalog-drift-watch", ids)


if __name__ == "__main__":
    unittest.main()
