#!/usr/bin/env python3
"""Unit + end-to-end tests for scripts/name_refs.py. The gate must be able to go red AND green on a real git repo."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))
import name_refs as n  # noqa: E402

OLD = "wom7oldname"


def cls(path, line=OLD):
    return n.classify(path, line, OLD)


class Classify(unittest.TestCase):
    def test_surface_classes(self):
        self.assertEqual(cls("src/index.ts", f"import x from '../{OLD}/src'"), "code")
        self.assertEqual(cls("wrangler.jsonc", f'"name": "{OLD}"'), "config")
        self.assertEqual(cls("justfile", f"cd {OLD}"), "config")
        self.assertEqual(cls("docs/ARCHITECTURE.md"), "docs")
        self.assertEqual(cls("openspec/changes/2026-x/proposal.md"), "spec")
        self.assertEqual(cls("apps/cp/specs/api/1.spec"), "spec")

    def test_env_default_is_its_own_class_and_beats_code(self):
        line = f'workers_url = os.environ.get("WORKERS_URL", "https://{OLD}.example.workers.dev")'
        self.assertEqual(cls("scripts/healthcheck.py", line), "env-default")
        self.assertEqual(cls("src/a.ts", f'const u = process.env.WORKERS_URL || "https://{OLD}.dev"'), "env-default")
        # an env read that does NOT embed the name is not an env-default
        self.assertNotEqual(cls("scripts/a.py", f'x = os.environ.get("WORKERS_URL")  # {OLD}'), "env-default")

    def test_history_and_records_may_keep_the_name(self):
        for p in ("supabase/migrations/2026_x.sql", "openspec/changes/archive/2026-a/tasks.md", ".tasks/archive/x.md",
                  "project/state-archive/a.md", "supabase/baseline/schema.sql"):
            self.assertEqual(cls(p), "history", p)
        for p in (".tasks/T1.md", "LESSONS.md", "STATE.md", ".agents/reports/x.md", "docs/decisions/AgDR-0001-x.md"):
            self.assertEqual(cls(p), "record", p)

    def test_generated_is_regenerated_not_edited(self):
        for p in ("TASKS.md", "docs/DECISIONS.md", "graphify-out/GRAPH_REPORT.md", "pnpm-lock.yaml", "CHANGELOG.md"):
            self.assertEqual(cls(p), "generated", p)

    def test_a_line_that_says_it_is_history_is_a_visible_note_not_a_live_hit(self):
        self.assertEqual(cls("src/index.ts", f"// was named {OLD} until 2026-08-01"), "note")
        self.assertEqual(cls("README.md", f"formerly {OLD}"), "note")
        self.assertEqual(cls("ROADMAP.md", f"Slug renamed `{OLD}` -> `new`"), "note")
        # ...but the same file with a CURRENT claim stays live
        self.assertEqual(cls("src/index.ts", f"// WORKERS_WEBHOOK_URL points at {OLD}"), "code")

    def test_history_beats_file_type(self):
        self.assertEqual(cls("supabase/migrations/1.ts"), "history")


class Env(unittest.TestCase):
    def test_only_url_shaped_names_are_candidates(self):
        self.assertTrue(n.URLISH.search("WORKERS_WEBHOOK_URL"))
        self.assertTrue(n.URLISH.search("WOM7API_WORKER_URL"))
        for bad in ("SUPABASE_SERVICE_ROLE_KEY", "WEBHOOK_SECRET", "SERVICE_ROLE_KEY", "API_TOKEN"):
            self.assertFalse(n.URLISH.search(bad), bad)


def git(cwd, *a):
    subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                        "GIT_COMMITTER_EMAIL": "t@t"})


class EndToEnd(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="name-refs-"))
        git(self.root, "init", "-q")
        repo = self.root / "wom7x"
        (repo / "src").mkdir(parents=True)
        git(repo, "init", "-q")
        (repo / "src" / "a.ts").write_text(f'export const u = process.env.URL_X ?? "https://{OLD}.dev";\n')
        (repo / "README.md").write_text(f"# {OLD}\n")
        (repo / "migrations").mkdir()
        (repo / "migrations" / "1.sql").write_text(f"-- {OLD}\n")
        (repo / "link").symlink_to(f"../{OLD}/x")
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "init")

    def run_cli(self, *args):
        r = subprocess.run([sys.executable, str(SCRIPTS_DIR / "name_refs.py"), OLD, "--root", str(self.root), *args],
                           capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr

    def test_gate_is_red_while_live_refs_remain_and_names_each_surface(self):
        code, out = self.run_cli("--gate")
        self.assertEqual(code, 1, out)
        for cls_ in ("[env-default] 1", "[docs] 1", "[symlink] 1", "[history] 1"):
            self.assertIn(cls_, out)

    def test_gate_is_green_when_only_history_remains(self):
        repo = self.root / "wom7x"
        (repo / "src" / "a.ts").write_text('export const u = process.env.URL_X ?? "https://new.dev";\n')
        (repo / "README.md").write_text("# new\n")
        (repo / "link").unlink()
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "renamed")
        code, out = self.run_cli("--gate")
        self.assertEqual(code, 0, out)
        self.assertIn("no live reference", out)

    def test_short_name_refuses(self):
        r = subprocess.run([sys.executable, str(SCRIPTS_DIR / "name_refs.py"), "ab", "--root", str(self.root)],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)


class _Tick(unittest.TextTestResult):
    def addSuccess(self, t):
        super().addSuccess(t); print(f"✅ {t.id().rsplit('.', 1)[-1]}")

    def addFailure(self, t, e):
        super().addFailure(t, e); print(f"❌ {t.id().rsplit('.', 1)[-1]}")

    def addError(self, t, e):
        super().addError(t, e); print(f"❌ {t.id().rsplit('.', 1)[-1]}")


if __name__ == "__main__":
    unittest.main(testRunner=unittest.TextTestRunner(resultclass=_Tick, verbosity=1))
