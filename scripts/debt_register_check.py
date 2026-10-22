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
  · **UNKNOWN CITATION (T331 AC1/AC3)** — a `D##` citation in live prose/skills/config that has
    neither an open row nor a `## Closed-Debt Ledger` entry in `TECH-DEBT.md`
  · **STALE OPEN ASSERTION (T331 AC2/AC3)** — a live citation to a `## Closed-Debt Ledger` entry
    that asserts the closed debt row is still open/active/tracked

Citation & Disambiguation Grammar (T331 AC3):
  · **Scanned surfaces:** `TECH-DEBT.md`, `CLAUDE.md`, `AGENTS.md`, `ROADMAP.md`,
    `wom7web/docs/**/*.md`, `.agents/skills/*/SKILL.md`, `wom7web/.agents/skills/*/SKILL.md`,
    `.w0m/sdlc.json`, `wom7web/project/test-suites.json`.
  · **Candidate token:** `\\bD([1-9]\\d*)\\b` (matches `[[D\\d+]]`, `` `D\\d+` ``, `debt row D\\d+`,
    `TECH-DEBT D\\d+`, and bare `D\\d+`; word boundaries reject `3D`, hex strings, UUIDs, and `D0`).
  · **Non-debt exclusions:**
    1. Mermaid graph node IDs (`D\\d+["..."]`, `--> D\\d+`, `D\\d+ -->`).
    2. Local checklist / AgDR decision-table labels (`- [ ] D1.`, `| **D1** |`, `AgDR-... D1–D5`).
    3. Cloudflare D1 database tokens (`D1` on lines mentioning `Cloudflare`, `Workers`, `KV`, `R2`,
       `SQLite`, `wrangler`, or `D1 database`).
  · **Classification:**
    - `open`: `D##` is an active row in `TECH-DEBT.md` → OK.
    - `closed_historical`: `D##` is in `## Closed-Debt Ledger` and the line does not assert open
      status → OK.
    - `stale_assertion` (HIGH): `D##` is in `## Closed-Debt Ledger` and the line matches an
      open-status assertion (`tracked as/in/under D##`, `see debt row D##`, `see TECH-DEBT D##`,
      `open/active/unresolved debt D##`, `D## is/remains open`) without a historical/closed
      qualifier (`closed`, `paid`, `deleted`, `resolved`, `retired`, `fixed`, `was`, `until`,
      `formerly`, `historically`, `said`).
    - `unknown_citation` (HIGH): `D##` is in neither open rows nor `## Closed-Debt Ledger`.
  · **Denominator & fail-closed reporting (T331 AC5):**
    Reports `files_scanned`, `citations_total`, `citations_open`, `citations_closed_historical`,
    `citations_unknown`, `citations_stale`, and `unmeasurable_surfaces`. Missing required surfaces
    in an estate checkout fail closed as `UNMEASURABLE`.

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
CLOSED_HEADING = re.compile(r"^##\s+Closed-Debt Ledger\b", re.I)
NEXT_HEADING = re.compile(r"^##\s+")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
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

DEBT_TOKEN = re.compile(r"\bD([1-9]\d*)\b")
MERMAID_NODE = re.compile(r"(?:-->\s*D\d+\b|\bD\d+\s*(?:-->|[\[\(\{]))")
LOCAL_DECISION_LINE = re.compile(
    r"(?:^\s*-\s*\[[ xX]\]\s*D\d+\.|^\s*\|\s*\*\*D\d+\*\*\s*\||AgDR-\d+.*`D1`[–-]`D\d+`)"
)
CLOUDFLARE_D1_CONTEXT = re.compile(
    r"(?i)\b(?:cloudflare|workers|wrangler|sqlite|d1\s+databases?|r2|kv)\b"
)
STALE_OPEN_PATTERNS = (
    re.compile(r"(?i)\btracked\s+(?:as|in|under)\s+\[*\`*(D[1-9]\d*)\`*\b"),
    re.compile(r"(?i)\bsee\s+(?:debt\s+row|TECH-DEBT(?:\.md)?)\s+\[*\`*(D[1-9]\d*)\`*\b"),
    re.compile(r"(?i)\b(?:open|active|unresolved)\s+debt(?:\s+row)?\s+\[*\`*(D[1-9]\d*)\`*\b"),
    re.compile(r"(?i)\[*\`*(D[1-9]\d*)\`*\]*\s+(?:is|remains)\s+(?:still\s+)?(?:open|active|unresolved)\b"),
)
HISTORICAL_GUARD = re.compile(
    r"(?i)\b(?:closed|paid|deleted|resolved|retired|fixed|was|until|formerly|historically|said)\b"
)


def ticket_status(tid: str) -> str | None:
    f = TICKETS / f"{tid}.md"
    if not f.is_file():
        return None
    m = re.search(r"^status:\s*(\S+)", f.read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else "unknown"


def split_register_sections(text: str) -> tuple[str, dict[str, dict]]:
    """Split TECH-DEBT.md into open-table text and parsed Closed-Debt Ledger entries."""
    open_lines: list[str] = []
    closed_ledger: dict[str, dict] = {}
    in_closed = False
    for lineno, line in enumerate(text.splitlines(), 1):
        if CLOSED_HEADING.match(line):
            in_closed = True
            continue
        if in_closed and NEXT_HEADING.match(line):
            in_closed = False
        if not in_closed:
            open_lines.append(line)
            continue
        m = ROW.match(line)
        if not m:
            continue
        did = m.group(1)
        cells = [c.strip() for c in m.group(2).split("|")]
        if cells and cells[-1] == "":
            cells = cells[:-1]
        closed_date = cells[0] if len(cells) >= 1 else ""
        paid_by = cells[1] if len(cells) >= 2 else ""
        summary = cells[2] if len(cells) >= 3 else ""
        refs = sorted({a or b for a, b in TREF.findall(paid_by)})
        closed_ledger[did] = {
            "id": did,
            "line": lineno,
            "closed": closed_date,
            "paid_by": paid_by,
            "tickets": refs,
            "summary": summary,
        }
    return "\n".join(open_lines), closed_ledger


def _is_non_debt_token(did: str, line: str) -> bool:
    if MERMAID_NODE.search(line):
        return True
    if LOCAL_DECISION_LINE.search(line):
        return True
    if did == "D1" and CLOUDFLARE_D1_CONTEXT.search(line):
        return True
    return False


def _is_stale_open_assertion(did: str, line: str) -> bool:
    if HISTORICAL_GUARD.search(line):
        return False
    for pat in STALE_OPEN_PATTERNS:
        for m in pat.finditer(line):
            if m.group(1) == did:
                return True
    return False


def collect_citation_surfaces(root: Path, register: Path) -> tuple[dict[str, str], list[str]]:
    """Collect readable surfaces and report any missing/unreadable required estate surfaces."""
    surfaces: dict[str, str] = {}
    unmeasurable: list[str] = []
    require_estate_surfaces = (root / ".w0m").is_dir() or os.environ.get("W0M_REQUIRE_SURFACES") == "1"

    reg_rel = str(register.relative_to(root)) if register.is_relative_to(root) else register.name
    surfaces[reg_rel] = register.read_text(encoding="utf-8")

    fixed_rel_paths = (
        "CLAUDE.md",
        "AGENTS.md",
        "ROADMAP.md",
        ".w0m/sdlc.json",
        "wom7web/project/test-suites.json",
    )
    for rel in fixed_rel_paths:
        p = root / rel
        if p.is_file():
            try:
                surfaces[rel] = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                unmeasurable.append(f"{rel} (unreadable)")
        elif require_estate_surfaces:
            unmeasurable.append(f"{rel} (missing)")

    docs_dir = root / "wom7web/docs"
    if docs_dir.is_dir():
        for p in sorted(docs_dir.rglob("*.md")):
            rel = str(p.relative_to(root))
            try:
                surfaces[rel] = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                unmeasurable.append(f"{rel} (unreadable)")
    elif require_estate_surfaces:
        unmeasurable.append("wom7web/docs (missing)")

    for sdir_rel in (".agents/skills", "wom7web/.agents/skills"):
        sdir = root / sdir_rel
        if sdir.is_dir():
            for p in sorted(sdir.glob("*/SKILL.md")):
                rel = str(p.relative_to(root))
                try:
                    surfaces[rel] = p.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    unmeasurable.append(f"{rel} (unreadable)")

    return surfaces, unmeasurable


def main() -> int:
    ap = argparse.ArgumentParser(description="Tech-debt register rot check")
    ap.add_argument("--enforce", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not REGISTER.is_file():
        print(f"[HIGH] {REGISTER.name} not found — cannot check a register that is not there.")
        return 1

    text = REGISTER.read_text(encoding="utf-8")
    open_text, closed_ledger = split_register_sections(text)
    rows = ROW.findall(open_text)
    if not rows:
        print("[HIGH] EMPTY CORPUS — parsed 0 debt rows. Fix the parse; do not read this as "
              "'the register is clean'.")
        return 1

    findings: dict[str, list[dict]] = {k: [] for k in
                                       ("duplicate", "dead_path", "dead_ticket",
                                        "stale_tracking", "resolved_not_deleted",
                                        "unknown_citation", "stale_assertion",
                                        "unmeasurable")}
    seen: dict[str, int] = {}

    for did, body in rows:
        if did in seen:
            findings["duplicate"].append({"id": did, "detail": "declared more than once"})
        seen[did] = seen.get(did, 0) + 1
        if did in closed_ledger:
            findings["duplicate"].append({
                "id": did,
                "detail": f"present in both open table and Closed-Debt Ledger (line {closed_ledger[did]['line']})",
            })

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

    for did, entry in closed_ledger.items():
        if not DATE_RE.match(entry["closed"]):
            findings["dead_ticket"].append(
                {"id": did, "detail": f"Closed-Debt Ledger invalid date '{entry['closed']}'"}
            )
        for t_ in entry["tickets"]:
            if ticket_status(t_) is None:
                findings["dead_ticket"].append(
                    {"id": did, "detail": f"Closed-Debt Ledger ticket {t_} has no ticket file"}
                )

    surfaces, unmeasurable_list = collect_citation_surfaces(ROOT, REGISTER)
    for u in unmeasurable_list:
        findings["unmeasurable"].append({"id": "UNMEASURABLE", "detail": u})

    citations_total = 0
    citations_open = 0
    citations_closed_historical = 0
    for rel, content in surfaces.items():
        is_register = rel.endswith("TECH-DEBT.md")
        for lineno, line in enumerate(content.splitlines(), 1):
            scan_line = line
            if is_register:
                m_row = ROW.match(line)
                if m_row:
                    scan_line = m_row.group(2)
            for m in DEBT_TOKEN.finditer(scan_line):
                did = f"D{m.group(1)}"
                if _is_non_debt_token(did, line):
                    continue
                citations_total += 1
                if did in seen:
                    citations_open += 1
                elif did in closed_ledger:
                    if _is_stale_open_assertion(did, line):
                        findings["stale_assertion"].append({
                            "id": did,
                            "detail": f"{rel}:{lineno} asserts closed debt is open (closed {closed_ledger[did]['closed']} by {closed_ledger[did]['paid_by']})",
                        })
                    else:
                        citations_closed_historical += 1
                else:
                    findings["unknown_citation"].append({
                        "id": did,
                        "detail": f"{rel}:{lineno} has no open row and no Closed-Debt Ledger entry",
                    })

    gating = {k: v for k, v in findings.items() if k != "stale_tracking"}
    total = sum(len(v) for v in gating.values())
    informational = len(findings["stale_tracking"])

    if args.json:
        print(json.dumps({
            "rows": len(rows),
            "closed_ledger_rows": len(closed_ledger),
            "files_scanned": len(surfaces),
            "citations_total": citations_total,
            "citations_open": citations_open,
            "citations_closed_historical": citations_closed_historical,
            "citations_unknown": len(findings["unknown_citation"]),
            "citations_stale": len(findings["stale_assertion"]),
            "unmeasurable_surfaces": unmeasurable_list,
            "findings": findings,
        }, indent=2))
        return 1 if (total and args.enforce) else 0

    print(
        f"[STEP] tech-debt register ↔ reality · {len(rows)} row(s) + {len(closed_ledger)} closed-ledger row(s) "
        f"in {REGISTER.name} · {len(surfaces)} file(s) scanned · {citations_total} citation(s) resolved "
        f"({citations_open} open, {citations_closed_historical} historical-closed)\n"
    )

    labels = {
        "duplicate": ("[HIGH]", "DUPLICATE ID"),
        "dead_path": ("[WARN]", "DEAD PATH — cites a missing file, and does NOT say it was removed"),
        "dead_ticket": ("[HIGH]", "DEAD TICKET — referenced ticket has no file"),
        "stale_tracking": ("[INFO]", "UNOWNED — no LIVE ticket in the Tracked cell (informational: "
                                    "the column has no grammar, see the module docstring)"),
        "resolved_not_deleted": ("[WARN]", "RESOLVED, NOT DELETED"),
        "unknown_citation": ("[HIGH]", "UNKNOWN CITATION — cited D## has no open row and no Closed-Debt Ledger entry"),
        "stale_assertion": ("[HIGH]", "STALE OPEN ASSERTION — cites closed D## as still open/tracked"),
        "unmeasurable": ("[HIGH]", "UNMEASURABLE — required citation surface missing or unreadable"),
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
