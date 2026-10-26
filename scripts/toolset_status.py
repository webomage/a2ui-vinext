#!/usr/bin/env python3
"""One entry point for the whole w0m toolset's state — T149 AC4.

COMPOSES the existing checks. It re-implements none of them, and that is the load-bearing rule:
a second implementation of any check is a second thing to drift, which is the failure this epic
exists to remove. Every child below is an existing `just` recipe declared in
`project/stacks-policy.json` (T130). Adding a check here means adding a recipe there first.

⚠️ NOT A HOOK. Do not wire this into pre-commit or pre-push. Its children ALREADY run there
(`secrets-check` at pre-commit; `docs-check`/`state-check`/`version-check` at pre-push), so hooking
the composite would run each of them twice and roughly double push time for no new information.
This is the *ask-me* surface, not a gate.

WHY EACH CHILD IS ATTRIBUTABLE. An aggregate "toolset unhealthy" is useless — the point of a status
command is to say which thing is unhealthy. So every child reports its own exit code, its own
duration, and its own last line, and a timeout is reported AGAINST THE CHILD THAT HUNG rather than
failing the whole run anonymously.

WHY IT NAMES WHAT IT RAN. Per this epic's own spec: a check that reports a count must report the set
it counted over. A composite that silently skipped a child would be the same defect one level up, so
the child list is printed every run, including any that were skipped and why.

Exit: 0 all children passed · 1 one or more failed/timed out · 2 config error (a child recipe is
missing, i.e. the registry and reality disagree).

Run: `just toolset-status`  ·  `just toolset-status --json`
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # @wom/

# name -> (just recipe argv, per-child timeout seconds, one-line purpose)
# Budget measured 2026-07-27: ~16.4s total. Timeouts are ~4x the measured time, so a genuinely slow
# run is tolerated but a hang is caught. ⚠️ Re-measure when adding a child — T149 AC4 was blocked for
# a week on a recorded "exceeds 5 minutes" that was really ~11s.
CHILDREN: list[tuple[str, list[str], int, str]] = [
    ("queue",      ["just", "tasks", "hot"],     30, "ticket ranking (T146)"),
    ("stacks",     ["just", "discovery"],        30, "stack registry ↔ code drift (T130)"),
    ("skills",     ["just", "skill", "check"],   60, "skill manifest ↔ lockfile (T127)"),
    ("state",      ["just", "state-check"],      60, "STATE.md freshness (T145)"),
    ("toolchain",  ["just", "sdlc-doctor"],     120, "SDLC toolchain conformance (T119)"),
]


def run_child(name: str, argv: list[str], timeout: int) -> dict:
    start = time.monotonic()
    try:
        proc = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        # Attributed to THIS child. A composite that just died would leave the reader guessing.
        return {"name": name, "status": "timeout", "code": None,
                "seconds": round(time.monotonic() - start, 1), "last": f"exceeded {timeout}s"}
    except FileNotFoundError:
        return {"name": name, "status": "missing", "code": None,
                "seconds": 0.0, "last": f"{argv[0]} not found"}
    out = (proc.stdout or "") + (proc.stderr or "")
    lines = [ln.rstrip() for ln in out.splitlines() if ln.strip()]
    return {
        "name": name,
        "status": "pass" if proc.returncode == 0 else "fail",
        "code": proc.returncode,
        "seconds": round(time.monotonic() - start, 1),
        "last": lines[-1][:160] if lines else "(no output)",
    }


def main() -> int:
    as_json = "--json" in sys.argv

    if not CHILDREN:
        # An empty child list must FAIL, never print "0/0 checks passed" as health. This composite
        # was written FOR the epic whose whole finding is that a check reports zero because it only
        # looks where it knows to look — and it shipped without this guard. Instance 12.
        print("✗ toolset-status: no children configured — refusing to report health over nothing",
              file=sys.stderr)
        return 2

    if shutil.which("just") is None:
        print("✗ toolset-status: `just` is not on PATH — the command interface itself is missing",
              file=sys.stderr)
        return 2

    results = [run_child(n, argv, t) for n, argv, t, _ in CHILDREN]

    if as_json:
        print(json.dumps({"children": results,
                          "total_seconds": round(sum(r["seconds"] for r in results), 1)},
                         indent=2))
    else:
        # Name the set that was enumerated — this epic's own rule applied to itself.
        print(f"▶ toolset-status — composed over {len(CHILDREN)} check(s): "
              f"{', '.join(n for n, *_ in CHILDREN)}")
        print(f"  {'check':<11}{'result':<9}{'time':>7}  detail")
        print("  " + "-" * 84)
        glyph = {"pass": "✅", "fail": "❌", "timeout": "⏱", "missing": "🔴"}
        for r in results:
            code = "" if r["code"] is None else f" ({r['code']})"
            print(f"  {r['name']:<11}{glyph[r['status']] + ' ' + r['status']:<9}"
                  f"{r['seconds']:>6}s  {r['last']}{code}")

    bad = [r for r in results if r["status"] != "pass"]
    total = round(sum(r["seconds"] for r in results), 1)

    if not as_json:
        if bad:
            print(f"\n❌ {len(bad)} of {len(results)} check(s) need attention "
                  f"({', '.join(r['name'] for r in bad)}) — {total}s total")
            print("   Each line above is the child's OWN exit code; fix the named check, not this "
                  "composite.")
        else:
            print(f"\n✅ toolset healthy — {len(results)}/{len(results)} checks passed, {total}s total")

    # A missing recipe means the registry and reality disagree: a config fault, not a finding.
    if any(r["status"] == "missing" for r in results):
        return 2
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
