#!/usr/bin/env python3
"""worktree_agent.py (T411 AC5) — Coordinated Worktree Orchestrator for Parallel AI Agents.

Eliminates the "Root-Only Worktree Illusion" where parallel agents created in root worktrees
unintentionally share the same unbranched working directory in sub-repos (w0m-web, w0m-api).

Commands:
  create <agent_id> [--subrepos web,api] [--branch <name>]
  remove <agent_id> [--force] [--delete-branch]
  list
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

# Resolve root workspace (@wom)
ROOT = Path(__file__).resolve().parents[1]
if not (ROOT / ".git").exists() and (ROOT.parent / ".git").exists():
    ROOT = ROOT.parent

SUBREPO_MAP = {
    "web": "w0m-web",
    "w0m-web": "w0m-web",
    "api": "w0m-api",
    "w0m-api": "w0m-api",
    "func": "w0m-cf",
    "w0m-cf": "w0m-cf",
    "ext": "w0m-ext",
    "w0m-ext": "w0m-ext",
    "sec": "w0m-sec",
    "w0m-sec": "w0m-sec",
    "skills": "w0m-skills",
    "w0m-skills": "w0m-skills",
    "pr": "w0m-pr",
    "w0m-pr": "w0m-pr",
}


def sh(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd or ROOT, capture_output=True, text=True)


def get_current_branch(repo: Path) -> str:
    res = sh(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo)
    return res.stdout.strip() or "beta"


def cmd_create(agent_id: str, subrepos_raw: list[str], base_branch: str | None = None) -> int:
    """Create coordinated linked worktrees for root and requested subrepos."""
    worktree_root = ROOT / ".worktrees" / agent_id
    branch_name = f"agent/{agent_id}"

    # Determine subrepos to isolate
    selected_subrepos: list[str] = []
    if not subrepos_raw:
        selected_subrepos = ["w0m-web"]
    else:
        for s in subrepos_raw:
            for item in s.split(","):
                item = item.strip().lower()
                if item in SUBREPO_MAP:
                    mapped = SUBREPO_MAP[item]
                    if mapped not in selected_subrepos:
                        selected_subrepos.append(mapped)

    print(f"▶ Provisioning coordinated worktrees for agent `{agent_id}`...")
    print(f"  Target path: {worktree_root}")
    print(f"  Branch:      {branch_name}")
    print(f"  Subrepos:    {', '.join(selected_subrepos)}")

    # 1. Root worktree
    if not worktree_root.exists():
        base = base_branch or get_current_branch(ROOT)
        # Check if branch already exists
        check_br = sh(["git", "show-ref", "--verify", f"refs/heads/{branch_name}"])
        add_args = ["git", "worktree", "add"]
        if check_br.returncode == 0:
            add_args.extend([str(worktree_root), branch_name])
        else:
            add_args.extend(["-b", branch_name, str(worktree_root), base])

        res = sh(add_args)
        if res.returncode != 0:
            print(f"❌ Failed to create root worktree: {res.stderr.strip()}", file=sys.stderr)
            return 1
        print(f"  ✓ Root worktree created at {worktree_root}")
    else:
        print(f"  ℹ Root worktree already exists at {worktree_root}")

    # 2. Subrepo worktrees & symlinks
    for sub in selected_subrepos:
        sub_dir = ROOT / sub
        if not sub_dir.is_dir() or not (sub_dir / ".git").exists():
            print(f"  ⚠️ Skipping {sub}: directory or git repository not found")
            continue

        sub_wt_dir = sub_dir / ".worktrees" / agent_id
        if not sub_wt_dir.exists():
            sub_base = base_branch or get_current_branch(sub_dir)
            check_br = sh(["git", "show-ref", "--verify", f"refs/heads/{branch_name}"], cwd=sub_dir)
            add_args = ["git", "worktree", "add"]
            if check_br.returncode == 0:
                add_args.extend([str(sub_wt_dir), branch_name])
            else:
                add_args.extend(["-b", branch_name, str(sub_wt_dir), sub_base])

            res = sh(add_args, cwd=sub_dir)
            if res.returncode != 0:
                print(f"❌ Failed to create worktree for {sub}: {res.stderr.strip()}", file=sys.stderr)
                return 1
            print(f"  ✓ {sub} worktree created at {sub_wt_dir}")

        # Link inside root worktree
        link_target = worktree_root / sub
        if link_target.is_symlink() or link_target.exists():
            link_target.unlink()
        
        # Create relative symlink: from worktree_root/sub to sub_dir/.worktrees/agent_id
        rel_target = os.path.relpath(sub_wt_dir, worktree_root)
        link_target.symlink_to(rel_target)
        print(f"  ✓ Linked {link_target.name} -> {rel_target}")

    print(f"\n✅ Agent worktree ready: {worktree_root}")
    return 0


def cmd_remove(agent_id: str, force: bool = False, delete_branch: bool = False) -> int:
    """Tear down linked worktrees for the agent."""
    worktree_root = ROOT / ".worktrees" / agent_id
    branch_name = f"agent/{agent_id}"

    print(f"▶ Removing coordinated worktrees for agent `{agent_id}`...")

    # Subrepo worktrees
    for sub in SUBREPO_MAP.values():
        sub_dir = ROOT / sub
        sub_wt = sub_dir / ".worktrees" / agent_id
        if sub_wt.exists():
            args = ["git", "worktree", "remove"]
            if force:
                args.append("--force")
            args.append(str(sub_wt))
            res = sh(args, cwd=sub_dir)
            if res.returncode == 0:
                print(f"  ✓ Removed {sub} worktree at {sub_wt}")
            else:
                print(f"  ⚠️ Could not remove {sub} worktree: {res.stderr.strip()}", file=sys.stderr)

            if delete_branch:
                sh(["git", "branch", "-D" if force else "-d", branch_name], cwd=sub_dir)

    # Root worktree
    if worktree_root.exists():
        args = ["git", "worktree", "remove"]
        if force:
            args.append("--force")
        args.append(str(worktree_root))
        res = sh(args)
        if res.returncode == 0:
            print(f"  ✓ Removed root worktree at {worktree_root}")
        else:
            print(f"  ⚠️ Could not remove root worktree: {res.stderr.strip()}", file=sys.stderr)

        if delete_branch:
            sh(["git", "branch", "-D" if force else "-d", branch_name])

    print(f"✅ Cleanup complete for agent `{agent_id}`.")
    return 0


def cmd_list() -> int:
    """List active coordinated agent worktrees."""
    wt_dir = ROOT / ".worktrees"
    if not wt_dir.exists():
        print("No active agent worktrees found.")
        return 0

    agents = [d.name for d in wt_dir.iterdir() if d.is_dir() and not d.name.startswith(".")]
    if not agents:
        print("No active agent worktrees found.")
        return 0

    print(f"Active agent worktrees ({len(agents)}):")
    for a in sorted(agents):
        path = wt_dir / a
        linked_subs = [p.name for p in path.iterdir() if p.is_symlink()]
        print(f"  • {a} -> {path} (isolated subrepos: {', '.join(linked_subs) or 'none'})")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Coordinated worktree manager for parallel agents.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # create
    p_create = subparsers.add_parser("create", help="Create linked worktrees for an agent.")
    p_create.add_argument("agent_id", help="Identifier for the agent (e.g. alpha, task-123)")
    p_create.add_argument("--subrepos", "-s", nargs="*", default=["w0m-web"], help="Target subrepos (e.g. web, api)")
    p_create.add_argument("--branch", "-b", default=None, help="Base branch (default: current branch)")

    # remove
    p_remove = subparsers.add_parser("remove", help="Remove linked worktrees.")
    p_remove.add_argument("agent_id", help="Agent identifier")
    p_remove.add_argument("--force", "-f", action="store_true", help="Force removal")
    p_remove.add_argument("--delete-branch", "-d", action="store_true", help="Delete git branch")

    # list
    subparsers.add_parser("list", help="List active agent worktrees.")

    args = parser.parse_args()
    if args.command == "create":
        return cmd_create(args.agent_id, args.subrepos, args.branch)
    elif args.command == "remove":
        return cmd_remove(args.agent_id, args.force, args.delete_branch)
    elif args.command == "list":
        return cmd_list()
    return 0


if __name__ == "__main__":
    sys.exit(main())
