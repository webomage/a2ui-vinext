#!/usr/bin/env python3
"""T527 — state-check at root push, repointed w0m-web pre-push, hook scope probe, and ticket row check.

Verifies all 4 acceptance criteria of T527:
  - AC1: The root repo's push runs `state-check` when its range touches `STATE.md`, `TASKS.md`,
         `.tasks/`, or `ROADMAP.md`, and fails the push on drift.
         Red probe: a root push range that adds a ticket with no board row is refused.
  - AC2: `w0m-web/.husky/pre-push` step 17 (`state-check`) and ticket-sync trigger are repointed
         to `@wom` (`git -C ..`), contain no dead `project/tickets/` branch (AgDR-0025), and name
         the repo they inspect (`@wom`).
  - AC3: `hooks_check.check_hook_scope_paths` pins hook path scopes against the real repo layout
         and fails if a hook greps for paths that do not exist in the repo whose range it reads.
  - AC4: Creating/committing a ticket re-renders `TASKS.md` (or fails closed if a `.tasks/T*.md`
         lacks a `TASKS.md` row) via `scripts/ticket_row_check.py` wired in `@wom/.pre-commit-config.yaml`.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

MONO_ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = MONO_ROOT / "w0m-web"

sys.path.insert(0, str(MONO_ROOT / "scripts"))

import hooks_check as hc  # noqa: E402
import install_hooks as ih  # noqa: E402
import root_pre_push as rpp  # noqa: E402
import ticket_row_check as trc  # noqa: E402

GIT_ENV = {
    "GIT_AUTHOR_NAME": "Test Agent",
    "GIT_AUTHOR_EMAIL": "test@w0m.dev",
    "GIT_COMMITTER_NAME": "Test Agent",
    "GIT_COMMITTER_EMAIL": "test@w0m.dev",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
    "GIT_TERMINAL_PROMPT": "0",
    "LC_ALL": "C",
}


def run_git(repo: Path, *args: str, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, **GIT_ENV, **(extra_env or {})}
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        env=env,
    )


class TestT527StateCheckPush(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="t527-test-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

    def _init_root_repo_with_origin(self) -> tuple[Path, Path]:
        """Create a bare origin.git and a working root repo with scripts/root_pre_push.py + pre-push hook."""
        origin = self.tmp / "origin.git"
        repo = self.tmp / "w0m"
        subprocess.run(
            ["git", "init", "-q", "--bare", "-b", "beta", str(origin)],
            check=True,
            env={**os.environ, **GIT_ENV},
        )
        subprocess.run(
            ["git", "clone", "-q", str(origin), str(repo)],
            check=True,
            env={**os.environ, **GIT_ENV},
        )
        run_git(repo, "checkout", "-q", "-b", "beta")

        # Copy root_pre_push.py, ticket_row_check.py, tasks_render.py into the fixture root repo
        scripts_dir = repo / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        for name in ("root_pre_push.py", "ticket_row_check.py", "tasks_render.py"):
            shutil.copy2(MONO_ROOT / "scripts" / name, scripts_dir / name)

        # Seed initial ticket T1 and TASKS.md with row for T1
        tasks_dir = repo / ".tasks"
        tasks_dir.mkdir(parents=True, exist_ok=True)
        (tasks_dir / "T1.md").write_text(
            "---\nid: T1\ntitle: \"Initial ticket\"\nstatus: queued\npriority: P2\nrepos: [tooling]\n---\n\n# T1\n",
            encoding="utf-8",
        )
        (repo / "TASKS.md").write_text(
            "# w0m — Task Queue\n\n## QUEUED & BACKLOG\n\n| # | Prio | Task | Repos | Ref | Status |\n"
            "|---|------|------|-------|-----|--------|\n"
            "| [T1](.tasks/T1.md) | **P2** | 🆕 **Initial ticket** | tooling | — | ⚪ **queued** |\n",
            encoding="utf-8",
        )
        (repo / "STATE.md").write_text("# STATE\n", encoding="utf-8")
        (repo / "ROADMAP.md").write_text("# ROADMAP\n", encoding="utf-8")
        (repo / "README.md").write_text("# w0m\n", encoding="utf-8")

        run_git(repo, "add", "-A")
        run_git(repo, "commit", "-q", "-m", "chore: initial root seed")
        run_git(repo, "push", "-q", "origin", "beta")

        # Install the root pre-push hook via install_hooks.ensure_root_pre_push
        note = ih.ensure_root_pre_push(repo)
        self.assertIn("pre-push", note)
        self.assertTrue((repo / ".git" / "hooks" / "pre-push").is_file())
        return origin, repo

    # ── AC1 ───────────────────────────────────────────────────────────────────────

    def test_ac1_red_probe_root_push_adding_ticket_without_board_row_is_refused(self) -> None:
        """AC1 red probe: a root push range that adds .tasks/T525.md with no TASKS.md row is refused."""
        origin, repo = self._init_root_repo_with_origin()
        before_origin_sha = run_git(origin, "rev-parse", "beta").stdout.strip()

        # Add T525 without updating TASKS.md
        (repo / ".tasks" / "T525.md").write_text(
            "---\nid: T525\ntitle: \"Rowless ticket\"\nstatus: queued\npriority: P2\nrepos: [tooling]\n---\n\n# T525\n",
            encoding="utf-8",
        )
        run_git(repo, "add", ".tasks/T525.md")
        run_git(repo, "commit", "-q", "-m", "feat(sdlc): add T525 without TASKS.md row")

        push_res = run_git(
            repo,
            "push",
            "origin",
            "beta",
            extra_env={"W0M_STATE_CHECK_CMD": "true"},
        )
        combined = push_res.stdout + push_res.stderr
        self.assertNotEqual(push_res.returncode, 0, f"Expected push to fail, got 0: {combined}")
        self.assertIn("T525", combined)
        self.assertIn("newly invisible", combined)

        # Remote origin/beta must not have moved
        after_origin_sha = run_git(origin, "rev-parse", "beta").stdout.strip()
        self.assertEqual(before_origin_sha, after_origin_sha)

    def test_ac1_root_push_fails_when_state_check_fails_on_tracking_surface_change(self) -> None:
        """AC1: touching STATE.md, TASKS.md, .tasks/ or ROADMAP.md runs state-check and blocks on drift."""
        origin, repo = self._init_root_repo_with_origin()
        before_origin_sha = run_git(origin, "rev-parse", "beta").stdout.strip()

        (repo / "ROADMAP.md").write_text("# ROADMAP\n\n## §13.7 gate-integrity\n", encoding="utf-8")
        run_git(repo, "add", "ROADMAP.md")
        run_git(repo, "commit", "-q", "-m", "docs(roadmap): update section")

        # Simulate state-check detecting drift (exit 1)
        push_fail = run_git(
            repo,
            "push",
            "origin",
            "beta",
            extra_env={"W0M_STATE_CHECK_CMD": "echo 'STATE.md drifted' >&2; exit 1"},
        )
        self.assertNotEqual(push_fail.returncode, 0)
        self.assertIn("state-check failed", push_fail.stdout + push_fail.stderr)
        self.assertEqual(run_git(origin, "rev-parse", "beta").stdout.strip(), before_origin_sha)

        # Once state-check passes (exit 0), the push succeeds
        push_ok = run_git(
            repo,
            "push",
            "origin",
            "beta",
            extra_env={"W0M_STATE_CHECK_CMD": "true"},
        )
        self.assertEqual(push_ok.returncode, 0, push_ok.stdout + push_ok.stderr)
        self.assertNotEqual(run_git(origin, "rev-parse", "beta").stdout.strip(), before_origin_sha)

    def test_ac1_root_push_skips_state_check_when_tracking_surfaces_untouched(self) -> None:
        """AC1: pushing root changes that do not touch STATE.md/TASKS.md/.tasks//ROADMAP.md skips state-check."""
        _origin, repo = self._init_root_repo_with_origin()
        (repo / "README.md").write_text("# w0m updated\n", encoding="utf-8")
        run_git(repo, "add", "README.md")
        run_git(repo, "commit", "-q", "-m", "docs: update README")

        # Even if W0M_STATE_CHECK_CMD would fail, it must not be invoked when tracking surfaces are untouched
        push_res = run_git(
            repo,
            "push",
            "origin",
            "beta",
            extra_env={"W0M_STATE_CHECK_CMD": "exit 1"},
        )
        combined = push_res.stdout + push_res.stderr
        self.assertEqual(push_res.returncode, 0, combined)
        self.assertIn("tracking surfaces untouched in push range; state-check skipped", combined)

    # ── AC2 ───────────────────────────────────────────────────────────────────────

    def test_ac2_w0m_web_pre_push_repointed_to_root_and_no_dead_project_tickets_branch(self) -> None:
        """AC2: w0m-web/.husky/pre-push has no dead project/tickets/ branch and names @wom (`git -C ..`)."""
        pre_push_text = (WEB_ROOT / ".husky" / "pre-push").read_text(encoding="utf-8")

        # No dead `project/tickets/` branch anywhere in w0m-web/.husky/pre-push (AgDR-0025)
        self.assertNotIn("project/tickets", pre_push_text)

        # Step 17 (`state-check`) explicitly inspects `..` (@wom root repo) and names `@wom`
        idx = pre_push_text.index('step_begin "state-check"')
        step_block = pre_push_text[idx : idx + 1500]
        self.assertIn("git -C .. diff --name-only", step_block)
        self.assertIn("@wom", step_block)
        self.assertIn("^(STATE\\.md|TASKS\\.md|\\.tasks/|ROADMAP\\.md)", step_block)

        # T652 / T651: fallback branch inspects `git -C .. diff --name-only "origin/beta" HEAD` and
        # ticket mirroring runs foreground in `just session-complete` (never detached `nohup`)
        self.assertIn('git -C .. diff --name-only "origin/beta" HEAD', step_block)
        self.assertIn("just session-complete", pre_push_text)
        exec_lines = "\n".join(
            ln for ln in pre_push_text.splitlines() if not ln.lstrip().startswith("#")
        )
        self.assertNotIn("nohup", exec_lines)

    # ── AC3 ───────────────────────────────────────────────────────────────────────

    def test_ac3_hooks_check_pins_scope_against_real_layout(self) -> None:
        """AC3: hooks_check passes on the real estate and fails when a hook greps for a non-existent path."""
        # Real estate has 0 scope-path findings
        real_findings = hc.check_hook_scope_paths(MONO_ROOT)
        self.assertEqual(real_findings, [], f"Unexpected findings on real estate: {real_findings}")

        # Red probe 1: w0m-web/.husky/pre-push grepping w0m-web's own diff for project/tickets/
        fx_web = self.tmp / "fx_web"
        (fx_web / "w0m-web" / ".husky").mkdir(parents=True, exist_ok=True)
        (fx_web / "w0m-web" / ".husky" / "pre-push").write_text(
            "#!/bin/sh\n"
            '_pushed_files=$(git diff --name-only "origin/$_branch" HEAD)\n'
            'if echo "$_pushed_files" | grep -qE "^(STATE\\.md|TASKS\\.md|project/tickets/|\\.tasks/|ROADMAP\\.md)"; then\n'
            "  just state-check\n"
            "fi\n",
            encoding="utf-8",
        )
        findings_1 = hc.check_hook_scope_paths(fx_web)
        self.assertTrue(
            any("project/tickets" in f and "w0m-web" in f for f in findings_1),
            f"Expected project/tickets finding in w0m-web, got: {findings_1}",
        )

        # Red probe 2: pre-commit files: filter targeting ^project/tickets/ in w0m-web
        fx_pc = self.tmp / "fx_pc"
        (fx_pc / "w0m-web").mkdir(parents=True, exist_ok=True)
        (fx_pc / "w0m-web" / ".pre-commit-config.yaml").write_text(
            "repos:\n"
            "  - repo: local\n"
            "    hooks:\n"
            "      - id: tickets-frontmatter\n"
            "        name: tickets\n"
            "        entry: echo ok\n"
            "        language: system\n"
            "        files: ^project/tickets/T\\d+\\.md$\n",
            encoding="utf-8",
        )
        findings_2 = hc.check_hook_scope_paths(fx_pc)
        self.assertTrue(
            any("project/tickets" in f and "w0m-web" in f for f in findings_2),
            f"Expected pre-commit scope finding, got: {findings_2}",
        )

        # Green probe: w0m-web/.husky/pre-push using `git -C .. diff` when @wom has the tracking surfaces
        (fx_web / "STATE.md").write_text("# STATE\n", encoding="utf-8")
        (fx_web / "TASKS.md").write_text("# TASKS\n", encoding="utf-8")
        (fx_web / ".tasks").mkdir(parents=True, exist_ok=True)
        (fx_web / "ROADMAP.md").write_text("# ROADMAP\n", encoding="utf-8")
        (fx_web / "w0m-web" / ".husky" / "pre-push").write_text(
            "#!/bin/sh\n"
            '_pushed_files=$(git -C .. diff --name-only "origin/$_branch" HEAD)\n'
            'if echo "$_pushed_files" | grep -qE "^(STATE\\.md|TASKS\\.md|\\.tasks/|ROADMAP\\.md)"; then\n'
            "  just state-check\n"
            "fi\n",
            encoding="utf-8",
        )
        self.assertEqual(hc.check_hook_scope_paths(fx_web), [])

    # ── AC4 ───────────────────────────────────────────────────────────────────────

    def test_ac4_ticket_row_check_wired_in_root_pre_commit_and_renders_or_refuses(self) -> None:
        """AC4: @wom/.pre-commit-config.yaml wires ticket-row-check, which auto-renders TASKS.md or fails closed."""
        root_pc = (MONO_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
        self.assertIn("id: ticket-row-check", root_pc)
        self.assertIn("python3 scripts/ticket_row_check.py", root_pc)

        _origin, repo = self._init_root_repo_with_origin()
        (repo / ".tasks" / "T2.md").write_text(
            "---\nid: T2\ntitle: \"New ticket\"\nstatus: queued\npriority: P1\nrepos: [tooling]\n---\n\n# T2\n",
            encoding="utf-8",
        )

        # 1. Verify-only (--check) refuses when T2 has no row in TASKS.md
        rc_check = trc.main(["--check", "--root", str(repo)])
        self.assertEqual(rc_check, 1)

        # 2. Pre-commit mode auto-runs tasks_render.py, adds row for T2 to TASKS.md, and stages TASKS.md
        rc_fix = trc.main(["--root", str(repo)])
        self.assertEqual(rc_fix, 0)
        tasks_md_text = (repo / "TASKS.md").read_text(encoding="utf-8")
        self.assertIsNotNone(re.search(r"^\|\s*\[T2\]\(\.tasks/T2\.md\)", tasks_md_text, re.M))

        staged = run_git(repo, "diff", "--cached", "--name-only").stdout.splitlines()
        self.assertIn("TASKS.md", staged)

    # ── T657 AC4 ──────────────────────────────────────────────────────────────────

    def test_t657_root_push_runs_catalog_check_on_catalog_inputs_and_blocks_drift(self) -> None:
        """T657 AC4: touching .w0m/skills.json, .w0m/sdlc.json, stacks-policy.json, or catalog-info.yaml gates push on catalog-check."""
        origin, repo = self._init_root_repo_with_origin()
        before_origin_sha = run_git(origin, "rev-parse", "beta").stdout.strip()

        (repo / ".w0m").mkdir(parents=True, exist_ok=True)
        (repo / ".w0m" / "skills.json").write_text('{"skills": {}}\n', encoding="utf-8")
        run_git(repo, "add", ".w0m/skills.json")
        run_git(repo, "commit", "-q", "-m", "chore(skills): bump observed_version")

        # 1. Red probe: catalog-check failure blocks @wom push
        push_fail = run_git(
            repo,
            "push",
            "origin",
            "beta",
            extra_env={"W0M_CATALOG_CHECK_CMD": "echo 'Catalog YAML drift detected' >&2; exit 1"},
        )
        self.assertNotEqual(push_fail.returncode, 0)
        self.assertIn("catalog-check failed", push_fail.stdout + push_fail.stderr)
        self.assertEqual(run_git(origin, "rev-parse", "beta").stdout.strip(), before_origin_sha)

        # 2. Clean catalog-check allows @wom push
        push_ok = run_git(
            repo,
            "push",
            "origin",
            "beta",
            extra_env={"W0M_CATALOG_CHECK_CMD": "true"},
        )
        self.assertEqual(push_ok.returncode, 0, push_ok.stdout + push_ok.stderr)
        after_sha = run_git(origin, "rev-parse", "beta").stdout.strip()
        self.assertNotEqual(after_sha, before_origin_sha)

        # 3. Unrelated commit skips catalog-check even if W0M_CATALOG_CHECK_CMD would fail
        (repo / "README.md").write_text("# w0m docs only\n", encoding="utf-8")
        run_git(repo, "add", "README.md")
        run_git(repo, "commit", "-q", "-m", "docs: readme tweak")
        push_skip = run_git(
            repo,
            "push",
            "origin",
            "beta",
            extra_env={"W0M_CATALOG_CHECK_CMD": "exit 1"},
        )
        self.assertEqual(push_skip.returncode, 0, push_skip.stdout + push_skip.stderr)

        # 4. Red probe for hooks_check on CATALOG_SCOPE_RE referencing non-existent path
        fx_cat = self.tmp / "fx_cat"
        (fx_cat / "scripts").mkdir(parents=True, exist_ok=True)
        (fx_cat / "scripts" / "root_pre_push.py").write_text(
            'CATALOG_SCOPE_RE = re.compile(r"^(nonexistent/catalog-policy\\.json)$")\n',
            encoding="utf-8",
        )
        findings_cat = hc.check_hook_scope_paths(fx_cat)
        self.assertTrue(
            any("nonexistent/catalog-policy.json" in f for f in findings_cat),
            f"Expected hooks_check finding on stale CATALOG_SCOPE_RE, got: {findings_cat}",
        )


if __name__ == "__main__":
    unittest.main()
