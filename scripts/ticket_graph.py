#!/usr/bin/env python3
"""Ticket interconnection audit — links, epics, and batch/program membership.

Answers what neither ranked board can: how the tickets relate to EACH OTHER.

    python3 scripts/ticket_graph.py

Checks, in order of how much damage each defect does:
  · dangling  — a [[Tnn]] pointing at a ticket that does not exist
  · orphan    — an open ticket nothing references and which references nothing
  · double    — a ticket claimed by more than one batch/program (neither is then authoritative)
  · asymmetry — a batch names a member that does not name it back
  · epic      — members of one batch scattered across different epics
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TICKETS = ROOT / ".tasks"
if not TICKETS.is_dir():
    sys.exit(f"FATAL: Canonical tickets directory not found at {TICKETS} (AgDR-0025: zero silent fallbacks)")
LEGEND = re.compile(r"\s*#\s*queued\s*\|.*$")
OPEN = {"queued", "in-progress", "blocked", "paused"}
# A batch declares membership in a table row. ⚠️ The first version anchored on the row STARTING
# with the link and silently missed T200 entirely, whose table has a numbered first column —
# a detector that reports "1 batch" when there are 2 is the vacuous-green shape again.
MEMBER_HDR = re.compile(r"^\|[^|\n]{0,12}\|?\s*\[\[(T[0-9a-z]+)\]\]\s*\|", re.M)


@dataclass
class Ticket:
    fm: dict[str, str]
    body: str
    refs: set[str] = field(default_factory=set)
    members: set[str] = field(default_factory=set)


tk: dict[str, Ticket] = {}
for f in sorted(TICKETS.glob("T*.md")):
    text = f.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---"):
        continue
    fm, body = text.split("---", 2)[1], text.split("---", 2)[2]
    d: dict[str, str] = {}
    for line in fm.splitlines():
        if ":" in line and not line.startswith(" "):
            k, _, val = line.partition(":")
            d[k.strip()] = LEGEND.sub("", val).strip().strip('"')
    tid = d.get("id", f.stem)
    tk[tid] = Ticket(fm=d, body=body,
                     refs=set(re.findall(r"\[\[(T[0-9a-z]+)\]\]", body)) - {tid},
                     members=set(MEMBER_HDR.findall(body)))

if not tk:
    print("🔴 EMPTY CORPUS — 0 tickets parsed. Fix the loader; do not read this as 'no tickets'.", file=sys.stderr)
    sys.exit(1)

ids = set(tk)
open_ids = {t for t, v in tk.items() if v.fm.get("status") in OPEN}

# A batch/program declares a member table AND is recognised either by the TITLE MARKER or by
# RECIPROCITY -- at least one declared member names it back (T228 AC6b, 2026-08-27).
#
# The title alone was the criterion until then, and it measured how someone worded a heading
# rather than whether the relationship exists: T149 (8 members) and T184 (7) are parents in
# substance and were invisible to both this tool and `sync-subissues`.
#
# 🔴 The member table alone does not work either. T239 declares a two-row table --
# `| ticket | issue | reason | its own words |` -- of tickets closed as `not-planned`. That is
# evidence ABOUT other tickets, not membership, and a member-count criterion adopts them as its
# children. Reciprocity separates the two without reference to any wording: measured 2026-08-27,
# T200 5/5, T203 5/5, T149 5/8, T184 4/7, T239 **0/2**.
#
# ⚠️ This must stay identical to `sync_subissues.batches()`. Two consumers disagreeing about what
# a field MEANS is the whole subject of T228; letting the graph and the mirror use different
# definitions of "parent" would reproduce it inside the ticket meant to end it.
def _is_parent(t: str, v) -> bool:
    if not v.members:
        return False
    if re.search(r"PARENT (BATCH|PROGRAM|EPIC)|TOP-LEVEL EPIC", str(v.fm.get("title", ""))):
        return True  # kept so a fresh parent is seen before its members point back
    return any(m in tk and t in tk[m].refs for m in v.members)


batches = {t: v.members for t, v in tk.items() if _is_parent(t, v)}

print(f"▶ TICKET GRAPH — {len(tk)} tickets ({len(open_ids)} open) · "
      f"{sum(len(v.refs) for v in tk.values())} [[links]] · {len(batches)} batch/program\n")

# ── 1. dangling references ───────────────────────────────────────────────────
dangling: dict[str, set[str]] = {}
for t, v in tk.items():
    miss = {r for r in v.refs if r not in ids}
    if miss:
        dangling[t] = miss
print(f"── dangling [[refs]] (point at no ticket): {sum(len(v) for v in dangling.values())}")
for t, miss in sorted(dangling.items())[:12]:
    print(f"     {t:6} → {', '.join(sorted(miss))}")

# ── 2. double membership ─────────────────────────────────────────────────────
owner: dict[str, list[str]] = defaultdict(list)
for b, members in batches.items():
    for m in members:
        owner[m].append(b)
double = {m: bs for m, bs in owner.items() if len(bs) > 1}
print(f"\n── claimed by MORE THAN ONE batch: {len(double)}"
      + ("   ✅ none — each member has one authority" if not double else ""))
for m, bs in sorted(double.items()):
    print(f"     🔴 {m} claimed by {', '.join(sorted(bs))}")

# ── 3. batch ↔ member symmetry + epic coherence ──────────────────────────────
print("\n── batches, their members, and whether each names its parent back")
for b, members in sorted(batches.items()):
    bep = str(tk[b].fm.get("epic", ""))
    print(f"  {b}  ({len(members)} members)  epic={bep or '(none)'}")
    for m in sorted(members):
        if m not in tk:
            print(f"     🔴 {m:6} MEMBER DOES NOT EXIST")
            continue
        back = b in tk[m].refs
        mep = str(tk[m].fm.get("epic", ""))
        same = "same epic" if mep == bep else f"⚠️ epic={mep or '(none)'}"
        print(f"     {'✅' if back else '🔴'} {m:6} {'names parent' if back else 'does NOT name parent'} · {same}")

# ── 4. orphans among open tickets ────────────────────────────────────────────
referenced = {r for v in tk.values() for r in v.refs}
orphans = sorted(t for t in open_ids
                 if t not in referenced and not tk[t].refs)
print(f"\n── OPEN tickets that neither reference nor are referenced: {len(orphans)}")
print("     " + (" ".join(orphans) if orphans else "none"))

# ── 5. most-connected ────────────────────────────────────────────────────────
deg: dict[str, int] = defaultdict(int)
for t, v in tk.items():
    for r in v.refs:
        deg[t] += 1
        deg[r] += 1
print("\n── most-connected tickets (in+out degree)")
for t, n in sorted(deg.items(), key=lambda x: -x[1])[:10]:
    st = tk[t].fm.get("status", "?") if t in tk else "MISSING"
    print(f"     {t:6} {n:3}  {st}")
