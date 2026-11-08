#!/usr/bin/env python3
"""Atomically allocate the next T-id from origin/beta + .tasks/ and create .tasks/T<N>.md (T531 AC2).

Why this exists:
  Scanning TASKS.md in memory to pick the next ticket ID races when two agents create tickets
  concurrently, and hand-editing a central TASKS.md row at creation time conflicts on rebase.

How `ticket_new.py` works:
  1. Queries `git ls-tree origin/beta .tasks/` (when available) and local `.tasks/T*.md` to
     determine the current maximum ticket number.
  2. Atomically claims `.tasks/T<N>.md` using `os.open(..., os.O_CREAT | os.O_EXCL | os.O_WRONLY)`,
     retrying with `N + 1` on `FileExistsError` so concurrent callers never collide.
  3. Populates the ticket from `project/templates/ticket.md` (or embedded canonical fallback)
     with valid frontmatter and sections.
  4. Regenerates `TASKS.md` from `.tasks/T*.md` via `scripts/tasks_render.py` in the same step.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import os
import re
import subprocess
import sys
import threading
from collections.abc import Iterator, Sequence
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import tasks_render  # noqa: E402

TICKET_FILE_RE = re.compile(r"^T(\d+)\.md$")
_INPROC_SEQ_LOCK = threading.Lock()


def _git_common_dir(repo_dir: Path) -> Path | None:
    proc = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=str(repo_dir),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    cand = Path(proc.stdout.strip()).resolve()
    return cand if cand.is_dir() else None


def _linked_worktree_ticket_ids(repo_dir: Path) -> set[int]:
    proc = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=str(repo_dir),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return set()
    ids: set[int] = set()
    for line in proc.stdout.splitlines():
        if line.startswith("worktree "):
            wt_path = Path(line[len("worktree ") :].strip())
            ids |= _local_ticket_ids(wt_path / ".tasks")
    return ids


@contextlib.contextmanager
def _ticket_seq_lock(repo_dir: Path) -> Iterator[None]:
    common_dir = _git_common_dir(repo_dir)
    with _INPROC_SEQ_LOCK:
        if common_dir is None:
            yield
            return
        lock_path = common_dir / "w0m-ticket-seq.lock"
        fh = lock_path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            with contextlib.suppress(OSError):
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            fh.close()


def _remote_ticket_ids(repo_dir: Path, remote_ref: str = "origin/beta") -> set[int]:
    proc = subprocess.run(
        ["git", "ls-tree", "--name-only", remote_ref, ".tasks/"],
        cwd=str(repo_dir),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return set()
    ids: set[int] = set()
    for line in proc.stdout.splitlines():
        name = Path(line.strip()).name
        m = TICKET_FILE_RE.match(name)
        if m:
            ids.add(int(m.group(1)))
    return ids


def _local_ticket_ids(tickets_dir: Path) -> set[int]:
    if not tickets_dir.is_dir():
        return set()
    ids: set[int] = set()
    for p in tickets_dir.iterdir():
        m = TICKET_FILE_RE.match(p.name)
        if m:
            ids.add(int(m.group(1)))
    return ids


def _render_ticket_body(
    ticket_id: str,
    title: str,
    *,
    area: str = "sdlc",
    priority: str = "P2",
    epic: str = "sdlc-tooling",
    status: str = "backlog",
    why: str = "Describe the problem and why it matters.",
    ac: Sequence[str] | None = None,
    created: str | None = None,
) -> str:
    created_date = created or dt.date.today().isoformat()
    ac_items = list(ac) if ac else ["Define measurable acceptance criterion."]
    ac_lines = "\n".join(f"- [ ] **AC{i + 1}:** {item}" for i, item in enumerate(ac_items))
    ac_total = len(ac_items)
    safe_title = title.replace('"', '\\"')
    return (
        "---\n"
        f"id: {ticket_id}\n"
        f'title: "{safe_title}"\n'
        f"status: {status}\n"
        f"priority: {priority}\n"
        f"area: {area}\n"
        f"epic: {epic}\n"
        "owner: null\n"
        f"created: {created_date}\n"
        "spec: null\n"
        "blocked_by: []\n"
        "x_ac_done: 0\n"
        f"x_ac_total: {ac_total}\n"
        "x_ac_pct: 0\n"
        "---\n\n"
        f"# {ticket_id} — {title}\n\n"
        "## Why\n\n"
        f"{why}\n\n"
        "## Scope\n\n"
        "- **In:** TBD\n"
        "- **Out:** TBD\n\n"
        "## Acceptance Criteria\n\n"
        f"{ac_lines}\n\n"
        "## Verification\n\n"
        "```bash\n"
        "just state-check\n"
        "```\n\n"
        "## Status\n\n"
        f"- {created_date}: Ticket created via `just ticket-new`.\n\n"
        "## Links\n\n"
        "- Spec: `None`\n"
    )


def allocate_ticket(
    title: str,
    *,
    repo_dir: Path = ROOT_DIR,
    tickets_dir: Path | None = None,
    tasks_md_path: Path | None = None,
    area: str = "sdlc",
    priority: str = "P2",
    epic: str = "sdlc-tooling",
    status: str = "backlog",
    why: str = "Describe the problem and why it matters.",
    ac: Sequence[str] | None = None,
    created: str | None = None,
    render_tasks: bool = True,
    draft_slug: str | None = None,
) -> tuple[str, Path]:
    """Atomically allocate and write `.tasks/T<N>.md` (or `.tasks/DRAFT-<slug>.md` when `draft_slug` is set).

    Returns `(ticket_id, ticket_path)`.
    """
    if not title or not title.strip():
        raise ValueError("ticket title must not be empty")

    repo_dir = Path(repo_dir).resolve()
    t_dir = Path(tickets_dir).resolve() if tickets_dir is not None else (repo_dir / ".tasks")
    t_md = Path(tasks_md_path).resolve() if tasks_md_path is not None else (repo_dir / "TASKS.md")
    t_dir.mkdir(parents=True, exist_ok=True)

    if draft_slug:
        clean_slug = re.sub(r"[^A-Za-z0-9_-]+", "-", draft_slug.strip()).strip("-")
        if clean_slug.upper().startswith("DRAFT-"):
            clean_slug = clean_slug[6:]
        if not clean_slug:
            raise ValueError("draft_slug must contain alphanumeric characters")
        ticket_id = f"DRAFT-{clean_slug}"
        ticket_path = t_dir / f"{ticket_id}.md"
        content = _render_ticket_body(
            ticket_id,
            title.strip(),
            area=area,
            priority=priority,
            epic=epic,
            status=status,
            why=why,
            ac=ac,
            created=created,
        )
        ticket_path.write_text(content, encoding="utf-8")
        _auto_build_context_tree(repo_dir, ticket_id)
        return ticket_id, ticket_path

    with _ticket_seq_lock(repo_dir):
        known_ids = (
            _remote_ticket_ids(repo_dir)
            | _local_ticket_ids(t_dir)
            | _linked_worktree_ticket_ids(repo_dir)
        )
        next_num = (max(known_ids) + 1) if known_ids else 1

        while True:
            ticket_id = f"T{next_num}"
            ticket_path = t_dir / f"{ticket_id}.md"
            try:
                fd = os.open(
                    str(ticket_path),
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    0o644,
                )
            except FileExistsError:
                next_num += 1
                continue

            try:
                content = _render_ticket_body(
                    ticket_id,
                    title.strip(),
                    area=area,
                    priority=priority,
                    epic=epic,
                    status=status,
                    why=why,
                    ac=ac,
                    created=created,
                )
                os.write(fd, content.encode("utf-8"))
            finally:
                os.close(fd)
            break

    if render_tasks:
        tasks_render.render_tasks_md(
            tasks_dir=t_dir,
            output_path=t_md,
            base_tasks_md=t_md,
        )

    _auto_build_context_tree(repo_dir, ticket_id)
    return ticket_id, ticket_path


def _auto_build_context_tree(repo_dir: Path, ticket_id: str) -> None:
    """Best-effort Harness² ContextTree materialization (.w0m/context/<ticket_id>/) on ticket creation."""
    ct_script = repo_dir / "w0m-web" / "project" / "scripts" / "context_tree.py"
    if not ct_script.is_file():
        return
    with contextlib.suppress(Exception):
        subprocess.run(
            [sys.executable, str(ct_script), ticket_id],
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )


def _detect_worktree_draft_slug(repo_dir: Path) -> str | None:
    proc = subprocess.run(
        ["git", "symbolic-ref", "--short", "HEAD"],
        cwd=str(repo_dir),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode == 0:
        branch = proc.stdout.strip()
        if branch.startswith("agent/") and len(branch) > len("agent/"):
            return branch[len("agent/") :]
    return None


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Atomically allocate the next T-id (or create DRAFT-<slug> in a worktree) and create .tasks/ ticket."
    )
    parser.add_argument("title", help="Ticket title")
    parser.add_argument("--area", default="sdlc", help="Ticket area (default: sdlc)")
    parser.add_argument("--priority", default="P2", help="Ticket priority (default: P2)")
    parser.add_argument("--epic", default="sdlc-tooling", help="Epic slug (default: sdlc-tooling)")
    parser.add_argument("--status", default="backlog", help="Initial status (default: backlog)")
    parser.add_argument("--why", default="Describe the problem and why it matters.", help="Why section text")
    parser.add_argument("--ac", action="append", default=None, help="Acceptance criterion (repeatable)")
    parser.add_argument("--repo", default=str(ROOT_DIR), help="Root repository path")
    parser.add_argument("--no-render", action="store_true", help="Skip regenerating TASKS.md")
    parser.add_argument(
        "--draft",
        nargs="?",
        const="auto",
        default=None,
        help="Create a deferred worktree draft ticket (.tasks/DRAFT-<slug>.md) assigned a T<N> on session-complete offload",
    )
    parser.add_argument(
        "--immediate",
        action="store_true",
        help="Force immediate T<N> allocation even when inside an agent/<slug> worktree",
    )
    args = parser.parse_args(argv)

    repo_path = Path(args.repo).resolve()
    draft_slug: str | None = None
    if not args.immediate:
        if args.draft == "auto":
            draft_slug = _detect_worktree_draft_slug(repo_path) or "worktree"
        elif args.draft:
            draft_slug = args.draft
        else:
            draft_slug = _detect_worktree_draft_slug(repo_path)

    ticket_id, ticket_path = allocate_ticket(
        args.title,
        repo_dir=repo_path,
        area=args.area,
        priority=args.priority,
        epic=args.epic,
        status=args.status,
        why=args.why,
        ac=args.ac,
        render_tasks=not args.no_render and not draft_slug,
        draft_slug=draft_slug,
    )
    print(f"{ticket_id}\t{ticket_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
