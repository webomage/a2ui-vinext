#!/usr/bin/env python3
"""w0m Commit-Bound Pre-Push Checkpoint Runner (T375).

Keys pre-push gate progress strictly to the current commit hash (HEAD):
- Skips execution in <1s if all gates for HEAD are already certified.
- Auto-continues from the exact failed step if the commit hash is unchanged.
- Supports arbitrary step resumption via PREPUSH_FROM=<step_id> or --from=<step_id>.
- Supports resetting checkpoint state via PREPUSH_RESET=1 or --reset.
- Persists checkpoints in ~/.cache/w0m/prepush/<repo>-<commit_hash>.json out of the git tree.

Standard library only. Python per w0m tool ladder.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

REGISTERED_STEPS: list[tuple[str, str]] = [
    ("identity", "w0m identity gate"),
    ("typecheck", "type checks (astro check)"),
    ("w0m-audit", "w0m audit (scoped drift + openspec)"),
    ("sdlc-trace", "ticket work moved the ticket (T110 AC4)"),
    ("authz-probe", "authorization probes (T198 AC4)"),
    ("deps-sync", "cross-repo dependency alignment (deps-policy)"),
    ("docs-check", "repo hygiene — required human-facing files (T135 AC5)"),
    ("license-check", "licence audit — manifests, vendored trees (T135 AC6)"),
    ("dep-licenses-check", "dependency licences audit (T135 AC6)"),
    ("cv-leak-check", "cv-leak-check (PII served surfaces)"),
    ("dod-check", "Definition-of-Done ratchet (T242)"),
    ("client-page-tenancy", "client-page tenancy (T198 AC1)"),
    ("suites-drift", "suite registry drift"),
    ("debt-check", "tech-debt register against reality"),
    ("drop-callers", "dropped relations callers (T194 AC5)"),
    ("emoji-check", "estate-wide emoji ratchet"),
    ("state-check", "STATE.md freshness (T145)"),
    ("typecheck-ratchet", "join/job typecheck ratchet (T149/D6)"),
    ("hooks-check", "hook-layer conformance (T149/T150)"),
    ("version-check", "one release format, one producer (T131)"),
]

STEP_IDS = [s[0] for s in REGISTERED_STEPS]
STEP_NAMES = {s[0]: s[1] for s in REGISTERED_STEPS}


def get_cache_dir() -> Path:
    """Resolve directory for checkpoint storage."""
    base = os.environ.get("W0M_PREPUSH_CACHE_DIR")
    if base:
        p = Path(base)
    else:
        p = Path.home() / ".cache" / "w0m" / "prepush"
    try:
        p.mkdir(parents=True, exist_ok=True)
    except OSError:
        p = Path("/tmp/w0m-prepush")
        p.mkdir(parents=True, exist_ok=True)
    return p


def resolve_commit(commit_override: str | None = None) -> str:
    """Resolve current commit hash from argument, env, or git rev-parse."""
    if commit_override and commit_override != "unknown":
        return commit_override.strip()
    env_commit = os.environ.get("W0M_COMMIT_HASH")
    if env_commit and env_commit != "unknown":
        return env_commit.strip()
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        return out.stdout.strip()
    except Exception:
        return "unknown"


def resolve_repo() -> str:
    """Resolve repository name from git remote or folder."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        return Path(out.stdout.strip()).name
    except Exception:
        return "wom7web"


def checkpoint_file_path(repo: str, commit_hash: str) -> Path:
    return get_cache_dir() / f"{repo}-{commit_hash}.json"


def load_checkpoint(repo: str, commit_hash: str) -> dict:
    if commit_hash == "unknown":
        return {}
    path = checkpoint_file_path(repo, commit_hash)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        return data
    except Exception as exc:
        print(f"⚠️  [prepush] Warning: corrupted checkpoint file {path} ({exc}); resetting.", file=sys.stderr)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return {}


def save_checkpoint(repo: str, commit_hash: str, data: dict) -> None:
    if commit_hash == "unknown":
        return
    path = checkpoint_file_path(repo, commit_hash)
    data["repo"] = repo
    data["commit"] = commit_hash
    data["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(path)
    except Exception as exc:
        print(f"⚠️  [prepush] Could not write checkpoint to {path}: {exc}", file=sys.stderr)


def is_reset_requested(args_reset: bool = False) -> bool:
    if args_reset:
        return True
    val = os.environ.get("PREPUSH_RESET", "").strip().lower()
    return val in {"1", "true", "yes"}


def get_resume_from(args_from: str | None = None) -> str | None:
    val = args_from or os.environ.get("PREPUSH_FROM")
    if not val:
        return None
    val = val.strip()
    if val in STEP_IDS:
        return val
    # Check if number 1..N was supplied
    if val.isdigit():
        idx = int(val) - 1
        if 0 <= idx < len(STEP_IDS):
            return STEP_IDS[idx]
    print(f"⚠️  [prepush] Unknown step '{val}' in PREPUSH_FROM. Valid steps: {', '.join(STEP_IDS)}", file=sys.stderr)
    return None


def cmd_check_certified(repo: str, commit_hash: str, args: argparse.Namespace) -> int:
    """Exit 0 if all registered steps are already marked passed for this commit."""
    if is_reset_requested(args.reset) or get_resume_from(args.resume_from):
        return 1
    cp = load_checkpoint(repo, commit_hash)
    if not cp or cp.get("status") != "passed":
        return 1
    steps = cp.get("steps", {})
    all_passed = all(steps.get(s_id, {}).get("status") == "passed" for s_id in STEP_IDS)
    if all_passed:
        updated = cp.get("updated_at", "recently")
        print(f"✅ [{repo}] Pre-push: commit {commit_hash[:8]} is already fully certified (all {len(STEP_IDS)} gates passed at {updated}). Skipping.")
        return 0
    return 1


def cmd_step_begin(repo: str, commit_hash: str, args: argparse.Namespace) -> int:
    """Determines whether step should run (exit 0) or be skipped as cached pass (exit 1)."""
    step_id = args.step_id
    desc = args.description or STEP_NAMES.get(step_id, step_id)

    if is_reset_requested(args.reset):
        # Clear checkpoint
        cp_path = checkpoint_file_path(repo, commit_hash)
        if cp_path.is_file():
            try:
                cp_path.unlink()
            except OSError:
                pass
        cp = {}
    else:
        cp = load_checkpoint(repo, commit_hash)

    resume_from = get_resume_from(args.resume_from)
    steps = cp.get("steps", {})

    # If an explicit resume_from is active
    if resume_from:
        target_idx = STEP_IDS.index(resume_from)
        curr_idx = STEP_IDS.index(step_id) if step_id in STEP_IDS else 0
        if curr_idx < target_idx:
            # Step is before the forced resume target
            dur = steps.get(step_id, {}).get("duration_s")
            dur_str = f" ({dur:.1f}s)" if dur is not None else ""
            print(f"  ✓ [cached pass] {desc}{dur_str}")
            return 1  # SKIP
        # At or past target: run
        cp["current_step"] = step_id
        save_checkpoint(repo, commit_hash, cp)
        echo_header(repo, desc)
        return 0  # RUN

    # Standard auto-continue behavior:
    # If this step was marked passed previously on this same commit,
    # and no prior registered step has failed or is pending:
    is_step_passed = steps.get(step_id, {}).get("status") == "passed"
    curr_idx = STEP_IDS.index(step_id) if step_id in STEP_IDS else -1

    if is_step_passed and curr_idx != -1:
        # Check that all earlier steps in registry also passed
        earlier_all_passed = all(steps.get(s, {}).get("status") == "passed" for s in STEP_IDS[:curr_idx])
        if earlier_all_passed:
            dur = steps.get(step_id, {}).get("duration_s")
            dur_str = f" ({dur:.1f}s)" if dur is not None else ""
            print(f"  ✓ [cached pass] {desc}{dur_str}")
            return 1  # SKIP

    # Must run step
    cp["current_step"] = step_id
    cp["status"] = "in_progress"
    save_checkpoint(repo, commit_hash, cp)
    echo_header(repo, desc)
    return 0  # RUN


def echo_header(repo: str, desc: str) -> None:
    print(f"⏳ [{repo}] Pre-push: {desc}...")


def cmd_step_pass(repo: str, commit_hash: str, args: argparse.Namespace) -> int:
    step_id = args.step_id
    cp = load_checkpoint(repo, commit_hash)
    if "steps" not in cp:
        cp["steps"] = {}
    cp["steps"][step_id] = {
        "status": "passed",
        "exit_code": 0,
        "duration_s": float(args.duration or 0.0),
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    cp["current_step"] = None

    # Check if all steps in registered set have now passed
    all_done = all(cp["steps"].get(s, {}).get("status") == "passed" for s in STEP_IDS)
    if all_done:
        cp["status"] = "passed"
        cp["last_failed_step"] = None
    save_checkpoint(repo, commit_hash, cp)
    return 0


def cmd_step_fail(repo: str, commit_hash: str, args: argparse.Namespace) -> int:
    step_id = args.step_id
    code = int(args.exit_code or 1)
    cp = load_checkpoint(repo, commit_hash)
    if "steps" not in cp:
        cp["steps"] = {}
    cp["steps"][step_id] = {
        "status": "failed",
        "exit_code": code,
        "duration_s": float(args.duration or 0.0),
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    cp["current_step"] = None
    cp["status"] = "failed"
    cp["last_failed_step"] = step_id
    save_checkpoint(repo, commit_hash, cp)

    desc = STEP_NAMES.get(step_id, step_id)
    print("\n" + "─" * 74, file=sys.stderr)
    print(f"❌ [{repo}] Pre-push checkpoint recorded failure at step '{step_id}' ({desc}).", file=sys.stderr)
    print(f"   When ready, re-running 'git push' will automatically continue from '{step_id}'.", file=sys.stderr)
    print(f"   · To restart from step 1: PREPUSH_RESET=1 git push (or 'just prepush-reset')", file=sys.stderr)
    print(f"   · To resume from any step: PREPUSH_FROM=<step_id> git push", file=sys.stderr)
    print("─" * 74 + "\n", file=sys.stderr)
    return 0


def cmd_status(repo: str, commit_hash: str, _args: argparse.Namespace) -> int:
    cp = load_checkpoint(repo, commit_hash)
    print(f"\n▶ Pre-push checkpoint status — repo: {repo} · commit: {commit_hash[:8]}")
    if not cp:
        print("  No checkpoint recorded for this commit (clean / unstarted).\n")
        return 0
    status = cp.get("status", "in_progress")
    last_failed = cp.get("last_failed_step")
    updated = cp.get("updated_at", "never")
    print(f"  Overall Status : {status.upper()}")
    if last_failed:
        print(f"  Failed At      : {last_failed}")
    print(f"  Last Update    : {updated}\n")

    steps = cp.get("steps", {})
    print(f"  {'#':<3} {'Step ID':<22} {'Status':<12} {'Duration':<10} {'Description'}")
    print("  " + "─" * 70)
    for idx, (s_id, s_desc) in enumerate(REGISTERED_STEPS, start=1):
        st = steps.get(s_id, {})
        st_val = st.get("status", "pending")
        if st_val == "passed":
            st_str = "✅ passed"
        elif st_val == "failed":
            st_str = f"❌ fail({st.get('exit_code', 1)})"
        else:
            st_str = "⚪ pending"
        dur = st.get("duration_s")
        dur_str = f"{dur:.1f}s" if dur is not None else "—"
        print(f"  {idx:<3} {s_id:<22} {st_str:<12} {dur_str:<10} {s_desc}")
    print("")
    return 0


def cmd_reset(repo: str, commit_hash: str, _args: argparse.Namespace) -> int:
    path = checkpoint_file_path(repo, commit_hash)
    if path.is_file():
        try:
            path.unlink()
            print(f"✅ Pre-push checkpoint deleted for {repo} @ {commit_hash[:8]}")
        except OSError as exc:
            print(f"❌ Failed to delete {path}: {exc}", file=sys.stderr)
            return 1
    else:
        print(f"ℹ️  No checkpoint file found for {repo} @ {commit_hash[:8]}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="w0m Commit-Bound Pre-Push Checkpoint Runner")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--commit", default=argparse.SUPPRESS, help="Commit hash (defaults to HEAD)")
    common.add_argument("--repo", default=argparse.SUPPRESS, help="Repository name (defaults to current dir name)")
    common.add_argument("--from", dest="resume_from", default=argparse.SUPPRESS, help="Start or resume execution from this step")
    common.add_argument("--reset", action="store_true", default=argparse.SUPPRESS, help="Clear checkpoint and run from step 1")

    parser = argparse.ArgumentParser(
        description="w0m Commit-Bound Pre-Push Checkpoint Runner",
        parents=[common],
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # check-certified
    subparsers.add_parser("check-certified", parents=[common], help="Check if commit is already fully certified")

    # step-begin
    p_begin = subparsers.add_parser("step-begin", parents=[common], help="Check if a step should run or skip")
    p_begin.add_argument("step_id", help="Step identifier")
    p_begin.add_argument("description", nargs="?", default="", help="Step description")

    # step-pass
    p_pass = subparsers.add_parser("step-pass", parents=[common], help="Record successful step completion")
    p_pass.add_argument("step_id", help="Step identifier")
    p_pass.add_argument("--duration", type=float, default=0.0, help="Step duration in seconds")

    # step-fail
    p_fail = subparsers.add_parser("step-fail", parents=[common], help="Record step failure")
    p_fail.add_argument("step_id", help="Step identifier")
    p_fail.add_argument("--exit-code", type=int, default=1, help="Process exit code")
    p_fail.add_argument("--duration", type=float, default=0.0, help="Step duration in seconds")

    # status
    subparsers.add_parser("status", parents=[common], help="Print checkpoint status for current commit")

    # reset
    subparsers.add_parser("reset", parents=[common], help="Clear checkpoint file for current commit")

    args = parser.parse_args()
    args.commit = getattr(args, "commit", None)
    args.repo = getattr(args, "repo", None)
    args.resume_from = getattr(args, "resume_from", None)
    args.reset = getattr(args, "reset", False)

    commit_hash = resolve_commit(args.commit)
    repo = args.repo or resolve_repo()

    if args.command == "check-certified":
        return cmd_check_certified(repo, commit_hash, args)
    elif args.command == "step-begin":
        return cmd_step_begin(repo, commit_hash, args)
    elif args.command == "step-pass":
        return cmd_step_pass(repo, commit_hash, args)
    elif args.command == "step-fail":
        return cmd_step_fail(repo, commit_hash, args)
    elif args.command == "status":
        return cmd_status(repo, commit_hash, args)
    elif args.command == "reset":
        return cmd_reset(repo, commit_hash, args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
