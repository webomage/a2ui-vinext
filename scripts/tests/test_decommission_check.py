#!/usr/bin/env python3
"""Prove the decommission-drift gate REJECTS — fixtures only, no network, no live repo state.

The gate this tests was added because the estate's tombstone log and its drift check had ZERO
overlap: 5 tombstones nothing read, 2 hardcoded terms of which only one corresponded to a
tombstone. A join built to fix that is worthless if it cannot go red, so every rejection path
below is exercised against a fixture rather than against the live log — a suite that passes only
because today's estate happens to be clean is a suite that stops meaning anything the moment it is
not.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DC = ROOT / "scripts/decommission_check.py"

spec = importlib.util.spec_from_file_location("dc", DC)
dc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dc)


class P:
    def __init__(self): self.n = 0; self.fail: list[str] = []
    def check(self, label, ok, detail=""):
        self.n += 1
        print(f"  {label:<66} {'ok' if ok else '!! FAILED'}")
        if not ok: self.fail.append(f"{label} {detail}".strip())


def write(body: str) -> Path:
    f = Path(tempfile.mkdtemp()) / "DECOMMISSIONED.md"
    f.write_text(body, encoding="utf-8")
    return f


BLOCK = "```absent\n{}\n```\n"


def main() -> int:
    p = P()

    print("\nPARSING — a tombstone is only asserted if it SAYS something")
    log = write("# T\n\n## alpha — retired\n\n" + BLOCK.format('code: ["zzz"]') +
                "\n## beta — retired\n\nprose only, no block\n")
    a, missing = dc.load_assertions(log)
    p.check("a tombstone WITH an absent block is parsed", len(a) == 1, str(a))
    p.check("a tombstone WITHOUT one is reported, not skipped silently",
            missing == ["beta — retired"], str(missing))
    p.check("repos defaults to wom7web when unstated", a[0]["repos"] == ["wom7web"], str(a[0]))

    print("\nTHE EMPTY CORPUS MUST FAIL (it must never report a confident green over nothing)")
    empty = write("# T\n\nno tombstones at all\n")
    a2, _ = dc.load_assertions(empty)
    p.check("a log with no absent blocks parses to zero assertions", a2 == [], str(a2))
    sys.argv = ["x", "--log", str(empty)]
    p.check("...and main() EXITS 1 on it rather than passing", dc.main() == 1)

    print("\nPATH ASSERTIONS — a retirement that came back is caught")
    tmp = Path(tempfile.mkdtemp())
    (tmp / "resurrected").mkdir()
    back = dc.check({"tombstone": "x", "code": [], "repos": [], "except": [],
                     "path": [str(tmp / "resurrected")]})
    p.check("an existing path is a REGRESSION", back and not back[0][0], str(back))
    gone = dc.check({"tombstone": "x", "code": [], "repos": [], "except": [],
                     "path": [str(tmp / "never-existed")]})
    p.check("a missing path is clean", gone and gone[0][0], str(gone))

    print("\nEXCEPT — allowed, but it must justify itself")
    bad = dc.check({"tombstone": "x", "code": [], "repos": [], "path": [],
                    "except": [{"path": "a.ts"}]})
    p.check("an except with no `why` is REFUSED", bad and not bad[0][0], str(bad))
    bad2 = dc.check({"tombstone": "x", "code": [], "repos": [], "path": [],
                     "except": [{"why": "reasons"}]})
    p.check("an except with no `path` is REFUSED", bad2 and not bad2[0][0], str(bad2))

    print("\nSTALE EXCEPT — an acknowledgement that outlived its cause is drift")
    stale = dc.check({"tombstone": "x", "code": [], "repos": [], "path": [],
                      "except": [{"path": "nothing/matches.ts", "why": "documented"}]})
    p.check("an except matching nothing is reported STALE",
            any("STALE" in d for _, _, d in stale), str(stale))

    print("\nTHE LIVE LOG IS WELL-FORMED")
    live, live_missing = dc.load_assertions(dc.LOG)
    p.check("the real DECOMMISSIONED.md parses", len(live) > 0, str(len(live)))
    p.check("...and is NON-EMPTY, so the live run is a real assertion", len(live) >= 5, str(len(live)))
    p.check("every live tombstone carries an absent block", live_missing == [], str(live_missing))
    p.check("every live except states a why",
            all(e.get("why") for x in live for e in x["except"]),
            str([e for x in live for e in x["except"] if not e.get("why")]))

    print("\n" + "-" * 78)
    if p.fail:
        print(f"FAIL — {len(p.fail)} of {p.n}:")
        for f in p.fail: print(f"  ✗ {f}")
        return 1
    print(f"✅ decommission-check rejects as designed — {p.n}/{p.n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
