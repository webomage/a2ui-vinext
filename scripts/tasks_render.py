#!/usr/bin/env python3
"""tasks_render.py (T411 AC2 / T412 AC3) — Compile TASKS.md deterministically from .tasks/T*.md files.

Turns TASKS.md into a 100% generated / synchronised projection from individual ticket files.
Agents edit .tasks/T##.md directly and never have to resolve markdown table merge conflicts.
Compiles to @wom/TASKS.md and maintains a symlink at wom7web/TASKS.md.

Usage:
  python3 scripts/tasks_render.py          # Regenerates TASKS.md
  python3 scripts/tasks_render.py --check  # Verifies TASKS.md is in sync (exit 0/1)
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any


def find_workspace_root(start_path: Path | None = None) -> Path:
    """Find the workspace root containing .tasks and .w0m/sdlc.json."""
    cur = (start_path or Path(__file__)).resolve()
    for parent in [cur] + list(cur.parents):
        if (parent / ".tasks").is_dir() and (parent / ".w0m").is_dir():
            return parent
        if (parent / ".git").exists() and (parent / "wom7web").is_dir():
            return parent
    return Path(__file__).resolve().parents[1]


WORKSPACE_ROOT = find_workspace_root()
MONO_ROOT = WORKSPACE_ROOT
WEB_ROOT = WORKSPACE_ROOT / "wom7web" if (WORKSPACE_ROOT / "wom7web").is_dir() else WORKSPACE_ROOT

# Allow importing tasks_query from root scripts or wom7web
sys.path.insert(0, str(WORKSPACE_ROOT / "scripts"))
sys.path.insert(0, str(WEB_ROOT / "project" / "scripts"))

tq: Any = None
try:
    import tasks_query as _tq
    tq = _tq
except ImportError:
    pass


STATUS_GLYPHS = {
    "done": "✅",
    "archived": "✅",
    "in-progress": "🟡",
    "blocked": "🔵",
    "paused": "💤",
    "queued": "⚪",
}


def parse_frontmatter(text: str) -> dict:
    """Extract frontmatter dict from ticket markdown."""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    out: dict = {}
    for line in text[3:end].splitlines():
        m = re.match(r"^([a-z_]+):\s*(.*)$", line.strip())
        if not m:
            continue
        key, raw = m.group(1), m.group(2).strip()
        if raw[:1] in ("\"", "'"):
            q = raw[0]
            closing = raw.find(q, 1)
            value = raw[1:closing] if closing > 0 else raw[1:]
        else:
            value = re.split(r"\s+#", raw, maxsplit=1)[0].strip()
        out[key] = value
    return out


def num_id(tid: str) -> int:
    m = re.search(r"\d+", tid)
    return int(m.group(0)) if m else 0


def render_row(ticket_data: dict, existing_row: str | None = None) -> str:
    """Render a clean 6-cell markdown row conforming to tasks_bounds."""
    tid = ticket_data["id"]
    status = ticket_data.get("status", "queued")
    prio = ticket_data.get("priority", "P2") or "P2"
    prio_str = f"**{prio}**" if prio in ("P0", "P1", "P2") else prio
    glyph = STATUS_GLYPHS.get(status, "⚪")
    if prio == "P0" and status == "queued":
        glyph = "🔴"

    # If existing row is present and valid, preserve its prose while syncing status & priority
    if existing_row:
        raw = existing_row.rstrip()
        cols = raw.split(" | ")
        if len(cols) == 6 and raw.endswith("|"):
            # Update col 1 (priority) and col 5 (status)
            cols[1] = prio_str
            # Keep status notes/details if already present, but ensure glyph and status match
            curr_status_cell = cols[5].rstrip("|").strip()
            # If current status cell already declares this status, keep it, else update
            if status in curr_status_cell or (status == "done" and "DONE" in curr_status_cell):
                status_cell = curr_status_cell
            else:
                status_cell = f"{glyph} **{status}**"
            cols[5] = status_cell + " |"
            return " | ".join(cols)

    # Format new row
    title = ticket_data.get("title", f"Ticket {tid}")
    repos = ticket_data.get("repos", "web")
    if isinstance(repos, str) and repos.startswith("[") and repos.endswith("]"):
        repos = repos[1:-1].replace("'", "").replace('"', "")
    spec = ticket_data.get("spec", "—") or "—"
    gh_issue = ticket_data.get("gh_issue", "0")
    
    # Path relative link
    link = f"[{tid}](.tasks/{tid}.md)"
    if gh_issue and gh_issue != "0":
        link += f" · [#{gh_issue}](https://github.com/casualuser/webomage.com/issues/{gh_issue})"

    status_cell = f"{glyph} **{status}**"
    task_text = f"🆕 **{title}**" if status == "queued" else f"**{title}**"
    
    return f"| {link} | {prio_str} | {task_text} | {repos} | {spec} | {status_cell} |"


def render_tasks_md(
    tasks_dir: Path | None = None,
    output_path: Path | None = None,
    base_tasks_md: Path | None = None,
) -> str:
    """Compile TASKS.md from ticket files."""
    if tasks_dir is None:
        if tq:
            tasks_dir = tq.resolve_tickets_dir()
        else:
            tasks_dir = WORKSPACE_ROOT / ".tasks"
            if not tasks_dir.is_dir():
                tasks_dir = WEB_ROOT / "project" / "tickets"

    if output_path is None:
        output_path = WORKSPACE_ROOT / "TASKS.md"

    if base_tasks_md is None:
        base_tasks_md = output_path if (output_path and output_path.exists()) else (WORKSPACE_ROOT / "TASKS.md")
        if not base_tasks_md.exists() and (WEB_ROOT / "TASKS.md").exists():
            base_tasks_md = WEB_ROOT / "TASKS.md"

    # Collect all tickets
    tickets: list[dict] = []
    for p in sorted(tasks_dir.glob("T*.md"), key=lambda f: num_id(f.stem)):
        txt = p.read_text(encoding="utf-8", errors="replace")
        fm = parse_frontmatter(txt)
        if fm.get("id"):
            tickets.append(fm)

    # Read existing TASKS.md to preserve existing rows and section headings if present
    existing_rows: dict[str, str] = {}
    header_prose = ""
    if base_tasks_md and base_tasks_md.exists():
        content = base_tasks_md.read_text(encoding="utf-8", errors="replace")
        # Split header before the first section heading (## )
        first_section = re.search(r"^##\s+", content, re.M)
        if first_section:
            header_prose = content[:first_section.start()]
        else:
            table_start = content.find("| # |")
            if table_start != -1:
                header_prose = content[:table_start]
        for line in content.splitlines():
            m = re.match(r"^\|\s*\[(T\d+[a-c]?)\]", line)
            if m:
                existing_rows[m.group(1)] = line

    if not header_prose:
        header_prose = (
            "# w0m — Task Queue\n\n"
            "> 🤝 **New agent / handoff? Read [`STATE.md`](STATE.md) first**\n\n"
            "Living, traced task queue across all w0m repos.\n"
            "This file is a GENERATED view compiled from `.tasks/T*.md` via `just tasks-render`.\n"
            "Agents edit `.tasks/T##.md` files directly. Do not manually resolve merge conflicts here.\n\n"
            "**Status legend:** 🔴 blocked/regression-shaped · 🟡 in progress · ⚪ queued · ✅ done · 💤 paused\n\n"
            "---\n\n"
        )

    # Partition tickets
    active_p0: list[dict] = []
    in_flight: list[dict] = []
    queued: list[dict] = []
    done: list[dict] = []
    paused_blocked: list[dict] = []

    for t in tickets:
        status = t.get("status", "queued")
        prio = t.get("priority", "P2")
        queue = t.get("queue", "")
        if status in ("done", "archived"):
            done.append(t)
        elif status == "in-progress" or prio == "P0" or queue == "now":
            active_p0.append(t)
        elif status in ("blocked", "paused"):
            paused_blocked.append(t)
        else:
            queued.append(t)

    # Deterministic sort within buckets
    prio_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "": 4}
    active_p0.sort(key=lambda x: (prio_order.get(x.get("priority", ""), 4), -num_id(x["id"])))
    queued.sort(key=lambda x: (prio_order.get(x.get("priority", ""), 4), -num_id(x["id"])))
    done.sort(key=lambda x: -num_id(x["id"]))

    lines: list[str] = [header_prose.rstrip(), ""]

    table_header = [
        "| # | Prio | Task | Repos | Ref | Status |",
        "|---|------|------|-------|-----|--------|",
    ]

    # Section 1: Active / Now
    lines.append("## NOW (active / top priority)\n")
    lines.extend(table_header)
    for t in active_p0:
        lines.append(render_row(t, existing_rows.get(t["id"])))
    lines.append("")

    # Section 2: In-Flight & Queued Backlog
    if queued or paused_blocked:
        lines.append("## QUEUED & BACKLOG\n")
        lines.extend(table_header)
        for t in queued:
            lines.append(render_row(t, existing_rows.get(t["id"])))
        for t in paused_blocked:
            lines.append(render_row(t, existing_rows.get(t["id"])))
        lines.append("")

    # Section 3: Completed
    if done:
        lines.append("## COMPLETED (recent done)\n")
        lines.extend(table_header)
        for t in done:
            lines.append(render_row(t, existing_rows.get(t["id"])))
        lines.append("")

    result = "\n".join(lines) + "\n"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(result, encoding="utf-8")

    # Maintain backward-compatible symlink at wom7web/TASKS.md if compiling to root TASKS.md
    if output_path.resolve() == (WORKSPACE_ROOT / "TASKS.md").resolve() and WEB_ROOT.is_dir():
        web_tasks = WEB_ROOT / "TASKS.md"
        if not web_tasks.is_symlink() or not web_tasks.resolve().is_file():
            if web_tasks.exists() or web_tasks.is_symlink():
                web_tasks.unlink()
            try:
                rel = os.path.relpath(output_path, WEB_ROOT)
                web_tasks.symlink_to(rel)
            except OSError:
                pass

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile TASKS.md from .tasks/ ticket files.")
    parser.add_argument("--check", action="store_true", help="Check if TASKS.md is in sync without writing.")
    parser.add_argument("--output", type=Path, default=None, help="Output TASKS.md path.")
    parser.add_argument("--tasks-dir", type=Path, default=None, help="Input tickets directory.")
    args = parser.parse_args()

    out_file = args.output or (WORKSPACE_ROOT / "TASKS.md")
    if args.check:
        if not out_file.exists():
            print(f"❌ TASKS.md does not exist at {out_file}.")
            return 1
        current = out_file.read_text(encoding="utf-8")
        rendered = render_tasks_md(
            tasks_dir=args.tasks_dir,
            output_path=Path("/tmp/tasks_render_check.md"),
            base_tasks_md=out_file,
        )
        if current != rendered:
            print("❌ TASKS.md is out of sync with ticket files. Run 'just tasks-render' to update.")
            return 1
        print("✅ TASKS.md is in sync.")
        return 0

    render_tasks_md(tasks_dir=args.tasks_dir, output_path=out_file)
    print(f"✅ TASKS.md successfully rendered to {out_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
