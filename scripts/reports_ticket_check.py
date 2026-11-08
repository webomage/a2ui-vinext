#!/usr/bin/env python3
"""Every file in `.agents/reports/` must cite a ticket that exists — ticket first (T428).

WHY. Reports are written incrementally, so they survive a session cut off by quota — and they were
routinely written BEFORE the ticket existed. The 39 KB parallel-agents proposal was the only record
of its work until T423–T428 were created from it. A report with no ticket is a second, untracked
source of work state; the ticket is the one source, and a report is an attachment to it.

THE RULE. A ticket id (`T123`, any case) in the FILENAME (`YYYY-MM-DD-t123-…`) or in the first
HEADER_LINES lines, AND that id has a file in `.tasks/`. Citing a ticket that does not exist is the
same defect as citing none.

Exit 0 = every report cites a real ticket · 1 = at least one does not · 2 = nothing to measure.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEADER_LINES = 12
TICKET_RE = re.compile(r"\b[Tt](\d{1,4})\b")
DRAFT_RE = re.compile(r"\b[Dd][Rr][Aa][Ff][Tt]-([A-Za-z0-9_-]+)\b")


def cited(path: Path) -> set[str]:
    head = "\n".join(path.read_text(encoding="utf-8", errors="replace").split("\n")[:HEADER_LINES])
    t_ids = {f"T{n}" for n in TICKET_RE.findall(path.name) + TICKET_RE.findall(head)}
    d_ids = {f"DRAFT-{s.lower()}" for s in DRAFT_RE.findall(path.name) + DRAFT_RE.findall(head)}
    return t_ids | d_ids


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", type=Path, default=ROOT, help="estate root (holds .agents/ and .tasks/)")
    args = ap.parse_args()
    reports = sorted(p for p in (args.root / ".agents" / "reports").glob("*") if p.is_file())
    tickets = {p.stem for p in (args.root / ".tasks").glob("T*.md")} | {
        f"DRAFT-{p.stem[6:].lower()}" for p in (args.root / ".tasks").glob("DRAFT-*.md")
    }
    if not reports or not tickets:
        print(f"❌ reports-ticket-check: {len(reports)} report(s), {len(tickets)} ticket(s) found — "
              "cannot measure, so not passing")
        return 2
    bad = []
    for p in reports:
        ids = cited(p)
        real = ids & tickets
        if not real:
            why = f"cites {', '.join(sorted(ids))}, none of which exist" if ids else "cites no ticket"
            bad.append(f"{p.name}: {why}")
    for b in bad:
        print(f"  ✗ {b}")
    print(f"{'❌' if bad else '✅'} reports-ticket-check: {len(reports)} report(s) in .agents/reports/, "
          f"{len(bad)} without an existing ticket (filename or first {HEADER_LINES} lines)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
