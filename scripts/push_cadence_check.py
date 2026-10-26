#!/usr/bin/env python3
"""Push cadence — unpushed work is work that exists in exactly one place.

Owner rule, 2026-08-20: *"we have to push at least daily and with every completed ticket also."*

The rule exists because of what today looked like before it: **34 commits across 6 repos, none
pushed**, representing a full day. Every one of them lived on a single laptop — while the very
ticket being worked ([[T231]]) is about not depending on a single laptop for backups. The estate
had a gate for stale STATE.md and none for unpushed commits.

Two conditions, both measured per repo:

  1. **AGE** — the oldest unpushed commit is older than `--max-age-hours` (default 24).
  2. **A COMPLETED TICKET IS UNPUSHED** — an unpushed commit message names a ticket whose
     `status:` is now `done`. Shipping a ticket and leaving it local is the case the owner named
     explicitly, and it is invisible to an age check on its own: a ticket can be finished and
     pushed-late within the same hour.

⚠️ It reports UNPUSHED, not UNCOMMITTED. Uncommitted work is a choice in progress; unpushed work is
finished work with no second copy.

Advisory by default so it can be read at any time; `--enforce` exits 1 for a hook.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ESTATE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ESTATE / "scripts"))  # estate root scripts/ (T419)
from tasks_query import resolve_tickets_dir  # noqa: E402 — canonical .tasks/ resolver (T411)
REPOS = ["wom7web", "wom7api", "wom7func", "wom7ext", "wom7mlx", "wom7sec", "wom7skills"]
TICKET = re.compile(r"\bT(\d{1,4})\b")
HOME = Path.home()


def detached_mirror_kind(estate: Path, home: Path, env: "os._Environ[str] | dict[str, str]") -> str | None:
    """Name the tree when every repo in it is checked out DETACHED (a release tag, or origin/beta), so none has an upstream to be ahead of.

    Release worktrees (`~/.w0m/releases/<v>/w0m`) and the persistent stable worktree (`~/.w0m/stable/w0m`) have this shape by design; a
    live checkout does not. The path test is a real parent-path test: a sibling such as `~/.w0m/releases-old` is not a mirror."""
    if env.get("W0M_RELEASE_WORKTREE") == "1":
        return "release worktree"
    for sub_dir, kind in ((".w0m/releases", "release worktree"), (".w0m/stable", "stable worktree")):
        if estate == home / sub_dir or (home / sub_dir) in estate.parents:
            return kind
    return None


def git(repo: Path, *args: str) -> str | None:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)
    return r.stdout.strip() if r.returncode == 0 else None


def done_tickets() -> set[str]:
    """Tickets whose record says the work is finished."""
    out = set()
    for f in resolve_tickets_dir().glob("T*.md"):
        head = f.read_text(encoding="utf-8", errors="replace")[:400]
        m = re.search(r"^status:\s*(\S+)", head, re.M)
        if m and m.group(1) in ("done", "archived"):
            out.add(f.stem)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-age-hours", type=float, default=24.0)
    ap.add_argument("--enforce", action="store_true")
    a = ap.parse_args()

    finished = done_tickets()
    if not finished:
        print("  ❌ parsed 0 done tickets — the reader is broken, not the queue empty.")
        return 2

    now = time.time()
    findings: list[str] = []
    rows: list[tuple[str, int, float, list[str]]] = []
    checked = 0

    for name in REPOS:
        repo = ESTATE / name
        if not (repo / ".git").exists():
            continue
        if git(repo, "rev-parse", "--abbrev-ref", "@{u}") is None:
            continue  # no upstream — nothing to be behind
        checked += 1
        log = git(repo, "log", "--format=%ct%x09%s", "@{u}..") or ""
        lines = [l for l in log.splitlines() if l.strip()]
        if not lines:
            continue
        oldest = min(int(l.split("\t")[0]) for l in lines)
        age_h = (now - oldest) / 3600
        shipped = sorted({f"T{m}" for l in lines for m in TICKET.findall(l.split("\t", 1)[1])
                          if f"T{m}" in finished})
        rows.append((name, len(lines), age_h, shipped))
        if age_h > a.max_age_hours:
            findings.append(f"{name}: oldest unpushed commit is {age_h:.1f}h old "
                            f"(limit {a.max_age_hours:g}h)")
        if shipped:
            findings.append(f"{name}: {', '.join(shipped)} completed but unpushed")

    if not checked:
        # A release or stable worktree has every repo detached, so none has an upstream: nothing there can be unpushed.
        kind = detached_mirror_kind(ESTATE, HOME, os.environ)
        if kind:
            print(f"  ✅ push cadence — {kind} (every repo is checked out detached, so there is nothing to be ahead of).")
            return 0
        print("  ❌ no repo had an upstream — cannot judge cadence. Unknown, not clean.")
        return 2

    if not rows:
        print(f"  ✅ push cadence — {checked} repo(s) with an upstream, nothing unpushed.")
        return 0

    print(f"  ▶ push cadence — {checked} repo(s) checked")
    for name, n, age_h, shipped in rows:
        tag = f" · ships {', '.join(shipped)}" if shipped else ""
        print(f"      {name:<14} {n:>3} unpushed · oldest {age_h:>5.1f}h{tag}")

    if not findings:
        print(f"\n  ✅ within cadence — nothing older than {a.max_age_hours:g}h, no completed "
              f"ticket left local.")
        return 0

    print(f"\n  🔴 {len(findings)} finding(s):")
    for f in findings:
        print(f"      · {f}")
    print("\n  Unpushed work exists in exactly one place. `git push` in the repos above.")
    return 1 if a.enforce else 0


if __name__ == "__main__":
    sys.exit(main())
