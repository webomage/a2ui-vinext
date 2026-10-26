#!/usr/bin/env python3
"""Flag w0m slash-commands that are not namespaced — a RATCHET, not a hard rule.

    python3 scripts/command_namespace_check.py             # report
    python3 scripts/command_namespace_check.py --enforce   # exit 1 if the count ROSE

WHY
---
On 2026-08-31 the owner found that **Antigravity binds `/tasks` to something of its own**, so w0m's
`/tasks` was shadowed and unreachable there. The collision was discovered by using the other IDE,
which is the expensive way to find it.

The estate cannot enumerate another ADE's built-in commands — there is no registry on disk to read
(`~/.antigravity` is VS Code-style extensions). So every unprefixed command is a bet against a
namespace nothing here can see, and the bet has already been lost once.

`w0m-` is the estate's existing prefix: 14 skills use it, and commands and skills share ONE `/`
namespace in Claude Code, so it covers both. openspec solves the same problem differently, with a
colon group (`opsx:apply`) — also fine, and also namespaced.

WHY A RATCHET AND NOT A BAN
---------------------------
`headroom` and `just` are unprefixed today and work. Renaming them on speculation would churn two
working commands and retrain muscle memory for a collision that has not happened. A ratchet blocks
the NEXT one from being added unprefixed while leaving those two alone — and if either does
collide, the fix is a rename, not a baseline bump.

🔴 Never raise `baseline` to go green. That is the same act as deleting a failing test. The number
only falls.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "w0m-web"

# Surfaces that carry SLASH-COMMANDS, declared rather than globbed. A new agent surface appearing
# here must be added deliberately — silently widening the scan would change the baseline's meaning.
SURFACES: tuple[tuple[str, str], ...] = (
    (".claude/commands", "Claude Code — the only surface carrying w0m's own commands today"),
    (".agent/workflows", "Antigravity's live surface. This is where /tasks was MISSING as well as "
                         "shadowed: renaming alone would not have made it reachable."),
    (".opencode/commands", "opencode. Deliberately undeclared in ide_surfaces; scanned so a "
                           "command appearing here is noticed rather than assumed absent."),
)

# Not ours to name. openspec generates these and already namespaces them with a colon.
THIRD_PARTY_PREFIXES = ("opsx", "openspec")

PREFIX = "w0m-"

# ── COVERAGE ────────────────────────────────────────────────────────────────────────────────────
# The namespace check catches unprefixed NAMES. It does not catch one-sided COVERAGE, and that is a
# distinct failure with the same consequence: a command on one surface is invisible on every other,
# and nothing says so.
#
# It has now happened in BOTH directions. `/tasks` was Claude-only, so it was missing from
# Antigravity — which is half of why renaming it alone would not have fixed anything.
# `w0m-local-dev` was Antigravity-only for months, so it was missing from Claude Code. Neither was
# reported by any gate; both were found by a person noticing an absence while using the other tool.
#
# `.opencode/commands` is deliberately excluded from parity: `.w0m/sdlc.json` does not declare
# opencode as a connected surface, so expecting parity there would manufacture a gap, not measure one.
PARITY_SURFACES = (".claude/commands", ".agent/workflows")

# DECIDED coverage, with the reason. A single-surface entry must say why.
COVERAGE_DECIDED: dict[str, tuple[tuple[str, ...], str]] = {
    "w0m-tasks": (PARITY_SURFACES,
                  "The ticket queue is the same question from either tool; it was the original "
                  "asymmetry and is now on both."),
    "w0m-local-dev": (PARITY_SURFACES,
                      "Running and verifying the app locally is tool-agnostic. Was "
                      "Antigravity-only until 2026-08-31."),
    "w0m-headroom": (PARITY_SURFACES,
                     "Mirrored 2026-08-31 by owner decision, after being recorded as an open "
                     "question rather than an oversight. The AGY copy SPLITS the answer instead of "
                     "pasting: the analyzers (status/audit/learn) read files and transfer "
                     "completely, but the routing argument — in-app subagents bypass the proxy — "
                     "was measured against CLAUDE CODE's engine and says nothing about "
                     "Antigravity's, so it is stated as not transferring."),
    "w0m-just": (PARITY_SURFACES,
                 "`just` is a plain CLI that behaves identically from any agent, so the Claude-only "
                 "asymmetry had no technical cause. Mirrored 2026-08-31. The AGY copy marks "
                 "`--list` and `--show` as `// turbo` (reading a recipe is safe and may run "
                 "unprompted) but never the run step — read-then-classify IS the safety mechanism."),
}

# Asymmetric and NOT yet decided. Reported, never failed — whether a command belongs on another
# surface is a judgement about how that tool is used, and a gate that blocks on an undecided
# question is one somebody switches off (T135 AC8).
# Empty, and that is the end state: every w0m command's coverage is now DECIDED. An entry here is
# an asymmetry nobody has ruled on — it should be rare and short-lived, never a parking space.
COVERAGE_UNDECIDED: dict[str, str] = {}
BASELINE_FILE = WEB / "project/command-namespace-baseline.json"

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"


def load_baseline() -> dict:
    if BASELINE_FILE.exists():
        return json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
    return {"unprefixed": 0, "accepted": {}}


def scan() -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """(unprefixed, ok) as (surface, name) pairs. Directories are namespaced groups and count as OK."""
    unprefixed: list[tuple[str, str]] = []
    ok: list[tuple[str, str]] = []
    for rel, _why in SURFACES:
        d = WEB / rel
        if not d.is_dir():
            continue
        for entry in sorted(d.iterdir()):
            if entry.name.startswith("."):
                continue
            name = entry.stem if entry.is_file() else entry.name
            if entry.is_file() and entry.suffix != ".md":
                continue
            if any(name.startswith(p) for p in THIRD_PARTY_PREFIXES):
                continue
            # A directory IS a namespace (`opsx/` -> `opsx:apply`), so it cannot collide bare.
            if entry.is_dir() or name.startswith(PREFIX):
                ok.append((rel, name))
            else:
                unprefixed.append((rel, name))
    return unprefixed, ok


def coverage() -> tuple[list[str], list[str], dict[str, list[str]]]:
    """(violations, notes, matrix). A DECIDED command missing a declared surface FAILS."""
    present: dict[str, list[str]] = {}
    for rel in PARITY_SURFACES:
        d = WEB / rel
        if not d.is_dir():
            continue
        for entry in sorted(d.iterdir()):
            name = entry.stem if entry.is_file() else entry.name
            if entry.is_file() and entry.suffix != ".md":
                continue
            if any(name.startswith(p) for p in THIRD_PARTY_PREFIXES) or name.startswith("."):
                continue
            present.setdefault(name, []).append(rel)

    violations: list[str] = []
    notes: list[str] = []
    for name, (want, why) in COVERAGE_DECIDED.items():
        have = present.get(name, [])
        for rel in want:
            if rel not in have:
                violations.append(f"{name}: declared for {rel} but absent there — {why}")
    for name, surfaces in sorted(present.items()):
        if name in COVERAGE_DECIDED:
            continue
        if len(surfaces) < len(PARITY_SURFACES):
            missing = [r for r in PARITY_SURFACES if r not in surfaces]
            reason = COVERAGE_UNDECIDED.get(name)
            if reason:
                notes.append(f"{name}: only on {', '.join(surfaces)} — {reason}")
            else:
                violations.append(
                    f"{name}: on {', '.join(surfaces)} but not {', '.join(missing)}, and its "
                    "coverage is UNDECLARED — add it to COVERAGE_DECIDED or COVERAGE_UNDECIDED")
    return violations, notes, present


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--enforce", action="store_true")
    ap.add_argument("--write-baseline", action="store_true",
                    help="record the CURRENT count. Only ever use this to LOWER it.")
    args = ap.parse_args()

    unprefixed, ok = scan()
    base = load_baseline()
    limit = int(base.get("unprefixed", 0))
    accepted = base.get("accepted", {})

    print(f"{DIM}▶ command namespace — {len(SURFACES)} surface(s), "
          f"{len(ok) + len(unprefixed)} w0m command(s){RESET}")
    for rel, name in ok:
        print(f"  {GREEN}ok{RESET}   {rel}/{name}")
    for rel, name in unprefixed:
        why = accepted.get(name)
        mark = f"{YELLOW}known{RESET}" if why else f"{RED}NEW{RESET}"
        print(f"  {mark:>16} {rel}/{name}" + (f" — {why}" if why else ""))

    if args.write_baseline:
        BASELINE_FILE.write_text(json.dumps(
            {"unprefixed": len(unprefixed), "accepted": accepted}, indent=2) + "\n",
            encoding="utf-8")
        print(f"\n  baseline written: {len(unprefixed)}")
        return 0

    # An empty scan is a broken scan, not a clean one.
    if not ok and not unprefixed:
        print(f"\n{RED}[FAIL] no commands found on any declared surface — cannot measure{RESET}")
        return 1

    cov_bad, cov_notes, matrix = coverage()
    print(f"\n{DIM}  coverage across {len(PARITY_SURFACES)} parity surface(s){RESET}")
    for name, surfaces in sorted(matrix.items()):
        both = len(surfaces) == len(PARITY_SURFACES)
        mark = f"{GREEN}both{RESET}" if both else f"{YELLOW}one {RESET}"
        print(f"  {mark} {name:<16} {', '.join(surfaces)}")
    for n in cov_notes:
        print(f"  {YELLOW}WARN {n}{RESET}")
    for b in cov_bad:
        print(f"  {RED}·{RESET} {b}")

    now = len(unprefixed)
    print(f"\n  unprefixed {now} / baseline {limit}")
    if now > limit:
        new = [f"{r}/{n}" for r, n in unprefixed if n not in accepted]
        print(f"{RED}[FAIL] the unprefixed count ROSE: {now} > {limit}{RESET}")
        for n in new:
            print(f"  {RED}·{RESET} {n} — prefix it `{PREFIX}…`, or namespace it as a directory")
        print(f"  {DIM}Do NOT raise the baseline. `/tasks` was already lost to Antigravity this "
              f"way.{RESET}")
        return 1 if args.enforce else 0
    if now < limit:
        print(f"{GREEN}  RATCHET IMPROVED — lower the baseline to {now} with --write-baseline{RESET}")
    if cov_bad:
        print(f"{RED}[FAIL] {len(cov_bad)} coverage problem(s){RESET}")
        return 1 if args.enforce else 0
    print(f"{GREEN}✅ no new unprefixed command; declared coverage holds{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
