#!/usr/bin/env python3
"""T151 AC2 — build/refresh the united multi-repo graphify graph, in one command.

Merges every first-party repo's graph into ~/.graphify/global-graph.json under an
EXPLICIT tag, and records what was merged in a sidecar manifest.

Why the manifest exists (this is the load-bearing part):
    `graphify global list` reports a node count and a date. Node count CANNOT be used
    to detect staleness, because `global add` deduplicates against nodes already in
    the union — w0m-api's 1,665-node graph merged as 1,657, and a naive count
    comparison reported that 8-node gap as "STALE" when nothing was wrong. The
    manifest records each repo's `built_at_commit` AT MERGE TIME, so
    `graph_health.py` can compare commits, which is exact.

⚠️ `graphify hook install` does NOT refresh the union — verified, zero references to
`global` in graphify/hooks.py. Hooks keep each repo's own graph.json current; this
command is what folds them together. Run it after a batch of work, not per commit.

Usage:
    python3 scripts/graph_global.py              # refresh every repo
    python3 scripts/graph_global.py --only api   # substring filter
    python3 scripts/graph_global.py --rebuild    # re-extract before merging

Exit codes: 0 = merged, 1 = a repo failed, 2 = config error.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ESTATE = Path(__file__).resolve().parents[1]
MANIFEST = Path.home() / ".graphify" / "w0m-union-manifest.json"

REPOS = {
    "w0m-web": "w0m-web",
    "w0m-api": "w0m-api",
    "w0m-cf": "w0m-cf",
    "w0m-skills": "w0m-skills",
    "w0m-ext": "w0m-ext",
    "w0m-sec": "w0m-sec",
    "w0m-mlx": "w0m-mlx/w0m-mlx",
}

# Not a failure — an excluded repo is a recorded decision. See T151 AC2.
# T186 (2026-08-08): emptied. wom7md is DECOMMISSIONED, not excluded — its 51 documents
# live in w0m-web (docs/design, docs/research) and reach the union through it. The entry
# survived the first pass of that ticket and kept printing "wom7md excluded by decision"
# on every union refresh, which is the exact failure the ticket was written to avoid: a
# recorded reason outliving the thing it explains.
EXCLUDED: dict[str, str] = {}


def run(cmd: list[str], cwd: Path | None = None) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=str(cwd) if cwd else None,
                       capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr)


def settled(repo: Path, budget_s: float) -> bool:
    """Is this repo's graph finished being written, or is a rebuild still in flight?

    T187. `.husky/post-commit` launches the per-repo rebuild in the BACKGROUND, so a union
    refresh moments later can merge a graph that is half-written. That would be invisible:
    `graphify extract` does not stamp `built_at_commit` (only `update` does), so for 6 of 7
    repos the manifest falls back to `head_at_merge` — recording a mid-rebuild graph as
    being AT HEAD. The union would then report *current* while holding older content, in
    the one artifact `just ask` is told to trust first.

    Signal: size+mtime stable across two consecutive samples. A rebuild writes the file, so
    a changing stamp means "in flight". Cheap, needs no graphify internals, and errs toward
    reporting a skip rather than certifying freshness it cannot see.

    budget_s <= 0 disables the wait (manual runs, where no rebuild was just triggered).
    """
    g = repo / "graphify-out" / "graph.json"
    if budget_s <= 0 or not g.exists():
        return True

    # Fast path (T187 AC6). Polling every repo costs a sample-pair each, which measured
    # 4,341 ms across 7 repos — over the 3 s budget this AC set, i.e. a tax on every push
    # to guard against something that is almost never happening. A file untouched for
    # longer than QUIET_S cannot be mid-write, so answer from mtime alone and poll only
    # the repo that was actually just rebuilt.
    quiet_s = 2.0
    try:
        st = g.stat()
    except OSError:
        return False
    if (time.time() - st.st_mtime) > quiet_s:
        return True

    interval, waited, last = 0.4, 0.0, (st.st_size, st.st_mtime_ns)
    while waited <= budget_s:
        time.sleep(interval)
        waited += interval
        try:
            st = g.stat()
        except OSError:
            return False
        stamp = (st.st_size, st.st_mtime_ns)
        if stamp == last:
            return True
        last = stamp
    return False


def built_at(repo: Path) -> str | None:
    g = repo / "graphify-out" / "graph.json"
    if not g.exists():
        return None
    try:
        return json.loads(g.read_text()).get("built_at_commit")
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="substring filter on the repo tag")
    ap.add_argument("--rebuild", action="store_true",
                    help="re-extract each repo before merging (slow: minutes per repo)")
    ap.add_argument("--settle", type=float, default=0.0, metavar="SECONDS",
                    help="T187: wait up to SECONDS for each repo's graph.json to stop "
                         "changing before merging it, and SKIP any repo still being "
                         "written. Default 0 (no wait) for manual runs; the pre-push "
                         "hook passes a budget because post-commit rebuilds in background.")
    args = ap.parse_args()

    if not (ESTATE / "w0m-web").is_dir():
        print(f"error: estate root not found at {ESTATE}", file=sys.stderr)
        return 2

    targets = {t: p for t, p in REPOS.items() if not args.only or args.only in t}
    if not targets:
        print(f"error: --only {args.only!r} matched no repo of {list(REPOS)} — "
              "a filter that matches nothing is an error, not an empty success",
              file=sys.stderr)
        return 2

    print(f"▶ union refresh — {len(targets)} repo(s): {', '.join(targets)}")
    for tag, reason in EXCLUDED.items():
        print(f" [INFO] {tag} excluded by decision: {reason}")

    manifest = {}
    if MANIFEST.exists():
        try:
            manifest = json.loads(MANIFEST.read_text())
        except (OSError, json.JSONDecodeError):
            manifest = {}

    failures = []
    unsettled = []
    for tag, rel in targets.items():
        repo = ESTATE / rel
        if not repo.is_dir():
            print(f"  🔴 {tag}: {rel} is not a directory")
            failures.append(tag)
            continue

        # T187 AC1/AC2 — never merge a graph that is still being written. A repo that does
        # not settle is SKIPPED and named; its manifest entry is left untouched so the union
        # keeps reporting the last commit it genuinely merged, instead of stamping HEAD over
        # partial content.
        if not settled(repo, args.settle):
            print(f" [SKIP] {tag}: SKIPPED — graph.json still being written after "
                  f"{args.settle:g}s (rebuild in flight); manifest entry left unchanged")
            unsettled.append(tag)
            continue

        graph_file = repo / "graphify-out" / "graph.json"
        if args.rebuild and graph_file.exists():
            print(f"  ⏳ {tag}: updating code graph at HEAD (local AST, no LLM, stamps built_at_commit)…")
            rc, out = run(["graphify", "update", "."], cwd=repo)
            if rc != 0:
                print(f"  🔴 {tag}: update failed rc={rc} — {out.strip().splitlines()[:1]}")
                failures.append(tag)
                continue
        elif not graph_file.exists():
            print(f"  ⏳ {tag}: extracting (--code-only: local AST, no API key, "
                  "no source leaves the machine)…")
            rc, out = run(["graphify", "extract", str(repo), "--code-only"])
            if rc != 0:
                print(f"  🔴 {tag}: extract failed rc={rc} — {out.strip().splitlines()[:1]}")
                failures.append(tag)
                continue

        rc, out = run(["graphify", "global", "add",
                       str(repo / "graphify-out" / "graph.json"), "--as", tag])
        if rc != 0:
            print(f"  🔴 {tag}: global add failed rc={rc}")
            failures.append(tag)
            continue

        # 🔴 `graphify extract` does NOT stamp built_at_commit — only `graphify update`
        # does (verified: w0m-web, built by update, has it; every extract-built graph
        # lacks it). So the staleness signal AC3 relies on is absent in 6 of 7 repos
        # until a post-commit rebuild has fired once. Record the repo HEAD at merge
        # time as a labelled fallback so staleness is measurable NOW, and say which
        # basis was used rather than silently mixing the two.
        commit = built_at(repo)
        rc_h, head_out = run(["git", "-C", str(repo), "rev-parse", "HEAD"])
        # Separate name because the type genuinely differs: `run` always yields a str, but a
        # failed rev-parse means there is NO head to record. Re-binding `head` to `str | None`
        # hid that the manifest can carry a null basis (T188).
        head: str | None = head_out.strip() if rc_h == 0 else None
        manifest[tag] = {
            "built_at_commit": commit,
            "head_at_merge": head,
            "basis": "built_at_commit" if commit else "head_at_merge",
            "path": rel,
        }
        shown = commit or head
        print(f"  ✅ {tag}: merged at {(shown or '?')[:7]}"
              f"{'' if commit else '  (basis: repo HEAD — graph carries no built_at_commit)'}")

    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"  manifest: {MANIFEST}")

    rc, out = run(["graphify", "global", "list"])
    print(out.rstrip())

    # T187 AC2 — a skip is reported in the summary, never folded into a silent green.
    # T96 AC3's lesson: an aggregate that drops its skipped members manufactures the
    # false confidence it exists to prevent.
    if unsettled:
        print(f"\n[SKIP] {len(unsettled)} repo(s) NOT MERGED — rebuild still in flight: "
              f"{', '.join(unsettled)}")
        print("   Their manifest entries are unchanged, so the union reports the last "
              "commit it actually merged. Re-run once the rebuild settles.")

    if failures:
        print(f"\n🔴 failed: {', '.join(failures)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
