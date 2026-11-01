from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "w0m-web"


def test_t480_no_unjustified_wait_for_timeout_in_gauge_tests() -> None:
    """T480 AC2: zero unjustified waitForTimeout calls across w0m-web/tests."""
    res = subprocess.run(
        [
            "ast-grep",
            "scan",
            "--custom-languages",
            "allow",
            "-c",
            "project/ast-grep/sgconfig.yml",
            "--filter",
            "^gauge-no-unjustified-wait-for-timeout$",
            "tests/",
        ],
        cwd=str(WEB),
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"Unjustified waitForTimeout found:\n{res.stdout}\n{res.stderr}"


def test_t480_timeouts_policy_and_fail_fast_guards_via_node() -> None:
    """T480 AC1, AC3, AC4, AC5b: verify stage-aware timeouts, auth bounce guard, 5xx guard, dev-server monitor, and watchdog."""
    script = """
const assert = require("node:assert/strict");
const {
  getTimeouts,
  assertRecoverablePageState,
  recordFatalDevServerError,
  clearFatalDevServerError,
  assertDevServerHealthy,
  ScenarioWatchdog,
} = require("./tests/support/timeouts");

(async () => {
  clearFatalDevServerError();

  // AC3: stage-aware timeout policy
  process.env.W0M_E2E_LOCAL = "1";
  const localPolicy = getTimeouts();
  assert.equal(localPolicy.stage, "local");
  assert.equal(localPolicy.navigationMs, 15000);
  assert.equal(localPolicy.stepWaitMs, 8000);
  assert.equal(localPolicy.actionMs, 5000);
  assert.equal(localPolicy.watchdogMs, 45000);

  delete process.env.W0M_E2E_LOCAL;
  process.env.E2E_LOCAL = "false";
  process.env.W0M_STAGE = "beta";
  delete process.env.PUBLIC_SUPABASE_URL;
  delete process.env.SUPABASE_URL;
  const livePolicy = getTimeouts();
  assert.equal(livePolicy.stage, "live");
  assert.equal(livePolicy.navigationMs, 30000);
  assert.equal(livePolicy.stepWaitMs, 15000);
  assert.equal(livePolicy.watchdogMs, 90000);

  // AC1: fail-fast on authenticated bounce to /login or /me/account?mfa_required=1
  const bouncedPage = {
    isClosed: () => false,
    url: () => "http://localhost:4325/login?reason=expired",
  };
  await assert.rejects(
    () =>
      assertRecoverablePageState(bouncedPage, {
        requireSession: true,
        requestedUrl: "http://localhost:4325/admin/leads",
      }),
    /redirected to \\/login\\?reason=expired/
  );

  const mfaBouncedPage = {
    isClosed: () => false,
    url: () => "http://localhost:4325/me/account?mfa_required=1",
  };
  await assert.rejects(
    () =>
      assertRecoverablePageState(mfaBouncedPage, {
        requireSession: true,
        requestedUrl: "http://localhost:4325/admin",
      }),
    /redirected to \\/me\\/account\\?mfa_required=1/
  );

  // AC1: intentional visit to /login is allowed
  await assert.doesNotReject(() =>
    assertRecoverablePageState(bouncedPage, {
      requireSession: true,
      requestedUrl: "http://localhost:4325/login",
    })
  );

  // AC1: HTTP 5xx fails fast when not explicitly expected
  const okPage = { isClosed: () => false, url: () => "http://localhost:4325/admin" };
  await assert.rejects(
    () =>
      assertRecoverablePageState(okPage, {
        requireSession: true,
        responseStatus: 500,
        allowErrorStatus: false,
      }),
    /Unrecoverable HTTP 500 response/
  );

  // AC5b: broken dev-server sentinel aborts across workers immediately
  recordFatalDevServerError("The file does not exist at .../.vite/deps_ssr/chunk-XYZ.js");
  assert.throws(() => assertDevServerHealthy(), /Dev server broken mid-run/);
  clearFatalDevServerError();

  // AC4: ScenarioWatchdog names spec, scenario, and step on stall
  const wd = new ScenarioWatchdog(200);
  wd.start("specs/admin.spec", "Create lead");
  wd.heartbeat("When I click save");
  await new Promise((r) => setTimeout(r, 350));
  assert.throws(
    () => wd.check(),
    /Stalled run detected.*spec="specs\\/admin\\.spec" scenario="Create lead" step="When I click save"/
  );
  wd.stop();
  console.log("T480 node assertions passed");
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
"""
    res = subprocess.run(
        ["./node_modules/.bin/ts-node-transpile-only", "-e", script],
        cwd=str(WEB),
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"Node probe failed:\n{res.stdout}\n{res.stderr}"
    assert "T480 node assertions passed" in res.stdout


def test_t480_local_multithreading_and_parallel_recipe_enabled() -> None:
    """T480 AC6: local default.properties enables multithreading and justfile wires --parallel."""
    props = (WEB / "env" / "local" / "default.properties").read_text(encoding="utf-8")
    assert "enable_multithreading = true" in props
    justfile_text = (ROOT / "justfile").read_text(encoding="utf-8")
    assert "--parallel -n ${W0M_E2E_WORKERS:-4}" in justfile_text
    assert 'pgrep -f "astro check|vite build"' in justfile_text
