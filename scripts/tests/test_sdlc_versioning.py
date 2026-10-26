#!/usr/bin/env python3
"""Red probe for sdlc-doctor's versioning conformance check (T131 AC5).

Run: just sdlc-versioning-test

WHAT THIS PROVES, AND WHAT IT DELIBERATELY DOES NOT
---------------------------------------------------
`check_versioning` **delegates** to `just version-check` and `just skills-version-check`. So this
tests the WIRING — that a failing gate becomes a doctor problem, a timeout becomes a note rather
than silence, and a passing pair adds nothing. It does **not** re-test what those gates detect;
that is their own job and they have their own red probes (`just version-test` drives the real
checker over fixture policies and asserts red on a reintroduced producer, red on an empty scan set,
red on an unreasoned exemption, and red when the producer cannot emit its own format).

Saying that boundary out loud matters. A test that mocked the gates AND claimed to prove version
conformance would be exactly the thing this estate keeps finding: a green assertion over a
comparison that was never actually made.

The failure modes asserted here are the ones that would make the doctor lie:
  * a gate fails and the doctor stays green      -> the preflight passes over a broken standard
  * a gate times out and the doctor stays green  -> UNVERIFIED silently reported as verified
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT / "wom7web"
DOCTOR = ROOT / "scripts" / "sdlc_doctor.py"


def load():
    spec = importlib.util.spec_from_file_location("sdlc_doctor_under_test", DOCTOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Probe:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.n = 0

    def check(self, label: str, ok: bool, detail: str = "") -> None:
        self.n += 1
        print(f"  {label:<64} {'ok' if ok else '!! FAILED'}")
        if not ok:
            self.failures.append(f"{label}{': ' + detail if detail else ''}")


def run_with(mod, outcomes: dict[str, tuple[int, str]]):
    """Drive check_versioning with stubbed gate outcomes. -> (problems, notes)"""
    calls: list[str] = []

    def fake_sh(*args, cwd=None, timeout=None):
        recipe = args[1] if len(args) > 1 else args[0]
        calls.append(recipe)
        return outcomes.get(recipe, (0, "ok"))

    real, mod.sh = mod.sh, fake_sh
    try:
        problems, notes = [], []
        mod.check_versioning(problems, notes)
        return problems, notes, calls
    finally:
        mod.sh = real


def main() -> int:
    p = Probe()
    if not DOCTOR.exists():
        print(f"FATAL: {DOCTOR} not found", file=sys.stderr)
        return 2
    mod = load()

    print("\nCOLLECTION LAYER — both gates must actually be invoked")
    _, _, calls = run_with(mod, {})
    p.check("version-check is invoked", "version-check" in calls, str(calls))
    p.check("skills-version-check is invoked", "skills-version-check" in calls, str(calls))

    print("\nGREEN — a conformant estate adds nothing")
    probs, notes, _ = run_with(mod, {})
    p.check("both gates passing produces no problem", not probs, str(probs))
    p.check("both gates passing produces no note", not notes, str(notes))

    print("\nRED — a failing gate MUST become a doctor problem")
    for recipe in ("version-check", "skills-version-check"):
        probs, notes, _ = run_with(mod, {recipe: (1, "some finding\nlast line")})
        p.check(f"{recipe} exit 1 -> problem", len(probs) == 1, str(probs))
        p.check(f"  └─ the problem names the recipe",
                bool(probs) and recipe in probs[0], str(probs))
        p.check(f"  └─ and carries the gate's own output",
                bool(probs) and "last line" in probs[0], str(probs))

    probs, notes, _ = run_with(mod, {"version-check": (1, "a"), "skills-version-check": (1, "b")})
    p.check("both failing -> two problems, neither masked", len(probs) == 2, str(probs))

    print("\nTIMEOUT — unverified must NOT read as verified")
    probs, notes, _ = run_with(mod, {"skills-version-check": (124, "timed out")})
    p.check("a timeout is reported, not swallowed", bool(notes), str(notes))
    p.check("a timeout says UNVERIFIED rather than failing the estate",
            bool(notes) and "UNVERIFIED" in notes[0] and not probs, f"{notes} {probs}")

    print("\nMISSING COMMAND — the doctor must not crash (the 2026-08-06 defect)")
    probs, notes, _ = run_with(mod, {"version-check": (127, "just: not found")})
    p.check("exit 127 is a problem, not a traceback", len(probs) == 1, str(probs))

    print("\n" + "-" * 78)
    if p.failures:
        print(f"FAIL — {len(p.failures)} of {p.n} checks failed:", file=sys.stderr)
        for f in p.failures:
            print(f"  ✗ {f}", file=sys.stderr)
        return 1
    print(f"✅ {p.n} checks — a failing version gate becomes a doctor problem, a timeout becomes an")
    print("   explicit UNVERIFIED note, and a conformant estate stays quiet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
