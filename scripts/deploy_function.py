#!/usr/bin/env python3
"""Deploy one or more named Supabase edge functions: the per-function top-level helper (T431, T432 AC2).

Usage (via the TTY-gated recipe only):
    just deploy-function <name> [<name> ...]
    e.g. `just deploy-function get-bot-status hume-token linkedin-share`

Replaces 26 hand-written per-function `deploy-*` recipes in w0m-api/justfile. They were all the
same line with a different name. Two could never run (their confirm steps were missing from
confirm-policy.json, and the gate fails closed), and one targeted a function with no source
(`deploy-log` → `log-event`). One parameterised recipe keeps the list in ONE place: the
`supabase/functions/` directory itself.

Fails closed, before anything is deployed, on: no names, a name with no function directory
(close matches are suggested), a `_shared`/dot directory, or a duplicate. Per-function flags such as
`verify_jwt` live in `supabase/config.toml`, so the deploy line is identical for every function.

It does NOT touch the project-wide DEPLOY_VERSION/DEPLOY_AT/DEPLOY_COMMIT secrets. Those stamp a
full release (`just deploy-functions` inside `deploy-all`), and re-deploying three functions is not
a release. However, per T432 AC2, it records a `deploy_log` row for `function:<names>` with explicit
`outcome` (`success` | `failed`) and `trigger` (`planned` | `incident`) so per-function deploys are
never invisible to delivery telemetry.
"""

from __future__ import annotations

import argparse
import difflib
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FUNCTIONS = ROOT / "w0m-api" / "supabase" / "functions"


def available() -> list[str]:
    return sorted(
        p.name
        for p in FUNCTIONS.iterdir()
        if p.is_dir()
        and not p.name.startswith(("_", "."))
        and p.name != "node_modules"
        and (p / "index.ts").is_file()
    )


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


def _git_output(*args: str) -> str:
    try:
        res = subprocess.run(
            ["git", *args],
            cwd=ROOT / "w0m-api",
            capture_output=True,
            text=True,
            timeout=5,
        )
        return res.stdout.strip() if res.returncode == 0 else ""
    except Exception:
        return ""


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
    errors = validate(list(a.names))
    if errors:
        for e in errors:
            print(f"❌ {e}")
        print("   Nothing was deployed. `just deploy-function-list` shows every deployable name.")
        return 1

    cmd = [
        "infisical",
        "run",
        f"--projectId={a.infisical_project_id}",
        "--env=beta",
        "--silent",
        "--",
        "supabase",
        "functions",
        "deploy",
        *a.names,
        "--use-api",
        "--project-ref",
        str(a.project_ref),
    ]
    print(f"Deploying {len(a.names)} function(s) to {a.project_ref}: {', '.join(a.names)}")
    if a.dry_run:
        print("DRY RUN:", " ".join(cmd))
        return 0

    deploy_res = subprocess.run(cmd, cwd=ROOT / "w0m-api")
    outcome = "success" if deploy_res.returncode == 0 else "failed"
    trigger = os.environ.get("W0M_DEPLOY_TRIGGER", "planned")
    incident_ref = os.environ.get("W0M_DEPLOY_INCIDENT_REF", "")
    commit = _git_output("rev-parse", "HEAD") or "unknown"
    actor = _git_output("config", "user.email") or "unknown"
    service_label = f"function:{','.join(a.names)}"

    log_cmd = [
        "infisical",
        "run",
        f"--projectId={a.infisical_project_id}",
        "--env=beta",
        "--silent",
        "--",
        sys.executable,
        str(ROOT / "scripts" / "log_deploy.py"),
        service_label,
        commit[:12],
        commit,
        actor,
        "--outcome",
        outcome,
        "--trigger",
        trigger,
    ]
    if incident_ref:
        log_cmd.extend(["--incident-ref", incident_ref])
    subprocess.run(log_cmd, cwd=ROOT, check=False)
    return int(deploy_res.returncode)


if __name__ == "__main__":
    sys.exit(main())
