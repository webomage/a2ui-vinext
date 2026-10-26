#!/usr/bin/env python3
"""Synchronize and validate the canonical epic vocabulary from ROADMAP.md (T239, T380).

Derives the closed epic slug vocabulary in `project/tickets-schema.jsonc` from `ROADMAP.md`
canonical slug declarations (§1–§38 and §13.1–§13.11).

Usage:
    python3 scripts/sync_epic_vocabulary.py --check
    python3 scripts/sync_epic_vocabulary.py --sync
    python3 scripts/sync_epic_vocabulary.py --normalize-tickets
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "wom7web"
ROADMAP = ROOT / "ROADMAP.md"
SCHEMA_FILE = WEB / "project" / "tickets-schema.jsonc"
TICKETS = ROOT / ".tasks"

sys.path.insert(0, str(WEB / "project" / "scripts"))
from authz_blanket_gate import strip_jsonc

# Canonical §13 subsections declared in ROADMAP.md (from the 2026-08-25 split)
SUB13_TITLES: dict[str, str] = {
    "13.1": "Standing health, status & guardrails",
    "13.2": "SDLC skill pipeline + tech-debt tracing in hooks",
    "13.3": "Skills expansion",
    "13.4": "Knowledge-graph engine research",
    "13.5": "Package discovery via MCP",
    "13.6": "The delivery record — ticket, board and tracker must agree",
    "13.7": "Gate integrity — a gate that cannot fail is not a gate",
    "13.8": "Agent substrate — many agents and sandboxes, one estate",
    "13.9": "Governed projects — what it means for a project to be in the estate",
    "13.10": "Toolchain currency — dependencies, runtimes and type safety",
    "13.11": "Platform operations — backups, deploys, migrations and cloud services",
}

def extract_roadmap_titles(roadmap_path: Path = ROADMAP) -> dict[str, str]:
    """Extract titles for all ROADMAP sections directly from ROADMAP.md (T531 AC2)."""
    text = roadmap_path.read_text(encoding="utf-8")
    titles: dict[str, str] = {}

    for line in text.splitlines():
        m = re.match(r"^##\s+(\d+)\.\s+(.*?)(?:\s+\([^\)]+\))?$", line)
        if m:
            sec = m.group(1)
            title = m.group(2).strip()
            title = re.sub(r"\s*\(P\d+.*?\)", "", title).strip()
            titles[sec] = title
            continue

        m_sub = re.match(
            r"^\*\s+\*\*(\d+\.\d+)\s+([^*]+?)\*\*\s*·\s*\*\*Epic slug:\*\*\s*`([^`]+)`",
            line,
        )
        if m_sub:
            titles[m_sub.group(1)] = m_sub.group(2).strip()

    for sub, title in SUB13_TITLES.items():
        titles.setdefault(sub, title)

    return titles


def extract_roadmap_epics(roadmap_path: Path = ROADMAP) -> dict[str, str]:
    """Extract canonical epic slugs for all ROADMAP sections directly from ROADMAP.md (T531 AC2)."""
    text = roadmap_path.read_text(encoding="utf-8")
    slugs: dict[str, str] = {}
    lines = text.splitlines()

    for i, line in enumerate(lines):
        m = re.match(r"^##\s+(\d+)\.", line)
        if m:
            sec = m.group(1)
            for next_line in lines[i + 1 : i + 8]:
                if re.match(r"^##\s+\d+\.", next_line):
                    break
                m_slug = re.search(r">\s*\*\*Epic slug[^*]*\*\*:?\s*`([^`]+)`", next_line)
                if m_slug:
                    slugs[sec] = m_slug.group(1)
                    break

        m_sub = re.match(r"^\*\s+\*\*(\d+\.\d+)\s+.*?\*\*.*?\*\*Epic slug:\*\*\s+`([^`]+)`", line)
        if m_sub:
            slugs[m_sub.group(1)] = m_sub.group(2)

    return dict(sorted(slugs.items(), key=lambda x: [int(p) for p in x[0].split(".")]))


def get_canonical_values() -> list[str]:
    """Return sorted canonical epic slug strings."""
    return sorted(set(extract_roadmap_epics().values()))


def get_epic_aliases() -> dict[str, dict[str, str]]:
    """Known aliases and unrolled spellings mapped to canonical epic slugs (T239 AC2, T380)."""
    slugs = extract_roadmap_epics()
    titles = extract_roadmap_titles()
    aliases: dict[str, dict[str, str]] = {}

    # Bare section spellings and legacy full strings
    for sec, slug in slugs.items():
        aliases[f"ROADMAP §{sec}"] = {
            "to": slug,
            "why": "bare section identifier; canonical form is kebab-case slug",
        }
        aliases[f"§{sec}"] = {
            "to": slug,
            "why": "bare section symbol; canonical form is kebab-case slug",
        }
        if sec in titles:
            if "." in sec:
                aliases[f"ROADMAP §{sec} — Platform Health, Tooling & Knowledge Infrastructure — {titles[sec]}"] = {
                    "to": slug,
                    "why": "legacy verbose subsection title; canonical form is kebab-case slug",
                }
            else:
                aliases[f"ROADMAP §{sec} — {titles[sec]}"] = {
                    "to": slug,
                    "why": "legacy verbose ROADMAP § title; canonical form is kebab-case slug",
                }

    # Historical ad-hoc spellings
    extra_aliases = {
        "security / data exposure": ("19", "historical security theme"),
        "security / RBAC": ("19", "historical security theme"),
        "security / config hygiene": ("19", "historical security theme"),
        "code hygiene / secrets": ("19", "historical security theme"),
        "ROADMAP §security / incident follow-up": ("19", "unanchored security theme"),
        "infrastructure / decommission": ("13", "historical tooling/infra theme"),
        "ROADMAP — design-system program (T42 audit→master→sync-back)": ("26", "design-system program"),
        "ROADMAP §13 — platform tooling": ("13", "ad-hoc section title"),
        "ROADMAP §13 — platform tooling & infra": ("13", "ad-hoc section title"),
        "ROADMAP §13 — SDLC platform": ("13", "ad-hoc section title"),
        "ROADMAP §13 — Platform tooling & internal mechanic": ("13", "ad-hoc section title"),
        "ROADMAP §13.3 — skills platform": ("13.3", "ad-hoc subsection title"),
        "ROADMAP §13.6 — Platform Health, Tooling & Knowledge Infrastructure": ("13.6", "shortened subsection title"),
        "ROADMAP §13.9 — Platform Health, Tooling & Knowledge Infrastructure": ("13.9", "shortened subsection title"),
        "ROADMAP §13.9 — Platform Health, Tooling & Knowledge Infrastructure — Governed projects": ("13.9", "shortened subsection title"),
        "ROADMAP §13.11 — Platform Health, Tooling & Knowledge Infrastructure": ("13.11", "shortened subsection title"),
        "ROADMAP §13.11 — Platform operations — backups, deploys, migrations and cloud services": ("13.11", "shortened subsection title"),
        "ROADMAP §10 (client conversion)": ("10", "parenthetical annotation"),
        "ROADMAP §10 (demo/onboarding)": ("10", "parenthetical annotation"),
        "ROADMAP §12 (MCP-first transport)": ("12", "parenthetical annotation"),
        "ROADMAP §12 (MCP-first transport) & §10 (Client Conversion Funnel, Blueprint Proposals & Unified Contracts)": ("12", "compound epic citation"),
        "ROADMAP §19 (Security, RBAC & Platform Hardening)": ("19", "parenthetical notation"),
        "ROADMAP §19 — Core identity model — candidates, members, clients": ("19", "in-ticket scope title"),
        "ROADMAP §19 — Tenancy, RBAC & Delivery Roles": ("19", "in-ticket scope title"),
        "ROADMAP §21 (Market Research & Business Strategy Continuation)": ("21", "parenthetical notation"),
        "ROADMAP §25 — platform-sync restoration": ("25", "shortened section title"),
        "ROADMAP §30 (wom7sec — audit toolchain, deployable as a service)": ("30", "parenthetical notation"),
        "ROADMAP §33 — client closed beta": ("33", "historical stage name"),
        "ROADMAP §33 (client closed beta)": ("33", "parenthetical historical stage name"),
        "ROADMAP §33 — Client Closed Beta — Full Feature Support, Staged": ("33", "historical stage name"),
        "ROADMAP §34 — Client Beta": ("34", "shortened section title"),
        "ROADMAP §4 — release versioning": ("4", "shortened section title"),
        # Non-existent sub-sections mapped to parent sections
        "ROADMAP §1.4": ("1", "sub-section was never written; rolled up to parent section"),
        "ROADMAP §21.1": ("21", "sub-section was never written; rolled up to parent section"),
        "ROADMAP §21.2": ("21", "sub-section was never written; rolled up to parent section"),
        "ROADMAP §21.3": ("21", "sub-section was never written; rolled up to parent section"),
        "ROADMAP §21.4": ("21", "sub-section was never written; rolled up to parent section"),
        "ROADMAP §22.5": ("22", "sub-section was never written; rolled up to parent section"),
        "ROADMAP §22.6": ("22", "sub-section was never written; rolled up to parent section"),
        "ROADMAP §22.7": ("22", "sub-section was never written; rolled up to parent section"),
        "ROADMAP §22.8": ("22", "sub-section was never written; rolled up to parent section"),
        "ROADMAP §23.1": ("23", "sub-section was never written; rolled up to parent section"),
        "ROADMAP §23.2": ("23", "sub-section was never written; rolled up to parent section"),
        "ROADMAP §24.2": ("24", "sub-section was never written; rolled up to parent section"),
        "ROADMAP §24.3": ("24", "sub-section was never written; rolled up to parent section"),
        "ROADMAP §24.4": ("24", "sub-section was never written; rolled up to parent section"),
        "ROADMAP §24.5": ("24", "sub-section was never written; rolled up to parent section"),
    }

    for raw, (sec, why) in extra_aliases.items():
        if sec in slugs:
            aliases[raw] = {"to": slugs[sec], "why": why}

    return aliases


def check_drift() -> list[str]:
    """Verify that `project/tickets-schema.jsonc` matches ROADMAP.md."""
    errs: list[str] = []
    schema = json.loads(strip_jsonc(SCHEMA_FILE.read_text(encoding="utf-8")))
    epic_vocab = schema.get("vocabularies", {}).get("epic", {})

    if not epic_vocab:
        return ["SCHEMA: vocabularies.epic is MISSING from project/tickets-schema.jsonc"]

    declared_values = set(epic_vocab.get("values", []))
    expected_values = set(get_canonical_values())

    missing = sorted(expected_values - declared_values)
    if missing:
        errs.append(f"SCHEMA/ROADMAP DRIFT: tickets-schema.jsonc omits {len(missing)} canonical epics: {missing[:3]}...")

    extra = sorted(declared_values - expected_values)
    if extra:
        errs.append(f"SCHEMA/ROADMAP DRIFT: tickets-schema.jsonc declares {len(extra)} values not in ROADMAP.md: {extra[:3]}...")

    return errs


def normalize_ticket_epics() -> tuple[int, int]:
    """Normalize all tickets in project/tickets/ to canonical epics and tag audit milestones.

    Returns (updated_count, total_count).
    """
    slugs = extract_roadmap_epics()
    aliases = get_epic_aliases()
    canonical_slugs = set(slugs.values())
    updated = 0
    total = 0

    # 10 dated audit tickets (T67-T76)
    audit_tickets = {
        "T67": "19",
        "T68": "19",
        "T69": "13",
        "T70": "13",
        "T71": "13",
        "T72": "15",
        "T73": "13",
        "T74": "13",
        "T75": "13",
        "T76": "13",
    }

    for p in sorted(TICKETS.glob("T*.md")):
        total += 1
        text = p.read_text(encoding="utf-8")
        stem = p.stem

        m_fm = re.match(r"^---\n(.*?)\n---\n", text, re.S)
        if not m_fm:
            continue
        fm_text = m_fm.group(1)

        m_ep = re.search(r"^epic:\s*(.*?)$", fm_text, re.M)
        if not m_ep:
            continue

        raw_val = m_ep.group(1).strip().strip("\"'")
        raw_clean = re.sub(r"\s+#.*$", "", raw_val).strip().strip("\"'")
        if not raw_clean:
            continue

        target_epic = None
        needs_milestone = False

        if stem in audit_tickets and (raw_clean.startswith("Audit 2026-07-17") or "Audit" in raw_clean):
            sec = audit_tickets[stem]
            target_epic = slugs[sec]
            needs_milestone = True
        elif raw_clean in canonical_slugs:
            target_epic = raw_clean
        elif raw_clean in aliases:
            target_epic = aliases[raw_clean]["to"]
        else:
            # Check if it has a section match
            m_s = re.search(r"§\s*(\d+(?:\.\d+)?)", raw_clean)
            if m_s and m_s.group(1) in slugs:
                target_epic = slugs[m_s.group(1)]

        changed = False
        new_fm = fm_text

        if target_epic and target_epic != raw_clean:
            new_fm = re.sub(
                r"^epic:\s*.*?$",
                f'epic: "{target_epic}"',
                new_fm,
                flags=re.M,
            )
            changed = True

        if needs_milestone and "milestone:" not in new_fm:
            # Add milestone after epic
            new_fm = re.sub(
                r"^(epic:\s*.*?)$",
                r'\1\nmilestone: "audit-2026-07-17"',
                new_fm,
                flags=re.M,
            )
            changed = True

        if changed:
            new_text = f"---\n{new_fm}\n---\n" + text[m_fm.end():]
            p.write_text(new_text, encoding="utf-8")
            updated += 1

    return updated, total


def update_schema_file() -> None:
    """Update project/tickets-schema.jsonc with generated epic vocabulary and milestone field."""
    text = SCHEMA_FILE.read_text(encoding="utf-8")

    vocab_marker = '"vocabularies": {'
    vocab_idx = text.find(vocab_marker)
    if vocab_idx == -1:
        raise ValueError("Cannot find 'vocabularies': { in tickets-schema.jsonc")

    fields_part = text[:vocab_idx]
    rest_part = text[vocab_idx:]

    # 1. Update fields: epic and milestone
    if '"milestone":' not in fields_part:
        old_epic_field = '    "epic":     { "required": true,  "type": "string", "allow_empty": true },'
        new_fields = (
            '    "epic":     { "required": true,  "vocabulary": "epic", "allow_empty": true,\n'
            '                  "note": "T239 AC1, T380 — cross-repo functional capability (§N). Canonical semantic kebab-case slugs derived from ROADMAP.md." },\n'
            '    "milestone": { "required": false, "vocabulary": "milestone",\n'
            '                   "note": "T239 AC3b — temporal phase or origin event (orthogonal to functional `epic`). Flat primitive in .w0m/sdlc.json -> milestones. Optional for ticket-side origin milestones (e.g. audit-2026-07-17)." },'
        )
        if old_epic_field in fields_part:
            fields_part = fields_part.replace(old_epic_field, new_fields, 1)

    # 2. Prepare vocabularies.epic
    epic_vocab = {
        "closed": True,
        "generated_from": "ROADMAP.md",
        "allow_empty": True,
        "values": get_canonical_values(),
        "aliases": get_epic_aliases(),
    }
    epic_json = json.dumps(epic_vocab, indent=6, ensure_ascii=False)
    indented_epic = '    "epic": ' + epic_json.replace("\n", "\n    ") + ",\n"

    milestone_vocab = (
        '    "milestone": {\n'
        '      "closed": false,\n'
        '      "source": ".w0m/sdlc.json -> milestones",\n'
        '      "note": "T239 AC3b — declared as a flat list in .w0m/sdlc.json. Membership is either declared (plan-side) or derived (ticket-side origin fact)."\n'
        '    }\n'
    )

    # Check if "epic" already in vocabularies (rest_part)
    if '    "epic": {' in rest_part and '    "milestone": {' in rest_part:
        start_idx = rest_part.find('    "epic": {')
        end_idx = rest_part.find('  },\n\n  // ── the GitHub projection', start_idx)
        if start_idx != -1 and end_idx != -1:
            rest_part = rest_part[:start_idx] + indented_epic + milestone_vocab + rest_part[end_idx:]
    else:
        # Insert after "repo": { ... }
        pattern = re.compile(r'(    "repo":\s*\{.*?"why_open":\s*".*?"\s*\})', re.S)
        m = pattern.search(rest_part)
        if m:
            replacement = m.group(1) + ",\n" + indented_epic + milestone_vocab
            rest_part = rest_part[:m.start()] + replacement + rest_part[m.end():]

    SCHEMA_FILE.write_text(fields_part + rest_part, encoding="utf-8")
    print("Updated project/tickets-schema.jsonc successfully.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync and validate epic vocabulary from ROADMAP.md")
    parser.add_argument("--check", action="store_true", help="Check if schema matches ROADMAP.md")
    parser.add_argument("--sync", action="store_true", help="Update tickets-schema.jsonc from ROADMAP.md")
    parser.add_argument("--normalize-tickets", action="store_true", help="Normalize all ticket epics in project/tickets/")
    args = parser.parse_args()

    if args.sync:
        update_schema_file()
        return 0

    if args.normalize_tickets:
        up, tot = normalize_ticket_epics()
        print(f"Normalized epics across {up} of {tot} tickets.")
        return 0

    if args.check:
        errs = check_drift()
        if errs:
            for e in errs:
                print(f"[ERROR] {e}", file=sys.stderr)
            return 1
        print("OK: tickets-schema.jsonc epic vocabulary matches ROADMAP.md")
        return 0

    print("Use --check, --sync, or --normalize-tickets.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
