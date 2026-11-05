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
import os
import shutil
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

_GIT_OVERRIDE_VARS = frozenset({
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_PREFIX",
})


def _clean_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Strip Git hook repo-override vars so `git -C <repo>` and `graphify` inspect `<repo>`, never a caller hook's GIT_DIR."""
    env = {k: v for k, v in os.environ.items() if k not in _GIT_OVERRIDE_VARS}
    if extra:
        env.update(extra)
    return env


def run(cmd: list[str], cwd: Path | None = None) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=str(cwd) if cwd else None,
                       env=_clean_env(), capture_output=True, text=True)
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
        raw_obj: object = json.loads(g.read_text())
        if isinstance(raw_obj, dict):
            val = raw_obj.get("built_at_commit")
            return str(val) if isinstance(val, str) and val else None
        return None
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def stale_commit_distance(repo: Path, built_commit: str | None) -> int | None:
    """Commits between `built_commit` and `HEAD` (None when `built_commit` is absent or unreachable)."""
    if not built_commit:
        return None
    rc, out = run(["git", "-C", str(repo), "rev-list", "--count", f"{built_commit}..HEAD"])
    txt = out.strip()
    return int(txt) if rc == 0 and txt.isdigit() else None


def resolve_graphify_python(repo: Path) -> str | None:
    """Resolve the Python interpreter hosting `graphify` for incremental `_rebuild_code`."""
    marker = repo / "graphify-out" / ".graphify_python"
    if marker.is_file():
        try:
            cand = marker.read_text(encoding="utf-8").strip()
            if cand and Path(cand).is_file():
                return cand
        except OSError:
            pass
    gbin = shutil.which("graphify")
    if gbin:
        try:
            first_line = Path(gbin).read_bytes()[:256].split(b"\n", 1)[0].decode("utf-8", errors="ignore")
            if first_line.startswith("#!"):
                parts = first_line[2:].strip().split()
                if parts:
                    interp = parts[-1] if parts[0].endswith("/env") and len(parts) > 1 else parts[0]
                    resolved = shutil.which(interp) if "/" not in interp else interp
                    if resolved and Path(resolved).is_file():
                        return resolved
        except OSError:
            pass
    return None


def stamp_built_at_commit(repo: Path, commit_sha: str) -> None:
    """Stamp `built_at_commit` on `graph.json` when an incremental check found unchanged AST topology."""
    g = repo / "graphify-out" / "graph.json"
    if not g.is_file() or not commit_sha:
        return
    try:
        raw_obj: object = json.loads(g.read_text(encoding="utf-8"))
        if not isinstance(raw_obj, dict) or raw_obj.get("built_at_commit") == commit_sha:
            return
        raw_obj["built_at_commit"] = commit_sha
        tmp = g.parent / ".graph.stamp.tmp.json"
        tmp.write_text(json.dumps(raw_obj, ensure_ascii=False), encoding="utf-8")
        tmp.replace(g)
    except (OSError, json.JSONDecodeError, ValueError):
        return


_INCREMENTAL_REBUILD_SNIPPET = (
    "import os, sys\n"
    "from pathlib import Path\n"
    "from graphify.watch import _rebuild_code, _apply_resource_limits\n"
    "_apply_resource_limits()\n"
    "paths = [Path(p) for p in os.environ.get('GRAPHIFY_CHANGED', '').splitlines() if p.strip()]\n"
    "ok = _rebuild_code(Path('.'), changed_paths=paths, force=True, block_on_lock=True)\n"
    "sys.exit(0 if ok else 1)\n"
)


def refresh_stale_repo_graph(repo: Path, prior_built: str | None, *, full_rebuild: bool) -> tuple[int, str]:
    """Refresh `repo/graphify-out/graph.json` incrementally when `prior_built` is reachable, else full."""
    rc_h, head_out = run(["git", "-C", str(repo), "rev-parse", "HEAD"])
    head_sha = head_out.strip() if rc_h == 0 else ""

    if not full_rebuild and prior_built:
        rc_d, diff_out = run(["git", "-C", str(repo), "diff", "--name-only", prior_built, "HEAD"])
        if rc_d == 0:
            changed = [
                ln.strip()
                for ln in diff_out.splitlines()
                if ln.strip() and not ln.strip().startswith("graphify-out/")
            ]
            if not changed:
                if head_sha:
                    stamp_built_at_commit(repo, head_sha)
                return 0, "no non-graph changes"
            gpy = resolve_graphify_python(repo)
            if gpy:
                env = _clean_env({"PYTHONHASHSEED": "0", "GRAPHIFY_CHANGED": "\n".join(changed)})
                p = subprocess.run(
                    [gpy, "-c", _INCREMENTAL_REBUILD_SNIPPET],
                    cwd=str(repo),
                    env=env,
                    capture_output=True,
                    text=True,
                )
                out = p.stdout + p.stderr
                if p.returncode == 0 and head_sha and built_at(repo) != head_sha:
                    stamp_built_at_commit(repo, head_sha)
                return p.returncode, out

    rc, out = run(["graphify", "update", "--force", "."], cwd=repo)
    if rc == 0 and head_sha and built_at(repo) != head_sha:
        stamp_built_at_commit(repo, head_sha)
    return rc, out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=None,
                    help="Explicit estate root directory (defaults to parent of scripts/)")
    ap.add_argument("--only", help="substring filter on the repo tag")
    ap.add_argument("--rebuild", action="store_true",
                    help="re-extract each repo before merging (slow: minutes per repo)")
    ap.add_argument("--auto-rebuild-stale", action="store_true",
                    help="T652: run `graphify update .` only on repos whose built_at_commit lags HEAD by > --stale-limit")
    ap.add_argument("--stale-limit", type=int, default=10,
                    help="Commit lag threshold for --auto-rebuild-stale (default 10, matching graph_fresh.py)")
    ap.add_argument("--settle", type=float, default=0.0, metavar="SECONDS",
                    help="T187: wait up to SECONDS for each repo's graph.json to stop "
                         "changing before merging it, and SKIP any repo still being "
                         "written. Default 0 (no wait) for manual runs; the pre-push "
                         "hook passes a budget because post-commit rebuilds in background.")
    args = ap.parse_args()

    estate_root = args.root.resolve() if args.root is not None else ESTATE
    if not (estate_root / "w0m-web").is_dir():
        print(f"error: estate root not found at {estate_root}", file=sys.stderr)
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

    manifest: dict[str, object] = {}
    if MANIFEST.exists():
        try:
            loaded_manifest: object = json.loads(MANIFEST.read_text())
            if isinstance(loaded_manifest, dict):
                manifest = dict(loaded_manifest)
        except (OSError, json.JSONDecodeError):
            manifest = {}

    failures: list[str] = []
    unsettled: list[str] = []
    for tag, rel in targets.items():
        repo = estate_root / rel
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
        prior_built = built_at(repo) if graph_file.exists() else None
        lag = stale_commit_distance(repo, prior_built)
        needs_stale_rebuild = (
            bool(args.auto_rebuild_stale)
            and graph_file.exists()
            and lag is not None
            and lag > max(0, int(args.stale_limit))
        )
        if (args.rebuild or needs_stale_rebuild) and graph_file.exists():
            mode_lbl = (
                f" (+{lag} commits > limit {args.stale_limit}, incremental diff)"
                if needs_stale_rebuild and not args.rebuild
                else " (full corpus)"
            )
            print(f"  ⏳ {tag}: updating code graph at HEAD{mode_lbl} (local AST, no LLM, stamps built_at_commit)…")
            rc, out = refresh_stale_repo_graph(repo, prior_built, full_rebuild=bool(args.rebuild))
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
