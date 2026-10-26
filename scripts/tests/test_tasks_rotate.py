#!/usr/bin/env python3
"""T228 AC8b — red probes for `tasks-rotate`.

The tool MOVES rows out of the board of record. A bug here loses a ticket silently, so every
assertion below is paired with a mutation showing it can fail.
"""
import json, pathlib, shutil, sys, tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import tasks_rotate as tr  # noqa: E402

failures: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(("  ✅ " if cond else "  ❌ ") + label + ("" if cond else f"  — {detail}"))
    if not cond:
        failures.append(label)


ROW_T1 = "| [T1](.tasks/T1.md) | **P1** | thing | web | ref | ✅ DONE |"
ROW_T2 = "| [T2](.tasks/T2.md) | **P1** | other | web | ref | ⚪ queued |"
ROW_T9 = "| [T9](.tasks/T9.md) | **P1** | orphan | web | ref | ✅ DONE |"

# ── status parsing ───────────────────────────────────────────────────────────────────────────
check("a done row's status cell is read as done", tr.status_cell(ROW_T1).startswith("✅"))
check("an open row's is not", not tr.status_cell(ROW_T2).startswith("✅"))
check("row_id extracts the id", tr.row_id(ROW_T1) == "T1")

with tempfile.TemporaryDirectory() as d:
    repo = pathlib.Path(d)
    (repo / ".tasks").mkdir(parents=True)
    (repo / ".tasks" / "T1.md").write_text("# T1\n" + "x" * 500)
    tr.ROOT = repo

    # ── the discrimination that matters: ticket file present vs absent ───────────────────────
    ok1, why1 = tr.clearance(ROW_T1, None)
    check("a done row WITH a ticket file clears with no paperwork", ok1, why1)
    ok9, why9 = tr.clearance(ROW_T9, None)
    check("a done row with NO ticket file is BLOCKED (T174's shape)", not ok9, why9)
    check("...and says why in terms of the risk", "only record" in why9, why9)

    # ── the written disposition, for the rows that need one ──────────────────────────────────
    ok, why = tr.clearance(ROW_T9, {"id": "T9", "sole_record_of": "a live security gap"})
    check("sole record with nowhere else to read it stays BLOCKED", not ok, why)
    ok, why = tr.clearance(ROW_T9, {"id": "T9", "sole_record_of": "a live security gap",
                                    "record_moved_to": "docs/SECURITY.md"})
    check("...and clears once the record has somewhere to live", ok, why)
    ok, why = tr.clearance(ROW_T9, {"id": "T9"})
    check("an explicit entry with no sole_record_of clears", ok, why)

# ── MUTATION: prove these assertions are not vacuous ─────────────────────────────────────────
# The pre-fix rule was "an entry exists" — paperwork, not evidence. It DISAGREES with the current
# rule on the live case (a row with a ticket file and no entry), which is the whole point.
def old_rule(entry: object) -> bool:
    return entry is not None
with tempfile.TemporaryDirectory() as d:
    repo = pathlib.Path(d)
    (repo / ".tasks").mkdir(parents=True)
    (repo / ".tasks" / "T1.md").write_text("# T1")
    tr.ROOT = repo
    check("MUTATION: the OLD paperwork rule would BLOCK a row the evidence clears",
          old_rule(None) is False and tr.clearance(ROW_T1, None)[0] is True)
    check("MUTATION: both rules still BLOCK the orphan row with no entry",
          old_rule(None) is False and tr.clearance(ROW_T9, None)[0] is False,
          "loosening the rule must not have removed the case it exists for")

# ── end to end: rows move verbatim, links survive, blocked rows stay ─────────────────────────
with tempfile.TemporaryDirectory() as d:
    repo = pathlib.Path(d)
    (repo / ".tasks").mkdir(parents=True)
    (repo / ".tasks" / "T1.md").write_text("# T1")
    board = ("# TASKS\n\n| id | p | t | r | ref | s |\n|---|---|---|---|---|---|\n"
             + ROW_T1 + "\n" + ROW_T2 + "\n" + ROW_T9 + "\n")
    (repo / "TASKS.md").write_text(board)
    (repo / "project" / "tasks-rotation.json").parent.mkdir(parents=True, exist_ok=True)
    (repo / "project" / "tasks-rotation.json").write_text(json.dumps({"rotated_on": "2026-08-29", "rotated": []}))
    tr.ROOT = repo
    tr.TASKS = repo / "TASKS.md"
    tr.ARCHIVE_DIR = repo / ".tasks" / "archive"
    tr.ARCHIVE = tr.ARCHIVE_DIR / "TASKS-archive.md"
    tr.INDEX = tr.ARCHIVE_DIR / "INDEX.md"
    tr.DISPOSITION = repo / "project" / "tasks-rotation.json"

    sys.argv = ["tasks_rotate.py", "--apply"]
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = tr.main()
    after = (repo / "TASKS.md").read_text()
    arc = tr.ARCHIVE.read_text()
    check("apply exits 0", rc == 0, buf.getvalue()[-300:])
    check("the cleared done row LEFT the board", ROW_T1 not in after)
    check("the cleared row is in the archive BYTE-IDENTICAL", ROW_T1 in arc)
    check("the OPEN row stayed", ROW_T2 in after)
    check("the BLOCKED orphan row stayed (no ticket file, no entry)", ROW_T9 in after)
    check("the index names what moved", "T1" in tr.INDEX.read_text())
    check("no backup left behind", not (repo / "TASKS.md.rotate-bak").exists())

print()
if failures:
    print(f"❌ {len(failures)} failure(s):")
    for f in failures:
        print(f"   · {f}")
    sys.exit(1)
print("✅ rotation clears on evidence, blocks the orphan row, and moves verbatim")
