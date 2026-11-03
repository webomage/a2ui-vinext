#!/usr/bin/env python3
"""test_ticket_audit.py — Unit & corpus reality probes for `scripts/ticket_audit.py` (T211, T616).

Covers:
  1. Ticket ID normalization & frontmatter inline `#` comment parsing
  2. Referenced path resolution (including `@wom/`, `{a,b}` brace expansion, repo-qualified & app paths)
  3. AC reality classification heuristics
  4. Four-surface reconciliation + `delivery_state` (`deployed (<ver>)` vs `landed_pending_deploy` vs `no_commit_trace`)
  5. Fail-closed empty-corpus guards (`exit 2`, AgDR-0025) for `--completed` and `--specs`
  6. Bidirectional red/green probes for `--completed --strict` and `--specs --strict`
     (missing file `NonExistentWidget.svelte`, retired `wom7*` repo prefix, missing exported symbol,
      nonexistent `public.<table_name>`, plus live estate corpus green check)

Run: `just ticket-audit-test` or `python3 scripts/tests/test_ticket_audit.py`
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import ticket_audit  # noqa: E402

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        failures.append(f"{label} — {detail}")


def test_id_normalization() -> None:
    print("── 1. Ticket ID Normalization ──")
    check("Numeric 382 normalizes to T382", ticket_audit.normalize_id("382") == "T382")
    check("Lowercase t382 normalizes to T382", ticket_audit.normalize_id("t382") == "T382")
    check("Standard T211 preserved", ticket_audit.normalize_id("T211") == "T211")
    check("Padded '  T101 ' normalizes to T101", ticket_audit.normalize_id("  T101 ") == "T101")


def test_frontmatter_parsing() -> None:
    print("\n── 2. Frontmatter & Body Parsing (Including Inline YAML Comments) ──")
    sample = """---
id: T999
title: "Sample Ticket"
status: done   # inline YAML comment (T616)
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
    check("Status strips inline # comment", fm.get("status") == "done", f"got {fm.get('status')!r}")
    check("Priority parsed correctly", fm.get("priority") == "P1")
    check("AC done parsed as int", fm.get("x_ac_done") == 2)
    check("AC total parsed as int", fm.get("x_ac_total") == 5)
    check("Body starts after frontmatter", "## Acceptance criteria" in body)


def test_referenced_paths_checking() -> None:
    print("\n── 3. Referenced Path Extraction & Brace Expansion ──")
    sample_text = "See `scripts/ticket_audit.py` and nonexistent `foo/bar/fake_file.ts`."
    repo_map = {"tooling": ROOT, "web": ROOT / "w0m-web"}
    resolving, missing = ticket_audit.check_referenced_paths(sample_text, repo_map)
    check("Resolving path detected", any("ticket_audit.py" in p for p in resolving))
    check("Missing path detected", "foo/bar/fake_file.ts" in missing)
    check(
        "Brace alternation expands {a,b}",
        ticket_audit.expand_brace_token("scripts/{ticket_audit,dod_check}.py")
        == ["scripts/ticket_audit.py", "scripts/dod_check.py"],
    )
    check(
        "Single-placeholder {id} is preserved as template",
        ticket_audit.expand_brace_token(".tasks/{id}.md") == [".tasks/{id}.md"],
    )


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
    repo_map = {"web": ROOT / "w0m-web"}
    missing_paths = ["some/missing/module.ts"]

    classified = ticket_audit.classify_acs(body, repo_map, missing_paths)
    check("Total 6 ACs extracted", len(classified) == 6)

    c_map = {c["id"]: c for c in classified}
    check(
        "AC1 flagged contradicted for missing path",
        c_map["AC1"]["verdict"] == "contradicted" and "missing/module.ts" in c_map["AC1"]["evidence"],
    )
    check(
        "AC2 flagged contradicted for ghost edge function",
        c_map["AC2"]["verdict"] == "contradicted" and "chat-stream" in c_map["AC2"]["evidence"],
    )
    check(
        "AC3 flagged contradicted for schema permission conflict",
        c_map["AC3"]["verdict"] == "contradicted" and "gamification" in c_map["AC3"]["evidence"],
    )
    check(
        "AC4 flagged contradicted for retired component",
        c_map["AC4"]["verdict"] == "contradicted" and "T199" in c_map["AC4"]["evidence"],
    )
    check(
        "AC5 ticked gate confirmed",
        c_map["AC5"]["verdict"] == "confirmed" and "just deno-check" in c_map["AC5"]["evidence"],
    )
    check("AC6 unticked gate unmeasurable", c_map["AC6"]["verdict"] == "unmeasurable")


def test_surface_drift_and_delivery_state() -> None:
    print("\n── 5. Four-Surface Reconciliation & Release Delivery State ──")
    res_missing = ticket_audit.audit_ticket("T999999", offline=True)
    check("Missing ticket returns exists=False", res_missing["exists"] is False)
    check("Missing ticket exit code is 2", res_missing["exit_code"] == 2)

    res_t382 = ticket_audit.audit_ticket("T382", offline=True, strict=False)
    check("T382 ticket exists", res_t382["exists"] is True)
    check("T382 has 5 ACs", len(res_t382["acs"]) == 5)
    check(
        "T382 delivery_state resolves to deployed (<version>)",
        str(res_t382.get("delivery_state", "")).startswith("deployed ("),
        f"got {res_t382.get('delivery_state')!r}",
    )

    res_t613 = ticket_audit.audit_ticket("T613", offline=True, strict=False)
    check(
        "T613 delivery_state resolves to landed_pending_deploy or deployed",
        res_t613.get("delivery_state") in ("landed_pending_deploy",)
        or str(res_t613.get("delivery_state", "")).startswith("deployed ("),
        f"got {res_t613.get('delivery_state')!r}",
    )

    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
        f.write("""---
id: T9999
title: "Synthetic Contradicted Ticket"
status: done
priority: P1
x_ac_done: 0
x_ac_total: 1
x_ac_pct: 0
---
# T9999
## Acceptance criteria
- [x] AC1 — References missing file `nonexistent/ghost_file.ts`
""")
        temp_path = Path(f.name)
    try:
        res_synth = ticket_audit.audit_ticket("T9999", offline=True, strict=True, ticket_file=temp_path)
        check(
            "Synthetic ticket identified contradiction",
            any(ac["verdict"] == "contradicted" for ac in res_synth["acs"]),
        )
        check(
            "Synthetic ticket catches x_ac_done=0 vs measured=1 parity drift",
            any("tasks_query AC parity" in d for d in res_synth["disagreements"]),
        )
        check(
            "Synthetic ticket with no git commit reports no_commit_trace",
            res_synth["delivery_state"] == "no_commit_trace",
            f"got {res_synth['delivery_state']!r}",
        )
        check("Strict mode exits 1 when contradictions exist", res_synth["exit_code"] == 1)
    finally:
        temp_path.unlink(missing_ok=True)


def test_corpus_fail_closed_and_red_green_probes() -> None:
    print("\n── 6. Fail-Closed Empty Corpus & Red/Green Reality Probes (T616 AC1/AC3) ──")
    shared_idx = ticket_audit.CodebaseRealityIndex(ticket_audit.resolve_repos())

    with tempfile.TemporaryDirectory() as tmp:
        empty_dir = Path(tmp) / "empty"
        empty_dir.mkdir()
        comp_empty = ticket_audit.audit_completed_corpus(empty_dir, idx=shared_idx)
        spec_empty = ticket_audit.audit_specs_corpus(empty_dir, idx=shared_idx)
        check("Empty completed corpus fails closed with exit_code=2", comp_empty["exit_code"] == 2)
        check("Empty specs corpus fails closed with exit_code=2", spec_empty["exit_code"] == 2)

        # RED probe 1: Completed ticket claiming nonexistent widget, symbol, retired wom7*, and fake SQL table
        red_tickets = Path(tmp) / "tickets_red"
        red_tickets.mkdir()
        (red_tickets / "T9991.md").write_text(
            """---
id: T9991
title: "Fake Completed Ticket"
status: done
closed_as: completed
created: 2026-11-02
x_ac_done: 1
x_ac_total: 1
x_ac_pct: 100
---
# T9991
## Acceptance criteria
- [x] AC1 — Built `w0m-web/apps/web/src/components/NonExistentWidget.svelte`, `wom7web/apps/web/foo.ts`, `export function totallyFakeGhostSymbol`, and `public.nonexistent_ghost_table_xyz`.
""",
            encoding="utf-8",
        )
        comp_red = ticket_audit.audit_completed_corpus(red_tickets, idx=shared_idx)
        joined_red = " | ".join(comp_red["contradicted"][0]["contradictions"]) if comp_red.get("contradicted") else ""
        check("RED completed corpus exits 1", comp_red["exit_code"] == 1)
        check("RED completed corpus names NonExistentWidget.svelte", "NonExistentWidget.svelte" in joined_red, joined_red)
        check("RED completed corpus catches retired wom7web path", "wom7web/apps/web/foo.ts" in joined_red, joined_red)
        check(
            "RED completed corpus catches missing exported symbol",
            "totallyFakeGhostSymbol" in joined_red,
            joined_red,
        )
        check(
            "RED completed corpus catches nonexistent SQL relation",
            "public.nonexistent_ghost_table_xyz" in joined_red,
            joined_red,
        )

        # RED probe 2: Canonical spec citing deleted script path and nonexistent SQL table
        red_specs = Path(tmp) / "specs_red"
        red_specs.mkdir()
        (red_specs / "spec.md").write_text(
            """# Sample Spec
## Requirements
### Requirement: Fake Check
The gate SHALL execute `scripts/deleted_nonexistent_gate_xyz.py` and query `public.fake_spec_table_xyz`.
""",
            encoding="utf-8",
        )
        spec_red = ticket_audit.audit_specs_corpus(red_specs, idx=shared_idx)
        joined_spec = " | ".join(spec_red["contradicted"][0]["contradictions"]) if spec_red.get("contradicted") else ""
        check("RED specs corpus exits 1", spec_red["exit_code"] == 1)
        check(
            "RED specs corpus names deleted script path",
            "scripts/deleted_nonexistent_gate_xyz.py" in joined_spec,
            joined_spec,
        )
        check(
            "RED specs corpus names nonexistent SQL relation",
            "public.fake_spec_table_xyz" in joined_spec,
            joined_spec,
        )

    # GREEN live estate check: `--completed` and `--specs` on the real workspace
    live_comp = ticket_audit.audit_completed_corpus(ROOT / ".tasks", idx=shared_idx)
    live_specs = ticket_audit.audit_specs_corpus(ROOT / "w0m-web" / "openspec" / "specs", idx=shared_idx)
    check(
        "LIVE completed tickets corpus passes with 0 contradictions",
        live_comp["exit_code"] == 0 and live_comp["done_tickets_scanned"] >= 500,
        f"got {live_comp.get('contradicted')}",
    )
    check(
        "LIVE canonical specs corpus passes with 0 contradictions",
        live_specs["exit_code"] == 0 and live_specs["specs_scanned"] >= 150,
        f"got {live_specs.get('contradicted')}",
    )

    # CLI subprocess `--json` check
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "ticket_audit.py"), "T382", "--offline", "--json"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=20,
    )
    payload = json.loads(proc.stdout) if proc.returncode == 0 else {}
    check(
        "CLI `--json` emits delivery_state and exits 0 on T382",
        proc.returncode == 0 and "delivery_state" in payload,
    )


def test_report_formatting() -> None:
    print("\n── 7. Report Formatting ──")
    res = ticket_audit.audit_ticket("T382", offline=True)
    md = ticket_audit.format_markdown_report(res)
    check("Report contains Title", "# Ticket Reality Audit — T382" in md)
    check("Report contains Recorded status", "**Recorded**:" in md)
    check("Report contains Cross-surface block", "**Cross-surface**:" in md)
    check("Report contains Delivery block", "delivery_state:" in md)
    check("Report contains table headers", "| AC | Recorded | Verdict | Evidence |" in md)
    check("Report contains Bottom line", "**Bottom line**:" in md)


def main() -> int:
    print("test_ticket_audit.py — Ticket & Spec Reality Audit Probes\n")
    test_id_normalization()
    test_frontmatter_parsing()
    test_referenced_paths_checking()
    test_ac_classification_heuristics()
    test_surface_drift_and_delivery_state()
    test_corpus_fail_closed_and_red_green_probes()
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
