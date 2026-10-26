#!/usr/bin/env python3
"""T228 AC6b — what makes a ticket a PARENT, and what does not.

The criterion was a TITLE STRING (`PARENT BATCH|PROGRAM|EPIC`) plus a member table. That measures
how someone worded a heading, not whether the relationship exists: T149 (8 members) and T184 (7)
are parents in substance and were invisible to both `ticket-graph` and `sync-subissues`.

🔴 Dropping to "declares a member table" over-matches, which is why this is a disjunction and not a
deletion. T239 declares `| ticket | issue | reason | its own words |` -- two tickets closed as
`not-planned`, with citations. That is evidence ABOUT other tickets, not membership, and a
member-count criterion would have adopted them as its children.

RECIPROCITY separates them without reference to any wording -- a parent-child relationship is
declared from both ends. Measured against the live corpus on 2026-08-27:
    T200 5/5 · T203 5/5 · T149 5/8 · T184 4/7 · T239 **0/2**
The threshold is therefore the WEAKEST one that works -- one member naming it back -- and not a
percentage. Picking 50% because it happens to separate this corpus is fitting the detector to the
answer, which AC6b explicitly forbids.

⚠️ These cases are SHAPES, not the live tickets. A test that reads `project/tickets/` would go red
the day someone edits T239, which is a test of the corpus rather than of the rule.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sync_subissues as ss  # noqa: E402


def parent(marked: bool, members: set[str], refs_back: set[str]) -> bool:
    """The rule under test, expressed once, exactly as `batches()` applies it."""
    if not members:
        return False
    if marked:
        return True
    return bool(members & refs_back)


CASES = [
    ("marker + members is a parent (T200/T203 shape)", True, {"T1", "T2"}, set(), True),
    ("member table + reciprocity is a parent (T149/T184 shape)", False, {"T1", "T2"}, {"T1"}, True),
    ("member table with NO reciprocity is NOT a parent (T239 shape)", False, {"T1", "T2"}, set(), False),
    ("the marker alone, with no members, is not a parent", True, set(), set(), False),
    ("a fresh parent is seen before its members point back", True, {"T1"}, set(), True),
    ("ONE reciprocating member is enough -- the threshold is not a percentage",
     False, {"T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"}, {"T3"}, True),
    ("reciprocity from a NON-member does not qualify it", False, {"T1"}, {"T9"}, False),
]


def main() -> int:
    fails = 0
    print("\nT228 AC6b — parent detection\n")
    for label, marked, members, back, want in CASES:
        got = parent(marked, members, back)
        ok = got == want
        fails += not ok
        print(f"  {'[OK]' if ok else '[FAIL]'} {label}")

    # The rule above must be the rule the tool actually ships. If `batches()` is rewritten and this
    # file is not, the cases above become a test of a function nobody calls.
    live = ss.batches()
    checks = [
        ("`batches()` finds T149 (member table, no title marker)", "T149" in live),
        ("`batches()` finds T184 (member table, no title marker)", "T184" in live),
        ("`batches()` finds T200 (title marker)", "T200" in live),
        ("`batches()` finds T203 (title marker)", "T203" in live),
        ("`batches()` EXCLUDES T239 (citation table, zero reciprocity)", "T239" not in live),
    ]
    for label, ok in checks:
        fails += not ok
        print(f"  {'[OK]' if ok else '[FAIL]'} {label}")

    total = len(CASES) + len(checks)
    print(f"\n{'[OK]' if not fails else '[FAIL]'} subissue parents: {total - fails}/{total} checks")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
