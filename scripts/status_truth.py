#!/usr/bin/env python3
"""Status-truth pass — measure every `in-progress` ticket against EVIDENCE, not its own field (T516).

For each one: AC progress, the last commit that MENTIONS the id, and the last commit that TOUCHED
the ticket file. Those are different facts — a ticket edited today with no code commit in a month
is being curated, not worked.

Read-only. Prints a table; changes nothing.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path
import re
import subprocess
import sys
from typing import TypedDict

ESTATE = Path(__file__).resolve().parent.parent
WEB = ESTATE / "wom7web"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from tasks_query import resolve_tickets_dir  # noqa: E402 — canonical .tasks/ resolver (T411)


class Row(TypedDict):
    """Typed so the report cannot index a str or compare a str to an int."""

    id: str
    prio: str
    done: int
    half: int
    total: int
    pct: float | None
    mention_d: int | None
    touch_d: int | None
    mention: str
    touch: str
    title: str


AC = re.compile(r"^- \[([ x~])\](?:\s|\*)*\*?\*?AC\d", re.M)


def sh(cwd: Path, *a: str) -> str:
    r = subprocess.run(a, capture_output=True, text=True, cwd=cwd, check=False)
    return r.stdout.strip()


def days(iso: str, today: date | None = None) -> int | None:
    if not iso:
        return None
    ref = today or date.today()
    try:
        return (ref - datetime.fromisoformat(iso[:10]).date()).days
    except ValueError:
        return None


def collect_git_log(cwd: Path) -> list[list[str]]:
    raw = sh(cwd, "git", "log", "--all", "--format=%as\t%s%n%b")
    return [ln.split("\t", 1) for ln in raw.splitlines() if "\t" in ln]


def last_mention(tid: str, log_entries: list[list[str]]) -> str:
    rx = re.compile(rf"(?<![0-9A-Za-z]){tid}(?![0-9])")
    for entry in log_entries:
        if len(entry) == 2 and rx.search(entry[1]):
            return entry[0]
    return ""


def measure_status_truth(
    tickets_dir: Path | None = None,
    code_repo: Path = WEB,
    tickets_repo: Path = ESTATE,
    today: date | None = None,
) -> list[Row]:
    tdir = tickets_dir or resolve_tickets_dir()
    ref_today = today or date.today()
    log_entries = collect_git_log(code_repo) if code_repo.is_dir() else []

    rows: list[Row] = []
    for f in sorted(tdir.glob("T*.md")):
        txt = f.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"^status:\s*(\S+)", txt, re.M)
        if not m or m.group(1) != "in-progress":
            continue
        tid = f.stem
        _p = re.search(r"^priority:\s*(\S+)", txt, re.M)
        prio = _p.group(1) if _p else "—"
        marks = AC.findall(txt)
        done = sum(1 for c in marks if c == "x")
        half = sum(1 for c in marks if c == "~")
        total = len(marks)
        mention = last_mention(tid, log_entries)
        rel_ticket = str(f.relative_to(tickets_repo)) if f.is_relative_to(tickets_repo) else str(f)
        touch = (
            sh(tickets_repo, "git", "log", "-1", "--format=%as", "--", rel_ticket)
            if (tickets_repo / ".git").exists()
            else ""
        )
        title_m = re.search(r'^title:\s*"?(.{0,58})', txt, re.M)
        title_str = title_m.group(1) if title_m else ""
        row: Row = {
            "id": tid,
            "prio": prio,
            "done": done,
            "half": half,
            "total": total,
            "pct": (100 * (done + 0.5 * half) / total) if total else None,
            "mention_d": days(mention, ref_today),
            "touch_d": days(touch, ref_today),
            "mention": mention or "never",
            "touch": touch or "never",
            "title": title_str,
        }
        rows.append(row)
    return rows


def key(r: Row) -> int:
    d = r["mention_d"]
    return d if d is not None else 9999


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="status_truth.py",
        description=__doc__,
    )
    ap.add_argument(
        "--tickets-dir",
        type=Path,
        default=None,
        help="override .tasks directory path (for offline testing)",
    )
    ap.add_argument(
        "--stale-days",
        type=int,
        default=14,
        help="days without a mentioning commit before flagging as stale (default: 14)",
    )
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    today = date.today()
    rows = measure_status_truth(tickets_dir=args.tickets_dir, today=today)

    print(f"\n  in-progress tickets: {len(rows)}   (measured {today})\n")
    print(f"  {'id':6} {'pri':4} {'ACs':>9} {'%':>5}  {'code-commit':>11} {'file-edit':>10}  title")
    print("  " + "─" * 104)
    for r in sorted(rows, key=key):
        acs = f"{r['done']}+{r['half']}~/{r['total']}" if r["total"] else "none"
        pct = f"{r['pct']:.0f}%" if r["pct"] is not None else "—"
        md = f"{r['mention_d']}d" if r["mention_d"] is not None else "never"
        td = f"{r['touch_d']}d" if r["touch_d"] is not None else "never"
        print(
            f"  {r['id']:6} {r['prio']:4} {acs:>9} {pct:>5}  {md:>11} {td:>10}  {r['title'][:52]}"
        )

    stale = [
        r for r in rows if r["mention_d"] is None or r["mention_d"] > int(args.stale_days)
    ]
    print(f"\n  no commit mentioning the id in >{args.stale_days} days: {len(stale)} of {len(rows)}")
    print(f"    {', '.join(r['id'] for r in sorted(stale, key=key))}")
    noacs = [r for r in rows if not r["total"]]
    if noacs:
        print(f"\n  [WARN] no parseable ACs at all (unrankable): {', '.join(r['id'] for r in noacs)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
