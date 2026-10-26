#!/usr/bin/env python3
"""T546: the scheduled tools upgrade PROPOSES `known_good` bumps; only `tools-promote --apply`, run in an agent tree, writes them.

Owner decision 2026-10-06 (option C). Until now `just tools-weekly` (a launchd agent) rewrote `project/policies/tools-policy.json` in the LIVE checkout and never
committed, so the owner's checkout sat dirty for a day, `git merge --ff-only` aborted, and a bump could land in the file without its smoke (semgrep on 2026-10-05:
held by the weekly run, written anyway by the reconcile step). Now:

1. `tools_upgrade.py --apply` and `--reconcile --apply` upgrade and smoke-test as before, but write a PROPOSAL to a machine-level state file
   (`~/.w0m/state/tools-proposed.json`, outside every tree so an agent tree sees what the live tree's scheduled run found) and never the policy;
2. `tools_upgrade.py --promote` lists the proposals; `--promote --apply` re-verifies each one NOW (installed == proposed, at least `min`, smoke passes) and
   writes `known_good` into THIS tree's policy, only when this tree is an agent tree, and removes what it promoted from the state file.

Offline: every external command (brew, the tool itself) is replaced by a fake.
"""
from __future__ import annotations

import io
import json
import re
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import tools_check  # noqa: E402
import tools_upgrade as tu  # noqa: E402

REPO = SCRIPTS.parent
POLICY_TEXT = json.dumps(
    {
        "tools": {
            "foo": {"min": "1.0.0", "known_good": "1.1.0", "required": True, "source": "brew", "auto": "minor", "smoke": "foo --version"},
            "bar": {"min": "2.0.0", "known_good": "2.0.0", "required": False, "source": "brew", "auto": "patch"},  # no smoke
        }
    },
    indent=2,
) + "\n"


def cp(rc: int = 0, out: str = "", err: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], rc, out, err)


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="tools-upgrade-"))
        self.policy = self.tmp / "tree" / "project" / "policies" / "tools-policy.json"
        self.policy.parent.mkdir(parents=True)
        self.policy.write_text(POLICY_TEXT)
        self.status = self.tmp / "tree" / "project" / ".tools-weekly-status.json"
        self.proposed = self.tmp / "state" / "tools-proposed.json"
        self.proposed.parent.mkdir(parents=True)
        self.patches = [
            mock.patch.object(tu, "POLICY", self.policy),
            mock.patch.object(tu, "STATUS", self.status),
            mock.patch.object(tu, "PROPOSED", self.proposed),
            mock.patch.object(tu, "ROOT", self.tmp / "tree"),
            mock.patch.object(tu, "WEB", self.tmp),
            mock.patch.object(tu, "report_outdated", lambda *a, **k: 0),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self) -> None:
        for p in self.patches:
            p.stop()
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def invoke(self, *argv: str) -> tuple[int, str]:
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "argv", ["tools_upgrade.py", *argv]), redirect_stdout(out), redirect_stderr(err):
            rc = tu.main()
        return rc, out.getvalue() + err.getvalue()

    def proposals(self) -> dict:
        return json.loads(self.proposed.read_text()) if self.proposed.exists() else {}


class WeeklyApplyProposesOnly(Base):
    def run_apply(self, *, installed_after: str = "1.2.0", smoke_rc: int = 0):
        upgraded = {"done": False}  # the installed version changes only once `brew upgrade` has run

        def fake_installed(name, arg="--version", spec=None):
            if name == "foo":
                return installed_after if upgraded["done"] else "1.1.0"
            return "2.0.0"

        def fake_run(cmd, cwd=None, timeout=300):
            if cmd[:2] == ["brew", "upgrade"]:
                upgraded["done"] = True
                return cp(0)
            return cp(smoke_rc, err="boom" if smoke_rc else "")

        with mock.patch.object(tu, "brew_latest", lambda: {"foo": "1.2.0", "bar": "2.0.0"}), mock.patch.object(tu, "installed_version", fake_installed), mock.patch.object(tu, "run", fake_run):
            return self.invoke("--apply")

    def test_a_smoke_verified_upgrade_is_recorded_as_a_proposal_and_the_policy_is_not_touched(self):
        before = self.policy.read_bytes()
        rc, out = self.run_apply()
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.policy.read_bytes(), before, "the scheduled run must never write tools-policy.json")
        p = self.proposals()
        self.assertEqual(sorted(p), ["foo"], p)
        self.assertEqual((p["foo"]["from"], p["foo"]["to"], p["foo"]["smoke"]), ("1.1.0", "1.2.0", "passed"))
        self.assertIn("tools-promote", out)

    def test_the_status_file_records_the_outcome_as_proposed_not_promoted(self):
        self.run_apply()
        st = json.loads(self.status.read_text())
        self.assertEqual(st["proposed"], ["foo 1.1.0→1.2.0"])
        self.assertNotIn("promoted", st)
        self.assertTrue(st["ok"])

    def test_a_failed_smoke_records_no_proposal_and_holds_the_tool(self):
        before = self.policy.read_bytes()
        rc, out = self.run_apply(smoke_rc=1)
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.proposals(), {})
        self.assertEqual(self.policy.read_bytes(), before)
        self.assertEqual(json.loads(self.status.read_text())["held"], ["foo"])

    def test_an_upgrade_that_did_not_take_records_no_proposal(self):
        rc, _ = self.run_apply(installed_after="1.1.0")
        self.assertEqual(rc, 1)
        self.assertEqual(self.proposals(), {})

    def test_a_second_run_replaces_the_proposal_for_the_same_tool(self):
        self.proposed.write_text(json.dumps({"foo": {"tool": "foo", "from": "1.0.0", "to": "1.1.5", "smoke": "passed", "source": "brew", "proposed_at": "2026-09-01T00:00:00"}}))
        self.run_apply()
        self.assertEqual(self.proposals()["foo"]["to"], "1.2.0")


class ReconcileProposesOnly(Base):
    def test_reconcile_apply_records_a_proposal_and_never_writes_the_policy(self):
        before = self.policy.read_bytes()
        with mock.patch.object(tu, "installed_version", lambda name, arg="--version", spec=None: {"foo": "1.2.0"}.get(name, "2.0.0")), mock.patch.object(tu, "run", lambda *a, **k: cp(0)):
            rc, out = self.invoke("--reconcile", "--apply")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.policy.read_bytes(), before)
        self.assertEqual(self.proposals()["foo"]["to"], "1.2.0")

    def test_reconcile_still_refuses_a_failing_smoke_and_a_missing_smoke(self):
        policy = json.loads(POLICY_TEXT)
        policy["tools"]["bar"]["known_good"] = "2.0.0"
        self.policy.write_text(json.dumps(policy))
        with mock.patch.object(tu, "installed_version", lambda name, arg="--version", spec=None: {"foo": "1.2.0", "bar": "2.0.1"}[name]), mock.patch.object(tu, "run", lambda *a, **k: cp(1, err="bad")):
            rc, out = self.invoke("--reconcile", "--apply")
        self.assertEqual(rc, 1)
        self.assertEqual(self.proposals(), {})
        self.assertIn("smoke FAILED", out)
        self.assertIn("NO smoke declared", out)


class Promote(Base):
    def seed(self, **over):
        entry = {"tool": "foo", "from": "1.1.0", "to": "1.2.0", "smoke": "passed", "source": "brew", "proposed_at": "2026-10-05T10:10:00"}
        entry.update(over)
        self.proposed.write_text(json.dumps({"foo": entry}))

    def promote(self, *extra, installed="1.2.0", smoke_rc=0, agent_tree=True):
        with mock.patch.object(tu, "installed_version", lambda name, arg="--version", spec=None: installed), mock.patch.object(tu, "run", lambda *a, **k: cp(smoke_rc, err="x" if smoke_rc else "")), mock.patch.object(tu, "is_agent_tree", lambda root: agent_tree):
            return self.invoke("--promote", *extra)

    def known_good(self) -> str:
        return json.loads(self.policy.read_text())["tools"]["foo"]["known_good"]

    def test_the_default_is_a_dry_run_that_lists_and_changes_nothing(self):
        self.seed()
        before = self.policy.read_bytes()
        rc, out = self.promote()
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.policy.read_bytes(), before)
        self.assertEqual(sorted(self.proposals()), ["foo"])
        self.assertIn("1.1.0", out)
        self.assertIn("1.2.0", out)
        self.assertIn("--apply", out)

    def test_apply_in_an_agent_tree_writes_known_good_and_clears_the_proposal(self):
        self.seed()
        rc, out = self.promote("--apply")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.known_good(), "1.2.0")
        self.assertEqual(self.proposals(), {})
        self.assertIn("commit", out.lower())

    def test_apply_outside_an_agent_tree_is_refused_and_changes_nothing(self):
        self.seed()
        before = self.policy.read_bytes()
        rc, out = self.promote("--apply", agent_tree=False)
        self.assertEqual(rc, 2, out)
        self.assertEqual(self.policy.read_bytes(), before)
        self.assertEqual(sorted(self.proposals()), ["foo"])
        self.assertIn("agent-tree", out)

    def test_it_re_verifies_so_a_stale_proposal_is_not_promoted(self):
        self.seed()
        rc, out = self.promote("--apply", installed="1.3.0")  # the tool moved on since the weekly run
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.known_good(), "1.1.0")
        self.assertIn("stale", out.lower())

    def test_a_tool_that_is_now_behind_the_proposal_is_not_promoted(self):
        self.seed()
        rc, out = self.promote("--apply", installed="1.1.0")
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.known_good(), "1.1.0")

    def test_the_smoke_is_run_again_at_promotion_and_a_failure_blocks_it(self):
        self.seed()
        rc, out = self.promote("--apply", smoke_rc=1)
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.known_good(), "1.1.0")
        self.assertEqual(sorted(self.proposals()), ["foo"], "a blocked proposal stays, so it stays visible")
        self.assertIn("smoke FAILED", out)

    def test_a_tool_with_no_smoke_is_never_promoted_silently(self):
        self.proposed.write_text(json.dumps({"bar": {"tool": "bar", "from": "2.0.0", "to": "2.0.1", "smoke": "none", "source": "brew", "proposed_at": "2026-10-05T10:10:00"}}))
        rc, out = self.promote("--apply", installed="2.0.1")
        self.assertEqual(rc, 1, out)
        self.assertEqual(json.loads(self.policy.read_text())["tools"]["bar"]["known_good"], "2.0.0")
        self.assertIn("NO smoke", out)

    def test_a_proposal_below_the_minimum_is_not_promoted(self):
        self.seed(to="0.9.0", **{"from": "1.1.0"})
        rc, out = self.promote("--apply", installed="0.9.0")
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.known_good(), "1.1.0")

    def test_a_proposal_for_a_tool_that_left_the_policy_is_reported_not_crashed_on(self):
        self.proposed.write_text(json.dumps({"ghost": {"tool": "ghost", "from": "1", "to": "2", "smoke": "passed", "source": "brew", "proposed_at": "x"}}))
        rc, out = self.promote("--apply")
        self.assertEqual(rc, 1, out)
        self.assertIn("ghost", out)

    def test_a_corrupt_state_file_fails_closed_with_its_path(self):
        self.proposed.write_text("{not json")
        rc, out = self.promote("--apply")
        self.assertEqual(rc, 2, out)
        self.assertIn(str(self.proposed), out)

    def test_no_proposals_is_a_clean_no_op(self):
        rc, out = self.promote("--apply")
        self.assertEqual(rc, 0, out)
        self.assertIn("nothing", out.lower())

    def test_one_good_and_one_blocked_promotes_the_good_one_and_keeps_the_other(self):
        self.proposed.write_text(json.dumps({
            "foo": {"tool": "foo", "from": "1.1.0", "to": "1.2.0", "smoke": "passed", "source": "brew", "proposed_at": "x"},
            "bar": {"tool": "bar", "from": "2.0.0", "to": "2.0.1", "smoke": "none", "source": "brew", "proposed_at": "x"},
        }))
        rc, out = self.promote("--apply", installed="1.2.0")
        self.assertEqual(self.known_good(), "1.2.0")
        self.assertEqual(sorted(self.proposals()), ["bar"])
        self.assertEqual(rc, 1, "partial: something stayed blocked, so the exit code says so")


class Structure(unittest.TestCase):
    def test_exactly_one_place_in_the_upgrade_script_writes_the_policy(self):
        """The SSOT guard: weekly and reconcile must have no policy write at all; only promote has one."""
        src = (SCRIPTS / "tools_upgrade.py").read_text()
        self.assertEqual(src.count("POLICY.write_text"), 1, "only the promote path may write tools-policy.json")
        i = src.index("POLICY.write_text")
        j = src.rfind("\ndef ", 0, i)
        self.assertIn("def promote", src[j : j + 40], "the single policy write must be inside promote()")

    def test_the_proposal_state_lives_outside_every_tree(self):
        self.assertFalse(str(tools_check.PROPOSED).startswith(str(REPO)), f"{tools_check.PROPOSED} is inside the repo: an agent tree could not see the live tree's weekly findings")
        self.assertTrue(str(tools_check.PROPOSED).startswith(str(Path.home() / ".w0m")) or "W0M_STATE_DIR" in __import__("os").environ)

    def test_the_agent_tree_detector_knows_the_agent_tree_root_and_not_the_live_checkout(self):
        self.assertTrue(tu.is_agent_tree(Path.home() / ".w0m" / "work" / "someone" / "w0m"))
        self.assertTrue(tu.is_agent_tree(Path.home() / ".w0m" / "work" / "someone" / "w0m" / "w0m-web"))
        self.assertFalse(tu.is_agent_tree(Path("/Users/proto/Projects/@self/@wom")))
        self.assertFalse(tu.is_agent_tree(Path.home() / ".w0m" / "workaround" / "w0m"), "a prefix match is not a path match")

    def test_the_justfiles_have_the_promote_recipe_and_no_weekly_recipe_promotes(self):
        """The root justfile duplicates these recipes, but the LAUNCHD job runs `just tools-weekly` from `@wom`, so the w0m-api recipe is the one that must be right."""
        for rel, forward in (("justfile", "scripts/tools_upgrade.py"),):
            jf = (REPO / rel).read_text()
            self.assertIn(f"tools-promote *args:\n    @python3 {forward} --promote {{{{ args }}}}", jf, rel)
            m = re.search(r"(?m)^tools-weekly[^\n]*:\n((?:[ \t]+[^\n]*\n?)+)", jf)  # the recipe definition, not a comment that names it
            self.assertIsNotNone(m, f"{rel}: no tools-weekly recipe")
            weekly = m.group(1)  # type: ignore[union-attr]
            self.assertNotIn("--promote", weekly, rel)
            self.assertNotIn("update-known-good", weekly, rel)
            self.assertIn("--apply", weekly, rel)

    def test_the_registered_suite_recipe_resolves_in_the_justfile_the_registry_runs(self):
        """The registry lives in w0m-web and runs recipes through w0m-api's justfile (w0m-web/justfile is a symlink to it). A recipe only in the root justfile reads as 'recipe not found', 0 checks."""
        reg = json.loads((REPO / "w0m-web" / "project" / "test-suites.json").read_text())["suites"]
        entry = next(s for s in reg if s["name"] == "tools-upgrade")
        jf = (REPO / "justfile").read_text()
        self.assertRegex(jf, rf"(?m)^{entry['recipe']}:\n    @python3 scripts/tests/test_tools_upgrade\.py")

    def test_compound_shell_smoke_uses_sh_c_and_missing_binary_returns_failure_without_crashing(self):
        """supabase's smoke starts with `cd ../w0m-api && ...`; splitting on spaces raises FileNotFoundError('cd') and aborts before proposals are saved."""
        self.assertEqual(tu.smoke_argv("ast-grep --version"), ["ast-grep", "--version"])
        self.assertEqual(
            tu.smoke_argv("cd ../w0m-api && infisical run --env=beta --silent -- sh -c 'true'"),
            ["sh", "-c", "cd ../w0m-api && infisical run --env=beta --silent -- sh -c 'true'"],
        )
        res = tu.run(["__no_such_binary_t546__"])
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("__no_such_binary_t546__", res.stderr)


class PendingIsVisible(unittest.TestCase):
    def test_the_full_check_names_pending_proposals_and_how_to_promote_them(self):
        tmp = Path(tempfile.mkdtemp(prefix="tools-pending-"))
        try:
            f = tmp / "p.json"
            f.write_text(json.dumps({"foo": {"tool": "foo", "from": "1.1.0", "to": "1.2.0", "smoke": "passed", "source": "brew", "proposed_at": "2026-10-05T10:10:00"}}))
            line = tools_check.pending_proposals_line(f)
            self.assertIn("1", line)
            self.assertIn("foo 1.1.0→1.2.0", line)
            self.assertIn("tools-promote", line)
            self.assertEqual(tools_check.pending_proposals_line(tmp / "missing.json"), "")
            f.write_text("{oops")
            self.assertIn("unreadable", tools_check.pending_proposals_line(f))
        finally:
            import shutil

            shutil.rmtree(tmp, ignore_errors=True)


class _Result(unittest.TextTestResult):
    """House style (scripts/run_suites.py counts them): one ✅/❌ line per check on stdout."""

    def addSuccess(self, test):  # noqa: N802
        super().addSuccess(test)
        print(f"  \u2705 {test.id().rsplit('.', 2)[-2]}.{test.id().rsplit('.', 1)[-1]}")

    def addFailure(self, test, err):  # noqa: N802
        super().addFailure(test, err)
        print(f"  \u274c {test.id().rsplit('.', 2)[-2]}.{test.id().rsplit('.', 1)[-1]}")

    def addError(self, test, err):  # noqa: N802
        super().addError(test, err)
        print(f"  \u274c {test.id().rsplit('.', 2)[-2]}.{test.id().rsplit('.', 1)[-1]}")


if __name__ == "__main__":
    unittest.main(testRunner=unittest.TextTestRunner(resultclass=_Result, verbosity=1))
