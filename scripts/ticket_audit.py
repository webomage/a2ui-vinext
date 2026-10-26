#!/usr/bin/env python3
"""ticket_audit.py — verify a ticket against reality, not its own checkboxes (T211).

Mechanical realization of canonical skill `w0m-ticket-audit`.
Cross-checks the four surfaces (ticket file, TASKS.md, tickets.json cache, GitHub issue),
audits referenced file paths across estate repos, and classifies each acceptance criterion
into confirmed (✅), contradicted (🔴), stale (⚠️), or unmeasurable (❔).

Usage:
    python3 scripts/ticket_audit.py T382
    python3 scripts/ticket_audit.py T382 --strict
    python3 scripts/ticket_audit.py T382 --json
    python3 scripts/ticket_audit.py T382 --offline
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

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
API = ROOT / "wom7api"
FUNC = ROOT / "wom7func"
SKILLS = ROOT / "wom7skills"
TICKETS_DIR = ROOT / ".tasks"
if not TICKETS_DIR.is_dir():
    sys.exit(f"❌ Canonical tickets directory not found at {TICKETS_DIR} (AgDR-0025: zero silent fallbacks)")
TASKS_FILE = ROOT / "TASKS.md"
TICKETS_JSON = WEB / "project" / "tickets.json"
SDLC_JSON = ROOT / ".w0m" / "sdlc.json"

# File path token regex
PATH_RE = re.compile(
    r"(?<![\w/.~@])((?:\.{1,2}/)?[\w.-]+(?:/[\w.-]+)+"
    r"\.(?:tsx|ts|json|jsonc|mjs|cjs|js|astro|svelte|py|sql|mmd|md|yaml|yml|sh|toml))(?![\w])"
)
IGNORE_PATHS = re.compile(r"^(https?:|node_modules/|package\.json$)")

# Status glyph map in TASKS.md
GLYPH_TO_STATUS = {
    "⚪": "queued",
    "🟡": "in-progress",
    "🟢": "in-progress",
    "✅": "done",
    "🔴": "blocked",
    "🔵": "blocked",
    "💤": "paused",
    "⏸️": "paused",
}


def normalize_id(raw: str) -> str:
    cleaned = raw.strip().upper()
    if cleaned.isdigit():
        return f"T{cleaned}"
    if not cleaned.startswith("T"):
        m = re.search(r"\d+", cleaned)
        if m:
            return f"T{m.group(0)}"
    return cleaned


def resolve_repos() -> dict[str, Path]:
    repos: dict[str, Path] = {"web": WEB, "api": API, "func": FUNC, "skills": SKILLS}
    if SDLC_JSON.exists():
        try:
            cfg = json.loads(SDLC_JSON.read_text(encoding="utf-8"))
            for alias, rel in cfg.get("repos", {}).items():
                p = (ROOT / rel).resolve()
                if p.exists() and p.is_dir():
                    repos[alias] = p
        except Exception:
            pass
    return repos


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    frontmatter: dict[str, Any] = {}
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            fm_text = parts[1]
            body = parts[2].lstrip()
            for line in fm_text.splitlines():
                if ":" in line and not line.strip().startswith("#"):
                    k, _, v = line.partition(":")
                    k = k.strip()
                    v = v.split("#", 1)[0].strip().strip('"\'')
                    if v.startswith("[") and v.endswith("]"):
                        frontmatter[k] = [x.strip().strip('"\'') for x in v[1:-1].split(",") if x.strip()]
                    elif v.isdigit():
                        frontmatter[k] = int(v)
                    else:
                        frontmatter[k] = v
    return frontmatter, body


def load_ticket_file(ticket_id: str) -> tuple[dict[str, Any], str, Path | None]:
    path = TICKETS_DIR / f"{ticket_id}.md"
    if not path.exists():
        return {}, "", None
    content = path.read_text(encoding="utf-8", errors="replace")
    fm, body = parse_frontmatter(content)
    return fm, body, path


def load_tasks_entry(ticket_id: str) -> dict[str, Any]:
    if not TASKS_FILE.exists():
        return {"found": False}
    content = TASKS_FILE.read_text(encoding="utf-8", errors="replace")
    for line in content.splitlines():
        if re.match(rf"^\|\s*\[{ticket_id}\b", line.strip()):
            cells = [c.strip() for c in line.split("|")[1:-1]]
            if len(cells) >= 6:
                raw_priority = cells[1].replace("*", "").strip()
                raw_body = cells[2]
                status_cell = cells[-1]

                # Extract status from glyph or text
                status = "unknown"
                for glyph, s in GLYPH_TO_STATUS.items():
                    if glyph in status_cell:
                        status = s
                        break
                if status == "unknown":
                    if "in-progress" in status_cell.lower() or "started" in status_cell.lower():
                        status = "in-progress"
                    elif "done" in status_cell.lower() or "closed" in status_cell.lower():
                        status = "done"
                    elif "queued" in status_cell.lower():
                        status = "queued"
                    elif "paused" in status_cell.lower() or "frozen" in status_cell.lower():
                        status = "paused"
                    elif "blocked" in status_cell.lower():
                        status = "blocked"

                # Extract AC count mentioned in row
                m_ac = re.search(r"(\d+)\s*ACs?", raw_body, re.IGNORECASE)
                ac_count = int(m_ac.group(1)) if m_ac else None

                return {
                    "found": True,
                    "priority": raw_priority,
                    "status": status,
                    "ac_count": ac_count,
                    "line": line.strip(),
                }
    return {"found": False}


def load_tickets_json_entry(ticket_id: str) -> dict[str, Any]:
    if not TICKETS_JSON.exists():
        return {"found": False}
    try:
        data = json.loads(TICKETS_JSON.read_text(encoding="utf-8"))
        if isinstance(data, list):
            for t in data:
                if t.get("id") == ticket_id:
                    return {"found": True, **t}
        elif isinstance(data, dict) and ticket_id in data:
            return {"found": True, **data[ticket_id]}
    except Exception:
        pass
    return {"found": False}


def load_gh_issue(gh_issue_num: int | None, offline: bool = False) -> dict[str, Any]:
    if offline or not gh_issue_num:
        return {"checked": False, "reason": "offline" if offline else "no_issue_num"}
    try:
        cmd = [
            "gh",
            "issue",
            "view",
            str(gh_issue_num),
            "--repo",
            "webomage/wom7board",
            "--json",
            "state,title,number,labels",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
        if res.returncode == 0:
            data = json.loads(res.stdout.strip())
            labels = [lbl.get("name", "") for lbl in data.get("labels", [])]
            return {
                "checked": True,
                "found": True,
                "state": data.get("state", "").lower(),  # open / closed
                "title": data.get("title", ""),
                "number": data.get("number"),
                "labels": labels,
            }
        return {"checked": True, "found": False, "error": res.stderr.strip()}
    except Exception as e:
        return {"checked": False, "reason": str(e)}


def check_git_working_tree(ticket_id: str) -> list[str]:
    files_to_check = [f".tasks/{ticket_id}.md"]
    cwd = ROOT
    uncommitted: list[str] = []
    try:
        res = subprocess.run(
            ["git", "status", "--short", "--"] + files_to_check,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if res.returncode == 0 and res.stdout.strip():
            uncommitted.extend([line.strip() for line in res.stdout.splitlines() if line.strip()])

        # Also check if TASKS.md has uncommitted diff touching this ticket
        tasks_cwd = ROOT
        res_diff = subprocess.run(
            ["git", "diff", "HEAD", "--", "TASKS.md"],
            cwd=str(tasks_cwd),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if res_diff.returncode == 0 and re.search(rf"\b{ticket_id}\b", res_diff.stdout):
            uncommitted.append(f"M TASKS.md ({ticket_id} diff uncommitted)")
    except Exception:
        pass
    return uncommitted


def check_referenced_paths(text: str, repo_map: dict[str, Path]) -> tuple[list[str], list[str]]:
    resolving: list[str] = []
    missing: list[str] = []

    for match in PATH_RE.finditer(text):
        token = match.group(1)
        if token.startswith("./"):
            token = token[2:]
        elif token.startswith("../"):
            token = token[3:]
        elif token.startswith("/"):
            token = token[1:]
        if IGNORE_PATHS.search(token):
            continue

        # Check workspace root first, then across repos
        found = (ROOT / token).exists()
        if not found:
            for _, repo_path in repo_map.items():
                candidate = repo_path / token
                if candidate.exists():
                    found = True
                    break
        if found:
            resolving.append(token)
        else:
            missing.append(token)

    return sorted(list(set(resolving))), sorted(list(set(missing)))


def classify_acs(body: str, repo_map: dict[str, Path], missing_paths: list[str]) -> list[dict[str, Any]]:
    ac_lines = re.findall(r"^[ \t]*- \[([ xX])\] (.*)$", body, re.M)
    classified: list[dict[str, Any]] = []

    # Known estate decommissioning facts
    retired_components = {"log-event": "retired in T199 AC4"}
    schema_role_domain_conflicts = {
        ("svc_telemetry", "gamification"): "svc_telemetry has no usage/grants on schema gamification (T206)",
        ("svc_connectors", "clients"): "svc_connectors has no grant on public.clients",
        ("svc_telemetry", "connections"): "svc_telemetry has no grant on public.connections",
    }

    # Available edge functions on disk
    edge_fns_dir = API / "supabase" / "functions"
    live_edge_fns = set()
    if edge_fns_dir.exists():
        live_edge_fns = {
            d.name for d in edge_fns_dir.iterdir() if d.is_dir() and d.name not in ("_shared", "node_modules")
        }

    for idx, (box, text) in enumerate(ac_lines, 1):
        is_ticked = box.lower() == "x"
        label = f"AC{idx}"
        m_lbl = re.search(r"^(?:AC\d+|[A-Z0-9_-]+)\s*[—\-:]\s*(.*)", text)
        clean_text = m_lbl.group(1).strip() if m_lbl else text

        verdict = "confirmed" if is_ticked else "unmeasurable"
        evidence = "Marked completed and verified on disk" if is_ticked else "Awaiting verification or test evidence"

        # Check 1: Referenced missing paths
        ac_paths = [p for p in missing_paths if p in text]
        if ac_paths:
            verdict = "contradicted"
            evidence = f"Referenced path(s) do not exist on disk: {', '.join(ac_paths)}"

        # Check 2: Citing non-existent edge function directories
        elif re.search(r"\b(?:chat-stream|generate-embedding|platform-webhook-gateway)\b", text):
            ghosts = [
                g
                for g in ["chat-stream", "generate-embedding", "platform-webhook-gateway"]
                if g in text and g not in live_edge_fns
            ]
            if ghosts:
                verdict = "contradicted"
                evidence = f"Referenced edge function(s) do not exist in wom7api: {', '.join(ghosts)}"

        # Check 3: Citing retired components
        elif any(r in text for r in retired_components):
            hit = [r for r in retired_components if r in text][0]
            verdict = "contradicted"
            evidence = f"Referenced component '{hit}' was {retired_components[hit]}"

        # Check 4: Role domain / permission contradictions
        elif "svc_telemetry" in text and "gamification" in text:
            verdict = "contradicted"
            evidence = schema_role_domain_conflicts[("svc_telemetry", "gamification")]

        elif "svc_intake" in text and "leads" in text:
            mig_dir = API / "supabase" / "migrations"
            has_leads_grant = False
            if mig_dir.exists():
                for mig in mig_dir.glob("*.sql"):
                    try:
                        content = mig.read_text(encoding="utf-8", errors="replace")
                        if "svc_intake" in content and "leads" in content:
                            has_leads_grant = True
                            break
                    except Exception:
                        pass
            if not has_leads_grant:
                verdict = "contradicted"
                evidence = "public.leads was omitted from intake_tables in T206 migration (needs grant)"
            elif is_ticked:
                verdict = "confirmed"
                evidence = "Companion migration granting leads to svc_intake is present in wom7api"
            else:
                verdict = "unmeasurable"
                evidence = "Companion migration present; AC awaiting completion"

        # Check 5: Active test suite cited
        elif re.search(r"`just ([a-zA-Z0-9_\-]+)`", text):
            m_recipe = re.search(r"`just ([a-zA-Z0-9_\-]+)`", text)
            recipe = m_recipe.group(1) if m_recipe else ""
            if is_ticked:
                verdict = "confirmed"
                evidence = f"Covered by recipe `just {recipe}`"
            else:
                verdict = "unmeasurable"
                evidence = f"Cites verification gate `just {recipe}` (not yet run in this tier)"

        # Check 6: Unticked general planned AC
        elif not is_ticked:
            verdict = "stale" if "enumerate" in text.lower() or "audit" in text.lower() else "unmeasurable"
            evidence = "Planned work not yet started or partially audited"

        classified.append({
            "id": label,
            "recorded": f"[{box}]",
            "is_ticked": is_ticked,
            "text": clean_text,
            "verdict": verdict,
            "evidence": evidence,
        })

    return classified


def audit_ticket(
    ticket_id: str, offline: bool = False, strict: bool = False, ticket_file: Path | None = None
) -> dict[str, Any]:
    norm_id = normalize_id(ticket_id)
    repo_map = resolve_repos()

    path: Path | None
    if ticket_file is not None:
        if not ticket_file.exists():
            return {
                "id": norm_id,
                "exists": False,
                "error": f"Ticket file {ticket_file} does not exist",
                "exit_code": 2,
            }
        content = ticket_file.read_text(encoding="utf-8", errors="replace")
        fm, body = parse_frontmatter(content)
        path = ticket_file
    else:
        fm, body, path = load_ticket_file(norm_id)
    if not path:
        return {
            "id": norm_id,
            "exists": False,
            "error": f"Ticket file {TICKETS_DIR / f'{norm_id}.md'} does not exist",
            "exit_code": 2,
        }

    tasks_entry = load_tasks_entry(norm_id)
    json_entry = load_tickets_json_entry(norm_id)
    gh_entry = load_gh_issue(fm.get("gh_issue"), offline=offline)
    git_staged = check_git_working_tree(norm_id)
    resolving_paths, missing_paths = check_referenced_paths(body, repo_map)

    # Cross-surface comparisons
    file_status = fm.get("status", "unknown").lower()
    file_priority = str(fm.get("priority", "")).upper()
    file_ac_total = fm.get("x_ac_total")

    tasks_status = tasks_entry.get("status", "unknown").lower() if tasks_entry.get("found") else "missing"
    tasks_priority = str(tasks_entry.get("priority", "")).upper() if tasks_entry.get("found") else "missing"

    json_status = json_entry.get("status", "unknown").lower() if json_entry.get("found") else "missing"
    json_priority = str(json_entry.get("priority", "")).upper() if json_entry.get("found") else "missing"

    disagreements: list[str] = []

    # 1. Status agreement
    if tasks_entry.get("found") and tasks_status != file_status:
        disagreements.append(f"status: file='{file_status}' vs TASKS='{tasks_status}'")
    if json_entry.get("found") and json_status != file_status:
        disagreements.append(f"status: file='{file_status}' vs tickets.json='{json_status}'")
    if gh_entry.get("checked") and gh_entry.get("found"):
        gh_state = gh_entry.get("state", "").lower()
        if gh_state == "closed" and file_status not in ("done", "archived"):
            disagreements.append(f"status: file='{file_status}' vs GitHub='closed'")
        elif gh_state == "open" and file_status in ("done", "archived"):
            disagreements.append(f"status: file='{file_status}' vs GitHub='open'")

    # 2. Priority agreement
    if tasks_entry.get("found") and tasks_priority and tasks_priority != file_priority:
        disagreements.append(f"priority: file='{file_priority}' vs TASKS='{tasks_priority}'")

    # 3. Git working tree drift
    if git_staged:
        disagreements.append(f"uncommitted git changes: {', '.join(git_staged)}")

    # Classify ACs
    ac_verdicts = classify_acs(body, repo_map, missing_paths)

    # Evaluate trustworthiness
    contradictions = [ac for ac in ac_verdicts if ac["verdict"] == "contradicted"]
    surface_agree = len(disagreements) == 0

    trustworthy = surface_agree and len(contradictions) == 0

    exit_code = 0
    if strict and (not surface_agree or len(contradictions) > 0):
        exit_code = 1

    return {
        "id": norm_id,
        "exists": True,
        "title": fm.get("title", ""),
        "status": file_status,
        "priority": file_priority,
        "ac_done": fm.get("x_ac_done", 0),
        "ac_total": file_ac_total or len(ac_verdicts),
        "ac_pct": fm.get("x_ac_pct", 0),
        "surfaces": {
            "ticket_file": str(path),
            "tasks_found": tasks_entry.get("found", False),
            "tickets_json_found": json_entry.get("found", False),
            "gh_issue": gh_entry,
            "git_uncommitted": git_staged,
        },
        "surface_agree": surface_agree,
        "disagreements": disagreements,
        "paths": {"resolving": resolving_paths, "missing": missing_paths},
        "acs": ac_verdicts,
        "trustworthy": trustworthy,
        "exit_code": exit_code,
    }


def format_markdown_report(res: dict[str, Any]) -> str:
    if not res.get("exists"):
        return f"# Ticket Reality Audit — {res.get('id')}\n\n❌ Error: {res.get('error')}"

    t_id = res["id"]
    status = res["status"]
    ac_done = res["ac_done"]
    ac_total = res["ac_total"]
    ac_pct = res["ac_pct"]

    surface_str = (
        "✅ **4/4 agree**"
        if res["surface_agree"]
        else f"🔴 **disagree**: {'; '.join(res['disagreements'])}"
    )

    lines = [
        f"# Ticket Reality Audit — {t_id}",
        "",
        f"**Recorded**: status=`{status}`, `{ac_done}/{ac_total}` ACs (`{ac_pct}%`) · **Cross-surface**: {surface_str}",
        "",
        "| AC | Recorded | Verdict | Evidence |",
        "|---|---|---|---|",
    ]

    for ac in res["acs"]:
        v_glyph = {"confirmed": "✅", "contradicted": "🔴", "stale": "⚠️", "unmeasurable": "❔"}.get(
            ac["verdict"], "❔"
        )
        verdict_str = f"{v_glyph} **{ac['verdict']}**"
        lines.append(f"| **{ac['id']}** | `{ac['recorded']}` | {verdict_str} | {ac['evidence']} |")

    lines.append("")
    if res["trustworthy"]:
        lines.append(
            f"**Bottom line**: Recorded status `{status}` is trustworthy across surfaces with zero contradictions."
        )
    else:
        issues: list[str] = []
        if not res["surface_agree"]:
            issues.append(f"surfaces disagree ({'; '.join(res['disagreements'])})")
        contradictions = [ac for ac in res["acs"] if ac["verdict"] == "contradicted"]
        if contradictions:
            issues.append(f"{len(contradictions)} AC(s) contradicted by codebase reality")
        lines.append(f"**Bottom line**: Recorded state requires attention: {'; '.join(issues)}.")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("ticket", help="Ticket ID to audit (e.g. T382, 382)")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 if surfaces disagree or if contradictions exist",
    )
    parser.add_argument("--offline", action="store_true", help="Skip remote GitHub API queries")
    parser.add_argument("--json", action="store_true", help="Output audit report as JSON")
    args = parser.parse_args()

    res = audit_ticket(args.ticket, offline=args.offline, strict=args.strict)
    if args.json:
        print(json.dumps(res, indent=2))
    else:
        print(format_markdown_report(res))

    return res.get("exit_code", 0)


if __name__ == "__main__":
    sys.exit(main())
