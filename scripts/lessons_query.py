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
from typing import Any


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
        if (parent / ".git").exists() and (parent / "w0m-web").is_dir():
            return parent
    return Path(__file__).resolve().parents[1]


def find_lessons_file(start_path: Path | None = None) -> Path:
    """Locate canonical @wom/LESSONS.md at workspace root. Fail fast if missing (AgDR-0025)."""
    root = find_workspace_root(start_path)
    canonical = root / "LESSONS.md"
    if not canonical.is_file():
        raise FileNotFoundError(f"Missing canonical LESSONS.md at {canonical}")
    return canonical


def _parse_lessons_file(lessons_path: Path, default_sec_num: int = 0, default_sec_name: str = "Preamble") -> list[Lesson]:
    """Parse a single markdown file containing one or more `### ...` lesson entries."""
    text = lessons_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    section_re = re.compile(r"^##\s+(\d+)\.\s+(.*)")
    heading_re = re.compile(r"^###\s+(.*)")

    current_section_num = default_sec_num
    current_section_name = default_sec_name

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


def parse_lessons(lessons_path: Path) -> list[Lesson]:
    """Parse LESSONS.md and/or a directory of keyed per-lesson `.md` files (T531 AC2)."""
    if lessons_path.is_dir():
        lessons: list[Lesson] = []
        for entry in sorted(lessons_path.glob("*.md"), key=lambda p: p.name):
            lessons.extend(_parse_lessons_file(entry))
        return lessons

    lessons = _parse_lessons_file(lessons_path)
    # Also load keyed per-lesson drop-in files from sibling `project/lessons/` or `lessons.d/`
    for rel_dir in ("project/lessons", "lessons.d"):
        dropin_dir = lessons_path.parent / rel_dir
        if dropin_dir.is_dir():
            for entry in sorted(dropin_dir.glob("*.md"), key=lambda p: p.name):
                lessons.extend(_parse_lessons_file(entry))
    return lessons


def record_lesson(
    lessons_dir: Path,
    key: str,
    title: str,
    body: str,
    *,
    section_num: int = 3,
    section_name: str = "Gates, Tests & Verification",
    date_ticket: str = "",
    generalisation: str = "",
    tell: str = "",
) -> Path:
    """Atomically write a keyed lesson file (`<lessons_dir>/<key>.md`) using O_CREAT | O_EXCL (T531 AC2).

    Two concurrent agents recording lessons write independent keyed files and never share an EOF anchor.
    """
    import os

    lessons_dir = Path(lessons_dir)
    lessons_dir.mkdir(parents=True, exist_ok=True)
    safe_key = re.sub(r"[^a-zA-Z0-9._-]+", "-", key.strip()).strip("-")
    if not safe_key:
        raise ValueError("lesson key must not be empty")

    target = lessons_dir / f"{safe_key}.md"
    fd = os.open(str(target), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    try:
        lines = [
            f"## {section_num}. {section_name}",
            "",
            f"### {title.strip()}",
        ]
        if date_ticket:
            dt_line = date_ticket.strip()
            if not dt_line.startswith("**"):
                dt_line = f"**{dt_line}**"
            lines.append(dt_line)
        if body:
            lines.append(body.strip())
        if generalisation:
            gen_line = generalisation.strip()
            if not (gen_line.startswith("⇒") or gen_line.startswith("=>")):
                gen_line = f"⇒ {gen_line}"
            lines.append(gen_line)
        if tell:
            tell_line = tell.strip()
            if not tell_line.startswith("⭐"):
                tell_line = f"⭐ **The tell:** {tell_line}"
            lines.append(tell_line)
        content = "\n".join(lines) + "\n"
        os.write(fd, content.encode("utf-8"))
    finally:
        os.close(fd)
    return target


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
    parser.add_argument("--harvest-friction", action="store_true", help="Harvest recent session transcripts & worktree landing events for Late-Learn friction (T602 AC4)")
    parser.add_argument("--since-hours", type=float, default=12.0, help="Hours of transcripts to scan (default: 12.0)")
    parser.add_argument("--tree-name", default=None, help="Optional agent tree set name")
    parser.add_argument("--current-tree", action="store_true", help="Filter digest output to items from the active tree/session while still logging cross-session state")
    parser.add_argument("--current-tree-source", default=None, help="Explicit transcript conversation ID or stem considered the active session")
    parser.add_argument("--record-event", default=None, help="Optional JSON friction event to record")
    parser.add_argument("--transcript", action="append", default=None, help="Explicit transcript file path(s) to scan (test seam)")
    parser.add_argument("--state-file", default=None, help="Override landing-friction.jsonl path (test seam)")

    args = parser.parse_args()

    if args.harvest_friction or args.record_event:
        extra: list[dict[str, str]] = []
        if args.record_event:
            try:
                ev: Any = json.loads(args.record_event)
                if isinstance(ev, dict):
                    extra.append({str(k): str(v) for k, v in ev.items()})
            except Exception as exc:
                print(f"ERROR: invalid --record-event JSON: {exc}", file=sys.stderr)
                return 2
        t_paths = [Path(p) for p in args.transcript] if args.transcript is not None else None
        s_file = Path(args.state_file) if args.state_file else FRICTION_STATE_FILE
        report = harvest_session_friction(
            find_workspace_root(),
            since_hours=args.since_hours,
            tree_name=args.tree_name,
            state_file=s_file,
            extra_events=extra,
            transcript_paths=t_paths,
            tree_only=args.current_tree,
            current_tree_source=args.current_tree_source,
        )
        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            print_friction_digest(report)
        return 0

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


FRICTION_STATE_FILE = Path.home() / ".w0m" / "state" / "landing-friction.jsonl"

_MISS_PATTERNS = (
    re.compile(r"cannot read [\"']?([^\"'\n]+?)[\"']?: file does not exist", re.IGNORECASE),
    re.compile(r"can't open file [\"']([^\"'\n]+)[\"']: \[Errno 2\]", re.IGNORECASE),
    re.compile(r"No such file or directory: [\"']?([^\"'\n]+?)[\"']?(?:$|\s)", re.IGNORECASE),
    re.compile(r"pathspec [\"']([^\"'\n]+)[\"'] did not match", re.IGNORECASE),
)

_PARAM_PATTERNS = (
    (re.compile(r"error: unrecognized arguments:\s*([^\n]+)"), "unrecognized_cli_args"),
    (re.compile(r"no such option:\s*([^\n]+)", re.IGNORECASE), "no_such_cli_option"),
    (re.compile(r"error: Justfile does not contain recipe `([^`]+)`"), "unknown_just_recipe"),
    (re.compile(r"OperationalError:\s*(no such column:[^\n]+)"), "sqlite_schema_miss"),
    (re.compile(r"could not find target content|target string not found", re.IGNORECASE), "edit_target_mismatch"),
)

_GATE_PATTERNS = (
    (re.compile(r"sh:\s*\d+:\s*([a-zA-Z0-9_.-]+):\s*not found"), "missing_worktree_binary"),
    (re.compile(r"refused:\s*([a-z_]+):\s*([^\n]+)"), "agent_tree_refusal"),
)


def _build_basename_index(root: Path) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Index tracked files across root and member repos by basename and by stem."""
    import subprocess

    by_name: dict[str, list[str]] = {}
    by_stem: dict[str, list[str]] = {}
    repos = ["."]
    sdlc_path = root / ".w0m" / "sdlc.json"
    if sdlc_path.is_file():
        try:
            sdlc_doc: dict[str, Any] = json.loads(sdlc_path.read_text(encoding="utf-8"))
            declared = sdlc_doc.get("repos", {})
            for val in declared.values():
                p = val if isinstance(val, str) else val.get("path")
                if p and p not in repos and (root / p / ".git").exists():
                    repos.append(p)
        except Exception:
            pass

    for r in repos:
        repo_dir = root if r == "." else root / r
        proc = subprocess.run(
            ["git", "-C", str(repo_dir), "ls-files"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            continue
        for rel in proc.stdout.splitlines():
            if not rel:
                continue
            full_rel = rel if r == "." else f"{r}/{rel}"
            name = Path(rel).name
            stem = Path(rel).stem
            by_name.setdefault(name, []).append(full_rel)
            by_stem.setdefault(stem, []).append(full_rel)
    return by_name, by_stem


def resolve_canonical_location(
    missing_path: str,
    root: Path,
    index: tuple[dict[str, list[str]], dict[str, list[str]]] | None = None,
) -> list[str]:
    """Resolve a missed path to its canonical tracked path(s) in the estate."""
    by_name, by_stem = index if index is not None else _build_basename_index(root)
    p = Path(missing_path.strip().rstrip(":"))
    if not p.name:
        return []
    exact = by_name.get(p.name, [])
    if exact:
        return sorted(set(exact))[:4]
    code_exts = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}
    stem_hits = [
        cand for cand in by_stem.get(p.stem, [])
        if Path(cand).suffix == p.suffix or (p.suffix in code_exts and Path(cand).suffix in code_exts)
    ]
    if stem_hits:
        return sorted(set(stem_hits))[:4]
    return []


def _scan_text_for_friction(
    text: str,
    source: str,
    root: Path,
    index: tuple[dict[str, list[str]], dict[str, list[str]]],
) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    for pat in _MISS_PATTERNS:
        for m in pat.finditer(text):
            raw_path = m.group(1).strip().rstrip("\r")
            if not raw_path or len(raw_path) > 240 or raw_path.startswith("/tmp/"):
                continue
            if raw_path.startswith("/") and not (
                str(root) in raw_path or "/.w0m/work/" in raw_path or "/Projects/" in raw_path
            ):
                continue
            # Normalize absolute estate/worktree paths to repo-relative when possible
            norm = raw_path
            for prefix in (str(root) + "/",):
                if norm.startswith(prefix):
                    norm = norm[len(prefix) :]
            norm_parts = norm.split("/w0m/", 1)
            if len(norm_parts) == 2 and ("/.w0m/work/" in raw_path or "/Projects/" in raw_path):
                norm = norm_parts[1]
            resolved = resolve_canonical_location(norm, root, index)
            events.append(
                {
                    "category": "location_miss",
                    "subtype": "missing_path",
                    "attempted": norm,
                    "resolved": ", ".join(resolved) if resolved else "unresolved",
                    "source": source,
                }
            )
    for pat, subtype in _PARAM_PATTERNS:
        for m in pat.finditer(text):
            detail = (m.group(1).strip() if m.lastindex else m.group(0).strip()).replace("\r", "")
            events.append(
                {
                    "category": "parameter_or_cli_error",
                    "subtype": subtype,
                    "attempted": detail[:160],
                    "resolved": "",
                    "source": source,
                }
            )
    for pat, subtype in _GATE_PATTERNS:
        for m in pat.finditer(text):
            detail = (
                f"{m.group(1)}: {m.group(2)}" if m.lastindex and m.lastindex >= 2 else m.group(1).strip()
            ).replace("\r", "")
            events.append(
                {
                    "category": "landing_or_gate_error",
                    "subtype": subtype,
                    "attempted": detail[:160],
                    "resolved": "",
                    "source": source,
                }
            )
    return events


def harvest_session_friction(
    root: Path | None = None,
    *,
    since_hours: float = 12.0,
    tree_name: str | None = None,
    state_file: Path = FRICTION_STATE_FILE,
    extra_events: list[dict[str, str]] | None = None,
    transcript_paths: list[Path] | None = None,
    tree_only: bool = False,
    current_tree_source: str | None = None,
) -> dict[str, object]:
    """Scan recent session transcripts and landing events for friction, persist to JSONL, and recommend Late-Learn actions (T602 AC4)."""
    import hashlib
    import time

    ws_root = root or find_workspace_root()
    index = _build_basename_index(ws_root)
    now = time.time()
    cutoff = now - (since_hours * 3600.0)

    candidates: list[Path] = []
    if transcript_paths is not None:
        candidates = [Path(p) for p in transcript_paths if Path(p).is_file()]
    else:
        agy_root = Path.home() / ".gemini" / "antigravity-cli" / "brain"
        if agy_root.is_dir():
            for p in agy_root.glob("*/.system_generated/logs/transcript.jsonl"):
                try:
                    if p.stat().st_mtime >= cutoff:
                        candidates.append(p)
                except OSError:
                    pass
        claude_root = Path.home() / ".claude" / "projects"
        if claude_root.is_dir():
            for p in sorted(claude_root.glob("*/*.jsonl"), key=lambda x: x.stat().st_mtime if x.exists() else 0, reverse=True)[:5]:
                try:
                    if p.stat().st_mtime >= cutoff:
                        candidates.append(p)
                except OSError:
                    pass

    raw_events: list[dict[str, str]] = [
        {"tree": tree_name or "", **ev} for ev in (extra_events or [])
    ]
    worktree_re = re.compile(r"/\.w0m/work/([a-z0-9][a-z0-9-]{0,39})/w0m\b")
    for tp in candidates:
        try:
            tp_text = tp.read_text(encoding="utf-8", errors="ignore")
            tp_trees = worktree_re.findall(tp_text)
            inferred_tree = tp_trees[-1] if tp_trees else ""
            tp_src = tp.parent.parent.parent.name if ".system_generated" in str(tp) else tp.stem
            if current_tree_source and tp_src == current_tree_source and tree_name:
                inferred_tree = tree_name
            for line in tp_text.splitlines():
                if not line.strip():
                    continue
                try:
                    obj: dict[str, Any] = json.loads(line)
                    content = str(obj.get("content") or "")
                    if not content and isinstance(obj.get("message"), dict):
                        content = json.dumps(obj["message"])
                except Exception:
                    content = line
                if any(
                    k in content
                    for k in (
                        "file does not exist",
                        "Errno 2",
                        "No such file or directory",
                        "unrecognized arguments",
                        "no such option",
                        "does not contain recipe",
                        "no such column",
                        "not found",
                        "refused:",
                    )
                ):
                    line_trees = worktree_re.findall(content)
                    line_tree = line_trees[-1] if line_trees else inferred_tree
                    for found in _scan_text_for_friction(content, tp_src, ws_root, index):
                        found.setdefault("tree", line_tree)
                        raw_events.append(found)
        except OSError:
            continue

    existing_fps: set[str] = set()
    persisted: list[dict[str, str]] = []
    if state_file.is_file():
        for line in state_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not line.strip():
                continue
            try:
                rec: Any = json.loads(line)
                if isinstance(rec, dict) and rec.get("fingerprint"):
                    existing_fps.add(str(rec["fingerprint"]))
                    persisted.append(rec)
            except Exception:
                continue

    deduped_session: dict[str, dict[str, str]] = {}
    new_records: list[dict[str, str]] = []
    iso_now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
    for ev in raw_events:
        key_str = f"{ev.get('category')}|{ev.get('subtype')}|{ev.get('attempted')}"
        fp = hashlib.sha1(key_str.encode("utf-8")).hexdigest()[:12]
        rec = {
            "timestamp": iso_now,
            "tree": str(ev.get("tree") or ""),
            "fingerprint": fp,
            **ev,
        }
        deduped_session[fp] = rec
        if fp not in existing_fps:
            existing_fps.add(fp)
            new_records.append(rec)

    if new_records:
        state_file.parent.mkdir(parents=True, exist_ok=True)
        with state_file.open("a", encoding="utf-8") as f:
            for r in new_records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    all_items = list(deduped_session.values())
    if tree_only and (current_tree_source or tree_name):
        active_items = [
            it
            for it in all_items
            if (current_tree_source and it.get("source") == current_tree_source)
            or (tree_name and (it.get("tree") == tree_name or tree_name in str(it.get("attempted") or "")))
        ]
    else:
        active_items = all_items
    by_category: dict[str, list[dict[str, str]]] = {
        "location_miss": [],
        "parameter_or_cli_error": [],
        "landing_or_gate_error": [],
    }
    for item in active_items:
        by_category.setdefault(item["category"], []).append(item)

    recommendations: list[dict[str, str]] = []
    for item in by_category.get("location_miss", []):
        if item.get("resolved") and item["resolved"] != "unresolved":
            recommendations.append(
                {
                    "target": "CLAUDE.md / LESSONS.md",
                    "reason": f"Path miss `{item['attempted']}` → canonical location is `{item['resolved']}`",
                    "action": f"Index `{item['resolved']}` in CLAUDE.md or add a `⭐ The tell` cue in LESSONS.md.",
                }
            )
    for item in by_category.get("parameter_or_cli_error", []):
        recommendations.append(
            {
                "target": "LESSONS.md",
                "reason": f"CLI/parameter friction ({item['subtype']}): `{item['attempted']}`",
                "action": "Capture a transferable CLI/schema tell in LESSONS.md if this recurred across turns.",
            }
        )
    for item in by_category.get("landing_or_gate_error", []):
        recommendations.append(
            {
                "target": "TECH-DEBT.md / .tasks/T##.md",
                "reason": f"Worktree/gate friction ({item['subtype']}): `{item['attempted']}`",
                "action": "Provision missing worktree fixture in `scripts/release.py` or file a `D##` / `T##` item.",
            }
        )

    return {
        "harvested_count": len(active_items),
        "cross_session_total": len(all_items),
        "newly_recorded_count": len(new_records),
        "tree_only": tree_only,
        "tree_name": tree_name or "",
        "since_hours": since_hours,
        "state_file": str(state_file),
        "by_category": by_category,
        "recommendations": recommendations,
    }


def print_friction_digest(report: dict[str, object]) -> None:
    """Print human-readable Late-Learn Friction Digest at worktree landing or via `just lessons-harvest`."""
    total = int(str(report.get("harvested_count") or 0))
    cross_total = int(str(report.get("cross_session_total") or total))
    new_cnt = int(str(report.get("newly_recorded_count") or 0))
    since_h = report.get("since_hours") or 12.0
    tree_only = bool(report.get("tree_only"))
    tree_name = str(report.get("tree_name") or "").strip()
    by_cat: dict[str, list[dict[str, str]]] = report.get("by_category") or {}  # type: ignore[assignment]
    recs: list[dict[str, str]] = report.get("recommendations") or []  # type: ignore[assignment]

    if tree_only and tree_name:
        scope_note = (
            f"tree={tree_name}: {total} in this tree, {cross_total} cross-session in last {since_h:g}h"
        )
    else:
        scope_note = f"{total} cross-session historical item(s) across last {since_h:g}h"

    print(
        f"▶ Late-Learn Friction Digest (info-only) — {scope_note} "
        f"({new_cnt} newly logged to {report.get('state_file')})"
    )
    if total == 0:
        if tree_only and cross_total > 0:
            print(
                f"  ✅ 0 friction items in `{tree_name}` (info-only: {cross_total} item(s) remain from sibling sessions; run `just lessons-harvest` to inspect)."
            )
        else:
            print("  ✅ 0 location misses, parameter errors, or gate refusals in recent transcripts.")
        return

    for cat, label in (
        ("location_miss", "Location Misses (attempted → canonical)"),
        ("parameter_or_cli_error", "Parameter / CLI / Schema Errors"),
        ("landing_or_gate_error", "Worktree / Gate Friction"),
    ):
        items = by_cat.get(cat) or []
        if not items:
            continue
        print(f"  • {label}: {len(items)}")
        for it in items[:6]:
            if it.get("resolved"):
                print(f"      - `{it['attempted']}` → `{it['resolved']}`")
            else:
                print(f"      - [{it['subtype']}] `{it['attempted']}`")
    if recs:
        print("  • Late-Learn Candidate Actions:")
        for r in recs[:5]:
            print(f"      → [{r['target']}] {r['reason']}")
            print(f"        {r['action']}")


if __name__ == "__main__":
    sys.exit(main())

