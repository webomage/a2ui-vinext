#!/usr/bin/env python3
"""`spec-drift`'s ownership rule — HARD only when EVERY owner is done.

🔴 **This gate had no test at all until 2026-08-22, and the rule it lacked a test for was wrong.**
It fired HARD on *any* done owner, and its remedy was *"archive the change"*.
`2026-07-11-client-conversion-and-contracts` is owned via `spec:` by **five** tickets and sits at
**0/25 tasks**; closing [[T2]] legitimately at 6/6 made the gate demand that a change with **four
open owners and no work done** be archived — to unblock a push.

⚠️ That is the failure mode worth naming: **a gate whose remedy is worse than its finding still gets
obeyed**, because the push is what the person came for. The dangerous outcome was not the false
positive, it was the instruction attached to it.

The intent is preserved rather than weakened, and both arms are asserted below: all-owners-done
still blocks; partial closure reports and says *do NOT archive*.

Run: `just spec-drift-ownership-test`
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "w0m-web"
sys.path.insert(0, str(ROOT / "scripts"))

import spec_drift_gate as g  # noqa: E402

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'✅' if ok else '❌'} {label}")
    if not ok:
        failures.append(f"{label} — {detail}")


def levels(refs, done=0, total=25):
    return [lvl for lvl, _ in g.ownership_verdict("a-change", refs, done, total)]


def message(refs, done=0, total=25):
    out = g.ownership_verdict("a-change", refs, done, total)
    return out[0][1] if out else ""


print("▶ spec-drift — the ownership rule\n")

# ── the real case that must STILL block ─────────────────────────────────────────────────────────
check("ALL owners done → HARD (spec-only-actually-built really is drift)",
      levels([("T2", "done")]) == ["HARD"], f"got {levels([('T2', 'done')])}")
check("ALL of several owners done → HARD",
      levels([("T2", "done"), ("T3", "done")]) == ["HARD"])
check("the HARD message says ALL, so the remedy is unambiguous",
      "ALL owning ticket(s)" in message([("T2", "done")]))

# ── 🔴 the false positive that was blocking a legitimate close ───────────────────────────────────
REAL = [("T2", "done"), ("T3", "queued"), ("T4", "queued"), ("T5", "queued"), ("T6", "queued")]
check("one done owner among four open → WARN, never HARD (the live T2 case)",
      levels(REAL) == ["WARN"], f"got {levels(REAL)}")
check("the WARN says DO NOT ARCHIVE — the remedy is the dangerous half",
      "do NOT archive" in message(REAL),
      "archiving a 0/25 change with four open owners is what the old rule instructed")
check("the WARN names both sides, so a reader can judge it",
      "T2" in message(REAL) and "T3" in message(REAL))

# ── neutral and edge cases ──────────────────────────────────────────────────────────────────────
check("no owners at all → this rule says nothing (the orphan WARN is a different rule)",
      levels([]) == [])
check("all owners open → nothing",
      levels([("T3", "queued"), ("T4", "in-progress")]) == [])
for st in ("in-progress", "blocked", "paused", "queued"):
    check(f"`{st}` counts as OPEN, not done",
          levels([("T2", "done"), ("T9", st)]) == ["WARN"],
          f"a {st} owner must keep the change out of HARD")

# ── MUTATION: prove the assertions discriminate ──────────────────────────────────────────────────
# The pre-fix rule: HARD on any done owner. It must DISAGREE with the current one on the live case,
# or these assertions are measuring nothing.
def old_rule(refs: list[tuple[str, str]]) -> list[str]:
    return ["HARD"] if any(st == "done" for _, st in refs) else []
check("MUTATION: the OLD rule would have fired HARD on the live case",
      old_rule(REAL) == ["HARD"])
check("MUTATION: the new rule does not — so the fix is real, not cosmetic",
      levels(REAL) != ["HARD"])
check("MUTATION: and both rules still agree when ALL owners are done",
      old_rule([("T2", "done")]) == levels([("T2", "done")]) == ["HARD"],
      "weakening the rule must not have removed the case it exists for")

# ── SPEC_CHANGE: a ticket may own MORE THAN ONE change ───────────────────────────────────────────
# The parser was `spec.split("openspec/changes/")[-1]`, which returns only the LAST path. A `spec:`
# naming two changes had every earlier one attributed to nobody — and "no owning ticket" is a WARN,
# so the loss never blocked anything. Found 2026-08-29: T117 declares two changes and only the
# trailing one counted, which meant the same-day fix for T102 worked ONLY because the new path was
# appended last rather than prepended.
TWO = ('../../docs/design/T117-rbac-unified-axes.md (design, migrated out 2026-07-22) '
       '+ openspec/changes/2026-07-22-rbac-unified-axes '
       '+ openspec/changes/2026-07-16-rbac-capability-model')
check("both changes in a two-change spec field are seen",
      g.SPEC_CHANGE.findall(TWO)
      == ["2026-07-22-rbac-unified-axes", "2026-07-16-rbac-capability-model"])
check("a single-change spec field still resolves",
      g.SPEC_CHANGE.findall("openspec/changes/2026-07-16-rbac-capability-model")
      == ["2026-07-16-rbac-capability-model"])
check("a spec field naming no change yields none",
      g.SPEC_CHANGE.findall("../../docs/design/T117-rbac-unified-axes.md") == [])
check("a trailing slash does not become part of the name",
      g.SPEC_CHANGE.findall("openspec/changes/a-change/") == ["a-change"])
check("a deeper path resolves to the change directory, not the file",
      g.SPEC_CHANGE.findall("openspec/changes/a-change/tasks.md") == ["a-change"])

# MUTATION: the old parser must DISAGREE on the two-change case, or this proves nothing.
def old_parse(s: str) -> list[str]:
    return ([s.rstrip("/").split("openspec/changes/")[-1].split("/")[0]]
            if "openspec/changes/" in s else [])
check("MUTATION: the OLD parser saw only the last of the two",
      old_parse(TWO) == ["2026-07-16-rbac-capability-model"])
check("MUTATION: the new parser disagrees with it — the fix is real",
      g.SPEC_CHANGE.findall(TWO) != old_parse(TWO))
check("MUTATION: and both still agree on the single-change case",
      g.SPEC_CHANGE.findall("openspec/changes/a-change")
      == old_parse("openspec/changes/a-change") == ["a-change"])

# ── T77 Gate Graduation & Recommendations (2026-10-01) ───────────────────────────
check("partial closure message contains 'do NOT archive'",
      all("do NOT archive" in m for _, m in g.ownership_verdict("a-change", REAL, 0, 25)))
check("active_changes excludes 'archive'",
      "archive" not in g.active_changes())

print()
if failures:
    print(f"❌ {len(failures)} failure(s):")
    for f in failures:
        print(f"   · {f}")
    sys.exit(1)
print("✅ HARD requires every owner done; partial closure reports and refuses to recommend archiving; T77 gate graduated")
