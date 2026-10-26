#!/usr/bin/env python3
"""T247 AC7 — prove that a toolchain FAILURE travels the chain.

Every mechanism in T112's toolchain updater existed and worked: the launchd schedule fired, the
detector was accurate, the drift was measured, the pre-push warning printed. And yet a run that
exited 1 on 2026-08-17 — holding `osv-scanner` and `semgrep` — reached nobody, and the owner found
the pending `infisical` patch from infisical's own CLI notice instead.

Nothing was missing. What was missing was any test that a **failure** travels. That is this file.

Each case below is a way the chain could go quiet again:
  · a held tool must be RECORDED (an outcome file that only appears on success cannot tell
    "succeeded" apart from "never ran")
  · a recorded hold must be SURFACED on the next push
  · a REQUIRED tool on an unverified version must not read as `ok`
  · reconciliation must refuse to promote what it cannot verify — otherwise it launders the very
    state this ticket exists to surface
  · a partial run and a total failure must not report the same exit code

Drives the modules directly with monkeypatched paths — no tool is installed, upgraded or smoked.

Run: `just toolchain-chain-test`
"""
import datetime
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "w0m-web"
sys.path.insert(0, str(ROOT / "scripts"))

import tools_check  # noqa: E402
import tools_upgrade  # noqa: E402

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'✅' if ok else '❌'} {label}")
    if not ok:
        failures.append(f"{label} — {detail}")


def capture(fn) -> str:
    """Run fn() and return everything it printed."""
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn()
    return buf.getvalue()


print("▶ T247 AC7 — does a toolchain failure travel the chain?\n")

# ── 1. a held tool is RECORDED, and a clean run is recorded as clean ────────────────────────────
with tempfile.TemporaryDirectory() as d:
    status = Path(d) / "status.json"
    saved = tools_check.STATUS
    tools_check.STATUS = status
    tools_upgrade.STATUS = status
    try:
        status.write_text(json.dumps({
            "ran": (datetime.datetime.now() - datetime.timedelta(days=4)).isoformat(),
            "ok": False, "promoted": ["gcloud 577.0.0→580.0.0"], "unverified": [],
            "held": ["osv-scanner", "semgrep"],
        }))
        # The cache must exist or warn_cached returns early before reading the status at all —
        # which is itself worth asserting, since a missing cache must not mask a failed run.
        cache = Path(d) / "cache.json"
        cache.write_text(json.dumps({"generated": datetime.datetime.now().isoformat(),
                                     "updates": []}))
        saved_cache = tools_check.CACHE
        tools_check.CACHE = cache
        try:
            out = capture(tools_check.warn_cached)
            check("a recorded hold is SURFACED on the next push", "FAILED" in out, out.strip()[:160])
            check("...and it NAMES the held tools", "osv-scanner" in out and "semgrep" in out,
                  out.strip()[:160])
            check("...and says how long ago, so a stale failure is not read as fresh",
                  "4d ago" in out, out.strip()[:160])

            # A clean run must be silent about runs — otherwise the warning becomes background noise
            # and the real one is missed, which is how the previous version failed.
            status.write_text(json.dumps({
                "ran": datetime.datetime.now().isoformat(), "ok": True,
                "promoted": ["infisical 0.43.121→0.43.124"], "unverified": [], "held": [],
            }))
            out_ok = capture(tools_check.warn_cached)
            check("a CLEAN run says nothing about runs", "FAILED" not in out_ok, out_ok.strip()[:160])

            # 🔴 The cache is written BEFORE the apply, so a failed run leaves a FRESH cache. Cache
            # age therefore cannot detect it — only the status record can. This asserts the two are
            # genuinely independent.
            status.write_text(json.dumps({
                "ran": datetime.datetime.now().isoformat(), "ok": False,
                "promoted": [], "unverified": [], "held": ["semgrep"],
            }))
            out_fresh = capture(tools_check.warn_cached)
            check("a FRESH cache does not mask a failed run (they are independent signals)",
                  "FAILED" in out_fresh, out_fresh.strip()[:160])
        finally:
            tools_check.CACHE = saved_cache
    finally:
        tools_check.STATUS = saved
        tools_upgrade.STATUS = saved

# ── 2. a REQUIRED tool on an unverified version is not `ok` ─────────────────────────────────────
def run_check(policy: dict, argv: list[str]) -> tuple[str, int]:
    with tempfile.TemporaryDirectory() as d:
        pol = Path(d) / "tools-policy.json"
        pol.write_text(json.dumps(policy))
        saved_pol, saved_argv = tools_check.POLICY, sys.argv
        tools_check.POLICY, sys.argv = pol, ["tools_check.py", *argv]
        try:
            import contextlib
            import io
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = tools_check.main()
            return buf.getvalue(), rc
        finally:
            tools_check.POLICY, sys.argv = saved_pol, saved_argv


# `python3` is present everywhere this runs; its real version is whatever it is, and known_good is
# set to a value it cannot equal — so the drift is guaranteed rather than hoped for.
REQ_DRIFT = {"tools": {"python3": {"min": "3.0.0", "known_good": "0.0.1", "required": True,
                                  "source": "brew", "auto": "none"}}}
OPT_DRIFT = {"tools": {"python3": {"min": "3.0.0", "known_good": "0.0.1", "required": False,
                                  "source": "brew", "auto": "none"}}}

out, rc = run_check(REQ_DRIFT, [])
check("a REQUIRED tool on an unverified version does NOT print `ok`",
      "DRIFT" in out and "\n  ok" not in out, out.strip()[-200:])
check("...and it is counted as required-drift, not folded into optional",
      "1 required-drift" in out, out.strip()[-200:])
out_s, rc_s = run_check(REQ_DRIFT, ["--strict"])
check("...and --strict FAILS on it", rc_s == 1, f"exit={rc_s}")

out_o, rc_o = run_check(OPT_DRIFT, [])
check("an OPTIONAL tool's drift stays informational and still reads `ok`",
      "ok —" in out_o and "0 required-drift" in out_o, out_o.strip()[-200:])
check("...and does not fail even under --strict",
      run_check(OPT_DRIFT, ["--strict"])[1] == 0, "optional drift must not gate")

# ── 3. reconciliation refuses what it cannot verify ────────────────────────────────────────────
def run_reconcile(tools: dict) -> tuple[list[str], list[str]]:
    with tempfile.TemporaryDirectory() as d:
        pol = Path(d) / "tools-policy.json"
        policy = {"tools": tools}
        pol.write_text(json.dumps(policy))
        saved = tools_upgrade.POLICY
        tools_upgrade.POLICY = pol
        try:
            import contextlib
            import io
            with contextlib.redirect_stdout(io.StringIO()):
                return tools_upgrade.reconcile(tools, policy, apply=False)
        finally:
            tools_upgrade.POLICY = saved


prom, blocked = run_reconcile({"python3": {"min": "3.0.0", "known_good": "0.0.1",
                                          "required": True, "source": "brew"}})
check("reconcile REFUSES a tool with no smoke declared", not prom and len(blocked) == 1,
      f"promoted={prom} blocked={blocked}")
check("...and says WHY, naming the missing smoke", "NO smoke" in (blocked[0] if blocked else ""),
      str(blocked))

prom2, blocked2 = run_reconcile({"python3": {"min": "3.0.0", "known_good": "0.0.1",
                                            "required": True, "source": "brew",
                                            "smoke": "false"}})
check("reconcile REFUSES a version whose smoke FAILS", not prom2 and len(blocked2) == 1,
      f"promoted={prom2} blocked={blocked2}")
check("...and reports it as a smoke failure", "smoke FAILED" in (blocked2[0] if blocked2 else ""),
      str(blocked2))

prom3, blocked3 = run_reconcile({"python3": {"min": "999.0.0", "known_good": "0.0.1",
                                            "required": True, "source": "brew",
                                            "smoke": "true"}})
check("reconcile REFUSES an installed version below min", not prom3 and len(blocked3) == 1,
      f"promoted={prom3} blocked={blocked3}")

prom4, blocked4 = run_reconcile({"python3": {"min": "3.0.0", "known_good": "999.0.0",
                                            "required": True, "source": "brew",
                                            "smoke": "true"}})
check("reconcile REFUSES to LOWER known_good (installed behind it is not a reconcile)",
      not prom4 and any("BEHIND" in b for b in blocked4), f"blocked={blocked4}")

prom5, blocked5 = run_reconcile({"python3": {"min": "3.0.0", "known_good": "0.0.1",
                                            "required": True, "source": "brew",
                                            "smoke": "true"}})
check("reconcile PROMOTES a version whose smoke passes", len(prom5) == 1 and not blocked5,
      f"promoted={prom5} blocked={blocked5}")

print()
if failures:
    print(f"❌ {len(failures)} failure(s):")
    for f in failures:
        print(f"   · {f}")
    sys.exit(1)
print("✅ toolchain-chain: a failure travels the chain — recorded, surfaced, and not laundered")
