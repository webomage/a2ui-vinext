#!/usr/bin/env python3
"""Commit only explicitly named paths while preserving concurrent working-tree and index state (T531 AC1).

Why this exists:
  `git commit -m <msg> -- <paths>` creates a temporary index for the commit, so when a
  pre-commit formatter (`oxfmt`, `ruff`, etc.) modifies a target file and runs `git add <file>`,
  Git restores the pre-hook `.git/index` afterward and leaves the file dirty (`MM <file>`).
  Conversely, `git add <paths> && git commit -m <msg>` sweeps in any other files already staged
  in `.git/index` by a concurrent agent or developer.

How `commit_by_path.py` works:
  1. Snapshots all non-target `.git/index` entries (`git ls-files --stage -z`) and non-target
     working-tree file bytes.
  2. Resets `.git/index` to `HEAD` and stages ONLY the requested `<paths>`.
  3. Runs `git commit -m <msg>` against the real `.git/index`, so pre-commit hooks see only
     `<paths>` in `git diff --cached` and any `git add` inside hooks updates the committed tree
     cleanly without leaving `MM` residue.
  4. Restores all non-target staged index entries and verifies/restores non-target working-tree
     bytes in `finally`.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence


class CommitByPathError(RuntimeError):
    """Raised when path-scoped commit validation or execution fails."""


def _git(
    repo_dir: Path,
    args: Sequence[str],
    *,
    check: bool = True,
    input_bytes: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(repo_dir),
        input=input_bytes,
        capture_output=True,
         check=False,
    )
    if check and proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace").strip()
        stdout = proc.stdout.decode("utf-8", errors="replace").strip()
        detail = stderr or stdout or f"exit {proc.returncode}"
        raise CommitByPathError(f"git {' '.join(args)} failed in {repo_dir}: {detail}")
    return proc


def _resolve_git_root(start: Path) -> Path:
    probe = start if start.is_dir() else start.parent
    proc = _git(probe, ["rev-parse", "--show-toplevel"])
    return Path(proc.stdout.decode("utf-8").strip()).resolve()


def _resolve_git_dir(repo_dir: Path) -> Path:
    proc = _git(repo_dir, ["rev-parse", "--git-dir"])
    raw = Path(proc.stdout.decode("utf-8").strip())
    return (repo_dir / raw).resolve() if not raw.is_absolute() else raw.resolve()


def _has_head(repo_dir: Path) -> bool:
    proc = _git(repo_dir, ["rev-parse", "--verify", "HEAD"], check=False)
    return proc.returncode == 0


def _read_stage_entries(repo_dir: Path) -> dict[str, tuple[str, str, str]]:
    """Return {rel_path: (mode, sha, stage)} from `git ls-files --stage -z`."""
    proc = _git(repo_dir, ["ls-files", "--stage", "-z"])
    entries: dict[str, tuple[str, str, str]] = {}
    for record in proc.stdout.split(b"\0"):
        if not record:
            continue
        meta_bytes, path_bytes = record.split(b"\t", 1)
        mode, sha, stage = meta_bytes.decode("utf-8").split(" ")
        rel_path = path_bytes.decode("utf-8")
        entries[rel_path] = (mode, sha, stage)
    return entries


def _read_head_paths(repo_dir: Path) -> set[str]:
    if not _has_head(repo_dir):
        return set()
    proc = _git(repo_dir, ["ls-tree", "-r", "--name-only", "-z", "HEAD"])
    return {
        p.decode("utf-8")
        for p in proc.stdout.split(b"\0")
        if p
    }


def _is_target_path(rel_path: str, target_rels: Sequence[str]) -> bool:
    for target in target_rels:
        if target in ("", "."):
            return True
        if rel_path == target or rel_path.startswith(target.rstrip("/") + "/"):
            return True
    return False


def _normalize_target_paths(repo_dir: Path, raw_paths: Sequence[str | Path], cwd: Path) -> list[str]:
    normalized: list[str] = []
    for raw in raw_paths:
        p = Path(raw)
        abs_p = (cwd / p) if not p.is_absolute() else p
        try:
            rel = abs_p.resolve(strict=False).relative_to(repo_dir.resolve())
        except ValueError:
            # Also allow already repo-relative paths when invoked with --repo
            rel = Path(os.path.normpath(str(p)))
            if str(rel).startswith(".."):
                raise CommitByPathError(
                    f"path '{raw}' is outside repository root '{repo_dir}'"
                ) from None
        rel_str = rel.as_posix()
        if rel_str not in normalized:
            normalized.append(rel_str)
    if not normalized:
        raise CommitByPathError("at least one path is required")
    return normalized


def _snapshot_non_target_worktree(
    repo_dir: Path,
    target_rels: Sequence[str],
) -> dict[str, bytes | None]:
    """Snapshot bytes of all non-target dirty/untracked files so hooks cannot corrupt them."""
    proc = _git(repo_dir, ["status", "--porcelain=v1", "-z", "--untracked-files=all"])
    snapshots: dict[str, bytes | None] = {}
    records = proc.stdout.split(b"\0")
    i = 0
    while i < len(records):
        rec = records[i]
        i += 1
        if not rec or len(rec) < 4:
            continue
        xy = rec[:2].decode("utf-8", errors="replace")
        rel_path = rec[3:].decode("utf-8", errors="replace")
        PathsToCheck = [rel_path]
        if "R" in xy or "C" in xy:
            if i < len(records) and records[i]:
                PathsToCheck.append(records[i].decode("utf-8", errors="replace"))
                i += 1
        for candidate in PathsToCheck:
            if _is_target_path(candidate, target_rels):
                continue
            abs_file = repo_dir / candidate
            if abs_file.is_file() or abs_file.is_symlink():
                try:
                    snapshots[candidate] = abs_file.read_bytes()
                except OSError:
                    pass
            elif not abs_file.exists():
                snapshots[candidate] = None
    return snapshots


def commit_by_path(
    repo_dir: Path,
    message: str,
    paths: Sequence[str | Path],
    *,
    cwd: Path | None = None,
) -> str:
    """Stage and commit only `paths` in `repo_dir`, preserving all other index and worktree state.

    Returns the new commit SHA.
    """
    if not message or not message.strip():
        raise CommitByPathError("commit message must not be empty")

    repo_dir = _resolve_git_root(Path(repo_dir))
    effective_cwd = Path(cwd).resolve() if cwd is not None else repo_dir
    target_rels = _normalize_target_paths(repo_dir, paths, effective_cwd)

    git_dir = _resolve_git_dir(repo_dir)
    index_file = git_dir / "index"
    saved_index_bytes = index_file.read_bytes() if index_file.is_file() else None
    saved_stage = _read_stage_entries(repo_dir)
    head_paths = _read_head_paths(repo_dir)
    has_head = _has_head(repo_dir)
    worktree_snapshots = _snapshot_non_target_worktree(repo_dir, target_rels)

    commit_succeeded = False
    try:
        # 1. Reset index to HEAD (or empty if unborn) so non-target staged changes are excluded.
        if has_head:
            _git(repo_dir, ["read-tree", "HEAD"])
        else:
            _git(repo_dir, ["rm", "-r", "--cached", "-q", "--ignore-unmatch", "."])

        # 2. Stage only target paths.
        _git(repo_dir, ["add", "-A", "--", *target_rels])

        # 3. Verify that target paths produced staged changes relative to HEAD.
        if has_head:
            diff_proc = _git(repo_dir, ["diff", "--cached", "--quiet"], check=False)
            if diff_proc.returncode == 0:
                raise CommitByPathError(
                    f"nothing to commit for paths: {', '.join(target_rels)}"
                )
        else:
            if not _read_stage_entries(repo_dir):
                raise CommitByPathError(
                    f"nothing to commit for paths: {', '.join(target_rels)}"
                )

        # 4. Run `git commit -m <message>` on the real index so pre-commit formatters (`oxfmt`)
        #    that run `git add <target>` update the committed index directly.
        _git(repo_dir, ["commit", "-m", message])
        commit_succeeded = True
    finally:
        if not commit_succeeded:
            if saved_index_bytes is not None:
                index_file.write_bytes(saved_index_bytes)
            elif index_file.exists():
                index_file.unlink()
        else:
            # Re-apply non-target index state from saved_stage.
            to_update: list[bytes] = []
            to_remove: list[str] = []

            for rel_path, (mode, sha, stage) in saved_stage.items():
                if _is_target_path(rel_path, target_rels):
                    continue
                to_update.append(f"{mode} {sha} {stage}\t{rel_path}\0".encode("utf-8"))

            for rel_path in head_paths:
                if _is_target_path(rel_path, target_rels):
                    continue
                if rel_path not in saved_stage:
                    to_remove.append(rel_path)

            if to_update:
                _git(
                    repo_dir,
                    ["update-index", "-z", "--index-info"],
                    input_bytes=b"".join(to_update),
                )
            if to_remove:
                _git(
                    repo_dir,
                    ["update-index", "--force-remove", "--", *to_remove],
                )

        # Verify / restore non-target working-tree file bytes if a hook touched them.
        for rel_path, expected_bytes in worktree_snapshots.items():
            abs_file = repo_dir / rel_path
            if expected_bytes is None:
                if abs_file.exists():
                    abs_file.unlink()
            else:
                current_bytes = abs_file.read_bytes() if abs_file.is_file() else None
                if current_bytes is None or (
                    hashlib.sha256(current_bytes).digest()
                    != hashlib.sha256(expected_bytes).digest()
                ):
                    abs_file.parent.mkdir(parents=True, exist_ok=True)
                    abs_file.write_bytes(expected_bytes)

    sha_proc = _git(repo_dir, ["rev-parse", "HEAD"])
    return sha_proc.stdout.decode("utf-8").strip()


def _detect_repo_and_paths(
    explicit_repo: str | None,
    raw_paths: Sequence[str],
    cwd: Path,
) -> tuple[Path, Path, list[str]]:
    if explicit_repo:
        repo_dir = _resolve_git_root((cwd / explicit_repo).resolve())
        return repo_dir, repo_dir, list(raw_paths)

    if not raw_paths:
        raise CommitByPathError("at least one path is required")

    # Determine enclosing git repo from the first path so running from estate root
    # with `w0m-web/foo.py` or `.tasks/T1.md` automatically targets the right repo.
    first_abs = (cwd / raw_paths[0]).resolve(strict=False)
    probe = first_abs if first_abs.is_dir() else first_abs.parent
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    repo_dir = _resolve_git_root(probe)
    return repo_dir, cwd, list(raw_paths)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Stage and commit only the named paths while preserving concurrent worktree/index state."
    )
    parser.add_argument(
        "-m",
        "--message",
        required=True,
        help="Commit message",
    )
    parser.add_argument(
        "--repo",
        default=None,
        help="Optional repository root path (auto-detected from paths if omitted)",
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="File or directory paths to stage and commit",
    )
    args = parser.parse_args(argv)

    cwd = Path.cwd()
    try:
        repo_dir, effective_cwd, rel_paths = _detect_repo_and_paths(
            args.repo,
            args.paths,
            cwd,
        )
        sha = commit_by_path(repo_dir, args.message, rel_paths, cwd=effective_cwd)
    except CommitByPathError as exc:
        print(f"commit-by-path: {exc}", file=sys.stderr)
        return 1

    print(f"committed {sha[:12]} in {repo_dir.name} ({', '.join(rel_paths)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
