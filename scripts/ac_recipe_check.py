#!/usr/bin/env python3
"""ac-recipe-check — a TICKED acceptance criterion may not cite a `just` recipe that does not exist.

🔴 **Why this exists.** [[T254]]'s plan cites the recipes that prove each phase, and two of them do
not exist yet. The ticket says so in prose — but prose is not a gate, and the failure mode is
specific: *a phase whose gate does not exist gets declared done on a code read.* Then, measuring
that, the corpus produced a sharper instance: **[[T250]] AC4 is TICKED and cites `just suites`,
which is not a recipe.** The real runner is `just test` / `just test-all`. I wrote that AC the day
before this gate, asserting where a gate runs, and named something that is not there.

🔑 **The rule is narrow on purpose, and the narrowness is the design.**

  · an **unticked** AC citing a missing recipe is a **PLAN** — the ticket intends to build it. Six
    tickets are in that state today (T152 T159 T183 T207 T214 T239) and none is a defect.
  · a **ticked** AC citing a missing recipe is a **false claim of completion** — it asserts a gate
    proved something, and the gate is not there.

⚠️ A gate over *all* citations would fire on 8 of 163 and at least three of those are legitimate:
`just oc` in [[T153]] is a rename's **old** name, `just serve` in [[T152]] appears in a sentence
about a recipe that does *not* exist. **A gate that cries wolf on 3 of 8 gets switched off**
([[T250]] AC2 learned this the hard way, and [[T135]] AC8 states it as policy). So historical and
negative references are ACKNOWLEDGED with a reason and **printed on every run** — an
acknowledgement that vanishes from the report is indistinguishable from a gate that stopped
looking ([[T246]] AC5).

Exit codes: 0 clean · 1 a ticked AC cites a missing recipe · 2 the recipe list could not be read
(cannot measure ≠ nothing to find).

Run it as `just ac-recipe-check`.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = ROOT / "wom7api"
TICKETS = ROOT / ".tasks"
if not TICKETS.is_dir():
    sys.exit(f"FATAL: Canonical tickets directory not found at {TICKETS} (AgDR-0025: zero silent fallbacks)")

#: The AC section, matched the way `ac_trace_check.py` matches it so the two gates cannot disagree
#: about where a ticket's criteria begin and end.
AC_SECTION = re.compile(r"^##+\s*Acceptance criteria\s*$(.*?)(?=^##\s|\Z)", re.S | re.M)
#: Split on the checkbox itself, so tick state stays attached to the text that follows it. Matching
#: the whole block and then looking for `[x]` anywhere would attribute a later AC's tick to an
#: earlier AC's citation.
AC_SPLIT = re.compile(r"^(- \[[ x]\] )", re.M)
#: A citation is a BACKTICKED `just <name>`. Unbackticked prose ("just run it") is not a citation,
#: and requiring the backtick is what keeps the corpus bounded rather than matching every sentence.
#:
#: ⚠️ **This boundary is the intended escape for prose, and it is stated so nobody has to guess.**
#: To *mention* a recipe that does not exist — a rename's old name, a correction recording what an
#: AC used to say — write it as italics, not code: *"just suites"*. That is not a claim that the
#: command works, so it is not this gate's business. The very first fix this gate produced needed
#: exactly that: T250's correction note quoted the dead name it was correcting, and the gate fired
#: on the sentence describing the fix.
CITE = re.compile(r"`just ([a-z0-9][a-z0-9-]*)")

#: Ticked ACs whose missing citation is CORRECT, each with the reason. Printed every run.
ACKNOWLEDGED: dict[tuple[str, str], str] = {
    ("T153", "oc"): (
        "a rename's OLD name. The AC records `openclaw-*`/`just oc` → `zeroclaw-*`/`just zc`; the "
        "absence of `just oc` is the ticket's own success condition, not a broken citation."
    ),
    ("T334", "skill-check"): (
        "a recipe in `artemioquierocomer.mx`'s OWN justfile (a client repo, `project/"
        "clients-policy.json` id `artemio`), not this estate's — `recipes()` only reads `just "
        "--list` from wom7api, which cannot see it. Verified directly in that repo: `just "
        "skill-check` -> `node scripts/verify_skills.mjs` -> \"56 managed skill(s) match the "
        "lockfile - 0 unmanaged, 0 drift.\" A true, checked citation this gate's scope cannot reach."
    ),
    ("T198", "deploy-client-api"): (
        "true when ticked: one of the 25 per-function recipes T431 (2026-09-23) replaced with "
        "`just deploy-function client-api`. The AC records what ran then, not a gate that should exist now."
    ),
    ("T246", "deploy-agent" + "-consultant"): (
        "true when ticked: a per-function recipe T431 replaced with `just deploy-function "
        "w0m-consultant`. The AC records that the deploy prompted, which the new recipe also does."
    ),
    ("T249", "deploy-agent" + "-consultant"): (
        "true when ticked: a per-function recipe T431 replaced with `just deploy-function "
        "w0m-consultant`. Historical citation of the deploy step, not a missing gate."
    ),
    ("T426", "claim"): (
        "a removal AC: T426 AC5 explicitly removes `just claim`/`unclaim`, `agent_claim.py`, and "
        "`_in/active-work.json`; the absence of `just claim` is the ticket's own success condition."
    ),
    ("T488", "resumes-upload-live"): (
        "true when ticked: T510 U4 retired `resumes-upload*` (and its root forwarder in T509 U0) after "
        "moving resume storage to the private `resumes` bucket verified by `just resume-vault-verify`."
    ),
    ("T506", "resumes-upload-live"): (
        "true when ticked: T510 U4 retired `resumes-upload*` (and its root forwarder in T509 U0) in "
        "favour of `just resume-vault-verify`."
    ),
    ("T510", "resumes-upload-live"): (
        "a removal/historical AC: T510 U4 explicitly retires `resumes-upload*` in favour of "
        "`just resume-vault-verify`; T509 U0 removed the dangling root forwarder."
    ),
}


def recipes() -> set[str] | None:
    """Every recipe `just` will actually run. None when the list cannot be read."""
    found = set()
    for cwd in (ROOT, API):
        try:
            out = subprocess.run(
                ["just", "--list"], cwd=cwd, capture_output=True, text=True, timeout=120
            )
            if out.returncode == 0:
                for line in out.stdout.splitlines():
                    m = re.match(r"^\s{4}([a-z0-9][a-z0-9-]*)", line)
                    if m:
                        found.add(m.group(1))
        except (OSError, subprocess.SubprocessError):
            pass
    return found or None


def citations(body: str) -> list[tuple[bool, str]]:
    """(is_ticked, recipe) for every backticked `just <recipe>` inside the AC section."""
    sec = AC_SECTION.search(body)
    if not sec:
        return []
    parts = AC_SPLIT.split(sec.group(1))
    out: list[tuple[bool, str]] = []
    for i in range(1, len(parts) - 1, 2):
        done = parts[i].strip() == "- [x]"
        for rec in CITE.findall(parts[i + 1]):
            out.append((done, rec))
    return out


def scan(live: set[str]) -> tuple[list[str], list[str], list[str]]:
    """(failures, plans, acknowledged) — three buckets, deliberately different tiers."""
    fail: list[str] = []
    plan: list[str] = []
    ack: list[str] = []
    for f in sorted(TICKETS.glob("T*.md")):
        tid = f.stem
        for done, rec in citations(f.read_text(encoding="utf-8", errors="replace")):
            if rec in live:
                continue
            if not done:
                plan.append(f"{tid}: `just {rec}` — unticked, so this is a plan")
            elif (tid, rec) in ACKNOWLEDGED:
                ack.append(f"{tid}: `just {rec}` — {ACKNOWLEDGED[(tid, rec)]}")
            else:
                fail.append(f"{tid}: a TICKED AC cites `just {rec}`, which is not a recipe")
    return fail, plan, ack


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    live = recipes()
    if live is None:
        # Cannot measure is not the same as nothing to find. Exit 2, never 0.
        print("❌ ac-recipe-check: could not read `just --list` — cannot measure, so not passing.")
        return 2

    fail, plan, ack = scan(live)
    total = sum(len(citations(f.read_text(encoding='utf-8', errors='replace')))
                for f in TICKETS.glob("T*.md"))
    if not total:
        # An empty corpus must fail rather than vacuously pass (T240).
        print("❌ ac-recipe-check: 0 recipe citations parsed — the reader is broken, not the "
              "tickets clean.")
        return 2

    if a.json:
        import json
        print(json.dumps({"live_recipes": len(live), "citations": total,
                          "failures": fail, "plans": plan, "acknowledged": ack}, indent=2))
        return 1 if fail else 0

    print(f"▶ ac-recipe-check — {total} citation(s) across the ticket corpus, "
          f"{len(live)} live recipe(s)")

    if ack:
        print(f"\n [INFO] {len(ack)} acknowledged (reason recorded, printed every run):")
        for a_ in ack:
            print(f"      {a_}")

    if plan:
        print(f"\n  ⚪ {len(plan)} unticked AC(s) cite a recipe that does not exist yet — reported, "
              f"NOT a finding:")
        for p in plan:
            print(f"      {p}")
        print("     An AC that plans to build a gate is allowed to name it before it exists.")

    if fail:
        print(f"\n  🔴 {len(fail)} TICKED AC(s) cite a recipe that does not exist:")
        for f_ in fail:
            print(f"      {f_}")
        print("\n  A ticked AC asserts a gate proved something. If the gate is not there, the")
        print("  assertion is unfounded — fix the name, build the recipe, or untick the AC.")
        print("  If the citation is deliberately historical, add it to ACKNOWLEDGED with a reason.")
        return 1

    print("\n  ✅ every ticked AC cites a recipe that exists.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
