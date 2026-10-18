#!/usr/bin/env python3
"""w0m-prs — Canonical GitHub PR discovery, health audit, watch poller & reporting tool.

Tracked by T345. Adheres to w0m CLI standard: offline-testable, deterministic JSON/table output,
safe headless Mermaid generation.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

CANONICAL_FORK_ORG = "webomage"
CANONICAL_CONTRIBUTOR = "casualuser"

PRESET_REPOS = {
    "wom7pr": [
        "jundot/omlx",
        "Blaizzy/mlx-vlm",
        "stablyai/orca",
        "openai/tart-guest-agent",
        "cirruslabs/tart",
        "bulwarkid/virtual-fido",
        "headroomlabs-ai/headroom",
        "oraios/serena",
        "google-research/harness2",
    ],
    # Backwards-compatibility alias
    "wom7open": [
        "jundot/omlx",
        "Blaizzy/mlx-vlm",
        "stablyai/orca",
        "openai/tart-guest-agent",
        "cirruslabs/tart",
        "bulwarkid/virtual-fido",
        "headroomlabs-ai/headroom",
        "oraios/serena",
        "google-research/harness2",
    ],
}


def run_cmd(
    cmd: List[str],
    check: bool = True,
    cwd: Optional[Path] = None,
    timeout: Optional[float] = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=check,
        cwd=cwd,
        timeout=timeout,
    )


def search_prs(
    author: Optional[str] = None,
    repo: Optional[str] = None,
    preset: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    prs: List[Dict[str, Any]] = []

    if preset and preset in PRESET_REPOS:
        for r in PRESET_REPOS[preset]:
            cmd = [
                "gh", "pr", "list",
                "-R", r,
                "--limit", str(limit),
                "--json", "number,title,state,url,createdAt,closedAt,isDraft,author",
            ]
            if author:
                cmd.extend(["--author", author])
            res = run_cmd(cmd, check=False)
            if res.returncode == 0 and res.stdout.strip():
                try:
                    items = json.loads(res.stdout)
                    for it in items:
                        it["repository"] = {"nameWithOwner": r}
                    prs.extend(items)
                except json.JSONDecodeError:
                    pass
        return prs

    cmd = [
        "gh", "search", "prs",
        "--limit", str(limit),
        "--json", "repository,number,title,state,url,createdAt,closedAt,isDraft",
    ]
    if author:
        cmd.extend(["--author", author])
    if repo:
        cmd.extend(["--repo", repo])

    res = run_cmd(cmd, check=False)
    if res.returncode == 0 and res.stdout.strip():
        try:
            return json.loads(res.stdout)
        except json.JSONDecodeError:
            return []
    return []


BOT_LOGINS = {
    "claassistant",
    "github-actions",
    "coderabbitai",
    "greptile-apps",
    "pullfrog",
    "chatgpt-codex-connector",
    "copilot",
    "codecov",
    "dependabot",
    "stale",
}


def is_bot_login(login: str) -> bool:
    if not login:
        return False
    low = login.lower()
    if low in BOT_LOGINS or low.endswith("[bot]") or low.endswith("-bot") or low.endswith("_bot"):
        return True
    return False


def parse_feedback(
    comments: List[Dict[str, Any]],
    reviews: List[Dict[str, Any]],
    author: Optional[str] = None,
) -> Dict[str, Any]:
    human_questions = 0
    human_suggestions = 0
    human_interactions = 0
    human_reviewers = set()

    bot_questions = 0
    bot_suggestions = 0
    bot_interactions = 0
    bot_reviewers = set()

    for c in comments or []:
        c_auth = (c.get("author") or {}).get("login", "")
        if not c_auth or (author and c_auth.lower() == author.lower()):
            continue
        body = c.get("body") or ""
        has_q = "?" in body
        has_s = "```suggestion" in body or "suggest" in body.lower() or "recommend" in body.lower()
        if is_bot_login(c_auth):
            bot_interactions += 1
            if has_q:
                bot_questions += 1
            if has_s:
                bot_suggestions += 1
            bot_reviewers.add(c_auth)
        else:
            human_interactions += 1
            if has_q:
                human_questions += 1
            if has_s:
                human_suggestions += 1
            human_reviewers.add(c_auth)

    for r in reviews or []:
        r_auth = (r.get("author") or {}).get("login", "")
        if not r_auth or (author and r_auth.lower() == author.lower()):
            continue
        body = r.get("body") or ""
        state = (r.get("state") or "").upper()
        has_q = "?" in body
        has_s = "```suggestion" in body or "suggest" in body.lower() or "recommend" in body.lower() or state == "CHANGES_REQUESTED"
        if is_bot_login(r_auth):
            bot_interactions += 1
            if has_q:
                bot_questions += 1
            if has_s:
                bot_suggestions += 1
            bot_reviewers.add(r_auth)
        else:
            human_interactions += 1
            if has_q:
                human_questions += 1
            if has_s:
                human_suggestions += 1
            human_reviewers.add(r_auth)

    if human_interactions > 0:
        parts = []
        if human_questions > 0:
            parts.append(f"❓ {human_questions}")
        if human_suggestions > 0:
            parts.append(f"💡 {human_suggestions}")
        parts.append(f"💬 {human_interactions}")
        revs = ", ".join(sorted(human_reviewers))
        summary = " ".join(parts) + f" ({revs})"
    elif bot_interactions > 0:
        parts = []
        if bot_questions > 0:
            parts.append(f"❓ {bot_questions}")
        if bot_suggestions > 0:
            parts.append(f"💡 {bot_suggestions}")
        parts.append(f"🤖 💬 {bot_interactions}")
        revs = ", ".join(sorted(bot_reviewers))
        summary = " ".join(parts) + f" ({revs})"
    else:
        summary = "-"

    return {
        "summary": summary,
        "human_questions": human_questions,
        "human_suggestions": human_suggestions,
        "human_interactions": human_interactions,
        "human_reviewers": sorted(human_reviewers),
        "bot_questions": bot_questions,
        "bot_suggestions": bot_suggestions,
        "bot_interactions": bot_interactions,
        "bot_reviewers": sorted(bot_reviewers),
    }


def audit_pr(repo: str, pr_number: int) -> Dict[str, Any]:
    cmd = [
        "gh", "pr", "view", str(pr_number),
        "-R", repo,
        "--json", "number,title,state,url,author,isDraft,mergeable,reviewDecision,comments,reviews,statusCheckRollup",
    ]
    res = run_cmd(cmd, check=False)
    if res.returncode != 0:
        return {"error": res.stderr.strip() or "Failed to view PR"}

    data = json.loads(res.stdout)
    rollup = data.get("statusCheckRollup", []) or []
    ci_status = "PASS"
    for check in rollup:
        conclusion = check.get("conclusion") or check.get("status")
        if conclusion in ("FAILURE", "TIMED_OUT", "ACTION_REQUIRED", "CANCELLED"):
            ci_status = "FAIL"
            break
        elif conclusion in ("IN_PROGRESS", "QUEUED", "PENDING"):
            ci_status = "PENDING"

    author = (data.get("author") or {}).get("login")
    feedback_data = parse_feedback(data.get("comments", []), data.get("reviews", []), author)

    return {
        "repo": repo,
        "number": data.get("number"),
        "title": data.get("title"),
        "state": data.get("state"),
        "mergeable": data.get("mergeable", "UNKNOWN"),
        "reviewDecision": data.get("reviewDecision") or "NONE",
        "commentsCount": len(data.get("comments", [])),
        "reviewsCount": len(data.get("reviews", [])),
        "ciStatus": ci_status,
        "feedback": feedback_data["summary"],
        "feedbackDetails": feedback_data,
        "url": data.get("url"),
    }


def cmd_search(args: argparse.Namespace) -> None:
    results = search_prs(author=args.author, repo=args.repo, preset=args.preset, limit=args.limit)
    if args.json:
        print(json.dumps(results, indent=2))
        return

    print(f"Discovered {len(results)} PR(s):")
    for p in results:
        repo_name = p.get("repository", {}).get("nameWithOwner", "unknown")
        num = p.get("number")
        state = p.get("state", "").upper()
        title = p.get("title", "")
        print(f"[{state}] {repo_name}#{num} - {title}")


def cmd_audit(args: argparse.Namespace) -> None:
    targets: List[tuple[str, int]] = []
    if args.repo and args.pr:
        targets.append((args.repo, args.pr))
    elif args.preset in ("wom7pr", "wom7open"):
        open_prs = search_prs(preset=args.preset, limit=20)
        for p in open_prs:
            repo_name = p.get("repository", {}).get("nameWithOwner")
            num = p.get("number")
            if repo_name and num:
                targets.append((repo_name, num))
    else:
        print("Error: Specify --repo and --pr, or --preset wom7pr", file=sys.stderr)
        sys.exit(1)

    audits = []
    for r, num in targets:
        info = audit_pr(r, num)
        audits.append(info)
        if not args.json:
            print(f"=== {r}#{num} ===")
            print(f"Title: {info.get('title')}")
            print(f"State: {info.get('state')} | Mergeable: {info.get('mergeable')} | Review: {info.get('reviewDecision')}")
            print(f"CI: {info.get('ciStatus')} | Comments: {info.get('commentsCount')} | Reviews: {info.get('reviewsCount')} | Feedback: {info.get('feedback')}")
            print(f"URL: {info.get('url')}\n")

    if args.json:
        print(json.dumps(audits, indent=2))


def cmd_watch(args: argparse.Namespace) -> None:
    interval_sec = args.interval * 60
    end_time = time.time() + (args.duration * 60)
    print(f"Watching PRs every {args.interval}m for {args.duration}m...")

    last_states: Dict[str, Any] = {}

    while time.time() < end_time:
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        print(f"[{now_str}] Polling active PRs...")

        targets = []
        if args.repo and args.pr:
            targets.append((args.repo, args.pr))
        else:
            open_prs = search_prs(preset=args.preset or "wom7pr", limit=10)
            for p in open_prs:
                repo_name = p.get("repository", {}).get("nameWithOwner")
                num = p.get("number")
                if repo_name and num:
                    targets.append((repo_name, num))

        for r, num in targets:
            key = f"{r}#{num}"
            info = audit_pr(r, num)
            prev = last_states.get(key)

            if prev is None:
                print(f"  {key}: {info.get('state')} | {info.get('mergeable')} | review: {info.get('reviewDecision')} | feedback: {info.get('feedback')}")
            else:
                deltas = []
                for field in ("state", "mergeable", "reviewDecision", "ciStatus", "commentsCount", "reviewsCount", "feedback"):
                    if prev.get(field) != info.get(field):
                        deltas.append(f"{field}: {prev.get(field)} -> {info.get(field)}")
                if deltas:
                    print(f"  DELTA on {key}: {', '.join(deltas)}")
                    if getattr(args, "notify", False):
                        print("\a[NOTIFY] Delta detected!", flush=True)
                else:
                    print(f"  {key}: unchanged ({info.get('mergeable')})")

            last_states[key] = info

        if time.time() + interval_sec >= end_time:
            break
        time.sleep(interval_sec)

    print("Watch session complete.")


def cmd_report(args: argparse.Namespace) -> None:
    author = args.author or "casualuser"
    prs = search_prs(author=author, limit=100)
    prs.sort(key=lambda x: x.get("createdAt", ""), reverse=True)

    total = len(prs)
    open_prs = [p for p in prs if p.get("state") == "open"]
    merged_prs = [p for p in prs if p.get("state") == "merged"]
    closed_prs = [p for p in prs if p.get("state") == "closed"]

    report_lines = [
        f"# Public PR Report: `@{author}`",
        f"\n**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"\nTotal PRs: {total} | Open: {len(open_prs)} | Merged: {len(merged_prs)} | Closed: {len(closed_prs)}",
        "\n## PR Lifecycle Topology",
        "```mermaid",
        "flowchart TD",
        '    subgraph Ingestion["Ingestion"]',
        f'        PRs["Author PRs ({total})"]',
        "    end",
        '    subgraph Review["Review & CI"]',
        f'        Open["Active Open ({len(open_prs)})"]',
        "    end",
        '    subgraph Terminal["Terminal State"]',
        f'        Merged["Merged ({len(merged_prs)})"]',
        f'        Closed["Closed ({len(closed_prs)})"]',
        "    end",
        "    PRs --> Open",
        "    Open --> Merged",
        "    Open --> Closed",
        "```",
        "\n## PR Status Distribution",
        "```mermaid",
        "xychart-beta",
        '    title "Pull Request Lifecycle State"',
        '    x-axis ["Open", "Merged", "Closed"]',
        f'    y-axis "Count" 0 --> {max(total, 10)}',
        f'    bar [{len(open_prs)}, {len(merged_prs)}, {len(closed_prs)}]',
        "```",
        "\n## PR Milestone Timeline",
        "```mermaid",
        "flowchart LR",
        '    P1["Discovery & Ingestion"] --> P2["Audit & Mergeability"]',
        '    P2 --> P3["Review & Verification"]',
        '    P3 --> P4["Landing & Archival"]',
        "```",
        "\n## Master PR Ledger",
        "| Repository | # | Title | State | Created |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]

    for p in prs:
        repo_name = p.get("repository", {}).get("nameWithOwner", "unknown")
        num = p.get("number")
        url = p.get("url", "")
        title = p.get("title", "")
        state = p.get("state", "").upper()
        created = (p.get("createdAt") or "")[:10]
        report_lines.append(f"| `{repo_name}` | [#{num}]({url}) | {title} | **{state}** | {created} |")

    report_content = "\n".join(report_lines)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report_content)
        print(f"Report written to {out_path}")
    else:
        print(report_content)


def cmd_table(args: argparse.Namespace) -> None:
    author = None if getattr(args, "all", False) else (getattr(args, "author", None) or "casualuser")
    preset = getattr(args, "preset", "wom7pr")
    repo = getattr(args, "repo", None)
    limit = getattr(args, "limit", 30)

    prs = search_prs(author=author, repo=repo, preset=preset, limit=limit)
    if not prs:
        target_desc = f"repo {repo}" if repo else f"preset {preset}"
        author_desc = f" by @{author}" if author else ""
        print(f"No active pull requests found for {target_desc}{author_desc}.")
        return

    # Sort by created desc
    prs.sort(key=lambda x: x.get("createdAt", ""), reverse=True)

    rows = []
    for p in prs:
        repo_name = p.get("repository", {}).get("nameWithOwner") or "unknown"
        num = p.get("number")
        if not num:
            continue
        info = audit_pr(repo_name, num)
        if "error" in info:
            rows.append({
                "repo": repo_name,
                "number": num,
                "title": p.get("title", ""),
                "state": p.get("state", "").upper(),
                "mergeable": "UNKNOWN",
                "review": "NONE",
                "feedback": "-",
                "ci": "N/A",
                "url": p.get("url", ""),
            })
        else:
            rows.append({
                "repo": repo_name,
                "number": num,
                "title": info.get("title", ""),
                "state": (info.get("state") or "").upper(),
                "mergeable": info.get("mergeable", "UNKNOWN"),
                "review": info.get("reviewDecision", "NONE"),
                "feedback": info.get("feedback", "-"),
                "ci": info.get("ciStatus", "N/A"),
                "url": info.get("url", ""),
            })

    if getattr(args, "markdown", False):
        print("| Repository | PR | Title | State | Mergeable | Review | Feedback | CI | URL |")
        print("| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |")
        for r in rows:
            print(f"| `{r['repo']}` | [#{r['number']}]({r['url']}) | {r['title']} | **{r['state']}** | `{r['mergeable']}` | `{r['review']}` | {r['feedback']} | `{r['ci']}` | {r['url']} |")
        return

    # Terminal aligned table
    headers = ("Repository", "PR", "Title", "State", "Mergeable", "Review", "Feedback", "CI", "URL")
    table_data = []
    for r in rows:
        title = r["title"]
        if len(title) > 45:
            title = title[:42] + "..."
        feedback = r["feedback"]
        if len(feedback) > 35:
            feedback = feedback[:32] + "..."
        table_data.append((
            r["repo"],
            f"#{r['number']}",
            title,
            r["state"],
            r["mergeable"],
            r["review"],
            feedback,
            r["ci"],
            r["url"],
        ))

    col_widths = [len(h) for h in headers]
    for row in table_data:
        for i, val in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(val)))

    header_str = "  ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    separator_str = "  ".join("-" * col_widths[i] for i in range(len(headers)))
    print(header_str)
    print(separator_str)
    for row in table_data:
        print("  ".join(str(row[i]).ljust(col_widths[i]) for i in range(len(headers))))


def inspect_fork(repo_path: Path, fetch: bool = True) -> Dict[str, Any]:
    """Inspect git synchronization status for a single fork."""
    repo_name = repo_path.name
    res_branch = run_cmd(["git", "branch", "--show-current"], check=False, cwd=repo_path)
    active_branch = res_branch.stdout.strip() if res_branch.returncode == 0 and res_branch.stdout.strip() else "HEAD"

    res_remotes = run_cmd(["git", "remote"], check=False, cwd=repo_path)
    remotes = set(res_remotes.stdout.split()) if res_remotes.returncode == 0 else set()

    if fetch:
        for r in ("upstream", "origin"):
            if r in remotes:
                try:
                    run_cmd(["git", "fetch", r, "--quiet"], check=False, cwd=repo_path, timeout=15)
                except Exception:
                    pass

    # Find upstream tracking target
    upstream_target = None
    target_remote = "upstream" if "upstream" in remotes else ("origin" if "origin" in remotes else None)
    if target_remote:
        for branch_candidate in ("main", "master"):
            check_ref = run_cmd(["git", "rev-parse", "--verify", f"{target_remote}/{branch_candidate}"], check=False, cwd=repo_path)
            if check_ref.returncode == 0:
                upstream_target = f"{target_remote}/{branch_candidate}"
                break

    behind_upstream, ahead_upstream = 0, 0
    if upstream_target:
        res_counts = run_cmd(["git", "rev-list", "--left-right", "--count", f"{upstream_target}...HEAD"], check=False, cwd=repo_path)
        if res_counts.returncode == 0 and res_counts.stdout.strip():
            parts = res_counts.stdout.strip().split()
            if len(parts) == 2:
                try:
                    behind_upstream, ahead_upstream = int(parts[0]), int(parts[1])
                except ValueError:
                    pass

    # Check origin tracking branch
    ahead_origin, behind_origin = 0, 0
    has_origin_branch = False
    if "origin" in remotes and active_branch != "HEAD":
        check_origin = run_cmd(["git", "rev-parse", "--verify", f"origin/{active_branch}"], check=False, cwd=repo_path)
        if check_origin.returncode == 0:
            has_origin_branch = True
            res_origin = run_cmd(["git", "rev-list", "--left-right", "--count", f"origin/{active_branch}...HEAD"], check=False, cwd=repo_path)
            if res_origin.returncode == 0 and res_origin.stdout.strip():
                parts = res_origin.stdout.strip().split()
                if len(parts) == 2:
                    try:
                        behind_origin, ahead_origin = int(parts[0]), int(parts[1])
                    except ValueError:
                        pass

    res_status = run_cmd(["git", "status", "--porcelain"], check=False, cwd=repo_path)
    dirty_count = len([l for l in res_status.stdout.splitlines() if l.strip()]) if res_status.returncode == 0 else 0

    status_notes = []
    if dirty_count > 0:
        status_notes.append(f"dirty ({dirty_count} files)")
    if behind_upstream > 0:
        status_notes.append(f"behind upstream by {behind_upstream}")
    if ahead_upstream > 0:
        status_notes.append(f"ahead upstream +{ahead_upstream}")
    if behind_origin > 0:
        status_notes.append(f"behind origin by {behind_origin}")
    if ahead_origin > 0:
        status_notes.append(f"unpushed +{ahead_origin}")

    if not status_notes:
        overall_status = "up to date"
    else:
        overall_status = ", ".join(status_notes)

    return {
        "repo": repo_name,
        "branch": active_branch,
        "upstream_ref": upstream_target or "-",
        "ahead_upstream": ahead_upstream,
        "behind_upstream": behind_upstream,
        "has_origin_branch": has_origin_branch,
        "ahead_origin": ahead_origin,
        "behind_origin": behind_origin,
        "dirty_count": dirty_count,
        "status": overall_status,
        "is_synced": (behind_upstream == 0 and behind_origin == 0 and dirty_count == 0),
    }


def find_workspace_root(start_path: Path | None = None) -> Path:
    """Find the workspace root containing .tasks and .w0m/sdlc.json."""
    cur = (start_path or Path(__file__)).resolve()
    for parent in [cur] + list(cur.parents):
        if (parent / ".tasks").is_dir() and (parent / ".w0m").is_dir():
            return parent
        if (parent / ".git").exists() and (parent / "wom7web").is_dir():
            return parent
    return Path(__file__).resolve().parents[1]


def resolve_forks_dir(specified: Optional[str] = None) -> Optional[Path]:
    if specified:
        p = Path(specified)
        if p.exists():
            return p
    workspace_root = find_workspace_root()
    for name in ("wom7pr", "wom7open"):
        candidate = workspace_root / name
        if candidate.exists():
            return candidate
    # Fallback to host estate root if running in a release worktree (~/.w0m/releases/...)
    for host_estate in (
        Path.home() / "Projects" / "!self" / "w0m",
        Path.home() / "Projects" / "@self" / "@wom",
        Path.home() / "Projects" / "w0m",
    ):
        for name in ("wom7pr", "wom7open"):
            candidate = host_estate / name
            if candidate.exists():
                return candidate
    return None



def fetch_fork(repo_path: Path) -> Dict[str, Any]:
    """Fetch all remotes for a single fork repository."""
    repo_name = repo_path.name
    res_remotes = run_cmd(["git", "remote"], check=False, cwd=repo_path)
    remotes = res_remotes.stdout.split() if res_remotes.returncode == 0 else []
    fetched = []
    errors = []
    t0 = time.time()
    for r in remotes:
        res = run_cmd(["git", "fetch", r, "--prune", "--quiet"], check=False, cwd=repo_path, timeout=30)
        if res.returncode == 0:
            fetched.append(r)
        else:
            errors.append(f"{r}: {res.stderr.strip()}")
    duration = round(time.time() - t0, 2)
    return {
        "repo": repo_name,
        "fetched": fetched,
        "errors": errors,
        "duration_seconds": duration,
        "success": len(errors) == 0,
    }


def get_fork_info(repo_path: Path) -> Dict[str, Any]:
    """Collect deep inspection metadata for a single fork repository."""
    base = inspect_fork(repo_path, fetch=False)
    repo_name = repo_path.name
    base["path"] = str(repo_path)

    # Remote URLs
    res_remote_v = run_cmd(["git", "remote", "-v"], check=False, cwd=repo_path)
    remotes_dict: Dict[str, str] = {}
    if res_remote_v.returncode == 0:
        for line in res_remote_v.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                r_name, r_url = parts[0], parts[1]
                remotes_dict[r_name] = r_url
    base["remotes"] = remotes_dict

    # Latest commit
    res_latest = run_cmd(["git", "log", "-1", "--format=%h - %an, %ar: %s"], check=False, cwd=repo_path)
    base["latest_commit"] = res_latest.stdout.strip() if res_latest.returncode == 0 else ""

    # Commits ahead of upstream
    commits_ahead: List[str] = []
    if base["upstream_ref"] != "-" and base["ahead_upstream"] > 0:
        res_log_ahead = run_cmd(["git", "log", "--oneline", f"{base['upstream_ref']}..HEAD", "-n", "10"], check=False, cwd=repo_path)
        if res_log_ahead.returncode == 0 and res_log_ahead.stdout.strip():
            commits_ahead = res_log_ahead.stdout.strip().splitlines()
    base["commits_ahead_upstream"] = commits_ahead

    # Commits behind upstream
    commits_behind: List[str] = []
    if base["upstream_ref"] != "-" and base["behind_upstream"] > 0:
        res_log_behind = run_cmd(["git", "log", "--oneline", f"HEAD..{base['upstream_ref']}", "-n", "10"], check=False, cwd=repo_path)
        if res_log_behind.returncode == 0 and res_log_behind.stdout.strip():
            commits_behind = res_log_behind.stdout.strip().splitlines()
    base["commits_behind_upstream"] = commits_behind

    # Uncommitted dirty files
    dirty_files: List[str] = []
    res_status_s = run_cmd(["git", "status", "--short"], check=False, cwd=repo_path)
    if res_status_s.returncode == 0 and res_status_s.stdout.strip():
        dirty_files = res_status_s.stdout.strip().splitlines()
    base["dirty_files"] = dirty_files

    # Diffstat vs upstream
    diffstat = ""
    if base["upstream_ref"] != "-":
        res_diffstat = run_cmd(["git", "diff", "--stat", f"{base['upstream_ref']}...HEAD"], check=False, cwd=repo_path)
        if res_diffstat.returncode == 0:
            diffstat = res_diffstat.stdout.strip()
    base["diffstat_vs_upstream"] = diffstat

    return base


def update_fork(repo_path: Path, rebase: bool = False, fetch: bool = True) -> Dict[str, Any]:
    """Safely update a fork repository from upstream."""
    repo_name = repo_path.name
    status = inspect_fork(repo_path, fetch=fetch)

    if status["dirty_count"] > 0:
        return {
            "repo": repo_name,
            "success": False,
            "action": "skipped_dirty",
            "message": f"Working tree has {status['dirty_count']} uncommitted change(s). Please commit or stash first.",
        }

    upstream_ref = status["upstream_ref"]
    if upstream_ref == "-":
        return {
            "repo": repo_name,
            "success": False,
            "action": "no_upstream",
            "message": "No upstream remote configured.",
        }

    active_branch = status["branch"]
    ahead = status["ahead_upstream"]
    behind = status["behind_upstream"]

    if active_branch in ("main", "master"):
        if behind == 0 and ahead == 0:
            return {
                "repo": repo_name,
                "success": True,
                "action": "up_to_date",
                "message": f"Already up to date with {upstream_ref}.",
            }
        elif behind > 0 and ahead == 0:
            res_merge = run_cmd(["git", "merge", "--ff-only", upstream_ref], check=False, cwd=repo_path)
            if res_merge.returncode == 0:
                return {
                    "repo": repo_name,
                    "success": True,
                    "action": "fast_forwarded",
                    "message": f"Successfully fast-forwarded {active_branch} to {upstream_ref} (+{behind} commits).",
                }
            else:
                return {
                    "repo": repo_name,
                    "success": False,
                    "action": "ff_failed",
                    "message": f"Fast-forward merge failed: {res_merge.stderr.strip()}",
                }
        elif ahead > 0 and behind == 0:
            return {
                "repo": repo_name,
                "success": True,
                "action": "ahead",
                "message": f"Branch {active_branch} is ahead of {upstream_ref} by {ahead} local commits (ready to push to origin).",
            }
        else:
            return {
                "repo": repo_name,
                "success": False,
                "action": "diverged",
                "message": f"Branch {active_branch} has diverged from {upstream_ref} (+{ahead}/-{behind}). Manual merge/rebase required.",
            }
    else:
        # Feature branch
        if behind == 0:
            return {
                "repo": repo_name,
                "success": True,
                "action": "up_to_date",
                "message": f"Feature branch '{active_branch}' is based on current {upstream_ref} (+{ahead}/-0).",
            }
        if rebase:
            res_rebase = run_cmd(["git", "rebase", upstream_ref], check=False, cwd=repo_path)
            if res_rebase.returncode == 0:
                return {
                    "repo": repo_name,
                    "success": True,
                    "action": "rebased",
                    "message": f"Successfully rebased '{active_branch}' onto {upstream_ref}.",
                }
            else:
                run_cmd(["git", "rebase", "--abort"], check=False, cwd=repo_path)
                return {
                    "repo": repo_name,
                    "success": False,
                    "action": "rebase_conflict",
                    "message": f"Rebase onto {upstream_ref} conflicted. Aborted rebase cleanly; manual rebase required.",
                }
        else:
            return {
                "repo": repo_name,
                "success": True,
                "action": "rebase_available",
                "message": f"Feature branch '{active_branch}' is behind {upstream_ref} by {behind} commits. Run with --rebase to rebase.",
            }


def cmd_forks(args: argparse.Namespace) -> None:
    forks_dir = resolve_forks_dir(args.dir)
    if not forks_dir or not forks_dir.exists():
        print("✗ Could not locate wom7pr directory.")
        sys.exit(1)

    subdirs = sorted([d for d in forks_dir.iterdir() if d.is_dir() and (d / ".git").exists()])
    if not subdirs:
        print(f"No git repositories found in {forks_dir}")
        return

    fetch = not args.no_fetch
    results = [inspect_fork(d, fetch=fetch) for d in subdirs]

    if args.json:
        print(json.dumps(results, indent=2))
        return

    headers = ["Repository", "Branch", "Upstream Ref", "vs Upstream", "Origin Sync", "Worktree", "Status"]
    table_data = []
    has_issues = False

    for r in results:
        if not r["is_synced"]:
            has_issues = True
        vs_upstream = f"+{r['ahead_upstream']}/-{r['behind_upstream']}" if r["upstream_ref"] != "-" else "-"
        origin_sync = f"+{r['ahead_origin']}/-{r['behind_origin']}" if r["has_origin_branch"] else "no remote branch"
        worktree = f"{r['dirty_count']} dirty" if r["dirty_count"] > 0 else "clean"
        table_data.append((
            r["repo"],
            r["branch"],
            r["upstream_ref"],
            vs_upstream,
            origin_sync,
            worktree,
            r["status"],
        ))

    if args.markdown:
        print(f"| {' | '.join(headers)} |")
        print(f"| {' | '.join(['---'] * len(headers))} |")
        for row in table_data:
            print(f"| {' | '.join(row)} |")
    else:
        col_widths = [len(h) for h in headers]
        for row in table_data:
            for i, val in enumerate(row):
                col_widths[i] = max(col_widths[i], len(str(val)))
        header_str = "  ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
        separator_str = "  ".join("-" * col_widths[i] for i in range(len(headers)))
        print(header_str)
        print(separator_str)
        for row in table_data:
            print("  ".join(str(row[i]).ljust(col_widths[i]) for i in range(len(headers))))

    print(f"\nChecked {len(results)} fork(s) in {forks_dir.name}/.")
    if has_issues and args.strict:
        print("✗ Strict mode: 1 or more forks require attention (behind upstream, behind origin, or dirty worktree).")
        sys.exit(1)


def cmd_fetch(args: argparse.Namespace) -> None:
    forks_dir = resolve_forks_dir(args.dir)
    if not forks_dir or not forks_dir.exists():
        print("✗ Could not locate wom7pr directory.")
        sys.exit(1)

    if args.repo:
        target = forks_dir / args.repo
        if not target.is_dir() or not (target / ".git").exists():
            print(f"✗ Repository '{args.repo}' not found in {forks_dir}")
            sys.exit(1)
        targets = [target]
    else:
        targets = sorted([d for d in forks_dir.iterdir() if d.is_dir() and (d / ".git").exists()])

    results = [fetch_fork(t) for t in targets]
    if args.json:
        print(json.dumps(results, indent=2))
        return

    print(f"Fetching remotes for {len(targets)} repository/repositories in {forks_dir.name}/...\n")
    for r in results:
        status_icon = "✓" if r["success"] else "✗"
        remotes_str = ", ".join(r["fetched"]) if r["fetched"] else "none"
        print(f"  {status_icon} {r['repo']}: fetched [{remotes_str}] ({r['duration_seconds']}s)")
        for err in r["errors"]:
            print(f"      ⚠ {err}")
    print("\nFetch complete.")


def cmd_info(args: argparse.Namespace) -> None:
    forks_dir = resolve_forks_dir(args.dir)
    if not forks_dir or not forks_dir.exists():
        print("✗ Could not locate wom7pr directory.")
        sys.exit(1)

    target = forks_dir / args.repo
    if not target.is_dir() or not (target / ".git").exists():
        print(f"✗ Repository '{args.repo}' not found in {forks_dir}")
        sys.exit(1)

    info = get_fork_info(target)
    if args.json:
        print(json.dumps(info, indent=2))
        return

    print(f"\nFork Inspection: {info['repo']}")
    print("═" * 60)
    print(f"  Path:             {info.get('path', target)}")
    print(f"  Active Branch:    {info['branch']}")
    print(f"  Upstream Target:  {info['upstream_ref']}")
    print(f"  Sync vs Upstream: +{info['ahead_upstream']}/-{info['behind_upstream']}")
    print(f"  Sync vs Origin:   +{info['ahead_origin']}/-{info['behind_origin']}")
    print(f"  Worktree:         {'Clean' if info['dirty_count'] == 0 else f'{info['dirty_count']} dirty file(s)'}")
    print(f"  Latest Commit:    {info.get('latest_commit', '-')}")

    if info.get("remotes"):
        print("\n  Remotes:")
        for r_name, r_url in info["remotes"].items():
            print(f"    • {r_name}: {r_url}")

    if info.get("commits_behind_upstream"):
        print(f"\n  Commits Behind Upstream ({len(info['commits_behind_upstream'])} shown):")
        for c in info["commits_behind_upstream"]:
            print(f"    ↓ {c}")

    if info.get("commits_ahead_upstream"):
        print(f"\n  Commits Ahead Upstream ({len(info['commits_ahead_upstream'])} shown):")
        for c in info["commits_ahead_upstream"]:
            print(f"    ↑ {c}")

    if info.get("dirty_files"):
        print(f"\n  Uncommitted Changes ({len(info['dirty_files'])}):")
        for f in info["dirty_files"][:10]:
            print(f"    * {f}")

    if info.get("diffstat_vs_upstream"):
        print("\n  Diffstat vs Upstream:")
        lines = info["diffstat_vs_upstream"].splitlines()
        for line in lines[-10:]:
            print(f"    {line}")
    print("═" * 60 + "\n")


def cmd_update(args: argparse.Namespace) -> None:
    forks_dir = resolve_forks_dir(args.dir)
    if not forks_dir or not forks_dir.exists():
        print("✗ Could not locate wom7pr directory.")
        sys.exit(1)

    if args.repo:
        target = forks_dir / args.repo
        if not target.is_dir() or not (target / ".git").exists():
            print(f"✗ Repository '{args.repo}' not found in {forks_dir}")
            sys.exit(1)
        targets = [target]
    else:
        targets = sorted([d for d in forks_dir.iterdir() if d.is_dir() and (d / ".git").exists()])

    fetch = not args.no_fetch
    results = [update_fork(t, rebase=args.rebase, fetch=fetch) for t in targets]
    if args.json:
        print(json.dumps(results, indent=2))
        return

    print(f"Updating {len(targets)} repository/repositories in {forks_dir.name}/...\n")
    for r in results:
        status_icon = "✓" if r["success"] else "⚠" if r["action"] in ("skipped_dirty", "rebase_available") else "✗"
        print(f"  {status_icon} {r['repo']} [{r['action']}]: {r['message']}")
    print("\nUpdate process complete.")


def main() -> None:
    parser = argparse.ArgumentParser(description="w0m-prs: GitHub PR tool for w0m estate (T345/T369/T377)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Search
    p_search = subparsers.add_parser("search", help="Search PRs by author, repo, or preset")
    p_search.add_argument("--author", type=str, help="GitHub author username")
    p_search.add_argument("--repo", type=str, help="GitHub repository (owner/name)")
    p_search.add_argument("--preset", type=str, choices=list(PRESET_REPOS.keys()), help="Preset target")
    p_search.add_argument("--limit", type=int, default=50, help="Maximum number of PRs")
    p_search.add_argument("--json", action="store_true", help="Output JSON")
    p_search.set_defaults(func=cmd_search)

    # Audit
    p_audit = subparsers.add_parser("audit", help="Audit PR mergeability, reviews, and CI")
    p_audit.add_argument("--repo", type=str, help="GitHub repository (owner/name)")
    p_audit.add_argument("--pr", type=int, help="PR number")
    p_audit.add_argument("--preset", type=str, choices=list(PRESET_REPOS.keys()), help="Preset target")
    p_audit.add_argument("--json", action="store_true", help="Output JSON")
    p_audit.set_defaults(func=cmd_audit)

    # Watch
    p_watch = subparsers.add_parser("watch", help="Monitor PRs on a background polling interval")
    p_watch.add_argument("--repo", type=str, help="GitHub repository (owner/name)")
    p_watch.add_argument("--pr", type=int, help="PR number")
    p_watch.add_argument("--preset", type=str, choices=list(PRESET_REPOS.keys()), default="wom7pr", help="Preset target (default: wom7pr)")
    p_watch.add_argument("--interval", type=float, default=5.0, help="Interval in minutes")
    p_watch.add_argument("--duration", type=float, default=30.0, help="Total duration in minutes")
    p_watch.add_argument("--notify", action="store_true", help="Send terminal bell/notification on delta")
    p_watch.set_defaults(func=cmd_watch)

    # Report
    p_report = subparsers.add_parser("report", help="Generate publication-grade Markdown report")
    p_report.add_argument("--author", type=str, default="casualuser", help="GitHub author username")
    p_report.add_argument("--out", type=str, help="Output file path")
    p_report.set_defaults(func=cmd_report)

    # Table
    p_table = subparsers.add_parser("table", help="Print fresh status table for PRs")
    p_table.add_argument("--author", type=str, default="casualuser", help="Filter by author (default: casualuser)")
    p_table.add_argument("--all", action="store_true", help="Show all authors across preset/repo")
    p_table.add_argument("--repo", type=str, help="GitHub repository (owner/name)")
    p_table.add_argument("--preset", type=str, choices=list(PRESET_REPOS.keys()), default="wom7pr", help="Preset target (default: wom7pr)")
    p_table.add_argument("--limit", type=int, default=30, help="Maximum number of PRs")
    p_table.add_argument("--markdown", action="store_true", help="Format output as Markdown table")
    p_table.set_defaults(func=cmd_table)

    # Forks
    p_forks = subparsers.add_parser("forks", help="Audit local fork synchronization against upstream remotes")
    p_forks.add_argument("--dir", type=str, help="Path to wom7pr directory")
    p_forks.add_argument("--no-fetch", action="store_true", help="Skip fetching remotes before checking")
    p_forks.add_argument("--strict", action="store_true", help="Exit non-zero if any fork is behind or dirty")
    p_forks.add_argument("--markdown", action="store_true", help="Format output as Markdown table")
    p_forks.add_argument("--json", action="store_true", help="Output structured JSON")
    p_forks.set_defaults(func=cmd_forks)

    # Fetch
    p_fetch = subparsers.add_parser("fetch", help="Fetch remotes for all forks or a specific repo")
    p_fetch.add_argument("repo", nargs="?", default=None, help="Specific repository name in wom7pr")
    p_fetch.add_argument("--dir", type=str, help="Path to wom7pr directory")
    p_fetch.add_argument("--json", action="store_true", help="Output structured JSON")
    p_fetch.set_defaults(func=cmd_fetch)

    # Info
    p_info = subparsers.add_parser("info", help="Deep inspection of a specific fork repository")
    p_info.add_argument("repo", type=str, help="Specific repository name in wom7pr")
    p_info.add_argument("--dir", type=str, help="Path to wom7pr directory")
    p_info.add_argument("--json", action="store_true", help="Output structured JSON")
    p_info.set_defaults(func=cmd_info)

    # Update
    p_update = subparsers.add_parser("update", help="Safely fast-forward or rebase forks with upstream")
    p_update.add_argument("repo", nargs="?", default=None, help="Specific repository name in wom7pr")
    p_update.add_argument("--rebase", action="store_true", help="Allow rebasing feature branches onto upstream")
    p_update.add_argument("--no-fetch", action="store_true", help="Skip fetching remotes before updating")
    p_update.add_argument("--dir", type=str, help="Path to wom7pr directory")
    p_update.add_argument("--json", action="store_true", help="Output structured JSON")
    p_update.set_defaults(func=cmd_update)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

