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

        suites = json.loads((ROOT / "w0m-web" / "project" / "test-suites.json").read_text(encoding="utf-8"))
        recipes = {s.get("recipe") for s in suites.get("suites", [])}
        self.assertIn("session-complete-test", recipes)


if __name__ == "__main__":
    unittest.main()
