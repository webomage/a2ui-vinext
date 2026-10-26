#!/usr/bin/env python3
"""T235 AC9 — refuse to commit work this agent did not do.

Why this exists
---------------
On 2026-08-19 a `git add -A` in this shared worktree swept the parallel **Antigravity** agent's
in-flight `project/scripts/upwork_mcp_sync.py` into a w0m commit. It was caught only because
`version-check` happened to trip on a version string inside the file — i.e. by luck, not by a gate.
Nothing in the estate asked *"am I committing work I did not do?"*.

Two checks, deliberately different in kind
------------------------------------------
1. **Co-tenancy registry** (declarative, precise, blind to unknown paths): paths in
   `project/co-tenancy.json` belong to another agent. Staging one is an error. This cannot catch a
   path nobody has declared yet — that is what check 2 is for.
2. **Open write handle** (general, precise, timing-dependent): if another live process holds a
   staged file open for writing, that file is in flight *right now* and is not ours to commit.
   Catches undeclared paths, but only while the other process still has the handle open.

Neither check is sufficient alone, and this docstring is the honest statement of that. The registry
is the durable memory; the lsof probe is the live tripwire.

Exit 1 on any hit. `W0M_STAGE_GUARD_OK=1` overrides (for the deliberate case where w0m really is
taking ownership of a co-tenant path) — it prints what it let through, so the override is auditable.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "w0m-web" / "project" / "co-tenancy.json"


def staged_files() -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        capture_output=True, text=True, check=False,
    )
    return [ln for ln in out.stdout.splitlines() if ln.strip()]


def registry_hits(files: list[str]) -> list[tuple[str, str, str]]:
    """(path, owner, reason) for every staged file a declared co-tenant owns."""
    if not REGISTRY.exists():
        return []
    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
    hits = []
    for agent, spec in (reg.get("agents") or {}).items():
        for pat in spec.get("paths", []):
            for f in files:
                # A trailing "/" declares a directory subtree; anything else is an exact path.
                owned = f.startswith(pat) if pat.endswith("/") else f == pat
                if owned:
                    hits.append((f, agent, spec.get("reason", "")))
    return hits


def open_write_handles(files: list[str]) -> list[tuple[str, str]]:
    """(path, holder) for staged files another live process holds open for writing.

    Best-effort: no lsof, no finding. A missing prerequisite must not read as a pass, so the
    caller prints the degraded state rather than silently returning clean.
    """
    if not shutil.which("lsof"):
        return []
    hits = []
    me = os.getpid()
    for f in files:
        p = Path(f)
        if not p.exists():
            continue
        out = subprocess.run(["lsof", "-F", "pcan", str(p)], capture_output=True, text=True, check=False)
        pid, cmd = None, None
        for ln in out.stdout.splitlines():
            if ln.startswith("p"):
                pid, cmd = int(ln[1:] or 0), None
            elif ln.startswith("c"):
                cmd = ln[1:]
            elif ln.startswith("a") and pid and pid != me and ("w" in ln[1:] or "u" in ln[1:]):
                hits.append((f, f"{cmd or '?'} (pid {pid})"))
    return hits


def main() -> int:
    files = staged_files()
    if not files:
        return 0

    reg = registry_hits(files)
    live = open_write_handles(files)
    override = os.environ.get("W0M_STAGE_GUARD_OK") == "1"

    if not reg and not live:
        note = "" if shutil.which("lsof") else "  ⚠️ lsof absent — live-handle check DEGRADED, registry only"
        print(f"  ✅ stage-guard — {len(files)} staged file(s), none owned elsewhere{note}")
        return 0

    label = "⚠️ OVERRIDDEN" if override else "❌"
    print(f"  {label} stage-guard — staged work that may not be this agent's:")
    for f, agent, why in reg:
        print(f"      · {f}\n          declared owner: {agent} — {why}")
    for f, holder in live:
        print(f"      · {f}\n          open for writing RIGHT NOW by {holder}")
    if override:
        print("  W0M_STAGE_GUARD_OK=1 — allowed, and recorded above.")
        return 0
    print("\n  Unstage them (`git restore --staged <path>`), or set W0M_STAGE_GUARD_OK=1 if w0m is")
    print("  deliberately taking ownership. Do NOT use --no-verify: it is prohibited estate-wide.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
