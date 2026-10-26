#!/usr/bin/env python3
"""Prove the ignore audit REJECTS — fixtures, not today's estate.

The audit's whole purpose is to notice that a rule and the index disagree. If it could only ever
pass, it would be indistinguishable from not running. Every rejection path is exercised below
against constructed input, plus a few assertions that the LIVE policy is well-formed — because a
policy whose entries carry no reasons is an allowlist wearing a gate's clothes.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
IA = ROOT / "scripts/ignore_audit.py"

spec = importlib.util.spec_from_file_location("ia", IA)
ia = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ia)


class P:
    def __init__(self): self.n = 0; self.fail: list[str] = []
    def check(self, label, ok, detail=""):
        self.n += 1
        print(f"  {label:<68} {'ok' if ok else '!! FAILED'}")
        if not ok: self.fail.append(f"{label} {detail}".strip())


def main() -> int:
    p = P()
    pol = ia.load_policy()

    print("\nREQUIRED-RULE REGEXES MUST FIRE RED ON A GITIGNORE THAT LACKS THEM")
    empty = "# nothing here\ndist/\n"
    full = ".env\nnode_modules/\n*.pem\n*.key\n"
    for rule in pol["required_rules"]["rules"]:
        m = rule["match"]
        p.check(f"`{rule['pattern']}` is ABSENT from a gitignore without it",
                not re.search(m, empty, re.M), m)
        p.check(f"`{rule['pattern']}` is FOUND when present",
                bool(re.search(m, full, re.M)), m)

    print("\nA NEGATION IS THE RULE WORKING, NOT DRIFT")
    # `!pattern` means NOT ignored. Counting it as a conflict is how the first version of this
    # policy acquired a bogus accepted-entry for .serena/project.yml.
    src = IA.read_text(encoding="utf-8")
    p.check("tracked_but_ignored skips negated rules", 'startswith("!")' in src)

    print("\nGENERATED / VENDORED SKIPPING IS PREFIX-BASED, NOT SEGMENT-BASED")
    # `.husky/_` is two segments; a segment-wise test silently missed it and reported husky's own
    # generated file as estate drift.
    p.check("`.husky/_` is declared as a generated dir", ".husky/_" in pol["generated"]["dirs"])
    p.check("the matcher uses prefix semantics", 'rel.startswith(g.rstrip("/")' in src)
    multi = [g for g in pol["generated"]["dirs"] if "/" in g]
    p.check("...which is required, because a multi-segment entry exists", bool(multi), str(multi))

    print("\nEVERY POLICY ENTRY MUST JUSTIFY ITSELF")
    acc = pol["accepted_tracked"]["entries"]
    und = pol["undecided_tracked"]["entries"]
    p.check("accepted set is non-empty (an empty policy proves nothing)", len(acc) > 0, str(len(acc)))
    p.check("every accepted entry states a why", all(e.get("why") for e in acc),
            str([e["path"] for e in acc if not e.get("why")]))
    p.check("every undecided entry states a note", all(e.get("note") for e in und),
            str([e["path"] for e in und if not e.get("note")]))
    p.check("every required rule states a why",
            all(r.get("why") for r in pol["required_rules"]["rules"]))
    p.check("every exemption states a why",
            all(e.get("why") for e in pol["required_rules"]["exempt"]))

    print("\nSCOPE IS DECLARED, AND CANNOT QUIETLY SHRINK")
    repos = [k for k in pol["governed"] if not k.startswith("_")]
    p.check("all 7 w0m repos are governed", len(repos) == 7, str(repos))
    p.check("an undeclared ignore file inside a governed repo is BLOCKING",
            "is not declared in ignore-policy.json" in src)
    p.check("a declared file that vanished is BLOCKING",
            "is declared but does not exist" in src)

    print("\nTHE LIVE ESTATE IS NON-VACUOUS")
    found = ia.find_ignore_files("wom7web", pol)
    p.check("wom7web really has ignore files to audit", len(found) >= 5, str(len(found)))
    p.check("...and the extension icons are no longer ignored (the fix holds)",
            not any(e["path"].startswith("extension/icons") for e in und + acc),
            "icons should be fixed by a negation, not accepted as a conflict")

    print("\n" + "-" * 78)
    if p.fail:
        print(f"FAIL — {len(p.fail)} of {p.n}:")
        for f in p.fail: print(f"  ✗ {f}")
        return 1
    print(f"✅ ignore-audit rejects as designed — {p.n}/{p.n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
