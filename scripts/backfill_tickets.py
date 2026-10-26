#!/usr/bin/env python3
"""Backfill `project/tickets/T##.md` for every TASKS.md row that has no ticket file.

WHY THIS EXISTS. `TASKS.md` is the queue and the T-row is status-of-record, but the
**ticket file is what the SDLC gates read** — `w0m-sdlc-start` loads it, and
`sync_github.py` builds the GitHub mirror by globbing `project/tickets/*.md`.
A row with no file is therefore invisible three times over: it cannot be started
through a gate, it never reaches GitHub Issues, and it never reaches the project
board. It is on the board a human reads and absent from every board a tool reads.

The gap was recorded as "six tickets have no file". Measured 2026-07-26: **36 rows,
29 of them not done.** A 5x undercount, which is itself the argument for generating
these mechanically rather than by hand.

WHAT IT DOES NOT DO — and this is the important part.
It does **not invent acceptance criteria**. The board row is real content written by
whoever filed the work; ACs are not, and a generated "- [ ] Observable outcome 1" is
worse than an honest blank because it looks like someone thought about it. Every
backfilled file carries an explicit `⚠️ BACKFILLED` banner and an empty AC section
naming what still has to be written. A backfilled ticket is a ticket that EXISTS,
not a ticket that is SPECIFIED.

Content is carried **verbatim** from the row: the Task cell becomes Summary, the
Status cell becomes the Status-notes entry, the Ref cell becomes Links. Nothing is
paraphrased, because paraphrasing 36 rows is 36 chances to quietly change a claim.

IDEMPOTENT AND NON-DESTRUCTIVE. A ticket file that already exists is never touched —
a hand-written ticket always wins over a generated one.

Usage:
    python3 scripts/backfill_tickets.py [--dry-run] [--only T87,T90]
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / "TASKS.md"
sys.path.insert(0, str(Path(__file__).resolve().parent))  # estate root scripts/
from tasks_query import resolve_tickets_dir  # noqa: E402 — canonical .tasks/ resolver (T411)
TICKETS = resolve_tickets_dir()
TODAY = dt.date.today().isoformat()

# Status cell marker -> frontmatter status. Measured from the live board rather than
# assumed: these five are the only markers that actually occur in a leading position.
MARKER_STATUS = {
    "⚪": "queued",
    "🟡": "in-progress",
    "🔵": "blocked",
    "✅": "done",
    "🅿": "paused",
}

# Section heading -> queue. The template's allowed values are
# now | next | p1 | backlog-ai | backlog-platform | security.
def section_to_queue(section: str) -> str:
    s = section.lower()
    if "now" in s and "🟢" in section:
        return "now"
    if "next" in s:
        return "next"
    if "security" in s or "ops" in s:
        return "security"
    if "backlog (ai" in s or "ai engine" in s:
        return "backlog-ai"
    if "backlog" in s:
        return "backlog-platform"
    if "done" in s:
        return "backlog-platform"
    # The dated owner-session / program sections are all P1 work.
    return "p1"


def parse_rows() -> list[dict]:
    rows: list[dict] = []
    section = ""
    for line in TASKS.read_text().split("\n"):
        if line.startswith("## "):
            section = line[3:].strip()
            continue
        # ⚠️ Lockstep with state_doctor.py::TASKS_ROW_RE / sdlc_doctor.py::check_ticket_parity.
        # FIXED 2026-08-05: the bare-id pattern matched 0 rows once the board moved to markdown
        # links, so this script reported nothing to backfill regardless of the real gap.
        m = re.match(r"^\|\s*[*_`]*\s*\[?\s*(T\d+[a-z]?)\s*\]?", line)
        if not m:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 6:
            # A malformed row is reported, never silently skipped — a row that does not
            # parse is exactly the row that would go missing again.
            print(f" [WARN] {m.group(1)}: row has {len(cells)} cells, expected 6 — skipped", file=sys.stderr)
            continue
        rows.append(
            {
                "id": cells[0],
                "prio": cells[1],
                "task": cells[2],
                "repos": cells[3],
                "ref": cells[4],
                "status_cell": cells[5],
                "section": section,
            }
        )
    return rows


def derive_title(task: str) -> str:
    """The Task cell opens with a bolded title, then an em-dash and the prose."""
    m = re.match(r"\s*\*\*(.+?)\*\*", task)
    title = m.group(1) if m else task.split("—")[0]
    title = re.sub(r"[`*_\[\]]", "", title).strip().rstrip(".")
    title = re.sub(r"\s+", " ", title)
    return title.replace('"', "'")


def derive_status(cell: str) -> str:
    for marker, status in MARKER_STATUS.items():
        if cell.lstrip().startswith(marker):
            return status
    return "queued"


def derive_priority(prio: str) -> str:
    m = re.search(r"P[0-3]", prio)
    return m.group(0) if m else ""


def derive_repos(cell: str) -> list[str]:
    """Repo tags from the board's Repos cell.

    🔴 Hardened after a live failure. The first version split on `[,/]` and passed the
    fragments straight through, which was fine until T90's cell —
    `web(cp: AdminLayout, index, managers, api, admin), api` — where a parenthesised
    detail contains a COLON. YAML read `web(cp: AdminLayout` as a **mapping**, so the
    ticket's `repos` came back as `[{...}, 'index', ...]` instead of a list of strings,
    and `sync_github.py` died on `TypeError: unhashable type: 'dict'` while building its
    area set. Detached and best-effort, it failed **silently** — the whole GitHub mirror
    stopped for every ticket because of one cell.
    ⇒ A frontmatter generator must emit values it can itself parse back.

    ⚠️ Second hardening pass. Stripping *balanced* parens was not enough: splitting on the
    comma inside `api(migrations, fns)` leaves the unbalanced halves `api(migrations` and
    `fns)`, and `sync_github.py` creates a GitHub **label per area** — so those become real
    labels like `'fns)'`, `'4 apps)'` and `'(research) recruit'`. Junk in a free-text board
    cell becomes junk in the GitHub org.
    ⇒ Do not sanitise a fragment; **whitelist** it. A repo tag is a short lowercase slug, and
    anything that is not one is dropped rather than cleaned up into something plausible.
    """
    cell = re.sub(r"\([^)]*\)", " ", cell)          # drop balanced parenthesised asides
    parts = [re.sub(r"[`*\[\]]", "", p).strip().lower() for p in re.split(r"[,/]", cell)]
    clean = [p for p in parts if re.fullmatch(r"[a-z][a-z0-9._-]{0,14}", p)]
    # Preserve order, drop duplicates. `dict.fromkeys` is order-preserving on 3.7+, and says
    # so plainly. The previous `not (p in seen or seen.add(p))` worked — `set.add` returns None,
    # so the `or` ran it purely for the side effect — but it reads as a bug and mypy flags it as
    # one, since a function returning None was being used as a value (T188).
    out = list(dict.fromkeys(clean))
    return out or ["web"]


def derive_epic(ref: str) -> str:
    m = re.search(r"ROADMAP\s*§\s*([\d.]+)", ref)
    return f"ROADMAP §{m.group(1)}" if m else ""


def derive_spec(ref: str) -> str:
    m = re.search(r"(openspec/changes/[0-9a-zA-Z\-/]+)", ref)
    return m.group(1).rstrip("/") if m else ""


def render(row: dict) -> str:
    tid = row["id"]
    title = derive_title(row["task"])
    status = derive_status(row["status_cell"])
    priority = derive_priority(row["prio"])
    repos = derive_repos(row["repos"])
    epic = derive_epic(row["ref"])
    spec = derive_spec(row["ref"])
    queue = section_to_queue(row["section"])
    related = sorted(set(re.findall(r"\[\[(T\d+[a-z]?)\]\]", row["task"] + row["ref"])))

    rel_line = ", ".join(f"[[{r}]]" for r in related) if related else "—"

    return f"""---
id: {tid}
title: "{title}"
status: {status}
queue: {queue}
priority: {priority}
repos: [{', '.join(repos)}]
epic: "{epic}"
spec: "{spec}"
gh_issue: 0
tags: [backfilled]
created: {TODAY}
---

# {tid} — {title}

> ⚠️ **BACKFILLED {TODAY}** from the `TASKS.md` board row, which had no ticket file.
> The Summary and Status notes below are the row's own prose, carried **verbatim** —
> nothing here is paraphrased or inferred.
> 🔴 **This ticket EXISTS; it is not SPECIFIED.** The acceptance criteria below are
> deliberately empty rather than invented: a generated *"observable outcome 1"* reads
> as though someone thought about it. **Run `w0m-sdlc-start {tid}` (which routes through
> `w0m-sdlc-research`) before treating any of this as verified** — the row may be stale,
> already done, or duplicated by another ticket.
> `created:` is the backfill date, **not** the date the work was filed; recover that
> from `git log -S{tid} -- TASKS.md` if it matters.

## Summary

{row['task']}

## Acceptance criteria

- [ ] **Not yet written.** Derive them from the Summary above via `w0m-sdlc-spec`,
      and make each one observable and testable. Do not tick anything here until the
      claim has been checked against the live system rather than against the board.

## Definition of Done

Per [`../../openspec/SPEC-AUTHORING-STANDARD.md`](../../openspec/SPEC-AUTHORING-STANDARD.md):
spec verified (`openspec-verify-change`), tests/skills mapped, ecosystem + security
checks passed, committed with the T-id, TASKS.md row + this ticket + GH issue in sync.

## Links

- **Board section:** {row['section'] or '—'}
- **Epic:** {epic or '—'}
- **Spec:** {spec or '—'}
- **Related:** {rel_line}
- **Ref (from the board row):** {row['ref'] or '—'}

## Status notes

**{TODAY} — backfilled.** Board row status cell, verbatim:

{row['status_cell'] or '(empty)'}
"""


def validate(tid: str, body: str) -> str | None:
    """Parse back what we are about to write. Returns a problem string, or None.

    The generator is the only thing standing between a free-text board cell and a YAML
    document every downstream tool parses. `sync_github.py` reads `repos` as a set member,
    so a non-string there is not a cosmetic defect — it is a crash that takes the whole
    mirror with it, quietly, because the sync runs detached.
    """
    try:
        import yaml  # optional dependency; absence must not silently disable the check
    except ImportError:
        return None if _WARNED_NO_YAML() else None
    try:
        fm = yaml.safe_load(body.split("---")[1])
    except Exception as exc:
        return f"frontmatter is not valid YAML: {exc}"
    if not isinstance(fm, dict):
        return "frontmatter did not parse to a mapping"
    if str(fm.get("id")) != tid:
        return f"id round-tripped as {fm.get('id')!r}, expected {tid!r}"
    repos = fm.get("repos")
    if not isinstance(repos, list) or any(not isinstance(r, str) for r in repos):
        return f"repos must be a list of plain strings, got {repos!r}"
    for field in ("title", "status", "queue"):
        if not isinstance(fm.get(field), str) or not fm.get(field):
            return f"{field} must be a non-empty string, got {fm.get(field)!r}"
    return None


_yaml_warned = False


def _WARNED_NO_YAML() -> bool:
    """Warn once, loudly, that validation is disabled — never fail open in silence."""
    global _yaml_warned
    if not _yaml_warned:
        _yaml_warned = True
        print(
            "⚠ pyyaml not importable — generated frontmatter is NOT being validated. "
            "Install it before trusting this run.",
            file=sys.stderr,
        )
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", default="", help="comma-separated T-ids")
    args = ap.parse_args()
    only = {x.strip() for x in args.only.split(",") if x.strip()}

    existing = {p.stem for p in TICKETS.glob("T*.md")}
    rows = parse_rows()
    seen: set[str] = set()
    dupes: list[str] = []
    written = 0
    skipped = 0

    for row in rows:
        tid = row["id"]
        if tid in seen:
            dupes.append(tid)
            continue
        seen.add(tid)
        if tid in existing:
            skipped += 1
            continue
        if only and tid not in only:
            continue
        target = TICKETS / f"{tid}.md"
        body = render(row)
        problem = validate(tid, body)
        if problem:
            # Fail closed. Emitting frontmatter this script cannot itself parse back is how
            # one bad board cell silently took down the entire GitHub mirror (see derive_repos).
            print(f"❌ {tid}: {problem}", file=sys.stderr)
            return 1
        if args.dry_run:
            print(f"  would write {target.relative_to(ROOT)}  [{derive_status(row['status_cell'])}] {derive_title(row['task'])[:56]}")
        else:
            target.write_text(body)
        written += 1

    if dupes:
        print(f"[WARN] duplicate board rows (first kept): {', '.join(sorted(set(dupes)))}", file=sys.stderr)

    verb = "would write" if args.dry_run else "wrote"
    print(f"\n✅ {verb} {written} ticket file(s); {skipped} already existed and were left untouched")
    print(f"   board rows parsed: {len(rows)}  unique ids: {len(seen)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
