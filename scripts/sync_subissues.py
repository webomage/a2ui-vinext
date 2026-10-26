#!/usr/bin/env python3
"""T228 AC6 — mirror the local batch↔member relationship onto GitHub as native sub-issues.

The batches already exist locally and `just ticket-graph` already proves their symmetry: T200 and
T203 each declare 5 members, and every member names its parent back. GitHub shows none of it — the
issues are 10 flat rows with the structure living only in a markdown table.

🔑 **Rebuilt from the TICKET FILES, never from issue titles.** That is AC6's explicit instruction and
it is not fussiness: a title is prose someone can edit on the web UI, so deriving structure from it
would let the tracker silently redefine the record it is supposed to reflect. Membership is read
with the SAME pattern `ticket_graph.py` uses, so the two cannot disagree.

⚠️ **T42 is deliberately NOT included, against the AC's own text.** AC6 names "T42 (T91/T92/T93)",
but T42 declares no member table, and T91/T92 say they **supersede** T42 — *"supersedes T42 audit"*,
*"supersedes T42 sync-into-code"*. Superseding is replacement, not containment; making them
sub-issues would encode the opposite of what the tickets say. Recorded on the ticket rather than
resolved by guessing.

Idempotent: an existing link is left alone. Dry run unless `--apply`.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "wom7web"
TICKETS = ROOT / ".tasks"
# Read from `.w0m/sdlc.json → vcs.repo`, not hardcoded — see the note in sync_github.py. Three
# scripts held their own copy of this string; a repo transfer would have broken all three silently.
sys.path.insert(0, str(WEB / "project" / "scripts"))
from authz_blanket_gate import strip_jsonc as _strip_jsonc  # noqa: E402  (one JSONC reader)
REPO = json.loads(_strip_jsonc((ROOT / ".w0m" / "sdlc.json").read_text()))["vcs"]["repo"]
# Same expression as ticket_graph.py — a batch declares membership in a table row, and the row may
# lead with a number column (T200) or with the link itself (T203).
MEMBER_HDR = re.compile(r"^\|[^|\n]{0,12}\|?\s*\[\[(T[0-9a-z]+)\]\]\s*\|", re.M)
# 🔑 And the SAME batch criterion: a declaring TITLE plus members. `ticket_graph.py` is the
# estate's authority on what a batch is, and this tool must not invent a looser one — a first
# version keyed only on "≥2 member rows" found 4 batches where the gate finds 2, and would have
# created 15 sub-issue links off its own definition.
# ⚠️ That over-match was informative rather than merely wrong: T149 ("…parent of the skills…") and
# T184 ("consolidate … behind one ticket") ARE parents in substance and declare member tables, but
# word their titles differently, so the gate cannot see them either. Recorded on T228, not fixed
# here by widening a regex until it agrees with me.
BATCH_TITLE = re.compile(r"PARENT (BATCH|PROGRAM|EPIC)|TOP-LEVEL EPIC")
# Any [[T…]] reference anywhere in a ticket — used for the reciprocity test above.
REF = re.compile(r"\[\[(T[0-9a-z]+)\]\]")


def gh(*args: str) -> str | None:
    r = subprocess.run(["gh", *args], capture_output=True, text=True, check=False)
    return r.stdout.strip() if r.returncode == 0 else None


def frontmatter_issue(tid: str) -> int | None:
    p = TICKETS / f"{tid}.md"
    if not p.exists():
        return None
    m = re.search(r"^gh_issue:\s*(\d+)", p.read_text(encoding="utf-8", errors="replace"), re.M)
    return int(m.group(1)) if m else None


def batches() -> dict[str, list[str]]:
    """Which tickets are PARENTS -- T228 AC6b.

    A parent declares a member table AND is recognised **either** by the title marker **or** by
    RECIPROCITY: at least one declared member names it back. The title alone was the criterion
    until 2026-08-27 and it measured how someone worded a heading, not whether the relationship
    exists -- [[T149]] (8 members) and [[T184]] (7) are parents in substance and were invisible.

    🔴 The member table alone does NOT work either, which is why this is a disjunction and not a
    deletion. [[T239]] declares a two-row table -- `| ticket | issue | reason | its own words |` --
    of tickets closed as `not-planned`. That is EVIDENCE ABOUT other tickets, not membership, and
    a member-count criterion would have made them its children.

    Reciprocity separates them without reference to any wording, measured 2026-08-27:
    T200 5/5, T203 5/5, T149 5/8, T184 4/7, **T239 0/2**. The threshold is therefore the weakest
    one that works -- ONE member naming it back -- rather than a percentage chosen to fit; picking
    50% here would be fitting the detector to the answer, which this AC explicitly forbids.

    The title arm is KEPT so a freshly-written parent is recognised before its members have been
    updated to point back at it.
    """
    parsed: dict[str, tuple[bool, set[str], set[str]]] = {}
    for p in sorted(TICKETS.glob("T*.md")):
        body = p.read_text(encoding="utf-8", errors="replace")
        title = re.search(r"^title:\s*(.+)$", body, re.M)
        marked = bool(title and BATCH_TITLE.search(title.group(1)))
        parsed[p.stem] = (marked, set(MEMBER_HDR.findall(body)) - {p.stem},
                          set(REF.findall(body)))

    out: dict[str, list[str]] = {}
    for tid, (marked, members, _refs) in parsed.items():
        if not members:
            continue
        reciprocated = any(m in parsed and tid in parsed[m][2] for m in members)
        if marked or reciprocated:
            out[tid] = sorted(members)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    found = batches()
    if not found:
        print("  ❌ found 0 batches — the member pattern is broken, not the queue flat.")
        return 2

    planned = skipped = existing = 0
    for parent, members in found.items():
        pnum = frontmatter_issue(parent)
        if not pnum:
            print(f" [SKIP] {parent}: no gh_issue in frontmatter — cannot link")
            continue
        have_raw = gh("api", f"repos/{REPO}/issues/{pnum}/sub_issues") or "[]"
        have = {i.get("number") for i in json.loads(have_raw)}
        print(f"\n  {parent} → #{pnum}  ({len(members)} member(s), {len(have)} already linked)")
        for m in members:
            mnum = frontmatter_issue(m)
            if not mnum:
                print(f" [SKIP] {m}: no gh_issue — skipped"); skipped += 1; continue
            if mnum in have:
                print(f"      ⚪ {m} (#{mnum}) already a sub-issue"); existing += 1; continue
            if not a.apply:
                print(f"      + would link {m} (#{mnum})"); planned += 1; continue
            # the API takes the sub-issue's DATABASE id, not its number
            raw = gh("api", f"repos/{REPO}/issues/{mnum}", "--jq", ".id")
            if not raw:
                print(f"      ❌ {m} (#{mnum}): could not read its id"); skipped += 1; continue
            r = subprocess.run(
                ["gh", "api", "--method", "POST", f"repos/{REPO}/issues/{pnum}/sub_issues",
                 "-F", f"sub_issue_id={raw}"],
                capture_output=True, text=True, check=False)
            if r.returncode == 0:
                print(f"      ✅ linked {m} (#{mnum})"); planned += 1
            else:
                print(f"      ❌ {m} (#{mnum}): {r.stderr.strip()[:110]}"); skipped += 1

    verb = "linked" if a.apply else "would link"
    print(f"\n  {verb} {planned} · already present {existing} · skipped {skipped}")
    if not a.apply:
        print("  Dry run — re-run with --apply.")
    return 1 if skipped else 0


if __name__ == "__main__":
    sys.exit(main())
