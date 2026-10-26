#!/usr/bin/env python3
"""Prove the TASKS.md row-shape check REJECTS — T243 AC3.

The board of record was the one surface with no validator: `tasks_bounds.py` measured bytes and
rows but never COLUMNS, and both ranked boards are built from the ticket FILES rather than these
rows — so eight malformed rows accumulated across roughly ten commits each and nothing said a word.
A gate nobody has watched fail is not a gate.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
TB = ROOT / "scripts/tasks_bounds.py"

spec = importlib.util.spec_from_file_location("tb", TB)
tb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tb)

GOOD = "| [T1](project/tickets/T1.md) | **P1** | task text | web | — | 🟡 |"


class P:
    def __init__(self): self.n = 0; self.fail: list[str] = []
    def check(self, label, ok, detail=""):
        self.n += 1
        print(f"  {label:<62} {'ok' if ok else '!! FAILED'}")
        if not ok: self.fail.append(f"{label} {detail}".strip())


def main() -> int:
    p = P()

    print("\nTHE BASELINE IS CLEAN")
    p.check("a well-formed 6-cell row passes", not tb.malformed_rows([GOOD]),
            str(tb.malformed_rows([GOOD])))

    print("\nBYTES MEAN BYTES, NOT CODE POINTS (2026-08-27)")
    # The gate read `len(text)` and `len(row)` -- CHARACTERS -- while its bound is declared
    # `max_bytes`/`max_row_bytes` and printed with a `B`. TASKS.md is emoji-dense, so it
    # under-reported itself by ~2% (650,227 vs 663,867) and three rows genuinely over the byte
    # bound were invisible. A gate that measures code points while saying bytes is not a strict
    # gate with a naming quirk -- it is a different gate.
    emoji_row = "| [T1](x) | **P1** | " + "🔴" * 100 + " | web | — | 🟡 |"
    p.check("a 100-emoji row is over 256 B but under 256 chars",
            len(emoji_row.encode("utf-8")) > 256 and len(emoji_row) < 256,
            f"{len(emoji_row.encode('utf-8'))} B vs {len(emoji_row)} chars")
    p.check("the fixture proves the two differ by more than rounding",
            len(emoji_row.encode("utf-8")) - len(emoji_row) > 200,
            f"delta {len(emoji_row.encode('utf-8')) - len(emoji_row)}")
    src = pathlib.Path(tb.__file__).read_text()
    p.check("tasks_bounds measures the FILE in bytes", 'len(text.encode("utf-8"))' in src)
    p.check("tasks_bounds measures each ROW in bytes", 'len(r.encode("utf-8"))' in src)
    p.check("no bare len(text) file measure remains", "(\"bytes\", len(text)," not in src)

    print("\nEACH REAL SHAPE FOUND IN THE CORPUS IS SEEN TO FAIL")
    # The exact two shapes T243 found. Neither loses text; both break the shape.
    seven = GOOD.rstrip(" |") + " | ✅ appended status prose"
    p.check("a 7th cell (prose beside the marker) is rejected", len(tb.malformed_rows([seven])) == 1,
            str(tb.malformed_rows([seven])))
    unterminated = GOOD.rstrip().rstrip("|").rstrip()
    p.check("an unterminated row is rejected", len(tb.malformed_rows([unterminated])) == 1,
            str(tb.malformed_rows([unterminated])))
    short = "| [T1](x) | **P1** | task | web | 🟡 |"
    p.check("a 5-cell row is rejected", len(tb.malformed_rows([short])) == 1,
            str(tb.malformed_rows([short])))

    print("\nTHE REPORT NAMES THE TICKET, NOT JUST THE COUNT")
    p.check("the finding carries the T-id", tb.malformed_rows([seven])[0].startswith("T1:"),
            str(tb.malformed_rows([seven])))

    print("\n🔴 THE MATCHER SEES SUFFIXED IDS — IT DID NOT, AND UNDER-COUNTED BY 3")
    # `T\\d+` missed T16a/T16b/T16c, so the file reported 236 rows where the board had 239:
    # a matcher under-reporting within its own stated scope.
# 🔴 T16a/T16b/T16c below are SYNTHETIC FIXTURES and must stay suffixed. The live tickets
# were renumbered to T16/T262/T263 on 2026-08-23, but what these probe is that the parser
# HANDLES a suffixed id at all — a property that must keep working whether or not one is in
# use today. A rename pass rewrote them once and silently neutered the probes: the collision
# fixture stopped colliding while still asserting a collision was found.
    suffixed = "| [T16a](project/tickets/T16a.md) | **P1** | t | web | — | 🟡 |"
    p.check("a suffixed id is MATCHED (so it can be checked at all)",
            tb.ROW.match(suffixed) is not None)
    p.check("...and passes when well-formed", not tb.malformed_rows([suffixed]))

    print("\n[NOTE] THE TRAP THAT BROKE T243'S OWN ROW ON THE DAY IT WAS FILED")
    # A literal " | " inside prose inflates the cell count. This is not a false positive to be
    # tuned away: the row genuinely renders wrong in markdown. The lesson is for the AUTHOR.
    piped = "| [T1](x) | **P1** | format is `| a | b |` here | web | — | 🟡 |"
    p.check("a literal ' | ' inside prose IS flagged (author's bug, not the gate's)",
            len(tb.malformed_rows([piped])) == 1, str(tb.malformed_rows([piped])))

    print("\nTHE LIVE BOARD IS CLEAN")
    board = (ROOT / "TASKS.md").read_text(encoding="utf-8", errors="replace").split("\n")
    rows = [l for l in board if tb.ROW.match(l)]
    p.check(f"all {len(rows)} live rows are well-formed", not tb.malformed_rows(rows),
            str(tb.malformed_rows(rows)[:5]))
    p.check("...and the corpus is non-empty (an empty set must never pass)", len(rows) > 100,
            f"{len(rows)} rows")

    print("\n" + "-" * 78)
    if p.fail:
        print(f"FAIL — {len(p.fail)} of {p.n}:", file=sys.stderr)
        for f in p.fail: print(f"  ✗ {f}", file=sys.stderr)
        return 1
    print(f"✅ {p.n} checks — the shape gate is seen to reject every malformed shape the")
    print("   corpus actually produced, including the one this suite's own ticket hit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
