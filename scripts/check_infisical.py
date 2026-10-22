#!/usr/bin/env python3
"""Pre-deploy Infisical check that names the REAL cause of a failure (T429).

Usage:
    python3 scripts/check_infisical.py [--project-id ID] [--env beta]

Why this exists: the old `check-infisical` recipe ran
`infisical run --env=beta --silent -- true >/dev/null 2>&1` and reported EVERY failure as
"session invalid/expired". On 2026-09-23 the session was fine. The estate root had no
`.infisical.json` project link after T421 moved the deploy recipes to `@wom/justfile`, and the CLI
said so ("Please either run infisical init … or pass in project id with --projectId flag"). The
recipe threw that line away, so the owner re-logged in for nothing. A check that can't tell "not
linked" from "not logged in" misleads the operator (measurement-trap lesson T242).

Cases (each prints its own cause and fix; exit 1 on any failure):
  a. no project link: no `--project-id` and no `.infisical.json` in cwd or its parents, OR the CLI
     asks for `infisical init` / `--projectId`
  a'. wrong project id: the CLI answers "Project with ID … not found"
  b. not logged in / expired session
  c. anything else: the first stderr line, ANSI-stripped and truncated

Secret safety: the probe runs `true`, which reads no secret, and stdout is discarded. Only stderr
from the CLI itself is inspected, and at most one line of it is printed. It never calls
`infisical secrets` (list/get print plaintext; see the estate memory on infisical).
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ANSI = re.compile(r"\x1b\[[0-9;]*m")
MAX_LINE = 300
FIX_LOGIN = "run `infisical login` (browser), confirm the active account is aleksei@webomage.com, then re-run."

NO_LINK_PATTERNS = ("infisical init", "--projectid")
WRONG_ID_PATTERNS = ("not found during bot lookup", "correct project id")
AUTH_PATTERNS = (
    "logged in",
    "login session",
    "infisical login",
    "session has expired",
    "token expired",
    "unauthorized",
    "status-code=401",
)
UPDATE_NOTICE_RE = re.compile(r"a new release of infisical is available:\s*([^\r\n]+)", re.IGNORECASE)


def extract_update_notice(stderr: str) -> str | None:
    """Return the version transition string if Infisical printed an update banner on stderr."""
    clean = ANSI.sub("", stderr or "")
    m = UPDATE_NOTICE_RE.search(clean)
    return m.group(1).strip() if m else None


def auto_upgrade_infisical() -> int:
    """Run tools_upgrade.py --only infisical --apply (or test seam W0M_INFISICAL_UPGRADE_CMD)."""
    override = os.environ.get("W0M_INFISICAL_UPGRADE_CMD")
    if override is not None:
        if not override.strip():
            return 0
        cmd = ["sh", "-c", override]
    else:
        script = Path(__file__).resolve().parent / "tools_upgrade.py"
        cmd = [sys.executable, str(script), "--only", "infisical", "--apply"]
    proc = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=300)
    if proc.returncode == 0:
        print("✅ Infisical CLI auto-upgraded and smoke-verified (`just tools-promote --apply` in an agent tree to record known_good).")
    else:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()
        msg = tail[-1][:MAX_LINE] if tail else f"exit {proc.returncode}"
        print(f"⚠️  Infisical auto-upgrade did not complete ({msg}) — continuing with current binary.")
    return proc.returncode


def find_link(start: Path) -> Path | None:
    """Return the nearest `.infisical.json` at or above `start` (the CLI's own lookup)."""
    for d in (start, *start.parents):
        candidate = d / ".infisical.json"
        if candidate.is_file():
            return candidate
    return None


def classify(stderr: str) -> tuple[str, str]:
    """Map CLI stderr to (case, first meaningful line)."""
    lines = [ANSI.sub("", ln).strip() for ln in stderr.splitlines()]
    # INF lines (e.g. "Injecting N secrets") are progress, not errors.
    meaningful = [ln for ln in lines if ln and " INF " not in f" {ln} "]
    low = stderr.lower()
    first = (meaningful[0] if meaningful else "(no stderr output)")[:MAX_LINE]
    if any(p in low for p in NO_LINK_PATTERNS):
        return "no-link", first
    if any(p in low for p in WRONG_ID_PATTERNS):
        return "wrong-id", first
    if any(p in low for p in AUTH_PATTERNS):
        return "auth", first
    return "other", first


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--project-id", default="", help="explicit Infisical project id (root justfile passes it)")
    ap.add_argument("--env", default="beta")
    ap.add_argument("--infisical", default=os.environ.get("W0M_INFISICAL_BIN", "infisical"),
                    help=argparse.SUPPRESS)  # test seam: point at a fake CLI
    args = ap.parse_args(argv)

    print("🔑 Checking Infisical session...")
    cwd = Path.cwd()
    if not args.project_id:
        link = find_link(cwd)
        if link is None:
            print(f"❌ Infisical project link missing — no --project-id given and no .infisical.json in {cwd} or its parents.")
            print("   This is NOT a login problem. Fix: run the recipe from a linked repo, or pass --project-id "
                  "(the root justfile does this via `infisical_project_id`).")
            return 1

    cmd = [args.infisical, "run"]
    if args.project_id:
        cmd.append(f"--projectId={args.project_id}")
    cmd += [f"--env={args.env}", "--silent", "--", "true"]
    try:
        proc = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                              stderr=subprocess.PIPE, text=True, timeout=60)
    except FileNotFoundError:
        print(f"❌ Infisical CLI not found (`{args.infisical}`). Fix: install it (`brew install infisical/get-cli/infisical`).")
        return 1
    except subprocess.TimeoutExpired:
        print("❌ Infisical check timed out after 60s — network/WARP problem, not necessarily auth. Fix: `just check-warp`, then re-run.")
        return 1

    if proc.returncode == 0:
        notice = extract_update_notice(proc.stderr or "")
        if notice:
            print(f"⚠️  Infisical CLI update available ({notice}) — auto-upgrading via tools_upgrade.py...")
            # Only run the real brew upgrade when using the real binary or explicit test seam
            if args.infisical == "infisical" or "W0M_INFISICAL_UPGRADE_CMD" in os.environ:
                auto_upgrade_infisical()
        print("✅ Infisical authenticated.")
        return 0

    case, first = classify(proc.stderr or "")
    if case == "no-link":
        print("❌ Infisical project link missing — the CLI has no project to read from. This is NOT a login problem.")
        print(f"   CLI said: {first}")
        print("   Fix: pass --project-id (root justfile: `infisical_project_id`), or run from a repo that has .infisical.json.")
    elif case == "wrong-id":
        print("❌ Infisical project id is wrong — the CLI can't find that project. This is NOT a login problem.")
        print(f"   CLI said: {first}")
        print("   Fix: correct `infisical_project_id` in the root justfile (it must equal wom7api/.infisical.json workspaceId).")
    elif case == "auth":
        print("❌ Infisical session invalid/expired — every deploy step that injects secrets will fail.")
        print(f"   CLI said: {first}")
        print(f"   Fix: {FIX_LOGIN}")
    else:
        print(f"❌ Infisical check failed (exit {proc.returncode}) for a reason this check does not recognise.")
        print(f"   CLI said: {first}")
        print("   Fix: read the line above. It is not classified as login or project-link, so don't assume either.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
