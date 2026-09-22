#!/usr/bin/env python3
"""T110 AC4 — check that ticket work actually moved the ticket. Instruction is not enforcement.

WHAT THIS EXISTS TO CATCH
    `CLAUDE.md` has said *"Update tracking surfaces in the same commit as the work"* since
    2026-07-21, and nothing verified it. The proof that instruction alone does not work is in
    T110's own history: a whole session worked T89/T99/T102 ad-hoc with **zero** gates invoked, and
    T89 sat at *"started — poller wired"* through an entire session that actually finished it. The
    board then misleads the next agent, which is the failure the whole SDLC exists to prevent.

WHAT IT CHECKS, STATED HONESTLY
    This is a **proxy**, and calling it anything else would overstate it. Nothing in git can prove
    a `w0m-sdlc-review` gate was *thought about*. What is observable is whether the tracked record
    moved with the code — and a `feat`/`fix` that changes behaviour under a T-id while its ticket
    and the board both stay still is the exact shape of ad-hoc work. So:

        a commit typed `feat` or `fix` that names T<n> must be accompanied, IN THE SAME PUSH, by a
        change to `.tasks/T<n>.md` or to `TASKS.md`.

    Measured over the corpus before choosing the rule: of 455 T-id commits since 2026-07-20, 31%
    moved no tracking surface — but most of those are `chore`/`docs` (STATE.md refreshes, ticket
    mirror syncs) where the rule should not apply. Narrowed to `feat`/`fix` it is 30%, and those
    are genuine misses. A gate red on 30% of history is unshippable (T135 AC8), so:

WHY THE SCOPE IS THE PUSH, NOT HISTORY
    Scoped to the commits being pushed, exactly as the spec-drift gate is (`--scope-diff`). Historic
    misses stay advisory instead of walling off a backlog nobody can retro-fix. Verified against the
    session that built this: 4 of 4 `feat`/`fix` commits pass, so it starts GREEN (T135 AC8).

WHY PUSH-LEVEL AND NOT SAME-COMMIT
    `CLAUDE.md` asks for the same *commit*, and that is the ideal — it is reported. But the
    enforceable floor is the push, because both failures this gate is named after were
    session-level, and a same-commit rule would fight legitimate commit splitting (a dependency fix
    and its ticket update are honestly two commits). Same-commit violations are printed as advice;
    push-level ones block.

    --range A..B   check an explicit range (default: origin/<branch>..HEAD)
    --all          audit all history in range, report only, never exit non-zero
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ.get("W0M_TRACE_ROOT") or Path(__file__).resolve().parents[1])

TID = re.compile(r"\bT(\d+)\b")
# Conventional-commit types that CLAIM to change behaviour. `chore`/`docs`/`refactor`/`test` are
# deliberately out of scope: the tracking-surface refreshes and mirror syncs that dominated the
# raw 31% are exactly those, and a gate that fires on its own bookkeeping teaches people to ignore it.
BEHAVIOUR = re.compile(r"^(feat|fix)\b")
BOARD = "TASKS.md"


def sh(args: list[str]) -> str:
    r = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""


def default_range() -> str:
    branch = sh(["git", "rev-parse", "--abbrev-ref", "HEAD"]).strip() or "beta"
    return f"origin/{branch}..HEAD"


def commits(rng: str) -> list[tuple[str, str, list[str]]]:
    raw = sh(["git", "log", rng, "--pretty=%H%x00%s"]).strip()
    out = []
    for line in raw.split("\n"):
        if not line:
            continue
        h, subj = line.split("\0", 1)
        files = sh(["git", "show", "--name-only", "--pretty=", "-r", h]).split()
        out.append((h, subj, files))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="T110 AC4 — ticket work must move the ticket")
    ap.add_argument("--range", dest="rng", default=None)
    ap.add_argument("--all", action="store_true", help="audit history; report only, never blocks")
    args = ap.parse_args()

    rng = args.rng or ("HEAD~200..HEAD" if args.all else default_range())
    cs = commits(rng)

    # Empty-set discipline: nothing to check is a legitimate no-op, but it must SAY so. A silent
    # green here is indistinguishable from a gate that examined the wrong range — which is the
    # failure this estate has shipped repeatedly.
    scoped = [(h, s, f) for h, s, f in cs if BEHAVIOUR.match(s) and TID.search(s)]
    if not cs:
        print(f"[INFO] sdlc-trace: range `{rng}` contains no commits — nothing to check "
              "(a valid no-op, NOT evidence the rule is being followed)")
        return 0
    if not scoped:
        print(f"✅ sdlc-trace: {len(cs)} commit(s) in `{rng}`, none of them a `feat`/`fix` naming a "
              "ticket — nothing in scope")
        return 0

    # Push-level: did ANY commit in the range move this ticket's record?
    moved: set[str] = set()
    board_moved = False
    for _h, _s, files in cs:
        if BOARD in files:
            board_moved = True
        for f in files:
            m = re.search(r"(?:^|/)(?:\.tasks|project/tickets)/T(\d+)\.md$", f)
            if m:
                moved.add(m.group(1))

    problems: list[str] = []
    advice: list[str] = []
    for h, subj, files in scoped:
        ids = set(TID.findall(subj))
        same_commit = BOARD in files or any(
            any(re.search(rf"(?:^|/)(?:\.tasks|project/tickets)/T{i}\.md$", f) for f in files)
            for i in ids
        )
        covered = board_moved or (ids & moved)
        if not covered:
            problems.append(
                f"{h[:8]} `{subj[:64]}` — changes behaviour under "
                f"{', '.join('T' + i for i in sorted(ids))} but nothing in this push touched "
                f"its ticket or {BOARD}")
        elif not same_commit:
            advice.append(
                f"{h[:8]} `{subj[:56]}` — ticket moved elsewhere in the push, not in this commit "
                f"(CLAUDE.md asks for the same commit)")

    print(f"▶ sdlc-trace — {len(cs)} commit(s) in `{rng}`, {len(scoped)} `feat`/`fix` naming a "
          f"ticket; {len(moved)} ticket file(s) moved, board moved={board_moved}")
    for a in advice:
        print(f" [INFO] {a}")

    if problems and not args.all:
        for p in problems:
            print(f"  ✗  {p}")
        print(f"\n❌ sdlc-trace failed — {len(problems)} commit(s) changed behaviour under a ticket "
              "without moving its record.")
        print("   CLAUDE.md: 'Update tracking surfaces in the same commit as the work.' A stale row "
              "misleads the next agent — T89 sat at 'started' through the session that finished it.")
        print("   Fix: update .tasks/T##.md (or project/tickets/T##.md), amend or "
              "add a commit, then re-push.")
        return 1
    if problems:
        for p in problems:
            print(f" [WARN] {p}")
        print(f"\n[INFO] sdlc-trace (--all): {len(problems)} historic miss(es) — report only.")
        return 0
    print("✅ sdlc-trace passed — every behaviour change under a ticket moved that ticket's record")
    return 0


if __name__ == "__main__":
    sys.exit(main())
