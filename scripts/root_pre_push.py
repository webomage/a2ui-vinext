#!/usr/bin/env python3
"""root_pre_push.py (T527 AC1) — Pre-push gate for the estate root repository (@wom).

Why this exists:
`STATE.md`, `TASKS.md`, `.tasks/`, and `ROADMAP.md` moved to the estate root repo (`@wom`) in T414,
while `w0m-web/.husky/pre-push` continued looking for them inside `w0m-web`'s own push range and
`@wom` had no pre-push hook at all. As a result, `state-check` never ran on any push and only failed
inside `just deploy-all` preflight (2026-10-01).

When pushing `@wom`, this hook inspects the push range (from git pre-push stdin refs, `--range`, or
`origin/<branch>..HEAD`) for changes matching `^(STATE\\.md|TASKS\\.md|\\.tasks/|ROADMAP\\.md)`.
When any tracking surface is touched in the push range:
  1. Verifies every `.tasks/T*.md` ticket has a board row in `TASKS.md` (`ticket_row_check`).
  2. Runs `state-check` (`python3 scripts/state_doctor.py --check`) and blocks the push on drift.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ticket_row_check  # noqa: E402

TRACKING_SCOPE_RE = re.compile(r"^(STATE\.md|TASKS\.md|\.tasks/|ROADMAP\.md)")
CATALOG_SCOPE_RE = re.compile(
    r"^(\.w0m/sdlc\.json|\.w0m/skills\.json|project/policies/stacks-policy\.json|catalog-info\.yaml)$"
)
ZERO_SHA_RE = re.compile(r"^0+$")


GIT_HOOK_ENV_VARS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_PREFIX",
    "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
)


def _clean_git_env() -> dict[str, str]:
    """Strip git-hook-injected GIT_* variables so `-C <repo>` and child repos resolve their own .git."""
    env = {k: v for k, v in os.environ.items() if k not in GIT_HOOK_ENV_VARS}
    env["LC_ALL"] = "C"
    return env


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        env=_clean_git_env(),
    )


def _files_in_range(root: Path, base_ref: str, head_ref: str) -> list[str]:
    res = _git(root, "diff", "--name-only", base_ref, head_ref)
    if res.returncode != 0:
        return []
    return [ln.strip() for ln in res.stdout.splitlines() if ln.strip()]


def _files_at_commit(root: Path, rev: str) -> list[str]:
    res = _git(root, "ls-tree", "-r", "--name-only", rev)
    if res.returncode != 0:
        return []
    return [ln.strip() for ln in res.stdout.splitlines() if ln.strip()]


def collect_pushed_files(
    root: Path,
    *,
    explicit_range: str | None = None,
    stdin_lines: list[str] | None = None,
) -> list[str]:
    """Resolve the list of repo-relative paths modified in the root push range."""
    if explicit_range:
        if ".." in explicit_range:
            base_ref, head_ref = explicit_range.split("..", 1)
            return _files_in_range(root, base_ref, head_ref)
        return _files_at_commit(root, explicit_range)

    if stdin_lines is None and not sys.stdin.isatty():
        try:
            raw = sys.stdin.read()
            stdin_lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        except OSError:
            stdin_lines = []

    if stdin_lines:
        touched: set[str] = set()
        saw_ref = False
        for line in stdin_lines:
            parts = line.split()
            if len(parts) < 4:
                continue
            saw_ref = True
            _local_ref, local_sha, _remote_ref, remote_sha = parts[:4]
            if ZERO_SHA_RE.match(local_sha):
                continue  # branch deletion
            if ZERO_SHA_RE.match(remote_sha):
                if _git(root, "rev-parse", "--verify", "-q", "origin/beta").returncode == 0:
                    touched.update(_files_in_range(root, "origin/beta", local_sha))
                else:
                    touched.update(_files_at_commit(root, local_sha))
            else:
                touched.update(_files_in_range(root, remote_sha, local_sha))
        if saw_ref:
            return sorted(touched)

    branch_res = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    branch = branch_res.stdout.strip() if branch_res.returncode == 0 else "beta"
    for candidate in (f"origin/{branch}", "origin/beta"):
        if _git(root, "rev-parse", "--verify", "-q", candidate).returncode == 0:
            return _files_in_range(root, candidate, "HEAD")

    return _files_at_commit(root, "HEAD")


def run_state_check(root: Path) -> tuple[int, str]:
    """Run state-check against the root repo."""
    clean_env = _clean_git_env()
    custom_cmd = os.environ.get("W0M_STATE_CHECK_CMD")
    if custom_cmd:
        res = subprocess.run(
            custom_cmd,
            shell=True,
            cwd=str(root),
            capture_output=True,
            text=True,
            env=clean_env,
        )
        return res.returncode, (res.stdout + res.stderr).strip()

    doctor = root / "scripts" / "state_doctor.py"
    if not doctor.is_file():
        return 0, ""

    res = subprocess.run(
        [sys.executable, str(doctor), "--check"],
        cwd=str(root),
        capture_output=True,
        text=True,
        env=clean_env,
    )
    return res.returncode, (res.stdout + res.stderr).strip()


def run_catalog_check(root: Path) -> tuple[int, str]:
    """Run Backstage catalog drift check against the root repo (T657 AC4)."""
    clean_env = _clean_git_env()
    custom_cmd = os.environ.get("W0M_CATALOG_CHECK_CMD")
    if custom_cmd:
        res = subprocess.run(
            custom_cmd,
            shell=True,
            cwd=str(root),
            capture_output=True,
            text=True,
            env=clean_env,
        )
        return res.returncode, (res.stdout + res.stderr).strip()

    catalog_script = root / "w0m-web" / "project" / "scripts" / "catalog_sync.py"
    if not catalog_script.is_file():
        return 0, ""

    res = subprocess.run(
        [sys.executable, str(catalog_script), "--check"],
        cwd=str(root),
        capture_output=True,
        text=True,
        env=clean_env,
    )
    return res.returncode, (res.stdout + res.stderr).strip()


def main(argv: list[str] | None = None) -> int:
    if os.environ.get("W0M_ROOT_PREPUSH_SKIP") == "1":
        return 0

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Override estate root directory.",
    )
    ap.add_argument(
        "--range",
        dest="push_range",
        default=None,
        help="Explicit git range (<base>..<head>) to inspect instead of stdin.",
    )
    args, _unknown = ap.parse_known_args(argv)

    root = (
        args.root.resolve()
        if args.root is not None
        else Path(os.environ.get("W0M_ROOT") or Path(__file__).resolve().parents[1]).resolve()
    )

    pushed_files = collect_pushed_files(root, explicit_range=args.push_range)
    touched_tracking = [f for f in pushed_files if TRACKING_SCOPE_RE.search(f)]
    touched_catalog = [f for f in pushed_files if CATALOG_SCOPE_RE.search(f)]

    if not touched_tracking and not touched_catalog:
        print("  → [@wom] tracking surfaces untouched in push range; state-check skipped.")
        return 0

    if touched_tracking:
        print(
            f"⏳ [@wom] Pre-push: tracking surfaces touched ({', '.join(touched_tracking[:5])}) "
            "— running ticket-row-check + state-check..."
        )

        # 1. Verify every .tasks/T*.md ticket has a row in TASKS.md (T527 AC1 red probe)
        ok_rows, missing_rows, _ = ticket_row_check.check_ticket_rows(
            root, auto_render=False, stage=False
        )
        if not ok_rows:
            print(
                f"❌ [@wom] Pre-push blocked: newly invisible ticket(s) in .tasks/ with no row in TASKS.md: "
                f"{', '.join(missing_rows)} (run 'just tasks-render' and commit TASKS.md).",
                file=sys.stderr,
            )
            return 1

        # 2. Run state-check (scripts/state_doctor.py --check)
        rc, out = run_state_check(root)
        if out:
            print(out, file=sys.stderr if rc != 0 else sys.stdout)
        if rc != 0:
            print(
                "❌ [@wom] Pre-push blocked: state-check failed (run 'just state-save' and commit STATE.md).",
                file=sys.stderr,
            )
            return 1

    if touched_catalog:
        print(
            f"⏳ [@wom] Pre-push: catalog surfaces touched ({', '.join(touched_catalog[:5])}) "
            "— running catalog-check..."
        )
        rc_cat, out_cat = run_catalog_check(root)
        if out_cat:
            print(out_cat, file=sys.stderr if rc_cat != 0 else sys.stdout)
        if rc_cat != 0:
            print(
                "❌ [@wom] Pre-push blocked: catalog-check failed (run 'just catalog-sync' and commit catalog-info.yaml + w0m-web/project/catalog-entities.json).",
                file=sys.stderr,
            )
            return 1

    print("✅ [@wom] Pre-push checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
