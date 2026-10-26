#!/usr/bin/env python3
"""Epic completeness (T135, T355 AC3/AC4): canonical 3-level `<tag1>_<tag2>_<tag3>` epic gate.

Parses the canonical 3-level tag off each `## N. Title \\`tag\\`` header in `ROADMAP.md` and
validates every ticket's `epic:` field in `.tasks/T*.md` against those canonical header tags.

Two directions, because only one of them is usually checked:
  ticket → canonical tag   a ticket with no `epic:` or an `epic:` not on any ROADMAP.md header
  section → ticket         a ROADMAP section whose canonical tag has no open ticket carrying it

GATED (T355 AC4): exits 1 on any untagged ROADMAP header, ticket missing `epic:`, ticket with a
non-canonical/dangling `epic:`, or multiple raw `epic:` spellings for one section.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from tasks_query import resolve_tickets_dir  # noqa: E402 — canonical .tasks/ resolver (T411)

TICKETS = resolve_tickets_dir()
ROADMAP = ROOT / "ROADMAP.md"

HEADER_WITH_TAG_RE = re.compile(
    r"^##\s+(?:\S+\s+)?(\d+)\.\s+(.*?)\s+`([a-z0-9]+_[a-z0-9]+_[a-z0-9_]+)`\s*$"
)
HEADER_ANY_RE = re.compile(r"^##\s+(?:\S+\s+)?(\d+)\.\s+(.*)$")
LEGEND = re.compile(r"\s*#\s*queued\s*\|.*$")
OPEN_STATUSES = {"queued", "in-progress", "blocked", "paused"}


def parse_roadmap_headers(
    roadmap_path: Path | None = None,
) -> tuple[dict[str, dict[str, str]], list[tuple[str, str]], list[str]]:
    """Parse `## N. Title \\`tag\\`` headers from ROADMAP.md.

    Returns:
      - `by_tag`: `{canonical_tag: {"section": sec_num, "title": title}}`
      - `untagged`: `[(sec_num, raw_title)]` for any numbered `## N.` header missing a 3-level `` `tag` ``
      - `duplicate_tags`: list of error strings if two sections share the same tag
    """
    target = roadmap_path or ROADMAP
    by_tag: dict[str, dict[str, str]] = {}
    untagged: list[tuple[str, str]] = []
    duplicate_tags: list[str] = []
    if not target.is_file():
        return by_tag, untagged, [f"ROADMAP.md not found at {target}"]

    for line in target.read_text(encoding="utf-8", errors="replace").splitlines():
        m_tag = HEADER_WITH_TAG_RE.match(line)
        if m_tag:
            sec, title, tag = m_tag.group(1), m_tag.group(2).strip(), m_tag.group(3).strip()
            if tag in by_tag:
                prev_sec = by_tag[tag]["section"]
                duplicate_tags.append(
                    f"duplicate canonical tag `{tag}` on ROADMAP §{prev_sec} and §{sec}"
                )
            by_tag[tag] = {"section": sec, "title": title}
            continue
        m_any = HEADER_ANY_RE.match(line)
        if m_any:
            untagged.append((m_any.group(1), m_any.group(2).strip()))

    return by_tag, untagged, duplicate_tags


def _parse_ticket_frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    fm = parts[1]
    t: dict[str, str] = {}
    for line in fm.splitlines():
        if ":" in line and not line.startswith(" "):
            k, _, v = line.partition(":")
            key = k.strip()
            v = LEGEND.sub("", v)
            v = re.sub(r"\s+#.*$", "", v)
            t[key] = v.strip().strip('"').strip("'")
    return t


def tnum(tid: str) -> tuple[int, str]:
    m = re.match(r"T(\d+)(.*)", tid)
    return (int(m.group(1)), m.group(2)) if m else (10**6, tid)


def check_epic_completeness(
    tickets_dir: Path | None = None,
    roadmap_path: Path | None = None,
) -> tuple[list[str], dict[str, Any]]:
    """Validate all tickets in `tickets_dir` against canonical 3-level tags on `roadmap_path` headers.

    Returns `(errors, details)` where `errors` is non-empty on any schema/completeness violation.
    """
    tdir = tickets_dir or TICKETS
    rm_path = roadmap_path or ROADMAP
    by_tag, untagged, duplicate_tags = parse_roadmap_headers(rm_path)

    tickets: dict[str, dict[str, str]] = {}
    for f in sorted(tdir.glob("T*.md")):
        t = _parse_ticket_frontmatter(f)
        if not t:
            continue
        tickets[t.get("id", f.stem)] = t

    open_t = {k: v for k, v in tickets.items() if v.get("status") in OPEN_STATUSES}

    by_sect_open: dict[str, list[str]] = defaultdict(list)
    by_sect_all: dict[str, list[str]] = defaultdict(list)
    no_epic_all: list[str] = []
    no_epic_open: list[str] = []
    non_canonical_all: dict[str, list[str]] = defaultdict(list)
    non_canonical_open: dict[str, list[str]] = defaultdict(list)
    dangling_all: dict[str, list[str]] = defaultdict(list)
    raw_variants: dict[str, set[str]] = defaultdict(set)

    for tid, t in sorted(tickets.items(), key=lambda x: tnum(x[0])):
        epic = t.get("epic", "").strip()
        is_open = tid in open_t
        if not epic:
            no_epic_all.append(tid)
            if is_open:
                no_epic_open.append(tid)
            continue
        if epic in by_tag:
            sec = by_tag[epic]["section"]
            raw_variants[sec].add(epic)
            by_sect_all[epic].append(tid)
            if is_open:
                by_sect_open[epic].append(tid)
        else:
            m_sec = re.search(r"§\s*(\d+)", epic)
            if m_sec:
                sec = m_sec.group(1)
                raw_variants[sec].add(epic)
                if not any(info["section"] == sec for info in by_tag.values()):
                    dangling_all[sec].append(tid)
            non_canonical_all[epic].append(tid)
            if is_open:
                non_canonical_open[epic].append(tid)

    multi = {s: sorted(v) for s, v in raw_variants.items() if len(v) > 1}

    errors: list[str] = []
    if not by_tag:
        errors.append(f"EPIC COMPLETENESS: 0 canonical 3-level tags parsed from {rm_path}")
    for sec, title in untagged:
        errors.append(
            f"EPIC COMPLETENESS: ROADMAP §{sec} ({title[:50]}) is missing a trailing canonical `<tag1>_<tag2>_<tag3>` marker"
        )
    errors.extend(f"EPIC COMPLETENESS: {d}" for d in duplicate_tags)
    if no_epic_all:
        errors.append(
            f"EPIC COMPLETENESS: {len(no_epic_all)} ticket(s) carry empty `epic:` ({', '.join(no_epic_all[:10])})"
        )
    for bad_epic, ids in sorted(non_canonical_all.items(), key=lambda kv: -len(kv[1])):
        errors.append(
            f"EPIC COMPLETENESS: `epic: {bad_epic!r}` on {', '.join(ids[:8])} is not a canonical 3-level tag on any ROADMAP.md header"
        )
    for sec, vs in sorted(multi.items(), key=lambda kv: int(kv[0])):
        errors.append(
            f"EPIC COMPLETENESS: ROADMAP §{sec} has {len(vs)} inconsistent `epic:` spellings: {vs}"
        )

    details: dict[str, Any] = {
        "total_tickets": len(tickets),
        "open_tickets": len(open_t),
        "canonical_tags": by_tag,
        "untagged_sections": untagged,
        "no_epic_all": no_epic_all,
        "no_epic_open": no_epic_open,
        "non_canonical_all": dict(non_canonical_all),
        "non_canonical_open": dict(non_canonical_open),
        "dangling_all": dict(dangling_all),
        "multi": multi,
        "by_sect_open": dict(by_sect_open),
        "by_sect_all": dict(by_sect_all),
    }
    return errors, details


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="Emit machine-readable JSON report")
    ap.add_argument(
        "--advisory",
        action="store_true",
        help="Print report and exit 0 even when drift is present (default is gating/blocking per T355 AC4)",
    )
    args = ap.parse_args(argv)

    errors, details = check_epic_completeness()
    by_tag: dict[str, dict[str, str]] = details["canonical_tags"]
    open_n: int = details["open_tickets"]
    total_n: int = details["total_tickets"]
    no_epic_all: list[str] = details["no_epic_all"]
    non_canonical_all: dict[str, list[str]] = details["non_canonical_all"]
    dangling_all: dict[str, list[str]] = details["dangling_all"]
    multi: dict[str, list[str]] = details["multi"]
    by_sect_open: dict[str, list[str]] = details["by_sect_open"]

    if args.json:
        print(json.dumps({"ok": not errors, "errors": errors, **details}, indent=2))
        return 0 if (args.advisory or not errors) else 1

    print(
        f"[EPIC COMPLETENESS] {open_n} open of {total_n} tickets · "
        f"{len(by_tag)} canonical 3-level ROADMAP tags\n"
    )

    print("── ticket → canonical tag (all tickets, gated per T355 AC3/AC4) ──")
    print(
        f"  {len(no_epic_all):3} ticket(s) carry NO epic at all "
        f"({len(no_epic_all) * 100 // max(total_n, 1)}% of the corpus)"
    )
    print(
        f"  {sum(len(v) for v in non_canonical_all.values()):3} carry an epic that is NOT a canonical ROADMAP header tag "
        f"({len(non_canonical_all)} distinct strings)"
    )
    print(
        f"  {sum(len(v) for v in dangling_all.values()):3} [ERR] point at a § that DOES NOT EXIST in ROADMAP.md"
    )
    for s, ids in sorted(dangling_all.items(), key=lambda x: int(x[0])):
        print(f"        §{s}: {' '.join(ids)}")
    if non_canonical_all:
        print("\n  non-canonical epic strings (rejected by gate):")
        for e, ids in sorted(non_canonical_all.items(), key=lambda x: -len(x[1])):
            print(f"    {len(ids):2} · {e[:64]:66} {' '.join(ids[:6])}")

    print("\n── inconsistent raw strings for one section ──")
    print(f"  {len(multi)} section(s) are written more than one way:")
    for s, vs in sorted(multi.items(), key=lambda x: -len(x[1]))[:8]:
        print(f"    §{s} ({len(vs)} spellings)")
        for v in sorted(vs):
            print(f"         {v[:88]}")

    print("\n── section → ticket (the direction nobody checks) ──")
    empty = [
        (tag, info["section"], info["title"])
        for tag, info in sorted(by_tag.items(), key=lambda kv: int(kv[1]["section"]))
        if tag not in by_sect_open
    ]
    print(f"  {len(empty)} of {len(by_tag)} ROADMAP sections have NO open ticket:")
    for tag, s, name in empty:
        flag = "  [OK] decommissioned" if "DECOMMISSION" in name.upper() else ""
        print(f"    §{s:<3} {tag:<32} {name[:48]}{flag}")

    print("\n── the sections that DO carry open work ──")
    for tag, ids in sorted(by_sect_open.items(), key=lambda x: -len(x[1])):
        info = by_tag.get(tag, {"section": "?", "title": "[ERR] NO SUCH TAG"})
        s = info["section"]
        name = info["title"]
        print(
            f"  §{s:<3} {tag:<32} {len(ids):3} open · {name[:38]:40} {' '.join(ids[:6])}"
            + (" …" if len(ids) > 6 else "")
        )

    if errors:
        print(f"\n[FAIL] EPIC COMPLETENESS GATE FAILED ({len(errors)} error(s)):", file=sys.stderr)
        for err in errors[:15]:
            print(f"  · {err}", file=sys.stderr)
        return 0 if args.advisory else 1

    print("\n[OK] All tickets carry canonical 3-level ROADMAP epic tags (0 drift)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
