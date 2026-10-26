#!/usr/bin/env python3
"""Is estate-root configuration versioned? (T294 AC4 — the probe that closes D32)

WHAT D32 WAS
------------
`@wom` was not a git repo, so everything sitting beside the seven repos — the estate MCP config, the
agent config, cross-repo audit reports — was versioned NOWHERE. Recorded as debt D32.

🔴 WHY A COMMIT DOES NOT CLOSE IT. Creating `casualuser/w0m` and committing those files fixes the
files that existed on 2026-09-02. It notices nothing about the next one. D32 is not "these files are
untracked", it is "estate-level configuration has no home", and that condition returns the moment
someone drops a config file at the estate root and it sits there unnoticed — which is exactly how the
first fifteen accumulated. A debt closed by an act rather than by a check is closed until it isn't.

So this asks the standing question: **is anything at the estate root untracked and unignored?**

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
It does not recurse into the seven repos — each governs itself, and their contents are excluded from
the estate repo via `.git/info/exclude` (NOT `.gitignore`; a parent .gitignore is read by tools below
it and broke osv-scanner estate-wide, see T294 AC2). It does not judge WHICH files belong in version
control; a deliberate exclusion is a decision someone writes down, and this reports the ones nobody
has decided about.

Run:  python3 scripts/estate_config_versioned.py [--json]
Exit: 0 = everything at the estate root is tracked or deliberately ignored
      1 = something is unversioned and undecided
      2 = could not measure (no estate repo, git unavailable) — never reported as clean
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ESTATE = Path(__file__).resolve().parents[1]
GREEN, RED, YELLOW, DIM, RESET = (
    ("\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m")
    if sys.stdout.isatty() else ("", "", "", "", "")
)


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(ESTATE), *args],
                          capture_output=True, text=True, check=False)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    # 🔴 An unmeasurable estate is not a clean one. If the repo is gone, D32 is BACK — that is the
    # loudest possible finding, not a reason to skip.
    top = git("rev-parse", "--show-toplevel")
    if top.returncode or Path(top.stdout.strip() or "/nonexistent") != ESTATE:
        print(f"{RED}✗ {ESTATE} is not a git repo — D32 has returned in full: estate-level "
              f"configuration is versioned nowhere{RESET}")
        return 2

    # Untracked and not ignored: files nobody has either committed or excluded.
    r = git("ls-files", "--others", "--exclude-standard")
    if r.returncode:
        print(f"{RED}✗ could not enumerate: {r.stderr.strip()[:160]}{RESET}")
        return 2
    undecided = sorted(f for f in r.stdout.split("\n") if f.strip())

    tracked = [f for f in git("ls-files").stdout.split("\n") if f.strip()]
    # An empty corpus means the probe is looking at nothing and would report clean forever.
    if not tracked:
        print(f"{RED}✗ the estate repo tracks NOTHING — refusing to report over an empty corpus"
              f"{RESET}")
        return 2

    if args.json:
        print(json.dumps({"tracked": len(tracked), "undecided": undecided}, indent=2))
        return 1 if undecided else 0

    print(f"{DIM}estate repo:{RESET} {ESTATE.name} — {len(tracked)} file(s) versioned")
    if not undecided:
        print(f"{GREEN}✅ D32 holds closed — nothing at the estate root is unversioned and "
              f"undecided{RESET}")
        return 0
    print(f"{RED}✗ {len(undecided)} file(s) at the estate root are neither tracked nor "
          f"ignored:{RESET}")
    for f in undecided[:12]:
        print(f"  {RED}·{RESET} {f}")
    if len(undecided) > 12:
        print(f"  {DIM}… and {len(undecided) - 12} more{RESET}")
    print(f"{DIM}  Commit it, or exclude it deliberately — an undecided file is how D32 "
          f"accumulated in the first place.{RESET}")
    print(f"{RED}✗ D32: {len(undecided)} undecided file(s) at the estate root{RESET}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
