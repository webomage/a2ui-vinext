#!/usr/bin/env python3
"""Intelligent Obsidian vault worktree guard for w0m deploys, preflight, and session landings (T653).

Guarantees that live Obsidian Desktop / Mobile activity inside engagement and root vaults
(`projects/<slug>/vault/**`, `.obsidian/**`, `**/.obsidian/**`) survives `just preflight`,
`just certify`, `just session-complete`, and `just deploy` / `just deploy-all` without:
  1. Triggering false-positive dirty-tree failures from Obsidian's EOF-newline/whitespace JSON rewrites
     or unstaged in-flight vault note edits, while keeping all runtime/code/staged checks fail-closed.
  2. Blocking `git merge --ff-only origin/beta` on canonical checkouts or corrupting `.obsidian/*.json`
     and open Markdown notes when upstream and local vault files both advance.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_VAULT_RE = re.compile(r"^projects/[^/]+/vault(?:/|$)")


@dataclass(frozen=True)
class RepoWorktreeClassification:
    noop_obsidian_json: list[str] = field(default_factory=list)
    live_vault_edits: list[str] = field(default_factory=list)
    blocking_dirty: list[str] = field(default_factory=list)

    @property
    def is_runtime_clean(self) -> bool:
        return len(self.blocking_dirty) == 0

    @property
    def has_vault_activity(self) -> bool:
        return bool(self.noop_obsidian_json or self.live_vault_edits)


@dataclass(frozen=True)
class VaultFastForwardResult:
    ok: bool
    status: str
    head_sha: str = ""
    healed_json: list[str] = field(default_factory=list)
    preserved_files: list[str] = field(default_factory=list)
    merged_files: list[str] = field(default_factory=list)
    conflict_files: list[str] = field(default_factory=list)


def _git_bytes(repo_dir: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    env = {
        **os.environ,
        "LC_ALL": "C",
        "GIT_TERMINAL_PROMPT": "0",
    }
    return subprocess.run(
        ["git", "-C", str(repo_dir), *args],
        capture_output=True,
        env=env,
        check=False,
    )


def _git_text(repo_dir: Path, *args: str) -> tuple[int, str]:
    proc = _git_bytes(repo_dir, *args)
    return proc.returncode, proc.stdout.decode("utf-8", errors="replace").strip()


def normalize_rel_path(raw_path: str) -> str:
    cleaned = raw_path.strip()
    if " -> " in cleaned:
        cleaned = cleaned.split(" -> ", 1)[1].strip()
    if cleaned.startswith('"') and cleaned.endswith('"') and len(cleaned) >= 2:
        cleaned = cleaned[1:-1]
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    return cleaned


def is_obsidian_config_json_path(rel_path: str) -> bool:
    norm = normalize_rel_path(rel_path)
    return ("/.obsidian/" in f"/{norm}") and norm.endswith(".json")


def is_obsidian_vault_path(rel_path: str) -> bool:
    """True when `rel_path` lives inside an Obsidian vault or `.obsidian/` metadata directory."""
    norm = normalize_rel_path(rel_path)
    if not norm:
        return False
    if norm == ".obsidian" or norm.startswith(".obsidian/") or "/.obsidian/" in f"/{norm}" or norm.endswith("/.obsidian"):
        return True
    return bool(PROJECT_VAULT_RE.match(norm))


def is_semantic_noop_obsidian_json(repo_dir: Path, rel_path: str, *, ref: str = "HEAD") -> bool:
    """True when unstaged `.obsidian/*.json` has identical JSON AST (or whitespace-only diff) vs `ref`."""
    norm = normalize_rel_path(rel_path)
    if not is_obsidian_config_json_path(norm):
        return False
    disk_path = repo_dir / norm
    if not disk_path.is_file():
        return False
    rc_staged, staged = _git_text(repo_dir, "diff", "--cached", "--name-only", "--", norm)
    if rc_staged != 0 or bool(staged):
        return False
    head_proc = _git_bytes(repo_dir, "show", f"{ref}:{norm}")
    if head_proc.returncode != 0:
        return False
    try:
        disk_bytes = disk_path.read_bytes()
    except OSError:
        return False
    if disk_bytes == head_proc.stdout:
        return True
    try:
        disk_obj: object = json.loads(disk_bytes.decode("utf-8"))
        head_obj: object = json.loads(head_proc.stdout.decode("utf-8"))
        if disk_obj == head_obj:
            return True
    except (UnicodeDecodeError, ValueError):
        pass
    rc_ws, ws_diff = _git_text(
        repo_dir, "diff", "--ignore-all-space", "--ignore-blank-lines", "--", norm
    )
    return rc_ws == 0 and ws_diff == ""


def inspect_repo_worktree(
    repo_dir: Path,
    *,
    include_untracked: bool = True,
) -> RepoWorktreeClassification:
    """Classify working-tree status lines without mutating disk (prevents Obsidian inotify loops)."""
    untracked_arg = "--untracked-files=all" if include_untracked else "--untracked-files=no"
    proc = _git_bytes(repo_dir, "status", "--porcelain", untracked_arg)
    if proc.returncode != 0:
        return RepoWorktreeClassification(blocking_dirty=["<git-status-failed>"])

    raw_lines = [
        ln for ln in proc.stdout.decode("utf-8", errors="replace").splitlines() if len(ln) >= 4
    ]
    noop_json: list[str] = []
    live_vault: list[str] = []
    blocking: list[str] = []

    for line in raw_lines:
        xy = line[:2]
        rel_path = normalize_rel_path(line[3:])
        x_stat, y_stat = xy[0], xy[1]

        # Any staged index modification or unmerged state is deliberate/blocking git work.
        if xy == "??":
            if is_obsidian_vault_path(rel_path):
                live_vault.append(rel_path)
            else:
                blocking.append(rel_path)
            continue

        if x_stat != " ":
            blocking.append(rel_path)
            continue

        # Unstaged working-tree change (` M`, ` D`, etc.)
        if y_stat == "M" and is_semantic_noop_obsidian_json(repo_dir, rel_path):
            noop_json.append(rel_path)
        elif is_obsidian_vault_path(rel_path):
            live_vault.append(rel_path)
        else:
            blocking.append(rel_path)

    return RepoWorktreeClassification(
        noop_obsidian_json=noop_json,
        live_vault_edits=live_vault,
        blocking_dirty=blocking,
    )


def heal_noop_obsidian_json(repo_dir: Path) -> list[str]:
    """Restore exact `HEAD` bytes on unstaged `.obsidian/*.json` files that have zero semantic JSON diff."""
    cls = inspect_repo_worktree(repo_dir, include_untracked=False)
    healed: list[str] = []
    for rel_path in cls.noop_obsidian_json:
        head_proc = _git_bytes(repo_dir, "show", f"HEAD:{rel_path}")
        if head_proc.returncode != 0:
            continue
        target = repo_dir / rel_path
        tmp = target.with_name(f".{target.name}.w0m-heal.tmp")
        try:
            tmp.write_bytes(head_proc.stdout)
            tmp.replace(target)
            healed.append(rel_path)
        except OSError:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
    return healed


def merge_obsidian_json_three_way(
    base_bytes: bytes | None,
    upstream_bytes: bytes,
    local_bytes: bytes,
) -> bytes | None:
    """Three-way key-level merge for `.obsidian/*.json` dicts so conflict markers never enter JSON."""
    try:
        upstream_obj: object = json.loads(upstream_bytes.decode("utf-8"))
        local_obj: object = json.loads(local_bytes.decode("utf-8"))
        if base_bytes is not None:
            base_obj: object = json.loads(base_bytes.decode("utf-8"))
        else:
            base_obj = {}
    except (UnicodeDecodeError, ValueError):
        return None
    if not (isinstance(upstream_obj, dict) and isinstance(local_obj, dict) and isinstance(base_obj, dict)):
        return None

    merged = dict(upstream_obj)
    for key, local_val in local_obj.items():
        if key not in base_obj or base_obj[key] != local_val:
            merged[key] = local_val
    for removed_key in set(base_obj) - set(local_obj):
        if removed_key in merged and upstream_obj.get(removed_key) == base_obj[removed_key]:
            del merged[removed_key]

    return (json.dumps(merged, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _three_way_merge_text(base_bytes: bytes, upstream_bytes: bytes, local_bytes: bytes) -> tuple[bool, bytes]:
    with tempfile.TemporaryDirectory(prefix="w0m-vault-merge-") as tmp_dir:
        tdir = Path(tmp_dir)
        local_f = tdir / "local"
        base_f = tdir / "base"
        upstream_f = tdir / "upstream"
        local_f.write_bytes(local_bytes)
        base_f.write_bytes(base_bytes)
        upstream_f.write_bytes(upstream_bytes)
        proc = subprocess.run(
            ["git", "merge-file", "-p", str(local_f), str(base_f), str(upstream_f)],
            capture_output=True,
            check=False,
        )
        if proc.returncode == 0:
            return True, proc.stdout
        return False, local_bytes


def _blob_at(repo_dir: Path, rev: str, rel_path: str) -> bytes | None:
    proc = _git_bytes(repo_dir, "show", f"{rev}:{rel_path}")
    return proc.stdout if proc.returncode == 0 else None


def fast_forward_preserving_vault(
    repo_dir: Path,
    target_ref: str = "origin/beta",
) -> VaultFastForwardResult:
    """Fast-forward `repo_dir` to `target_ref` while preserving live unstaged/untracked Obsidian vault edits."""
    rc_head, base_sha = _git_text(repo_dir, "rev-parse", "HEAD")
    rc_target, target_sha = _git_text(repo_dir, "rev-parse", f"{target_ref}^{{commit}}")
    if rc_head != 0 or rc_target != 0 or not base_sha or not target_sha:
        return VaultFastForwardResult(ok=False, status="unresolved_ref")

    if base_sha == target_sha:
        return VaultFastForwardResult(ok=True, status="already_up_to_date", head_sha=base_sha[:10])

    if _git_bytes(repo_dir, "merge-base", "--is-ancestor", base_sha, target_sha).returncode != 0:
        return VaultFastForwardResult(ok=False, status="skipped_non_ff_or_dirty_overlap")

    # Fast path 1: non-overlapping worktree (zero disk touches on Obsidian files).
    direct_ff = _git_bytes(repo_dir, "merge", "--ff-only", "--quiet", target_ref)
    if direct_ff.returncode == 0:
        return VaultFastForwardResult(ok=True, status="fast_forwarded", head_sha=target_sha[:10])

    # Fast path 2: heal no-op `.obsidian/*.json` formatting drift and retry.
    healed = heal_noop_obsidian_json(repo_dir)
    if healed:
        retry_ff = _git_bytes(repo_dir, "merge", "--ff-only", "--quiet", target_ref)
        if retry_ff.returncode == 0:
            return VaultFastForwardResult(
                ok=True,
                status="fast_forwarded",
                head_sha=target_sha[:10],
                healed_json=healed,
            )

    # Path 3: check whether ONLY unstaged/untracked Obsidian vault files block the fast-forward.
    cls = inspect_repo_worktree(repo_dir, include_untracked=True)
    if not cls.is_runtime_clean or not cls.live_vault_edits:
        return VaultFastForwardResult(
            ok=False,
            status="skipped_non_ff_or_dirty_overlap",
            healed_json=healed,
        )

    vault_paths = list(dict.fromkeys(cls.live_vault_edits))
    snapshots: dict[str, bytes | None] = {}
    for rel_path in vault_paths:
        fpath = repo_dir / rel_path
        snapshots[rel_path] = fpath.read_bytes() if fpath.is_file() else None

    stash_msg = f"w0m-obsidian-vault-guard:{base_sha[:8]}->{target_sha[:8]}"
    stash_proc = _git_bytes(
        repo_dir, "stash", "push", "--include-untracked", "-m", stash_msg, "--", *vault_paths
    )
    if stash_proc.returncode != 0:
        return VaultFastForwardResult(
            ok=False,
            status="skipped_non_ff_or_dirty_overlap",
            healed_json=healed,
        )

    ff_after_stash = _git_bytes(repo_dir, "merge", "--ff-only", "--quiet", target_ref)
    if ff_after_stash.returncode != 0:
        _git_bytes(repo_dir, "stash", "pop", "--quiet")
        return VaultFastForwardResult(
            ok=False,
            status="skipped_non_ff_or_dirty_overlap",
            healed_json=healed,
        )

    preserved: list[str] = []
    merged: list[str] = []
    conflicts: list[str] = []

    for rel_path, local_bytes in snapshots.items():
        dest = repo_dir / rel_path
        base_blob = _blob_at(repo_dir, base_sha, rel_path)
        upstream_blob = _blob_at(repo_dir, target_sha, rel_path)

        if local_bytes is None:
            # Local unstaged deletion in vault: only keep deleted if upstream did not edit the file.
            if base_blob == upstream_blob and dest.is_file():
                dest.unlink(missing_ok=True)
                preserved.append(rel_path)
            continue

        dest.parent.mkdir(parents=True, exist_ok=True)
        if base_blob == upstream_blob or upstream_blob is None:
            dest.write_bytes(local_bytes)
            preserved.append(rel_path)
            continue

        if local_bytes == upstream_blob:
            preserved.append(rel_path)
            continue

        if is_obsidian_config_json_path(rel_path):
            merged_json = merge_obsidian_json_three_way(base_blob, upstream_blob, local_bytes)
            if merged_json is not None:
                dest.write_bytes(merged_json)
                merged.append(rel_path)
                continue

        clean_merge, merged_bytes = _three_way_merge_text(
            base_blob or b"", upstream_blob, local_bytes
        )
        if clean_merge:
            dest.write_bytes(merged_bytes)
            merged.append(rel_path)
        else:
            # Keep operator's live note untouched without conflict markers; save upstream reference alongside.
            dest.write_bytes(local_bytes)
            sidecar = dest.with_name(f"{dest.stem}.upstream-{target_sha[:8]}{dest.suffix}")
            sidecar.write_bytes(upstream_blob)
            conflicts.append(rel_path)

    # Drop temporary stash only when every file replayed/merged cleanly; retain stash on conflict as extra backup.
    if not conflicts:
        rc_top, top_msg = _git_text(repo_dir, "stash", "list", "-n", "1")
        if rc_top == 0 and stash_msg in top_msg:
            _git_bytes(repo_dir, "stash", "drop", "--quiet", "stash@{0}")

    return VaultFastForwardResult(
        ok=True,
        status="fast_forwarded_vault_preserved",
        head_sha=target_sha[:10],
        healed_json=healed,
        preserved_files=preserved,
        merged_files=merged,
        conflict_files=conflicts,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect, heal, or fast-forward Obsidian vault checkouts.")
    parser.add_argument("--repo", default="w0m-web", help="Path to git repository (default: w0m-web)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="Classify working-tree changes into noop JSON, live vault, and blocking dirt")
    sub.add_parser("heal", help="Restore HEAD bytes on semantic no-op `.obsidian/*.json` files")
    ff_p = sub.add_parser("fast-forward", help="Fast-forward repo while preserving live Obsidian vault edits")
    ff_p.add_argument("--target", default="origin/beta", help="Target ref (default: origin/beta)")
    args = parser.parse_args(argv)

    repo_dir = Path(args.repo).resolve()
    if args.cmd == "status":
        cls = inspect_repo_worktree(repo_dir, include_untracked=True)
        print(
            json.dumps(
                {
                    "repo": str(repo_dir),
                    "is_runtime_clean": cls.is_runtime_clean,
                    "noop_obsidian_json": cls.noop_obsidian_json,
                    "live_vault_edits": cls.live_vault_edits,
                    "blocking_dirty": cls.blocking_dirty,
                },
                indent=2,
            )
        )
        return 0 if cls.is_runtime_clean else 1
    if args.cmd == "heal":
        healed = heal_noop_obsidian_json(repo_dir)
        print(json.dumps({"repo": str(repo_dir), "healed": healed}, indent=2))
        return 0
    if args.cmd == "fast-forward":
        res = fast_forward_preserving_vault(repo_dir, args.target)
        print(json.dumps(res.__dict__, indent=2))
        return 0 if res.ok else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
