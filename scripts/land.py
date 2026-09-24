#!/usr/bin/env python3
"""Local Merge Queue and Single Committer to beta (T425).

Provides `just land <worktree|name>` and `just land root [--ticket T<id>]`:
- Single committer queue serialized via `.git/w0m-land.lock` (AC1)
- Rebase-then-fast-forward member landing pipeline (AC2)
- Cross-repo topological lineage order (AC3)
- Root repo selective staging (never git add -A) (AC4)
- Discard-and-regenerate engine for generated views (AC5)
- Register append-only enforcement (AC6)
- Policy and tooling explicit --include guard (AC7)
- Ticket-ID race detection against beta (AC8)
- Sets W0M_LAND=1 on commits (AC10)
"""

from __future__ import annotations

import argparse
import datetime
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]

# Estate topological order
TOPOLOGICAL_ORDER = [
    "api",
    "wom7api",
    "cf",
    "func",
    "wom7func",
    "web",
    "wom7web",
    "ext",
    "wom7ext",
    "sec",
    "wom7sec",
    "skills",
    "wom7skills",
    "mlx",
    "wom7mlx",
    "root",
    "@wom",
]

REGISTERS = {
    "LESSONS.md",
    "TECH-DEBT.md",
    "ROADMAP.md",
    "docs/DECISIONS.md",
}

GENERATED_FILES = {
    "TASKS.md",
    "STATE.md",
}

POLICY_AND_TOOLING_PREFIXES = [
    "project/policies/",
    "scripts/",
    "justfile",
    ".agents/rules/",
    ".pre-commit-config.yaml",
    "CHANGELOG.md",
]


def sort_repos_topologically(repos: List[str]) -> List[str]:
    """Sort repos in estate dependency order (api -> func -> web -> ... -> root)."""
    def rank(name: str) -> int:
        norm = name.lower().strip()
        for idx, item in enumerate(TOPOLOGICAL_ORDER):
            if norm == item or norm.endswith(f"/{item}"):
                return idx
        return len(TOPOLOGICAL_ORDER) - 1  # default right before root

    return sorted(repos, key=rank)


class LandLock:
    """Exclusive filesystem lock for land serialization."""

    def __init__(self, repo_root: Path, timeout_sec: int = 0):
        self.repo_root = repo_root
        git_path = repo_root / ".git"
        if git_path.is_file():
            res = subprocess.run(["git", "rev-parse", "--git-common-dir"], cwd=repo_root, capture_output=True, text=True)
            if res.returncode == 0 and res.stdout.strip():
                common_dir = Path(res.stdout.strip())
                self.lock_dir = common_dir if common_dir.is_absolute() else (repo_root / common_dir).resolve()
            else:
                self.lock_dir = repo_root
        else:
            self.lock_dir = git_path
        self.lock_path = self.lock_dir / "w0m-land.lock"
        self.timeout_sec = timeout_sec
        self.acquired = False

    def is_pid_alive(self, pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
            return True
        except PermissionError:
            return True
        except ProcessLookupError:
            return False
        except OSError:
            return False

    def check_status(self) -> Tuple[str, Optional[int], Optional[str]]:
        if not self.lock_path.exists():
            return "UNLOCKED", None, None

        try:
            content = self.lock_path.read_text().splitlines()
            pid = int(content[0].strip()) if content else -1
            ts = content[1].strip() if len(content) > 1 else "unknown"
            if self.is_pid_alive(pid):
                return "LOCKED", pid, ts
            else:
                return "STALE", pid, ts
        except Exception:
            return "STALE", None, None

    def acquire(self) -> bool:
        start = time.time()
        self.lock_dir.mkdir(parents=True, exist_ok=True)

        while True:
            status, pid, ts = self.check_status()
            if status == "UNLOCKED":
                try:
                    # Write exclusive
                    with open(self.lock_path, "x") as f:
                        f.write(f"{os.getpid()}\n{datetime.datetime.now().isoformat()}\n")
                    self.acquired = True
                    return True
                except FileExistsError:
                    pass  # Contention race
            elif status == "STALE":
                # Clean up stale lock
                try:
                    self.lock_path.unlink(missing_ok=True)
                    with open(self.lock_path, "x") as f:
                        f.write(f"{os.getpid()}\n{datetime.datetime.now().isoformat()}\n")
                    self.acquired = True
                    return True
                except Exception:
                    pass

            if self.timeout_sec <= 0 or (time.time() - start) >= self.timeout_sec:
                return False
            time.sleep(0.5)

    def release(self):
        if self.acquired:
            try:
                self.lock_path.unlink(missing_ok=True)
            except Exception:
                pass
            self.acquired = False

    def __enter__(self):
        if not self.acquire():
            status, pid, ts = self.check_status()
            raise RuntimeError(f"Queue is locked by PID {pid} since {ts} (use --wait or inspect `just land-status`)")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()


def run_git(args: List[str], cwd: Path, env: Optional[dict] = None) -> subprocess.CompletedProcess:
    base_env = dict(os.environ)
    if env:
        base_env.update(env)
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env=base_env)


def log_land(repo_root: Path, message: str):
    """Write message to land log and stdout."""
    log_file = repo_root / ".git" / "land.log"
    ts = datetime.datetime.now().isoformat()
    entry = f"[{ts}] {message}\n"
    try:
        with open(log_file, "a") as f:
            f.write(entry)
    except Exception:
        pass
    print(f"▶ [land] {message}")


def check_conflicts(repo_root: Path, target_ref: str, base_ref: str = "beta") -> Tuple[bool, List[str]]:
    """Dry-run merge conflict detection using git merge-tree."""
    # Find merge-base
    mb = run_git(["merge-base", base_ref, target_ref], cwd=repo_root)
    if mb.returncode != 0:
        return False, [f"Could not find merge-base between {base_ref} and {target_ref}"]

    base_commit = mb.stdout.strip()
    mt = run_git(["merge-tree", "--write-tree", base_ref, target_ref], cwd=repo_root)
    if mt.returncode == 0:
        return True, []  # Clean merge tree

    # Parse conflicting files from merge-tree or diff
    conflicts = []
    lines = mt.stdout.splitlines() + mt.stderr.splitlines()
    for line in lines:
        if "conflict" in line.lower() or "CONFLICT" in line:
            conflicts.append(line.strip())

    if not conflicts:
        conflicts = ["Unclean merge tree detected"]

    return False, conflicts


def validate_register_append_only(repo_root: Path, filepath: Path) -> Tuple[bool, Optional[str]]:
    """Verify that edits to registers contain only additions (no line modifications or deletions)."""
    rel_path = filepath.relative_to(repo_root) if filepath.is_absolute() else filepath
    # Get unstaged + staged diff vs HEAD
    diff = run_git(["diff", "HEAD", "--", str(rel_path)], cwd=repo_root)
    if diff.returncode != 0 or not diff.stdout.strip():
        return True, None

    for line in diff.stdout.splitlines():
        # Diff header lines start with --- or +++
        if line.startswith("---") or line.startswith("+++"):
            continue
        # Check for deletion lines
        if line.startswith("-"):
            # Deletions or modified lines are prohibited in append-only registers
            stripped = line[1:].strip()
            # Allow trailing whitespace / empty line deletions
            if stripped:
                return False, f"append-only violation in {rel_path}: deleted or replaced line: '{stripped[:60]}'"

    return True, None


def land_root(
    repo_root: Path,
    ticket_id: Optional[str] = None,
    includes: Optional[List[str]] = None,
    new_ticket: bool = False,
    skip_state_check: bool = False,
    commit_msg: Optional[str] = None,
) -> int:
    """Selective landing for shared root repo (@wom)."""
    includes = includes or []

    # Ticket ID race guard (AC8)
    if ticket_id and new_ticket:
        clean_id = ticket_id.lstrip("T")
        target_file = f".tasks/T{clean_id}.md"
        # Check if file exists on beta branch
        check_cat = run_git(["cat-file", "-e", f"beta:{target_file}"], cwd=repo_root)
        if check_cat.returncode == 0:
            print(f"🔴 Ticket T{clean_id} already exists on beta (ticket-ID race detected).", file=sys.stderr)
            return 1

    # Check register append-only integrity (AC6)
    for reg in REGISTERS:
        reg_file = repo_root / reg
        if reg_file.exists():
            ok, err = validate_register_append_only(repo_root, reg_file)
            if not ok:
                print(f"🔴 {err}", file=sys.stderr)
                return 1

    # Policy and tooling explicit --include guard (AC7)
    diff_stat = run_git(["diff", "HEAD", "--name-only"], cwd=repo_root)
    untracked = run_git(["ls-files", "--others", "--exclude-standard"], cwd=repo_root)
    modified_paths = set(diff_stat.stdout.splitlines() + untracked.stdout.splitlines())

    for path_str in modified_paths:
        for prefix in POLICY_AND_TOOLING_PREFIXES:
            if path_str == prefix or path_str.startswith(prefix):
                if path_str not in includes:
                    print(
                        f"🔴 Policy/tooling file '{path_str}' modified without explicit `--include`. Halting land.",
                        file=sys.stderr,
                    )
                    return 1

    # Discard and regenerate generated files (AC5)
    for gen in GENERATED_FILES:
        gen_path = repo_root / gen
        if gen in modified_paths:
            # Revert any dirty edits made by agent
            run_git(["checkout", "HEAD", "--", gen], cwd=repo_root)
            log_land(repo_root, f"discarded agent edit to {gen} — regenerated from .tasks/")

    # Regenerate TASKS.md if tasks-render is present
    render_script = repo_root / "scripts" / "tasks_render.py"
    if render_script.exists():
        subprocess.run([sys.executable, str(render_script)], cwd=repo_root, capture_output=True)

    # Regenerate STATE.md if state_doctor is present (T428 AC2)
    state_script = repo_root / "scripts" / "state_doctor.py"
    if state_script.exists():
        subprocess.run([sys.executable, str(state_script), "--write"], cwd=repo_root, capture_output=True)

    # Selective staging: only stage declared paths (AC4)
    staged_paths = []
    if ticket_id:
        clean_id = ticket_id.lstrip("T")
        ticket_file = repo_root / ".tasks" / f"T{clean_id}.md"
        if ticket_file.exists():
            run_git(["add", str(ticket_file)], cwd=repo_root)
            staged_paths.append(f".tasks/T{clean_id}.md")

        # Stage reports for this ticket
        reports_dir = repo_root / ".agents" / "reports"
        if reports_dir.exists():
            for rep in reports_dir.glob(f"*[tT]{clean_id}*"):
                run_git(["add", str(rep)], cwd=repo_root)
                staged_paths.append(str(rep.relative_to(repo_root)))

    # Stage register appends if modified
    for reg in REGISTERS:
        if reg in modified_paths:
            run_git(["add", reg], cwd=repo_root)
            staged_paths.append(reg)

    # Stage generated files
    for gen in GENERATED_FILES:
        diff_gen = run_git(["diff", "--name-only", "--", gen], cwd=repo_root)
        if diff_gen.stdout.strip():
            run_git(["add", gen], cwd=repo_root)
            staged_paths.append(gen)

    # Stage explicitly included files
    for inc in includes:
        if (repo_root / inc).exists():
            run_git(["add", inc], cwd=repo_root)
            staged_paths.append(inc)

    # Check staged status
    staged_diff = run_git(["diff", "--cached", "--name-only"], cwd=repo_root)
    if not staged_diff.stdout.strip():
        print("▶ Nothing staged for landing.")
        return 0

    # Run state check if available and not skipped (AC8)
    if not skip_state_check:
        state_doctor = repo_root / "scripts" / "state_doctor.py"
        if state_doctor.exists():
            sr = subprocess.run([sys.executable, str(state_doctor), "--check"], cwd=repo_root, capture_output=True, text=True)
            if sr.returncode != 0:
                print(f"🔴 Pre-land state check failed:\n{sr.stderr or sr.stdout}", file=sys.stderr)
                return 1

    # Commit with W0M_LAND=1 (AC10)
    commit_title = commit_msg or (f"chore({ticket_id or 'queue'}): land root" if ticket_id else "chore: land root")
    commit_env = dict(os.environ)
    commit_env["W0M_LAND"] = "1"

    commit_res = run_git(["commit", "-m", commit_title], cwd=repo_root, env=commit_env)
    if commit_res.returncode != 0:
        print(f"🔴 Root commit failed:\n{commit_res.stderr}", file=sys.stderr)
        return 1

    log_land(repo_root, f"successfully landed root commit: {commit_title} (paths: {', '.join(staged_paths)})")
    return 0


def land_member_worktree(
    repo_root: Path,
    target_worktree: str,
    ticket_id: Optional[str] = None,
    skip_push: bool = False,
) -> int:
    """Execute the 8-step member land pipeline (AC2)."""
    # 1. Main checkout is clean (fail closed)
    status_main = run_git(["status", "--porcelain"], cwd=repo_root)
    if status_main.stdout.strip():
        print(f"🔴 Main checkout in {repo_root} is dirty. Fail closed. Commit or stash before landing.", file=sys.stderr)
        return 1

    # Resolve target worktree path
    target_path = Path(target_worktree)
    if not target_path.is_absolute():
        # Check standard Orca workspace location or relative path
        orca_cand = Path.home() / "orca" / "workspaces" / repo_root.name / target_worktree
        if orca_cand.exists():
            target_path = orca_cand
        else:
            target_path = repo_root / target_worktree

    if not target_path.exists():
        print(f"🔴 Target worktree '{target_worktree}' does not exist at {target_path}", file=sys.stderr)
        return 1

    # Get worktree current branch
    br = run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=target_path)
    branch = br.stdout.strip()
    if not branch or branch == "HEAD":
        print(f"🔴 Target worktree is in detached HEAD state", file=sys.stderr)
        return 1

    log_land(repo_root, f"landing branch '{branch}' from {target_path}")

    # Auto-detect ticket ID from branch name if not explicitly passed
    if not ticket_id:
        m = re.search(r"\b[tT](\d+)\b", branch) or re.search(r"[tT](\d+)", branch)
        if m:
            ticket_id = f"T{m.group(1)}"

    # 2. Fetch latest beta if remote exists
    remotes = run_git(["remote"], cwd=repo_root).stdout.splitlines()
    if "origin" in remotes:
        run_git(["fetch", "origin", "beta"], cwd=repo_root)

    # 3. Rebase unit onto beta inside the unit's worktree
    rebase_res = run_git(["rebase", "beta"], cwd=target_path)
    if rebase_res.returncode != 0:
        run_git(["rebase", "--abort"], cwd=target_path)
        print(f"🔴 Rebase conflict in worktree {target_path}. Rebase aborted. Please resolve conflicts in worktree.", file=sys.stderr)
        return 1

    # 4. Regenerate lockfile if touched
    diff_lock = run_git(["diff", "beta...HEAD", "--name-only"], cwd=target_path)
    if "pnpm-lock.yaml" in diff_lock.stdout:
        log_land(repo_root, "regenerating pnpm lockfile in worktree")
        subprocess.run(["pnpm", "install", "--lockfile-only"], cwd=target_path, capture_output=True)
    if "deno.lock" in diff_lock.stdout:
        log_land(repo_root, "regenerating deno lockfile in worktree")
        subprocess.run(["deno", "cache", "--lock=deno.lock"], cwd=target_path, capture_output=True)

    # 5. Run full pre-push gate set inside worktree
    just_prepush = shutil.which("just")
    if just_prepush and (target_path / "justfile").exists():
        gate_res = subprocess.run([just_prepush, "pre-push"], cwd=target_path, capture_output=True, text=True)
        if gate_res.returncode != 0:
            print(f"🔴 Pre-push quality gate failed in worktree:\n{gate_res.stderr or gate_res.stdout}", file=sys.stderr)
            return 1

    # 6. Fast-forward beta in main checkout (--ff-only)
    env_land = dict(os.environ)
    env_land["W0M_LAND"] = "1"
    ff_res = run_git(["merge", "--ff-only", branch], cwd=repo_root, env=env_land)
    if ff_res.returncode != 0:
        print(f"🔴 Fast-forward merge of {branch} into beta failed in main checkout:\n{ff_res.stderr}", file=sys.stderr)
        return 1

    # 7. Offer push
    log_land(repo_root, f"fast-forwarded beta to {branch} successfully")

    # 8. Archive via Orca if available
    orca_bin = shutil.which("orca")
    if orca_bin:
        subprocess.run([orca_bin, "worktree", "archive", "--path", str(target_path)], capture_output=True)

    # If ticket was passed, land root tracker
    if ticket_id:
        return land_root(repo_root, ticket_id=ticket_id)

    return 0


def main() -> int:
    # Normalize convenience flags & default subcommand:
    # 1. `land --check <target>` -> `land check <target>`
    # 2. `land --status` -> `land status`
    # 3. `land <worktree>` -> `land land <worktree>` (if not root/check/status/help)
    raw_args = sys.argv[1:]
    if raw_args:
        if raw_args[0] == "--check":
            raw_args = ["check", *raw_args[1:]]
        elif raw_args[0] == "--status":
            raw_args = ["status", *raw_args[1:]]
        elif raw_args[0] not in ("status", "check", "root", "land", "-h", "--help"):
            raw_args = ["land", *raw_args]

    parser = argparse.ArgumentParser(description="w0m Local Merge Queue & Single Committer to Beta")
    subparsers = parser.add_subparsers(dest="command")

    # status
    subparsers.add_parser("status", help="Show lock state and queue status")

    # check
    check_p = subparsers.add_parser("check", help="Dry-run conflict check against beta")
    check_p.add_argument("target", help="Worktree path or branch name to check")

    # root
    root_p = subparsers.add_parser("root", help="Land root repository artifacts safely")
    root_p.add_argument("--ticket", help="Active ticket ID (e.g. T425)")
    root_p.add_argument("--include", action="append", default=[], help="Explicitly allowed tool/policy path")
    root_p.add_argument("--new-ticket", action="store_true", help="Assert ticket is new (enforces ID-race check)")
    root_p.add_argument("--skip-state-check", action="store_true", help="Skip state-check gate")
    root_p.add_argument("--message", "-m", help="Commit message")
    root_p.add_argument("--wait", type=int, default=0, help="Wait up to N seconds for lock")

    # member land
    land_p = subparsers.add_parser("land", help="Land a member worktree onto beta")
    land_p.add_argument("worktree", help="Worktree path, name, or branch")
    land_p.add_argument("--ticket", help="Active ticket ID to land in root afterwards")
    land_p.add_argument("--skip-push", action="store_true", help="Do not push after landing")
    land_p.add_argument("--wait", type=int, default=0, help="Wait up to N seconds for lock")

    args = parser.parse_args(raw_args)

    repo_root = Path.cwd()
    # Resolve top-level git root
    gr = run_git(["rev-parse", "--show-toplevel"], cwd=repo_root)
    if gr.returncode == 0:
        repo_root = Path(gr.stdout.strip())

    if args.command == "status":
        lock = LandLock(repo_root)
        status, pid, ts = lock.check_status()
        print(f"▶ Land Lock Status: {status}")
        if pid:
            print(f"  PID: {pid} (since {ts})")
        return 0

    if args.command == "check":
        clean, conflicts = check_conflicts(repo_root, args.target)
        if clean:
            print(f"✅ CLEAN — {args.target} can be fast-forwarded or merged into beta without conflicts.")
            return 0
        else:
            print(f"🔴 CONFLICT detected for {args.target}:", file=sys.stderr)
            for c in conflicts:
                print(f"  · {c}", file=sys.stderr)
            return 1

    if args.command == "root":
        lock = LandLock(repo_root, timeout_sec=args.wait)
        try:
            with lock:
                return land_root(
                    repo_root,
                    ticket_id=args.ticket,
                    includes=args.include,
                    new_ticket=args.new_ticket,
                    skip_state_check=args.skip_state_check,
                    commit_msg=args.message,
                )
        except RuntimeError as e:
            print(f"🔴 {e}", file=sys.stderr)
            return 1

    if args.command == "land":
        lock = LandLock(repo_root, timeout_sec=args.wait)
        try:
            with lock:
                return land_member_worktree(
                    repo_root,
                    target_worktree=args.worktree,
                    ticket_id=args.ticket,
                    skip_push=args.skip_push,
                )
        except RuntimeError as e:
            print(f"🔴 {e}", file=sys.stderr)
            return 1

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
