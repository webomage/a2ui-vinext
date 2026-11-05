#!/usr/bin/env python3
"""Unit tests for w0m Commit-Bound Pre-Push Checkpoint Runner (T375).

Validates:
- Commit-hash bound state isolation
- Instant skip on fully certified commits
- Auto-continue from the exact failed step
- Arbitrary step resumption via --from / PREPUSH_FROM
- Full reset via --reset / PREPUSH_RESET
- Graceful recovery from corrupted checkpoint files
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RUNNER = ROOT / "scripts" / "prepush_runner.py"
sys.path.insert(0, str(ROOT / "scripts"))


class TestPrepushRunner(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="w0m-test-prepush-")
        self.env = dict(os.environ)
        self.env["W0M_PREPUSH_CACHE_DIR"] = self.tmp_dir
        self.repo = "testrepo"
        self.commit_a = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        self.commit_b = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def run_cmd(self, *args, env_extra: dict | None = None) -> subprocess.CompletedProcess:
        env = dict(self.env)
        if env_extra:
            env.update(env_extra)
        cmd = [sys.executable, str(RUNNER), "--repo", self.repo, *args]
        return subprocess.run(cmd, capture_output=True, text=True, env=env)

    def test_fresh_commit_not_certified(self):
        res = self.run_cmd("check-certified", "--commit", self.commit_a)
        self.assertEqual(res.returncode, 1)

    def test_step_begin_and_cached_skip(self):
        # First call: should run (exit 0)
        res1 = self.run_cmd("step-begin", "identity", "w0m identity gate", "--commit", self.commit_a)
        self.assertEqual(res1.returncode, 0)
        self.assertIn("⏳ [testrepo] Pre-push: w0m identity gate...", res1.stdout)

        # Mark step as passed
        res_pass = self.run_cmd("step-pass", "identity", "--duration", "0.5", "--commit", self.commit_a)
        self.assertEqual(res_pass.returncode, 0)

        # Second call on same commit: should be skipped (exit 1)
        res2 = self.run_cmd("step-begin", "identity", "w0m identity gate", "--commit", self.commit_a)
        self.assertEqual(res2.returncode, 1)
        self.assertIn("✓ [cached pass] w0m identity gate (0.5s)", res2.stdout)

    def test_auto_continue_from_failed_step(self):
        # Step 1 passes
        self.assertEqual(self.run_cmd("step-begin", "identity", "--commit", self.commit_a).returncode, 0)
        self.assertEqual(self.run_cmd("step-pass", "identity", "--commit", self.commit_a).returncode, 0)

        # Step 2 fails
        self.assertEqual(self.run_cmd("step-begin", "typecheck", "--commit", self.commit_a).returncode, 0)
        res_fail = self.run_cmd("step-fail", "typecheck", "--exit-code", "1", "--commit", self.commit_a)
        self.assertEqual(res_fail.returncode, 0)
        self.assertIn("checkpoint recorded failure at step 'typecheck'", res_fail.stderr)

        # Second run on same commit:
        # Step 1 should skip (exit 1)
        res_step1 = self.run_cmd("step-begin", "identity", "--commit", self.commit_a)
        self.assertEqual(res_step1.returncode, 1)
        self.assertIn("cached pass", res_step1.stdout)

        # Step 2 should auto-resume and run (exit 0)
        res_step2 = self.run_cmd("step-begin", "typecheck", "--commit", self.commit_a)
        self.assertEqual(res_step2.returncode, 0)
        self.assertIn("⏳ [testrepo] Pre-push: type checks (astro check)...", res_step2.stdout)

    def test_full_certification_and_instant_skip(self):
        from prepush_runner import STEP_IDS
        # Pass all steps
        for step_id in STEP_IDS:
            self.run_cmd("step-pass", step_id, "--commit", self.commit_a)

        # Now check-certified should exit 0 immediately
        res = self.run_cmd("check-certified", "--commit", self.commit_a)
        self.assertEqual(res.returncode, 0)
        self.assertIn("is already fully certified", res.stdout)
        self.assertIn("Skipping", res.stdout)

    def test_prepush_from_override(self):
        from prepush_runner import STEP_IDS
        # Pass all steps
        for step_id in STEP_IDS:
            self.run_cmd("step-pass", step_id, "--commit", self.commit_a)

        # With --from=license-check, check-certified should return 1 (do not skip all)
        res_check = self.run_cmd("check-certified", "--from", "license-check", "--commit", self.commit_a)
        self.assertEqual(res_check.returncode, 1)

        # Steps before license-check should skip (exit 1)
        res_before = self.run_cmd("step-begin", "typecheck", "--from", "license-check", "--commit", self.commit_a)
        self.assertEqual(res_before.returncode, 1)
        self.assertIn("cached pass", res_before.stdout)

        # license-check should run (exit 0)
        res_target = self.run_cmd("step-begin", "license-check", "--from", "license-check", "--commit", self.commit_a)
        self.assertEqual(res_target.returncode, 0)
        self.assertIn("⏳", res_target.stdout)

    def test_prepush_reset(self):
        from prepush_runner import STEP_IDS
        for step_id in STEP_IDS:
            self.run_cmd("step-pass", step_id, "--commit", self.commit_a)

        # Reset flag forces step 1 to run
        res = self.run_cmd("step-begin", "identity", "--reset", "--commit", self.commit_a)
        self.assertEqual(res.returncode, 0)
        self.assertIn("⏳", res.stdout)

    def test_commit_isolation(self):
        from prepush_runner import STEP_IDS
        for step_id in STEP_IDS:
            self.run_cmd("step-pass", step_id, "--commit", self.commit_a)

        # Commit A is certified
        self.assertEqual(self.run_cmd("check-certified", "--commit", self.commit_a).returncode, 0)

        # Commit B is not certified
        self.assertEqual(self.run_cmd("check-certified", "--commit", self.commit_b).returncode, 1)

        # Step 1 on Commit B must run
        self.assertEqual(self.run_cmd("step-begin", "identity", "--commit", self.commit_b).returncode, 0)

    def test_corrupt_checkpoint_recovery(self):
        cp_file = Path(self.tmp_dir) / f"{self.repo}-{self.commit_a}.json"
        cp_file.write_text("{corrupted json", encoding="utf-8")

        # Must not crash, should fall back to clean run (exit 0)
        res = self.run_cmd("step-begin", "identity", "--commit", self.commit_a)
        self.assertEqual(res.returncode, 0)
        self.assertIn("Warning: corrupted checkpoint file", res.stderr)

    def test_status_output(self):
        self.run_cmd("step-pass", "identity", "--duration", "1.2", "--commit", self.commit_a)
        self.run_cmd("step-fail", "typecheck", "--exit-code", "2", "--duration", "3.4", "--commit", self.commit_a)

        res = self.run_cmd("status", "--commit", self.commit_a)
        self.assertEqual(res.returncode, 0)
        self.assertIn("FAILED", res.stdout)
        self.assertIn("Runmark Digest", res.stdout)
        self.assertIn("Cache Reason", res.stdout)
        self.assertIn("typecheck", res.stdout)
        self.assertIn("1.2s", res.stdout)
        self.assertIn("3.4s", res.stdout)

    def test_runmark_digest_and_why_not(self):
        from prepush_runner import STEP_IDS, compute_runmark_digest, why_not
        os.environ["W0M_PREPUSH_CACHE_DIR"] = self.tmp_dir

        digest1 = compute_runmark_digest()
        digest2 = compute_runmark_digest([("identity", "gate")])
        self.assertEqual(len(digest1), 12)
        self.assertNotEqual(digest1, digest2)

        # Unstarted commit explains why_not
        r0 = why_not(self.repo, self.commit_a)
        self.assertIn("no checkpoint recorded", r0)

        # Pass all steps
        for step_id in STEP_IDS:
            self.run_cmd("step-pass", step_id, "--commit", self.commit_a)

        # Certified commit has empty why_not
        self.assertEqual(why_not(self.repo, self.commit_a), "")
        self.assertEqual(why_not(self.repo, self.commit_a, step_id="identity"), "")

        # Mutating runmark_digest in checkpoint invalidates certification with explicit reason
        cp_file = Path(self.tmp_dir) / f"{self.repo}-{self.commit_a}.json"
        cp_data = json.loads(cp_file.read_text(encoding="utf-8"))
        cp_data["runmark_digest"] = "000000000000"
        cp_file.write_text(json.dumps(cp_data), encoding="utf-8")

        r_mismatch = why_not(self.repo, self.commit_a)
        self.assertIn("runmark config digest mismatch", r_mismatch)
        self.assertEqual(self.run_cmd("check-certified", "--commit", self.commit_a).returncode, 1)

    def test_parallel_sibling_pass_retained_on_failure_and_resume(self):
        # Simulate a parallel gate group where w0m-audit passes, license-check fails,
        # and dep-licenses-check + emoji-check pass after license-check failed (T477 AC2).
        self.assertEqual(self.run_cmd("step-pass", "identity", "--commit", self.commit_a).returncode, 0)
        self.assertEqual(self.run_cmd("step-pass", "typecheck", "--commit", self.commit_a).returncode, 0)
        self.assertEqual(self.run_cmd("step-pass", "w0m-audit", "--commit", self.commit_a).returncode, 0)
        self.assertEqual(self.run_cmd("step-fail", "license-check", "--exit-code", "1", "--commit", self.commit_a).returncode, 0)
        self.assertEqual(self.run_cmd("step-pass", "dep-licenses-check", "--commit", self.commit_a).returncode, 0)
        self.assertEqual(self.run_cmd("step-pass", "emoji-check", "--commit", self.commit_a).returncode, 0)

        cp_file = Path(self.tmp_dir) / f"{self.repo}-{self.commit_a}.json"
        cp_data = json.loads(cp_file.read_text(encoding="utf-8"))
        self.assertEqual(cp_data["status"], "failed")
        self.assertEqual(cp_data["last_failed_step"], "license-check")

        # On resume, sibling steps that already passed in the parallel group skip as cached pass,
        # while the failed step (license-check) runs again.
        self.assertEqual(self.run_cmd("step-begin", "dep-licenses-check", "--commit", self.commit_a).returncode, 1)
        self.assertEqual(self.run_cmd("step-begin", "emoji-check", "--commit", self.commit_a).returncode, 1)
        self.assertEqual(self.run_cmd("step-begin", "license-check", "--commit", self.commit_a).returncode, 0)

    def test_run_typecheck_bounded_concurrency_and_fixed_order(self):
        web_root = ROOT / "w0m-web"
        # Pass case: prints all 4 apps in fixed package.json order (web, cp, demo, me)
        res_ok = self.run_cmd(
            "run-typecheck",
            "--concurrency",
            "3",
            "--web-root",
            str(web_root),
            env_extra={"W0M_TYPECHECK_CMD_TEMPLATE": "echo 'Result (10 files): - 0 errors - 0 warnings - 0 hints [{app}]'"},
        )
        self.assertEqual(res_ok.returncode, 0)
        positions = [res_ok.stdout.index(f"[typecheck:{app}]") for app in ("web", "cp", "demo", "me")]
        self.assertEqual(positions, sorted(positions))
        self.assertIn(
            "[typecheck:cp] scope: astro check covers .astro/.ts; 123 .svelte file(s) excluded by astro check -> gated by svelte-typecheck-ratchet",
            res_ok.stdout,
        )

        # Fail case: names every failing app and exits 1
        res_fail = self.run_cmd(
            "run-typecheck",
            "--concurrency",
            "3",
            "--web-root",
            str(web_root),
            env_extra={"W0M_TYPECHECK_CMD_TEMPLATE": "if [ '{app}' = 'cp' ] || [ '{app}' = 'me' ]; then exit 1; fi"},
        )
        self.assertEqual(res_fail.returncode, 1)
        self.assertIn("cp, me", res_fail.stderr)

    def test_host_ram_scaling_and_global_lock(self):
        from prepush_runner import (
            default_node_max_old_space_mb,
            default_typecheck_concurrency,
            host_total_ram_gib,
            typecheck_global_lock,
        )

        # Host RAM detection returns a positive float
        self.assertGreater(host_total_ram_gib(), 1.0)

        # <=8 GiB host (e.g. 5 GiB APU) scales to concurrency=1 and 2048 MB V8 heap
        self.assertEqual(default_typecheck_concurrency(5.0), 1)
        self.assertEqual(default_typecheck_concurrency(8.0), 1)
        self.assertEqual(default_node_max_old_space_mb(5.0), 2048)
        self.assertEqual(default_node_max_old_space_mb(8.0), 2048)

        # 12 GiB host scales to concurrency=2 and 4096 MB V8 heap
        self.assertEqual(default_typecheck_concurrency(12.0), 2)
        self.assertEqual(default_node_max_old_space_mb(12.0), 4096)

        # >=16 GiB host scales to concurrency=3 and 8192 MB V8 heap
        self.assertEqual(default_typecheck_concurrency(16.0), 3)
        self.assertEqual(default_node_max_old_space_mb(16.0), 8192)

        # Global flock context manager acquires and releases cleanly
        os.environ["W0M_PREPUSH_CACHE_DIR"] = self.tmp_dir
        with typecheck_global_lock():
            self.assertTrue((Path(self.tmp_dir) / "typecheck.lock").is_file())


class TestHookMatchesRegistry(unittest.TestCase):
    """T503: a step registered in prepush_runner.py but absent from the hook is certified without ever running (`step-pass` is only reached through the
    hook), and a step in the hook that is not registered is invisible to `status`. Both directions, and the fast-ratchet step must run the registry's tier."""

    HOOK = Path(__file__).resolve().parents[2] / "w0m-web" / ".husky" / "pre-push"

    def setUp(self):
        from prepush_runner import STEP_IDS
        self.ids = STEP_IDS
        self.text = self.HOOK.read_text()

    def test_every_registered_step_is_run_by_the_hook(self):
        import re
        begun = set(re.findall(r'step_begin "([a-z0-9-]+)"', self.text))
        self.assertEqual(sorted(set(self.ids) - begun), [], "registered but never begun by the hook")

    def test_every_step_the_hook_begins_is_registered(self):
        import re
        begun = set(re.findall(r'step_begin "([a-z0-9-]+)"', self.text))
        self.assertEqual(sorted(begun - set(self.ids)), [], "begun by the hook but not registered")

    def test_the_deploy_ratchet_step_runs_the_prepush_tier(self):
        i = self.text.index('step_begin "deploy-ratchets"')
        block = self.text[i:i + 900]
        self.assertIn("just test-prepush", block)
        self.assertIn("step_pass \"deploy-ratchets\"", block)

    def test_parallel_readonly_group_precedes_serial_state_check(self):
        pg_call = self.text.index("\nrun_parallel_readonly_gates\n")
        state_step = self.text.index('step_begin "state-check"')
        self.assertLess(pg_call, state_step, "state-check must run serially after run_parallel_readonly_gates (T477 AC2)")


if __name__ == "__main__":
    unittest.main()

