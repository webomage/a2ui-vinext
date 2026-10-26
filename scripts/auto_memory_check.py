#!/usr/bin/env python3
"""auto_memory_check.py — advisory check for index↔body divergence in auto-memory.

Implements T232 AC14.
Checks that MEMORY.md hooks:
  1. Point to files that actually exist on disk.
  2. Do not carry critical status claims (e.g. RESOLVED, CLOSED, DONE) that are absent
     from the underlying topic file body.

Advisory only — exits 0 on missing directory (per-machine cache, not versioned repo).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path


def find_auto_memory_dir(custom_path: str | None = None) -> Path | None:
    if custom_path:
        p = Path(custom_path).expanduser().resolve()
        return p if p.is_dir() else None

    # Check ~/.claude/projects/ for wom project memory
    home = Path.home()
    claude_projects = home / ".claude" / "projects"
    if not claude_projects.is_dir():
        return None

    candidates = [
        claude_projects / "-Users-proto-Projects--self--wom" / "memory",
        claude_projects / "-Users-proto-Projects--self-wom" / "memory",
    ]
    for c in candidates:
        if c.is_dir():
            return c

    # Fallback: scan for any directory ending with --wom/memory
    for p in claude_projects.glob("*wom*/memory"):
        if p.is_dir():
            return p

    return None


def check_memory_consistency(memory_dir: Path) -> tuple[int, list[str]]:
    index_file = memory_dir / "MEMORY.md"
    if not index_file.is_file():
        return 0, [f"Missing index file: {index_file}"]

    text = index_file.read_text(encoding="utf-8")
    lines = text.splitlines()

    link_re = re.compile(r"^\s*-\s*\[(.*?)\]\((.*?)\)(?:\s*—\s*(.*))?$")
    warnings: list[str] = []
    checked = 0

    status_keywords = ["RESOLVED", "CLOSED", "PAID DOWN", "FIXED", "DONE"]

    for idx, line in enumerate(lines, start=1):
        m = link_re.match(line)
        if not m:
            continue

        checked += 1
        title = m.group(1).strip()
        filename = m.group(2).strip()
        hook = (m.group(3) or "").strip()

        target_path = memory_dir / filename
        if not target_path.is_file():
            warnings.append(f"Line {idx}: Hook '{title}' links to non-existent file '{filename}'")
            continue

        body_text = target_path.read_text(encoding="utf-8")

        # Check for status claim divergence
        for kw in status_keywords:
            if kw in hook.upper() and kw not in body_text.upper():
                warnings.append(
                    f"Line {idx} ({filename}): Hook asserts '{kw}' but claim is missing from body file"
                )

    return checked, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Check auto-memory index↔body divergence (T232 AC14).")
    parser.add_argument("--dir", "-d", help="Custom path to auto-memory directory")
    args = parser.parse_args()

    mem_dir = find_auto_memory_dir(args.dir)
    if not mem_dir:
        print("[INFO] auto-memory: no local Claude auto-memory directory found on this machine (advisory only).")
        return 0

    checked_count, warnings = check_memory_consistency(mem_dir)
    print(f"Auto-memory check: {checked_count} hook(s) verified in {mem_dir}")

    if warnings:
        print(f"\n[WARN] {len(warnings)} potential divergence finding(s):")
        for w in warnings:
            print(f"  • {w}")
        print("\nNote: Auto-memory is an unversioned machine cache (AC14 advisory).")
        return 0

    print("[OK] All auto-memory hooks resolve to existing files with backed status claims.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
