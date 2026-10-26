#!/usr/bin/env python3
"""Epic completeness: do tickets point at real ROADMAP sections, and do sections have tickets?

Two directions, because only one of them is usually checked:
  ticket → section   a ticket whose `epic:` names a section that does not exist
  section → ticket   a ROADMAP section with no open ticket carrying it

Prints a report; exits 0 always (advisory, per T135 AC8).
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT / "wom7web"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from tasks_query import resolve_tickets_dir  # noqa: E402 — canonical .tasks/ resolver (T411)
TICKETS = resolve_tickets_dir()
ROADMAP = ROOT / "ROADMAP.md"

from sync_epic_vocabulary import extract_roadmap_epics

# Reverse mapping: slug -> parent section number (e.g. 'delivery-record-sync' -> '13')
SLUG_TO_SECT: dict[str, str] = {v: k.split(".")[0] for k, v in extract_roadmap_epics().items()}

# ── ROADMAP sections that exist ──────────────────────────────────────────────
sections: dict[str, str] = {}
for line in ROADMAP.read_text().splitlines():
    m = re.match(r"^##\s+(?:\S+\s+)?(\d+)\.\s+(.*)$", line)
    if m:
        sections[m.group(1)] = m.group(2).strip()

LEGEND = re.compile(r"\s*#\s*queued\s*\|.*$")

# ── every ticket's frontmatter ───────────────────────────────────────────────
Ticket = dict[str, str]
tickets: dict[str, Ticket] = {}
for f in sorted(TICKETS.glob("T*.md")):
    text = f.read_text()
    if not text.startswith("---"):
        continue
    fm = text.split("---", 2)[1]
    t: Ticket = {}
    for line in fm.splitlines():
        if ":" in line and not line.startswith(" "):
            k, _, v = line.partition(":")
            key = k.strip()
            # ⚠️ The ticket template leaves its own legend inside the VALUE
            # (`status: done          # queued | in-progress | blocked | done | paused`), on
            # 40 of 195 tickets. A parser that does not strip it drops those tickets from
            # BOTH the open and the done set — that is the whole 123-vs-141 discrepancy.
            # 🔴 Strip the LEGEND, not every `#`: an `epic:` legitimately contains one
            # (`Audit 2026-07-17 #7`), and a blanket `split("#")` silently eats it.
            v = LEGEND.sub("", v)
            t[key] = v.strip().strip('"')
    tickets[t.get("id", f.stem)] = t

OPEN = {"queued", "in-progress", "blocked", "paused"}
open_t = {k: v for k, v in tickets.items() if v.get("status") in OPEN}

# ── roll an `epic:` string up to a section number ────────────────────────────
def sect(epic: str) -> str | None:
    if epic in SLUG_TO_SECT:
        return SLUG_TO_SECT[epic]
    m = re.search(r"§\s*(\d+)", epic)
    return m.group(1) if m else None


by_sect: dict[str, list[str]] = defaultdict(list)
no_epic: list[str] = []
non_roadmap: dict[str, list[str]] = defaultdict(list)
dangling: dict[str, list[str]] = defaultdict(list)
raw_variants: dict[str, set[str]] = defaultdict(set)

def tnum(tid: str) -> tuple[int, str]:
    m = re.match(r"T(\d+)(.*)", tid)
    return (int(m.group(1)), m.group(2)) if m else (10**6, tid)


for tid, t in sorted(open_t.items(), key=lambda x: tnum(x[0])):
    epic = t.get("epic", "").strip()
    if not epic:
        no_epic.append(tid)
        continue
    s = sect(epic)
    if s is None:
        non_roadmap[epic].append(tid)
        continue
    raw_variants[s].add(epic)
    if s not in sections:
        dangling[s].append(tid)
    by_sect[s].append(tid)

print(f"▶ EPIC COMPLETENESS — {len(open_t)} open of {len(tickets)} tickets · "
      f"{len(sections)} ROADMAP sections\n")

print(f"── ticket → section ──")
print(f"  {len(no_epic):3} open tickets carry NO epic at all "
      f"({len(no_epic) * 100 // max(len(open_t), 1)}% of the open set)")
print(f"  {sum(len(v) for v in non_roadmap.values()):3} carry an epic that is not a ROADMAP § "
      f"({len(non_roadmap)} distinct strings)")
print(f"  {sum(len(v) for v in dangling.values()):3} 🔴 point at a § that DOES NOT EXIST in ROADMAP.md")
for s, ids in sorted(dangling.items(), key=lambda x: int(x[0])):
    print(f"        §{s}: {' '.join(ids)}")
if non_roadmap:
    print("\n  non-ROADMAP epic strings (not wrong, just unrolled-up):")
    for e, ids in sorted(non_roadmap.items(), key=lambda x: -len(x[1])):
        print(f"    {len(ids):2} · {e[:64]:66} {' '.join(ids[:6])}")

print(f"\n── inconsistent raw strings for one section ──")
multi = {s: v for s, v in raw_variants.items() if len(v) > 1}
print(f"  {len(multi)} section(s) are written more than one way:")
for s, vs in sorted(multi.items(), key=lambda x: -len(x[1]))[:8]:
    print(f"    §{s} ({len(vs)} spellings)")
    for v in sorted(vs):
        print(f"         {v[:88]}")

print(f"\n── section → ticket (the direction nobody checks) ──")
empty = [(s, name) for s, name in sorted(sections.items(), key=lambda x: int(x[0]))
         if s not in by_sect]
print(f"  {len(empty)} of {len(sections)} ROADMAP sections have NO open ticket:")
for s, name in empty:
    flag = "  ✅ decommissioned" if "DECOMMISSION" in name.upper() else ""
    print(f"    §{s:<3} {name[:74]}{flag}")

print(f"\n── the sections that DO carry work ──")
for s, ids in sorted(by_sect.items(), key=lambda x: -len(x[1])):
    name = sections.get(s, "🔴 NO SUCH SECTION")
    print(f"  §{s:<3} {len(ids):3} open · {name[:56]:58} {' '.join(ids[:8])}"
          + (" …" if len(ids) > 8 else ""))
