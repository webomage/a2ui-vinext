#!/usr/bin/env python3
"""Red probes for `debt_register_check.py`.

🔴 **This gate was wired BLOCKING on pre-push before it had a single probe.** That is the exact
rule `LESSONS.md` states — *"every gate ships with probes that prove it goes red"* — broken by the
person who wrote the rule down, in the same session. It is here now because a blocking gate nobody
has watched fail is indistinguishable from one whose regex silently stopped matching.

The probes that matter are the **false-alarm regressions**, because this checker has already raised
two rounds of them against the real register:

  1. It matched every `T##` in a row's PROSE instead of the `Tracked` column, and flagged
     **41 of 48 rows**. An 85% hit rate is a broken check, not a rotten register.
  2. It matched "resolved"/"closed" anywhere in a row and flagged **7, of which 6 were false** —
     including **D48's "🔴 NOT RESOLVED"**, the exact inverse of the finding it claimed.

Offline: every case is a synthetic register in a temp dir. Run: `just debt-check-test`.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "debt_register_check.py"

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'[OK]' if ok else '[FAIL]'} {label}")
    if not ok:
        failures.append(f"{label}{(' — ' + detail) if detail else ''}")


# ⚠️ The REAL register's columns, exactly: `| ID | Area | Debt | Impact | Tracked |`. The first
# draft of this fixture omitted `Area`, which shifted every cell by one — so the probe read the
# Impact column as Debt and the Added column as Tracked, and reported the GATE as broken when the
# fixture was. A probe built on a guessed schema tests the guess.
HEADER = "| ID | Area | Debt | Impact | Tracked |\n|---|---|---|---|---|\n"


def run(
    rows: str,
    extra_files: dict[str, str] | None = None,
    require_surfaces: bool = False,
) -> tuple[int, str]:
    """Run the checker against a synthetic register, via its REPO constant."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".tasks").mkdir(parents=True)
        (root / "TECH-DEBT.md").write_text(HEADER + rows, encoding="utf-8")
        # A real, live ticket so "tracked by something open" is expressible.
        (root / ".tasks" / "T900.md").write_text("---\nid: T900\nstatus: in-progress\n---\n")
        (root / ".tasks" / "T901.md").write_text("---\nid: T901\nstatus: done\n---\n")
        if extra_files:
            for rel, content in extra_files.items():
                p = root / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content, encoding="utf-8")
        probe = root / "probe.py"
        probe.write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
        import os
        env = {**os.environ, "W0M_WORKSPACE_ROOT": str(root)}
        if require_surfaces:
            env["W0M_REQUIRE_SURFACES"] = "1"
        r = subprocess.run([sys.executable, str(probe), "--enforce"],
                           capture_output=True, text=True, env=env)
        return r.returncode, r.stdout + r.stderr



print("\n── it goes RED on each class it claims to catch ──")

code, out = run("| D1 | api | a thing | x | T900 |\n"
                "| D1 | api | another thing | x | T900 |\n")
check("a DUPLICATE id is a finding", code == 1 and "DUPLICATE ID: 1" in out, out[-200:])

code, out = run("| D2 | api | see `src/gone/widget.ts` for the shape | x | T900 |\n")
check("a cited file that does not exist is a finding",
      code == 1 and "DEAD PATH" in out and "widget.ts" in out, out[-200:])

code, out = run("| D3 | api | a thing | x | T404 |\n")
check("a Tracked ticket with no file is a finding",
      code == 1 and "T404" in out, out[-200:])

code, out = run("| D4 | api | [RESOLVED] **RESOLVED** — paid down last week | x | T900 |\n")
check("a row whose own text says RESOLVED is a finding",
      code == 1 and "RESOLVED, NOT DELETED: 1" in out, out[-200:])

print("\n── the false alarms it ACTUALLY raised (regression probes) ──")

# 🔴 41-of-48. A row may CITE a finished ticket in its explanation without being tracked by it.
code, out = run("| D5 | api | this was found while reading T901's migration | x | T900 |\n")
check("a finished ticket cited in PROSE is not stale tracking (was 41/48 false)",
      code == 0 and "UNOWNED" in out and "D5" not in out.split("UNOWNED")[1][:200], out[-300:])

# 🔴 D48. The inverse of the finding, reported as the finding.
code, out = run("| D6 | api | 🔴 NOT RESOLVED — the bucket is still public | x | T900 |\n")
check('"NOT RESOLVED" is not a resolution (the D48 false positive)',
      code == 0 and "RESOLVED, NOT DELETED: 0" in out, out[-300:])

code, out = run("| D7 | api | the tech_debt table was closed 2026-07-21 | x | T900 |\n")
check('"closed <date>" in prose is not a row status', code == 0, out[-300:])

print("\n── and stays quiet where a finding would be wrong ──")

# ⚠️ Ten real rows say this deliberately. Flagging it would train people to invent a ticket id.
code, out = run("| D8 | api | a real, unfiled thing | x | — (needs a T-row) |\n")
check("`— (needs a T-row)` is an honest record, not rot", code == 0, out[-300:])

# The row ABOUT a deletion legitimately cites the deleted path.
code, out = run("| D9 | api | `lib/vault.ts` was removed by the migration | x | T900 |\n")
check("a row that SAYS a file was removed may cite it", code == 0, out[-300:])

# 🔴 The removal words must be read in the PROSE, not inside the cited filename. This fixture
# was originally named `missing.ts` and excused itself — the gate reported no finding because
# the path it was complaining about contained one of its own suppression words.
code, out = run("| D11 | api | `src/lib/missing-keys.ts` still ships | x | T900 |\n")
check("a dead path cannot excuse itself via a word in its own FILENAME",
      code == 1 and "DEAD PATH" in out, out[-300:])

# UNOWNED is informational — the Tracked column has no grammar (D54).
code, out = run("| D10 | api | a real thing nobody owns | x | T901 |\n")
check("UNOWNED is reported but does NOT gate",
      code == 0 and "UNOWNED" in out and "D10" in out, out[-300:])

print("\n── and refuses to report health over nothing ──")

code, out = run("")
check("an EMPTY register fails rather than reading as clean",
      code == 1 and "EMPTY CORPUS" in out, out[-200:])

print("\n── T331: citation → register & Closed-Debt Ledger checks ──")

CLOSED_LEDGER_BLOCK = (
    "\n## Closed-Debt Ledger\n\n"
    "| ID | Closed | Paid by | Summary |\n"
    "|---|---|---|---|\n"
    "| D15 | 2026-08-31 | [[T901]] | DECOMMISSIONED.md tracked in git |\n"
    "| D32 | 2026-09-02 | [[T901]] | Workspace root git repo |\n"
)

code, out = run(
    "| D1 | api | active debt row | x | T900 |\n" + CLOSED_LEDGER_BLOCK,
    extra_files={"CLAUDE.md": "We track this under [[D999]] in the register.\n"},
)
check(
    "RED: citing nonexistent D999 fails with UNKNOWN CITATION",
    code == 1 and "UNKNOWN CITATION" in out and "D999" in out,
    out[-300:],
)

code, out = run(
    "| D1 | api | active debt row | x | T900 |\n" + CLOSED_LEDGER_BLOCK,
    extra_files={"CLAUDE.md": "The file is unversioned — see debt row D15.\n"},
)
check(
    "RED: open-status assertion against closed D15 fails with STALE OPEN ASSERTION",
    code == 1 and "STALE OPEN ASSERTION" in out and "D15" in out,
    out[-300:],
)

code, out = run(
    "| D15 | api | still in open table too | x | T900 |\n" + CLOSED_LEDGER_BLOCK,
)
check(
    "RED: a debt ID present in both open table and Closed-Debt Ledger fails with DUPLICATE ID",
    code == 1 and "DUPLICATE ID" in out and "D15" in out,
    out[-300:],
)

code, out = run(
    "| D1 | api | active debt row | x | T900 |\n" + CLOSED_LEDGER_BLOCK,
    extra_files={
        "CLAUDE.md": (
            "Active debt [[D1]] (`D1`) is tracked.\n"
            "Historical reference: D15 was closed on 2026-08-31 and belongs to the [[D32]]/[[D15]] class.\n"
            "Non-debt tokens: Cloudflare Workers D1 database, 3D rendering, 0xD1, and Mermaid:\n"
            "  C1 --> D99[\"Returns Stale Data\"]\n"
        ),
    },
)
check(
    "GREEN: valid open citation, historical closed citation, and non-debt tokens pass with denominator",
    code == 0
    and "UNKNOWN CITATION — cited D## has no open row and no Closed-Debt Ledger entry: 0" in out
    and "STALE OPEN ASSERTION — cites closed D## as still open/tracked: 0" in out
    and "2 file(s) scanned" in out,
    out[-400:],
)

code, out = run(
    "| D1 | api | active debt row | x | T900 |\n" + CLOSED_LEDGER_BLOCK,
    require_surfaces=True,
)
check(
    "RED: missing required citation surfaces fail closed as UNMEASURABLE",
    code == 1 and "UNMEASURABLE" in out and "CLAUDE.md (missing)" in out,
    out[-300:],
)

import json as _json
live_r = subprocess.run(
    [sys.executable, str(SCRIPT), "--enforce", "--json"],
    capture_output=True,
    text=True,
)
live_data = _json.loads(live_r.stdout) if live_r.returncode == 0 else {}
check(
    "GREEN: live estate register + citation scan passes --enforce with 0 unknown/stale/unmeasurable",
    live_r.returncode == 0
    and live_data.get("closed_ledger_rows", 0) >= 20
    and live_data.get("files_scanned", 0) > 100
    and live_data.get("citations_total", 0) > 0
    and live_data.get("citations_unknown") == 0
    and live_data.get("citations_stale") == 0
    and live_data.get("unmeasurable_surfaces") == [],
    live_r.stdout[-300:] + live_r.stderr[-300:],
)

print()
if failures:
    print(f"[FAIL] {len(failures)} failure(s):")
    for f in failures:
        print(f"   · {f}")
    sys.exit(1)
print("[OK] debt-register: all checks passed")
