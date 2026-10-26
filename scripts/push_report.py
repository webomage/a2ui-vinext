#!/usr/bin/env python3
"""push_report.py — Parse pre-push log and render Pre-Push Final Report (T390).

Extracts and aggregates non-blocking warnings, advisories, ratchets, and capacity
notices across all 20 pre-push gates, displaying a structured summary before exit.

Standard library only. Python per w0m tool ladder.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

# Category labels and order
CATEGORY_ORDER = [
    ("astro-check", "Astro Check"),
    ("audit-security", "Audit & Security"),
    ("dependencies", "Dependencies"),
    ("cli-tools", "CLI Tools"),
    ("ticket-duplicates", "Ticket Duplication"),
    ("tech-debt", "Tech Debt"),
    ("state-surface", "State Surface"),
    ("ratchets", "Ratchets"),
    ("hooks", "Hook Hygiene"),
]


def parse_log_text(text: str) -> dict[str, list[str]]:
    """Parse log text and extract categorized warnings and advisories."""
    findings: dict[str, list[str]] = {}

    def add(cat: str, msg: str) -> None:
        clean = msg.strip()
        if not clean:
            return
        if cat not in findings:
            findings[cat] = []
        if clean not in findings[cat]:
            findings[cat].append(clean)

    # Summary hints from astro check
    # Example: Result (194 files):\n- 0 errors\n- 0 warnings\n- 17 hints
    for m in re.finditer(
        r"Result \((\d+) files?\):\s*(?:-\s*\d+\s+errors?\s*)?(?:-\s*\d+\s+warnings?\s*)?-\s*([1-9]\d*)\s+hints?",
        text,
    ):
        files_cnt, hints_cnt = m.groups()
        add("astro-check", f"astro check: {hints_cnt} hint(s) reported across {files_cnt} files")

    lines = text.splitlines()

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # 1. Astro Check Warnings & Hints
        # Example: src/pages/jobs/[id].astro:15:9 - warning ts(6133): 'res' is declared but its value is never read.
        # Example: src/pages/api/admin/impersonate.ts:192:13 - warning ts(6385): 'supabase' is deprecated.
        # Example: src/pages/interview/[id].astro:10:23 - hint ts(6385): 'supabase' is deprecated.
        m_astro = re.search(
            r"(\S+\.(?:astro|ts|tsx|svelte|js):\d+:\d+)\s+-\s+(?:warning|hint)\s+(?:ts\(\d+\):\s+)?(.+)",
            stripped,
        )
        if m_astro:
            loc, msg = m_astro.groups()
            add("astro-check", f"{loc}: {msg}")
            continue

        # 2. Audit & Security Warnings
        # Example: ⚠️  WARN  [security] reputation-staleness — last confirmed 15d ago (>7d)
        if "[security] reputation-staleness" in stripped:
            detail = stripped.split("—", 1)[-1].strip() if "—" in stripped else stripped
            # Trim long resolution notes for summary readability
            if "—" in detail:
                detail = detail.split("—")[0].strip()
            add("audit-security", f"reputation-staleness: {detail}")
            continue

        if "[security] safe-browsing" in stripped:
            detail = stripped.split("—", 1)[-1].strip() if "—" in stripped else stripped
            add("audit-security", f"safe-browsing: {detail}")
            continue

        if "[git] branch beta" in stripped and "ahead" in stripped:
            detail = stripped.split("—", 1)[-1].strip() if "—" in stripped else stripped
            add("audit-security", f"git branch beta: {detail}")
            continue

        # 3. Dependencies
        # Example: advisory @supabase/supabase-js: wom7ext @ ^2.87.1 (target ^2.110.7) — 23 minors behind
        if "advisory @" in stripped or "advisory " in stripped and "target" in stripped:
            clean_adv = re.sub(r"^[⚠ℹ️\s*]+advisory\s+", "", stripped)
            add("dependencies", clean_adv)
            continue

        # 4. CLI Tools
        # Example: 1 CLI tool update(s) available (1 auto): gcloud
        m_tools = re.search(r"(\d+\s+CLI tool update\(s\) available[^\n]*)", stripped)
        if m_tools:
            add("cli-tools", m_tools.group(1))
            continue

        # 5. Ticket Duplication Advisories
        # Example: ⚠️  7 duplicate/overlapping pair(s) detected:
        m_dups = re.search(r"(\d+\s+duplicate/overlapping pair\(s\) detected)", stripped)
        if m_dups:
            add("ticket-duplicates", f"{m_dups.group(1)} in queue (run `just ticket-dups` to review)")
            continue

        # 5. Tech Debt Register
        # Example: UNOWNED — no LIVE ticket in the Tracked cell: 17
        m_unowned = re.search(r"UNOWNED — no LIVE ticket in the Tracked cell[^:]*:\s*(\d+)", stripped)
        if m_unowned:
            count = m_unowned.group(1)
            add("tech-debt", f"{count} unowned debt rows in TECH-DEBT.md (tracking tickets completed)")
            continue

        # Example: this push adds 2 TODO/FIXME/HACK marker(s)
        m_added_debt = re.search(r"this push adds\s+(\d+)\s+TODO/FIXME/HACK marker\(s\)", stripped)
        if m_added_debt:
            add("tech-debt", f"adds {m_added_debt.group(1)} TODO/FIXME/HACK marker(s) in this push")
            continue

        # 6. State Surface Capacity
        # Example: STATE.md 628/900 lines (70%) · 73,345/81,920 bytes (90%) — run `just state-rotate` before adding more
        if "STATE.md" in stripped and ("lines" in stripped or "bytes" in stripped) and ("rotate" in stripped or "%" in stripped):
            clean_state = re.sub(r"^[ℹ️⚠️\s*]+", "", stripped)
            add("state-surface", clean_state)
            continue

        # 7. Ratchets & Integrity
        # Example: join: 12 errors, at baseline
        if "join:" in stripped and "errors" in stripped and "baseline" in stripped:
            clean_join = re.sub(r"^[·\s*]+", "", stripped)
            add("ratchets", clean_join)
            continue

        if "beat baseline" in stripped or ("stale" in stripped and "shared" in stripped and "baseline" in stripped):
            add("ratchets", "DoD ratchet beat baseline (stale/shared lower; lower in project/dod-baseline.json)")
            continue

        # 8. Hook Hygiene
        # Example: web/typecheck (pre-push) wired from ANOTHER repo: wom7ext/.pre-commit-config.yaml
        if "wired from ANOTHER repo" in stripped:
            clean_hook = re.sub(r"^[ℹ️\s*]+", "", stripped)
            add("hooks", clean_hook)
            continue

        if "exempt from the `just` contract" in stripped:
            clean_exempt = re.sub(r"^[ℹ️\s*]+", "", stripped)
            # Truncate after 60 chars if very long
            if len(clean_exempt) > 75:
                clean_exempt = clean_exempt[:72] + "…"
            add("hooks", clean_exempt)
            continue

    return findings


def format_report(findings: dict[str, list[str]]) -> str:
    """Format categorized findings into a high-visibility terminal banner."""
    if not findings:
        return ""

    total_count = sum(len(items) for items in findings.values())
    lines = [
        "",
        "─" * 80,
        f"PRE-PUSH FINAL REPORT: {total_count} Informative Finding(s) & Advisory Notice(s)",
        "─" * 80,
    ]

    for cat_id, cat_title in CATEGORY_ORDER:
        items = findings.get(cat_id)
        if not items:
            continue
        tag = f"[{cat_id}]"
        for item in items:
            lines.append(f"  · {tag:<18} {item}")

    lines.append("─" * 80)
    lines.append("")
    return "\n".join(lines)


def resolve_log_path(explicit_path: str | None = None) -> Path | None:
    """Locate the pre-push log file to parse."""
    if explicit_path and explicit_path != "-":
        p = Path(explicit_path)
        return p if p.is_file() else None

    # Check environment variable from hook_log_wrap.sh
    env_log = os.environ.get("W0M_HOOK_RUN")
    if env_log and Path(env_log).is_file():
        return Path(env_log)

    # Check default cache dir
    cache_dir = Path.home() / ".cache" / "w0m" / "hooks"
    latest_symlink = cache_dir / "wom7web-pre-push-latest.log"
    if latest_symlink.is_file():
        return latest_symlink

    # Check any recent pre-push log in cache_dir
    if cache_dir.is_dir():
        logs = sorted(cache_dir.glob("*pre-push*.log"), key=lambda x: x.stat().st_mtime, reverse=True)
        if logs:
            return logs[0]

    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Pre-push log warning & advisory extractor")
    parser.add_argument("log_path", nargs="?", default=None, help="Path to hook log file (or - for stdin)")
    parser.add_argument("--quiet", action="store_true", help="Print nothing if zero findings")
    parser.add_argument("--json", action="store_true", help="Output findings as JSON")
    args = parser.parse_args()

    try:
        content = ""
        if args.log_path == "-" or (args.log_path is None and not sys.stdin.isatty()):
            content = sys.stdin.read()
        else:
            resolved = resolve_log_path(args.log_path)
            if resolved and resolved.is_file():
                content = resolved.read_text(encoding="utf-8", errors="replace")

        findings = parse_log_text(content) if content else {}

        if args.json:
            print(json.dumps(findings, indent=2))
            return 0

        report = format_report(findings)
        if report:
            print(report)
        elif not args.quiet:
            print("[OK] Pre-push execution clean — zero warnings or advisories.")
    except Exception as exc:
        # Fail open: reporting issues must NEVER fail an otherwise green push
        print(f"⚠️  [push-report] Notice: report extraction bypassed ({exc})", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
