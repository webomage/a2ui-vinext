#!/usr/bin/env python3
"""T33 — enforce `openspec/SPEC-AUTHORING-STANDARD.md` mechanically.

WHY THIS EXISTS
    The standard shipped 2026-07-13 (T33 AC1) and then nothing checked it. AC3 said "applied to
    all new changes by default", which in practice meant "an agent might remember". Measured
    2026-08-02: across the three P1 specs AC2 names, **18 requirements carried exactly 1 Feature
    block**. A standard nothing verifies is a document, not a standard.

WHAT IT CHECKS
    Per `### Requirement:` block, the four things the standard actually mandates:
      · **Feature:**            — the wider context, who it serves, non-goals
      · #### Scenario:          — at least one; the standard asks for happy path + failure
      · **Acceptance criteria** — binary and testable, the per-requirement definition of done
      · **Verify with**         — the skills that prove it

    Deliberately shallow: presence, not quality. A checker cannot judge whether a Feature
    paragraph is any good, and pretending otherwise would be the vacuous-gate trap in a new
    costume. It catches the block being *absent*, which is the actual failure mode here.

RATCHET, NOT A CLIFF
    25 spec files across 18 active changes predate the standard. Failing on all of them would
    make the gate un-runnable and it would be disabled within a day. So the baseline records
    today's non-conforming count: it may SHRINK freely, and any INCREASE fails. New specs must
    conform; old ones get paid down by [[T33]] AC2 and by whoever next touches them.

SCOPE
    Active changes only — `openspec/changes/*/specs/**/*.md`, excluding `archive/`. Archived
    changes are history; rewriting them would be churn with no reader.

Run: `just spec-standard-check`   ·   rebaseline: `--write-baseline`
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "w0m-web"
# Overridable so the gate can be proven RED against a FIXTURE estate. Planting a deliberately
# malformed requirement in a real spec would mean committing the defect the gate exists to catch.
_root = os.environ.get("W0M_SPEC_ROOT")
CHANGES = Path(_root) if _root else WEB / "openspec" / "changes"
BASELINE = (CHANGES.parent / "spec-standard-baseline.json") if _root else \
    WEB / "project" / "spec-standard-baseline.json"

REQ = re.compile(r"^###\s+Requirement:\s*(.+?)\s*$", re.M)
CHECKS = {
    "Feature": re.compile(r"^\*\*Feature:\*\*", re.M),
    "Scenario": re.compile(r"^####\s+Scenario:", re.M),
    "Acceptance criteria": re.compile(r"^\*\*Acceptance criteria\*\*", re.M),
    "Verify with": re.compile(r"^\*\*Verify with\*\*", re.M),
}


def spec_files() -> list[Path]:
    if not CHANGES.is_dir():
        return []
    return sorted(
        p for p in CHANGES.glob("*/specs/**/*.md")
        if "archive" not in p.relative_to(CHANGES).parts
    )


def requirements(text: str) -> list[tuple[str, str]]:
    """Split into (name, body) per `### Requirement:` — body runs to the next h3+ or EOF."""
    out = []
    marks = list(REQ.finditer(text))
    for i, m in enumerate(marks):
        start = m.end()
        # Stop at the next requirement, or any heading of level <= 3 (a new section).
        nxt = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        sect = re.search(r"^#{1,3}\s+(?!#)", text[start:nxt], re.M)
        end = start + sect.start() if sect else nxt
        out.append((m.group(1), text[start:end]))
    return out


def audit() -> tuple[list[dict], int, int]:
    findings, total = [], 0
    for f in spec_files():
        text = f.read_text(errors="ignore")
        for name, body in requirements(text):
            total += 1
            missing = [k for k, rx in CHECKS.items() if not rx.search(body)]
            if missing:
                # Report repo-relative when the file is inside the repo; fall back to
                # corpus-relative otherwise. A hard `relative_to(WEB)` raises the moment the
                # corpus is overridden — which is every fixture run, so the gate crashed rather
                # than reported. Found by test_spec_standard.py on its first execution.
                try:
                    shown = f.relative_to(WEB)
                except ValueError:
                    shown = f.relative_to(CHANGES)
                findings.append({
                    "file": str(shown), "requirement": name, "missing": missing,
                })
    return findings, total, len(findings)


def main() -> int:
    ap = argparse.ArgumentParser(description="Spec-authoring standard gate (T33)")
    ap.add_argument("--write-baseline", action="store_true",
                    help="record today's non-conforming count as the ceiling")
    ap.add_argument("--verbose", action="store_true", help="list every non-conforming requirement")
    args = ap.parse_args()

    files = spec_files()
    findings, total, bad = audit()

    print(f"\n▶ spec-standard — {len(files)} active spec file(s), {total} requirement(s)")

    # An empty corpus must FAIL. A gate that reports "0 offenders" because it looked in the wrong
    # place is the defect this estate keeps re-finding; silence here would read as compliance.
    if not files or total == 0:
        print("❌ NO requirements found — the corpus is empty, which is a broken glob, not a "
              "clean estate. Refusing to report a pass.")
        return 2

    conforming = total - bad
    print(f"  conforming: {conforming}/{total}   non-conforming: {bad}")

    if args.verbose and findings:
        print("\n── non-conforming ──")
        for f in findings:
            print(f"  · {f['file']}")
            print(f"      {f['requirement']} — missing: {', '.join(f['missing'])}")

    if args.write_baseline:
        BASELINE.write_text(json.dumps({
            "_comment": "T33 AC3 ratchet ceiling: non-conforming requirements in ACTIVE openspec "
                        "changes. It may SHRINK freely; any increase fails the gate. Do NOT raise "
                        "it to unblock a push — that converts the ratchet into a rubber stamp. "
                        "Retrofit the requirement instead (SPEC-AUTHORING-STANDARD.md).",
            "non_conforming": bad, "total_requirements": total,
        }, indent=2) + "\n")
        print(f"\n✅ baseline written: {bad} non-conforming of {total}")
        return 0

    if not BASELINE.exists():
        print(f"\n[WARN] no baseline yet — run `just spec-standard-check --write-baseline` once.")
        return 0

    ceiling = json.loads(BASELINE.read_text())["non_conforming"]
    if bad > ceiling:
        print(f"\n❌ non-conforming rose {ceiling} → {bad}. A new or edited requirement is missing "
              f"part of the enriched block.\n   Fix it (openspec/SPEC-AUTHORING-STANDARD.md), or "
              f"see exactly which with `--verbose`.\n   Do NOT re-baseline to get past this.")
        return 1
    if bad < ceiling:
        print(f"\n✅ improved {ceiling} → {bad} — re-baseline to lock the gain in:\n"
              f"   just spec-standard-check --write-baseline")
        return 0
    print(f"\n✅ holding at the {ceiling} pre-standard requirement(s); nothing new slipped in.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
