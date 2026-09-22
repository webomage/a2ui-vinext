#!/usr/bin/env python3
"""T72 AC4 — the retired spec systems stay retired, and no new dialect lands undeclared.

    python3 scripts/spec_systems_gate.py             # advisory, exits 0
    python3 scripts/spec_systems_gate.py --enforce   # exits 1 on a finding
    python3 scripts/spec_systems_gate.py --selftest  # red-probes itself

🔑 **The failure this guards is an agent believing a legacy spec.** Three parallel spec systems
coexisted for a year, one of them a DSL citing a `src/lib/models` that does not exist, and nothing
stopped an agent from reading it as truth. Deleting them was the easy half; keeping them deleted is
this file.

**The decided authority** (`openspec/SPEC-AUTHORING-STANDARD.md`):
  · **OpenSpec** specifies CHANGES · **Gauge** (`*.spec`) specifies TESTS — both standard, not rivals
  · Gherkin (`*.feature`) is a **customer-project** tool and must not appear in a `w0m7*` repo
  · `.agent/specs/system_v1.md` and `wom7ext/.windsurf/` are RETIRED

⚠️ **GAUGE IS A KEEPER AND THIS GATE MUST NEVER FLAG IT.** 381 `.spec` files are the executable
test corpus. T72's own title — *"Consolidate spec systems"* — invites deleting them, so the probe
below asserts that a `.spec` file raises NOTHING. A gate that counted them as a rival system would
delete the estate's entire test suite while reporting success.

⚠️ **`.agent/` IS ANTIGRAVITY'S LIVE SURFACE.** Only `.agent/specs/system_v1.md` was retired. An
agent has already deleted a client's whole `.agent/` on a narrower warning, so this gate names one
file and never the directory.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ESTATE = Path(__file__).resolve().parents[1]
W0M_REPOS = ["wom7web", "wom7api", "wom7func", "wom7ext", "wom7mlx", "wom7sec", "wom7skills"]

# Exact paths, never directories — see the docstring's `.agent/` warning.
RETIRED = [
    ("wom7web/.agent/specs/system_v1.md", "the system_v1 DSL (cites a nonexistent `src/lib/models`)"),
    ("wom7ext/.windsurf", "the speckit workflows (all 9 referenced a `.specify/` scaffold that is gone)"),
]
SKIP = {"node_modules", "dist", ".git", "build", ".astro", ".wrangler", ".svelte-kit"}


def gherkin_in_w0m() -> list[Path]:
    """`.feature` files inside a w0m repo — drift by the standing decision."""
    out = []
    for repo in W0M_REPOS:
        root = ESTATE / repo
        if not root.is_dir():
            continue
        out += [p for p in root.rglob("*.feature") if not (SKIP & set(p.parts))]
    return sorted(out)


def selftest() -> int:
    """🔴 Red-probe: the gate must FIRE on a reappearance and stay silent on a Gauge spec."""
    import tempfile
    fails = []

    def check(label, ok):
        print(f"  {'✅' if ok else '❌'} {label}")
        if not ok:
            fails.append(label)

    with tempfile.TemporaryDirectory() as tmp:
        fake = Path(tmp)
        (fake / "wom7web/.agent/specs").mkdir(parents=True)
        (fake / "wom7web/.agent/specs/system_v1.md").write_text("# resurrected")
        (fake / "wom7ext").mkdir(parents=True)
        (fake / "wom7ext/x.feature").write_text("Feature: drift")
        (fake / "wom7web/specs").mkdir(parents=True)
        (fake / "wom7web/specs/keeper.spec").write_text("# Gauge spec — MUST NOT be flagged")

        global ESTATE
        real, ESTATE = ESTATE, fake
        try:
            found = [rel for rel, _ in RETIRED if (ESTATE / rel).exists()]
            check("a resurrected `system_v1.md` is caught",
                  "wom7web/.agent/specs/system_v1.md" in found)
            g = gherkin_in_w0m()
            check("a `.feature` inside a w0m repo is caught", len(g) == 1)
            check("🔑 a Gauge `.spec` raises NOTHING — it is the test corpus, not a rival",
                  not any(p.suffix == ".spec" for p in g))
            (ESTATE / "wom7ext/x.feature").unlink()
            (ESTATE / "wom7web/.agent/specs/system_v1.md").unlink()
            check("a clean tree reports clean",
                  not gherkin_in_w0m() and not [r for r, _ in RETIRED if (ESTATE / r).exists()])
        finally:
            ESTATE = real

    print()
    if fails:
        print(f"❌ {len(fails)} self-test failure(s)")
        return 1
    print("✅ spec-systems: the gate is proven to fire, and proven not to flag Gauge")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="T72 AC4 — retired spec systems stay retired")
    ap.add_argument("--enforce", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()

    print("▶ T72 — spec-system authority\n")
    resurrected = [(rel, why) for rel, why in RETIRED if (ESTATE / rel).exists()]
    gherkin = gherkin_in_w0m()

    # An empty corpus means the scan is broken, not that the estate is clean.
    spec_count = sum(1 for r in W0M_REPOS
                     for p in (ESTATE / r).rglob("*.spec") if not (SKIP & set(p.parts))) \
        if (ESTATE / "wom7web").is_dir() else 0
    if spec_count == 0:
        print("  🔴 EMPTY CORPUS — 0 Gauge `.spec` files found across the estate. The scan is "
              "broken; do not read this as 'no spec systems'.")
        return 1
    print(f"  ✅ Gauge intact — {spec_count} `.spec` file(s), the executable test corpus (KEEPER)")

    if resurrected:
        print(f"\n  🔴 RETIRED SYSTEM IS BACK: {len(resurrected)}")
        for rel, why in resurrected:
            print(f"       {rel}\n         └ {why}")
    else:
        print("  ✅ both retired systems are still gone")

    if gherkin:
        by_repo: dict[str, int] = {}
        for p in gherkin:
            by_repo[p.relative_to(ESTATE).parts[0]] = by_repo.get(p.relative_to(ESTATE).parts[0], 0) + 1
        print(f"\n [MED] GHERKIN IN A w0m REPO: {len(gherkin)} file(s) — "
              + ", ".join(f"{k} {v}" for k, v in sorted(by_repo.items())))
        print("       Gherkin is a CUSTOMER-PROJECT tool by standing decision; inside w0m it "
              "migrates to Gauge.")
        print(" [WARN] These RUN (`cucumber-js` is wired as `test:e2e`) — migrate, do not delete.")
        for p in gherkin[:6]:
            print(f"         · {p.relative_to(ESTATE)}")
        if len(gherkin) > 6:
            print(f"         …and {len(gherkin) - 6} more")
    else:
        print("  ✅ no Gherkin inside any w0m repo")

    n = len(resurrected) + len(gherkin)
    print(f"\n── {len(resurrected)} resurrection(s), {len(gherkin)} Gherkin file(s)."
          + ("" if args.enforce else " Advisory: exits 0."))
    # 🔴 Only a RESURRECTION gates. The Gherkin backlog is pre-existing and migrating 16 running
    # e2e specs is its own piece of work — gating on it would install a red check nobody can clear
    # in one push, which is how a gate teaches people to route around it (T135 AC8).
    return 1 if (resurrected and args.enforce) else 0


if __name__ == "__main__":
    raise SystemExit(main())
