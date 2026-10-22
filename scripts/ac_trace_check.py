#!/usr/bin/env python3
"""Audit: does every ticket's acceptance-criteria state actually reach the ranker and agree with status?

The parser understands four checkbox states ([x] [ ] [~] [N/A]). That fixes tickets whose ACs
are checkboxes. It does NOTHING for a ticket that writes acceptance criteria in a shape with no
checkbox at all — a `## AC6` heading, or `- **AC1 —** …` with the box omitted. Those still report
(0, 0) and are EXCLUDED from the sdlc ranking as "unmeasurable", which is indistinguishable from a
ticket that genuinely never wrote any.

In addition (T245), every ticket states its progress twice: `status:` in frontmatter and the ratio
of ticked `AC<n>` bullets. This audit checks both directions of status-vs-AC disagreement:
  - DONE / ARCHIVED with unticked ACs (stale-done, unless exempt via duplicate/not-planned target)
  - 100% ticked ACs with status not in {done, archived}:
      * [PENDING-CLOSURE] when frontmatter declares what remains (`pending_closure`, `blocked_by`, or `status: paused`/`blocked`) (AC1b)
      * [COMPLETE-NOT-DONE] hard ERROR otherwise (AC1)
  - [QUEUED-WITH-PROGRESS] `status: queued` with 0 < done < total (AC3, 0-instance ratchet)
  - [IN-PROGRESS-ZERO-AC] `status: in-progress` with 0 ticked ACs — reported distinctly as a question, not a verdict (AC4)
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
TICKETS = Path(os.environ["W0M_TASKS_DIR"]) if "W0M_TASKS_DIR" in os.environ else (ROOT / ".tasks")

sys.path.insert(0, str(ROOT / "scripts"))
import tasks_query as tq  # noqa: E402

# Any line that names an AC — heading, bold, list item, with or without a checkbox.
AC_MENTION = re.compile(r"^\s*(#{1,4}\s*|[-*]\s*(\[[^\]]*\]\s*)?)?\*{0,2}AC\d+[a-z]?\b", re.M)
# A checkbox under `## Acceptance criteria` that carries no `AC<n>` id is a real criterion the
# ranker cannot see. 64 tickets were in this state because the TEMPLATE showed id-less bullets.
SECTION = re.compile(r"^##+\s*Acceptance criteria\s*$(.*?)(?=^##\s|\Z)", re.S | re.M)
# `~~struck~~` is a WITHDRAWN criterion — superseded wording (T120) or explicitly dropped (T150).
# Counting it would make a finished ticket look less complete than it is, which is the same class
# of lie as not counting a real one.
BOX_NO_ID = re.compile(r"^\s*-\s*\[[^\]]*\]\s+(?!~~)(?!\*{0,2}AC\d)\S", re.M)
PLACEHOLDER = re.compile(r"Not yet written", re.I)

SUPERSEDED = re.compile(
    r"CLOSED AS A DUPLICATE of \[\[(T\d+)\]\]|^superseded_by:\s*\[?\[?(T\d+)", re.I | re.M
)


def superseded_target(body: str) -> str | None:
    """The ticket that carries this one's work, if this ticket was closed in favour of another.

    A ticket closed as a duplicate legitimately has DONE status and zero ticked criteria — the work
    is tracked elsewhere, so ticking its boxes would be a lie and leaving them unticked is correct.
    Without this, the only honest record of a duplicate reads as drift.

    Deliberately NOT a bare keyword match in prose. The body exemption requires NAMING a ticket, and
    the caller verifies that ticket EXISTS — otherwise the word "duplicate" anywhere in a body would
    silence the check, which is a loophole rather than an exemption.
    """
    m = SUPERSEDED.search(body)
    if not m:
        return None
    return m.group(1) or m.group(2)


def pending_closure_reason(fm: dict[str, Any], status: str) -> str | None:
    """Return the declared pending-closure escape reason if present (T245 AC1b).

    100% ACs is not always the same claim as `done` because the AC list does not necessarily cover
    deployment, owner sign-off, or external blockers. A ticket at 100% ACs is exempt from the AC1
    hard error when it explicitly declares what remains via `pending_closure:`, non-empty
    `blocked_by:`, or `status: paused` / `blocked`.
    """
    pending = str(fm.get("pending_closure") or "").strip()
    if pending:
        return f"pending_closure: {pending}"
    blocked_raw = str(fm.get("blocked_by") or "").strip()
    if blocked_raw and blocked_raw != "[]":
        refs = re.findall(r"T[0-9a-z]+", blocked_raw)
        if refs:
            return f"blocked_by: {', '.join(refs)}"
        return f"blocked_by: {blocked_raw}"
    if status in ("paused", "blocked"):
        return f"status: {status}"
    return None


def audit_tickets(tickets_dir: Path | None = None) -> dict[str, Any]:
    """Audit all tickets in `tickets_dir` for AC traceability and status-vs-AC disagreements."""
    tdir = tickets_dir if tickets_dir is not None else TICKETS
    if not tdir.is_dir():
        return {
            "rows": [],
            "counted": [],
            "uncounted": [],
            "none": [],
            "unnumbered": [],
            "stale": [],
            "exempt": [],
            "complete_not_done": [],
            "pending_closure": [],
            "queued_with_progress": [],
            "in_progress_zero_ac": [],
            "supersedes": {},
            "exit_code": 2,
        }

    rows: list[dict[str, Any]] = []
    counted: list[tuple[str, str, str, int, int, int]] = []
    uncounted: list[tuple[str, str, str, int, int, int]] = []
    none: list[tuple[str, str, str, int, int, int]] = []
    unnumbered: list[tuple[str, str, str, int]] = []
    complete_not_done: list[tuple[str, str, str, int, int]] = []
    pending_closure: list[tuple[str, str, str, int, int, str]] = []
    queued_with_progress: list[tuple[str, str, str, int, int]] = []
    in_progress_zero_ac: list[tuple[str, str, str, int, int]] = []
    supersedes: dict[str, str | None] = {}

    ticket_files = sorted(
        tdir.glob("T*.md"),
        key=lambda p: int(re.sub(r"\D", "", p.stem) or 0),
    )

    for ticket_file in ticket_files:
        fm = tq.frontmatter(ticket_file)
        tid = str(fm.get("id") or "").strip()
        if not tid:
            continue
        st = str(fm.get("status") or "").strip()
        pr_raw = str(fm.get("priority") or "").strip()
        if pr_raw.lower() in ("none", "null", ""):
            pr = "—"
        else:
            pr = pr_raw

        body = ticket_file.read_text(encoding="utf-8", errors="replace")
        done = len(tq.AC_DONE.findall(body))
        total = len(tq.AC_ANY.findall(body)) - len(tq.AC_NA.findall(body))
        mentions = len(AC_MENTION.findall(body))

        rows.append({"id": tid, "status": st, "priority": pr, "fm": fm})
        rec = (tid, st, pr, done, total, mentions)

        target = superseded_target(body)
        if target and not (tdir / f"{target}.md").exists():
            target = None  # names a ticket that does not exist — not an exemption
        closed_as = str(fm.get("closed_as") or "").strip().lower()
        if not target and closed_as in ("duplicate", "not-planned"):
            ref_match = re.search(r"\[\[(T\d+)\]\]", body)
            if ref_match and (tdir / f"{ref_match.group(1)}.md").exists():
                target = ref_match.group(1)
            else:
                target = f"closed_as:{closed_as}"
        supersedes[tid] = target

        sec = SECTION.search(body)
        idless = 0
        if sec and not PLACEHOLDER.search(sec.group(1)):
            idless = len(BOX_NO_ID.findall(sec.group(1)))
        if idless:
            unnumbered.append((tid, st, pr, idless))

        if total > 0:
            counted.append(rec)
            if done == total and st not in ("done", "archived"):
                escape = pending_closure_reason(fm, st)
                if escape is not None:
                    pending_closure.append((tid, st, pr, done, total, escape))
                else:
                    complete_not_done.append((tid, st, pr, done, total))
            elif st == "queued" and 0 < done < total:
                queued_with_progress.append((tid, st, pr, done, total))
            elif st == "in-progress" and done == 0:
                in_progress_zero_ac.append((tid, st, pr, done, total))
        elif mentions:
            uncounted.append(rec)
        else:
            none.append(rec)

    all_stale = [
        (tid, pr, d, tot)
        for tid, st, pr, d, tot, _m in counted
        if st in ("done", "archived") and tot > 0 and d < tot
    ]
    stale = [r for r in all_stale if not supersedes.get(r[0])]
    exempt = [(r[0], r[1], r[2], r[3], str(supersedes.get(r[0]))) for r in all_stale if supersedes.get(r[0])]

    if not rows or not counted:
        exit_code = 2
    elif uncounted or stale or unnumbered or complete_not_done or queued_with_progress:
        exit_code = 1
    else:
        exit_code = 0

    return {
        "rows": rows,
        "counted": counted,
        "uncounted": uncounted,
        "none": none,
        "unnumbered": unnumbered,
        "stale": stale,
        "exempt": exempt,
        "complete_not_done": complete_not_done,
        "pending_closure": pending_closure,
        "queued_with_progress": queued_with_progress,
        "in_progress_zero_ac": in_progress_zero_ac,
        "supersedes": supersedes,
        "exit_code": exit_code,
    }


def format_report(result: dict[str, Any]) -> str:
    """Format the human-readable and suite-runner-compatible report."""
    rows = result["rows"]
    counted = result["counted"]
    uncounted = result["uncounted"]
    none = result["none"]
    unnumbered = result["unnumbered"]
    stale = result["stale"]
    exempt = result["exempt"]
    complete_not_done = result["complete_not_done"]
    pending_closure = result["pending_closure"]
    queued_with_progress = result["queued_with_progress"]
    in_progress_zero_ac = result["in_progress_zero_ac"]

    lines: list[str] = []
    lines.append(
        f"searched {len(counted)} measurable ticket(s) across {len(rows)} total "
        f"(COUNTED {len(counted)} · UNCOUNTED {len(uncounted)} · NONE {len(none)})"
    )

    if not rows or not counted:
        lines.append(
            f"[FAIL] ac-trace-check: searched {len(counted)} measurable ticket(s) across {len(rows)} total "
            "— refusing to certify tracing over an empty set"
        )
        return "\n".join(lines)

    lines.append(f"\n── [UNCOUNTED] AC-shaped text the ranker cannot see ({len(uncounted)}) ──")
    for tid, st, pr, _d, _tot, m in uncounted:
        open_mark = "OPEN" if st not in ("done", "archived", "cancelled") else "closed"
        lines.append(f"  {tid:6} {pr:3} {st:12} {open_mark:6} — {m} AC mention(s), parser sees 0")
    if not uncounted:
        lines.append("  (none)")

    lines.append(f"\n── [STALE-DONE] DONE but with unticked criteria ({len(stale)}) ──")
    for tid, pr, d, tot in stale:
        lines.append(f"  {tid:6} {pr:3} {d}/{tot} — {tot - d} unticked")
    if not stale:
        lines.append("  (none)")
    if exempt:
        lines.append(
            f"\n── [EXEMPT] closed in favour of another ticket or not-planned, so unticked criteria are CORRECT "
            f"({len(exempt)}) ──"
        )
        for tid, pr, d, tot, target in exempt:
            lines.append(f"  {tid:6} {pr:3} {d}/{tot} — work tracked in {target}")

    lines.append(
        f"\n── [COMPLETE-NOT-DONE] 100% ticked ACs with status not in {{done, archived}} ({len(complete_not_done)}) ──"
    )
    for tid, st, pr, d, tot in complete_not_done:
        lines.append(f"  {tid:6} {pr:3} {st:12} {d}/{tot} — 100% ACs ticked but status is '{st}' with no pending_closure")
    if not complete_not_done:
        lines.append("  (none)")

    if pending_closure:
        lines.append(
            f"\n── [PENDING-CLOSURE] 100% ticked ACs held open by declared condition ({len(pending_closure)}) ──"
        )
        for tid, st, pr, d, tot, reason in pending_closure:
            lines.append(f"  {tid:6} {pr:3} {st:12} {d}/{tot} — held open ({reason})")

    lines.append(
        f"\n── [QUEUED-WITH-PROGRESS] status: queued with ticked ACs ({len(queued_with_progress)}) ──"
    )
    for tid, st, pr, d, tot in queued_with_progress:
        lines.append(f"  {tid:6} {pr:3} {st:12} {d}/{tot} — {d} AC(s) ticked while status is still 'queued'")
    if not queued_with_progress:
        lines.append("  (none)")

    lines.append(
        f"\n── [IN-PROGRESS-ZERO-AC] status: in-progress with 0 ticked ACs — "
        f"question: optimistic status or unticked progress? ({len(in_progress_zero_ac)}) ──"
    )
    for tid, st, pr, d, tot in in_progress_zero_ac:
        lines.append(
            f"  {tid:6} {pr:3} {st:12} {d}/{tot} ? — question: is status optimistic, or is work landing with 0 ACs ticked?"
        )
    if not in_progress_zero_ac:
        lines.append("  (none)")

    lines.append(f"\n── [ID-LESS] criteria with NO `AC<n>` id ({len(unnumbered)}) — invisible to the ranker ──")
    for tid, st, pr, n in unnumbered[:12]:
        lines.append(f"  {tid:6} {pr:3} {st:12} {n} id-less checkbox(es)")
    if not unnumbered:
        lines.append("  (none)")

    if result["exit_code"] != 0:
        lines.append(
            f"\n[FAIL] ac-trace-check FAILED — "
            f"{len(uncounted)} untraceable, "
            f"{len(stale)} stale-done, "
            f"{len(complete_not_done)} complete-not-done, "
            f"{len(queued_with_progress)} queued-with-progress, "
            f"{len(unnumbered)} id-less"
        )
    else:
        lines.append(
            f"\n[OK] ac-trace-check: {len(counted)} measurable ticket(s) across {len(rows)} total — "
            "every ticket's AC state reaches the ranker and agrees with status"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit ticket AC traceability and status-vs-AC agreement.")
    parser.add_argument(
        "--tickets-dir",
        type=Path,
        default=None,
        help="Override canonical .tasks directory (for fixture testing).",
    )
    args = parser.parse_args(argv)
    tdir = args.tickets_dir if args.tickets_dir is not None else TICKETS
    if args.tickets_dir is None and not tdir.is_dir():
        sys.exit(f"FATAL: Canonical tickets directory not found at {tdir} (AgDR-0025: zero silent fallbacks)")
    result = audit_tickets(tdir)
    print(format_report(result))
    return int(result["exit_code"])


if __name__ == "__main__":
    sys.exit(main())
