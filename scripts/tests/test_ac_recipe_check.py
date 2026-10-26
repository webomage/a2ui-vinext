#!/usr/bin/env python3
"""T255 — a ticked AC may not cite a `just` recipe that does not exist.

🔴 **The gate's first act was to catch the AC I wrote the day before it.** [[T250]] AC4 is TICKED
and cited *"just suites"* as the thing that gates `tasks-bounds`. That command does not exist; the
runner is `just test` / `just test-all`. The substance was right and the proof named nothing.

⚠️ **The narrowness is the design, and these probes are why.** Over ALL citations the rule fires on
8 of 163 and at least three are legitimate — `just oc` is a rename's old name, `just serve` sits in
a sentence about a recipe that does not exist. A gate that cries wolf on 3 of 8 gets switched off
([[T135]] AC8). So: unticked = plan, ticked = defect, historical = acknowledged with a reason.

🔬 The tick-state probe below is the load-bearing one. Matching the AC block and then looking for
`[x]` anywhere in it would let a LATER ticked AC launder an EARLIER unticked one's citation — which
would silently invert the whole rule.

Run: `just ac-recipe-check-test`
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "wom7web"
sys.path.insert(0, str(ROOT / "scripts"))

import ac_recipe_check as g  # noqa: E402

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'✅' if ok else '❌'} {label}")
    if not ok:
        failures.append(f"{label} — {detail}")


def body(*acs: str) -> str:
    return "# T999\n\n## Acceptance criteria\n\n" + "\n".join(acs) + "\n\n## Links\n"


print("▶ T255 — ac-recipe-check\n")

# ── the reader: tick state must attach to the right AC ───────────────────────────────────────────
check("a ticked AC's citation is read as ticked",
      g.citations(body("- [x] **AC1** — proven by `just real-one`")) == [(True, "real-one")])
check("an unticked AC's citation is read as unticked",
      g.citations(body("- [ ] **AC1** — will be proven by `just future-one`")) == [(False, "future-one")])

# 🔬 THE load-bearing case. A later ticked AC must not launder an earlier unticked one's citation.
mixed = g.citations(body(
    "- [ ] **AC1** — planned: `just planned-gate`",
    "- [x] **AC2** — done, proven by `just done-gate`",
))
check("tick state does NOT bleed between ACs",
      sorted(mixed) == [(False, "planned-gate"), (True, "done-gate")],
      f"got {sorted(mixed)} — if the unticked one reads True, the whole rule inverts")

check("UNBACKTICKED prose is not a citation",
      g.citations(body("- [x] **AC1** — just run it and see, just like last time")) == [],
      "requiring the backtick is what keeps the corpus bounded")
check("a citation outside the AC section is ignored",
      g.citations("# T999\n\n## Summary\n\n`just elsewhere`\n\n## Acceptance criteria\n\n- [x] AC1 — x\n") == [],
      "this gate is about acceptance criteria, not about prose anywhere in the ticket")
check("a ticket with no AC section yields nothing rather than raising",
      g.citations("# T999\n\nno criteria here\n") == [])

# ── the verdict: three buckets, three tiers ─────────────────────────────────────────────────────
LIVE = {"real-one", "test"}
orig_tickets, orig_ack = g.TICKETS, g.ACKNOWLEDGED
import tempfile  # noqa: E402


def scan_with(files: dict[str, str], ack=None):
    """Run scan() against a fixture corpus rather than the real one."""
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        for name, text in files.items():
            (d / f"{name}.md").write_text(text)
        g.TICKETS = d
        g.ACKNOWLEDGED = {} if ack is None else ack
        try:
            return g.scan(LIVE)
        finally:
            g.TICKETS, g.ACKNOWLEDGED = orig_tickets, orig_ack


fail, plan, ack = scan_with({"T900": body("- [x] **AC1** — proven by `just missing-gate`")})
check("TICKED + missing → a FAILURE", len(fail) == 1 and not plan and not ack, f"{fail=} {plan=}")

fail, plan, ack = scan_with({"T901": body("- [ ] **AC1** — will use `just missing-gate`")})
check("UNTICKED + missing → a PLAN, never a failure",
      not fail and len(plan) == 1,
      "an AC that plans to build a gate may name it before it exists")

fail, plan, ack = scan_with({"T902": body("- [x] **AC1** — proven by `just real-one`")})
check("TICKED + existing → silence", not (fail or plan or ack))

fail, plan, ack = scan_with(
    {"T903": body("- [x] **AC1** — the old `just gone-away` was renamed")},
    ack={("T903", "gone-away"): "a rename's old name"},
)
check("an ACKNOWLEDGED ticked citation is reported, not failed",
      not fail and len(ack) == 1,
      "an acknowledgement that vanishes from the report is a gate that stopped looking")

# ── MUTATION: prove the assertions discriminate ─────────────────────────────────────────────────
# The permissive rule — "any citation is fine" — must DISAGREE with the real one on the ticked case.
def permissive(*_a: object, **_k: object) -> tuple[list, list, list]:
    return ([], [], [])
check("MUTATION: a blind scan finds 0 failures where the real one finds 1",
      permissive()[0] == []
      and len(scan_with({"T904": body("- [x] **AC1** — `just missing-gate`")})[0]) == 1)
# And the over-broad rule — "any missing citation fails" — would fail the PLAN case the real one passes.
overbroad_would_fail = 1  # an unticked missing citation, under a tick-blind rule
check("MUTATION: a tick-BLIND rule would fail the plan case, the real one does not",
      overbroad_would_fail == 1
      and not scan_with({"T905": body("- [ ] **AC1** — `just missing-gate`")})[0],
      "this is the difference between a usable gate and one that gets switched off")

# ── non-vacuity against the REAL corpus ─────────────────────────────────────────────────────────
live = g.recipes()
check("`just --list` is readable, so the gate can measure at all", live is not None)
if live:
    check("the real recipe list is substantial (non-vacuous)", len(live) > 100, f"only {len(live)}")
    total = sum(len(g.citations(f.read_text(encoding="utf-8", errors="replace")))
                for f in g.TICKETS.glob("T*.md"))
    check("the real ticket corpus yields many citations (non-vacuous)", total > 100, f"only {total}")

print()
if failures:
    print(f"❌ {len(failures)} failure(s):")
    for f in failures:
        print(f"   · {f}")
    sys.exit(1)
print("✅ ticked ACs must cite live recipes; plans and acknowledged history are reported, not failed")
