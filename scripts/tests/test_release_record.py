#!/usr/bin/env python3
"""T554: the release record must land on `origin/beta` however many agents are landing there, and never strand a commit in the live checkout.

2026-10-07: a deploy shipped, published its tags, then `record_release` committed `releases/<v>.json` and CHANGELOG.md on the owner's LIVE checkout and ran one
`git push origin beta`. agy had landed in between, the push was rejected (non-fast-forward), and the commit stayed on the live branch: ahead 1, behind 1, so the
owner's `git merge --ff-only` catch-up failed too. `last_deployed()` also read `releases/` from that working tree, so a record that landed anywhere else was invisible to the
next cut.

Now: the record commit is built with git plumbing directly on the freshly fetched tip (no working tree, no index, no checkout), pushed, retried on a lost race, and parked in
machine-level state with an explicit retry command when it cannot land. `last_deployed()` reads `origin/beta`. These tests use throwaway git repositories (a bare origin, the
"estate" clone, a second "agent" clone); no network, nothing outside the temp dir.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import release  # noqa: E402

ENV = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C", "GIT_CONFIG_NOSYSTEM": "1"}
V = "2026.10.07-1791355037"
REC = f"releases/{V}.json"
FILES = {REC: b'{"version": "' + V.encode() + b'", "deployed": true}\n', "CHANGELOG.md": b"# changelog\nnew line\n"}
MSG = f"chore(T473): release {V} deployed (api, web)"


def git(cwd: Path, *args: str, check: bool = True, input: str | None = None) -> str:
    p = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, env=ENV, input=input)
    if check and p.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed in {cwd}: {p.stderr.strip()}")
    return p.stdout.strip()


class World:
    """A bare origin, the live checkout ("estate") and another agent's clone."""

    def __init__(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="release-record-"))
        self.origin = self.tmp / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "beta", str(self.origin)], check=True, env=ENV)
        seed = self.tmp / "seed"
        subprocess.run(["git", "clone", "-q", str(self.origin), str(seed)], check=True, env=ENV, capture_output=True)
        self.configure(seed)
        git(seed, "checkout", "-q", "-b", "beta")
        (seed / "README.md").write_text("estate\n")
        (seed / "CHANGELOG.md").write_text("# changelog\nold line\n")
        git(seed, "add", "-A")
        git(seed, "commit", "-q", "-m", "init")
        git(seed, "push", "-q", "origin", "beta")
        self.estate = self.clone("estate")
        self.agent = self.clone("agent")
        self.state = self.tmp / "state"

    def configure(self, repo: Path) -> None:
        git(repo, "config", "user.name", "Release Test")
        git(repo, "config", "user.email", "release@test.invalid")

    def clone(self, name: str) -> Path:
        d = self.tmp / name
        subprocess.run(["git", "clone", "-q", "-b", "beta", str(self.origin), str(d)], check=True, env=ENV, capture_output=True)
        self.configure(d)
        return d

    def agent_lands(self, name: str) -> str:
        """Another agent pushes one commit to origin/beta."""
        git(self.agent, "pull", "-q", "--rebase", "origin", "beta")
        (self.agent / f"{name}.txt").write_text(name + "\n")
        git(self.agent, "add", "-A")
        git(self.agent, "commit", "-q", "-m", f"work: {name}")
        git(self.agent, "push", "-q", "origin", "beta")
        return git(self.agent, "rev-parse", "HEAD")

    def remote_tip(self) -> str:
        return git(self.origin, "rev-parse", "beta")

    def land(self, **kw):
        kw.setdefault("sleep", lambda s: None)
        kw.setdefault("state_dir", self.state)
        return release.land_release_record(self.estate, V, dict(FILES), MSG, **kw)

    def cleanup(self) -> None:
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.w = World()
        self.addCleanup(self.w.cleanup)


class LandsOnTheTip(Base):
    def test_the_commit_is_built_on_the_freshly_fetched_tip_not_the_stale_local_branch(self):
        agent_commit = self.w.agent_lands("agy-work")  # origin moved; the estate has not fetched
        r = self.w.land()
        self.assertEqual(r.status, "landed", r)
        self.assertEqual(git(self.w.origin, "rev-parse", "beta~1"), agent_commit, "parent must be the other agent's commit")
        self.assertEqual(self.w.remote_tip(), r.commit)

    def test_it_adds_exactly_the_given_paths_and_nothing_else(self):
        self.w.agent_lands("agy-work")
        self.w.land()
        changed = sorted(git(self.w.origin, "diff", "--name-only", "beta~1", "beta").splitlines())
        self.assertEqual(changed, sorted(FILES))
        self.assertEqual(git(self.w.origin, "show", f"beta:{REC}") + "\n", FILES[REC].decode())

    def test_the_regenerated_changelog_replaces_the_tips_even_when_it_differs(self):
        self.w.agent_lands("agy-work")
        self.w.land()
        self.assertEqual(git(self.w.origin, "show", "beta:CHANGELOG.md"), FILES["CHANGELOG.md"].decode().strip())

    def test_the_commit_message_and_a_single_parent(self):
        self.w.land()
        self.assertEqual(git(self.w.origin, "log", "-1", "--format=%s", "beta"), MSG)
        self.assertEqual(len(git(self.w.origin, "log", "-1", "--format=%P", "beta").split()), 1)

    def test_the_live_checkout_working_tree_index_and_branch_are_never_touched(self):
        before = (git(self.w.estate, "rev-parse", "HEAD"), git(self.w.estate, "status", "--porcelain"))
        (self.w.estate / "scratch.txt").write_text("someone's uncommitted work\n")
        self.w.land()
        self.assertEqual(git(self.w.estate, "status", "--porcelain"), "?? scratch.txt")
        self.assertFalse((self.w.estate / "releases").exists(), "no release file may be written into the live working tree")
        self.assertEqual(git(self.w.estate, "diff", "--cached", "--name-only"), "")
        self.assertEqual(before[0], git(self.w.estate, "rev-parse", "beta"), "the live local branch must not gain a commit")

    def test_no_commit_is_left_on_the_live_local_branch_even_when_it_must_retry(self):
        self.w.agent_lands("a1")
        n = {"i": 0}

        def race(attempt: int) -> None:
            if attempt == 1:
                n["i"] += 1
                self.w.agent_lands("raced")

        r = self.w.land(_between_fetch_and_push=race)
        self.assertEqual(r.status, "landed")
        self.assertEqual(git(self.w.estate, "rev-list", "--count", "origin/beta..beta"), "0")


class RaceHandling(Base):
    def test_a_lost_race_is_retried_on_the_new_tip_and_lands(self):
        raced: list[str] = []

        def race(attempt: int) -> None:
            if attempt == 1:
                raced.append(self.w.agent_lands("raced"))

        r = self.w.land(_between_fetch_and_push=race)
        self.assertEqual((r.status, r.attempts), ("landed", 2), r)
        self.assertEqual(git(self.w.origin, "rev-parse", "beta~1"), raced[0])
        self.assertEqual(git(self.w.origin, "show", f"beta:{REC}") + "\n", FILES[REC].decode())

    def test_the_other_agents_work_survives_the_retry(self):
        def race(attempt: int) -> None:
            if attempt <= 2:
                self.w.agent_lands(f"raced-{attempt}")

        self.w.land(_between_fetch_and_push=race)
        files = git(self.w.origin, "ls-tree", "-r", "--name-only", "beta").splitlines()
        self.assertIn("raced-1.txt", files)
        self.assertIn("raced-2.txt", files)
        self.assertIn(REC, files)

    def test_a_race_lost_every_time_parks_the_payload_and_names_the_retry_command(self):
        tip_before = self.w.remote_tip()

        def race(attempt: int) -> None:
            self.w.agent_lands(f"raced-{attempt}")

        r = self.w.land(max_attempts=3, _between_fetch_and_push=race)
        self.assertEqual((r.status, r.attempts), ("pending", 3), r)
        self.assertNotEqual(self.w.remote_tip(), tip_before)
        self.assertNotIn(REC, git(self.w.origin, "ls-tree", "-r", "--name-only", "beta").splitlines())
        self.assertTrue((self.w.state / V / "payload.json").exists())
        self.assertIn(f"release-record {V}", r.note)
        self.assertEqual(git(self.w.estate, "rev-list", "--count", "origin/beta..beta"), "0", "even a failed landing leaves no commit on the live branch")

    def test_retry_lands_the_parked_payload_and_clears_it(self):
        self.w.land(max_attempts=1, _between_fetch_and_push=lambda a: self.w.agent_lands("raced"))
        self.assertTrue((self.w.state / V).exists())
        r = release.retry_pending_record(self.w.estate, V, state_dir=self.w.state, sleep=lambda s: None)
        self.assertEqual(r.status, "landed", r)
        self.assertFalse((self.w.state / V).exists())
        self.assertEqual(git(self.w.origin, "show", f"beta:{REC}") + "\n", FILES[REC].decode())

    def test_retry_of_a_version_with_nothing_parked_fails_closed(self):
        with self.assertRaises(SystemExit) as e:
            release.retry_pending_record(self.w.estate, "2026.01.01-1", state_dir=self.w.state, sleep=lambda s: None)
        self.assertIn("nothing parked", str(e.exception))

    def test_a_refusal_that_is_not_a_race_is_not_retried(self):
        hook = self.w.origin / "hooks" / "pre-receive"
        hook.write_text("#!/bin/sh\necho 'policy: nope' >&2\nexit 1\n")
        hook.chmod(0o755)
        calls: list[int] = []
        r = self.w.land(max_attempts=5, _between_fetch_and_push=lambda a: calls.append(a))
        self.assertEqual(r.status, "failed", r)
        self.assertEqual(calls, [1], "retrying a policy refusal five times would hide it")
        self.assertIn("policy: nope", r.note)
        self.assertTrue((self.w.state / V / "payload.json").exists(), "the payload is still parked so it is not lost")


class Idempotence(Base):
    def test_landing_twice_adds_one_commit(self):
        self.w.land()
        tip = self.w.remote_tip()
        r = self.w.land()
        self.assertEqual(r.status, "already", r)
        self.assertEqual(self.w.remote_tip(), tip)

    def test_a_different_record_for_the_same_version_is_refused_not_overwritten(self):
        self.w.land()
        with self.assertRaises(SystemExit) as e:
            release.land_release_record(self.w.estate, V, {REC: b'{"other": 1}\n'}, MSG, state_dir=self.w.state, sleep=lambda s: None)
        self.assertIn("already exists with different content", str(e.exception))

    def test_a_rejected_path_outside_releases_and_changelog_is_refused(self):
        for bad in ("README.md", "../escape.json", "/etc/passwd", "releases/../README.md", ".tasks/T1.md"):
            with self.assertRaises(SystemExit, msg=bad):
                release.land_release_record(self.w.estate, V, {bad: b"x"}, MSG, state_dir=self.w.state, sleep=lambda s: None)


class CatchUp(Base):
    def test_a_clean_live_checkout_is_fast_forwarded_after_landing(self):
        r = self.w.land()
        self.assertTrue(release.fast_forward_estate(self.w.estate))
        self.assertEqual(git(self.w.estate, "rev-parse", "HEAD"), r.commit)
        self.assertTrue((self.w.estate / REC).exists())

    def test_uncommitted_work_in_other_files_does_not_block_the_catch_up(self):
        (self.w.estate / "scratch.txt").write_text("mine\n")
        self.w.land()
        self.assertTrue(release.fast_forward_estate(self.w.estate))
        self.assertEqual((self.w.estate / "scratch.txt").read_text(), "mine\n")

    def test_a_diverged_live_branch_is_reported_never_forced(self):
        (self.w.estate / "local.txt").write_text("local commit\n")
        git(self.w.estate, "add", "-A")
        git(self.w.estate, "commit", "-q", "-m", "local")
        local = git(self.w.estate, "rev-parse", "HEAD")
        self.w.land()
        self.assertFalse(release.fast_forward_estate(self.w.estate))
        self.assertEqual(git(self.w.estate, "rev-parse", "HEAD"), local)


class LastDeployed(Base):
    def put(self, version: str, deployed: bool) -> None:
        git(self.w.agent, "pull", "-q", "--rebase", "origin", "beta")
        (self.w.agent / "releases").mkdir(exist_ok=True)
        (self.w.agent / "releases" / f"{version}.json").write_text(json.dumps({"version": version, "deployed": deployed}) + "\n")
        git(self.w.agent, "add", "-A")
        git(self.w.agent, "commit", "-q", "-m", f"record {version}")
        git(self.w.agent, "push", "-q", "origin", "beta")

    def test_it_reads_the_newest_deployed_record_from_origin_beta_not_from_the_working_tree(self):
        self.put("2026.10.01-100", True)
        self.put("2026.10.02-200", True)
        git(self.w.estate, "fetch", "-q", "origin", "beta")
        self.assertFalse((self.w.estate / "releases").exists())
        self.assertEqual(release.last_deployed(self.w.estate)["version"], "2026.10.02-200")

    def test_a_record_that_landed_elsewhere_is_seen_even_when_the_working_tree_is_stale(self):
        self.put("2026.10.01-100", True)
        git(self.w.estate, "pull", "-q", "--ff-only", "origin", "beta")
        self.put("2026.10.03-300", True)  # lands while the live checkout is behind
        git(self.w.estate, "fetch", "-q", "origin", "beta")
        self.assertEqual(release.last_deployed(self.w.estate)["version"], "2026.10.03-300")

    def test_records_that_were_not_deployed_are_skipped(self):
        self.put("2026.10.01-100", True)
        self.put("2026.10.02-200", False)
        git(self.w.estate, "fetch", "-q", "origin", "beta")
        self.assertEqual(release.last_deployed(self.w.estate)["version"], "2026.10.01-100")

    def test_no_records_is_none_not_an_error(self):
        git(self.w.estate, "fetch", "-q", "origin", "beta")
        self.assertIsNone(release.last_deployed(self.w.estate))

    def test_no_origin_beta_fails_closed(self):
        lone = Path(tempfile.mkdtemp(prefix="release-lone-"))
        self.addCleanup(__import__("shutil").rmtree, lone, True)
        subprocess.run(["git", "init", "-q", "-b", "beta", str(lone)], check=True, env=ENV)
        with self.assertRaises(SystemExit) as e:
            release.last_deployed(lone)
        self.assertIn("origin/beta", str(e.exception))


class Structure(unittest.TestCase):
    """Source guards: the old mechanism must not come back."""

    SRC = (SCRIPTS / "release.py").read_text()

    def code(self, name: str) -> str:
        """The code of one top-level function: exactly that function (not the self-test's string literals), docstring removed."""
        m = re.search(rf"^def {name}\b.*?(?=^def |^class |^@dataclass|\Z)", self.SRC, re.S | re.M)
        self.assertIsNotNone(m, f"no function {name}")
        return re.sub(r'"""(?:.|\n)*?"""', "", m.group(0), count=1)  # type: ignore[union-attr]

    def test_record_release_no_longer_commits_or_pushes_in_the_live_checkout(self):
        b = self.code("record_release")
        self.assertNotIn('"commit"', b)
        self.assertNotIn('"push", "--quiet", "origin", BRANCH', b)
        self.assertNotIn("RECORDS.mkdir", b)
        self.assertNotIn("write_text", b)
        self.assertIn("land_release_record(", b)

    def test_deploy_from_no_longer_copies_the_changelog_into_the_live_checkout(self):
        b = self.code("deploy_from")
        self.assertNotIn("copy2", b)
        self.assertNotIn("cl_dst", b)

    def test_the_landing_uses_plumbing_and_never_the_working_tree(self):
        b = self.code("land_release_record")
        for needed in ("commit-tree", "write-tree", "GIT_INDEX_FILE", "hash-object"):
            self.assertIn(needed, b)
        for banned in ('"checkout"', '"reset"', '"stash"', '"merge"', '"commit",', "--force", "--no-verify", "-f\""):
            self.assertNotIn(banned, b, banned)

    def test_the_cli_exposes_the_retry_and_the_recipes_exist_where_the_runner_reads_them(self):
        self.assertIn('cmd == "record"', self.SRC)
        root = SCRIPTS.parent
        jf_path = root / "justfile" if (root / "justfile").exists() else root / "w0m-api" / "justfile"
        jf = jf_path.read_text()
        self.assertRegex(jf, r"(?m)^release-record \*args:\n    @")
        self.assertRegex(jf, r"(?m)^release-record-test:\n    @")
        reg = json.loads((root / "w0m-web" / "project" / "test-suites.json").read_text())["suites"]
        entry = next((s for s in reg if s["name"] == "release-record"), None)
        self.assertIsNotNone(entry, "suite 'release-record' is not registered")
        self.assertTrue(entry.get("blocking", True))


class _Result(unittest.TextTestResult):
    """House style (scripts/run_suites.py counts them): one check line per test on stdout."""

    def addSuccess(self, test):  # noqa: N802
        super().addSuccess(test)
        print(f"  ✅ {test.id().rsplit('.', 2)[-2]}.{test.id().rsplit('.', 1)[-1]}")

    def addFailure(self, test, err):  # noqa: N802
        super().addFailure(test, err)
        print(f"  ❌ {test.id().rsplit('.', 2)[-2]}.{test.id().rsplit('.', 1)[-1]}")

    def addError(self, test, err):  # noqa: N802
        super().addError(test, err)
        print(f"  ❌ {test.id().rsplit('.', 2)[-2]}.{test.id().rsplit('.', 1)[-1]}")


if __name__ == "__main__":
    unittest.main(testRunner=unittest.TextTestRunner(resultclass=_Result, verbosity=1))
