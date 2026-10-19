#!/usr/bin/env python3
"""The tech-debt register against reality — does a row still describe something true?

    python3 project/scripts/debt_register_check.py             # advisory, exits 0
    python3 project/scripts/debt_register_check.py --enforce   # exits 1 on a rotted row

`CLAUDE.md` instructs *"read before building, delete rows the ticket pays down"* — and **nothing
checks that either half happened**. The markers side is automated (`just tech-debt` greps
TODO/FIXME/HACK, and pre-push counts what a push adds); the DECIDED side is 48 hand-written rows
that no gate has ever read.

🔑 **The failure mode is a register that reads as current while describing a fixed world.** The
`public.tech_debt` Supabase census was retired 2026-07-21 for exactly that — *"78% noise, never
resolved anything, and its documented query referenced columns that do not exist."* A markdown
register rots the same way, more quietly.

What it checks, all of it mechanical:
  · **DUPLICATE ID** — two rows claiming the same D-number
  · **DEAD PATH** — a file the row cites that no longer exists
  · **DEAD TICKET** — a `[[T##]]`/`T##` reference with no ticket file
  · **UNOWNED** — the Tracked cell names only tickets that are finished, so no live ticket is
    carrying this row. ⚠️ **This is informational, not a defect.** Read on for why.

🔴 **The `Tracked` column has NO DEFINED GRAMMAR, and that is the real finding.** It holds at least
four different statements today, and free text cannot distinguish them:

    T89 gap                        found during T89; owned by nobody
    T168 (recorded), consumed by…  T168 RECORDED it — T168 was never going to fix it
    T169 AC1/AC6 (accepted)        an ACCEPTED risk, not pending work
    — (found at T135's gate)       honestly unowned, with provenance

A first version of this check read all of those as *"tracked by a finished ticket ⇒ stale"* and
reported **17 rows**, of which the ones examined were all still-real debt that had simply outlived
the ticket that noticed them. ⇒ **Give the column a grammar before gating on it** — e.g. an explicit
`owner:` vs `found-at:` — and until then this class stays informational.
  · **RESOLVED, NOT DELETED** — a row whose text says RESOLVED/PAID, still sitting in the register

⚠️ **A row with `— (needs a T-row)` is NOT rot.** Ten rows say that deliberately; it means *nobody
has filed the ticket yet*, which is a real state and honestly recorded. Flagging it would train
people to write a fake ticket id to silence the gate.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

def find_workspace_root(start_path: Path | None = None) -> Path:
    """Find the workspace root containing .tasks and .w0m/sdlc.json."""
    cur = (start_path or Path(__file__)).resolve()
    for parent in [cur] + list(cur.parents):
        if (parent / ".tasks").is_dir() and (parent / ".w0m").is_dir():
            return parent
        if (parent / ".git").exists() and (parent / "wom7web").is_dir():
            return parent
    return Path(__file__).resolve().parents[1]


import os

ROOT = Path(os.environ.get("W0M_WORKSPACE_ROOT") or find_workspace_root())
REGISTER = Path(os.environ.get("W0M_TECH_DEBT_MD") or (ROOT / "TECH-DEBT.md"))
TICKETS = Path(os.environ.get("W0M_TASKS_DIR") or (ROOT / ".tasks"))

ROW = re.compile(r"^\|\s*(D\d+)\s*\|(.*)$", re.M)
TREF = re.compile(r"\[\[(T\d+[a-z]?)\]\]|\b(T\d+[a-z]?)\b")
# A path is worth checking only if it looks like one: has a slash and a real extension.
PATH = re.compile(r"`([\w./@-]+/[\w.@-]+\.(?:ts|tsx|js|mjs|py|astro|svelte|sql|json|md|sh|yaml|yml))`")
# 🔴 A row-STATUS declaration, not the word appearing in prose. The first version matched
# `\b(RESOLVED|CLOSED|…)\b` anywhere and reported 7 rows of which SIX were false: it hit
# "closed 2026-07-21", Vite's "resolved at runtime", "closed P0", "closed tickets", a sub-part that
# "were resolved", and — worst — **D48's "🔴 NOT RESOLVED"**, the exact inverse of the finding.
# A status declaration in this register opens the Debt cell and is marked: `✅ **RESOLVED …`.
# T257 AC4 — glyph branch retired now that TECH-DEBT.md and test fixtures use bracketed text markers.
RESOLVED = re.compile(
    r"^\s*\[(?:RESOLVED|DONE|OK)\]\s*\*\*(RESOLVED|PAID DOWN|FIXED AND DELETED)\b",
    re.I)
NOT_RESOLVED = re.compile(r"NOT\s+RESOLVED", re.I)


def ticket_status(tid: str) -> str | None:
    f = TICKETS / f"{tid}.md"
    if not f.is_file():
        return None
    m = re.search(r"^status:\s*(\S+)", f.read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else "unknown"


def main() -> int:
    ap = argparse.ArgumentParser(description="Tech-debt register rot check")
    ap.add_argument("--enforce", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not REGISTER.is_file():
        print(f"[HIGH] {REGISTER.name} not found — cannot check a register that is not there.")
        return 1

    text = REGISTER.read_text(encoding="utf-8")
    rows = ROW.findall(text)
    if not rows:
        print("[HIGH] EMPTY CORPUS — parsed 0 debt rows. Fix the parse; do not read this as "
              "'the register is clean'.")
        return 1

    findings: dict[str, list[dict]] = {k: [] for k in
                                       ("duplicate", "dead_path", "dead_ticket",
                                        "stale_tracking", "resolved_not_deleted")}
    seen: dict[str, int] = {}

    for did, body in rows:
        if did in seen:
            findings["duplicate"].append({"id": did, "detail": "declared more than once"})
        seen[did] = seen.get(did, 0) + 1

        # ⚠️ A debt row ABOUT a deletion legitimately cites the deleted path — D27/D28 describe
        # `lib/vault.ts` precisely because T168 removed it. So a missing path is only interesting
        # when the row does not say it was removed.
        # ⚠️ Search the row's PROSE, with the cited paths blanked out first. Without that, the
        # removal words are matched inside the filename itself — a row citing
        # `src/lib/missing-keys.ts` or `packages/orphan-cleanup.ts` excuses its own dead path and
        # the finding is silently suppressed. Caught by this gate's own probe, which happened to
        # name its fixture `missing.ts`.
        prose = PATH.sub(" ", body)
        says_removed = re.search(
            r"\b(deleted|removed|retired|dropped|decommission|does not exist|absent|missing|"
            r"no longer|orphan)", prose, re.I)
        for pth in PATH.findall(body):
            if not (ROOT / pth).exists() and not (ROOT / "wom7web" / pth).exists():
                if not says_removed:
                    findings["dead_path"].append({"id": did, "detail": pth})

        # 🔴 ONLY the Tracked column, never the row's prose. The first version matched every
        # `T##` anywhere in the body and flagged 41 of 48 rows — a row that merely CITES a finished
        # ticket in its explanation is not stale tracking. An 85% hit rate is a broken check, not a
        # rotten register, and a report that noisy is one nobody reads.
        cells = [c.strip() for c in body.split("|")]
        tracked = cells[-2] if len(cells) >= 2 else ""
        refs = {a or b for a, b in TREF.findall(tracked)}
        for t_ in sorted(refs):
            st = ticket_status(t_)
            if st is None:
                findings["dead_ticket"].append({"id": did, "detail": f"{t_} has no ticket file"})
            elif st in ("done", "archived"):
                findings["stale_tracking"].append(
                    {"id": did, "detail": f"only reference is {t_} ({st})"})

        # The Debt cell is the first field after the id.
        debt_cell = body.split("|")[1] if body.count("|") >= 1 else body
        if RESOLVED.search(debt_cell) and not NOT_RESOLVED.search(body):
            findings["resolved_not_deleted"].append(
                {"id": did, "detail": "row text says resolved — CLAUDE.md says delete it"})

    if args.json:
        print(json.dumps({"rows": len(rows), "findings": findings}, indent=2))
        return 1 if (any(findings.values()) and args.enforce) else 0

    gating = {k: v for k, v in findings.items() if k != "stale_tracking"}
    total = sum(len(v) for v in gating.values())
    informational = len(findings["stale_tracking"])
    print(f"[STEP] tech-debt register ↔ reality · {len(rows)} row(s) in {REGISTER.name}\n")

    labels = {
        "duplicate": ("[HIGH]", "DUPLICATE ID"),
        "dead_path": ("[WARN]", "DEAD PATH — cites a missing file, and does NOT say it was removed"),
        "dead_ticket": ("[HIGH]", "DEAD TICKET — referenced ticket has no file"),
        "stale_tracking": ("[INFO]", "UNOWNED — no LIVE ticket in the Tracked cell (informational: "
                                    "the column has no grammar, see the module docstring)"),
        "resolved_not_deleted": ("[WARN]", "RESOLVED, NOT DELETED"),
    }
    for key, (marker, label) in labels.items():
        hits = findings[key]
        print(f"  {marker} {label}: {len(hits)}")
        for h in hits[:8]:
            print(f"       {h['id']}  {h['detail']}")
        if len(hits) > 8:
            print(f"       …and {len(hits) - 8} more")
        if not hits:
            print("       [OK] none")

    print()
    if total:
        print(f"── {total} finding(s), plus {informational} informational."
              + ("" if args.enforce else " Advisory: exits 0."))
        print(" [WARN] A `— (needs a T-row)` tracked value is NOT a finding — it is an honest "
              "record that nobody has filed the ticket yet.")
    else:
        print(f"── every row still describes something true"
              + (f" ({informational} unowned, informational)." if informational else "."))
    return 1 if (total and args.enforce) else 0


if __name__ == "__main__":
    raise SystemExit(main())
