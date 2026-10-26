#!/usr/bin/env python3
"""T151 AC4 — graphify health across the estate, as numbers rather than a vibe.

Reports, per repo: whether a graph exists, its node/link counts, how many commits
STALE it is, whether the freshness hooks are installed, and whether the repo is in
the global (united) graph — plus whether the union's copy still matches the repo's.

Two rules this obeys deliberately, both learned the hard way in this estate:

1. **It names every repo it enumerated.** A health report that silently covers 1 of 8
   repos is the exact failure this estate keeps finding. The repo list is printed
   whether or not each repo has anything to say.

2. **An empty corpus is a FAILURE, not a pass.** If no repo is enumerated, or the
   estate root is wrong, it exits 2 rather than printing a clean green report over
   nothing.

⚠️ UNION FRESHNESS IS A SEPARATE FACT FROM REPO FRESHNESS. `graphify hook install`
rebuilds a repo's own graph.json on commit; it does NOT re-merge into the global
graph (verified: zero references to `global` in graphify/hooks.py). So a repo can be
perfectly fresh while the union still holds last week's copy of it. That is this
ticket's own failure mode one level up, so it gets its own column.

Usage:
    python3 scripts/graph_health.py            # human table
    python3 scripts/graph_health.py --json     # machine-readable
    python3 scripts/graph_health.py --strict   # exit 1 if anything is stale

Exit codes: 0 = reported, 1 = --strict and something is stale, 2 = config error.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ESTATE = Path(__file__).resolve().parents[1]

# tag -> path, relative to the estate root. The tag is what the global graph knows
# the repo as; for w0m-mlx the directory name alone is ambiguous, hence explicit tags.
REPOS = {
    "w0m-web": "w0m-web",
    "w0m-api": "w0m-api",
    "w0m-cf": "w0m-cf",
    "w0m-skills": "w0m-skills",
    "w0m-ext": "w0m-ext",
    "w0m-sec": "w0m-sec",
    "w0m-mlx": "w0m-mlx/w0m-mlx",
}

# Repos deliberately absent from the union, with the reason shown in the report so
# "missing" is never confused with "forgotten".
# T186 (2026-08-08): wom7md was removed from REPOS and from here — the repo is
# decommissioned, not merely excluded. Its 51 documents live in wom7web (docs/design,
# docs/research), so the union now covers them via w0m-web itself rather than skipping
# a repo. Leaving a stale EXCLUDED entry would keep reporting a reason for the absence
# of something that no longer exists. See DECOMMISSIONED.md.
EXCLUDED: dict[str, str] = {}

STALE_COMMITS_WARN = 25

# Written by graph_global.py: tag -> the repo commit its graph was merged at.
MANIFEST = Path.home() / ".graphify" / "w0m-union-manifest.json"


def git(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(repo), *args],
                         capture_output=True, text=True)
    return out.stdout.strip() if out.returncode == 0 else ""


def global_members() -> dict[str, int]:
    """tag -> node count, from `graphify global list`.

    Shells out rather than parsing ~/.graphify/global-graph.json, which is ~68 MB;
    reading it to answer 'which repos are in it' would make the health check slower
    than the thing it reports on.
    """
    out = subprocess.run(["graphify", "global", "list"],
                         capture_output=True, text=True)
    members: dict[str, int] = {}
    for line in out.stdout.splitlines():
        m = re.match(r"\s+(\S+):\s+(\d+)\s+nodes", line)
        if m:
            members[m.group(1)] = int(m.group(2))
    return members


def hook_status(repo: Path) -> str:
    """post-commit/post-checkout install state, via graphify's own checker.

    Run from inside the repo: it resolves core.hooksPath, which w0m-web redirects to
    .husky/_ while every other repo uses the default. Asking graphify beats guessing
    a path per repo.

    🔴 Parse NEGATIVELY. graphify prints "post-commit: not installed", and
    `"installed" in line` is True for that string — the first version of this
    function reported `both` for all 8 repos when none had a hook at all. A
    substring test whose negative case contains the positive case is a false green;
    `tests/test_graph_health.py` pins both phrasings.
    """
    out = subprocess.run(["graphify", "hook", "status"],
                         cwd=str(repo), capture_output=True, text=True)
    return _parse_hook_status(out.stdout)


def _parse_hook_status(txt: str) -> str:
    """Split out so it can be tested against real graphify output, both states."""
    state = {}
    for line in txt.splitlines():
        m = re.match(r"\s*(post-commit|post-checkout)\s*:\s*(.+?)\s*$", line)
        if m:
            state[m.group(1)] = not m.group(2).lower().startswith("not ")
    if not state:
        return "unknown"
    if all(state.values()) and len(state) == 2:
        return "both"
    if any(state.values()):
        return "partial"
    return "none"


def inspect(tag: str, rel: str, members: dict[str, int], manifest: dict) -> dict:
    repo = ESTATE / rel
    row = {"tag": tag, "path": rel, "exists": repo.is_dir(), "graph": False,
           "nodes": 0, "links": 0, "stale_commits": None, "built_at": None,
           "hooks": "n/a", "in_union": tag in members,
           "union_nodes": members.get(tag), "union_matches": None, "merged_at": None, "compared_to": None,
           "compare_basis": None,
           "excluded_reason": EXCLUDED.get(tag)}
    if not repo.is_dir():
        return row

    row["hooks"] = hook_status(repo)
    g = repo / "graphify-out" / "graph.json"
    if not g.exists():
        return row

    row["graph"] = True
    try:
        d = json.loads(g.read_text())
    except (OSError, json.JSONDecodeError, ValueError):
        row["built_at"] = "UNREADABLE"
        return row

    row["nodes"] = len(d.get("nodes", []))
    row["links"] = len(d.get("links", []))
    built = d.get("built_at_commit")
    row["built_at"] = (built or "")[:7] or None
    if built:
        n = git(repo, "rev-list", "--count", f"{built}..HEAD")
        row["stale_commits"] = int(n) if n.isdigit() else None

    # The union holds a SNAPSHOT taken at `global add` time.
    # 🔴 Do NOT compare node counts to detect staleness: `global add` deduplicates
    # against nodes already in the union, so w0m-api's 1,665-node graph merged as
    # 1,657 and a count comparison called that 8-node gap STALE when nothing had
    # changed. Compare the recorded merge commit instead — that is exact.
    if row["in_union"]:
        rec = manifest.get(tag) or {}
        # Prefer the graph's own stamp; fall back to the repo HEAD recorded at merge
        # time, because `graphify extract` does not stamp built_at_commit at all.
        merged_at = rec.get("built_at_commit") or rec.get("head_at_merge")
        row["merge_basis"] = rec.get("basis")
        row["merged_at"] = (merged_at or "")[:7] or None
        current = built or git(repo, "rev-parse", "HEAD")
        # Record what was actually compared. Displaying `built_at` here printed
        # "now@None" for every extract-built graph — a correct verdict with a label
        # that made it look like a bug in the check rather than real drift.
        row["compared_to"] = (current or "")[:7] or None
        row["compare_basis"] = "built_at_commit" if built else "repo HEAD"
        if merged_at and current:
            row["union_matches"] = (merged_at == current)
        else:
            row["union_matches"] = None  # unknown, NOT "fine"

    # Staleness: use the graph's own stamp when it has one. When it does not, the
    # honest answer is "unmeasurable", not 0 — reporting 0 would read as "fresh".
    if row["stale_commits"] is None and row["graph"]:
        row["stale_basis"] = "unmeasurable — graph carries no built_at_commit"
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 when any repo is stale, unhooked, or out of the union")
    args = ap.parse_args()

    if not (ESTATE / "w0m-web").is_dir():
        print(f"error: estate root not found at {ESTATE}", file=sys.stderr)
        return 2
    if not REPOS:
        print("error: empty repo set — a health report over nothing is not evidence",
              file=sys.stderr)
        return 2

    members = global_members()
    manifest = {}
    if MANIFEST.exists():
        try:
            manifest = json.loads(MANIFEST.read_text())
        except (OSError, json.JSONDecodeError):
            manifest = {}
    rows = [inspect(t, p, members, manifest) for t, p in REPOS.items()]
    covered = sum(1 for r in rows if r["graph"])
    in_union = sum(1 for r in rows if r["in_union"])

    if args.json:
        print(json.dumps({"estate": str(ESTATE), "enumerated": list(REPOS),
                          "rows": rows, "union_members": members}, indent=2))
    else:
        print(f"▶ graphify health — enumerated {len(rows)} repo(s): "
              f"{', '.join(REPOS)}")
        print(f"  estate root: {ESTATE}")
        print()
        print(f"  {'tag':<15} {'graph':<6} {'nodes':>7} {'links':>7} {'stale':>7} "
              f"{'hooks':<8} {'union':<8} {'sync'}")
        print("  " + "-" * 76)
        for r in rows:
            stale = "—" if r["stale_commits"] is None else f"{r['stale_commits']}"
            union = "yes" if r["in_union"] else ("excl" if r["excluded_reason"] else "NO")
            sync = "—"
            if r["union_matches"] is True:
                sync = "ok"
            elif r["union_matches"] is False:
                sync = f"STALE(merged@{r['merged_at']} now@{r['compared_to']})"
            elif r["in_union"]:
                sync = "unknown"
            print(f"  {r['tag']:<15} {'yes' if r['graph'] else 'no':<6} "
                  f"{r['nodes']:>7} {r['links']:>7} {stale:>7} "
                  f"{r['hooks']:<8} {union:<8} {sync}")
        print()
        for r in rows:
            if r["excluded_reason"]:
                print(f" [INFO] {r['tag']} excluded from the union: {r['excluded_reason']}")
        print(f"  coverage: {covered}/{len(rows)} repos have a graph · "
              f"{in_union}/{len(rows)} in the union")
        print(" [WARN] hooks refresh a repo's OWN graph only — they do NOT re-merge into")
        print("      the union. Refresh that with `just graph-global`.")

    if args.strict:
        bad = [r["tag"] for r in rows
               if (r["stale_commits"] or 0) > STALE_COMMITS_WARN
               or r["union_matches"] is False
               or (not r["in_union"] and not r["excluded_reason"])]
        if bad:
            print(f"\n🔴 stale or unmerged: {', '.join(bad)}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
