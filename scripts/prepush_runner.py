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
import concurrent.futures
import contextlib
import datetime
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

REGISTERED_STEPS: list[tuple[str, str]] = [
    ("identity", "w0m identity gate"),
    ("typecheck", "type checks (astro check)"),
    ("w0m-audit", "w0m audit (scoped drift + openspec)"),
    ("sdlc-trace", "ticket work moved the ticket (T110 AC4)"),
    ("authz-probe", "authorization probes (T198 AC4)"),
    ("authz-admin-client", "RLS-bypassing admin client ratchet (T327)"),
    ("route-policy", "every app mounts the auth middleware; no undeclared /api/* route (T453)"),
    ("plan-set", "current_plan resolves to a ROADMAP epic and was not hand-edited (T335)"),
    ("secret-flow", "every pushed secret is read somewhere (T244)"),
    ("deps-sync", "cross-repo dependency alignment (deps-policy)"),
    ("docs-check", "repo hygiene — required human-facing files (T135 AC5)"),
    ("license-check", "licence audit — manifests, vendored trees (T135 AC6)"),
    ("dep-licenses-check", "dependency licences audit (T135 AC6)"),
    ("cv-leak-check", "cv-leak-check (PII served surfaces)"),
    ("dod-check", "Definition-of-Done ratchet (T242)"),
    ("client-page-tenancy", "client-page tenancy (T198 AC1)"),
    ("suites-drift", "suite registry drift"),
    ("deploy-ratchets", "fast ratchets a deploy would run (T503)"),
    ("debt-check", "tech-debt register against reality"),
    ("drop-callers", "dropped relations callers (T194 AC5)"),
    ("emoji-check", "estate-wide emoji ratchet"),
    ("typecheck-ratchet", "join/job typecheck ratchet (T149/D6)"),
    ("hooks-check", "hook-layer conformance (T149/T150)"),
    ("version-check", "one release format, one producer (T131)"),
    ("state-check", "STATE.md freshness (T145)"),
]

STEP_IDS = [s[0] for s in REGISTERED_STEPS]
STEP_NAMES = {s[0]: s[1] for s in REGISTERED_STEPS}


def compute_runmark_digest(steps: list[tuple[str, str]] | None = None) -> str:
    """Compute a 12-char content-addressed SHA-256 digest over registered pre-push steps (T556 AC6)."""
    target = steps if steps is not None else REGISTERED_STEPS
    payload = json.dumps([s[0] for s in target], separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


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


@contextlib.contextmanager
def checkpoint_lock(repo: str, commit_hash: str) -> Iterator[None]:
    """Acquire an exclusive flock around checkpoint read-modify-write for parallel gate groups (T477 AC2)."""
    if commit_hash == "unknown":
        yield
        return
    lock_path = get_cache_dir() / f"{repo}-{commit_hash}.lock"
    try:
        fh = lock_path.open("w", encoding="utf-8")
    except OSError:
        yield
        return
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        fh.close()


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
    data["runmark_digest"] = compute_runmark_digest()
    data["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
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


def why_not(
    repo: str,
    commit_hash: str,
    args: argparse.Namespace | None = None,
    step_id: str | None = None,
) -> str:
    """Return '' if the checkpoint/step is certified and reusable, else a 1-line invalidation reason (T556 AC6)."""
    args_reset = getattr(args, "reset", False) if args else False
    args_from = getattr(args, "resume_from", None) if args else None

    if is_reset_requested(args_reset):
        return "reset requested (PREPUSH_RESET or --reset)"

    resume_from = get_resume_from(args_from)
    if resume_from:
        if step_id is None:
            return f"forced resume from '{resume_from}' (PREPUSH_FROM or --from)"
        target_idx = STEP_IDS.index(resume_from)
        curr_idx = STEP_IDS.index(step_id) if step_id in STEP_IDS else 0
        if curr_idx >= target_idx:
            return f"forced resume at/after '{resume_from}'"
        return ""

    cp = load_checkpoint(repo, commit_hash)
    if not cp:
        return f"no checkpoint recorded for {repo}@{commit_hash[:8]}"

    expected_digest = compute_runmark_digest()
    recorded_digest = cp.get("runmark_digest")
    if recorded_digest and recorded_digest != expected_digest:
        return f"runmark config digest mismatch (checkpoint={recorded_digest} vs current={expected_digest})"

    steps = cp.get("steps", {})
    if step_id is not None:
        st = steps.get(step_id, {})
        st_status = st.get("status", "pending")
        if st_status != "passed":
            return f"step '{step_id}' status is '{st_status}'"
        return ""

    if cp.get("status") != "passed":
        failed_at = cp.get("last_failed_step")
        if failed_at:
            return f"checkpoint status is '{cp.get('status')}' (failed at '{failed_at}')"
        return f"checkpoint status is '{cp.get('status', 'in_progress')}'"

    for s_id in STEP_IDS:
        s_stat = steps.get(s_id, {}).get("status", "pending")
        if s_stat != "passed":
            return f"step '{s_id}' is '{s_stat}'"

    return ""


def cmd_check_certified(repo: str, commit_hash: str, args: argparse.Namespace) -> int:
    """Exit 0 if all registered steps are already marked passed for this commit."""
    reason = why_not(repo, commit_hash, args=args, step_id=None)
    if not reason:
        cp = load_checkpoint(repo, commit_hash)
        updated = cp.get("updated_at", "recently")
        digest = cp.get("runmark_digest", compute_runmark_digest())
        print(f"✅ [{repo}] Pre-push: commit {commit_hash[:8]} (runmark {digest}) is already fully certified (all {len(STEP_IDS)} gates passed at {updated}). Skipping.")
        return 0
    return 1


def format_step_bar(step_id: str, width: int = 16) -> str:
    if step_id not in STEP_IDS:
        return ""
    idx = STEP_IDS.index(step_id) + 1
    total = len(STEP_IDS)
    pct = int((idx / total) * 100) if total > 0 else 100
    filled_len = int(width * idx // total) if total > 0 else width
    empty_len = max(0, width - filled_len)
    bar = "█" * filled_len + "░" * empty_len
    return f"[{idx:>2}/{total:<2}] [{bar}] {pct:>3}% | "


def cmd_step_begin(repo: str, commit_hash: str, args: argparse.Namespace) -> int:
    """Determines whether step should run (exit 0) or be skipped as cached pass (exit 1)."""
    step_id = args.step_id
    desc = args.description or STEP_NAMES.get(step_id, step_id)
    bar_prefix = format_step_bar(step_id)

    with checkpoint_lock(repo, commit_hash):
        reason = why_not(repo, commit_hash, args=args, step_id=step_id)
        if is_reset_requested(args.reset) and (args.reset or step_id == STEP_IDS[0]):
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
                dur = steps.get(step_id, {}).get("duration_s")
                dur_str = f" ({dur:.1f}s)" if dur is not None else ""
                print(f"  {bar_prefix}✓ [cached pass] {desc}{dur_str}", flush=True)
                return 1  # SKIP
            cp["current_step"] = step_id
            save_checkpoint(repo, commit_hash, cp)
            echo_header(repo, desc, reason, step_id=step_id)
            return 0  # RUN

        # Standard auto-continue behavior:
        if not reason:
            dur = steps.get(step_id, {}).get("duration_s")
            dur_str = f" ({dur:.1f}s)" if dur is not None else ""
            print(f"  {bar_prefix}✓ [cached pass] {desc}{dur_str}", flush=True)
            return 1  # SKIP

        # Must run step
        cp["current_step"] = step_id
        if cp.get("status") != "failed":
            cp["status"] = "in_progress"
        save_checkpoint(repo, commit_hash, cp)
        echo_header(repo, desc, reason, step_id=step_id)
        return 0  # RUN


def echo_header(repo: str, desc: str, reason: str = "", step_id: str = "") -> None:
    suffix = f" [why_not: {reason}]" if reason else ""
    bar_prefix = format_step_bar(step_id) if step_id else ""
    print(f"  {bar_prefix}⏳ [{repo}] Pre-push: {desc}...{suffix}", flush=True)


def cmd_step_pass(repo: str, commit_hash: str, args: argparse.Namespace) -> int:
    step_id = args.step_id
    dur = float(args.duration or 0.0)
    with checkpoint_lock(repo, commit_hash):
        cp = load_checkpoint(repo, commit_hash)
        if "steps" not in cp:
            cp["steps"] = {}
        cp["steps"][step_id] = {
            "status": "passed",
            "exit_code": 0,
            "duration_s": dur,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        cp["current_step"] = None

        all_done = all(cp["steps"].get(s, {}).get("status") == "passed" for s in STEP_IDS)
        any_failed = any(cp["steps"].get(s, {}).get("status") == "failed" for s in STEP_IDS)
        if all_done:
            cp["status"] = "passed"
            cp["last_failed_step"] = None
        elif any_failed:
            cp["status"] = "failed"
            cp["last_failed_step"] = next(
                (s for s in STEP_IDS if cp["steps"].get(s, {}).get("status") == "failed"),
                cp.get("last_failed_step"),
            )
        save_checkpoint(repo, commit_hash, cp)
    bar_prefix = format_step_bar(step_id)
    print(f"  {bar_prefix}✅ [{repo}] {step_id} passed ({dur:.1f}s)", flush=True)
    return 0


def cmd_step_fail(repo: str, commit_hash: str, args: argparse.Namespace) -> int:
    step_id = args.step_id
    code = int(args.exit_code or 1)
    with checkpoint_lock(repo, commit_hash):
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
        cp["last_failed_step"] = next(
            (s for s in STEP_IDS if cp["steps"].get(s, {}).get("status") == "failed"),
            step_id,
        )
        save_checkpoint(repo, commit_hash, cp)

    desc = STEP_NAMES.get(step_id, step_id)
    print("\n" + "─" * 74, file=sys.stderr)
    print(f"❌ [{repo}] Pre-push checkpoint recorded failure at step '{step_id}' ({desc}).", file=sys.stderr)
    print(f"   When ready, re-running 'git push' will automatically continue from '{step_id}'.", file=sys.stderr)
    print(f"   · To restart from step 1: PREPUSH_RESET=1 git push (or 'just prepush-reset')", file=sys.stderr)
    print(f"   · To resume from any step: PREPUSH_FROM=<step_id> git push", file=sys.stderr)
    print("─" * 74 + "\n", file=sys.stderr)
    return 0


def discover_typecheck_apps(web_root: Path) -> list[str]:
    """Read the ordered list of apps gated by `scripts.typecheck` in `wom7web/package.json`."""
    pkg = web_root / "package.json"
    data = json.loads(pkg.read_text(encoding="utf-8"))
    script = data.get("scripts", {}).get("typecheck", "")
    apps = re.findall(r"--filter\s+(\S+)\s+exec\s+astro\s+check", script)
    if not apps:
        raise ValueError(f"no `--filter <app> exec astro check` entries found in {pkg}")
    return apps


def host_total_ram_gib() -> float:
    """Detect total usable system memory in GiB via /proc/meminfo or sysconf (T573)."""
    try:
        meminfo = Path("/proc/meminfo")
        if meminfo.is_file():
            for line in meminfo.read_text(encoding="utf-8").splitlines():
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    return kb / (1024.0 * 1024.0)
    except (OSError, ValueError, IndexError):
        pass
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        if isinstance(pages, int) and isinstance(page_size, int) and pages > 0 and page_size > 0:
            return (pages * page_size) / (1024.0**3)
    except (AttributeError, ValueError, OSError):
        pass
    return 16.0


def default_typecheck_concurrency(ram_gib: float | None = None) -> int:
    """Choose safe astro check concurrency from host RAM so <=8 GiB hosts never swap-thrash (T573)."""
    total_gib = host_total_ram_gib() if ram_gib is None else ram_gib
    if total_gib <= 8.0:
        return 1
    if total_gib <= 14.0:
        return 2
    return 3


def default_node_max_old_space_mb(ram_gib: float | None = None) -> int:
    """Choose V8 heap ceiling (--max-old-space-size) proportional to host RAM so GC runs before swap (T573)."""
    total_gib = host_total_ram_gib() if ram_gib is None else ram_gib
    if total_gib <= 8.0:
        return 2048
    if total_gib <= 14.0:
        return 4096
    return 8192


@contextlib.contextmanager
def typecheck_global_lock() -> Iterator[None]:
    """Serialize run-typecheck invocations across concurrent worktrees/hooks via flock (T573)."""
    lock_path = get_cache_dir() / "typecheck.lock"
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    except OSError:
        yield
        return
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("  ⏳ [typecheck] waiting for another active typecheck run to finish...", flush=True)
            fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        with contextlib.suppress(OSError):
            fcntl.flock(fd, fcntl.LOCK_UN)
        with contextlib.suppress(OSError):
            os.close(fd)


def cmd_run_typecheck(args: argparse.Namespace) -> int:
    """Run `astro check` across all gated apps with host-RAM-aware concurrency and deterministic buffered output (T477 AC2 / T573)."""
    if getattr(args, "web_root", None):
        web_root = Path(args.web_root).resolve()
    else:
        cwd = Path.cwd().resolve()
        web_root = (cwd / "wom7web") if (cwd / "wom7web" / "package.json").is_file() else cwd
    ram_gib = host_total_ram_gib()
    raw_conc = getattr(args, "concurrency", None)
    env_conc = os.environ.get("W0M_TYPECHECK_CONCURRENCY")
    if raw_conc is not None:
        concurrency = int(raw_conc)
    elif env_conc:
        concurrency = int(env_conc)
    else:
        concurrency = default_typecheck_concurrency(ram_gib)
    concurrency = max(1, min(concurrency, 4))
    max_old_space = default_node_max_old_space_mb(ram_gib)
    try:
        apps = discover_typecheck_apps(web_root)
    except Exception as exc:
        print(f"❌ typecheck: could not read gated apps from {web_root / 'package.json'}: {exc}", file=sys.stderr)
        return 2

    cmd_template = os.environ.get("W0M_TYPECHECK_CMD_TEMPLATE", "")

    def _check_one(app: str) -> tuple[str, int, float, str]:
        t0 = time.monotonic()
        env = {
            **os.environ,
            "NODE_OPTIONS": os.environ.get("NODE_OPTIONS", f"--max-old-space-size={max_old_space}"),
            "ASTRO_TELEMETRY_DISABLED": "1",
            "DO_NOT_TRACK": "1",
        }
        if cmd_template:
            cmd = ["sh", "-c", cmd_template.format(app=app)]
        else:
            cmd = ["pnpm", "--filter", app, "exec", "astro", "check"]
        proc = subprocess.run(cmd, cwd=web_root, stdin=subprocess.DEVNULL, capture_output=True, text=True, env=env)
        dur = time.monotonic() - t0
        return app, proc.returncode, dur, (proc.stdout or "") + (proc.stderr or "")

    with typecheck_global_lock():
        t_start = time.monotonic()
        results_by_app: dict[str, tuple[int, float, str]] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
            future_map = {pool.submit(_check_one, app): app for app in apps}
            for fut in concurrent.futures.as_completed(future_map):
                app_name, rc, dur, out = fut.result()
                results_by_app[app_name] = (rc, dur, out)

    failed_apps: list[str] = []
    total_svelte = 0
    for app in apps:
        rc, dur, out = results_by_app[app]
        mark = "✅" if rc == 0 else "❌"
        app_src = web_root / "apps" / app / "src"
        svelte_count = sum(1 for _ in app_src.rglob("*.svelte")) if app_src.is_dir() else 0
        total_svelte += svelte_count
        print(f"  {mark} [typecheck:{app}] ({dur:.1f}s)", flush=True)
        print(
            f"     [typecheck:{app}] scope: astro check covers .astro/.ts; "
            f"{svelte_count} .svelte file(s) excluded by astro check -> gated by svelte-typecheck-ratchet",
            flush=True,
        )
        if out.strip():
            print(out.rstrip(), flush=True)
        if rc != 0:
            failed_apps.append(app)

    total_dur = time.monotonic() - t_start
    if failed_apps:
        print(
            f"❌ typecheck failed ({len(failed_apps)}/{len(apps)} app(s) failed in {total_dur:.1f}s, "
            f"concurrency={concurrency}): {', '.join(failed_apps)}",
            file=sys.stderr,
            flush=True,
        )
        return 1

    if not cmd_template:
        svelte_ratchet = web_root / "project" / "scripts" / "svelte_typecheck_ratchet.py"
        if svelte_ratchet.is_file():
            sr = subprocess.run([sys.executable, str(svelte_ratchet), "--web-root", str(web_root)], cwd=web_root)
            if sr.returncode != 0:
                return sr.returncode

    print(
        f"  ✅ typecheck: all {len(apps)} apps passed in {total_dur:.1f}s (concurrency={concurrency}; "
        f"{total_svelte} .svelte file(s) excluded by astro check -> gated by svelte-typecheck-ratchet)",
        flush=True,
    )
    return 0


def cmd_status(repo: str, commit_hash: str, _args: argparse.Namespace) -> int:
    cp = load_checkpoint(repo, commit_hash)
    print(f"\n▶ Pre-push checkpoint status — repo: {repo} · commit: {commit_hash[:8]}")
    if not cp:
        print("  No checkpoint recorded for this commit (clean / unstarted).")
        print(f"  Cache Reason   : {why_not(repo, commit_hash, args=_args)}\n")
        return 0
    status = cp.get("status", "in_progress")
    last_failed = cp.get("last_failed_step")
    updated = cp.get("updated_at", "never")
    digest = cp.get("runmark_digest", compute_runmark_digest())
    reason = why_not(repo, commit_hash, args=_args)
    print(f"  Overall Status : {status.upper()}")
    print(f"  Runmark Digest : {digest}")
    print(f"  Cache Reason   : {reason or 'certified (reusable)'}")
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

    # run-typecheck (T477 AC2 / T573)
    p_tc = subparsers.add_parser("run-typecheck", parents=[common], help="Run astro check across gated apps with host-RAM-aware concurrency")
    p_tc.add_argument("--concurrency", type=int, default=None, help="Max concurrent astro check processes (1-4, defaults to host RAM auto-scale)")
    p_tc.add_argument("--web-root", default=None, help="Path to wom7web root (defaults to cwd)")

    # status
    subparsers.add_parser("status", parents=[common], help="Print checkpoint status for current commit")

    # reset
    subparsers.add_parser("reset", parents=[common], help="Clear checkpoint file for current commit")

    args = parser.parse_args()
    args.commit = getattr(args, "commit", None)
    args.repo = getattr(args, "repo", None)
    args.resume_from = getattr(args, "resume_from", None)
    args.reset = getattr(args, "reset", False)

    if args.command == "run-typecheck":
        return cmd_run_typecheck(args)

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

