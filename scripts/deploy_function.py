#!/usr/bin/env python3
"""Deploy one or more named Supabase edge functions: the per-function top-level helper (T431).

Usage (via the TTY-gated recipe only):
    just deploy-function <name> [<name> ...]
    e.g. `just deploy-function get-bot-status hume-token linkedin-share`

Replaces 26 hand-written per-function `deploy-*` recipes in wom7api/justfile. They were all the
same line with a different name. Two could never run (their confirm steps were missing from
confirm-policy.json, and the gate fails closed), and one targeted a function with no source
(`deploy-log` → `log-event`). One parameterised recipe keeps the list in ONE place: the
`supabase/functions/` directory itself.

Fails closed, before anything is deployed, on: no names, a name with no function directory
(close matches are suggested), a `_shared`/dot directory, or a duplicate. Per-function flags such as
`verify_jwt` live in `supabase/config.toml`, so the deploy line is identical for every function.

It does NOT touch the project-wide DEPLOY_VERSION/DEPLOY_AT/DEPLOY_COMMIT secrets. Those stamp a
full release (`just deploy-functions` inside `deploy-all`), and re-deploying three functions is not
a release.
"""

from __future__ import annotations

import argparse
import difflib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FUNCTIONS = ROOT / "wom7api" / "supabase" / "functions"


def available() -> list[str]:
    return sorted(p.name for p in FUNCTIONS.iterdir()
                  if p.is_dir() and not p.name.startswith(("_", ".")) and p.name != "node_modules"
                  and (p / "index.ts").is_file())


def validate(names: list[str]) -> list[str]:
    """Return a list of error lines; empty means every name is deployable."""
    have = set(available())
    errors: list[str] = []
    if not names:
        errors.append("no function named. Usage: just deploy-function <name> [<name> ...]")
    seen: set[str] = set()
    for n in names:
        if n in seen:
            errors.append(f"`{n}` given twice")
            continue
        seen.add(n)
        if n not in have:
            near = difflib.get_close_matches(n, sorted(have), n=3)
            hint = f" (did you mean: {', '.join(near)})" if near else ""
            errors.append(f"`{n}` is not a function in {FUNCTIONS.relative_to(ROOT)}{hint}")
    return errors


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Deploy named Supabase edge functions.")
    ap.add_argument("names", nargs="*")
    ap.add_argument("--project-ref", required=True)
    ap.add_argument("--infisical-project-id", required=True)
    ap.add_argument("--list", action="store_true", help="print deployable function names and exit")
    ap.add_argument("--dry-run", action="store_true", help="validate and print the command; deploy nothing")
    a = ap.parse_args(argv)

    if a.list:
        print("\n".join(available()))
        return 0
    errors = validate(a.names)
    if errors:
        for e in errors:
            print(f"❌ {e}")
        print("   Nothing was deployed. `just deploy-function-list` shows every deployable name.")
        return 1

    cmd = ["infisical", "run", f"--projectId={a.infisical_project_id}", "--env=beta", "--silent", "--",
           "supabase", "functions", "deploy", *a.names, "--use-api", "--project-ref", a.project_ref]
    print(f"Deploying {len(a.names)} function(s) to {a.project_ref}: {', '.join(a.names)}")
    if a.dry_run:
        print("DRY RUN:", " ".join(cmd))
        return 0
    os.chdir(ROOT / "wom7api")  # supabase CLI resolves supabase/functions and config.toml from here
    os.execvp(cmd[0], cmd)
    return 1  # unreachable: execvp replaces the process or raises


if __name__ == "__main__":
    sys.exit(main())
