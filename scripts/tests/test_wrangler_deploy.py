#!/usr/bin/env python3
"""Offline unit & red-probe tests for scripts/wrangler_deploy.py (T639).

Verifies:
1. Clean exit 0 passes on attempt 1 without retry.
2. Cloudflare Workers Assets error `Completion token has already been consumed [code: 100312]`
   (observed in deploy-logs/run-2026.11.04-1793813884.log) triggers a fresh-session retry and recovers.
3. Non-transient errors (Authentication error [code: 10000], invalid config, syntax errors) fail closed
   immediately on attempt 1 with zero retries (AgDR-0025).
4. Exhausting max_attempts returns the underlying non-zero exit code loudly.
5. Every `wrangler deploy` call site in root `justfile` invokes `scripts/wrangler_deploy.py` while keeping
   literal `wrangler deploy` visible to `confirm_step.py`.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "wrangler_deploy.py"


def _run_wrapper(stub_code: str, state_file: Path, max_attempts: int = 3) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--max-attempts",
            str(max_attempts),
            "--backoff",
            "0",
            "--",
            sys.executable,
            "-c",
            stub_code,
            str(state_file),
        ],
        capture_output=True,
        text=True,
    )


class WranglerDeployRetryTests(unittest.TestCase):
    def test_clean_command_runs_once_and_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            counter = Path(tmp) / "count.txt"
            code = (
                "import pathlib, sys; p = pathlib.Path(sys.argv[1]); "
                "n = int(p.read_text()) + 1 if p.exists() else 1; p.write_text(str(n)); "
                "print('Deployed webomage-cp triggers')"
            )
            res = _run_wrapper(code, counter)
            self.assertEqual(res.returncode, 0)
            self.assertEqual(counter.read_text(), "1")
            self.assertIn("Deployed webomage-cp triggers", res.stdout)

    def test_retries_cloudflare_100312_completion_token_and_recovers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            counter = Path(tmp) / "count.txt"
            code = (
                "import pathlib, sys\n"
                "p = pathlib.Path(sys.argv[1])\n"
                "n = int(p.read_text()) + 1 if p.exists() else 1\n"
                "p.write_text(str(n))\n"
                "if n == 1:\n"
                "    sys.stderr.write('✘ [ERROR] A request to the Cloudflare API (/accounts/af20/workers/scripts/webomage-cp/versions) failed.\\n"
                "  Completion token has already been consumed [code: 100312]\\n')\n"
                "    raise SystemExit(1)\n"
                "print('Uploaded 0 of 0 assets; Deployed webomage-cp')\n"
            )
            res = _run_wrapper(code, counter)
            self.assertEqual(res.returncode, 0, msg=res.stderr)
            self.assertEqual(counter.read_text(), "2")
            self.assertIn("cloudflare-100312-completion-token", res.stderr)
            self.assertIn("wrangler deploy succeeded on attempt 2/3", res.stdout)

    def test_non_transient_auth_or_config_error_fails_closed_immediately(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            counter = Path(tmp) / "count.txt"
            code = (
                "import pathlib, sys\n"
                "p = pathlib.Path(sys.argv[1])\n"
                "n = int(p.read_text()) + 1 if p.exists() else 1\n"
                "p.write_text(str(n))\n"
                "sys.stderr.write('✘ [ERROR] Authentication error [code: 10000]\\n')\n"
                "raise SystemExit(1)\n"
            )
            res = _run_wrapper(code, counter)
            self.assertEqual(res.returncode, 1)
            self.assertEqual(counter.read_text(), "1", "non-transient errors must never retry")
            self.assertNotIn("retrying fresh session", res.stderr)

    def test_exhausted_transient_retries_exit_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            counter = Path(tmp) / "count.txt"
            code = (
                "import pathlib, sys\n"
                "p = pathlib.Path(sys.argv[1])\n"
                "n = int(p.read_text()) + 1 if p.exists() else 1\n"
                "p.write_text(str(n))\n"
                "sys.stderr.write('Completion token has already been consumed [code: 100312]\\n')\n"
                "raise SystemExit(1)\n"
            )
            res = _run_wrapper(code, counter, max_attempts=3)
            self.assertEqual(res.returncode, 1)
            self.assertEqual(counter.read_text(), "3")
            self.assertIn("failed after 3 attempt(s)", res.stderr)

    def test_root_justfile_wraps_all_five_wrangler_deploys(self) -> None:
        body = (ROOT / "justfile").read_text(encoding="utf-8")
        deploy_lines = [
            ln.strip()
            for ln in body.splitlines()
            if "pnpm exec wrangler deploy" in ln and not ln.lstrip().startswith("#")
        ]
        self.assertEqual(len(deploy_lines), 5, f"expected 5 wrangler deploy lines, got {len(deploy_lines)}")
        for ln in deploy_lines:
            self.assertIn(
                "scripts/wrangler_deploy.py",
                ln,
                f"unwrapped wrangler deploy line in root justfile: {ln}",
            )


if __name__ == "__main__":
    unittest.main()
