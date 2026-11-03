#!/usr/bin/env python3
"""Test Multi-Agent Concurrency Architecture (T411).

Asserts:
1. Ticket resolution finds .tasks/ when present (and respects W0M_TASKS_DIR).
2. Concurrent edits to distinct tickets in .tasks/ do not collide or create merge conflicts.
3. tasks_render compiles TASKS.md deterministically and idempotently from .tasks/T*.md.
4. Scoped w0m_audit ignores untracked in-flight draft specs during push validation.
5. sdlc_trace recognizes commits touching .tasks/T##.md without requiring TASKS.md edits.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Estate paths
ROOT_WORKSPACE = Path(__file__).resolve().parents[2]
WEB_ROOT = ROOT_WORKSPACE / "w0m-web"

SCRIPTS = ROOT_WORKSPACE / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(1, str(WEB_ROOT / "project" / "scripts"))


class TestAgentConcurrency(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="w0m-test-concurrency-")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_tickets_directory_resolver(self):
        """Resolver checks W0M_TASKS_DIR, root .tasks/, and falls back to project/tickets/."""
        import tasks_query as tq

        # 1. Explicit env override
        custom_dir = Path(self.tmpdir) / "custom_tasks"
        custom_dir.mkdir()
        (custom_dir / "T999.md").write_text(
            "---\nid: T999\ntitle: Custom Task\nstatus: queued\npriority: P1\n---\n"
        )
        os.environ["W0M_TASKS_DIR"] = str(custom_dir)
        try:
            resolved = tq.resolve_tickets_dir()
            self.assertEqual(resolved.resolve(), custom_dir.resolve())
            self.assertTrue((resolved / "T999.md").exists())
        finally:
            del os.environ["W0M_TASKS_DIR"]

        # 2. Local/root .tasks/ directory
        root_tasks = Path(self.tmpdir) / ".tasks"
        root_tasks.mkdir()
        (root_tasks / "T998.md").write_text(
            "---\nid: T998\ntitle: Root Task\nstatus: in-progress\npriority: P0\n---\n"
        )
        resolved = tq.resolve_tickets_dir(search_root=Path(self.tmpdir))
        self.assertEqual(resolved.resolve(), root_tasks.resolve())

    def test_concurrent_ticket_edits_no_conflict(self):
        """Two agents editing separate tickets in .tasks/ commit cleanly with zero conflicts."""
        repo = Path(self.tmpdir) / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.email", "test@w0m.io"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "w0m Agent"], cwd=repo, check=True)

        tasks_dir = repo / ".tasks"
        tasks_dir.mkdir()
        (tasks_dir / "T901.md").write_text("---\nid: T901\nstatus: queued\npriority: P1\n---\n# T901\n")
        (tasks_dir / "T902.md").write_text("---\nid: T902\nstatus: queued\npriority: P2\n---\n# T902\n")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "chore: initial tickets"], cwd=repo, check=True)

        # Agent Alpha branches and works on T901
        subprocess.run(["git", "checkout", "-q", "-b", "agent-alpha"], cwd=repo, check=True)
        (tasks_dir / "T901.md").write_text("---\nid: T901\nstatus: in-progress\npriority: P1\n---\n# T901 started\n")
        subprocess.run(["git", "commit", "-am", "feat(T901): start T901"], cwd=repo, check=True)

        # Agent Beta branches from main and works on T902
        subprocess.run(["git", "checkout", "-q", "main"], cwd=repo, check=True)
        subprocess.run(["git", "checkout", "-q", "-b", "agent-beta"], cwd=repo, check=True)
        (tasks_dir / "T902.md").write_text("---\nid: T902\nstatus: done\npriority: P2\n---\n# T902 completed\n")
        subprocess.run(["git", "commit", "-am", "feat(T902): complete T902"], cwd=repo, check=True)

        # Merge Agent Alpha into main
        subprocess.run(["git", "checkout", "-q", "main"], cwd=repo, check=True)
        subprocess.run(["git", "merge", "-q", "--no-ff", "agent-alpha", "-m", "merge alpha"], cwd=repo, check=True)

        # Merge Agent Beta into main -> MUST succeed without conflicts!
        merge_res = subprocess.run(["git", "merge", "--no-ff", "agent-beta", "-m", "merge beta"], cwd=repo, capture_output=True, text=True)
        self.assertEqual(merge_res.returncode, 0, f"Concurrent ticket merge failed with conflict: {merge_res.stderr}")
        self.assertIn("in-progress", (tasks_dir / "T901.md").read_text())
        self.assertIn("done", (tasks_dir / "T902.md").read_text())

    def test_tasks_render_deterministic_output(self):
        """tasks_render compiles .tasks/ into TASKS.md idempotently and conforms to table bounds."""
        import tasks_render as tr

        tasks_dir = Path(self.tmpdir) / ".tasks"
        tasks_dir.mkdir()
        (tasks_dir / "T801.md").write_text(
            "---\nid: T801\ntitle: First Active Task\nstatus: in-progress\npriority: P0\nrepos: [web]\nqueue: now\n---\n# T801\n"
        )
        (tasks_dir / "T802.md").write_text(
            "---\nid: T802\ntitle: Second Queued Task\nstatus: queued\npriority: P1\nrepos: [api]\n---\n# T802\n"
        )
        (tasks_dir / "T803.md").write_text(
            "---\nid: T803\ntitle: Completed Task\nstatus: done\npriority: P2\nrepos: [tooling]\n---\n# T803\n"
        )

        out_tasks_md = Path(self.tmpdir) / "TASKS.md"
        tr.render_tasks_md(tasks_dir=tasks_dir, output_path=out_tasks_md)
        self.assertTrue(out_tasks_md.exists())

        content_pass1 = out_tasks_md.read_text(encoding="utf-8")
        self.assertIn("T801", content_pass1)
        self.assertIn("T802", content_pass1)
        self.assertIn("T803", content_pass1)
        self.assertIn("🟡", content_pass1)
        self.assertIn("⚪", content_pass1)
        self.assertIn("✅", content_pass1)

        # Idempotence: Second render produces identical byte content
        tr.render_tasks_md(tasks_dir=tasks_dir, output_path=out_tasks_md)
        content_pass2 = out_tasks_md.read_text(encoding="utf-8")
        self.assertEqual(content_pass1, content_pass2)

        # Validate rows with tasks_bounds rule (6 columns)
        import tasks_bounds as tb
        rows = [ln for ln in content_pass1.splitlines() if tb.ROW.match(ln)]
        self.assertEqual(len(rows), 3)
        malformed = tb.malformed_rows(rows)
        self.assertEqual(malformed, [], f"tasks_render produced malformed rows: {malformed}")

        # T617 regression: prose containing the substring "done" on a paused/queued row must NOT
        # prevent tasks_render from updating the leading status claim when the ticket flips to done.
        stale_row = (
            "| [T802](.tasks/T802.md) | **P2** | **Second Queued Task** | api | — "
            "| 💤 **paused** — rotation done, history purge still open |"
        )
        synced_row = tr.render_row({"id": "T802", "status": "done", "priority": "P2"}, stale_row)
        synced_cells = tb.row_status_cells([synced_row])
        self.assertEqual(tb.row_claim(synced_cells["T802"])[0], "done", synced_row)

    def test_sdlc_trace_supports_root_tasks(self):
        """sdlc_trace detects ticket progress in .tasks/T##.md without requiring TASKS.md edits."""
        repo = Path(self.tmpdir) / "trace_repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.email", "trace@w0m.io"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "w0m Trace"], cwd=repo, check=True)

        tasks_dir = repo / ".tasks"
        tasks_dir.mkdir()
        (repo / "TASKS.md").write_text("| ticket | prio |\n")
        (repo / "code.py").write_text("v = 1\n")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "chore: base"], cwd=repo, check=True)

        # Commit modifying code and .tasks/T411.md, but leaving TASKS.md completely untouched
        (repo / "code.py").write_text("v = 2\n")
        (tasks_dir / "T411.md").write_text("---\nid: T411\nstatus: in-progress\n---\n# T411 updated\n")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "feat(T411): update concurrency logic"], cwd=repo, check=True)

        env = {**os.environ, "W0M_TRACE_ROOT": str(repo)}
        sdlc_trace_script = SCRIPTS / "sdlc_trace.py"
        res = subprocess.run(
            [sys.executable, str(sdlc_trace_script), "--range", "HEAD~1..HEAD"],
            cwd=repo,
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(res.returncode, 0, f"sdlc_trace failed to recognize .tasks/ update: {res.stdout}\n{res.stderr}")

    def test_scoped_prepush_audit_ignores_untracked(self):
        """w0m_audit --scope-diff evaluates push commits only, ignoring untracked WIP directories."""
        import w0m_audit as wa

        # Create a mock repo
        repo = Path(self.tmpdir) / "audit_repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.email", "audit@w0m.io"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "w0m Audit"], cwd=repo, check=True)
        subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo, check=True)
        subprocess.run(["git", "config", "tag.gpgsign", "false"], cwd=repo, check=True)

        (repo / "file.txt").write_text("initial\n")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "chore: initial"], cwd=repo, check=True)

        # Baseline tag
        subprocess.run(["git", "tag", "base-tag"], cwd=repo, check=True)

        # Commit modifying file.txt
        (repo / "file.txt").write_text("updated\n")
        subprocess.run(["git", "commit", "-am", "fix: update file"], cwd=repo, check=True)

        # Untracked in-flight invalid draft spec directory
        untracked_spec = repo / "openspec" / "changes" / "draft-untracked"
        untracked_spec.mkdir(parents=True)
        (untracked_spec / "broken.md").write_text("half-written spec\n")

        # Running diff --name-only base-tag HEAD should only report file.txt
        res = subprocess.run(
            ["git", "diff", "--name-only", "base-tag", "HEAD"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        )
        changed = set(res.stdout.splitlines())
        self.assertIn("file.txt", changed)
        self.assertNotIn("openspec/changes/draft-untracked/broken.md", changed)


if __name__ == "__main__":
    unittest.main()
