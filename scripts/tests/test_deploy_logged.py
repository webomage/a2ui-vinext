#!/usr/bin/env python3
"""Red probes for `deploy_logged.py`. Offline — no deploy is run.

The two properties that matter cannot be inspected, only exercised:
  · the redactor removes secret SHAPES from a transcript, and reports how many
  · a failing recipe still exits non-zero through the wrapper
A logger that swallowed either would turn a broken, leaky deploy into a clean green record.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

# 🔴 Never write fixtures into the real deploy-log directory. This suite ran on every `just test`
# and buried the estate's actual deploy record: 32 of 33 files were its own `__t210_no_such_recipe__`
# transcripts, and rotation was pruning real ones to keep them.
import os as _os, tempfile as _tf
_os.environ["W0M_DEPLOY_LOGS"] = _tf.mkdtemp(prefix="w0m-deploy-logs-test-")

# 🔴 Nor the real consent file (2026-10-04). deploy_logged.py ends with `confirm_step.py --clear` (T541), and this suite runs it as a subprocess twice. This suite runs
# INSIDE `just deploy-all`'s test tier, so without its own consent path each run unlinked the owner's LIVE consent about two minutes into the deploy, and `db-migrate`
# then asked a second time ("run directly, outside agreed root"). Same failure as 2026-08-16 (confirm_step.py, CONSENT), same cure.
_CONSENT_SENTINEL = Path(_tf.mkdtemp(prefix="w0m-consent-test-")) / "consent.json"
_os.environ["W0M_CONFIRM_CONSENT"] = str(_CONSENT_SENTINEL)


ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT / "w0m-web"
spec = importlib.util.spec_from_file_location("dl", ROOT / "scripts/deploy_logged.py")
dl = importlib.util.module_from_spec(spec); spec.loader.exec_module(dl)

fails = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global fails
    if not ok:
        fails += 1
    print(f"  {'✅' if ok else '❌'} {name}{'' if ok else f' — {detail}'}")


print("▶ deploy-logged red probes\n")

# ── the redactor must FIRE on each shape it claims to cover ───────────────────────────────────
# ⚠️ ASSEMBLED AT RUNTIME, never written as literals. A file containing a real-shaped JWT or a
# postgres URI with an inline password is a file gitleaks and semgrep block at pre-commit — and
# they did, on the first version of this probe. Both were right: a scanner cannot tell a fixture
# from a leak, and it should not try. Joining the parts keeps the redactor's input honest (it
# still sees the full shape at runtime) while leaving no contiguous match in the source.
_J = ".".join(["eyJhbGciOiJIUzI1NiJ9", "eyJzdWIiOiIxMjM0NTY3ODkwIn0", "dozjgNryP4J3jVmNHl0w5N"])
SAMPLES = {
    "supabase-key": "key is sb_" + "secret_AbCdEf0123456789xyz here",
    "jwt": "token " + _J,
    "bearer": "Authorization: Bearer " + "abcdef0123456789ABCDEF",
    "assigned": "SUPABASE_SERVICE_ROLE_KEY=" + "hunter2hunter2hunter2",
    "pg-url": "postgres" + "ql://postgres:" + "s3cr3tpw" + "@db.example.com:5432/postgres",
}
for label, sample in SAMPLES.items():
    out, counts = dl.redact(sample)
    check(f"redacts {label}", counts.get(label, 0) >= 1 and "redacted" in out,
          f"counts={counts} out={out!r}")

# the leaked VALUE must be gone, not merely annotated
out, _ = dl.redact(SAMPLES["assigned"])
check("the secret value itself is removed", "hunter2" not in out, out)
check("the variable NAME survives", "SUPABASE_SERVICE_ROLE_KEY" in out, out)

# ── and must NOT fire on ordinary deploy chatter ──────────────────────────────────────────────
BENIGN = [
    "Injecting 98 Infisical secrets into your application process",
    "Uploaded w0m-api (4.21 sec)",
    "https://api.webomage.com/health",
    "warning: 3 vulnerabilities found",
]
for line in BENIGN:
    _, counts = dl.redact(line)
    check(f"leaves benign line alone: {line[:38]}…", not counts, f"counts={counts}")

# ── the transcript is named after the release deploy_log RECORDED, not the first version printed ──
# Run 7's shape: the functions printed a second version first, the apps + deploy_log carried another.
_run7 = ("Deploying all functions (Version: 2026.09.24-1790227320)...\n"
         "Building apps/web (Version: 2026.09.24-1790226662)...\n"
         "📝 deploy_log: release @ 2026.09.24-1790226662\n")
_rel, _all = dl.release_of(_run7)
check("names the release deploy_log recorded, not the first version printed",
      _rel == "2026.09.24-1790226662", f"got {_rel}")
check("...and reports every distinct version, so a split stamp is visible", len(_all) == 2, f"{_all}")
_rel, _all = dl.release_of("> web@2026.09.18-1789776836 build\n" + _run7)
check("the package.json version pnpm prints is NOT counted as a release stamp",
      "2026.09.18-1789776836" not in _all and len(_all) == 2, f"{_all}")
_rel, _all = dl.release_of("Version: 2026.09.24-1790226662\n(no deploy_log row written)\n")
check("with no deploy_log row, the version the run printed still names it",
      _rel == "2026.09.24-1790226662" and _all == ["2026.09.24-1790226662"], f"{_rel} {_all}")

# ── ANSI and pty artefacts are stripped, content is not ───────────────────────────────────────
cleaned = dl.clean("Script started on x\r\n\x1b[32m✅ ok\x1b[0m\r\n\x04Script done on y\r\n")
check("strips ANSI, CR, ^D and script banners", cleaned.strip() == "✅ ok", repr(cleaned))

# ── the wrapper's teardown must never reach the real consent file (2026-10-04) ───────────────────
# Checked BEFORE any subprocess runs, and the suite stops here if it fails: running the wrapper unisolated is exactly what deletes a live deploy's consent.
_real_consent = Path(_tf.gettempdir()) / "w0m-confirm-consent.json"
if Path(_os.environ.get("W0M_CONFIRM_CONSENT", "")) in (Path(""), _real_consent):
    print("❌ W0M_CONFIRM_CONSENT is not isolated: refusing to run the wrapper, its teardown would delete the real consent")
    raise SystemExit(1)
_real_before = _real_consent.read_bytes() if _real_consent.exists() else None
_CONSENT_SENTINEL.write_text("{}", encoding="utf-8")

# ── a failing recipe must stay failed ─────────────────────────────────────────────────────────
# Exercised through the real entrypoint, against a recipe name that cannot exist.
proc = subprocess.run([sys.executable, str(ROOT / "scripts/deploy_logged.py"),
                       "__t210_no_such_recipe__"],
                      capture_output=True, text=True, cwd=ROOT)
check("a failing recipe exits non-zero through the wrapper", proc.returncode != 0,
      f"returncode={proc.returncode}")
check("and the failure is visible in the summary", "❌" in proc.stdout, proc.stdout[-200:])

# ── a non-deploy recipe mentioning a version must land as run-*.log, never deploy-*.log (T291) ──
test_log_dir = Path(_os.environ["W0M_DEPLOY_LOGS"])
_changelog = ROOT / "CHANGELOG.md"
_before = _changelog.read_bytes() if _changelog.exists() else None
proc_v = subprocess.run([sys.executable, str(ROOT / "scripts/deploy_logged.py"),
                         "version"],
                        capture_output=True, text=True, cwd=ROOT)
check("non-deploy recipe running 'version' exits zero", proc_v.returncode == 0,
      f"returncode={proc_v.returncode}")
# T430: a non-release run must never regenerate the real estate CHANGELOG.md (it did, and wrote it empty).
check("a non-release recipe leaves the real CHANGELOG.md untouched",
      (_changelog.read_bytes() if _changelog.exists() else None) == _before)
deploy_logs = list(test_log_dir.glob("deploy-*.log"))
run_logs = list(test_log_dir.glob("run-*.log"))
check("non-deploy recipe did NOT create a deploy-*.log", len(deploy_logs) == 0,
      f"found fake deploy logs: {[p.name for p in deploy_logs]}")
check("non-deploy recipe created a run-*.log instead", len(run_logs) >= 1,
      f"expected run-*.log, found: {[p.name for p in test_log_dir.iterdir()]}")

# ── T507: audit_transcript categorizes findings into structured sections ──
sample_log = (
    "[WARN] [vite] [INEFFECTIVE_DYNAMIC_IMPORT] module dynamically imported\n"
    "↳ error: recipe `forks-check` failed on line 4473 with exit code 1 (advisory)\n"
    "[Browser ERROR]: Failed to load resource: the server responded with a status of 503\n"
    "npm warn Unknown project config \"enable-pre-post-scripts\"\n"
    "Random trouble line with error occurred\n"
)
audit_res = dl.audit_transcript(sample_log)
check("categorizes build warnings", len(audit_res["build_warnings"]) == 1, repr(audit_res["build_warnings"]))
check("categorizes advisory suite failures", len(audit_res["advisory_failures"]) == 1, repr(audit_res["advisory_failures"]))
check("categorizes browser errors", len(audit_res["browser_errors"]) == 1, repr(audit_res["browser_errors"]))
check("categorizes tool chatter", len(audit_res["tool_chatter"]) == 1, repr(audit_res["tool_chatter"]))
check("categorizes other trouble", len(audit_res["other_trouble"]) == 1, repr(audit_res["other_trouble"]))

# ── T523 AC4 + T666 AC3: harmless Gauge summaries, WebGL/WebGPU driver warnings, and asset upload paths are excluded ──
harmless_and_real_log = (
    "Specifications:   2 executed  2 passed  0 failed  0 skipped\n"
    "Scenarios:        7 executed  7 passed  0 failed  0 skipped\n"
    "[Browser WARNING]: [.WebGL-0x1240065b500] GL Driver Message (OpenGL, Performance, GL_CLOSE_PATH_NV, High): GPU stall due to ReadPixels\n"
    " ✔[Browser WARNING]: No available adapters.\n"
    "Uploading asset (upwork-poller): supabase/functions/_shared/upwork-failure.ts\n"
    "npm warn Unknown env config \"verify-deps-before-run\". This will stop working in the next major version of npm.\n"
    "(Use `node --trace-deprecation ...` to show where the warning was created)\n"
    "Specifications:   2 executed  1 passed  1 failed  0 skipped\n"
    "Failed step: I should see the dashboard\n"
    "DeprecationWarning: custom application deprecation notice\n"
)
t523_res = dl.audit_transcript(harmless_and_real_log)
check(
    "T523 AC4 + T666 AC3: excludes Gauge 0-failed, WebGL/WebGPU adapter hints, asset upload filenames, and npm env chatter from other_trouble",
    len(t523_res["other_trouble"]) == 3
    and len(t523_res["tool_chatter"]) == 2
    and all(
        "0 failed" not in ln
        and "GL_CLOSE_PATH_NV" not in ln
        and "No available adapters" not in ln
        and "upwork-failure.ts" not in ln
        for ln in t523_res["other_trouble"]
    ),
    repr(t523_res),
)
check(
    "T523 AC4: still counts non-zero failed Gauge summary, failed step, and deprecation lines",
    any("1 failed" in ln for ln in t523_res["other_trouble"])
    and any("Failed step:" in ln for ln in t523_res["other_trouble"])
    and any("DeprecationWarning:" in ln for ln in t523_res["other_trouble"]),
    repr(t523_res["other_trouble"]),
)

# ── T523 AC5: release-to-release delta calculation and rise reporting ──
deltas_res = dl.compute_audit_deltas(
    {"browser_errors_count": 288, "other_trouble_count": 19, "build_warnings_count": 4},
    {"release": "2026.09.30-1790816882", "browser_errors_count": 0, "other_trouble_count": 19, "build_warnings_count": 4},
)
check(
    "T523 AC5: computes browser_errors_delta and flags rising_metrics against previous release",
    deltas_res["previous_release"] == "2026.09.30-1790816882"
    and deltas_res["browser_errors_delta"] == 288
    and deltas_res["other_trouble_delta"] == 0
    and any("browser_errors: 0 -> 288 (+288)" in m for m in deltas_res["rising_metrics"]),
    repr(deltas_res),
)

check("the wrapper's teardown cleared the ISOLATED consent file (the clear still fires)", not _CONSENT_SENTINEL.exists(), str(_CONSENT_SENTINEL))
_real_after = _real_consent.read_bytes() if _real_consent.exists() else None
check("and left the real consent file exactly as it was", _real_after == _real_before, "the real consent changed during this suite")

audit_latest = test_log_dir / "deploy-audit-latest.json"
check("creates deploy-audit-latest.json", audit_latest.exists(), f"missing {audit_latest}")
if audit_latest.exists():
    import json as _json
    audit_doc = _json.loads(audit_latest.read_text(encoding="utf-8"))
    check(
        "T668 AC3: deploy-audit-latest.json persists tool_chatter and other_trouble arrays alongside counts",
        isinstance(audit_doc.get("tool_chatter"), list)
        and isinstance(audit_doc.get("other_trouble"), list)
        and "tool_chatter_count" in audit_doc
        and "other_trouble_count" in audit_doc,
        repr(audit_doc),
    )

# ── T722 AC2: Transient Edge Function deploy 500s recovered by retry vs unrecovered failure ──
recovered_fn_log = (
    'unexpected deploy status 500: {"message":"Function deploy failed due to an internal error"}\n'
    'unexpected deploy status 500: {"message":"Function deploy failed due to an internal error"}\n'
    "Try rerunning the command with --debug to troubleshoot the error.\n"
    "  ↻ 2 of 64 function(s) not updated: submit-service-request telegram-webhook\n"
    "    retry 1/3 in 20s, 2 at a time\n"
    "Deployed Functions on project pqbbjgeapylcengbuvee: submit-service-request, telegram-webhook\n"
    "  ✅ all 64 function(s) updated on live.\n"
)
rec_audit = dl.audit_transcript(recovered_fn_log)
check(
    "T722 AC2: classifies self-healed Supabase Function 500 + retry lines into recovered_retries (0 other_trouble)",
    len(rec_audit["recovered_retries"]) == 5 and len(rec_audit["other_trouble"]) == 0,
    repr(rec_audit),
)

unrecovered_fn_log = (
    'unexpected deploy status 500: {"message":"Function deploy failed due to an internal error"}\n'
    "Try rerunning the command with --debug to troubleshoot the error.\n"
    "  ↻ 2 of 64 function(s) not updated: submit-service-request telegram-webhook\n"
    "    retry 3/3 in 120s, 2 at a time\n"
    "  ❌ 2 function(s) STILL not updated after 3 retries — live is MIXED: submit-service-request telegram-webhook\n"
)
unrec_audit = dl.audit_transcript(unrecovered_fn_log)
check(
    "T722 AC2 (RED): keeps 500 + retry lines in other_trouble when functions remain STILL not updated",
    len(unrec_audit["recovered_retries"]) == 0 and len(unrec_audit["other_trouble"]) >= 3,
    repr(unrec_audit),
)

clean_audit_path = test_log_dir / "clean-audit.json"
clean_audit_path.write_text(
    '{"release":"2026.11.11-1794417310","exit_code":0,"build_warnings_count":0,"browser_errors_count":0,"recovered_retries_count":4,"other_trouble_count":0}\n',
    encoding="utf-8",
)
proc_audit_ok = subprocess.run(
    [sys.executable, str(ROOT / "scripts/deploy_logged.py"), "--audit-check", "--audit-file", str(clean_audit_path)],
    capture_output=True,
    text=True,
    cwd=ROOT,
)
check("T722 AC2: --audit-check exits 0 on clean/recovered audit record", proc_audit_ok.returncode == 0, proc_audit_ok.stdout)

dirty_audit_path = test_log_dir / "dirty-audit.json"
dirty_audit_path.write_text(
    '{"release":"2026.11.11-1794417310","exit_code":0,"build_warnings_count":0,"browser_errors_count":0,"recovered_retries_count":0,"other_trouble_count":2,"other_trouble":["Middleware Error: Astro.locals.runtime.env"]}\n',
    encoding="utf-8",
)
proc_audit_bad = subprocess.run(
    [sys.executable, str(ROOT / "scripts/deploy_logged.py"), "--audit-check", "--audit-file", str(dirty_audit_path)],
    capture_output=True,
    text=True,
    cwd=ROOT,
)
check("T722 AC2 (RED): --audit-check exits 1 when unrecovered other_trouble > 0", proc_audit_bad.returncode == 1, proc_audit_bad.stdout)

# ── T734 AC2: check-guardrails zero-finding pass summaries vs real osv-scanner / ast-grep findings ──
guardrails_clean_log = (
    "Filtered 19 vulnerabilities from output\n"
    "No issues found\n"
    "Filtered 2 vulnerabilities from output\n"
    "No issues found\n"
    "[ast-grep] Checked 3 rules (w0m-no-bare-except-pass-py, w0m-no-eval-call-ts, w0m-no-env-fallback-chain) -> 0 finding(s) (0 error, 0 warning)\n"
)
gr_clean = dl.audit_transcript(guardrails_clean_log)
check(
    "T734 AC2: excludes osv-scanner Filtered N vulnerabilities and ast-grep 0 finding(s) pass summaries from other_trouble",
    len(gr_clean["other_trouble"]) == 0,
    repr(gr_clean),
)

guardrails_dirty_log = (
    "Filtered 19 vulnerabilities from output\n"
    "Total 1 package affected by 5 known vulnerabilities (0 Critical, 0 High, 4 Medium, 1 Low, 0 Unknown) from 1 ecosystem.\n"
    "5 vulnerabilities can be fixed.\n"
    "[ast-grep] Checked 3 rules (w0m-no-bare-except-pass-py, w0m-no-eval-call-ts, w0m-no-env-fallback-chain) -> 1 finding(s) (1 error, 0 warning)\n"
)
gr_dirty = dl.audit_transcript(guardrails_dirty_log)
check(
    "T734 AC2 (RED): still flags real osv-scanner vulnerability totals and non-zero ast-grep findings in other_trouble",
    len(gr_dirty["other_trouble"]) == 3
    and any("Total 1 package affected" in ln for ln in gr_dirty["other_trouble"])
    and any("5 vulnerabilities can be fixed" in ln for ln in gr_dirty["other_trouble"])
    and any("-> 1 finding(s)" in ln for ln in gr_dirty["other_trouble"]),
    repr(gr_dirty),
)

print("\n" + ("✅ all deploy-logged probes passed" if not fails
              else f"❌ {fails} probe(s) failed"))
raise SystemExit(1 if fails else 0)
