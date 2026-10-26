#!/usr/bin/env python3
"""T242 AC6 — tests for ticket_id_align_check: the T<n> == gh_issue == #<n> invariant.

Proves:
1. Detects when gh_issue is missing.
2. Detects when gh_issue does not match the numeric base (misaligned).
3. Detects when remote issue title does not match T<n> prefix.
4. Passes when ticket base == gh_issue == remote issue number and title matches.
5. Handles offline mode cleanly without network calls.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "wom7web"
sys.path.insert(0, str(ROOT / "scripts"))

try:
    import ticket_id_align_check as c  # noqa: E402
except ImportError:
    c = None  # Expected to fail initially in TDD red step

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'✅' if ok else '❌'} {label}")
    if not ok:
        failures.append(f"{label} — {detail}")


print("▶ T242 — ticket_id_align_check\n")

if c is None:
    print("❌ ticket_id_align_check module does not exist yet (RED)")
    sys.exit(1)

# ── 1. Aligned ticket fixture ────────────────────────────────────────────────
aligned_tickets = [
    {"id": "T1", "base": 1, "gh_issue": 1, "title": "First ticket"},
    {"id": "T2", "base": 2, "gh_issue": 2, "title": "Second ticket"},
]
errs = c.check_alignment(aligned_tickets)
check("fully aligned tickets produce 0 errors", len(errs) == 0, f"got {errs}")

# ── 2. Missing gh_issue ──────────────────────────────────────────────────────
missing_issue_tickets = [
    {"id": "T1", "base": 1, "gh_issue": None, "title": "First ticket"},
]
errs = c.check_alignment(missing_issue_tickets)
check("missing gh_issue is flagged as an error",
      len(errs) == 1 and "missing" in errs[0].lower(),
      f"got {errs}")

# ── 3. Misaligned gh_issue ───────────────────────────────────────────────────
misaligned_tickets = [
    {"id": "T42", "base": 42, "gh_issue": 103, "title": "Misaligned ticket"},
]
errs = c.check_alignment(misaligned_tickets)
check("misaligned gh_issue (T42 != #103) is flagged as an error",
      len(errs) == 1 and "42" in errs[0] and "103" in errs[0],
      f"got {errs}")

# ── 4. Remote title check (when remote_issues map provided) ──────────────────
remote_issues = {
    1: "T1 — First ticket",
    2: "Wrong Title Without Prefix",
}
errs = c.check_alignment(aligned_tickets, remote_issues=remote_issues)
check("remote title mismatch is flagged as an error",
      len(errs) == 1 and "T2" in errs[0],
      f"got {errs}")

# ── 5. Missing remote issue (remote_issues provided but key absent) ──────────
remote_issues_partial = {
    1: "T1 — First ticket",
}
errs = c.check_alignment(aligned_tickets, remote_issues=remote_issues_partial)
check("missing remote issue on GitHub is flagged as an error",
      len(errs) == 1 and "T2" in errs[0] and "absent" in errs[0].lower(),
      f"got {errs}")

print()
if failures:
    print(f"❌ {len(failures)} failure(s):")
    for f in failures:
        print(f"   · {f}")
    sys.exit(1)
print("✅ ticket_id_align_check detects missing, misaligned, and mismatched issues")
