#!/usr/bin/env python3
"""T432 AC5, AC6 & AC7 — Delivery & DevEx Measurement Cockpit (`just dora`, `just devex-pulse`).

Implements the measurement charter in `docs/decisions/AgDR-0036-delivery-and-devex-measurement-charter.md`:
  - Emits the 5 DORA 2024/2025 metrics as JSONL (`dora_5` record):
      1. deployment_frequency
      2. lead_time_for_changes
      3. change_fail_rate
      4. failed_deployment_recovery_time
      5. deployment_rework_rate
    marking any metric `unmeasurable` (with explicit `reason`) when required inputs are absent
    (never fabricating 0 / 0.0% / success, per T242).
  - Emits Agent-DevEx friction signals & weekly 3-question owner perceptual pulse (`agent_devex` record).
  - Emits the DX Core 4 one-page scorecard (`dx_core_4` record: Speed · Effectiveness · Quality · Impact),
    computing `Impact` from `.tasks/T*.md` done-ticket share by `area` and verifying zero unconfirmed
    `# ⚠️ inferred` area tags remain.

Usage:
    python3 scripts/dora_metrics.py [--since 30] [--service release]
    python3 scripts/dora_metrics.py --pulse [--flow 4 --feedback 4 --cognitive-load 3 --notes "..."]
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys
from typing import Any

HERE = Path(__file__).resolve()
ESTATE_ROOT = HERE.parents[1]
RELEASES_DIR = ESTATE_ROOT / "releases"
INCIDENTS_DIR = ESTATE_ROOT / ".incidents"
INCIDENT_SCHEMA_PATH = INCIDENTS_DIR / "incident.schema.json"
TASKS_DIR = ESTATE_ROOT / ".tasks"
DEPLOY_LOGS_DIR = ESTATE_ROOT / "deploy-logs"
SUITES_PATH = ESTATE_ROOT / "w0m-web" / "project" / "test-suites.json"
PY_TYPING_BASELINE_PATH = ESTATE_ROOT / "w0m-web" / "project" / "py-typing-baseline.json"

VERSION_EPOCH_RE = re.compile(r"^(?P<date>\d{4}\.\d{2}\.\d{2})-(?P<epoch>\d{9,12})$")
INFERRED_AREA_RE = re.compile(r"^area:.*#\s*⚠️\s*inferred", re.M)

# Confirmed override for T59 so Track C's concurrent edit on T59.md does not rebase-conflict
CONFIRMED_AREA_OVERRIDES: dict[str, str] = {
    "T59": "data",
}

PRODUCT_AREAS: frozenset[str] = frozenset({"product", "ai", "data", "web"})
PLATFORM_AREAS: frozenset[str] = frozenset(
    {"sdlc", "tools", "tooling", "infra", "security", "schemas", "knowledge", "skills", "platform", "mcp", "integrations"}
)


def _load_json_dict(path: Path) -> dict[str, Any]:
    raw: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: expected JSON object")
    return raw


def parse_iso_utc(ts: str) -> float:
    cleaned = ts.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    dt = datetime.fromisoformat(cleaned)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def parse_release_epoch(version: str) -> float | None:
    m = VERSION_EPOCH_RE.match(version.strip())
    if not m:
        return None
    return float(int(m.group("epoch")))


def load_releases(releases_dir: Path = RELEASES_DIR) -> list[dict[str, Any]]:
    if not releases_dir.is_dir():
        return []
    records: list[dict[str, Any]] = []
    for p in sorted(releases_dir.glob("*.json")):
        try:
            doc = _load_json_dict(p)
        except Exception:
            continue
        ver = str(doc.get("version") or p.stem)
        epoch = parse_release_epoch(ver)
        if epoch is None:
            continue
        doc["_epoch"] = epoch
        records.append(doc)
    records.sort(key=lambda r: float(r["_epoch"]))
    return records


def validate_incident_record(doc: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = (
        "id",
        "title",
        "severity",
        "status",
        "detected_at",
        "recovered_at",
        "cause_deploy_version",
        "resolution_deploy_version",
        "affected_services",
        "tickets",
        "summary",
    )
    for req in required:
        if req not in doc:
            errors.append(f"missing required field '{req}'")
    inc_id = doc.get("id")
    if not isinstance(inc_id, str) or not re.match(r"^INC-\d{4}-\d{2}-\d{2}-\d{3}$", inc_id):
        errors.append(f"invalid id {inc_id!r}")
    if doc.get("severity") not in ("sev1", "sev2", "sev3"):
        errors.append(f"invalid severity {doc.get('severity')!r}")
    if doc.get("status") not in ("open", "resolved"):
        errors.append(f"invalid status {doc.get('status')!r}")
    det = doc.get("detected_at")
    if not isinstance(det, str):
        errors.append("detected_at must be an ISO-8601 string")
    else:
        try:
            parse_iso_utc(det)
        except Exception as err:
            errors.append(f"invalid detected_at: {err}")
    rec = doc.get("recovered_at")
    if rec is not None:
        if not isinstance(rec, str):
            errors.append("recovered_at must be an ISO-8601 string or null")
        else:
            try:
                parse_iso_utc(rec)
            except Exception as err:
                errors.append(f"invalid recovered_at: {err}")
    return errors


def load_incidents(incidents_dir: Path = INCIDENTS_DIR) -> tuple[list[dict[str, Any]], list[str]]:
    if not incidents_dir.is_dir():
        return [], []
    incidents: list[dict[str, Any]] = []
    errors: list[str] = []
    for p in sorted(incidents_dir.glob("INC-*.json")):
        try:
            doc = _load_json_dict(p)
        except Exception as err:
            errors.append(f"{p.name}: {err}")
            continue
        errs = validate_incident_record(doc)
        if errs:
            errors.extend(f"{p.name}: {e}" for e in errs)
            continue
        doc["_detected_epoch"] = parse_iso_utc(str(doc["detected_at"]))
        doc["_recovered_epoch"] = (
            parse_iso_utc(str(doc["recovered_at"])) if doc.get("recovered_at") is not None else None
        )
        incidents.append(doc)
    return incidents, errors


def query_live_deploy_log(since_days: int, service: str | None = None) -> tuple[list[dict[str, Any]] | None, str | None]:
    """Query public.deploy_log when DATABASE_URL is available; otherwise return (None, reason)."""
    db_url = os.environ.get("DATABASE_URL", "").strip()
    if not db_url:
        return None, "DATABASE_URL is not set in environment"
    where_clauses = [f"deployed_at >= now() - interval '{int(since_days)} days'"]
    if service:
        safe_svc = service.replace("'", "''")
        where_clauses.append(f"service = '{safe_svc}'")
    where_sql = " AND ".join(where_clauses)
    sql = (
        "SELECT COALESCE(json_agg(row_to_json(t)), '[]'::json)::text FROM ("
        "SELECT service, version, commit, actor, "
        "EXTRACT(EPOCH FROM deployed_at) AS deployed_epoch, "
        "outcome, trigger, incident_ref "
        f"FROM public.deploy_log WHERE {where_sql} ORDER BY deployed_at ASC"
        ") t;"
    )
    try:
        res = subprocess.run(
            ["psql", db_url, "-t", "-A", "-v", "ON_ERROR_STOP=1", "-c", sql],
            capture_output=True,
            text=True,
            timeout=8,
        )
        if res.returncode != 0:
            err_line = (res.stderr or "").strip().splitlines()
            short_err = err_line[0] if err_line else "psql exited non-zero"
            return None, f"deploy_log query failed ({short_err})"
        payload = res.stdout.strip() or "[]"
        rows: list[dict[str, Any]] = json.loads(payload)
        return rows, None
    except Exception as err:
        return None, f"deploy_log query error ({err})"


def _git_commit_epoch(repo_dir: Path, sha: str) -> float | None:
    if not sha or not (repo_dir / ".git").exists():
        return None
    try:
        res = subprocess.run(
            ["git", "-C", str(repo_dir), "show", "-s", "--format=%ct", sha],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if res.returncode == 0 and res.stdout.strip().isdigit():
            return float(int(res.stdout.strip()))
    except Exception:
        pass
    return None


def compute_dora_5(
    *,
    since_days: int = 30,
    service: str | None = None,
    releases_dir: Path = RELEASES_DIR,
    incidents_dir: Path = INCIDENTS_DIR,
    estate_root: Path = ESTATE_ROOT,
    live_rows_override: tuple[list[dict[str, Any]] | None, str | None] | None = None,
) -> dict[str, Any]:
    all_releases = load_releases(releases_dir)
    all_incidents, incident_errors = load_incidents(incidents_dir)

    latest_epoch = max(
        [r["_epoch"] for r in all_releases]
        + [i["_detected_epoch"] for i in all_incidents]
        + [datetime.now(timezone.utc).timestamp()]
    )
    cutoff_epoch = latest_epoch - (since_days * 86400.0)

    filtered_releases: list[dict[str, Any]] = []
    for r in all_releases:
        if float(r["_epoch"]) < cutoff_epoch:
            continue
        if not r.get("deployed", True):
            continue
        if service and service != "release":
            deployed_apps = r.get("deployed_apps") or []
            if service not in deployed_apps:
                continue
        filtered_releases.append(r)

    filtered_incidents: list[dict[str, Any]] = []
    for inc in all_incidents:
        if float(inc["_detected_epoch"]) < cutoff_epoch:
            continue
        if service and service not in (inc.get("affected_services") or []):
            continue
        filtered_incidents.append(inc)

    live_rows, live_err = (
        live_rows_override
        if live_rows_override is not None
        else query_live_deploy_log(since_days, service)
    )

    # 1. Deployment Frequency
    deploys_count = len(live_rows) if live_rows is not None else len(filtered_releases)
    if deploys_count == 0:
        dep_freq: dict[str, Any] = {
            "status": "unmeasurable",
            "reason": (
                f"0 deployments found in last {since_days}d for service={service or 'all'} "
                f"(live_db={live_err or 'empty'})"
            ),
        }
    else:
        per_day = round(deploys_count / max(since_days, 1), 3)
        per_week = round(per_day * 7.0, 2)
        dep_freq = {
            "status": "measured",
            "source": "public.deploy_log" if live_rows is not None else "releases/*.json",
            "deploys_count": deploys_count,
            "window_days": since_days,
            "deploys_per_day": per_day,
            "deploys_per_week": per_week,
        }

    # 2. Lead Time for Changes
    lead_hours: list[float] = []
    for r in filtered_releases:
        rel_epoch = float(r["_epoch"])
        repos_map = r.get("repos")
        if not isinstance(repos_map, dict):
            continue
        root_sha = str(repos_map.get(".") or "")
        commit_epoch = _git_commit_epoch(estate_root, root_sha)
        if commit_epoch is not None and rel_epoch >= commit_epoch:
            lead_hours.append(round((rel_epoch - commit_epoch) / 3600.0, 3))

    if not lead_hours:
        lead_time: dict[str, Any] = {
            "status": "unmeasurable",
            "reason": f"no reachable release commit timestamps in last {since_days}d",
        }
    else:
        sorted_lt = sorted(lead_hours)
        p90_idx = min(len(sorted_lt) - 1, int(round(0.9 * (len(sorted_lt) - 1))))
        lead_time = {
            "status": "measured",
            "sample_size": len(sorted_lt),
            "median_hours": round(float(statistics.median(sorted_lt)), 2),
            "p90_hours": round(float(sorted_lt[p90_idx]), 2),
        }

    # 3. Change Fail Rate (CFR) & 5. Deployment Rework Rate
    if live_rows is not None and len(live_rows) > 0:
        total_d = len(live_rows)
        failed_d = sum(
            1
            for row in live_rows
            if row.get("outcome") in ("failed", "rolled_back", "hotfixed")
        )
        rework_d = sum(
            1
            for row in live_rows
            if row.get("trigger") == "incident" or row.get("outcome") in ("rolled_back", "hotfixed")
        )
        cfr: dict[str, Any] = {
            "status": "measured",
            "source": "public.deploy_log",
            "failed_deploys": failed_d,
            "total_deploys": total_d,
            "rate_pct": round((failed_d / total_d) * 100.0, 2),
        }
        rework: dict[str, Any] = {
            "status": "measured",
            "source": "public.deploy_log",
            "rework_deploys": rework_d,
            "total_deploys": total_d,
            "rate_pct": round((rework_d / total_d) * 100.0, 2),
        }
    elif filtered_releases and filtered_incidents:
        total_d = len(filtered_releases)
        failed_d = len(filtered_incidents)
        rework_d = sum(1 for inc in filtered_incidents if inc.get("resolution_deploy_version"))
        cfr = {
            "status": "measured",
            "source": "releases/*.json + .incidents/*.json (offline lower-bound; live deploy_log unavailable)",
            "live_deploy_log_note": live_err,
            "failed_deploys": failed_d,
            "total_deploys": total_d,
            "rate_pct": round((failed_d / total_d) * 100.0, 2),
        }
        rework = {
            "status": "measured",
            "source": "releases/*.json + .incidents/*.json (offline lower-bound; live deploy_log unavailable)",
            "live_deploy_log_note": live_err,
            "rework_deploys": rework_d,
            "total_deploys": total_d,
            "rate_pct": round((rework_d / total_d) * 100.0, 2),
        }
    else:
        cfr = {
            "status": "unmeasurable",
            "reason": (
                f"live deploy_log outcome column unavailable ({live_err}) and 0 matching incidents in window; "
                "refusing to fabricate 0% failure rate (T242 / AgDR-0036)"
            ),
        }
        rework = {
            "status": "unmeasurable",
            "reason": (
                f"live deploy_log trigger column unavailable ({live_err}) and 0 matching incidents in window; "
                "refusing to fabricate 0% rework rate (T242 / AgDR-0036)"
            ),
        }

    # 4. Failed Deployment Recovery Time (formerly MTTR)
    recovery_hours: list[float] = []
    for inc in filtered_incidents:
        det_e = inc.get("_detected_epoch")
        rec_e = inc.get("_recovered_epoch")
        if isinstance(det_e, float) and isinstance(rec_e, float) and rec_e >= det_e:
            recovery_hours.append(round((rec_e - det_e) / 3600.0, 2))

    if not recovery_hours:
        fdrt: dict[str, Any] = {
            "status": "unmeasurable",
            "reason": f"0 resolved incidents in last {since_days}d (cannot compute recovery time from 0 incidents)",
        }
    else:
        fdrt = {
            "status": "measured",
            "incident_count": len(recovery_hours),
            "median_hours": round(float(statistics.median(recovery_hours)), 2),
            "max_hours": round(float(max(recovery_hours)), 2),
        }

    return {
        "record_type": "dora_5",
        "charter_agdr": "AgDR-0036",
        "window_days": since_days,
        "service_filter": service or "all",
        "incident_schema_errors": incident_errors,
        "metrics": {
            "deployment_frequency": dep_freq,
            "lead_time_for_changes": lead_time,
            "change_fail_rate": cfr,
            "failed_deployment_recovery_time": fdrt,
            "deployment_rework_rate": rework,
        },
    }


def record_owner_pulse(
    flow: int,
    feedback: int,
    cognitive_load: int,
    notes: str = "",
    pulse_file: Path = DEPLOY_LOGS_DIR / "devex-pulse.jsonl",
) -> dict[str, Any]:
    for label, val in (("flow", flow), ("feedback", feedback), ("cognitive_load", cognitive_load)):
        if not isinstance(val, int) or val < 1 or val > 5:
            raise ValueError(f"{label} score must be an integer 1..5, got {val!r}")
    entry: dict[str, Any] = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "flow_score": flow,
        "feedback_loop_score": feedback,
        "cognitive_load_score": cognitive_load,
        "composite_score": round((flow + feedback + cognitive_load) / 3.0, 2),
        "notes": notes.strip(),
    }
    pulse_file.parent.mkdir(parents=True, exist_ok=True)
    with pulse_file.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry


def compute_agent_devex(
    *,
    deploy_logs_dir: Path = DEPLOY_LOGS_DIR,
    suites_path: Path = SUITES_PATH,
    typing_baseline_path: Path = PY_TYPING_BASELINE_PATH,
) -> dict[str, Any]:
    # 1. Agent friction log (`deploy-logs/agent-devex.jsonl`)
    friction_file = deploy_logs_dir / "agent-devex.jsonl"
    friction_events: list[dict[str, Any]] = []
    if friction_file.is_file():
        for line in friction_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                ev: dict[str, Any] = json.loads(line)
                if isinstance(ev, dict):
                    friction_events.append(ev)
            except Exception:
                continue

    if friction_events:
        hook_ms = [float(e["hook_duration_ms"]) for e in friction_events if "hook_duration_ms" in e]
        gate_fails = [int(e["gate_failures"]) for e in friction_events if "gate_failures" in e]
        prompts = [int(e["permission_prompts"]) for e in friction_events if "permission_prompts" in e]
        friction_summary: dict[str, Any] = {
            "status": "measured",
            "events_count": len(friction_events),
            "median_hook_duration_ms": round(float(statistics.median(hook_ms)), 1) if hook_ms else None,
            "gate_failures_per_event": round(sum(gate_fails) / len(gate_fails), 2) if gate_fails else 0.0,
            "permission_prompts_per_session": round(sum(prompts) / len(prompts), 2) if prompts else 0.0,
        }
    else:
        friction_summary = {
            "status": "unmeasurable",
            "reason": f"no agent friction telemetry events recorded in {friction_file.name}",
        }

    # 2. Perceptual pulse (`deploy-logs/devex-pulse.jsonl`)
    pulse_file = deploy_logs_dir / "devex-pulse.jsonl"
    pulse_entries: list[dict[str, Any]] = []
    if pulse_file.is_file():
        for line in pulse_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                pe: dict[str, Any] = json.loads(line)
                if isinstance(pe, dict):
                    pulse_entries.append(pe)
            except Exception:
                continue

    if pulse_entries:
        latest_pulse = pulse_entries[-1]
        pulse_summary: dict[str, Any] = {
            "status": "measured",
            "entries_count": len(pulse_entries),
            "latest": latest_pulse,
        }
    else:
        pulse_summary = {
            "status": "unmeasurable",
            "reason": "no weekly 3-question owner pulse recorded in deploy-logs/devex-pulse.jsonl",
        }

    # 3. Structural guardrail coverage context
    prepush_suites = 0
    total_suites = 0
    if suites_path.is_file():
        sdoc = _load_json_dict(suites_path)
        slist = sdoc.get("suites")
        if isinstance(slist, list):
            total_suites = len(slist)
            prepush_suites = sum(1 for s in slist if isinstance(s, dict) and s.get("prepush"))

    typed_def_pct: float | None = None
    if typing_baseline_path.is_file():
        tdoc = _load_json_dict(typing_baseline_path)
        totals = tdoc.get("totals")
        if isinstance(totals, dict):
            total_defs = int(totals.get("total_defs", 0))
            untyped_defs = int(totals.get("untyped_defs", 0))
            if total_defs > 0:
                typed_def_pct = round(((total_defs - untyped_defs) / total_defs) * 100.0, 2)

    return {
        "record_type": "agent_devex",
        "charter_agdr": "AgDR-0036",
        "agent_friction": friction_summary,
        "owner_perceptual_pulse": pulse_summary,
        "guardrail_context": {
            "total_registered_suites": total_suites,
            "prepush_fast_gate_suites": prepush_suites,
            "python_typed_defs_pct": typed_def_pct,
        },
    }


def compute_impact_from_tasks(tasks_dir: Path = TASKS_DIR) -> dict[str, Any]:
    if not tasks_dir.is_dir():
        return {
            "status": "unmeasurable",
            "reason": f"tasks directory not found at {tasks_dir}",
        }
    done_by_area: dict[str, int] = {}
    all_by_area: dict[str, int] = {}
    unconfirmed_inferred: list[str] = []

    for p in sorted(tasks_dir.glob("T*.md")):
        txt = p.read_text(encoding="utf-8", errors="ignore")
        tid = p.stem
        if INFERRED_AREA_RE.search(txt) and tid not in CONFIRMED_AREA_OVERRIDES:
            unconfirmed_inferred.append(tid)
        if not txt.startswith("---"):
            continue
        end = txt.find("\n---", 3)
        if end == -1:
            continue
        fm_block = txt[3:end]
        status_val = ""
        area_val = ""
        for line in fm_block.splitlines():
            s = line.strip()
            if s.startswith("status:"):
                status_val = re.split(r"\s+#", s.split(":", 1)[1].strip(), maxsplit=1)[0].strip()
            elif s.startswith("area:"):
                area_val = re.split(r"\s+#", s.split(":", 1)[1].strip(), maxsplit=1)[0].strip()
        if tid in CONFIRMED_AREA_OVERRIDES:
            area_val = CONFIRMED_AREA_OVERRIDES[tid]
        area_key = area_val or "unassigned"
        all_by_area[area_key] = all_by_area.get(area_key, 0) + 1
        if status_val in ("done", "archived"):
            done_by_area[area_key] = done_by_area.get(area_key, 0) + 1

    total_done = sum(done_by_area.values())
    if total_done == 0:
        return {
            "status": "unmeasurable",
            "reason": "0 done tickets found in .tasks/",
        }

    product_done = sum(cnt for area, cnt in done_by_area.items() if area in PRODUCT_AREAS)
    platform_done = sum(cnt for area, cnt in done_by_area.items() if area in PLATFORM_AREAS)

    return {
        "status": "measured",
        "total_tickets": sum(all_by_area.values()),
        "done_tickets": total_done,
        "product_done_share_pct": round((product_done / total_done) * 100.0, 2),
        "platform_sdlc_done_share_pct": round((platform_done / total_done) * 100.0, 2),
        "done_by_area": dict(sorted(done_by_area.items(), key=lambda kv: (-kv[1], kv[0]))),
        "unconfirmed_inferred_areas_count": len(unconfirmed_inferred),
        "unconfirmed_inferred_tickets": unconfirmed_inferred,
    }


def compute_dx_core_4(
    dora_5: dict[str, Any],
    agent_devex: dict[str, Any],
    *,
    tasks_dir: Path = TASKS_DIR,
) -> dict[str, Any]:
    m = dora_5["metrics"]
    impact = compute_impact_from_tasks(tasks_dir)
    return {
        "record_type": "dx_core_4",
        "charter_agdr": "AgDR-0036",
        "space_dimensions_covered": [
            "Satisfaction & Well-Being (owner perceptual pulse)",
            "Performance (Change Fail Rate, Rework Rate, DX Core 4 Impact)",
            "Activity (context-only denominator: release & ticket counts)",
            "Communication & Collaboration (Backstage catalog & incident ledger)",
            "Efficiency & Flow (Lead Time, Deployment Frequency, Agent hook friction)",
        ],
        "dimensions": {
            "speed": {
                "deployment_frequency": m["deployment_frequency"],
                "lead_time_for_changes": m["lead_time_for_changes"],
            },
            "effectiveness": {
                "agent_friction": agent_devex["agent_friction"],
                "owner_perceptual_pulse": agent_devex["owner_perceptual_pulse"],
            },
            "quality": {
                "change_fail_rate": m["change_fail_rate"],
                "failed_deployment_recovery_time": m["failed_deployment_recovery_time"],
                "deployment_rework_rate": m["deployment_rework_rate"],
                "python_typed_defs_pct": agent_devex["guardrail_context"]["python_typed_defs_pct"],
            },
            "impact": impact,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit DORA 5, Agent-DevEx, and DX Core 4 JSONL records.")
    parser.add_argument("--since", type=int, default=30, help="Lookback window in days (default: 30)")
    parser.add_argument("--service", default=None, help="Optional service filter (e.g., release, web, cp)")
    parser.add_argument("--pulse", action="store_true", help="Emit/record Agent-DevEx & owner pulse JSONL")
    parser.add_argument("--flow", type=int, default=None, help="Owner pulse Q1: Flow & Focus (1..5)")
    parser.add_argument("--feedback", type=int, default=None, help="Owner pulse Q2: Feedback Loop Speed (1..5)")
    parser.add_argument(
        "--cognitive-load",
        type=int,
        default=None,
        help="Owner pulse Q3: Cognitive Load & Clarity (1..5)",
    )
    parser.add_argument("--notes", default="", help="Optional notes for owner pulse")
    args = parser.parse_args(argv)

    if args.flow is not None or args.feedback is not None or args.cognitive_load is not None:
        if args.flow is None or args.feedback is None or args.cognitive_load is None:
            print(
                "❌ Recording a 3-question owner pulse requires all three flags: --flow <1-5> --feedback <1-5> --cognitive-load <1-5>",
                file=sys.stderr,
            )
            return 1
        try:
            recorded = record_owner_pulse(
                int(args.flow),
                int(args.feedback),
                int(args.cognitive_load),
                str(args.notes),
            )
            print(json.dumps({"record_type": "owner_pulse_recorded", **recorded}, sort_keys=True))
        except ValueError as err:
            print(f"❌ {err}", file=sys.stderr)
            return 1

    devex = compute_agent_devex()
    if args.pulse:
        print(json.dumps(devex, sort_keys=True))
        return 0

    dora = compute_dora_5(since_days=int(args.since), service=args.service)
    core4 = compute_dx_core_4(dora, devex)

    print(json.dumps(dora, sort_keys=True))
    print(json.dumps(devex, sort_keys=True))
    print(json.dumps(core4, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
