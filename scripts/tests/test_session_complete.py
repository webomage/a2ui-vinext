#!/usr/bin/env python3
"""Offline unit and throwaway-git integration tests for scripts/session_complete.py (T640)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import session_complete as sc


def _git_init_repo(repo_dir: Path, *, bare: bool = False) -> None:
    repo_dir.mkdir(parents=True, exist_ok=True)
    args = ["git", "init", "-q"]
    if bare:
        args.append("--bare")
    else:
        args.extend(["-b", "beta"])
    subprocess.run(args, cwd=str(repo_dir), check=True)
    if not bare:
        subprocess.run(["git", "config", "user.email", "test@w0m.local"], cwd=str(repo_dir), check=True)
        subprocess.run(["git", "config", "user.name", "w0m Test"], cwd=str(repo_dir), check=True)
        subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=str(repo_dir), check=True)


SAMPLE_TICKET_OPEN = """---
id: T42
title: "Sample wrap-up ticket"
status: in-progress
area: sdlc
queue: now
priority: P1
repos: [tooling]
epic: "sdlc_tooling_platform"
spec: ""
spec_exempt: "audit_sweep"
agent_id: "agy:demo-set"
gh_issue:
tags: [sdlc]
created: 2026-11-04
---

# T42 -- Sample wrap-up ticket

## Summary

Sample summary.

## Acceptance criteria

- [ ] AC1 -- First observable outcome
- [x] AC2 -- Second observable outcome

## Definition of Done

All tests pass.

## Links

- **Epic:** [[ROADMAP]] section 13

## Status notes

- **2026-11-04**: Claimed T42.
"""


class SessionCompleteTests(unittest.TestCase):
    def test_detect_session_context_in_agent_tree_and_set_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            canon = tmp / "canon" / "w0m"
            work_root = tmp / "work"
            _git_init_repo(canon)
            (canon / ".w0m").mkdir(parents=True)
            (canon / ".tasks").mkdir(parents=True)
            (canon / ".w0m" / "sdlc.json").write_text('{"profile": "w0m"}\n', encoding="utf-8")
            (canon / ".tasks" / "T1.md").write_text("---\nid: T1\n---\n", encoding="utf-8")
            subprocess.run(["git", "add", "-A"], cwd=str(canon), check=True)
            subprocess.run(["git", "commit", "-q", "-m", "chore(T1): init"], cwd=str(canon), check=True)

            wt = work_root / "demo-set" / "w0m"
            wt.parent.mkdir(parents=True)
            subprocess.run(
                ["git", "worktree", "add", "-q", "-b", "agent/demo-set", str(wt), "HEAD"],
                cwd=str(canon),
                check=True,
            )

            conv_uuid = "c2262ec5-a16b-40d2-8638-3f0995a1902b"
            env_patch = {
                "ORCA_TERMINAL_HANDLE": "term_test_caller_1",
                "ORCA_TAB_ID": "tab_test_caller_1",
                "W0M_SESSION_CONVERSATION_ID": conv_uuid,
            }
            with mock.patch.dict(os.environ, env_patch, clear=False):
                ctx_inside = sc.detect_session_context(cwd=wt, work_root=work_root)
                self.assertTrue(ctx_inside.in_agent_tree)
                self.assertEqual(ctx_inside.set_name, "demo-set")
                self.assertEqual(Path(ctx_inside.worktree_root), wt.resolve())
                self.assertEqual(Path(ctx_inside.canonical_root), canon.resolve())
                self.assertEqual(ctx_inside.terminal_handle, "term_test_caller_1")
                self.assertEqual(ctx_inside.conversation_id, conv_uuid)

                ctx_override = sc.detect_session_context(
                    cwd=canon,
                    set_override="demo-set",
                    work_root=work_root,
                )
                self.assertTrue(ctx_override.in_agent_tree)
                self.assertEqual(ctx_override.set_name, "demo-set")
                self.assertEqual(Path(ctx_override.worktree_root), wt.resolve())
                self.assertEqual(Path(ctx_override.canonical_root), canon.resolve())

    def test_discover_target_tickets_from_status_and_claims(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            repo = Path(tmp_str) / "w0m"
            _git_init_repo(repo)
            (repo / ".w0m").mkdir()
            (repo / ".tasks").mkdir()
            (repo / ".w0m" / "sdlc.json").write_text('{"profile": "w0m"}\n', encoding="utf-8")
            (repo / ".tasks" / "T10.md").write_text(
                '---\nid: T10\nstatus: done\nagent_id: "agy:other"\n---\n',
                encoding="utf-8",
            )
            (repo / ".tasks" / "T11.md").write_text(
                '---\nid: T11\nstatus: in-progress\nagent_id: "agy:demo-set"\n---\n',
                encoding="utf-8",
            )
            subprocess.run(["git", "add", "-A"], cwd=str(repo), check=True)
            subprocess.run(["git", "commit", "-q", "-m", "chore(T10): base"], cwd=str(repo), check=True)

            # Untracked T12
            (repo / ".tasks" / "T12.md").write_text("---\nid: T12\nstatus: in-progress\n---\n", encoding="utf-8")

            discovered = sc.discover_target_tickets(repo, agent_id="agy:demo-set")
            self.assertEqual(discovered, ["T11", "T12"])

    def test_normalize_ticket_file_enforces_dod_acs_and_lesson_disposition(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            tpath = Path(tmp_str) / "T42.md"

            # 1. Missing Definition of Done -> fail closed
            no_dod = SAMPLE_TICKET_OPEN.replace("## Definition of Done\n\nAll tests pass.\n\n", "")
            tpath.write_text(no_dod, encoding="utf-8")
            with self.assertRaises(sc.SessionCompleteError) as cm_dod:
                sc.normalize_ticket_file(tpath, complete_acs=True, no_lessons=True)
            self.assertEqual(cm_dod.exception.step, "missing_dod")

            # 2. Unchecked AC without --complete-acs -> fail closed
            tpath.write_text(SAMPLE_TICKET_OPEN, encoding="utf-8")
            with self.assertRaises(sc.SessionCompleteError) as cm_ac:
                sc.normalize_ticket_file(tpath, complete_acs=False, no_lessons=True)
            self.assertEqual(cm_ac.exception.step, "unchecked_acs")
            self.assertIn("AC1", cm_ac.exception.detail)

            # 3. Missing lesson disposition without --no-lessons / --lesson-note -> fail closed
            with self.assertRaises(sc.SessionCompleteError) as cm_les:
                sc.normalize_ticket_file(tpath, complete_acs=True, no_lessons=False)
            self.assertEqual(cm_les.exception.step, "missing_lesson_disposition")

            # 4. Dry-run leaves disk untouched
            res_dry = sc.normalize_ticket_file(
                tpath,
                complete_acs=True,
                no_lessons=True,
                today="2026-11-04",
                dry_run=True,
            )
            self.assertTrue(res_dry.changed)
            self.assertIn("- [ ] AC1", tpath.read_text(encoding="utf-8"))

            # 5. Live normalization updates status, queue, closed_as, ACs, and lesson disposition
            res = sc.normalize_ticket_file(
                tpath,
                complete_acs=True,
                no_lessons=True,
                today="2026-11-04",
                dry_run=False,
            )
            self.assertTrue(res.changed)
            self.assertEqual(res.completed_acs, ["AC1"])
            self.assertTrue(res.lesson_disposition_added)
            updated = tpath.read_text(encoding="utf-8")
            self.assertIn("status: done\n", updated)
            self.assertIn("closed_as: completed\n", updated)
            self.assertIn("queue: done\n", updated)
            self.assertIn("- [x] AC1 -- First observable outcome", updated)
            self.assertIn("Lessons: none (routine delivery).", updated)

    def test_maybe_renumber_colliding_tickets_rewrites_branch_artifacts_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            origin = tmp / "origin.git"
            _git_init_repo(origin, bare=True)

            seed = tmp / "seed"
            _git_init_repo(seed)
            subprocess.run(["git", "remote", "add", "origin", str(origin)], cwd=str(seed), check=True)
            (seed / ".w0m").mkdir()
            (seed / ".tasks").mkdir()
            (seed / ".agents" / "reports").mkdir(parents=True)
            (seed / ".w0m" / "sdlc.json").write_text('{"profile": "w0m"}\n', encoding="utf-8")
            (seed / "LESSONS.md").write_text("# Lessons\n\n- Existing T10 rule.\n", encoding="utf-8")
            (seed / ".tasks" / "T10.md").write_text("---\nid: T10\nstatus: done\n---\n", encoding="utf-8")
            subprocess.run(["git", "add", "-A"], cwd=str(seed), check=True)
            subprocess.run(["git", "commit", "-q", "-m", "chore(T10): seed"], cwd=str(seed), check=True)
            subprocess.run(["git", "push", "-q", "origin", "HEAD:beta"], cwd=str(seed), check=True)

            # Create agent worktree off T10 before origin advances
            wt = tmp / "work" / "set-b" / "w0m"
            wt.parent.mkdir(parents=True)
            subprocess.run(["git", "fetch", "-q", "origin"], cwd=str(seed), check=True)
            subprocess.run(
                ["git", "worktree", "add", "-q", "-b", "agent/set-b", str(wt), "origin/beta"],
                cwd=str(seed),
                check=True,
            )
            subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=str(wt), check=True)

            # Agent B commits T11 locally
            (wt / ".tasks" / "T11.md").write_text(
                "---\nid: T11\ntitle: \"Agent B work\"\nstatus: done\n---\n\n# T11 -- Agent B\n",
                encoding="utf-8",
            )
            (wt / ".agents" / "reports").mkdir(parents=True, exist_ok=True)
            (wt / ".agents" / "reports" / "2026-11-04-t11-agent-b.md").write_text(
                "# T11 Report\n\nVerified t11.\n",
                encoding="utf-8",
            )
            (wt / "LESSONS.md").write_text(
                "# Lessons\n\n- Existing T10 rule.\n- Earned in T11: renumber cleanly.\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "add", "-A"], cwd=str(wt), check=True)
            subprocess.run(["git", "commit", "-q", "-m", "feat(T11): agent b local commit"], cwd=str(wt), check=True)

            # Meanwhile Agent A lands its own T11 onto origin/beta!
            (seed / ".tasks" / "T11.md").write_text(
                "---\nid: T11\ntitle: \"Agent A landed first\"\nstatus: done\n---\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "add", "-A"], cwd=str(seed), check=True)
            subprocess.run(["git", "commit", "-q", "-m", "feat(T11): agent a"], cwd=str(seed), check=True)
            subprocess.run(["git", "push", "-q", "origin", "HEAD:beta"], cwd=str(seed), check=True)

            mapped, renames = sc.maybe_renumber_colliding_tickets(wt, ["T11"], dry_run=False)
            self.assertEqual(renames, {"T11": "T12"})
            self.assertEqual(mapped, ["T12"])
            self.assertFalse((wt / ".tasks" / "T11.md").exists())
            self.assertTrue((wt / ".tasks" / "T12.md").is_file())
            self.assertIn("id: T12", (wt / ".tasks" / "T12.md").read_text(encoding="utf-8"))
            self.assertTrue((wt / ".agents" / "reports" / "2026-11-04-t12-agent-b.md").is_file())
            lessons_after = (wt / "LESSONS.md").read_text(encoding="utf-8")
            self.assertIn("Existing T10 rule.", lessons_after)
            self.assertIn("Earned in T12: renumber cleanly.", lessons_after)

    def test_mirror_reports_copies_matching_reports_idempotently(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            repo = Path(tmp_str) / "w0m"
            _git_init_repo(repo)
            (repo / ".agents" / "reports").mkdir(parents=True)
            (repo / "w0m-web" / "docs" / "reports").mkdir(parents=True)
            sdlc = {
                "session_wrapup": {
                    "reports_canonical_dir": ".agents/reports",
                    "reports_mirror_dir": "w0m-web/docs/reports",
                }
            }
            (repo / ".agents" / "reports" / "2026-11-04-t42-audit.md").write_text(
                "# T42 Audit\n",
                encoding="utf-8",
            )
            (repo / ".agents" / "reports" / "2026-10-01-t99-unrelated.md").write_text(
                "# T99 Old\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "add", "-A"], cwd=str(repo), check=True)
            subprocess.run(["git", "commit", "-q", "-m", "chore(T42): reports"], cwd=str(repo), check=True)

            first = sc.mirror_reports(repo, sdlc, ["T42"])
            self.assertEqual(first, ["w0m-web/docs/reports/2026-11-04-t42-audit.md"])
            self.assertTrue((repo / "w0m-web" / "docs" / "reports" / "2026-11-04-t42-audit.md").is_file())
            self.assertFalse((repo / "w0m-web" / "docs" / "reports" / "2026-10-01-t99-unrelated.md").exists())

            second = sc.mirror_reports(repo, sdlc, ["T42"])
            self.assertEqual(second, [])

    def test_run_verification_gates_fails_closed_on_nonzero_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            repo = Path(tmp_str)
            sdlc = {
                "session_wrapup": {
                    "verification_gates": [
                        "python3 -c \"import sys; sys.exit(0)\"",
                        "python3 -c \"import sys; sys.stderr.write('boom\\n'); sys.exit(2)\"",
                    ]
                }
            }
            with self.assertRaises(sc.SessionCompleteError) as cm:
                sc.run_verification_gates(repo, sdlc)
            self.assertEqual(cm.exception.step, "verification_gate_failed")
            self.assertIn("boom", cm.exception.detail)

    def test_run_verification_gates_scopes_ticket_schema_errors_to_schema_and_targets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            repo = Path(tmp_str)
            (repo / "scripts").mkdir(parents=True)
            (repo / "scripts" / "ticket_schema_check.py").write_text(
                "import json, sys\n"
                "print(json.dumps({'checked': 2, 'errors': 1, 'warnings': 0, 'rows': [\n"
                "    {'ticket': 'T234', 'errors': ['legacy repo vocabulary'], 'warnings': []}\n"
                "]}))\n",
                encoding="utf-8",
            )
            sdlc = {"session_wrapup": {"verification_gates": ["python3 -c \"import sys; sys.exit(0)\""]}}
            ok_res = sc.run_verification_gates(repo, sdlc, ["T640"])
            self.assertEqual(len(ok_res), 2)
            with self.assertRaises(sc.SessionCompleteError):
                sc.run_verification_gates(repo, sdlc, ["T234"])

    def test_archive_and_finalize_never_closes_caller_terminal_synchronously(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            canon = Path(tmp_str)
            (canon / "scripts").mkdir(parents=True)
            (canon / "scripts" / "orca_sessions.py").write_text("# stub\n", encoding="utf-8")

            ctx = sc.SessionContext(
                cwd=str(canon),
                worktree_root=str(canon),
                canonical_root=str(canon),
                work_root=str(canon / "work"),
                in_agent_tree=False,
                set_name=None,
                agent_id="agy:main",
                conversation_id="c2262ec5-a16b-40d2-8638-3f0995a1902b",
                agent_pid=2665,
                terminal_handle="term_live_caller_99",
                tab_id="tab_live_99",
                pane_key=None,
            )

            recorded_cmds: list[list[str]] = []

            def fake_run(cmd: list[str], *, cwd: Path, check: bool = False, timeout: float | None = None):
                recorded_cmds.append(list(cmd))
                return subprocess.CompletedProcess(cmd, 0, '{"ok": true, "collected": []}', "")

            with mock.patch.object(sc, "_run", side_effect=fake_run):
                res = sc.archive_and_finalize_session(
                    ctx,
                    close_completed_others=True,
                    close_self_when_settled=False,
                    skip_final_state_check=True,
                )

            self.assertTrue(res["archive"]["archived"])
            self.assertEqual(len(recorded_cmds), 2)
            arch_cmd, close_cmd = recorded_cmds
            self.assertIn("archive", arch_cmd)
            self.assertNotIn("--close-terminals", arch_cmd)
            self.assertIn("close-completed", close_cmd)
            self.assertIn("--exclude-handle", close_cmd)
            self.assertIn("term_live_caller_99", close_cmd)

    def test_estate_wiring_in_justfile_sdlc_json_and_test_suites(self) -> None:
        justfile_text = (ROOT / "justfile").read_text(encoding="utf-8")
        self.assertIn("session-complete *args:", justfile_text)
        self.assertIn("session-complete-test:", justfile_text)
        self.assertIn("scripts/session_complete.py", justfile_text)

        sdlc = json.loads((ROOT / ".w0m" / "sdlc.json").read_text(encoding="utf-8"))
        wrapup = sdlc.get("session_wrapup") or {}
        self.assertEqual(wrapup.get("command"), "just session-complete")
        self.assertEqual(wrapup.get("script"), "scripts/session_complete.py")
        gates = set(wrapup.get("verification_gates") or [])
        self.assertIn("just catalog-check", gates)
        self.assertIn("just skills-catalog-check", gates)

        suites = json.loads((ROOT / "w0m-web" / "project" / "test-suites.json").read_text(encoding="utf-8"))
        recipes = {s.get("recipe") for s in suites.get("suites", [])}
        self.assertIn("session-complete-test", recipes)

    def test_sync_tickets_to_github_full_sync_scope_degrade_and_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            wt = Path(tmp_str) / "w0m"
            (wt / "scripts").mkdir(parents=True)
            (wt / "scripts" / "sync_github.py").write_text("# stub\n", encoding="utf-8")

            # 1. Dry-run and skip make zero subprocess calls
            with mock.patch.object(sc, "_run") as m_none:
                self.assertEqual(
                    sc.sync_tickets_to_github(wt, ["T650"], dry_run=True)["mode"],
                    "dry_run",
                )
                self.assertEqual(
                    sc.sync_tickets_to_github(wt, ["T650"], skip=True)["mode"],
                    "skipped",
                )
                m_none.assert_not_called()

            # 2. Full sync happy path
            calls_ok: list[list[str]] = []

            def fake_ok(cmd: list[str], *, cwd: Path, check: bool = False, timeout: float | None = None):
                calls_ok.append(list(cmd))
                return subprocess.CompletedProcess(cmd, 0, "  T650 -> #650\n", "")

            with mock.patch.object(sc, "_run", side_effect=fake_ok):
                res_ok = sc.sync_tickets_to_github(wt, ["T650", "t651"])
            self.assertEqual(res_ok["mode"], "full_sync")
            self.assertEqual(res_ok["tickets"], ["T650", "T651"])
            self.assertEqual(len(calls_ok), 1)
            self.assertIn("--tickets", calls_ok[0])
            self.assertIn("T650,T651", calls_ok[0])

            # 3. Missing read:project scope retries once with --issues-only so GitHub Issues still close
            calls_deg: list[list[str]] = []

            def fake_missing_scope(cmd: list[str], *, cwd: Path, check: bool = False, timeout: float | None = None):
                calls_deg.append(list(cmd))
                if "--issues-only" not in cmd:
                    return subprocess.CompletedProcess(
                        cmd,
                        1,
                        "",
                        "FATAL: gh project list failed (missing required scopes [read:project])",
                    )
                return subprocess.CompletedProcess(cmd, 0, "  T650 -> #650\n", "")

            with mock.patch.object(sc, "_run", side_effect=fake_missing_scope):
                res_deg = sc.sync_tickets_to_github(wt, ["T650"])
            self.assertEqual(res_deg["mode"], "issues_only_missing_project_scope")
            self.assertEqual(len(calls_deg), 2)
            self.assertIn("--issues-only", calls_deg[1])

            # 4. Non-scope failure fails closed (AgDR-0025: zero silent fallbacks)
            def fake_hard_fail(cmd: list[str], *, cwd: Path, check: bool = False, timeout: float | None = None):
                return subprocess.CompletedProcess(cmd, 1, "", "FATAL: active gh account is 'wrong'")

            with mock.patch.object(sc, "_run", side_effect=fake_hard_fail):
                with self.assertRaises(sc.SessionCompleteError) as cm:
                    sc.sync_tickets_to_github(wt, ["T650"])
            self.assertEqual(cm.exception.step, "github_ticket_sync_failed")

    def test_refresh_canonical_graph_union_runs_auto_rebuild_stale_and_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            canon = Path(tmp_str) / "w0m"
            (canon / "scripts").mkdir(parents=True)

            # 1. Missing script skips cleanly
            self.assertEqual(
                sc.refresh_canonical_graph_union(canon),
                {"refreshed": False, "reason": "missing_graph_global_script"},
            )

            (canon / "scripts" / "graph_global.py").write_text("# stub\n", encoding="utf-8")

            # 2. Missing graphify binary skips cleanly
            with mock.patch.object(sc.shutil, "which", return_value=None):
                self.assertEqual(
                    sc.refresh_canonical_graph_union(canon),
                    {"refreshed": False, "reason": "graphify_absent"},
                )

            # 3. Invokes graph_global.py --root <canon> --auto-rebuild-stale
            recorded: list[list[str]] = []

            def fake_graph_ok(cmd: list[str], *, cwd: Path, check: bool = False, timeout: float | None = None):
                recorded.append(list(cmd))
                return subprocess.CompletedProcess(cmd, 0, "union refresh ok\n", "")

            with (
                mock.patch.object(sc.shutil, "which", return_value="/usr/bin/graphify"),
                mock.patch.object(sc, "_run", side_effect=fake_graph_ok),
            ):
                res = sc.refresh_canonical_graph_union(canon)
            self.assertTrue(res["refreshed"])
            self.assertEqual(len(recorded), 1)
            self.assertIn("--root", recorded[0])
            self.assertIn(str(canon), recorded[0])
            self.assertIn("--auto-rebuild-stale", recorded[0])

            # 4. Non-zero exit fails closed (AgDR-0025)
            def fake_graph_fail(cmd: list[str], *, cwd: Path, check: bool = False, timeout: float | None = None):
                return subprocess.CompletedProcess(cmd, 1, "", "🔴 failed: w0m-web")

            with (
                mock.patch.object(sc.shutil, "which", return_value="/usr/bin/graphify"),
                mock.patch.object(sc, "_run", side_effect=fake_graph_fail),
            ):
                with self.assertRaises(sc.SessionCompleteError) as cm_graph:
                    sc.refresh_canonical_graph_union(canon)
            self.assertEqual(cm_graph.exception.step, "graph_union_refresh_failed")

    def test_harvest_and_refresh_surfaces_runs_catalog_and_skills_catalog_generators(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            wt = Path(tmp_str) / "w0m"
            (wt / "scripts").mkdir(parents=True)
            (wt / "w0m-web" / "project" / "scripts").mkdir(parents=True)
            for rel in (
                "scripts/tickets_frontmatter_sync.py",
                "scripts/tasks_render.py",
                "scripts/decisions_index.py",
                "scripts/state_doctor.py",
                "w0m-web/project/scripts/catalog_sync.py",
                "w0m-web/project/scripts/skills_catalog_gen.py",
            ):
                (wt / rel).write_text("# stub\n", encoding="utf-8")

            recorded_cmds: list[list[str]] = []

            def fake_run(
                cmd: list[str],
                *,
                cwd: Path,
                check: bool = False,
                timeout: float | None = None,
            ) -> subprocess.CompletedProcess[str]:
                recorded_cmds.append(list(cmd))
                return subprocess.CompletedProcess(cmd, 0, "", "")

            with mock.patch.object(sc, "_run", side_effect=fake_run):
                res = sc.harvest_and_refresh_surfaces(wt, dry_run=False)

            self.assertIn("catalog_sync", res["refreshed"])
            self.assertIn("skills_catalog_gen", res["refreshed"])
            self.assertTrue(
                any(
                    str(wt / "w0m-web/project/scripts/catalog_sync.py") in cmd and "--write" in cmd
                    for cmd in recorded_cmds
                )
            )
            self.assertTrue(
                any(
                    str(wt / "w0m-web/project/scripts/skills_catalog_gen.py") in cmd and "--write" in cmd
                    for cmd in recorded_cmds
                )
            )

    def test_ticket_new_allocates_unique_ids_across_linked_git_worktrees_concurrently(self) -> None:
        from concurrent.futures import ThreadPoolExecutor
        import ticket_new as tn

        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            origin = tmp / "origin.git"
            _git_init_repo(origin, bare=True)

            canon = tmp / "canon" / "w0m"
            _git_init_repo(canon)
            subprocess.run(["git", "remote", "add", "origin", str(origin)], cwd=str(canon), check=True)
            (canon / ".tasks").mkdir(parents=True)
            (canon / ".tasks" / "T1.md").write_text("---\nid: T1\nstatus: done\n---\n", encoding="utf-8")
            subprocess.run(["git", "add", "-A"], cwd=str(canon), check=True)
            subprocess.run(["git", "commit", "-q", "-m", "chore(T1): seed"], cwd=str(canon), check=True)
            subprocess.run(["git", "push", "-q", "origin", "HEAD:beta"], cwd=str(canon), check=True)

            worktrees: list[Path] = []
            for name in ("set-a", "set-b", "set-c"):
                wt = tmp / "work" / name / "w0m"
                wt.parent.mkdir(parents=True)
                subprocess.run(
                    ["git", "worktree", "add", "-q", "-b", f"agent/{name}", str(wt), "origin/beta"],
                    cwd=str(canon),
                    check=True,
                )
                worktrees.append(wt)

            def alloc(idx_wt: tuple[int, Path]) -> str:
                idx, wt = idx_wt
                tid, _ = tn.allocate_ticket(
                    f"Parallel worktree ticket {idx}",
                    repo_dir=wt,
                    render_tasks=False,
                )
                return tid

            with ThreadPoolExecutor(max_workers=3) as pool:
                allocated = set(pool.map(alloc, list(enumerate(worktrees, start=1))))

            self.assertEqual(allocated, {"T2", "T3", "T4"})

            isolated = tmp / "isolated"
            _git_init_repo(isolated)
            iso_tid, _ = tn.allocate_ticket("Isolated standalone repo", repo_dir=isolated, render_tasks=False)
            self.assertEqual(iso_tid, "T1")

    def test_maybe_renumber_compacts_collisions_and_gaps_scrubs_gh_issue_and_supports_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            origin = tmp / "origin.git"
            _git_init_repo(origin, bare=True)

            seed = tmp / "seed"
            _git_init_repo(seed)
            subprocess.run(["git", "remote", "add", "origin", str(origin)], cwd=str(seed), check=True)
            (seed / ".w0m").mkdir()
            (seed / ".tasks").mkdir()
            (seed / ".w0m" / "sdlc.json").write_text('{"profile": "w0m"}\n', encoding="utf-8")
            (seed / ".tasks" / "T10.md").write_text("---\nid: T10\nstatus: done\n---\n", encoding="utf-8")
            subprocess.run(["git", "add", "-A"], cwd=str(seed), check=True)
            subprocess.run(["git", "commit", "-q", "-m", "chore(T10): seed"], cwd=str(seed), check=True)
            subprocess.run(["git", "push", "-q", "origin", "HEAD:beta"], cwd=str(seed), check=True)

            # 1. Collision + gh_issue scrub + --dry-run
            wt_b = tmp / "work" / "set-b" / "w0m"
            wt_b.parent.mkdir(parents=True)
            subprocess.run(["git", "fetch", "-q", "origin"], cwd=str(seed), check=True)
            subprocess.run(
                ["git", "worktree", "add", "-q", "-b", "agent/set-b", str(wt_b), "origin/beta"],
                cwd=str(seed),
                check=True,
            )
            t11_body = SAMPLE_TICKET_OPEN.replace("T42", "T11").replace("gh_issue:\n", "gh_issue: 11\n")
            (wt_b / ".tasks" / "T11.md").write_text(t11_body, encoding="utf-8")
            subprocess.run(["git", "add", "-A"], cwd=str(wt_b), check=True)
            subprocess.run(["git", "commit", "-q", "-m", "feat(T11): set-b local"], cwd=str(wt_b), check=True)

            # Advance origin/beta to T11
            (seed / ".tasks" / "T11.md").write_text("---\nid: T11\nstatus: done\n---\n", encoding="utf-8")
            subprocess.run(["git", "add", "-A"], cwd=str(seed), check=True)
            subprocess.run(["git", "commit", "-q", "-m", "feat(T11): landed first"], cwd=str(seed), check=True)
            subprocess.run(["git", "push", "-q", "origin", "HEAD:beta"], cwd=str(seed), check=True)

            with mock.patch.dict(os.environ, {"W0M_WORK_ROOT": str(tmp / "work")}, clear=False):
                rc_dry, summary_dry = sc.run_session_complete(
                    ["T11", "--set", "set-b", "--complete-acs", "--no-lessons", "--dry-run"]
                )
            self.assertEqual(rc_dry, 0)
            self.assertEqual(summary_dry["renumberedTickets"], {"T11": "T12"})
            self.assertEqual(summary_dry["targetTickets"], ["T12"])
            self.assertTrue((wt_b / ".tasks" / "T11.md").is_file())

            mapped_b, renames_b = sc.maybe_renumber_colliding_tickets(wt_b, ["T11"], dry_run=False)
            self.assertEqual(renames_b, {"T11": "T12"})
            self.assertEqual(mapped_b, ["T12"])
            t12_text = (wt_b / ".tasks" / "T12.md").read_text(encoding="utf-8")
            self.assertIn("gh_issue:\n", t12_text)
            self.assertNotIn("gh_issue: 11", t12_text)

            # 2. Early-finisher gap compaction: origin/beta is at T11, set-c holds unpushed T12,
            #    set-d finishes early with T13 -> compacts T13 -> T12 so landing leaves zero gap.
            wt_d = tmp / "work" / "set-d" / "w0m"
            wt_d.parent.mkdir(parents=True)
            subprocess.run(["git", "fetch", "-q", "origin"], cwd=str(seed), check=True)
            subprocess.run(
                ["git", "worktree", "add", "-q", "-b", "agent/set-d", str(wt_d), "origin/beta"],
                cwd=str(seed),
                check=True,
            )
            t13_body = SAMPLE_TICKET_OPEN.replace("T42", "T13").replace("gh_issue:\n", "gh_issue: 13\n")
            (wt_d / ".tasks" / "T13.md").write_text(t13_body, encoding="utf-8")
            subprocess.run(["git", "add", "-A"], cwd=str(wt_d), check=True)
            subprocess.run(["git", "commit", "-q", "-m", "feat(T13): early finisher"], cwd=str(wt_d), check=True)

            mapped_d, renames_d = sc.maybe_renumber_colliding_tickets(wt_d, ["T13"], dry_run=False)
            self.assertEqual(renames_d, {"T13": "T12"})
            self.assertEqual(mapped_d, ["T12"])
            self.assertFalse((wt_d / ".tasks" / "T13.md").exists())
            t12_d_text = (wt_d / ".tasks" / "T12.md").read_text(encoding="utf-8")
            self.assertIn("id: T12\n", t12_d_text)
            self.assertIn("gh_issue:\n", t12_d_text)
            self.assertNotIn("gh_issue: 13", t12_d_text)

    def test_session_complete_lock_serializes_callers_and_releases_on_process_exit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            lock_dir = Path(tmp_str)
            ready_file = lock_dir / "ready"
            holder_code = (
                "import sys, time\n"
                f"sys.path.insert(0, {str(SCRIPTS_DIR)!r})\n"
                "from pathlib import Path\n"
                "import session_complete as sc\n"
                f"with sc.session_complete_lock(Path({str(lock_dir)!r}), holder='set-a', timeout_seconds=5.0):\n"
                f"    Path({str(ready_file)!r}).write_text('ok', encoding='utf-8')\n"
                "    time.sleep(30.0)\n"
            )
            proc = subprocess.Popen([sys.executable, "-c", holder_code])
            try:
                deadline = sc.time.monotonic() + 5.0
                while not ready_file.is_file() and sc.time.monotonic() < deadline:
                    sc.time.sleep(0.02)
                self.assertTrue(ready_file.is_file())

                with self.assertRaises(sc.SessionCompleteError) as cm:
                    with sc.session_complete_lock(
                        lock_dir,
                        holder="set-b",
                        timeout_seconds=0.15,
                        poll_interval=0.05,
                    ):
                        pass
                self.assertEqual(cm.exception.step, "session_complete_lock_timeout")
            finally:
                proc.kill()
                proc.wait(timeout=5.0)

            # Kernel automatically releases flock on SIGKILL -> next caller acquires immediately
            with sc.session_complete_lock(lock_dir, holder="set-b", timeout_seconds=1.0, poll_interval=0.05):
                meta = json.loads((lock_dir / "w0m-session-complete.lock").read_text(encoding="utf-8"))
                self.assertEqual(meta["holder"], "set-b")

    def test_precertify_web_prepush_runs_local_hook_only_when_ahead_and_uncertified(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            origin_web = tmp / "w0m-web.git"
            _git_init_repo(origin_web, bare=True)

            wt = tmp / "w0m"
            web = wt / "w0m-web"
            _git_init_repo(web)
            subprocess.run(["git", "remote", "add", "origin", str(origin_web)], cwd=str(web), check=True)
            (web / ".husky").mkdir(parents=True)
            hook_marker = tmp / "hook_ran"
            (web / ".husky" / "pre-push").write_text(
                f"#!/bin/sh\nprintf 'ran' > {str(hook_marker)!r}\nexit 0\n",
                encoding="utf-8",
            )
            (web / "README.md").write_text("base\n", encoding="utf-8")
            subprocess.run(["git", "add", "-A"], cwd=str(web), check=True)
            subprocess.run(["git", "commit", "-q", "-m", "chore: base"], cwd=str(web), check=True)
            subprocess.run(["git", "push", "-q", "origin", "HEAD:beta"], cwd=str(web), check=True)

            # 1. Ahead == 0 -> skipped
            res_clean = sc.precertify_web_prepush(wt)
            self.assertEqual(res_clean["status"], "not_ahead")
            self.assertFalse(hook_marker.exists())

            # 2. Ahead > 0 -> executes .husky/pre-push locally before SSH push
            (web / "README.md").write_text("ahead\n", encoding="utf-8")
            subprocess.run(["git", "add", "-A"], cwd=str(web), check=True)
            subprocess.run(["git", "commit", "-q", "-m", "feat: ahead"], cwd=str(web), check=True)

            res_ran = sc.precertify_web_prepush(wt)
            self.assertEqual(res_ran["status"], "certified_locally")
            self.assertTrue(hook_marker.is_file())

    def test_deferred_draft_ticket_allocation_and_promotion_on_offload(self) -> None:
        import ticket_new as tn

        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            origin = tmp / "origin.git"
            _git_init_repo(origin, bare=True)

            seed = tmp / "seed"
            _git_init_repo(seed)
            subprocess.run(["git", "remote", "add", "origin", str(origin)], cwd=str(seed), check=True)
            (seed / ".w0m").mkdir()
            (seed / ".tasks").mkdir()
            (seed / ".agents" / "reports").mkdir(parents=True)
            (seed / ".w0m" / "sdlc.json").write_text('{"profile": "w0m"}\n', encoding="utf-8")
            (seed / "LESSONS.md").write_text("# Lessons\n\n- Base T11 rule.\n", encoding="utf-8")
            (seed / ".tasks" / "T11.md").write_text("---\nid: T11\nstatus: done\n---\n", encoding="utf-8")
            subprocess.run(["git", "add", "-A"], cwd=str(seed), check=True)
            subprocess.run(["git", "commit", "-q", "-m", "chore(T11): seed"], cwd=str(seed), check=True)
            subprocess.run(["git", "push", "-q", "origin", "HEAD:beta"], cwd=str(seed), check=True)

            wt = tmp / "work" / "my-feature" / "w0m"
            wt.parent.mkdir(parents=True)
            subprocess.run(["git", "fetch", "-q", "origin"], cwd=str(seed), check=True)
            subprocess.run(
                ["git", "worktree", "add", "-q", "-b", "agent/my-feature", str(wt), "origin/beta"],
                cwd=str(seed),
                check=True,
            )

            # 1. Allocate draft ticket without burning a sequential T## ID
            draft_tid, draft_path = tn.allocate_ticket(
                "Deferred ticket ID allocation",
                repo_dir=wt,
                render_tasks=False,
                draft_slug="my-feature",
            )
            self.assertEqual(draft_tid, "DRAFT-my-feature")
            self.assertEqual(draft_path.name, "DRAFT-my-feature.md")

            draft_body = SAMPLE_TICKET_OPEN.replace("T42", "DRAFT-my-feature")
            draft_path.write_text(draft_body, encoding="utf-8")
            (wt / ".agents" / "reports").mkdir(parents=True, exist_ok=True)
            (wt / ".agents" / "reports" / "2026-11-08-draft-my-feature-audit.md").write_text(
                "# DRAFT-my-feature Audit\n\nVerified draft-my-feature.\n",
                encoding="utf-8",
            )
            (wt / "LESSONS.md").write_text(
                "# Lessons\n\n- Base T11 rule.\n- Earned in DRAFT-my-feature: defer ID until offload.\n",
                encoding="utf-8",
            )

            # 2. Discover target tickets finds DRAFT-my-feature
            discovered = sc.discover_target_tickets(wt)
            self.assertEqual(discovered, ["DRAFT-my-feature"])

            # 3. Promote DRAFT-my-feature -> T12 on offload
            mapped, renames = sc.maybe_renumber_colliding_tickets(wt, discovered, dry_run=False)
            self.assertEqual(renames, {"DRAFT-my-feature": "T12"})
            self.assertEqual(mapped, ["T12"])
            self.assertFalse(draft_path.exists())
            promoted_path = wt / ".tasks" / "T12.md"
            self.assertTrue(promoted_path.is_file())
            self.assertIn("id: T12\n", promoted_path.read_text(encoding="utf-8"))
            promoted_report = wt / ".agents" / "reports" / "2026-11-08-t12-audit.md"
            self.assertTrue(promoted_report.is_file())
            self.assertIn("# T12 Audit", promoted_report.read_text(encoding="utf-8"))
            self.assertIn("Earned in T12: defer ID until offload.", (wt / "LESSONS.md").read_text(encoding="utf-8"))

    def test_maybe_resequence_colliding_and_out_of_order_migrations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            api_origin = tmp / "w0m-api-origin.git"
            _git_init_repo(api_origin, bare=True)

            api_seed = tmp / "w0m-api-seed"
            _git_init_repo(api_seed)
            subprocess.run(["git", "remote", "add", "origin", str(api_origin)], cwd=str(api_seed), check=True)
            mig_seed = api_seed / "supabase" / "migrations"
            mig_seed.mkdir(parents=True)
            (mig_seed / "20261108050000_base.sql").write_text("select 1;\n", encoding="utf-8")
            subprocess.run(["git", "add", "-A"], cwd=str(api_seed), check=True)
            subprocess.run(["git", "commit", "-q", "-m", "chore(T1): base mig"], cwd=str(api_seed), check=True)
            subprocess.run(["git", "push", "-q", "origin", "HEAD:beta"], cwd=str(api_seed), check=True)

            wt = tmp / "work" / "mig-feature" / "w0m"
            (wt / ".tasks").mkdir(parents=True)
            api_wt = wt / "w0m-api"
            subprocess.run(["git", "fetch", "-q", "origin"], cwd=str(api_seed), check=True)
            subprocess.run(
                ["git", "worktree", "add", "-q", "-b", "agent/mig-feature", str(api_wt), "origin/beta"],
                cwd=str(api_seed),
                check=True,
            )

            # Another agent lands 20261108080000_other.sql on origin/beta while our worktree created 20261108060000_ours.sql
            (mig_seed / "20261108080000_other.sql").write_text("select 2;\n", encoding="utf-8")
            subprocess.run(["git", "add", "-A"], cwd=str(api_seed), check=True)
            subprocess.run(["git", "commit", "-q", "-m", "feat(T2): other mig"], cwd=str(api_seed), check=True)
            subprocess.run(["git", "push", "-q", "origin", "HEAD:beta"], cwd=str(api_seed), check=True)

            (api_wt / "supabase" / "migrations" / "20261108060000_ours.sql").write_text("select 3;\n", encoding="utf-8")
            (wt / ".tasks" / "T3.md").write_text(
                "---\nid: T3\n---\n\nSee `20261108060000_ours.sql`.\n",
                encoding="utf-8",
            )

            renames = sc.maybe_resequence_colliding_migrations(wt, dry_run=False)
            self.assertEqual(renames, {"20261108060000_ours.sql": "20261108080001_ours.sql"})
            self.assertFalse((api_wt / "supabase" / "migrations" / "20261108060000_ours.sql").exists())
            self.assertTrue((api_wt / "supabase" / "migrations" / "20261108080001_ours.sql").is_file())
            self.assertIn("20261108080001_ours.sql", (wt / ".tasks" / "T3.md").read_text(encoding="utf-8"))

    def test_harvest_and_refresh_surfaces_tickets_only_skips_non_ticket_generators(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            wt = Path(tmp_str) / "w0m"
            (wt / "scripts").mkdir(parents=True)
            (wt / "w0m-web" / "project" / "scripts").mkdir(parents=True)
            for rel in (
                "scripts/lessons_query.py",
                "scripts/tickets_frontmatter_sync.py",
                "scripts/tasks_render.py",
                "scripts/decisions_index.py",
                "scripts/state_doctor.py",
                "w0m-web/project/scripts/catalog_sync.py",
                "w0m-web/project/scripts/skills_catalog_gen.py",
                "w0m-web/project/scripts/cp_feature_index.py",
            ):
                (wt / rel).write_text("# stub\n", encoding="utf-8")

            recorded_cmds: list[list[str]] = []

            def fake_run(
                cmd: list[str],
                *,
                cwd: Path,
                check: bool = False,
                timeout: float | None = None,
            ) -> subprocess.CompletedProcess[str]:
                recorded_cmds.append(list(cmd))
                return subprocess.CompletedProcess(cmd, 0, "", "")

            with mock.patch.object(sc, "_run", side_effect=fake_run):
                res = sc.harvest_and_refresh_surfaces(wt, dry_run=False, tickets_only=True)

            self.assertEqual(res["refreshed"], ["tickets_frontmatter_sync", "tasks_render", "state_doctor"])
            self.assertFalse(any("catalog_sync.py" in " ".join(c) for c in recorded_cmds))
            self.assertFalse(any("cp_feature_index.py" in " ".join(c) for c in recorded_cmds))

    def test_agent_tree_can_regenerate_web_derived_files(self) -> None:
        web_scripts = ROOT / "w0m-web" / "project" / "scripts"
        if str(web_scripts) not in sys.path:
            sys.path.insert(0, str(web_scripts))
        import agent_tree as at  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmp_str:
            web_dir = Path(tmp_str) / "w0m-web"
            (web_dir / "project" / "scripts").mkdir(parents=True)
            (web_dir / "project" / "scripts" / "codemap_gen.py").write_text("# stub\n", encoding="utf-8")
            (web_dir / "project" / "scripts" / "cp_feature_index.py").write_text("# stub\n", encoding="utf-8")

            self.assertTrue(
                at._can_regenerate_web_files(web_dir, ["docs/CODEMAP.md", "docs/CP-FEATURE-INDEX.md"])
            )
            self.assertFalse(
                at._can_regenerate_web_files(web_dir, ["docs/CODEMAP.md", "apps/cp/src/index.ts"])
            )

    def test_land_and_cleanup_tree_defers_graph_refresh_and_reuses_pre_land_cert(self) -> None:
        ctx = sc.SessionContext(
            cwd="/tmp/work/fast/w0m",
            worktree_root="/tmp/work/fast/w0m",
            canonical_root="/tmp/canon/w0m",
            work_root="/tmp/work",
            in_agent_tree=True,
            set_name="fast",
            agent_id="agy:fast",
            conversation_id=None,
            agent_pid=None,
            terminal_handle=None,
            tab_id=None,
            pane_key=None,
        )
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            wt = tmp / "work" / "fast" / "w0m"
            canon = tmp / "canon" / "w0m"
            (wt / "w0m-web" / "project" / "scripts").mkdir(parents=True)
            (canon / "w0m-web" / "project" / "scripts").mkdir(parents=True)
            (wt / "w0m-web" / "project" / "scripts" / "agent_tree.py").write_text("# stub\n", encoding="utf-8")
            (canon / "w0m-web" / "project" / "scripts" / "agent_tree.py").write_text("# stub\n", encoding="utf-8")
            ctx = sc.SessionContext(
                cwd=str(wt),
                worktree_root=str(wt),
                canonical_root=str(canon),
                work_root=str(tmp / "work"),
                in_agent_tree=True,
                set_name="fast",
                agent_id="agy:fast",
                conversation_id=None,
                agent_pid=None,
                terminal_handle=None,
                tab_id=None,
                pane_key=None,
            )
            orig_cwd = Path.cwd()
            try:
                with (
                    mock.patch.object(sc, "ensure_prepush_deps"),
                    mock.patch.object(sc, "precertify_web_prepush", return_value={"status": "already_certified"}),
                    mock.patch.object(sc, "_estate_head_shas", return_value={".": "abc123", "w0m-web": "def456"}),
                    mock.patch.object(
                        sc,
                        "_run",
                        return_value=subprocess.CompletedProcess(["land"], 0, "landed ok\n", ""),
                    ),
                    mock.patch.object(sc, "fast_forward_canonical_checkout", return_value={".": "fast_forwarded"}),
                    mock.patch.object(sc, "certify_estate_tree") as mock_cert,
                    mock.patch.object(sc, "refresh_canonical_graph_union") as mock_graph,
                ):
                    info = sc.land_and_cleanup_tree(
                        ctx,
                        remove_tree=False,
                        certify_after_land=True,
                        pre_land_certified=True,
                        defer_graph_refresh=True,
                    )
                mock_cert.assert_not_called()
                mock_graph.assert_not_called()
                self.assertEqual(info["graphUnionRefresh"], {"refreshed": False, "deferred": True})
                self.assertTrue(info["postLandCert"]["reusedPreLandCert"])
            finally:
                os.chdir(str(orig_cwd))

    def test_draft_disambiguation_and_post_commit_rollback_on_gate_failure(self) -> None:
        import ticket_new as tn

        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            origin = tmp / "origin.git"
            _git_init_repo(origin, bare=True)

            seed = tmp / "seed"
            _git_init_repo(seed)
            subprocess.run(["git", "remote", "add", "origin", str(origin)], cwd=str(seed), check=True)
            (seed / ".tasks").mkdir()
            (seed / ".tasks" / "T10.md").write_text("---\nid: T10\nstatus: done\n---\n", encoding="utf-8")
            (seed / "LESSONS.md").write_text("# Lessons\n\n- Base rule.\n", encoding="utf-8")
            subprocess.run(["git", "add", "-A"], cwd=str(seed), check=True)
            subprocess.run(["git", "commit", "-q", "-m", "chore(T10): seed"], cwd=str(seed), check=True)
            subprocess.run(["git", "push", "-q", "origin", "HEAD:beta"], cwd=str(seed), check=True)

            wt = tmp / "work" / "parallel-set" / "w0m"
            wt.parent.mkdir(parents=True)
            subprocess.run(["git", "fetch", "-q", "origin"], cwd=str(seed), check=True)
            subprocess.run(
                ["git", "worktree", "add", "-q", "-b", "agent/parallel-set", str(wt), "origin/beta"],
                cwd=str(seed),
                check=True,
            )

            # 1. Two draft allocations with the same worktree slug disambiguate cleanly
            d1, p1 = tn.allocate_ticket("First worktree task", repo_dir=wt, render_tasks=False, draft_slug="parallel-set")
            d2, p2 = tn.allocate_ticket("Second worktree task", repo_dir=wt, render_tasks=False, draft_slug="parallel-set")
            self.assertEqual(d1, "DRAFT-parallel-set")
            self.assertNotEqual(d1, d2)
            self.assertTrue(p1.is_file())
            self.assertTrue(p2.is_file())
            p2.unlink()

            # 2. If a gate fails after commit_dirty_repos, soft reset + rollback restores DRAFT-parallel-set.md
            mapped, renames = sc.maybe_renumber_colliding_tickets(wt, [d1], dry_run=False)
            self.assertEqual(renames, {"DRAFT-parallel-set": "T11"})
            self.assertEqual(mapped, ["T11"])
            (wt / "LESSONS.md").write_text("# Lessons\n\n- Base rule.\n- Earned in T11: test rollback.\n", encoding="utf-8")
            subprocess.run(["git", "add", "-A"], cwd=str(wt), check=True)
            subprocess.run(["git", "commit", "-q", "-m", "feat(T11): committed before cert failure"], cwd=str(wt), check=True)

            sc._soft_reset_worktree_to_merge_base(wt)
            sc._rollback_renumbered_tickets(wt, renames)
            self.assertFalse((wt / ".tasks" / "T11.md").exists())
            self.assertTrue((wt / ".tasks" / "DRAFT-parallel-set.md").is_file())
            self.assertIn("Earned in DRAFT-parallel-set:", (wt / "LESSONS.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
