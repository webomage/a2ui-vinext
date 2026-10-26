#!/usr/bin/env python3
"""Audit the estate's ignore files — inventory, rule/index agreement, and required coverage.

    python3 scripts/ignore_audit.py             # report
    python3 scripts/ignore_audit.py --enforce   # exit 1 on a blocking finding

THE FAILURE MODE THIS EXISTS FOR
--------------------------------
**A rule and the index disagree, and nothing notices.** git cannot un-track a committed file by
adding a pattern later, so every rule written after the fact is silently inert for whatever already
exists. It is invisible from either side: `git status` is clean, and the .gitignore reads correct.

It surfaced three times in one session before anyone went looking:

  · `.turbo/` and `scratch/` were reported as an Obsidian-vs-Quartz corpus divergence. The real
    cause was that both are TRACKED while matching .gitignore.
  · `check_final{,2,3}.txt` -- 2,792 lines of Astro build log -- were tracked despite `check*.txt`.
  · `w0m-ext/docs/ARCHITECTURE.md` turned out to be gitignored, so an edit to it could never
    survive a clone. That one was found only because a doc link happened to point at it.

Measured across the estate on 2026-08-31: **540 tracked-but-ignored files**, 502 of them under a
single rule.

WHAT IS AUDITED, AND WHAT IS DELIBERATELY NOT
---------------------------------------------
Scope is DECLARED in `project/ignore-policy.json`, never discovered, because most ignore files here
are not ours: 11 third-party repos under `_ext/`, 10 vendored MLX repos, orca under `_in/`, and a
dozen written by tools. Auditing those would be auditing other people's decisions. An ignore file
inside a governed repo that the policy does not list is DRIFT and is reported -- that is what stops
"declared scope" from becoming "scope that quietly shrinks".

BLOCKING vs REPORTED
--------------------
Blocking: inventory drift, a missing required rule, an accepted exception that no longer matches.
Reported only: the undecided tracked-but-ignored backlog. Deciding those means choosing whether to
untrack a file or drop a rule, which is owner work -- and a gate that blocks on an undecided
question is one somebody switches off (T135 AC8).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ESTATE = Path(__file__).resolve().parents[1]
WEB_ROOT = ESTATE / "w0m-web"
POLICY = ESTATE / "project/policies/ignore-policy.json"

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"

IGNORE_NAME = re.compile(r"^\.[a-z0-9]*ignore$|^\.gitignore$")


def load_policy() -> dict:
    return json.loads(POLICY.read_text(encoding="utf-8"))


def _repos(pol: dict) -> list[str]:
    return [k for k in pol["governed"] if not k.startswith("_")]


def find_ignore_files(repo: str, pol: dict) -> list[str]:
    """Every ignore-shaped file inside a governed repo, minus tool-generated and vendored trees."""
    root = ESTATE / repo
    gen = set(pol["generated"]["dirs"])
    vend = tuple(pol["vendored"]["prefixes"])
    out: list[str] = []
    for p in root.rglob(".*ignore"):
        if not IGNORE_NAME.match(p.name):
            continue
        rel = p.relative_to(root).as_posix()
        # Prefix match, not segment match: `.husky/_` is two segments and a segment-wise test
        # silently missed it, reporting husky's own generated file as estate drift.
        if any(rel == g or rel.startswith(g.rstrip("/") + "/") for g in gen):
            continue
        if any(rel.startswith(v.rstrip("/") + "/") for v in vend):
            continue
        # Build output. `target/` is Rust's and holds vendored CMake deps that ship their own
        # .gitignore -- 2 of them, which the first run reported as estate drift.
        if any(seg in ("node_modules", "target", "dist", "build", "ext", ".quartz-engine", "public")
               for seg in rel.split("/")[:-1]):
            continue
        out.append(rel)
    return sorted(out)


def tracked_but_ignored(repo: str) -> list[tuple[str, str]]:
    """(rule, path) for every tracked file some ignore rule matches. The core check."""
    root = ESTATE / repo
    ls = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True, check=False)
    if ls.returncode != 0:
        return []
    ci = subprocess.run(
        ["git", "check-ignore", "--no-index", "-v", "--stdin"],
        cwd=root, input=ls.stdout, capture_output=True, text=True, check=False,
    )
    out: list[tuple[str, str]] = []
    for line in ci.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) == 2:
            rule, path = parts
            # A negation (`!pattern`) means NOT ignored -- it is the rule working, not drift.
            if ":!" in rule or rule.rsplit(":", 1)[-1].startswith("!"):
                continue
            out.append((rule, path))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--enforce", action="store_true")
    args = ap.parse_args()

    pol = load_policy()
    repos = _repos(pol)
    blocking: list[str] = []
    notes: list[str] = []

    print(f"{DIM}▶ ignore audit — {len(repos)} governed repo(s){RESET}")

    # ── 1. INVENTORY ───────────────────────────────────────────────────────────────────────────
    declared_total = found_total = 0
    for repo in repos:
        declared = set(pol["governed"][repo])
        found = set(find_ignore_files(repo, pol))
        declared_total += len(declared)
        found_total += len(found)
        for extra in sorted(found - declared):
            blocking.append(f"{repo}: {extra} exists but is not declared in ignore-policy.json")
        for missing in sorted(declared - found):
            blocking.append(f"{repo}: {missing} is declared but does not exist")
    print(f"  inventory   {found_total} ignore file(s) found, {declared_total} declared")

    # ── 2. REQUIRED RULES ──────────────────────────────────────────────────────────────────────
    exempt = {(e["repo"], e["pattern"]) for e in pol["required_rules"]["exempt"]}
    missing_rules = 0
    for repo in repos:
        gi = ESTATE / repo / ".gitignore"
        text = gi.read_text(encoding="utf-8", errors="replace") if gi.exists() else ""
        for rule in pol["required_rules"]["rules"]:
            if (repo, rule["pattern"]) in exempt:
                continue
            if not re.search(rule["match"], text, re.M):
                missing_rules += 1
                blocking.append(f"{repo}: .gitignore has no `{rule['pattern']}` rule — {rule['why']}")
    print(f"  required    {len(pol['required_rules']['rules'])} rule(s) x repo, {missing_rules} missing")

    # ── 3. RULE vs INDEX ───────────────────────────────────────────────────────────────────────
    accepted = {(e["repo"], e["path"]) for e in pol["accepted_tracked"]["entries"]}
    undecided = {(e["repo"], e["path"]) for e in pol["undecided_tracked"]["entries"]}
    seen_accepted: set[tuple[str, str]] = set()
    total_conflicts = 0
    unknown: dict[tuple[str, str], int] = {}

    for repo in repos:
        for rule, path in tracked_but_ignored(repo):
            total_conflicts += 1
            key = next((k for k in accepted | undecided
                        if k[0] == repo and (path == k[1] or path.startswith(k[1]))), None)
            if key in accepted:
                seen_accepted.add(key)
            elif key in undecided:
                pass
            else:
                unknown[(repo, rule.rsplit(":", 1)[-1])] = unknown.get((repo, rule.rsplit(":", 1)[-1]), 0) + 1

    print(f"  rule/index  {total_conflicts} tracked file(s) matched by an ignore rule")
    for (repo, rule), n in sorted(unknown.items(), key=lambda x: -x[1]):
        blocking.append(f"{repo}: {n} tracked file(s) match `{rule}` — undeclared; decide and record it")

    for entry in pol["accepted_tracked"]["entries"]:
        if (entry["repo"], entry["path"]) not in seen_accepted:
            blocking.append(f"{entry['repo']}: accepted exception `{entry['path']}` matches nothing "
                            "any more — STALE, remove it")

    for e in pol["undecided_tracked"]["entries"]:
        notes.append(f"{e['repo']}: {e['path']} — {e['count']} file(s) UNDECIDED. {e['note']}")

    for note in notes:
        print(f"  {YELLOW}WARN {note}{RESET}")

    if blocking:
        print(f"\n{RED}[FAIL] {len(blocking)} finding(s){RESET}")
        for b in blocking:
            print(f"  {RED}·{RESET} {b}")
        return 1 if args.enforce else 0

    print(f"\n{GREEN}✅ ignore files are governed — inventory matches, required rules present, "
          f"every rule/index conflict accounted for{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
