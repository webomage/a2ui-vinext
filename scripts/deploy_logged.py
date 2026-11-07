#!/usr/bin/env python3
"""Run a deploy recipe with the FULL transcript written to a file.

    just deploy-logged                 # the whole deploy
    just deploy-logged deploy-api      # one stage
    just deploy-logged --keep-raw ...  # also keep the unprocessed pty capture

Why this exists: the deploy prints more than a terminal scrollback holds, and the interesting parts
— wrangler's warnings, a failed sub-step, a stack trace — are exactly the ones that scroll away.
An agent cannot watch the console at all, so *"it deployed fine"* is otherwise an unverifiable claim.

🔑 **It uses `script(1)` rather than a pipe, and that is the whole design.**
  · A pipe would capture the output but **break the interactive confirms** (`_confirm` prompts on
    every deploy step) and strip the TTY, changing how wrangler and pnpm render.
  · A pipe also **masks the exit status** — `cmd | tee` reports *tee's* status, which is this
    estate's documented way of turning a failed command into a green log.
  `script` allocates a real pty, so prompts work and colour survives; measured on this machine, it
  **propagates the child's exit code** (verified with `sh -c 'exit 7'` → 7) and captures **both**
  stdout and stderr. The exit code is re-raised at the end rather than swallowed.

⚠️ **The transcript is scanned and redacted before it is written.** A deploy injects secrets through
`infisical run`, and while the CLIs are not supposed to echo them, a log is a file that outlives the
session — so this assumes they might and checks. Anything redacted is COUNTED and reported: a silent
redaction would be indistinguishable from a clean run, which is the failure mode this whole file
exists to avoid.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

WORKSPACE = Path(__file__).resolve().parents[1]  # @wom (estate root)
REPO = WORKSPACE / "w0m-web"                     # w0m-web/
# 🔴 Overridable, and it must be. This directory is the ESTATE'S RECORD of real deploys, and the
# probe suite writes here too — so on 2026-08-16 it held 33 files of which 32 were fixtures
# (`just __t210_no_such_recipe__`), the newest real transcript was two days old, and the monthly
# rotation was diligently rotating test output. A deploy failed three times that day and every
# diagnosis had to be reconstructed from wrangler's own logs, because the record did not exist.
# Tests point this at their own directory; nothing else may write here.
LOGS = Path(os.environ.get("W0M_DEPLOY_LOGS") or (WORKSPACE / "deploy-logs"))

ANSI = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]|\x1B\][^\x07]*\x07")

# 🔑 The release-version format is read from `.w0m/sdlc.json`, never restated here. That file says
# in as many words that a regex hardcoded elsewhere is "the second source of truth this ticket
# exists to prevent" — and a transcript named in a private format would be exactly that.
POLICY = WORKSPACE / ".w0m" / "sdlc.json"


def version_regex() -> re.Pattern[str]:
    pol_doc: dict[str, Any] = json.loads(POLICY.read_text())
    pol = pol_doc["versioning"]
    # anchored in the policy for whole-string matching; here it must match INSIDE a log line
    return re.compile(pol["regex"].lstrip("^").rstrip("$"))


def release_of(text: str) -> tuple[str | None, list[str]]:
    """(the release this transcript published, every distinct version it mentions).

    The release is the one `_log-deploy` recorded (`📝 deploy_log: release @ <v>`) — the transcript
    IS that row's record, so its name must match `deploy_log`. Only when no row was written does the
    first version printed stand in. Run 7 (2026-09-24) named its transcript after the FUNCTIONS'
    version, which `deploy_log` never held, because a nested `just` had minted a second one and it
    printed first; `changelog-drift` then reported a deploy that never existed.
    """
    rx = version_regex()
    # Only RELEASE stamps count: the deploy banners' `Version: <v>` and the deploy_log line. A bare
    # scan also matches the package.json version pnpm prints (`> web@2026.09.18-… build`), which
    # is a manifest field, not a release — counting it would warn on every deploy.
    stamped = re.compile(r"(?:Version: |release @ )(" + rx.pattern + ")")
    versions = list(dict.fromkeys(m.group(1) for m in stamped.finditer(text)))
    recorded = re.search(r"deploy_log: release @ (" + rx.pattern + ")", text)
    if recorded:
        return recorded.group(1), versions
    first = rx.search(text)
    return (versions[0] if versions else (first.group(0) if first else None)), versions


# Recipes that actually publish a release to production and stamp deploy_log (T291 AC1).
# Running any other recipe (e.g. `version`, `test`, `deploy-api`) through deploy_logged
# must NEVER produce a `deploy-<release>.log` transcript.
RELEASE_RECIPES: frozenset[str] = frozenset({"deploy", "_deploy-chain", "deploy-all", "_deploy-all-chain"})


def producer_version() -> str | None:
    """Ask the ONE declared producer. Never reconstruct the format — a second site that builds it
    is a second format waiting to diverge, which is what `just version-check` exists to catch."""
    r = subprocess.run(["just", "version"], cwd=WORKSPACE, capture_output=True, text=True)
    out = r.stdout.strip().splitlines()
    return out[-1].strip() if r.returncode == 0 and out else None

# Redaction is deliberately shape-based, not name-based: a value is dangerous because of what it
# looks like, and the name next to it is whatever the tool felt like printing.
SECRETS: list[tuple[str, re.Pattern[str]]] = [
    ("supabase-key",  re.compile(r"\bsb_(?:secret|publishable)_[A-Za-z0-9_\-]{8,}")),
    ("jwt",           re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}")),
    ("bearer",        re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{16,}")),
    # ⚠️ `KEY` is in this list because the first version listed TOKEN|SECRET|PASSWORD|APIKEY and
    # therefore did NOT match `SUPABASE_SERVICE_ROLE_KEY=…` — the single likeliest thing to leak
    # from a deploy in this estate. The red probe caught it; reading the pattern had not.
    ("assigned",      re.compile(r"(?i)\b([A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|CREDENTIAL|KEY))\s*[=:]\s*\S{8,}")),
    ("pg-url",        re.compile(r"postgres(?:ql)?://[^\s:]+:[^\s@]+@")),
]

# A step banner in the transcript. `just` echoes each recipe's own `@echo` lines, and the deploy's
# stages announce themselves, so this is a real structure rather than a guess.
# T257 AC2 — bracketed text markers segment the log exactly as the glyphs do. Both forms are
# accepted so producers can convert one at a time; the glyph branch goes only when the last
# producer has moved, in the same commit as the policy declaration.
STEP = re.compile(r"^\s*(?:[🔑✅❌📸🔍⏳▶]|\[(?:OK|FAIL|STEP|KEY|SHOT|SCAN|WAIT|RUN)\]|Deploying|Building|=== )")
TROUBLE = re.compile(r"(?i)\b(error|failed|failure|warn|warning|deprecat\w*|vulnerab\w*|cannot|refus\w*|denied|timeout|retry)\b")


def clean(raw: str) -> str:
    text = ANSI.sub("", raw)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # `script` writes a literal ^D and its own header/footer lines
    text = text.replace("\x04", "")
    return "\n".join(
        ln for ln in text.split("\n")
        if not ln.startswith(("Script started on", "Script done on"))
    )


def redact(text: str) -> tuple[str, dict[str, int]]:
    counts: dict[str, int] = {}
    for label, pat in SECRETS:
        def sub(m: re.Match[str]) -> str:
            counts[label] = counts.get(label, 0) + 1
            # Keep the assignment's NAME so the log still says which variable appeared.
            if label == "assigned":
                return f"{m.group(1)}=<redacted:{label}>"
            return f"<redacted:{label}>"
        text = pat.sub(sub, text)
    return text, counts


def audit_transcript(text: str) -> dict[str, list[str]]:
    """T507: Categorize findings in a deploy transcript into structured audit sections."""
    lines = text.split("\n")
    build_warnings: list[str] = []
    advisory_failures: list[str] = []
    browser_errors: list[str] = []
    tool_chatter: list[str] = []
    other_trouble: list[str] = []

    rx_build_warn = re.compile(
        r"(?:\[WARN\]\s*\[(?:vite|lightningcss|astro)\]|"
        r"\[lightningcss minify\]|"
        r"INEFFECTIVE_DYNAMIC_IMPORT|"
        r"didn't resolve at build time|"
        r"warning:\s*(?:unresolved|invalid|unknown|deprecat))",
        re.IGNORECASE,
    )
    rx_browser_err = re.compile(
        r"(?:\[Browser (?:ERROR|PageError|HTTP [45]\d\d)\]|"
        r"Failed to load resource: the server responded with a status of [45]\d\d|"
        r"Error while running audit's match function)",
        re.IGNORECASE,
    )
    rx_tool_chatter = re.compile(
        r"(?:npm warn Unknown (?:project|env) config|"
        r"\[DEP\d+\] DeprecationWarning|"
        r"^\(Use `node --trace-deprecation|"
        r"Updates are available\. Run `gauge update)",
        re.IGNORECASE,
    )
    rx_advisory = re.compile(
        r"(?:↳\s*error:\s*recipe\s*`[^`]+`\s*failed.*\(advisory\)|"
        r"❌\s*[\w-]+\s+\S+\s*check\(s\)\s*\(advisory\)|"
        r"advisory suite\(s\) failing)",
        re.IGNORECASE,
    )
    # T523 AC4 + T666 AC3 — Exclude harmless summary/driver/asset lines that match `TROUBLE` only by word shape:
    # 1. Gauge summary lines with 0 failures (`Specifications: 2 executed 2 passed 0 failed`)
    # 2. Chromium WebGL GPU driver performance hints (`[Browser WARNING]: ... GL Driver Message ... GL_CLOSE_PATH_NV`)
    # 3. Headless Chromium WebGPU adapter probe (`[Browser WARNING]: No available adapters.`)
    # 4. Supabase CLI asset upload paths whose filename contains `-failure.ts` (`Uploading asset (...): supabase/functions/...`)
    rx_harmless_trouble = re.compile(
        r"(?:^(?:Specifications|Scenarios):\s+\d+\s+executed\s+\d+\s+passed\s+0\s+failed\b|"
        r"\[Browser WARNING\]:.*GL Driver Message.*(?:GL_CLOSE_PATH_NV|ReadPixels|Performance)|"
        r"\[Browser (?:WARNING|Console)\]:\s*No available adapters\.|"
        r"^Uploading asset \([^)]+\):\s+supabase/functions/)",
        re.IGNORECASE,
    )

    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if rx_build_warn.search(s):
            build_warnings.append(s)
        elif rx_advisory.search(s):
            advisory_failures.append(s)
        elif rx_browser_err.search(s):
            browser_errors.append(s)
        elif rx_tool_chatter.search(s):
            tool_chatter.append(s)
        elif rx_harmless_trouble.search(s):
            continue
        elif TROUBLE.search(s):
            other_trouble.append(s)

    return {
        "build_warnings": build_warnings,
        "advisory_failures": advisory_failures,
        "browser_errors": browser_errors,
        "tool_chatter": tool_chatter,
        "other_trouble": other_trouble,
    }


def previous_release_audit(logs_dir: Path, current_release: str | None = None) -> dict[str, object] | None:
    """T523 AC5: Load the most recent prior `deploy-<release>.audit.json` to compare counts release-to-release."""
    if not logs_dir.is_dir():
        return None
    candidates = sorted(logs_dir.glob("deploy-*.audit.json"), key=lambda p: p.name, reverse=True)
    for path in candidates:
        if current_release and path.name == f"deploy-{current_release}.audit.json":
            continue
        try:
            data: Any = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("release"):
                return data
        except (OSError, ValueError):
            continue
    return None


def compute_audit_deltas(
    current: dict[str, object],
    previous: dict[str, object] | None,
) -> dict[str, object]:
    """T523 AC5: Compute release-to-release deltas for browser_errors, other_trouble, and build_warnings."""
    if not previous:
        return {
            "previous_release": None,
            "browser_errors_delta": None,
            "other_trouble_delta": None,
            "build_warnings_delta": None,
            "rising_metrics": [],
        }

    prev_rel = str(previous.get("release") or "")
    cur_br = int(str(current.get("browser_errors_count") or 0))
    prev_br = int(str(previous.get("browser_errors_count") or 0))
    cur_tr = int(str(current.get("other_trouble_count") or 0))
    prev_tr = int(str(previous.get("other_trouble_count") or 0))
    cur_bw = int(str(current.get("build_warnings_count") or 0))
    prev_bw = int(str(previous.get("build_warnings_count") or 0))

    br_delta = cur_br - prev_br
    tr_delta = cur_tr - prev_tr
    bw_delta = cur_bw - prev_bw

    rising: list[str] = []
    if br_delta > 0:
        rising.append(f"browser_errors: {prev_br} -> {cur_br} (+{br_delta})")
    if tr_delta > 0:
        rising.append(f"other_trouble: {prev_tr} -> {cur_tr} (+{tr_delta})")
    if bw_delta > 0:
        rising.append(f"build_warnings: {prev_bw} -> {cur_bw} (+{bw_delta})")

    return {
        "previous_release": prev_rel or None,
        "browser_errors_delta": br_delta,
        "other_trouble_delta": tr_delta,
        "build_warnings_delta": bw_delta,
        "rising_metrics": rising,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Run a deploy recipe and keep the whole transcript")
    ap.add_argument("recipe", nargs="*", default=["deploy"],
                    help="just recipe(s) to run from w0m-api (default: deploy)")
    ap.add_argument("--keep-raw", action="store_true",
                    help="also keep the unprocessed pty capture next to the clean log")
    args = ap.parse_args()
    recipe = args.recipe or ["deploy"]

    LOGS.mkdir(exist_ok=True)
    # Provisional name only — the real one is the RELEASE this run produced, which cannot be known
    # until it has. `deploy_version` is a justfile variable evaluated per invocation, so the stamp
    # this process could compute would belong to a different invocation than the deploy it wraps.
    raw_path = LOGS / "_in-progress.raw"
    log_path = LOGS / "_in-progress.log"

    print(f"▶ logging `just {' '.join(recipe)}` (from w0m-api) → {log_path}")

    # 🔴 `script(1)` REQUIRES a real terminal — without one it dies with
    # `tcgetattr/ioctl: Operation not supported on socket`, leaving an empty log and an exit code
    # that says the deploy failed when it never ran. That is a worse outcome than not logging, so
    # the mode is chosen from what stdin actually is, and the log records which one was used.
    interactive = sys.stdin.isatty()

    if interactive:
        # stdin/stdout/stderr INHERITED: the user watches it live and answers the confirms, while
        # `script` writes the same bytes to the file. Capturing here instead would break both.
        if sys.platform == "darwin":
            cmd = ["script", "-q", str(raw_path), "just", *recipe]
        else:
            cmd = ["script", "-q", "-e", "-c", shlex.join(["just", *recipe]), str(raw_path)]
        proc = subprocess.run(cmd, cwd=WORKSPACE)
        rc = proc.returncode
        raw = raw_path.read_text(errors="replace")
    else:
        # ⚠️ No terminal (agent shell, cron, CI). Prompts cannot be answered here, so any recipe
        # gated by `_confirm` will fail — correctly, and visibly, rather than hanging.
        print(" [WARN] no TTY — capturing through a pipe instead of a pty.")
        print("     Colour and progress rendering will differ, and any interactive confirm will")
        print("     FAIL rather than prompt. Run this from a real terminal to deploy.\n")
        chunks: list[str] = []
        with subprocess.Popen(["just", *recipe], cwd=WORKSPACE, stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, bufsize=1) as pr:
            assert pr.stdout is not None
            for line in pr.stdout:          # stream live AND keep it
                sys.stdout.write(line)
                chunks.append(line)
            rc = pr.wait()
        # The exit code comes from wait(), not from a pipeline — nothing to mask it.
        raw = "".join(chunks)
        raw_path.write_text(raw)
    text, counts = redact(clean(raw))

    # T291 AC1: A transcript is named a RELEASE only when one was actually PUBLISHED,
    # decided by what the run DID (exit 0 on a release recipe) rather than merely
    # matching a version string printed to stdout. Non-deploy recipes, failed runs,
    # or single-stage checks land as run-*.log.
    found, versions = release_of(text)
    is_release = rc == 0 and any(r in RELEASE_RECIPES for r in recipe)
    if len(versions) > 1:
        print(f" [WARN] this transcript carries {len(versions)} different release versions "
              f"({', '.join(versions)}) — one deploy must stamp ONE; the services disagree on what shipped")
    if is_release and found:
        release: str | None = found
        final = LOGS / f"deploy-{release}.log"
    else:
        # No release was published (a non-deploy recipe, a sub-recipe, or a failure before the stamp).
        # Naming it after a release would claim one that does not exist, so it is named as a RUN.
        release = None
        final = LOGS / f"run-{producer_version() or 'unstamped'}.log"

    header = [
        # 🔑 ONE timestamp, in the declared schema, and it is the artefact's own name. An earlier
        # draft printed a second, ISO-formatted clock reading here too — a second time format in
        # the very file adopting the standard, which is the drift the standard exists to stop.
        # `just version-check` flagged it, correctly, and DELETING it was the fix; an exemption
        # would have preserved the thing being standardised against.
        # ⚠️ Describing that removed line rather than quoting it is deliberate: version-check
        # matches inside comments, so pasting the old expression here re-triggers the finding —
        # a gate you cannot satisfy by doing the right thing. Filed as D56.
        f"# artefact  : {final.name}",
        f"# recipe    : just {' '.join(recipe)}   (cwd: {WORKSPACE})",
        f"# exit code : {rc}",
        (f"# release   : {release}   (as stamped by the deploy itself)" if release else
         "# release   : none — this run published no release version"),
        f"# capture   : {'pty (script)' if interactive else 'pipe (no TTY)'}",
        "#",
        ("# Captured via script(1) on a pty: both stdout and stderr, prompts intact."
         if interactive else
         "# Captured through a PIPE — no TTY was available. Both streams are here and the exit code"
         "\n# is real, but prompts could not be answered and rendering differs from a terminal."),
        "# ANSI stripped. Secrets redacted by shape — see the count below.",
        "",
    ]
    final.write_text("\n".join(header) + text)
    log_path.unlink(missing_ok=True)
    if args.keep_raw:
        raw_path.replace(final.with_suffix(".raw"))
    else:
        raw_path.unlink(missing_ok=True)
    log_path = final

    lines = text.split("\n")
    steps = [ln.strip() for ln in lines if STEP.match(ln) and ln.strip()]
    audit = audit_transcript(text)

    # T507 / T523 AC5: Write structured deploy audit record with release-to-release deltas
    prev_audit = previous_release_audit(LOGS, current_release=release)
    audit_file = LOGS / "deploy-audit-latest.json"
    audit_record: dict[str, object] = {
        "release": release,
        "recipe": recipe,
        "exit_code": rc,
        "build_warnings_count": len(audit["build_warnings"]),
        "build_warnings": audit["build_warnings"][:50],
        "advisory_failures_count": len(audit["advisory_failures"]),
        "advisory_failures": audit["advisory_failures"][:50],
        "browser_errors_count": len(audit["browser_errors"]),
        "browser_errors": audit["browser_errors"][:50],
        "tool_chatter_count": len(audit["tool_chatter"]),
        "other_trouble_count": len(audit["other_trouble"]),
    }
    deltas = compute_audit_deltas(audit_record, prev_audit)
    audit_record.update(deltas)
    audit_file.write_text(json.dumps(audit_record, indent=2) + "\n")
    if is_release and release:
        (LOGS / f"deploy-{release}.audit.json").write_text(json.dumps(audit_record, indent=2) + "\n")

    print(f"\n▶ transcript: {log_path}  ({len(lines)} lines)")
    if counts:
        print(f"  🔴 REDACTED {sum(counts.values())} secret-shaped value(s): {counts}")
        print("     A deploy tool printed something that looks like a credential. Worth chasing —")
        print("     the redaction protects the file, not the process that leaked it.")
    else:
        print("  ✅ no secret-shaped values found in the transcript")

    # ── T507: Structured Audit Section ──
    print(f"\n  {len(steps)} step banner(s)")
    bw_count = len(audit["build_warnings"])
    if bw_count == 0:
        print("  ✅ 0 build warnings (Vite, Rollup, LightningCSS, Astro clean)")
    else:
        print(f"  ⚠️  {bw_count} build warning(s):")
        for w in audit["build_warnings"][:15]:
            print(f"     │ {w[:140]}")
        if bw_count > 15:
            print(f"     … {bw_count - 15} more build warning(s)")

    adv_count = len(audit["advisory_failures"])
    if adv_count > 0:
        print(f"  🟡 {adv_count} advisory test suite finding(s) (non-blocking):")
        for a in audit["advisory_failures"][:10]:
            print(f"     │ {a[:140]}")

    br_count = len(audit["browser_errors"])
    if br_count > 0:
        print(f"  [WARN] {br_count} browser console / network error(s):")
        for b in audit["browser_errors"][:10]:
            print(f"     │ {b[:140]}")

    if audit["other_trouble"]:
        print(f"  ℹ  {len(audit['other_trouble'])} line(s) matching warning/error keywords:")
        for t in audit["other_trouble"][:15]:
            print(f"     │ {t[:140]}")
        if len(audit["other_trouble"]) > 15:
            print(f"     … {len(audit['other_trouble']) - 15} more")

    if audit["tool_chatter"]:
        print(f"  ℹ  {len(audit['tool_chatter'])} tool deprecation/chatter line(s) filtered")

    print(f"  ℹ  audit record: {audit_file.name}")
    rising = deltas.get("rising_metrics")
    if isinstance(rising, list) and rising:
        print(
            f"  ⚠️  [advisory] audit count rise vs previous release {deltas.get('previous_release')}: "
            f"{', '.join(str(x) for x in rising)}"
        )

    # Rotate on the way out, so the directory stays bucketed without anyone remembering to do it.
    # --quiet keeps a normal deploy silent about rotation; it speaks only when it actually moves or
    # prunes something. Failure here must never change the deploy's verdict, hence the guard.
    try:
        subprocess.run([sys.executable, str(WORKSPACE / "scripts/deploy_logs_rotate.py"),
                        "--apply", "--quiet"], cwd=WORKSPACE, check=False)
    except OSError as e:
        print(f" [WARN] rotation skipped ({e}) — the transcript above is unaffected")

    # Regenerate CHANGELOG.md from `deploy_log`, on the way out, for the same reason rotation is
    # here: so it happens without anyone remembering to do it.
    #
    # 🔴 This was the gap. The table filled up correctly for six weeks while the DOCUMENT sat at
    # `2026.07.10-1783720961` — written by the very commit that added the generator — because
    # `just changelog` was a manual recipe nobody ran. `just changelog-drift` now measures the gap
    # offline; this closes it. Only on success: a failed deploy has nothing to publish, and a
    # changelog that lists an aborted deploy is worse than a stale one.
    # 🔴 T430: gate on `is_release`, not `rc == 0`. Any successful wrapped recipe used to regenerate
    # the REAL estate CHANGELOG.md, including `deploy_logged.py version` inside `just test`
    # (deploy-logged-test). On 2026-09-23 a suite run wrote an EMPTY changelog over the committed one.
    if is_release:
        try:
            cg = subprocess.run(["just", "changelog"], cwd=WORKSPACE,
                                check=False, capture_output=True, text=True, timeout=180)
            if cg.returncode != 0:
                print("  [WARN] changelog regeneration failed — the deploy itself is "
                      "unaffected. Run `just changelog` by hand; `just changelog-drift` "
                      "will keep reporting until you do.")
        except (OSError, subprocess.SubprocessError) as e:
            print(f"  [WARN] changelog regeneration skipped ({e}) — verdict unaffected")

    print("\n" + (f"✅ `just {' '.join(recipe)}` exited 0" if rc == 0
                  else f"❌ `just {' '.join(recipe)}` exited {rc}"))
    # ⚠️ Re-raised, not swallowed. A wrapper that always exits 0 is how a failed deploy becomes a
    # green log — the exact substitution this file exists to prevent.
    return rc


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        # T541: Teardown cleanup: unlinked active consent file so it cannot leak to subsequent standalone commands
        try:
            subprocess.run([sys.executable, str(WORKSPACE / "scripts/confirm_step.py"), "--clear"],
                           cwd=WORKSPACE, check=False, capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            pass
