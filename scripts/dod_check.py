#!/usr/bin/env python3
"""Every ticket with acceptance criteria has a Definition of Done, and it is not STALE.

🔴 Presence was never the problem. Measured 2026-08-25: **262 of 282 tickets already had a DoD**,
and all 20 without one were already `done`. What is unchecked is CURRENCY — and that is what fails.

Two went stale in a single day:
  · T267 — the DoD certified 7 of 8 ACs. It was written 2026-08-23 in the filing commit; AC8 was
    folded in 2026-08-24 and the DoD was never revisited.
  · T281 — it asserted a rule the owner had REJECTED mid-build, plus a condition a scheduled backup
    had already made unachievable.

Both were found only because a person asked. `ticket-schema-check` verifies the section EXISTS; it
cannot see whether it still describes the work.

🔑 The staleness test is: was an acceptance criterion ADDED in a commit LATER than the last commit
to touch the DoD block? If so the DoD certifies a SMALLER ticket than the one that now exists.

🔴 The first version of this check asked whether an AC was TICKED after the DoD, and reported 95
stale out of 261. That was the check being wrong, not the corpus: **ticking an AC after the DoD is
the normal, correct flow** — the DoD is written up front at `spec` and the ACs are ticked over the
following days. A gate that fires on the healthy path is worse than no gate; it would have been
switched off within a week (T135 AC8).

⚠️ It cannot catch a DoD that is wrong on the day it is written — T281's superseded clause was
edited into the same commits as the work, so this check would have passed it. Presence and freshness
are checkable; truth is not, and pretending otherwise would be the vacuous shape this estate hunts.

Run: `just dod-check`
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

def find_workspace_root(start_path: Path | None = None) -> Path:
    """Find the workspace root containing .tasks and .w0m/sdlc.json."""
    cur = (start_path or Path(__file__)).resolve()
    for parent in [cur] + list(cur.parents):
        if (parent / ".tasks").is_dir() and (parent / ".w0m").is_dir():
            return parent
        if (parent / ".git").exists() and (parent / "wom7web").is_dir():
            return parent
    return Path(__file__).resolve().parents[1]


ROOT = find_workspace_root()
WEB = ROOT / "wom7web" if (ROOT / "wom7web").is_dir() else ROOT
TICKETS = WEB / "project" / "tickets"
BASELINE = WEB / "project" / "dod-baseline.json"



def _norm(t: str) -> str:
    return " ".join(t.split()).lower()


def _dod_block(text: str) -> str:
    """The DoD section's body, or '' when absent."""
    out, on = [], False
    for ln in text.splitlines():
        if ln.startswith("## Definition of Done"):
            on = True; continue
        if on and ln.startswith("## "):
            break
        if on:
            out.append(ln.rstrip())
    return "\n".join(out).strip()


_AC_LINE = re.compile(r"^- \[.\] ")


def _ac_growth_all() -> dict[str, int]:
    """ticket stem -> newest commit time where its AC COUNT rose. ONE git call for the corpus.

    🔴 Was 261 separate `git log -p` calls and took 1:43 — too slow for a hook, and a slow hook is
    a bypassed hook. One pass over the whole directory, split by the `diff --git` headers, does the
    same work in seconds. The COUNT DELTA rule is unchanged; only the plumbing is.
    """
    try:
        r = subprocess.run(["git", "log", "-p", "--reverse", "--format=%at", "--", "."],
                           cwd=TICKETS, capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.SubprocessError):
        return {}
    grew: dict[str, int] = {}
    delta: dict[str, int] = {}
    t = 0
    cur = ""

    def flush() -> None:
        for stem, d in delta.items():
            if d > 0:
                grew[stem] = max(grew.get(stem, 0), t)
        delta.clear()

    for ln in r.stdout.splitlines():
        if re.fullmatch(r"\d{9,}", ln):
            flush(); t = int(ln); cur = ""; continue
        if ln.startswith("diff --git "):
            # 🔴 git prints REPO-RELATIVE paths even with cwd=TICKETS, so the line reads
            # `diff --git a/project/tickets/T1.md b/project/tickets/T1.md`. An earlier `b/(T\d+)`
            # matched nothing, AC_GROWTH came back EMPTY, every ticket read "never grew" and the
            # gate went permanently GREEN — caught only because stale jumped 17 -> 0 with no work
            # done. A ratchet that silently reads zero is the worst possible failure for a ratchet.
            m = re.search(r"/(T\d+)\.md$", ln)
            cur = m.group(1) if m else ""
            continue
        if not cur:
            continue
        if ln.startswith("+") and not ln.startswith("+++") and _AC_LINE.match(ln[1:]):
            delta[cur] = delta.get(cur, 0) + 1
        elif ln.startswith("-") and not ln.startswith("---") and _AC_LINE.match(ln[1:]):
            delta[cur] = delta.get(cur, 0) - 1
    flush()
    return grew


AC_GROWTH = _ac_growth_all()

# 🔴 NON-VACUITY GUARD. If the corpus-wide parse returns nothing, every ticket reads "never grew"
# and the stale count is 0 — a ratchet that has silently stopped measuring while reporting its best
# possible result. That happened on 2026-08-25: git prints repo-relative paths even with
# cwd=TICKETS, a `b/(T\d+)` pattern matched none of them, and stale went 17 -> 0 with no work done.
# ⇒ An empty parse is UNMEASURABLE (exit 2), never a pass. This is the one check that must run
# before any verdict.
if not AC_GROWTH and any(TICKETS.glob("T*.md")):
    print("\n  [UNMEASURABLE] the corpus-wide AC-history parse returned NOTHING while tickets exist.")
    print("     Every ticket would read 'never grew' and the stale count would be a false 0.")
    print("     Check the `diff --git` path pattern in _ac_growth_all().")
    print("\ndod-check: UNMEASURABLE (not a pass, and not a failure)")
    raise SystemExit(2)


def history(path: Path) -> tuple[int, int] | None:
    """(newest commit where the AC COUNT rose, newest commit where the DoD BODY changed).

    🔴 Fifth version of the staleness test. Each earlier one was rejected on a measurement:
      v1  "AC ticked after the DoD"      95/261 — ticking after the DoD is the NORMAL flow.
      v2  "AC line added"               158/261 — a tick rewrites the line, so it reads as added.
      v3  "new AC identifier appeared"  108/261 — counted the 2026-08-01 "backfill AC ids onto 232
          criteria" commit as scope; an identical 19.3d delta across T1-T11 gave it away.
      v4  count delta, DoD via diff      62/261 — the AC half was right; the DoD half only saw an
          edit when the `## Definition of Done` HEADING appeared as an ADDED line, so body-only
          rewrites were invisible. Caught on T281, whose DoD I had just rewritten and which still
          read stale.
    ⇒ v5 keeps the count delta (now corpus-wide in one call) and settles the DoD by HASHING the
    section at each commit — the only way to see a body-only edit. Pass 2 runs ONLY for tickets
    pass 1 already suspects.
    """
    grew = AC_GROWTH.get(path.stem, 0)
    if not grew:
        return (0, 1)                       # never grew -> cannot be stale
    name = path.name
    try:
        revs = subprocess.run(["git", "log", "--reverse", "--format=%H %at", "--", name],
                              cwd=path.parent, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    dod_touched, last = 0, None
    for line in revs.stdout.splitlines():
        sha, _, at = line.partition(" ")
        if not sha:
            continue
        try:
            blob = subprocess.run(["git", "show", f"{sha}:./{name}"],
                                  cwd=path.parent, capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            return None
        cur = _dod_block(blob.stdout) if blob.returncode == 0 else ""
        if cur != last:
            dod_touched = int(at)
            last = cur
    return (grew, dod_touched)


_ap = argparse.ArgumentParser(description="DoD presence, currency and vacuity")
_ap.add_argument("--ticket", help="check ONE ticket and exit non-zero if it fails "
                                  "(the form the `spec` gate calls)")
ARGS = _ap.parse_args()
ONLY = (ARGS.ticket or "").strip().upper() or None

missing: list[str] = []
stale: list[str] = []
shared: list[str] = []
_bodies: dict[str, list[str]] = {}
unmeasurable: list[str] = []
ok = 0


for f in sorted(TICKETS.glob("T*.md"), key=lambda p: int(p.stem[1:])):
    txt = f.read_text(encoding="utf-8")
    body = txt.split("---", 2)[2] if txt.count("---") >= 2 else txt
    if not re.search(r"^- \[.\] ", body, re.M):
        continue                                    # no ACs -> no DoD required
    if "## Definition of Done" not in body:
        if not ONLY or f.stem == ONLY:
            missing.append(f.stem)
        continue

    # 🔴 A DoD shared verbatim with other tickets is not a Definition of Done — it is a template
    # nobody replaced. Measured 2026-08-25: 129 of 282 tickets (46%) carried one identical process
    # checklist ("spec verified, tests/skills mapped, ecosystem + security checks passed…"), which
    # says nothing about what any of them is FOR. The standard requires the ticket's own domain
    # language; a sentence 129 tickets share cannot be it.
    _bodies.setdefault(_norm(_dod_block(txt)), []).append(f.stem)

    if ONLY and f.stem != ONLY:
        continue                                  # vacuity was already collected above
    h = history(f)
    if h is None:
        # 🔑 Its own state, never folded into a pass or a failure (T242's rule).
        unmeasurable.append(f.stem)
        continue
    ac_added, dod_touched = h
    if ac_added and dod_touched and ac_added > dod_touched:
        days = (ac_added - dod_touched) / 86400
        stale.append(f"{f.stem} (scope GREW {days:.1f}d after the DoD was last touched)")
    else:
        ok += 1

for _body, _ids in _bodies.items():
    if len(_ids) > 1 and len(_body) > 40:
        shared.extend(_ids if not ONLY else [i for i in _ids if i == ONLY])

if ONLY:
    # 🔑 The `spec` gate's form: one ticket, one verdict, non-zero on failure. A DoD shared with
    # other tickets is the common case at this gate — the template is what a new ticket starts
    # with, and replacing it is the work the gate exists to require.
    print(f"\nDefinition of Done -- {ONLY}\n")
    if ONLY in missing:
        print(f"  [MISSING] {ONLY} has acceptance criteria and no Definition of Done")
    elif ONLY in shared:
        n = max(len(v) for k, v in _bodies.items() if ONLY in v)
        print(f"  [SHARED]  {ONLY}'s DoD is byte-identical to {n - 1} other ticket(s).")
        print("            That is the template, not a Definition of Done. Write what must be")
        print("            observably true for THIS ticket, in its own domain language.")
    elif any(s_.startswith(ONLY + " ") for s_ in stale):
        print(f"  [STALE]   {next(s_ for s_ in stale if s_.startswith(ONLY + ' '))}")
        print("            Scope grew past the DoD. Update it in the same commit as the change.")
    else:
        print(f"  [OK] {ONLY} carries a DoD that is its own, and no newer than its scope.")
        raise SystemExit(0)
    print("\n  See `openspec/SPEC-AUTHORING-STANDARD.md` -> Ticket entities.")
    raise SystemExit(1)

print("\nDefinition of Done -- presence, currency and vacuity\n")
print(f"  {ok} current · {len(stale)} stale · {len(missing)} missing · "
      f"{len(shared)} shared-boilerplate · {len(unmeasurable)} unmeasurable")
if shared:
    groups = sorted(((len(v), v) for k, v in _bodies.items() if len(v) > 1 and len(k) > 40),
                    reverse=True)
    for n, ids in groups[:3]:
        print(f"  [SHARED]  {n} tickets carry one identical DoD: {', '.join(ids[:8])}"
              f"{' …' if n > 8 else ''}")
for m in missing:
    print(f"  [MISSING] {m} has acceptance criteria and no Definition of Done")
for s in stale[:20]:
    print(f"  [STALE]   {s}")
if len(stale) > 20:
    print(f"            ... and {len(stale) - 20} more")
for u in unmeasurable[:5]:
    print(f"  [UNMEASURABLE] {u} -- git blame could not be read; NOT counted as a pass")

# ── the ratchet (T242, blocking from 2026-08-25) ─────────────────────────────────────────────
# 🔴 Blocking on the ABSOLUTE numbers would fail every push on 155 findings. The estate's answer
# to that is a downward-only baseline, the same shape as `md_headings_estate`: the numbers may
# fall freely and may never rise. `missing` is a hard zero rather than a ratchet.
# ⚠️ Raising a baseline to go green is the same act as deleting a failing test.
print()
try:
    _RATCHET = json.loads(BASELINE.read_text(encoding="utf-8"))["ratchet"]
except (OSError, ValueError, KeyError) as _e:
    # An unreadable baseline is UNMEASURABLE, never a pass — the T242 rule.
    print(f"  [UNMEASURABLE] {BASELINE.name} could not be read -- {_e}")
    print("\ndod-check: UNMEASURABLE (not a pass, and not a failure)")
    raise SystemExit(2)

_now = {"missing": len(missing), "stale": len(stale), "shared": len(shared)}
_rose = []
for _k, _cfg in _RATCHET.items():
    _base, _got = int(_cfg["baseline"]), _now.get(_k, 0)
    # 🔑 `[OK]` / `[FAIL]` EXACTLY — `run_suites.py:55` counts `^\s*\[(?:OK|PASS|FAIL)\]\s`, and
    # a padded `[OK  ]` matches none of it. The first blocking run reported "1 suite(s) passed with
    # an UNREADABLE check count", which is the runner correctly refusing to distinguish this from a
    # suite that exited 0 having asserted nothing.
    _mark = "OK" if _got <= _base else "FAIL"
    _arrow = "=" if _got == _base else ("v" if _got < _base else "^")
    print(f"  [{_mark}] {_k:8} {_got:4} {_arrow} baseline {_base}"
          + ("   HARD ZERO" if _cfg.get("hard_zero") else ""))
    if _got > _base:
        _rose.append(f"{_k}: {_got} > {_base}")

if _rose:
    print()
    for _r in _rose:
        print(f"  [BLOCKED] {_r}")
    print("\n  A DoD ratchet only ever falls. Fix the ticket -- do NOT raise the baseline in")
    print("  project/dod-baseline.json; that is the same act as deleting a failing test.")
    print("\ndod-check: FAILED -- the ratchet rose.")
    raise SystemExit(1)

_fell = [k for k, c in _RATCHET.items() if _now.get(k, 0) < int(c["baseline"])]
if _fell:
    print(f"\n  [LOWER] {', '.join(_fell)} fell below baseline -- lower it in "
          f"project/dod-baseline.json so the gain is kept.")

print(f"\ndod-check: OK -- ratchet held ({ok} current). "
      f"{len(stale)} stale and {len(shared)} shared remain, both paid down at the `spec` gate.")
raise SystemExit(0)
