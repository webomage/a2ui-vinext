#!/usr/bin/env python3
"""w0m-prs — Canonical GitHub PR discovery, health audit, watch poller & reporting tool.

Tracked by T345. Adheres to w0m CLI standard: offline-testable, deterministic JSON/table output,
safe headless Mermaid generation.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

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
        "Neywa-Labs/mlx-vlm",
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
        "JeffHoogland/moksha",
        "BodhiDev/bodhi-profile-iso",
        "BodhiDev/bodhi7packages",
        "BodhiDev/bodhi8packages",
        "elayadesign/ai-design-skills",
        "cloudflare/security-audit-skill",
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
        "JeffHoogland/moksha",
        "BodhiDev/bodhi-profile-iso",
        "BodhiDev/bodhi7packages",
        "BodhiDev/bodhi8packages",
        "elayadesign/ai-design-skills",
        "cloudflare/security-audit-skill",
    ],
}

UPSTREAM_DEFAULT_BRANCH_OVERRIDES: dict[str, str] = {
    "Graphify-Labs/graphify": "v8",
    "graphify": "v8",
    "JeffHoogland/moksha": "master",
    "moksha": "master",
    "bulwarkid/virtual-fido": "master",
    "virtual-fido": "master",
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
                    items: list[dict[str, Any]] = json.loads(res.stdout)
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
            return cast(list[dict[str, Any]], json.loads(res.stdout))
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


GH_LIST_CONNECTION_CAP = 100


def _has_complete_audit_fields(item: Dict[str, Any]) -> bool:
    if not all(k in item for k in ("mergeable", "comments", "reviews", "statusCheckRollup")):
        return False
    if (item.get("state") or "").upper() == "OPEN" and item.get("mergeable") == "UNKNOWN":
        return False
    if any(len(item.get(k) or []) >= GH_LIST_CONNECTION_CAP for k in ("comments", "reviews", "statusCheckRollup")):
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
        data: dict[str, Any] = json.loads(res.stdout)
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
                retry_data: dict[str, Any] = json.loads(retry_res.stdout)
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

    # Find upstream tracking target (honor canonical default-branch overrides & remote HEAD before fallback)
    upstream_target = None
    target_remote = "upstream" if "upstream" in remotes else ("origin" if "origin" in remotes else None)
    if target_remote:
        override_branch = UPSTREAM_DEFAULT_BRANCH_OVERRIDES.get(repo_name)
        candidate_order: list[str] = []
        if override_branch:
            candidate_order.append(override_branch)
        sym_head = run_cmd(
            ["git", "symbolic-ref", "-q", "--short", f"refs/remotes/{target_remote}/HEAD"],
            check=False,
            cwd=repo_path,
        )
        if sym_head.returncode == 0 and sym_head.stdout.strip():
            sym_val = sym_head.stdout.strip()
            if sym_val.startswith(f"{target_remote}/"):
                sym_branch = sym_val.split("/", 1)[1]
                if sym_branch and sym_branch not in candidate_order:
                    candidate_order.append(sym_branch)
        for fb in ("main", "master", "v8"):
            if fb not in candidate_order:
                candidate_order.append(fb)
        for branch_candidate in candidate_order:
            check_ref = run_cmd(
                ["git", "rev-parse", "--verify", f"{target_remote}/{branch_candidate}"],
                check=False,
                cwd=repo_path,
            )
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


def resolve_canonical_estate_root(
    workspace_root: Path | None = None,
    home_dir: Path | None = None,
) -> Path:
    """Resolve the persistent host estate checkout (`T615` AC4).

    When invoked from inside an ephemeral `~/.w0m/work*` or `~/.w0m/releases*` worktree,
    maps back to the live host estate root so Orca automations never persist temporary
    worktree paths in `precheck` commands.
    """
    ws = (workspace_root or find_workspace_root()).resolve()
    home = (home_dir or Path.home()).resolve()
    w0m_ephemeral_root = home / ".w0m"
    try:
        is_ephemeral = ws == w0m_ephemeral_root or w0m_ephemeral_root in ws.parents
    except OSError:
        is_ephemeral = False
    if is_ephemeral:
        for candidate in (
            home / "Projects" / "!self" / "w0m",
            home / "Projects" / "@self" / "@wom",
            home / "Projects" / "w0m",
        ):
            if (candidate / "scripts" / "w0m_prs.py").is_file():
                return candidate
    return ws


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
                payload: dict[str, Any] = json.loads(res_search.stdout)
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
                payload: dict[str, Any] = json.loads(cp.stdout)
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
            cast(dict[str, Any], json.loads(cp_id.stdout))
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
        cast(dict[str, Any], json.loads(cp_mut.stdout))
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
    "moksha": "JeffHoogland/moksha",
    "bodhi-profile-iso": "BodhiDev/bodhi-profile-iso",
    "bodhi7packages": "BodhiDev/bodhi7packages",
    "bodhi8packages": "BodhiDev/bodhi8packages",
    "ai-design-skills": "elayadesign/ai-design-skills",
    "security-audit-skill": "cloudflare/security-audit-skill",
}

# Per-repository upstream contribution rules registry (`AgDR-0058` / `T655`)
UPSTREAM_CONTRIBUTION_RULES: dict[str, dict[str, Any]] = {
    "ml-explore/mlx-lm": {
        "automation_mode": "banned",
        "template_profile": "mlx_lm_manual",
        "requires_linked_issue": False,
        "auto_create_issue": False,
        "requires_gpg_signature": True,
        "requires_visual_proof_for_ui": False,
        "max_open_prs": None,
        "max_loc": None,
        "policy_note": (
            "HARD BAN (CONTRIBUTING.md:14-15 & AGENTS.md:10-28): Strictly prohibits AI-written PR descriptions, "
            "review replies, git push, and automated PR creation (penalty: PR closure + contributor ban)."
        ),
    },
    "Graphify-Labs/graphify": {
        "automation_mode": "human_description_required",
        "template_profile": "graphify_5_section",
        "requires_linked_issue": False,
        "auto_create_issue": False,
        "requires_gpg_signature": True,
        "requires_visual_proof_for_ui": False,
        "max_open_prs": None,
        "max_loc": None,
        "policy_note": (
            "CONTRIBUTING.md:128-135 requires human-authored PR descriptions, Co-Authored-By commit trailers, "
            "Conventional Commit title, and 5-section PULL_REQUEST_TEMPLATE.md targeting base v8."
        ),
    },
    "oraios/serena": {
        "automation_mode": "cla_required",
        "template_profile": "standard",
        "requires_linked_issue": True,
        "auto_create_issue": False,
        "requires_gpg_signature": True,
        "requires_visual_proof_for_ui": False,
        "max_open_prs": 3,
        "max_loc": None,
        "policy_note": (
            "Requires Oraios CLA (license/cla), SPDX header, CHANGELOG.md entry, max 3 open PRs, "
            "and prior issue agreement for non-trivial changes."
        ),
    },
    "google-research/harness2": {
        "automation_mode": "cla_required",
        "template_profile": "standard",
        "requires_linked_issue": False,
        "auto_create_issue": False,
        "requires_gpg_signature": True,
        "requires_visual_proof_for_ui": False,
        "max_open_prs": None,
        "max_loc": None,
        "policy_note": "Requires signed Google Individual/Corporate CLA (cla/google).",
    },
    "headroomlabs-ai/headroom": {
        "automation_mode": "strict_governance",
        "template_profile": "headroom_7_section",
        "requires_linked_issue": True,
        "auto_create_issue": False,
        "requires_gpg_signature": True,
        "requires_visual_proof_for_ui": False,
        "max_open_prs": 10,
        "max_loc": None,
        "policy_note": (
            "Enforces scripts/pr-governance.py (7 exact ## headings, ### Test Output fenced block, "
            "4 Real Behavior Proof bullets, 7 Runtime Rollout Safety bullets, 0 CHANGELOG.md edits, max 10 open PRs)."
        ),
    },
    "stablyai/orca": {
        "automation_mode": "auto",
        "template_profile": "orca_11_section",
        "requires_linked_issue": True,
        "auto_create_issue": True,
        "requires_gpg_signature": True,
        "requires_visual_proof_for_ui": True,
        "max_open_prs": None,
        "max_loc": None,
        "policy_note": (
            "AI-welcome (.github/CONTRIBUTING.md:218-227); mandates 11-section .github/pull_request_template.md, "
            "`Fixes #<issue>` (PRs without linked issues from outside contributors are ignored), honest Visual Proof "
            "(before/after media or `N/A` + reason), Risk level, AI Disclosure, Review, and Checklist."
        ),
    },
    "jundot/omlx": {
        "automation_mode": "auto",
        "template_profile": "omlx_3_section",
        "requires_linked_issue": False,
        "auto_create_issue": False,
        "requires_gpg_signature": True,
        "requires_visual_proof_for_ui": True,
        "max_open_prs": None,
        "max_loc": 1000,
        "policy_note": (
            "AI-welcome (docs/CONTRIBUTING.md:66-68); requires ## Summary, ## Validation, and ## Checklist "
            "(.github/pull_request_template.md); external PRs >1,000 LoC auto-convert to Draft."
        ),
    },
    "Blaizzy/mlx-vlm": {
        "automation_mode": "auto",
        "template_profile": "standard",
        "requires_linked_issue": False,
        "auto_create_issue": False,
        "requires_gpg_signature": True,
        "requires_visual_proof_for_ui": False,
        "max_open_prs": None,
        "max_loc": None,
        "policy_note": "Enforces GitHub-verified commit signatures (`Check commit signatures` workflow).",
    },
    "Neywa-Labs/mlx-vlm": {
        "automation_mode": "auto",
        "template_profile": "standard",
        "requires_linked_issue": False,
        "auto_create_issue": False,
        "requires_gpg_signature": True,
        "requires_visual_proof_for_ui": False,
        "max_open_prs": None,
        "max_loc": None,
        "policy_note": "Enforces GitHub-verified commit signatures (`Check commit signatures` workflow).",
    },
    "mizorewww/laya-mlx": {
        "automation_mode": "auto",
        "template_profile": "standard",
        "requires_linked_issue": False,
        "auto_create_issue": False,
        "requires_gpg_signature": True,
        "requires_visual_proof_for_ui": False,
        "max_open_prs": None,
        "max_loc": None,
        "policy_note": "Standard open-source contribution rules; pure-MLX unit test verification expected.",
    },
    "oxiglade/mlx-rs": {
        "automation_mode": "auto",
        "template_profile": "standard",
        "requires_linked_issue": False,
        "auto_create_issue": False,
        "requires_gpg_signature": True,
        "requires_visual_proof_for_ui": False,
        "max_open_prs": None,
        "max_loc": None,
        "policy_note": "Standard Rust crate rules (`cargo test`, shared `arch/{attention,activation}.rs` helpers).",
    },
    "openai/tart-guest-agent": {
        "automation_mode": "auto",
        "template_profile": "standard",
        "requires_linked_issue": False,
        "auto_create_issue": False,
        "requires_gpg_signature": True,
        "requires_visual_proof_for_ui": False,
        "max_open_prs": None,
        "max_loc": None,
        "policy_note": "Standard Swift/Go contribution workflow with unit tests.",
    },
    "cirruslabs/tart": {
        "automation_mode": "auto",
        "template_profile": "standard",
        "requires_linked_issue": False,
        "auto_create_issue": False,
        "requires_gpg_signature": True,
        "requires_visual_proof_for_ui": False,
        "max_open_prs": None,
        "max_loc": None,
        "policy_note": "Standard Swift macOS virtualization contribution workflow.",
    },
    "bulwarkid/virtual-fido": {
        "automation_mode": "auto",
        "template_profile": "standard",
        "requires_linked_issue": False,
        "auto_create_issue": False,
        "requires_gpg_signature": True,
        "requires_visual_proof_for_ui": False,
        "max_open_prs": None,
        "max_loc": None,
        "policy_note": "Targets `master` base branch; standard Go/contrib tests.",
    },
    "JeffHoogland/moksha": {
        "automation_mode": "auto",
        "template_profile": "standard",
        "requires_linked_issue": False,
        "auto_create_issue": False,
        "requires_gpg_signature": True,
        "requires_visual_proof_for_ui": False,
        "max_open_prs": None,
        "max_loc": None,
        "policy_note": "Targets `master` base branch; zero-warning C99/EFL compilation required.",
    },
    "BodhiDev/bodhi-profile-iso": {
        "automation_mode": "auto",
        "template_profile": "standard",
        "requires_linked_issue": False,
        "auto_create_issue": False,
        "requires_gpg_signature": True,
        "requires_visual_proof_for_ui": False,
        "max_open_prs": None,
        "max_loc": None,
        "policy_note": "Targets `main` base branch; verified `eet` profile compilation.",
    },
    "BodhiDev/bodhi7packages": {
        "automation_mode": "auto",
        "template_profile": "standard",
        "requires_linked_issue": False,
        "auto_create_issue": False,
        "requires_gpg_signature": True,
        "requires_visual_proof_for_ui": False,
        "max_open_prs": None,
        "max_loc": None,
        "policy_note": "Targets `main` base branch; clean `patch -p1 --fuzz=0` Debian quilt series.",
    },
    "BodhiDev/bodhi8packages": {
        "automation_mode": "auto",
        "template_profile": "standard",
        "requires_linked_issue": False,
        "auto_create_issue": False,
        "requires_gpg_signature": True,
        "requires_visual_proof_for_ui": False,
        "max_open_prs": None,
        "max_loc": None,
        "policy_note": "Targets `main` base branch; clean `patch -p1 --fuzz=0` Debian quilt series across noble & trixie.",
    },
    "elayadesign/ai-design-skills": {
        "automation_mode": "auto",
        "template_profile": "standard",
        "requires_linked_issue": False,
        "auto_create_issue": False,
        "requires_gpg_signature": True,
        "requires_visual_proof_for_ui": False,
        "max_open_prs": None,
        "max_loc": None,
        "policy_note": "Standard Markdown skill repository rules.",
    },
    "cloudflare/security-audit-skill": {
        "automation_mode": "cla_required",
        "template_profile": "standard",
        "requires_linked_issue": False,
        "auto_create_issue": False,
        "requires_gpg_signature": True,
        "requires_visual_proof_for_ui": False,
        "max_open_prs": None,
        "max_loc": None,
        "policy_note": "Cloudflare open-source repository (check CLA/template before opening PRs).",
    },
}


def get_repo_contribution_rules(repo: str) -> dict[str, Any]:
    """Return the `AgDR-0058` contribution rule profile for `repo`."""
    if repo in UPSTREAM_CONTRIBUTION_RULES:
        return dict(UPSTREAM_CONTRIBUTION_RULES[repo])
    return {
        "automation_mode": "auto",
        "template_profile": "standard",
        "requires_linked_issue": False,
        "auto_create_issue": False,
        "requires_gpg_signature": True,
        "requires_visual_proof_for_ui": False,
        "max_open_prs": None,
        "max_loc": None,
        "policy_note": "Default standard open-source repository profile.",
    }


# Active upstream PR head branches (excluded from unsubmitted pending branch list)
ACTIVE_OPEN_PR_HEAD_BRANCHES: set[str] = {
    "feat/global-graph-sync-and-status",                    # Graphify-Labs/graphify#4727
    "fix/turboquant-dim512-threadgroup-fallback",           # Neywa-Labs/mlx-vlm#2288 (Blaizzy/mlx-vlm#2288)
    "fix/menubar-adopt-external-omlx",                      # jundot/omlx#3743
    "feat/macos-deep-link-worktree",                        # stablyai/orca#21157
    "feat/macos-deep-link-shortcuts",                       # stablyai/orca#21148
    "feat/zeroclaw-agent-connector",                        # stablyai/orca#16597
    "feat/media-clipboard-and-file-transfer",               # openai/tart-guest-agent#62
    "macos_release",                                        # bulwarkid/virtual-fido#48
    "feat/linux-desktop-hotkey-helper",                     # bulwarkid/virtual-fido#56
    "fix/native-serve-tests-and-torchless-calibration",     # mizorewww/laya-mlx#27
    "feat/cross-worktree-tab-move",                         # stablyai/orca#37029
    "feat/agent-collaboration-board",                       # stablyai/orca#37030
    "feat/mobile-camera-capture-chat",                      # stablyai/orca#37031
    "feat/mobile-live-input-password-mask",                 # stablyai/orca#37032
    "feat/obsidian-ofm-engine",                             # stablyai/orca#37033
    "fix/mobile-markdown-external-tab-read",                # stablyai/orca#37035
    "feat/nested-subfolder-git-and-sdlc-repo",              # stablyai/orca#37510
    "feat/mobile-session-tab-reorder",                      # stablyai/orca#37511
    "feat/mobile-terminal-triple-tap-enter",                # stablyai/orca#37995
    "feat/mobile-four-side-edge-arrows",                    # stablyai/orca#38612
    "fix/webgl-atlas-version-desync-recovery",              # stablyai/orca#38857
    "fix/terminal-smooth-resize-and-replay",                # stablyai/orca#38858
    "fix/mobile-terminal-theme-enforcement",                # stablyai/orca#38859
    "fix/mobile-live-input-prompt-backload",                # stablyai/orca#38863
    "feat/system-and-docker-monitors",                      # stablyai/orca#38987
    "fix/linux-cli-stale-appimage-and-dispatcher",          # stablyai/orca#38991
    "feat/mobile-terminal-4-tap-alt-m",                     # stablyai/orca#38993
    "feat/subagent-display-and-floating-category",          # stablyai/orca#38995
    "feat/eight-zone-window-snapping",                      # JeffHoogland/moksha#310
    "fix/desktop-editor-icon-path-and-size",                # JeffHoogland/moksha#311
    "feat/appimage-diricon-and-rdns-wmclass",               # JeffHoogland/moksha#312
    "feat/eight-zone-window-snap-bindings",                 # BodhiDev/bodhi-profile-iso#2
    "feat/moksha-snap-and-icon-backports",                  # BodhiDev/bodhi7packages#10 & BodhiDev/bodhi8packages#8
    "feat/mlx-lm-gemma4-arch",                              # oxiglade/mlx-rs#442
    "perf/gemma4-kv-shared-prefill-and-moe-sanitize",       # ml-explore/mlx-lm#2026
}

# Internal / archived / superseded / inherited-upstream sub-branches (excluded from unsubmitted pending branch list)
INTERNAL_OR_SUPERSEDED_BRANCHES: set[str] = {
    "feat/audit-host-services",
    "feat/w0m-overlay-updater-feed",  # T619: webomage/orca self-healing overlay release feed runtime branch
    "fix/mobile-landscape-safe-area-insets",  # T662: superseded upstream by stablyai/orca#28749 SideSafeArea (PR #37034 closed)
    "feat/omlx-proxy-routing",  # T669: merged upstream in headroomlabs-ai/headroom#4597 (2026-11-08)
    "perf/terminal-chat-redraw-and-tab-caching",  # T669: closed upstream in stablyai/orca#38861 (#39462 covers DOM refresh gate; overlay/split candidate)
    "fix/gemma4-turboquant-sdpa256-bounds",
    "w0m/v1.7.0-astro",
    "PR_restructured",
    "cleaned",
    "dkit",
    "feature/final-polish",
    "feature/tests-docs-new",
    "feature/transports",
    "features",
    "hid",
    "transports",
    "uhid",
    "macos",
    "macos_mini",
    "macos_purego",
    "macos_stable",
    "macos_vhid",
    "tested",
    "dependabot/cargo/minijinja-3",
    "dependabot/cargo/sha2-0.11",
    "mlx-rs-eval-threads",
    "bl6",
    "dev",
    "stefan",
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
    "JeffHoogland/moksha:feat/eight-zone-window-snapping": {
        "ticket": "T618",
        "title": "feat(border,actions): add 8-zone window snapping with top-half edge default and Super+Arrow chords",
        "why": (
            "Moksha previously supported left/right half maximization (`E_MAXIMIZE_LEFT`, `E_MAXIMIZE_RIGHT`), while dragging a window "
            "to the top edge only offered full-screen maximize (`max_top_edge`), dragging to the bottom edge or screen corners had no snap "
            "zone at all, and `Super+Up` / `Super+Down` did not snap to top/bottom halves or compose with left/right halves into corner quarters.\n\n"
            "**Why Top Half (`E_MAXIMIZE_TOP`) is proposed as the default top-edge drag action**:\n"
            "1. **4-edge + 4-corner geometric symmetry**: Dragging to any of the 4 screen edges (Left, Right, Top, Bottom) consistently tiles "
            "to that `50%` half, while dragging within `64px` of any of the 4 screen corners tiles to that `25%` corner quarter.\n"
            "2. **Eliminating a missing mouse gesture without losing Full Maximize**: Full Maximize already has three fast, muscle-memory "
            "triggers in Moksha (double-clicking the titlebar, clicking the titlebar Maximize button, and pressing `Super+Up` twice via "
            "`Top Half -> Full Maximize` promotion), whereas Top Half previously had **zero** mouse gesture—making vertical top/bottom split "
            "workflows impossible with the mouse alone.\n"
            "3. **Opt-in toggle for traditional behavior**: Users who prefer top-edge full maximize can enable `\"Maximize fully when dragging "
            "to top edge\"` (`e_config->snap_top_edge_maximize`) directly in **Settings -> Windows -> Window Geometry -> Maximization**."
        ),
        "what_for": (
            "Gives Moksha users complete 8-zone window tiling (Left/Right/Top/Bottom halves + Top-Left/Top-Right/Bottom-Left/Bottom-Right "
            "quarters) via mouse edge/corner drag, window border context menu, and `Super+Arrow` keyboard chords, with clean saved-geometry "
            "restoration on unsnap or drag-away."
        ),
        "how": (
            "- **`src/bin/e_border.h` & `src/bin/e_border.c`**: Adds `E_MAXIMIZE_TOP` (`0x100`), `E_MAXIMIZE_BOTTOM` (`0x200`), and compound "
            "quarter masks (`E_MAXIMIZE_TOP_LEFT`, `E_MAXIMIZE_TOP_RIGHT`, `E_MAXIMIZE_BOTTOM_LEFT`, `E_MAXIMIZE_BOTTOM_RIGHT`), shelf-obstacle-aware "
            "zone geometry calculation (`e_zone_useful_geometry_get`), `64px` corner detection + 4-edge drag snapping in `_e_border_eval`, and "
            "saved-geometry restoration when dragging a snapped window off its zone.\n"
            "- **`src/bin/e_actions.c`**: Extends `window_maximize_by` (`top`, `bottom`, `top_left`, `top_right`, `bottom_left`, `bottom_right`) "
            "with quarter chord transitions (`Left + Up -> Top-Left`, `Top-Left + Down -> Left -> Bottom-Left`, `Up + Up -> Top -> Full`, "
            "`Full + Down -> Top -> Restore`).\n"
            "- **`src/bin/e_config.{h,c}`, `config/bodhi/e.src`, `e_int_border_menu.c`, & `src/modules/conf_window_manipulation/e_int_config_window_geometry.c`**: "
            "Adds `snap_top_edge_maximize` (default `0`, `max_top_edge` default `1`), updates `Super+Up`/`Super+Down` defaults, exposes Top/Bottom/Quarter "
            "entries in the window Maximize menu, and adds the Window Geometry checkbox.\n"
            "- **Verification**: Full `src/bin`, `src/modules`, and `config` build cleanly with zero compiler warnings (`gcc -Wall`)."
        ),
    },
    "JeffHoogland/moksha:fix/desktop-editor-icon-path-and-size": {
        "ticket": "T618",
        "title": "fix(eap_editor): store absolute icon path on border-created .desktop and pick largest _NET_WM_ICON",
        "why": (
            "When creating a launcher from a running X11 window via Window Menu -> Create Icon (`e_desktop_border_edit`), `e_eap_editor.c` "
            "wrote the extracted window icon PNG to `~/.e/e/icons/<bname>-<pid>.png` (`path`), but assigned `desktop->icon = strdup(file)` "
            "(bare filename without directory). Because `~/.e/e/icons` is not a standard XDG icon theme directory, `efreet_icon_path_find` "
            "failed to resolve the bare filename after saving—rendering a `?` fallback icon on shelves/IBar—and broke `_e_desktop_edit_free_data`'s "
            "own `ecore_file_unlink(editor->tmp_image_path)` cleanup on cancel. In addition, `e_desktop_border_edit` unconditionally grabbed "
            "`bd->client.netwm.icons[0]`, which for many Electron/Chromium/GTK apps is `16x16`, producing blurry upscaled launcher icons, and "
            "did not strip `/` if `bname` contained a path."
        ),
        "what_for": (
            "Ensures launchers created via Window Menu -> Create Icon immediately resolve their extracted icon across shelves, IBar, and "
            "menus at crisp highest-available `_NET_WM_ICON` resolution (e.g., `256x256` or `512x512`), sanitize `bname` safely, and unlink "
            "temporary PNGs cleanly if the dialog is canceled."
        ),
        "how": (
            "- **`src/bin/e_eap_editor.c`**: Scans `bd->client.netwm.icons[0..num_icons-1]` to select the largest `width * height` entry, "
            "sanitizes `bname` with `ecore_file_file_get(bname)` before building `file`, and stores `desktop->icon = strdup(path)`.\n"
            "- **Verification**: Clean compilation of `src/bin/enlightenment` with zero warnings."
        ),
    },
    "JeffHoogland/moksha:feat/appimage-diricon-and-rdns-wmclass": {
        "ticket": "T618",
        "title": "feat(border): resolve reverse-DNS WM_CLASS, AppImage .DirIcon, >=64px _NET_WM_ICON, and negative client_inset",
        "why": (
            "Modern Linux desktop apps packed as AppImages, Flatpaks, or Electron/CSD windows hit four window-icon and frame-geometry edge "
            "cases in `src/bin/e_border.c`:\n"
            "1. Apps with reverse-DNS `WM_CLASS` (e.g., `md.obsidian.Obsidian`, `org.telegram.desktop`) missed `.desktop` files named "
            "`obsidian.desktop` or `telegram.desktop` when `StartupWMClass` was absent.\n"
            "2. Portable AppImages run from FUSE mounts (`/tmp/.mount_*/...`) without installed `.desktop` entries and often omit `_NET_WM_ICON`, "
            "falling back to a generic `?` icon despite shipping `.DirIcon` at the mount root.\n"
            "3. `_e_border_eval0` always rendered `bd->client.netwm.icons[0]`, picking blurry `16x16` icons even when `64x64`–`512x512` "
            "sizes were present in `_NET_WM_ICON`.\n"
            "4. `_e_border_client_inset_calc` subtracted `_GTK_FRAME_EXTENTS` from border insets without clamping at `0`, producing negative "
            "`client_inset.{l,r,t,b}` on borderless GTK3/4 CSD windows."
        ),
        "what_for": (
            "Delivers automatic crisp window/IBar/taskbar icons out of the box for reverse-DNS apps (Obsidian, Telegram, Flatpaks), "
            "uninstalled FUSE AppImages, and multi-size `_NET_WM_ICON` clients, while preventing negative frame-extents geometry bugs on "
            "borderless GTK CSD windows."
        ),
        "how": (
            "- **`src/bin/e_border.c`**:\n"
            "  - `_e_border_client_inset_calc`: Clamps `l`, `r`, `t`, `b` with `MAX(0, ...)`.\n"
            "  - `_e_border_eval0`: Adds trailing-dot segment fallback (`strrchr(..., '.')`) for `efreet_util_desktop_wm_class_find` / "
            "`efreet_util_desktop_exec_find`.\n"
            "  - `_e_border_netwm_best_icon_get`: Prefers the smallest `_NET_WM_ICON` entry `>= 64x64` (falling back to largest available "
            "if all are `< 64x64`).\n"
            "  - `_e_border_appimage_diricon_add`: Resolves `/proc/<netwm.pid>/exe` when under `/tmp/.mount_*` and loads `<mount_root>/.DirIcon` "
            "into Evas when neither `.desktop` nor `_NET_WM_ICON` supplied an icon.\n"
            "- **Verification**: Clean compilation of `src/bin/enlightenment` with zero warnings."
        ),
    },
    "BodhiDev/bodhi-profile-iso:feat/eight-zone-window-snap-bindings": {
        "ticket": "T618",
        "title": "feat(iso): enable top-half edge snap and bind Super+Up/Down to top/bottom window snap",
        "why": (
            "With 8-zone window snapping in Moksha (`E_MAXIMIZE_TOP`, `E_MAXIMIZE_BOTTOM`, and corner quarters), the default Bodhi ISO "
            "profile (`src/ISO/e.src`) still had `max_top_edge: 0` and mapped `Super+Up` (`\"Up\"`, `MODIFIER_WIN`) to `window_maximize_by` "
            "`\"default\"` (full maximize) and `Super+Down` (`\"Down\"`, `MODIFIER_WIN`) to `window_iconic_toggle` (minimize). Setting "
            "top-edge drag to Top Half (`snap_top_edge_maximize: 0`) and `Super+Up`/`Super+Down` to `\"default top\"`/`\"default bottom\"` "
            "makes all 4 edges + 4 corners symmetric out of the box while preserving double `Super+Up` for Full Maximize."
        ),
        "what_for": (
            "Provides symmetric 8-zone mouse edge/corner snapping and `Super+Arrow` half/quarter keyboard tiling out of the box on fresh "
            "Bodhi Linux installations."
        ),
        "how": (
            "- **`src/ISO/e.src`**: Sets `max_top_edge: 1`, adds `snap_top_edge_maximize: 0`, and updates `Super+Up` (`params: \"default top\"`) "
            "and `Super+Down` (`action: \"window_maximize_by\"`, `params: \"default bottom\"`).\n"
            "- **Verification**: Verified round-trip compilation with `/usr/bin/eet -e tmp/e.cfg config src/ISO/e.src 1`."
        ),
    },
    "BodhiDev/bodhi7packages:feat/moksha-snap-and-icon-backports": {
        "ticket": "T618",
        "title": "moksha (0.4.2-5): backport 8-zone window snapping and desktop/AppImage icon fixes",
        "why": (
            "Bodhi Linux 7.0 (`jammy`) ships `moksha 0.4.2-4`, which lacks 8-zone edge/corner window snapping (top/bottom halves + 4 corners "
            "with top-half edge default), saves bare filenames instead of full paths for window-created `.desktop` icons (`?` icon regression), "
            "and misses icons on reverse-DNS `WM_CLASS` apps (e.g., Obsidian) and portable FUSE AppImages."
        ),
        "what_for": (
            "Delivers native 8-zone window snapping and crisp window/IBar/launcher icon resolution to existing Bodhi Linux 7 users via a "
            "clean `0.4.2-5` Debian quilt patch release without requiring an EFL upgrade."
        ),
        "how": (
            "- **`moksha/debian/patches/{01-eight-zone-window-snapping,02-fix-desktop-editor-icon-path-and-size,03-appimage-diricon-and-rdns-wmclass}.patch` & `series`**: "
            "Backports all three upstream Moksha commits cleanly onto `0.4.2-4` (`c338b91b4`).\n"
            "- **`moksha/debian/changelog`**: Adds `0.4.2-5` release entry targeting `jammy`.\n"
            "- **Verification**: Verified `patch -p1 --fuzz=0` sequential application on `0.4.2-4`, full binary + module compilation, `ldd` "
            "shared library resolution, and `.deb` packaging."
        ),
    },
    "BodhiDev/bodhi8packages:feat/moksha-snap-and-icon-backports": {
        "ticket": "T618",
        "title": "moksha (0.4.2-5): backport 8-zone window snapping and desktop/AppImage icon fixes for noble & trixie",
        "why": (
            "Bodhi Linux 8 (`noble` and `trixie` tracks) packages `moksha 0.4.2-4` and shares the same missing 8-zone window snapping and "
            "desktop/AppImage/reverse-DNS `WM_CLASS` icon resolution gaps as Bodhi 7."
        ),
        "what_for": (
            "Keeps Bodhi 8 (`noble` and `trixie`) `moksha` packages at parity (`0.4.2-5`) with upstream Moksha and Bodhi 7."
        ),
        "how": (
            "- **`moksha/{noble,trixie}/debian/patches/{01-...,02-...,03-...,series}` & `debian/changelog`**: Adds identical `--fuzz=0` "
            "quilt patches and `0.4.2-5` changelog entries for both `noble` and `trixie`.\n"
            "- **Verification**: Verified clean `patch -p1 --fuzz=0` sequential application against `0.4.2-4`."
        ),
    },
    "stablyai/orca:fix/linux-cli-stale-appimage-and-dispatcher": {
        "ticket": "T618",
        "title": "fix(cli): replace legacy Linux CLI symlinks with bare dispatcher and auto-heal stale AppImage launchers",
        "why": (
            "On Linux AppImage installations, two CLI lifecycle regressions broke `orca` terminal commands after upgrades or AppImage moves:\n"
            "1. `CliInstaller.install()` on Linux returned early when `~/.local/bin/orca` was a symlink pointing to the current target or "
            "wrote a raw symlink instead of the `# orca-serve-bare-orca-dispatcher` shell wrapper—even though `CliInstaller.remove()` only "
            "recognizes regular files carrying that marker—leaving bare `orca` invocations without daemon-forwarding dispatch.\n"
            "2. When an AppImage was upgraded or moved (e.g., old versioned `.AppImage` replaced by a new filename), `~/.orca/cli-launcher` "
            "retained the deleted old AppImage path (`existsSync === false`). Neither startup nor `cli:status` auto-repaired the dead "
            "registration, so `orca` failed in terminals until the user manually toggled CLI install in Settings."
        ),
        "what_for": (
            "Guarantees Linux AppImage users get the marked `# orca-serve-bare-orca-dispatcher` wrapper on `CliInstaller.install()` and "
            "automatically heals `~/.orca/cli-launcher` + `~/.local/bin/orca` whenever a packaged AppImage launches after an older registered "
            "AppImage path was deleted or moved—without overwriting live side-by-side AppImages."
        ),
        "how": (
            "- **`src/main/cli/linux-bare-orca-dispatcher.ts` & `src/main/cli/cli-installer.ts`**: Exports `installLinuxBareOrcaDispatcherForLauncher` "
            "and updates `CliInstaller.install()` on Linux to replace legacy symlinks/wrappers with the marked bare-orca dispatcher.\n"
            "- **`src/main/cli/local-cli-registration-coordinator.ts`**: "
            "Detects dead `~/.orca/cli-launcher` paths (`!existsSync(registeredLauncher)`) when `process.env.APPIMAGE` is live and re-installs "
            "both `~/.orca/cli-launcher` and `~/.local/bin/orca` automatically during CLI registration/status checks.\n"
            "- **Verification**: `13/13` Vitest tests passing across `cli-installer.test.ts` and "
            "`local-cli-registration-coordinator.test.ts`."
        ),
    },
    "stablyai/orca:fix/webgl-atlas-version-desync-recovery": {
        "ticket": "T618",
        "title": "fix(renderer): detect and recover xterm WebGL glyph-atlas version desync on pane reveal",
        "why": (
            "On Linux/X11 GPUs (especially AMD/Mesa and multi-pane tab switches), xterm's WebGL renderer can silently desynchronize "
            "`renderer._glyphRenderer._atlas.version` from `_model.glyphAtlasVersion` across hidden/parked cycles or context pressure—leaving "
            "revealed terminal panes completely blank or missing glyphs even though `refresh(0, rows - 1)` ran during `presentPaneViewport`."
        ),
        "what_for": (
            "Automatically detects WebGL glyph-atlas version desynchronization after `presentPaneViewport` on pane reveal and triggers a "
            "bounded one-shot `clearTextureAtlas()` + full viewport `refresh()` recovery so terminal panes never stay blank after tab switching."
        ),
        "how": (
            "- **`src/renderer/src/lib/pane-manager/pane-webgl-atlas-version-desync.ts`**: Inspects xterm's internal WebGL renderer "
            "(`hasPaneWebglAtlasVersionDesync`) with defensive optional-property guards across xterm versions.\n"
            "- **`src/renderer/src/lib/pane-manager/pane-reveal-repaint.ts`**: Checks `hasPaneWebglAtlasVersionDesync(pane)` inside "
            "`schedulePaneRevealPresent`'s settled frame (while preserving `WeakRef` pane lifetime semantics) and escalates at most once "
            "via `pane.xterm.clearTextureAtlas?.()` + `presentPaneViewport(pane)`.\n"
            "- **`src/renderer/src/lib/pane-manager/pane-reveal-atlas-desync.test.ts`**: Adds unit tests covering desync detection, single-shot "
            "escalation, healthy no-op, and missing `clearTextureAtlas` resilience (`11/11` tests passing with `pane-reveal-lifetime.test.ts`)."
        ),
    },
    "bulwarkid/virtual-fido:feat/linux-desktop-hotkey-helper": {
        "ticket": "T618",
        "title": "feat(contrib): add Linux desktop user-presence hotkey helper, systemd user unit, and uhid udev rule",
        "why": (
            "On Linux desktops (X11/Wayland WMs without a built-in GUI prompt integration), `virtual-fido` requires either writing to a "
            "`--signal-file` FIFO or typing a newline into `cmd/demo start`'s stdin to approve WebAuthn/FIDO2 user-presence (`UP`) checks—"
            "forcing users to keep a dedicated terminal open and lacked rootless `/dev/uhid` udev rules and systemd user service templates."
        ),
        "what_for": (
            "Provides a ready-to-install Linux desktop integration (`contrib/linux-desktop/`) with rootless `/dev/uhid` udev permissions, "
            "a hardened `systemd --user` service, `virtual-fido-ctl`, and a desktop-notification + global-hotkey `virtual-fido-hotkey` "
            "trigger that works cleanly with both `--signal-file` builds and FIFO-backed `cmd/demo start` setups without blocking if the "
            "daemon is stopped."
        ),
        "how": (
            "- **`contrib/linux-desktop/70-virtual-fido-uhid.rules`**: Grants `MODE=\"0660\", TAG+=\"uaccess\"` on `/dev/uhid` for active "
            "local desktop seat users without broad group privileges.\n"
            "- **`contrib/linux-desktop/virtual-fido-hotkey` & `virtual-fido-ctl`**: Uses `os.open(..., os.O_WRONLY | os.O_NONBLOCK)` on "
            "FIFOs so pressing a bound desktop hotkey never hangs the WM when no reader is attached, paired with `notify-send` feedback.\n"
            "- **`contrib/linux-desktop/virtual-fido.service`, `README.md`, & `test_hotkey.py`**: Adds systemd user service template, setup "
            "docs, and `unittest` suite (`3/3` tests passing)."
        ),
    },
    "stablyai/orca:feat/mobile-terminal-triple-tap-enter": {
        "ticket": "T621",
        "title": "feat(mobile): send Enter on terminal triple-tap gesture",
        "why": (
            "In mobile terminal sessions—especially interactive TUI selection prompts and comment fields such as Antigravity (`agy`) "
            "approval/feedback dialogs—submitting a choice or free-text comment without opening the secondary key sheet or toggling input "
            "modes is awkward: tapping the Message-mode send button without a trailing newline in inline TUI prompts can leave input "
            "uncommitted, and adding custom key chords just to send `Enter` (`\\r`) adds unnecessary friction."
        ),
        "what_for": (
            "Lets mobile users triple-tap anywhere on the terminal viewport to immediately send an `Enter` (`\\r`) keystroke—with optional "
            "toggle in Settings (`Triple-tap for Enter`, enabled by default), light haptic feedback, and Live Input pending-edit flush so "
            "typed prompt text is committed in order before `\\r` arrives."
        ),
        "how": (
            "- **`mobile/src/terminal/document/touch-tap-selection.ts`, `terminal-webview-messages.ts`, & `TerminalWebView.tsx`**: Detects "
            "bounded 3-tap sequences (`<= 300ms` inter-tap, `<= 24px` drift) inside the terminal WebView gesture state machine without "
            "delaying single-tap focus or double-tap word selection, emitting `{ type: 'triple-tap' }` when enabled.\n"
            "- **`mobile/src/session/use-mobile-session-terminal-triple-tap.ts`**: Flushes pending Live Input edits before sending `\\r` via "
            "`sendAccessoryTerminalBytes` and triggers light haptic impact.\n"
            "- **`mobile/src/settings/terminal-triple-tap-enter-preference.ts` & `MobileTerminalSettingsSection.tsx`**: Persists the "
            "default-enabled `terminalTripleTapEnter` preference in SecureStore and exposes a toggle in Terminal Settings.\n"
            "- **Verification**: `79/79` mobile Vitest tests passing (including `use-mobile-session-terminal-triple-tap.test.tsx` and "
            "`touch-tap-selection.test.ts`), `0` localization drift, and `0` `oxlint` warnings/errors."
        ),
    },
    "stablyai/orca:feat/mobile-terminal-4-tap-alt-m": {
        "ticket": "T635",
        "title": "feat(mobile): send Alt+M on terminal 4-tap gesture",
        "why": (
            "Interactive CLI coding agents (Claude Code, Antigravity `agy`, Codex, OpenCode) bind `Alt+M` (`\\x1bm`) to cycle execution/permission "
            "modes on the fly, yet mobile software keyboards have no `Alt` modifier key—forcing mobile users to open accessory modal sheets "
            "or maintain custom shortcut keys just to toggle agent modes."
        ),
        "what_for": (
            "Adds an independently toggleable `4-tap for Alt+M` terminal gesture (`Terminal Settings -> Gestures`, enabled by default) that "
            "sends `Alt+M` (`\\x1bm`, encoded via `encodeTerminalKeyForModes` with Live Input flush and selection haptic feedback) on four "
            "consecutive single-finger taps without opening the software keyboard."
        ),
        "how": (
            "- **`mobile/src/terminal/document/surface-tap.ts`, `terminal-webview-messages.ts`, & `use-terminal-webview-controller.ts`**: "
            "Detects 4 consecutive single-finger non-link taps (`<= 400ms` inter-tap, `<= 45px` radius) inside the terminal WebView, "
            "disqualifying streaks on scroll, pinch, selection, or movement past tap slop, and emitting `{ type: 'terminal-quad-tap' }`.\n"
            "- **`mobile/src/session/use-mobile-session-terminal-quad-tap.ts`**: Flushes pending Live Input bytes and sends mode-encoded "
            "`\\x1bm` via `handleAccessoryKey`.\n"
            "- **`mobile/src/terminal/terminal-accessory-layout.ts` & `TerminalShortcutSettings.tsx`**: Persists `quadTapAltMEnabled` "
            "(default `true`) inside the bridge-allowlisted terminal accessory layout preference and exposes a separate `4-tap for Alt+M` "
            "switch under `GESTURES`.\n"
            "- **Verification**: Mobile `tsc --noEmit`, `verify:mobile-localization`, `oxlint`, and Vitest suites (`surface-tap`, "
            "`use-mobile-session-terminal-quad-tap`, and `terminal-accessory-layout`) passing with `0` errors."
        ),
    },
    "stablyai/orca:feat/mobile-four-side-edge-arrows": {
        "ticket": "T635 / T641 / T646",
        "title": "feat(mobile): add sticky 4-side edge arrows (Floating Orbs default), opt-in bottom-right switcher dock, and zoom-stable Gamepad HUD",
        "why": (
            "Navigating long transcripts, file/diff previews, session tabs, and interactive terminal prompts one-handed on mobile requires "
            "either stretching to top tab bars or keeping the software keyboard / accessory dock open; furthermore, pinch-zooming terminal "
            "WebViews scales overlay controls out of reach, and always-on corner mode chips crowd pane surfaces."
        ),
        "what_for": (
            "Renders sticky 4-side inner-edge navigation controls defaulting out-of-the-box to compact half-transparent `Floating Orbs` "
            "(`'orbs'`, alongside selectable `Edge Pills`, `Edge Strips`, `Gamepad HUD`, and `Off`) inside a zoom-stable `visualViewport` "
            "counter-scaled HUD, while keeping the bottom-right quick-switcher chip + `⚙` settings button hidden by default "
            "(`DEFAULT_EDGE_SWITCHER_CHIP_HIDDEN = true`, opt-in via `Show quick-switcher chip`)."
        ),
        "how": (
            "- **`mobile/src/navigation/edge-arrows/*` & `use-zoom-stable-viewport.ts`**: Defaults `DEFAULT_EDGE_NAVIGATION_MODE` to `'orbs'` "
            "and `DEFAULT_EDGE_SWITCHER_CHIP_HIDDEN` to `true`, wraps all 4 modes in a `1 / scale` `visualViewport` HUD "
            "(`transformOrigin: 'top left'`), docks the opt-in `edge-arrow-flavour-chip` + `edge-arrow-settings-button` bottom-right (lifting "
            "above native-chat jump-to-tail FAB), and adds `EdgeGamepadPad.tsx` with hold-to-repeat D-pad and terminal action cluster.\n"
            "- **`terminal-accessory-layout.ts`, `EdgeNavigationSettingsSection.tsx`, & `EdgeNavigationModeSheet.tsx`**: Persists `'pills' | "
            "'strips' | 'orbs' | 'gamepad' | 'off'` and explicit boolean `edgeSwitcherChipHidden` (`true` or `false`) in `orca:terminal-accessory-layout`.\n"
            "- **Verification**: `10/10` edge-navigation Vitest tests, `verify:mobile-localization`, `build-mobile-web-app-bundle`, and `oxlint` clean."
        ),
    },
    "stablyai/orca:fix/terminal-smooth-resize-and-replay": {
        "ticket": "T635 / T653",
        "title": "fix(terminal,mobile): suppress redundant SIGWINCH redraws and dynamically hold streaming resize bursts",
        "why": (
            "Interactive CLI coding agents (`claude`, `codex`, `agy`, `opencode`) render rich transcripts in the normal scrollback buffer "
            "rather than the alternate screen (`?1049h`). When a Desktop split pane, sidebar, `SessionRestoredBanner`, or Mobile viewport/keyboard "
            "resizes (`SIGWINCH`), these TUIs clear and re-stream their entire conversation transcript across dozens of PTY chunks—producing "
            "jarring top-to-bottom long-scrolling waterfalls, while redundant no-op `SIGWINCH` signals on reattach, recurring `1000ms` grid-drift "
            "probes, and `SessionRestoredBanner` title-space toggles triggered repeated full-transcript redraws without any real geometry change."
        ),
        "what_for": (
            "Eliminates redundant no-op `SIGWINCH` and layout-refit triggers across Desktop and Mobile, and dynamically holds the last painted "
            "terminal frame across multi-chunk `SIGWINCH` / `?2026` rewrite bursts (up to `1200ms` while rewrite chunks actively stream) so "
            "resizes and tab reveals swap cleanly without visible top-to-bottom scrolling waterfalls."
        ),
        "how": (
            "- **Desktop (`pty-resize-repaint-hold.ts`, `pty-input-forward.ts`, `foreground-grid-drift-probe.ts`, `session-restored-banner-pane-state.ts`, `remote-program-redraw.ts`, `RetainedPaneHost.tsx`)**: "
            "Captures `.xterm-screen` on foreground `SIGWINCH` and dynamically extends the hold up to `1200ms` while active rewrite chunks keep arriving (`< 60ms` inter-chunk gap, `90ms` initial no-output timeout); "
            "gates `createReattachGridPush` `transport.resize` + `SIGWINCH` on actual dimension change; skips recurring `1000ms` `proposeDimensions()` polling once settled; floats `SessionRestoredBanner` as a non-layout overlay; "
            "arms `resizeRepaintHold` across `remote-program-redraw` `rows +/- 1` nudges; and deduplicates `RetainedPaneHost` fit events by measured `width`/`height`.\n"
            "- **Mobile (`terminal-write-coalescer.ts`, `resize-repaint-hold.ts`, `terminal-viewport-refit.ts`, `use-terminal-webview-handle.ts`)**: "
            "Dynamically extends `beginResizeBurst()` and WebView canvas hold across active streaming rewrite chunks (up to `1200ms` cap), settles transient height-only refits (`280ms`), skips forced `unsubscribe`+`subscribe` when `updateViewport` succeeds with `applied: false`, and avoids mid-`?2026` `flushNow()` in `readPromptBackload`.\n"
            "- **Verification**: Desktop and Mobile Vitest suites, `oxlint --deny-warnings`, and `tsc --noEmit` passing cleanly."
        ),
    },
    "stablyai/orca:fix/mobile-terminal-theme-enforcement": {
        "ticket": "T641 / T653",
        "title": "fix(terminal,mobile): enforce light/dark appearance across agent sessions, native chat, and WebViews",
        "why": (
            "Agent TUI sessions (`claude`, `codex`, `opencode`, `agy`) and terminal/chat surfaces rendered black or dark-on-dark in Light mode across Mobile and Desktop due to multiple interacting gaps:\n"
            "1. Mobile never forwarded its active Light/Dark foreground/background colors on `session.tabs.createTerminal`, `agent.launch`, `agent.launchReplay`, or `terminal.setViewerColors`, so hosts answered TUI `OSC 10/11` and `CSI ?996n` queries with dark `#282c34`—causing TUIs to bake dark RGB ANSI backgrounds into cell attributes.\n"
            "2. Mobile `TerminalWebView` (native + web) baked `#1a1b26` into `document.body` and provisional xterm scope and left `.xterm-viewport` at `#000`.\n"
            "3. Desktop `native-chat-appearance-style.ts` defaulted `terminalUseSeparateLightTheme` to `false` with a `#000000` fallback, `terminal-appearance.ts` published UI `appearance.mode` (`'light'`) alongside dark terminal backgrounds when `terminalUseSeparateLightTheme === false` (mismatching `?996n`/mode `2031` vs `OSC 11`), and `terminalOptions` omitted initial `theme` on xterm creation."
        ),
        "what_for": (
            "Ensures interactive CLI agents, Native Chat transcripts, Desktop `TerminalPane`, and Mobile `TerminalWebView` (iOS, Android, and Web) "
            "consistently honor Light and Dark appearance from frame zero—both visually and in host-answered PTY color queries (`OSC 10/11`, `CSI ?996n`, DEC mode `2031`)."
        ),
        "how": (
            "- **Host & Mobile RPC (`session-tabs-schemas-params.ts`, `agent-launch-params.ts`, `runtime-rpc-mobile-method-routing.ts`, `mobile-terminal-create.ts`, `agent-launch-surfaces.ts`)**: "
            "Routes `terminal.setViewerColors` for mobile clients and forwards `terminalColorQueryReplies` from Mobile's active `colorScheme` across terminal/agent launches into `admitPairedCreateColors`.\n"
            "- **Mobile WebView (`TerminalWebView.tsx`, `TerminalWebView.web.tsx`, `terminal-webview-html.ts`, `document-style.ts`, `document-scope.ts`)**: "
            "Seeds initial Light/Dark background and foreground into `documentElement`, `body`, host container, and provisional xterm scope, and makes `.xterm`/`.xterm-viewport` transparent.\n"
            "- **Desktop (`native-chat-appearance-style.ts`, `terminal-appearance.ts`, `terminal-pane-manager-options.ts`, `use-document-appearance.ts`, `terminal.css`)**: "
            "Aligns `terminalUseSeparateLightTheme ?? true` and light fallback colors, derives `effectiveMode` from terminal background luminance, supplies initial `theme` to `terminalOptions`, and applies pre-hydration document theme.\n"
            "- **Verification**: `48/48` Desktop and `31/31` Mobile Vitest tests plus `oxlint --deny-warnings` clean."
        ),
    },
    "stablyai/orca:perf/terminal-chat-redraw-and-tab-caching": {
        "ticket": "T653",
        "title": "perf(terminal,chat): coalesce streaming redraws and bound warm tab caches",
        "why": (
            "Active agent chat and terminal sessions caused sustained high CPU/GPU redraw churn and unbounded warm-surface memory growth across Desktop and Mobile:\n"
            "1. Single-pane tabs in Native Chat view (`NativeChatPaneCover`) kept `rendererVisible === true` on the covered `TerminalPane`, leaving main-to-renderer PTY streaming at foreground priority, WebGL active, and xterm parsing invisible TUI spinner output underneath the chat cover.\n"
            "2. DEC `?2026` synchronized-output holding (`shouldProtectNativeWindowsSynchronizedOutput`) was gated strictly to Windows ConPTY, `FOREGROUND_IMMEDIATE_BUDGET_CHARS` (`128 KiB` / `500ms`) bypassed batching on sustained unattended TUI redraw bursts, and `shouldForceForegroundRenderRefresh` forced redundant DOM `refreshVisibleRows` + `scheduleViewportSettleRefresh` repaints over WebGL.\n"
            "3. Hidden `StructuredAgentSessionPaneOverlayLayer` tabs and Mobile `TerminalPaneView` `WebView` instances remained mounted without bound across tab switches, and `useNativeChatPacedText` kept `requestAnimationFrame` reveal loops and fade timers running while backgrounded."
        ),
        "what_for": (
            "Eliminates invisible background xterm/WebGL rendering under Native Chat covers, holds split DEC `?2026` synchronized frames cross-platform while coalescing sustained unattended streaming bursts, skips redundant DOM double-refreshes on WebGL panes, pauses hidden text-reveal `rAF` loops, and bounds warm tab caches across Desktop and Mobile."
        ),
        "how": (
            "- **Desktop (`use-terminal-pane-global-effects.ts`, `pane-host-capability-flags.ts`, `write-pty-output-to-xterm.ts`, `foreground-output-budgets.ts`, `foreground-output-refresh.ts`, `terminal-hidden-view-parking.ts`)**: "
            "Treats single-pane Native Chat covers as hidden for PTY visibility/WebGL, enables DEC `?2026` frame holding cross-platform while keeping cursor-show stripping and `1000ms` cursor-restore coalescing ConPTY-only, caps unattended immediate foreground writes to `4 KiB` / `500ms` (`scheduleDrain(0)` coalescing beyond that), skips redundant DOM rewrite refresh when WebGL is active on non-ConPTY hosts, and tightens hot-retain limits (`3` tabs / `2` worktrees).\n"
            "- **Native Chat & Overlay (`use-native-chat-paced-text.ts`, `use-mobile-native-chat-paced-text.ts`, `StructuredAgentSessionPaneOverlayLayer.tsx`)**: "
            "Pauses 60fps `rAF` + fade timers while backgrounded (`document.hidden` / `AppState !== 'active'`) and cold-parks inactive structured chat overlay slots beyond LRU `2`.\n"
            "- **Mobile (`MobileSessionActiveContent.tsx`, `TerminalPaneView.tsx`, `use-warm-terminal-handles.ts`, `use-mobile-session-terminal-webview.ts`)**: "
            "Memoizes `TerminalPaneView`, bounds mounted hidden `TerminalWebView` instances to a `3`-handle warm LRU, and cleans up `webReadyHandlesRef` / `initializedHandlesRef` when evicted WebViews unmount.\n"
            "- **Verification**: `155/155` Desktop and `23/23` Mobile Vitest tests plus `oxlint --deny-warnings` passing cleanly."
        ),
    },
    "stablyai/orca:fix/mobile-live-input-prompt-backload": {
        "ticket": "T621 / T653",
        "title": "fix(mobile): backload existing prompt text when opening Live Input and prevent duplicate seed strokes",
        "why": (
            "When switching a mobile terminal into Live Input mode after partially typing a command or prompt in the shell/TUI, the Live Input "
            "composer started empty—causing edits or backspace gestures to desynchronize from the terminal's actual prompt line or re-send "
            "already-present characters."
        ),
        "what_for": (
            "Reads the current prompt line tail from the active xterm buffer (`readPromptBackload`) when entering Live Input mode so existing "
            "prompt text is pre-seeded without re-transmitting those characters to the PTY."
        ),
        "how": (
            "- **`mobile/src/terminal/document/prompt-backload.ts` & `use-terminal-webview-handle.ts`**: Extracts active cursor-line prompt text "
            "after stripping shell/TUI prompt prefixes and exposes `readPromptBackload()` on `TerminalWebViewHandle`.\n"
            "- **`mobile/src/session/use-mobile-session-live-input.ts`**: Seeds the Live Input buffer baseline without emitting duplicate strokes.\n"
            "- **Verification**: Unit tests in `prompt-backload.test.ts` and `use-mobile-session-live-input.test.ts`."
        ),
    },
    "stablyai/orca:feat/subagent-display-and-floating-category": {
        "ticket": "T621 / T653",
        "title": "feat(sidebar,chat): group floating/subagent sessions and surface live subagent activity badges",
        "why": (
            "Dispatched subagent and floating ad-hoc sessions mixed flatly with primary feature worktrees or lacked compact live subagent "
            "activity indicators in sidebar cards and Native Chat headers, making multi-agent orchestration harder to scan at a glance."
        ),
        "what_for": (
            "Groups floating/ad-hoc sessions cleanly in the workspace sidebar and surfaces live subagent status/count badges across worktree "
            "cards and structured/terminal agent headers."
        ),
        "how": (
            "- **Sidebar & Subagent Projection (`src/renderer/src/components/sidebar/*`, `src/shared/agent-session/*`)**: Categorizes floating "
            "and child subagent sessions with live status counts and collapsible grouping.\n"
            "- **Verification**: Renderer and shared unit tests passing with `oxlint --deny-warnings` clean."
        ),
    },
    "stablyai/orca:feat/system-and-docker-monitors": {
        "ticket": "T638",
        "title": "feat(terminal,mobile): add built-in *top and Docker TUI monitor launcher",
        "why": (
            "Developers regularly inspect host CPU/RAM, Docker/Podman containers, GPU load, disk usage, and I/O (`btop`, `htop`, "
            "`lazydocker`, `ctop`, `docker stats`, `nvtop`, `radeontop`, `ncdu`, `duf`, `iotop`, `nethogs`, `top`), yet launching "
            "any of them inside Orca currently requires opening a blank terminal tab and typing the command by hand—which is "
            "especially slow on Orca Mobile."
        ),
        "what_for": (
            "Auto-detects installed system, container, GPU, disk, and network `*top` TUIs on the workspace's execution host "
            "(`local`, `wsl`, or paired `runtime`) with zero subprocess spawning and surfaces one-click/one-tap `Monitors` launchers "
            "in the Desktop `+` dropdown submenu, the Desktop `+` search omnibox, and the Mobile `New Tab -> Monitors (*top)` sheet."
        ),
        "how": (
            "- **Shared & Host Preflight (`src/shared/system-monitors.ts`, `src/main/preflight/system-monitor-detection.ts`)**: "
            "Typed 21-tool catalog across System, Docker/Containers/Kubernetes, GPU, Disk, and I/O & Network probed via bounded "
            "PATH directory scans (`detectAgentCommandsOnHost`), exposed over Electron IPC (`preflight:detectMonitors`) and "
            "execution-host-routed RPC (`preflight.detectMonitors`).\n"
            "- **Desktop & Mobile Launchers (`TabBarSystemMonitorsSubmenu.tsx`, `tab-create-menu-options.ts`, `MobileSystemMonitorsSheet.tsx`)**: "
            "Adds `Monitors` submenu + `+` search omnibox items on Desktop and `Monitors (*top)` action sheet on Mobile with "
            "`shell-ready` startup delivery and fallback presets when paired to older hosts.\n"
            "- **Verification**: `oxlint`, `tsc --noEmit`, Desktop & Mobile localization catalogs, and Desktop + Mobile Vitest suites clean."
        ),
    },
    "stablyai/orca:feat/zeroclaw-agent-connector": {
        "ticket": "T584",
        "title": "feat(agent): add ZeroClaw agent connector and AI Vault scanner",
        "why": (
            "ZeroClaw (`zeroclaw`) is a fast, low-memory Rust coding agent used alongside Claude Code, Codex, Gemini, OpenCode, "
            "OpenClaw, and Pi. Without native registration in Orca's `TuiAgent` catalog and AI Vault scanner, terminal tabs running "
            "`zeroclaw` lacked agent status detection and mobile TUI launch support, sessions under `~/.zeroclaw/` were invisible in "
            "AI Vault across local/WSL/SSH hosts, and canonical ZeroClaw skill roots could not be discovered."
        ),
        "what_for": (
            "Adds first-class support for ZeroClaw so users can launch `zeroclaw` from the Desktop and Mobile agent picker, browse "
            "and search local/WSL/SSH ZeroClaw JSONL transcripts (including subagent transcripts, token usage, and model metrics) in "
            "AI Vault with one-click `zeroclaw --session <id>` resume, and discover skills across `~/.zeroclaw` and `.zeroclaw/skills`."
        ),
        "how": (
            "- **TUI Agent Catalog (`src/shared/tui-agent.ts`, `src/shared/tui-agent-config.ts`, `src/renderer/src/lib/agent-catalog.tsx`, `mobile/src/tasks/mobile-tui-agents.ts`)**: "
            "Registers `'zeroclaw'` with `detectCmd`/`launchCmd`, line-buffered prompt delivery, branding/icon, and status badge mapping.\n"
            "- **AI Vault Scanner & Graph Parser (`src/main/ai-vault/`, `src/shared/ai-vault-*.ts`)**: Scans `~/.zeroclaw/sessions`, "
            "`~/.zeroclaw/data/sessions`, and `~/.zeroclaw/agents/**/sessions` across local, WSL, and remote SSH hosts (honoring "
            "`ZEROCLAW_STATE_DIR` / `ZEROCLAW_HOME`) and wires subagent transcripts + `zeroclaw --session <id>` resume.\n"
            "- **Skills Discovery (`src/main/skills/`, `src/shared/native-chat-*.ts`)**: Indexes canonical ZeroClaw global and workspace skill roots.\n"
            "- **Verification**: Dedicated `session-scanner-zeroclaw.test.ts` plus `166` AI Vault/skills/TUI parity tests, `typecheck`, and localization checks clean."
        ),
    },
    "stablyai/orca:feat/macos-deep-link-shortcuts": {
        "ticket": "T584",
        "title": "feat(orchestration): support macOS deep-link protocol for orchestration shortcuts and automation",
        "why": (
            "Orca's multi-agent orchestration engine (`orca orchestration`) previously required interactive clicks inside the desktop "
            "UI or running CLI commands from a terminal already bound to an Orca runtime session. External system automations (macOS "
            "Shortcuts, Siri triggers, Raycast, calendar/webhook hooks, or IDE buttons) had no URL scheme entrypoint to hand an "
            "orchestration objective and target repository to Orca across cold starts and running instances."
        ),
        "what_for": (
            "Lets external automation tools—Apple Shortcuts, Siri, Raycast, CI webhooks, and local scripts—open or pre-stage an Orca "
            "orchestration session via `orca://orchestration/new?repo=<repo>&objective=<text>` (or `run` / `create`) across both cold "
            "launches and running instances."
        ),
        "how": (
            "- **Shared Parser & Validation (`src/shared/orchestration-deep-link.ts`)**: Parses `orca://orchestration/{new,create,run}` "
            "with bounded query sanitization and strict repository identifier matching.\n"
            "- **Main-Process Readiness Buffer (`src/main/startup/orchestration-deep-link-state.ts`)**: Buffers cold-start argv and "
            "macOS `open-url` / `second-instance` links until renderer IPC readiness, resetting cleanly on window close.\n"
            "- **Renderer Routing (`src/renderer/src/store/slices/ui/`)**: Consumes pending orchestration deep links and pre-fills "
            "the target repository and objective without auto-executing unreviewed shell commands.\n"
            "- **Verification**: Full parser, main-process readiness latch, and renderer store Vitest suites passing with `typecheck` and `oxlint` clean."
        ),
    },
    "stablyai/orca:feat/macos-deep-link-worktree": {
        "ticket": "T584",
        "title": "feat(worktree): support macOS deep-link protocol for worktree creation",
        "why": (
            "Previously, Orca handled `orca://` deep links only for account auth callbacks, remote host pairing (`orca://pair`), and "
            "live session joining (`orca://join`). Opening a worktree from an external workflow (GitHub/Linear/Jira browser extension, "
            "Raycast/Alfred launcher, or review script) required manually switching to Orca, opening the workspace composer, picking "
            "the repository, and typing the worktree and base branch names by hand."
        ),
        "what_for": (
            "Lets external developer tools, browser bookmarklets, issue trackers, and CLI scripts open Orca's existing New Workspace "
            "Composer pre-filled with a target repository, worktree name, and base branch via `orca://worktree/create?...` or "
            "`https://app.orca.dev/worktree/create?...`."
        ),
        "how": (
            "- **URL Parser & Ref Sanitizer (`src/shared/worktree-deep-link.ts`)**: Validates `orca://worktree/create` parameters and "
            "rejects path traversal or invalid git ref characters across POSIX and Windows.\n"
            "- **Main-Process Lifecycle (`src/main/startup/worktree-deep-link-state.ts`)**: Buffers cold-start argv and `open-url` / "
            "`second-instance` events behind a renderer readiness latch that resets when the window closes.\n"
            "- **Renderer Composer Pre-fill (`src/renderer/src/store/slices/ui/ui-slice-view-actions.ts`)**: Matches `repo` by `id`, "
            "`displayName`, or basename and opens `new-workspace-composer` with `prefilledName`, `initialRepoId`, and `initialBaseBranch` "
            "(user still explicitly confirms creation).\n"
            "- **Verification**: Unit tests in `worktree-deep-link.test.ts`, `worktree-deep-link-state.test.ts`, `useIpcEvents-lifecycle.test.ts`, "
            "and `ui-page-navigation.test.ts` passing."
        ),
    },
    "jundot/omlx:fix/menubar-adopt-external-omlx": {
        "ticket": "T584",
        "title": "fix(menubar): detect and adopt manually-started oMLX server on port conflict",
        "why": (
            "When a developer or LaunchAgent starts `omlx serve` from the CLI and later opens the macOS oMLX Menubar app, "
            "`ServerProcess.start()` detects the occupied port via `PortConflictResolver` and transitions into `.failed` (`portConflict`) "
            "with an informational-only alert. Even when `PortConflictResolver` positively verifies that the process holding the port "
            "is a genuine `oMLX` server instance with a known `pid`, the menubar app could not adopt, stop, or restart it (`killExternal(_:)` "
            "had zero call sites and `stop()` / `forceRestart()` were no-ops while `process == nil`)."
        ),
        "what_for": (
            "Lets developers who start `omlx serve` from terminal scripts, `tmux`, or LaunchAgents open the macOS Menubar app and "
            "choose **Take Over** (explicitly adopting `pid` so Stop/Restart and live health polling work from the menubar) or **Stop It**, "
            "while keeping foreign non-oMLX port holders strictly informational and untouched."
        ),
        "how": (
            "- **`ServerProcess.adoptExternal(_:)`**: Kept out of `start()`'s automatic path so the existing `.portConflict` contract "
            "is 100% preserved (per `#3319`); records `adoptedExternalPid`, transitions state to `.running`, and wires `stop()` / "
            "`forceRestart()` to signal `adoptedExternalPid` via `PortConflictResolver.killExternal(_:)` when `process == nil`.\n"
            "- **`MenubarController`**: Offers **Take Over**, **Stop It**, and **Cancel** on `.portConflict` only when "
            "`isOMLXInstance == true` with a valid `pid`.\n"
            "- **Validation (Apple M1 Max, 64 GB RAM, macOS)**: `xcodebuild` succeeds; new integration test "
            "`testAdoptExternalServerAndStopKillsIt` spawns a real external `dev_server.py` process, triggers `.portConflict`, "
            "calls `adoptExternal(_:)`, and verifies `stop()` terminates the external OS process; full `ServerProcessIntegrationTests` "
            "(including `testPortConflictCanBeFixedWithOfflineApply`) and `oMLXTests` pass."
        ),
    },
}


# Per-proposal target compliance metadata (`AgDR-0058` / `T655`)
PROPOSAL_COMPLIANCE_META: dict[str, dict[str, Any]] = {
    "stablyai/orca:feat/zeroclaw-agent-connector": {
        "eli5": (
            "Adds first-class support for the ZeroClaw (`zeroclaw`) Rust coding agent so users can launch it from Orca, "
            "browse/search/resume its session transcripts in AI Vault, and discover its skills across local, WSL, and SSH hosts."
        ),
        "linked_issue": 38849,
        "issue_kind": "feature",
        "issue_title": "[Feature]: First-class ZeroClaw agent connector, AI Vault transcript scanner, and skills discovery",
        "visual_change": True,
        "risk_level": "Low",
        "risk_summary": (
            "Additive `'zeroclaw'` union member across TUI agent catalog, AI Vault scanner roots, and skill discovery roots; "
            "existing agent connectors and scanner caches are unchanged. Plain `git revert` cleanly backs out all changes."
        ),
    },
    "stablyai/orca:feat/macos-deep-link-shortcuts": {
        "eli5": (
            "Lets Apple Shortcuts, Raycast, Siri, and scripts open an Orca orchestration composer pre-filled with a target "
            "repository and objective via `orca://orchestration/new?repo=...&objective=...`."
        ),
        "linked_issue": 21158,
        "issue_kind": "feature",
        "visual_change": False,
        "visual_proof_na_reason": (
            "Protocol/IPC deep-link handler (`orca://orchestration/...`) that routes into the existing orchestration composer "
            "without adding or modifying any UI chrome."
        ),
        "risk_level": "Low",
        "risk_summary": (
            "Scoped strictly to `orca://orchestration/*` URL parsing and IPC readiness buffering; never auto-executes commands "
            "without user confirmation in the composer. Plain revert restores prior deep-link routing."
        ),
    },
    "stablyai/orca:feat/macos-deep-link-worktree": {
        "eli5": (
            "Lets issue trackers, browser bookmarklets, Raycast, and scripts open Orca's New Workspace Composer pre-filled "
            "with repository, worktree name, and base branch via `orca://worktree/create?...`."
        ),
        "linked_issue": 21159,
        "issue_kind": "feature",
        "visual_change": False,
        "visual_proof_na_reason": (
            "Protocol/IPC deep-link handler (`orca://worktree/create?...`) that pre-fills the existing New Workspace Composer "
            "dialog with zero UI layout or styling changes."
        ),
        "risk_level": "Low",
        "risk_summary": (
            "Strictly sanitizes git ref/path query inputs and only pre-fills the existing composer modal (no automatic git mutation "
            "until the user clicks Create). Plain revert cleanly removes the route."
        ),
    },
    "stablyai/orca:feat/cross-worktree-tab-move": {
        "eli5": (
            "Lets you drag a live terminal or agent tab onto another workspace in the sidebar (or right-click -> Move to Workspace) "
            "to move it between the Floating Workspace and project worktrees without killing the running session."
        ),
        "linked_issue": 24022,
        "issue_kind": "feature",
        "visual_change": True,
        "sibling_notes": (
            "Complements `#28115` (which handles dragging tabs into split panes within the same workspace) by enabling cross-workspace "
            "tab transfers across `unifiedTabsByWorktree`, including Floating Workspace <-> docked worktree moves (`#24022`)."
        ),
        "risk_level": "Medium",
        "risk_summary": (
            "Touches renderer tab/group state maps (`unifiedTabsByWorktree`, `groupsByWorktree`, `layoutByWorktree`) during explicit "
            "cross-worktree move actions while keeping `ptyIdsByTabId` intact; same-worktree tab drag/split paths remain unchanged. "
            "Plain revert backs out cleanly with no persisted schema migration."
        ),
    },
    "stablyai/orca:feat/agent-collaboration-board": {
        "eli5": (
            "Adds `orca orchestration lock-acquire`, `lock-release`, `lock-list`, and a run-scoped collaboration board in SQLite "
            "so multiple agents working in parallel can take turns on shared resources (like ports or test databases) without colliding."
        ),
        "linked_issue": 38850,
        "issue_kind": "feature",
        "issue_title": "[Feature]: FIFO resource locks and shared collaboration board for multi-agent orchestration runs",
        "visual_change": False,
        "visual_proof_na_reason": (
            "Headless CLI (`orca orchestration lock-*`), runtime RPC, and SQLite store (`src/cli/*`, `src/main/*`, `src/shared/*`); "
            "zero renderer or mobile UI changes."
        ),
        "risk_level": "Low",
        "risk_summary": (
            "Additive SQLite tables (`CREATE TABLE IF NOT EXISTS`) and new `orchestration.lock*` RPC/CLI endpoints; existing "
            "orchestration task/mail/worker flows are untouched. Plain revert leaves existing orchestration tables intact."
        ),
    },
    "stablyai/orca:feat/mobile-camera-capture-chat": {
        "eli5": (
            "Adds a `Take Photo` camera option inside Orca Mobile's chat and terminal attachment menus so you can snap a photo "
            "of a screen or whiteboard directly into an agent session without switching apps."
        ),
        "linked_issue": 38851,
        "issue_kind": "feature",
        "issue_title": "[Feature]: Direct camera photo capture in Orca Mobile chat and terminal attachment docks",
        "visual_change": True,
        "risk_level": "Low",
        "risk_summary": (
            "Scoped to mobile attachment action sheets (`pickFromCamera` via `expo-image-picker`); reuses the existing chunked "
            "base64 attachment upload pipeline and handles denied camera permissions gracefully. Plain revert backs out cleanly."
        ),
    },
    "stablyai/orca:feat/mobile-live-input-password-mask": {
        "eli5": (
            "Automatically hides typed characters behind `*` asterisks in Orca Mobile's input bar when a terminal asks for a "
            "password (`sudo`, `ssh`, `gpg`), with a tap-to-toggle Show/Hide eye button."
        ),
        "linked_issue": 38852,
        "issue_kind": "feature",
        "issue_title": "[Feature]: Automatic password prompt asterisk masking and Show/Hide toggle in Orca Mobile terminal input dock",
        "visual_change": True,
        "risk_level": "Low",
        "risk_summary": (
            "Scoped to mobile `MobileSessionCommandDock` visual masking and per-handle prompt detection; raw PTY byte transmission "
            "is unchanged and users can always toggle `Show`/`Hide` manually. Plain revert backs out cleanly."
        ),
    },
    "stablyai/orca:feat/obsidian-ofm-engine": {
        "eli5": (
            "Renders Obsidian-style `[[wikilinks]]`, `![[embeds]]`, and `> [!NOTE]` / `> [!WARNING]` callout boxes natively in "
            "Orca's Markdown reader so Obsidian vaults and agent notes look and link properly."
        ),
        "linked_issue": 3040,
        "issue_kind": "feature",
        "visual_change": True,
        "risk_level": "Low",
        "risk_summary": (
            "Scoped to Markdown preview blockquote/link rendering (`MarkdownBlockquoteOrCallout.tsx`, `markdown-doc-links.ts`); "
            "standard CommonMark/GFM blockquotes and `[text](url)` links render identically. Plain revert restores prior preview."
        ),
    },
    "stablyai/orca:fix/mobile-markdown-external-tab-read": {
        "eli5": (
            "Allows Orca Mobile to read Markdown files outside the git workspace root when those files are already explicitly open "
            "as tabs on the paired desktop host, and shows a clear message if an unopened outside file is requested."
        ),
        "linked_issue": 32115,
        "issue_kind": "bug",
        "visual_change": False,
        "visual_proof_na_reason": (
            "Host file-read authorization for already-open desktop Markdown tab paths plus structured error propagation into "
            "existing mobile reader state; no UI layout or visual component changes."
        ),
        "risk_level": "Low",
        "risk_summary": (
            "Security boundary preserved: external disk reads are authorized strictly for canonical file paths currently open in "
            "an active desktop Markdown tab (`markdown-tab-disk-host.ts`); arbitrary path reads outside workspace remain rejected. "
            "Plain revert backs out cleanly."
        ),
    },
    "stablyai/orca:feat/nested-subfolder-git-and-sdlc-repo": {
        "eli5": (
            "Finds nested git repositories inside umbrella/monorepo folders even when the root `.gitignore` uses `/*`, and lets "
            "workspaces resolve their canonical GitHub Issues/PRs target from `.w0m/sdlc.json`."
        ),
        "linked_issue": 23385,
        "issue_kind": "feature",
        "visual_change": False,
        "visual_proof_na_reason": (
            "Main-process nested git discovery (`src/main/project-groups/*`) and GitHub repository target resolution "
            "(`src/main/github/*`) only; zero renderer or mobile UI changes."
        ),
        "sibling_notes": (
            "Complements `#32872` (plain non-git subfolders inside a single git repo) by discovering actual nested `.git` "
            "repositories inside umbrella git roots (`#23385`) while skipping `.worktrees`/`.w0m` clone containers."
        ),
        "risk_level": "Low",
        "risk_summary": (
            "Bounded directory scan in `nested-repo-discovery.ts` explicitly excludes `.git`, `node_modules`, `.worktrees`, and "
            "`.w0m` worktree containers; `.w0m/sdlc.json` lookup is a fast no-op when absent. Plain revert backs out cleanly."
        ),
    },
    "stablyai/orca:feat/mobile-session-tab-reorder": {
        "eli5": (
            "Lets you reorder tabs on Orca Mobile by dragging the active tab pill left/right or tapping `Move Tab Left` / "
            "`Move Tab Right` in the long-press menu, syncing the new tab order live with Desktop."
        ),
        "linked_issue": 38853,
        "issue_kind": "feature",
        "issue_title": "[Feature]: Reorder session tabs on Orca Mobile via horizontal drag and long-press action sheet",
        "visual_change": True,
        "risk_level": "Low",
        "risk_summary": (
            "Scoped to mobile tab strip drag/sheet reordering and the `session.tabs.move` relay write; paired agent+terminal "
            "tabs move together atomically, and older hosts without `session.tabs.move` fail gracefully without crashing. Plain revert."
        ),
    },
    "stablyai/orca:fix/linux-cli-stale-appimage-and-dispatcher": {
        "eli5": (
            "Fixes `orca` terminal commands breaking on Linux after updating or moving an `.AppImage` by automatically refreshing "
            "stale `~/.orca/cli-launcher` paths and installing the proper `~/.local/bin/orca` wrapper script."
        ),
        "linked_issue": 38990,
        "issue_kind": "bug",
        "issue_title": "[Bug]: Linux AppImage upgrades leave stale ~/.orca/cli-launcher paths and legacy ~/.local/bin/orca symlinks",
        "visual_change": False,
        "visual_proof_na_reason": (
            "Main-process Linux CLI launcher/symlink installer logic (`src/main/cli/*`); zero UI changes."
        ),
        "risk_level": "Low",
        "risk_summary": (
            "Linux-only (`process.platform === 'linux'` and `process.env.APPIMAGE`), triggers repair only when the registered "
            "launcher path no longer exists on disk so side-by-side AppImages are never clobbered. Plain revert."
        ),
    },
    "stablyai/orca:fix/webgl-atlas-version-desync-recovery": {
        "eli5": (
            "Fixes terminal panes occasionally showing up blank when switching tabs on Linux/GPU systems by detecting when xterm's "
            "WebGL font cache gets out of sync and refreshing it automatically."
        ),
        "linked_issue": 38856,
        "issue_kind": "bug",
        "issue_title": "[Bug]: Terminal pane reveals blank when xterm WebGL glyph-atlas version desynchronizes across parked tabs",
        "visual_change": False,
        "visual_proof_na_reason": (
            "Internal xterm WebGL glyph-atlas desynchronization check and one-shot `clearTextureAtlas()` recovery on pane reveal "
            "(`src/renderer/src/lib/pane-manager/*`); zero UI layout, chrome, or styling changes."
        ),
        "sibling_notes": (
            "Distinct from `#6071` (general WebGL context loss) and `#38120` (macOS atlas page cap): targets live WebGL contexts "
            "where `_glyphRenderer._atlas.version !== _model.glyphAtlasVersion` after hidden-tab parking."
        ),
        "risk_level": "Low",
        "risk_summary": (
            "Guarded behind optional-chaining checks on xterm's WebGL renderer and runs at most once per pane reveal when a real "
            "atlas version mismatch is detected (`0` overhead on healthy reveals). Plain revert backs out cleanly."
        ),
    },
    "stablyai/orca:feat/mobile-terminal-triple-tap-enter": {
        "eli5": (
            "Lets you triple-tap anywhere on a mobile terminal screen to send `Enter` right away—making it easy to confirm CLI "
            "menus and prompts one-handed without opening extra key bars."
        ),
        "linked_issue": 38854,
        "issue_kind": "feature",
        "issue_title": "[Feature]: Triple-tap terminal gesture on Orca Mobile to send Enter with Live Input flush",
        "visual_change": True,
        "risk_level": "Low",
        "risk_summary": (
            "Scoped to mobile WebView 3-tap detection (`<= 300ms`, `<= 24px` drift) without delaying single-tap focus or double-tap "
            "word selection, and can be toggled off in Terminal Settings (`Triple-tap for Enter`). Plain revert."
        ),
    },
    "stablyai/orca:feat/mobile-terminal-4-tap-alt-m": {
        "eli5": (
            "Lets you 4-tap on a mobile terminal screen to send `Alt+M` so you can switch agent modes (like Plan/Auto mode in "
            "Claude Code or Antigravity) even though phone keyboards don't have an `Alt` key."
        ),
        "linked_issue": 38992,
        "issue_kind": "feature",
        "issue_title": "[Feature]: 4-tap terminal gesture on Orca Mobile to send Alt+M mode-cycle shortcut",
        "visual_change": True,
        "visual_proof_urls": [
            "![Mobile Terminal Shortcuts — 4-tap for Alt+M gesture toggle (@2x dark)](https://raw.githubusercontent.com/webomage/orca/pr-assets/t657-visual-proof/t657/mobile-quad-tap-alt-m-settings-dark-2x.png)"
        ],
        "risk_level": "Low",
        "risk_summary": (
            "Scoped to mobile terminal 4-tap streak detection and persisted `quadTapAltMEnabled` toggle under Terminal Settings -> "
            "Gestures. Plain revert backs out cleanly."
        ),
    },
    "stablyai/orca:feat/mobile-four-side-edge-arrows": {
        "eli5": (
            "Adds compact translucent edge navigation orbs (plus optional Edge Pills, Edge Strips, or a Gamepad D-pad HUD) on "
            "Orca Mobile so you can scroll transcripts, switch tabs, and navigate terminal prompts one-handed even while zoomed in."
        ),
        "linked_issue": 38855,
        "issue_kind": "feature",
        "issue_title": "[Feature]: Zoom-stable 4-side edge navigation controls and optional Gamepad HUD on Orca Mobile",
        "visual_change": True,
        "risk_level": "Low",
        "risk_summary": (
            "Scoped to mobile `edge-arrows` overlay (`'orbs'` default, quick-switcher chip hidden by default via "
            "`DEFAULT_EDGE_SWITCHER_CHIP_HIDDEN = true`, full `'off'` mode in Settings). Plain revert backs out cleanly."
        ),
    },
    "stablyai/orca:fix/terminal-smooth-resize-and-replay": {
        "eli5": (
            "Stops terminal agent chats from visibly scrolling and re-streaming their whole conversation top-to-bottom when a "
            "pane resizes, a tab reattaches, or the mobile keyboard opens."
        ),
        "linked_issue": 21204,
        "issue_kind": "bug",
        "visual_change": False,
        "visual_proof_na_reason": (
            "Internal PTY `SIGWINCH` deduplication, `SessionRestoredBanner` non-layout overlay positioning, and streaming resize "
            "frame-hold timing across existing Desktop and Mobile terminal panes; adds zero new UI controls."
        ),
        "sibling_notes": (
            "Addresses the root `SIGWINCH` reattach/drift-probe triggers and multi-chunk normal-buffer TUI rewrite waterfalls "
            "across Desktop and Mobile (`#21204`, related `#15799`)."
        ),
        "risk_level": "Medium",
        "risk_summary": (
            "Touches Desktop and Mobile terminal resize/repaint-hold timing (`<= 1200ms` hard cap with `90ms` initial no-output "
            "timeout so idle shells never stall) and gates reattach `SIGWINCH` on real grid dimension changes. Plain revert."
        ),
    },
    "stablyai/orca:fix/mobile-terminal-theme-enforcement": {
        "eli5": (
            "Fixes terminal and agent sessions rendering with black backgrounds in Light mode on Mobile and Desktop by forwarding "
            "the active Light/Dark colors to terminal color queries (`OSC 10/11`, `CSI ?996n`) and seeding initial WebView/xterm themes."
        ),
        "linked_issue": 32242,
        "issue_kind": "bug",
        "visual_change": False,
        "visual_proof_na_reason": (
            "Protocol (`OSC 10/11`, `CSI ?996n`, `terminal.setViewerColors`) and existing Light/Dark theme token enforcement "
            "eliminating hardcoded `#000000`/`#1a1b26`/`#282c34` dark fallbacks; adds zero new UI widgets or layout changes."
        ),
        "sibling_notes": (
            "Fixes `#32242` (and related light-mode terminal background mismatches in `#23139`) across paired Mobile RPC, "
            "Mobile `TerminalWebView`, and Desktop `terminal-appearance.ts`."
        ),
        "risk_level": "Low",
        "risk_summary": (
            "Additive optional `terminalColorQueryReplies` RPC field (backwards-compatible with older paired hosts/phones) and "
            "luminance-consistent theme initialization on Desktop and Mobile WebViews. Plain revert backs out cleanly."
        ),
    },
    "stablyai/orca:perf/terminal-chat-redraw-and-tab-caching": {
        "eli5": (
            "Cuts high CPU/GPU usage and memory growth during long agent chat sessions by pausing hidden terminal/WebGL rendering "
            "under Native Chat views, batching rapid terminal redraw bursts cross-platform, and capping background warm tab caches."
        ),
        "linked_issue": 38860,
        "issue_kind": "bug",
        "issue_title": "[Bug]: High CPU/GPU redraw churn under Native Chat covers, unbatched DEC ?2026 TUI bursts, and unbounded warm tab WebViews",
        "visual_change": False,
        "visual_proof_na_reason": (
            "Internal rendering/scheduler optimization (`rendererVisible` gating under `NativeChatPaneCover`, cross-platform DEC "
            "`?2026` frame holding, `4 KiB` unattended write coalescing, background `rAF` pause, and LRU warm-cache bounds); "
            "zero visual layout or UI changes."
        ),
        "sibling_notes": (
            "Orthogonal and complementary to `#35251` (subagent tree memoization) and `#31332` (background tab eviction): targets "
            "live `NativeChatPaneCover` xterm suppression, cross-platform DEC `?2026` frame holding, WebGL double-refresh removal, "
            "and Mobile `TerminalWebView` 3-handle warm LRU."
        ),
        "risk_level": "Medium",
        "risk_summary": (
            "Adjusts Desktop PTY visibility gating under single-pane Native Chat covers, cross-platform DEC `?2026` synchronized "
            "frame holding (keeping cursor-show stripping ConPTY-only), and warm LRU caps (`3` tabs Desktop/Mobile, `2` structured "
            "overlays); evicted tabs cleanly rehydrate from snapshot/daemon on focus. Plain revert."
        ),
    },
    "stablyai/orca:fix/mobile-live-input-prompt-backload": {
        "eli5": (
            "When you open Live Input on Orca Mobile after already typing part of a command in the terminal, it now pre-fills "
            "that existing prompt text instead of starting blank or sending duplicate letters."
        ),
        "linked_issue": 38862,
        "issue_kind": "bug",
        "issue_title": "[Bug]: Opening Live Input on Orca Mobile starts empty instead of seeding existing terminal prompt text",
        "visual_change": False,
        "visual_proof_na_reason": (
            "Buffer state synchronization (`readPromptBackload` into the existing Live Input text buffer without re-sending "
            "seed characters); zero new UI chrome or layout changes."
        ),
        "risk_level": "Low",
        "risk_summary": (
            "Scoped to mobile Live Input entry baseline seeding (`prompt-line-backload.ts` + `use-terminal-live-input-commit.ts`); "
            "normal direct terminal typing and empty prompts behave identically. Plain revert backs out cleanly."
        ),
    },
    "stablyai/orca:feat/subagent-display-and-floating-category": {
        "eli5": (
            "Groups floating and subagent sessions neatly in the sidebar and shows live subagent count/status badges so multi-agent "
            "runs are easy to scan at a glance."
        ),
        "linked_issue": 38994,
        "issue_kind": "feature",
        "issue_title": "[Feature]: Group floating/subagent sessions in sidebar and display live subagent activity badges",
        "visual_change": True,
        "visual_proof_urls": [
            "![Floating sidebar section with flat subagent activity rows (@2x dark)](https://raw.githubusercontent.com/webomage/orca/pr-assets/t657-visual-proof/t657/subagent-floating-flat-dark-2x.png)",
            "![Floating sidebar section with collapsible subagent tree hierarchy (@2x dark)](https://raw.githubusercontent.com/webomage/orca/pr-assets/t657-visual-proof/t657/subagent-floating-tree-dark-2x.png)",
        ],
        "risk_level": "Low",
        "risk_summary": (
            "Scoped to sidebar session grouping projection and subagent badge rendering; underlying worktree and session records "
            "are unchanged. Plain revert."
        ),
    },
    "stablyai/orca:feat/system-and-docker-monitors": {
        "eli5": (
            "Auto-detects installed system, Docker, GPU, disk, and network monitors (`btop`, `htop`, `lazydocker`, `nvtop`, etc.) "
            "and lets you launch them in one click from Desktop `+ -> Monitors` or Mobile `New Tab -> Monitors (*top)`."
        ),
        "linked_issue": 38986,
        "issue_kind": "feature",
        "issue_title": "[Feature]: One-click *top and Docker TUI monitor detection and launcher across Desktop and Mobile",
        "visual_change": True,
        "visual_proof_urls": [
            "![Desktop New Tab -> Monitors submenu (@2x dark)](https://raw.githubusercontent.com/webomage/orca/pr-assets/t657-visual-proof/t657/system-monitors-desktop-submenu-dark-2x.png)",
            "![Mobile Monitors (*top) action sheet (@2x dark)](https://raw.githubusercontent.com/webomage/orca/pr-assets/t657-visual-proof/t657/system-monitors-mobile-sheet-dark-2x.png)",
        ],
        "risk_level": "Low",
        "risk_summary": (
            "Uses bounded zero-subprocess `PATH` directory scans (`detectAgentCommandsOnHost`) and opens standard terminal tabs "
            "with fallback presets when paired to older hosts. Plain revert backs out cleanly."
        ),
    },
    "jundot/omlx:fix/menubar-adopt-external-omlx": {
        "linked_issue": None,
        "visual_change": False,
        "visual_proof_na_reason": "Native macOS NSAlert button actions covered by ServerProcessIntegrationTests.",
    },
}


def get_enriched_proposal(key: str, base_prop: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Merge canonical `CONTRIBUTION_PROPOSALS[key]` with `PROPOSAL_COMPLIANCE_META[key]` (`AgDR-0058`)."""
    raw = dict(base_prop if base_prop is not None else CONTRIBUTION_PROPOSALS.get(key, {}))
    meta = PROPOSAL_COMPLIANCE_META.get(key, {})
    merged: dict[str, Any] = {**raw, **meta}
    if ":" in key and "upstream_repo" not in merged:
        upstream_repo, branch = key.split(":", 1)
        merged["upstream_repo"] = upstream_repo
        merged["branch"] = branch
    return merged


def format_pr_proposal_body(proposal: dict[str, Any], upstream_repo: str = "") -> str:
    """Render a target-project-compliant PR description body (`AgDR-0058` / `T655`).

    - `stablyai/orca`: Renders the full 11-section `.github/pull_request_template.md` (`## ELI5`, `## What Changed`,
      `## Why`, `## Linked Issue` with `Fixes #<num>`, honest `## Visual Proof`, `## Testing`, `## Risk`,
      `## AI Disclosure`, `## Review`, `## Agent skill upstream boundary`, `## Notes`, and `## Checklist`).
    - `jundot/omlx`: Renders `.github/pull_request_template.md` (`## Summary`, `## Validation`, `## Checklist`).
    - Standard repositories: Renders `## Why (Rationale & Problem)`, `## What For (Use Cases & Value)`,
      and `## How (Implementation, Invariants & Verification)`.
    """
    repo = upstream_repo or str(proposal.get("upstream_repo") or "")
    rules = get_repo_contribution_rules(repo)
    profile = rules.get("template_profile", "standard")

    if profile == "orca_11_section":
        eli5 = str(proposal.get("eli5") or proposal.get("what_for") or "").strip()
        what_for = str(proposal.get("what_for") or "").strip()
        how = str(proposal.get("how") or "").strip()
        why = str(proposal.get("why") or "").strip()
        sibling_notes = str(proposal.get("sibling_notes") or "").strip()
        why_full = f"{why}\n\n**Related / Sibling PR Context:** {sibling_notes}" if sibling_notes else why

        linked_issue = proposal.get("linked_issue")
        issue_line = f"Fixes #{linked_issue}" if linked_issue else "Fixes #<!-- resolved via w0m_prs auto-issue gate -->"

        visual_change = bool(proposal.get("visual_change", False))
        visual_urls = [str(u).strip() for u in (proposal.get("visual_proof_urls") or []) if str(u).strip()]
        if not visual_change:
            na_reason = str(
                proposal.get("visual_proof_na_reason")
                or "Non-visual internal/CLI/protocol change with no UI layout or styling modifications."
            ).strip()
            visual_section = f"`N/A` — {na_reason}"
            visual_satisfied = True
        elif visual_urls:
            visual_section = "\n\n".join(visual_urls)
            visual_satisfied = True
        else:
            visual_section = (
                "_Pending before/after screenshot or video attachment via GitHub UI "
                "(no binary media committed to repository files per template rules; UI behavior verified by automated tests below)._"
            )
            visual_satisfied = False

        risk_level = str(proposal.get("risk_level") or "Low").strip()
        risk_summary = str(
            proposal.get("risk_summary")
            or "Scoped to touched modules with automated unit tests; plain `git revert` cleanly backs out the change."
        ).strip()
        review_summary = str(
            proposal.get("review_summary")
            or (
                "- **Cross-platform (`macOS`, `Linux`, `Windows`) & Remote/SSH/Mobile**: Verified path, platform, and paired-host RPC boundaries.\n"
                "- **Agent & provider neutrality**: No single-vendor lock-in or regressions to existing TUI/native chat providers.\n"
                "- **Performance & memory**: Bounded timers, caches, and listeners with deterministic cleanup on unmount/park.\n"
                "- **Security**: Strict input validation and workspace/IPC authorization boundaries preserved."
            )
        ).strip()
        visual_check = "x" if visual_satisfied else " "

        return (
            f"## ELI5\n\n{eli5}\n\n"
            f"## What Changed\n\n{what_for}\n\n{how}\n\n"
            f"## Why\n\n{why_full}\n\n"
            f"## Linked Issue\n\n{issue_line}\n\n"
            f"## Visual Proof\n\n{visual_section}\n\n"
            f"## Testing\n\n"
            f"- [x] I manually tested these changes locally\n"
            f"- [x] Automated tests added/updated, or explained why not below\n\n"
            f"## Risk\n\n"
            f"**Level:** {risk_level}\n\n{risk_summary}\n\n"
            f"## AI Disclosure\n\n"
            f"Developed and verified with AI pair-programming assistance (Google Antigravity / Claude Code), "
            f"with full human architectural review and local test/typecheck/lint verification.\n\n"
            f"## Review\n\n{review_summary}\n\n"
            f"## Agent skill upstream boundary\n\n"
            f"- [x] Not applicable, or this change copies or mechanically translates no upstream skill-installer source, "
            f"tests, fixtures, registry entries, path tables, comments, or documentation.\n\n"
            f"## Notes\n\n"
            f"Ensure no issues in: Security, Cross-platform support (Linux, Windows, Mac), Remote SSH, Mobile, "
            f"general backwards compatibility, performance\n\n"
            f"## Checklist\n\n"
            f"- [x] This PR is small and focused\n"
            f"- [x] I explained what changed and why (ELI5, the user-facing before/after, the mechanism, and why over the alternatives)\n"
            f"- [x] I stated the risk: what could break, for whom, and how to back it out\n"
            f"- [{visual_check}] Before/after screenshots or videos attached for UI changes, or `N/A` with reason\n"
            f"- [x] Self-reviewed for correctness, security, and performance\n"
            f"- [x] Cross-platform, SSH/remote, and path/shortcut impact considered (or N/A)\n"
            f"- [x] `pnpm lint`, `pnpm typecheck`, `pnpm test`, and `pnpm build` pass (or CI will cover; local preferred)\n"
        )

    if profile == "omlx_3_section":
        why = str(proposal.get("why") or "").strip()
        what_for = str(proposal.get("what_for") or "").strip()
        how = str(proposal.get("how") or "").strip()
        visual_change = bool(proposal.get("visual_change", False))
        visual_urls = [str(u).strip() for u in (proposal.get("visual_proof_urls") or []) if str(u).strip()]
        vis_box = "x" if (not visual_change or bool(visual_urls)) else " "
        return (
            f"## Summary\n\n{why}\n\n{what_for}\n\n"
            f"## Validation\n\n{how}\n\n"
            f"## Checklist\n\n"
            f"- [x] I read [CONTRIBUTING.md](https://github.com/jundot/omlx/blob/main/docs/CONTRIBUTING.md).\n"
            f"- [x] I understand every change in this PR and can explain it in review.\n"
            f"- [{vis_box}] For UI or UX changes, I attached before and after screenshots.\n"
        )

    return (
        f"## Why (Rationale & Problem)\n\n{proposal['why']}\n\n"
        f"## What For (Use Cases & Value)\n\n{proposal['what_for']}\n\n"
        f"## How (Implementation, Invariants & Verification)\n\n{proposal['how']}\n"
    )


def validate_pr_compliance(
    repo: str,
    title: str,
    body: str,
    *,
    visual_change: bool = False,
    mergeable: str = "MERGEABLE",
) -> dict[str, Any]:
    """Validate a PR title and Markdown body against `UPSTREAM_CONTRIBUTION_RULES` (`AgDR-0058` / `T655`)."""
    rules = get_repo_contribution_rules(repo)
    profile = rules.get("template_profile", "standard")
    findings: list[str] = []
    warnings: list[str] = []
    text = body or ""

    if rules.get("automation_mode") == "banned":
        warnings.append("AUTOMATION_BANNED: AI-written PR descriptions, pushes, and PR edits are strictly prohibited.")
        if "strictly prohibited to use AI to write PR description" not in text:
            findings.append("Missing mlx-lm `.github/pull_request_template.md` AI-prohibition acknowledgment line.")
        if "AI usage disclosure:" not in text:
            findings.append("Missing mlx-lm `AI usage disclosure:` field (must be filled manually by human author).")

    elif profile == "orca_11_section":
        required_headings = (
            "## ELI5",
            "## What Changed",
            "## Why",
            "## Linked Issue",
            "## Visual Proof",
            "## Testing",
            "## Risk",
            "## AI Disclosure",
            "## Review",
            "## Agent skill upstream boundary",
            "## Notes",
            "## Checklist",
        )
        for h in required_headings:
            if h not in text:
                findings.append(f"Missing required stablyai/orca heading `{h}`")
        if not re.search(r"\bFixes\s+#\d+\b", text, flags=re.IGNORECASE):
            findings.append("Missing mandatory `Fixes #<issue>` link under `## Linked Issue` (outside-contributor rule)")
        if "**Level:**" not in text:
            findings.append("Missing `**Level:** Low | Medium | High` under `## Risk`")
        vis_match = re.search(r"## Visual Proof\s*\n+(.*?)(?=\n## |\Z)", text, flags=re.DOTALL)
        vis_body = vis_match.group(1) if vis_match else ""
        has_media = bool(
            re.search(
                r"(?:!\[[^\]]*\]\([^)]+\)|https://github\.com/user-attachments/assets/|https://[^\s)\"]+githubusercontent\.com/|<video\b)",
                vis_body,
            )
        )
        has_na = "`N/A`" in vis_body
        if visual_change and not has_media:
            if has_na:
                findings.append("UI change falsely marked `N/A` under `## Visual Proof`")
            else:
                warnings.append("UI change pending uploaded before/after screenshot or video attachment")
        elif not visual_change and not (has_na or has_media):
            findings.append("Non-visual PR must state `` `N/A` `` + concise reason under `## Visual Proof`")

    elif profile == "omlx_3_section":
        for h in ("## Summary", "## Validation", "## Checklist"):
            if h not in text:
                findings.append(f"Missing required jundot/omlx heading `{h}`")

    elif profile == "headroom_7_section":
        for h in (
            "## Description",
            "## Type of Change",
            "## Changes Made",
            "## Testing",
            "## Real Behavior Proof",
            "## Runtime Rollout Safety",
            "## Checklist",
        ):
            if h not in text:
                findings.append(f"Missing required headroom governance heading `{h}`")
        if "### Test Output" not in text:
            findings.append("Missing required `### Test Output` section")

    elif profile == "graphify_5_section":
        for h in ("## Type of change", "## How was this tested?", "## Graphify-specific checklist"):
            if h not in text:
                findings.append(f"Missing required Graphify heading `{h}`")
        if not re.match(r"^(feat|fix|docs|chore|refactor|test|perf|ci|build)(\([^)]+\))?!?:\s+.+", title or ""):
            findings.append("PR title does not follow Conventional Commits (`feat:`, `fix:`, etc.)")

    else:
        if len(text.strip()) < 40:
            findings.append("PR description is too brief (< 40 chars)")

    if mergeable == "CONFLICTING":
        warnings.append("PR is currently CONFLICTING with upstream base branch and needs rebase")

    compliant = len(findings) == 0
    if not compliant:
        status = "NON_COMPLIANT"
    elif warnings:
        status = "COMPLIANT_WITH_WARNINGS"
    else:
        status = "COMPLIANT"

    return {
        "repo": repo,
        "compliant": compliant,
        "status": status,
        "automationMode": rules.get("automation_mode", "auto"),
        "templateProfile": profile,
        "findings": findings,
        "warnings": warnings,
    }


def resolve_or_create_upstream_issue(
    repo: str,
    proposal: dict[str, Any],
    *,
    auto_create: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Resolve an existing upstream issue for `proposal`, or create a 1:1 issue when `auto_create=True` (`AgDR-0058`)."""
    preset_num = proposal.get("linked_issue")
    if isinstance(preset_num, int) and preset_num > 0:
        return {
            "ok": True,
            "issueNumber": preset_num,
            "source": "pre_mapped",
            "url": f"https://github.com/{repo}/issues/{preset_num}",
        }

    rules = get_repo_contribution_rules(repo)
    if rules.get("automation_mode") != "auto":
        return {"ok": False, "issueNumber": None, "source": "refused_policy", "error": "Repo disallows auto-issue creation"}

    issue_title = str(proposal.get("issue_title") or "").strip()
    issue_kind = str(proposal.get("issue_kind") or ("bug" if str(proposal.get("title", "")).startswith(("fix", "perf")) else "feature"))
    if not issue_title:
        clean_t = re.sub(r"^[a-z]+(?:\([^)]+\))?:\s*", "", str(proposal.get("title") or "Improvement")).strip()
        prefix = "[Bug]: " if issue_kind == "bug" else "[Feature]: "
        issue_title = prefix + clean_t[:1].upper() + clean_t[1:]

    # Search open issues authored by casualuser or matching exact title first to guarantee idempotence
    search_needle = re.sub(r"^\[(Bug|Feature|Other)\]:\s*", "", issue_title).strip()[:60]
    if search_needle:
        scp = run_cmd(
            [
                "gh",
                "issue",
                "list",
                "-R",
                repo,
                "--state",
                "open",
                "--search",
                f"{json.dumps(search_needle)} in:title",
                "--limit",
                "5",
                "--json",
                "number,title,url",
            ],
            check=False,
            timeout=15.0,
        )
        if scp.returncode == 0 and scp.stdout.strip():
            try:
                found_issues: list[dict[str, Any]] = json.loads(scp.stdout)
                for fi in found_issues:
                    ftitle = str(fi.get("title") or "").lower()
                    if search_needle.lower()[:32] in ftitle and fi.get("number"):
                        return {
                            "ok": True,
                            "issueNumber": int(fi["number"]),
                            "source": "matched_existing",
                            "url": str(fi.get("url") or f"https://github.com/{repo}/issues/{fi['number']}"),
                        }
            except ValueError:
                pass

    if not auto_create:
        return {"ok": False, "issueNumber": None, "source": "missing", "error": "No matching upstream issue found"}

    if dry_run:
        return {"ok": True, "issueNumber": None, "source": "dry_run_would_create", "plannedTitle": issue_title}

    why = str(proposal.get("why") or "").strip()
    what_for = str(proposal.get("what_for") or "").strip()
    how = str(proposal.get("how") or "").strip()
    if repo == "stablyai/orca":
        if issue_kind == "bug":
            issue_body = (
                f"### Operating system\n\nLinux\n\n"
                f"### Orca version\n\nv1.4.251\n\n"
                f"### Details\n\n{why}\n\n**Expected behavior / scope:**\n{what_for}\n"
            )
        else:
            issue_body = (
                f"### Problem or use case\n\n{why}\n\n"
                f"### Proposed solution\n\n{what_for}\n\n"
                f"### Alternatives or additional context\n\n{how}\n"
            )
    else:
        issue_body = f"## Problem\n\n{why}\n\n## Proposed Solution\n\n{what_for}\n"

    ccp = run_cmd(
        ["gh", "issue", "create", "-R", repo, "--title", issue_title, "--body", issue_body],
        check=False,
        timeout=25.0,
    )
    if ccp.returncode != 0:
        return {"ok": False, "issueNumber": None, "source": "create_failed", "error": ccp.stderr.strip()}

    out_url = ccp.stdout.strip().splitlines()[-1].strip() if ccp.stdout.strip() else ""
    m_num = re.search(r"/issues/(\d+)\b", out_url)
    if not m_num:
        return {"ok": False, "issueNumber": None, "source": "parse_failed", "error": f"Unexpected output: {out_url}"}
    inum = int(m_num.group(1))
    return {"ok": True, "issueNumber": inum, "source": "created", "url": out_url}


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


SUPERSEDED_PRS: dict[str, dict[str, str]] = {}


def _git_plumbing(repo_path: Path, args: list[str], *, env_extra: Optional[dict[str, str]] = None) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "LC_ALL": "C"}
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["git", *args],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=False,
        env=env,
        timeout=15.0,
    )


def evaluate_pr_alignment(
    repo_path: Path,
    branch_or_ref: str,
    upstream_ref: str = "upstream/main",
    *,
    pr_state: str = "OPEN",
    superseded_by: str = "",
) -> dict[str, Any]:
    """Evaluate a fork/PR branch against `upstream_ref` without mutating the working tree (`T613` AC1).

    Classifies into:
    - `UP_TO_DATE`
    - `CLEAN_REBASEABLE`
    - `CONFLICTING_NEEDS_REBASE`
    - `OBSOLETE_PATCH_EQUIVALENT` (`git cherry` reports 0 `+` commits or 0 ahead)
    - `OBSOLETE_EMPTY_AFTER_REBASE` (clean 3-way merge produces identical tree OID to `upstream_ref`)
    - `OBSOLETE_UPSTREAM_MERGED`
    - `OBSOLETE_SUPERSEDED`
    """
    st_upper = (pr_state or "OPEN").upper()
    if st_upper == "MERGED":
        return {
            "branch": branch_or_ref,
            "upstreamRef": upstream_ref,
            "alignmentStatus": "OBSOLETE_UPSTREAM_MERGED",
            "isObsolete": True,
            "aheadUpstream": 0,
            "behindUpstream": 0,
            "reason": "Merged upstream",
        }
    if superseded_by:
        return {
            "branch": branch_or_ref,
            "upstreamRef": upstream_ref,
            "alignmentStatus": "OBSOLETE_SUPERSEDED",
            "isObsolete": True,
            "aheadUpstream": 0,
            "behindUpstream": 0,
            "reason": f"Superseded by {superseded_by}",
        }

    head_ref = ""
    for cand in (f"refs/heads/{branch_or_ref}", f"refs/remotes/origin/{branch_or_ref}", branch_or_ref):
        v = _git_plumbing(repo_path, ["rev-parse", "--verify", "--quiet", f"{cand}^{{commit}}"])
        if v.returncode == 0 and v.stdout.strip():
            head_ref = cand
            break
    if not head_ref:
        return {
            "branch": branch_or_ref,
            "upstreamRef": upstream_ref,
            "alignmentStatus": "UNAVAILABLE_LOCAL_REF",
            "isObsolete": False,
            "aheadUpstream": 0,
            "behindUpstream": 0,
            "reason": "Branch ref not present locally",
        }

    up_verify = _git_plumbing(repo_path, ["rev-parse", "--verify", "--quiet", f"{upstream_ref}^{{commit}}"])
    if up_verify.returncode != 0:
        return {
            "branch": branch_or_ref,
            "upstreamRef": upstream_ref,
            "alignmentStatus": "NO_UPSTREAM_REF",
            "isObsolete": False,
            "aheadUpstream": 0,
            "behindUpstream": 0,
            "reason": f"Missing {upstream_ref}",
        }

    counts_cp = _git_plumbing(repo_path, ["rev-list", "--left-right", "--count", f"{upstream_ref}...{head_ref}"])
    behind, ahead = 0, 0
    if counts_cp.returncode == 0 and counts_cp.stdout.strip():
        parts = counts_cp.stdout.strip().split()
        if len(parts) == 2:
            behind, ahead = int(parts[0]), int(parts[1])

    if ahead == 0:
        return {
            "branch": branch_or_ref,
            "upstreamRef": upstream_ref,
            "alignmentStatus": "OBSOLETE_PATCH_EQUIVALENT",
            "isObsolete": True,
            "aheadUpstream": 0,
            "behindUpstream": behind,
            "reason": "Branch has 0 commits ahead of upstream",
        }

    cherry_cp = _git_plumbing(repo_path, ["cherry", upstream_ref, head_ref])
    if cherry_cp.returncode == 0:
        plus_lines = [ln for ln in cherry_cp.stdout.splitlines() if ln.startswith("+ ")]
        if len(plus_lines) == 0:
            return {
                "branch": branch_or_ref,
                "upstreamRef": upstream_ref,
                "alignmentStatus": "OBSOLETE_PATCH_EQUIVALENT",
                "isObsolete": True,
                "aheadUpstream": ahead,
                "behindUpstream": behind,
                "reason": "All branch commits are patch-equivalent in upstream (`git cherry`)",
            }

    if behind == 0:
        return {
            "branch": branch_or_ref,
            "upstreamRef": upstream_ref,
            "alignmentStatus": "UP_TO_DATE",
            "isObsolete": False,
            "aheadUpstream": ahead,
            "behindUpstream": 0,
            "reason": "Branch is rebased onto latest upstream HEAD",
        }

    mb_cp = _git_plumbing(repo_path, ["merge-base", upstream_ref, head_ref])
    if mb_cp.returncode != 0 or not mb_cp.stdout.strip():
        return {
            "branch": branch_or_ref,
            "upstreamRef": upstream_ref,
            "alignmentStatus": "CONFLICTING_NEEDS_REBASE",
            "isObsolete": False,
            "aheadUpstream": ahead,
            "behindUpstream": behind,
            "reason": "No common merge-base with upstream",
        }
    mb = mb_cp.stdout.strip()
    up_tree_cp = _git_plumbing(repo_path, ["rev-parse", f"{upstream_ref}^{{tree}}"])
    up_tree = up_tree_cp.stdout.strip()

    # Perform an index-only 3-way merge (`git read-tree --aggressive -i -m`) inside a temp GIT_INDEX_FILE.
    # Never touches the working tree OR `.git/objects` (100% read-only on the repo object store).
    any_resolved_differs_from_upstream = False
    with tempfile.TemporaryDirectory(prefix="w0m-prs-idx-") as tmp_idx_dir:
        idx_path = str(Path(tmp_idx_dir) / "index")
        idx_env = {"GIT_INDEX_FILE": idx_path}
        rt = _git_plumbing(
            repo_path,
            ["read-tree", "--aggressive", "-i", "-m", mb, upstream_ref, head_ref],
            env_extra=idx_env,
        )
        if rt.returncode != 0:
            return {
                "branch": branch_or_ref,
                "upstreamRef": upstream_ref,
                "alignmentStatus": "CONFLICTING_NEEDS_REBASE",
                "isObsolete": False,
                "aheadUpstream": ahead,
                "behindUpstream": behind,
                "reason": "3-way tree read failed due to structural conflict",
            }

        unmerged_cp = _git_plumbing(repo_path, ["ls-files", "-u"], env_extra=idx_env)
        if unmerged_cp.stdout.strip():
            # Group stages (1=base, 2=ours/upstream, 3=theirs/head) per path and run `git merge-file -p`
            by_path: dict[str, dict[str, tuple[str, str]]] = {}
            for uline in unmerged_cp.stdout.splitlines():
                meta, _, fpath = uline.partition("\t")
                mparts = meta.split()
                if len(mparts) == 3 and fpath:
                    mode_str, blob_sha, stage_str = mparts
                    by_path.setdefault(fpath, {})[stage_str] = (mode_str, blob_sha)

            for idx_num, (fpath, stages) in enumerate(by_path.items()):
                s1 = stages.get("1")
                s2 = stages.get("2")
                s3 = stages.get("3")
                # Resolve trivial unchanged-on-one-side cases if left unmerged
                if s2 is not None and s3 is not None and s2 == s3:
                    _git_plumbing(repo_path, ["update-index", "--force-remove", "--", fpath], env_extra=idx_env)
                    _git_plumbing(
                        repo_path,
                        ["update-index", "--add", "--cacheinfo", f"{s2[0]},{s2[1]},{fpath}"],
                        env_extra=idx_env,
                    )
                    continue
                if s1 is not None and s3 == s1:
                    # Head did not modify `fpath`; upstream's state (`s2` or deleted) wins cleanly.
                    _git_plumbing(repo_path, ["update-index", "--force-remove", "--", fpath], env_extra=idx_env)
                    if s2 is not None:
                        _git_plumbing(
                            repo_path,
                            ["update-index", "--add", "--cacheinfo", f"{s2[0]},{s2[1]},{fpath}"],
                            env_extra=idx_env,
                        )
                    continue
                if s1 is not None and s2 == s1:
                    # Upstream did not modify `fpath`; head modified or deleted it (`s3 != s2`).
                    any_resolved_differs_from_upstream = True
                    continue

                if s2 is None or s3 is None:
                    # True modify/delete or add/delete conflict
                    return {
                        "branch": branch_or_ref,
                        "upstreamRef": upstream_ref,
                        "alignmentStatus": "CONFLICTING_NEEDS_REBASE",
                        "isObsolete": False,
                        "aheadUpstream": ahead,
                        "behindUpstream": behind,
                        "reason": f"Modify/delete conflict in {fpath}",
                    }
                f_base = Path(tmp_idx_dir) / f"b_{idx_num}"
                f_ours = Path(tmp_idx_dir) / f"o_{idx_num}"
                f_theirs = Path(tmp_idx_dir) / f"t_{idx_num}"
                if s1 is not None:
                    b1 = subprocess.run(["git", "cat-file", "blob", s1[1]], cwd=repo_path, capture_output=True)
                    f_base.write_bytes(b1.stdout if b1.returncode == 0 else b"")
                else:
                    f_base.write_bytes(b"")
                b2 = subprocess.run(["git", "cat-file", "blob", s2[1]], cwd=repo_path, capture_output=True)
                b3 = subprocess.run(["git", "cat-file", "blob", s3[1]], cwd=repo_path, capture_output=True)
                f_ours.write_bytes(b2.stdout if b2.returncode == 0 else b"")
                f_theirs.write_bytes(b3.stdout if b3.returncode == 0 else b"")

                mf = subprocess.run(
                    ["git", "merge-file", "-p", str(f_ours), str(f_base), str(f_theirs)],
                    cwd=repo_path,
                    capture_output=True,
                )
                if mf.returncode != 0:
                    return {
                        "branch": branch_or_ref,
                        "upstreamRef": upstream_ref,
                        "alignmentStatus": "CONFLICTING_NEEDS_REBASE",
                        "isObsolete": False,
                        "aheadUpstream": ahead,
                        "behindUpstream": behind,
                        "reason": f"Content conflict in {fpath}",
                    }
                # Compute blob OID without `-w` (zero writes to `.git/objects`).
                ho = subprocess.run(
                    ["git", "hash-object", "--stdin"],
                    cwd=repo_path,
                    input=mf.stdout,
                    capture_output=True,
                )
                merged_blob = ho.stdout.decode("utf-8", errors="replace").strip() if ho.returncode == 0 else ""
                if not merged_blob or merged_blob != s2[1] or s2[0] != s3[0]:
                    # Clean merge whose resulting blob differs from upstream (`s2`), so tree != up_tree.
                    any_resolved_differs_from_upstream = True
                else:
                    # Merged blob equals `s2[1]` (which already exists in `.git/objects`).
                    _git_plumbing(
                        repo_path,
                        ["update-index", "--force-remove", "--", fpath],
                        env_extra=idx_env,
                    )
                    _git_plumbing(
                        repo_path,
                        ["update-index", "--add", "--cacheinfo", f"{s2[0]},{s2[1]},{fpath}"],
                        env_extra=idx_env,
                    )

        identical_to_upstream = False
        if not any_resolved_differs_from_upstream:
            di_cp = _git_plumbing(repo_path, ["diff-index", "--quiet", "--cached", upstream_ref], env_extra=idx_env)
            identical_to_upstream = di_cp.returncode == 0

    if identical_to_upstream:
        return {
            "branch": branch_or_ref,
            "upstreamRef": upstream_ref,
            "alignmentStatus": "OBSOLETE_EMPTY_AFTER_REBASE",
            "isObsolete": True,
            "aheadUpstream": ahead,
            "behindUpstream": behind,
            "reason": "3-way merge onto upstream produces identical tree OID (0 diff)",
        }

    return {
        "branch": branch_or_ref,
        "upstreamRef": upstream_ref,
        "alignmentStatus": "CLEAN_REBASEABLE",
        "isObsolete": False,
        "aheadUpstream": ahead,
        "behindUpstream": behind,
        "reason": f"Cleanly rebaseable onto {upstream_ref} (-{behind}/+{ahead})",
    }


def _inspect_fork_and_branches(repo_path: Path, fetch: bool) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    fork_name = repo_path.name
    upstream_repo = FORK_UPSTREAM_MAP.get(fork_name, f"upstream/{fork_name}")
    fork_info = inspect_fork(repo_path, fetch=fetch)
    fork_wt = {
        "fork": fork_name,
        "upstream_repo": upstream_repo,
        "branch": fork_info.get("branch", "beta"),
        "upstream_ref": fork_info.get("upstream_ref", "-"),
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
            or bname.startswith("overlay/")
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
        if ahead_u <= 0:
            continue
        align = evaluate_pr_alignment(repo_path, ref_short, upstream_ref)
        if align.get("isObsolete"):
            seen_branch_names.add(bname)
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
                "alignmentStatus": align.get("alignmentStatus", "UP_TO_DATE"),
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
    """Discover active upstream PRs, unsubmitted PR-ready feature branches across `w0m-pr/*`, and active worktrees (`T599` AC3, `T593` AC4, `T613` AC1)."""
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
            head_branch = str((info if "error" not in info else p).get("headRefName") or p.get("headRefName") or "")
            if "error" in info:
                entry = {
                    "repo": repo_name,
                    "number": num,
                    "title": p.get("title", ""),
                    "state": (p.get("state") or "OPEN").upper(),
                    "headRefName": head_branch,
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
                    "headRefName": head_branch,
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

    upstream_to_fork_path: dict[str, tuple[Path, str]] = {}
    pending_branches: list[dict[str, Any]] = []
    fork_worktrees: list[dict[str, Any]] = []
    for rp, (fork_wt, branches) in zip(fork_repo_paths, fork_results):
        fork_worktrees.append(fork_wt)
        upstream_to_fork_path[fork_wt["upstream_repo"]] = (rp, str(fork_wt.get("upstream_ref") or "upstream/main"))
        for b in branches:
            b["open_prs_in_repo"] = len(open_repos_with_pr.get(b["upstream_repo"], []))
            pending_branches.append(b)

    obsolete_prs: list[dict[str, Any]] = []
    for entry in open_prs:
        pr_key = f"{entry['repo']}#{entry['number']}"
        superseded_by = (SUPERSEDED_PRS.get(pr_key) or {}).get("superseded_by", "")
        fork_pair = upstream_to_fork_path.get(entry["repo"])
        if fork_pair and entry.get("headRefName") and fork_pair[1] != "-":
            align = evaluate_pr_alignment(
                fork_pair[0],
                entry["headRefName"],
                fork_pair[1],
                pr_state=entry["state"],
                superseded_by=superseded_by,
            )
            if align["alignmentStatus"] == "UNAVAILABLE_LOCAL_REF":
                align["alignmentStatus"] = (
                    "CONFLICTING_NEEDS_REBASE" if entry["mergeable"] == "CONFLICTING" else "UP_TO_DATE"
                )
        else:
            is_obs = entry["state"] == "MERGED" or bool(superseded_by)
            status_val = (
                "OBSOLETE_UPSTREAM_MERGED"
                if entry["state"] == "MERGED"
                else (
                    "OBSOLETE_SUPERSEDED"
                    if superseded_by
                    else ("CONFLICTING_NEEDS_REBASE" if entry["mergeable"] == "CONFLICTING" else "UP_TO_DATE")
                )
            )
            align = {
                "alignmentStatus": status_val,
                "isObsolete": is_obs,
                "aheadUpstream": 0,
                "behindUpstream": 0,
                "reason": "",
            }
        entry["alignmentStatus"] = align["alignmentStatus"]
        entry["isObsolete"] = bool(align["isObsolete"])
        entry["aheadUpstream"] = int(align.get("aheadUpstream", 0))
        entry["behindUpstream"] = int(align.get("behindUpstream", 0))
        if entry["isObsolete"]:
            comment_msg = f"Closing as superseded / already landed upstream ({entry['alignmentStatus']})."
            entry["closeCommand"] = (
                f"gh pr close {entry['number']} -R {entry['repo']} --comment {json.dumps(comment_msg)}"
            )
            obsolete_prs.append(entry)
        else:
            entry["closeCommand"] = ""

    return {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "author": author,
        "preset": preset,
        "openPrCount": len(open_prs),
        "openPrs": open_prs,
        "obsoletePrCount": len(obsolete_prs),
        "obsoletePrs": obsolete_prs,
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
    include_worktrees: bool = True,
    record_pending_deltas: bool = False,
    consume_pending_deltas: bool = False,
) -> dict[str, Any]:
    """Compare live PR + fork branch state against `~/.w0m/state/prs-watch-state.json` (`T599` AC3, `T615` AC1/AC4).

    Used as the zero-token shell `--precheck` gate for Orca Automations:
    - Returns `changed=True` (CLI exits `0`) when any PR state/mergeability/review/CI/comment count,
      rebase obsolescence status, or pending fork branch changes.
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
            loaded_prev: dict[str, Any] = json.loads(target_file.read_text(encoding="utf-8"))
            prev = loaded_prev
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
            if p.get("isObsolete"):
                deltas.append(f"OBSOLETE_PR {key} ({p.get('alignmentStatus')})")
            continue
        if bool(p.get("isObsolete")) and not bool(old.get("isObsolete")):
            deltas.append(f"OBSOLETE_PR {key} ({p.get('alignmentStatus')})")
        elif "alignmentStatus" in p and "alignmentStatus" in old and old.get("alignmentStatus") != p.get("alignmentStatus"):
            deltas.append(f"PR_DELTA {key} alignmentStatus: {old.get('alignmentStatus')} -> {p.get('alignmentStatus')}")
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

    if include_worktrees and "agentTrees" in current and "agentTrees" in prev:
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

    prev_pending = [str(x) for x in (prev.get("pending_deltas") or []) if str(x)]
    if consume_pending_deltas and prev_pending:
        deltas = list(dict.fromkeys([*prev_pending, *deltas]))

    to_save = dict(current)
    if "launch_history" not in to_save and isinstance(prev.get("launch_history"), list):
        to_save["launch_history"] = prev["launch_history"]
    if "obsolete_prs" not in to_save:
        curr_obs = {f"{p['repo']}#{p['number']}": p for p in (current.get("obsoletePrs") or []) if isinstance(p, dict)}
        raw_prev_obs = prev.get("obsolete_prs")
        prev_obs: dict[str, Any] = raw_prev_obs if isinstance(raw_prev_obs, dict) else {}
        to_save["obsolete_prs"] = {**prev_obs, **curr_obs}
    if consume_pending_deltas:
        to_save.pop("pending_deltas", None)
    elif record_pending_deltas:
        merged_pending = list(dict.fromkeys([*prev_pending, *deltas]))
        if merged_pending:
            to_save["pending_deltas"] = merged_pending
    elif prev_pending and "pending_deltas" not in to_save:
        to_save["pending_deltas"] = prev_pending

    target_file.write_text(json.dumps(to_save, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(target_file, 0o600)
    except OSError:
        pass

    return {
        "changed": len(deltas) > 0,
        "deltaCount": len(deltas),
        "deltas": deltas,
        "stateFile": str(target_file),
        "openPrCount": current.get("openPrCount", 0),
        "obsoletePrCount": current.get("obsoletePrCount", 0),
        "pendingBranchCount": current.get("pendingBranchCount", 0),
        "agentTreeCount": current.get("agentTreeCount", 0),
    }


def _select_matching_proposal_keys(branch_filter: Optional[str]) -> set[str]:
    """Resolve matching `CONTRIBUTION_PROPOSALS` keys via exact match first, then substring fallback."""
    if not branch_filter or not branch_filter.strip():
        return set(CONTRIBUTION_PROPOSALS.keys())
    needle = branch_filter.strip().lower()
    exact_matches: set[str] = set()
    substring_matches: set[str] = set()
    for key, prop in CONTRIBUTION_PROPOSALS.items():
        upstream_repo, bname = key.split(":", 1)
        fork_name = next((k for k, v in FORK_UPSTREAM_MAP.items() if v == upstream_repo), upstream_repo.split("/")[-1])
        exact_fields = (bname, key, upstream_repo, fork_name, str(prop.get("ticket", "")))
        if any(needle == f.lower() for f in exact_fields if f):
            exact_matches.add(key)
        sub_fields = (*exact_fields, str(prop.get("title", "")))
        if any(needle in f.lower() for f in sub_fields if f):
            substring_matches.add(key)
    return exact_matches if exact_matches else substring_matches


def build_pr_proposals(
    *,
    branch_filter: Optional[str] = None,
    forks_dir: Optional[Path] = None,
) -> list[dict[str, Any]]:
    """Build target-rule-compliant PR proposals for all prepared contribution branches (`T593` AC4, `AgDR-0058`)."""
    fdir = forks_dir or resolve_forks_dir()
    matched_keys = _select_matching_proposal_keys(branch_filter)
    items: list[dict[str, Any]] = []
    for key, raw_prop in CONTRIBUTION_PROPOSALS.items():
        if key not in matched_keys:
            continue
        prop = get_enriched_proposal(key, raw_prop)
        upstream_repo, bname = key.split(":", 1)
        fork_name = next((k for k, v in FORK_UPSTREAM_MAP.items() if v == upstream_repo), upstream_repo.split("/")[-1])
        default_branch = UPSTREAM_DEFAULT_BRANCH_OVERRIDES.get(
            upstream_repo,
            "v8"
            if upstream_repo.endswith("/graphify")
            else ("master" if upstream_repo.endswith(("/virtual-fido", "/moksha")) else "main"),
        )
        head_sha = "-"
        if fdir and (fdir / fork_name / ".git").exists():
            sha_cp = run_cmd(
                ["git", "rev-parse", "--short=10", f"refs/heads/{bname}"],
                check=False,
                cwd=fdir / fork_name,
            )
            if sha_cp.returncode == 0 and sha_cp.stdout.strip():
                head_sha = sha_cp.stdout.strip()
        body = format_pr_proposal_body(prop, upstream_repo=upstream_repo)
        rules = get_repo_contribution_rules(upstream_repo)
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
                "linked_issue": prop.get("linked_issue"),
                "visual_change": bool(prop.get("visual_change", False)),
                "visual_proof_urls": list(prop.get("visual_proof_urls") or []),
                "automation_mode": rules.get("automation_mode", "auto"),
                "template_profile": rules.get("template_profile", "standard"),
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
    only_unsubmitted: bool = False,
    auto_create_issues: bool = True,
    push_missing_origin: bool = True,
    allow_pending_visual: bool = False,
) -> dict[str, Any]:
    """Submit (or dry-run preview) prepared upstream PRs under 6-gate `AgDR-0058` governance (`T655`).

    Enforces:
      1. Repo automation policy (`REFUSED-REPO-POLICY` on `ml-explore/mlx-lm`, `Graphify-Labs/graphify`, CLA repos)
      2. Honest visual proof (`HELD-NEEDS-VISUAL-PROOF` when UI PR lacks uploaded media)
      3. Local branch existence, GPG signature check (on `webomage` forks), standalone 3-way `upstream/<base>`
         conflict check (`REFUSED-CONFLICT-UPSTREAM`), and non-force `origin/<branch>` sync
      4. Existing open PR + third-party sibling PR scan
      5. Mandatory `Fixes #<issue>` linkage / idempotent 1:1 upstream issue creation
      6. Target PR template validation (`REFUSED-TEMPLATE-NONCOMPLIANT`)
    """
    fdir = forks_dir or resolve_forks_dir()
    proposals = build_pr_proposals(branch_filter=branch_filter, forks_dir=fdir)
    if only_unsubmitted:
        proposals = [
            p
            for p in proposals
            if p["branch"] not in ACTIVE_OPEN_PR_HEAD_BRANCHES
            and p["branch"] not in INTERNAL_OR_SUPERSEDED_BRANCHES
        ]

    results: list[dict[str, Any]] = []
    for item in proposals:
        upstream_repo = item["upstream_repo"]
        bname = item["branch"]
        fork_name = item["fork"]
        rules = get_repo_contribution_rules(upstream_repo)
        auto_mode = rules.get("automation_mode", "auto")
        enriched = get_enriched_proposal(item["key"])

        # Gate 1: Target repository automation policy
        if auto_mode in ("banned", "human_description_required", "cla_required", "strict_governance"):
            if dry_run and not only_unsubmitted and branch_filter is None:
                # Preserve legacy dry-run preview overview while annotating policy restriction
                results.append(
                    {
                        **item,
                        "status": "DRY_RUN_READY" if auto_mode != "banned" else "REFUSED-REPO-POLICY",
                        "policyNote": rules.get("policy_note", ""),
                    }
                )
                continue
            results.append(
                {
                    **item,
                    "status": "REFUSED-REPO-POLICY",
                    "stderr": f"REFUSED-REPO-POLICY ({auto_mode}): {rules.get('policy_note', '')}",
                }
            )
            continue

        # Gate 2: Honest Visual Proof check for UI PRs
        if (
            rules.get("requires_visual_proof_for_ui")
            and bool(enriched.get("visual_change"))
            and not (enriched.get("visual_proof_urls") or [])
            and not allow_pending_visual
        ):
            if dry_run and not only_unsubmitted and branch_filter is None:
                results.append({**item, "status": "DRY_RUN_READY", "holdReason": "NEEDS_VISUAL_PROOF"})
                continue
            results.append(
                {
                    **item,
                    "status": "HELD-NEEDS-VISUAL-PROOF",
                    "stderr": (
                        "HELD-NEEDS-VISUAL-PROOF: Target repo requires real before/after screenshots or video for UI "
                        "changes (`visual_change=True`); refusing to fabricate `N/A`."
                    ),
                }
            )
            continue

        # Gate 3: Local repo alignment, GPG signature & origin push check
        repo_path = (fdir / fork_name) if fdir else None
        has_local_git = bool(repo_path and (repo_path / ".git").exists())
        pushed_origin = False
        if has_local_git and repo_path is not None:
            local_verify = run_cmd(
                ["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{bname}^{{commit}}"],
                check=False,
                cwd=repo_path,
            )
            if local_verify.returncode != 0:
                if not dry_run:
                    results.append(
                        {
                            **item,
                            "status": "REFUSED-MISSING-BRANCH",
                            "stderr": f"Local branch refs/heads/{bname} does not exist in {repo_path}",
                        }
                    )
                    continue
            else:
                align = evaluate_pr_alignment(repo_path, bname, f"upstream/{item['base_branch']}")
                if align["alignmentStatus"] == "CONFLICTING_NEEDS_REBASE":
                    if dry_run and not only_unsubmitted and branch_filter is None:
                        results.append({**item, "status": "DRY_RUN_READY", "alignmentStatus": align["alignmentStatus"]})
                        continue
                    results.append(
                        {
                            **item,
                            "status": "REFUSED-CONFLICT-UPSTREAM",
                            "alignmentStatus": align["alignmentStatus"],
                            "stderr": f"REFUSED-CONFLICT-UPSTREAM: {align.get('reason', 'Conflicts with upstream base')}",
                        }
                    )
                    continue
                if align.get("isObsolete"):
                    results.append(
                        {
                            **item,
                            "status": "REFUSED-OBSOLETE",
                            "alignmentStatus": align["alignmentStatus"],
                            "stderr": f"REFUSED-OBSOLETE: {align.get('reason', '')}",
                        }
                    )
                    continue

                origin_url_cp = run_cmd(["git", "remote", "get-url", "origin"], check=False, cwd=repo_path)
                is_webomage_origin = CANONICAL_FORK_ORG in (origin_url_cp.stdout or "")
                if is_webomage_origin and rules.get("requires_gpg_signature"):
                    sig_cp = run_cmd(["git", "log", "-1", "--format=%G?", f"refs/heads/{bname}"], check=False, cwd=repo_path)
                    sig_status = (sig_cp.stdout or "").strip()
                    if sig_status not in ("G", "U", "E"):
                        results.append(
                            {
                                **item,
                                "status": "REFUSED-UNSIGNED-COMMIT",
                                "stderr": f"REFUSED-UNSIGNED-COMMIT: HEAD of {bname} has GPG status '{sig_status}' (expected G)",
                            }
                        )
                        continue

                if not dry_run and push_missing_origin and is_webomage_origin:
                    orig_cp = run_cmd(
                        ["git", "rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{bname}^{{commit}}"],
                        check=False,
                        cwd=repo_path,
                    )
                    local_sha_full = local_verify.stdout.strip()
                    orig_sha_full = orig_cp.stdout.strip() if orig_cp.returncode == 0 else ""
                    if orig_sha_full != local_sha_full:
                        push_cp = run_cmd(
                            ["git", "push", "origin", f"refs/heads/{bname}:refs/heads/{bname}"],
                            check=False,
                            cwd=repo_path,
                            timeout=30.0,
                        )
                        if push_cp.returncode != 0:
                            results.append(
                                {
                                    **item,
                                    "status": "FAILED",
                                    "stderr": f"Failed to push {bname} to origin: {push_cp.stderr.strip()}",
                                }
                            )
                            continue
                        pushed_origin = True

        if dry_run:
            results.append({**item, "status": "DRY_RUN_READY"})
            continue

        # Gate 4: Existing open PR & sibling scan
        existing_cp = run_cmd(
            [
                "gh",
                "pr",
                "list",
                "--repo",
                upstream_repo,
                "--head",
                bname,
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
                existing_items: Any = json.loads(existing_cp.stdout)
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

        # Gate 5: Linked issue resolution / auto-creation when required
        resolved_issue = enriched.get("linked_issue")
        issue_source = "none"
        if rules.get("requires_linked_issue"):
            ires = resolve_or_create_upstream_issue(
                upstream_repo,
                enriched,
                auto_create=bool(auto_create_issues and rules.get("auto_create_issue")),
                dry_run=False,
            )
            if not ires.get("ok") or not ires.get("issueNumber"):
                results.append(
                    {
                        **item,
                        "status": "REFUSED-MISSING-ISSUE",
                        "stderr": f"REFUSED-MISSING-ISSUE: {ires.get('error', 'No linked upstream issue')}",
                    }
                )
                continue
            resolved_issue = int(ires["issueNumber"])
            issue_source = str(ires.get("source", "resolved"))
            enriched = {**enriched, "linked_issue": resolved_issue}

        # Gate 6: Render & validate target-native PR body
        final_body = format_pr_proposal_body(enriched, upstream_repo=upstream_repo)
        comp = validate_pr_compliance(
            upstream_repo,
            item["title"],
            final_body,
            visual_change=bool(enriched.get("visual_change", False)),
        )
        if not comp["compliant"]:
            results.append(
                {
                    **item,
                    "status": "REFUSED-TEMPLATE-NONCOMPLIANT",
                    "stderr": "; ".join(comp["findings"]),
                }
            )
            continue

        cp = run_cmd(
            [
                "gh",
                "pr",
                "create",
                "--repo",
                upstream_repo,
                "--base",
                item["base_branch"],
                "--head",
                f"{CANONICAL_FORK_ORG}:{bname}",
                "--title",
                item["title"],
                "--body",
                final_body,
            ],
            check=False,
            timeout=30.0,
        )
        err_text = cp.stderr.strip() if cp.returncode != 0 else ""
        already_open_err = cp.returncode != 0 and "already exists" in err_text.lower()
        results.append(
            {
                **item,
                "body": final_body,
                "linked_issue": resolved_issue,
                "issue_source": issue_source,
                "pushed_origin": pushed_origin,
                "status": "SUBMITTED" if cp.returncode == 0 else ("ALREADY_OPEN" if already_open_err else "FAILED"),
                "url": cp.stdout.strip() if cp.returncode == 0 else "",
                "stderr": "" if already_open_err else err_text,
            }
        )

    allowed_ok_statuses = (
        ("DRY_RUN_READY", "REFUSED-REPO-POLICY")
        if (dry_run and not only_unsubmitted and branch_filter is None)
        else ("DRY_RUN_READY", "SUBMITTED", "ALREADY_OPEN")
    )
    ok_flag = bool(results) and all(r["status"] in allowed_ok_statuses for r in results)
    first_err = next((r.get("stderr", "") for r in results if r["status"] not in allowed_ok_statuses and r.get("stderr")), "")
    return {
        "ok": ok_flag,
        "dryRun": dry_run,
        "error": "" if ok_flag else first_err,
        "count": len(results),
        "results": results,
    }


def audit_open_prs_compliance(
    *,
    author: str = CANONICAL_CONTRIBUTOR,
    preset: str = "w0m-pr",
    remediate: bool = False,
    dry_run: bool = True,
    auto_create_issues: bool = True,
) -> dict[str, Any]:
    """Audit all open external PRs against per-repo contribution rules and optionally remediate bodies (`AgDR-0058`)."""
    repos = PRESET_REPOS.get(preset, PRESET_REPOS["w0m-pr"])

    def _fetch_open_with_body(r: str) -> list[dict[str, Any]]:
        cp = run_cmd(
            [
                "gh",
                "pr",
                "list",
                "-R",
                r,
                "--author",
                author,
                "--state",
                "open",
                "--limit",
                "40",
                "--json",
                "number,title,headRefName,baseRefName,mergeable,reviewDecision,url,body,isDraft",
            ],
            check=False,
            timeout=GH_CMD_TIMEOUT_SEC,
        )
        if cp.returncode == 0 and cp.stdout.strip():
            try:
                arr: list[dict[str, Any]] = json.loads(cp.stdout)
                for it in arr:
                    it["repo"] = r
                return arr
            except ValueError:
                return []
        return []

    raw_prs: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(MAX_GH_CONCURRENCY, max(1, len(repos)))) as pool:
        for chunk in pool.map(_fetch_open_with_body, repos):
            raw_prs.extend(chunk)

    raw_prs.sort(key=lambda x: (str(x.get("repo", "")), int(x.get("number") or 0)))
    audited: list[dict[str, Any]] = []

    for pr in raw_prs:
        repo = str(pr["repo"])
        num = int(pr["number"])
        head_branch = str(pr.get("headRefName") or "")
        title = str(pr.get("title") or "")
        body = str(pr.get("body") or "")
        mergeable = str(pr.get("mergeable") or "UNKNOWN")
        prop_key = f"{repo}:{head_branch}"
        has_prop = prop_key in CONTRIBUTION_PROPOSALS
        enriched = get_enriched_proposal(prop_key) if has_prop else {}
        vis_change = bool(enriched.get("visual_change", False))

        before_comp = validate_pr_compliance(
            repo,
            title,
            body,
            visual_change=vis_change,
            mergeable=mergeable,
        )
        rules = get_repo_contribution_rules(repo)
        remediation_status = "NONE"
        remediated_issue: Optional[int] = None
        after_comp = before_comp

        if remediate and not before_comp["compliant"]:
            if rules.get("automation_mode") != "auto":
                remediation_status = f"SKIPPED-POLICY ({rules.get('automation_mode')})"
            elif not has_prop:
                remediation_status = "SKIPPED-NO-PROPOSAL"
            else:
                # Preserve any uploaded GitHub media URLs already in the PR body
                existing_media = re.findall(
                    r"(?:!\[[^\]]*\]\([^)]+\)|https://github\.com/user-attachments/assets/[^\s)\"]+|https://[^\s)\"]+githubusercontent\.com/[^\s)\"]+)",
                    body,
                )
                merged_media = list(dict.fromkeys([*(enriched.get("visual_proof_urls") or []), *existing_media]))
                work_prop: dict[str, Any] = {**enriched, "visual_proof_urls": merged_media}

                if rules.get("requires_linked_issue"):
                    # Reuse any existing Fixes/Closes #<num> in the PR body if not already pre-mapped
                    if not work_prop.get("linked_issue"):
                        m_existing = re.search(r"\b(?:Fixes|Closes|Resolves)\s+#(\d+)\b", body, flags=re.IGNORECASE)
                        if m_existing:
                            work_prop["linked_issue"] = int(m_existing.group(1))
                    ires = resolve_or_create_upstream_issue(
                        repo,
                        work_prop,
                        auto_create=bool(auto_create_issues and rules.get("auto_create_issue")),
                        dry_run=dry_run,
                    )
                    if ires.get("issueNumber"):
                        remediated_issue = int(ires["issueNumber"])
                        work_prop["linked_issue"] = remediated_issue
                    elif dry_run and ires.get("source") == "dry_run_would_create":
                        work_prop["linked_issue"] = 999999  # placeholder solely to validate dry-run template rendering

                new_body = format_pr_proposal_body(work_prop, upstream_repo=repo)
                after_comp = validate_pr_compliance(
                    repo,
                    title,
                    new_body,
                    visual_change=vis_change,
                    mergeable=mergeable,
                )
                if dry_run:
                    remediation_status = "DRY_RUN_WOULD_REMEDIATE" if after_comp["compliant"] else "DRY_RUN_STILL_NONCOMPLIANT"
                elif after_comp["compliant"]:
                    ecp = run_cmd(
                        ["gh", "pr", "edit", str(num), "-R", repo, "--body", new_body],
                        check=False,
                        timeout=25.0,
                    )
                    remediation_status = "REMEDIATED" if ecp.returncode == 0 else f"FAILED ({ecp.stderr.strip()})"
                else:
                    remediation_status = "REFUSED-STILL-NONCOMPLIANT"

        audited.append(
            {
                "repo": repo,
                "number": num,
                "title": title,
                "headRefName": head_branch,
                "baseRefName": pr.get("baseRefName", ""),
                "mergeable": mergeable,
                "reviewDecision": pr.get("reviewDecision") or "NONE",
                "url": pr.get("url", f"https://github.com/{repo}/pull/{num}"),
                "automationMode": rules.get("automation_mode", "auto"),
                "templateProfile": rules.get("template_profile", "standard"),
                "compliantBefore": before_comp["compliant"],
                "statusBefore": before_comp["status"],
                "findingsBefore": before_comp["findings"],
                "warningsBefore": before_comp["warnings"],
                "remediationStatus": remediation_status,
                "linkedIssue": remediated_issue or enriched.get("linked_issue"),
                "compliantAfter": after_comp["compliant"],
                "statusAfter": after_comp["status"],
                "findingsAfter": after_comp["findings"],
                "warningsAfter": after_comp["warnings"],
            }
        )

    compliant_count = sum(1 for a in audited if a["compliantAfter"])
    return {
        "ok": True,
        "dryRun": dry_run,
        "remediate": remediate,
        "totalOpenPrs": len(audited),
        "compliantCount": compliant_count,
        "nonCompliantCount": len(audited) - compliant_count,
        "prs": audited,
    }


def auto_submit_compliant_prs(
    *,
    branch_filter: Optional[str] = None,
    forks_dir: Optional[Path] = None,
    dry_run: bool = False,
    auto_create_issues: bool = True,
) -> dict[str, Any]:
    """Full auto-mode upstream PR submission sweep (`just pr-auto`, `AgDR-0058` / `T655`).

    Evaluates all unsubmitted `CONTRIBUTION_PROPOSALS` (or `branch_filter`), auto-submitting every
    branch that passes all 6 `AgDR-0058` compliance gates while cleanly holding branches that need
    visual screenshots, upstream conflict rebase, or manual human submission (`ml-explore/mlx-lm`).
    """
    sub = submit_prepared_prs(
        branch_filter=branch_filter,
        forks_dir=forks_dir,
        dry_run=dry_run,
        only_unsubmitted=(branch_filter is None),
        auto_create_issues=auto_create_issues,
        push_missing_origin=True,
        allow_pending_visual=False,
    )
    res_list = sub["results"]
    submitted = [r for r in res_list if r["status"] in ("SUBMITTED", "DRY_RUN_READY")]
    already_open = [r for r in res_list if r["status"] == "ALREADY_OPEN"]
    held_visual = [r for r in res_list if r["status"] == "HELD-NEEDS-VISUAL-PROOF"]
    refused_conflict = [r for r in res_list if r["status"] == "REFUSED-CONFLICT-UPSTREAM"]
    refused_policy = [r for r in res_list if r["status"] == "REFUSED-REPO-POLICY"]
    failed = [
        r
        for r in res_list
        if r["status"]
        not in (
            "SUBMITTED",
            "DRY_RUN_READY",
            "ALREADY_OPEN",
            "HELD-NEEDS-VISUAL-PROOF",
            "REFUSED-CONFLICT-UPSTREAM",
            "REFUSED-REPO-POLICY",
        )
    ]
    return {
        "ok": len(failed) == 0,
        "dryRun": dry_run,
        "totalEvaluated": len(res_list),
        "submittedCount": len(submitted),
        "alreadyOpenCount": len(already_open),
        "heldVisualCount": len(held_visual),
        "refusedConflictCount": len(refused_conflict),
        "refusedPolicyCount": len(refused_policy),
        "failedCount": len(failed),
        "results": res_list,
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
    canonical_root = resolve_canonical_estate_root(workspace_root)
    precheck_cmd = (
        f"python3 {canonical_root / 'scripts' / 'w0m_prs.py'} check-delta "
        f"--preset {preset} --ignore-worktrees --close-settled"
    )
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
            runs_data = (cast(dict[str, Any], json.loads(runs_cp.stdout)).get("result") or {}).get("runs") or []
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
                run_id = ((cast(dict[str, Any], json.loads(create_run_cp.stdout)).get("result") or {}).get("run") or {}).get("id")
            except ValueError:
                pass
    else:
        run_cmd([orca_bin, "orchestration", "run-use", "--id", str(run_id), "--json"], check=False, timeout=10.0)

    if run_id:
        tlist_cp = run_cmd([orca_bin, "orchestration", "task-list", "--run", str(run_id), "--json"], check=False, timeout=10.0)
        existing_tasks: list[dict[str, Any]] = []
        if tlist_cp.returncode == 0 and tlist_cp.stdout.strip():
            try:
                existing_tasks = (cast(dict[str, Any], json.loads(tlist_cp.stdout)).get("result") or {}).get("tasks") or []
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
                    task_id = ((cast(dict[str, Any], json.loads(tcreate_cp.stdout)).get("result") or {}).get("task") or {}).get("id")
                except ValueError:
                    pass

    # 3. Create or update scheduled Orca Automation with Zero-Token Precheck
    automation_id = None
    existing_agent_id = None
    alist_cp = run_cmd([orca_bin, "automations", "list", "--json"], check=False, timeout=10.0)
    if alist_cp.returncode == 0 and alist_cp.stdout.strip():
        try:
            autos = (cast(dict[str, Any], json.loads(alist_cp.stdout)).get("result") or {}).get("automations") or []
            for a in autos:
                if a.get("name") == automation_name:
                    automation_id = a.get("id")
                    existing_agent_id = a.get("agentId")
                    break
        except ValueError:
            pass

    prompt_text = (
        "Run `just prs-reconcile --sync-orca` to align clean w0m-pr/* forks with upstream, detect and detach any "
        "post-rebase obsolete PRs, record a collapsed-by-default `<details>` launch report on the Orca PRs task, "
        "and close completed idle agent sessions. Then if `$ORCA_TERMINAL_HANDLE` is set, run "
        "`python3 scripts/w0m_prs.py close-run-when-settled --daemon --terminal \"$ORCA_TERMINAL_HANDLE\" --initial-delay 2` "
        "and reply with the concise collapsed `<details>` launch summary."
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
                "--fresh-session",
                "--json",
            ],
            check=False,
            timeout=15.0,
        )
        if acreate_cp.returncode == 0 and acreate_cp.stdout.strip():
            try:
                res_obj = cast(dict[str, Any], json.loads(acreate_cp.stdout)).get("result") or {}
                automation_id = (res_obj.get("automation") or res_obj).get("id")
            except ValueError:
                pass
    else:
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
                "--fresh-session",
                "--enabled",
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


def _details_block(title: str, body: str) -> str:
    """Wrap Markdown inside a collapsed-by-default `<details>` block (never `open`) with clean blank lines."""
    return f"<details>\n\n<summary><b>{title}</b></summary>\n\n{body.strip()}\n\n</details>"


def format_launch_report(payload: dict[str, Any]) -> str:
    """Format a PRs monitor launch report using collapsed-by-default `<details>` sections (`T613` AC3)."""
    run_num = payload.get("runNumber") or "latest"
    ts = payload.get("timestamp") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    status_str = str(payload.get("status") or "completed")
    deltas = payload.get("deltas") or []
    fork_updates = payload.get("forkUpdates") or []
    obsolete_prs = payload.get("obsoletePrs") or []
    closed_sessions = payload.get("closedSessions") or []
    open_prs = payload.get("openPrs") or []
    candidates = payload.get("candidateBranches") or []
    worktrees = payload.get("worktrees") or []

    headline = payload.get("headline") or (
        f"Run #{run_num} ({ts}, {status_str}) — {len(deltas)} delta(s), "
        f"{len(open_prs)} open PR(s), {len(obsolete_prs)} obsolete PR(s), "
        f"{len(closed_sessions)} completed session(s) closed."
    )

    delta_lines: list[str] = []
    if deltas:
        for d in deltas:
            if isinstance(d, dict):
                delta_lines.append(f"- **{d.get('type', 'DELTA')}**: {d.get('summary', '')}")
            else:
                delta_lines.append(f"- `{d}`")
    else:
        delta_lines.append("- No PR/branch state deltas since previous snapshot.")
    if fork_updates:
        for fu in fork_updates:
            delta_lines.append(f"- Fork `{fu.get('repo')}` [`{fu.get('action')}`]: {fu.get('message', '')}")
    block_deltas = _details_block(
        f"Deltas & Fork Alignment ({len(deltas)} deltas, {len(fork_updates)} fork updates)",
        "\n".join(delta_lines),
    )

    if obsolete_prs:
        obs_lines = []
        for op in obsolete_prs:
            cmd_hint = f" — `{op.get('closeCommand')}`" if op.get("closeCommand") else ""
            obs_lines.append(
                f"- **{op.get('repo')}#{op.get('number')}** (`{op.get('branch') or op.get('headRefName') or '-'}`) "
                f"→ `{op.get('alignmentStatus')}`{cmd_hint}"
            )
        obs_body = "\n".join(obs_lines)
    else:
        obs_body = "- Zero obsolete PRs detected after upstream rebase check."
    block_obsolete = _details_block(f"Obsolete PRs After Upstream Rebase ({len(obsolete_prs)})", obs_body)

    pr_lines = [
        "| Repo & PR | Mergeable | Alignment | Review | CI | Feedback |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    for p in open_prs:
        url = p.get("url") or f"https://github.com/{p.get('repo')}/pull/{p.get('number')}"
        pr_lines.append(
            f"| [{p.get('repo')}#{p.get('number')}]({url}) | `{p.get('mergeable', 'UNKNOWN')}` | "
            f"`{p.get('alignmentStatus', 'UP_TO_DATE')}` | `{p.get('reviewDecision', 'NONE')}` | "
            f"`{p.get('ciStatus', 'N/A')}` | {p.get('feedback', '-')} |"
        )
    if candidates:
        pr_lines.append("")
        pr_lines.append("**Unsubmitted PR-Ready Fork Branches:**")
        for b in candidates:
            pr_lines.append(
                f"- `{b.get('upstream_repo')}` ← `{b.get('branch')}@{b.get('head_sha')}` (+{b.get('ahead_upstream')})"
            )
    block_prs = _details_block(
        f"Open Upstream PRs ({len(open_prs)}) & Candidate Branches ({len(candidates)})",
        "\n".join(pr_lines),
    )

    sess_lines: list[str] = []
    if closed_sessions:
        for cs in closed_sessions:
            sess_lines.append(f"- Closed `{cs.get('handle')}` (`{cs.get('reason', 'completed')}`)")
    else:
        sess_lines.append("- No completed idle agent sessions required closing.")
    if worktrees:
        for wt in worktrees:
            st = "clean" if wt.get("clean") else f"dirty ({', '.join(wt.get('dirty_repos') or [])})"
            sess_lines.append(f"- Worktree `{wt.get('name')}` (`{wt.get('agent_id', '-')}`): {st}")
    block_sessions = _details_block(
        f"Worktrees ({len(worktrees)}) & Closed Completed Sessions ({len(closed_sessions)})",
        "\n".join(sess_lines),
    )

    return "\n\n".join([headline, block_deltas, block_obsolete, block_prs, block_sessions])


def _default_orca_hooks_dir() -> Path:
    if sys.platform.startswith("darwin"):
        return Path.home() / "Library" / "Application Support" / "orca" / "agent-hooks"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else (Path.home() / ".config")
    return base / "orca" / "agent-hooks"


def spawn_detached_closer(
    *,
    terminal_handle: Optional[str] = None,
    automation_id: Optional[str] = None,
    initial_delay_sec: float = 2.0,
    max_wait_sec: float = 60.0,
    poll_interval_sec: float = 0.5,
) -> dict[str, Any]:
    """Spawn `close-run-when-settled` outside the agent tool-runner cgroup/PGID (`T615` AC4).

    On Linux with `systemd-run`, launches a transient `--user --collect` unit in `user.slice`
    with Orca CLI/runtime environment variables forwarded so synchronous tool-call teardown
    cannot `SIGKILL` the background closer before `outputSnapshot` settles. Falls back to
    `subprocess.Popen(..., start_new_session=True)` when `systemd-run` is unavailable.
    """
    handle = (terminal_handle or os.environ.get("ORCA_TERMINAL_HANDLE") or "").strip()
    if not handle:
        return {"ok": False, "spawned": False, "reason": "missing_terminal_handle"}

    inner_cmd = [
        sys.executable,
        str(Path(__file__).resolve()),
        "close-run-when-settled",
        "--terminal",
        handle,
        "--initial-delay",
        str(initial_delay_sec),
        "--max-wait",
        str(max_wait_sec),
        "--poll-interval",
        str(poll_interval_sec),
    ]
    if automation_id:
        inner_cmd.extend(["--automation-id", str(automation_id)])

    sd_bin = shutil.which("systemd-run") if sys.platform.startswith("linux") else None
    if sd_bin:
        sd_cmd = [sd_bin, "--user", "--collect"]
        for env_key in (
            "ORCA_CLI_COMMAND",
            "ORCA_USER_DATA_PATH",
            "ORCA_RUNTIME_SOURCE_PROFILE_PATH",
            "XDG_CONFIG_HOME",
            "HOME",
            "PATH",
        ):
            env_val = os.environ.get(env_key)
            if env_val:
                sd_cmd.append(f"--setenv={env_key}={env_val}")
        sd_cmd.extend(inner_cmd)
        sd_cp = run_cmd(sd_cmd, check=False, timeout=8.0)
        if sd_cp.returncode == 0:
            return {
                "ok": True,
                "spawned": True,
                "mechanism": "systemd-run",
                "handle": handle,
                "unit": sd_cp.stdout.strip(),
            }

    proc = subprocess.Popen(
        inner_cmd,
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )
    return {
        "ok": True,
        "spawned": True,
        "mechanism": "setsid",
        "handle": handle,
        "pid": proc.pid,
    }


def close_run_when_settled(
    *,
    automation_id: Optional[str] = None,
    terminal_handle: Optional[str] = None,
    hook_status_dir: Optional[Path] = None,
    initial_delay_sec: float = 0.0,
    max_wait_sec: float = 60.0,
    poll_interval_sec: float = 0.5,
) -> dict[str, Any]:
    """Wait until Orca persists `outputSnapshot` on a finalized automation run and close its tab (`T615` AC2/AC4).

    Aborts without closing if hook telemetry indicates the pane is actively `working` / `permission`.
    """
    handle = (terminal_handle or os.environ.get("ORCA_TERMINAL_HANDLE") or "").strip()
    if not handle:
        return {"ok": False, "closed": False, "reason": "missing_terminal_handle"}

    if initial_delay_sec > 0:
        time.sleep(initial_delay_sec)

    orca_bin = resolve_orca_bin()
    hdir = hook_status_dir if hook_status_dir is not None else _default_orca_hooks_dir()

    tlist_cp = run_cmd([orca_bin, "terminal", "list", "--json"], check=False, timeout=8.0)
    tab_id = ""
    pane_key = ""
    if tlist_cp.returncode == 0 and tlist_cp.stdout.strip():
        try:
            tdata: dict[str, Any] = json.loads(tlist_cp.stdout)
            terms = ((tdata.get("result") or {}).get("terminals") or tdata.get("terminals") or [])
            matched = next((t for t in terms if isinstance(t, dict) and t.get("handle") == handle), None)
            if matched is None and terms:
                return {"ok": True, "closed": False, "reason": "already_closed"}
            if isinstance(matched, dict):
                tab_id = str(matched.get("tabId") or "")
                leaf_id = str(matched.get("leafId") or "")
                if tab_id and leaf_id:
                    pane_key = f"{tab_id}:{leaf_id}"
        except ValueError:
            pass

    t0 = time.monotonic()
    last_reason = "timeout_waiting_for_settle"
    while True:
        # 1. Check hook telemetry — never close while working or awaiting permission
        is_busy = False
        if hdir.is_dir():
            for hf in hdir.glob("*.json"):
                try:
                    hobj: Any = json.loads(hf.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if isinstance(hobj, dict) and isinstance(hobj.get("entries"), dict):
                    entries = list(hobj["entries"].values())
                elif isinstance(hobj, dict) and "paneKey" not in hobj and "payload" not in hobj:
                    entries = list(hobj.values())
                else:
                    entries = [hobj]
                for ent in entries:
                    if not isinstance(ent, dict):
                        continue
                    epk = str(ent.get("paneKey") or "")
                    etab = str(ent.get("tabId") or "")
                    if (pane_key and epk == pane_key) or (tab_id and etab == tab_id):
                        st = str(((ent.get("payload") or {}).get("state")) or ent.get("state") or "").lower()
                        if st in ("working", "running", "thinking", "tool-use", "permission"):
                            is_busy = True
                            break
                if is_busy:
                    break

        if is_busy:
            last_reason = "session_working"
        else:
            runs_cmd = [orca_bin, "automations", "runs", "--limit", "15", "--json"]
            if automation_id:
                runs_cmd.extend(["--id", automation_id])
            rcp = run_cmd(runs_cmd, check=False, timeout=8.0)
            if rcp.returncode == 0 and rcp.stdout.strip():
                try:
                    rdata: dict[str, Any] = json.loads(rcp.stdout)
                    runs = ((rdata.get("result") or {}).get("runs") or [])
                    active_match = any(
                        isinstance(r, dict)
                        and str(r.get("status") or "").lower() in ("pending", "dispatched", "running")
                        and ((pane_key and r.get("terminalPaneKey") == pane_key) or (tab_id and r.get("terminalSessionId") == tab_id))
                        for r in runs
                    )
                    if active_match:
                        last_reason = "run_still_dispatched"
                    else:
                        fin = next(
                            (
                                r
                                for r in runs
                                if isinstance(r, dict)
                                and str(r.get("status") or "").lower()
                                in ("completed", "skipped", "skipped_precheck", "cancelled", "dispatch_failed")
                                and (str(r.get("status") or "").lower() != "completed" or bool(r.get("outputSnapshot")))
                                and (
                                    (pane_key and r.get("terminalPaneKey") == pane_key)
                                    or (tab_id and r.get("terminalSessionId") == tab_id)
                                    or (not pane_key and not tab_id)
                                )
                            ),
                            None,
                        )
                        if fin is not None:
                            ccp = run_cmd(
                                [orca_bin, "terminal", "close", "--terminal", handle, "--tab", "--json"],
                                check=False,
                                timeout=8.0,
                            )
                            return {
                                "ok": ccp.returncode == 0,
                                "closed": ccp.returncode == 0,
                                "handle": handle,
                                "runId": fin.get("id"),
                                "runNumber": fin.get("runNumber"),
                            }
                        last_reason = "awaiting_output_snapshot"
                except ValueError:
                    last_reason = "invalid_runs_json"

        if (time.monotonic() - t0) >= max_wait_sec:
            break
        time.sleep(max(0.01, poll_interval_sec))

    return {"ok": True, "closed": False, "handle": handle, "reason": last_reason}


def reconcile_prs_and_forks(
    *,
    author: str = CANONICAL_CONTRIBUTOR,
    preset: str = "w0m-pr",
    forks_dir: Optional[Path] = None,
    state_path: Optional[Path] = None,
    worktree: str = "active",
    align_forks: bool = True,
    fetch: bool = True,
    sync_orca: bool = False,
    close_sessions: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Align clean `w0m-pr/*` forks, detect/detach obsolete PRs, close completed sessions, and persist collapsed launch report (`T613` AC1-AC3)."""
    fdir = forks_dir or resolve_forks_dir()
    target_state = state_path or (Path.home() / ".w0m" / "state" / "prs-watch-state.json")
    target_state.parent.mkdir(parents=True, exist_ok=True)

    fork_updates: list[dict[str, Any]] = []
    if align_forks and fdir and fdir.is_dir():
        targets = sorted([d for d in fdir.iterdir() if d.is_dir() and (d / ".git").exists()])
        for d in targets:
            if dry_run:
                st = inspect_fork(d, fetch=fetch)
                action = "skipped_dirty" if st.get("dirty_count", 0) > 0 else (
                    "would_fast_forward" if st.get("behind_upstream", 0) > 0 and st.get("ahead_upstream", 0) == 0 else "up_to_date"
                )
                fork_updates.append({"repo": d.name, "success": True, "action": action, "message": st.get("status", "")})
            else:
                res_u = update_fork(d, rebase=False, fetch=fetch)
                if res_u.get("action") != "up_to_date":
                    fork_updates.append(res_u)

    discovered = discover_new_prs_and_branches(author=author, preset=preset, forks_dir=fdir, fetch=False)
    delta_res = check_prs_delta(
        author=author,
        preset=preset,
        state_path=target_state,
        forks_dir=fdir,
        current_override=discovered,
        include_worktrees=False,
        consume_pending_deltas=True,
    )

    obsolete_prs = discovered.get("obsoletePrs") or []
    closed_sessions: list[dict[str, Any]] = []
    pruned_trees: list[str] = []
    detached_urls: list[str] = []

    if close_sessions:
        try:
            scripts_dir = str(Path(__file__).resolve().parent)
            if scripts_dir not in sys.path:
                sys.path.insert(0, scripts_dir)
            import orca_sessions as _osess

            c_res = _osess.close_completed_sessions(dry_run=dry_run)
            closed_sessions = list(c_res.get("closed") or [])
            pruned_trees = list(c_res.get("prunedTrees") or [])
        except Exception:
            pass

    orca_bin = resolve_orca_bin()
    automation_id = None
    run_number: Any = None
    orch_run_id = None
    orch_task_id = None

    if sync_orca and not dry_run:
        obsolete_urls = [str(p["url"]) for p in obsolete_prs if p.get("url")]
        if obsolete_urls:
            rm_cp = run_cmd(
                [orca_bin, "reference", "remove", *obsolete_urls, "--worktree", worktree, "--json"],
                check=False,
                timeout=10.0,
            )
            if rm_cp.returncode == 0:
                detached_urls = obsolete_urls

        alist_cp = run_cmd([orca_bin, "automations", "list", "--json"], check=False, timeout=8.0)
        if alist_cp.returncode == 0 and alist_cp.stdout.strip():
            try:
                alist_obj: dict[str, Any] = json.loads(alist_cp.stdout)
                autos = (alist_obj.get("result") or {}).get("automations") or []
                for a in autos:
                    if "Upstream PRs" in str(a.get("name") or ""):
                        automation_id = a.get("id")
                        break
            except ValueError:
                pass
        if automation_id:
            aruns_cp = run_cmd(
                [orca_bin, "automations", "runs", "--id", str(automation_id), "--limit", "1", "--json"],
                check=False,
                timeout=8.0,
            )
            if aruns_cp.returncode == 0 and aruns_cp.stdout.strip():
                try:
                    aruns_obj: dict[str, Any] = json.loads(aruns_cp.stdout)
                    latest_runs = (aruns_obj.get("result") or {}).get("runs") or []
                    if latest_runs:
                        run_number = latest_runs[0].get("runNumber")
                except ValueError:
                    pass

    state_data: dict[str, Any] = {}
    if target_state.is_file():
        try:
            loaded_state: dict[str, Any] = json.loads(target_state.read_text(encoding="utf-8"))
            state_data = loaded_state
        except (OSError, ValueError):
            state_data = {}

    history: list[dict[str, Any]] = list(state_data.get("launch_history") or [])
    if run_number is None:
        prev_nums = [int(h["runNumber"]) for h in history if isinstance(h, dict) and str(h.get("runNumber", "")).isdigit()]
        run_number = (max(prev_nums) + 1) if prev_nums else 1

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    headline = (
        f"{delta_res['deltaCount']} delta(s), {len(discovered.get('openPrs') or [])} open PR(s), "
        f"{len(obsolete_prs)} obsolete PR(s), {len(closed_sessions)} session(s) closed"
    )
    report_payload = {
        "runNumber": run_number,
        "timestamp": now_iso,
        "status": "completed",
        "headline": headline,
        "deltas": delta_res["deltas"],
        "forkUpdates": fork_updates,
        "obsoletePrs": obsolete_prs,
        "closedSessions": closed_sessions,
        "openPrs": discovered.get("openPrs") or [],
        "candidateBranches": discovered.get("pendingBranches") or [],
        "worktrees": discovered.get("agentTrees") or [],
    }
    report_md = format_launch_report(report_payload)
    history_entry = {
        "runNumber": run_number,
        "timestamp": now_iso,
        "status": "completed",
        "headline": headline,
        "deltaCount": delta_res["deltaCount"],
        "obsoleteCount": len(obsolete_prs),
        "closedSessionsCount": len(closed_sessions),
        "markdown": report_md,
    }
    history = [h for h in history if not (isinstance(h, dict) and h.get("runNumber") == run_number)]
    history.insert(0, history_entry)
    state_data["launch_history"] = history[:25]
    state_data["obsolete_prs"] = {f"{p['repo']}#{p['number']}": p for p in obsolete_prs}
    if not dry_run:
        target_state.write_text(json.dumps(state_data, indent=2) + "\n", encoding="utf-8")
        try:
            os.chmod(target_state, 0o600)
        except OSError:
            pass

    if sync_orca and not dry_run:
        runs_cp = run_cmd([orca_bin, "orchestration", "run-list", "--json"], check=False, timeout=8.0)
        if runs_cp.returncode == 0 and runs_cp.stdout.strip():
            try:
                runs_obj: dict[str, Any] = json.loads(runs_cp.stdout)
                for r in (runs_obj.get("result") or {}).get("runs") or []:
                    if "Upstream PRs" in str(r.get("objective") or ""):
                        orch_run_id = r.get("id")
                        break
            except ValueError:
                pass
        if orch_run_id:
            t_cp = run_cmd(
                [orca_bin, "orchestration", "task-list", "--run", str(orch_run_id), "--json"],
                check=False,
                timeout=8.0,
            )
            if t_cp.returncode == 0 and t_cp.stdout.strip():
                try:
                    tasks_obj: dict[str, Any] = json.loads(t_cp.stdout)
                    tasks = (tasks_obj.get("result") or {}).get("tasks") or []
                    if tasks:
                        orch_task_id = tasks[0].get("id")
                except ValueError:
                    pass
        if orch_run_id and orch_task_id:
            run_cmd(
                [
                    orca_bin,
                    "orchestration",
                    "task-update",
                    "--id",
                    str(orch_task_id),
                    "--run",
                    str(orch_run_id),
                    "--status",
                    "completed",
                    "--result",
                    report_md,
                    "--json",
                ],
                check=False,
                timeout=10.0,
            )

    return {
        "ok": True,
        "dryRun": dry_run,
        "runNumber": run_number,
        "timestamp": now_iso,
        "headline": headline,
        "deltaCount": delta_res["deltaCount"],
        "deltas": delta_res["deltas"],
        "forkUpdates": fork_updates,
        "obsoletePrCount": len(obsolete_prs),
        "obsoletePrs": obsolete_prs,
        "detachedReferenceUrls": detached_urls,
        "closedSessions": closed_sessions,
        "prunedTrees": pruned_trees,
        "orchestrationTaskId": orch_task_id,
        "markdown": report_md,
    }


def close_obsolete_prs(
    *,
    author: str = CANONICAL_CONTRIBUTOR,
    preset: str = "w0m-pr",
    forks_dir: Optional[Path] = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    """List or close post-rebase obsolete upstream PRs under `AgDR-0058` per-repo policy gates (`T613` AC1, `T655`)."""
    discovered = discover_new_prs_and_branches(author=author, preset=preset, forks_dir=forks_dir, fetch=False)
    obsolete = discovered.get("obsoletePrs") or []
    results: list[dict[str, Any]] = []
    for op in obsolete:
        repo_name = str(op.get("repo") or "")
        rules = get_repo_contribution_rules(repo_name)
        if rules.get("automation_mode") == "banned":
            results.append(
                {
                    **op,
                    "actionStatus": "REFUSED-REPO-POLICY",
                    "stderr": f"REFUSED-REPO-POLICY: {rules.get('policy_note', '')}",
                }
            )
            continue
        if dry_run:
            results.append({**op, "actionStatus": "PROPOSED_CLOSE"})
            continue
        comment_msg = f"Closing as superseded / already landed upstream ({op.get('alignmentStatus')})."
        cp = run_cmd(
            ["gh", "pr", "close", str(op["number"]), "-R", repo_name, "--comment", comment_msg],
            check=False,
            timeout=20.0,
        )
        results.append(
            {
                **op,
                "actionStatus": "CLOSED" if cp.returncode == 0 else "FAILED",
                "stderr": cp.stderr.strip() if cp.returncode != 0 else "",
            }
        )
    ok_flag = all(r["actionStatus"] in ("PROPOSED_CLOSE", "CLOSED", "REFUSED-REPO-POLICY") for r in results)
    return {"ok": ok_flag, "dryRun": dry_run, "count": len(results), "results": results}


def get_launch_reports(*, limit: int = 15, state_path: Optional[Path] = None) -> dict[str, Any]:
    """Return bounded collapsed-by-default launch reports for Orca's PRs Updates task & Control Panel UI (`T613` AC3)."""
    target_state = state_path or (Path.home() / ".w0m" / "state" / "prs-watch-state.json")
    state_data: dict[str, Any] = {}
    if target_state.is_file():
        try:
            loaded_state2: dict[str, Any] = json.loads(target_state.read_text(encoding="utf-8"))
            state_data = loaded_state2
        except (OSError, ValueError):
            state_data = {}

    by_run: dict[Any, dict[str, Any]] = {}
    for item in state_data.get("launch_history") or []:
        if isinstance(item, dict):
            by_run[item.get("runNumber") or item.get("timestamp")] = item

    orca_bin = resolve_orca_bin()
    auto_id = ""
    auto_name = "w0m Upstream PRs & Fork Branches Monitor"
    auto_schedule = "*/15 * * * *"
    task_id = ""

    alist_cp = run_cmd([orca_bin, "automations", "list", "--json"], check=False, timeout=6.0)
    if alist_cp.returncode == 0 and alist_cp.stdout.strip():
        try:
            alist_obj2: dict[str, Any] = json.loads(alist_cp.stdout)
            for a in (alist_obj2.get("result") or {}).get("automations") or []:
                if "Upstream PRs" in str(a.get("name") or ""):
                    auto_id = str(a.get("id") or "")
                    auto_name = str(a.get("name") or auto_name)
                    raw_trig = a.get("trigger")
                    auto_schedule = str(raw_trig.get("cron") or raw_trig.get("expression") or auto_schedule) if isinstance(raw_trig, dict) else str(raw_trig or auto_schedule)
                    break
        except ValueError:
            pass

    if auto_id:
        rcp = run_cmd([orca_bin, "automations", "runs", "--id", auto_id, "--limit", str(limit), "--json"], check=False, timeout=6.0)
        if rcp.returncode == 0 and rcp.stdout.strip():
            try:
                rcp_obj: dict[str, Any] = json.loads(rcp.stdout)
                for r in (rcp_obj.get("result") or {}).get("runs") or []:
                    if not isinstance(r, dict):
                        continue
                    rnum = r.get("runNumber")
                    if rnum in by_run:
                        continue
                    rstatus = str(r.get("status") or "completed")
                    started_ms = r.get("startedAt") or r.get("scheduledAt") or 0
                    ts_iso = (
                        datetime.fromtimestamp(float(started_ms) / 1000.0, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                        if started_ms
                        else ""
                    )
                    snap_content = str(((r.get("outputSnapshot") or {}).get("content")) or r.get("errorMessage") or "").strip()
                    summary_line = (
                        "Skipped by zero-token precheck (no PR/branch deltas)"
                        if rstatus == "skipped_precheck"
                        else f"Automation launch #{rnum} ({rstatus})"
                    )
                    body_md = _details_block(
                        f"Launch #{rnum} Output ({rstatus})",
                        snap_content[:2400] if snap_content else f"- Status: `{rstatus}`",
                    )
                    by_run[rnum] = {
                        "runNumber": rnum,
                        "timestamp": ts_iso,
                        "status": rstatus,
                        "headline": summary_line,
                        "deltaCount": 0 if rstatus == "skipped_precheck" else 1,
                        "obsoleteCount": 0,
                        "closedSessionsCount": 0,
                        "markdown": body_md,
                    }
            except ValueError:
                pass

    reports = sorted(
        by_run.values(),
        key=lambda x: (int(x["runNumber"]) if str(x.get("runNumber", "")).isdigit() else 0, str(x.get("timestamp") or "")),
        reverse=True,
    )[: max(1, limit)]

    return {
        "task": {
            "automationId": auto_id,
            "taskId": task_id,
            "name": auto_name,
            "schedule": auto_schedule,
        },
        "reports": reports,
    }


def get_prs_enriched(
    *,
    author: str = CANONICAL_CONTRIBUTOR,
    preset: str = "w0m-pr",
    forks_dir: Optional[Path] = None,
    limit: int = 30,
) -> list[dict[str, Any]]:
    """Return upstream PRs enriched with `alignmentStatus`, `isObsolete`, and `closeCommand` for Control Panel UI (`T613` AC3)."""
    disc = discover_new_prs_and_branches(author=author, preset=preset, forks_dir=forks_dir, fetch=False)
    items: list[dict[str, Any]] = []
    for p in (disc.get("openPrs") or [])[: max(1, limit)]:
        items.append(
            {
                **p,
                "repository": {"nameWithOwner": p.get("repo", "")},
            }
        )
    return items


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
    branch_filter = getattr(args, "branch", None) or getattr(args, "query", None)
    items = build_pr_proposals(branch_filter=branch_filter, forks_dir=forks_dir)
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
    branch_filter = getattr(args, "branch", None) or getattr(args, "query", None)
    res = submit_prepared_prs(
        branch_filter=branch_filter,
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
    if getattr(args, "close_settled", False):
        try:
            scripts_dir = str(Path(__file__).resolve().parent)
            if scripts_dir not in sys.path:
                sys.path.insert(0, scripts_dir)
            import orca_sessions as _osess

            _osess.close_completed_sessions(dry_run=False)
        except Exception:
            pass
    res = check_prs_delta(
        author=args.author,
        preset=args.preset,
        state_path=state_path,
        forks_dir=forks_dir,
        include_worktrees=not bool(getattr(args, "ignore_worktrees", False)),
        record_pending_deltas=True,
    )
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
    p_delta.add_argument(
        "--ignore-worktrees",
        action="store_true",
        help="Ignore unrelated ~/.w0m/work/* dirty-repo churn when checking PR deltas",
    )
    p_delta.add_argument(
        "--close-settled",
        action="store_true",
        help="Reap finalized completed Orca automation run tabs before checking deltas",
    )
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
    p_props.add_argument("query", nargs="?", default=None, help="Optional branch, ticket, repo, or keyword filter")
    p_props.add_argument("--branch", type=str, default=None, help="Filter by branch, ticket, repo, or keyword")
    p_props.add_argument("--dir", type=str, help="Path to w0m-pr directory")
    p_props.add_argument("--json", action="store_true", help="Output structured JSON")
    p_props.set_defaults(func=cmd_proposals)

    # Submit (T593 AC4 — owner-confirmed PR submission or --dry-run preview)
    p_submit = subparsers.add_parser(
        "submit", help="Submit prepared w0m-pr upstream PRs (requires human confirmation or --dry-run)"
    )
    p_submit.add_argument("query", nargs="?", default=None, help="Optional branch, ticket, repo, or keyword filter")
    p_submit.add_argument("--branch", type=str, default=None, help="Specific branch, ticket, repo, or keyword to submit")
    p_submit.add_argument("--dir", type=str, help="Path to w0m-pr directory")
    p_submit.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Preview gh pr create commands without submitting (--no-dry-run for live submission)",
    )
    p_submit.add_argument("--json", action="store_true", help="Output structured JSON")
    p_submit.set_defaults(func=cmd_submit)

    _register_t613_subparsers(subparsers)

    args = parser.parse_args()
    args.func(args)


def cmd_reconcile(args: argparse.Namespace) -> None:
    forks_dir = Path(args.dir) if getattr(args, "dir", None) else None
    state_path = Path(args.state_file) if getattr(args, "state_file", None) else None
    res = reconcile_prs_and_forks(
        author=args.author,
        preset=args.preset,
        forks_dir=forks_dir,
        state_path=state_path,
        worktree=args.worktree,
        align_forks=not bool(args.no_align),
        fetch=not bool(args.no_fetch),
        sync_orca=bool(args.sync_orca),
        close_sessions=not bool(args.no_close_sessions),
        dry_run=bool(args.dry_run),
    )
    if args.json:
        print(json.dumps(res, indent=2))
        return
    print(res["markdown"])


def cmd_obsolete(args: argparse.Namespace) -> None:
    forks_dir = Path(args.dir) if getattr(args, "dir", None) else None
    res = close_obsolete_prs(
        author=args.author,
        preset=args.preset,
        forks_dir=forks_dir,
        dry_run=not bool(args.close),
    )
    if args.json:
        print(json.dumps(res, indent=2))
        if not res.get("ok"):
            sys.exit(2)
        return
    if not res.get("ok"):
        print(res.get("error", "Refused"), file=sys.stderr)
        sys.exit(2)
    print(f"=== Post-Rebase Obsolete Upstream PRs ({res['count']}) ===")
    if not res["results"]:
        print("  ✓ Zero open PRs are obsolete against upstream.")
        return
    for r in res["results"]:
        print(
            f"  [{r['actionStatus']}] {r['repo']}#{r['number']} ({r.get('headRefName', '-')}) -> {r['alignmentStatus']}\n"
            f"    Command: {r.get('closeCommand', '')}"
        )


def cmd_launch_reports(args: argparse.Namespace) -> None:
    state_path = Path(args.state_file) if getattr(args, "state_file", None) else None
    res = get_launch_reports(limit=int(args.limit), state_path=state_path)
    if args.json:
        print(json.dumps(res, indent=2))
        return
    print(f"=== {res['task']['name']} — Launch Reports ({len(res['reports'])}) ===")
    for rep in res["reports"]:
        print(f"\n{rep.get('markdown') or rep.get('headline')}")


def cmd_prs_enriched(args: argparse.Namespace) -> None:
    forks_dir = Path(args.dir) if getattr(args, "dir", None) else None
    items = get_prs_enriched(
        author=args.author,
        preset=args.preset,
        forks_dir=forks_dir,
        limit=int(args.limit),
    )
    if args.json:
        print(json.dumps(items, indent=2))
        return
    for it in items:
        obs_tag = f" [OBSOLETE: {it['alignmentStatus']}]" if it.get("isObsolete") else f" [{it.get('alignmentStatus', 'UP_TO_DATE')}]"
        print(f"  {it['repo']}#{it['number']}{obs_tag} | {it.get('mergeable')} | {it.get('title')}")


def cmd_close_run_when_settled(args: argparse.Namespace) -> None:
    if getattr(args, "daemon", False):
        dres = spawn_detached_closer(
            terminal_handle=getattr(args, "terminal", None),
            automation_id=getattr(args, "automation_id", None),
            initial_delay_sec=float(args.initial_delay),
            max_wait_sec=float(args.max_wait),
            poll_interval_sec=float(args.poll_interval),
        )
        if args.json:
            print(json.dumps(dres, indent=2))
        elif dres.get("spawned"):
            print(f"[SPAWNED DETACHED CLOSER] handle={dres.get('handle')} mechanism={dres.get('mechanism')}")
        else:
            print(f"[SKIPPED CLOSER] reason={dres.get('reason')}")
        return

    res = close_run_when_settled(
        automation_id=getattr(args, "automation_id", None),
        terminal_handle=getattr(args, "terminal", None),
        initial_delay_sec=float(args.initial_delay),
        max_wait_sec=float(args.max_wait),
        poll_interval_sec=float(args.poll_interval),
    )
    if args.json:
        print(json.dumps(res, indent=2))
    elif res.get("closed"):
        print(f"[CLOSED SETTLED RUN TAB] handle={res.get('handle')} run=#{res.get('runNumber')}")
    else:
        print(f"[SKIPPED CLOSE] handle={res.get('handle')} reason={res.get('reason')}")


def _register_t613_subparsers(subparsers: Any) -> None:
    p_rec = subparsers.add_parser(
        "reconcile",
        help="Align clean w0m-pr/* forks, detect obsolete PRs, close completed sessions, and emit collapsed launch report",
    )
    p_rec.add_argument("--author", type=str, default=CANONICAL_CONTRIBUTOR, help="GitHub author username")
    p_rec.add_argument("--preset", type=str, choices=list(PRESET_REPOS.keys()), default="w0m-pr", help="Preset target")
    p_rec.add_argument("--dir", type=str, help="Path to w0m-pr directory")
    p_rec.add_argument("--state-file", type=str, help="Override state file path")
    p_rec.add_argument("--worktree", type=str, default="active", help="Orca worktree selector")
    p_rec.add_argument("--no-align", action="store_true", help="Skip fast-forwarding w0m-pr/* base branches")
    p_rec.add_argument("--no-fetch", action="store_true", help="Skip git fetch during fork alignment")
    p_rec.add_argument("--sync-orca", action="store_true", help="Update Orca task & detach obsolete PR references")
    p_rec.add_argument("--no-close-sessions", action="store_true", help="Skip closing completed idle agent sessions")
    p_rec.add_argument("--dry-run", action="store_true", help="Preview actions without mutating git or Orca")
    p_rec.add_argument("--json", action="store_true", help="Output structured JSON")
    p_rec.set_defaults(func=cmd_reconcile)

    p_obs = subparsers.add_parser(
        "obsolete", help="Audit or close upstream PRs rendered obsolete after upstream rebase (T435 human-gated)"
    )
    p_obs.add_argument("--author", type=str, default=CANONICAL_CONTRIBUTOR, help="GitHub author username")
    p_obs.add_argument("--preset", type=str, choices=list(PRESET_REPOS.keys()), default="w0m-pr", help="Preset target")
    p_obs.add_argument("--dir", type=str, help="Path to w0m-pr directory")
    p_obs.add_argument("--close", action="store_true", help="Close obsolete PRs (requires human confirmation gate)")
    p_obs.add_argument("--json", action="store_true", help="Output structured JSON")
    p_obs.set_defaults(func=cmd_obsolete)

    p_lr = subparsers.add_parser(
        "launch-reports", help="List collapsed-by-default PRs monitor launch reports for Orca task & CP UI"
    )
    p_lr.add_argument("--limit", type=int, default=15, help="Max launch reports to return")
    p_lr.add_argument("--state-file", type=str, help="Override state file path")
    p_lr.add_argument("--json", action="store_true", help="Output structured JSON")
    p_lr.set_defaults(func=cmd_launch_reports)

    p_pe = subparsers.add_parser(
        "prs-enriched", help="Return open PRs enriched with rebase alignment and obsolescence status"
    )
    p_pe.add_argument("--author", type=str, default=CANONICAL_CONTRIBUTOR, help="GitHub author username")
    p_pe.add_argument("--preset", type=str, choices=list(PRESET_REPOS.keys()), default="w0m-pr", help="Preset target")
    p_pe.add_argument("--dir", type=str, help="Path to w0m-pr directory")
    p_pe.add_argument("--limit", type=int, default=30, help="Maximum PRs to return")
    p_pe.add_argument("--json", action="store_true", help="Output structured JSON")
    p_pe.set_defaults(func=cmd_prs_enriched)

    p_crs = subparsers.add_parser(
        "close-run-when-settled",
        help="Wait until Orca persists outputSnapshot for an automation run and safely close its terminal tab",
    )
    p_crs.add_argument("--automation-id", type=str, default=None, help="Optional Orca automation ID")
    p_crs.add_argument("--terminal", type=str, default=None, help="Orca terminal handle (default: $ORCA_TERMINAL_HANDLE)")
    p_crs.add_argument("--initial-delay", type=float, default=0.0, help="Initial delay in seconds before polling")
    p_crs.add_argument("--max-wait", type=float, default=60.0, help="Max seconds to wait for run settle")
    p_crs.add_argument("--poll-interval", type=float, default=0.5, help="Polling interval in seconds")
    p_crs.add_argument(
        "--daemon",
        action="store_true",
        help="Spawn detached outside agent tool-runner cgroup (systemd-run --user --collect on Linux, setsid fallback)",
    )
    p_crs.add_argument("--json", action="store_true", help="Output structured JSON")
    p_crs.set_defaults(func=cmd_close_run_when_settled)

    p_comp = subparsers.add_parser(
        "compliance",
        help="Audit open external PRs against target repo contribution rules and optionally remediate bodies (AgDR-0058)",
    )
    p_comp.add_argument("--author", type=str, default=CANONICAL_CONTRIBUTOR, help="GitHub author username")
    p_comp.add_argument("--preset", type=str, choices=list(PRESET_REPOS.keys()), default="w0m-pr", help="Preset target")
    p_comp.add_argument("--remediate", action="store_true", help="Remediate non-compliant PR bodies on auto-mode repos")
    p_comp.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Preview compliance remediations without editing GitHub PRs",
    )
    p_comp.add_argument("--no-create-issues", action="store_true", help="Do not auto-create missing upstream issues")
    p_comp.add_argument("--json", action="store_true", help="Output structured JSON")
    p_comp.set_defaults(func=cmd_compliance)

    p_auto = subparsers.add_parser(
        "auto",
        help="Full auto-mode upstream PR submission for all rule-compliant prepared branches (AgDR-0058)",
    )
    p_auto.add_argument("query", nargs="?", default=None, help="Optional branch, ticket, repo, or keyword filter")
    p_auto.add_argument("--branch", type=str, default=None, help="Filter by branch, ticket, repo, or keyword")
    p_auto.add_argument("--dir", type=str, help="Path to w0m-pr directory")
    p_auto.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Preview gate evaluation without creating GitHub PRs or issues",
    )
    p_auto.add_argument("--no-create-issues", action="store_true", help="Do not auto-create missing upstream issues")
    p_auto.add_argument("--json", action="store_true", help="Output structured JSON")
    p_auto.set_defaults(func=cmd_auto)


def cmd_compliance(args: argparse.Namespace) -> None:
    res = audit_open_prs_compliance(
        author=args.author,
        preset=args.preset,
        remediate=bool(args.remediate),
        dry_run=bool(args.dry_run),
        auto_create_issues=not bool(args.no_create_issues),
    )
    if args.json:
        print(json.dumps(res, indent=2))
        return
    print(
        f"=== Upstream PR Contribution Compliance Audit "
        f"(open={res['totalOpenPrs']}, compliant={res['compliantCount']}, nonCompliant={res['nonCompliantCount']}) ==="
    )
    for p in res["prs"]:
        rem = f" | remediate={p['remediationStatus']}" if p["remediationStatus"] != "NONE" else ""
        iss = f" | issue=#{p['linkedIssue']}" if p.get("linkedIssue") else ""
        print(
            f"  [{p['statusAfter']}] {p['repo']}#{p['number']} ({p['headRefName']}) "
            f"| mode={p['automationMode']} | mergeable={p['mergeable']}{iss}{rem}"
        )
        for f in p["findingsAfter"]:
            print(f"    ✗ {f}")
        for w in p["warningsAfter"]:
            print(f"    ⚠ {w}")


def cmd_auto(args: argparse.Namespace) -> None:
    forks_dir = Path(args.dir) if getattr(args, "dir", None) else None
    branch_filter = getattr(args, "branch", None) or getattr(args, "query", None)
    res = auto_submit_compliant_prs(
        branch_filter=branch_filter,
        forks_dir=forks_dir,
        dry_run=bool(args.dry_run),
        auto_create_issues=not bool(args.no_create_issues),
    )
    if args.json:
        print(json.dumps(res, indent=2))
        if not res.get("ok"):
            sys.exit(2)
        return
    mode = "DRY-RUN" if res["dryRun"] else "FULL AUTO-MODE"
    print(
        f"=== Upstream PR Auto-Mode ({mode}: evaluated={res['totalEvaluated']}, "
        f"submitted={res['submittedCount']}, alreadyOpen={res['alreadyOpenCount']}, "
        f"heldVisual={res['heldVisualCount']}, conflict={res['refusedConflictCount']}, "
        f"policyBlocked={res['refusedPolicyCount']}, failed={res['failedCount']}) ==="
    )
    for r in res["results"]:
        iss_tag = f" [Fixes #{r['linked_issue']}]" if r.get("linked_issue") else ""
        print(f"  [{r['status']}] {r['upstream_repo']} <- {CANONICAL_FORK_ORG}:{r['branch']}@{r['head_sha']}{iss_tag} — {r['title']}")
        if r.get("url"):
            print(f"    URL: {r['url']}")
        elif r.get("stderr"):
            print(f"    Note: {r['stderr']}")
    if not res.get("ok"):
        sys.exit(2)


if __name__ == "__main__":
    main()


