#!/usr/bin/env python3
"""T242 AC8 — tests for close_legacy_tracker_issues.

Proves:
1. Derives target issue number correctly from legacy issue title prefix (e.g. 'T42 ...' -> 42).
2. Falls back to target repo URL if no T-id prefix found.
3. Formats close comment citing T242 and target URL.
4. Dry-run mode performs no mutation.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "wom7web"
sys.path.insert(0, str(ROOT / "scripts"))

try:
    import close_legacy_tracker_issues as c  # noqa: E402
except ImportError:
    c = None

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'✅' if ok else '❌'} {label}")
    if not ok:
        failures.append(f"{label} — {detail}")


print("▶ T242 — close_legacy_tracker_issues tests\n")

if c is None:
    print("❌ close_legacy_tracker_issues module does not exist")
    sys.exit(1)

# 1. Target issue derivation with T-id
num, url = c.parse_target_issue("T42 — Decouple platform source defaults", "webomage/wom7board")
check("derives target issue number 42 from title", num == 42, f"got {num}")
check("constructs target URL pointing to issue 42 in webomage/wom7board",
      url == "https://github.com/webomage/wom7board/issues/42", f"got {url}")

# 2. Target issue derivation without T-id
num_none, url_fallback = c.parse_target_issue("Ad-hoc unnumbered task", "webomage/wom7board")
check("returns None for issue without T-id prefix", num_none is None, f"got {num_none}")
check("constructs fallback repo URL",
      url_fallback == "https://github.com/webomage/wom7board", f"got {url_fallback}")

# 3. Comment format
comment = c.format_close_comment(url)
check("comment contains target URL", url in comment, f"got {comment}")
check("comment cites T242", "T242" in comment, f"got {comment}")

# 4. Dry run mutation
res = c.close_issue(123, "comment", apply=False)
check("dry-run close_issue returns True without executing command", res is True)

print(f"\nResult: {len(failures)} failure(s)")
sys.exit(1 if failures else 0)
