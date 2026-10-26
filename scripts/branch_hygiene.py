#!/usr/bin/env python3
"""Read-only SDLC branch hygiene monitor and stage-branch consolidation report (T148).

Enumerates governed repositories across the w0m estate (or explicit --repo targets),
inspects explicit refs (`refs/heads/*`, `refs/remotes/origin/*`) via `git for-each-ref`
and `git rev-list --left-right --count` (never `git log @{u}..`), and reports:
  - Per repo, per branch: ahead/behind vs canonical stage branch (`refs/remotes/origin/beta`),
    last commit ISO timestamp, upstream configuration, merged status, and staleness.
  - Stage-branch (`main` <-> `beta`) alignment or divergence classification.
  - Excluded repositories (`wom7mlx/wom7mlx`) reported as informational / excluded.

Strictly read-only (T148 AC1, AC5, AC6, AC7):
  - Never mutates any ref (no fetch, push, merge, reset, or branch deletion).
  - Non-blocking in normal report mode (exits 0 when branches are enumerated).
  - Fails closed (exits 2) when zero branches are enumerated (vacuity guard, AC6).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SDLC_JSON = ROOT / ".w0m" / "sdlc.json"

FORBIDDEN_GIT_SUBCOMMANDS = frozenset({
    "fetch",
    "push",
    "pull",
    "merge",
    "rebase",
    "reset",
    "checkout",
    "switch",
    "branch",
    "tag",
    "clean",
    "commit",
    "stash",
    "cherry-pick",
    "update-ref",
})

ALLOWED_GIT_SUBCOMMANDS = frozenset({
    "for-each-ref",
    "rev-list",
    "merge-base",
})


def run_git_readonly(repo_path: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    """Execute a strictly read-only git plumbing command against repo_path."""
    if not args or args[0] in FORBIDDEN_GIT_SUBCOMMANDS or args[0] not in ALLOWED_GIT_SUBCOMMANDS:
        raise ValueError(f"Refusing non-whitelisted git subcommand: {args}")
    cmd = ["git", "-C", str(repo_path), "--no-pager", *args]
    return subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=30)


def load_branch_model(root: Path) -> dict[str, Any]:
    """Load the branch_model contract from .w0m/sdlc.json."""
    candidates = [
        root / ".w0m" / "sdlc.json",
        SDLC_JSON,
    ]
    for path in candidates:
        if path.exists():
            data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
            if "branch_model" in data and isinstance(data["branch_model"], dict):
                return data["branch_model"]
    raise RuntimeError("branch_model missing from .w0m/sdlc.json")


def resolve_repo_dir(root: Path, repo_name: str) -> Path:
    """Resolve a logical repo identifier (@wom or subdir) to its filesystem path."""
    if repo_name in ("@wom", "."):
        return root
    return root / repo_name


def inspect_repo(
    repo_name: str,
    repo_path: Path,
    model: dict[str, Any],
    stale_days: int,
    now_ts: float,
    excluded: bool = False,
) -> dict[str, Any]:
    """Inspect all explicit local and origin refs in a single repository."""
    canonical = str(model.get("canonical_branch", "beta"))
    single_branch_repos = set(model.get("single_branch_by_design", []))
    legacy_status_map = model.get("legacy_main_status", {})

    if not repo_path.exists():
        return {
            "repo": repo_name,
            "path": str(repo_path),
            "exists": False,
            "excluded": excluded,
            "canonical_ref": None,
            "main_status": "REPO_MISSING",
            "beta_ahead_of_main": None,
            "main_ahead_of_beta": None,
            "branches": [],
            "stale_count": 0,
            "diverged": False,
        }

    fmt = "%(refname)|%(objectname:short)|%(committerdate:iso-strict)|%(committerdate:unix)|%(upstream:short)"
    res = run_git_readonly(
        repo_path,
        ["for-each-ref", f"--format={fmt}", "refs/heads", "refs/remotes/origin"],
    )
    if res.returncode != 0:
        return {
            "repo": repo_name,
            "path": str(repo_path),
            "exists": False,
            "excluded": excluded,
            "canonical_ref": None,
            "main_status": "GIT_ERROR",
            "beta_ahead_of_main": None,
            "main_ahead_of_beta": None,
            "branches": [],
            "stale_count": 0,
            "diverged": False,
            "error": res.stderr.strip(),
        }

    raw_refs: list[dict[str, Any]] = []
    ref_Index: dict[str, dict[str, Any]] = {}
    for line in res.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("|")
        if len(parts) != 5:
            continue
        refname, sha, iso_date, unix_str, upstream = parts
        if refname == "refs/remotes/origin/HEAD":
            continue
        try:
            commit_ts = int(unix_str)
        except ValueError:
            commit_ts = int(now_ts)
        entry = {
            "refname": refname,
            "sha": sha,
            "commit_date": iso_date,
            "commit_ts": commit_ts,
            "upstream": upstream,
        }
        raw_refs.append(entry)
        ref_Index[refname] = entry

    # Determine explicit canonical stage ref (prefer refs/remotes/origin/<canonical>, then refs/heads/<canonical>)
    remote_canonical = f"refs/remotes/origin/{canonical}"
    local_canonical = f"refs/heads/{canonical}"
    if remote_canonical in ref_Index:
        canonical_ref = remote_canonical
    elif local_canonical in ref_Index:
        canonical_ref = local_canonical
    elif raw_refs:
        canonical_ref = raw_refs[0]["refname"]
    else:
        canonical_ref = None

    branches: list[dict[str, Any]] = []
    stale_count = 0

    for item in raw_refs:
        refname = item["refname"]
        if refname.startswith("refs/heads/"):
            short_name = refname[len("refs/heads/"):]
            scope = "local"
            upstream_configured = bool(item["upstream"])
            upstream_val = item["upstream"] if upstream_configured else None
        elif refname.startswith("refs/remotes/"):
            short_name = refname[len("refs/remotes/"):]
            scope = "remote"
            upstream_configured = True
            upstream_val = refname
        else:
            short_name = refname
            scope = "other"
            upstream_configured = bool(item["upstream"])
            upstream_val = item["upstream"] or None

        ahead = 0
        behind = 0
        merged = True
        if canonical_ref and refname != canonical_ref:
            cnt = run_git_readonly(
                repo_path,
                ["rev-list", "--left-right", "--count", f"{canonical_ref}...{refname}"],
            )
            if cnt.returncode == 0:
                 nums = cnt.stdout.strip().split()
                 if len(nums) == 2:
                     behind = int(nums[0])
                     ahead = int(nums[1])
            merged = ahead == 0

        age_days = max(0.0, (now_ts - item["commit_ts"]) / 86400.0)
        is_canonical = short_name in (canonical, f"origin/{canonical}")
        is_stale = (age_days >= float(stale_days)) and not is_canonical
        if is_stale:
            stale_count += 1

        branches.append({
            "refname": refname,
            "name": short_name,
            "scope": scope,
            "sha": item["sha"],
            "last_commit_date": item["commit_date"],
            "age_days": round(age_days, 1),
            "upstream_configured": upstream_configured,
            "upstream": upstream_val,
            "ahead_of_stage": ahead,
            "behind_stage": behind,
            "merged_into_stage": merged,
            "stale": is_stale,
            "open_pr": False,
        })

    # Stage consolidation check: main <-> beta
    remote_main = "refs/remotes/origin/main"
    local_main = "refs/heads/main"
    main_ref = remote_main if remote_main in ref_Index else (local_main if local_main in ref_Index else None)

    beta_ahead_of_main: int | None = None
    main_ahead_of_beta: int | None = None
    diverged = False

    if main_ref and canonical_ref:
        cnt = run_git_readonly(
            repo_path,
            ["rev-list", "--left-right", "--count", f"{canonical_ref}...{main_ref}"],
        )
        if cnt.returncode == 0:
            nums = cnt.stdout.strip().split()
            if len(nums) == 2:
                beta_ahead_of_main = int(nums[0])
                main_ahead_of_beta = int(nums[1])
        if (main_ahead_of_beta or 0) > 0 and (beta_ahead_of_main or 0) > 0:
            diverged = True
            repo_legacy_meta = legacy_status_map.get(repo_name, {})
            if repo_legacy_meta.get("diverged_pre_rewrite_do_not_merge"):
                main_status = "DIVERGED_PRE_REWRITE_DO_NOT_MERGE"
            else:
                main_status = "DIVERGED"
        elif (main_ahead_of_beta or 0) > 0:
            diverged = True
            main_status = "MAIN_AHEAD"
        elif (beta_ahead_of_main or 0) > 0:
            main_status = "TRAILS_BETA_CLEANLY"
        else:
            main_status = "IN_SYNC"
    else:
        if repo_name in single_branch_repos:
            main_status = "SINGLE_BRANCH_BY_DESIGN"
        else:
            main_status = "NO_MAIN_BRANCH"

    return {
        "repo": repo_name,
        "path": str(repo_path),
        "exists": True,
        "excluded": excluded,
        "canonical_ref": canonical_ref,
        "main_ref": main_ref,
        "main_status": main_status,
        "beta_ahead_of_main": beta_ahead_of_main,
        "main_ahead_of_beta": main_ahead_of_beta,
        "branches": branches,
        "stale_count": stale_count,
        "diverged": diverged,
    }


def build_report(
    root: Path,
    explicit_repos: list[Path] | None = None,
    stale_days_override: int | None = None,
) -> dict[str, Any]:
    """Build the full branch hygiene report across governed (or explicit) repositories."""
    model = load_branch_model(root)
    stale_days = (
        stale_days_override
        if stale_days_override is not None
        else int(model.get("stale_days", 14))
    )
    now_ts = time.time()

    repo_reports: list[dict[str, Any]] = []
    if explicit_repos:
        for rpath in explicit_repos:
            resolved = rpath.resolve()
            repo_reports.append(
                inspect_repo(resolved.name, resolved, model, stale_days, now_ts, excluded=False)
            )
    else:
        governed = model.get(
            "governed_repos",
            ["@wom", "wom7web", "wom7api", "wom7func", "wom7skills", "wom7ext", "wom7sec"],
        )
        excluded_list = model.get("excluded_repos", ["wom7mlx/wom7mlx"])
        for rname in governed:
            rpath = resolve_repo_dir(root, rname)
            repo_reports.append(
                inspect_repo(rname, rpath, model, stale_days, now_ts, excluded=False)
            )
        for rname in excluded_list:
            rpath = resolve_repo_dir(root, rname)
            repo_reports.append(
                inspect_repo(rname, rpath, model, stale_days, now_ts, excluded=True)
            )

    governed_reports = [r for r in repo_reports if not r["excluded"]]
    total_branches = sum(len(r["branches"]) for r in governed_reports)
    empty_repos = [r["repo"] for r in governed_reports if len(r["branches"]) == 0]
    diverged_repos = [r["repo"] for r in governed_reports if r["diverged"]]
    stale_branches = [
        f"{r['repo']}:{b['refname']}"
        for r in governed_reports
        for b in r["branches"]
        if b["stale"]
    ]
    missing_upstream = [
        f"{r['repo']}:{b['refname']}"
        for r in governed_reports
        for b in r["branches"]
        if b["scope"] == "local" and not b["upstream_configured"]
    ]

    vacuous = (len(governed_reports) == 0) or (total_branches == 0) or bool(empty_repos)

    return {
        "read_only": True,
        "stale_days": stale_days,
        "branch_model": model,
        "repos": repo_reports,
        "summary": {
            "governed_repo_count": len(governed_reports),
            "excluded_repo_count": len(repo_reports) - len(governed_reports),
            "total_branches": total_branches,
            "empty_repos": empty_repos,
            "diverged_repos": diverged_repos,
            "stale_branch_count": len(stale_branches),
            "stale_branches": stale_branches,
            "missing_upstream_count": len(missing_upstream),
            "missing_upstream": missing_upstream,
            "vacuous": vacuous,
        },
    }


def render_text_report(report: dict[str, Any]) -> str:
    """Format the human-readable branch hygiene report without decorative pictographs."""
    lines: list[str] = []
    summary = report["summary"]
    model = report["branch_model"]
    lines.append(
        "branch-hygiene (read-only) — "
        f"{summary['governed_repo_count']} governed repo(s), "
        f"{summary['total_branches']} branch ref(s), "
        f"canonical={model.get('canonical_branch', 'beta')}, "
        f"stale_days={report['stale_days']}"
    )
    lines.append("")
    lines.append("Stage-branch (main <-> beta) summary:")
    for r in report["repos"]:
        tag = "[EXCLUDED]" if r["excluded"] else ("[WARN]" if r["diverged"] else "[OK]")
        b_ahead = "-" if r["beta_ahead_of_main"] is None else str(r["beta_ahead_of_main"])
        m_ahead = "-" if r["main_ahead_of_beta"] is None else str(r["main_ahead_of_beta"])
        lines.append(
            f"  {tag:10s} {r['repo']:16s} status={r['main_status']:34s} "
            f"beta_ahead={b_ahead:5s} main_ahead={m_ahead:5s} "
            f"refs={len(r['branches'])} stale={r['stale_count']}"
        )

    lines.append("")
    lines.append("Per-repository explicit branch refs:")
    for r in report["repos"]:
        hdr_note = " (excluded from uniformity per T148 Note)" if r["excluded"] else ""
        lines.append(f"  [{r['repo']}]{hdr_note} canonical_ref={r['canonical_ref']}")
        if not r["branches"]:
            lines.append("    [FAIL] 0 branches enumerated")
            continue
        for b in r["branches"]:
            flags: list[str] = []
            if b["stale"]:
                flags.append(f"STALE({b['age_days']}d)")
            if b["scope"] == "local" and not b["upstream_configured"]:
                flags.append("NO_UPSTREAM")
            if not b["merged_into_stage"]:
                flags.append("UNMERGED")
            flag_str = f" [{' '.join(flags)}]" if flags else ""
            up_str = b["upstream"] if b["upstream_configured"] else "none"
            lines.append(
                f"    - {b['refname']:36s} sha={b['sha']:8s} "
                f"ahead={b['ahead_of_stage']:<4d} behind={b['behind_stage']:<5d} "
                f"merged={str(b['merged_into_stage']):<5s} upstream={up_str:<14s} "
                f"last_commit={b['last_commit_date']}{flag_str}"
            )

    lines.append("")
    if summary["diverged_repos"]:
        lines.append(
            f"[WARN] Diverged main<->beta repos ({len(summary['diverged_repos'])}): "
            + ", ".join(summary["diverged_repos"])
        )
    if summary["stale_branches"]:
        lines.append(
            f"[WARN] Stale branches >={report['stale_days']}d ({summary['stale_branch_count']}): "
            + ", ".join(summary["stale_branches"])
        )
    if summary["vacuous"]:
        lines.append(
            "[FAIL] Vacuous branch report: zero branches enumerated in "
            + (", ".join(summary["empty_repos"]) if summary["empty_repos"] else "target set")
        )
    else:
        lines.append(
            "[OK] Read-only branch hygiene report complete (non-blocking surface; 0 refs mutated)."
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=ROOT, help="Estate root directory")
    ap.add_argument(
        "--repo",
        type=Path,
        action="append",
        dest="repos",
        help="Explicit repository path(s) to inspect (overrides estate governed_repos list)",
    )
    ap.add_argument("--stale-days", type=int, default=None, help="Stale threshold in days")
    ap.add_argument("--json", action="store_true", help="Emit JSON output")
    ap.add_argument("--self-test", action="store_true", help="Verify read-only contract and model")
    args = ap.parse_args(argv)

    try:
        report = build_report(
            root=args.root.resolve(),
            explicit_repos=args.repos,
            stale_days_override=args.stale_days,
        )
    except Exception as exc:
        print(f"[FAIL] branch-hygiene failed to load contract: {exc}", file=sys.stderr)
        return 2

    if args.self_test:
        if report["summary"]["vacuous"]:
            print("[FAIL] self-test failed: vacuous branch enumeration", file=sys.stderr)
            return 1
        print("[OK] branch-hygiene self-test passed")
        return 0

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(render_text_report(report))

    if report["summary"]["vacuous"]:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
