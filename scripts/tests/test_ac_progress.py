#!/usr/bin/env python3
"""Regression proof for ac_progress() — the AC checkbox states the ranker must understand.

T125 sat at a reported **4/4 = 100%** while one AC was explicitly blocked, because the parser
matched only `[x]` and `[ ]`. That ticket used two further states — `[N/A]` for a conditional
whose branch was not taken, and `[~]` for half-done — so both lines were invisible and the
denominator shrank to exactly the completed ones.

Worse, the workaround made it: an earlier session saw 4/5 = 80%, judged the N/A line to be
inflating the open count, and changed its checkbox to `[N/A]` — turning an undercount into a
false green. Its own note said *"worth fixing in the ranker, not just here."* This is that fix.

Rules:
  [x]    done      → counts toward done AND total
  [ ]    open      → counts toward total only
  [~]    partial   → counts toward total only (it is NOT done)
  [N/A]  excluded  → counts toward NEITHER (a branch not taken is not outstanding work)

Run: `just ac-progress-test`
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import tasks_query  # noqa: E402

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'✅' if ok else '❌'} {label}")
    if not ok:
        failures.append(f"{label}{(' — ' + detail) if detail else ''}")


TMP = Path(tempfile.mkdtemp(prefix="ac-progress-"))
tasks_query.TICKETS = TMP


def progress(body: str, tid: str = "T999") -> tuple[int, int]:
    (TMP / f"{tid}.md").write_text(body)
    return tasks_query.ac_progress(tid)


print("\n── the states the parser must understand ──")

check("all done → 2/2", progress("- [x] **AC1 — a**\n- [x] **AC2 — b**\n") == (2, 2))
check("one open → 1/2", progress("- [x] **AC1 — a**\n- [ ] **AC2 — b**\n") == (1, 2))

# The T125 shape, exactly.
t125 = ("- [x] **AC1 — decided**\n"
        "- [x] **AC2a — auth**\n"
        "- [x] **AC2b — drift**\n"
        "- [x] **AC3 — local-exec**\n"
        "- [N/A] **AC4 — branch not taken**\n"
        "- [~] **AC5 — half done, blocked**\n")
check("the T125 shape is 4/5, NOT 4/4 = 100%", progress(t125) == (4, 5), str(progress(t125)))

check("[~] is counted as NOT done but IS in the denominator",
      progress("- [x] **AC1 — a**\n- [~] **AC2 — half**\n") == (1, 2))
check("[N/A] is excluded from BOTH — a branch not taken is not outstanding work",
      progress("- [x] **AC1 — a**\n- [N/A] **AC2 — n/a**\n") == (1, 1))
check("a ticket that is ONLY N/A is unmeasurable (0,0), not 100%",
      progress("- [N/A] **AC1 — n/a**\n") == (0, 0))
check("no ACs at all stays (0,0) — unmeasurable, not unstarted",
      progress("# just a ticket\n\nsome prose\n") == (0, 0))
check("indented sub-criteria are counted (T154 nests AC8a–d)",
      progress("- [x] **AC8 — parent**\n  - [x] **AC8a — sub**\n  - [ ] **AC8b — sub**\n") == (2, 3))
check("a prose mention of AC is not a criterion",
      progress("- [x] **AC1 — a**\n\nSee AC1 for detail; [x] is not a checkbox here.\n") == (1, 1))

print("\n── the bold ** must not be load-bearing ──")

# The parser required `**AC`. Nine tickets wrote acceptance criteria without the bold — a
# perfectly ordinary style — and were silently excluded from the sdlc ranking, indistinguishable
# from tickets that never wrote any. T158 was one of them, filed the day after I opened a ticket
# about things that render as absent rather than flagged.
check("an UNBOLDED criterion counts", progress("- [ ] AC1 — a\n- [x] AC2 — b\n") == (1, 2))
check("bold and unbolded mix in one ticket",
      progress("- [x] **AC1 — a**\n- [ ] AC2 — b\n") == (1, 2))
check("the T145 shape (bold AFTER the id) counts",
      progress("- [x] AC1 ✅ **VERIFIED** — did the thing\n") == (1, 1))
check("[N/A] and [~] still work unbolded",
      progress("- [x] AC1 — a\n- [N/A] AC2 — n/a\n- [~] AC3 — half\n") == (1, 2))

# A digit is required after AC so ordinary prose in a checklist cannot be mistaken for a criterion.
check("a checkbox line that merely starts with AC-ish words is NOT a criterion",
      progress("- [x] **AC1 — real**\n- [ ] ACCESS control review\n") == (1, 1))

print()
if failures:
    print(f"❌ {len(failures)} failure(s):")
    for f in failures:
        print(f"   · {f}")
    sys.exit(1)
print("✅ ac-progress: all checks passed")
