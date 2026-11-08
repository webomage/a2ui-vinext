#!/usr/bin/env python3
"""Unit and RED-probe suite for `scripts/automation_health.py` and `preflight` Obsidian churn handling (T652)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import automation_health as ah  # noqa: E402
import preflight as pf  # noqa: E402
import sync_github as sg  # noqa: E402


def _git(repo: Path, *args: str) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(
        {
            "LC_ALL": "C",
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        }
    )
    res = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    return res.stdout.strip()


def _init_git_repo(repo: Path) -> str:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q")
    (repo / "README.md").write_text("init\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-q", "-m", "chore: init")
    return _git(repo, "rev-parse", "HEAD")


class TestAutomationHealth(unittest.TestCase):
    def _build_fixture_estate(self, tmp: Path, *, max_pending: int = 2, max_graph_lag: int = 2) -> tuple[Path, Path]:
        estate = tmp / "estate"
        (estate / ".w0m").mkdir(parents=True, exist_ok=True)
        sdlc: dict[str, Any] = {
            "automation_health": {
                "max_pending_ticket_mirror": max_pending,
                "max_graph_union_commit_lag": max_graph_lag,
                "max_cf_single_redirect_rules_per_zone": 10,
                "forbid_detached_git_log_hooks": True,
                "forbid_swallowed_deploy_snapshots": True,
            }
        }
        (estate / ".w0m" / "sdlc.json").write_text(json.dumps(sdlc), encoding="utf-8")

        # Clean Cloudflare Free-Tier Single Redirect ruleset fixture (<= 10 rules, braces inside string + comment)
        cf_dir = estate / "w0m-api" / "cloudflare"
        cf_dir.mkdir(parents=True, exist_ok=True)
        (cf_dir / "redirects.tf").write_text(
            "# rules { commented out block must not count }\n"
            'resource "cloudflare_ruleset" "http_request_dynamic_redirect" {\n'
            '  zone_id = data.cloudflare_zone.this.id\n'
            '  name    = "default"\n'
            '  kind    = "zone"\n'
            '  phase   = "http_request_dynamic_redirect"\n\n'
            "  rules {\n"
            '    action      = "redirect"\n'
            '    description = "301 www and beta"\n'
            "    enabled     = true\n"
            '    expression  = "(http.host in {\\"www.webomage.com\\" \\"beta.webomage.com\\"})"\n'
            "    action_parameters {\n"
            "      from_value {\n"
            "        status_code           = 301\n"
            "        preserve_query_string = true\n"
            "        target_url {\n"
            '          expression = "concat(\\"https://webomage.com\\", http.request.uri.path)"\n'
            "        }\n"
            "      }\n"
            "    }\n"
            "  }\n"
            "}\n",
            encoding="utf-8",
        )

        # Clean justfile
        (estate / "justfile").write_text(
            "deploy-web:\n"
            "    @node w0m-web/apps/web/scripts/snapshot-settings.mjs\n\n"
            "_post-deploy-knowledge:\n"
            "    python3 scripts/graph_global.py --auto-rebuild-stale\n",
            encoding="utf-8",
        )

        # Clean husky hook
        husky = estate / "w0m-web" / ".husky"
        husky.mkdir(parents=True, exist_ok=True)
        (husky / "pre-push").write_text("#!/bin/sh\necho ok\n", encoding="utf-8")

        # Init w0m-web git repo + graph manifest
        web_head = _init_git_repo(estate / "w0m-web")
        manifest_path = tmp / "w0m-union-manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "w0m-web": {
                        "built_at_commit": web_head,
                        "head_at_merge": web_head,
                        "basis": "built_at_commit",
                        "path": "w0m-web",
                    }
                }
            ),
            encoding="utf-8",
        )

        # Create 2 synced tickets in .tasks/ + index in w0m-web/project/tickets-sync-index.json
        tasks_dir = estate / ".tasks"
        tasks_dir.mkdir(parents=True, exist_ok=True)
        proj_dir = estate / "w0m-web" / "project"
        proj_dir.mkdir(parents=True, exist_ok=True)
        for idx in (1, 2):
            (tasks_dir / f"T{idx}.md").write_text(
                f"---\nid: T{idx}\ntitle: Test {idx}\nstatus: queued\narea: sdlc\nqueue: now\n"
                f"priority: P1\nrepos: [web]\nepic: \"\"\nspec: \"\"\ngh_issue: {idx}\ntags: [sdlc]\n"
                f"created: 2026-11-05\n---\n\n# T{idx}\n\n## Summary\n\nBody {idx}.\n",
                encoding="utf-8",
            )

        # Compute exact hashes for T1 and T2
        orig_dry, orig_tdir, orig_idx = sg.DRY, sg.TICKETS_DIR, sg.INDEX
        try:
            sg.DRY = True
            sg.TICKETS_DIR = tasks_dir
            sg.INDEX = proj_dir / "tickets-sync-index.json"
            loaded = sg.load_tickets()
            hashes = {
                t["id"]: sg.projection_hash(sg.projection_of(t, sg.summary_of(t["id"])))
                for t in loaded
            }
        finally:
            sg.DRY, sg.TICKETS_DIR, sg.INDEX = orig_dry, orig_tdir, orig_idx

        (proj_dir / "tickets-sync-index.json").write_text(
            json.dumps({"projection_version": sg.PROJECTION_VERSION, "tickets": hashes}),
            encoding="utf-8",
        )
        return estate, manifest_path

    def test_clean_estate_passes_all_checks(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            estate, mpath = self._build_fixture_estate(Path(td))
            ok, results = ah.run_checks(estate, manifest_path=mpath, require_graphify=True)
            self.assertTrue(ok, results)
            self.assertEqual(len(results), 6)

    def test_red_detached_nohup_hook_fails(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            estate, mpath = self._build_fixture_estate(Path(td))
            (estate / "w0m-web" / ".husky" / "pre-push").write_text(
                '#!/bin/sh\nnohup python3 ../scripts/sync_github.py >".git/w0m-ticket-sync.log" 2>&1 &\n',
                encoding="utf-8",
            )
            ok, results = ah.run_checks(estate, manifest_path=mpath, require_graphify=True)
            self.assertFalse(ok)
            by_name = {r["name"]: r for r in results}
            self.assertFalse(by_name["no-detached-git-log-hooks"]["ok"])

    def test_red_swallowed_snapshot_or_skipped_post_deploy_knowledge_fails(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            estate, mpath = self._build_fixture_estate(Path(td))
            (estate / "justfile").write_text(
                "deploy-web:\n"
                "    @node w0m-web/apps/web/scripts/snapshot-settings.mjs || true\n\n"
                "_post-deploy-knowledge:\n"
                "    if [ -n \"${W0M_RELEASE_WORKTREE:-}\" ]; then echo \"knowledge refresh skipped in a release worktree\"; exit 0; fi\n"
                "    just knowledge-light || true\n",
                encoding="utf-8",
            )
            ok, results = ah.run_checks(estate, manifest_path=mpath, require_graphify=True)
            self.assertFalse(ok)
            by_name = {r["name"]: r for r in results}
            self.assertFalse(by_name["no-swallowed-deploy-producers"]["ok"])
            self.assertIn("snapshot-*.mjs", by_name["no-swallowed-deploy-producers"]["detail"])
            self.assertIn("unconditionally skips", by_name["no-swallowed-deploy-producers"]["detail"])

    def test_red_pending_ticket_mirror_exceeding_ceiling_fails(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            estate, mpath = self._build_fixture_estate(Path(td), max_pending=1)
            for idx in (3, 4):
                (estate / ".tasks" / f"T{idx}.md").write_text(
                    f"---\nid: T{idx}\ntitle: New {idx}\nstatus: queued\narea: sdlc\nqueue: now\n"
                    f"priority: P1\nrepos: [web]\nepic: \"\"\nspec: \"\"\ngh_issue:\ntags: [sdlc]\n"
                    f"created: 2026-11-05\n---\n\n# T{idx}\n\n## Summary\n\nUnsynced.\n",
                    encoding="utf-8",
                )
            ok, results = ah.run_checks(estate, manifest_path=mpath, require_graphify=True)
            self.assertFalse(ok)
            by_name = {r["name"]: r for r in results}
            self.assertFalse(by_name["bounded-ticket-mirror-lag"]["ok"])
            self.assertIn("2/4", by_name["bounded-ticket-mirror-lag"]["detail"])

    def test_red_graph_union_commit_lag_exceeding_ceiling_fails(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            estate, mpath = self._build_fixture_estate(Path(td), max_graph_lag=1)
            web = estate / "w0m-web"
            for n in (1, 2):
                (web / "README.md").write_text(f"step {n}\n", encoding="utf-8")
                _git(web, "add", "README.md")
                _git(web, "commit", "-q", "-m", f"chore: step {n}")
            ok, results = ah.run_checks(estate, manifest_path=mpath, require_graphify=True)
            self.assertFalse(ok)
            by_name = {r["name"]: r for r in results}
            self.assertFalse(by_name["bounded-graph-union-lag"]["ok"])
            self.assertIn("w0m-web: +2", by_name["bounded-graph-union-lag"]["detail"])

    def test_preflight_obsidian_whitespace_churn_vs_substantive_edit(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "repo"
            _init_git_repo(repo)
            obs = repo / "projects" / "w0m" / "vault" / ".obsidian"
            obs.mkdir(parents=True, exist_ok=True)
            app_json = obs / "app.json"
            app_json.write_text('{\n  "spellcheck": true\n}\n', encoding="utf-8")
            _git(repo, "add", "projects/w0m/vault/.obsidian/app.json")
            _git(repo, "commit", "-q", "-m", "chore: add obsidian app.json")

            # 1. Strip trailing newline only (exact Obsidian Desktop vault-open churn)
            app_json.write_text('{\n  "spellcheck": true\n}', encoding="utf-8")
            lines = [ln for ln in pf._git(repo, "status", "--porcelain").splitlines() if ln]
            self.assertEqual(len(lines), 1)
            self.assertTrue(pf._is_benign_obsidian_churn(repo, lines[0]))

            # 2. Substantive setting edit inside app.json MUST NOT be treated as benign churn
            app_json.write_text('{\n  "spellcheck": false\n}', encoding="utf-8")
            lines2 = [ln for ln in pf._git(repo, "status", "--porcelain").splitlines() if ln]
            self.assertFalse(pf._is_benign_obsidian_churn(repo, lines2[0]))

    def test_graph_global_clean_env_strips_hook_git_dir_overrides(self) -> None:
        from unittest import mock
        import graph_global as gg

        with mock.patch.dict(
            os.environ,
            {
                "GIT_DIR": "/tmp/caller-hook/.git",
                "GIT_WORK_TREE": "/tmp/caller-hook",
                "GIT_INDEX_FILE": "/tmp/caller-hook/.git/index",
                "GIT_COMMON_DIR": "/tmp/caller-hook/.git",
                "GIT_SSH_COMMAND": "ssh -o BatchMode=yes",
            },
            clear=False,
        ):
            cleaned = gg._clean_env({"PYTHONHASHSEED": "0"})
            self.assertNotIn("GIT_DIR", cleaned)
            self.assertNotIn("GIT_WORK_TREE", cleaned)
            self.assertNotIn("GIT_INDEX_FILE", cleaned)
            self.assertNotIn("GIT_COMMON_DIR", cleaned)
            self.assertEqual(cleaned.get("GIT_SSH_COMMAND"), "ssh -o BatchMode=yes")
            self.assertEqual(cleaned.get("PYTHONHASHSEED"), "0")

    def test_red_cf_free_tier_redirect_quota_exceeded_or_business_regex_or_vacuous_fails(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            estate, mpath = self._build_fixture_estate(Path(td))
            cf_tf = estate / "w0m-api" / "cloudflare" / "redirects.tf"

            # 1. 11 rules (> 10 Free-Tier cap) MUST fail closed with exact count
            eleven_rules = "\n".join(
                f'  rules {{\n    action = "redirect"\n    expression = "(http.host eq \\"h{i}.webomage.com\\")"\n  }}'
                for i in range(11)
            )
            cf_tf.write_text(
                'resource "cloudflare_ruleset" "http_request_dynamic_redirect" {\n'
                '  phase = "http_request_dynamic_redirect"\n'
                f"{eleven_rules}\n"
                "}\n",
                encoding="utf-8",
            )
            ok, results = ah.run_checks(estate, manifest_path=mpath, require_graphify=True)
            self.assertFalse(ok)
            by_name = {r["name"]: r for r in results}
            self.assertFalse(by_name["cf-free-tier-redirect-quota"]["ok"])
            self.assertIn("11 rules > Free-Tier cap 10", by_name["cf-free-tier-redirect-quota"]["detail"])

            # 2. Business-only `regex_replace` / `matches` inside <= 10 rules MUST fail closed
            cf_tf.write_text(
                'resource "cloudflare_ruleset" "http_request_dynamic_redirect" {\n'
                '  phase = "http_request_dynamic_redirect"\n'
                "  rules {\n"
                '    action = "redirect"\n'
                '    expression = "(http.request.uri.path matches \\"^/interview/\\")"\n'
                "    action_parameters {\n"
                "      from_value {\n"
                "        target_url {\n"
                '          expression = "regex_replace(http.request.uri.path, \\"^/interview/\\", \\"/me/interviews/\\")"\n'
                "        }\n"
                "      }\n"
                "    }\n"
                "  }\n"
                "}\n",
                encoding="utf-8",
            )
            ok2, results2 = ah.run_checks(estate, manifest_path=mpath, require_graphify=True)
            self.assertFalse(ok2)
            by_name2 = {r["name"]: r for r in results2}
            self.assertFalse(by_name2["cf-free-tier-redirect-quota"]["ok"])
            self.assertIn("Business/Enterprise-only regex operator", by_name2["cf-free-tier-redirect-quota"]["detail"])

            # 3. Vacuous pass refusal when 0 dynamic-redirect rulesets are parsed
            cf_tf.write_text("# empty file\n", encoding="utf-8")
            ok3, _ = ah.check_cloudflare_free_tier_redirect_quota(estate, 10)
            self.assertFalse(ok3)


if __name__ == "__main__":
    result = unittest.main(verbosity=1, exit=False).result
    if result.wasSuccessful():
        print(f"  [PASS] test-automation-health: {result.testsRun} check(s) passed")
        sys.exit(0)
    sys.exit(1)
