#!/usr/bin/env python3
"""T250 AC4 — the TASKS row and the ticket must not disagree about status.

`CLAUDE.md` designates the T-row as **status-of-record**. Measured 2026-08-22 the row and the
ticket's own `status:` disagreed on **8 tickets**, 7 of them on the axis that matters, and nothing
compared the two surfaces. [[T243]] built status ↔ **ACs**; this is its missing sibling.

🔑 **The sharpest one is T74** — its row says ✅ over a ticket still `queued`. Every other
disagreement *understates* progress, which is merely stale; T74 is a **false green on the surface
the estate calls status-of-record**, so anyone reading the queue to pick work skips it.

⚠️ **Every fixture below exists because a real measurement was wrong first.** The reader went
through four refinements, and each was forced by data rather than foresight:

  1. **bare `|` split** reported 11 rows as broken that are fine — cells legitimately contain `||`
     and escaped pipes. `" | "` is the splitter `malformed_rows` already round-trips.
  2. **glyph alone** made `🔴 queued` unreadable — 🔴 is *emphasis*, not state.
  3. **any status word after the glyph** read `🟡 done via prettier, oxfmt pending` as a claim of
     done and invented a finding. A declaration ENDS at the word.
  4. **the unmappable bucket** surfaced `💤`/`⏸️` missing from the mapping entirely — two rows that
     would have silently passed. A row the gate cannot read is not a row that agrees.

🔬 And the ticket this probe belongs to recorded one of those wrong measurements as fact: it said
TASKS.md tables have differing column counts, and named T202 among four "false positives". Both
were artefacts of ① — every table is 6 columns with Status at index 5, and **T202 is a real
finding**.

Run: `just tasks-row-status-test`
"""

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "wom7web"
sys.path.insert(0, str(ROOT / "scripts"))

import tasks_bounds as tb  # noqa: E402

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'✅' if ok else '❌'} {label}")
    if not ok:
        failures.append(f"{label} — {detail}")


print("▶ T250 AC4 — row ↔ ticket status agreement\n")

# ── the declared mapping, case by case ──────────────────────────────────────────────────────────
CASES = [
    ("✅ **DONE 2026-08-22 — 6/6**", "done", "a ✅ lead is a claim of done"),
    ("⚪ queued", "queued", "⚪ plus the word"),
    ("⚪ **filed 2026-08-14 — spec proposal created**", "queued", "⚪ alone"),
    ("🟡 **AC1-AC4 BUILT**", "in-progress", "🟡 alone"),
    ("🟢 **BUILD DONE 2026-08-07** — spec strict-valid", "in-progress",
     "🟢 alone — `BUILD DONE` is PROSE inside the cell, not the declaration"),
    ("🔵 blocked on Google + owner", "blocked", "🔵 plus the word"),
    ("💤 P2", "paused", "💤 alone — the glyph the first mapping missed"),
    ("🟡 queued", "queued", "an explicit WORD beats the glyph, being more specific"),
    ("🔴 queued  📝 **FIX WRITTEN — awaiting the owner**", "queued",
     "🔴 is emphasis; the word after it carries the state"),
    ("🟡 done via prettier, oxfmt pending", "in-progress",
     "PROSE, not a declaration — an alphanumeric after the word means a sentence"),
]
for cell, expected, why in CASES:
    got, how = tb.row_claim(cell)
    check(f"{cell[:34]!r:38} → {expected:12} ({why})", got == expected, f"got {got!r} via {how}")

for cell in ("🔴 **filed 2026-08-12 — nothing built**", "no glyph at all", ""):
    got, how = tb.row_claim(cell)
    check(f"{cell[:34]!r:38} → UNMAPPABLE, never guessed", got is None, f"got {got!r} via {how}")

# ── the cell reader survives the shapes that broke the first version ────────────────────────────
ROWS = [
    "| [T900](project/tickets/T900.md) | P1 | task | web | ref | ⚪ queued |",
    # `||` inside prose: the bare-`|` split gave this row 8 cells and mis-read the Status column.
    "| [T901](project/tickets/T901.md) | P1 | gate is `a || b` here | web | ref | ✅ **DONE** |",
    # malformed on purpose — 5 cells. Must be SKIPPED, not column-5-read.
    "| [T902](project/tickets/T902.md) | P1 | task | web | ⚪ queued |",
]
cells = tb.row_status_cells(ROWS)
check("a cell containing `||` still reads its Status correctly",
      cells.get("T901") == "✅ **DONE**", f"got {cells.get('T901')!r}")
check("a malformed row is SKIPPED, not mis-read",
      "T902" not in cells,
      "reading column 5 of a row that has five cells is how a checker invents findings")
check("well-shaped rows are read", set(cells) == {"T900", "T901"}, f"got {sorted(cells)}")

# ── the three tiers, against fixture tickets ────────────────────────────────────────────────────
with tempfile.TemporaryDirectory() as td:
    tix = Path(td)
    for tid, status in [("T900", "done"), ("T901", "queued"), ("T903", "in-progress"),
                        ("T904", "done"), ("T905", "paused")]:
        (tix / f"{tid}.md").write_text(f"---\nid: {tid}\nstatus: {status}\n---\n")

    fixture = {
        "T900": "⚪ queued",                    # ticket done  → HARD
        "T901": "✅ **DONE**",                  # ticket queued → HARD (the T74 shape)
        "T903": "⚪ queued",                    # in-progress vs queued → SOFT
        "T904": "✅ **DONE 2026-08-22**",        # agrees
        "T905": "🔴 **filed — nothing built**",  # unmappable
    }
    hard, soft, unmappable = tb.status_disagreements(fixture, tix)
    check("a `done` ticket whose row claims queued is a HARD finding",
          any(h.startswith("T900:") for h in hard), f"hard={hard}")
    check("a ✅ row over a `queued` ticket is a HARD finding (the T74 false green)",
          any(h.startswith("T901:") for h in hard), f"hard={hard}")
    check("queued-vs-in-progress is SOFT, not hard",
          any(s.startswith("T903:") for s in soft) and not any(h.startswith("T903:") for h in hard),
          f"hard={hard} soft={soft}")
    check("an agreeing row appears in NO bucket",
          not any("T904" in x for x in hard + soft + unmappable))
    check("an unreadable row is reported, not counted as agreement",
          any(u.startswith("T905:") for u in unmappable), f"unmappable={unmappable}")
    check("exactly 2 hard, 1 soft, 1 unmappable — no double-counting",
          (len(hard), len(soft), len(unmappable)) == (2, 1, 1),
          f"got {(len(hard), len(soft), len(unmappable))}")

    # MUTATION — a reader that maps nothing must produce NO hard findings. Without this, "the gate
    # passes" and "the gate reads nothing" are the same observation, which is the defect class this
    # estate keeps shipping.
    real = tb.row_claim
    tb.row_claim = lambda cell: (None, "stubbed blind")
    try:
        blind_hard, _, blind_unmappable = tb.status_disagreements(fixture, tix)
    finally:
        tb.row_claim = real
    check("MUTATION: a blind reader finds 0 hard and flags everything unmappable",
          blind_hard == [] and len(blind_unmappable) == len(fixture),
          f"hard={blind_hard} unmappable={len(blind_unmappable)}")
    check("MUTATION discriminates — the real reader DOES find the same fixture hard",
          len(tb.status_disagreements(fixture, tix)[0]) == 2)

    # A ticket with no file is skipped rather than assumed to disagree.
    orphan_hard, _, _ = tb.status_disagreements({"T999": "✅ **DONE**"}, tix)
    check("a row whose ticket file is missing is skipped, not failed",
          orphan_hard == [], f"got {orphan_hard}")

# ── non-vacuity against the REAL corpus ─────────────────────────────────────────────────────────
real_rows = [ln for ln in (ROOT / "TASKS.md").read_text().split("\n") if tb.ROW.match(ln)]
real_cells = tb.row_status_cells(real_rows)
check("the real corpus yields a status cell for most rows (non-vacuous)",
      len(real_cells) > 100, f"only {len(real_cells)} of {len(real_rows)} rows read")
check("every table in TASKS.md really is 6 columns — the premise T250 got wrong",
      len(real_cells) == len(real_rows),
      f"{len(real_rows) - len(real_cells)} row(s) unreadable; if >0, malformed_rows should say so")

print()
if failures:
    print(f"❌ {len(failures)} failure(s):")
    for f in failures:
        print(f"   · {f}")
    sys.exit(1)
print("✅ the row and the ticket are compared, and the comparison is proven to reject")
