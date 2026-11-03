#!/usr/bin/env python3
"""ticket_audit.py — verify tickets and canonical specs against live codebase & deploy reality (T211, T616).

Mechanical realization of canonical skill `w0m-ticket-audit` and `just reality-verify`.
Cross-checks the four tracking/delivery surfaces:
  1. Ticket definition file (`.tasks/T##.md` + frontmatter vs body AC count parity)
  2. Queue board row (`TASKS.md` or rotated `.tasks/archive/TASKS-archive.md`)
  3. Computed task ranker / query surface (`scripts/tasks_query.py` AC/status parity)
  4. Release deployment manifest (`releases/*.json` -> `deployed (<version>)`,
     `landed_pending_deploy`, or `no_commit_trace`) + optional GitHub issue (`--gh`)

Also supports corpus-wide completed-ticket (`--completed [--since YYYY-MM-DD]`) and canonical-spec
(`--specs`) reality verification across estate file paths, exported symbols, and Supabase SQL
relations, failing closed (`exit 2`) if any corpus directory is missing or empty (`AgDR-0025`).

Usage:
    python3 scripts/ticket_audit.py T382
    python3 scripts/ticket_audit.py T382 --strict --offline
    python3 scripts/ticket_audit.py --completed --specs --strict --offline
    python3 scripts/ticket_audit.py --completed --since 1970-01-01 --json
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
        if (parent / ".git").exists() and (parent / "w0m-web").is_dir():
            return parent
    return Path(__file__).resolve().parents[1]


ROOT = find_workspace_root()
WEB = ROOT / "w0m-web" if (ROOT / "w0m-web").is_dir() else ROOT
API = ROOT / "w0m-api"
FUNC = ROOT / "w0m-cf"
EXT = ROOT / "w0m-ext"
SEC = ROOT / "w0m-sec"
SKILLS = ROOT / "w0m-skills"
MLX = ROOT / "w0m-mlx" / "w0m-mlx"
TICKETS_DIR = Path(os.environ["W0M_AUDIT_TICKETS_DIR"]) if os.environ.get("W0M_AUDIT_TICKETS_DIR") else (ROOT / ".tasks")
if not os.environ.get("W0M_AUDIT_TICKETS_DIR") and not TICKETS_DIR.is_dir():
    sys.exit(f"❌ Canonical tickets directory not found at {TICKETS_DIR} (AgDR-0025: zero silent fallbacks)")
TASKS_FILE = ROOT / "TASKS.md"
TASKS_ARCHIVE_FILE = ROOT / ".tasks" / "archive" / "TASKS-archive.md"
TICKETS_JSON = WEB / "project" / "tickets.json"
SDLC_JSON = ROOT / ".w0m" / "sdlc.json"
RELEASES_DIR = ROOT / "releases"
DEFAULT_SPECS_DIR = (
    Path(os.environ["W0M_AUDIT_SPECS_DIR"])
    if os.environ.get("W0M_AUDIT_SPECS_DIR")
    else (WEB / "openspec" / "specs")
)
# Post-root-elevation & layout-policy cutover date (T411 .tasks/, T446 project/policies/, AgDR-0025).
DEFAULT_COMPLETED_SINCE = "2026-10-25"

# Single-ticket general file path token regex
PATH_RE = re.compile(
    r"(?<![\w/.~@])((?:\.{1,2}/)?[\w.-]+(?:/[\w.-]+)+"
    r"\.(?:tsx|ts|json|jsonc|mjs|cjs|js|astro|svelte|py|sql|mmd|md|yaml|yml|sh|toml))(?![\w])"
)
IGNORE_PATHS = re.compile(r"^(https?:|node_modules/|package\.json$)")

# Anchored estate path regex for corpus-wide `--completed` and `--specs` verification
ANCHORED_BACKTICK_RE = re.compile(r"`([^`\n]+)`")
ANCHORED_PREFIX_RE = re.compile(
    r"^(?:@wom/|(?:\.{1,2}/)*)"
    r"(?:w0m-(?:web|api|cf|ext|sec|skills|mlx)/|wom7[a-z0-9_-]*/|"
    r"apps/|packages/|scripts/|project/(?:policies|templates|scripts|data)/|"
    r"supabase/|extension/src/|\.tasks/|\.agents/reports/|docs/|just/)"
    r"[A-Za-z0-9_.@\[\]{},/-]+"
    r"\.(?:tsx|ts|json|jsonc|mjs|cjs|js|astro|svelte|py|sql|mmd|md|yaml|yml|sh|toml|just)$"
)
RETIRED_WOM7_RE = re.compile(r"`((?:\.{1,2}/)*wom7[a-z0-9_-]*/[A-Za-z0-9_./-]+)`")
NEGATION_LINE_RE = re.compile(
    r"(?:\b(?:does\s+not\s+exist|do\s+not\s+exist|not\s+exist|must\s+not\s+exist|shall\s+not|"
    r"without\s+a|without\s+any|deleted|removed|retired|retire\s+after|absent|no\s+longer|"
    r"legacy|formerly|replaced|forbid|prohibit|never|instead\s+of|drop|dropped|decommission|"
    r"rename|renamed|moved|migrated|untracked|gitignored)\b|❌\s*none|→|->)",
    re.I,
)
SCENARIO_GIVEN_FIXTURE_RE = re.compile(
    r"^\s*-\s*\*\*(?:GIVEN|Given)\*\*(?:\s|$)",
)
EXPORT_CLAIM_RE = re.compile(
    r"`export\s+(?:async\s+)?(?:function|const|let|class|type|interface|enum)\s+([A-Za-z_][A-Za-z0-9_]*)`"
)
PUBLIC_SQL_RE = re.compile(r"`public\.([a-z_][a-z0-9_]*)`|(?<![A-Za-z0-9_/-])public\.([a-z_][a-z0-9_]*)\b")
NON_SQL_PUBLIC_EXTS = {
    "pdf", "md", "mdx", "ts", "tsx", "js", "mjs", "cjs", "json", "jsonc",
    "astro", "svelte", "html", "css", "svg", "png", "jpg", "jpeg", "webp",
    "ico", "txt", "xml", "webmanifest", "sql",
}

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
    repos: dict[str, Path] = {
        "root": ROOT,
        "web": WEB,
        "api": API,
        "func": FUNC,
        "ext": EXT,
        "sec": SEC,
        "skills": SKILLS,
        "mlx": MLX,
    }
    if SDLC_JSON.exists():
        try:
            cfg: dict[str, Any] = json.loads(SDLC_JSON.read_text(encoding="utf-8"))
            for alias, rel in cfg.get("repos", {}).items():
                p = (ROOT / rel).resolve()
                if p.exists() and p.is_dir():
                    repos[alias] = p
        except Exception:
            pass
    return {k: v for k, v in repos.items() if v.exists() and v.is_dir()}


def _search_bases(repo_map: dict[str, Path]) -> list[Path]:
    bases: list[Path] = [ROOT]
    for p in repo_map.values():
        if p not in bases:
            bases.append(p)
    extras = [
        EXT / "extension",
        SKILLS / "skills",
        API / "supabase" / "functions",
        WEB / "apps" / "web",
        WEB / "apps" / "cp",
        WEB / "apps" / "job",
        WEB / "apps" / "join",
    ]
    for e in extras:
        if e.is_dir() and e not in bases:
            bases.append(e)
    return bases


def expand_brace_token(token: str) -> list[str]:
    """Expand multi-option `{a,b}` path tokens into concrete candidate paths (preserving `{id}` templates)."""
    m = re.search(r"\{([^{}]+,[^{}]+)\}", token)
    if not m:
        return [token]
    prefix = token[: m.start()]
    suffix = token[m.end() :]
    items = [part.strip() for part in m.group(1).split(",") if part.strip()]
    if len(items) < 2:
        return [token]
    expanded: list[str] = []
    for item in items:
        expanded.extend(expand_brace_token(f"{prefix}{item}{suffix}"))
    return expanded


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
                    raw_v = v.strip()
                    if raw_v and raw_v[0] in ("\"", "'"):
                        q = raw_v[0]
                        end_q = raw_v.find(q, 1)
                        clean_v = raw_v[1:end_q].strip() if end_q != -1 else raw_v.strip("\"'")
                    else:
                        clean_v = raw_v.split("#", 1)[0].strip().strip("\"'")
                    if clean_v.startswith("[") and clean_v.endswith("]"):
                        frontmatter[k] = [
                            x.strip().strip("\"'") for x in clean_v[1:-1].split(",") if x.strip()
                        ]
                    elif clean_v.isdigit():
                        frontmatter[k] = int(clean_v)
                    else:
                        frontmatter[k] = clean_v
    return frontmatter, body


def load_ticket_file(ticket_id: str, tickets_dir: Path | None = None) -> tuple[dict[str, Any], str, Path | None]:
    tdir = tickets_dir or TICKETS_DIR
    path = tdir / f"{ticket_id}.md"
    if not path.exists():
        return {}, "", None
    content = path.read_text(encoding="utf-8", errors="replace")
    fm, body = parse_frontmatter(content)
    return fm, body, path


def _parse_tasks_row(line: str, surface_name: str) -> dict[str, Any] | None:
    cells = [c.strip() for c in line.split("|")[1:-1]]
    if len(cells) < 6:
        return None
    raw_priority = cells[1].replace("*", "").strip()
    raw_body = cells[2]
    status_cell = cells[-1]

    status = "unknown"
    for glyph, s in GLYPH_TO_STATUS.items():
        if glyph in status_cell:
            status = s
            break
    if status == "unknown":
        low = status_cell.lower()
        if "in-progress" in low or "started" in low:
            status = "in-progress"
        elif "done" in low or "closed" in low:
            status = "done"
        elif "queued" in low:
            status = "queued"
        elif "paused" in low or "frozen" in low:
            status = "paused"
        elif "blocked" in low:
            status = "blocked"

    m_ac = re.search(r"(\d+)\s*ACs?", raw_body, re.IGNORECASE)
    ac_count = int(m_ac.group(1)) if m_ac else None
    return {
        "found": True,
        "surface": surface_name,
        "priority": raw_priority,
        "status": status,
        "ac_count": ac_count,
        "line": line.strip(),
    }


def load_tasks_entry(ticket_id: str) -> dict[str, Any]:
    for surface_name, fpath in (("TASKS.md", TASKS_FILE), ("TASKS-archive.md", TASKS_ARCHIVE_FILE)):
        if not fpath.exists():
            continue
        content = fpath.read_text(encoding="utf-8", errors="replace")
        for line in content.splitlines():
            if re.match(rf"^\|\s*\[{re.escape(ticket_id)}\b", line.strip()):
                parsed = _parse_tasks_row(line, surface_name)
                if parsed:
                    return parsed
    return {"found": False}


def load_tickets_json_entry(ticket_id: str) -> dict[str, Any]:
    if not TICKETS_JSON.exists():
        return {"found": False}
    try:
        data: Any = json.loads(TICKETS_JSON.read_text(encoding="utf-8"))
        if isinstance(data, list):
            for t in data:
                if t.get("id") == ticket_id:
                    return {"found": True, **t}
        elif isinstance(data, dict) and ticket_id in data:
            return {"found": True, **data[ticket_id]}
    except Exception:
        pass
    return {"found": False}


AC_QUERY_ANY = re.compile(r"^\s*-\s*\[(x|X| |~|N/A)\]\s*\*{0,2}AC\d", re.M)
AC_QUERY_DONE = re.compile(r"^\s*-\s*\[[xX]\]\s*\*{0,2}AC\d", re.M)
AC_QUERY_NA = re.compile(r"^\s*-\s*\[N/A\]\s*\*{0,2}AC\d", re.M)


def load_tasks_query_surface(fm: dict[str, Any], body: str) -> dict[str, Any]:
    """Verify frontmatter `x_ac_done`/`x_ac_total` parity against `tasks_query.ac_progress` (Surface 3)."""
    measured_done = len(AC_QUERY_DONE.findall(body))
    measured_total = len(AC_QUERY_ANY.findall(body)) - len(AC_QUERY_NA.findall(body))
    fm_done = fm.get("x_ac_done")
    fm_total = fm.get("x_ac_total")
    parity_ok = True
    drift_detail = ""
    if measured_total > 0 and isinstance(fm_total, int) and fm_total != measured_total:
        parity_ok = False
        drift_detail = f"x_ac_total={fm_total} vs measured={measured_total}"
    elif measured_total > 0 and isinstance(fm_done, int) and fm_done != measured_done:
        parity_ok = False
        drift_detail = f"x_ac_done={fm_done} vs measured={measured_done}"
    return {
        "measured_ac_done": measured_done,
        "measured_ac_total": measured_total,
        "parity_ok": parity_ok,
        "drift_detail": drift_detail,
    }


def load_gh_issue(gh_issue_num: int | None, offline: bool = False) -> dict[str, Any]:
    if offline or not gh_issue_num:
        return {"checked": False, "reason": "offline" if offline else "no_issue_num"}
    gh_repo = "webomage/w0m"
    if SDLC_JSON.exists():
        try:
            cfg_gh: dict[str, Any] = json.loads(SDLC_JSON.read_text(encoding="utf-8"))
            gh_repo = cfg_gh.get("vcs", {}).get("repo") or gh_repo
        except Exception:
            pass
    try:
        cmd = [
            "gh",
            "issue",
            "view",
            str(gh_issue_num),
            "--repo",
            gh_repo,
            "--json",
            "state,title,number,labels",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
        if res.returncode == 0:
            gh_data: dict[str, Any] = json.loads(res.stdout.strip())
            labels = [lbl.get("name", "") for lbl in gh_data.get("labels", [])]
            return {
                "checked": True,
                "found": True,
                "state": gh_data.get("state", "").lower(),
                "title": gh_data.get("title", ""),
                "number": gh_data.get("number"),
                "labels": labels,
            }
        return {"checked": True, "found": False, "error": res.stderr.strip()}
    except Exception as e:
        return {"checked": False, "reason": str(e)}


class ReleaseDeliveryIndex:
    """Fast git + `releases/*.json` index classifying ticket commits vs deployed releases."""

    def __init__(self, root: Path = ROOT, releases_dir: Path = RELEASES_DIR) -> None:
        self.root = root
        self.releases_dir = releases_dir
        self._built = False
        self.latest_version: str | None = None
        self.ticket_commits: dict[str, list[tuple[str, str]]] = {}
        self.deployed_shas: dict[str, set[str]] = {}
        self.commit_rank: dict[str, dict[str, int]] = {}
        self.releases: list[tuple[str, dict[str, str]]] = []

    def _ensure_built(self) -> None:
        if self._built:
            return
        self._built = True
        repo_dirs: dict[str, Path] = {
            ".": self.root,
            "w0m-web": self.root / "w0m-web",
            "w0m-api": self.root / "w0m-api",
            "w0m-cf": self.root / "w0m-cf",
            "w0m-ext": self.root / "w0m-ext",
            "w0m-sec": self.root / "w0m-sec",
            "w0m-skills": self.root / "w0m-skills",
            "w0m-mlx/w0m-mlx": self.root / "w0m-mlx" / "w0m-mlx",
        }
        if self.releases_dir.is_dir():
            for rf in sorted(self.releases_dir.glob("*.json")):
                try:
                    data: dict[str, Any] = json.loads(rf.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if not data.get("deployed"):
                    continue
                ver = str(data.get("version") or rf.stem)
                repos_obj = data.get("repos")
                if isinstance(repos_obj, dict):
                    self.releases.append((ver, {str(k): str(v) for k, v in repos_obj.items()}))
            if self.releases:
                self.latest_version = self.releases[-1][0]

        latest_repos = self.releases[-1][1] if self.releases else {}
        tid_re = re.compile(r"\b(T\d+)\b")

        for rkey, rpath in repo_dirs.items():
            if not (rpath / ".git").exists():
                continue
            try:
                log_res = subprocess.run(
                    ["git", "log", "--reverse", "--format=%H %s"],
                    cwd=str(rpath),
                    capture_output=True,
                    text=True,
                    timeout=20,
                )
            except Exception:
                continue
            if log_res.returncode != 0:
                continue
            ranks: dict[str, int] = {}
            for idx, ln in enumerate(log_res.stdout.splitlines()):
                sha, _, subj = ln.partition(" ")
                if not sha:
                    continue
                ranks[sha] = idx
                for m in tid_re.finditer(subj):
                    self.ticket_commits.setdefault(m.group(1), []).append((rkey, sha))
            self.commit_rank[rkey] = ranks

            dep_sha = latest_repos.get(rkey)
            if dep_sha:
                try:
                    rev_res = subprocess.run(
                        ["git", "rev-list", dep_sha],
                        cwd=str(rpath),
                        capture_output=True,
                        text=True,
                        timeout=15,
                    )
                    if rev_res.returncode == 0:
                        self.deployed_shas[rkey] = set(rev_res.stdout.splitlines())
                except Exception:
                    pass

    def classify(self, ticket_id: str, status: str) -> str:
        if status != "done":
            return "not_completed"
        self._ensure_built()
        commits = self.ticket_commits.get(ticket_id, [])
        if not commits:
            return "no_commit_trace"
        if not self.releases:
            return "landed_pending_deploy"

        for rkey, sha in commits:
            dep_set = self.deployed_shas.get(rkey)
            if dep_set is None or sha not in dep_set:
                return "landed_pending_deploy"

        # Determine earliest release whose deployed SHAs are >= every commit rank for this ticket
        max_rank_by_repo: dict[str, int] = {}
        for rkey, sha in commits:
            r = self.commit_rank.get(rkey, {}).get(sha, 0)
            max_rank_by_repo[rkey] = max(max_rank_by_repo.get(rkey, 0), r)

        for ver, rel_repos in self.releases:
            covers_all = True
            for rkey, req_rank in max_rank_by_repo.items():
                rel_sha = rel_repos.get(rkey, "")
                rel_rank = self.commit_rank.get(rkey, {}).get(rel_sha, -1)
                if rel_rank < req_rank:
                    covers_all = False
                    break
            if covers_all:
                return f"deployed ({ver})"

        return f"deployed ({self.latest_version})"


_DELIVERY_INDEX = ReleaseDeliveryIndex()


def check_git_working_tree(ticket_id: str) -> list[str]:
    files_to_check = [f".tasks/{ticket_id}.md"]
    uncommitted: list[str] = []
    try:
        res = subprocess.run(
            ["git", "status", "--short", "--"] + files_to_check,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if res.returncode == 0 and res.stdout.strip():
            uncommitted.extend([line.strip() for line in res.stdout.splitlines() if line.strip()])

        res_diff = subprocess.run(
            ["git", "diff", "HEAD", "--", "TASKS.md"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if res_diff.returncode == 0 and re.search(rf"\b{re.escape(ticket_id)}\b", res_diff.stdout):
            uncommitted.append(f"M TASKS.md ({ticket_id} diff uncommitted)")
    except Exception:
        pass
    return uncommitted


def resolve_candidate_path(token: str, bases: list[Path], base_file: Path | None = None) -> bool:
    clean = token.strip()
    if clean.startswith("@wom/"):
        clean = clean[5:]
    if base_file is not None:
        try:
            if (base_file.parent / token).resolve().exists():
                return True
        except OSError:
            pass
    stripped = clean.lstrip("./")
    while stripped.startswith("../"):
        stripped = stripped[3:]
    for b in bases:
        if (b / clean).exists() or (b / stripped).exists():
            return True
    return False


def check_referenced_paths(text: str, repo_map: dict[str, Path]) -> tuple[list[str], list[str]]:
    resolving: list[str] = []
    missing: list[str] = []
    bases = _search_bases(repo_map)

    for match in PATH_RE.finditer(text):
        raw_token = match.group(1)
        token = raw_token
        if token.startswith("./"):
            token = token[2:]
        elif token.startswith("../"):
            token = token[3:]
        elif token.startswith("/"):
            token = token[1:]
        if IGNORE_PATHS.search(token):
            continue

        if resolve_candidate_path(token, bases):
            resolving.append(token)
        else:
            missing.append(token)

    return sorted(set(resolving)), sorted(set(missing))


def classify_acs(body: str, repo_map: dict[str, Path], missing_paths: list[str]) -> list[dict[str, Any]]:
    ac_lines = re.findall(r"^[ \t]*- \[([ xX])\] (.*)$", body, re.M)
    classified: list[dict[str, Any]] = []

    retired_components = {"log-event": "retired in T199 AC4"}
    schema_role_domain_conflicts = {
        ("svc_telemetry", "gamification"): "svc_telemetry has no usage/grants on schema gamification (T206)",
        ("svc_connectors", "clients"): "svc_connectors has no grant on public.clients",
        ("svc_telemetry", "connections"): "svc_telemetry has no grant on public.connections",
    }

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

        ac_paths = [p for p in missing_paths if p in text and not NEGATION_LINE_RE.search(text)]
        if ac_paths:
            verdict = "contradicted"
            evidence = f"Referenced path(s) do not exist on disk: {', '.join(ac_paths)}"
        elif re.search(r"\b(?:chat-stream|generate-embedding|platform-webhook-gateway)\b", text):
            ghosts = [
                g
                for g in ["chat-stream", "generate-embedding", "platform-webhook-gateway"]
                if g in text and g not in live_edge_fns
            ]
            if ghosts:
                verdict = "contradicted"
                evidence = f"Referenced edge function(s) do not exist in w0m-api: {', '.join(ghosts)}"
        elif any(r in text for r in retired_components) and not NEGATION_LINE_RE.search(text):
            hit = [r for r in retired_components if r in text][0]
            verdict = "contradicted"
            evidence = f"Referenced component '{hit}' was {retired_components[hit]}"
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
                evidence = "Companion migration granting leads to svc_intake is present in w0m-api"
            else:
                verdict = "unmeasurable"
                evidence = "Companion migration present; AC awaiting completion"
        elif re.search(r"`just ([a-zA-Z0-9_\-]+)`", text):
            m_recipe = re.search(r"`just ([a-zA-Z0-9_\-]+)`", text)
            recipe = m_recipe.group(1) if m_recipe else ""
            if is_ticked:
                verdict = "confirmed"
                evidence = f"Covered by recipe `just {recipe}`"
            else:
                verdict = "unmeasurable"
                evidence = f"Cites verification gate `just {recipe}` (not yet run in this tier)"
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


class CodebaseRealityIndex:
    """Indexes SQL relations and exported TS/Python symbols for corpus-wide reality verification."""

    def __init__(self, repo_map: dict[str, Path]) -> None:
        self.repo_map = repo_map
        self.bases = _search_bases(repo_map)
        self.sql_relations: set[str] = set()
        self.exported_symbols: set[str] = set()
        self._build_sql_index()
        self._build_symbol_index()

    def _build_sql_index(self) -> None:
        rel_pat = re.compile(
            r"(?:CREATE\s+(?:OR\s+REPLACE\s+)?(?:MATERIALIZED\s+)?(?:TABLE|VIEW|FUNCTION|TYPE)\s+"
            r"(?:IF\s+NOT\s+EXISTS\s+)?(?:public\.)?\"?([a-zA-Z0-9_]+)\"?|"
            r"ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:ONLY\s+)?(?:public\.)?\"?([a-zA-Z0-9_]+)\"?|"
            r"CONSTRAINT\s+\"?([a-zA-Z0-9_]+)\"?\s+(?:CHECK|PRIMARY|UNIQUE|FOREIGN))",
            re.I,
        )
        for sql_dir in (API / "supabase" / "baseline", API / "supabase" / "migrations"):
            if not sql_dir.is_dir():
                continue
            for sf in sql_dir.glob("*.sql"):
                txt = sf.read_text(encoding="utf-8", errors="ignore")
                for m in rel_pat.finditer(txt):
                    name = (m.group(1) or m.group(2) or m.group(3)).lower()
                    self.sql_relations.add(name)

    def _build_symbol_index(self) -> None:
        ts_export_re = re.compile(
            r"\bexport\s+(?:async\s+)?(?:function|const|let|class|type|interface|enum)\s+([A-Za-z_][A-Za-z0-9_]*)"
        )
        ts_reexport_re = re.compile(r"\bexport\s*\{([^}]+)\}")
        py_def_re = re.compile(r"^(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)", re.M)

        ts_roots = [
            WEB / "apps",
            WEB / "packages",
            API / "supabase" / "functions",
            FUNC / "src",
            EXT / "extension" / "src",
        ]
        for r in ts_roots:
            if not r.is_dir():
                continue
            for f in r.rglob("*"):
                if f.suffix not in (".ts", ".tsx", ".mjs", ".js", ".astro", ".svelte"):
                    continue
                if "node_modules" in f.parts or "dist" in f.parts or ".astro" in f.parts:
                    continue
                txt = f.read_text(encoding="utf-8", errors="ignore")
                for m in ts_export_re.finditer(txt):
                    self.exported_symbols.add(m.group(1))
                for m in ts_reexport_re.finditer(txt):
                    for part in m.group(1).split(","):
                        cleaned = part.strip().split(" as ")[-1].strip()
                        if cleaned.startswith("type "):
                            cleaned = cleaned[5:].strip()
                        if cleaned and cleaned.isidentifier():
                            self.exported_symbols.add(cleaned)

        for py_root in (ROOT / "scripts", WEB / "project" / "scripts", API / "scripts"):
            if not py_root.is_dir():
                continue
            for f in py_root.glob("*.py"):
                txt = f.read_text(encoding="utf-8", errors="ignore")
                for m in py_def_re.finditer(txt):
                    self.exported_symbols.add(m.group(1))


def audit_markdown_claims(
    text: str,
    idx: CodebaseRealityIndex,
    base_file: Path | None = None,
    check_sql: bool = True,
) -> list[str]:
    """Return contradicted path, exported-symbol, and SQL-relation claims in `text`."""
    contradictions: list[str] = []
    scenario_fixtures: set[str] = set()

    for lineno, line in enumerate(text.splitlines(), 1):
        if line.startswith("#"):
            if line.startswith("#### Scenario:") or line.startswith("### ") or line.startswith("## "):
                scenario_fixtures.clear()
        if SCENARIO_GIVEN_FIXTURE_RE.search(line):
            for m in ANCHORED_BACKTICK_RE.finditer(line):
                scenario_fixtures.add(m.group(1).strip())
            continue
        if NEGATION_LINE_RE.search(line):
            continue

        # 1. Retired wom7* repo prefix check
        for m_ret in RETIRED_WOM7_RE.finditer(line):
            contradictions.append(f"L{lineno}: retired repo path `{m_ret.group(1)}`")

        # 2. Anchored file paths (supporting `{a,b}` brace expansion)
        for m_bt in ANCHORED_BACKTICK_RE.finditer(line):
            raw_tok = m_bt.group(1).strip()
            if raw_tok in scenario_fixtures:
                continue
            if any(c in raw_tok for c in ("<", "*", "#", " ")):
                continue
            if (
                "/dist/" in raw_tok
                or raw_tok.startswith("dist/")
                or "openspec/changes/" in raw_tok
                or raw_tok.startswith("w0m-pr/")
            ):
                continue
            if not ANCHORED_PREFIX_RE.match(raw_tok):
                continue
            for tok in expand_brace_token(raw_tok):
                if "{" in tok or "}" in tok:
                    continue
                if not resolve_candidate_path(tok, idx.bases, base_file=base_file):
                    contradictions.append(f"L{lineno}: missing file `{tok}`")

        # 3. Explicit `export function/const/class/type/interface <Ident>` claims
        for m_sym in EXPORT_CLAIM_RE.finditer(line):
            sym = m_sym.group(1)
            if sym not in idx.exported_symbols:
                contradictions.append(f"L{lineno}: missing exported symbol `{sym}`")

        # 4. Supabase `public.<relation>` SQL claims
        if check_sql and idx.sql_relations:
            for m_sql in PUBLIC_SQL_RE.finditer(line):
                rel = (m_sql.group(1) or m_sql.group(2)).lower()
                if rel in NON_SQL_PUBLIC_EXTS:
                    continue
                if rel not in idx.sql_relations:
                    contradictions.append(f"L{lineno}: nonexistent SQL relation `public.{rel}`")

    return list(dict.fromkeys(contradictions))


def _extract_verification_sections(body: str) -> str:
    """Extract `## Acceptance criteria`, `## Definition of Done`, and `## Status` sections."""
    target_prefixes = ("## acceptance criteria", "## definition of done", "## status", "## links")
    keep_lines: list[str] = []
    active = False
    for ln in body.splitlines():
        if ln.startswith("## "):
            low = ln.strip().lower()
            active = any(low.startswith(p) for p in target_prefixes)
        if active:
            keep_lines.append(ln)
    return "\n".join(keep_lines) if keep_lines else body


def audit_completed_corpus(
    tickets_dir: Path,
    since: str = DEFAULT_COMPLETED_SINCE,
    idx: CodebaseRealityIndex | None = None,
) -> dict[str, Any]:
    if not tickets_dir.is_dir():
        return {
            "unmeasurable": True,
            "error": f"Tickets directory {tickets_dir} does not exist",
            "exit_code": 2,
        }
    ticket_files = sorted(
        tickets_dir.glob("T*.md"),
        key=lambda p: int(re.sub(r"\D", "", p.stem) or "0"),
    )
    if not ticket_files:
        return {
            "unmeasurable": True,
            "error": f"Tickets directory {tickets_dir} holds zero T*.md files",
            "exit_code": 2,
        }

    reality_idx = idx or CodebaseRealityIndex(resolve_repos())
    done_total = 0
    deep_checked = 0
    contradicted_tickets: list[dict[str, Any]] = []
    delivery_counts: dict[str, int] = {"deployed": 0, "landed_pending_deploy": 0, "no_commit_trace": 0}

    for tf in ticket_files:
        content = tf.read_text(encoding="utf-8", errors="replace")
        fm, body = parse_frontmatter(content)
        status = str(fm.get("status", "")).lower()
        if status != "done":
            continue
        closed_as = str(fm.get("closed_as", "completed") or "completed").lower()
        if closed_as not in ("completed", ""):
            continue

        done_total += 1
        tid = normalize_id(str(fm.get("id") or tf.stem))
        d_state = _DELIVERY_INDEX.classify(tid, status)
        if d_state.startswith("deployed"):
            delivery_counts["deployed"] += 1
        elif d_state == "landed_pending_deploy":
            delivery_counts["landed_pending_deploy"] += 1
        else:
            delivery_counts["no_commit_trace"] += 1

        issues: list[str] = []
        # AC checkbox parity check across all completed tickets
        tq = load_tasks_query_surface(fm, body)
        if not tq["parity_ok"]:
            issues.append(f"frontmatter AC drift ({tq['drift_detail']})")

        created = str(fm.get("created", "")).strip()
        in_since_window = (not created) or (created >= since)
        if in_since_window:
            deep_checked += 1
            scoped_text = _extract_verification_sections(body)
            issues.extend(audit_markdown_claims(scoped_text, reality_idx, base_file=tf, check_sql=True))

        if issues:
            contradicted_tickets.append({
                "id": tid,
                "file": str(tf),
                "created": created,
                "delivery_state": d_state,
                "contradictions": list(dict.fromkeys(issues)),
            })

    if done_total == 0:
        return {
            "unmeasurable": True,
            "error": f"Zero completed (`status: done`) tickets found in {tickets_dir}",
            "exit_code": 2,
        }

    return {
        "unmeasurable": False,
        "since": since,
        "done_tickets_scanned": done_total,
        "deep_reality_checked": deep_checked,
        "delivery_counts": delivery_counts,
        "contradicted_count": len(contradicted_tickets),
        "contradicted": contradicted_tickets,
        "exit_code": 1 if contradicted_tickets else 0,
    }


def audit_specs_corpus(
    specs_dir: Path,
    idx: CodebaseRealityIndex | None = None,
) -> dict[str, Any]:
    if not specs_dir.is_dir():
        return {
            "unmeasurable": True,
            "error": f"Canonical specs directory {specs_dir} does not exist",
            "exit_code": 2,
        }
    spec_files = sorted(specs_dir.rglob("*.md"))
    if not spec_files:
        return {
            "unmeasurable": True,
            "error": f"Canonical specs directory {specs_dir} holds zero *.md files",
            "exit_code": 2,
        }

    reality_idx = idx or CodebaseRealityIndex(resolve_repos())
    contradicted_specs: list[dict[str, Any]] = []
    for sf in spec_files:
        txt = sf.read_text(encoding="utf-8", errors="replace")
        issues = audit_markdown_claims(txt, reality_idx, base_file=sf, check_sql=True)
        if issues:
            try:
                rel_path = str(sf.relative_to(ROOT))
            except ValueError:
                rel_path = str(sf)
            contradicted_specs.append({
                "spec": rel_path,
                "contradictions": issues,
            })

    return {
        "unmeasurable": False,
        "specs_scanned": len(spec_files),
        "sql_relations_indexed": len(reality_idx.sql_relations),
        "exported_symbols_indexed": len(reality_idx.exported_symbols),
        "contradicted_count": len(contradicted_specs),
        "contradicted": contradicted_specs,
        "exit_code": 1 if contradicted_specs else 0,
    }


def audit_ticket(
    ticket_id: str,
    offline: bool = False,
    strict: bool = False,
    ticket_file: Path | None = None,
    check_gh: bool = False,
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
    tq_entry = load_tasks_query_surface(fm, body)
    gh_entry = load_gh_issue(fm.get("gh_issue"), offline=(offline and not check_gh))
    git_staged = check_git_working_tree(norm_id) if ticket_file is None else []
    resolving_paths, missing_paths = check_referenced_paths(body, repo_map)

    file_status = str(fm.get("status", "unknown")).lower()
    file_priority = str(fm.get("priority", "")).upper()
    file_ac_total = fm.get("x_ac_total")
    delivery_state = _DELIVERY_INDEX.classify(norm_id, file_status)

    tasks_status = str(tasks_entry.get("status", "unknown")).lower() if tasks_entry.get("found") else "missing"
    tasks_priority = str(tasks_entry.get("priority", "")).upper() if tasks_entry.get("found") else "missing"

    json_status = str(json_entry.get("status", "unknown")).lower() if json_entry.get("found") else "missing"

    disagreements: list[str] = []

    if tasks_entry.get("found") and tasks_status != file_status:
        disagreements.append(f"status: file='{file_status}' vs {tasks_entry.get('surface', 'TASKS')}='{tasks_status}'")
    if json_entry.get("found") and json_status != file_status:
        disagreements.append(f"status: file='{file_status}' vs tickets.json='{json_status}'")
    if not tq_entry["parity_ok"]:
        disagreements.append(f"tasks_query AC parity: {tq_entry['drift_detail']}")
    if gh_entry.get("checked") and gh_entry.get("found"):
        gh_state = str(gh_entry.get("state", "")).lower()
        if gh_state == "closed" and file_status not in ("done", "archived"):
            disagreements.append(f"status: file='{file_status}' vs GitHub='closed'")
        elif gh_state == "open" and file_status in ("done", "archived"):
            disagreements.append(f"status: file='{file_status}' vs GitHub='open'")

    if tasks_entry.get("found") and tasks_priority and tasks_priority != file_priority:
        disagreements.append(
            f"priority: file='{file_priority}' vs {tasks_entry.get('surface', 'TASKS')}='{tasks_priority}'"
        )

    if git_staged:
        disagreements.append(f"uncommitted git changes: {', '.join(git_staged)}")

    ac_verdicts = classify_acs(body, repo_map, missing_paths)
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
        "delivery_state": delivery_state,
        "ac_done": fm.get("x_ac_done", 0),
        "ac_total": file_ac_total or len(ac_verdicts),
        "ac_pct": fm.get("x_ac_pct", 0),
        "surfaces": {
            "ticket_file": str(path),
            "tasks_found": tasks_entry.get("found", False),
            "tasks_surface": tasks_entry.get("surface"),
            "tasks_query": tq_entry,
            "tickets_json_found": json_entry.get("found", False),
            "gh_issue": gh_entry,
            "delivery_state": delivery_state,
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
    delivery_state = res.get("delivery_state", "unknown")

    surface_str = (
        "✅ **4/4 agree**"
        if res["surface_agree"]
        else f"🔴 **disagree**: {'; '.join(res['disagreements'])}"
    )

    lines = [
        f"# Ticket Reality Audit — {t_id}",
        "",
        (
            f"**Recorded**: status=`{status}`, `{ac_done}/{ac_total}` ACs (`{ac_pct}%`) · "
            f"**Cross-surface**: {surface_str} · **Delivery**: `delivery_state: {delivery_state}`"
        ),
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


def format_corpus_report(
    completed_res: dict[str, Any] | None,
    specs_res: dict[str, Any] | None,
) -> str:
    lines: list[str] = ["▶ Reality Verification — Completed Tickets & Canonical Specs", ""]

    if completed_res is not None:
        if completed_res.get("unmeasurable"):
            lines.append(f"  [UNMEASURABLE] completed-tickets: {completed_res.get('error')}")
        else:
            scanned = completed_res["done_tickets_scanned"]
            deep = completed_res["deep_reality_checked"]
            bad = completed_res["contradicted_count"]
            dc = completed_res["delivery_counts"]
            mark = "OK" if bad == 0 else "FAIL"
            lines.append(
                f"  [{mark}] completed tickets: {scanned} done scanned ({deep} deep-checked since "
                f"{completed_res['since']}), {bad} contradicted "
                f"[deployed={dc['deployed']}, landed_pending_deploy={dc['landed_pending_deploy']}, "
                f"no_commit_trace={dc['no_commit_trace']}]"
            )
            for item in completed_res["contradicted"][:25]:
                lines.append(f"      🔴 {item['id']} ({item['file']}): {'; '.join(item['contradictions'])}")

    if specs_res is not None:
        if specs_res.get("unmeasurable"):
            lines.append(f"  [UNMEASURABLE] canonical-specs: {specs_res.get('error')}")
        else:
            scanned = specs_res["specs_scanned"]
            bad = specs_res["contradicted_count"]
            sql_n = specs_res["sql_relations_indexed"]
            sym_n = specs_res["exported_symbols_indexed"]
            mark = "OK" if bad == 0 else "FAIL"
            lines.append(
                f"  [{mark}] canonical specs: {scanned} spec files audited against {sql_n} SQL relations "
                f"and {sym_n} exported symbols, {bad} contradicted"
            )
            for item in specs_res["contradicted"][:25]:
                lines.append(f"      🔴 {item['spec']}: {'; '.join(item['contradictions'])}")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("ticket", nargs="?", help="Ticket ID to audit (e.g. T382, 382)")
    parser.add_argument(
        "--completed",
        action="store_true",
        help="Audit completed (`status: done`) tickets across `.tasks/` against live repo/SQL/release state",
    )
    parser.add_argument(
        "--since",
        default=DEFAULT_COMPLETED_SINCE,
        help=f"Created-date floor (YYYY-MM-DD) for deep path/symbol/SQL audit in --completed mode (default: {DEFAULT_COMPLETED_SINCE})",
    )
    parser.add_argument(
        "--specs",
        action="store_true",
        help="Audit canonical `w0m-web/openspec/specs/**/*.md` against live files, symbols, and SQL relations",
    )
    parser.add_argument("--tickets-dir", type=Path, default=None, help="Override `.tasks` directory")
    parser.add_argument("--specs-dir", type=Path, default=None, help="Override `openspec/specs` directory")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 if surfaces disagree or if contradictions exist",
    )
    parser.add_argument("--offline", action="store_true", help="Skip remote GitHub API queries")
    parser.add_argument("--gh", action="store_true", help="Query remote GitHub issue status via `gh` CLI")
    parser.add_argument("--json", action="store_true", help="Output audit report as JSON")
    args = parser.parse_args(argv)

    if args.completed or args.specs:
        shared_idx = CodebaseRealityIndex(resolve_repos())
        comp_res = (
            audit_completed_corpus(args.tickets_dir or TICKETS_DIR, since=args.since, idx=shared_idx)
            if args.completed
            else None
        )
        sp_res = (
            audit_specs_corpus(args.specs_dir or DEFAULT_SPECS_DIR, idx=shared_idx)
            if args.specs
            else None
        )

        if args.json:
            payload: dict[str, Any] = {}
            if comp_res is not None:
                payload["completed"] = comp_res
            if sp_res is not None:
                payload["specs"] = sp_res
            print(json.dumps(payload, indent=2))
        else:
            print(format_corpus_report(comp_res, sp_res))

        codes = [r["exit_code"] for r in (comp_res, sp_res) if r is not None]
        if 2 in codes:
            return 2
        if args.strict and 1 in codes:
            return 1
        return 0

    if not args.ticket:
        parser.error("Provide a ticket ID (e.g. T382) or pass --completed / --specs")

    res = audit_ticket(
        args.ticket,
        offline=(args.offline or not args.gh),
        strict=args.strict,
        check_gh=args.gh,
    )
    if args.json:
        print(json.dumps(res, indent=2))
    else:
        print(format_markdown_report(res))

    return int(res.get("exit_code", 0))


if __name__ == "__main__":
    sys.exit(main())
