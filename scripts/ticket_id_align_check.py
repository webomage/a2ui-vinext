#!/usr/bin/env python3
r"""ticket-id-align-check — quality gate enforcing T<n> == gh_issue == #<n> (T242 AC6).

Aligns the local ticket ID to GitHub issue counter permanently:
1. Every ticket file `project/tickets/T<n>.md` must record `gh_issue: <n>`.
2. Any discrepancy (missing `gh_issue`, `gh_issue != base_number`) is an error.
3. In online mode (`--online` or when not `--offline`), checks that remote issue `#<n>`
   exists in the tracker repository and its title begins with `T<n> — `.

Exit codes: 0 = aligned, 1 = misaligned or error.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "wom7web"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from tasks_query import resolve_tickets_dir  # noqa: E402 — canonical .tasks/ resolver (T411)
TICKETS = resolve_tickets_dir()

ID_RE = re.compile(r"^T(\d+)([a-z]?)$")
FM_RE = re.compile(r"^---\n(.*?)\n---", re.S)


def frontmatter(text: str) -> dict[str, str]:
    m = FM_RE.match(text)
    if not m:
        return {}
    fm: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" not in line or line.startswith(("#", " ", "\t")):
            continue
        k, _, v = line.partition(":")
        v = v.split("#", 1)[0].strip().strip('"').strip("'")
        fm[k.strip()] = v
    return fm


def load_tickets(tickets_dir: Path = TICKETS) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for f in sorted(tickets_dir.glob("T*.md")):
        m = ID_RE.match(f.stem)
        if not m:
            continue
        fm = frontmatter(f.read_text(encoding="utf-8", errors="replace"))
        raw_issue = fm.get("gh_issue")
        try:
            gh_issue = int(raw_issue) if raw_issue is not None and raw_issue != "" else None
        except ValueError:
            gh_issue = None
        out.append({
            "id": f.stem,
            "base": int(m.group(1)),
            "suffix": m.group(2),
            "title": fm.get("title", ""),
            "gh_issue": gh_issue,
        })
    return out


def fetch_remote_issues(repo: str) -> dict[int, str]:
    """Fetch all issue numbers and titles from the target GitHub repo."""
    env = {**os.environ, "GH_CONFIG_DIR": os.environ.get(
        "GH_CONFIG_DIR", str(Path.home() / ".config" / "gh-w0m"))}
    cmd = [
        "gh", "issue", "list",
        "--repo", repo,
        "--state", "all",
        "--limit", "1000",
        "--json", "number,title",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=120, env=env)
        data = json.loads(r.stdout)
        return {item["number"]: item["title"] for item in data}
    except Exception as e:
        print(f"[WARN] Failed to fetch remote issues from {repo}: {e}", file=sys.stderr)
        return {}


def check_alignment(
    tickets: list[dict[str, Any]],
    remote_issues: dict[int, str] | None = None,
) -> list[str]:
    """Return a list of errors where T<n> != gh_issue != remote #<n>."""
    errors: list[str] = []
    for t in tickets:
        tid = t["id"]
        base = t["base"]
        gh_issue = t.get("gh_issue")

        if gh_issue is None:
            errors.append(f"{tid}: missing 'gh_issue' in frontmatter (expected {base})")
            continue

        if gh_issue != base:
            errors.append(f"{tid}: misaligned — frontmatter gh_issue {gh_issue} != ticket base {base}")
            continue

        if remote_issues is not None:
            if base not in remote_issues:
                errors.append(f"{tid}: remote issue #{base} absent on GitHub")
            else:
                remote_title = remote_issues[base]
                expected_prefix = f"{tid} — "
                if not remote_title.startswith(expected_prefix):
                    errors.append(
                        f"{tid}: remote issue #{base} title mismatch (got '{remote_title[:40]}…', "
                        f"expected prefix '{expected_prefix}')"
                    )

    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--offline", action="store_true", help="skip remote GitHub issue checks")
    ap.add_argument("--online", action="store_true", help="force remote GitHub issue checks")
    ap.add_argument("--repo", default="webomage/wom7board", help="target GitHub repository")
    ap.add_argument("--json", action="store_true", help="output JSON")
    args = ap.parse_args()

    ts = load_tickets()
    if not ts:
        print("ticket-id-align-check: 0 tickets found — cannot measure", file=sys.stderr)
        return 2

    remote: dict[int, str] | None = None
    if args.online or (not args.offline and os.environ.get("CI") != "true"):
        # Attempt to fetch remote issues if requested or online
        if args.online:
            remote = fetch_remote_issues(args.repo)

    errors = check_alignment(ts, remote_issues=remote)

    if args.json:
        print(json.dumps({
            "total_tickets": len(ts),
            "error_count": len(errors),
            "errors": errors,
            "aligned": len(errors) == 0,
        }, indent=2))
        return 1 if errors else 0

    print(f"ticket-id-align-check — checked {len(ts)} ticket(s)")
    if errors:
        print(f"❌ {len(errors)} alignment error(s):")
        for err in errors[:25]:
            print(f"   · {err}")
        if len(errors) > 25:
            print(f"   … and {len(errors) - 25} more")
        return 1

    remote_msg = f" (verified against {args.repo})" if remote else " (local frontmatter)"
    print(f"[OK] all {len(ts)} tickets strictly aligned: T<n> == gh_issue == #<n>{remote_msg}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
