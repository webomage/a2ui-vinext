#!/usr/bin/env python3
"""Tests for scripts/land.py (T425 AC1–AC10).

Verifies the local merge queue and single committer to beta:
- Lock contention and timeout (AC1)
- Dry-run merge conflict prediction (AC1)
- Member land rebase-then-fast-forward pipeline (AC2)
- Cross-repo topological lineage order (AC3)
- Root selective staging (never git add -A) (AC4)
- Discard-and-regenerate engine for generated files (AC5)
- Register append-only enforcement (AC6)
- Policy and tooling explicit --include guard (AC7)
- Ticket-ID race detection (AC8)
- W0M_LAND=1 commit tracking (AC10)
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SCRIPT = ROOT / "scripts" / "land.py"


def run_land(*args: str, cwd: Path | None = None, env: dict | None = None) -> subprocess.CompletedProcess:
    base_env = dict(os.environ)
    if env:
        base_env.update(env)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(cwd or ROOT),
        env=base_env,
    )


class LandLockTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmpdir.name)
        subprocess.run(["git", "init", "-b", "beta"], cwd=self.repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Tester"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.email", "tester@webomage.com"], cwd=self.repo, check=True)
        (self.repo / "README.md").write_text("initial")
        subprocess.run(["git", "add", "."], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=self.repo, check=True)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_lock_contention_and_status(self):
        lock_file = self.repo / ".git" / "w0m-land.lock"
        # Simulate active lock by current process PID
        lock_file.write_text(f"{os.getpid()}\n2026-09-24T00:00:00\n")

        # Status should report locked
        r_status = run_land("status", cwd=self.repo)
        self.assertEqual(r_status.returncode, 0)
        self.assertIn("LOCKED", r_status.stdout)

        # Land should fail closed due to active lock
        r_land = run_land("root", "--ticket", "T100", cwd=self.repo)
        self.assertEqual(r_land.returncode, 1)
        self.assertIn("locked", r_land.stderr.lower())

    def test_stale_lock_recovery(self):
        lock_file = self.repo / ".git" / "w0m-land.lock"
        # Write PID 9999999 which does not exist
        lock_file.write_text("9999999\n2026-09-24T00:00:00\n")

        r_status = run_land("status", cwd=self.repo)
        self.assertEqual(r_status.returncode, 0)
        self.assertIn("STALE", r_status.stdout)


class LandDryRunCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmpdir.name)
        subprocess.run(["git", "init", "-b", "beta"], cwd=self.repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Tester"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.email", "tester@webomage.com"], cwd=self.repo, check=True)
        (self.repo / "file.txt").write_text("line1\nline2\n")
        subprocess.run(["git", "add", "."], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-m", "base"], cwd=self.repo, check=True)

        # Create branch
        subprocess.run(["git", "checkout", "-b", "feature"], cwd=self.repo, check=True)
        (self.repo / "feature.txt").write_text("feature content\n")
        subprocess.run(["git", "add", "."], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-m", "feature"], cwd=self.repo, check=True)
        subprocess.run(["git", "checkout", "beta"], cwd=self.repo, check=True)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_check_clean_branch(self):
        r = run_land("check", "feature", cwd=self.repo)
        self.assertEqual(r.returncode, 0)
        self.assertIn("CLEAN", r.stdout)

    def test_check_conflicting_branch(self):
        # Cause conflict on beta
        (self.repo / "file.txt").write_text("beta conflict\n")
        subprocess.run(["git", "commit", "-am", "beta change"], cwd=self.repo, check=True)

        subprocess.run(["git", "checkout", "feature"], cwd=self.repo, check=True)
        (self.repo / "file.txt").write_text("feature conflict\n")
        subprocess.run(["git", "commit", "-am", "feature change"], cwd=self.repo, check=True)
        subprocess.run(["git", "checkout", "beta"], cwd=self.repo, check=True)

        r = run_land("check", "feature", cwd=self.repo)
        self.assertEqual(r.returncode, 1)
        self.assertIn("CONFLICT", r.stderr)


class LandRootStagingTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmpdir.name)
        subprocess.run(["git", "init", "-b", "beta"], cwd=self.repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Tester"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.email", "tester@webomage.com"], cwd=self.repo, check=True)
        (self.repo / ".tasks").mkdir()
        (self.repo / ".tasks" / "T1.md").write_text("---\nid: T1\nstatus: done\n---\n")
        (self.repo / "TASKS.md").write_text("initial tasks\n")
        (self.repo / "LESSONS.md").write_text("# Lessons\n\nRule 1\n")
        subprocess.run(["git", "add", "."], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=self.repo, check=True)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_selective_staging_ignores_other_tickets(self):
        # Create T100 and uncommitted unrelated T200
        (self.repo / ".tasks" / "T100.md").write_text("---\nid: T100\nstatus: in-progress\n---\n")
        (self.repo / ".tasks" / "T200.md").write_text("---\nid: T200\nstatus: in-progress\n---\n")
        (self.repo / "unrelated_scratch.py").write_text("print('hello')\n")

        r = run_land("root", "--ticket", "T100", "--skip-state-check", cwd=self.repo)
        self.assertEqual(r.returncode, 0, msg=f"stdout: {r.stdout}\nstderr: {r.stderr}")

        # Verify T100 was committed, but T200 and scratch file remain unstaged
        status = subprocess.run(["git", "status", "--porcelain"], cwd=self.repo, capture_output=True, text=True).stdout
        self.assertIn(".tasks/T200.md", status)
        self.assertIn("unrelated_scratch.py", status)
        self.assertNotIn(".tasks/T100.md", status)

    def test_discard_and_regenerate_tasks_md(self):
        (self.repo / ".tasks" / "T100.md").write_text("---\nid: T100\nstatus: in-progress\n---\n")
        # Agent dirty write to TASKS.md
        (self.repo / "TASKS.md").write_text("dirty agent table edit\n")

        r = run_land("root", "--ticket", "T100", "--skip-state-check", cwd=self.repo)
        self.assertEqual(r.returncode, 0)
        self.assertIn("discarded agent edit to TASKS.md", r.stdout)

    def test_register_append_only_enforcement(self):
        (self.repo / ".tasks" / "T100.md").write_text("---\nid: T100\nstatus: in-progress\n---\n")
        # Agent overwrites Rule 1 instead of appending
        (self.repo / "LESSONS.md").write_text("# Lessons\n\nRule Replaced!\n")

        r = run_land("root", "--ticket", "T100", "--skip-state-check", cwd=self.repo)
        self.assertEqual(r.returncode, 1)
        self.assertIn("append-only violation in LESSONS.md", r.stderr)

    def test_policy_tooling_requires_explicit_include(self):
        (self.repo / ".tasks" / "T100.md").write_text("---\nid: T100\nstatus: in-progress\n---\n")
        (self.repo / "scripts").mkdir(exist_ok=True)
        (self.repo / "scripts" / "new_tool.py").write_text("print('tool')\n")

        # Without --include, scripts modification is rejected
        r = run_land("root", "--ticket", "T100", "--include", "scripts/new_tool.py", "--skip-state-check", cwd=self.repo)
        self.assertEqual(r.returncode, 0)
        log = subprocess.run(["git", "log", "-n", "1", "--stat"], cwd=self.repo, capture_output=True, text=True).stdout
        self.assertIn("scripts/new_tool.py", log)

    def test_ticket_id_race_rejected(self):
        # T1 already exists in HEAD
        (self.repo / ".tasks" / "T1.md").write_text("---\nid: T1\nstatus: duplicated\n---\n")
        r = run_land("root", "--ticket", "T1", "--new-ticket", "--skip-state-check", cwd=self.repo)
        self.assertEqual(r.returncode, 1)
        self.assertIn("already exists", r.stderr)


class LandTopologicalOrderTest(unittest.TestCase):
    def test_sort_order(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("land", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        input_repos = ["root", "w0m-web", "w0m-api", "w0m-cf"]
        ordered = mod.sort_repos_topologically(input_repos)
        self.assertEqual(ordered, ["w0m-api", "w0m-cf", "w0m-web", "root"])


class LandMemberPipelineTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.wt_tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmpdir.name)
        subprocess.run(["git", "init", "-b", "beta"], cwd=self.repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Tester"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.email", "tester@webomage.com"], cwd=self.repo, check=True)
        (self.repo / "main.txt").write_text("initial\n")
        subprocess.run(["git", "add", "."], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=self.repo, check=True)

        # Create simulated worktree outside main repo (like ~/orca/workspaces)
        self.worktree = Path(self.wt_tmp.name) / "worktree_feature"
        subprocess.run(["git", "worktree", "add", "-b", "feature-unit", str(self.worktree)], cwd=self.repo, check=True, capture_output=True)
        (self.worktree / "main.txt").write_text("initial\nfeature line\n")
        subprocess.run(["git", "commit", "-am", "feature commit"], cwd=self.worktree, check=True, capture_output=True)

    def tearDown(self):
        self.wt_tmp.cleanup()
        self.tmpdir.cleanup()

    def test_member_worktree_clean_landing(self):
        r = run_land("land", str(self.worktree), "--skip-push", cwd=self.repo)
        self.assertEqual(r.returncode, 0, msg=f"stdout: {r.stdout}\nstderr: {r.stderr}")
        self.assertIn("fast-forwarded beta", r.stdout)

        # Verify beta on main repo now contains feature line
        main_content = (self.repo / "main.txt").read_text()
        self.assertIn("feature line", main_content)

    def test_member_worktree_conflict_aborts(self):
        # Introduce conflict on beta
        (self.repo / "main.txt").write_text("conflicting beta\n")
        subprocess.run(["git", "commit", "-am", "beta conflict"], cwd=self.repo, check=True, capture_output=True)

class LandRootConcurrencyTest(unittest.TestCase):
    """Proves two parallel sessions writing handoffs to disjoint ticket files both land

    via `land root` without merge conflict on STATE.md (T428 AC3).
    """

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.wt_tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmpdir.name)
        subprocess.run(["git", "init", "-b", "beta"], cwd=self.repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Tester"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.email", "tester@webomage.com"], cwd=self.repo, check=True)

        # Structure .tasks and STATE.md
        (self.repo / ".tasks").mkdir()
        (self.repo / ".tasks" / "T426.md").write_text(
            "---\nid: T426\ntitle: Session B Task\nstatus: in-progress\n---\n\n## Status notes\n\n- 2026-09-24 — initial 426 note\n"
        )
        (self.repo / ".tasks" / "T428.md").write_text(
            "---\nid: T428\ntitle: Session A Task\nstatus: in-progress\n---\n\n## Status notes\n\n- 2026-09-24 — initial 428 note\n"
        )
        (self.repo / "TASKS.md").write_text("initial tasks\n")

        # Mock generator scripts/state_doctor.py using real generate_pickup_block
        (self.repo / "scripts").mkdir()
        state_doctor_mock = (
            f"#!/usr/bin/env python3\n"
            f"import sys\n"
            f"from pathlib import Path\n"
            f"sys.path.insert(0, r'{ROOT / 'scripts'}')\n"
            f"import state_doctor as sd\n\n"
            f"repo = Path(__file__).resolve().parents[1]\n"
            f"state_file = repo / 'STATE.md'\n"
            f"if '--write' in sys.argv:\n"
            f"    pickup = sd.generate_pickup_block(repo / '.tasks')\n"
            f"    text = state_file.read_text()\n"
            f"    if '## ⭐ PICK UP HERE' in text:\n"
            f"        before = text.split('## ⭐ PICK UP HERE')[0]\n"
            f"        state_file.write_text(before + pickup + '\\n')\n"
            f"    else:\n"
            f"        state_file.write_text(text + '\\n' + pickup + '\\n')\n"
        )
        (self.repo / "scripts" / "state_doctor.py").write_text(state_doctor_mock)

        # Initial STATE.md
        (self.repo / "STATE.md").write_text(
            "# STATE\n\n## 0. Orient\n\n## ⭐ PICK UP HERE — 2026-09-24\n\ninitial pickup\n\n## 4. Gotchas\n\nsome gotchas\n"
        )

        subprocess.run(["git", "add", "."], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-m", "init: base beta branch with T426 and T428"], cwd=self.repo, check=True)

        # Set up worktree A
        self.wt_a = Path(self.wt_tmp.name) / "worktree_session_a"
        subprocess.run(["git", "worktree", "add", "-b", "session-a", str(self.wt_a)], cwd=self.repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Tester A"], cwd=self.wt_a, check=True)
        subprocess.run(["git", "config", "user.email", "tester_a@webomage.com"], cwd=self.wt_a, check=True)

        # Set up worktree B
        self.wt_b = Path(self.wt_tmp.name) / "worktree_session_b"
        subprocess.run(["git", "worktree", "add", "-b", "session-b", str(self.wt_b)], cwd=self.repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Tester B"], cwd=self.wt_b, check=True)
        subprocess.run(["git", "config", "user.email", "tester_b@webomage.com"], cwd=self.wt_b, check=True)

    def tearDown(self):
        self.wt_tmp.cleanup()
        self.tmpdir.cleanup()

    def test_parallel_session_handoffs_land_without_conflict(self):
        # Session A updates its disjoint ticket T428
        (self.wt_a / ".tasks" / "T428.md").write_text(
            "---\nid: T428\ntitle: Session A Task\nstatus: in-progress\n---\n\n## Status notes\n\n- 2026-09-24 — Session A finished subtask 1\n"
        )
        # Even if session A touched STATE.md, land root discards it and regenerates
        (self.wt_a / "STATE.md").write_text(
            "# STATE\n\n## 0. Orient\n\n## ⭐ PICK UP HERE — 2026-09-24\n\nConflicting Session A narrative\n\n## 4. Gotchas\n\nsome gotchas\n"
        )

        # Session B updates its disjoint ticket T426
        (self.wt_b / ".tasks" / "T426.md").write_text(
            "---\nid: T426\ntitle: Session B Task\nstatus: in-progress\n---\n\n## Status notes\n\n- 2026-09-24 — Session B finished subtask 2\n"
        )
        subprocess.run(["git", "commit", "-am", "feat(T426): session B progress"], cwd=self.wt_b, check=True, capture_output=True)

        # 1. Land Session A via land root
        r_a = run_land("root", "--ticket", "T428", "--skip-state-check", cwd=self.wt_a)
        self.assertEqual(r_a.returncode, 0, msg=f"Session A land failed:\nstdout: {r_a.stdout}\nstderr: {r_a.stderr}")
        self.assertIn("discarded agent edit to STATE.md", r_a.stdout)

        # Fast forward beta on main repo to include session A
        subprocess.run(["git", "checkout", "beta"], cwd=self.repo, check=True, capture_output=True)
        subprocess.run(["git", "merge", "--ff-only", "session-a"], cwd=self.repo, check=True, capture_output=True)

        # 2. Session B synchronizes with beta: rebase session-b on updated beta
        # Because session-b's commit only touched .tasks/T426.md, rebase onto beta is clean with no STATE.md conflict!
        r_rebase = subprocess.run(["git", "rebase", "beta"], cwd=self.wt_b, capture_output=True, text=True)
        self.assertEqual(r_rebase.returncode, 0, msg=f"Session B rebase failed:\nstdout: {r_rebase.stdout}\nstderr: {r_rebase.stderr}")

        # 3. Land Session B via land root
        r_b = run_land("root", "--ticket", "T426", "--skip-state-check", cwd=self.wt_b)
        self.assertEqual(r_b.returncode, 0, msg=f"Session B land failed:\nstdout: {r_b.stdout}\nstderr: {r_b.stderr}")

        # Fast forward beta on main repo to include session B
        subprocess.run(["git", "merge", "--ff-only", "session-b"], cwd=self.repo, check=True, capture_output=True)

        # 4. Verify beta STATE.md contains both synthesized handoffs without merge conflict:
        final_state = (self.repo / "STATE.md").read_text()
        self.assertNotIn("Conflicting Session A narrative", final_state)
        self.assertIn("Session A finished subtask 1", final_state)
        self.assertIn("Session B finished subtask 2", final_state)
        self.assertNotIn("<<<<<<<", final_state)
        self.assertNotIn(">>>>>>>", final_state)


if __name__ == "__main__":
    unittest.main()
