#!/usr/bin/env python3
"""lessons_query.py — query, search, and audit earned rules in LESSONS.md.

Implements T232 AC10 (active reading of the lessons register).
Parses theme sections, rule headings, context, generalisations (⇒), and tells (⭐).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Lesson:
    section_num: int
    section_name: str
    title: str
    date_ticket: str
    body: str
    generalisation: str
    tell: str
    line_number: int
    cue: str = ""
    lesson: str = ""
    evidence: str = ""
    confidence: str = "medium"


def _extract_cue(tell: str, title: str) -> str:
    """Derive Harness² 'cue' (trigger symptom) from tell line or fallback to title."""
    if tell:
        cleaned = re.sub(r"^[⭐\s]*(\*\*The tell:?\*\*|The tell:?)\s*", "", tell.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if cleaned:
            return cleaned
    return title


def _extract_lesson_rule(generalisation: str, title: str) -> str:
    """Derive Harness² 'lesson' (actionable rule) from generalisation or title."""
    if generalisation:
        cleaned = re.sub(r"^(⇒|=>)\s*(\*\*The generalisation:?\*\*|\*\*[^*]+\*\*\s*[—-]?)*\s*", "", generalisation.strip())
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if cleaned:
            return f"{title} — {cleaned}" if title.lower() not in cleaned.lower() else cleaned
    return title


def _extract_evidence(date_ticket: str, body: str) -> str:
    """Derive Harness² 'evidence' (commit/test/trajectory proof) from date_ticket + body."""
    parts = []
    if date_ticket:
        parts.append(re.sub(r"^\*\*|\*\*$", "", date_ticket.strip()))
    if body:
        first_line = body.splitlines()[0].strip()
        if first_line:
            parts.append(first_line)
    return " ".join(parts).strip()


def _infer_confidence(date_ticket: str, body: str, generalisation: str) -> str:
    """Infer Harness² confidence ('high' when backed by ticket/gate/test or multi-incident proof)."""
    combined = f"{date_ticket} {body} {generalisation}"
    if re.search(r"\bT\d+\b", combined) or re.search(
        r"\b(gate|check|test|probe|ratchet|twice|three times)\b", combined, flags=re.IGNORECASE
    ):
        return "high"
    return "medium"


def to_harness2_experience(l: Lesson) -> dict[str, str | int]:
    """Export a Lesson record in Harness² Experience Library schema (cue/lesson/evidence/confidence)."""
    return {
        "line_number": l.line_number,
        "section": f"§{l.section_num} {l.section_name}",
        "cue": l.cue or _extract_cue(l.tell, l.title),
        "lesson": l.lesson or _extract_lesson_rule(l.generalisation, l.title),
        "evidence": l.evidence or _extract_evidence(l.date_ticket, l.body),
        "confidence": l.confidence or _infer_confidence(l.date_ticket, l.body, l.generalisation),
    }


def format_harness2_index(lessons: list[Lesson]) -> str:
    """Format a compact cue-indexed summary compatible with Harness² library/INDEX.md."""
    if not lessons:
        return "# Experience Library Index (0 entries)\n"
    out = [f"# Experience Library Index ({len(lessons)} entries)", ""]
    for l in lessons:
        exp = to_harness2_experience(l)
        cue_short = str(exp["cue"])[:110]
        lesson_short = str(exp["lesson"])[:130]
        conf = exp["confidence"]
        out.append(
            f"- [L{l.line_number} §{l.section_num}] **Cue:** {cue_short} → **Lesson:** {lesson_short} *(confidence: {conf})*"
        )
    return "\n".join(out) + "\n"


def find_workspace_root(start_path: Path | None = None) -> Path:
    """Find the workspace root containing .tasks and .w0m/sdlc.json."""
    cur = (start_path or Path(__file__)).resolve()
    for parent in [cur] + list(cur.parents):
        if (parent / ".tasks").is_dir() and (parent / ".w0m").is_dir():
            return parent
        if (parent / ".git").exists() and (parent / "wom7web").is_dir():
            return parent
    return Path(__file__).resolve().parents[1]


def find_lessons_file(start_path: Path | None = None) -> Path:
    """Locate canonical @wom/LESSONS.md at workspace root. Fail fast if missing (AgDR-0025)."""
    root = find_workspace_root(start_path)
    canonical = root / "LESSONS.md"
    if not canonical.is_file():
        raise FileNotFoundError(f"Missing canonical LESSONS.md at {canonical}")
    return canonical


def parse_lessons(lessons_path: Path) -> list[Lesson]:
    """Parse LESSONS.md into structured Lesson records."""
    text = lessons_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    section_re = re.compile(r"^##\s+(\d+)\.\s+(.*)")
    heading_re = re.compile(r"^###\s+(.*)")

    current_section_num = 0
    current_section_name = "Preamble"

    lessons: list[Lesson] = []
    current_title: str | None = None
    current_line: int = 0
    current_block: list[str] = []

    def flush_lesson():
        nonlocal current_title, current_line, current_block
        if not current_title:
            return

        date_ticket = ""
        gen_lines = []
        tell_lines = []
        body_lines = []

        for line in current_block:
            stripped = line.strip()
            if not stripped:
                continue
            if not date_ticket and stripped.startswith("**") and ("**" in stripped[2:]):
                date_ticket = stripped
                continue

            if stripped.startswith("⇒") or stripped.startswith("=>"):
                gen_lines.append(stripped)
            elif stripped.startswith("⭐") or "The tell" in stripped:
                tell_lines.append(stripped)
            else:
                body_lines.append(stripped)

        clean_title = re.sub(r"^[^\w\s`'\"]+", "", current_title).strip()
        body_str = "\n".join(body_lines)
        gen_str = "\n".join(gen_lines)
        tell_str = "\n".join(tell_lines)

        lessons.append(
            Lesson(
                section_num=current_section_num,
                section_name=current_section_name,
                title=clean_title,
                date_ticket=date_ticket,
                body=body_str,
                generalisation=gen_str,
                tell=tell_str,
                line_number=current_line,
                cue=_extract_cue(tell_str, clean_title),
                lesson=_extract_lesson_rule(gen_str, clean_title),
                evidence=_extract_evidence(date_ticket, body_str),
                confidence=_infer_confidence(date_ticket, body_str, gen_str),
            )
        )
        current_title = None
        current_block = []

    for idx, line in enumerate(lines, start=1):
        sec_m = section_re.match(line)
        if sec_m:
            flush_lesson()
            current_section_num = int(sec_m.group(1))
            current_section_name = sec_m.group(2).split("—")[0].strip()
            continue

        head_m = heading_re.match(line)
        if head_m:
            flush_lesson()
            current_title = head_m.group(1).strip()
            current_line = idx
            current_block = []
            continue

        if current_title:
            current_block.append(line)

    flush_lesson()
    return lessons


def filter_lessons(
    lessons: list[Lesson],
    query: str | None = None,
    section: str | None = None,
) -> list[Lesson]:
    """Filter lessons by text query and/or section number/name."""
    filtered = lessons

    if section:
        s_norm = section.strip().lower()
        if s_norm.isdigit():
            sec_target = int(s_norm)
            filtered = [l for l in filtered if l.section_num == sec_target]
        else:
            filtered = [l for l in filtered if s_norm in l.section_name.lower()]

    if query:
        q_terms = [t.lower() for t in query.split() if t.strip()]
        res = []
        for l in filtered:
            searchable = (
                f"{l.title} {l.date_ticket} {l.body} {l.generalisation} {l.tell} {l.cue} {l.lesson}".lower()
            )
            if all(t in searchable for t in q_terms):
                res.append(l)
        filtered = res

    return filtered


def print_summary(lessons_path: Path, lessons: list[Lesson]) -> None:
    """Print overall summary census and statistics."""
    content = lessons_path.read_text(encoding="utf-8")
    line_count = len(content.splitlines())
    byte_count = len(content.encode("utf-8"))

    print(f"LESSONS.md Census: {len(lessons)} lessons parsed across {lessons_path}")
    print(f"Retention Bounds: {line_count} lines / {byte_count} bytes (Limit: 1000 lines / 90 KiB)")
    print("-" * 70)

    by_sec: dict[str, list[Lesson]] = {}
    for l in lessons:
        sec_key = f"§{l.section_num} {l.section_name}"
        by_sec.setdefault(sec_key, []).append(l)

    for sec, sec_lessons in sorted(by_sec.items()):
        print(f"  {sec:<36} {len(sec_lessons):>3} lesson(s)")

    print("-" * 70)
    print("Recent lessons:")
    for l in lessons[-5:]:
        print(f"  • L{l.line_number}: {l.title[:65]}")
    print("\nRun `just lessons <query>` to search rules, `just lessons --tell` to scan tells, or `just lessons --index` for Harness² cue index.")


def print_results(results: list[Lesson], tell_only: bool = False) -> None:
    """Format matched lesson results."""
    if not results:
        print("No lessons matched query.")
        return

    print(f"Matched {len(results)} lesson(s):\n")
    for l in results:
        print(f"[Section {l.section_num}: {l.section_name}] line {l.line_number} (confidence: {l.confidence})")
        print(f"  RULE: {l.title}")
        if l.date_ticket:
            print(f"  CONTEXT: {l.date_ticket}")
        if not tell_only and l.body:
            preview = l.body.splitlines()[0] if l.body else ""
            print(f"  DETAIL: {preview[:100]}...")
        if not tell_only and l.generalisation:
            print(f"  {l.generalisation}")
        if l.tell:
            print(f"  {l.tell}")
        print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Query and audit w0m LESSONS.md rules.")
    parser.add_argument("query", nargs="*", default=None, help="Search query string")
    parser.add_argument("--section", "-s", help="Filter by section number (1-7) or name")
    parser.add_argument("--tell", "-t", action="store_true", help="Print only rule and tell for fast skimming")
    parser.add_argument("--index", "-i", action="store_true", help="Print compact Harness² cue/lesson/confidence index")
    parser.add_argument("--json", "-j", action="store_true", help="Output results in JSON format")
    parser.add_argument("--path", "-p", help="Custom path to LESSONS.md")

    args = parser.parse_args()
    query_str = " ".join(args.query).strip() if args.query else None

    try:
        lessons_path = Path(args.path) if args.path else find_lessons_file()
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    lessons = parse_lessons(lessons_path)

    if not query_str and not args.section and not args.tell and not args.index and not args.json:
        print_summary(lessons_path, lessons)
        return 0

    results = filter_lessons(lessons, query=query_str, section=args.section)

    if args.index:
        print(format_harness2_index(results), end="")
        return 0

    if args.json:
        out = [asdict(l) for l in results]
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0

    print_results(results, tell_only=args.tell)
    return 0


if __name__ == "__main__":
    sys.exit(main())

