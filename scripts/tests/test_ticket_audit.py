#!/usr/bin/env python3
"""test_ticket_audit.py — Unit test suite for ticket reality audit CLI (T211 AC4).

Offline red-probes testing four-surface reconciliation, path drift,
and acceptance criteria reality classification.

Run: `just ticket-audit-test` or `python3 project/scripts/tests/test_ticket_audit.py`
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import ticket_audit  # noqa: E402

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        failures.append(f"{label} — {detail}")


def test_id_normalization() -> None:
    print("── 1. Ticket ID Normalization ──")
    check("Numeric 382 normalizes to T382", ticket_audit.normalize_id("382") == "T382")
    check("Lowercase t382 normalizes to T382", ticket_audit.normalize_id("t382") == "T382")
    check("Standard T211 preserved", ticket_audit.normalize_id("T211") == "T211")
    check("Padded '  T101 ' normalizes to T101", ticket_audit.normalize_id("  T101 ") == "T101")


def test_frontmatter_parsing() -> None:
    print("\n── 2. Frontmatter & Body Parsing ──")
    sample = """---
id: T999
title: "Sample Ticket"
status: queued
priority: P1
x_ac_done: 2
x_ac_total: 5
x_ac_pct: 40
---

# T999 — Sample Ticket

## Acceptance criteria
- [x] AC1 — First
- [ ] AC2 — Second
"""
    fm, body = ticket_audit.parse_frontmatter(sample)
    check("ID parsed correctly", fm.get("id") == "T999")
    check("Status parsed correctly", fm.get("status") == "queued")
    check("Priority parsed correctly", fm.get("priority") == "P1")
    check("AC done parsed as int", fm.get("x_ac_done") == 2)
    check("AC total parsed as int", fm.get("x_ac_total") == 5)
    check("Body starts after frontmatter", "## Acceptance criteria" in body)


def test_referenced_paths_checking() -> None:
    print("\n── 3. Referenced Path Extraction & Resolution ──")
    sample_text = "See `scripts/ticket_audit.py` and nonexistent `foo/bar/fake_file.ts`."
    repo_map = {"tooling": ROOT, "web": ROOT / "wom7web"}
    resolving, missing = ticket_audit.check_referenced_paths(sample_text, repo_map)
    check("Resolving path detected", any("ticket_audit.py" in p for p in resolving))
    check("Missing path detected", "foo/bar/fake_file.ts" in missing)


def test_ac_classification_heuristics() -> None:
    print("\n── 4. Acceptance Criteria Reality Classification ──")
    body = """
## Acceptance criteria
- [ ] AC1 — Valid criterion referencing missing file `some/missing/module.ts`
- [ ] AC2 — Adopt svc_ai in chat-stream pipeline
- [ ] AC3 — Adopt svc_telemetry in gamification-ingest
- [ ] AC4 — Log event with log-event service
- [x] AC5 — Covered by gate `just deno-check`
- [ ] AC6 — Planned gate `just nonexistent-gate-xyz`
"""
    repo_map = {"web": ROOT / "wom7web"}
    missing_paths = ["some/missing/module.ts"]

    classified = ticket_audit.classify_acs(body, repo_map, missing_paths)
    check("Total 6 ACs extracted", len(classified) == 6)

    c_map = {c["id"]: c for c in classified}

    # AC1: missing path -> contradicted
    check(
        "AC1 flagged contradicted for missing path",
        c_map["AC1"]["verdict"] == "contradicted" and "missing/module.ts" in c_map["AC1"]["evidence"],
    )

    # AC2: non-existent edge function chat-stream -> contradicted
    check(
        "AC2 flagged contradicted for ghost edge function",
        c_map["AC2"]["verdict"] == "contradicted" and "chat-stream" in c_map["AC2"]["evidence"],
    )

    # AC3: svc_telemetry + gamification conflict -> contradicted
    check(
        "AC3 flagged contradicted for schema permission conflict",
        c_map["AC3"]["verdict"] == "contradicted" and "gamification" in c_map["AC3"]["evidence"],
    )

    # AC4: retired log-event -> contradicted
    check(
        "AC4 flagged contradicted for retired component",
        c_map["AC4"]["verdict"] == "contradicted" and "T199" in c_map["AC4"]["evidence"],
    )

    # AC5: ticked gate -> confirmed
    check(
        "AC5 ticked gate confirmed",
        c_map["AC5"]["verdict"] == "confirmed" and "just deno-check" in c_map["AC5"]["evidence"],
    )

    # AC6: unticked gate -> unmeasurable
    check(
        "AC6 unticked gate unmeasurable",
        c_map["AC6"]["verdict"] == "unmeasurable",
    )


def test_surface_drift_detection() -> None:
    print("\n── 5. Surface Drift Detection & Mismatch Reporting ──")
    # Test non-existent ticket
    res_missing = ticket_audit.audit_ticket("T999999", offline=True)
    check("Missing ticket returns exists=False", res_missing["exists"] is False)
    check("Missing ticket exit code is 2", res_missing["exit_code"] == 2)

    # Audit T382 in offline mode
    res_t382 = ticket_audit.audit_ticket("T382", offline=True, strict=False)
    check("T382 ticket exists", res_t382["exists"] is True)
    check("T382 has 5 ACs", len(res_t382["acs"]) == 5)

    # Test synthetic ticket with contradiction in strict mode
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
        f.write("""---
id: T9999
title: "Synthetic Contradicted Ticket"
status: queued
priority: P1
x_ac_done: 0
x_ac_total: 1
x_ac_pct: 0
---
# T9999
## Acceptance criteria
- [ ] AC1 — References missing file `nonexistent/ghost_file.ts`
""")
        temp_path = Path(f.name)
    try:
        res_synth = ticket_audit.audit_ticket("T9999", offline=True, strict=True, ticket_file=temp_path)
        check("Synthetic ticket identified contradiction", any(ac["verdict"] == "contradicted" for ac in res_synth["acs"]))
        check("Strict mode exits 1 when contradictions exist", res_synth["exit_code"] == 1)
    finally:
        temp_path.unlink(missing_ok=True)


def test_report_formatting() -> None:
    print("\n── 6. Report Formatting & JSON Output ──")
    res = ticket_audit.audit_ticket("T382", offline=True)
    md = ticket_audit.format_markdown_report(res)
    check("Report contains Title", "# Ticket Reality Audit — T382" in md)
    check("Report contains Recorded status", "**Recorded**:" in md)
    check("Report contains Cross-surface block", "**Cross-surface**:" in md)
    check("Report contains table headers", "| AC | Recorded | Verdict | Evidence |" in md)
    check("Report contains Bottom line", "**Bottom line**:" in md)


def main() -> int:
    print("test_ticket_audit.py — Ticket Reality Audit Probes\n")
    test_id_normalization()
    test_frontmatter_parsing()
    test_referenced_paths_checking()
    test_ac_classification_heuristics()
    test_surface_drift_detection()
    test_report_formatting()

    print("\n" + "═" * 60)
    if failures:
        print(f"FAILED: {len(failures)} assertion(s) failed:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("ALL PROBES PASSED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
