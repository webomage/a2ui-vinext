#!/usr/bin/env python3
"""Render deploy_log rows and Conventional Commits into CHANGELOG.md, grouped by version.

- Extracts commit ranges between successive deploy commits.
- Categorizes Conventional Commits into Features and Fixes, filtering out noise.
- Links and enriches tickets, sanitizing security/confidential tags.
- Redacts actor personal emails and PII from deployment tables.
- Preserves deploy stamp headings for `just changelog-drift` parity.

Part of release-versioning (T436). Run via `just changelog`.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections import OrderedDict
from pathlib import Path

CONVENTIONAL_RE = re.compile(
    r"^(feat|fix|perf|docs|chore|refactor|test|ci|style|build)(?:\(([^)]+)\))?!?: (.+)$",
    re.IGNORECASE,
)
TICKET_RE = re.compile(r"\b(T\d{1,4})\b")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


def fetch_rows_from_db(db_url: str, limit: int = 500) -> list[str]:
    sql = (
        f"SELECT deployed_at, version, service, COALESCE(commit,''), COALESCE(actor,'') "
        f"FROM public.deploy_log ORDER BY deployed_at DESC LIMIT {limit}"
    )
    try:
        res = subprocess.run(
            ["psql", db_url, "-At", "-F", "\t", "-c", sql],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
        )
        if res.returncode == 0:
            return res.stdout.splitlines()
    except Exception:
        pass
    return []


def sanitize_text(text: str) -> str:
    """Redact personal emails, tokens, and raw confidential markers."""
    text = EMAIL_RE.sub("[redacted]", text)
    text = re.sub(r"\b[A-Z0-9_]{3,}_(?:KEY|SECRET|TOKEN|PASSWORD)\b", "[redacted-secret]", text)
    text = re.sub(r"\b(?:CONFIDENTIAL(?:-CLIENT-[A-Z0-9_]+)?|INTERNAL\s+ONLY)\b", "[internal]", text, flags=re.IGNORECASE)
    return text


def load_ticket_info(ticket_id: str, tasks_dir: Path) -> dict:
    ticket_file = tasks_dir / f"{ticket_id}.md"
    if not ticket_file.exists():
        return {}
    info = {"id": ticket_id, "title": "", "tags": [], "area": ""}
    try:
        content = ticket_file.read_text(encoding="utf-8")
        in_fm = False
        for line in content.splitlines():
            line_str = line.strip()
            if line_str == "---":
                if not in_fm:
                    in_fm = True
                    continue
                else:
                    break
            if in_fm:
                if line_str.startswith("title:"):
                    info["title"] = line_str.split(":", 1)[1].strip().strip("\"'")
                elif line_str.startswith("tags:"):
                    raw_tags = line_str.split(":", 1)[1].strip()
                    if raw_tags.startswith("[") and raw_tags.endswith("]"):
                        info["tags"] = [t.strip().strip("\"'") for t in raw_tags[1:-1].split(",") if t.strip()]
                elif line_str.startswith("area:"):
                    info["area"] = line_str.split(":", 1)[1].strip().strip("\"'")
    except Exception:
        pass
    return info


def get_commits_in_range(
    root: Path,
    curr_commit: str,
    prev_commit: str = "",
    curr_time: str = "",
    prev_time: str = "",
) -> list[tuple[str, str, str]]:
    """Retrieve commits (sha, subject, body) between two deploy points."""
    cmd = ["git", "-C", str(root), "log", "--no-merges", "--pretty=format:%H%x09%s%x09%b"]

    has_curr = False
    has_prev = False
    if curr_commit and curr_commit != "-":
        r = subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", curr_commit], capture_output=True)
        has_curr = (r.returncode == 0)
    if prev_commit and prev_commit != "-":
        r = subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", prev_commit], capture_output=True)
        has_prev = (r.returncode == 0)

    # Check direct ancestor range
    if has_curr and has_prev:
        anc = subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", prev_commit, curr_commit], capture_output=True)
        if anc.returncode == 0:
            res = subprocess.run(cmd + [f"{prev_commit}..{curr_commit}"], capture_output=True, text=True)
            if res.returncode == 0 and res.stdout.strip():
                return _parse_git_log_output(res.stdout)

    # Fall back to timestamp window if available
    if curr_time and prev_time:
        res = subprocess.run(cmd + [f"--since={prev_time}", f"--until={curr_time}"], capture_output=True, text=True)
        if res.returncode == 0 and res.stdout.strip():
            return _parse_git_log_output(res.stdout)

    # Single commit fallback
    if has_curr:
        res = subprocess.run(cmd + ["-n", "10", curr_commit], capture_output=True, text=True)
        if res.returncode == 0 and res.stdout.strip():
            return _parse_git_log_output(res.stdout)

    return []


def _parse_git_log_output(raw: str) -> list[tuple[str, str, str]]:
    commits = []
    for line in raw.splitlines():
        parts = line.split("\t")
        sha = parts[0]
        subject = parts[1] if len(parts) > 1 else ""
        body = parts[2] if len(parts) > 2 else ""
        commits.append((sha, subject, body))
    return commits


def categorize_commits(
    commits: list[tuple[str, str, str]], tasks_dir: Path
) -> dict[str, list[str]]:
    features: list[str] = []
    fixes: list[str] = []

    seen_subjects = set()

    for sha, subject, body in commits:
        if not subject:
            continue
        subj_clean = subject.strip()
        if subj_clean in seen_subjects:
            continue
        seen_subjects.add(subj_clean)

        m = CONVENTIONAL_RE.match(subj_clean)
        commit_type = ""
        scope = ""
        desc = subj_clean

        if m:
            commit_type = m.group(1).lower()
            scope = m.group(2) or ""
            desc = m.group(3).strip()
        else:
            if subj_clean.lower().startswith("feat"):
                commit_type = "feat"
            elif subj_clean.lower().startswith("fix"):
                commit_type = "fix"

        # Filter out internal plumbing noise
        if commit_type in ("chore", "ci", "test", "style", "refactor", "build"):
            continue

        if commit_type not in ("feat", "fix", "perf"):
            continue

        # Find tickets
        tickets = TICKET_RE.findall(subj_clean + " " + body)
        ticket_links = []
        is_security = False

        for t in OrderedDict.fromkeys(tickets):
            t_info = load_ticket_info(t, tasks_dir)
            t_tags = t_info.get("tags", [])
            if any(tag in ("security", "p0", "cve", "vulnerability") for tag in t_tags):
                is_security = True
            ticket_links.append(f"[{t}](file:///.tasks/{t}.md)")

        scope_str = f"**{scope}**: " if scope else ""
        clean_desc = sanitize_text(desc)

        if is_security:
            # Neutralize sensitive vulnerability mechanics
            clean_desc = re.sub(
                r"(?:exploit|vulnerability|bypass|leak|forge|invalidation race|injection).*",
                "security hardening & verification",
                clean_desc,
                flags=re.IGNORECASE,
            )

        ticket_suffix = f" ({', '.join(ticket_links)})" if ticket_links else ""
        entry = f"- {scope_str}{clean_desc}{ticket_suffix}"

        if commit_type == "feat" or commit_type == "perf":
            features.append(entry)
        elif commit_type == "fix":
            fixes.append(entry)

    return {"features": features, "fixes": fixes}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="CHANGELOG.md", help="Output changelog path")
    parser.add_argument("--root", default=".", help="Workspace root directory")
    parser.add_argument("--limit", type=int, default=500, help="DB query row limit")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    tasks_dir = root / ".tasks"
    out_path = Path(args.out)

    lines: list[str] = []
    if not sys.stdin.isatty():
        lines = [line.rstrip("\n") for line in sys.stdin]
    else:
        db_url = os.environ.get("DATABASE_URL")
        if db_url:
            lines = fetch_rows_from_db(db_url, limit=args.limit)
        else:
            print("DATABASE_URL not set and nothing on stdin", file=sys.stderr)
            return 1

    groups: OrderedDict[str, dict] = OrderedDict()
    for line in lines:
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        deployed_at, version, service = parts[0], parts[1], parts[2]
        commit = parts[3] if len(parts) > 3 else ""
        actor = parts[4] if len(parts) > 4 else ""
        g = groups.setdefault(version, {"first_seen": deployed_at, "rows": []})
        g["rows"].append((service, commit, actor, deployed_at))

    version_list = list(groups.items())

    out = [
        "# Changelog",
        "",
        "_Generated from the `deploy_log` table by `just changelog`. "
        "Each heading is one deploy stamp (`YYYY.MM.DD-<unixtimestamp>`)._",
        "",
    ]

    for idx, (version, g) in enumerate(version_list):
        out.append(f"## {version}")
        out.append(f"_First deployed: {g['first_seen']}_")
        out.append("")

        # Resolve primary release commit and previous release commit
        curr_commit = ""
        for svc, c, _, _ in g["rows"]:
            if svc == "release" and c:
                curr_commit = c
                break
        if not curr_commit and g["rows"]:
            curr_commit = g["rows"][0][1]

        prev_commit = ""
        prev_time = ""
        if idx + 1 < len(version_list):
            prev_g = version_list[idx + 1][1]
            prev_time = prev_g["first_seen"]
            for svc, c, _, _ in prev_g["rows"]:
                if svc == "release" and c:
                    prev_commit = c
                    break
            if not prev_commit and prev_g["rows"]:
                prev_commit = prev_g["rows"][0][1]

        commits = get_commits_in_range(
            root,
            curr_commit=curr_commit,
            prev_commit=prev_commit,
            curr_time=g["first_seen"],
            prev_time=prev_time,
        )

        categorized = categorize_commits(commits, tasks_dir)

        if categorized["features"]:
            out.append("### Features")
            out.extend(categorized["features"])
            out.append("")

        if categorized["fixes"]:
            out.append("### Fixes")
            out.extend(categorized["fixes"])
            out.append("")

        # Public deployment table (Redacting personal actor email)
        out.append("| Service | Commit | Deployed at |")
        out.append("|---|---|---|")
        for service, commit, actor, deployed_at in g["rows"]:
            out.append(f"| {service} | `{commit or '-'}` | {deployed_at} |")
        out.append("")

    rendered = "\n".join(out) + "\n"
    # Ensure all rendered text is sanitized
    rendered = sanitize_text(rendered)

    out_path.write_text(rendered, encoding="utf-8")
    print(f"Wrote {out_path} ({len(groups)} version(s)).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
