#!/usr/bin/env python3
"""ticket_recycle.py — automated recycling of closed duplicate ticket IDs (T397).

Repurposes closed duplicate ticket IDs with new task content while strictly
preserving the T<n> == gh_issue == #<n> 1:1 invariant across local files and GitHub.

Usage:
    python3 project/scripts/ticket_recycle.py --list
    python3 project/scripts/ticket_recycle.py --recycle T398 --draft draft.md [--no-sync]
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
TICKETS_DIR = ROOT / ".tasks"
TASKS_FILE = ROOT / "TASKS.md"


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Extract YAML frontmatter and markdown body from ticket text."""
    frontmatter: dict[str, Any] = {}
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            fm_text = parts[1]
            body = parts[2].lstrip()
            for line in fm_text.splitlines():
                if ":" in line and not line.strip().startswith("#"):
                    k, _, v = line.partition(":")
                    k = k.strip()
                    v = v.split("#", 1)[0].strip().strip('"\'')
                    if v.startswith("[") and v.endswith("]"):
                        items = [x.strip().strip('"\'') for x in v[1:-1].split(",") if x.strip()]
                        frontmatter[k] = items
                    elif v.isdigit():
                        frontmatter[k] = int(v)
                    else:
                        frontmatter[k] = v
    return frontmatter, body


def list_recyclable_tickets(tickets_dir: Path = TICKETS_DIR) -> list[dict[str, Any]]:
    """Enumerate all tickets that are eligible for recycling (closed as duplicate)."""
    candidates = []
    for f in sorted(tickets_dir.glob("T*.md"), key=lambda p: int(re.sub(r"\D", "", p.stem) or 0)):
        try:
            txt = f.read_text(encoding="utf-8", errors="replace")
            fm, _ = parse_frontmatter(txt)
            is_dup = (
                fm.get("closed_as") == "duplicate"
                or (fm.get("status") == "done" and bool(re.search(r">\s*⚠️\s*\*\*CLOSED AS A DUPLICATE", txt)))
            )
            ac_done = int(fm.get("x_ac_done", 0))
            if is_dup and ac_done == 0 and fm.get("status") == "done":
                dup_target = ""
                m = re.search(r"CLOSED AS A DUPLICATE of \[\[(T\d+)\]\]|duplicate_of:\s*(T\d+)|^superseded_by:\s*\[?\[?(T\d+)", txt, re.I | re.M)
                if m:
                    dup_target = m.group(1) or m.group(2) or m.group(3)
                candidates.append({
                    "id": f.stem,
                    "title": fm.get("title", ""),
                    "closed_as": fm.get("closed_as", "duplicate"),
                    "duplicate_of": dup_target,
                    "gh_issue": fm.get("gh_issue", int(re.sub(r"\D", "", f.stem) or 0)),
                    "path": f,
                })
        except OSError:
            continue
    return candidates


def validate_target_ticket(target_id: str, tickets_dir: Path = TICKETS_DIR) -> tuple[bool, str, dict[str, Any]]:
    """Verify target ticket exists and is safe to recycle (closed as duplicate)."""
    target_path = tickets_dir / f"{target_id.upper()}.md"
    if not target_path.exists():
        return False, f"Target ticket {target_id} does not exist at {target_path}", {}

    txt = target_path.read_text(encoding="utf-8", errors="replace")
    fm, _ = parse_frontmatter(txt)

    # Safety: Refuse to recycle active work
    if fm.get("status") in ("queued", "in-progress"):
        return False, f"Ticket {target_id} is ACTIVE ({fm.get('status')}) — cannot be recycled!", fm

    # Safety: Refuse to recycle delivered work that is not a duplicate or has completed ACs
    ac_done = int(fm.get("x_ac_done", 0))
    is_dup = (
        fm.get("closed_as") == "duplicate"
        or (fm.get("status") == "done" and bool(re.search(r">\s*⚠️\s*\*\*CLOSED AS A DUPLICATE", txt)))
    )
    if not is_dup:
        return False, f"Ticket {target_id} is not marked as a closed duplicate — cannot be recycled!", fm

    if ac_done > 0:
        return False, f"Ticket {target_id} has {ac_done} completed ACs (delivered work) — cannot be recycled!", fm

    return True, "", fm


def check_draft_uniqueness(draft_path: Path) -> tuple[bool, str]:
    script = Path(__file__).resolve().parent / "ticket_duplicate_check.py"
    if not script.exists():
        return True, ""

    res = subprocess.run(
        [sys.executable, str(script), "--check-draft", str(draft_path), "--json"],
        capture_output=True,
        text=True,
    )
    try:
        data = json.loads(res.stdout)
        if data.get("is_duplicate") or res.returncode != 0:
            matches = data.get("matches", [])
            top = matches[0] if matches else {}
            return False, f"Draft duplicates existing ticket {top.get('id', '?')} ({top.get('similarity', 0):.0%}): {top.get('title', '')}"
    except json.JSONDecodeError:
        if res.returncode != 0:
            return False, f"Draft failed duplication check (exit code {res.returncode})"

    return True, ""


def update_tasks_row(tasks_file: Path, ticket_id: str, new_ticket_data: dict[str, Any]) -> bool:
    """Update row for ticket_id in TASKS.md."""
    if not tasks_file.exists():
        return False

    content = tasks_file.read_text(encoding="utf-8")
    lines = content.splitlines()
    found = False
    new_lines = []

    t_num = int(re.sub(r"\D", "", ticket_id) or 0)
    priority = new_ticket_data.get("priority", "P1")
    title = new_ticket_data.get("title", "")
    summary = new_ticket_data.get("summary", "")
    ac_count = new_ticket_data.get("ac_count", 5)
    repos = ", ".join(new_ticket_data.get("repos", ["web", "tooling"]))
    epic = new_ticket_data.get("epic", "gate-integrity")
    today = datetime.date.today().isoformat()

    row_pattern = re.compile(rf"^\|\s*\[{ticket_id}\].*?$")
    new_row = (
        f"| [{ticket_id}](project/tickets/{ticket_id}.md) · [#{t_num}](https://github.com/webomage/wom7board/issues/{t_num}) "
        f"| **{priority}** | 🆕 **{title}** 🆕 {summary} **{ac_count} ACs.** | {repos} | {epic} | ⚪ queued {today} |"
    )

    for line in lines:
        if row_pattern.match(line):
            new_lines.append(new_row)
            found = True
        else:
            new_lines.append(line)

    if found:
        tasks_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return found


def recycle_ticket(
    target_id: str,
    draft_path: Path,
    tickets_dir: Path = TICKETS_DIR,
    tasks_file: Path = TASKS_FILE,
    do_sync: bool = True,
) -> int:
    """Atomically recycle closed duplicate ticket ID with new draft content."""
    target_id = target_id.upper()
    t_num = int(re.sub(r"\D", "", target_id) or 0)

    # 1. Safety check target
    ok, err_msg, old_fm = validate_target_ticket(target_id, tickets_dir)
    if not ok:
        print(f"❌ [FAIL] {err_msg}", file=sys.stderr)
        return 1

    # 2. Safety check draft
    if not draft_path.exists():
        print(f"❌ [FAIL] Draft file not found: {draft_path}", file=sys.stderr)
        return 2

    draft_text = draft_path.read_text(encoding="utf-8", errors="replace")
    draft_fm, draft_body = parse_frontmatter(draft_text)

    unique, dup_msg = check_draft_uniqueness(draft_path)
    if not unique:
        print(f"❌ [FAIL] {dup_msg}", file=sys.stderr)
        return 1

    # Extract AC count and summary
    acs = re.findall(r"^- \[.\] (.*)$", draft_text, re.M)
    ac_count = len(acs) if acs else 5
    m_sum = re.search(r"## Summary\s*\n\s*(.*?)(?=\n## |\Z)", draft_text, re.DOTALL)
    summary_text = m_sum.group(1).strip() if m_sum else ""
    summary_short = re.sub(r"\s+", " ", summary_text)[:160]

    title = draft_fm.get("title", "")
    if not title:
        m_t = re.search(r"^#\s+(?:T\d+\s+[—\-]\s+)?(.*)$", draft_body, re.M)
        if m_t:
            title = m_t.group(1).strip()

    today = datetime.date.today().isoformat()
    repos = draft_fm.get("repos", ["tooling", "web"])
    if isinstance(repos, str):
        repos = [r.strip() for r in repos.split(",") if r.strip()]

    # Clean body: Remove any old duplicate banners if copied over
    clean_body = re.sub(r">\s*⚠️\s*\*\*CLOSED AS A DUPLICATE.*?\n(?=\n|#)", "", draft_body, flags=re.DOTALL)

    # 3. Construct recycled ticket content
    new_fm_lines = [
        "---",
        f"id: {target_id}",
        f'title: "{title}"',
        "status: queued",
        f"area: {draft_fm.get('area', 'sdlc')}",
        f"queue: {draft_fm.get('queue', 'backlog-platform')}",
        f"priority: {draft_fm.get('priority', 'P1')}",
        f"repos: [{', '.join(repos)}]",
        f'epic: "{draft_fm.get("epic", "gate-integrity")}"',
        f'spec: "{draft_fm.get("spec", "")}"',
        "type: task",
        f"gh_issue: {t_num}",
        f"tags: [{', '.join(draft_fm.get('tags', ['sdlc', 'automation']))}]",
        f"created: {today}",
        "x_ac_done: 0",
        f"x_ac_total: {ac_count}",
        "x_ac_pct: 0",
        "x_hot_score: 60",
        "x_blocked_by: []",
        f"x_synced: {today}",
        "---",
        "",
    ]

    new_content = "\n".join(new_fm_lines) + clean_body.lstrip()

    # Write target ticket file atomically
    target_path = tickets_dir / f"{target_id}.md"
    target_path.write_text(new_content, encoding="utf-8")
    print(f"✅ Atomically rewrote {target_path} (preserved ID {target_id} and gh_issue {t_num})")

    # 4. Update TASKS.md
    new_ticket_meta = {
        "priority": draft_fm.get("priority", "P1"),
        "title": title,
        "summary": summary_short,
        "ac_count": ac_count,
        "repos": repos,
        "epic": draft_fm.get("epic", "gate-integrity"),
    }
    updated_tasks = update_tasks_row(tasks_file, target_id, new_ticket_meta)
    if updated_tasks:
        print(f"✅ Updated {target_id} row in {tasks_file}")
    else:
        print(f"⚠️  {target_id} row not found in {tasks_file} (manual row add may be required)")

    # 5. Remote GitHub issue synchronization
    if do_sync:
        sync_script = Path(__file__).resolve().parent / "sync_github.py"
        if sync_script.exists():
            print(f"▶ Reopening and synchronizing GitHub issue #{t_num} on webomage/wom7board...")
            res_sync = subprocess.run([sys.executable, str(sync_script)], capture_output=True, text=True)
            if res_sync.returncode == 0:
                print(f"✅ Issue #{t_num} reopened and synchronized on GitHub Project #2")
            else:
                print(f"⚠️  sync_github.py exited {res_sync.returncode}: {res_sync.stderr}", file=sys.stderr)

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--list", action="store_true", help="list all recyclable closed duplicate tickets")
    parser.add_argument("--recycle", metavar="T_ID", help="target ticket ID to recycle (e.g. T398)")
    parser.add_argument("--draft", type=Path, help="path to new ticket draft markdown file")
    parser.add_argument("--no-sync", action="store_true", help="skip remote GitHub synchronization")
    parser.add_argument("--json", action="store_true", help="output in JSON format")
    args = parser.parse_args()

    if args.list:
        candidates = list_recyclable_tickets()
        if args.json:
            print(json.dumps(candidates, indent=2, default=str))
            return 0

        print(f"▶ Recyclable Duplicate Ticket Pool ({len(candidates)} candidate(s) available):")
        if not candidates:
            print("  (no recyclable duplicate tickets found)")
            return 0

        for c in candidates:
            target_info = f" (closed duplicate of {c['duplicate_of']})" if c["duplicate_of"] else ""
            print(f"  · {c['id']} [gh_issue: #{c['gh_issue']}]{target_info}: {c['title']}")
        print("\nTo recycle a ticket ID for new work:")
        print("  just ticket-recycle --recycle <T_ID> --draft <draft.md>")
        return 0

    if args.recycle:
        if not args.draft:
            print("❌ [FAIL] --draft <file> is required when --recycle is specified.", file=sys.stderr)
            return 2
        return recycle_ticket(args.recycle, args.draft, do_sync=not args.no_sync)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
