#!/usr/bin/env python3
"""Red probes for the deps-policy lockstep resolution.

Estate rule (T164 `sg-test`, T135 AC7): a gate with no test that makes it FAIL is a gate nobody
has proven works. `declared_version()` was changed on 2026-08-11 — lockstep previously read only
`pnpm.overrides`, which made it silently unusable for a direct dependency — so the new precedence
needs probes rather than a green run.

    python3 scripts/deps_sync_test.py     # exits 1 if any probe fails to fire

Offline: operates on package.json dicts in memory, no repo and no network.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from deps_sync import declared_version  # noqa: E402

Pkg = dict[str, object]

OV: Pkg = {"pnpm": {"overrides": {"x": "1.0.0"}}}
DEV: Pkg = {"devDependencies": {"x": "2.0.0"}}
DEP: Pkg = {"dependencies": {"x": "3.0.0"}}

CASES: list[tuple[str, Pkg, tuple[str | None, str]]] = [
    ("an override is found and named",
     OV, ("1.0.0", "pnpm.overrides")),

    ("a devDependency is found when there is no override — the wrangler case that "
     "returned None before 2026-08-11",
     DEV, ("2.0.0", "devDependencies")),

    ("a plain dependency is found when there is neither",
     DEP, ("3.0.0", "dependencies")),

    ("🔑 an override WINS over a devDependency — it is the stronger claim, forcing the "
     "whole transitive tree, and demoting it would silently weaken every existing entry",
     {**OV, **DEV}, ("1.0.0", "pnpm.overrides")),

    ("a devDependency wins over a dependency (the section pnpm itself prefers for tooling)",
     {**DEV, **DEP}, ("2.0.0", "devDependencies")),

    ("a repo that declares the dep NOWHERE reports None, so lockstep still fails loudly "
     "rather than treating 'absent' as 'agrees'",
     {}, (None, "dependencies")),

    ("an empty overrides block does not shadow a real devDependency",
     {"pnpm": {"overrides": {}}, **DEV}, ("2.0.0", "devDependencies")),
]


def main() -> int:
    fails: list[str] = []
    for name, pkg, expect in CASES:
        got = declared_version(pkg, "x")
        ok = got == expect
        print(f"{'✅' if ok else '🔴'} {name}")
        if not ok:
            fails.append(f"{name}\n     expected {expect!r}, got {got!r}")

    import unittest
    from tests.test_deps_sync import TestDepsSyncUpperBounds

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestDepsSyncUpperBounds)
    runner = unittest.TextTestRunner(verbosity=0)
    res = runner.run(suite)
    if not res.wasSuccessful():
        fails.append(f"TestDepsSyncUpperBounds failed ({len(res.failures)} failures, {len(res.errors)} errors)")
    else:
        print(f"✅ TestDepsSyncUpperBounds ({res.testsRun} unit & red-probe checks passed)")

    print(f"\n── {len(CASES) - len(fails)} of {len(CASES)} probes fired (+ {res.testsRun} unit checks).")
    for f in fails:
        print(f"\n🔴 {f}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
