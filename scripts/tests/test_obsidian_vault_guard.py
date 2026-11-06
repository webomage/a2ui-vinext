#!/usr/bin/env python3
"""Offline unit & throwaway-git tests for scripts/obsidian_vault_guard.py & deploy/landing integration (T653)."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import deploy_cert as dc  # noqa: E402
import obsidian_vault_guard as ovg  # noqa: E402
import session_complete as sc  # noqa: E402


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


def _init_repo(path: Path, *, bare: bool = False) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if bare:
        subprocess.run(["git", "init", "-q", "--bare", "-b", "beta"], cwd=str(path), check=True)
        return
    subprocess.run(["git", "init", "-q", "-b", "beta"], cwd=str(path), check=True)
    _git(path, "config", "user.email", "test@w0m.local")
    _git(path, "config", "user.name", "w0m Test")
    _git(path, "config", "commit.gpgsign", "false")


def _commit_all(repo: Path, msg: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", msg)
    return _git(repo, "rev-parse", "HEAD")


class ObsidianVaultGuardTests(unittest.TestCase):
    def test_vault_path_boundary_classification(self) -> None:
        self.assertTrue(ovg.is_obsidian_vault_path(".obsidian/app.json"))
        self.assertTrue(ovg.is_obsidian_vault_path("projects/w0m/vault/.obsidian/app.json"))
        self.assertTrue(ovg.is_obsidian_vault_path("projects/w0m/vault/notes/architecture.md"))
        self.assertTrue(ovg.is_obsidian_vault_path("projects/artemio/vault/index.md"))

        self.assertFalse(ovg.is_obsidian_vault_path("apps/cp/src/lib/vault-reader.ts"))
        self.assertFalse(ovg.is_obsidian_vault_path("project/scripts/resume_vault_verify.py"))
        self.assertFalse(ovg.is_obsidian_vault_path("scripts/vault_push_r2.py"))
        self.assertFalse(ovg.is_obsidian_vault_path("README.md"))

    def test_readonly_inspection_classifies_noop_json_live_vault_and_blocking_dirt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            repo = Path(tmp_str) / "w0m-web"
            _init_repo(repo)
            app_json = repo / "projects" / "w0m" / "vault" / ".obsidian" / "app.json"
            note_md = repo / "projects" / "w0m" / "vault" / "notes" / "plan.md"
            code_ts = repo / "apps" / "web" / "src" / "index.ts"
            app_json.parent.mkdir(parents=True, exist_ok=True)
            note_md.parent.mkdir(parents=True, exist_ok=True)
            code_ts.parent.mkdir(parents=True, exist_ok=True)

            app_json.write_text('{\n  "readableLineLength": true,\n  "strictLineBreaks": false\n}\n', encoding="utf-8")
            note_md.write_text("# Plan\n\nInitial text.\n", encoding="utf-8")
            code_ts.write_text("export const ok = true;\n", encoding="utf-8")
            _commit_all(repo, "chore: seed vault and app")

            # 1. Obsidian strips trailing newline & reorders keys without semantic change
            raw_no_newline = '{"strictLineBreaks":false,"readableLineLength":true}'
            app_json.write_text(raw_no_newline, encoding="utf-8")
            cls1 = ovg.inspect_repo_worktree(repo, include_untracked=True)
            self.assertTrue(cls1.is_runtime_clean)
            self.assertEqual(cls1.noop_obsidian_json, ["projects/w0m/vault/.obsidian/app.json"])
            self.assertEqual(cls1.live_vault_edits, [])
            # Must NOT rewrite disk during read-only inspection (avoids inotify loops with Obsidian)
            self.assertEqual(app_json.read_text(encoding="utf-8"), raw_no_newline)

            # 2. Genuine unstaged vault edit + untracked vault note -> still runtime-clean, recorded in live_vault_edits
            note_md.write_text("# Plan\n\nLive editing in Obsidian.\n", encoding="utf-8")
            untracked_note = repo / "projects" / "w0m" / "vault" / "notes" / "scratch.md"
            untracked_note.write_text("Uncommitted vault note\n", encoding="utf-8")
            cls2 = ovg.inspect_repo_worktree(repo, include_untracked=True)
            self.assertTrue(cls2.is_runtime_clean)
            self.assertIn("projects/w0m/vault/notes/plan.md", cls2.live_vault_edits)
            self.assertIn("projects/w0m/vault/notes/scratch.md", cls2.live_vault_edits)

            # 3. Staged vault change MUST block (agent forgot to commit staged work)
            _git(repo, "add", "projects/w0m/vault/notes/plan.md")
            cls_staged = ovg.inspect_repo_worktree(repo, include_untracked=False)
            self.assertFalse(cls_staged.is_runtime_clean)
            self.assertEqual(cls_staged.blocking_dirty, ["projects/w0m/vault/notes/plan.md"])
            _git(repo, "reset", "HEAD", "--", "projects/w0m/vault/notes/plan.md")

            # 4. Non-vault code edit MUST block
            code_ts.write_text("export const ok = false;\n", encoding="utf-8")
            cls_code = ovg.inspect_repo_worktree(repo, include_untracked=False)
            self.assertFalse(cls_code.is_runtime_clean)
            self.assertEqual(cls_code.blocking_dirty, ["apps/web/src/index.ts"])

    def test_deploy_cert_survives_live_vault_edits_and_fails_closed_on_code_or_staged_edits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            estate = tmp / "w0m"
            _init_repo(estate)
            (estate / ".gitignore").write_text("w0m-web/\n", encoding="utf-8")
            (estate / ".w0m").mkdir(parents=True, exist_ok=True)
            (estate / ".w0m" / "sdlc.json").write_text(
                json.dumps({"repos": {"web": "w0m-web"}}) + "\n",
                encoding="utf-8",
            )
            _commit_all(estate, "chore: init umbrella")

            web = estate / "w0m-web"
            _init_repo(web)
            (web / "project").mkdir(parents=True, exist_ok=True)
            (web / "project" / "test-suites.json").write_text('{"suites": []}\n', encoding="utf-8")
            app_json = web / "projects" / "w0m" / "vault" / ".obsidian" / "app.json"
            note_md = web / "projects" / "w0m" / "vault" / "index.md"
            app_json.parent.mkdir(parents=True, exist_ok=True)
            app_json.write_text('{\n  "vimMode": false\n}\n', encoding="utf-8")
            note_md.write_text("# Vault\n", encoding="utf-8")
            _commit_all(web, "chore: init web")

            env = {"W0M_DEPLOY_CERT_CACHE_DIR": str(tmp / "cert-cache"), "W0M_DEPLOY_LOGGED": "1"}
            rc0, _ = dc.cmd_certify(estate, env=env, runner=lambda *_a, **_k: 0)
            self.assertEqual(rc0, 0)

            # Live Obsidian edits in vault do NOT invalidate committed HEAD deploy certificate
            app_json.write_text('{"vimMode":false}', encoding="utf-8")
            note_md.write_text("# Vault\n\nLive session note while deploy is running.\n", encoding="utf-8")
            state_live = dc.inspect_tree_set(estate)
            self.assertTrue(state_live.is_clean)
            self.assertEqual(state_live.vault_dirty_files, {"w0m-web": ["projects/w0m/vault/index.md"]})
            rc_hit, summary_hit = dc.cmd_certify(estate, env=env, runner=lambda *_a, **_k: 1)
            self.assertEqual(rc_hit, 0)
            self.assertTrue(summary_hit["cached"])

            # Non-vault tracked file edit STILL fails closed immediately
            (web / "project" / "test-suites.json").write_text('{"suites": [{"name": "x"}]}\n', encoding="utf-8")
            state_dirty = dc.inspect_tree_set(estate)
            self.assertFalse(state_dirty.is_clean)
            self.assertEqual(state_dirty.dirty_repos, ["w0m-web"])

    def test_fast_forward_merges_obsidian_json_and_notes_and_protects_conflicts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            origin = tmp / "origin-web.git"
            _init_repo(origin, bare=True)

            canonical = tmp / "canonical" / "w0m-web"
            _init_repo(canonical)
            _git(canonical, "remote", "add", "origin", str(origin))
            app_json = canonical / "projects" / "w0m" / "vault" / ".obsidian" / "app.json"
            roadmap_md = canonical / "projects" / "w0m" / "vault" / "roadmap.md"
            conflict_md = canonical / "projects" / "w0m" / "vault" / "daily.md"
            app_json.parent.mkdir(parents=True, exist_ok=True)
            app_json.write_text('{\n  "readableLineLength": true,\n  "showFrontmatter": true\n}\n', encoding="utf-8")
            roadmap_md.write_text("Line 1\n\nLine 2\n\nLine 3\n", encoding="utf-8")
            conflict_md.write_text("Shared heading\nSame line edited both sides\n", encoding="utf-8")
            _commit_all(canonical, "chore: initial")
            _git(canonical, "push", "-q", "-u", "origin", "beta")

            # Clone an agent worktree that lands upstream changes on origin/beta
            agent = tmp / "agent-web"
            subprocess.run(["git", "clone", "-q", "-b", "beta", str(origin), str(agent)], check=True)
            _git(agent, "config", "user.email", "agent@w0m.local")
            _git(agent, "config", "user.name", "Agent")
            _git(agent, "config", "commit.gpgsign", "false")

            (agent / "projects" / "w0m" / "vault" / ".obsidian" / "app.json").write_text(
                '{\n  "readableLineLength": true,\n  "showFrontmatter": true,\n  "alwaysUpdateLinks": true\n}\n',
                encoding="utf-8",
            )
            (agent / "projects" / "w0m" / "vault" / "roadmap.md").write_text(
                "Line 1 (updated upstream)\n\nLine 2\n\nLine 3\n",
                encoding="utf-8",
            )
            (agent / "projects" / "w0m" / "vault" / "daily.md").write_text(
                "Shared heading\nUpstream replacement on line 2\n",
                encoding="utf-8",
            )
            upstream_sha = _commit_all(agent, "feat: upstream vault & config updates")
            _git(agent, "push", "-q", "origin", "beta")

            # Meanwhile in canonical, Obsidian has live unstaged edits across all 3 files + an untracked note!
            app_json.write_text('{"readableLineLength":false,"showFrontmatter":true}', encoding="utf-8")
            roadmap_md.write_text("Line 1\n\nLine 2\n\nLine 3 (edited live in Obsidian)\n", encoding="utf-8")
            conflict_md.write_text("Shared heading\nOperator live note on line 2\n", encoding="utf-8")
            inbox_note = canonical / "projects" / "w0m" / "vault" / "inbox-note.md"
            inbox_note.write_text("Fresh untracked note\n", encoding="utf-8")

            outcomes = sc.fast_forward_canonical_checkout(tmp / "canonical", ["w0m-web"])
            self.assertTrue(outcomes["w0m-web"].startswith("fast_forwarded:"))
            self.assertEqual(_git(canonical, "rev-parse", "HEAD"), upstream_sha)

            # 1. `.obsidian/app.json` merged both upstream `alwaysUpdateLinks` and local `readableLineLength=false` as valid JSON!
            merged_cfg: dict[str, object] = json.loads(app_json.read_text(encoding="utf-8"))
            self.assertEqual(
                merged_cfg,
                {
                    "readableLineLength": False,
                    "showFrontmatter": True,
                    "alwaysUpdateLinks": True,
                },
            )

            # 2. `roadmap.md` cleanly 3-way merged both non-overlapping paragraphs!
            merged_roadmap = roadmap_md.read_text(encoding="utf-8")
            self.assertIn("Line 1 (updated upstream)", merged_roadmap)
            self.assertIn("Line 3 (edited live in Obsidian)", merged_roadmap)

            # 3. `daily.md` overlapping line kept operator's live note without `<<<<<<<` corruption + wrote upstream sidecar!
            live_daily = conflict_md.read_text(encoding="utf-8")
            self.assertEqual(live_daily, "Shared heading\nOperator live note on line 2\n")
            self.assertNotIn("<<<<<<<", live_daily)
            sidecars = list(conflict_md.parent.glob("daily.upstream-*.md"))
            self.assertEqual(len(sidecars), 1)
            self.assertIn("Upstream replacement on line 2", sidecars[0].read_text(encoding="utf-8"))

            # 4. Untracked vault note survived untouched!
            self.assertEqual(inbox_note.read_text(encoding="utf-8"), "Fresh untracked note\n")


if __name__ == "__main__":
    res = unittest.main(verbosity=1, exit=False).result
    if res.wasSuccessful():
        print(f"  ✅ test-obsidian-vault-guard: {res.testsRun} check(s) passed")
        raise SystemExit(0)
    raise SystemExit(1)
