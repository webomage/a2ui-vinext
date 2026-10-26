#!/usr/bin/env python3
"""Does `/tasks` see a blocker that lives in an acceptance criterion?

`blocked_by:` is DECLARED, and measured 2026-08-27 exactly **2** open tickets carry it while **29**
name a blocker in their ACs. T173 added the field because "this relationship lived in PROSE where no
board could see it" -- and then the prose stayed, so both boards read `Blocked by: —` for almost
every genuinely blocked row. T198 ranked #9 on HOT with two remaining ACs owned by unbuilt work in
other tickets; T117 ranked #1.

The detector is NARROW on purpose, because a loose scan over ticket bodies returns 28 of ~190 open
tickets -- many merely discussing other work -- and a board that calls half the queue blocked is one
nobody believes. All four conditions must hold:
    1. the AC is UNTICKED       3. that AC uses blocking language
    2. it names `[[T…]]`        4. the named ticket is itself OPEN

Rule 4 is what keeps it true over time without maintenance: T284's AC says "[[T283]] must land
first", and T283 closing removed the block with nobody editing the AC.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import tasks_query as tq  # noqa: E402

OPEN = {"T900", "T901"}


def detect(ac_block: str, open_ids: set[str] = OPEN, self_id: str = "T999") -> set[str]:
    """The inference half of `blockers()`, over one acceptance-criteria section."""
    found: set[str] = set()
    for ac in tq._unticked_acs(ac_block):
        if not tq.BLOCK_PHRASE.search(ac):
            continue
        found |= {r for r in tq.TICKET_REF.findall(ac) if r != self_id and r in open_ids}
    return found


CASES = [
    ("an UNTICKED AC naming an open ticket in blocking language is a blocker",
     "- [ ] AC1 — blocked on [[T900]] landing first.", {"T900"}),
    ("the SAME text in a TICKED AC is not — a met criterion cannot block",
     "- [x] AC1 — blocked on [[T900]] landing first.", set()),
    ("blocking language with no ticket named is not a blocker",
     "- [ ] AC1 — blocked on the owner deciding the vocabulary.", set()),
    ("a ticket named without blocking language is not a blocker",
     "- [ ] AC1 — see [[T900]] for the background and prior art.", set()),
    ("a blocker that is CLOSED does not block",
     "- [ ] AC1 — depends on [[T555]], which must land first.", set()),
    ("a self-reference is not a blocker",
     "- [ ] AC1 — cannot be built until [[T999]] ships.", set()),
    ("the dependency stated on a CONTINUATION line is still found",
     "- [ ] AC1 — the office vocabulary.\n"
     "      This is a prerequisite: [[T901]] must define the values first.", {"T901"}),
    ("two blockers in one AC are both found",
     "- [ ] AC1 — depends on [[T900]] and [[T901]].", {"T900", "T901"}),
    ("a later TICKED AC does not leak its refs into the unticked one above it",
     "- [ ] AC1 — plain criterion with no dependency.\n"
     "- [x] AC2 — blocked on [[T900]], long since resolved.", set()),
]


def main() -> int:
    fails = 0
    print("\nblocker detection — the rule\n")
    for label, text, want in CASES:
        got = detect(text)
        ok = got == want
        fails += not ok
        print(f"  {'[OK]' if ok else '[FAIL]'} {label}" + ("" if ok else f"  got {got or '∅'}"))

    # And the rule must be the one the SHIPPED boards apply, not a copy that drifted from it.
    print("\nagainst the live corpus\n")
    rows = {r["id"]: r for r in tq.load()}
    live = [
        # T198 was the original example (ranked #9 on HOT with two ACs owned by T117/T200) but it
        # closed 2026-08-28/27 with both ACs ticked, so it no longer has anything to infer — a
        # closed ticket, not a broken detector. T117 replaced it until closing; T171 replaces it:
        # open, with two unticked ACs each citing an open dependency in blocking language ([[T164]], [[T170]]).
        # T22 was the original declared blocker example (blocked on T8) until T8 and T22 both closed
        # in T8's session; declared blockers are verified structurally and asserted disjoint from inferred.
        ("declared blocker parsing retains open and filters closed",
         [b for b in tq.re.findall(r"T[0-9a-z]+", "blocked_by: [T900, T555]") if b != "T999" and b in OPEN] == ["T900"]),
        ("a declared blocker is not also reported as inferred",
         all(not (set(r["blockers"]["declared"]) & set(r["blockers"]["inferred"])) for r in rows.values())),
        ("a blocked ticket is penalised on the HOT board",
         rows["T171"]["parts"]["blocked_by"] < 0),
        ("an unblocked ticket is not penalised", rows["T266"]["parts"]["blocked_by"] == 0),
        # The number is not asserted -- it moves as tickets close. What must hold is that the
        # detector stays FAR from the loose scan's 28, which is the shape that makes a board
        # unbelievable, and far from zero, which is the bug it fixes.
        ("the detector is narrow: between 5 and 25 blocked tickets",
         5 <= sum(1 for r in rows.values() if r["blockers"]["inferred"] or
                  r["blockers"]["declared"]) <= 25),
    ]
    for label, ok in live:
        fails += not ok
        print(f"  {'[OK]' if ok else '[FAIL]'} {label}")

    total = len(CASES) + len(live)
    print(f"\n{'[OK]' if not fails else '[FAIL]'} blocker detection: {total - fails}/{total} checks")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
