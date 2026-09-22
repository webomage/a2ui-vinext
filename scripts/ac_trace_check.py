#!/usr/bin/env python3
"""Audit: does every ticket's acceptance-criteria state actually reach the ranker?

The parser now understands four checkbox states ([x] [ ] [~] [N/A]). That fixes tickets whose ACs
are checkboxes. It does NOTHING for a ticket that writes acceptance criteria in a shape with no
checkbox at all — a `## AC6` heading, or `- **AC1 —** …` with the box omitted. Those still report
(0, 0) and are EXCLUDED from the sdlc ranking as "unmeasurable", which is indistinguishable from a
ticket that genuinely never wrote any.

Three buckets:
  COUNTED    the parser sees ACs                        → fine
  UNCOUNTED  AC-shaped text present, parser sees none    → the defect this hunts
  NONE       no AC mention anywhere                      → genuinely unmeasurable
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TICKETS = ROOT / ".tasks"
if not TICKETS.is_dir():
    sys.exit(f"FATAL: Canonical tickets directory not found at {TICKETS} (AgDR-0025: zero silent fallbacks)")

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
    r"CLOSED AS A DUPLICATE of \[\[(T\d+)\]\]|^superseded_by:\s*\[?\[?(T\d+)", re.I | re.M)


def superseded_target(body: str) -> str | None:
    """The ticket that carries this one's work, if this ticket was closed in favour of another.

    A ticket closed as a duplicate legitimately has DONE status and zero ticked criteria — the work
    is tracked elsewhere, so ticking its boxes would be a lie and leaving them unticked is correct.
    Without this, the only honest record of a duplicate reads as drift.

    ⚠️ Deliberately NOT a keyword match. The exemption requires NAMING a ticket, and the caller
    verifies that ticket EXISTS — otherwise the word "duplicate" anywhere in a body would silence
    the check, which is a loophole rather than an exemption.
    """
    m = SUPERSEDED.search(body)
    if not m:
        return None
    return m.group(1) or m.group(2)


rows = tq.load()
counted, uncounted, none, unnumbered = [], [], [], []
supersedes: dict[str, str | None] = {}

for t in sorted(rows, key=lambda r: int(re.sub(r"\D", "", r["id"]) or 0)):
    ticket_file = TICKETS / f"{t['id']}.md"
    if not ticket_file.exists():
        continue
    body = ticket_file.read_text(encoding="utf-8", errors="replace")
    done, total = tq.ac_progress(t["id"])
    mentions = len(AC_MENTION.findall(body))
    rec = (t["id"], t["status"], t.get("priority") or "—", done, total, mentions)
    target = superseded_target(body)
    if target and not (TICKETS / f"{target}.md").exists():
        target = None  # names a ticket that does not exist — not an exemption
    supersedes[t["id"]] = target
    sec = SECTION.search(body)
    idless = 0
    if sec and not PLACEHOLDER.search(sec.group(1)):
        idless = len(BOX_NO_ID.findall(sec.group(1)))
    if idless:
        unnumbered.append((t["id"], t["status"], t.get("priority") or "—", idless))
    if total:
        counted.append(rec)
    elif mentions:
        uncounted.append(rec)
    else:
        none.append(rec)

if not rows:
    # An empty corpus must fail, not report a tidy "0 uncounted".
    print("❌ ac-trace-check: parsed 0 tickets — refusing to certify tracing over an empty set")
    sys.exit(2)

print(f"tickets: {len(rows)}   COUNTED {len(counted)}   UNCOUNTED {len(uncounted)}   NONE {len(none)}")

print(f"\n── 🔴 UNCOUNTED — AC-shaped text the ranker cannot see ({len(uncounted)}) ──")
for tid, st, pr, d, tot, m in uncounted:
    open_mark = "OPEN" if st not in ("done", "archived", "cancelled") else "closed"
    print(f"  {tid:6} {pr:3} {st:12} {open_mark:6} — {m} AC mention(s), parser sees 0")
if not uncounted:
    print("  (none)")

# A DONE ticket with unticked criteria is the other half of the same drift: the work landed and
# the boxes never moved, so the ranking reads it as unstarted.
_all_stale = [(tid, pr, d, tot) for tid, st, pr, d, tot, m in counted
              if st in ("done", "archived") and tot and d < tot]
stale = [r for r in _all_stale if not supersedes.get(r[0])]
exempt = [r for r in _all_stale if supersedes.get(r[0])]
print(f"\n── 🟡 DONE but with unticked criteria ({len(stale)}) ──")
for tid, pr, d, tot in stale:
    print(f"  {tid:6} {pr:3} {d}/{tot} — {tot - d} unticked")
if not stale:
    print("  (none)")
if exempt:
    print(f"\n── ⚪ EXEMPT — closed in favour of another ticket, so unticked criteria are CORRECT "
          f"({len(exempt)}) ──")
    for tid, pr, d, tot in exempt:
        print(f"  {tid:6} {pr:3} {d}/{tot} — work tracked in {supersedes[tid]}")

print(f"\n  COUNTED {len(counted)} · NONE {len(none)} (no AC text at all — genuinely unmeasurable)")

print(f"\n── 🔴 criteria with NO `AC<n>` id ({len(unnumbered)}) — real, and invisible to the ranker ──")
for tid, st, pr, n in unnumbered[:12]:
    print(f"  {tid:6} {pr:3} {st:12} {n} id-less checkbox(es)")
if not unnumbered:
    print("  (none)")

if uncounted or stale or unnumbered:
    print(f"\n❌ ac-trace-check FAILED — {len(uncounted)} untraceable, {len(stale)} stale-done, "
          f"{len(unnumbered)} id-less")
    sys.exit(1)
print("\n✅ ac-trace-check: every ticket's AC state reaches the ranker")
