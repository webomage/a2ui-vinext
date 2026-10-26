#!/usr/bin/env python3
"""T242 AC8 — Disposition legacy tracker issues in casualuser/webomage.com.

Closes open issues in the legacy tracker as 'duplicate', leaving a comment
pointing to the corresponding issue in the dedicated tracker repo (webomage/wom7board).
Preserves the repository itself so owner contribution graph activity is protected.

Usage:
    python3 scripts/close_legacy_tracker_issues.py            # dry-run
    python3 scripts/close_legacy_tracker_issues.py --limit 5   # preview first 5
    python3 scripts/close_legacy_tracker_issues.py --apply     # execute
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

DEFAULT_SOURCE_REPO = "casualuser/webomage.com"
DEFAULT_TARGET_REPO = "webomage/wom7board"


def parse_target_issue(title: str, target_repo: str = DEFAULT_TARGET_REPO) -> tuple[int | None, str]:
    """Derive target issue number and URL from legacy issue title."""
    m = re.search(r"\bT(\d+)\b", title)
    if m:
        target_num = int(m.group(1))
        return target_num, f"https://github.com/{target_repo}/issues/{target_num}"
    return None, f"https://github.com/{target_repo}"


def format_close_comment(target_url: str) -> str:
    """Format the closing comment linking to the new tracker."""
    return f"Superseded by {target_url} — issue tracking moved to the dedicated w0m tracker repo (T242)."


def fetch_open_issues(repo: str = DEFAULT_SOURCE_REPO) -> list[dict]:
    """Fetch open issues from the source repository."""
    cmd = [
        "gh", "issue", "list",
        "--repo", repo,
        "--state", "open",
        "--limit", "1000",
        "--json", "number,title"
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Failed to fetch issues from {repo}: {res.stderr.strip()}")
    return json.loads(res.stdout)


def close_issue(
    issue_num: int,
    comment: str,
    repo: str = DEFAULT_SOURCE_REPO,
    reason: str = "duplicate",
    apply: bool = False,
) -> bool:
    """Close a legacy issue with reason and closing comment."""
    if not apply:
        return True
    cmd = [
        "gh", "issue", "close",
        str(issue_num),
        "--repo", repo,
        "--reason", reason,
        "--comment", comment,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"  ❌ #{issue_num}: {res.stderr.strip()}", file=sys.stderr)
        return False
    return True


def run(
    source_repo: str = DEFAULT_SOURCE_REPO,
    target_repo: str = DEFAULT_TARGET_REPO,
    apply: bool = False,
    limit: int = 0,
) -> int:
    """Execute the disposition loop."""
    print(f"▶ T242 AC8 — Close legacy issues in {source_repo} (target: {target_repo})")
    print(f"  Mode: {'APPLY (live)' if apply else 'DRY RUN'}\n")

    issues = fetch_open_issues(source_repo)
    total = len(issues)
    print(f"  Found {total} open issue(s) in {source_repo}.")

    if limit > 0:
        issues = issues[:limit]
        print(f"  Limited to {len(issues)} issue(s).")

    closed = 0
    failed = 0

    for iss in issues:
        num = iss["number"]
        title = iss["title"]
        target_num, target_url = parse_target_issue(title, target_repo)
        comment = format_close_comment(target_url)

        prefix = "[APPLY]" if apply else "[DRY-RUN]"
        target_label = f"#{target_num}" if target_num else target_repo
        print(f"  {prefix} #{num} ({title[:50]}...) -> close as duplicate -> {target_label}")

        ok = close_issue(num, comment, repo=source_repo, reason="duplicate", apply=apply)
        if ok:
            closed += 1
        else:
            failed += 1

    verb = "Closed" if apply else "Would close"
    print(f"\n  {verb} {closed} issue(s) · {failed} failed.")
    if not apply:
        print("  Dry run complete. Use --apply to execute.")
    return 1 if failed > 0 else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=DEFAULT_SOURCE_REPO, help=f"Source repo (default: {DEFAULT_SOURCE_REPO})")
    parser.add_argument("--target-repo", default=DEFAULT_TARGET_REPO, help=f"Target repo (default: {DEFAULT_TARGET_REPO})")
    parser.add_argument("--apply", action="store_true", help="Execute live close mutations")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of issues to process")
    args = parser.parse_args()

    return run(source_repo=args.repo, target_repo=args.target_repo, apply=args.apply, limit=args.limit)


if __name__ == "__main__":
    sys.exit(main())
