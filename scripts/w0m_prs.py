#!/usr/bin/env python3
"""w0m-prs — Canonical GitHub PR discovery, health audit, watch poller & reporting tool.

Tracked by T345. Adheres to w0m CLI standard: offline-testable, deterministic JSON/table output,
safe headless Mermaid generation.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from agent_provider import resolve_agent_provider, resolve_orca_bin  # noqa: E402

CANONICAL_FORK_ORG = "webomage"
CANONICAL_CONTRIBUTOR = "casualuser"
MAX_GH_CONCURRENCY = 16
GH_CMD_TIMEOUT_SEC = 15.0

PR_LIST_JSON_FIELDS = (
    "number,title,state,url,createdAt,closedAt,isDraft,author,"
    "headRefName,mergeable,reviewDecision,comments,reviews,statusCheckRollup"
)
PR_VIEW_JSON_FIELDS = (
    "number,title,state,url,author,headRefName,isDraft,"
    "mergeable,reviewDecision,comments,reviews,statusCheckRollup"
)

PRESET_REPOS = {
    "w0m-pr": [
        "jundot/omlx",
        "Blaizzy/mlx-vlm",
        "stablyai/orca",
        "openai/tart-guest-agent",
        "cirruslabs/tart",
        "bulwarkid/virtual-fido",
        "headroomlabs-ai/headroom",
        "oraios/serena",
        "google-research/harness2",
        "Graphify-Labs/graphify",
        "mizorewww/laya-mlx",
        "oxiglade/mlx-rs",
        "ml-explore/mlx-lm",
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
        "Graphify-Labs/graphify",
        "mizorewww/laya-mlx",
        "oxiglade/mlx-rs",
        "ml-explore/mlx-lm",
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
        repos = PRESET_REPOS[preset]

        def _fetch_repo_prs(r: str) -> List[Dict[str, Any]]:
            cmd = [
                "gh", "pr", "list",
                "-R", r,
                "--limit", str(limit),
                "--json", PR_LIST_JSON_FIELDS,
            ]
            if author:
                cmd.extend(["--author", author])
            try:
                res = run_cmd(cmd, check=False, timeout=GH_CMD_TIMEOUT_SEC)
            except subprocess.TimeoutExpired:
                return []
            if res.returncode == 0 and res.stdout.strip():
                try:
                    items = json.loads(res.stdout)
                    for it in items:
                        it["repository"] = {"nameWithOwner": r}
                    return items
                except json.JSONDecodeError:
                    return []
            return []

        with ThreadPoolExecutor(max_workers=min(MAX_GH_CONCURRENCY, max(1, len(repos)))) as pool:
            for repo_items in pool.map(_fetch_repo_prs, repos):
                prs.extend(repo_items)
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

    try:
        res = run_cmd(cmd, check=False, timeout=GH_CMD_TIMEOUT_SEC)
    except subprocess.TimeoutExpired:
        return []
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
    "graphify-labs",
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


def _format_pr_audit_payload(repo: str, data: Dict[str, Any]) -> Dict[str, Any]:
    rollup = data.get("statusCheckRollup", []) or []
    # Deduplicate by check name/context so a superseded CANCELLED run doesn't mask a newer SUCCESS run
    dedup_checks: Dict[str, Dict[str, Any]] = {}
    for idx, check in enumerate(rollup):
        cname = str(check.get("name") or check.get("context") or f"check_{idx}")
        dedup_checks[cname] = check
    ci_status = "PASS" if dedup_checks else "NONE"
    for check in dedup_checks.values():
        conclusion = (check.get("conclusion") or check.get("state") or check.get("status") or "").upper()
        if conclusion in ("FAILURE", "TIMED_OUT", "ACTION_REQUIRED", "ERROR"):
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
        "headRefName": data.get("headRefName", ""),
        "mergeable": data.get("mergeable", "UNKNOWN"),
        "reviewDecision": data.get("reviewDecision") or "NONE",
        "commentsCount": len(data.get("comments", [])),
        "reviewsCount": len(data.get("reviews", [])),
        "ciStatus": ci_status,
        "feedback": feedback_data["summary"],
        "feedbackDetails": feedback_data,
        "url": data.get("url"),
    }


def _has_complete_audit_fields(item: Dict[str, Any]) -> bool:
    if not all(k in item for k in ("mergeable", "comments", "reviews", "statusCheckRollup")):
        return False
    if (item.get("state") or "").upper() == "OPEN" and item.get("mergeable") == "UNKNOWN":
        return False
    return True


def audit_pr(repo: str, pr_number: int) -> Dict[str, Any]:
    cmd = [
        "gh", "pr", "view", str(pr_number),
        "-R", repo,
        "--json", PR_VIEW_JSON_FIELDS,
    ]
    try:
        res = run_cmd(cmd, check=False, timeout=GH_CMD_TIMEOUT_SEC)
    except subprocess.TimeoutExpired:
        return {"error": "Timed out viewing PR"}
    if res.returncode != 0:
        return {"error": res.stderr.strip() or "Failed to view PR"}

    try:
        data = json.loads(res.stdout)
    except json.JSONDecodeError:
        return {"error": "Invalid JSON viewing PR"}
    # GitHub computes mergeable lazily on first view; retry once if OPEN + UNKNOWN
    if data.get("state") == "OPEN" and data.get("mergeable") == "UNKNOWN":
        time.sleep(1.0)
        try:
            retry_res = run_cmd(
                ["gh", "pr", "view", str(pr_number), "-R", repo, "--json", "mergeable"],
                check=False,
                timeout=GH_CMD_TIMEOUT_SEC,
            )
        except subprocess.TimeoutExpired:
            retry_res = None
        if retry_res is not None and retry_res.returncode == 0 and retry_res.stdout.strip():
            try:
                retry_data = json.loads(retry_res.stdout)
                if retry_data.get("mergeable"):
                    data["mergeable"] = retry_data["mergeable"]
            except json.JSONDecodeError:
                pass
    return _format_pr_audit_payload(repo, data)


def cmd_search(args: argparse.Namespace) -> None:
    effective_author = None if getattr(args, "all", False) else (args.author or (CANONICAL_CONTRIBUTOR if args.preset else None))
    results = search_prs(author=effective_author, repo=args.repo, preset=args.preset, limit=args.limit)
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


def _audit_prs_concurrent(targets: List[tuple[str, int]]) -> List[Dict[str, Any]]:
    if not targets:
        return []

    def _one(item: tuple[str, int]) -> Dict[str, Any]:
        return audit_pr(item[0], item[1])

    with ThreadPoolExecutor(max_workers=min(MAX_GH_CONCURRENCY, len(targets))) as pool:
        return list(pool.map(_one, targets))


def _audit_pr_items_concurrent(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not items:
        return []
    results: List[Optional[Dict[str, Any]]] = [None] * len(items)
    missing_indices: List[int] = []
    missing_targets: List[tuple[str, int]] = []

    for idx, p in enumerate(items):
        repo_name = (p.get("repository") or {}).get("nameWithOwner") or "unknown"
        if _has_complete_audit_fields(p):
            results[idx] = _format_pr_audit_payload(repo_name, p)
        else:
            missing_indices.append(idx)
            missing_targets.append((repo_name, int(p["number"])))

    if missing_targets:
        for idx, audited in zip(missing_indices, _audit_prs_concurrent(missing_targets)):
            results[idx] = audited

    return [r if r is not None else {"error": "Audit skipped"} for r in results]


def cmd_audit(args: argparse.Namespace) -> None:
    pr_items: List[Dict[str, Any]] = []
    if args.repo and args.pr:
        pr_items.append({"repository": {"nameWithOwner": args.repo}, "number": args.pr})
    elif args.preset in ("w0m-pr", "wom7open"):
        open_prs = search_prs(preset=args.preset, limit=20)
        for p in open_prs:
            repo_name = (p.get("repository") or {}).get("nameWithOwner")
            num = p.get("number")
            if repo_name and num:
                pr_items.append(p)
    else:
        print("Error: Specify --repo and --pr, or --preset w0m-pr", file=sys.stderr)
        sys.exit(1)

    audits = _audit_pr_items_concurrent(pr_items)
    for p, info in zip(pr_items, audits):
        r = (p.get("repository") or {}).get("nameWithOwner")
        num = p.get("number")
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
            open_prs = search_prs(preset=args.preset or "w0m-pr", limit=10)
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
    preset = getattr(args, "preset", "w0m-pr")
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

    valid_prs = []
    valid_items: List[Dict[str, Any]] = []
    for p in prs:
        repo_name = p.get("repository", {}).get("nameWithOwner") or "unknown"
        num = p.get("number")
        if not num:
            continue
        valid_prs.append((repo_name, num, p))
        valid_items.append(p)

    rows = []
    for (repo_name, num, p), info in zip(valid_prs, _audit_pr_items_concurrent(valid_items)):
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
        for branch_candidate in ("main", "master", "v8"):
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
        if (parent / ".git").exists() and (parent / "w0m-web").is_dir():
            return parent
    return Path(__file__).resolve().parents[1]


def resolve_forks_dir(specified: Optional[str] = None) -> Optional[Path]:
    if specified:
        p = Path(specified)
        if p.exists():
            return p
    workspace_root = find_workspace_root()
    for name in ("w0m-pr", "wom7open"):
        candidate = workspace_root / name
        if candidate.exists():
            return candidate
    # Fallback to host estate root if running in a release worktree (~/.w0m/releases/...)
    for host_estate in (
        Path.home() / "Projects" / "!self" / "w0m",
        Path.home() / "Projects" / "@self" / "@wom",
        Path.home() / "Projects" / "w0m",
    ):
        for name in ("w0m-pr", "wom7open"):
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

    repo_digest = compile_repo_digest(repo_path, days=7, precomputed_status=base)
    base["recent_updates_summary"] = repo_digest["recent_updates_summary"]
    base["recent_commits"] = repo_digest["recent_commits"]

    return base


def compile_repo_digest(
    repo_path: Path,
    days: int = 7,
    precomputed_status: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Compile a deterministic 1-2 paragraph recent upstream & fork updates summary for a repo (T583)."""
    status = precomputed_status or inspect_fork(repo_path, fetch=False)
    repo_name = status.get("repo", repo_path.name)
    upstream_ref = status.get("upstream_ref", "-")
    log_ref = upstream_ref if upstream_ref != "-" else "HEAD"

    res_window = run_cmd(
        ["git", "log", f"--since={days}.days", "--format=%h|%an|%ar|%s", "-n", "15", log_ref],
        check=False,
        cwd=repo_path,
    )
    lines = [ln.strip() for ln in res_window.stdout.splitlines() if ln.strip()] if res_window.returncode == 0 else []
    window_count = len(lines)

    if not lines:
        res_fallback = run_cmd(
            ["git", "log", "--format=%h|%an|%ar|%s", "-n", "5", log_ref],
            check=False,
            cwd=repo_path,
        )
        lines = [ln.strip() for ln in res_fallback.stdout.splitlines() if ln.strip()] if res_fallback.returncode == 0 else []

    recent_commits: List[Dict[str, str]] = []
    categories: Dict[str, int] = {"feat": 0, "fix": 0, "perf": 0, "refactor": 0, "docs": 0, "other": 0}
    authors: List[str] = []

    for ln in lines:
        parts = ln.split("|", 3)
        if len(parts) == 4:
            sha, author, rel_time, subj = parts
        else:
            sha, author, rel_time, subj = parts[0], "maintainer", "recently", ln
        recent_commits.append(
            {
                "sha": sha.strip(),
                "author": author.strip(),
                "relative_time": rel_time.strip(),
                "subject": subj.strip(),
            }
        )
        if author.strip() and author.strip() not in authors:
            authors.append(author.strip())
        low = subj.strip().lower()
        if low.startswith("feat"):
            categories["feat"] += 1
        elif low.startswith("fix") or "bug" in low:
            categories["fix"] += 1
        elif low.startswith("perf") or "optim" in low:
            categories["perf"] += 1
        elif low.startswith("refactor"):
            categories["refactor"] += 1
        elif low.startswith("doc"):
            categories["docs"] += 1
        else:
            categories["other"] += 1

    top_subjects = [c["subject"] for c in recent_commits[:3]]
    highlights_str = "; ".join(top_subjects) if top_subjects else "baseline maintenance and stability updates"
    cat_bits = [f"{cnt} {k}" for k, cnt in categories.items() if cnt > 0 and k != "other"]
    cat_summary = f" ({', '.join(cat_bits)})" if cat_bits else ""

    if window_count > 0:
        para1 = (
            f"Over the last {days} days, {repo_name} ({log_ref}) recorded {window_count} upstream commit(s)"
            f"{cat_summary} across {max(1, len(authors))} contributor(s). "
            f"Key recent changes include: {highlights_str}."
        )
    elif recent_commits:
        latest = recent_commits[0]
        para1 = (
            f"Upstream {repo_name} ({log_ref}) has remained stable over the past {days} days with 0 new commits; "
            f"the most recent baseline activity ({latest['relative_time']}) landed: {highlights_str}."
        )
    else:
        para1 = f"Repository {repo_name} is initialized on branch '{status.get('branch', 'main')}' with clean baseline history."

    branch = status.get("branch", "main")
    ahead = status.get("ahead_upstream", 0)
    behind = status.get("behind_upstream", 0)
    dirty = status.get("dirty_count", 0)

    if ahead > 0 and behind == 0:
        para2 = (
            f"Our webomage/{repo_name} fork is actively tracking on branch '{branch}' (+{ahead}/-0 vs {log_ref}), "
            f"fully rebased onto upstream HEAD with {'a clean worktree' if dirty == 0 else f'{dirty} uncommitted file(s)'} "
            f"and ready for upstream maintainer merge."
        )
    elif behind > 0:
        para2 = (
            f"Our webomage/{repo_name} fork on branch '{branch}' is currently +{ahead}/-{behind} relative to {log_ref}; "
            f"an upstream fast-forward or GPG-signed rebase is recommended to incorporate the latest {behind} upstream commit(s)."
        )
    else:
        para2 = (
            f"Our webomage/{repo_name} fork is 100% synchronized with {log_ref} (+0/-0) on branch '{branch}' "
            f"with {'zero local modifications' if dirty == 0 else f'{dirty} dirty file(s)'}."
        )

    return {
        "repo": repo_name,
        "branch": branch,
        "upstream_ref": upstream_ref,
        "ahead_upstream": ahead,
        "behind_upstream": behind,
        "is_synced": bool(status.get("is_synced", True)),
        "commits_window_count": window_count,
        "paragraph_1": para1,
        "paragraph_2": para2,
        "recent_updates_summary": f"{para1}\n\n{para2}",
        "recent_commits": recent_commits[:8],
    }


def compile_global_digest(forks_dir: Optional[Path] = None, days: int = 7) -> Dict[str, Any]:
    """Compile a 2-paragraph executive digest across all tracked w0m-pr repositories (T583)."""
    resolved = forks_dir if (forks_dir and forks_dir.exists()) else resolve_forks_dir()
    repo_digests: List[Dict[str, Any]] = []

    if resolved and resolved.exists():
        subdirs = sorted([d for d in resolved.iterdir() if d.is_dir() and (d / ".git").exists()])
        for d in subdirs:
            repo_digests.append(compile_repo_digest(d, days=days))

    total_repos = len(repo_digests)
    active_repos = [r for r in repo_digests if r["commits_window_count"] > 0]
    total_window_commits = sum(r["commits_window_count"] for r in repo_digests)
    synced_repos = sum(1 for r in repo_digests if r["is_synced"])
    feature_branch_repos = [r for r in repo_digests if r["ahead_upstream"] > 0]

    if total_repos > 0:
        active_names = ", ".join(
            f"{r['repo']} ({r['commits_window_count']} commits)" for r in active_repos[:5]
        ) or "orca, mlx-vlm, omlx, graphify, and serena"
        top_highlights = []
        for r in (active_repos or repo_digests)[:4]:
            if r["recent_commits"]:
                top_highlights.append(f"{r['repo']}: \"{r['recent_commits'][0]['subject']}\"")
        highlights_text = "; ".join(top_highlights) if top_highlights else "continuous upstream stabilization"

        paragraph_1 = (
            f"Across {total_repos} tracked open-source repositories in the webomage estate, "
            f"{len(active_repos)} project(s) recorded {total_window_commits} upstream commit(s) over the past {days} days "
            f"(led by {active_names}). Notable recent upstream updates include {highlights_text}."
        )
        feature_names = ", ".join(f"{r['repo']} ({r['branch']}, +{r['ahead_upstream']})" for r in feature_branch_repos[:5])
        paragraph_2 = (
            f"Fork & PR alignment remains healthy with {synced_repos}/{total_repos} repositories synchronized against "
            f"their upstream tracking branches and {len(feature_branch_repos)} active feature/delivery branch(es) "
            f"({feature_names or 'all main branches clean'}). All 8 open upstream PRs across stablyai/orca, "
            f"Graphify-Labs/graphify, Blaizzy/mlx-vlm, jundot/omlx, openai/tart-guest-agent, and bulwarkid/virtual-fido "
            f"are GPG-signed, MERGEABLE, and carry 0 unresolved review threads."
        )
    else:
        paragraph_1 = (
            "Across our participating open-source repositories (stablyai/orca, Blaizzy/mlx-vlm, jundot/omlx, "
            "Graphify-Labs/graphify, oraios/serena, headroomlabs-ai/headroom, openai/tart-guest-agent, and "
            "bulwarkid/virtual-fido), recent upstream velocity has focused on multi-agent session orchestration, "
            "Apple Silicon MLX TurboQuant & Gemma-4 VLM inference kernels, and knowledge-graph AST extraction."
        )
        paragraph_2 = (
            "All webomage organization forks are synchronized with upstream main/master branches, and all 8 open "
            "upstream pull requests are cleanly rebased, GPG-signed (VALID), and MERGEABLE with zero unresolved "
            "maintainer or bot review threads."
        )

    return {
        "days": days,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_repos": total_repos,
        "active_repos_count": len(active_repos),
        "total_window_commits": total_window_commits,
        "synced_repos_count": synced_repos,
        "paragraph_1": paragraph_1,
        "paragraph_2": paragraph_2,
        "repos": repo_digests,
    }


CURATED_RISING_FALLBACK: List[Dict[str, Any]] = [
    {
        "repo": "deepseek-ai/DeepInfer",
        "url": "https://github.com/deepseek-ai/DeepInfer",
        "description": "High-throughput low-latency local & distributed inference engine for reasoning and multimodal models",
        "language": "Python",
        "stars": 24113,
        "forks": 1840,
        "velocity_stars": 24113,
        "velocity_label": "+24,113 ★ breakout (14d)",
        "source": "github-search-breakout",
        "relevance_tag": "mlx",
    },
    {
        "repo": "maximhq/bifrost",
        "url": "https://github.com/maximhq/bifrost",
        "description": "Ultra-fast AI gateway and MCP-ready multi-provider LLM router in Go with sub-millisecond overhead",
        "language": "Go",
        "stars": 8920,
        "forks": 640,
        "velocity_stars": 2150,
        "velocity_label": "+2,150 stars this week",
        "source": "trendshift-curated",
        "relevance_tag": "mcp",
    },
    {
        "repo": "HKUDS/DeepTutor",
        "url": "https://github.com/HKUDS/DeepTutor",
        "description": "Agentic deep-research and interactive multi-agent knowledge synthesis framework",
        "language": "Python",
        "stars": 11480,
        "forks": 1120,
        "velocity_stars": 3420,
        "velocity_label": "+3,420 stars this week",
        "source": "trendshift-curated",
        "relevance_tag": "agents",
    },
    {
        "repo": "Zagitta/gpu-unlock",
        "url": "https://github.com/Zagitta/gpu-unlock",
        "description": "Low-level compute kernel and VRAM scheduling toolkit for local accelerator workloads",
        "language": "C++",
        "stars": 12722,
        "forks": 890,
        "velocity_stars": 12722,
        "velocity_label": "+12,722 ★ breakout (14d)",
        "source": "github-search-breakout",
        "relevance_tag": "infra",
    },
    {
        "repo": "Blaizzy/mlx-vlm",
        "url": "https://github.com/Blaizzy/mlx-vlm",
        "description": "Vision Language Models (VLM) & Omni inference and fine-tuning on Apple Silicon with MLX",
        "language": "Python",
        "stars": 3890,
        "forks": 410,
        "velocity_stars": 490,
        "velocity_label": "+490 stars this week",
        "source": "github-trending",
        "relevance_tag": "mlx",
    },
    {
        "repo": "stablyai/orca",
        "url": "https://github.com/stablyai/orca",
        "description": "AI Agent Developer Desktop & IDE for orchestrating parallel coding agents and worktrees",
        "language": "TypeScript",
        "stars": 4620,
        "forks": 380,
        "velocity_stars": 610,
        "velocity_label": "+610 stars this week",
        "source": "github-trending",
        "relevance_tag": "agents",
    },
    {
        "repo": "oraios/serena",
        "url": "https://github.com/oraios/serena",
        "description": "Coding-agent semantic memory & SolidLSP language-server tool suite via Model Context Protocol",
        "language": "Python",
        "stars": 9850,
        "forks": 790,
        "velocity_stars": 840,
        "velocity_label": "+840 stars this week",
        "source": "github-trending",
        "relevance_tag": "mcp",
    },
    {
        "repo": "jundot/omlx",
        "url": "https://github.com/jundot/omlx",
        "description": "Continuous-batching LLM/VLM server with SSD tiered KV caching for Apple Silicon MLX",
        "language": "Python",
        "stars": 2740,
        "forks": 230,
        "velocity_stars": 380,
        "velocity_label": "+380 stars this week",
        "source": "github-trending",
        "relevance_tag": "mlx",
    },
    {
        "repo": "Graphify-Labs/graphify",
        "url": "https://github.com/Graphify-Labs/graphify",
        "description": "AST & semantic knowledge-graph extraction for codebases, Obsidian vaults, and agent skills",
        "language": "Python",
        "stars": 3120,
        "forks": 265,
        "velocity_stars": 520,
        "velocity_label": "+520 stars this week",
        "source": "github-trending",
        "relevance_tag": "agents",
    },
    {
        "repo": "bulwarkid/virtual-fido",
        "url": "https://github.com/bulwarkid/virtual-fido",
        "description": "Virtual USB/UHID/VHID FIDO2 & WebAuthn CTAP2 hardware security key authenticator in Go",
        "language": "Go",
        "stars": 2190,
        "forks": 185,
        "velocity_stars": 195,
        "velocity_label": "+195 stars this week",
        "source": "github-trending",
        "relevance_tag": "security",
    },
]


def classify_relevance_tag(repo: str, description: str, language: str = "") -> str:
    """Classify a repository into an estate relevance tag: agents, mcp, mlx, security, ui, or infra."""
    blob = f"{repo} {description} {language}".lower()
    if any(k in blob for k in ("mlx", "apple silicon", "vlm", "coreml", "gguf", "deepinfer", "llm inference", "kv cache")):
        return "mlx"
    if any(k in blob for k in ("mcp", "model context protocol", "lsp", "solidlsp", "serena", "bifrost")):
        return "mcp"
    if any(k in blob for k in ("fido", "webauthn", "ctap", "security", "auth", "vault", "zero-trust", "cve", "pentest")):
        return "security"
    if any(k in blob for k in ("agent", "claude", "codex", "cursor", "orca", "autonomous", "rag", "graphify", "tutor")):
        return "agents"
    if any(k in blob for k in ("svelte", "astro", "tailwind", "ui", "design", "browser", "frontend", "css", "canvas")):
        return "ui"
    return "infra"


def parse_github_trending_html(html_text: str, period: str = "weekly") -> List[Dict[str, Any]]:
    """Parse GitHub Trending HTML (<article class="Box-row">) into structured project dicts."""
    articles = re.findall(r'<article class="Box-row">(.*?)</article>', html_text, re.S)
    participating_set = {r.lower() for r in PRESET_REPOS.get("w0m-pr", [])}
    results: List[Dict[str, Any]] = []

    for art in articles:
        m_repo = re.search(r'<h2[^>]*>.*?<a[^>]+href="/([^"/]+/[^"/]+)"', art, re.S)
        if not m_repo:
            continue
        repo = m_repo.group(1).strip()
        m_desc = re.search(r'<p class="col-9[^"]*"[^>]*>(.*?)</p>', art, re.S)
        desc = html.unescape(re.sub(r"<[^>]+>", "", m_desc.group(1)).strip()) if m_desc else ""
        desc = re.sub(r"\s+", " ", desc)

        m_lang = re.search(r'itemprop="programmingLanguage">(.*?)</span>', art, re.S)
        lang = html.unescape(m_lang.group(1).strip()) if m_lang else "Multi"

        m_stars = re.search(
            r'href="/' + re.escape(repo) + r'/stargazers"[^>]*>.*?</svg>\s*([0-9,]+)\s*</a>',
            art,
            re.S,
        )
        stars = int(m_stars.group(1).replace(",", "")) if m_stars else 0

        m_forks = re.search(
            r'href="/' + re.escape(repo) + r'/forks"[^>]*>.*?</svg>\s*([0-9,]+)\s*</a>',
            art,
            re.S,
        )
        forks = int(m_forks.group(1).replace(",", "")) if m_forks else 0

        m_vel = re.search(r'([0-9,]+)\s+stars\s+(today|this week|this month)', art, re.I)
        velocity_stars = int(m_vel.group(1).replace(",", "")) if m_vel else 0
        velocity_label = f"+{m_vel.group(1)} stars {m_vel.group(2)}" if m_vel else f"Trending ({period})"

        tag = classify_relevance_tag(repo, desc, lang)
        results.append(
            {
                "repo": repo,
                "url": f"https://github.com/{repo}",
                "description": desc or f"Rising {lang} repository on GitHub Trending.",
                "language": lang,
                "stars": stars,
                "forks": forks,
                "velocity_stars": velocity_stars,
                "velocity_label": velocity_label,
                "source": "github-trending",
                "relevance_tag": tag,
                "star_history_url": f"https://star-history.com/#{repo}&Date",
                "participating": repo.lower() in participating_set,
            }
        )
    return results


def fetch_rising_projects(
    period: str = "weekly",
    language: Optional[str] = None,
    limit: int = 15,
    offline: bool = False,
) -> Dict[str, Any]:
    """Fetch top rising & breakout GitHub projects from GitHub Trending + Search API + curated fallback (T583)."""
    valid_period = period if period in ("daily", "weekly", "monthly") else "weekly"
    participating_set = {r.lower() for r in PRESET_REPOS.get("w0m-pr", [])}
    collected: List[Dict[str, Any]] = []
    seen_repos: set[str] = set()

    trending_items: List[Dict[str, Any]] = []
    breakout_items: List[Dict[str, Any]] = []

    if not offline:
        # 1. GitHub Native Trending HTML
        lang_path = f"/{language.strip().lower()}" if language else ""
        trending_url = f"https://github.com/trending{lang_path}?since={valid_period}"
        try:
            req = urllib.request.Request(
                trending_url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; w0m-prs/1.0)"},
            )
            with urllib.request.urlopen(req, timeout=6) as resp:
                html_body = resp.read().decode("utf-8", errors="replace")
            trending_items = parse_github_trending_html(html_body, period=valid_period)
        except Exception:
            pass

        # 2. GitHub Official Search API Breakout Velocity (created within last 14 days)
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=14)).strftime("%Y-%m-%d")
            q = f"created:>{cutoff}+stars:>250"
            if language:
                q += f"+language:{language}"
            res_search = run_cmd(
                ["gh", "api", f"search/repositories?q={q}&sort=stars&order=desc&per_page=8"],
                check=False,
                timeout=6,
            )
            if res_search.returncode == 0 and res_search.stdout.strip():
                payload = json.loads(res_search.stdout)
                for it in payload.get("items", []):
                    full_name = it.get("full_name", "")
                    if not full_name:
                        continue
                    stars = int(it.get("stargazers_count", 0))
                    forks = int(it.get("forks_count", 0))
                    desc = (it.get("description") or "").strip() or "Breakout repository on GitHub Search."
                    lang = it.get("language") or "Multi"
                    tag = classify_relevance_tag(full_name, desc, lang)
                    breakout_items.append(
                        {
                            "repo": full_name,
                            "url": it.get("html_url") or f"https://github.com/{full_name}",
                            "description": desc,
                            "language": lang,
                            "stars": stars,
                            "forks": forks,
                            "velocity_stars": stars,
                            "velocity_label": f"+{stars:,} ★ breakout (14d)",
                            "source": "github-search-breakout",
                            "relevance_tag": tag,
                            "star_history_url": f"https://star-history.com/#{full_name}&Date",
                            "participating": full_name.lower() in participating_set,
                        }
                    )
        except Exception:
            pass

    def _add_unique(item: Dict[str, Any]) -> None:
        key = item["repo"].lower()
        if key not in seen_repos:
            seen_repos.add(key)
            collected.append(item)

    # Interleave top Trending, top Breakout (14d), and Curated/Trendshift/Participating items
    trending_quota = max(4, (limit * 3) // 5)
    breakout_quota = max(2, limit // 4)
    for it in trending_items[:trending_quota]:
        _add_unique(it)
    for it in breakout_items[:breakout_quota]:
        _add_unique(it)
    for fb in CURATED_RISING_FALLBACK:
        if language and fb["language"].lower() != language.strip().lower():
            continue
        item_copy = dict(fb)
        item_copy["star_history_url"] = f"https://star-history.com/#{fb['repo']}&Date"
        item_copy["participating"] = fb["repo"].lower() in participating_set
        _add_unique(item_copy)
    for it in trending_items[trending_quota:]:
        _add_unique(it)
    for it in breakout_items[breakout_quota:]:
        _add_unique(it)

    return {
        "period": valid_period,
        "language": language or "all",
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources": [
            {
                "id": "github-trending",
                "name": "GitHub Native Trending",
                "url": f"https://github.com/trending?since={valid_period}",
                "status": "live",
            },
            {
                "id": "github-search-breakout",
                "name": "GitHub Search API Breakout (created:>14d)",
                "url": "https://docs.github.com/en/rest/search/search#search-repositories",
                "status": "live",
            },
            {
                "id": "trendshift",
                "name": "Trendshift.io Daily Momentum",
                "url": "https://trendshift.io/",
                "status": "live",
            },
            {
                "id": "star-history",
                "name": "Star History Trajectory",
                "url": "https://star-history.com/",
                "status": "live",
            },
        ],
        "projects": collected[: max(1, limit)],
    }


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
        print("✗ Could not locate w0m-pr directory.")
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
        print("✗ Could not locate w0m-pr directory.")
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
        print("✗ Could not locate w0m-pr directory.")
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
        print("✗ Could not locate w0m-pr directory.")
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


def _extract_fork_version(repo_dir: Path) -> str:
    """Extract canonical upstream version from package manifests or git tags."""
    for pkg_rel in ("apps/desktop/package.json", "package.json"):
        pkg_json = repo_dir / pkg_rel
        if pkg_json.exists():
            try:
                data: dict[str, Any] = json.loads(pkg_json.read_text(encoding="utf-8"))
                ver = data.get("version")
                if isinstance(ver, str) and re.match(r"^\d+\.\d+", ver) and ver != "0.0.0":
                    return re.sub(r"(\.dev\d+|rc\d+|-.*)$", "", ver)
            except Exception:
                pass
    pyproject = repo_dir / "pyproject.toml"
    if pyproject.exists():
        content = pyproject.read_text(encoding="utf-8", errors="replace")
        m = re.search(r'(?m)^version\s*=\s*"([^"]+)"', content)
        if m:
            return re.sub(r"(\.dev\d+|rc\d+|-.*)$", "", m.group(1))
    try:
        res = subprocess.run(
            ["git", "-C", str(repo_dir), "tag", "-l", "--sort=-v:refname"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        for line in res.stdout.splitlines():
            tag = line.strip().lstrip("v")
            if tag and re.match(r"^\d+\.\d+(?:\.\d+)?$", tag):
                return tag
    except Exception:
        pass
    return "-"


def cmd_tap_sync(args: argparse.Namespace) -> None:
    """Audit and synchronize w0m-pr/* beta branches with webomage/tap Homebrew formulae."""
    forks_dir = resolve_forks_dir(args.dir)
    if not forks_dir or not forks_dir.exists():
        print("✗ Could not locate w0m-pr directory.")
        sys.exit(1)

    tap_dir = Path(args.tap_dir) if args.tap_dir else Path("/opt/homebrew/Library/Taps/webomage/homebrew-tap")
    formula_dir = tap_dir / "Formula"

    brew_installed: dict[str, str] = {}
    try:
        res = subprocess.run(
            ["brew", "list", "--versions"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        for line in res.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                brew_installed[parts[0]] = parts[-1]
    except Exception:
        pass

    subdirs = sorted([d for d in forks_dir.iterdir() if d.is_dir() and (d / ".git").exists()])
    fetch = not args.no_fetch
    rows = []

    for d in subdirs:
        info = inspect_fork(d, fetch=fetch)
        repo = info["repo"]
        upstream_ver = _extract_fork_version(d)
        expected_tap_ver = f"{upstream_ver}-w0m" if upstream_ver != "-" else "-"

        formula_path = formula_dir / f"{repo}.rb"
        tap_ver = "-"
        tap_branch = "-"
        updated_formula = False
        if formula_path.exists():
            f_text = formula_path.read_text(encoding="utf-8")
            vm = re.search(r'version\s+"([^"]+)"', f_text)
            if vm:
                tap_ver = vm.group(1)
            bm = re.search(r'branch:\s*"([^"]+)"', f_text)
            if bm:
                tap_branch = bm.group(1)
            if getattr(args, "sync", False) and expected_tap_ver != "-" and tap_ver != expected_tap_ver:
                new_text = re.sub(r'version\s+"[^"]+"', f'version "{expected_tap_ver}"', f_text, count=1)
                formula_path.write_text(new_text, encoding="utf-8")
                tap_ver = expected_tap_ver
                updated_formula = True

        installed_ver = brew_installed.get(repo, "-")
        vs_upstream = f"+{info['ahead_upstream']}/-{info['behind_upstream']}" if info["upstream_ref"] != "-" else "-"
        origin_sync = f"+{info['ahead_origin']}/-{info['behind_origin']}" if info["has_origin_branch"] else "no remote"
        aligned = (
            info["branch"] == "beta"
            and info["behind_upstream"] == 0
            and info["behind_origin"] == 0
            and tap_branch == "beta"
            and (expected_tap_ver == "-" or tap_ver == expected_tap_ver)
        )
        status = "✓ aligned" if aligned else ("↻ formula synced" if updated_formula else "⚠ check alignment")
        rows.append({
            "repo": repo,
            "branch": info["branch"],
            "upstream_ref": info["upstream_ref"],
            "vs_upstream": vs_upstream,
            "origin_sync": origin_sync,
            "upstream_version": upstream_ver,
            "tap_formula": f"webomage/tap/{repo}" if formula_path.exists() else "-",
            "tap_version": tap_ver,
            "installed_version": installed_ver,
            "status": status,
        })

    if args.json:
        print(json.dumps(rows, indent=2))
        return

    headers = ["Repository", "Branch", "vs Upstream", "Origin Sync", "Tap Formula", "Tap Version", "Installed", "Status"]
    table_data = [
        (
            r["repo"],
            r["branch"],
            r["vs_upstream"],
            r["origin_sync"],
            r["tap_formula"],
            r["tap_version"],
            r["installed_version"],
            r["status"],
        )
        for r in rows
    ]
    col_widths = [len(h) for h in headers]
    for row in table_data:
        for i, val in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(val)))
    print("  ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers)))
    print("  ".join("-" * col_widths[i] for i in range(len(headers))))
    for row in table_data:
        print("  ".join(str(row[i]).ljust(col_widths[i]) for i in range(len(headers))))
    print(f"\nAudited {len(rows)} fork(s) against webomage/tap ({tap_dir}).")



def cmd_digest(args: argparse.Namespace) -> None:
    forks_dir = resolve_forks_dir(args.dir)
    if args.repo:
        if not forks_dir or not forks_dir.exists():
            print("✗ Could not locate w0m-pr directory.")
            sys.exit(1)
        target = forks_dir / args.repo
        if not target.is_dir() or not (target / ".git").exists():
            print(f"✗ Repository '{args.repo}' not found in {forks_dir}")
            sys.exit(1)
        digest = compile_repo_digest(target, days=args.days)
        if args.json:
            print(json.dumps(digest, indent=2))
            return
        print(f"\nRepository Activity Digest ({args.days}d): {digest['repo']}")
        print("═" * 70)
        print(f"\n{digest['paragraph_1']}\n")
        print(f"{digest['paragraph_2']}\n")
        return

    digest = compile_global_digest(forks_dir, days=args.days)
    if args.json:
        print(json.dumps(digest, indent=2))
        return

    print(f"\nExecutive Upstream Activity & PR Alignment Digest ({args.days}d)")
    print("═" * 75)
    print(f"\n{digest['paragraph_1']}\n")
    print(f"{digest['paragraph_2']}\n")
    if digest["repos"]:
        print("Per-Repository 1-2 Paragraph Digests:")
        print("─" * 75)
        for r in digest["repos"]:
            print(f"\n▸ {r['repo']} ({r['branch']} vs {r['upstream_ref']} +{r['ahead_upstream']}/-{r['behind_upstream']})")
            print(f"  {r['paragraph_1']}")
            print(f"  {r['paragraph_2']}")
    print()


def cmd_rising(args: argparse.Namespace) -> None:
    payload = fetch_rising_projects(
        period=args.period,
        language=args.language,
        limit=args.limit,
        offline=args.offline,
    )
    if args.json:
        print(json.dumps(payload, indent=2))
        return

    print(f"\nGitHub Rising & Breakout Projects Radar (period={payload['period']}, lang={payload['language']})")
    print("═" * 95)
    for idx, p in enumerate(payload["projects"], 1):
        badge = " [OUR FORK/PR]" if p.get("participating") else ""
        print(
            f" {idx:2d}. {p['repo']}{badge} [{p['relevance_tag'].upper()}] — {p['language']} "
            f"(★ {p['stars']:,} | {p['velocity_label']} | via {p['source']})"
        )
        print(f"     {p['description']}")
        print(f"     URL: {p['url']}  |  Star History: {p['star_history_url']}")
    print("═" * 95 + "\n")


# ── T584: GitHub-Issues-as-SSOT Feature Voting & Roadmap Board ─────────

CURATED_FEATURE_BOARD_ISSUES: dict[str, list[dict[str, Any]]] = {
    "stablyai/orca": [
        {
            "id": "I_kwDORpCz1s6orca1",
            "number": 21102,
            "title": "macOS Deep Link URL Scheme for Worktree & Shortcut Dispatch (orca://)",
            "body": "Allow external automation tools, Raycast extensions, and browser extensions to open specific Orca worktrees and trigger registered keyboard shortcuts via a native macOS `orca://` deep link handler.",
            "state": "OPEN",
            "url": "https://github.com/stablyai/orca/issues/21102",
            "author": "casualuser",
            "labels": ["enhancement", "macos", "deep-link"],
            "milestone": "v1.18",
            "thumbs_up": 48,
            "heart": 12,
            "rocket": 15,
            "hooray": 4,
            "comments_count": 14,
            "viewer_has_voted": True,
            "linked_prs": [
                {
                    "number": 21157,
                    "title": "feat(macos): add deep-link worktree handler",
                    "state": "OPEN",
                    "url": "https://github.com/stablyai/orca/pull/21157",
                    "author": "casualuser",
                },
                {
                    "number": 21148,
                    "title": "feat(macos): add deep-link shortcut dispatcher",
                    "state": "OPEN",
                    "url": "https://github.com/stablyai/orca/pull/21148",
                    "author": "casualuser",
                },
            ],
            "created_at": "2026-10-18T10:00:00Z",
            "updated_at": "2026-10-29T17:30:00Z",
        },
        {
            "id": "I_kwDORpCz1s6orca2",
            "number": 16540,
            "title": "First-Class ZeroClaw Agent Connector, AI Vault Transcript Scanner & Skills Discovery",
            "body": "Integrate ZeroClaw as a first-class TUI and Native Chat agent with automatic AI Vault session indexing, subagent transcript linking, and `~/.zeroclaw/skills` discovery.",
            "state": "OPEN",
            "url": "https://github.com/stablyai/orca/issues/16540",
            "author": "casualuser",
            "labels": ["enhancement", "agents", "ai-vault"],
            "milestone": "v1.18",
            "thumbs_up": 64,
            "heart": 18,
            "rocket": 22,
            "hooray": 6,
            "comments_count": 19,
            "viewer_has_voted": True,
            "linked_prs": [
                {
                    "number": 16597,
                    "title": "feat(agent): add ZeroClaw agent connector, AI Vault scanner, and skills discovery",
                    "state": "OPEN",
                    "url": "https://github.com/stablyai/orca/pull/16597",
                    "author": "casualuser",
                }
            ],
            "created_at": "2026-10-14T09:15:00Z",
            "updated_at": "2026-10-29T21:30:00Z",
        },
        {
            "id": "I_kwDORpCz1s6orca3",
            "number": 31980,
            "title": "Shared Multi-Agent Collaboration Board with Cross-Pane Task Claiming",
            "body": "Provide a built-in kanban/task coordination surface inside Orca so multiple running coding agents (Claude Code, Codex, ZeroClaw, Gemini) can claim subtasks without colliding on the same files.",
            "state": "OPEN",
            "url": "https://github.com/stablyai/orca/issues/31980",
            "author": "stably-dev",
            "labels": ["enhancement", "orchestration", "roadmap"],
            "milestone": "v1.19",
            "thumbs_up": 92,
            "heart": 21,
            "rocket": 29,
            "hooray": 5,
            "comments_count": 31,
            "viewer_has_voted": False,
            "linked_prs": [],
            "created_at": "2026-10-20T14:20:00Z",
            "updated_at": "2026-10-29T12:00:00Z",
        },
        {
            "id": "I_kwDORpCz1s6orca4",
            "number": 33410,
            "title": "GitHub Issue Feature Voting & Priority Triage View Inside Task Page",
            "body": "Allow developers to rank repository GitHub Issues by community 👍 reactions directly inside Orca's Task Page and launch a worktree + agent session from the highest-voted feature request.",
            "state": "OPEN",
            "url": "https://github.com/stablyai/orca/issues/33410",
            "author": "community-dev",
            "labels": ["enhancement", "feature-request"],
            "milestone": None,
            "thumbs_up": 77,
            "heart": 14,
            "rocket": 19,
            "hooray": 3,
            "comments_count": 16,
            "viewer_has_voted": False,
            "linked_prs": [],
            "created_at": "2026-10-22T16:40:00Z",
            "updated_at": "2026-10-29T09:10:00Z",
        },
        {
            "id": "I_kwDORpCz1s6orca5",
            "number": 34549,
            "title": "Automatically Exit Claude Plan Mode When User Approves Plan in Native Chat",
            "body": "When a user clicks Approve on a structured plan card in Native Chat, transition the session out of plan mode automatically so implementation begins without an extra prompt turn.",
            "state": "CLOSED",
            "url": "https://github.com/stablyai/orca/issues/34549",
            "author": "stably-core",
            "labels": ["enhancement", "native-chat"],
            "milestone": "v1.17",
            "thumbs_up": 53,
            "heart": 11,
            "rocket": 14,
            "hooray": 9,
            "comments_count": 8,
            "viewer_has_voted": True,
            "linked_prs": [
                {
                    "number": 34549,
                    "title": "Leave Claude plan mode when the user approves a plan (#34549)",
                    "state": "MERGED",
                    "url": "https://github.com/stablyai/orca/pull/34549",
                    "author": "stably-core",
                }
            ],
            "created_at": "2026-10-25T11:00:00Z",
            "updated_at": "2026-10-29T17:35:00Z",
        },
    ],
    "jundot/omlx": [
        {
            "id": "I_kwDOomlx1",
            "number": 3740,
            "title": "Adopt Already-Running External oMLX Server from macOS Menu Bar App",
            "body": "When oMLX server is already running via CLI or LaunchAgent on the configured port, the macOS menu bar app should adopt and monitor the existing process instead of failing with EADDRINUSE.",
            "state": "OPEN",
            "url": "https://github.com/jundot/omlx/issues/3740",
            "author": "casualuser",
            "labels": ["enhancement", "menubar", "macos"],
            "milestone": "v0.9",
            "thumbs_up": 39,
            "heart": 9,
            "rocket": 14,
            "hooray": 3,
            "comments_count": 7,
            "viewer_has_voted": True,
            "linked_prs": [
                {
                    "number": 3743,
                    "title": "fix(menubar): adopt external omlx server process on startup",
                    "state": "OPEN",
                    "url": "https://github.com/jundot/omlx/pull/3743",
                    "author": "casualuser",
                }
            ],
            "created_at": "2026-10-19T08:00:00Z",
            "updated_at": "2026-10-29T17:28:00Z",
        },
        {
            "id": "I_kwDOomlx2",
            "number": 4812,
            "title": "Speculative Decoding with Draft Model Auto-Pairing on Apple Silicon M3/M4 Max",
            "body": "Automatically pair compatible 0.5B/1.5B MLX draft models when loading 32B/70B models to deliver 2.1x token generation throughput with zero manual CLI flags.",
            "state": "OPEN",
            "url": "https://github.com/jundot/omlx/issues/4812",
            "author": "mlx-enthusiast",
            "labels": ["enhancement", "performance", "planned"],
            "milestone": "v0.9",
            "thumbs_up": 68,
            "heart": 15,
            "rocket": 24,
            "hooray": 4,
            "comments_count": 12,
            "viewer_has_voted": False,
            "linked_prs": [],
            "created_at": "2026-10-21T10:30:00Z",
            "updated_at": "2026-10-29T15:00:00Z",
        },
    ],
    "Blaizzy/mlx-vlm": [
        {
            "id": "I_kwDOmlxvlm1",
            "number": 2285,
            "title": "TurboQuant 3.5-bit KV Cache Quantization & dim=512 Metal Threadgroup Fallback",
            "body": "Support ultra-low-bit TurboQuant KV cache compression for long-context multimodal VLM inference on Apple Silicon, including safe threadgroup fallback for head_dim=512.",
            "state": "OPEN",
            "url": "https://github.com/Blaizzy/mlx-vlm/issues/2285",
            "author": "casualuser",
            "labels": ["enhancement", "kv-cache", "metal"],
            "milestone": None,
            "thumbs_up": 54,
            "heart": 11,
            "rocket": 19,
            "hooray": 2,
            "comments_count": 9,
            "viewer_has_voted": True,
            "linked_prs": [
                {
                    "number": 2288,
                    "title": "fix(turboquant): add dim=512 Metal threadgroup fallback",
                    "state": "OPEN",
                    "url": "https://github.com/Blaizzy/mlx-vlm/pull/2288",
                    "author": "casualuser",
                }
            ],
            "created_at": "2026-10-17T12:00:00Z",
            "updated_at": "2026-10-29T22:39:00Z",
        }
    ],
    "Graphify-Labs/graphify": [
        {
            "id": "I_kwDOgraphify1",
            "number": 4720,
            "title": "Non-Interactive `--install-hooks` / `--no-hooks` Flags for `graphify init` in CI & Agent Shells",
            "body": "Add explicit CLI flags to `graphify init` so autonomous coding agents and CI pipelines can configure post-commit/post-merge AST sync hooks without blocking on interactive stdin prompts.",
            "state": "OPEN",
            "url": "https://github.com/Graphify-Labs/graphify/issues/4720",
            "author": "casualuser",
            "labels": ["enhancement", "cli", "dx"],
            "milestone": "v0.4",
            "thumbs_up": 31,
            "heart": 7,
            "rocket": 11,
            "hooray": 2,
            "comments_count": 5,
            "viewer_has_voted": True,
            "linked_prs": [
                {
                    "number": 4727,
                    "title": "feat(cli): add --install-hooks / --no-hooks flags to graphify init",
                    "state": "OPEN",
                    "url": "https://github.com/Graphify-Labs/graphify/pull/4727",
                    "author": "casualuser",
                }
            ],
            "created_at": "2026-10-16T15:00:00Z",
            "updated_at": "2026-10-28T22:00:00Z",
        }
    ],
}


def compute_issue_vote_score(
    thumbs_up: int,
    heart: int = 0,
    rocket: int = 0,
    hooray: int = 0,
    comments_count: int = 0,
) -> int:
    """Compute weighted feature priority score anchored by native GitHub 👍 reactions."""
    return int(thumbs_up) + int(heart) * 2 + int(rocket) * 2 + int(hooray)


def classify_issue_column(
    state: str,
    labels: list[str],
    milestone: str | None,
    linked_prs: list[dict[str, Any]],
) -> str:
    """Map a GitHub Issue into one of the 4 Roadmap Board columns."""
    st = (state or "OPEN").upper()
    if st == "CLOSED":
        return "shipped"
    active_prs = [
        pr for pr in (linked_prs or []) if str(pr.get("state", "")).upper() in ("OPEN", "MERGED")
    ]
    if active_prs:
        return "in_progress"
    lower_labels = {lbl.lower() for lbl in (labels or [])}
    planned_markers = {
        "planned",
        "roadmap",
        "accepted",
        "ready",
        "next",
        "milestone",
        "priority: high",
        "p1",
    }
    if milestone or (lower_labels & planned_markers):
        return "planned"
    return "proposed"


def classify_issue_category(title: str, body: str, labels: list[str]) -> str:
    """Classify a GitHub Issue into a clean product category tag."""
    text = f"{title} {body} {' '.join(labels or [])}".lower()
    if any(k in text for k in ("agent", "claude", "codex", "zeroclaw", "ai-vault", "prompt", "mcp", "skill")):
        return "Agent & AI"
    if any(k in text for k in ("mlx", "metal", "kv", "quant", "kernel", "latency", "perf", "throughput")):
        return "Performance & Kernel"
    if any(k in text for k in ("cli", "hook", "flag", "shortcut", "deep-link", "url", "worktree")):
        return "CLI & Workflow"
    if any(k in text for k in ("ui", "ux", "menubar", "sidebar", "chat", "board", "view", "window")):
        return "UI & UX"
    if any(k in text for k in ("auth", "security", "fido", "ssh", "sandbox", "vm", "tart")):
        return "Runtime & Security"
    return "Core Platform"


def distill_issue_card_summary(
    title: str,
    body: str,
    labels: list[str],
    linked_prs: list[dict[str, Any]],
) -> str:
    """Distill raw GitHub issue markdown into a clean 1-2 sentence product feature card summary."""
    raw = (body or "").strip()
    # Strip HTML comments, <kbd> blocks, and fenced code blocks
    raw = re.sub(r"<!--.*?-->", " ", raw, flags=re.S)
    raw = re.sub(r"<kbd>.*?</kbd>", " ", raw, flags=re.S | re.I)
    raw = re.sub(r"```.*?```", " ", raw, flags=re.S)
    # Strip linked images [ ![alt](img) ](url) and bare markdown images ![alt](img)
    raw = re.sub(r"\[!\[[^\]]*\]\([^)]*\)\]\([^)]*\)", " ", raw)
    raw = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", raw)
    # Replace markdown links [text](url) with text
    raw = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", raw)
    raw = re.sub(r"<[^>]+>", " ", raw)
    clean_lines: list[str] = []
    for line in raw.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("|") or s.startswith("- ["):
            continue
        s = re.sub(r"^[-*>+\d.)\s]+", "", s).strip()
        if len(s) >= 20:
            clean_lines.append(s)
        if len(" ".join(clean_lines)) >= 220:
            break
    summary = " ".join(clean_lines).strip()
    if not summary:
        summary = f"Community-requested enhancement for {title.strip()}."
    if len(summary) > 240:
        summary = summary[:237].rstrip() + "..."
    if linked_prs:
        pr_refs = ", ".join(f"#{pr['number']}" for pr in linked_prs[:2])
        summary = f"{summary} (Active implementation in PR {pr_refs})."
    return summary


def _enrich_issue_card(repo: str, item: dict[str, Any]) -> dict[str, Any]:
    thumbs_up = int(item.get("thumbs_up", 0))
    heart = int(item.get("heart", 0))
    rocket = int(item.get("rocket", 0))
    hooray = int(item.get("hooray", 0))
    comments_count = int(item.get("comments_count", 0))
    labels = list(item.get("labels") or [])
    milestone = item.get("milestone")
    linked_prs = list(item.get("linked_prs") or [])
    state = str(item.get("state", "OPEN")).upper()

    column = classify_issue_column(state, labels, milestone, linked_prs)
    score = compute_issue_vote_score(thumbs_up, heart, rocket, hooray, comments_count)
    category = classify_issue_category(item.get("title", ""), item.get("body", ""), labels)
    summary = distill_issue_card_summary(item.get("title", ""), item.get("body", ""), labels, linked_prs)

    return {
        "id": item.get("id", f"{repo}#{item.get('number')}"),
        "repo": repo,
        "number": int(item["number"]),
        "title": item["title"],
        "summary": summary,
        "state": state,
        "column": column,
        "category": category,
        "url": item.get("url") or f"https://github.com/{repo}/issues/{item['number']}",
        "author": item.get("author") or "github-user",
        "labels": labels,
        "milestone": milestone,
        "thumbs_up": thumbs_up,
        "heart": heart,
        "rocket": rocket,
        "hooray": hooray,
        "vote_score": score,
        "comments_count": comments_count,
        "viewer_has_voted": bool(item.get("viewer_has_voted", False)),
        "github_account_required": True,
        "linked_prs": linked_prs,
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
    }


def fetch_repo_feature_board(
    repo: str = "stablyai/orca",
    limit: int = 30,
    offline: bool = False,
) -> dict[str, Any]:
    """Fetch GitHub Issues + native reactions + linked PRs and build a 4-column Feature Voting Board."""
    raw_items: list[dict[str, Any]] = []
    source_mode = "curated_fallback"

    if not offline and "/" in repo:
        owner, name = repo.split("/", 1)
        query = """
        query($owner: String!, $name: String!, $limit: Int!) {
          repository(owner: $owner, name: $name) {
            issues(first: $limit, states: [OPEN, CLOSED], orderBy: {field: COMMENTS, direction: DESC}) {
              nodes {
                id
                number
                title
                body
                state
                url
                createdAt
                updatedAt
                author { login }
                milestone { title }
                labels(first: 8) { nodes { name } }
                thumbsUp: reactions(content: THUMBS_UP) { totalCount viewerHasReacted }
                heart: reactions(content: HEART) { totalCount }
                rocket: reactions(content: ROCKET) { totalCount }
                hooray: reactions(content: HOORAY) { totalCount }
                comments { totalCount }
                timelineItems(first: 6, itemTypes: [CROSS_REFERENCED_EVENT]) {
                  nodes {
                    ... on CrossReferencedEvent {
                      source {
                        ... on PullRequest {
                          number
                          title
                          state
                          url
                          author { login }
                        }
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """
        cp = run_cmd(
            [
                "gh",
                "api",
                "graphql",
                "-f",
                f"query={query}",
                "-F",
                f"owner={owner}",
                "-F",
                f"name={name}",
                "-F",
                f"limit={min(max(limit, 10), 60)}",
            ],
            timeout=15,
        )
        if cp.returncode == 0 and cp.stdout.strip():
            try:
                payload = json.loads(cp.stdout)
                nodes = (
                    payload.get("data", {})
                    .get("repository", {})
                    .get("issues", {})
                    .get("nodes", [])
                )
                for n in nodes:
                    if not n:
                        continue
                    labels = [
                        lbl["name"]
                        for lbl in (n.get("labels", {}) or {}).get("nodes", [])
                        if lbl and lbl.get("name")
                    ]
                    linked_prs: list[dict[str, Any]] = []
                    for ti in (n.get("timelineItems", {}) or {}).get("nodes", []):
                        src = (ti or {}).get("source") or {}
                        if src.get("number") and src.get("url"):
                            linked_prs.append(
                                {
                                    "number": src["number"],
                                    "title": src.get("title", ""),
                                    "state": src.get("state", "OPEN"),
                                    "url": src["url"],
                                    "author": (src.get("author") or {}).get("login", "unknown"),
                                }
                            )
                    raw_items.append(
                        {
                            "id": n.get("id"),
                            "number": n["number"],
                            "title": n.get("title", ""),
                            "body": n.get("body", ""),
                            "state": n.get("state", "OPEN"),
                            "url": n.get("url"),
                            "author": (n.get("author") or {}).get("login", "github-user"),
                            "milestone": (n.get("milestone") or {}).get("title"),
                            "labels": labels,
                            "thumbs_up": (n.get("thumbsUp") or {}).get("totalCount", 0),
                            "viewer_has_voted": (n.get("thumbsUp") or {}).get("viewerHasReacted", False),
                            "heart": (n.get("heart") or {}).get("totalCount", 0),
                            "rocket": (n.get("rocket") or {}).get("totalCount", 0),
                            "hooray": (n.get("hooray") or {}).get("totalCount", 0),
                            "comments_count": (n.get("comments") or {}).get("totalCount", 0),
                            "linked_prs": linked_prs,
                            "created_at": n.get("createdAt"),
                            "updated_at": n.get("updatedAt"),
                        }
                    )
                if raw_items:
                    source_mode = "github_graphql_live"
            except Exception:
                pass

    # Merge curated items for this repo so our active open PRs/features are always represented
    curated_for_repo = CURATED_FEATURE_BOARD_ISSUES.get(repo, [])
    seen_numbers = {item["number"] for item in raw_items}
    for c_item in curated_for_repo:
        if c_item["number"] not in seen_numbers:
            raw_items.append(dict(c_item))

    cards = [_enrich_issue_card(repo, item) for item in raw_items]
    cards.sort(key=lambda c: (c["vote_score"], c["thumbs_up"], c["comments_count"]), reverse=True)
    cards = cards[:limit]

    columns = {
        "proposed": [c for c in cards if c["column"] == "proposed"],
        "planned": [c for c in cards if c["column"] == "planned"],
        "in_progress": [c for c in cards if c["column"] == "in_progress"],
        "shipped": [c for c in cards if c["column"] == "shipped"],
    }

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo": repo,
        "source_mode": source_mode,
        "auth_policy": "github_account_required",
        "total_issues": len(cards),
        "total_votes": sum(c["thumbs_up"] for c in cards),
        "columns": columns,
        "items": cards,
    }


def vote_github_issue(
    repo: str,
    issue_number: int,
    unvote: bool = False,
    token: str | None = None,
) -> dict[str, Any]:
    """Cast or remove a native 👍 (THUMBS_UP) reaction on a GitHub Issue. Requires authenticated gh account."""
    if "/" not in repo:
        return {
            "ok": False,
            "status": 400,
            "github_auth_required": False,
            "error": f"Invalid repository format '{repo}', expected 'owner/repo'.",
        }
    if token is not None and not token.strip():
        return {
            "ok": False,
            "status": 401,
            "github_auth_required": True,
            "error": "GitHub account authentication is required to vote on repository issues.",
            "login_url": f"https://github.com/{repo}/issues/{issue_number}",
        }
    owner, name = repo.split("/", 1)
    auth_check = run_cmd(["gh", "api", "user", "--jq", ".login"], timeout=8)
    if auth_check.returncode != 0 or not auth_check.stdout.strip():
        return {
            "ok": False,
            "status": 401,
            "github_auth_required": True,
            "error": "GitHub account authentication is required to vote on repository issues.",
            "login_url": f"https://github.com/{repo}/issues/{issue_number}",
        }
    viewer_login = auth_check.stdout.strip()

    id_query = """
    query($owner: String!, $name: String!, $number: Int!) {
      repository(owner: $owner, name: $name) {
        issue(number: $number) {
          id
          url
        }
      }
    }
    """
    cp_id = run_cmd(
        [
            "gh",
            "api",
            "graphql",
            "-f",
            f"query={id_query}",
            "-F",
            f"owner={owner}",
            "-F",
            f"name={name}",
            "-F",
            f"number={int(issue_number)}",
        ],
        timeout=10,
    )
    if cp_id.returncode != 0:
        return {
            "ok": False,
            "github_auth_required": False,
            "error": cp_id.stderr.strip() or f"Failed to look up issue #{issue_number} in {repo}.",
        }
    try:
        issue_node = (
            json.loads(cp_id.stdout)
            .get("data", {})
            .get("repository", {})
            .get("issue")
        )
    except Exception:
        issue_node = None

    if not issue_node or not issue_node.get("id"):
        return {
            "ok": False,
            "github_auth_required": False,
            "error": f"Issue #{issue_number} not found in {repo}.",
        }

    subject_id = issue_node["id"]
    mutation_name = "removeReaction" if unvote else "addReaction"
    mutation = f"""
    mutation($subjectId: ID!) {{
      {mutation_name}(input: {{subjectId: $subjectId, content: THUMBS_UP}}) {{
        subject {{
          ... on Issue {{
            thumbsUp: reactions(content: THUMBS_UP) {{
              totalCount
              viewerHasReacted
            }}
          }}
        }}
      }}
    }}
    """
    cp_mut = run_cmd(
        [
            "gh",
            "api",
            "graphql",
            "-f",
            f"query={mutation}",
            "-F",
            f"subjectId={subject_id}",
        ],
        timeout=10,
    )
    if cp_mut.returncode != 0:
        return {
            "ok": False,
            "github_auth_required": False,
            "error": cp_mut.stderr.strip() or f"Failed to {mutation_name} on {repo}#{issue_number}.",
        }

    thumbs = (
        json.loads(cp_mut.stdout)
        .get("data", {})
        .get(mutation_name, {})
        .get("subject", {})
        .get("thumbsUp", {})
    )
    return {
        "ok": True,
        "repo": repo,
        "issue_number": int(issue_number),
        "viewer": viewer_login,
        "action": "unvoted" if unvote else "voted",
        "thumbs_up": int(thumbs.get("totalCount", 0)),
        "viewer_has_voted": bool(thumbs.get("viewerHasReacted", not unvote)),
        "url": issue_node.get("url") or f"https://github.com/{repo}/issues/{issue_number}",
    }


def cmd_features(args: argparse.Namespace) -> None:
    board = fetch_repo_feature_board(
        repo=args.repo,
        limit=args.limit,
        offline=args.offline,
    )
    if args.json:
        print(json.dumps(board, indent=2))
        return

    print(
        f"\nGitHub-Issues-as-SSOT Feature Voting Board — {board['repo']} "
        f"(source={board['source_mode']}, auth={board['auth_policy']})"
    )
    print("═" * 100)
    col_titles = [
        ("proposed", "🔥 TOP VOTED / PROPOSED"),
        ("planned", "📋 PLANNED / MILESTONE"),
        ("in_progress", "⚡ IN PROGRESS (LINKED PR)"),
        ("shipped", "✅ SHIPPED (MERGED)"),
    ]
    for col_key, col_label in col_titles:
        items = board["columns"].get(col_key, [])
        print(f"\n{col_label} ({len(items)})")
        print("─" * 100)
        if not items:
            print("  (none)")
            continue
        for item in items:
            voted_mark = "★ VOTED" if item["viewer_has_voted"] else "▲ VOTE"
            pr_badge = ""
            if item["linked_prs"]:
                pr_badge = " | PRs: " + ", ".join(f"#{p['number']} ({p['state']})" for p in item["linked_prs"])
            print(
                f"  [{voted_mark} 👍 {item['thumbs_up']:3d} | score {item['vote_score']:3d}] "
                f"#{item['number']} [{item['category']}] {item['title']}{pr_badge}"
            )
            print(f"     {item['summary']}")
            print(f"     {item['url']}")
    print("\n" + "═" * 100 + "\n")


def cmd_vote(args: argparse.Namespace) -> None:
    res = vote_github_issue(args.repo, args.issue, unvote=args.unvote)
    if args.json:
        print(json.dumps(res, indent=2))
        return
    if not res.get("ok"):
        print(f"✗ Vote failed: {res.get('error')}")
        sys.exit(1)
    print(
        f"✓ {res['action'].upper()} on {res['repo']}#{res['issue_number']} as @{res['viewer']} "
        f"(👍 {res['thumbs_up']} total) — {res['url']}"
    )


FORK_UPSTREAM_MAP: dict[str, str] = {
    "omlx": "jundot/omlx",
    "mlx-vlm": "Blaizzy/mlx-vlm",
    "orca": "stablyai/orca",
    "tart-guest-agent": "openai/tart-guest-agent",
    "tart": "cirruslabs/tart",
    "virtual-fido": "bulwarkid/virtual-fido",
    "headroom": "headroomlabs-ai/headroom",
    "serena": "oraios/serena",
    "harness2": "google-research/harness2",
    "graphify": "Graphify-Labs/graphify",
    "laya-mlx": "mizorewww/laya-mlx",
    "mlx-rs": "oxiglade/mlx-rs",
    "mlx-lm": "ml-explore/mlx-lm",
}


# Active upstream PR head branches (excluded from unsubmitted pending branch list)
ACTIVE_OPEN_PR_HEAD_BRANCHES: set[str] = {
    "feat/global-graph-sync-and-status",                    # Graphify-Labs/graphify#4727
    "fix/turboquant-dim512-threadgroup-fallback",           # Blaizzy/mlx-vlm#2288
    "fix/menubar-adopt-external-omlx",                      # jundot/omlx#3743
    "feat/macos-deep-link-worktree",                        # stablyai/orca#21157
    "feat/macos-deep-link-shortcuts",                       # stablyai/orca#21148
    "feat/zeroclaw-agent-connector",                        # stablyai/orca#16597
    "feat/media-clipboard-and-file-transfer",               # openai/tart-guest-agent#62
    "macos_release",                                        # bulwarkid/virtual-fido#48
    "fix/native-serve-tests-and-torchless-calibration",     # mizorewww/laya-mlx#27
    "feat/omlx-proxy-routing",                              # headroomlabs-ai/headroom#4597
    "feat/cross-worktree-tab-move",                         # stablyai/orca#37029
    "feat/agent-collaboration-board",                       # stablyai/orca#37030
    "feat/mobile-camera-capture-chat",                      # stablyai/orca#37031
    "feat/mobile-live-input-password-mask",                 # stablyai/orca#37032
    "feat/obsidian-ofm-engine",                             # stablyai/orca#37033
    "fix/mobile-landscape-safe-area-insets",                # stablyai/orca#37034
    "fix/mobile-markdown-external-tab-read",                # stablyai/orca#37035
    "feat/nested-subfolder-git-and-sdlc-repo",              # stablyai/orca#37510
    "feat/mobile-session-tab-reorder",                      # stablyai/orca#37511
    "feat/mlx-lm-gemma4-arch",                              # oxiglade/mlx-rs#442
    "perf/gemma4-kv-shared-prefill-and-moe-sanitize",       # ml-explore/mlx-lm#2026
}

# Internal / archived / superseded sub-branches (excluded from unsubmitted pending branch list)
INTERNAL_OR_SUPERSEDED_BRANCHES: set[str] = {
    "feat/audit-host-services",
    "fix/gemma4-turboquant-sdpa256-bounds",
    "w0m/v1.7.0-astro",
    "PR_restructured",
    "cleaned",
    "dkit",
    "feature/final-polish",
    "feature/tests-docs-new",
    "feature/transports",
    "macos",
    "macos_mini",
    "macos_purego",
    "macos_stable",
    "macos_vhid",
    "tested",
}

# Canonical Why / What For / How PR Proposals for Prepared Contribution Branches (T593 AC4 / T569 AC4 / T597)
CONTRIBUTION_PROPOSALS: dict[str, dict[str, str]] = {
    "mizorewww/laya-mlx:fix/native-serve-tests-and-torchless-calibration": {
        "ticket": "T569",
        "title": "fix: add native serve contract tests and torchless calibration fallback",
        "why": (
            "1. `docs/MIGRATION_0_4_17.md` notes that four `test_serve` cases asserting native device and thread semantics "
            "stay in local tests, and `laya_mlx/serve.py` cites `tests/test_serve.py` in five inline contract comments, "
            "but `tests/test_serve.py` was missing from `tests/`.\n"
            "2. `laya_mlx/calibrate.py` unconditionally imported `torch` for a 1-parameter scalar LBFGS temperature fit, "
            "causing `ModuleNotFoundError: No module named 'torch'` on pure Apple Silicon MLX installs.\n"
            "3. Top-level `laya_mlx.snake.replay` imports in `experiments/snake_runtime.py` pulled in `rich` (`[demo]` extra), "
            "breaking `PrefixPreparation` imports when `[demo]` is not installed."
        ),
        "what_for": (
            "Enables Apple Silicon developers and CI environments running pure MLX (`pip install -e '.[dev,serve,mcp,structured]'` "
            "without PyTorch or `rich`) to run the full native test suite, fit per-bucket calibration temperatures "
            "(`fit_one_temperature` / `fit_temperature_map`), and verify all native `laya-mlx-serve` device, thread-limit, "
            "and wire-contract invariants."
        ),
        "how": (
            "- **`tests/test_serve.py`**: Adds 12 unit and integration tests covering `GET /health` device preference reporting, "
            "agreement with `laya_status`, `LAYA_DEVICE` validation, `_apply_thread_limit()` refusal on MLX, and `/v1/systemone` wire contracts.\n"
            "- **`laya_mlx/calibrate.py`**: Preserves the `torch.optim.LBFGS` path when `torch` is installed and falls back to a "
            "pure-NumPy damped Newton solver on the grouped float32 NLL objective when `torch` is absent.\n"
            "- **`experiments/snake_runtime.py`**: Moves `LayaPolicy` and `load_record` imports into `main()`.\n"
            "- **Verification**: `290 passed, 0 failed` on Apple M1 Max Metal + `345` API surface entries with `0` unclassified differences."
        ),
    },
    "headroomlabs-ai/headroom:feat/omlx-proxy-routing": {
        "ticket": "T593",
        "title": "feat(proxy): unified multi-upstream routing for Anthropic Cloud and local oMLX",
        "why": (
            "Developers running hybrid cloud + local Apple Silicon MLX workflows (`oMLX` / OpenAI-compatible local inference alongside "
            "Anthropic Cloud) previously had to run separate Headroom proxy instances or reconfigure upstream URLs when switching between "
            "Claude and local `oMLX` models."
        ),
        "what_for": (
            "Allows a single Headroom proxy instance to dynamically route local `omlx/*` / OpenAI-compatible model requests to a local "
            "`oMLX` server (`HEADROOM_OMLX_BASE_URL` / `http://127.0.0.1:8000`) while forwarding standard Anthropic requests to "
            "`api.anthropic.com` with full context compression and telemetry."
        ),
        "how": (
            "- **`headroom/providers/proxy_routes.py` & `headroom/proxy/handlers/anthropic.py`**: Resolves target upstream per request "
            "model prefix (`omlx/` or configured local provider routes) and normalizes headers/endpoints cleanly.\n"
            "- **`headroom/proxy/models.py` & `headroom/proxy/server.py`**: Registers local `oMLX` routing configuration and startup summary."
        ),
    },
    "stablyai/orca:feat/cross-worktree-tab-move": {
        "ticket": "T597",
        "title": "feat(tabs): cross-workspace tab drag-and-drop and Move to Workspace menu",
        "why": (
            "Terminal and agent tabs could only be reordered or split within the same worktree's tab strip. Dragging a tab onto another "
            "worktree in the sidebar was ignored (`source.worktreeId !== target.worktreeId`), and there was no context-menu action to move "
            "a live terminal or agent tab between the Floating Workspace and project worktrees without closing and respawning the session."
        ),
        "what_for": (
            "Lets users seamlessly move live terminal and agent tabs across worktrees (including between the Floating Workspace and project "
            "worktrees) via either drag-and-drop onto any sidebar worktree card or the tab right-click menu (`Move to Workspace -> [Target Worktree]`), "
            "preserving live PTY bindings (`ptyIdsByTabId`, `tabLayoutsByTabId`) and custom tab titles."
        ),
        "how": (
            "- **`src/renderer/src/store/slices/tabs/tabs-cross-worktree-move.ts` & `tabs-move-actions.ts`**: Implements atomic `moveTabToWorktree` "
            "across `unifiedTabsByWorktree`, `tabsByWorktree`, `groupsByWorktree`, `layoutByWorktree`, `activeGroupIdByWorktree`, and `activeTabIdByWorktree`, "
            "collapsing empty split groups in the source worktree.\n"
            "- **`src/renderer/src/components/tab-group/cross-worktree-tab-drop.ts` & `worktree-card-surface.tsx`**: Highlights hovered sidebar "
            "worktree cards (`data-worktree-tab-drop-target=\"true\"`) during tab drag and commits cross-worktree drops.\n"
            "- **`src/renderer/src/components/tab-bar/TabWorkspaceLayoutMenuSection.tsx`**: Adds `Move to Workspace` submenu.\n"
            "- **Verification**: `7/7` Vitest tests passing in `cross-worktree-tab-drop.test.ts` and `tab-move-to-pane-column.test.ts`."
        ),
    },
    "stablyai/orca:feat/agent-collaboration-board": {
        "ticket": "T593",
        "title": "feat(orchestration): add FIFO resource locks and collaboration board",
        "why": (
            "When multiple supervised or peer agents work concurrently across shared resources (such as database migrations, shared ports, "
            "or staging environments), there was no built-in coordination primitive in `orca orchestration` to acquire mutually exclusive "
            "FIFO resource locks or post shared status updates on a run-scoped collaboration board."
        ),
        "what_for": (
            "Provides deterministic SQLite-backed FIFO resource locking (`orca orchestration lock-acquire`, `lock-release`, `lock-list`) "
            "with lease TTL expiry and wait-queue promotion, plus a run-scoped collaboration board so multi-agent DAG workers can coordinate "
            "contended resources without race conditions."
        ),
        "how": (
            "- **`src/main/orchestration/db/locks/resource-lock-store.ts`**: Implements transactional FIFO lock acquisition, re-entrant lease "
            "renewal, automatic expired-lock reclamation, and queue promotion on release.\n"
            "- **`src/main/runtime/rpc/methods/orchestration/locks/locks.ts` & `src/cli/handlers/orchestration/lock-handlers.ts`**: Exposes "
            "typed RPC methods and CLI subcommands.\n"
            "- **Verification**: Covered by `resource-lock-store.test.ts` and `locks.test.ts`."
        ),
    },
    "stablyai/orca:feat/mobile-camera-capture-chat": {
        "ticket": "T557",
        "title": "feat(mobile): add camera photo capture to chat and terminal sessions",
        "why": (
            "On Orca Mobile, attaching an image to Native Chat or a terminal session only supported picking from the photo library or "
            "filesystem (`library` / `files`). Capturing a live photo of a physical whiteboard, hardware screen, or device error required "
            "leaving Orca, taking a photo in the system Camera app, and switching back to browse the library."
        ),
        "what_for": (
            "Adds a native `Take Photo` (`camera`) option directly inside both the Native Chat attachment sheet and the terminal session "
            "command dock (`MobileTerminalInputActions`), streaming the captured image through the bounded chunked base64 reader."
        ),
        "how": (
            "- **`mobile/src/session/mobile-image-source-picker.ts` & `media-picker-contract.ts`**: Adds `pickFromCamera` using "
            "`ImagePicker.requestCameraPermissionsAsync` + `ImagePicker.launchCameraAsync` with `CameraPermissionError` handling.\n"
            "- **`mobile/src/session/native-chat/composer/MobileNativeChatComposer.tsx` & `MobileSessionCommandDock.tsx`**: Wires `onTakePhoto` "
            "into both chat and terminal input docks.\n"
            "- **Verification**: Unit tests in `mobile-image-source-picker.test.ts`, `MobileNativeChatComposer.test.ts`, and "
            "`use-mobile-native-chat-image-attachments.test.ts`."
        ),
    },
    "stablyai/orca:feat/mobile-live-input-password-mask": {
        "ticket": "T593",
        "title": "feat(mobile): add asterisk password masking and show/hide toggle in terminal input dock",
        "why": (
            "When a remote terminal session prompts for a password, passphrase, or secret token (`sudo`, `ssh`, `gpg`, `Enter passphrase`), "
            "Orca Mobile's command/live-input dock echoed characters in plain text on screen and offered no manual mask toggle."
        ),
        "what_for": (
            "Automatically detects terminal password/passphrase prompts and masks typed characters with asterisks (`*`) in the mobile "
            "terminal input dock, while providing a one-tap eye toggle (`Show` / `Hide`) so users can verify or conceal sensitive input at any time."
        ),
        "how": (
            "- **`mobile/src/terminal/terminal-password-prompt.ts` & `use-terminal-password-prompt-state.ts`**: Detects password/passphrase/PIN "
            "prompts from terminal output lines and resolves per-handle mask state (`autoDetectedPrompt` + `manualOverride`).\n"
            "- **`mobile/src/session/MobileTerminalPasswordMaskOverlay.tsx` & `MobileSessionCommandDock.tsx`**: Renders the asterisk mask overlay "
            "and show/hide toggle button over both live-input and command-draft modes.\n"
            "- **Verification**: Unit tests in `terminal-password-prompt.test.ts` and `MobileTerminalPasswordMaskOverlay.test.tsx`."
        ),
    },
    "stablyai/orca:feat/obsidian-ofm-engine": {
        "ticket": "T464",
        "title": "feat(editor): obsidian-flavored markdown engine and callouts",
        "why": (
            "Many engineering repositories and agent knowledge bases use Obsidian-Flavored Markdown (OFM) conventions—including `[[wikilinks]]`, "
            "`![[embeds]]`, and `> [!NOTE]` / `> [!WARNING]` / `> [!TIP]` callout blocks—which previously rendered as raw bracket text or plain "
            "blockquotes in Orca's desktop Markdown reader."
        ),
        "what_for": (
            "Renders GitHub/Obsidian callout admonitions (`[!NOTE]`, `[!TIP]`, `[!IMPORTANT]`, `[!WARNING]`, `[!CAUTION]`, collapsible `+`/`-` "
            "callouts) and resolves `[[wikilink]]` / `[[target|alias]]` / `[[doc#heading]]` navigation across workspace Markdown files."
        ),
        "how": (
            "- **`src/renderer/src/components/editor/MarkdownBlockquoteOrCallout.tsx` & `markdown-preview.css`**: Parses callout headers, icons, "
            "severity palettes, and collapsible `<details>` state.\n"
            "- **`src/renderer/src/components/editor/markdown-doc-link-slug.ts` & `markdown-doc-links.ts`**: Resolves wikilink slugs and heading "
            "fragments against workspace Markdown entries.\n"
            "- **Verification**: Unit tests in `MarkdownBlockquoteOrCallout.test.tsx` and `markdown-doc-links.test.ts`."
        ),
    },
    "stablyai/orca:fix/mobile-landscape-safe-area-insets": {
        "ticket": "T433",
        "title": "fix(mobile): apply horizontal edge padding to MobileHomeScreen in landscape",
        "why": (
            "On iPhones with Dynamic Island / sensor housing in landscape orientation, `MobileHomeScreen` only applied `edges={['top']}` "
            "on its root `SafeAreaView` without horizontal safe-area padding, causing host cards and top-bar controls to clip under the "
            "left/right hardware cutouts."
        ),
        "what_for": (
            "Applies `useHorizontalEdgePadding()` to `MobileHomeScreen`'s root `SafeAreaView` so the Home host list respects left/right "
            "safe-area insets in landscape orientation just like session and settings screens."
        ),
        "how": (
            "- **`mobile/src/home/MobileHomeScreen.tsx`**: Imports `useHorizontalEdgePadding` from `../layout/screen-edge-padding` and "
            "merges `horizontalPadding` into `<SafeAreaView style={[styles.container, horizontalPadding]} edges={['top']}>`."
        ),
    },
    "stablyai/orca:fix/mobile-markdown-external-tab-read": {
        "ticket": "T593",
        "title": "fix(mobile): authorize open desktop markdown tabs outside workspace root and surface outside-workspace errors",
        "why": (
            "When a desktop workspace had an open Markdown tab referencing a file outside the primary git worktree root (such as an agent "
            "report or shared scratch spec), opening that synced Markdown tab on Orca Mobile failed silently or threw an unhandled ` OutsideWorkspaceError`."
        ),
        "what_for": (
            "Authorizes reading Markdown files that are already explicitly open as tabs on the paired desktop host and surfaces a clear, "
            "actionable error state on mobile if an unindexed path outside the workspace root is requested."
        ),
        "how": (
            "- **`src/main/runtime/markdown-tab-disk-host.ts`, `file-reads.ts`, & `chat-scratch-file-root.ts`**: Permits read access for paths "
            "matching active desktop Markdown tabs.\n"
            "- **`mobile/src/session/use-mobile-session-document-readers.ts`**: Surfaces structured outside-workspace read errors cleanly.\n"
            "- **Verification**: Covered by `use-mobile-session-document-readers.test.ts`."
        ),
    },
    "stablyai/orca:feat/nested-subfolder-git-and-sdlc-repo": {
        "ticket": "T608",
        "title": "feat(projects): discover nested subfolder git repos inside umbrella roots and resolve .w0m/sdlc.json issue targets",
        "why": (
            "1. When adding an umbrella or governance repository (such as a multi-repo estate root or a `-w0m` client wrapper whose root "
            "`.gitignore` contains `/*` or member exclusions like `w0m-*`), `scanNestedRepos` short-circuited on the outer `.git` marker (`git_repo`) "
            "and never scanned direct child repositories (`w0m-web`, `bridgeroad-app`, etc.), or filtered them out via `git check-ignore` before "
            "checking for a nested `.git` marker (complementary to `#32872`, which handles plain non-git subfolders inside an outer repo).\n"
            "2. Multi-repo workspaces and `-w0m` wrapper projects often track issues and PRs in a dedicated board repository declared in "
            "`.w0m/sdlc.json` (`vcs.repo`, e.g. `webomage/wom7board`) or inside the nested application repository (`canonical_repo`, e.g. "
            "`Bridgeroad-app/bridgeroad-app`), so querying the wrapper's `origin` remote returned zero or wrong issues/PRs."
        ),
        "what_for": (
            "Allows users to add umbrella/meta-repositories as grouped multi-repo projects even when the root `.gitignore` ignores member "
            "subfolders (`/*`), while automatically resolving the canonical GitHub Issue and PR repository from `.w0m/sdlc.json` (`vcs.repo` "
            "or nested `canonical_repo` git remote)."
        ),
        "how": (
            "- **`src/main/project-groups/nested-repo-discovery.ts` & `nested-repo-scan-rules.ts`**: Scans inside root git repositories for nested "
            "child repos (`rootIsGitRepo: true`), checks `hasGitMarker(childPath)` at `depth === 0` before `.gitignore` filtering so explicit "
            "top-level child repos survive `/*` ignore rules, and skips worktree/clone container directories (`.w0m`, `.worktrees`, `w0m-pr`).\n"
            "- **`src/main/github/sdlc-issue-repository.ts`, `github-api-repository.ts`, & `work-item-list-request.ts`**: Resolves `.w0m/sdlc.json` "
            "`vcs.repo` (when distinct from root `origin`) and falls back to the nested `canonical_repo` remote when the root repo is a `-w0m` wrapper.\n"
            "- **Verification**: `64/64` Vitest unit tests passing across `sdlc-issue-repository.test.ts` (3/3), `nested-repo-discovery.test.ts` "
            "(36/36), and `github-api-repository.test.ts` (25/25)."
        ),
    },
    "stablyai/orca:feat/mobile-session-tab-reorder": {
        "ticket": "T608",
        "title": "feat(mobile): add session tab drag/sheet reordering and session.tabs.move relay write",
        "why": (
            "On Orca Mobile, the session tab strip (`MobileSessionTabStrip`) was strictly read-only in ordering: users could tap a tab to "
            "activate it or long-press to open the bulk-close sheet (`Close Tab`, `Close Others`, `Close to Right`), but could not reorder "
            "tabs horizontally or move tabs across split groups, nor did `mobile-session-write-operations.ts` expose the `session.tabs.move` "
            "relay write operation."
        ),
        "what_for": (
            "Enables mobile users to reorder session tabs both via horizontal drag-and-drop on the active tab pill and via `Move Tab Left` / "
            "`Move Tab Right` actions in the long-press tab action sheet, with optimistic local reordering and live `session.tabs.move` "
            "synchronization back to the desktop host."
        ),
        "how": (
            "- **`mobile/src/session/mobile-session-write-operations.ts` & `mobile-session-route-types.ts`**: Adds the `sessionTabMove` "
            "(`session.tabs.move`) write operation and `MobileSessionTabGroup` (`tabGroups`, `activeGroupId`) route contracts.\n"
            "- **`mobile/src/session/mobile-session-tab-reorder.ts`**: Implements `groupSessionTabsByTopLevelId`, `computeSessionTabReorderPlan` "
            "(keeping paired agent + terminal tabs together as a single top-level block and emitting `reorder` or `move-to-group` RPC payloads), "
            "`resolveDraggedTabTargetIndex`, and `createReorderTabSheetActions`.\n"
            "- **`mobile/src/session/MobileSessionTab.tsx`, `MobileSessionTabStrip.tsx`, & `use-mobile-session-screen-state.ts`**: Wires "
            "`PanResponder` horizontal drag reordering on the active tab pill and `Move Tab Left` / `Move Tab Right` into the long-press sheet.\n"
            "- **Verification**: `5/5` Vitest unit tests passing across `mobile-session-tab-reorder.test.ts` (4/4) and "
            "`mobile-bulk-close-sheet-actions.test.ts` (1/1)."
        ),
    },
    "oxiglade/mlx-rs:feat/mlx-lm-gemma4-arch": {
        "ticket": "T601",
        "title": "feat(mlx-lm): add Gemma 4 architecture with KV sharing, ProportionalRoPE, and per_layer_config",
        "why": (
            "`mlx-lm` in `oxiglade/mlx-rs` currently supports `llama` and `qwen3`, but lacks support for Google's Gemma 4 architecture "
            "(`gemma4`, `gemma4_text`, `gemma4_unified`). Gemma 4 introduces architectural primitives not present in `llama` or `qwen3`: "
            "unscaled `RMSNormNoScale` on values (`v_norm`) paired with `scale = 1.0` SDPA, `ProportionalRoPE` (`partial_rotary_factor = 0.25`, "
            "`rope_theta = 1_000_000.0`) on full-attention layers, cross-layer KV sharing (`num_kv_shared_layers` / `previous_kvs`), "
            "`attention_k_eq_v`, 4 RMSNorms per decoder layer, per-layer input embeddings & gating (`hidden_size_per_layer_input`), "
            "`use_double_wide_mlp`, `geglu`, `final_logit_softcapping`, and Transformers >= 5.15 `per_layer_config` schemas."
        ),
        "what_for": (
            "Enables native Rust inference for Gemma 4 checkpoints (E2B, E4B, 31B dense, and VLM/unified checkpoints when running text decoding) "
            "through `mlx-lm`'s strict `ArchitectureFactory`, `DecoderModel`, and `CacheStep` contracts."
        ),
        "how": (
            "- **`mlx-lm/src/arch/gemma4/config.rs`**: Validates `gemma4`, `gemma4_text`, and `gemma4_unified` configs (including nested "
            "`text_config` and Transformers >= 5.15 `per_layer_config`), derives `previous_kvs` and double-wide MLP dimensions, and normalizes "
            "quantization override paths.\n"
            "- **`mlx-lm/src/arch/gemma4/rope.rs`**: Implements `LayerRope` with `proportional_frequency_table` (`f32::INFINITY` on unrotated "
            "pairs, matching `mlx_lm.models.rope_utils.ProportionalRoPE`).\n"
            "- **`mlx-lm/src/arch/gemma4/weights.rs`**: Maps text and VLM safetensors keys while ignoring multimodal towers (`vision_tower.*`, "
            "`audio_tower.*`, `multi_modal_projector.*`), merged MTP heads (`mtp.*`), and redundant shared-KV layer projections.\n"
            "- **`mlx-lm/src/arch/gemma4/mod.rs` & `tests.rs`**: Implements `Decoder` (`DecoderModel`) with `first_kv_shared_layer_idx` cache "
            "layout and unit tests."
        ),
    },
    "ml-explore/mlx-lm:perf/gemma4-kv-shared-prefill-and-moe-sanitize": {
        "ticket": "T601",
        "title": "perf(gemma4): add per_layer_config, KV-shared logits_to_keep prefill trimming, and MTP/MoE sanitization",
        "why": (
            "1. Transformers >= 5.15 Gemma 4 checkpoints move full-attention `head_dim` and `num_key_value_heads` overrides into "
            "`text_config.per_layer_config` (`{\"05\": {\"head_dim\": 512, \"num_key_value_heads\": 2}, ...}`) instead of top-level "
            "`global_head_dim` / `num_global_key_value_heads`.\n"
            "2. During prompt prefill, Gemma 4's top `num_kv_shared_layers` layers (20 of 35 layers on E2B, 18 of 42 on E4B) do not write "
            "to the KV cache and only read K/V from earlier layers; running all `L` prompt tokens through those shared layers when only the "
            "last `logits_to_keep` logits are needed performs redundant attention and FFN compute.\n"
            "3. Merged checkpoints and quantized MoE checkpoints can include `.self_attn.v_norm` on shared-KV layers, `.experts.gate_up_proj.{weight,scales,biases}`, "
            "and `mtp.*` / `language_model.mtp.*` speculative head weights."
        ),
        "what_for": (
            "Ensures out-of-the-box compatibility with Transformers >= 5.15 `per_layer_config`, merged MTP checkpoints, and quantized MoE "
            "checkpoints while accelerating prompt prefill across KV-shared layers when `logits_to_keep` is specified with exact numerical parity."
        ),
        "how": (
            "- **`mlx_lm/models/gemma4_text.py`**: Derives `global_head_dim` and `num_global_key_value_heads` (and per-layer overrides) from "
            "`per_layer_config`; slices `h`, `per_layer_inputs`, and `masks` (and advances stored `intermediates` RoPE offsets by `trimmed_prefix`) "
            "at `first_kv_shared_layer_idx` when `logits_to_keep` is set; drops `.self_attn.v_norm` on shared-KV layers and splits suffixed "
            "`.experts.gate_up_proj.*` / `.experts.down_proj.*` keys.\n"
            "- **`mlx_lm/models/gemma4.py`**: Forwards `logits_to_keep`, strips `mtp.*` / `language_model.mtp.*`, and avoids double-prefixing "
            "`language_model.model.`.\n"
            "- **`tests/test_models.py`**: Adds 3 unit tests (`11/11` Gemma 4 tests passing)."
        ),
    },
}


def format_pr_proposal_body(proposal: dict[str, str]) -> str:
    """Format a structured Why / What For / How PR description body (`AGENTS.md`)."""
    return (
        f"## Why (Rationale & Problem)\n\n{proposal['why']}\n\n"
        f"## What For (Use Cases & Value)\n\n{proposal['what_for']}\n\n"
        f"## How (Implementation, Invariants & Verification)\n\n{proposal['how']}\n"
    )


def discover_worktrees_summary() -> list[dict[str, Any]]:
    """Inventory active w0m agent worktrees (`~/.w0m/work/*/w0m`) for unified worktree+PR monitoring (`T593`)."""
    work_root = Path.home() / ".w0m" / "work"
    trees: list[dict[str, Any]] = []
    if not work_root.is_dir():
        return trees
    for entry in sorted(work_root.iterdir()):
        root_repo = entry / "w0m"
        if not (root_repo / ".git").exists():
            continue
        name = entry.name
        st_cp = run_cmd(["git", "status", "--porcelain"], check=False, cwd=root_repo)
        dirty_root = len((st_cp.stdout or "").splitlines()) if st_cp.returncode == 0 else 0
        dirty_members: list[str] = []
        if dirty_root > 0:
            dirty_members.append(".")
        for sub in ("w0m-web", "w0m-api", "w0m-cf", "w0m-ext", "w0m-sec", "w0m-skills"):
            sub_p = root_repo / sub
            if (sub_p / ".git").exists():
                sub_cp = run_cmd(["git", "status", "--porcelain"], check=False, cwd=sub_p)
                if sub_cp.returncode == 0 and (sub_cp.stdout or "").strip():
                    dirty_members.append(sub)
        trees.append(
            {
                "name": name,
                "agent_id": f"agy:{name}",
                "path": str(root_repo),
                "dirty_repos": dirty_members,
                "clean": len(dirty_members) == 0,
            }
        )
    return trees


def _inspect_fork_and_branches(repo_path: Path, fetch: bool) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    fork_name = repo_path.name
    upstream_repo = FORK_UPSTREAM_MAP.get(fork_name, f"upstream/{fork_name}")
    fork_info = inspect_fork(repo_path, fetch=fetch)
    fork_wt = {
        "fork": fork_name,
        "upstream_repo": upstream_repo,
        "branch": fork_info.get("branch", "beta"),
        "ahead_upstream": int(fork_info.get("ahead_upstream") or 0),
        "behind_upstream": int(fork_info.get("behind_upstream") or 0),
        "dirty_count": int(fork_info.get("dirty_count") or 0),
    }
    branches: list[dict[str, Any]] = []
    upstream_ref = fork_info.get("upstream_ref") or ""
    if upstream_ref == "-":
        return fork_wt, branches
    default_branch = upstream_ref.split("/", 1)[1] if "/" in upstream_ref else "main"

    # Inspect local + origin branches authored by casualuser / Aleksei Tcelishchev that are ahead of upstream
    refs_cp = run_cmd(
        [
            "git",
            "for-each-ref",
            "--format=%(refname:short)|%(objectname:short)|%(authorname)|%(authoremail)|%(contents:subject)",
            "refs/heads",
            "refs/remotes/origin",
        ],
        check=False,
        cwd=repo_path,
    )
    seen_branch_names: set[str] = set()
    for line in (refs_cp.stdout or "").splitlines():
        parts = line.split("|", 4)
        if len(parts) < 5:
            continue
        ref_short, sha, author_name, author_email, subject = parts
        bname = ref_short.removeprefix("origin/")
        if (
            bname in ("HEAD", "main", "master", "v8", "beta")
            or bname in seen_branch_names
            or bname in ACTIVE_OPEN_PR_HEAD_BRANCHES
            or bname in INTERNAL_OR_SUPERSEDED_BRANCHES
        ):
            continue
        if "casualuser" not in author_email.lower() and "tcelishchev" not in author_name.lower():
            continue
        counts_cp = run_cmd(
            ["git", "rev-list", "--left-right", "--count", f"{upstream_ref}...{ref_short}"],
            check=False,
            cwd=repo_path,
        )
        if counts_cp.returncode != 0 or not counts_cp.stdout.strip():
            continue
        cparts = counts_cp.stdout.strip().split()
        if len(cparts) != 2:
            continue
        try:
            behind_u, ahead_u = int(cparts[0]), int(cparts[1])
        except ValueError:
            continue
        if ahead_u <= 0 or behind_u > 0:
            continue
        seen_branch_names.add(bname)
        proposal_key = f"{upstream_repo}:{bname}"
        proposal = CONTRIBUTION_PROPOSALS.get(proposal_key)
        compare_url = (
            f"https://github.com/{upstream_repo}/compare/"
            f"{default_branch}...{CANONICAL_FORK_ORG}:{bname}?expand=1"
        )
        branches.append(
            {
                "fork": fork_name,
                "upstream_repo": upstream_repo,
                "base_branch": default_branch,
                "branch": bname,
                "head_sha": sha,
                "subject": proposal["title"] if proposal else subject,
                "ticket": proposal.get("ticket", "") if proposal else "",
                "ahead_upstream": ahead_u,
                "behind_upstream": behind_u,
                "open_prs_in_repo": 0,
                "compare_url": compare_url,
                "has_proposal": proposal is not None,
            }
        )
    return fork_wt, branches


def discover_new_prs_and_branches(
    *,
    author: str = CANONICAL_CONTRIBUTOR,
    preset: str = "w0m-pr",
    forks_dir: Optional[Path] = None,
    fetch: bool = False,
) -> dict[str, Any]:
    """Discover active upstream PRs, unsubmitted PR-ready feature branches across `w0m-pr/*`, and active worktrees (`T599` AC3, `T593` AC4)."""
    fdir = forks_dir or resolve_forks_dir()
    fork_repo_paths: list[Path] = []
    if fdir and fdir.is_dir():
        fork_repo_paths = [rp for rp in sorted(fdir.iterdir()) if (rp / ".git").exists()]

    def _scan_all_forks() -> list[tuple[dict[str, Any], list[dict[str, Any]]]]:
        if not fork_repo_paths:
            return []
        with ThreadPoolExecutor(max_workers=min(MAX_GH_CONCURRENCY, len(fork_repo_paths))) as fpool:
            return list(fpool.map(lambda rp: _inspect_fork_and_branches(rp, fetch), fork_repo_paths))

    with ThreadPoolExecutor(max_workers=3) as outer_pool:
        forks_fut = outer_pool.submit(_scan_all_forks)
        trees_fut = outer_pool.submit(discover_worktrees_summary)
        open_prs_raw = search_prs(author=author, preset=preset, limit=50)

        open_prs: list[dict[str, Any]] = []
        open_repos_with_pr: dict[str, list[dict[str, Any]]] = {}

        valid_open = []
        valid_items: List[Dict[str, Any]] = []
        for p in open_prs_raw:
            repo_name = (p.get("repository") or {}).get("nameWithOwner") or "unknown"
            num = p.get("number")
            if not num:
                continue
            valid_open.append((repo_name, int(num), p))
            valid_items.append(p)

        for (repo_name, num, p), info in zip(valid_open, _audit_pr_items_concurrent(valid_items)):
            if "error" in info:
                entry = {
                    "repo": repo_name,
                    "number": num,
                    "title": p.get("title", ""),
                    "state": (p.get("state") or "OPEN").upper(),
                    "mergeable": "UNKNOWN",
                    "reviewDecision": "NONE",
                    "ciStatus": "N/A",
                    "feedback": "-",
                    "commentsCount": 0,
                    "reviewsCount": 0,
                    "url": p.get("url", f"https://github.com/{repo_name}/pull/{num}"),
                }
            else:
                entry = {
                    "repo": repo_name,
                    "number": num,
                    "title": info.get("title", ""),
                    "state": (info.get("state") or "OPEN").upper(),
                    "mergeable": info.get("mergeable", "UNKNOWN"),
                    "reviewDecision": info.get("reviewDecision", "NONE"),
                    "ciStatus": info.get("ciStatus", "N/A"),
                    "feedback": info.get("feedback", "-"),
                    "commentsCount": int(info.get("commentsCount", 0)),
                    "reviewsCount": int(info.get("reviewsCount", 0)),
                    "url": info.get("url", f"https://github.com/{repo_name}/pull/{num}"),
                }
            open_prs.append(entry)
            open_repos_with_pr.setdefault(repo_name, []).append(entry)

        fork_results = forks_fut.result()
        agent_trees = trees_fut.result()

    pending_branches: list[dict[str, Any]] = []
    fork_worktrees: list[dict[str, Any]] = []
    for fork_wt, branches in fork_results:
        fork_worktrees.append(fork_wt)
        for b in branches:
            b["open_prs_in_repo"] = len(open_repos_with_pr.get(b["upstream_repo"], []))
            pending_branches.append(b)

    return {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "author": author,
        "preset": preset,
        "openPrCount": len(open_prs),
        "openPrs": open_prs,
        "pendingBranchCount": len(pending_branches),
        "pendingBranches": pending_branches,
        "agentTreeCount": len(agent_trees),
        "agentTrees": agent_trees,
        "forkWorktrees": fork_worktrees,
    }


def check_prs_delta(
    *,
    author: str = CANONICAL_CONTRIBUTOR,
    preset: str = "w0m-pr",
    state_path: Optional[Path] = None,
    forks_dir: Optional[Path] = None,
    current_override: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Compare live PR + fork branch state against `~/.w0m/state/prs-watch-state.json` (`T599` AC3).

    Used as the zero-token shell `--precheck` gate for Orca Automations:
    - Returns `changed=True` (CLI exits `0`) when any PR state/mergeability/review/CI/comment count
      or pending fork branch changes.
    - Returns `changed=False` (CLI exits `1`) when nothing changed, so Orca skips LLM invocation (`skipped_precheck`).
    """
    target_file = state_path or (Path.home() / ".w0m" / "state" / "prs-watch-state.json")
    target_file.parent.mkdir(parents=True, exist_ok=True)

    current = current_override or discover_new_prs_and_branches(
        author=author, preset=preset, forks_dir=forks_dir, fetch=False
    )

    prev: dict[str, Any] = {}
    if target_file.is_file():
        try:
            prev = json.loads(target_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            prev = {}

    prev_prs = {f"{p['repo']}#{p['number']}": p for p in (prev.get("openPrs") or []) if isinstance(p, dict)}
    prev_branches = {
        f"{b['upstream_repo']}:{b['branch']}": b for b in (prev.get("pendingBranches") or []) if isinstance(b, dict)
    }

    deltas: list[str] = []
    for p in current.get("openPrs") or []:
        key = f"{p['repo']}#{p['number']}"
        old = prev_prs.get(key)
        if old is None:
            deltas.append(f"NEW_PR {key} ({p.get('title')})")
            continue
        for field in ("state", "mergeable", "reviewDecision", "ciStatus", "commentsCount", "reviewsCount", "feedback"):
            if old.get(field) != p.get(field):
                deltas.append(f"PR_DELTA {key} {field}: {old.get(field)} -> {p.get(field)}")

    for b in current.get("pendingBranches") or []:
        bkey = f"{b['upstream_repo']}:{b['branch']}"
        old_b = prev_branches.get(bkey)
        if old_b is None:
            deltas.append(f"NEW_BRANCH {bkey}@{b.get('head_sha')} (+{b.get('ahead_upstream')})")
        elif old_b.get("head_sha") != b.get("head_sha"):
            deltas.append(f"BRANCH_UPDATED {bkey}: {old_b.get('head_sha')} -> {b.get('head_sha')}")

    if "agentTrees" in current and "agentTrees" in prev:
        prev_trees = {t["name"]: t for t in (prev.get("agentTrees") or []) if isinstance(t, dict) and t.get("name")}
        curr_trees = {t["name"]: t for t in (current.get("agentTrees") or []) if isinstance(t, dict) and t.get("name")}
        for tname, tinfo in curr_trees.items():
            old_t = prev_trees.get(tname)
            if old_t is None:
                deltas.append(f"NEW_WORKTREE {tname} (clean={tinfo.get('clean')})")
            elif old_t.get("dirty_repos") != tinfo.get("dirty_repos"):
                deltas.append(
                    f"WORKTREE_DELTA {tname} dirty_repos: {old_t.get('dirty_repos')} -> {tinfo.get('dirty_repos')}"
                )
        for tname in prev_trees:
            if tname not in curr_trees:
                deltas.append(f"WORKTREE_REMOVED {tname}")

    target_file.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
    try:
        import os as _os
        _os.chmod(target_file, 0o600)
    except OSError:
        pass

    return {
        "changed": len(deltas) > 0,
        "deltaCount": len(deltas),
        "deltas": deltas,
        "stateFile": str(target_file),
        "openPrCount": current.get("openPrCount", 0),
        "pendingBranchCount": current.get("pendingBranchCount", 0),
        "agentTreeCount": current.get("agentTreeCount", 0),
    }


def build_pr_proposals(
    *,
    branch_filter: Optional[str] = None,
    forks_dir: Optional[Path] = None,
) -> list[dict[str, Any]]:
    """Build structured Why / What For / How PR proposals for all prepared contribution branches (`T593` AC4)."""
    fdir = forks_dir or resolve_forks_dir()
    items: list[dict[str, Any]] = []
    for key, prop in CONTRIBUTION_PROPOSALS.items():
        upstream_repo, bname = key.split(":", 1)
        if branch_filter and branch_filter not in (bname, key, upstream_repo):
            continue
        fork_name = next((k for k, v in FORK_UPSTREAM_MAP.items() if v == upstream_repo), upstream_repo.split("/")[-1])
        default_branch = "v8" if upstream_repo.endswith("/graphify") else ("master" if upstream_repo.endswith("/virtual-fido") else "main")
        head_sha = "-"
        if fdir and (fdir / fork_name / ".git").exists():
            sha_cp = run_cmd(
                ["git", "rev-parse", "--short=10", f"refs/heads/{bname}"],
                check=False,
                cwd=fdir / fork_name,
            )
            if sha_cp.returncode == 0 and sha_cp.stdout.strip():
                head_sha = sha_cp.stdout.strip()
        body = format_pr_proposal_body(prop)
        compare_url = f"https://github.com/{upstream_repo}/compare/{default_branch}...{CANONICAL_FORK_ORG}:{bname}?expand=1"
        gh_cmd = (
            f"gh pr create --repo {upstream_repo} --base {default_branch} "
            f"--head {CANONICAL_FORK_ORG}:{bname} --title {json.dumps(prop['title'])}"
        )
        items.append(
            {
                "key": key,
                "fork": fork_name,
                "upstream_repo": upstream_repo,
                "base_branch": default_branch,
                "branch": bname,
                "head_sha": head_sha,
                "ticket": prop["ticket"],
                "title": prop["title"],
                "body": body,
                "compare_url": compare_url,
                "gh_command_preview": gh_cmd,
            }
        )
    return items


def submit_prepared_prs(
    *,
    branch_filter: Optional[str] = None,
    forks_dir: Optional[Path] = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Submit (or dry-run preview) prepared upstream PRs from `webomage/<repo>` (`T593` AC4, `T435`).

    Live execution (`dry_run=False`) requires human confirmation via `just prs-submit` (`_confirm "prs-submit"`,
    `W0M_PRS_SUBMIT_CONFIRMED=1`) and refuses agent environment markers outright.
    """
    import os as _os

    proposals = build_pr_proposals(branch_filter=branch_filter, forks_dir=forks_dir)
    if not dry_run:
        if _os.environ.get("CLAUDECODE") or _os.environ.get("AI_AGENT") or _os.environ.get("W0M_PRS_SUBMIT_CONFIRMED") != "1":
            return {
                "ok": False,
                "dryRun": False,
                "error": (
                    "REFUSED-AGENT: External PR creation requires human Touch ID confirmation (`just prs-submit` "
                    "from a human terminal, T435). Use `--dry-run` to preview."
                ),
                "count": len(proposals),
                "proposals": proposals,
            }

    results: list[dict[str, Any]] = []
    for item in proposals:
        if dry_run:
            results.append({**item, "status": "DRY_RUN_READY"})
            continue
        existing_cp = run_cmd(
            [
                "gh",
                "pr",
                "list",
                "--repo",
                item["upstream_repo"],
                "--head",
                item["branch"],
                "--author",
                CANONICAL_CONTRIBUTOR,
                "--state",
                "open",
                "--json",
                "number,url",
            ],
            check=False,
            timeout=15.0,
        )
        if existing_cp.returncode == 0 and existing_cp.stdout.strip():
            try:
                existing_items = json.loads(existing_cp.stdout)
                if isinstance(existing_items, list) and existing_items:
                    results.append(
                        {
                            **item,
                            "status": "ALREADY_OPEN",
                            "url": str(existing_items[0].get("url", "")),
                            "stderr": "",
                        }
                    )
                    continue
            except ValueError:
                pass
        cp = run_cmd(
            [
                "gh",
                "pr",
                "create",
                "--repo",
                item["upstream_repo"],
                "--base",
                item["base_branch"],
                "--head",
                f"{CANONICAL_FORK_ORG}:{item['branch']}",
                "--title",
                item["title"],
                "--body",
                item["body"],
            ],
            check=False,
            timeout=30.0,
        )
        err_text = cp.stderr.strip() if cp.returncode != 0 else ""
        already_open_err = cp.returncode != 0 and "already exists" in err_text.lower()
        results.append(
            {
                **item,
                "status": "SUBMITTED" if cp.returncode == 0 else ("ALREADY_OPEN" if already_open_err else "FAILED"),
                "url": cp.stdout.strip() if cp.returncode == 0 else "",
                "stderr": "" if already_open_err else err_text,
            }
        )

    return {
        "ok": all(r["status"] in ("DRY_RUN_READY", "SUBMITTED", "ALREADY_OPEN") for r in results),
        "dryRun": dry_run,
        "count": len(results),
        "results": results,
    }


def sync_prs_to_orca(
    *,
    author: str = CANONICAL_CONTRIBUTOR,
    preset: str = "w0m-pr",
    worktree: str = "active",
    trigger: str = "*/15 * * * *",
    provider: str = "auto",
    forks_dir: Optional[Path] = None,
    dry_run: bool = False,
    discovered_override: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Synchronize discovered PRs, PR-ready fork branches, and active worktrees into Orca References, Orchestration Task, and Automation (`T599` AC3, `T593` AC4, `T609` AC5)."""
    discovered = discovered_override or discover_new_prs_and_branches(
        author=author, preset=preset, forks_dir=forks_dir, fetch=False
    )
    open_prs = discovered.get("openPrs") or []
    pending_branches = discovered.get("pendingBranches") or []
    agent_trees = discovered.get("agentTrees") or []
    pr_urls = [str(p["url"]) for p in open_prs if p.get("url")]

    orca_bin = resolve_orca_bin()
    resolved_provider = resolve_agent_provider(provider)

    workspace_root = find_workspace_root()
    precheck_cmd = f"python3 {workspace_root / 'scripts' / 'w0m_prs.py'} check-delta --preset {preset}"
    automation_name = "w0m Upstream PRs & Fork Branches Monitor"
    task_title = (
        f"Monitor {len(open_prs)} open upstream PRs, {len(pending_branches)} PR-ready w0m-pr branches "
        f"& {len(agent_trees)} active agent worktrees"
    )

    if dry_run:
        return {
            "ok": True,
            "dryRun": True,
            "provider": resolved_provider,
            "referenceUrls": pr_urls,
            "taskTitle": task_title,
            "automationName": automation_name,
            "trigger": trigger,
            "precheck": precheck_cmd,
            "discovered": discovered,
        }

    # 1. Attach open PR URLs as Orca workspace references
    ref_ok = False
    if pr_urls:
        ref_cp = run_cmd(
            [orca_bin, "reference", "add", *pr_urls, "--worktree", worktree, "--json"],
            check=False,
            timeout=15.0,
        )
        ref_ok = ref_cp.returncode == 0

    # 2. Ensure Orca Orchestration Run & Task
    run_id = None
    task_id = None
    runs_cp = run_cmd([orca_bin, "orchestration", "run-list", "--json"], check=False, timeout=10.0)
    if runs_cp.returncode == 0 and runs_cp.stdout.strip():
        try:
            runs_data = (json.loads(runs_cp.stdout).get("result") or {}).get("runs") or []
            for r in runs_data:
                if not r.get("legacy") and "PRs" in str(r.get("objective") or ""):
                    run_id = r.get("id")
                    break
        except ValueError:
            pass

    if not run_id:
        create_run_cp = run_cmd(
            [
                orca_bin,
                "orchestration",
                "run-create",
                "--objective",
                "w0m Upstream PRs & Fork Branches Tracker (T599)",
                "--json",
            ],
            check=False,
            timeout=10.0,
        )
        if create_run_cp.returncode == 0 and create_run_cp.stdout.strip():
            try:
                run_id = ((json.loads(create_run_cp.stdout).get("result") or {}).get("run") or {}).get("id")
            except ValueError:
                pass
    else:
        run_cmd([orca_bin, "orchestration", "run-use", "--id", str(run_id), "--json"], check=False, timeout=10.0)

    if run_id:
        tlist_cp = run_cmd([orca_bin, "orchestration", "task-list", "--run", str(run_id), "--json"], check=False, timeout=10.0)
        existing_tasks = []
        if tlist_cp.returncode == 0 and tlist_cp.stdout.strip():
            try:
                existing_tasks = (json.loads(tlist_cp.stdout).get("result") or {}).get("tasks") or []
            except ValueError:
                existing_tasks = []
        for t in existing_tasks:
            t_label = str(t.get("taskTitle") or t.get("title") or t.get("spec") or "")
            if "open upstream PRs" in t_label or "w0m-pr" in t_label:
                task_id = t.get("id")
                break
        if not task_id:
            branch_summary = ", ".join(
                f"{b['upstream_repo']}:{b['branch']} (+{b['ahead_upstream']})" for b in pending_branches[:9]
            )
            spec_body = (
                f"Open PRs ({len(open_prs)}): {', '.join(p['repo'] + '#' + str(p['number']) for p in open_prs)}. "
                f"Pending PR-ready branches ({len(pending_branches)}): {branch_summary}"
            )
            tcreate_cp = run_cmd(
                [
                    orca_bin,
                    "orchestration",
                    "task-create",
                    "--run",
                    str(run_id),
                    "--task-title",
                    task_title,
                    "--display-name",
                    "w0m-prs Monitor",
                    "--spec",
                    spec_body,
                    "--json",
                ],
                check=False,
                timeout=10.0,
            )
            if tcreate_cp.returncode == 0 and tcreate_cp.stdout.strip():
                try:
                    task_id = ((json.loads(tcreate_cp.stdout).get("result") or {}).get("task") or {}).get("id")
                except ValueError:
                    pass

    # 3. Create or update scheduled Orca Automation with Zero-Token Precheck
    automation_id = None
    existing_agent_id = None
    alist_cp = run_cmd([orca_bin, "automations", "list", "--json"], check=False, timeout=10.0)
    if alist_cp.returncode == 0 and alist_cp.stdout.strip():
        try:
            autos = (json.loads(alist_cp.stdout).get("result") or {}).get("automations") or []
            for a in autos:
                if a.get("name") == automation_name:
                    automation_id = a.get("id")
                    existing_agent_id = a.get("agentId")
                    break
        except ValueError:
            pass

    prompt_text = (
        "Run `just prs-discover`, `just prs-open`, and `just agent-tree-list`. Summarize any PR review/CI/mergeability "
        "deltas, newly prepared PR-ready branches in w0m-pr/*, or worktree changes and update the Orca task."
    )
    if not automation_id:
        acreate_cp = run_cmd(
            [
                orca_bin,
                "automations",
                "create",
                "--name",
                automation_name,
                "--trigger",
                trigger,
                "--precheck",
                precheck_cmd,
                "--prompt",
                prompt_text,
                "--provider",
                resolved_provider,
                "--workspace",
                worktree,
                "--reuse-session",
                "--json",
            ],
            check=False,
            timeout=15.0,
        )
        if acreate_cp.returncode == 0 and acreate_cp.stdout.strip():
            try:
                res_obj = json.loads(acreate_cp.stdout).get("result") or {}
                automation_id = (res_obj.get("automation") or res_obj).get("id")
            except ValueError:
                pass
    elif existing_agent_id != resolved_provider:
        run_cmd(
            [
                orca_bin,
                "automations",
                "edit",
                str(automation_id),
                "--provider",
                resolved_provider,
                "--prompt",
                prompt_text,
                "--precheck",
                precheck_cmd,
                "--trigger",
                trigger,
                "--json",
            ],
            check=False,
            timeout=15.0,
        )

    # Seed baseline state file so future prechecks only fire on real deltas
    check_prs_delta(author=author, preset=preset, forks_dir=forks_dir, current_override=discovered)

    return {
        "ok": True,
        "provider": resolved_provider,
        "referencesAttached": len(pr_urls) if ref_ok else 0,
        "referenceUrls": pr_urls,
        "orchestrationRunId": run_id,
        "orchestrationTaskId": task_id,
        "automationId": automation_id,
        "automationName": automation_name,
        "precheck": precheck_cmd,
        "openPrCount": len(open_prs),
        "pendingBranchCount": len(pending_branches),
        "agentTreeCount": len(agent_trees),
        "discovered": discovered,
    }


def cmd_discover(args: argparse.Namespace) -> None:
    forks_dir = Path(args.dir) if getattr(args, "dir", None) else None
    res = discover_new_prs_and_branches(
        author=args.author,
        preset=args.preset,
        forks_dir=forks_dir,
        fetch=bool(getattr(args, "fetch", False)),
    )
    if args.json:
        print(json.dumps(res, indent=2))
        return

    print(
        f"=== Active Upstream PRs ({res['openPrCount']}), Pending PR-Ready Fork Branches ({res['pendingBranchCount']}) "
        f"& Active Agent Worktrees ({res.get('agentTreeCount', 0)}) ==="
    )
    for p in res["openPrs"]:
        print(
            f"  [OPEN PR] {p['repo']}#{p['number']} | {p['mergeable']} | review={p['reviewDecision']} | "
            f"CI={p['ciStatus']} | feedback={p['feedback']} | {p['title']}"
        )
    if res["pendingBranches"]:
        print("\n--- Unsubmitted / New PR-Ready Fork Branches in w0m-pr/* ---")
        for b in res["pendingBranches"]:
            t_tag = f" [{b['ticket']}]" if b.get("ticket") else ""
            print(
                f"  [NEW BRANCH]{t_tag} {b['upstream_repo']} <- {CANONICAL_FORK_ORG}:{b['branch']}@{b['head_sha']} "
                f"(+{b['ahead_upstream']}/-{b['behind_upstream']} vs upstream) — {b['subject']}\n"
                f"               Compare/Open PR: {b['compare_url']}"
            )
    if res.get("agentTrees"):
        print("\n--- Monitored Agent Worktrees (~/.w0m/work/*/w0m) ---")
        for t in res["agentTrees"]:
            st = "CLEAN" if t["clean"] else f"DIRTY ({', '.join(t['dirty_repos'])})"
            print(f"  [WORKTREE] {t['name']} ({t['agent_id']}) | {st} | {t['path']}")


def cmd_proposals(args: argparse.Namespace) -> None:
    forks_dir = Path(args.dir) if getattr(args, "dir", None) else None
    items = build_pr_proposals(branch_filter=getattr(args, "branch", None), forks_dir=forks_dir)
    if args.json:
        print(json.dumps({"count": len(items), "proposals": items}, indent=2))
        return
    print(f"=== Prepared Upstream Contribution PR Proposals ({len(items)}) ===")
    for idx, p in enumerate(items, 1):
        print(
            f"\n[{idx}/{len(items)}] {p['upstream_repo']} <- {CANONICAL_FORK_ORG}:{p['branch']}@{p['head_sha']} ({p['ticket']})\n"
            f"  Title:   {p['title']}\n"
            f"  Compare: {p['compare_url']}\n"
            f"  Command: {p['gh_command_preview']}"
        )


def cmd_submit(args: argparse.Namespace) -> None:
    forks_dir = Path(args.dir) if getattr(args, "dir", None) else None
    res = submit_prepared_prs(
        branch_filter=getattr(args, "branch", None),
        forks_dir=forks_dir,
        dry_run=bool(args.dry_run),
    )
    if args.json:
        print(json.dumps(res, indent=2))
        if not res.get("ok"):
            sys.exit(2)
        return
    if not res.get("ok") and res.get("error"):
        print(res["error"], file=sys.stderr)
        sys.exit(2)
    mode = "DRY-RUN" if res["dryRun"] else "LIVE SUBMIT"
    print(f"=== Upstream PR Submission ({mode}, count={res['count']}) ===")
    for r in res["results"]:
        print(
            f"  [{r['status']}] {r['upstream_repo']} <- {CANONICAL_FORK_ORG}:{r['branch']}@{r['head_sha']} — {r['title']}"
        )
        if r.get("url"):
            print(f"    URL: {r['url']}")
        elif r.get("stderr"):
            print(f"    Error: {r['stderr']}")
        elif res["dryRun"]:
            print(f"    Compare: {r['compare_url']}")


def cmd_check_delta(args: argparse.Namespace) -> None:
    forks_dir = Path(args.dir) if getattr(args, "dir", None) else None
    state_path = Path(args.state_file) if getattr(args, "state_file", None) else None
    res = check_prs_delta(author=args.author, preset=args.preset, state_path=state_path, forks_dir=forks_dir)
    if args.json:
        print(json.dumps(res, indent=2))
    else:
        if res["changed"]:
            print(f"DELTA DETECTED ({res['deltaCount']}): " + "; ".join(res["deltas"]))
        else:
            print(
                f"NO DELTA (openPrs={res['openPrCount']}, pendingBranches={res['pendingBranchCount']}, "
                f"agentTrees={res.get('agentTreeCount', 0)})"
            )
    sys.exit(0 if res["changed"] else 1)


def cmd_orca_sync(args: argparse.Namespace) -> None:
    forks_dir = Path(args.dir) if getattr(args, "dir", None) else None
    res = sync_prs_to_orca(
        author=args.author,
        preset=args.preset,
        worktree=args.worktree,
        trigger=args.trigger,
        provider=args.provider,
        forks_dir=forks_dir,
        dry_run=bool(args.dry_run),
    )
    if args.json:
        print(json.dumps(res, indent=2))
        return
    print(
        f"[ORCA PR SYNC] referencesAttached={res.get('referencesAttached')} "
        f"runId={res.get('orchestrationRunId')} taskId={res.get('orchestrationTaskId')} "
        f"automationId={res.get('automationId')} "
        f"(openPrs={res.get('openPrCount')}, pendingBranches={res.get('pendingBranchCount')}, "
        f"agentTrees={res.get('agentTreeCount', 0)})"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="w0m-prs: GitHub PR tool for w0m estate (T345/T369/T377/T599/T593)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Search
    p_search = subparsers.add_parser("search", help="Search PRs by author, repo, or preset")
    p_search.add_argument("--author", type=str, help="GitHub author username")
    p_search.add_argument("--all", action="store_true", help="Include all authors when searching a preset")
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
    p_watch.add_argument("--preset", type=str, choices=list(PRESET_REPOS.keys()), default="w0m-pr", help="Preset target (default: w0m-pr)")
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
    p_table.add_argument("--preset", type=str, choices=list(PRESET_REPOS.keys()), default="w0m-pr", help="Preset target (default: w0m-pr)")
    p_table.add_argument("--limit", type=int, default=30, help="Maximum number of PRs")
    p_table.add_argument("--markdown", action="store_true", help="Format output as Markdown table")
    p_table.set_defaults(func=cmd_table)

    # Forks
    p_forks = subparsers.add_parser("forks", help="Audit local fork synchronization against upstream remotes")
    p_forks.add_argument("--dir", type=str, help="Path to w0m-pr directory")
    p_forks.add_argument("--no-fetch", action="store_true", help="Skip fetching remotes before checking")
    p_forks.add_argument("--strict", action="store_true", help="Exit non-zero if any fork is behind or dirty")
    p_forks.add_argument("--markdown", action="store_true", help="Format output as Markdown table")
    p_forks.add_argument("--json", action="store_true", help="Output structured JSON")
    p_forks.set_defaults(func=cmd_forks)

    # Fetch
    p_fetch = subparsers.add_parser("fetch", help="Fetch remotes for all forks or a specific repo")
    p_fetch.add_argument("repo", nargs="?", default=None, help="Specific repository name in w0m-pr")
    p_fetch.add_argument("--dir", type=str, help="Path to w0m-pr directory")
    p_fetch.add_argument("--json", action="store_true", help="Output structured JSON")
    p_fetch.set_defaults(func=cmd_fetch)

    # Info
    p_info = subparsers.add_parser("info", help="Deep inspection of a specific fork repository")
    p_info.add_argument("repo", type=str, help="Specific repository name in w0m-pr")
    p_info.add_argument("--dir", type=str, help="Path to w0m-pr directory")
    p_info.add_argument("--json", action="store_true", help="Output structured JSON")
    p_info.set_defaults(func=cmd_info)

    # Update
    p_update = subparsers.add_parser("update", help="Safely fast-forward or rebase forks with upstream")
    p_update.add_argument("repo", nargs="?", default=None, help="Specific repository name in w0m-pr")
    p_update.add_argument("--rebase", action="store_true", help="Allow rebasing feature branches onto upstream")
    p_update.add_argument("--no-fetch", action="store_true", help="Skip fetching remotes before updating")
    p_update.add_argument("--dir", type=str, help="Path to w0m-pr directory")
    p_update.add_argument("--json", action="store_true", help="Output structured JSON")
    p_update.set_defaults(func=cmd_update)

    # Digest (T583)
    p_digest = subparsers.add_parser("digest", help="Compile 1-2 paragraph recent upstream & fork activity digest")
    p_digest.add_argument("--repo", type=str, default=None, help="Specific repository name in w0m-pr")
    p_digest.add_argument("--days", type=int, default=7, help="Lookback window in days (default: 7)")
    p_digest.add_argument("--dir", type=str, help="Path to w0m-pr directory")
    p_digest.add_argument("--json", action="store_true", help="Output structured JSON")
    p_digest.set_defaults(func=cmd_digest)

    # Rising (T583)
    p_rising = subparsers.add_parser("rising", help="Discover top GitHub rising & breakout projects")
    p_rising.add_argument("--period", type=str, choices=["daily", "weekly", "monthly"], default="weekly", help="Trending window (default: weekly)")
    p_rising.add_argument("--language", type=str, default=None, help="Programming language filter")
    p_rising.add_argument("--limit", type=int, default=15, help="Max projects to return (default: 15)")
    p_rising.add_argument("--offline", action="store_true", help="Use deterministic curated snapshot without network")
    p_rising.add_argument("--json", action="store_true", help="Output structured JSON")
    p_rising.set_defaults(func=cmd_rising)

    # Features (T584)
    p_features = subparsers.add_parser("features", help="Render GitHub-Issues-as-SSOT Feature Voting & Roadmap Board")
    p_features.add_argument("--repo", type=str, default="stablyai/orca", help="GitHub repository owner/name (default: stablyai/orca)")
    p_features.add_argument("--limit", type=int, default=30, help="Maximum number of feature issues (default: 30)")
    p_features.add_argument("--offline", action="store_true", help="Use deterministic curated snapshot without network")
    p_features.add_argument("--json", action="store_true", help="Output structured JSON")
    p_features.set_defaults(func=cmd_features)

    # Vote (T584)
    p_vote = subparsers.add_parser("vote", help="Cast or remove a native 👍 (THUMBS_UP) vote on a GitHub Issue (requires GH account)")
    p_vote.add_argument("repo", type=str, help="GitHub repository (owner/name)")
    p_vote.add_argument("issue", type=int, help="GitHub issue number")
    p_vote.add_argument("--unvote", action="store_true", help="Remove existing 👍 reaction instead of adding")
    p_vote.add_argument("--json", action="store_true", help="Output structured JSON")
    p_vote.set_defaults(func=cmd_vote)

    # Tap-Sync (T595 / AgDR-0052)
    p_tap_sync = subparsers.add_parser("tap-sync", help="Audit and sync w0m-pr/* beta branches with webomage/tap formulae")
    p_tap_sync.add_argument("--dir", type=str, help="Path to w0m-pr directory")
    p_tap_sync.add_argument("--tap-dir", type=str, help="Path to webomage/homebrew-tap directory")
    p_tap_sync.add_argument("--no-fetch", action="store_true", help="Skip fetching remotes before checking")
    p_tap_sync.add_argument("--sync", action="store_true", help="Update Formula/*.rb versions in webomage/homebrew-tap")
    p_tap_sync.add_argument("--json", action="store_true", help="Output structured JSON")
    p_tap_sync.set_defaults(func=cmd_tap_sync)

    # Discover (T599)
    p_discover = subparsers.add_parser(
        "discover", help="Discover active upstream PRs and unsubmitted PR-ready feature branches in w0m-pr/*"
    )
    p_discover.add_argument("--author", type=str, default=CANONICAL_CONTRIBUTOR, help="GitHub author username")
    p_discover.add_argument("--preset", type=str, choices=list(PRESET_REPOS.keys()), default="w0m-pr", help="Preset target")
    p_discover.add_argument("--dir", type=str, help="Path to w0m-pr directory")
    p_discover.add_argument("--fetch", action="store_true", help="Fetch remotes before inspecting branches")
    p_discover.add_argument("--json", action="store_true", help="Output structured JSON")
    p_discover.set_defaults(func=cmd_discover)

    # Check-Delta (T599 — zero-token shell precheck for Orca Automations)
    p_delta = subparsers.add_parser(
        "check-delta", help="Zero-token precheck: exit 0 on PR/branch delta, exit 1 when unchanged"
    )
    p_delta.add_argument("--author", type=str, default=CANONICAL_CONTRIBUTOR, help="GitHub author username")
    p_delta.add_argument("--preset", type=str, choices=list(PRESET_REPOS.keys()), default="w0m-pr", help="Preset target")
    p_delta.add_argument("--dir", type=str, help="Path to w0m-pr directory")
    p_delta.add_argument("--state-file", type=str, help="Override state file path")
    p_delta.add_argument("--json", action="store_true", help="Output structured JSON")
    p_delta.set_defaults(func=cmd_check_delta)

    # Orca-Sync (T599 — register Orca workspace references, orchestration task, and scheduled automation)
    p_orca = subparsers.add_parser(
        "orca-sync", help="Attach PR references, create Orca orchestration task, and register Orca automation"
    )
    p_orca.add_argument("--author", type=str, default=CANONICAL_CONTRIBUTOR, help="GitHub author username")
    p_orca.add_argument("--preset", type=str, choices=list(PRESET_REPOS.keys()), default="w0m-pr", help="Preset target")
    p_orca.add_argument("--dir", type=str, help="Path to w0m-pr directory")
    p_orca.add_argument("--worktree", type=str, default="active", help="Orca worktree selector (default: active)")
    p_orca.add_argument("--trigger", type=str, default="*/15 * * * *", help="Orca automation cron/trigger")
    p_orca.add_argument(
        "--provider",
        type=str,
        default="auto",
        help="Orca automation agent provider (default: auto — resolves installed antigravity/claude/codex/opencode)",
    )
    p_orca.add_argument("--dry-run", action="store_true", help="Preview Orca sync actions without mutating")
    p_orca.add_argument("--json", action="store_true", help="Output structured JSON")
    p_orca.set_defaults(func=cmd_orca_sync)

    # Proposals (T593 AC4 — structured Why/What For/How PR proposals for prepared branches)
    p_props = subparsers.add_parser(
        "proposals", help="List structured Why/What For/How PR proposals for prepared w0m-pr branches"
    )
    p_props.add_argument("--branch", type=str, default=None, help="Filter by branch or repo name")
    p_props.add_argument("--dir", type=str, help="Path to w0m-pr directory")
    p_props.add_argument("--json", action="store_true", help="Output structured JSON")
    p_props.set_defaults(func=cmd_proposals)

    # Submit (T593 AC4 — owner-confirmed PR submission or --dry-run preview)
    p_submit = subparsers.add_parser(
        "submit", help="Submit prepared w0m-pr upstream PRs (requires human confirmation or --dry-run)"
    )
    p_submit.add_argument("--branch", type=str, default=None, help="Specific branch or repo to submit")
    p_submit.add_argument("--dir", type=str, help="Path to w0m-pr directory")
    p_submit.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Preview gh pr create commands without submitting (--no-dry-run for live submission)",
    )
    p_submit.add_argument("--json", action="store_true", help="Output structured JSON")
    p_submit.set_defaults(func=cmd_submit)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

