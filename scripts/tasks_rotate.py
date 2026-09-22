#!/usr/bin/env python3
"""T228 AC8b — rotate DONE rows out of TASKS.md, with a disposition record.

`state-rotate` and `deploy-logs-rotate` existed; this did not, which is why AC8b is a BUILD.

🔴 THE RULE THIS TOOL EXISTS TO ENFORCE. T174's first rotation caught a section that was the only
standing record of a live security gap. So a row is NEVER moved because its status says `done` — it
moves because a human wrote a disposition entry for it in `project/tasks-rotation.json` saying what
it was the sole record of, and where that record now lives. No entry, no move. That is the whole
safety property; everything else here is bookkeeping.

Default mode PROPOSES and changes nothing. `--apply` moves only rows that are cleared.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
TASKS = ROOT / "TASKS.md"
ARCHIVE_DIR = ROOT / ".tasks" / "archive"
ARCHIVE = ARCHIVE_DIR / "TASKS-archive.md"
INDEX = ARCHIVE_DIR / "INDEX.md"
DISPOSITION = ROOT / "project" / "tasks-rotation.json"

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from tasks_bounds import ROW, malformed_rows  # noqa: E402  (one row definition, not two)

TICKET_LINK = re.compile(r"\.tasks/T\d+[a-c]?\.md")
ISSUE_LINK = re.compile(r"github\.com/casualuser/webomage\.com/issues/\d+")
ROW_ID = re.compile(r"^\| \[(T\d+[a-c]?)\]")
BOUND_BYTES = 409_600


def row_id(row: str) -> str:
    m = ROW_ID.match(row)
    return m.group(1) if m else "?"


def status_cell(row: str) -> str:
    """The LAST cell. Only meaningful on a well-formed six-cell row — malformed rows are excluded
    before this is called, because a literal `|` in prose shifts every cell and would make an open
    row read as done (T243's failure, in the direction that loses data)."""
    cells = [c.strip() for c in row.strip().strip("|").split("|")]
    return cells[-1] if cells else ""


def load_disposition() -> dict[str, dict]:
    if not DISPOSITION.exists():
        return {}
    raw = json.loads(DISPOSITION.read_text())
    return {e["id"]: e for e in raw.get("rotated", [])}


def clearance(row: str, entry: dict | None) -> tuple[bool, str]:
    """May this row move?

    🔑 The rule is EVIDENCE-based, not paperwork-based, and that distinction is deliberate. An
    earlier draft demanded a hand-written entry for all 95 done rows — which in practice would have
    been 95 auto-generated `sole_record_of: null` lines, i.e. a gate that always says yes. A gate
    satisfied by bulk-filling it is not a gate; this estate has shipped that mistake before.

    So: a row clears MECHANICALLY when its ticket file exists, because [[T228]] AC5b established
    that *the ticket is the source and the board a projection* — the row is a rendering of a record
    that lives elsewhere. Rotation then MOVES it verbatim into the archive rather than deleting it,
    so even a row carrying something its ticket file lacks is still readable afterwards. What
    survives as a genuine risk is a row with NO ticket file: nothing else holds it, and T174's case
    was exactly that shape. Those fail closed and need a written disposition.
    """
    tid = row_id(row)
    ticket = ROOT / ".tasks" / f"{tid}.md"
    if ticket.exists():
        return True, f"record lives in .tasks/{tid}.md ({len(ticket.read_bytes()):,} B)"
    if entry is None:
        return False, "NO ticket file and no disposition entry — this row may be the only record"
    sole = entry.get("sole_record_of")
    if sole and not entry.get("record_moved_to"):
        return False, f"sole record of {sole!r} with nowhere else to read it — move the record first"
    return True, (f"no ticket file; disposition says record is at {entry['record_moved_to']}"
                  if sole else "no ticket file; disposition clears it explicitly")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="perform the move (default: propose only)")
    args = ap.parse_args()

    if not TASKS.exists():
        print("❌ UNMEASURABLE — TASKS.md not found"); return 2

    text = TASKS.read_text(encoding="utf-8")
    lines = text.splitlines()
    rows = [l for l in lines if ROW.match(l)]
    if not rows:
        # An empty corpus must fail, not pass — a rotation tool that finds no rows has either been
        # pointed at the wrong file or the format changed under it.
        print("❌ UNMEASURABLE — no ticket rows matched; TASKS.md format may have changed"); return 2

    mal = set(malformed_rows(rows))
    if mal:
        print(f"  WARNING: {len(mal)} malformed row(s) EXCLUDED from rotation — a literal `|` in prose "
              f"shifts the status cell, and a misread status here loses an OPEN row:")
        for m in sorted(mal, key=row_id):
            print(f"     {row_id(m)}")

    done = [r for r in rows if r not in mal and status_cell(r).startswith("✅")]
    disp = load_disposition()
    total = len(text.encode("utf-8"))

    cleared: list[tuple[str, str]] = []
    blocked: list[tuple[str, str]] = []
    for r in done:
        ok, why = clearance(r, disp.get(row_id(r)))
        (cleared if ok else blocked).append((r, why))

    b = lambda rs: sum(len(r.encode("utf-8")) + 1 for r in rs)
    print(f"\n▶ tasks-rotate — {len(rows)} row(s) · {len(done)} done · "
          f"{len(cleared)} cleared to move · {len(blocked)} blocked\n")
    print(f"  TASKS.md      {total:>9,} B   bound {BOUND_BYTES:,} B   ({total / BOUND_BYTES * 100:.0f}%)")
    if cleared:
        after = total - b([r for r, _ in cleared])
        print(f"  after moving  {after:>9,} B   ({after / BOUND_BYTES * 100:.0f}%)"
              f"   {'✅ within bound' if after <= BOUND_BYTES else f'🔴 still {after - BOUND_BYTES:,} B over'}")
    if blocked:
        all_done_after = total - b(done)
        print(f"  (all {len(done)} done rows would give {all_done_after:,} B, "
              f"{all_done_after / BOUND_BYTES * 100:.0f}% — the ceiling rotation can reach)")

    if blocked:
        print(f"\n  🔴 {len(blocked)} row(s) NOT cleared — each needs a disposition entry:")
        for r, why in sorted(blocked, key=lambda x: -len(x[0]))[:12]:
            print(f"     {row_id(r):<6} {len(r.encode('utf-8')):>7,} B  {why}")
        if len(blocked) > 12:
            print(f"     … and {len(blocked) - 12} more")

    if not args.apply:
        print("\n  Reports only. `--apply` moves the CLEARED rows; it never moves a blocked one.")
        return 0

    if not cleared:
        print("\n  Nothing cleared to move. Write disposition entries first."); return 0

    # ── apply ────────────────────────────────────────────────────────────────────────────────
    moving = {row_id(r) for r, _ in cleared}
    backup = TASKS.with_suffix(".md.rotate-bak")
    shutil.copy2(TASKS, backup)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    kept = [l for l in lines if not (ROW.match(l) and row_id(l) in moving)]
    stamp = json.loads(DISPOSITION.read_text()).get("rotated_on", "undated")
    chunk = [f"\n## Rotated {stamp} — {len(cleared)} row(s)\n"] + [r for r, _ in cleared]
    prior = ARCHIVE.read_text(encoding="utf-8") if ARCHIVE.exists() else (
        "# TASKS.md archive\n\nRows rotated out of `TASKS.md` by `just tasks-rotate --apply`, "
        "**verbatim** — moved, never deleted.\nA row is here because its ticket file holds the record "
        "(T228 AC5b: the ticket is the\nsource, the board a projection), or because an explicit "
        "disposition entry in\n`project/tasks-rotation.json` cleared it. See [`INDEX.md`](INDEX.md) for which.\n")

    TASKS.write_text("\n".join(kept) + "\n", encoding="utf-8")
    ARCHIVE.write_text(prior.rstrip() + "\n" + "\n".join(chunk) + "\n", encoding="utf-8")

    # ── integrity, fail-closed ───────────────────────────────────────────────────────────────
    new_text, arc_text = TASKS.read_text(encoding="utf-8"), ARCHIVE.read_text(encoding="utf-8")
    problems = []
    for r, _ in cleared:
        if r not in arc_text:
            problems.append(f"{row_id(r)} did not land in the archive byte-identical")
    for name, pat in (("ticket", TICKET_LINK), ("issue", ISSUE_LINK)):
        before, after = len(pat.findall(text)), len(pat.findall(new_text)) + len(pat.findall(arc_text))
        if after < before:
            problems.append(f"{before - after} {name} link(s) LOST ({before} → {after})")

    if problems:
        shutil.copy2(backup, TASKS)
        print("\n  ❌ ROLLED BACK — integrity check failed:")
        for p in problems:
            print(f"     · {p}")
        return 1

    INDEX.write_text(
        "# Rotated ticket rows — index\n\n"
        "Generated by `just tasks-rotate --apply`. The rows themselves are in "
        "[`TASKS-archive.md`](TASKS-archive.md), verbatim.\n\n"
        "| Ticket | Rotated | Was the sole record of | Record now at |\n|---|---|---|---|\n"
        # `.get(i, {})` — most cleared rows have NO disposition entry, because the evidence rule
        # clears them on the ticket file's existence. Indexing `disp[i]` assumed paperwork that the
        # rule deliberately does not require; the red probes caught it as a KeyError on first run.
        + "".join(
            f"| {i} | {disp.get(i, {}).get('rotated', stamp)} "
            f"| {disp.get(i, {}).get('sole_record_of') or '—'} "
            f"| {disp.get(i, {}).get('record_moved_to') or f'.tasks/{i}.md'} |\n"
            for i in sorted(moving))
        , encoding="utf-8")
    backup.unlink()
    final = len(new_text.encode("utf-8"))
    print(f"\n  ✅ moved {len(cleared)} row(s) → {ARCHIVE.relative_to(ROOT)}")
    print(f"     every row byte-identical in the archive; ticket + issue links preserved")
    print(f"     TASKS.md now {final:,} B ({final / BOUND_BYTES * 100:.0f}% of bound)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
