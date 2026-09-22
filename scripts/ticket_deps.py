#!/usr/bin/env python3
"""T173 — make cross-ticket dependencies machine-readable, so the boards stop lying.

    python3 scripts/ticket_deps.py             # advisory, exits 0
    python3 scripts/ticket_deps.py --enforce   # exits 1 on a dangling/self/cyclic dep
    python3 scripts/ticket_deps.py --test      # red probes against fixtures, no repo data

🔑 **The defect this closes.** A ticket's remaining work is often owned by a DIFFERENT, unstarted
ticket, and that fact lives only in prose. The `sdlc` board then presents it as nearly done. Five
instances are on record:

    T22  AC4 → T8         (the guardrail; T22 is P1 and BLOCKED, T8 was untriaged until 2026-08-13)
    T20  AC4 → T7         (rolling-summary memory, written in the ticket as "= T7")
    T110 AC3 → D7/T104    ⚪ RESOLVED 2026-08-07 — D7 was stale and the AC is ticked. Recorded here
                             ONLY as a warning: re-adding it would resurrect a retired blocker.
    T167     → T165       (sequenced in T167's SUMMARY; missed by an agent reading the title)
    T117 AC9 → AC5        (stated in an AMENDMENT; offered to the owner as doable before it was read)

The last two were produced by agents *while working on this estate*, which is the argument for a
field over a convention: prose is not readable by the thing doing the ranking.

⚠️ **A dependency that RESOLVES must be removed, not left.** T110's own note records the cost of the
opposite: a blocker that had gone stale kept gating a P1. `--enforce` therefore fails on a
`blocked_by` pointing at a ticket that is already closed, exactly as it fails on a dangling one.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TICKETS = ROOT / ".tasks"
if not TICKETS.is_dir():
    sys.exit(f"FATAL: Canonical tickets directory not found at {TICKETS} (AgDR-0025: zero silent fallbacks)")
OPEN = {"queued", "in-progress", "blocked", "paused"}


def parse(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        return {}, text
    fm, body = text.split("---", 2)[1], text.split("---", 2)[2]
    d: dict[str, str] = {}
    for line in fm.splitlines():
        m = re.match(r"^(\w+):[ \t]*(.*)$", line)
        if m:
            d[m.group(1)] = m.group(2).strip().strip('"')
    return d, body


def load() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for f in sorted(TICKETS.glob("T*.md")):
        fmv, body = parse(f.read_text())
        if not fmv:
            continue
        tid = fmv.get("id") or f.stem
        out[tid] = {"fm": fmv, "body": body, "status": fmv.get("status", ""),
                    "blocked_by": [x.strip() for x in
                                   re.findall(r"[\w.]+", fmv.get("blocked_by", "")) if x.strip()]}
    return out


def findings(tk: dict[str, dict]) -> list[str]:
    out: list[str] = []
    for tid, t in sorted(tk.items()):
        for dep in t["blocked_by"]:
            if dep == tid:
                out.append(f"🔴 SELF-DEP    {tid} lists itself in blocked_by")
            elif dep not in tk:
                out.append(f"🔴 DANGLING    {tid} → {dep}: no such ticket. A dependency on nothing "
                           f"reads as a blocker forever")
            elif tk[dep]["status"] not in OPEN:
                out.append(f"🟡 RESOLVED    {tid} → {dep} is `{tk[dep]['status']}` — REMOVE it. "
                           f"A stale blocker gating live work is what T110/D7 cost")
    # cycles
    seen: set[str] = set()

    def walk(n: str, path: list[str]) -> None:
        if n in path:
            out.append(f"🔴 CYCLE       {' → '.join(path[path.index(n):] + [n])}")
            return
        if n in seen or n not in tk:
            return
        seen.add(n)
        for d in tk[n]["blocked_by"]:
            walk(d, path + [n])

    for tid in tk:
        walk(tid, [])
    return out


def main() -> int:
    if "--test" in sys.argv:
        return selftest()
    tk = load()
    if not tk:
        print("🔴 EMPTY CORPUS — 0 tickets parsed. Fix the loader; do not read this as 'no deps'.")
        return 1
    deps = {t: v["blocked_by"] for t, v in tk.items() if v["blocked_by"]}
    print(f"▶ T173 — ticket dependencies · {len(tk)} ticket(s) · "
          f"{len(deps)} declaring `blocked_by` · {sum(len(v) for v in deps.values())} edge(s)\n")
    for t, ds in sorted(deps.items()):
        for d in ds:
            st = tk[d]["status"] if d in tk else "MISSING"
            mark = "🔴" if d not in tk or tk[d]["status"] not in OPEN else "✅"
            print(f"  {mark} {t:6} blocked_by {d:6} ({st})")
    fs = findings(tk)
    print()
    if fs:
        for f in fs:
            print("  " + f)
        print(f"\n── {len(fs)} finding(s)." +
              ("" if "--enforce" in sys.argv else " Advisory: exits 0 (T135 AC8)."))
    else:
        print("  ✅ every declared dependency resolves to an open ticket; no cycles, no self-deps.")
    return 1 if (fs and "--enforce" in sys.argv) else 0


def selftest() -> int:
    """Red probes — fixtures only, no repo data. AC5: proven RED before green."""
    cases = [
        ("dangling",  {"T1": {"blocked_by": ["T999"], "status": "queued"}}, "DANGLING"),
        ("self-dep",  {"T1": {"blocked_by": ["T1"], "status": "queued"}}, "SELF-DEP"),
        ("resolved",  {"T1": {"blocked_by": ["T2"], "status": "queued"},
                       "T2": {"blocked_by": [], "status": "done"}}, "RESOLVED"),
        ("cycle",     {"T1": {"blocked_by": ["T2"], "status": "queued"},
                       "T2": {"blocked_by": ["T1"], "status": "queued"}}, "CYCLE"),
        ("clean",     {"T1": {"blocked_by": ["T2"], "status": "queued"},
                       "T2": {"blocked_by": [], "status": "queued"}}, None),
    ]
    print("▶ T173 — red probes for the dependency checker (fixtures, no repo data)\n")
    ok = 0
    for name, fx, want in cases:
        got = findings(fx)
        if want is None:
            passed = not got
            detail = "no findings, as required" if passed else f"unexpected: {got}"
        else:
            hits = [g for g in got if want in g]
            passed = bool(hits)
            detail = hits[0][:92] if hits else "NOTHING — the checker did not fire"
        ok += passed
        print(f"  {'✅' if passed else '🔴'} {name:10} {detail}")
    print(f"\n── {ok}/{len(cases)} probes behaved as specified.")
    return 0 if ok == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
