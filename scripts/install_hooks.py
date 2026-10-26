#!/usr/bin/env python3
"""w0m git-hook installer.

Installs the version-controlled `.pre-commit-config.yaml` (the single source of
truth) into every first-party wom7* repo using the pre-commit framework, for
both the pre-commit and commit-msg stages. This replaces the old approach that
wrote a bespoke `.git/hooks/pre-commit` pointing at an absolute path — those
were not reproducible across machines/clones and duplicated the framework.

Resolves `$GIT_COMMON_DIR/hooks` via `git rev-parse --git-common-dir` (T408) so
running `install_hooks.py` from either the primary checkout or a `git worktree`
installs and wraps hooks in the shared common hooks directory, while verifying
that repos with `core.hooksPath = .husky/_` (`w0m-web`) have tracked, executable
dispatcher shims (`pre-commit`, `commit-msg`, `pre-push`) present on disk.

Run from anywhere:  python3 scripts/install_hooks.py
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# Repo root is one level up from this file (…/@wom/scripts/…).
ROOT = Path(__file__).resolve().parents[1]

# First-party repos to standardize. The nested w0m-mlx/w0m-mlx is the real repo;
# the w0m-mlx/ parent is a workspace of vendored upstream clones and is skipped.
# The estate workspace repo itself (T294). It is not a `wom7*` directory, so the glob above cannot
# find it — and it is the one repo whose first commit ran through no hooks at all, because
# `.git/hooks` did not exist when it was created. Listing it here is what makes that a one-time
# condition rather than a standing one.
EXPLICIT = [ROOT / "w0m-mlx" / "w0m-mlx", ROOT]

REQUIRED_HUSKY_SHIMS = ("pre-commit", "commit-msg", "pre-push")

# The logging preamble injected into each generated hook. Kept as a SOURCE line rather than a copy
# of the logic: one wrapper, edited once, and a hook that cannot drift from its siblings.
#
# 🔴 NO ABSOLUTE PATHS. The installer's own docstring records why the previous approach was
# replaced — "pointing at an absolute path — those were not reproducible across machines/clones".
# The path is resolved at RUN time from the repo root (or `$GIT_COMMON_DIR` for standalone
# worktrees), trying the sibling layout (…/@wom/w0m-api) and then the nested one
# (…/@wom/w0m-mlx/w0m-mlx).
#
# ⚠️ `|| true` and `2>/dev/null`: a missing wrapper must degrade to NO LOGGING, never to a broken
# hook. Losing the log is an inconvenience; losing the gate is an incident.
WRAP_MARK = "w0m hook-log wrapper"
WRAP_TEMPLATE = """# {mark} — injected by scripts/install_hooks.py, re-applied on every install.
# `.git/hooks/` is NOT versioned, so this cannot live here permanently; the installer is the
# versioned surface and re-running it is what makes this reproducible.
W0M_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
W0M_COMMON="$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null)"
W0M_WRAP="$W0M_ROOT/scripts/hook_log_wrap.sh"
[ -f "$W0M_WRAP" ] || W0M_WRAP="$W0M_ROOT/../scripts/hook_log_wrap.sh"
[ -f "$W0M_WRAP" ] || W0M_WRAP="$W0M_ROOT/../../scripts/hook_log_wrap.sh"
[ -f "$W0M_WRAP" ] || W0M_WRAP="$W0M_ROOT/../w0m-web/scripts/hook_log_wrap.sh"
[ -f "$W0M_WRAP" ] || W0M_WRAP="$W0M_ROOT/../../w0m-web/scripts/hook_log_wrap.sh"
[ -f "$W0M_WRAP" ] || W0M_WRAP="$W0M_ROOT/w0m-web/scripts/hook_log_wrap.sh"
[ -f "$W0M_WRAP" ] || W0M_WRAP="$W0M_COMMON/../scripts/hook_log_wrap.sh"
[ -f "$W0M_WRAP" ] || W0M_WRAP="$W0M_COMMON/../../scripts/hook_log_wrap.sh"
[ -f "$W0M_WRAP" ] || W0M_WRAP="$W0M_COMMON/../../w0m-web/scripts/hook_log_wrap.sh"
[ -f "$W0M_WRAP" ] || W0M_WRAP="$W0M_COMMON/../../../w0m-web/scripts/hook_log_wrap.sh"
[ -f "$W0M_WRAP" ] || W0M_WRAP="$W0M_COMMON/../w0m-web/scripts/hook_log_wrap.sh"
[ -f "$W0M_WRAP" ] && W0M_HOOK_NAME={hook} . "$W0M_WRAP" 2>/dev/null || true
"""

WRAP_SNIPPET = WRAP_TEMPLATE.format(mark=WRAP_MARK, hook="pre-commit")

ROOT_PRE_PUSH_SCRIPT = (
    "#!/usr/bin/env sh\n"
    + WRAP_TEMPLATE.format(mark=WRAP_MARK, hook="pre-push")
    + """if [ -n "$W0M_ROOT" ] && [ -f "$W0M_ROOT/scripts/root_pre_push.py" ]; then
  exec python3 "$W0M_ROOT/scripts/root_pre_push.py" "$@"
elif [ -n "$W0M_ROOT" ] && [ -f "$W0M_ROOT/../scripts/stale_path_check.py" ]; then
  python3 "$W0M_ROOT/../scripts/stale_path_check.py" || exit 1
  exec python3 "$W0M_ROOT/../scripts/justfile_calls_check.py"
elif [ -n "$W0M_COMMON" ] && [ -f "$W0M_COMMON/../scripts/root_pre_push.py" ]; then
  exec python3 "$W0M_COMMON/../scripts/root_pre_push.py" "$@"
fi
exit 0
"""
)


def common_hooks_dir(repo: Path) -> Path:
    """Resolve `$GIT_COMMON_DIR/hooks` so worktrees and primary checkouts share one hooks path."""
    res = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--git-common-dir"],
        capture_output=True,
        text=True,
    )
    if res.returncode == 0 and res.stdout.strip():
        return (repo / res.stdout.strip()).resolve() / "hooks"
    return repo / ".git" / "hooks"


def inject_logging(repo: Path, hook: str = "pre-commit") -> str:
    """Add the run-logging preamble to a generated hook, after its shebang. Idempotent.

    Returns a short status for the caller to print. Never raises: a failure to add LOGGING must
    not fail the hook INSTALL, or a cosmetic feature becomes a reason the gates are missing.
    """
    f = common_hooks_dir(repo) / hook
    snippet = WRAP_TEMPLATE.format(mark=WRAP_MARK, hook=hook)
    try:
        if not f.exists():
            return "no hook to wrap"
        body = f.read_text()
        if WRAP_MARK in body:
            return "logging already wrapped"
        lines = body.splitlines(keepends=True)
        # After the shebang, which must stay on line 1 or the kernel picks the wrong interpreter.
        at = 1 if lines and lines[0].startswith("#!") else 0
        f.write_text("".join(lines[:at]) + snippet + "".join(lines[at:]))
        f.chmod(0o755)
        return "logging wrapped"
    except OSError as exc:
        return f"logging NOT wrapped ({exc})"


def ensure_root_pre_push(repo: Path) -> str:
    """Ensure the estate root repo has a pre-push hook delegating to `scripts/root_pre_push.py`."""
    hooks_dir = common_hooks_dir(repo)
    f = hooks_dir / "pre-push"
    try:
        hooks_dir.mkdir(parents=True, exist_ok=True)
        if not f.exists() or f.read_text() != ROOT_PRE_PUSH_SCRIPT:
            f.write_text(ROOT_PRE_PUSH_SCRIPT)
            f.chmod(0o755)
            return "pre-push installed"
        f.chmod(0o755)
        return "pre-push verified"
    except OSError as exc:
        return f"pre-push NOT installed ({exc})"


def discover_repos() -> list[Path]:
    repos: list[Path] = []
    for d in sorted(list(ROOT.glob("w0m-*")) + list(ROOT.glob("wom7*"))):
        if (d / ".git").exists() and (d / ".pre-commit-config.yaml").exists() and d not in repos:
            repos.append(d)
    for d in EXPLICIT:
        if (d / ".git").exists() and (d / ".pre-commit-config.yaml").exists() and d not in repos:
            repos.append(d)
    return repos


def custom_hooks_path(repo: Path) -> str:
    """Return configured `core.hooksPath` if set, or empty string."""
    res = subprocess.run(
        ["git", "-C", str(repo), "config", "--get", "core.hooksPath"],
        capture_output=True,
        text=True,
    )
    return res.stdout.strip() if res.returncode == 0 else ""


def hooks_path_is_custom(repo: Path) -> bool:
    """True when the repo delegates hooks elsewhere (e.g. husky). pre-commit
    refuses to install over a custom core.hooksPath, so we let that repo's own
    tooling invoke `pre-commit run` instead."""
    return custom_hooks_path(repo) != ""


def verify_custom_hooks(repo: Path, hooks_rel: str) -> tuple[bool, str]:
    """Fail closed if a repo's custom `core.hooksPath` (e.g. `.husky/_`) is missing or non-executable."""
    hooks_dir = repo / hooks_rel
    if not hooks_dir.is_dir():
        return False, f"core.hooksPath={hooks_rel!r} directory is missing at {hooks_dir}"
    missing: list[str] = []
    for shim in REQUIRED_HUSKY_SHIMS:
        shim_path = hooks_dir / shim
        if not shim_path.is_file():
            missing.append(shim)
            continue
        try:
            shim_path.chmod(0o755)
        except OSError:
            pass
        if not os.access(shim_path, os.X_OK):
            missing.append(f"{shim} (not executable)")
    if missing:
        return False, f"core.hooksPath={hooks_rel!r} missing required hook shim(s): {', '.join(missing)}"
    return True, f"custom core.hooksPath ({hooks_rel}) verified ({', '.join(REQUIRED_HUSKY_SHIMS)} executable)"


def main() -> int:
    repos = discover_repos()
    if not repos:
        print("No wom7* repos with a .pre-commit-config.yaml found under", ROOT)
        return 1

    failures: list[str] = []
    for repo in repos:
        name = "." if repo == ROOT else str(repo.relative_to(ROOT))
        if (repo / ".husky").is_dir() and not hooks_path_is_custom(repo):
            subprocess.run(
                ["git", "-C", str(repo), "config", "core.hooksPath", ".husky/_"],
                capture_output=True,
                text=True,
            )
        if hooks_path_is_custom(repo):
            ok, msg = verify_custom_hooks(repo, custom_hooks_path(repo))
            if ok:
                print(f"✅ {name}: {msg}")
            else:
                print(f"❌ {name}: {msg}")
                failures.append(name)
            continue
        # Drop any stale bespoke hook left by the old installer so the framework
        # hook is the only pre-commit hook.
        hdir = common_hooks_dir(repo)
        legacy = hdir / "pre-commit.legacy"
        if legacy.exists():
            legacy.unlink()
        res = subprocess.run(
            [
                "pre-commit",
                "install",
                "--overwrite",
                "--hook-type",
                "pre-commit",
                "--hook-type",
                "commit-msg",
            ],
            cwd=str(repo),
            capture_output=True,
            text=True,
        )
        if res.returncode == 0:
            note = inject_logging(repo, "pre-commit")
            commit_msg_note = inject_logging(repo, "commit-msg")
            extra = ""
            if repo in (ROOT, ROOT / "w0m-api"):
                extra = f" · {ensure_root_pre_push(repo)}"
            print(
                f"✅ {name}: {res.stdout.strip() or 'installed'} · pre-commit:{note} · commit-msg:{commit_msg_note}{extra}"
            )
        else:
            print(f"❌ {name}: {res.stderr.strip() or res.stdout.strip()}")
            failures.append(name)

    if failures:
        print("\nFailed:", ", ".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
