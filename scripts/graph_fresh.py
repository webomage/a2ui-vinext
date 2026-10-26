#!/usr/bin/env python3
"""Guarantee the UNITED graph is current before anything trusts it (T163 AC2).

Why this exists
---------------
`graphify hook install` refreshes each repo's OWN graph on post-commit but **never
re-merges the union** — that is a manual `just graph-global`. So the united graph
drifts behind every single commit. Measured 2026-08-04: **all 7 in-union repos were
STALE**, including from commits made minutes earlier, and `graph-health --strict`
exited 1.

That inverts the whole premise of T163. Making "graph before grep" the default while
the index lags reality means the default path answers *confidently wrong* — strictly
worse than the grep it replaces, because grep at least reads current bytes. A stale
index is not a slow index; it is a lying one.

So: check (~1.4s), and re-merge only when actually stale (~13s). Cheap enough to sit
in front of every `just ask` without anyone wanting to skip it.

    graph_fresh.py               check; auto-merge if stale; prove it took
    graph_fresh.py --check-only  check only, exit 1 if stale (never writes)
    graph_fresh.py --quiet       say nothing when already fresh

NO VACUOUS GREEN: after a merge this RE-CHECKS and fails if the union is still
behind, rather than assuming the merge worked because it exited 0.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
HEALTH = HERE / "graph_health.py"
GLOBAL = HERE / "graph_global.py"

# How far a repo's own graph may lag HEAD before the graph path is refused outright.
# Deliberately much tighter than graph_health's STALE_COMMITS_WARN (25): that constant
# governs a HEALTH REPORT a human reads, this one governs whether an AGENT is allowed to
# answer "where is X" from the index instead of reading the file. A dozen commits of drift
# is invisible in a dashboard and decisive in an answer.
STALE_COMMITS_FAIL = 10


def probe() -> tuple[list[str], list[tuple[str, int]], str]:
    """Return (union_behind, graph_behind, error).

    TWO INDEPENDENT AXES, and checking only one is how this script was wrong on its
    first cut (2026-08-04, caught within minutes of writing it):

      union_behind  — the union does not carry the repo's current graph.
                      `union_matches` compares merged_at to the graph's BUILT_AT commit.
                      Fix: `graph-global`, ~13s. Cheap, so we auto-fix it.
      graph_behind  — the repo's OWN graph was built N commits before HEAD.
                      ⚠️ `union_matches` can be True while this is 13 — the union
                      faithfully carries a graph that is itself out of date. Checking
                      `union_matches` alone therefore reports "current" about a lying
                      index. Fix: re-extract that repo, MINUTES — never silently run
                      inside someone's question.

    Missing evidence is an error, never 'fresh'.
    """
    p = subprocess.run([sys.executable, str(HEALTH), "--json"],
                       capture_output=True, text=True, cwd=HERE.parent)
    if p.returncode != 0 and not p.stdout.strip():
        return [], [], f"graph-health failed (rc={p.returncode}): {(p.stderr or '').strip()[:200]}"
    try:
        rows = json.loads(p.stdout)["rows"]
    except (json.JSONDecodeError, KeyError) as e:
        return [], [], f"graph-health emitted no usable JSON: {e}"
    # Only in-union repos can be stale-in-union. (Until T186 this cited wom7md as the
    # standing exclusion; that repo is decommissioned and the exclusion set is now empty.)
    inu = [r for r in rows if r.get("in_union")]
    union_behind = [r["tag"] for r in inu if r.get("union_matches") is not True]
    graph_behind = [(r["tag"], r["stale_commits"]) for r in inu if (r.get("stale_commits") or 0) > 0]
    return union_behind, graph_behind, ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check-only", action="store_true", help="exit 1 if stale; never write")
    ap.add_argument("--quiet", action="store_true", help="silent when already fresh")
    args = ap.parse_args()

    union_behind, graph_behind, err = probe()
    if err:
        # Cannot confirm freshness is a FAILURE, not a pass — the estate's standing rule.
        print(f"❌ graph freshness UNKNOWN — {err}", file=sys.stderr, flush=True)
        return 1

    # Axis 2 is always REPORTED, never auto-fixed: re-extraction takes minutes and must
    # not run inside a question. Loud enough to act on, not silent enough to trust.
    bad = [(t, n) for t, n in graph_behind if n > STALE_COMMITS_FAIL]
    if graph_behind:
        detail = ", ".join(f"{t} +{n}" for t, n in sorted(graph_behind, key=lambda x: -x[1]))
        print(f"[WARN] repo graphs built BEHIND HEAD: {detail}"
              f"\n   → these answers may be out of date; re-extract with: just graph-global --rebuild",
              file=sys.stderr, flush=True)

    if union_behind and not args.check_only:
        print(f"⟳ union stale for {len(union_behind)} repo(s) ({', '.join(union_behind)}) — re-merging…", flush=True)
        m = subprocess.run([sys.executable, str(GLOBAL)], capture_output=True, text=True,
                           cwd=HERE.parent.parent)
        if m.returncode != 0:
            print(f"❌ graph-global failed (rc={m.returncode}): {(m.stderr or '').strip()[:300]}",
                  file=sys.stderr, flush=True)
            return 1
        # Prove it, don't assume it: a merge that exits 0 but leaves the union behind is
        # exactly the false green this script exists to prevent.
        union_behind, graph_behind, err2 = probe()
        if err2 or union_behind:
            print(f"❌ re-merge did NOT make the union current — still behind: "
                  f"{', '.join(union_behind) or err2}", file=sys.stderr, flush=True)
            return 1
        bad = [(t, n) for t, n in graph_behind if n > STALE_COMMITS_FAIL]
        print("✅ union re-merged and verified current", flush=True)
    elif union_behind:
        print(f"❌ union STALE for {len(union_behind)}: {', '.join(union_behind)}\n"
              f"   → fix: just graph-global", file=sys.stderr, flush=True)
        return 1

    if bad:
        print(f"❌ refusing to call this graph current — {', '.join(f'{t} is +{n} commits behind' for t, n in bad)}"
              f" (limit {STALE_COMMITS_FAIL})", file=sys.stderr, flush=True)
        return 1
    if not union_behind and not graph_behind and not args.quiet:
        print("✅ graphs are current — repo graphs at HEAD, union carries them", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
