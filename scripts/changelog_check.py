#!/usr/bin/env python3
"""Public disclosure guardrail linter for CHANGELOG.md (T436).

Verifies that CHANGELOG.md is clean of:
- Personal email addresses and actor PII
- Raw secrets, service keys, and token identifiers
- Confidential client markers and internal-only tags
- Unsanitized vulnerability/exploit identifiers

Run via `just changelog-check`.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

FORBIDDEN_RULES = [
    (
        "EMAIL",
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
        "Personal/actor email address detected",
    ),
    (
        "SECRET_TOKEN",
        re.compile(r"\b[A-Z0-9_]{3,}_(?:KEY|SECRET|TOKEN|PASSWORD)\b"),
        "Raw secret, key, or token identifier detected",
    ),
    (
        "CONFIDENTIAL",
        re.compile(r"\b(?:CONFIDENTIAL(?:-CLIENT-[A-Z0-9_]+)?|INTERNAL\s+ONLY|PROPRIETARY)\b", re.IGNORECASE),
        "Confidential or internal-only marker detected",
    ),
    (
        "VULN_EXPLOIT",
        re.compile(r"\b(?:CVE-\d{4}-\d+|zero-day|exploit\s+payload)\b", re.IGNORECASE),
        "Unsanitized vulnerability or exploit disclosure detected",
    ),
]


def scan_file(path: Path) -> list[dict]:
    findings = []
    if not path.exists():
        return [{"rule": "MISSING_FILE", "line": 0, "match": str(path), "message": f"File does not exist: {path}"}]

    try:
        content = path.read_text(encoding="utf-8")
    except Exception as e:
        return [{"rule": "READ_ERROR", "line": 0, "match": str(path), "message": f"Could not read file: {e}"}]

    for idx, line in enumerate(content.splitlines(), start=1):
        # Skip pure markdown link URLs if they are relative file links (file:///)
        for rule_id, pattern, desc in FORBIDDEN_RULES:
            matches = pattern.finditer(line)
            for m in matches:
                matched_text = m.group(0)
                findings.append({
                    "rule": rule_id,
                    "line": idx,
                    "match": matched_text,
                    "message": desc,
                    "context": line.strip(),
                })
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan CHANGELOG.md for public disclosure violations")
    parser.add_argument("--path", default="CHANGELOG.md", help="Path to CHANGELOG.md file")
    parser.add_argument("--json", action="store_true", help="Output findings as JSON")
    args = parser.parse_args()

    target = Path(args.path)
    if not target.exists():
        print(f"changelog-check: file does not exist: {target}", file=sys.stderr)
        return 2

    findings = scan_file(target)

    if args.json:
        print(json.dumps({"findings": findings, "clean": len(findings) == 0}, indent=2))
        return 1 if findings else 0

    if not findings:
        print(f"✅ changelog-check passed ({target} clean)")
        return 0

    print(f"🔴 changelog-check failed: {len(findings)} disclosure violation(s) found in {target}:")
    for f in findings:
        print(f"  line {f['line']} [{f['rule']}]: {f['message']} -> '{f['match']}'")
        if "context" in f:
            print(f"    context: {f['context']}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
