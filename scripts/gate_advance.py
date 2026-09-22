#!/usr/bin/env python3
"""Atomic ticket gate transition (T119 AC5).

WHY THIS EXISTS
    Advancing a ticket touches three surfaces that must agree: the ticket's YAML
    status, its TASKS.md row, and project/tickets.json. Doing that by hand is how
    they drift — and it is not hypothetical. During T117 (2026-07-22) a hand-edit
    of tickets.json used json.dumps WITHOUT ensure_ascii=False, re-encoding every
    non-ASCII character in the file and turning a one-line change into a 47-line
    diff. It was caught only because the diff was read.

    So this writes tickets.json through exactly the contract sync_github.py uses
    (indent=2, ensure_ascii=False, trailing newline), and refuses to write at all
    unless every surface it is about to touch was found.

WHAT IT DOES NOT DO
    It does not commit. Staging is offered (--stage) but the commit is left to the
    caller, because the commit message is the one part of a transition that should
    never be templated — it is where the reasoning lives.

Usage:
    python3 scripts/gate_advance.py T117 --status in-progress --note "spec written"
    python3 scripts/gate_advance.py T117 --status done --glyph ✅ --stage
    python3 scripts/gate_advance.py T117 --status blocked --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import NoReturn

def find_workspace_root(start_path: Path | None = None) -> Path:
    """Find the workspace root containing .tasks and .w0m/sdlc.json."""
    cur = (start_path or Path(__file__)).resolve()
    for parent in [cur] + list(cur.parents):
        if (parent / ".tasks").is_dir() and (parent / ".w0m").is_dir():
            return parent
        if (parent / ".git").exists() and (parent / "wom7web").is_dir():
            return parent
    return Path(__file__).resolve().parents[1]


ROOT = find_workspace_root()
TASKS = ROOT / "TASKS.md"
MANIFEST = ROOT / "wom7web" / "project" / "tickets.json"

WORD_FOR = {"⚪": "queued", "🟡": "in-progress", "🔴": "blocked", "💤": "paused", "✅": "done"}

# status -> the TASKS.md glyph that means the same thing
GLYPH = {
    "queued": "⚪",
    "in-progress": "🟡",
    "blocked": "🔴",
    "paused": "💤",
    "done": "✅",
}


def fail(msg: str) -> NoReturn:
    """Print and exit. Declared NoReturn because it never returns — that is what lets a
    caller's `if x is None: fail(...)` narrow `x` for everything after it (T189)."""
    print(f"❌ gate-advance: {msg}", file=sys.stderr)
    sys.exit(1)


def load_ticket(tid: str) -> Path:
    p = ROOT / ".tasks" / f"{tid}.md"
    if not p.is_file():
        fail(f"no ticket file at {p.relative_to(ROOT)}")
    return p



def set_frontmatter_status(text: str, status: str) -> str:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        fail("ticket has no YAML frontmatter")
    fm = m.group(1)
    if not re.search(r"^status:\s*\S+", fm, re.M):
        fail("ticket frontmatter has no `status:` key")
    # Preserve any trailing comment on the status line (e.g. the allowed-values hint).
    new_fm = re.sub(
        r"^status:\s*\S+(\s*#.*)?$",
        lambda mm: f"status: {status}{mm.group(1) or ''}",
        fm, count=1, flags=re.M,
    )
    return text[:m.start(1)] + new_fm + text[m.end(1):]


def append_status_note(text: str, note: str) -> str:
    stamp = date.today().isoformat()
    line = f"- **{stamp} — {note}**\n"
    m = re.search(r"^## Status notes\s*$", text, re.M)
    if not m:
        return text.rstrip("\n") + f"\n\n## Status notes\n\n{line}"
    return text.rstrip("\n") + "\n" + line


def find_tasks_row(tid: str) -> str:
    r"""Locate the ticket's board row, or fail. Separated from the write so the caller can
    validate every surface BEFORE mutating any of them — see main().

    🔴 FIXED 2026-08-05: the pattern was `^\\| {tid} \\|`, requiring a BARE id with single
    spaces. The board writes every row as a markdown link —
    `| [T165](project/tickets/T165.md) · [#162](…) |` — so it matched **0 of 156 rows** and
    every `just gate` call died with "not queued". This was the FOURTH copy of the same
    bare-id assumption (state_doctor.py, sdlc_doctor.py, backfill_tickets.py were fixed
    earlier the same day); it was missed because its regex is built with an f-string, so a
    grep for the literal pattern did not reach it.

    🔴 FIXED 2026-09-11: the id had no boundary after it, so `T7` matched as a bare PREFIX of
    `T70`/`T71`/`T74`/`T75` (any row whose id starts with the same digits) and `re.search`
    returned whichever collision came first in the file — `just gate T7 in-progress` silently
    flipped **T70's** board glyph while leaving T7's own row untouched. Caught only because the
    diff was read. The `(?!\d)` lookahead below requires the id to end where the ticket id ends.
    """
    text = TASKS.read_text(encoding="utf-8")
    pat = re.compile(
        rf"^\|\s*[*_`]*\s*\[?\s*{re.escape(tid)}(?!\d)\s*\]?(?:\([^)]*\))?[^|]*\|.*$", re.M
    )
    m = pat.search(text)
    if not m:
        fail(f"no row for {tid} in TASKS.md — refusing to advance a ticket that is not on the board")
    return m.group(0)


def update_tasks_row(tid: str, glyph: str, dry: bool, row: str) -> bool:
    text = TASKS.read_text(encoding="utf-8")
    # The status is the last cell; swap only its leading glyph.
    cells = row.split("|")
    status_cell = cells[-2]
    swapped = re.sub(r"^(\s*)(⚪|🟡|🔴|💤|✅)?\s*", rf"\1{glyph} ", status_cell, count=1)
    if swapped == status_cell:
        return False
    cells[-2] = swapped
    # The glyph is structural; the prose beside it is human. Swapping only the glyph can leave
    # "🟡 **queued**" — a contradiction that reads as drift. We do not rewrite prose (it carries
    # reasoning), but we refuse to leave the contradiction silent.
    contradiction = [
        w for w in ("queued", "in progress", "in-progress", "blocked", "paused", "done")
        if w in status_cell.lower() and w.replace(" ", "-") != WORD_FOR[glyph]
    ]
    if contradiction:
        print(f"   ⚠  TASKS.md prose still says '{contradiction[0]}' next to {glyph} — "
              f"update the wording by hand; only the glyph is mechanical")
    if not dry:
        TASKS.write_text(text.replace(row, "|".join(cells)), encoding="utf-8")
    return True


def update_manifest(tid: str, status: str, dry: bool) -> bool:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    hit = next((t for t in data if isinstance(t, dict) and t.get("id") == tid), None)
    if hit is None:
        fail(f"{tid} is absent from project/tickets.json — run `just sync-tickets` first")
    if hit.get("status") == status:
        return False
    hit["status"] = status
    if not dry:
        # EXACTLY sync_github.py's contract — see the module docstring for why.
        MANIFEST.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ticket")
    ap.add_argument("--status", required=True, choices=sorted(GLYPH))
    ap.add_argument("--note", help="status-note line appended to the ticket")
    ap.add_argument("--glyph", help="override the TASKS.md glyph")
    ap.add_argument("--stage", action="store_true", help="git add the touched files")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    tid = a.ticket.upper()
    glyph = a.glyph or GLYPH[a.status]
    ticket_path = load_ticket(tid)

    # Resolve every surface BEFORE writing any of them: a partial transition is
    # worse than none, because the next reader cannot tell which surface is right.
    text = ticket_path.read_text(encoding="utf-8")
    new_text = set_frontmatter_status(text, a.status)
    if a.note:
        new_text = append_status_note(new_text, a.note)

    # 🔴 FIXED 2026-08-05 — this block wrote the ticket file and THEN looked up the board row,
    # so a missing/unmatched row left the ticket advanced and the glyph stale: exactly the
    # partial transition the comment above forbids. Observed on T165: frontmatter said
    # in-progress while the board still read "⚪ queued". Resolve the row FIRST, mutate after.
    row = find_tasks_row(tid)

    changed = []
    if new_text != text:
        if not a.dry_run:
            ticket_path.write_text(new_text, encoding="utf-8")
        changed.append(str(ticket_path.relative_to(ROOT)))
    if update_tasks_row(tid, glyph, a.dry_run, row):
        changed.append("TASKS.md")
    if update_manifest(tid, a.status, a.dry_run):
        changed.append("project/tickets.json")

    verb = "would update" if a.dry_run else "updated"
    print(f"{'🔎' if a.dry_run else '✅'} {tid} → {a.status} {glyph}: {verb} " +
          (", ".join(changed) if changed else "nothing (already in that state)"))

    if a.stage and changed and not a.dry_run:
        subprocess.run(["git", "-C", str(ROOT), "add", *changed], check=True)
        print(f"   staged {len(changed)} file(s) — commit message is yours to write")
    return 0


if __name__ == "__main__":
    sys.exit(main())
