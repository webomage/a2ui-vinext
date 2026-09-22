#!/usr/bin/env python3
"""T228 AC8 — measure TASKS.md against its declared bound, the way T174 bounds STATE.md.

TASKS.md is the traced queue and had **no declared bound** while STATE.md has had one since T174.
Measured 2026-08-20 it is 512,655 bytes, of which 231 ticket rows are 95%.

🔑 The file does not grow by gaining rows. It grows by rows becoming essays — median row 1,420 B,
longest 16,415 B, one row alone 3% of the file. A whole-file bound can be satisfied while single
rows keep swelling, which is why `max_row_bytes` exists here and has no equivalent in STATE.md's
model.

⚠️ **Reports; never edits.** T174's first rotation caught a section that was the only standing
record of a live security gap. A long row is often long because it carries a finding nothing else
records, so this prints and exits — rotation stays a deliberate act with a disposition record.

Exit 0 within bounds · 1 over (with `--enforce`) · 2 when it cannot measure.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "wom7web"
# ⚠️ `[a-c]?` matters: the original `T\d+` missed T16a/T16b/T16c, so this reported 236 rows where
# the board has 239 — a matcher under-counting within its own stated scope (T243).
ROW = re.compile(r"^\| \[T\d+[a-c]?\]")
#: A row is `|id|prio|task|repos|ref|status|` — SIX cells, terminated. T243: eight rows drifted off
#: that shape and no gate saw it, because this file measured bytes and rows but never COLUMNS, and
#: the ranked boards are built from the ticket FILES rather than these rows. So the board of record
#: was the one surface with no validator. 🔬 Splitting on " | " is faithful here (round-trip
#: verified on all 239 rows), but a literal " | " inside prose inflates the count — which is exactly
#: how T243's own row broke on the day it was filed.
EXPECTED_COLS = 6
PY_MARK = None


def malformed_rows(rows: list[str]) -> list[str]:
    """Rows that are not `EXPECTED_COLS` terminated cells. Extracted so it can be PROVEN to reject
    (T243 AC3) — the shape check lived inline in main() first, where the only way to exercise it was
    to corrupt the real TASKS.md."""
    out: list[str] = []
    for r in rows:
        raw = r.rstrip()
        cols = raw.split(" | ")
        tid = (re.match(r"^\| \[(T\d+[a-c]?)\]", raw) or [None, "?"])[1]
        if len(cols) != EXPECTED_COLS or not raw.endswith("|"):
            out.append(f"{tid}: {len(cols)} cell(s), terminated={raw.endswith('|')}")
    return out


# ── T250: the row and the ticket must not disagree about status ───────────────────────────────
#
# `CLAUDE.md` designates the T-row as **status-of-record**, and measured 2026-08-22 the row and the
# ticket's own `status:` disagreed on **8 tickets** — 7 on the axis that matters. The two surfaces
# are written in the same commit by convention and by nothing else, and convention is not a gate.
# [[T243]] built status ↔ **ACs**; this is its missing sibling, status ↔ **row**.
#
# 🔑 **The mapping has to be DECLARED, because the glyphs are not all statuses.** ✅ 🟡 🟢 ⚪ 🔵 read
# as state; 🔴 is *emphasis* (a P0 row leads with it and then says `queued`). A gate cannot make
# that judgement, so it is written down here and the leading token — nothing later in the cell — is
# what counts. Everything after the declaration is prose.
# 💤/⏸️ were MISSING from the first mapping and the unmappable bucket is what surfaced them —
# T18 (`💤 P2`) and T183 (`💤 ⏸️ **PAUSED …**`) both sit over tickets that really are `paused`. That
# is the bucket earning its place: a row the gate cannot read is not a row that agrees, so printing
# them rather than skipping them turned two silent passes into a corrected mapping.
STATUS_GLYPH = {"✅": "done", "🔵": "blocked", "⚪": "queued", "🟡": "in-progress",
                "🟢": "in-progress", "💤": "paused", "⏸️": "paused",
                # T257 AC2 — the TEXT form, read alongside the glyphs. ⚠️ READER ONLY: this makes a
                # bracketed row legible, it does not convert TASKS.md. That conversion changes the
                # board's ROW FORMAT rather than a print statement, which is why T257 sequences it
                # last — and why teaching the reader first is what makes it safe to attempt at all.
                # Longest first matters here as it does for STATUS_WORDS: `[IN-PROGRESS]` must be
                # tried before any shorter key that prefixes it.
                "[IN-PROGRESS]": "in-progress", "[BLOCKED]": "blocked", "[QUEUED]": "queued",
                "[PAUSED]": "paused", "[DONE]": "done"}
#: Longest first: `in-progress` must win over a prefix match on `in`.
STATUS_WORDS = ("in-progress", "queued", "blocked", "paused", "done")
#: 🔴 carries no state of its own. It is accepted as a lead-in so the word after it can be read.
EMPHASIS = ("🔴", "[P0]")


def row_claim(cell: str) -> tuple[str | None, str]:
    """What state the row's Status cell CLAIMS, and how that was decided.

    Returns `(None, why)` when the cell does not open with anything mappable — reported, never
    guessed at. Four refinements, each forced by real data rather than foresight:

      1. the leading glyph alone → too coarse: `🔴 queued` is a P0 marker over a queued ticket, and
         reading 🔴 as a state loses the word that follows it;
      2. so an explicit status WORD after the glyph wins, being more specific — that cleared two
         rows written the same day in the `🟡 queued` form;
      3. but a bare word match is too loose: `🟡 done via prettier, oxfmt pending` is a SENTENCE
         about partial work, and reading `done` out of it invented a finding. A declaration ends at
         the word; an alphanumeric right after it means prose, so fall back to the glyph;
      4. and the cell is split off the row with `" | "`, the splitter `malformed_rows` already
         round-trips, NOT a bare `|` — cells legitimately contain `||` and escaped pipes, and a
         bare split reported 11 rows as broken that are fine.
    """
    t = cell.lstrip()
    # Longest first: with text markers in the table, a shorter key must never shadow a longer one
    # that also matches (the same rule STATUS_WORDS documents for `in-progress` over `in`).
    lead = next((g for g in sorted(list(STATUS_GLYPH) + list(EMPHASIS), key=len, reverse=True)
                 if t.startswith(g)), None)
    if lead is None:
        return None, "no leading status glyph"
    rest = t[len(lead):].lstrip()
    low = rest.lower()
    for w in STATUS_WORDS:
        if low.startswith(w):
            after = rest[len(w):]
            if not after.strip() or not after.lstrip()[:1].isalnum():
                return w, f"{lead} + `{w}`"
            break  # prose, not a declaration
    return STATUS_GLYPH.get(lead), f"{lead} alone"


def row_status_cells(rows: list[str]) -> dict[str, str]:
    """ticket id -> its Status cell, for well-shaped rows only.

    A malformed row is skipped here rather than mis-read: `malformed_rows` already reports it, and
    reading column 5 of a row that has seven cells is how a checker invents findings.
    """
    out: dict[str, str] = {}
    for r in rows:
        raw = r.rstrip()
        cols = raw.split(" | ")
        m = re.match(r"^\| \[(T\d+[a-c]?)\]", raw)
        if m and len(cols) == EXPECTED_COLS and m.group(1) not in out:
            out[m.group(1)] = cols[5].rstrip("|").strip()
    return out


def status_disagreements(
    cells: dict[str, str], tickets: Path
) -> tuple[list[str], list[str], list[str]]:
    """(hard, soft, unmappable) — three buckets, deliberately different tiers.

    🔴 **hard** is the done axis ONLY: a row claiming done over a ticket that is not `done`, or a
    `done` ticket whose row does not say so. Binary, decidable, and it is where the damage is — a
    ✅ over an open ticket means anyone reading the queue to pick work SKIPS it.
    ⚠️ **soft** is queued-vs-in-progress-vs-blocked. Real drift, but the distinction is genuinely
    soft in prose and 8 reds at once teach people to route around the aggregate ([[T135]] AC8), so
    it reports and does not block.
    ⚪ **unmappable** is printed rather than skipped silently — a row the gate cannot read is not a
    row that agrees.
    """
    hard: list[str] = []
    soft: list[str] = []
    unmappable: list[str] = []
    for tid, cell in sorted(cells.items()):
        f = tickets / f"{tid}.md"
        if not f.is_file():
            continue
        m = re.search(r"^status: *(\S+)", f.read_text(encoding="utf-8", errors="replace"), re.M)
        if not m:
            continue
        actual = m.group(1)
        claim, how = row_claim(cell)
        if claim is None:
            unmappable.append(f"{tid}: {how} — {cell[:52]!r}")
        elif (claim == "done") != (actual == "done"):
            hard.append(f"{tid}: ticket `{actual}`, row claims `{claim}` ({how})")
        elif claim != actual:
            soft.append(f"{tid}: ticket `{actual}`, row claims `{claim}` ({how})")
    return hard, soft, unmappable


def truth_exit(malformed: list[str], hard: list[str]) -> int:
    """Non-zero when a row is WRONG, regardless of `--enforce`. Budgets are not the same thing.

    🔑 **T250 AC4 — this is the tier decision, written down rather than implied.** The byte budget
    here is deliberately set BELOW the file's current size (409,600 against ~580,000), because a
    bound placed just above the present state declares the present state normal. It is therefore
    **permanently red on purpose**, and `--enforce` returns 1 on it — so routing a status
    contradiction through `--enforce` would gate every push on a target nobody intends to meet
    today, and the estate's answer to a permanently-red blocking gate is that people learn to route
    around the aggregate ([[T135]] AC8).

    So the two verdicts separate:

      · **budgets** — advisory unless `--enforce`. A long row is often long because it carries a
        finding nothing else records ([[T174]]'s first rotation caught exactly that).
      · **truth** — a row that is not six terminated cells, or that contradicts its own ticket
        about `done`, is simply WRONG. Not a target, not a judgement call, nothing to grow into.

    ⇒ **Where it runs, explicitly** (AC4 asked, and *"a `-check` recipe nobody calls"* is [[T195]]'s
    blind spot): `just tasks-bounds` is declared as `.w0m/sdlc.json → tasks_surface.check` and
    registered in `project/test-suites.json` at tier `offline` with **no `blocking: false`** — and
    `run_suites.py:80` defaults `blocking` to **True**. So `just suites` already treats it as
    blocking and, from here on, a status contradiction fails it while a byte overage does not.
    ⚠️ This PROMOTES the shape check, which was written *"advisory until promoted"*. Safe to promote
    now and stated rather than slipped in: shape is at **0** findings, so nothing turns red today.
    """
    return 1 if (malformed or hard) else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--enforce", action="store_true")
    a = ap.parse_args()

    cfg = ROOT / ".w0m" / "sdlc.json"
    if not cfg.exists():
        print(f"  ❌ no {cfg} — nothing declares a bound, so nothing can be measured against one.")
        return 2
    surface = json.loads(cfg.read_text(encoding="utf-8")).get("tasks_surface") or {}
    ret = surface.get("retention") or {}
    if not ret:
        print("  ❌ `.w0m/sdlc.json → tasks_surface.retention` is absent — an unbounded file cannot "
              "be reported as growing. That absence IS the finding T177 recorded.")
        return 2

    f = ROOT / surface.get("file", "TASKS.md")
    if not f.exists():
        print(f"  ❌ {f} not found."); return 2
    text = f.read_text(encoding="utf-8", errors="replace")
    lines = text.split("\n")
    rows = [l for l in lines if ROW.match(l)]
    if not rows:
        print("  ❌ 0 ticket rows parsed — the matcher is broken, not the queue empty.")
        return 2

    # ── row SHAPE (T243) ─────────────────────────────────────────────────────
    malformed = malformed_rows(rows)
    if malformed:
        print(f"  🔴 {len(malformed)} row(s) are not {EXPECTED_COLS} terminated cells:")
        for m in malformed[:12]:
            print(f"      {m}")
        if len(malformed) > 12:
            print(f"      … and {len(malformed) - 12} more")
        print("     A 7th cell is status prose appended beside the marker; a missing final `|`")
        print("     leaves the last cell unterminated. Neither loses text — both break the shape.")
    else:
        print(f"  ✓ shape       all {len(rows)} row(s) are {EXPECTED_COLS} terminated cells")

    # ── row TRUTH (T250) — does the row agree with the ticket about status? ───
    cells = row_status_cells(rows)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import tasks_query as tq
    tickets_dir = tq.resolve_tickets_dir()
    hard, soft, unmappable = status_disagreements(cells, tickets_dir)
    if not cells:
        # An empty corpus must fail rather than vacuously pass: "0 disagreements of 0" is not
        # evidence the queue is honest (T240).
        print("  ❌ 0 status cells parsed from the rows — the reader is broken, not the queue clean.")
        return 2
    if hard:
        print(f"  🔴 {len(hard)} row(s) disagree with their ticket about DONE, of {len(cells)}:")
        for h in hard:
            print(f"      {h}")
        print("     A ✅ over an open ticket is a FALSE GREEN on the surface CLAUDE.md calls")
        print("     status-of-record — anyone reading the queue to pick work skips it. Resolve by")
        print("     reading the ticket; the direction is NOT uniform.")
    else:
        print(f"  ✓ done axis   all {len(cells)} row(s) agree with their ticket about `done`")
    if soft:
        print(f"  ⚪ {len(soft)} row(s) differ on queued/in-progress/blocked (reported, not blocking):")
        for sft in soft[:8]:
            print(f"      {sft}")
        if len(soft) > 8:
            print(f"      … and {len(soft) - 8} more")
    if unmappable:
        print(f"  ⚪ {len(unmappable)} row(s) open with nothing the declared mapping reads:")
        for u in unmappable[:6]:
            print(f"      {u}")
        if len(unmappable) > 6:
            print(f"      … and {len(unmappable) - 6} more")

    over: list[str] = []
    # 🔴 BYTES MEANS BYTES. This read `len(text)` until 2026-08-27, which is CHARACTERS -- and
    # TASKS.md is emoji-dense, so the gate under-reported itself by ~2% (650,227 vs 663,867) and
    # three rows that exceed the byte bound were invisible to it. The bound is declared
    # `max_bytes`/`max_row_bytes` and printed with a `B`; measuring code points while saying bytes
    # is the estate's recurring defect, found here in the gate that measures the bound.
    checks = [("bytes", len(text.encode("utf-8")), ret.get("max_bytes")),
              ("lines", len(lines), ret.get("max_lines"))]
    print(f"  ▶ tasks-bounds — {f.name}: {len(rows)} ticket row(s)")
    for label, actual, limit in checks:
        if not limit:
            continue
        pct = 100 * actual // limit
        mark = "✓" if actual <= limit else "🔴"
        print(f"      {mark} {label:<6} {actual:>9,} / {limit:>9,}  ({pct}%)")
        if actual > limit:
            over.append(f"{label} {actual:,} > {limit:,}")

    rmax = ret.get("max_row_bytes")
    if rmax:
        fat = sorted(((len(r.encode("utf-8")), r) for r in rows
                      if len(r.encode("utf-8")) > rmax), reverse=True)
        pct_rows = 100 * len(fat) // len(rows)
        mark = "✓" if not fat else "🔴"
        print(f"      {mark} rows over {rmax:,} B: {len(fat)} of {len(rows)} ({pct_rows}%)")
        for n, r in fat[:5]:
            tid = (re.match(r"^\| \[(T\d+)\]", r) or [None, "?"])[1]
            print(f"          {tid:<6} {n:>7,} B")
        if len(fat) > 5:
            print(f"          … and {len(fat)-5} more")
        if fat:
            over.append(f"{len(fat)} row(s) over {rmax:,} B")

    if not over:
        print("\n  ✅ within every declared bound.")
        return truth_exit(malformed, hard)
    print(f"\n  🔴 over on {len(over)}: {'; '.join(over)}")
    print(" [WARN] This REPORTS. Rotation is a deliberate act with a disposition record — a long row is")
    print("     often long because it holds a finding nothing else records (T174's first run caught")
    print("     a section that was the only standing record of a live security gap).")
    # Shape is a HARD finding, not a budget: bytes/rows are a target to grow into, but a malformed
    # row is simply wrong. It still respects --enforce, so the gate is advisory until promoted.
    # Budgets respect --enforce; truth does not. See truth_exit.
    return truth_exit(malformed, hard) or (1 if a.enforce else 0)


if __name__ == "__main__":
    sys.exit(main())
