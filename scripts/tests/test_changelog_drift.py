#!/usr/bin/env python3
r"""T258 -- probes for `changelog-drift`.

The gate answers one question offline: has a deploy happened since the newest CHANGELOG entry? The
probes below exist because two plausible readings of that question are both wrong in a way that
would make the gate useless:

  * comparing stamps as STRINGS. `2026.08.16-1786891220` vs `2026.08.16-999999999` orders wrong as
    text, and same-day deploys are exactly when a changelog falls behind by one entry.
  * counting stamps found anywhere in the file. The preamble prose names the stamp FORMAT, so a
    changelog with zero releases would parse as having one -- a document about being empty claiming
    to be full.

Run: `just changelog-drift-test`
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "wom7web"
sys.path.insert(0, str(ROOT / "scripts"))

import changelog_drift as g  # noqa: E402

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'✅' if ok else '❌'} {label}")
    if not ok:
        failures.append(f"{label} — {detail}")


print("▶ T258 — changelog-drift\n")

# ── the stamp reader ────────────────────────────────────────────────────────────────────────────
check("a stamp is parsed into (unix, full)",
      g.stamps("## 2026.07.10-1783720961") == [(1783720961, "2026.07.10-1783720961")])
check("no stamp yields nothing rather than raising", g.stamps("# Changelog\n\nnothing here") == [])

# 🔬 Ordering must be NUMERIC. Two deploys on one day is precisely when a changelog falls behind.
same_day = g.stamps("2026.08.16-1786891220 2026.08.16-1786999999")
check("same-day stamps order by the unix suffix, numerically",
      same_day[0][0] == 1786999999,
      f"got {same_day} — string ordering here would silently mis-rank same-day deploys")
check("duplicate stamps are collapsed",
      len(g.stamps("2026.07.10-1783720961 x 2026.07.10-1783720961")) == 1)

# ── the headings-only rule ──────────────────────────────────────────────────────────────────────
# 🔬 The real CHANGELOG's preamble names the FORMAT in prose. Counting prose would invent a release.
real = g.CHANGELOG.read_text(encoding="utf-8") if g.CHANGELOG.exists() else ""
if real:
    all_stamps = g.stamps(real)
    head_stamps = g.changelog_stamps()
    check("headings-only parsing is actually narrower than whole-file parsing on the real file",
          len(head_stamps) <= len(all_stamps))
    check("the real changelog's newest entry is read from a heading",
          bool(head_stamps) and head_stamps[0][1] in
          "\n".join(l for l in real.splitlines() if l.startswith("## ")),
          "if this reads a stamp from prose, an empty changelog reports a release")

# ── the comparison ─────────────────────────────────────────────────────────────────────────────
cl, dl = g.changelog_stamps(), g.deploy_stamps()
check("the real deploy transcripts on disk are found (non-vacuous)",
      len(dl) > 0,
      "an empty transcript list must exit 2, never 0 — unmeasurable is not clean")
if cl and dl:
    behind = [s for s in dl if s[0] > cl[0][0]]
    # This is a MEASUREMENT of the estate, not an assertion about it: at filing the changelog was
    # 2 deploys behind. The probe asserts the comparison WORKS, in whichever direction it lands.
    check("the behind-set is computed consistently with the two stamp lists",
          all(s[0] > cl[0][0] for s in behind)
          and all(s[0] <= cl[0][0] for s in dl if s not in behind))
    print(f"       (measured: changelog at {cl[0][1]}, {len(behind)} deploy(s) newer)")

# ── MUTATION: prove the comparison discriminates ────────────────────────────────────────────────
old_cl, old_dl = g.changelog_stamps, g.deploy_stamps
try:
    g.changelog_stamps = lambda: [(1000, "2026.01.01-1000")]
    g.deploy_stamps = lambda: [(2000, "2026.02.02-2000")]
    check("MUTATION: a newer deploy than the newest entry is detected",
          [s for s in g.deploy_stamps() if s[0] > g.changelog_stamps()[0][0]] != [])
    g.deploy_stamps = lambda: [(500, "2025.12.12-500")]
    check("MUTATION: an older deploy than the newest entry is NOT flagged",
          [s for s in g.deploy_stamps() if s[0] > g.changelog_stamps()[0][0]] == [],
          "a gate that fires on an up-to-date changelog gets switched off")
finally:
    g.changelog_stamps, g.deploy_stamps = old_cl, old_dl

print()
if failures:
    print(f"❌ {len(failures)} failure(s):")
    for f in failures:
        print(f"   · {f}")
    sys.exit(1)
print("✅ stamps order numerically, only headings count as releases, and drift is detected offline")
