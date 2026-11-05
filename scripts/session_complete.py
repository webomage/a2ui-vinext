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
import datetime as dt
import json
import os
import re
import shlex
import subprocess
import sys
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_WORK_ROOT = Path.home() / ".w0m" / "work"
AGENT_ROOT_SUBDIR = "w0m"
BASE_REF = "origin/beta"
TARGET_BRANCH = "beta"

TICKET_ARG_RE = re.compile(r"^[Tt](\d{1,5})$")
TICKET_FILE_RE = re.compile(r"^T(\d{1,5})\.md$")
REPORT_CITE_RE = re.compile(r"\b[Tt](\d{1,5})\b")
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
    m = TICKET_ARG_RE.fullmatch(raw.strip())
    if not m:
        raise SessionCompleteError("invalid_ticket", f"Invalid ticket ID '{raw}' (expected T<number>)")
    return f"T{int(m.group(1))}"


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

    st = _git(worktree_root, "status", "--porcelain", "--", ".tasks/")
    if st.returncode == 0:
        for line in st.stdout.splitlines():
            if len(line) < 4:
                continue
            cand_path = line[3:].strip().split(" -> ")[-1].strip()
            m = TICKET_FILE_RE.match(Path(cand_path).name)
            if m and (worktree_root / cand_path).is_file():
                found_nums.add(int(m.group(1)))

    diff = _git(worktree_root, "diff", "--name-only", f"{BASE_REF}...HEAD", "--", ".tasks/")
    if diff.returncode == 0:
        for line in diff.stdout.splitlines():
            cand_path = line.strip()
            m = TICKET_FILE_RE.match(Path(cand_path).name)
            if m and (worktree_root / cand_path).is_file():
                found_nums.add(int(m.group(1)))

    if agent_id:
        tickets_dir = worktree_root / ".tasks"
        if tickets_dir.is_dir():
            for tpath in tickets_dir.glob("T*.md"):
                m = TICKET_FILE_RE.match(tpath.name)
                if not m:
                    continue
                parsed = _parse_frontmatter(tpath.read_text(encoding="utf-8", errors="replace"))
                if not parsed:
                    continue
                fm_lines, _ = parsed
                owner = _frontmatter_get(fm_lines, "agent_id")
                t_status = _frontmatter_get(fm_lines, "status")
                if owner == agent_id and t_status != "done":
                    found_nums.add(int(m.group(1)))

    if not found_nums and not allow_empty:
        raise SessionCompleteError(
            "no_target_tickets",
            "No modified or agent-claimed tickets detected in .tasks/; pass ticket ID(s) explicitly "
            "(e.g. `just session-complete T640`).",
        )
    return [f"T{n}" for n in sorted(found_nums)]


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


def _rewrite_ticket_id_tokens(text: str, old_tid: str, new_tid: str) -> str:
    old_lower = old_tid.lower()
    new_lower = new_tid.lower()
    updated = re.sub(rf"\b{re.escape(old_tid)}\b", new_tid, text)
    updated = re.sub(rf"\b{re.escape(old_lower)}\b", new_lower, updated)
    return updated


def maybe_renumber_colliding_tickets(
    worktree_root: Path,
    target_tickets: Sequence[str],
    *,
    dry_run: bool = False,
    fetch_remote: bool = True,
) -> tuple[list[str], dict[str, str]]:
    """Detect and renumber newly added branch tickets that collide with `origin/beta` (contiguous next ID)."""
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
    added_ids = sorted(local_ids - base_ids)
    clash = [n for n in added_ids if n in origin_ids]
    if not clash:
        return list(target_tickets), {}

    next_num = max(origin_ids) + 1
    renames: dict[str, str] = {}
    for old_num in clash:
        renames[f"T{old_num}"] = f"T{next_num}"
        next_num += 1

    mapped_targets = [renames.get(t, t) for t in target_tickets]
    if dry_run:
        return mapped_targets, renames

    head_sha = _git(worktree_root, "rev-parse", "HEAD").stdout.strip()
    if head_sha and head_sha != merge_base:
        _git(worktree_root, "reset", "--soft", merge_base, check=True)

    w0m_web_dir = worktree_root / "w0m-web"
    if (w0m_web_dir / ".git").exists():
        _git(w0m_web_dir, "fetch", "-q", "origin")
        web_mb = _git(w0m_web_dir, "merge-base", "HEAD", BASE_REF).stdout.strip()
        web_head = _git(w0m_web_dir, "rev-parse", "HEAD").stdout.strip()
        if web_mb and web_head and web_head != web_mb:
            _git(w0m_web_dir, "reset", "--soft", web_mb, check=True)

    for old_tid, new_tid in renames.items():
        old_tpath = tickets_dir / f"{old_tid}.md"
        new_tpath = tickets_dir / f"{new_tid}.md"
        if new_tpath.exists():
            raise SessionCompleteError("renumber_conflict", f"Target path already exists: {new_tpath}")
        if old_tpath.is_file():
            raw = old_tpath.read_text(encoding="utf-8")
            new_tpath.write_text(_rewrite_ticket_id_tokens(raw, old_tid, new_tid), encoding="utf-8")
            old_tpath.unlink()
            _git(worktree_root, "rm", "--cached", "-q", "--ignore-unmatch", f".tasks/{old_tid}.md")

        for rel_dir in (".agents/reports", "w0m-web/docs/reports"):
            rdir = worktree_root / rel_dir
            if not rdir.is_dir():
                continue
            for rfile in sorted(rdir.iterdir()):
                if not rfile.is_file():
                    continue
                if re.search(rf"\b{re.escape(old_tid.lower())}\b", rfile.name, re.IGNORECASE):
                    new_name = _rewrite_ticket_id_tokens(rfile.name, old_tid, new_tid)
                    dest = rdir / new_name
                    content = rfile.read_text(encoding="utf-8", errors="replace")
                    dest.write_text(_rewrite_ticket_id_tokens(content, old_tid, new_tid), encoding="utf-8")
                    if dest != rfile:
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

        lessons_path = worktree_root / "LESSONS.md"
        if lessons_path.is_file():
            diff_l = _git(worktree_root, "diff", merge_base, "--", "LESSONS.md")
            if old_tid in diff_l.stdout:
                base_lessons_proc = _git(worktree_root, "show", f"{merge_base}:LESSONS.md")
                curr_lessons = lessons_path.read_text(encoding="utf-8")
                base_prefix = base_lessons_proc.stdout.rstrip("\n")
                if base_lessons_proc.returncode == 0 and curr_lessons.startswith(base_prefix):
                    suffix = curr_lessons[len(base_prefix) :]
                    lessons_path.write_text(
                        base_prefix + _rewrite_ticket_id_tokens(suffix, old_tid, new_tid),
                        encoding="utf-8",
                    )
                else:
                    lessons_path.write_text(
                        _rewrite_ticket_id_tokens(curr_lessons, old_tid, new_tid),
                        encoding="utf-8",
                    )

    return mapped_targets, renames


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
            for gen_rel in ("STATE.md", "TASKS.md", "docs/DECISIONS.md", "LESSONS.md"):
                if (repo_dir / gen_rel).exists():
                    _git(repo_dir, "checkout", "HEAD", "--", gen_rel)
        elif rel_path == "w0m-web":
            dash = repo_dir / "docs" / "STATUS-DASHBOARD.html"
            if dash.exists():
                _git(repo_dir, "checkout", "HEAD", "--", "docs/STATUS-DASHBOARD.html")

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
) -> TicketNormalizationResult:
    if not ticket_path.is_file():
        raise SessionCompleteError("missing_ticket", f"Ticket file does not exist: {ticket_path}")

    tid = ticket_path.stem
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
    return {
        f"T{int(n)}"
        for n in REPORT_CITE_RE.findall(report_path.name) + REPORT_CITE_RE.findall(head)
    }


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


def harvest_and_refresh_surfaces(
    worktree_root: Path,
    *,
    set_name: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    harvest_script = worktree_root / "scripts" / "lessons_query.py"
    harvest_output = ""
    if harvest_script.is_file():
        cmd = [sys.executable, str(harvest_script), "--harvest-friction"]
        if set_name:
            cmd.extend(["--tree-name", set_name])
        res = _run(cmd, cwd=worktree_root)
        harvest_output = (res.stdout or res.stderr).strip()[-600:]

    refreshed: list[str] = []
    if not dry_run:
        generators: tuple[tuple[str, tuple[str, ...]], ...] = (
            ("tickets_frontmatter_sync", ("scripts/tickets_frontmatter_sync.py",)),
            ("tasks_render", ("scripts/tasks_render.py",)),
            ("decisions_index", ("scripts/decisions_index.py",)),
            ("state_doctor", ("scripts/state_doctor.py", "--write")),
        )
        for label, rel_cmd in generators:
            script_path = worktree_root / rel_cmd[0]
            if script_path.is_file():
                _run([sys.executable, str(script_path), *rel_cmd[1:]], cwd=worktree_root, check=True)
                refreshed.append(label)

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


def run_verification_gates(
    worktree_root: Path,
    sdlc_config: dict[str, Any],
    target_tickets: Sequence[str] = (),
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

    commands: list[tuple[str, list[str]]] = []
    for raw_gate in gates:
        gate_str = str(raw_gate).strip()
        if not gate_str:
            continue
        argv = shlex.split(gate_str)
        if argv and argv[0] == "python3":
            argv[0] = sys.executable
        commands.append((gate_str, argv))

    results: list[dict[str, Any]] = []
    total = len(commands) + (1 if (worktree_root / "scripts" / "ticket_schema_check.py").is_file() else 0)
    for idx, (label, argv) in enumerate(commands, 1):
        print(f"[session-complete] [{idx}/{total}] {label} ...", file=sys.stderr, flush=True)
        proc = _run(argv, cwd=worktree_root)
        results.append({"gate": label, "returncode": proc.returncode})
        if proc.returncode != 0:
            tail = ((proc.stderr or "") + "\n" + (proc.stdout or "")).strip()[-2000:]
            raise SessionCompleteError(
                "verification_gate_failed",
                f"Gate failed ({label}, exit {proc.returncode}):\n{tail}",
            )

    schema_script = worktree_root / "scripts" / "ticket_schema_check.py"
    if schema_script.is_file():
        label = "scripts/ticket_schema_check.py --json (SCHEMA + target tickets)"
        print(f"[session-complete] [{total}/{total}] {label} ...", file=sys.stderr, flush=True)
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
        results.append({"gate": label, "returncode": 1 if bad_lines else 0})
        if bad_lines:
            formatted = "\n".join(bad_lines)
            raise SessionCompleteError(
                "verification_gate_failed",
                f"Gate failed ({label}):\n{formatted}",
            )
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
    """Fast-forward `beta` in `canonical_root` for landed repos when non-overlapping."""
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
        ff_res = _git(repo_dir, "merge", "--ff-only", BASE_REF)
        if ff_res.returncode == 0:
            new_sha = _git(repo_dir, "rev-parse", "--short", "HEAD").stdout.strip()
            outcomes[rel_path] = f"fast_forwarded:{new_sha}"
        else:
            outcomes[rel_path] = "skipped_non_ff_or_dirty_overlap"
    return outcomes


def ensure_prepush_deps(worktree_root: Path) -> None:
    """Link local pnpm store into `w0m-web/node_modules` when `w0m-web` has commits to land."""
    web_dir = worktree_root / "w0m-web"
    if not (web_dir / ".git").exists() or not (web_dir / "pnpm-lock.yaml").is_file():
        return
    if (web_dir / "node_modules" / ".modules.yaml").is_file():
        return
    counts = _git(web_dir, "rev-list", "--left-right", "--count", f"{BASE_REF}...HEAD")
    if counts.returncode != 0:
        return
    parts = counts.stdout.split()
    if len(parts) != 2 or int(parts[1]) <= 0:
        return
    print("[session-complete] Linking w0m-web/node_modules from pnpm store for pre-push gates ...", file=sys.stderr, flush=True)
    _run(["pnpm", "install", "--frozen-lockfile", "--prefer-offline"], cwd=web_dir, check=True)


def land_and_cleanup_tree(
    ctx: SessionContext,
    *,
    remove_tree: bool = True,
) -> dict[str, Any]:
    wt_root = Path(ctx.worktree_root)
    canon_root = Path(ctx.canonical_root)

    if ctx.in_agent_tree and ctx.set_name:
        ensure_prepush_deps(wt_root)
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

        # CRITICAL: Switch working directory out of `~/.w0m/work/<set>/w0m` to `canonical_root`
        # BEFORE removing the agent tree so subsequent subprocesses never fail with dead `getcwd`.
        os.chdir(str(canon_root))

        ff_targets = [rel_path for rel_path, _ in _discover_estate_repos(canon_root)]
        ff_outcomes = fast_forward_canonical_checkout(canon_root, ff_targets)

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
            "treeRemoved": removed,
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
    return {
        "mode": "canonical_direct_push",
        "pushed": pushed,
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
    ap.add_argument("--allow-no-ticket", action="store_true", help="Allow wrap-up when zero tickets are targeted")
    ap.add_argument("--json", action="store_true", help="Emit machine-readable JSON summary")
    return ap


def run_session_complete(argv: Sequence[str] | None = None) -> tuple[int, dict[str, Any]]:
    args = build_parser().parse_args(list(argv) if argv is not None else None)

    ctx = detect_session_context(
        set_override=args.set_name,
        conversation_override=args.conversation,
    )
    wt_root = Path(ctx.worktree_root)
    sdlc_config = load_sdlc_config(wt_root)

    explicit = [*args.tickets, *(args.extra_tickets or [])]
    targets = discover_target_tickets(
        wt_root,
        explicit_tickets=explicit,
        agent_id=ctx.agent_id,
        allow_empty=bool(args.allow_no_ticket),
    )

    renumbered: dict[str, str] = {}
    if ctx.in_agent_tree and not args.dry_run and not args.skip_land:
        wait_for_land_lock(Path(ctx.work_root) if ctx.work_root else None)
    if ctx.in_agent_tree and not args.no_auto_renumber and targets:
        targets, renumbered = maybe_renumber_colliding_tickets(
            wt_root,
            targets,
            dry_run=bool(args.dry_run),
        )
    if ctx.in_agent_tree and not args.dry_run and not args.skip_land:
        sync_worktree_onto_origin_beta(wt_root)

    ticket_results: list[dict[str, Any]] = []
    for tid in targets:
        res = normalize_ticket_file(
            wt_root / ".tasks" / f"{tid}.md",
            complete_acs=bool(args.complete_acs),
            no_lessons=bool(args.no_lessons),
            lesson_note=args.lesson_note,
            dry_run=bool(args.dry_run),
        )
        ticket_results.append(asdict(res))

    mirrored_reports = mirror_reports(
        wt_root,
        sdlc_config,
        targets,
        dry_run=bool(args.dry_run),
    )

    surfaces_info = harvest_and_refresh_surfaces(
        wt_root,
        set_name=ctx.set_name,
        dry_run=bool(args.dry_run),
    )

    if args.dry_run:
        summary = {
            "ok": True,
            "dryRun": True,
            "context": asdict(ctx),
            "targetTickets": targets,
            "renumberedTickets": renumbered,
            "normalizedTickets": ticket_results,
            "mirroredReports": mirrored_reports,
            "surfaces": surfaces_info,
            "configuredGates": list((sdlc_config.get("session_wrapup") or {}).get("verification_gates") or []),
        }
        return 0, summary

    gate_results: list[dict[str, Any]] = []
    if not args.skip_gates:
        gate_results = run_verification_gates(wt_root, sdlc_config, targets)

    primary_tid = targets[0] if targets else "T0"
    committed = commit_dirty_repos(
        wt_root,
        primary_ticket=primary_tid,
        commit_message=args.commit_message,
    )

    if not args.skip_gates and targets:
        gate_results.extend(run_post_commit_ticket_audits(wt_root, targets))

    land_info: dict[str, Any] = {"mode": "skipped"}
    finalize_info: dict[str, Any] = {"mode": "skipped"}
    if not args.skip_land:
        if ctx.in_agent_tree:
            wait_for_land_lock(Path(ctx.work_root) if ctx.work_root else None)
            extra_renumbered: dict[str, str] = {}
            if not args.no_auto_renumber and targets:
                targets, extra_renumbered = maybe_renumber_colliding_tickets(
                    wt_root,
                    targets,
                    dry_run=False,
                )
                renumbered.update(extra_renumbered)
            synced_late = sync_worktree_onto_origin_beta(wt_root)
            if extra_renumbered or synced_late:
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
                surfaces_info = harvest_and_refresh_surfaces(wt_root, set_name=ctx.set_name, dry_run=False)
                primary_tid = targets[0] if targets else "T0"
                committed = commit_dirty_repos(
                    wt_root,
                    primary_ticket=primary_tid,
                    commit_message=args.commit_message,
                )
                if not args.skip_gates and targets:
                    gate_results.extend(run_post_commit_ticket_audits(wt_root, targets))

        land_info = land_and_cleanup_tree(
            ctx,
            remove_tree=not bool(args.keep_tree),
        )
        finalize_info = archive_and_finalize_session(
            ctx,
            close_completed_others=bool(args.close_completed_others),
            close_self_when_settled=bool(args.close_self_when_settled),
            skip_final_state_check=bool(args.skip_gates),
        )

    summary = {
        "ok": True,
        "dryRun": False,
        "context": asdict(ctx),
        "targetTickets": targets,
        "renumberedTickets": renumbered,
        "normalizedTickets": ticket_results,
        "mirroredReports": mirrored_reports,
        "surfaces": surfaces_info,
        "verificationGates": gate_results,
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
