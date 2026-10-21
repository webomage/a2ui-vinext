#!/usr/bin/env python3
"""T432 — Unit & Red-Probe Tests for `scripts/dora_metrics.py` and `scripts/log_deploy.py` (`just dora-test`).

Verifies:
  1. `log_deploy.py` validates `outcome` and `trigger` and FAILS CLOSED on missing or invalid values.
  2. Incident records in `.incidents/INC-*.json` validate against `.incidents/incident.schema.json`.
  3. `dora_metrics.py` computes all 5 DORA metrics accurately and marks metrics `unmeasurable` (with reason)
     when required inputs are absent — never fabricating 0% or 0h (T242 / AgDR-0036).
  4. `record_owner_pulse` and `compute_agent_devex` validate 1..5 bounds and emit JSONL.
  5. `compute_dx_core_4` computes Done-ticket share by `area` and confirms 0 unverified `# ⚠️ inferred`
     area tags remain across `.tasks/T*.md`.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

HERE = Path(__file__).resolve()
SCRIPTS_DIR = HERE.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import dora_metrics as dm  # noqa: E402
import log_deploy as ld  # noqa: E402


def run_all_tests() -> tuple[int, list[str]]:
    failures: list[str] = []
    checks = 0

    def check(label: str, cond: bool, detail: str = "") -> None:
        nonlocal checks
        checks += 1
        if cond:
            print(f"  ✅ {label}")
        else:
            msg = f"{label}: {detail}" if detail else label
            print(f"  ❌ {msg}", file=sys.stderr)
            failures.append(msg)

    # 1. log_deploy.py validation & fail-closed red probes (AC3)
    o, t, r = ld.validate_deploy_metadata("success", "planned", None)
    check(
        "log_deploy accepts valid (success, planned)",
        (o, t, r) == ("success", "planned", None),
    )

    rejected_bad_outcome = False
    try:
        ld.validate_deploy_metadata("maybe_ok", "planned", None)
    except ValueError:
        rejected_bad_outcome = True
    check("log_deploy rejects invalid outcome fail-closed", rejected_bad_outcome)

    rejected_bad_trigger = False
    try:
        ld.validate_deploy_metadata("success", "manual_yolo", None)
    except ValueError:
        rejected_bad_trigger = True
    check("log_deploy rejects invalid trigger fail-closed", rejected_bad_trigger)

    sql = ld.build_insert_sql("release", "2026.10.21-1792556546", "abc1234", "dev@w0m.xyz", "hotfixed", "incident", "INC-2026-10-06-001")
    check(
        "log_deploy build_insert_sql includes outcome, trigger, and incident_ref",
        "'hotfixed', 'incident', 'INC-2026-10-06-001'" in sql,
        sql,
    )

    # 2. Real .incidents/ ledger validates cleanly (AC4)
    incidents, inc_errors = dm.load_incidents()
    check(
        ".incidents/ contains >= 2 valid historical incident records with 0 schema errors",
        len(incidents) >= 2 and not inc_errors,
        f"count={len(incidents)}, errors={inc_errors}",
    )

    # 3. Red probe: missing inputs yield `unmeasurable`, never fabricated 0% (AC1 & AC5)
    with tempfile.TemporaryDirectory() as tmp:
        empty_rel = Path(tmp) / "releases"
        empty_inc = Path(tmp) / "incidents"
        empty_rel.mkdir()
        empty_inc.mkdir()
        unm = dm.compute_dora_5(
            since_days=30,
            releases_dir=empty_rel,
            incidents_dir=empty_inc,
            live_rows_override=(None, "simulated offline DB"),
        )
        m = unm["metrics"]
        all_unm = all(
            m[k]["status"] == "unmeasurable" and bool(m[k].get("reason"))
            for k in (
                "deployment_frequency",
                "lead_time_for_changes",
                "change_fail_rate",
                "failed_deployment_recovery_time",
                "deployment_rework_rate",
            )
        )
        check(
            "dora_5 marks all 5 metrics 'unmeasurable' with explicit reason when inputs are absent",
            all_unm,
            json.dumps(m),
        )

    # 4. Real estate dora_5 + dx_core_4 calculation (AC5 & AC7)
    real_dora = dm.compute_dora_5(since_days=30, live_rows_override=(None, "offline test"))
    rm = real_dora["metrics"]
    check(
        "real estate dora_5 measures deployment_frequency and failed_deployment_recovery_time",
        rm["deployment_frequency"]["status"] == "measured"
        and rm["failed_deployment_recovery_time"]["status"] == "measured",
        json.dumps(rm),
    )

    # 5. Owner 3-question pulse & Agent-DevEx (AC6)
    with tempfile.TemporaryDirectory() as tmp:
        pulse_path = Path(tmp) / "devex-pulse.jsonl"
        entry = dm.record_owner_pulse(4, 5, 3, "smooth agent worktree flow", pulse_file=pulse_path)
        check(
            "record_owner_pulse writes 3-question JSONL entry with composite score",
            entry["composite_score"] == 4.0 and pulse_path.is_file(),
            str(entry),
        )
        bad_pulse = False
        try:
            dm.record_owner_pulse(6, 3, 3, pulse_file=pulse_path)
        except ValueError:
            bad_pulse = True
        check("record_owner_pulse rejects out-of-range score (6 > 5)", bad_pulse)

    # 6. DX Core 4 Impact & confirmed inferred ticket areas (AC7)
    devex = dm.compute_agent_devex()
    core4 = dm.compute_dx_core_4(real_dora, devex)
    impact = core4["dimensions"]["impact"]
    check(
        "DX Core 4 impact measures product vs platform share with 0 unconfirmed inferred areas",
        impact["status"] == "measured"
        and impact["unconfirmed_inferred_areas_count"] == 0
        and impact["product_done_share_pct"] > 0,
        json.dumps(impact),
    )

    return checks, failures


def main() -> int:
    print("▶ T432 — DORA 5, Agent-DevEx & DX Core 4 Test Suite")
    checks, failures = run_all_tests()
    if failures:
        print(f"\n❌ {len(failures)}/{checks} check(s) failed.", file=sys.stderr)
        return 1
    print(f"\n✅ All {checks}/{checks} DORA & DevEx checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
