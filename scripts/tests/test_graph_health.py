#!/usr/bin/env python3
"""T151 AC4 — regression tests for graph_health's parsers.

Every case here exists because the first implementation got it wrong on the live
estate, not because it seemed worth checking:

* `_parse_hook_status` originally tested `"installed" in line`. graphify prints
  `post-commit: not installed`, and that substring test is TRUE for the negative
  case — so the health report claimed `hooks: both` for all 8 repos when not one
  had a hook installed. A false green in the tool built to detect false greens.

Run: python3 project/scripts/tests/test_graph_health.py
Exit: 0 all pass, 1 any failure.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from graph_health import _parse_hook_status  # noqa: E402

FAILS: list[str] = []


def check(name: str, got, want) -> None:
    if got == want:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}: got {got!r}, want {want!r}")
        FAILS.append(name)


def main() -> int:
    # The exact strings graphify emits. If graphify ever rephrases these, this test
    # is what tells us the parser has gone blind rather than the estate gone green.
    check("both not installed -> none",
          _parse_hook_status("post-commit: not installed\npost-checkout: not installed"),
          "none")
    check("both installed -> both",
          _parse_hook_status("post-commit: installed\npost-checkout: installed"),
          "both")
    check("one each -> partial",
          _parse_hook_status("post-commit: installed\npost-checkout: not installed"),
          "partial")
    check("reverse partial -> partial",
          _parse_hook_status("post-commit: not installed\npost-checkout: installed"),
          "partial")

    # graphify prints the install PATH on success; the parser must not be fooled by
    # a path that happens to contain the word "not".
    check("installed-at-path -> both",
          _parse_hook_status(
              "post-commit: installed at /repo/.husky/post-commit\n"
              "post-checkout: installed at /repo/.husky/post-checkout"),
          "both")

    # 🔴 The anti-vacuity cases: no output must NOT read as a clean "none".
    check("empty output -> unknown", _parse_hook_status(""), "unknown")
    check("unrelated output -> unknown",
          _parse_hook_status("Not in a git repository."), "unknown")

    # Only one line present is not enough to claim "both".
    check("single installed line -> partial",
          _parse_hook_status("post-commit: installed"), "partial")

    print()
    if FAILS:
        print(f"FAILURES PRESENT ({len(FAILS)})")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
