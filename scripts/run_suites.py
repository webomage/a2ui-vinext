#!/usr/bin/env python3
"""Run every declared test/check suite and report how many checks actually executed (T160).

WHY THIS EXISTS
---------------
`.w0m/sdlc.json → commands.test` was `just test`, which ran **vitest only — 1 test**. Every Python
gate suite ran only when named by hand. The `w0m-sdlc-verify` gate instructs the agent to run
`commands.test`, so following that instruction produced a green verification while ~110 checks
never executed. The gate that exists to stop false greens was the source of one.

DESIGN RULES, each earned
-------------------------
* **Declared, not discovered.** Suites live in `project/test-suites.json`. `--drift` reports any
  `*-test`/`*-check` recipe missing from it, so the registry cannot rot the way the gap did.
* **Fails closed on a missing suite.** A declared recipe that does not exist is a FAILURE, never a
  quiet skip — a skipped suite reporting green is the defect this tool removes.
* **Counts are reported, per suite and in total.** "It passed" is not falsifiable without them:
  0 checks passing must look different from 110 checks passing. A suite that exits 0 having run
  **zero** checks is called out as VACUOUS.
* **Tiers.** `offline` needs no secrets and no network; `live` does. `just test` runs offline only,
  so it stays runnable in a bare checkout — an aggregate that needs injection is one people route
  around, and a gate that gets routed around is not a gate.
* **Non-blocking needs a written reason.** A suite may be advisory (a known-red backlog), but only
  with `reason` recorded — the same rule the exposure baseline uses for accepting a finding.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "wom7web"
API = ROOT / "wom7api"

# Overridable so the runner can be driven against a fixture registry — the tests need to
# prove the failure paths without executing real suites.
REGISTRY = Path(os.environ.get("W0M_SUITES_REGISTRY") or (WEB / "project" / "test-suites.json"))

# House format: every suite prints "  ✅ label" / "  ❌ label" per check. vitest prints its own.
CHECK = re.compile(r"^\s*[✅❌]\s", re.M)
# T257 step 1 — the TEXT dialect, accepted ALONGSIDE the glyphs, never instead of them.
#
# 🔴 This is the first step of the emoji-to-text migration and the ONLY safe one to take first.
# The owner's 2026-08-22 instruction prohibits emoji in logs, but this counter is what makes a
# suite's checks countable at all: convert producers before teaching the reader and all 126 suites
# report ZERO checks and pass vacuously — a green aggregate measuring nothing. So the reader learns
# the new form while still accepting the old, and producers move afterwards, one at a time.
#
# Earned immediately: T256's and T258's three new gates printed text verdicts and landed in the
# `?`-count bucket, which is the bucket that cannot be told apart from "ran nothing".
TEXT_CHECK = re.compile(r"^\s*\[(?:OK|PASS|FAIL)\]\s", re.M)
VITEST = re.compile(r"Tests\s+(\d+)\s+passed", re.M)
# Fallbacks for the same runner. `Tests N passed` is stable when vitest is run alone (measured
# 3/3) but went unread inside a full deploy — so accept the Test Files line and a bare
# "N passed" as well, rather than let one reporter quirk move a gate.
VITEST_FILES = re.compile(r"Test Files\s+(\d+)\s+passed", re.M)
# Not line-anchored: pytest's own summary pads the number with a `====` banner on both sides
# (`==== 14 passed in 0.17s ====`), so a `^\s*` anchor never reaches it — measured against
# active-work-heads-up-test, whose `pytest -v` output has no other dialect this can read.
PASSED_N = re.compile(r"(?:^|\s)(\d+)\s+passed\b", re.M)
# Measured 2026-08-16 from reports/uncounted/*.log — the dialects the remaining suites ACTUALLY
# speak, read off their captured output rather than guessed at:
NODE_TEST = re.compile(r"^\s*ℹ\s+pass\s+(\d+)", re.M)        # node:test  — skills, deno-test
OK_N_THING = re.compile(r"\bok\s+—\s+(\d+)\s+\w", re.M)      # `ok — 25 tools`, `ok — 3 rule(s)`
SCANNED_N = re.compile(r"—\s*(\d+)\s+\w+\s+against\b", re.M)  # `— 222 tickets against …`
# Suites do not share one dialect. Measured 2026-08-16 across the 16 that reported `?`:
#   ✅/❌ line starts …… the house style (most suites)
#   ✓/✗ line starts …… version-test, deps-check, mmd-validate, skills-catalogue-test
#   "ALL PASS (24/24)" … version-test's summary
#   mypy "Success: no issues found in 91 source files" … py-typecheck, once per package
# Teaching the counter these is worth it; chasing every future dialect is not, which is what the
# UNCOUNTED ratchet below is for.
TICK = re.compile(r"^\s*[✓✗×]\s", re.M)
# 🔴 There is deliberately NO `TEXT_TICK`. One was added on 2026-08-23 and removed the same day:
# it was byte-identical to TEXT_CHECK, and `count_checks` tries the CHECK branch FIRST, so a
# text-only suite is always counted there and the TICK branch is never reached for text. The
# separate matcher could not fire — a dead protocol declaration, which is the exact shape T257
# exists to remove.
# ⇒ The TEXT dialect is SHARED across both glyph dialects, and that is what makes the migration
# safe: a TICK producer converting to [PASS]/[FAIL] is picked up by the CHECK branch with an
# identical count. Reader-first is satisfied by TEXT_CHECK alone.
RATIO = re.compile(r"\((\d+)\s*/\s*\d+\)")
MYPY = re.compile(r"Success: no issues found in (\d+) source file", re.M)


def load_registry() -> list[dict]:
    if not REGISTRY.is_file():
        sys.exit(f"❌ run-suites: registry not found: {REGISTRY}")
    try:
        data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    except ValueError as e:
        sys.exit(f"❌ run-suites: registry is malformed: {e}")
    suites = data.get("suites") or []
    if not suites:
        sys.exit("❌ run-suites: registry declares no suites — refusing to report a green run "
                 "over an empty set")
    for s in suites:
        if not s.get("blocking", True) and not s.get("reason"):
            sys.exit(f"❌ run-suites: suite '{s.get('name')}' is non-blocking with no reason. "
                     "Advisory status is a decision and must be written down.")
    return suites


def recipe_exists(recipe: str) -> bool:
    r = subprocess.run(["just", "--show", recipe], cwd=API, capture_output=True, text=True)
    return r.returncode == 0


ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def count_checks(out: str) -> int | None:
    """How many checks a suite reported, or None when its output cannot be read.

    🔴 `None` is NOT the same as zero, and the difference is the whole point. A suite that ran
    **0** checks is VACUOUS and must fail. A suite whose output this cannot parse is *unknown* —
    it might have run 500 checks or none, and nothing here can tell. Reporting both as a green tick
    with a `?` is how an unmeasured suite passes for an audited one, so the caller separates them
    and ratchets the unknown count (see `main`).
    """
    out = ANSI.sub("", out)          # colour must never decide whether a check is counted
    n = len(CHECK.findall(out)) + len(TEXT_CHECK.findall(out))
    if n:
        return n
    n = len(TICK.findall(out))          # glyphs only — text was already caught above
    if n:
        return n
    for rx in (VITEST, VITEST_FILES, NODE_TEST, OK_N_THING, SCANNED_N, PASSED_N):
        m = rx.search(out)
        if m:
            return int(m.group(1))
    mypy = MYPY.findall(out)
    if mypy:
        return sum(int(x) for x in mypy)
    m = RATIO.search(out)
    if m:
        return int(m.group(1))
    return None


def run(suite: dict) -> dict:
    recipe = suite["recipe"]
    if not recipe_exists(recipe):
        return {**suite, "status": "MISSING", "checks": 0, "rc": 127}
    p = subprocess.run(["just", recipe], cwd=API, capture_output=True, text=True)
    out = p.stdout + p.stderr
    checks = count_checks(out)
    status = "pass" if p.returncode == 0 else "FAIL"
    if status == "pass" and checks == 0:
        status = "VACUOUS"
    return {**suite, "status": status, "checks": checks, "rc": p.returncode, "raw": out,
            "tail": out.strip().splitlines()[-1][:100] if out.strip() else ""}


# A recipe is a suite because of what it RUNS, not what it is called (T195 AC4 / D37).
# The name test alone made `audit`, `py-typecheck` and `mmd-validate` structurally invisible —
# not overlooked by this gate, but unreachable by it, which is a different and worse failure.
# ⚠️ Both signals are needed. Name-only misses a well-behaved gate with an ordinary name; body-only
# misses a `*-test` recipe that shells out to something this cannot recognise.
RECIPE = re.compile(r"^([a-z][a-z0-9-]*)(?:\s+[^:\n]*)?:(?:[^=\n].*)?$", re.M)
SUITE_NAME = re.compile(r"(?:-test|-check)$")
# `project/scripts/tests/` IS the test home, and `--check`/`--enforce`/`--drift` is the estate's
# gate-flag convention — a recipe doing either is a suite whatever it is named.
SUITE_BODY = re.compile(r"scripts/tests/|--check\b|--enforce\b|--drift\b")

# T240 AC1: A recipe that forwards CLI arguments (*args: or {{args}}) to a script that accepts
# gating flags (--enforce, --check, --drift) is a suite even if its name does not end in -test/-check
# and its body does not contain the flag literally.
FORWARD_ARGS = re.compile(r"\{\{\s*args\s*\}\}|\*args\b")
SCRIPT_GATING_FLAG = re.compile(
    r"(?:add_argument\s*\(\s*['\"]--(enforce|check|drift)['\"]"
    r"|['\"]--(enforce|check|drift)['\"]\s*in\s*(?:sys\.)?argv"
    r"|\bargparse\b.*['\"]--(enforce|check|drift)['\"])"
)


def inspect_script_capability(body: str) -> str | None:
    """Check if a recipe forwarding arguments calls a script that accepts gating flags (T240 AC1)."""
    if not FORWARD_ARGS.search(body):
        return None
    py_scripts = re.findall(r"python3\s+([^\s'\"]+\.py)", body)
    for py in py_scripts:
        py_path = Path(py)
        candidates = [py_path, ROOT / py_path, WEB / py_path, API / py_path]
        for c in candidates:
            if c.is_file():
                try:
                    content = c.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                m = SCRIPT_GATING_FLAG.search(content)
                if m:
                    flag = m.group(1) or m.group(2) or m.group(3)
                    return f"script {py_path.name} accepts --{flag} via forwarded args"
    return None


SCHEDULES = WEB / "project" / "launchd" / "schedules.jsonc"


def scheduled_recipes() -> set[str]:
    """Recipes the machine runs UNATTENDED, from the declared launchd schedule.

    T247 AC2 — a third reason to demand a registry entry, and a different KIND of reason from the
    other two. `SUITE_NAME` and `SUITE_BODY` both ask "does this look like a test?"; neither can
    see `tools-weekly`, which upgrades production tooling on a timer and matches neither pattern.
    Measured 2026-08-21: **all four** scheduled agents were undeclared — `tools-weekly`,
    `backup-daily`, `backup-weekly`, `schema-weekly` — so the two jobs that take the database
    backups had no registry entry either.

    The question this asks is not "is it a suite" but "does anything run without a human watching,
    that nobody has triaged". A scheduled job may well be `excluded` — several of these mutate and
    must never be run by `just test` — but it must be excluded ON PURPOSE, with a reason.

    Parsed with a string-aware JSONC scan rather than a regex: `//` occurs inside URLs, and the
    estate has a standing rule against regex comment-stripping for exactly that reason.
    """
    try:
        raw = SCHEDULES.read_text(encoding="utf-8")
    except OSError:
        return set()
    out, in_str, esc, i = [], False, False, 0
    while i < len(raw):
        c = raw[i]
        if in_str:
            out.append(c)
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
            out.append(c)
        elif c == "/" and i + 1 < len(raw) and raw[i + 1] == "/":
            while i < len(raw) and raw[i] != "\n":
                i += 1
            continue
        else:
            out.append(c)
        i += 1
    try:
        sched = json.loads("".join(out))
    except ValueError:
        return set()
    return {a["command"] for a in sched.get("agents", []) if a.get("command")}


def recipes(jf: str) -> dict[str, str]:
    """Every justfile recipe as name -> body (the indented block beneath it)."""
    out: dict[str, str] = {}
    lines = jf.splitlines()
    for i, line in enumerate(lines):
        m = RECIPE.match(line)
        if not m or line.startswith((" ", "\t", "#")):
            continue
        body: list[str] = []
        for nxt in lines[i + 1:]:
            if nxt.strip() and not nxt.startswith((" ", "\t")):
                break
            body.append(nxt)
        out[m.group(1)] = "\n".join(body)
    return out


def find_red_proof(n: str, suites: list[dict], declared: set[str]) -> str | None:
    """Check if a recipe has a declared red-proof test (T240 AC3 Tier B)."""
    for candidate in (f"{n}-test", f"{n}-check", f"test_{n}", f"{n}-probe"):
        if candidate in declared:
            return candidate
    for s in suites:
        if s.get("name") == n and s.get("recipe") != n:
            return s.get("recipe")
        if s.get("name") in (f"{n}-test", f"{n}-probe"):
            return s.get("recipe")
    return None


def drift(suites: list[dict]) -> dict[str, str]:
    """Any recipe that behaves like a suite and the registry does not declare, and WHY it matched.

    Returning the reason is not decoration: the first widened run reported 15 recipes as
    "*-test/*-check" when 14 were, and one (`suites-drift`) had matched on its body. A drift
    report that misdescribes its own reasoning is the thing it exists to catch.
    """
    jf = (API / "justfile").read_text(encoding="utf-8")
    scheduled = scheduled_recipes()
    found: dict[str, str] = {}
    for n, body in recipes(jf).items():
        cap = inspect_script_capability(body)
        if SUITE_NAME.search(n):
            found[n] = "name ends -test/-check"
        elif SUITE_BODY.search(body):
            found[n] = "body runs a test script or a --check/--enforce/--drift gate"
        elif cap:
            found[n] = cap
        elif n in scheduled:
            # Not "looks like a suite" — "runs unattended and nobody triaged it". See
            # scheduled_recipes(): this is the reason `tools-weekly` could fail every week in a
            # launchd log with no declared owner.
            found[n] = "runs on a launchd schedule (project/launchd/schedules.jsonc)"
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    # A deliberately excluded recipe must carry a reason, so "we forgot" and "we decided" cannot
    # look the same in this report.
    excluded = set()
    for e in data.get("excluded") or []:
        if not e.get("reason"):
            sys.exit(f"❌ run-suites: excluded recipe '{e.get('recipe')}' has no reason.")
        excluded.add(e["recipe"])
    declared = {s["recipe"] for s in suites} | excluded

    out: dict[str, str] = {}
    for n, why in sorted(found.items()):
        if n not in declared:
            proof = find_red_proof(n, suites, declared)
            if proof:
                out[n] = f"[Tier B] {why} (red-proof '{proof}' is declared)"
            else:
                out[n] = f"[Tier A] {why}"
    return out


def select_suites(suites: list[dict], tier: str, prepush: bool = False) -> list[dict]:
    """Which suites a run covers. `prepush` selects by the registry's `"prepush": true` flag and by nothing else (T503)."""
    if prepush:
        return [s for s in suites if s.get("prepush") is True]
    return [s for s in suites if tier == "all" or s.get("tier", "offline") == tier]


def prepush_problems(suites: list[dict]) -> list[str]:
    """A suite may only carry `prepush` if it can really gate a push: a real boolean, offline, and blocking. Returned as sentences; empty = fine."""
    out = []
    for s in suites:
        if "prepush" not in s:
            continue
        n = s.get("name", "?")
        if not isinstance(s["prepush"], bool):
            out.append(f"{n}: `prepush` must be true or false, not {s['prepush']!r}")
        elif s["prepush"]:
            if s.get("tier", "offline") != "offline":
                out.append(f"{n}: a prepush suite must be tier offline (a live suite cannot run on every push)")
            if not s.get("blocking", True):
                out.append(f"{n}: a prepush suite must be blocking (an advisory suite cannot gate a push)")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the declared test/check suites (T160)")
    ap.add_argument("--tier", default="offline", choices=["offline", "live", "all"])
    ap.add_argument("--drift", action="store_true", help="only report registry drift")
    ap.add_argument("--prepush", action="store_true",
                    help="run only the suites flagged \"prepush\": true (fast, deterministic ratchets; used by pre-push and the deploy pre-flight)")
    args = ap.parse_args()

    suites = load_registry()
    if args.drift:
        missing = drift(suites)
        tier_a = {n: why for n, why in missing.items() if why.startswith("[Tier A]")}
        tier_b = {n: why for n, why in missing.items() if why.startswith("[Tier B]")}
        print(f"▶ suite-registry drift — {len(suites)} declared, {len(missing)} undeclared "
              f"({len(tier_a)} Tier A, {len(tier_b)} Tier B)")
        if tier_a:
            print(f"\n  🔴 Tier A — completely undeclared ({len(tier_a)}):")
            for m, why in tier_a.items():
                print(f"     [WARN] {m} ({why.removeprefix('[Tier A] ')})")
        if tier_b:
            print(f"\n  🟡 Tier B — red-proof declared, gate itself unrun ({len(tier_b)}):")
            for m, why in tier_b.items():
                print(f"     [WARN] {m} ({why.removeprefix('[Tier B] ')})")
        if missing:
            print("\n❌ undeclared suites exist — add them (or record why they are excluded)")
            return 1
        print("  ✅ every recipe that behaves like a suite is declared")
        return 0

    problems = prepush_problems(suites)
    if problems:
        print("❌ run-suites: the registry's prepush flags are invalid:")
        for pr in problems:
            print(f"   · {pr}")
        return 1
    picked = select_suites(suites, args.tier, args.prepush)
    label = "prepush" if args.prepush else f"tier={args.tier}"
    if not picked:
        print(f"❌ run-suites: no suites in {label}")
        return 1

    print(f"▶ suites — {label} · {len(picked)} declared\n")
    results, total = [], 0
    for s in picked:
        r = run(s)
        results.append(r)
        if isinstance(r["checks"], int):
            total += r["checks"]
        mark = {"pass": "✅", "FAIL": "❌", "MISSING": "🚫", "VACUOUS": "⚠️"}[r["status"]]
        n = "?" if r["checks"] is None else r["checks"]
        block = "" if r.get("blocking", True) else "  (advisory)"
        print(f"  {mark} {r['name']:22} {str(n):>4} check(s){block}")
        if r["status"] in ("FAIL", "MISSING"):
            print(f"       ↳ {r.get('tail') or 'recipe not found'}")

    # ── UNCOUNTED: suites that ran and passed, but whose check count could not be read ──────
    #
    # 🔴 These are NOT the same as a clean result, and the distinction is the reason this block
    # exists. `?` means the output was in a dialect the parser does not know — so a suite running
    # 500 checks and a suite running NONE print identically, both with a green tick. The VACUOUS
    # guard only catches an explicit zero, which an unparseable suite can never report.
    #
    # Deliberately NOT blocking: it would fail every deploy today over a formatting difference.
    # Instead it is a RATCHET — the number may fall, never rise — so the blind spot cannot grow
    # while nobody is looking. Same shape as the spec-standard ceiling, for the same reason.
    uncounted = [r for r in results if r["checks"] is None and r["status"] == "pass"]

    # 🔑 Keep the RAW OUTPUT OF EVERY SUITE, not just the summary line.
    #
    # Owner ask 2026-08-16: "preserve not only the full deploy log but also raw output from each
    # step/tool." The full transcript already exists (wom7api/deploy-logs/run-*.log); what was
    # missing is the per-tool detail behind each one-line verdict, which is exactly what you need
    # when a suite says something surprising and the transcript has already scrolled past it.
    #
    # This also ends a specific failure of method: `vitest` read as 59 in every standalone run and
    # `?` inside the owner's deploys, and I tested THREE hypotheses (injected env, CI=1, ANSI
    # colour) that were each wrong, because none of them was the environment that produced the
    # output. A tool that reports "I could not read this" owes you the thing it could not read.
    # Reading the dumps took minutes and fixed 4 of the 6 unreadable suites at once.
    if not args.prepush:
        dump_dir = WEB / "reports" / "suites"
        try:
            dump_dir.mkdir(parents=True, exist_ok=True)
            for old_log in dump_dir.glob("*.log"):
                old_log.unlink()          # this run's evidence, not an archaeology pile
            for r in results:
                body = r.get("raw", "") or "<no output captured>"
                header = (f"# suite: {r['name']}  recipe: {r['recipe']}  status: {r['status']}  "
                          f"exit: {r['rc']}  checks: {r['checks']}\n"
                          f"# tier: {r.get('tier', 'offline')}  blocking: {r.get('blocking', True)}\n"
                          + "# " + "-" * 70 + "\n")
                (dump_dir / f"{r['name']}.log").write_text(header + body)
        except OSError:
            pass
    ceiling_path = WEB / "project" / "suite-uncounted-baseline.json"
    ceiling = None
    if ceiling_path.exists():
        try:
            ceiling = json.loads(ceiling_path.read_text()).get("uncounted")
        except (OSError, ValueError):
            ceiling = None

    hard = [r for r in results if r["status"] in ("FAIL", "MISSING") and r.get("blocking", True)]
    soft = [r for r in results if r["status"] in ("FAIL", "MISSING") and not r.get("blocking", True)]
    vac = [r for r in results if r["status"] == "VACUOUS"]

    print(f"\n  {total} check(s) ran across {len(picked)} suite(s)")
    if uncounted:
        names = ", ".join(r["name"] for r in uncounted)
        print(f" [UNKNOWN] {len(uncounted)} suite(s) passed with an UNREADABLE check count: {names}")
        print("     Their output uses a dialect this counter does not know, so 'ran 500 checks'")
        print("     and 'ran none' look identical — and the total above excludes them.")
    if not args.prepush:
        print(f" [FILE] raw output of all {len(results)} suite(s): reports/suites/*.log")
    if ceiling is not None and len(uncounted) > ceiling:
        # ⚠️ ADVISORY, not blocking — and this cost a deploy to learn.
        #
        # Written 2026-08-16 with the comment "deliberately NOT blocking" and a `return 1` three
        # lines later, which blocked. It then failed the owner's deploy because `vitest` drifted
        # into the unreadable set: measured 3/3 stable when run alone, unreadable inside a full
        # deploy. Blocking a ship on a measurement that moves for reasons nobody has explained is
        # strictly worse than the blind spot it was bounding.
        #
        # It still SAYS so, loudly, every run — the number is visible and the rise is named.
        print(f"\n[WARN] unreadable-count suites rose {ceiling} → {len(uncounted)} (advisory).")
        print("   A suite reports in a dialect nothing can measure, so it cannot be told apart")
        print("   from one that ran no checks. Make it print ✅/❌ (or ✓/✗) per check, or extend")
        print("   count_checks(). Do NOT raise the baseline just to silence this.")
    if soft:
        print(f"  🟡 {len(soft)} advisory suite(s) failing: {', '.join(r['name'] for r in soft)}")
    if vac:
        print(f" [WARN] {len(vac)} suite(s) exited 0 having run ZERO checks: "
              f"{', '.join(r['name'] for r in vac)} — a pass over nothing is not a pass")
    if hard:
        print(f"\n❌ {len(hard)} blocking suite(s) failed: {', '.join(r['name'] for r in hard)}")
        return 1
    if not total:
        print("\n❌ zero checks ran in total — that is a broken aggregate, not a clean run")
        return 1
    print("\n✅ all blocking suites passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
