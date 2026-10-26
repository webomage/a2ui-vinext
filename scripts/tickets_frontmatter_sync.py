#!/usr/bin/env python3
"""Materialise `just tasks`' derived fields into each ticket's frontmatter, for Obsidian.

WHY AT ALL. `project/tickets/` sits inside the wom7web Obsidian vault, so all 292 tickets are
already notes — but Obsidian can only sort and filter on FRONTMATTER, and the three things that make
the queue readable are computed, not stored: acceptance-criteria progress, blockers, and the two
ranking scores. Without them a Base over the vault can show status and priority and nothing that
says what to work on.

🔴 WHY THIS IS DANGEROUS, AND WHAT MAKES IT SAFE. Writing a computed value into a file is creating a
second copy that starts rotting immediately: tick one AC and 292 files disagree with reality. The
estate has met this before and the answer is always the same shape — `state-save` writes STATE.md's
mechanical block and `state-check` fails the push when it drifts. This is that pattern:

    just tickets-frontmatter-sync            -- write
    just tickets-frontmatter-sync --check    -- fail if any file disagrees with the computation

The generated keys are namespaced `x_` so they are visibly derived, and a human key is never
touched. In particular `blocked_by` is LEFT ALONE — two tickets declare it by hand and it is
authoritative; the inferred set goes to `x_blocked_by` beside it, never over it.

⚠️ Frontmatter is edited LINE BY LINE, never round-tripped through a YAML dumper. Re-serialising
these files would re-encode every non-ASCII character — which is exactly how `tickets.json` was
corrupted once before.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tasks_query lives in estate scripts/ (T419)

import tasks_query as tq  # noqa: E402
from tasks_query import resolve_tickets_dir  # noqa: E402 — canonical .tasks/ resolver (T411)
TICKETS = resolve_tickets_dir()

# Every key this tool owns. Anything here is overwritten on sync; anything else is never touched.
OWNED = ("x_ac_done", "x_ac_total", "x_ac_pct", "x_hot_score", "x_blocked_by", "x_synced")


def hot_score_for_frontmatter(row: dict, *, include_age: bool = False) -> int:
    """Compute the deterministic frontmatter hot score without the time-dependent `age` term (T552 AC1).

    `just tasks` includes `parts["age"]` (`days_since_created // 7`) on read, so the live ranking
    still ages tickets up. Persisting the age term into `.tasks/T*.md` (`x_hot_score`) caused ~1/7
    of the corpus to go stale every midnight with zero commits, turning `tickets-frontmatter-check`
    into a blocking deploy gate that expired daily.
    """
    score = int(row.get("score", 0))
    if include_age:
        return score
    age = int((row.get("parts") or {}).get("age", 0))
    return score - age


def derive(today: date | None = None, *, include_age: bool = False) -> dict[str, dict[str, str]]:
    """-> {ticket_id: {key: rendered_value}} for every ticket the queue can see."""
    tq.TICKETS = TICKETS
    out: dict[str, dict[str, str]] = {}
    for row in tq.load(today=today):
        tid = row["id"]
        done, total = tq.ac_progress(tid)
        b = row.get("blockers") or {"declared": [], "inferred": []}
        # Declared blockers are the human's; only the inferred set is ours to write.
        inferred = b.get("inferred") or []
        fields = {
            "x_ac_done": str(done),
            "x_ac_total": str(total),
            # -1, not 0, when there is nothing to measure. A ticket with no acceptance criteria is
            # UNMEASURABLE and must not sort beside one that is genuinely at 0% (the SDLC board
            # excludes them for the same reason). 0 would make 19 tickets look merely unstarted.
            "x_ac_pct": str(round(100 * done / total) if total else -1),
            "x_hot_score": str(hot_score_for_frontmatter(row, include_age=include_age)),
            "x_blocked_by": "[" + ", ".join(inferred) + "]" if inferred else "[]",
        }
        out[tid] = fields
    return out


compute_derived = derive


def splice(text: str, fields: dict[str, str], stamp: str) -> str:
    """Replace or append the owned keys inside the frontmatter block, touching nothing else."""
    m = re.match(r"^(---\n)(.*?)(\n---\n)", text, re.S)
    if not m:
        return text
    head, body, tail = m.group(1), m.group(2), m.group(3)
    lines = body.split("\n")
    kept = [ln for ln in lines if not re.match(r"^(" + "|".join(OWNED) + r"):", ln)]
    added = [f"{k}: {v}" for k, v in fields.items()] + [f"x_synced: {stamp}"]
    return head + "\n".join(kept + added) + tail + text[m.end():]


def read_owned(text: str) -> dict[str, str]:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return {}
    got = {}
    for ln in m.group(1).split("\n"):
        k = re.match(r"^(" + "|".join(OWNED) + r"):\s*(.*)$", ln)
        if k and k.group(1) != "x_synced":
            got[k.group(1)] = k.group(2).strip()
    return got


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Sync derived queue fields into ticket frontmatter.")
    ap.add_argument("--check", action="store_true",
                    help="do not write; exit 1 if any file disagrees with the computation")
    ap.add_argument("--stamp", default="", help="value for x_synced (tests pass a fixed one)")
    ap.add_argument("--today", default="", help="reference date YYYY-MM-DD for derive() (tests pass two dates)")
    ap.add_argument("--porcelain", action="store_true",
                    help="print ONLY the paths this run rewrote, one per line, for `xargs git add`. "
                         "The pre-commit hook stages exactly those — staging all of "
                         "project/tickets/ would sweep in unrelated edits a person had not "
                         "chosen to commit.")
    a = ap.parse_args(argv)

    today_val = date.fromisoformat(a.today) if a.today else None
    want = derive(today=today_val)
    if not want:
        print("UNMEASURABLE: the queue returned no tickets — that is a broken read, not an empty "
              "backlog.", file=sys.stderr)
        return 2

    stamp = a.stamp or __import__("datetime").date.today().isoformat()
    drifted, written, missing = [], 0, 0
    for tid, fields in sorted(want.items()):
        p = TICKETS / f"{tid}.md"
        if not p.is_file():
            missing += 1
            continue
        text = p.read_text(encoding="utf-8")
        if a.check:
            got = read_owned(text)
            if got != fields:
                diff = {k: (got.get(k, "(absent)"), v) for k, v in fields.items() if got.get(k) != v}
                drifted.append((tid, diff))
            continue
        # Compare the OWNED fields, not the whole text: the stamp changes every day, so a full-text
        # compare rewrote all ~430 tickets on the first run of each day (T430, measured 2026-09-23)
        # — a churn that makes every parallel agent's commit collide on every ticket file.
        if read_owned(text) == fields:
            continue
        new = splice(text, fields, stamp)
        if new != text:
            p.write_text(new, encoding="utf-8")
            written += 1
            if a.porcelain:
                print(p.relative_to(TICKETS.parent))  # repo-relative for `git add` in the estate repo (T430)

    if a.check:
        print(f"\nticket frontmatter vs the live queue — {len(want)} ticket(s)\n")
        for tid, diff in drifted[:12]:
            first = next(iter(diff.items()))
            print(f"  [FAIL] {tid}: {first[0]} is {first[1][0]}, computed {first[1][1]}"
                  + (f"  (+{len(diff)-1} more field(s))" if len(diff) > 1 else ""))
        if len(drifted) > 12:
            print(f"  … and {len(drifted) - 12} more")
        if drifted:
            print(f"\n[FAIL] {len(drifted)} ticket(s) carry stale derived fields. Run "
                  f"`just tickets-frontmatter-sync` and commit — do NOT hand-edit an `x_` key.",
                  file=sys.stderr)
            return 1
        print(f"[OK] all {len(want)} tickets agree with the computation.")
        return 0

    if not a.porcelain:
        print(f"[OK] {written} ticket(s) updated, {len(want) - written - missing} already current"
              + (f", {missing} missing file(s)" if missing else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
