#!/usr/bin/env python3
"""Offline unit & throwaway-git red-probe tests for scripts/deploy_cert.py & --skip-prepush (T650, AgDR-0057)."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Mapping, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import deploy_cert as dc  # noqa: E402
import run_suites as rs  # noqa: E402


def _init_git(repo_dir: Path) -> None:
    repo_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "beta"], cwd=str(repo_dir), check=True)
    subprocess.run(["git", "config", "user.email", "test@w0m.local"], cwd=str(repo_dir), check=True)
    subprocess.run(["git", "config", "user.name", "w0m Test"], cwd=str(repo_dir), check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=str(repo_dir), check=True)


def _commit_all(repo_dir: Path, msg: str) -> str:
    subprocess.run(["git", "add", "-A"], cwd=str(repo_dir), check=True)
    subprocess.run(["git", "commit", "-q", "-m", msg], cwd=str(repo_dir), check=True)
    out = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(repo_dir),
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()


def _make_fake_estate(base: Path) -> Path:
    estate = base / "w0m"
    _init_git(estate)
    (estate / ".gitignore").write_text("w0m-web/\nw0m-api/\n", encoding="utf-8")
    (estate / ".w0m").mkdir(parents=True, exist_ok=True)
    (estate / ".w0m" / "sdlc.json").write_text(
        json.dumps({"repos": {"web": "w0m-web", "api": "w0m-api"}}) + "\n",
        encoding="utf-8",
    )
    _commit_all(estate, "chore: init umbrella")

    web = estate / "w0m-web"
    _init_git(web)
    (web / "project").mkdir(parents=True, exist_ok=True)
    (web / "project" / "test-suites.json").write_text(
        json.dumps({"suites": [{"name": "s1", "recipe": "r1", "tier": "offline", "blocking": True}]}) + "\n",
        encoding="utf-8",
    )
    _commit_all(web, "chore: init web")

    api = estate / "w0m-api"
    _init_git(api)
    (api / "README.md").write_text("api\n", encoding="utf-8")
    _commit_all(api, "chore: init api")
    return estate


class RecordingRunner:
    def __init__(self, rc: int = 0) -> None:
        self.rc = rc
        self.calls: list[tuple[list[str], str, dict[str, str]]] = []

    def __call__(
        self,
        cmd: Sequence[str],
        cwd: Path,
        extra_env: Mapping[str, str] | None = None,
    ) -> int:
        self.calls.append((list(cmd), str(cwd), dict(extra_env or {})))
        return self.rc


class DeployCertTests(unittest.TestCase):
    def test_certify_hits_cache_in_deploy_context_and_runs_uncached_standalone(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            estate = _make_fake_estate(tmp)
            cache_dir = tmp / "cache"
            deploy_env = {"W0M_DEPLOY_CERT_CACHE_DIR": str(cache_dir), "W0M_DEPLOY_LOGGED": "1"}
            standalone_env = {"W0M_DEPLOY_CERT_CACHE_DIR": str(cache_dir)}

            runner = RecordingRunner()
            rc, summary = dc.cmd_certify(estate, env=standalone_env, runner=runner)
            self.assertEqual(rc, 0)
            self.assertFalse(summary["cached"])
            self.assertTrue(summary["record"]["certified"])
            self.assertEqual(len(runner.calls), 4)  # 3 pre-commit guardrail checks + 1 run_suites medium

            # Repeat certify is an instant cache hit
            runner_repeat = RecordingRunner()
            rc2, summary2 = dc.cmd_certify(estate, env=standalone_env, runner=runner_repeat)
            self.assertEqual(rc2, 0)
            self.assertTrue(summary2["cached"])
            self.assertEqual(len(runner_repeat.calls), 0)

            # Inside deploy context (`W0M_DEPLOY_LOGGED=1`), preflight + guardrails + test all skip in 0 calls
            runner_deploy = RecordingRunner()
            self.assertEqual(dc.cmd_preflight(estate, env=deploy_env, runner=runner_deploy), 0)
            self.assertEqual(dc.cmd_guardrails(estate, env=deploy_env, runner=runner_deploy), 0)
            self.assertEqual(dc.cmd_test(estate, level="medium", env=deploy_env, runner=runner_deploy), 0)
            self.assertEqual(len(runner_deploy.calls), 0)

            # Standalone outside deploy context ALWAYS runs guardrails and test uncached
            runner_manual = RecordingRunner()
            self.assertEqual(dc.cmd_guardrails(estate, env=standalone_env, runner=runner_manual), 0)
            self.assertEqual(dc.cmd_test(estate, level="medium", env=standalone_env, runner=runner_manual), 0)
            self.assertEqual(len(runner_manual.calls), 4)

    def test_red_probe_dirty_tracked_file_refuses_certify_and_misses_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            estate = _make_fake_estate(tmp)
            cache_dir = tmp / "cache"
            deploy_env = {"W0M_DEPLOY_CERT_CACHE_DIR": str(cache_dir), "W0M_DEPLOY_LOGGED": "1"}

            # Certify clean first
            self.assertEqual(dc.cmd_certify(estate, env=deploy_env, runner=RecordingRunner())[0], 0)

            # Dirty a tracked file in w0m-api without committing
            (estate / "w0m-api" / "README.md").write_text("uncommitted edit\n", encoding="utf-8")

            rc_dirty, detail = dc.cmd_certify(estate, env=deploy_env, runner=RecordingRunner())
            self.assertEqual(rc_dirty, 1)
            self.assertEqual(detail["reason"], "dirty_tree")
            self.assertEqual(detail["dirty_repos"], ["w0m-api"])

            # Deploy-local on dirty tree MUST NOT hit cached clean certificate
            runner_dirty = RecordingRunner()
            self.assertEqual(dc.cmd_preflight(estate, env=deploy_env, runner=runner_dirty), 0)
            self.assertEqual(dc.cmd_guardrails(estate, env=deploy_env, runner=runner_dirty), 0)
            self.assertEqual(dc.cmd_test(estate, level="medium", env=deploy_env, runner=runner_dirty), 0)
            self.assertGreaterEqual(len(runner_dirty.calls), 5)

    def test_red_probe_member_commit_drift_and_policy_drift_invalidate_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            estate = _make_fake_estate(tmp)
            cache_dir = tmp / "cache"
            deploy_env = {"W0M_DEPLOY_CERT_CACHE_DIR": str(cache_dir), "W0M_RELEASE_WORKTREE": "1"}

            s0 = dc.inspect_tree_set(estate)
            self.assertEqual(dc.cmd_certify(estate, env=deploy_env, runner=RecordingRunner())[0], 0)

            # 1. Advance w0m-api by 1 commit while umbrella & w0m-web stay unchanged -> digest MUST change -> MISS
            (estate / "w0m-api" / "README.md").write_text("v2\n", encoding="utf-8")
            _commit_all(estate / "w0m-api", "feat: bump api")
            s1 = dc.inspect_tree_set(estate)
            self.assertNotEqual(s0.tree_set_digest, s1.tree_set_digest)
            self.assertEqual(dc.load_cert_record(s1, deploy_env), {})

            # Certify s1, then mutate policy digest calculation via test-suites.json commit -> MISS
            self.assertEqual(dc.cmd_certify(estate, env=deploy_env, runner=RecordingRunner())[0], 0)
            (estate / "w0m-web" / "project" / "test-suites.json").write_text(
                json.dumps({"suites": [{"name": "s2", "recipe": "r2", "tier": "offline", "blocking": True}]}) + "\n",
                encoding="utf-8",
            )
            _commit_all(estate / "w0m-web", "chore: update suites")
            s2 = dc.inspect_tree_set(estate)
            self.assertNotEqual(s1.policy_digest, s2.policy_digest)
            self.assertEqual(dc.load_cert_record(s2, deploy_env), {})

    def test_uncached_deploy_deduplicates_prepush_and_seals_certificate_for_retry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            estate = _make_fake_estate(tmp)
            cache_dir = tmp / "cache"
            deploy_env = {"W0M_DEPLOY_CERT_CACHE_DIR": str(cache_dir), "W0M_DEPLOY_LOGGED": "1"}

            runner = RecordingRunner()
            # 1. Uncached deploy: preflight runs --prepush
            self.assertEqual(dc.cmd_preflight(estate, env=deploy_env, runner=runner), 0)
            self.assertIn("--prepush", runner.calls[-1][0])

            # 2. Guardrails run once
            self.assertEqual(dc.cmd_guardrails(estate, env=deploy_env, runner=runner), 0)

            # 3. Test runs with --skip-prepush (deduplicating the 16 prepush suites!) and seals certified=True
            self.assertEqual(dc.cmd_test(estate, level="medium", env=deploy_env, runner=runner), 0)
            self.assertIn("--skip-prepush", runner.calls[-1][0])

            state = dc.inspect_tree_set(estate)
            rec = dc.load_cert_record(state, deploy_env)
            self.assertTrue(rec.get("certified"))

            # 4. Subsequent retry (e.g. `just release-deploy`) hits cache across all 3 stages in 0 calls!
            retry_runner = RecordingRunner()
            self.assertEqual(dc.cmd_preflight(estate, env=deploy_env, runner=retry_runner), 0)
            self.assertEqual(dc.cmd_guardrails(estate, env=deploy_env, runner=retry_runner), 0)
            self.assertEqual(dc.cmd_test(estate, level="medium", env=deploy_env, runner=retry_runner), 0)
            self.assertEqual(len(retry_runner.calls), 0)

            # 5. W0M_DEPLOY_CERT_RESET=1 forces re-execution, and invalid values fail closed
            reset_env = {**deploy_env, "W0M_DEPLOY_CERT_RESET": "1"}
            reset_runner = RecordingRunner()
            self.assertEqual(dc.cmd_preflight(estate, env=reset_env, runner=reset_runner), 0)
            self.assertEqual(len(reset_runner.calls), 1)

            with self.assertRaises(SystemExit):
                dc.reset_requested({"W0M_DEPLOY_CERT_RESET": "invalid"})

    def test_run_suites_skip_prepush_partitions_medium_cleanly(self) -> None:
        suites = rs.load_registry()
        pre = rs.select_suites(suites, "offline", prepush=True, level="medium")
        full_med = rs.select_suites(suites, "offline", prepush=False, level="medium", skip_prepush=False)
        rest_med = rs.select_suites(suites, "offline", prepush=False, level="medium", skip_prepush=True)

        pre_names = {s["name"] for s in pre}
        full_names = {s["name"] for s in full_med}
        rest_names = {s["name"] for s in rest_med}

        self.assertTrue(pre_names)
        self.assertEqual(pre_names & rest_names, set())
        self.assertEqual(pre_names | rest_names, full_names)


if __name__ == "__main__":
    res = unittest.main(verbosity=1, exit=False).result
    if res.wasSuccessful():
        print(f"  ✅ test-deploy-cert: {res.testsRun} check(s) passed")
        raise SystemExit(0)
    raise SystemExit(1)
