#!/usr/bin/env python3
"""session_complete.py (T640) -- Single-command in-session SDLC wrap-up, archive, land, and live sync.

Designed to be invoked BY THE AGENT FROM INSIDE ITS OWN ACTIVE SESSION (`just session-complete`),
whether `cwd` is an isolated `~/.w0m/work/<set>/w0m` agent tree or the canonical `@wom` root:

  1. Detects caller session context (`conversation_id` from process ancestry, `ORCA_TERMINAL_HANDLE`
     so the active session NEVER kills its own PTY mid-turn, `worktree_root`, and `canonical_root`
     via `git rev-parse --git-common-dir`).
  2. Auto-discovers target `T##` tickets (or accepts explicit `T##` IDs) and optionally auto-renumbers
     branch-added tickets if a concurrent session landed a colliding `T##` on `origin/beta`.
  3. Normalizes `.tasks/T##.md` (`status: done`, `queue: done`, `closed_as: completed`, verified ACs,
     `## Definition of Done`, and explicit lesson disposition in `## Status notes`).
  4. Mirrors session reports from `.agents/reports/` into `session_wrapup.reports_mirror_dir`
     (`w0m-web/docs/reports/`).
  5. Harvests session friction (`lessons_query.py --harvest-friction`) and refreshes derived surfaces
     (`tickets_frontmatter_sync.py`, `tasks_render.py`, `decisions_index.py`, `state_doctor.py --write`).
  6. Executes every gate in `.w0m/sdlc.json -> session_wrapup.verification_gates` plus strict offline
     `ticket_audit.py` and `ticket_schema_check.py --enforce`, failing closed before committing/landing.
  7. Commits dirty member repos (`w0m-web`) first and umbrella (`.`) last, lands via
     `agent_tree.py land --set <set>`, switches `cwd` to `canonical_root` BEFORE removing `<set>`,
     fast-forwards clean/non-overlapping `beta` checkouts in `canonical_root`, archives the caller's
     conversation transcript via `orca_sessions.py archive`, and verifies `just state-check` on
     `canonical_root` last.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from collections.abc import Iterator, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)
from progress_bar import format_progress_bar

DEFAULT_WORK_ROOT = Path.home() / ".w0m" / "work"
AGENT_ROOT_SUBDIR = "w0m"
BASE_REF = "origin/beta"
TARGET_BRANCH = "beta"

TICKET_ARG_RE = re.compile(r"^[Tt](\d{1,5})$")
DRAFT_ARG_RE = re.compile(r"^[Dd][Rr][Aa][Ff][Tt]-([A-Za-z0-9_-]+)$")
TICKET_FILE_RE = re.compile(r"^T(\d{1,5})\.md$")
DRAFT_FILE_RE = re.compile(r"^DRAFT-([A-Za-z0-9_-]+)\.md$")
REPORT_CITE_RE = re.compile(r"\b(?:[Tt](\d{1,5})|[Dd][Rr][Aa][Ff][Tt]-([A-Za-z0-9_-]+))\b")
CONV_ANCESTRY_RE = re.compile(
    r"--(?:conversation|resume)(?:=|\s+)([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
    re.IGNORECASE,
)
UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
AC_LINE_RE = re.compile(r"^(\s*-\s*\[)([ xX~]|N/A)(\]\s+(?:\*\*)?AC\d+[a-z]?\b.*)$")
LESSON_DISPOSITION_RE = re.compile(
    r"(?:\bLESSONS\.md\b|\bLessons\s*:\s*none\b|\bLesson\s+disposition\b)",
    re.IGNORECASE,
)
REPORT_HEADER_LINES = 12


class SessionCompleteError(RuntimeError):
    """Fail-closed error during session wrap-up."""

    def __init__(self, step: str, message: str) -> None:
        super().__init__(f"[{step}] {message}")
        self.step = step
        self.detail = message


@dataclass
class SessionContext:
    cwd: str
    worktree_root: str
    canonical_root: str
    work_root: str
    in_agent_tree: bool
    set_name: str | None
    agent_id: str | None
    conversation_id: str | None
    agent_pid: int | None
    terminal_handle: str | None
    tab_id: str | None
    pane_key: str | None


@dataclass
class TicketNormalizationResult:
    ticket_id: str
    path: str
    changed: bool
    previous_status: str
    previous_queue: str
    lesson_disposition_added: bool = False
    completed_acs: list[str] = field(default_factory=list)


def _run(
    cmd: Sequence[str],
    *,
    cwd: Path,
    check: bool = False,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "LC_ALL": "C", "GIT_TERMINAL_PROMPT": "0", "GIT_EDITOR": "true"}
    proc = subprocess.run(
        list(cmd),
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout,
        check=False,
    )
    if check and proc.returncode != 0:
        tail = ((proc.stderr or "") + "\n" + (proc.stdout or "")).strip()[-2000:]
        raise SessionCompleteError("command_failed", f"{' '.join(cmd)} (exit {proc.returncode}):\n{tail}")
    return proc


def _git(repo: Path, *args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
    return _run(["git", "-C", str(repo), *args], cwd=repo, check=check)


def _find_estate_root(start: Path) -> Path:
    cur = start.resolve()
    if cur.is_file():
        cur = cur.parent
    for cand in (cur, *cur.parents):
        if (cand / ".w0m" / "sdlc.json").is_file() and (cand / ".tasks").is_dir():
            return cand
    raise SessionCompleteError(
        "estate_root",
        f"Could not locate .w0m/sdlc.json + .tasks/ walking up from {start}",
    )


def _resolve_canonical_root(worktree_root: Path) -> Path:
    proc = _git(worktree_root, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if proc.returncode == 0 and proc.stdout.strip():
        common_git = Path(proc.stdout.strip()).resolve()
        candidate = common_git.parent
        if (candidate / ".w0m" / "sdlc.json").is_file():
            return candidate
    return worktree_root.resolve()


def _detect_caller_process_conversation(start_pid: int | None = None) -> tuple[str | None, int | None]:
    for env_key in ("W0M_SESSION_CONVERSATION_ID", "AGY_CONVERSATION_ID", "CONVERSATION_ID"):
        val = os.environ.get(env_key, "").strip()
        if UUID_RE.fullmatch(val):
            return val.lower(), None

    pid = start_pid if start_pid is not None else os.getpid()
    visited: set[int] = set()
    while pid > 1 and pid not in visited:
        visited.add(pid)
        try:
            proc = subprocess.run(
                ["ps", "-o", "pid=,ppid=,args=", "-p", str(pid)],
                capture_output=True,
                text=True,
                timeout=3.0,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            break
        line = proc.stdout.strip()
        if not line:
            break
        parts = line.split(None, 2)
        if len(parts) < 2:
            break
        try:
            cur_pid = int(parts[0])
            ppid = int(parts[1])
        except ValueError:
            break
        args_str = parts[2] if len(parts) > 2 else ""
        m = CONV_ANCESTRY_RE.search(args_str)
        if m:
            return m.group(1).lower(), cur_pid
        pid = ppid
    return None, None


def detect_session_context(
    *,
    cwd: Path | None = None,
    set_override: str | None = None,
    conversation_override: str | None = None,
    work_root: Path | None = None,
) -> SessionContext:
    eff_cwd = (cwd or Path.cwd()).resolve()
    eff_work_root = (
        Path(os.environ["W0M_WORK_ROOT"]).resolve()
        if os.environ.get("W0M_WORK_ROOT")
        else (work_root or DEFAULT_WORK_ROOT).resolve()
    )

    if set_override:
        candidate_tree = eff_work_root / set_override / AGENT_ROOT_SUBDIR
        if not (candidate_tree / ".w0m" / "sdlc.json").is_file():
            raise SessionCompleteError(
                "no_such_set",
                f"Agent tree set '{set_override}' not found at {candidate_tree}",
            )
        wt_root = candidate_tree.resolve()
    else:
        wt_root = _find_estate_root(eff_cwd)

    in_agent_tree = False
    set_name: str | None = None
    try:
        rel_parts = wt_root.relative_to(eff_work_root).parts
        if len(rel_parts) >= 2 and rel_parts[1] == AGENT_ROOT_SUBDIR:
            in_agent_tree = True
            set_name = rel_parts[0]
    except ValueError:
        in_agent_tree = False

    canon_root = _resolve_canonical_root(wt_root)
    agent_id: str | None = f"agy:{set_name}" if set_name else None
    ai_script = wt_root / "w0m-web" / "project" / "scripts" / "agent_identity.py"
    if ai_script.is_file():
        proc = _run([sys.executable, str(ai_script), "whoami", "--json"], cwd=wt_root)
        if proc.returncode == 0 and proc.stdout.strip():
            try:
                ai_data: Any = json.loads(proc.stdout)
                if isinstance(ai_data, dict) and str(ai_data.get("agent_id") or "").strip():
                    agent_id = str(ai_data["agent_id"]).strip()
            except json.JSONDecodeError:
                pass

    ancestry_cid, agent_pid = _detect_caller_process_conversation()
    conv_id = (conversation_override or "").strip().lower() or ancestry_cid
    if conv_id and not UUID_RE.fullmatch(conv_id):
        raise SessionCompleteError("invalid_conversation", f"Invalid conversation UUID: {conv_id}")

    terminal_handle = os.environ.get("ORCA_TERMINAL_HANDLE", "").strip() or None
    tab_id = os.environ.get("ORCA_TAB_ID", "").strip() or None
    pane_key = (os.environ.get("ORCA_AGENT_PANE") or os.environ.get("ORCA_PANE_KEY") or "").strip() or None

    return SessionContext(
        cwd=str(eff_cwd),
        worktree_root=str(wt_root),
        canonical_root=str(canon_root),
        work_root=str(eff_work_root),
        in_agent_tree=in_agent_tree,
        set_name=set_name,
        agent_id=agent_id,
        conversation_id=conv_id,
        agent_pid=agent_pid,
        terminal_handle=terminal_handle,
        tab_id=tab_id,
        pane_key=pane_key,
    )


def _parse_frontmatter(text: str) -> tuple[list[str], list[str]] | None:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            return lines[1:idx], lines[idx + 1 :]
    return None


def _frontmatter_get(fm_lines: Sequence[str], key: str) -> str:
    pat = re.compile(rf"^{re.escape(key)}\s*:\s*(.*)$")
    for raw in fm_lines:
        m = pat.match(raw.rstrip("\r\n"))
        if m:
            val = m.group(1).split("#", 1)[0].strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
                val = val[1:-1]
            return val
    return ""


def _frontmatter_set(fm_lines: list[str], key: str, value: str, *, after_key: str | None = None) -> bool:
    pat = re.compile(rf"^({re.escape(key)}\s*:\s*)([^\r\n#]*)(.*)$")
    for idx, raw in enumerate(fm_lines):
        ending = "\r\n" if raw.endswith("\r\n") else ("\n" if raw.endswith("\n") else "")
        body = raw.rstrip("\r\n")
        m = pat.match(body)
        if m:
            comment = m.group(3)
            new_line = (
                f"{key}: {value} {comment.lstrip()}{ending}"
                if comment.strip()
                else f"{key}: {value}{ending}"
            )
            if new_line != raw:
                fm_lines[idx] = new_line
                return True
            return False

    new_entry = f"{key}: {value}\n"
    if after_key:
        after_pat = re.compile(rf"^{re.escape(after_key)}\s*:")
        for idx, raw in enumerate(fm_lines):
            if after_pat.match(raw):
                fm_lines.insert(idx + 1, new_entry)
                return True
    fm_lines.append(new_entry)
    return True


def normalize_ticket_id(raw: str) -> str:
    s = raw.strip()
    m = TICKET_ARG_RE.fullmatch(s)
    if m:
        return f"T{int(m.group(1))}"
    md = DRAFT_ARG_RE.fullmatch(s)
    if md:
        return f"DRAFT-{md.group(1)}"
    raise SessionCompleteError(
        "invalid_ticket",
        f"Invalid ticket ID '{raw}' (expected T<number> or DRAFT-<slug>)",
    )


def discover_target_tickets(
    worktree_root: Path,
    *,
    explicit_tickets: Sequence[str] = (),
    agent_id: str | None = None,
    allow_empty: bool = False,
) -> list[str]:
    if explicit_tickets:
        seen: set[str] = set()
        ordered: list[str] = []
        for raw in explicit_tickets:
            tid = normalize_ticket_id(raw)
            if tid not in seen:
                seen.add(tid)
                ordered.append(tid)
        return ordered

    found_nums: set[int] = set()
    found_drafts: set[str] = set()

    st = _git(worktree_root, "status", "--porcelain", "--", ".tasks/")
    if st.returncode == 0:
        for line in st.stdout.splitlines():
            if len(line) < 4:
                continue
            cand_path = line[3:].strip().split(" -> ")[-1].strip()
            name = Path(cand_path).name
            m = TICKET_FILE_RE.match(name)
            if m and (worktree_root / cand_path).is_file():
                found_nums.add(int(m.group(1)))
            elif (md := DRAFT_FILE_RE.match(name)) and (worktree_root / cand_path).is_file():
                found_drafts.add(f"DRAFT-{md.group(1)}")

    diff = _git(worktree_root, "diff", "--name-only", f"{BASE_REF}...HEAD", "--", ".tasks/")
    if diff.returncode == 0:
        for line in diff.stdout.splitlines():
            cand_path = line.strip()
            name = Path(cand_path).name
            m = TICKET_FILE_RE.match(name)
            if m and (worktree_root / cand_path).is_file():
                found_nums.add(int(m.group(1)))
            elif (md := DRAFT_FILE_RE.match(name)) and (worktree_root / cand_path).is_file():
                found_drafts.add(f"DRAFT-{md.group(1)}")

    if agent_id:
        tickets_dir = worktree_root / ".tasks"
        if tickets_dir.is_dir():
            for tpath in [*tickets_dir.glob("T*.md"), *tickets_dir.glob("DRAFT-*.md")]:
                m = TICKET_FILE_RE.match(tpath.name)
                md = DRAFT_FILE_RE.match(tpath.name)
                if not m and not md:
                    continue
                parsed = _parse_frontmatter(tpath.read_text(encoding="utf-8", errors="replace"))
                if not parsed:
                    continue
                fm_lines, _ = parsed
                owner = _frontmatter_get(fm_lines, "agent_id")
                t_status = _frontmatter_get(fm_lines, "status")
                if owner == agent_id and t_status != "done":
                    if m:
                        found_nums.add(int(m.group(1)))
                    elif md:
                        found_drafts.add(f"DRAFT-{md.group(1)}")

    if not found_nums and not found_drafts and not allow_empty:
        raise SessionCompleteError(
            "no_target_tickets",
            "No modified or agent-claimed tickets detected in .tasks/; pass ticket ID(s) explicitly "
            "(e.g. `just session-complete T640` or `just session-complete DRAFT-<slug>`).",
        )
    return [f"T{n}" for n in sorted(found_nums)] + sorted(found_drafts)


def _ids_at_git_ref(repo: Path, ref: str) -> set[int]:
    proc = _git(repo, "ls-tree", "-r", "--name-only", ref, ".tasks/")
    if proc.returncode != 0:
        return set()
    ids: set[int] = set()
    for line in proc.stdout.splitlines():
        m = TICKET_FILE_RE.match(Path(line.strip()).name)
        if m:
            ids.add(int(m.group(1)))
    return ids


def _rewrite_ticket_id_map(text: str, renames: dict[str, str]) -> str:
    if not renames:
        return text
    lower_lookup: dict[str, tuple[str, str]] = {
        old_tid.lower(): (new_tid, new_tid.lower())
        for old_tid, new_tid in renames.items()
    }
    pattern = re.compile(
        r"\b(" + "|".join(re.escape(k) for k in sorted(lower_lookup, key=len, reverse=True)) + r")\b",
        re.IGNORECASE,
    )

    def _repl(m: re.Match[str]) -> str:
        matched = m.group(1)
        upper_new, lower_new = lower_lookup[matched.lower()]
        return lower_new if matched.islower() else upper_new

    return pattern.sub(_repl, text)


def _rewrite_ticket_id_tokens(text: str, old_tid: str, new_tid: str) -> str:
    return _rewrite_ticket_id_map(text, {old_tid: new_tid})


def _scrub_gh_issue_frontmatter(text: str) -> str:
    parsed = _parse_frontmatter(text)
    if not parsed:
        return text
    fm_lines, body_lines = parsed
    gh_pat = re.compile(r"^gh_issue\s*:.*$")
    new_fm: list[str] = []
    for raw_line in fm_lines:
        ending = "\r\n" if raw_line.endswith("\r\n") else ("\n" if raw_line.endswith("\n") else "")
        if gh_pat.match(raw_line.rstrip("\r\n")):
            new_fm.append(f"gh_issue:{ending}")
        else:
            new_fm.append(raw_line)
    return "---\n" + "".join(new_fm) + "---\n" + "".join(body_lines)


def maybe_renumber_colliding_tickets(
    worktree_root: Path,
    target_tickets: Sequence[str],
    *,
    dry_run: bool = False,
    fetch_remote: bool = True,
) -> tuple[list[str], dict[str, str]]:
    """Promote `DRAFT-<slug>` tickets and compact branch-added `T##` onto `[max(origin/beta)+1, ...]`."""
    if fetch_remote:
        _git(worktree_root, "fetch", "-q", "origin")

    origin_ids = _ids_at_git_ref(worktree_root, BASE_REF)
    if not origin_ids:
        return list(target_tickets), {}

    mb_proc = _git(worktree_root, "merge-base", "HEAD", BASE_REF)
    if mb_proc.returncode != 0 or not mb_proc.stdout.strip():
        return list(target_tickets), {}
    merge_base = mb_proc.stdout.strip()
    base_ids = _ids_at_git_ref(worktree_root, merge_base)

    tickets_dir = worktree_root / ".tasks"
    local_ids = {
        int(m.group(1))
        for p in tickets_dir.glob("T*.md")
        if (m := TICKET_FILE_RE.match(p.name))
    }
    max_origin = max(origin_ids)
    added_ids = sorted(
        n for n in (local_ids - base_ids) if (n in origin_ids or n > max_origin)
    )
    draft_ids = sorted(
        f"DRAFT-{m.group(1)}"
        for p in tickets_dir.glob("DRAFT-*.md")
        if (m := DRAFT_FILE_RE.match(p.name))
    )
    if not added_ids and not draft_ids:
        return list(target_tickets), {}

    start_num = max_origin + 1
    total_new = len(added_ids) + len(draft_ids)
    expected_ids = list(range(start_num, start_num + total_new))
    renames: dict[str, str] = {}
    for old_num, new_num in zip(added_ids, expected_ids[: len(added_ids)], strict=True):
        if old_num != new_num:
            renames[f"T{old_num}"] = f"T{new_num}"
    for draft_tid, new_num in zip(draft_ids, expected_ids[len(added_ids) :], strict=True):
        renames[draft_tid] = f"T{new_num}"
    if not renames:
        return list(target_tickets), {}

    ci_renames = {k.lower(): v for k, v in renames.items()}
    mapped_targets = [ci_renames.get(t.lower(), t) for t in target_tickets]
    if dry_run:
        return mapped_targets, renames

    head_sha = _git(worktree_root, "rev-parse", "HEAD").stdout.strip()
    if head_sha and head_sha != merge_base:
        _git(worktree_root, "reset", "--soft", merge_base, check=True)

    for rel_path, repo_dir in _discover_estate_repos(worktree_root):
        if rel_path == "." or not (repo_dir / ".git").exists():
            continue
        _git(repo_dir, "fetch", "-q", "origin")
        repo_mb = _git(repo_dir, "merge-base", "HEAD", BASE_REF).stdout.strip()
        repo_head = _git(repo_dir, "rev-parse", "HEAD").stdout.strip()
        if repo_mb and repo_head and repo_head != repo_mb:
            _git(repo_dir, "reset", "--soft", repo_mb, check=True)

    # Two-phase `.tasks/` rename so chained renames (`T11->T12, T12->T13`) never collide mid-flight,
    # and strip any pre-renumber `gh_issue:` frontmatter so GitHub Issue `#old` is never overwritten.
    staged_tmps: list[tuple[Path, Path]] = []
    for old_tid, new_tid in renames.items():
        old_tpath = tickets_dir / f"{old_tid}.md"
        new_tpath = tickets_dir / f"{new_tid}.md"
        if old_tpath.is_file():
            raw = old_tpath.read_text(encoding="utf-8")
            rewritten = _scrub_gh_issue_frontmatter(_rewrite_ticket_id_map(raw, renames))
            tmp_tpath = tickets_dir / f".renumber-tmp-{old_tid}.md"
            tmp_tpath.write_text(rewritten, encoding="utf-8")
            old_tpath.unlink()
            _git(worktree_root, "rm", "--cached", "-q", "--ignore-unmatch", f".tasks/{old_tid}.md")
            staged_tmps.append((tmp_tpath, new_tpath))

    for tmp_tpath, new_tpath in staged_tmps:
        if new_tpath.exists():
            raise SessionCompleteError("renumber_conflict", f"Target path already exists: {new_tpath}")
        tmp_tpath.replace(new_tpath)

    for rel_dir in (".agents/reports", "w0m-web/docs/reports"):
        rdir = worktree_root / rel_dir
        if not rdir.is_dir():
            continue
        report_tmps: list[tuple[Path, Path]] = []
        for rfile in sorted(rdir.iterdir()):
            if not rfile.is_file():
                continue
            cited_lower = {c.lower() for c in cited_tickets_in_report(rfile)}
            matched = any(
                re.search(rf"\b{re.escape(old_tid.lower())}\b", rfile.name, re.IGNORECASE)
                or old_tid.lower() in cited_lower
                for old_tid in renames
            )
            if not matched:
                continue
            new_name = _rewrite_ticket_id_map(rfile.name, renames)
            dest = rdir / new_name
            content = rfile.read_text(encoding="utf-8", errors="replace")
            rewritten_report = _rewrite_ticket_id_map(content, renames)
            if dest == rfile:
                rfile.write_text(rewritten_report, encoding="utf-8")
            else:
                tmp_r = rdir / f".renumber-tmp-{rfile.name}"
                tmp_r.write_text(rewritten_report, encoding="utf-8")
                rfile.unlink()
                if rel_dir == ".agents/reports":
                    _git(worktree_root, "rm", "--cached", "-q", "--ignore-unmatch", f"{rel_dir}/{rfile.name}")
                elif rel_dir == "w0m-web/docs/reports" and (worktree_root / "w0m-web" / ".git").exists():
                    _git(
                        worktree_root / "w0m-web",
                        "rm",
                        "--cached",
                        "-q",
                        "--ignore-unmatch",
                        f"docs/reports/{rfile.name}",
                    )
                report_tmps.append((tmp_r, dest))
        for tmp_r, dest in report_tmps:
            tmp_r.replace(dest)

    lessons_path = worktree_root / "LESSONS.md"
    if lessons_path.is_file():
        diff_l = _git(worktree_root, "diff", merge_base, "--", "LESSONS.md")
        diff_lower = diff_l.stdout.lower()
        if any(old_tid.lower() in diff_lower for old_tid in renames):
            base_lessons_proc = _git(worktree_root, "show", f"{merge_base}:LESSONS.md")
            curr_lessons = lessons_path.read_text(encoding="utf-8")
            base_prefix = base_lessons_proc.stdout.rstrip("\n")
            if base_lessons_proc.returncode == 0 and curr_lessons.startswith(base_prefix):
                suffix = curr_lessons[len(base_prefix) :]
                lessons_path.write_text(
                    base_prefix + _rewrite_ticket_id_map(suffix, renames),
                    encoding="utf-8",
                )
            else:
                lessons_path.write_text(
                    _rewrite_ticket_id_map(curr_lessons, renames),
                    encoding="utf-8",
                )

    return mapped_targets, renames


def _rollback_renumbered_tickets(worktree_root: Path, renames: dict[str, str]) -> None:
    """Revert in-flight `DRAFT-<slug> -> T<N>` (or `T<old> -> T<new>`) renames if a pre-land gate fails."""
    if not renames:
        return
    inv_renames = {new_tid: old_tid for old_tid, new_tid in renames.items()}
    tickets_dir = worktree_root / ".tasks"
    for new_tid, old_tid in inv_renames.items():
        new_tpath = tickets_dir / f"{new_tid}.md"
        old_tpath = tickets_dir / f"{old_tid}.md"
        if new_tpath.is_file() and not old_tpath.exists():
            raw = new_tpath.read_text(encoding="utf-8")
            rewritten = _scrub_gh_issue_frontmatter(_rewrite_ticket_id_map(raw, inv_renames))
            old_tpath.write_text(rewritten, encoding="utf-8")
            new_tpath.unlink()
            _git(worktree_root, "rm", "--cached", "-q", "--ignore-unmatch", f".tasks/{new_tid}.md")

    for rel_dir in (".agents/reports", "w0m-web/docs/reports"):
        rdir = worktree_root / rel_dir
        if not rdir.is_dir():
            continue
        for rfile in sorted(rdir.iterdir()):
            if not rfile.is_file():
                continue
            cited_lower = {c.lower() for c in cited_tickets_in_report(rfile)}
            matched = any(
                re.search(rf"\b{re.escape(new_tid.lower())}\b", rfile.name, re.IGNORECASE)
                or new_tid.lower() in cited_lower
                for new_tid in inv_renames
            )
            if not matched:
                continue
            old_name = _rewrite_ticket_id_map(rfile.name, inv_renames)
            dest = rdir / old_name
            content = rfile.read_text(encoding="utf-8", errors="replace")
            rewritten_report = _rewrite_ticket_id_map(content, inv_renames)
            if dest == rfile:
                rfile.write_text(rewritten_report, encoding="utf-8")
            else:
                dest.write_text(rewritten_report, encoding="utf-8")
                rfile.unlink()

    lessons_path = worktree_root / "LESSONS.md"
    if lessons_path.is_file():
        curr_lessons = lessons_path.read_text(encoding="utf-8")
        rewritten_lessons = _rewrite_ticket_id_map(curr_lessons, inv_renames)
        if rewritten_lessons != curr_lessons:
            lessons_path.write_text(rewritten_lessons, encoding="utf-8")


def _soft_reset_worktree_to_merge_base(worktree_root: Path) -> None:
    """Soft-reset `HEAD` back to `merge-base(HEAD, origin/beta)` across umbrella and member repos
    so a post-commit gate failure (`deploy_cert_failed`) can cleanly roll back `DRAFT-<slug> -> T<N>`.
    """
    for _, repo_dir in _discover_estate_repos(worktree_root):
        if not (repo_dir / ".git").exists():
            continue
        mb_proc = _git(repo_dir, "merge-base", "HEAD", BASE_REF)
        head_proc = _git(repo_dir, "rev-parse", "HEAD")
        if mb_proc.returncode == 0 and head_proc.returncode == 0:
            mb = mb_proc.stdout.strip()
            head = head_proc.stdout.strip()
            if mb and head and mb != head:
                _git(repo_dir, "reset", "--soft", mb)


MIGRATION_FILE_RE = re.compile(r"^(\d{8,14})_(.+)\.sql$")


def _step_migration_version(ver: str) -> str:
    try:
        from datetime import datetime, timedelta, timezone

        dt = datetime.strptime(ver, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        return (dt + timedelta(seconds=1)).strftime("%Y%m%d%H%M%S")
    except ValueError:
        return f"{int(ver) + 1:014d}"


def _next_migration_version(existing_versions: set[str], candidate: str) -> str:
    existing_14 = [v for v in existing_versions if len(v) == 14 and v.isdigit()]
    if existing_14:
        highest = max(existing_14)
        if len(candidate) != 14 or not candidate.isdigit() or candidate <= highest:
            candidate = _step_migration_version(highest)
    while candidate in existing_versions:
        candidate = _step_migration_version(candidate)
    return candidate


def _migrations_at_git_ref(api_repo: Path, ref: str) -> dict[str, set[str]]:
    proc = _git(api_repo, "ls-tree", "-r", "--name-only", ref, "supabase/migrations/")
    if proc.returncode != 0:
        return {}
    by_ver: dict[str, set[str]] = {}
    for raw in proc.stdout.splitlines():
        name = Path(raw.strip()).name
        m = MIGRATION_FILE_RE.match(name)
        if m:
            by_ver.setdefault(m.group(1), set()).add(name)
    return by_ver


def maybe_resequence_colliding_migrations(
    worktree_root: Path,
    *,
    dry_run: bool = False,
    fetch_remote: bool = True,
) -> dict[str, str]:
    """Re-sequence branch-added SQL migrations in `w0m-api/supabase/migrations/` if their 14-digit
    version collides with or precedes a migration landed on `origin/beta` by a concurrent worktree.
    """
    api_repo = worktree_root / "w0m-api"
    mig_dir = api_repo / "supabase" / "migrations"
    if not (api_repo / ".git").exists() or not mig_dir.is_dir():
        return {}
    if fetch_remote:
        _git(api_repo, "fetch", "-q", "origin")

    origin_migs = _migrations_at_git_ref(api_repo, BASE_REF)
    if not origin_migs:
        return {}
    mb_proc = _git(api_repo, "merge-base", "HEAD", BASE_REF)
    if mb_proc.returncode != 0 or not mb_proc.stdout.strip():
        return {}
    merge_base = mb_proc.stdout.strip()
    base_migs = _migrations_at_git_ref(api_repo, merge_base)
    base_filenames = {fn for fns in base_migs.values() for fn in fns}

    added_files: list[tuple[str, str, str]] = []
    for path in sorted(mig_dir.glob("*.sql")):
        if path.name in base_filenames:
            continue
        m = MIGRATION_FILE_RE.match(path.name)
        if m:
            added_files.append((m.group(1), m.group(2), path.name))

    if not added_files:
        return {}

    origin_14 = [v for v in origin_migs if len(v) == 14 and v.isdigit()]
    max_origin_14 = max(origin_14) if origin_14 else ""
    used_versions: set[str] = set(origin_migs.keys()) | set(base_migs.keys())

    mig_renames: dict[str, str] = {}
    for old_ver, slug, old_name in added_files:
        collides = old_ver in used_versions
        out_of_order = bool(len(old_ver) == 14 and old_ver.isdigit() and max_origin_14 and old_ver <= max_origin_14)
        if not collides and not out_of_order:
            used_versions.add(old_ver)
            continue
        new_ver = _next_migration_version(used_versions, old_ver)
        used_versions.add(new_ver)
        new_name = f"{new_ver}_{slug}.sql"
        if new_name != old_name:
            mig_renames[old_name] = new_name

    if not mig_renames or dry_run:
        return mig_renames

    repo_head = _git(api_repo, "rev-parse", "HEAD").stdout.strip()
    if repo_head and repo_head != merge_base:
        _git(api_repo, "reset", "--soft", merge_base, check=True)

    staged_tmps: list[tuple[Path, Path]] = []
    for old_name, new_name in mig_renames.items():
        old_p = mig_dir / old_name
        new_p = mig_dir / new_name
        if old_p.is_file():
            tmp_p = mig_dir / f".reseq-tmp-{old_name}"
            tmp_p.write_text(old_p.read_text(encoding="utf-8"), encoding="utf-8")
            old_p.unlink()
            _git(api_repo, "rm", "--cached", "-q", "--ignore-unmatch", f"supabase/migrations/{old_name}")
            staged_tmps.append((tmp_p, new_p))

    for tmp_p, new_p in staged_tmps:
        tmp_p.replace(new_p)

    for search_dir in (worktree_root / ".tasks", worktree_root / ".agents" / "reports", worktree_root / "w0m-web" / "docs" / "reports"):
        if not search_dir.is_dir():
            continue
        for doc_file in sorted(search_dir.glob("*.md")):
            raw = doc_file.read_text(encoding="utf-8", errors="replace")
            updated = raw
            for old_name, new_name in mig_renames.items():
                updated = updated.replace(old_name, new_name)
            if updated != raw:
                doc_file.write_text(updated, encoding="utf-8")

    return mig_renames


def _rollback_resequenced_migrations(worktree_root: Path, mig_renames: dict[str, str]) -> None:
    if not mig_renames:
        return
    api_repo = worktree_root / "w0m-api"
    mig_dir = api_repo / "supabase" / "migrations"
    for old_name, new_name in mig_renames.items():
        new_p = mig_dir / new_name
        old_p = mig_dir / old_name
        if new_p.is_file() and not old_p.exists():
            old_p.write_text(new_p.read_text(encoding="utf-8"), encoding="utf-8")
            new_p.unlink()
            _git(api_repo, "rm", "--cached", "-q", "--ignore-unmatch", f"supabase/migrations/{new_name}")


def _resolve_session_lock_dir(worktree_root: Path, work_root: str | None = None) -> Path | None:
    proc = _git(worktree_root, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if proc.returncode == 0 and proc.stdout.strip():
        common_git = Path(proc.stdout.strip()).resolve()
        if common_git.is_dir():
            return common_git
    if work_root:
        wr = Path(work_root)
        if wr.is_dir():
            return wr
    return None


@contextlib.contextmanager
def session_complete_lock(
    lock_dir: Path | None,
    *,
    holder: str = "unknown",
    timeout_seconds: float = 2400.0,
    poll_interval: float = 1.0,
    lock_filename: str = "w0m-session-complete.lock",
) -> Iterator[Path | None]:
    """Serialize live `session-complete` runs across worktrees via kernel `fcntl.flock` (T660)."""
    if lock_dir is None or not lock_dir.is_dir():
        yield None
        return
    lock_path = lock_dir / lock_filename
    fh = lock_path.open("a+", encoding="utf-8")
    acquired = False
    start = time.monotonic()
    last_log = -30.0
    try:
        while True:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except BlockingIOError:
                holder_desc = "another session"
                try:
                    fh.seek(0)
                    raw = fh.read().strip()
                    if raw:
                        meta: Any = json.loads(raw)
                        if isinstance(meta, dict):
                            h_name = str(meta.get("holder") or "unknown")
                            h_pid = meta.get("pid")
                            holder_desc = f"{h_name} (pid {h_pid})" if h_pid else h_name
                except (OSError, json.JSONDecodeError):
                    pass
                elapsed = time.monotonic() - start
                if elapsed >= timeout_seconds:
                    raise SessionCompleteError(
                        "session_complete_lock_timeout",
                        f"Timed out after {elapsed:.1f}s waiting for w0m-session-complete.lock held by {holder_desc}",
                    ) from None
                if elapsed - last_log >= 30.0:
                    print(
                        f"[session-complete] Waiting for active session-complete lock ({holder_desc}, {int(elapsed)}s) ...",
                        file=sys.stderr,
                        flush=True,
                    )
                    last_log = elapsed
                time.sleep(min(poll_interval, max(0.01, timeout_seconds - elapsed)))

        payload = {
            "pid": os.getpid(),
            "holder": holder,
            "acquired_at": dt.datetime.now(dt.UTC).isoformat(),
        }
        fh.seek(0)
        fh.truncate()
        fh.write(json.dumps(payload) + "\n")
        fh.flush()
        yield lock_path
    finally:
        if acquired:
            with contextlib.suppress(OSError):
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        fh.close()


def wait_for_land_lock(work_root: Path | None, *, timeout_seconds: float = 1200.0) -> None:
    """Wait politely for any live sibling `.land.lock` holder to finish before syncing and running gates."""
    if not work_root or not work_root.is_dir():
        return
    lock_file = work_root / ".land.lock"
    start = time.monotonic()
    last_log = -30.0
    while lock_file.is_file():
        holder_pid: int | None = None
        holder_set = "unknown"
        try:
            meta: Any = json.loads(lock_file.read_text(encoding="utf-8"))
            if isinstance(meta, dict):
                raw_pid = meta.get("pid")
                if isinstance(raw_pid, int):
                    holder_pid = raw_pid
                holder_set = str(meta.get("set_name") or "unknown")
        except (OSError, json.JSONDecodeError):
            break
        if holder_pid is not None:
            try:
                os.kill(holder_pid, 0)
            except ProcessLookupError:
                break
            except PermissionError:
                pass
        elapsed = time.monotonic() - start
        if elapsed >= timeout_seconds:
            raise SessionCompleteError(
                "land_lock_timeout",
                f"Timed out after {int(elapsed)}s waiting for .land.lock held by {holder_set} (pid {holder_pid})",
            )
        if elapsed - last_log >= 30.0:
            print(
                f"[session-complete] Waiting for sibling .land.lock ({holder_set}, pid {holder_pid}, {int(elapsed)}s) ...",
                file=sys.stderr,
                flush=True,
            )
            last_log = elapsed
        time.sleep(5.0)


def sync_worktree_onto_origin_beta(worktree_root: Path) -> list[str]:
    """Advance umbrella and member repos in an agent tree onto `origin/beta` before regenerating surfaces."""
    synced: list[str] = []
    for rel_path, repo_dir in _discover_estate_repos(worktree_root):
        if not (repo_dir / ".git").exists():
            continue
        _git(repo_dir, "fetch", "-q", "origin")
        mb_proc = _git(repo_dir, "merge-base", "HEAD", BASE_REF)
        origin_proc = _git(repo_dir, "rev-parse", BASE_REF)
        head_proc = _git(repo_dir, "rev-parse", "HEAD")
        if mb_proc.returncode != 0 or origin_proc.returncode != 0 or head_proc.returncode != 0:
            continue
        mb = mb_proc.stdout.strip()
        origin_sha = origin_proc.stdout.strip()
        head_sha = head_proc.stdout.strip()
        if not mb or not origin_sha or mb == origin_sha:
            continue

        if head_sha != mb:
            _git(repo_dir, "reset", "--soft", mb, check=True)
        _git(repo_dir, "reset", "HEAD", check=True)

        lesson_tail = ""
        if rel_path == ".":
            base_l = _git(repo_dir, "show", f"{mb}:LESSONS.md")
            lessons_file = repo_dir / "LESSONS.md"
            if base_l.returncode == 0 and lessons_file.is_file():
                cur_l = lessons_file.read_text(encoding="utf-8")
                base_l_prefix = base_l.stdout.rstrip("\n")
                if cur_l.startswith(base_l_prefix):
                    lesson_tail = cur_l[len(base_l_prefix) :]
                elif cur_l != base_l.stdout:
                    base_line_set = set(base_l.stdout.splitlines())
                    added_lines = [ln for ln in cur_l.splitlines() if ln.strip() and ln not in base_line_set]
                    if added_lines:
                        lesson_tail = "\n" + "\n".join(added_lines) + "\n"
            for gen_rel in ("STATE.md", "TASKS.md", "docs/DECISIONS.md", "LESSONS.md", "catalog-info.yaml"):
                if (repo_dir / gen_rel).exists():
                    _git(repo_dir, "checkout", "HEAD", "--", gen_rel)
        elif rel_path == "w0m-web":
            for gen_web_rel in (
                "docs/CODEMAP.md",
                "docs/CP-FEATURE-INDEX.md",
                "docs/STATUS-DASHBOARD.html",
                "docs/SKILLS-CATALOG.md",
                "project/catalog-entities.json",
                "project/tickets.json",
                "project/tickets-sync-index.json",
            ):
                if (repo_dir / gen_web_rel).exists():
                    _git(repo_dir, "checkout", "HEAD", "--", gen_web_rel)

        dirty = _git(repo_dir, "status", "--porcelain").stdout.strip()
        if dirty:
            _git(repo_dir, "stash", "push", "-u", "-q", "-m", "session-complete-sync", check=True)
        _git(repo_dir, "reset", "--hard", "-q", BASE_REF, check=True)
        if dirty:
            pop = _git(repo_dir, "stash", "pop", "-q")
            if pop.returncode != 0:
                raise SessionCompleteError(
                    "sync_rebase_conflict",
                    f"Conflict applying working tree changes onto {BASE_REF} in {rel_path}:\n{pop.stdout}\n{pop.stderr}",
                )
        if rel_path == "." and lesson_tail.strip():
            lessons_file = repo_dir / "LESSONS.md"
            latest_l = lessons_file.read_text(encoding="utf-8") if lessons_file.is_file() else ""
            if lesson_tail.strip() not in latest_l:
                lessons_file.write_text(
                    latest_l.rstrip("\n") + "\n\n" + lesson_tail.lstrip("\n"),
                    encoding="utf-8",
                )
        synced.append(rel_path)
    return synced


def _extract_h2_section(body_text: str, heading_pattern: str) -> tuple[int, int] | None:
    m = re.search(heading_pattern, body_text, re.MULTILINE | re.IGNORECASE)
    if not m:
        return None
    start = m.start()
    rest = body_text[m.end() :]
    m_next = re.search(r"^##\s+", rest, re.MULTILINE)
    end = m.end() + m_next.start() if m_next else len(body_text)
    return start, end


def normalize_ticket_file(
    ticket_path: Path,
    *,
    complete_acs: bool = False,
    no_lessons: bool = False,
    lesson_note: str | None = None,
    today: str | None = None,
    dry_run: bool = False,
    ticket_id_override: str | None = None,
) -> TicketNormalizationResult:
    if not ticket_path.is_file():
        raise SessionCompleteError("missing_ticket", f"Ticket file does not exist: {ticket_path}")

    tid = ticket_id_override or ticket_path.stem
    raw = ticket_path.read_text(encoding="utf-8")
    parsed = _parse_frontmatter(raw)
    if not parsed:
        raise SessionCompleteError("invalid_frontmatter", f"{tid}: missing YAML frontmatter block")

    fm_lines, body_lines = parsed
    prev_status = _frontmatter_get(fm_lines, "status")
    prev_queue = _frontmatter_get(fm_lines, "queue")
    prev_closed_as = _frontmatter_get(fm_lines, "closed_as")

    body_text = "".join(body_lines)
    if not re.search(r"^##\s+Definition\s+of\s+Done\b", body_text, re.MULTILINE | re.IGNORECASE):
        raise SessionCompleteError(
            "missing_dod",
            f"{tid}: missing required '## Definition of Done' section (enforced by dod-check)",
        )

    unchecked_acs: list[str] = []
    completed_acs: list[str] = []
    new_body_lines: list[str] = []
    for line in body_lines:
        stripped = line.rstrip("\r\n")
        ending = line[len(stripped) :]
        m_ac = AC_LINE_RE.match(stripped)
        if m_ac:
            state = m_ac.group(2)
            ac_id_match = re.search(r"\b(AC\d+[a-z]?)\b", m_ac.group(3))
            ac_label = ac_id_match.group(1) if ac_id_match else "AC"
            if state in (" ", "~"):
                if complete_acs:
                    new_body_lines.append(f"{m_ac.group(1)}x{m_ac.group(3)}{ending}")
                    completed_acs.append(ac_label)
                    continue
                unchecked_acs.append(ac_label)
        new_body_lines.append(line)

    if unchecked_acs:
        raise SessionCompleteError(
            "unchecked_acs",
            f"{tid}: unchecked acceptance criteria ({', '.join(unchecked_acs)}). "
            "Verify and check them off with evidence, or pass --complete-acs.",
        )

    body_text = "".join(new_body_lines)
    status_bounds = _extract_h2_section(body_text, r"^##\s+Status(?:\s+notes)?\b.*$")
    if status_bounds is None:
        raise SessionCompleteError(
            "missing_status_section",
            f"{tid}: missing required '## Status notes' (or '## Status') section",
        )

    s_start, s_end = status_bounds
    status_section = body_text[s_start:s_end]
    links_bounds = _extract_h2_section(body_text, r"^##\s+Links\b.*$")
    links_section = body_text[links_bounds[0] : links_bounds[1]] if links_bounds else ""

    has_lesson_disp = bool(
        LESSON_DISPOSITION_RE.search(status_section) or LESSON_DISPOSITION_RE.search(links_section)
    )
    lesson_added = False
    eff_today = today or dt.date.today().isoformat()
    if not has_lesson_disp:
        if lesson_note and lesson_note.strip():
            note_line = f"- **{eff_today}**: {lesson_note.strip()}\n"
        elif no_lessons:
            note_line = f"- **{eff_today}**: Lessons: none (routine delivery).\n"
        else:
            raise SessionCompleteError(
                "missing_lesson_disposition",
                f"{tid}: missing explicit lesson disposition in '## Status notes'. "
                "Record an earned rule in LESSONS.md + cite it in Status notes, "
                "pass --lesson-note '...', or pass --no-lessons.",
            )
        trimmed = status_section.rstrip("\r\n")
        trailing_ws = status_section[len(trimmed) :] or "\n"
        updated_status = f"{trimmed}\n{note_line}{trailing_ws}"
        body_text = body_text[:s_start] + updated_status + body_text[s_end:]
        lesson_added = True

    fm_copy = list(fm_lines)
    _frontmatter_set(fm_copy, "status", "done")
    _frontmatter_set(fm_copy, "queue", "done")
    if not prev_closed_as:
        _frontmatter_set(fm_copy, "closed_as", "completed", after_key="status")
    cur_type = _frontmatter_get(fm_copy, "type").lower()
    if cur_type == "fix":
        _frontmatter_set(fm_copy, "type", "bug")
    elif cur_type in ("chore", "refactor", "perf", "test", "docs", "ci", "build"):
        _frontmatter_set(fm_copy, "type", "task")
    elif not cur_type:
        _frontmatter_set(fm_copy, "type", "task", after_key="spec")
    if not any(re.match(r"^gh_issue\s*:", ln.rstrip("\r\n")) for ln in fm_copy):
        _frontmatter_set(fm_copy, "gh_issue", "", after_key="agent_id")

    rendered = "---\n" + "".join(fm_copy) + "---\n" + body_text
    changed = rendered != raw
    if changed and not dry_run:
        ticket_path.write_text(rendered, encoding="utf-8")

    return TicketNormalizationResult(
        ticket_id=tid,
        path=str(ticket_path),
        changed=changed,
        previous_status=prev_status,
        previous_queue=prev_queue,
        lesson_disposition_added=lesson_added,
        completed_acs=completed_acs,
    )


def cited_tickets_in_report(report_path: Path) -> set[str]:
    head = "\n".join(
        report_path.read_text(encoding="utf-8", errors="replace").splitlines()[:REPORT_HEADER_LINES]
    )
    cited: set[str] = set()
    for num, draft_slug in REPORT_CITE_RE.findall(report_path.name) + REPORT_CITE_RE.findall(head):
        if num:
            cited.add(f"T{int(num)}")
        elif draft_slug:
            cited.add(f"DRAFT-{draft_slug}")
    return cited


def mirror_reports(
    worktree_root: Path,
    sdlc_config: dict[str, Any],
    target_tickets: Sequence[str],
    *,
    dry_run: bool = False,
) -> list[str]:
    wrapup = sdlc_config.get("session_wrapup")
    if not isinstance(wrapup, dict):
        return []

    canon_rel = str(wrapup.get("reports_canonical_dir") or ".agents/reports").strip()
    mirror_rel = str(wrapup.get("reports_mirror_dir") or "").strip()
    if not mirror_rel:
        return []

    src_dir = worktree_root / canon_rel
    dst_dir = worktree_root / mirror_rel
    if not src_dir.is_dir():
        return []

    target_set = set(target_tickets)
    changed_report_names: set[str] = set()
    st = _git(worktree_root, "status", "--porcelain", "--", canon_rel)
    if st.returncode == 0:
        for line in st.stdout.splitlines():
            if len(line) >= 4:
                changed_report_names.add(Path(line[3:].strip().split(" -> ")[-1]).name)
    diff = _git(worktree_root, "diff", "--name-only", f"{BASE_REF}...HEAD", "--", canon_rel)
    if diff.returncode == 0:
        for line in diff.stdout.splitlines():
            if line.strip():
                changed_report_names.add(Path(line.strip()).name)

    mirrored: list[str] = []
    for src_file in sorted(src_dir.iterdir()):
        if not src_file.is_file():
            continue
        cites_target = bool(cited_tickets_in_report(src_file) & target_set)
        is_branch_report = src_file.name in changed_report_names
        if not (cites_target or is_branch_report):
            continue
        dst_file = dst_dir / src_file.name
        src_bytes = src_file.read_bytes()
        if dst_file.is_file() and dst_file.read_bytes() == src_bytes:
            continue
        if not dry_run:
            dst_dir.mkdir(parents=True, exist_ok=True)
            dst_file.write_bytes(src_bytes)
        mirrored.append(str(dst_file.relative_to(worktree_root)))
    return mirrored


def _refresh_synced_ticket_index_hashes(worktree_root: Path) -> bool:
    """Recompute `tickets-sync-index.json` hashes for already-synced tickets (`gh_issue` present) after frontmatter/TASKS.md render."""
    web_root = worktree_root / "w0m-web" if (worktree_root / "w0m-web").is_dir() else worktree_root
    idx_path = web_root / "project" / "tickets-sync-index.json"
    tickets_dir = worktree_root / ".tasks"
    if not idx_path.is_file() or not tickets_dir.is_dir():
        return False
    scripts_dir = str(worktree_root / "scripts")
    web_scripts_dir = str(web_root / "project" / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    if web_scripts_dir not in sys.path and Path(web_scripts_dir).is_dir():
        sys.path.insert(0, web_scripts_dir)
    try:
        import sync_github as sg  # noqa: PLC0415
    except Exception:
        return False

    orig_dry = sg.DRY
    orig_tickets_dir = sg.TICKETS_DIR
    orig_index = sg.INDEX
    orig_manifest = sg.MANIFEST
    try:
        sg.DRY = False
        sg.TICKETS_DIR = tickets_dir
        sg.INDEX = idx_path
        sg.MANIFEST = web_root / "project" / "tickets.json"
        recorded = sg.load_index()
        tickets = sg.load_tickets()
        changed = False
        for t in tickets:
            tid = str(t.get("id") or "")
            if not tid:
                continue
            if t.get("gh_issue") is not None and tid in recorded:
                desired_hash = sg.projection_hash(sg.projection_of(t, sg.summary_of(tid)))
                if recorded.get(tid) != desired_hash:
                    recorded[tid] = desired_hash
                    changed = True
        if changed:
            sg.save_index(recorded)
        return changed
    except Exception:
        return False
    finally:
        sg.DRY = orig_dry
        sg.TICKETS_DIR = orig_tickets_dir
        sg.INDEX = orig_index
        sg.MANIFEST = orig_manifest


def harvest_and_refresh_surfaces(
    worktree_root: Path,
    *,
    set_name: str | None = None,
    dry_run: bool = False,
    tickets_only: bool = False,
) -> dict[str, Any]:
    harvest_script = worktree_root / "scripts" / "lessons_query.py"
    harvest_output = ""
    if not tickets_only and harvest_script.is_file():
        cmd = [sys.executable, str(harvest_script), "--harvest-friction"]
        if set_name:
            cmd.extend(["--tree-name", set_name])
        res = _run(cmd, cwd=worktree_root)
        harvest_output = (res.stdout or res.stderr).strip()[-600:]

    refreshed: list[str] = []
    if not dry_run:
        generators: list[tuple[str, tuple[str, ...]]] = [
            ("tickets_frontmatter_sync", ("scripts/tickets_frontmatter_sync.py",)),
            ("tasks_render", ("scripts/tasks_render.py",)),
        ]
        if not tickets_only:
            generators.extend(
                [
                    ("decisions_index", ("scripts/decisions_index.py",)),
                    ("catalog_sync", ("w0m-web/project/scripts/catalog_sync.py", "--write")),
                    ("skills_catalog_gen", ("w0m-web/project/scripts/skills_catalog_gen.py", "--write")),
                    ("cp_feature_index", ("w0m-web/project/scripts/cp_feature_index.py",)),
                ]
            )
            if (worktree_root / "w0m-web" / ".codegraph" / "graph.db").is_file():
                generators.append(("codemap_gen", ("w0m-web/project/scripts/codemap_gen.py", "--write")))
        generators.append(("state_doctor", ("scripts/state_doctor.py", "--write")))

        t0_gen = time.monotonic()
        total_gens = len(generators)
        for idx_g, (label, rel_cmd) in enumerate(generators, 1):
            script_path = worktree_root / rel_cmd[0]
            if script_path.is_file():
                print(
                    format_progress_bar(
                        idx_g,
                        total_gens,
                        f"refresh surface: {label} ...",
                        elapsed_sec=time.monotonic() - t0_gen,
                        prefix="[session-complete:surfaces]",
                    ),
                    file=sys.stderr,
                    flush=True,
                )
                _run([sys.executable, str(script_path), *rel_cmd[1:]], cwd=worktree_root, check=True)
                refreshed.append(label)

        if _refresh_synced_ticket_index_hashes(worktree_root):
            refreshed.append("tickets_sync_index_hashes")

    return {"harvestSummary": harvest_output, "refreshed": refreshed}


def load_sdlc_config(worktree_root: Path) -> dict[str, Any]:
    sdlc_path = worktree_root / ".w0m" / "sdlc.json"
    if not sdlc_path.is_file():
        raise SessionCompleteError("missing_sdlc_config", f"Missing {sdlc_path}")
    try:
        data: Any = json.loads(sdlc_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SessionCompleteError("invalid_sdlc_config", f"Corrupt {sdlc_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SessionCompleteError("invalid_sdlc_config", f"{sdlc_path} root must be a JSON object")
    return data


def _verify_target_ticket_schema(
    worktree_root: Path,
    target_tickets: Sequence[str],
) -> dict[str, Any] | None:
    schema_script = worktree_root / "scripts" / "ticket_schema_check.py"
    if not schema_script.is_file():
        return None
    label = "scripts/ticket_schema_check.py --json (SCHEMA + target tickets)"
    proc = _run([sys.executable, str(schema_script), "--json"], cwd=worktree_root)
    if proc.returncode != 0:
        tail = ((proc.stderr or "") + "\n" + (proc.stdout or "")).strip()[-2000:]
        raise SessionCompleteError(
            "verification_gate_failed",
            f"Gate failed ({label}, exit {proc.returncode}):\n{tail}",
        )
    try:
        payload: dict[str, Any] = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise SessionCompleteError(
            "verification_gate_failed",
            f"Invalid JSON from ticket_schema_check.py: {exc}",
        ) from exc
    target_set = {t.upper() for t in target_tickets}
    bad_lines: list[str] = []
    for row in payload.get("rows") or []:
        row_tid = str(row.get("ticket", "")).upper()
        errs = row.get("errors") or []
        if not errs:
            continue
        if not target_set or row_tid in target_set:
            bad_lines.extend(f"  {row.get('ticket')}: {err}" for err in errs)
        elif row_tid == "SCHEMA":
            for err in errs:
                cited = {m.upper() for m in re.findall(r"\bT\d+\b", str(err), re.IGNORECASE)}
                if not cited or (cited & target_set):
                    bad_lines.append(f"  SCHEMA: {err}")
    if bad_lines:
        formatted = "\n".join(bad_lines)
        raise SessionCompleteError(
            "verification_gate_failed",
            f"Gate failed ({label}):\n{formatted}",
        )
    return {"gate": label, "returncode": 0}


def _filter_gates_for_mode(
    gates: list[Any],
    dev_mode: str,
) -> list[str]:
    """Filter `.w0m/sdlc.json -> session_wrapup.verification_gates` by `ultra` | `balance` | `wise` (T704 AC4/AC5)."""
    raw_list = [str(g).strip() for g in gates if str(g).strip()]
    if dev_mode == "wise":
        return raw_list
    if dev_mode == "ultra":
        ultra_tokens = (
            "lessons_check.py",
            "supabase_surface_drift_check.py",
            "ds-conformance",
            "ui-ticket-leak-check",
            "reports-ticket-check",
            "state-check",
        )
        return [g for g in raw_list if any(tok in g for tok in ultra_tokens)]
    # `balance` mode (default): defer estate-wide 90s py-typecheck and 129-file mmd-validate to `just deploy` / `wise`
    deferred_in_balance = (
        "just py-typecheck",
        "just mmd-validate",
        "just skills-sync --check",
        "just standards-check",
    )
    return [g for g in raw_list if g not in deferred_in_balance]


def run_verification_gates(
    worktree_root: Path,
    sdlc_config: dict[str, Any],
    target_tickets: Sequence[str] = (),
    dev_mode: str = "balance",
) -> list[dict[str, Any]]:
    wrapup = sdlc_config.get("session_wrapup")
    if not isinstance(wrapup, dict):
        raise SessionCompleteError("missing_session_wrapup", ".w0m/sdlc.json missing session_wrapup object")
    gates = wrapup.get("verification_gates")
    if not isinstance(gates, list) or not gates:
        raise SessionCompleteError(
            "missing_verification_gates",
            ".w0m/sdlc.json -> session_wrapup.verification_gates must be a non-empty list",
        )

    selected_gates = _filter_gates_for_mode(gates, dev_mode)
    commands: list[tuple[str, list[str]]] = []
    for gate_str in selected_gates:
        argv = shlex.split(gate_str)
        if argv and argv[0] == "python3":
            argv[0] = sys.executable
        commands.append((gate_str, argv))

    results: list[dict[str, Any]] = []
    total = len(commands) + (1 if (worktree_root / "scripts" / "ticket_schema_check.py").is_file() else 0)
    t0_gates = time.monotonic()
    for idx, (label, argv) in enumerate(commands, 1):
        bar_line = format_progress_bar(
            idx,
            total,
            f"{label} ...",
            elapsed_sec=time.monotonic() - t0_gates,
            prefix="[session-complete]",
        )
        print(bar_line, file=sys.stderr, flush=True)
        proc = _run(argv, cwd=worktree_root)
        results.append({"gate": label, "returncode": proc.returncode})
        if proc.returncode != 0:
            tail = ((proc.stderr or "") + "\n" + (proc.stdout or "")).strip()[-2000:]
            raise SessionCompleteError(
                "verification_gate_failed",
                f"Gate failed ({label}, exit {proc.returncode}):\n{tail}",
            )

    if (worktree_root / "scripts" / "ticket_schema_check.py").is_file():
        label = "scripts/ticket_schema_check.py --json (SCHEMA + target tickets)"
        bar_line = format_progress_bar(
            total,
            total,
            f"{label} ...",
            elapsed_sec=time.monotonic() - t0_gates,
            prefix="[session-complete]",
        )
        print(bar_line, file=sys.stderr, flush=True)
        schema_res = _verify_target_ticket_schema(worktree_root, target_tickets)
        if schema_res is not None:
            results.append(schema_res)
    return results


def run_post_commit_ticket_audits(
    worktree_root: Path,
    target_tickets: Sequence[str],
) -> list[dict[str, Any]]:
    """Run strict single-ticket reality audits AFTER committing (when git working tree is clean)."""
    audit_script = worktree_root / "scripts" / "ticket_audit.py"
    if not audit_script.is_file():
        return []
    results: list[dict[str, Any]] = []
    for tid in target_tickets:
        label = f"scripts/ticket_audit.py {tid} --strict --offline"
        proc = _run(
            [sys.executable, str(audit_script), tid, "--strict", "--offline"],
            cwd=worktree_root,
        )
        results.append({"gate": label, "returncode": proc.returncode})
        if proc.returncode != 0:
            tail = ((proc.stderr or "") + "\n" + (proc.stdout or "")).strip()[-2000:]
            raise SessionCompleteError(
                "ticket_audit_failed",
                f"Post-commit ticket audit failed ({label}, exit {proc.returncode}):\n{tail}",
            )
    return results


def _discover_estate_repos(root_dir: Path) -> list[tuple[str, Path]]:
    """Return `[(rel_path, abs_dir), ...]` with member repos first and `.` last."""
    rel_py = root_dir / "scripts" / "release.py"
    if rel_py.is_file():
        sys_path_entry = str(rel_py.parent)
        if sys_path_entry not in sys.path:
            sys.path.insert(0, sys_path_entry)
        import release as rel_mod

        repos = rel_mod.estate_repos(root_dir)
        members = sorted((r.path, r.abs(root_dir)) for r in repos if r.path != ".")
        umbrella = [(r.path, r.abs(root_dir)) for r in repos if r.path == "."]
        return members + umbrella

    candidates: list[tuple[str, Path]] = []
    web_dir = root_dir / "w0m-web"
    if (web_dir / ".git").exists():
        candidates.append(("w0m-web", web_dir))
    candidates.append((".", root_dir))
    return candidates


WRAPUP_SUBJECT_RE = re.compile(
    r"^chore\(T\d+\): (?:complete session wrap-up and archive|mirror session wrap-up surfaces)$"
)


def _unwind_unpushed_wrapup_commits(repo_dir: Path) -> None:
    """Unwind prior unpushed session-complete commits on retry so retries produce one clean commit."""
    mb_proc = _git(repo_dir, "merge-base", "HEAD", BASE_REF)
    if mb_proc.returncode != 0 or not mb_proc.stdout.strip():
        return
    mb = mb_proc.stdout.strip()
    while True:
        head_proc = _git(repo_dir, "rev-parse", "HEAD")
        if head_proc.returncode != 0:
            break
        head = head_proc.stdout.strip()
        if not head or head == mb:
            break
        subj = _git(repo_dir, "log", "-1", "--format=%s", "HEAD").stdout.strip()
        if not WRAPUP_SUBJECT_RE.match(subj):
            break
        _git(repo_dir, "reset", "--soft", "HEAD~1", check=True)


def commit_dirty_repos(
    worktree_root: Path,
    *,
    primary_ticket: str,
    commit_message: str | None = None,
) -> dict[str, str]:
    committed: dict[str, str] = {}
    repos = _discover_estate_repos(worktree_root)
    for rel_path, repo_dir in repos:
        st = _git(repo_dir, "status", "--porcelain")
        if st.returncode != 0 or not st.stdout.strip():
            continue
        if (repo_dir / ".git").exists():
            _unwind_unpushed_wrapup_commits(repo_dir)
        if rel_path == ".":
            harvest_and_refresh_surfaces(worktree_root, dry_run=False)
        _git(repo_dir, "add", "-A", check=True)
        staged = _git(repo_dir, "diff", "--cached", "--name-only")
        if not staged.stdout.strip():
            continue
        msg = (
            commit_message
            if (rel_path == "." and commit_message)
            else (
                f"chore({primary_ticket}): complete session wrap-up and archive"
                if rel_path == "."
                else f"chore({primary_ticket}): mirror session wrap-up surfaces"
            )
        )
        if "co-authored-by:" in msg.lower():
            raise SessionCompleteError("forbidden_trailer", "Co-Authored-By trailers are forbidden")
        _git(repo_dir, "commit", "-m", msg, check=True)
        sha = _git(repo_dir, "rev-parse", "HEAD", check=True).stdout.strip()
        committed[rel_path] = sha
    return committed


def fast_forward_canonical_checkout(
    canonical_root: Path,
    repo_rel_paths: Sequence[str],
) -> dict[str, str]:
    """Fast-forward `beta` in `canonical_root` for landed repos, preserving live Obsidian vault edits (T653)."""
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from obsidian_vault_guard import fast_forward_preserving_vault  # noqa: PLC0415

    outcomes: dict[str, str] = {}
    ordered = [r for r in repo_rel_paths if r != "."] + (["."] if "." in repo_rel_paths else [])
    for rel_path in ordered:
        repo_dir = canonical_root if rel_path == "." else (canonical_root / rel_path)
        if not (repo_dir / ".git").exists():
            outcomes[rel_path] = "missing"
            continue
        branch = _git(repo_dir, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        if branch != TARGET_BRANCH:
            outcomes[rel_path] = f"skipped_branch:{branch}"
            continue
        fetch_res = _git(repo_dir, "fetch", "-q", "origin", TARGET_BRANCH)
        if fetch_res.returncode != 0:
            outcomes[rel_path] = "fetch_failed"
            continue
        ff_res = fast_forward_preserving_vault(repo_dir, BASE_REF)
        if ff_res.ok:
            new_sha = _git(repo_dir, "rev-parse", "--short", "HEAD").stdout.strip()
            outcomes[rel_path] = f"fast_forwarded:{new_sha}"
            if ff_res.preserved_files or ff_res.merged_files or ff_res.healed_json:
                print(
                    f"[session-complete] {rel_path}: fast-forwarded to {new_sha} while preserving Obsidian vault "
                    f"(healed={len(ff_res.healed_json)}, preserved={len(ff_res.preserved_files)}, merged={len(ff_res.merged_files)})",
                    file=sys.stderr,
                    flush=True,
                )
        else:
            outcomes[rel_path] = "skipped_non_ff_or_dirty_overlap"
    return outcomes


def ensure_prepush_deps(worktree_root: Path) -> None:
    """Materialize local pnpm store into `w0m-api`, `w0m-cf`, and `w0m-web` `node_modules` when commits land.

    `w0m-web` RPC clients (`apps/{web,cp}/src/lib/rpc.ts`) import `AppType` across repo boundaries from
    `w0m-cf/src/index` and `w0m-api/src/index` (`T733`). If `w0m-cf/node_modules` or `w0m-api/node_modules`
    remains a symlink to the canonical checkout while `pnpm-lock.yaml` bumped `hono`, TypeScript resolves two
    distinct `hono` versions across `hc<AppType>` and fails `astro check`.
    """
    web_dir = worktree_root / "w0m-web"
    if not (web_dir / ".git").exists():
        return
    counts = _git(web_dir, "rev-list", "--left-right", "--count", f"{BASE_REF}...HEAD")
    web_ahead = (
        counts.returncode == 0
        and len(counts.stdout.split()) == 2
        and int(counts.stdout.split()[1]) > 0
    )

    for rel in ("w0m-api", "w0m-cf", "w0m-web"):
        repo_dir = worktree_root / rel
        if not (repo_dir / ".git").exists() or not (repo_dir / "pnpm-lock.yaml").is_file():
            continue
        nm = repo_dir / "node_modules"
        lock_diff = _git(repo_dir, "diff", "--name-only", f"{BASE_REF}...HEAD", "--", "pnpm-lock.yaml")
        lock_changed = lock_diff.returncode == 0 and bool(lock_diff.stdout.strip())
        needs_install = False
        if rel == "w0m-web" and web_ahead and (nm.is_symlink() or not (nm / ".modules.yaml").is_file()):
            needs_install = True
        elif lock_changed and (nm.is_symlink() or not (nm / ".modules.yaml").is_file()):
            needs_install = True
        if not needs_install:
            continue
        if nm.is_symlink():
            nm.unlink()
        print(
            f"[session-complete] Materializing {rel}/node_modules from pnpm store for pre-push gates ...",
            file=sys.stderr,
            flush=True,
        )
        _run(
            ["pnpm", "install", "--frozen-lockfile", "--prefer-offline", "--config.confirmModulesPurge=false"],
            cwd=repo_dir,
            check=True,
        )


def certify_estate_tree(
    estate_root: Path,
    *,
    canonical_root: Path | None = None,
    source: str = "session-complete",
) -> dict[str, Any] | None:
    """Certify the clean estate tree-set (`check-guardrails` + `offline/medium`) into `~/.cache/w0m/deploy-cert/` (T650)."""
    cert_script = estate_root / "scripts" / "deploy_cert.py"
    if not cert_script.is_file():
        return None
    cmd = [
        sys.executable,
        str(cert_script),
        "--root",
        str(estate_root),
        "certify",
        "--source",
        source,
        "--json",
    ]
    if canonical_root is not None:
        cmd.extend(["--canonical-root", str(canonical_root)])
    print(f"[session-complete] Certifying estate tree-set ({source}) ...", file=sys.stderr, flush=True)
    proc = _run(cmd, cwd=estate_root, check=False)
    if proc.returncode != 0:
        tail = ((proc.stderr or "") + "\n" + (proc.stdout or "")).strip()[-2500:]
        raise SessionCompleteError(
            "deploy_cert_failed",
            f"Estate tree-set certification failed (exit {proc.returncode}):\n{tail}",
        )
    if proc.stdout.strip():
        with contextlib.suppress(json.JSONDecodeError):
            parsed: dict[str, Any] = json.loads(proc.stdout)
            return parsed
    return {"ok": True}


def _estate_head_shas(estate_root: Path) -> dict[str, str]:
    shas: dict[str, str] = {}
    for rel_path, repo_dir in _discover_estate_repos(estate_root):
        if (repo_dir / ".git").exists():
            res = _git(repo_dir, "rev-parse", "HEAD")
            if res.returncode == 0 and res.stdout.strip():
                shas[rel_path] = res.stdout.strip()
    return shas


def refresh_canonical_graph_union(
    canon_root: Path,
    *,
    lock_dir: Path | None = None,
    holder: str = "canonical",
) -> dict[str, Any]:
    """Refresh canonical `codegraph` DBs, `~/.graphify/global-graph.json`, and `~/.w0m/knowledge-index/corpus.sqlite` (`T652`)."""
    with session_complete_lock(
        lock_dir,
        holder=holder,
        lock_filename="w0m-graph-rebuild.lock",
    ):
        graph_script = canon_root / "scripts" / "graph_global.py"
        if not graph_script.is_file():
            return {"refreshed": False, "reason": "missing_graph_global_script"}
        if shutil.which("graphify") is None:
            return {"refreshed": False, "reason": "graphify_absent"}

        codegraph_synced: list[str] = []
        if shutil.which("codegraph") is not None:
            for repo_rel in ("w0m-web", "w0m-api", "w0m-cf", "w0m-skills", "w0m-ext", "w0m-sec"):
                repo_dir = canon_root / repo_rel
                if (repo_dir / ".codegraph").is_dir():
                    cg_proc = _run(["codegraph", "sync"], cwd=repo_dir, check=False)
                    if cg_proc.returncode == 0:
                        codegraph_synced.append(repo_rel)

        kb_indexed = False
        kb_script = canon_root / "scripts" / "w0m_kb_vector.py"
        kb_db = Path.home() / ".w0m" / "knowledge-index" / "corpus.sqlite"
        if kb_script.is_file() and kb_db.is_file():
            print("[session-complete] Refreshing hybrid KB vector + BM25 index ...", file=sys.stderr, flush=True)
            kb_proc = _run([sys.executable, str(kb_script), "index", "--root", str(canon_root)], cwd=canon_root, check=False)
            kb_indexed = kb_proc.returncode == 0

        cmd = [
            sys.executable,
            str(graph_script),
            "--root",
            str(canon_root),
            "--auto-rebuild-stale",
            "--stale-limit",
            "0",
        ]
        print("[session-complete] Refreshing canonical knowledge-graph union ...", file=sys.stderr, flush=True)
        proc = _run(cmd, cwd=canon_root, check=False)
        if proc.returncode != 0:
            tail = ((proc.stderr or "") + "\n" + (proc.stdout or "")).strip()[-2000:]
            raise SessionCompleteError(
                "graph_union_refresh_failed",
                f"Canonical graph union refresh failed (exit {proc.returncode}):\n{tail}",
            )
        return {
            "refreshed": True,
            "codegraphSynced": codegraph_synced,
            "kbVectorIndexed": kb_indexed,
            "output": proc.stdout.strip()[-1200:],
        }


def precertify_web_prepush(worktree_root: Path) -> dict[str, Any]:
    """Run `w0m-web/.husky/pre-push` locally before `agent_tree.py land` opens an SSH socket (T660)."""
    web_dir = worktree_root / "w0m-web"
    if not (web_dir / ".git").exists():
        return {"status": "missing_web_repo"}

    counts = _git(web_dir, "rev-list", "--left-right", "--count", f"{BASE_REF}...HEAD")
    if counts.returncode != 0:
        return {"status": "no_base_ref"}
    parts = counts.stdout.split()
    if len(parts) != 2 or int(parts[1]) <= 0:
        return {"status": "not_ahead"}

    web_head = _git(web_dir, "rev-parse", "HEAD").stdout.strip()
    prepush_py = worktree_root / "scripts" / "prepush_runner.py"
    if prepush_py.is_file() and web_head:
        cert = _run(
            [sys.executable, str(prepush_py), "check-certified", "--commit", web_head],
            cwd=web_dir,
        )
        if cert.returncode == 0:
            return {"status": "already_certified", "commit": web_head}

    hook_path = web_dir / ".husky" / "pre-push"
    if not hook_path.is_file():
        return {"status": "no_prepush_hook"}

    ensure_prepush_deps(worktree_root)
    remote_proc = _git(web_dir, "remote", "get-url", "origin")
    remote_url = remote_proc.stdout.strip() if remote_proc.returncode == 0 else "origin"
    print(
        f"[session-complete] Pre-certifying w0m-web@{web_head[:8]} pre-push gates locally before SSH push ...",
        file=sys.stderr,
        flush=True,
    )
    env = {**os.environ, "LC_ALL": "C", "GIT_TERMINAL_PROMPT": "0", "GIT_EDITOR": "true"}
    proc = subprocess.run(
        ["sh", str(hook_path), "origin", remote_url],
        cwd=str(web_dir),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    if proc.returncode != 0:
        tail = ((proc.stderr or "") + "\n" + (proc.stdout or "")).strip()[-2500:]
        raise SessionCompleteError(
            "web_prepush_failed",
            f"w0m-web local pre-push certification failed (exit {proc.returncode}):\n{tail}",
        )
    return {"status": "certified_locally", "commit": web_head}


def land_and_cleanup_tree(
    ctx: SessionContext,
    *,
    remove_tree: bool = True,
    certify_after_land: bool = True,
    precertify_web: bool = True,
    pre_land_certified: bool = False,
    defer_graph_refresh: bool = False,
) -> dict[str, Any]:
    wt_root = Path(ctx.worktree_root)
    canon_root = Path(ctx.canonical_root)

    if ctx.in_agent_tree and ctx.set_name:
        ensure_prepush_deps(wt_root)
        if precertify_web or certify_after_land:
            precertify_web_prepush(wt_root)
        pre_land_shas = _estate_head_shas(wt_root)
        agent_tree_py = wt_root / "w0m-web" / "project" / "scripts" / "agent_tree.py"
        if not agent_tree_py.is_file():
            raise SessionCompleteError("missing_agent_tree_script", f"Missing {agent_tree_py}")

        land_cmd = [
            sys.executable,
            str(agent_tree_py),
            "land",
            "--set",
            ctx.set_name,
            "--lock-timeout",
            "1800",
        ]
        land_proc = _run(land_cmd, cwd=wt_root, check=False)
        if land_proc.returncode != 0:
            # If a 20-minute w0m-web pre-push run certified HEAD right as GitHub closed the idle SSH
            # socket, retry once immediately so `check-certified` skips pre-push in <1s and pushes cleanly.
            prepush_py = wt_root / "scripts" / "prepush_runner.py"
            web_dir = wt_root / "w0m-web"
            retried = False
            if prepush_py.is_file() and (web_dir / ".git").exists():
                web_head = _git(web_dir, "rev-parse", "HEAD").stdout.strip()
                if web_head:
                    cert = _run(
                        [sys.executable, str(prepush_py), "check-certified", "--commit", web_head],
                        cwd=web_dir,
                    )
                    if cert.returncode == 0:
                        print(
                            f"[session-complete] w0m-web@{web_head[:8]} is pre-push certified; retrying land after SSH drop ...",
                            file=sys.stderr,
                            flush=True,
                        )
                        land_proc = _run(land_cmd, cwd=wt_root, check=True)
                        retried = True
            if not retried:
                tail = ((land_proc.stderr or "") + "\n" + (land_proc.stdout or "")).strip()[-2000:]
                raise SessionCompleteError(
                    "command_failed",
                    f"{' '.join(land_cmd)} (exit {land_proc.returncode}):\n{tail}",
                )

        post_land_cert: dict[str, Any] | None = None
        if certify_after_land:
            post_land_shas = _estate_head_shas(wt_root)
            if pre_land_certified and pre_land_shas and pre_land_shas == post_land_shas:
                post_land_cert = {
                    "ok": True,
                    "cached": True,
                    "reusedPreLandCert": True,
                }
            else:
                # If a concurrent push caused `land` to rebase onto a new `origin/beta` tip,
                # certify the exact landed SHA set while `wt_root` is still clean and intact.
                post_land_cert = certify_estate_tree(
                    wt_root,
                    canonical_root=canon_root,
                    source="session-complete-post-land",
                )

        # CRITICAL: Switch working directory out of `~/.w0m/work/<set>/w0m` to `canonical_root`
        # BEFORE removing the agent tree so subsequent subprocesses never fail with dead `getcwd`.
        os.chdir(str(canon_root))

        ff_targets = [rel_path for rel_path, _ in _discover_estate_repos(canon_root)]
        ff_outcomes = fast_forward_canonical_checkout(canon_root, ff_targets)
        graph_refresh = (
            {"refreshed": False, "deferred": True}
            if defer_graph_refresh
            else refresh_canonical_graph_union(canon_root)
        )

        removed = False
        if remove_tree:
            canon_agent_tree_py = canon_root / "w0m-web" / "project" / "scripts" / "agent_tree.py"
            _run(
                [sys.executable, str(canon_agent_tree_py), "remove", ctx.set_name],
                cwd=canon_root,
                check=True,
            )
            removed = True

        return {
            "mode": "agent_tree_land",
            "set_name": ctx.set_name,
            "landOutput": land_proc.stdout.strip()[-1200:],
            "canonicalFastForward": ff_outcomes,
            "graphUnionRefresh": graph_refresh,
            "treeRemoved": removed,
            "postLandCert": post_land_cert,
        }

    pushed: dict[str, str] = {}
    for rel_path, repo_dir in _discover_estate_repos(canon_root):
        counts = _git(repo_dir, "rev-list", "--left-right", "--count", f"{BASE_REF}...HEAD")
        if counts.returncode != 0:
            continue
        behind, ahead = (int(x) for x in counts.stdout.split())
        if ahead <= 0:
            continue
        if behind > 0:
            _git(repo_dir, "rebase", BASE_REF, check=True)
        _git(repo_dir, "push", "origin", f"HEAD:{TARGET_BRANCH}", check=True)
        pushed[rel_path] = _git(repo_dir, "rev-parse", "HEAD").stdout.strip()
    if not pushed:
        graph_refresh_direct: dict[str, Any] = {"refreshed": False, "reason": "nothing_pushed"}
    elif defer_graph_refresh:
        graph_refresh_direct = {"refreshed": False, "deferred": True}
    else:
        graph_refresh_direct = refresh_canonical_graph_union(canon_root)
    return {
        "mode": "canonical_direct_push",
        "pushed": pushed,
        "graphUnionRefresh": graph_refresh_direct,
        "treeRemoved": False,
    }


def archive_and_finalize_session(
    ctx: SessionContext,
    *,
    close_completed_others: bool = False,
    close_self_when_settled: bool = False,
    skip_final_state_check: bool = False,
) -> dict[str, Any]:
    canon_root = Path(ctx.canonical_root)
    orca_script = canon_root / "scripts" / "orca_sessions.py"

    archive_info: dict[str, Any] = {"archived": False}
    if ctx.conversation_id and orca_script.is_file():
        res = _run(
            [
                sys.executable,
                str(orca_script),
                "archive",
                "--host",
                "local",
                "--conversation",
                ctx.conversation_id,
                "--json",
            ],
            cwd=canon_root,
        )
        if res.returncode == 0 and res.stdout.strip():
            try:
                raw_archive: dict[str, Any] = json.loads(res.stdout)
                archive_info = {"archived": True, **raw_archive}
            except json.JSONDecodeError:
                archive_info = {"archived": True, "raw": res.stdout.strip()}

    closed_others_info: dict[str, Any] | None = None
    if close_completed_others and orca_script.is_file():
        cmd = [sys.executable, str(orca_script), "close-completed", "--host", "local", "--json"]
        if ctx.terminal_handle:
            cmd.extend(["--exclude-handle", ctx.terminal_handle])
        res = _run(cmd, cwd=canon_root)
        if res.returncode == 0 and res.stdout.strip():
            try:
                raw_closed: dict[str, Any] = json.loads(res.stdout)
                closed_others_info = raw_closed
            except json.JSONDecodeError:
                closed_others_info = {"raw": res.stdout.strip()}

    if not skip_final_state_check and (canon_root / "scripts" / "state_doctor.py").is_file():
        _run(
            [sys.executable, str(canon_root / "scripts" / "state_doctor.py"), "--check"],
            cwd=canon_root,
            check=True,
        )

    detached_closer_info: dict[str, Any] | None = None
    if close_self_when_settled:
        prs_script = canon_root / "scripts" / "w0m_prs.py"
        if ctx.terminal_handle and prs_script.is_file():
            sys_entry = str(prs_script.parent)
            if sys_entry not in sys.path:
                sys.path.insert(0, sys_entry)
            import w0m_prs

            detached_closer_info = w0m_prs.spawn_detached_closer(
                terminal_handle=ctx.terminal_handle,
                initial_delay_sec=3.0,
                max_wait_sec=90.0,
            )
        else:
            detached_closer_info = {"ok": False, "spawned": False, "reason": "missing_terminal_handle"}

    return {
        "archive": archive_info,
        "closedCompletedOthers": closed_others_info,
        "detachedSelfCloser": detached_closer_info,
        "finalStateCheck": "skipped" if skip_final_state_check else "ok",
    }


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Complete w0m SDLC session wrap-up, verification gates, landing, and archive from inside an active session."
    )
    ap.add_argument(
        "tickets",
        nargs="*",
        help="Ticket ID(s) to close/normalize (e.g. T640 T638). Auto-detected from branch/claims if omitted.",
    )
    ap.add_argument("--ticket", dest="extra_tickets", action="append", default=[], help="Additional ticket ID(s)")
    ap.add_argument("--set", dest="set_name", default=None, help="Explicit agent tree set name under ~/.w0m/work")
    ap.add_argument("--conversation", default=None, help="Explicit conversation UUID override")
    ap.add_argument(
        "--complete-acs",
        action="store_true",
        help="Mark remaining open `- [ ] ACn` checkboxes as `- [x]` on target tickets",
    )
    ap.add_argument(
        "--no-lessons",
        action="store_true",
        help="Record `Lessons: none (routine delivery)` on target tickets lacking a lesson disposition",
    )
    ap.add_argument(
        "--lesson-note",
        default=None,
        help="Explicit lesson disposition line to append to target tickets lacking one",
    )
    ap.add_argument(
        "--no-auto-renumber",
        action="store_true",
        help="Disable automatic renumbering of newly added tickets that collide with origin/beta",
    )
    ap.add_argument("--commit-message", default=None, help="Custom umbrella commit message")
    ap.add_argument("--dry-run", action="store_true", help="Validate and preview wrap-up without mutating or landing")
    ap.add_argument("--skip-land", action="store_true", help="Normalize, verify gates, and commit locally without pushing")
    ap.add_argument(
        "--skip-gh-sync",
        action="store_true",
        help="Skip targeted GitHub Issue + Projects v2 sync during wrap-up (offline mode)",
    )
    ap.add_argument("--keep-tree", action="store_true", help="Keep agent tree directory after landing")
    ap.add_argument("--skip-gates", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument(
        "--close-completed-others",
        action="store_true",
        help="Close OTHER completed Orca agent/automation tabs while strictly sparing this session's terminal",
    )
    ap.add_argument(
        "--close-self-when-settled",
        action="store_true",
        help="Spawn a detached settled-output closer so this terminal tab closes AFTER the final response finishes",
    )
    ap.add_argument(
        "--mode",
        choices=("ultra", "balance", "wise"),
        default=None,
        help="Development mode override (ultra | balance | wise; defaults to active project mode)",
    )
    ap.add_argument("--allow-no-ticket", action="store_true", help="Allow wrap-up when zero tickets are targeted")
    ap.add_argument("--json", action="store_true", help="Emit machine-readable JSON summary")
    return ap


def sync_tickets_to_github(
    worktree_root: Path,
    target_tickets: Sequence[str],
    *,
    skip: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Mirror closed/updated target tickets to GitHub Issues + Projects v2 (`T651`).

    Runs BEFORE `harvest_and_refresh_surfaces()` and `commit_dirty_repos()` so backfilled `gh_issue:`
    keys, `w0m-web/project/tickets.json`, and `w0m-web/project/tickets-sync-index.json` are committed
    in the same wrap-up commit (preventing stale-open GitHub issues in `webomage/wom7board`).
    """
    tids_set = {t.strip().upper() for t in target_tickets if t and t.strip()}
    tickets_dir = worktree_root / ".tasks"
    if tickets_dir.is_dir():
        for p in tickets_dir.glob("T*.md"):
            m = TICKET_FILE_RE.match(p.name)
            if not m:
                continue
            try:
                txt = p.read_text(encoding="utf-8")
                if not re.search(r"^gh_issue:\s*\d+", txt, re.M):
                    tids_set.add(f"T{m.group(1)}")
            except OSError:
                pass
    sorted_tids = sorted(tids_set, key=lambda x: int(x[1:]) if x[1:].isdigit() else 999999)
    if dry_run:
        return {"mode": "dry_run", "tickets": sorted_tids}
    if skip:
        return {"mode": "skipped", "tickets": sorted_tids}
    if not sorted_tids:
        return {"mode": "no_tickets", "tickets": []}

    sync_script = worktree_root / "scripts" / "sync_github.py"
    if not sync_script.is_file():
        return {"mode": "missing_script", "tickets": sorted_tids}

    csv_tids = ",".join(sorted_tids)
    print(
        f"[session-complete] Syncing ticket(s) {csv_tids} to GitHub tracker ...",
        file=sys.stderr,
        flush=True,
    )
    proc = _run(
        [sys.executable, str(sync_script), "--tickets", csv_tids],
        cwd=worktree_root,
    )
    if proc.returncode == 0:
        return {
            "mode": "full_sync",
            "tickets": sorted_tids,
            "output": (proc.stdout or "").strip()[-800:],
        }

    combined = f"{proc.stderr or ''}\n{proc.stdout or ''}"
    if "read:project" in combined or "lacks Projects v2 scope" in combined:
        print(
            "[session-complete] [WARN] active GH_CONFIG_DIR lacks read:project scope; "
            "syncing GitHub Issues via --issues-only so closed tickets never stay open on GitHub "
            "(refresh Projects v2 scope via: gh auth refresh -h github.com -s project,read:project)",
            file=sys.stderr,
            flush=True,
        )
        proc_issues = _run(
            [sys.executable, str(sync_script), "--tickets", csv_tids, "--issues-only"],
            cwd=worktree_root,
        )
        if proc_issues.returncode == 0:
            return {
                "mode": "issues_only_missing_project_scope",
                "tickets": sorted_tids,
                "output": (proc_issues.stdout or "").strip()[-800:],
            }
        combined = f"{proc_issues.stderr or ''}\n{proc_issues.stdout or ''}"

    raise SessionCompleteError(
        "github_ticket_sync_failed",
        f"sync_github.py --tickets {csv_tids} failed (exit {proc.returncode}):\n{combined.strip()[-1500:]}",
    )


def run_session_complete(argv: Sequence[str] | None = None) -> tuple[int, dict[str, Any]]:
    args = build_parser().parse_args(list(argv) if argv is not None else None)

    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from dev_mode import resolve_active_mode  # noqa: PLC0415

    active_dev_mode, dev_mode_source = resolve_active_mode(getattr(args, "mode", None))

    ctx = detect_session_context(
        set_override=args.set_name,
        conversation_override=args.conversation,
    )
    wt_root = Path(ctx.worktree_root)
    sdlc_config = load_sdlc_config(wt_root)
    print(
        f"[session-complete] Active project mode: {active_dev_mode.upper()} (source: {dev_mode_source})",
        file=sys.stderr,
        flush=True,
    )

    lock_dir = (
        _resolve_session_lock_dir(wt_root, ctx.work_root)
        if (not args.dry_run and not args.skip_land)
        else None
    )
    holder_label = ctx.set_name or ctx.agent_id or "canonical"

    t0_session = time.monotonic()
    total_phases = 8

    def _emit_phase(phase_idx: int, phase_label: str) -> None:
        if args.json:
            return
        print(
            format_progress_bar(
                phase_idx,
                total_phases,
                f"[Phase {phase_idx}/{total_phases} · mode={active_dev_mode}] {phase_label}",
                elapsed_sec=time.monotonic() - t0_session,
                prefix="[session-complete:phase]",
            ),
            file=sys.stderr,
            flush=True,
        )

    with session_complete_lock(lock_dir, holder=holder_label):
        _emit_phase(1, "Discovering & normalizing target tickets + syncing origin/beta ...")
        explicit = [*args.tickets, *(args.extra_tickets or [])]
        targets = discover_target_tickets(
            wt_root,
            explicit_tickets=explicit,
            agent_id=ctx.agent_id,
            allow_empty=bool(args.allow_no_ticket),
        )

        renumbered: dict[str, str] = {}
        resequenced_migrations: dict[str, str] = {}
        committed: dict[str, str] = {}
        has_draft_targets = any(t.startswith("DRAFT-") for t in targets)
        if ctx.in_agent_tree and not args.dry_run and not args.skip_land:
            wait_for_land_lock(Path(ctx.work_root) if ctx.work_root else None)
        if (ctx.in_agent_tree or has_draft_targets) and (not args.no_auto_renumber or has_draft_targets) and targets:
            targets, renumbered = maybe_renumber_colliding_tickets(
                wt_root,
                targets,
                dry_run=bool(args.dry_run),
            )
        if ctx.in_agent_tree and not args.no_auto_renumber:
            resequenced_migrations = maybe_resequence_colliding_migrations(
                wt_root,
                dry_run=bool(args.dry_run),
            )
        if ctx.in_agent_tree and not args.dry_run and not args.skip_land:
            sync_worktree_onto_origin_beta(wt_root)

        try:
            reverse_renames = {new_t.lower(): old_t for old_t, new_t in renumbered.items()} if args.dry_run else {}
            ticket_results: list[dict[str, Any]] = []
            for tid in targets:
                disk_tid = reverse_renames.get(tid.lower(), tid)
                res = normalize_ticket_file(
                    wt_root / ".tasks" / f"{disk_tid}.md",
                    complete_acs=bool(args.complete_acs),
                    no_lessons=bool(args.no_lessons),
                    lesson_note=args.lesson_note,
                    dry_run=bool(args.dry_run),
                    ticket_id_override=tid,
                )
                ticket_results.append(asdict(res))

            mirrored_reports = mirror_reports(
                wt_root,
                sdlc_config,
                targets,
                dry_run=bool(args.dry_run),
            )

            if not args.dry_run and not args.skip_gates and targets:
                _verify_target_ticket_schema(wt_root, targets)

            _emit_phase(2, "Harvesting lessons & refreshing estate tracking surfaces ...")
            surfaces_info = harvest_and_refresh_surfaces(
                wt_root,
                set_name=ctx.set_name,
                dry_run=bool(args.dry_run),
            )

            if args.dry_run:
                gh_sync_info = sync_tickets_to_github(
                    wt_root,
                    targets,
                    skip=bool(args.skip_gh_sync or args.skip_land),
                    dry_run=True,
                )
                summary = {
                    "ok": True,
                    "dryRun": True,
                    "context": asdict(ctx),
                    "targetTickets": targets,
                    "renumberedTickets": renumbered,
                    "normalizedTickets": ticket_results,
                    "mirroredReports": mirrored_reports,
                    "githubSync": gh_sync_info,
                    "surfaces": surfaces_info,
                    "configuredGates": list((sdlc_config.get("session_wrapup") or {}).get("verification_gates") or []),
                }
                return 0, summary

            _emit_phase(3, "Running session wrap-up verification gates ...")
            gate_results: list[dict[str, Any]] = []
            if not args.skip_gates:
                gate_results = run_verification_gates(
                    wt_root,
                    sdlc_config,
                    targets,
                    dev_mode=active_dev_mode,
                )

            _emit_phase(4, "Synchronizing closed tickets to GitHub Issues & Project #6 ...")
            gh_sync_info = sync_tickets_to_github(
                wt_root,
                targets,
                skip=bool(args.skip_gh_sync or args.skip_land),
                dry_run=False,
            )
            if gh_sync_info.get("mode") in ("full_sync", "issues_only_missing_project_scope"):
                prev_harvest = surfaces_info.get("harvestSummary", "")
                prev_refreshed = list(surfaces_info.get("refreshed") or [])
                ticket_surfaces = harvest_and_refresh_surfaces(
                    wt_root,
                    set_name=ctx.set_name,
                    dry_run=False,
                    tickets_only=True,
                )
                for r_item in ticket_surfaces.get("refreshed") or []:
                    if r_item not in prev_refreshed:
                        prev_refreshed.append(r_item)
                surfaces_info = {
                    "harvestSummary": prev_harvest,
                    "refreshed": prev_refreshed,
                }

            _emit_phase(5, "Committing dirty estate repositories & post-commit ticket audits ...")
            primary_tid = ", ".join(targets) if targets else "T0"
            committed = commit_dirty_repos(
                wt_root,
                primary_ticket=primary_tid,
                commit_message=args.commit_message,
            )

            if not args.skip_gates and targets:
                gate_results.extend(run_post_commit_ticket_audits(wt_root, targets))

            _emit_phase(6, "Certifying estate tree for deploy ...")
            run_full_deploy_cert = (active_dev_mode == "wise") and (not bool(args.skip_gates))
            deploy_cert_info: dict[str, Any] | None = None
            if run_full_deploy_cert:
                deploy_cert_info = certify_estate_tree(
                    wt_root,
                    canonical_root=Path(ctx.canonical_root),
                    source="session-complete-pre-land",
                )
            else:
                deploy_cert_info = {
                    "status": "deferred_to_deploy",
                    "mode": active_dev_mode,
                }

            land_info: dict[str, Any] = {"mode": "skipped"}
            finalize_info: dict[str, Any] = {"mode": "skipped"}
            if not args.skip_land:
                _emit_phase(7, "Landing agent tree onto origin/beta & fast-forwarding canonical root ...")
                if ctx.in_agent_tree:
                    wait_for_land_lock(Path(ctx.work_root) if ctx.work_root else None)
                    extra_renumbered: dict[str, str] = {}
                    extra_reseq_migs: dict[str, str] = {}
                    if not args.no_auto_renumber and targets:
                        targets, extra_renumbered = maybe_renumber_colliding_tickets(
                            wt_root,
                            targets,
                            dry_run=False,
                        )
                        renumbered.update(extra_renumbered)
                    if not args.no_auto_renumber:
                        extra_reseq_migs = maybe_resequence_colliding_migrations(
                            wt_root,
                            dry_run=False,
                        )
                        resequenced_migrations.update(extra_reseq_migs)
                    synced_late = sync_worktree_onto_origin_beta(wt_root)
                    if extra_renumbered or extra_reseq_migs or synced_late:
                        ticket_results = [
                            asdict(
                                normalize_ticket_file(
                                    wt_root / ".tasks" / f"{tid}.md",
                                    complete_acs=bool(args.complete_acs),
                                    no_lessons=bool(args.no_lessons),
                                    lesson_note=args.lesson_note,
                                    dry_run=False,
                                )
                            )
                            for tid in targets
                        ]
                        mirrored_reports = mirror_reports(wt_root, sdlc_config, targets, dry_run=False)
                        gh_sync_info = sync_tickets_to_github(
                            wt_root,
                            targets,
                            skip=bool(args.skip_gh_sync),
                            dry_run=False,
                        )
                        surfaces_info = harvest_and_refresh_surfaces(wt_root, set_name=ctx.set_name, dry_run=False)
                        primary_tid = targets[0] if targets else "T0"
                        committed = commit_dirty_repos(
                            wt_root,
                            primary_ticket=primary_tid,
                            commit_message=args.commit_message,
                        )
                        if not args.skip_gates and targets:
                            gate_results.extend(run_post_commit_ticket_audits(wt_root, targets))
                        if run_full_deploy_cert:
                            deploy_cert_info = certify_estate_tree(
                                wt_root,
                                canonical_root=Path(ctx.canonical_root),
                                source="session-complete-late-sync",
                            )

                land_info = land_and_cleanup_tree(
                    ctx,
                    remove_tree=not bool(args.keep_tree),
                    certify_after_land=run_full_deploy_cert,
                    precertify_web=not bool(args.skip_gates),
                    pre_land_certified=run_full_deploy_cert and bool(deploy_cert_info),
                    defer_graph_refresh=True,
                )
                if land_info.get("mode") == "canonical_direct_push" and run_full_deploy_cert:
                    canon_p = Path(ctx.canonical_root)
                    deploy_cert_info = certify_estate_tree(
                        canon_p,
                        canonical_root=canon_p,
                        source="session-complete-direct-push",
                    )
                _emit_phase(8, "Archiving session & verifying final canonical state ...")
                finalize_info = archive_and_finalize_session(
                    ctx,
                    close_completed_others=bool(args.close_completed_others),
                    close_self_when_settled=bool(args.close_self_when_settled),
                    skip_final_state_check=bool(args.skip_gates),
                )
        except SessionCompleteError:
            if not args.dry_run and wt_root.is_dir():
                if committed and (renumbered or resequenced_migrations):
                    _soft_reset_worktree_to_merge_base(wt_root)
                if renumbered:
                    _rollback_renumbered_tickets(wt_root, renumbered)
                if resequenced_migrations:
                    _rollback_resequenced_migrations(wt_root, resequenced_migrations)
            raise

    if not args.skip_land and isinstance(land_info.get("graphUnionRefresh"), dict) and land_info["graphUnionRefresh"].get("deferred"):
        if active_dev_mode == "wise":
            land_info["graphUnionRefresh"] = refresh_canonical_graph_union(
                Path(ctx.canonical_root),
                lock_dir=lock_dir,
                holder=holder_label,
            )
        else:
            land_info["graphUnionRefresh"] = {
                "status": "deferred_to_deploy",
                "mode": active_dev_mode,
                "reason": "Full kb_vector + graph_global rebuild is deferred to `just deploy` or `--mode wise` (T704 AC5).",
            }

    summary = {
        "ok": True,
        "dryRun": False,
        "devMode": active_dev_mode,
        "devModeSource": dev_mode_source,
        "context": asdict(ctx),
        "targetTickets": targets,
        "renumberedTickets": renumbered,
        "normalizedTickets": ticket_results,
        "mirroredReports": mirrored_reports,
        "githubSync": gh_sync_info,
        "surfaces": surfaces_info,
        "verificationGates": gate_results,
        "deployCert": deploy_cert_info,
        "committedRepos": committed,
        "landing": land_info,
        "finalization": finalize_info,
    }
    return 0, summary


def _print_human_summary(summary: dict[str, Any]) -> None:
    ctx = summary["context"]
    mode = "DRY-RUN" if summary.get("dryRun") else "COMPLETE"
    print(f"[SESSION-{mode}] worktree={ctx['worktree_root']} canonical={ctx['canonical_root']}")
    if ctx.get("conversation_id") or ctx.get("terminal_handle"):
        print(
            f"  caller       : conversation={ctx.get('conversation_id') or '-'} "
            f"terminal={ctx.get('terminal_handle') or '-'} (spared)"
        )
    print(f"  tickets      : {', '.join(summary['targetTickets']) or '(none)'}")
    if summary.get("renumberedTickets"):
        pairs = ", ".join(f"{k}->{v}" for k, v in summary["renumberedTickets"].items())
        print(f"  renumbered   : {pairs}")
    if summary.get("mirroredReports"):
        print(f"  mirrored     : {len(summary['mirroredReports'])} report(s) -> {', '.join(summary['mirroredReports'])}")
    gh_sync = summary.get("githubSync") or {}
    if gh_sync.get("mode"):
        print(f"  gh sync      : {gh_sync.get('mode')} ({len(gh_sync.get('tickets') or [])} ticket(s))")
    if summary.get("dryRun"):
        print(f"  gates queued : {len(summary.get('configuredGates') or [])}")
        return
    print(f"  gates passed : {len(summary.get('verificationGates') or [])}")
    if summary.get("committedRepos"):
        commits_str = ", ".join(f"{k}@{v[:8]}" for k, v in summary["committedRepos"].items())
        print(f"  committed    : {commits_str}")
    landing = summary.get("landing") or {}
    if landing.get("mode") != "skipped":
        print(
            f"  landed       : mode={landing.get('mode')} "
            f"tree_removed={landing.get('treeRemoved')}"
        )
        ff = landing.get("canonicalFastForward") or {}
        if ff:
            ff_summary = ", ".join(f"{k}:{v}" for k, v in ff.items() if v.startswith("fast_forwarded"))
            if ff_summary:
                print(f"  live sync    : {ff_summary}")
    fin = summary.get("finalization") or {}
    if fin.get("finalStateCheck") == "ok":
        print("  final check  : state-check OK on canonical root")


def main(argv: Sequence[str] | None = None) -> int:
    json_flag = "--json" in (argv if argv is not None else sys.argv[1:])
    try:
        rc, summary = run_session_complete(argv)
    except SessionCompleteError as exc:
        if json_flag:
            print(json.dumps({"ok": False, "step": exc.step, "error": exc.detail}, indent=2))
        else:
            print(f"[SESSION-COMPLETE FAILED] {exc}", file=sys.stderr)
        return 1
    if json_flag:
        print(json.dumps(summary, indent=2))
    else:
        _print_human_summary(summary)
    return rc


if __name__ == "__main__":
    sys.exit(main())
