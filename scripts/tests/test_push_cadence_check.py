#!/usr/bin/env python3
"""Tests for project/scripts/push_cadence_check.py: which trees are detached mirrors of origin/beta, and what the check does there.

Found 2026-10-01 (T481): the blocking `push-cadence` suite exempted the RELEASE worktrees (every repo detached at a tag, so no upstream) but not the
persistent STABLE worktree (every repo detached at origin/beta, the same shape), so `just test` run in stable could never pass: "no repo had an upstream".
The exemption also tested the path with a string prefix, which would equally exempt a sibling directory that merely starts with the same characters.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import push_cadence_check as pc  # noqa: E402

HOME = Path("/Users/someone")


class MirrorKind(unittest.TestCase):
    def kind(self, estate: str, env: dict | None = None):
        return pc.detached_mirror_kind(Path(estate), HOME, env or {})

    def test_a_release_worktree_is_a_detached_mirror(self):
        self.assertEqual(self.kind("/Users/someone/.w0m/releases/2026.10.01-1/w0m"), "release worktree")

    def test_the_stable_worktree_is_a_detached_mirror(self):
        self.assertEqual(self.kind("/Users/someone/.w0m/stable/w0m"), "stable worktree")

    def test_the_live_checkout_is_not(self):
        self.assertIsNone(self.kind("/Users/someone/Projects/@self/@wom"))

    def test_the_release_environment_flag_alone_marks_a_release_worktree(self):
        self.assertEqual(self.kind("/anywhere/else", {"W0M_RELEASE_WORKTREE": "1"}), "release worktree")

    def test_a_flag_that_is_not_exactly_1_does_not(self):
        for v in ("0", "", "true", "yes", "2"):
            self.assertIsNone(self.kind("/anywhere/else", {"W0M_RELEASE_WORKTREE": v}), v)

    def test_a_sibling_directory_with_the_same_prefix_is_not_a_mirror(self):
        for p in ("/Users/someone/.w0m/releases-old/w0m", "/Users/someone/.w0m/stable-copy/w0m", "/Users/someone/.w0m/stablex"):
            self.assertIsNone(self.kind(p), p)

    def test_the_mirror_root_itself_counts(self):
        self.assertEqual(self.kind("/Users/someone/.w0m/stable"), "stable worktree")
        self.assertEqual(self.kind("/Users/someone/.w0m/releases"), "release worktree")

    def test_another_users_mirror_is_not_this_users(self):
        self.assertIsNone(self.kind("/Users/other/.w0m/stable/w0m"))


class MainWithNoUpstream(unittest.TestCase):
    """main() on an estate where no repo has an upstream: clean ONLY for a detached mirror, otherwise 'cannot judge' (2), never a pass."""

    def run_main(self, estate: Path, env: dict | None = None, home: Path | None = None) -> tuple[int, str]:
        """`env` is EXACTLY the release flag state under test. The flag is cleared first: `just deploy` exports W0M_RELEASE_WORKTREE=1 to every
        suite it runs, so a test that leaves it alone passes by hand and fails inside the deploy's own test gate (found 2026-10-01, T481)."""
        out: list[str] = []
        clean = {k: v for k, v in os.environ.items() if k != "W0M_RELEASE_WORKTREE"}
        with mock.patch.object(pc, "ESTATE", estate), \
             mock.patch.object(pc, "done_tickets", return_value={"T1"}), \
             mock.patch.object(pc, "HOME", home or HOME), \
             mock.patch.dict(pc.os.environ, {**clean, **(env or {})}, clear=True), \
             mock.patch.object(sys, "argv", ["push_cadence_check.py"]), \
             mock.patch("builtins.print", side_effect=lambda *a, **k: out.append(" ".join(map(str, a)))):
            rc = pc.main()
        return rc, "\n".join(out)

    def estate_with_repos(self, root: Path) -> Path:
        for name in pc.REPOS:
            (root / name / ".git").mkdir(parents=True)        # a .git directory that is not a repository: `git rev-parse @{u}` fails
        return root

    def test_the_stable_worktree_passes_and_says_what_it_is(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            estate = self.estate_with_repos(home / ".w0m" / "stable" / "w0m")
            rc, out = self.run_main(estate, home=home)
            self.assertEqual(rc, 0, out)
            self.assertIn("stable worktree", out)

    def test_a_release_worktree_still_passes(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            estate = self.estate_with_repos(home / ".w0m" / "releases" / "v1" / "w0m")
            rc, out = self.run_main(estate, home=home)
            self.assertEqual(rc, 0, out)
            self.assertIn("release worktree", out)

    def test_the_release_flag_exempts_any_tree_and_is_reported_as_a_release_worktree(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            estate = self.estate_with_repos(home / "Projects" / "estate")
            rc, out = self.run_main(estate, env={"W0M_RELEASE_WORKTREE": "1"}, home=home)
            self.assertEqual(rc, 0, out)
            self.assertIn("release worktree", out)

    def test_an_ordinary_estate_with_no_upstream_is_unknown_not_clean(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            estate = self.estate_with_repos(home / "Projects" / "estate")
            rc, out = self.run_main(estate, home=home)
            self.assertEqual(rc, 2, out)
            self.assertIn("cannot judge", out)

    def test_advisory_findings_emit_countable_fail_marker(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            estate = self.estate_with_repos(home / "Projects" / "estate")
            def fake_git(repo: Path, *args: str) -> str | None:
                if args == ("rev-parse", "--abbrev-ref", "@{u}"):
                    return "origin/beta" if repo.name == "w0m-web" else None
                if args == ("log", "--format=%ct%x09%s", "@{u}.."):
                    return f"{int(pc.time.time())}\tdocs(T1): done commit"
                return None
            with mock.patch.object(pc, "git", side_effect=fake_git):
                rc, out = self.run_main(estate, home=home)
            self.assertEqual(rc, 0, out)
            self.assertIn("[FAIL] 1 finding(s):", out)



class _Tick(unittest.TextTestResult):
    def addSuccess(self, t):
        super().addSuccess(t); print(f"✅ {t.id().rsplit('.', 1)[-1]}")

    def addFailure(self, t, e):
        super().addFailure(t, e); print(f"❌ {t.id().rsplit('.', 1)[-1]}")

    def addError(self, t, e):
        super().addError(t, e); print(f"❌ {t.id().rsplit('.', 1)[-1]}")


if __name__ == "__main__":
    unittest.main(testRunner=unittest.TextTestRunner(resultclass=_Tick, verbosity=1))
