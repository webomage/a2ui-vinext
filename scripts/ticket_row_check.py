#!/usr/bin/env python3
"""ticket_row_check.py (T527 AC1 / AC4) — Ensure every .tasks/T*.md ticket has a row in TASKS.md.

Why this exists:
On 2026-10-01, `just deploy-all` failed at preflight because `state-check` reported T525 and T526
as "newly invisible" — `.tasks/T525.md` and `.tasks/T526.md` had been created and committed without
re-rendering `TASKS.md`.

Modes:
  python3 scripts/ticket_row_check.py          # Pre-commit mode: auto-runs tasks_render.py + git add TASKS.md
                                               # when a row is missing, then fails closed if still missing.
  python3 scripts/ticket_row_check.py --check  # Verify-only (pre-push / CI): exit 1 if any .tasks/T*.md
                                               # has no row in TASKS.md.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

TASKS_ROW_RE = re.compile(r"^\|\s*[*_`]*\s*\[?\s*(T\d+[a-z]?)\s*\]?", re.M)
TICKET_STEM_RE = re.compile(r"^T(\d+)[a-z]?$")


def _num_id(tid: str) -> tuple[int, str]:
    m = re.search(r"\d+", tid)
    return (int(m.group(0)) if m else 0, tid)


def resolve_root(explicit_root: Path | None = None) -> Path:
    if explicit_root is not None:
        return explicit_root.resolve()
    env_root = os.environ.get("W0M_ROOT")
    if env_root:
        return Path(env_root).resolve()
    return Path(__file__).resolve().parents[1]


def find_missing_rows(root: Path) -> tuple[list[str], list[str]]:
    """Return (all_ticket_ids, missing_ticket_ids) comparing .tasks/T*.md against TASKS.md."""
    tasks_dir = root / ".tasks"
    tasks_md = root / "TASKS.md"

    if not tasks_dir.is_dir():
        return [], []

    ticket_ids: list[str] = []
    for p in sorted(tasks_dir.glob("T*.md"), key=lambda f: _num_id(f.stem)):
        if TICKET_STEM_RE.match(p.stem):
            ticket_ids.append(p.stem)

    if not ticket_ids:
        return [], []

    if not tasks_md.is_file():
        return ticket_ids, list(ticket_ids)

    content = tasks_md.read_text(encoding="utf-8", errors="replace")
    board_ids = set(TASKS_ROW_RE.findall(content))
    missing = [tid for tid in ticket_ids if tid not in board_ids]
    return ticket_ids, missing


def check_ticket_rows(
    root: Path,
    *,
    auto_render: bool = False,
    stage: bool = True,
) -> tuple[bool, list[str], bool]:
    """Check that every .tasks/T*.md has a row in TASKS.md.

    Returns (ok, missing_ids, rendered_and_staged).
    """
    ticket_ids, missing = find_missing_rows(root)
    if not missing:
        return True, [], False

    rendered = False
    render_script = root / "scripts" / "tasks_render.py"
    if auto_render and render_script.is_file():
        res = subprocess.run(
            [
                sys.executable,
                str(render_script),
                "--tasks-dir",
                str(root / ".tasks"),
                "--output",
                str(root / "TASKS.md"),
            ],
            cwd=str(root),
            capture_output=True,
            text=True,
        )
        if res.returncode == 0:
            rendered = True
            if stage and (root / ".git").exists():
                subprocess.run(
                    ["git", "-C", str(root), "add", "TASKS.md"],
                    capture_output=True,
                    text=True,
                )
            _, missing = find_missing_rows(root)

    return len(missing) == 0, missing, rendered


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--check",
        action="store_true",
        help="Verify-only: do not run tasks_render.py; exit 1 if any ticket lacks a TASKS.md row.",
    )
    ap.add_argument(
        "--no-auto-render",
        action="store_true",
        help="Disable automatic tasks_render.py execution even in pre-commit mode.",
    )
    ap.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Override workspace root directory.",
    )
    args = ap.parse_args(argv)

    root = resolve_root(args.root)
    ticket_ids, initial_missing = find_missing_rows(root)
    if not initial_missing:
        print(f"✅ ticket-row-check: all {len(ticket_ids)} ticket(s) have a board row in TASKS.md.")
        return 0

    auto_render = not args.check and not args.no_auto_render
    ok, missing, rendered = check_ticket_rows(root, auto_render=auto_render, stage=True)
    if ok:
        print(
            f"✅ ticket-row-check: auto-rendered and staged TASKS.md for {', '.join(initial_missing)}."
        )
        return 0

    print(
        f"❌ ticket-row-check: newly invisible ticket(s) in .tasks/ with no row in TASKS.md: "
        f"{', '.join(missing)} (run 'just tasks-render' and stage TASKS.md)",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
