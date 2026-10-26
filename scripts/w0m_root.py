#!/usr/bin/env python3
"""Canonical fail-closed @wom workspace root resolver and escaping-symlink detector (T427 / AgDR-0025).

Provides a single deterministic resolution contract for `@wom` scripts without
multi-path fallback search ladders or cross-repository shadow symlinks:
1. If `W0M_ROOT` is set in the environment, validate that `<W0M_ROOT>/.w0m/sdlc.json`
   exists and return the resolved `Path`. If invalid, fail closed (`RuntimeError`).
2. If `require_env=True` and `W0M_ROOT` is unset/empty, fail closed (`RuntimeError`).
3. Otherwise resolve deterministically from the script's fixed structural depth and
   validate `<root>/.w0m/sdlc.json`.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def _validate_estate_root(candidate: Path, source: str) -> Path:
    resolved = candidate.expanduser().resolve()
    sdlc_path = resolved / ".w0m" / "sdlc.json"
    if not resolved.is_dir() or not sdlc_path.is_file():
        raise RuntimeError(
            f"Invalid w0m estate root from {source}: '{candidate}' "
            f"(missing '{sdlc_path}'; T427 / AgDR-0025 fail-closed check)."
        )
    return resolved


def resolve_w0m_root(
    anchor: Path | str | None = None,
    *,
    require_env: bool = False,
    env: dict[str, str] | None = None,
) -> Path:
    """Resolve the `@wom` workspace root deterministically and fail closed on invalid state."""
    environ = os.environ if env is None else env
    raw_env = environ.get("W0M_ROOT", "").strip()
    if raw_env:
        return _validate_estate_root(Path(raw_env), "W0M_ROOT")

    if require_env:
        raise RuntimeError(
            "W0M_ROOT environment variable is unset; required by T427 / AgDR-0025 fail-closed contract."
        )

    here = Path(anchor).resolve() if anchor is not None else Path(__file__).resolve()
    if here.is_file():
        here = here.parent

    # Fixed structural depth: either `<root>/scripts` (depth 1) or `<root>/w0m-web/project/scripts` (depth 3).
    if here.name == "scripts" and here.parent.name == "project" and here.parent.parent.name == "w0m-web":
        candidate = here.parents[2]
    elif here.name == "scripts":
        candidate = here.parent
    else:
        candidate = here

    return _validate_estate_root(candidate, f"anchor:{here}")


def find_escaping_tracked_symlinks(repo_dir: Path) -> list[tuple[str, str]]:
    """Return tracked git symlinks (`120000`) in `repo_dir` whose target escapes `repo_dir`."""
    repo_root = repo_dir.resolve()
    proc = subprocess.run(
        ["git", "-C", str(repo_root), "ls-files", "-s"],
        capture_output=True,
        text=True,
        check=True,
    )
    escaping: list[tuple[str, str]] = []
    for line in proc.stdout.splitlines():
        if not line.startswith("120000 "):
            continue
        _, rel_path = line.split("\t", 1)
        link_path = repo_root / rel_path
        if not link_path.is_symlink():
            continue
        raw_target = os.readlink(link_path)
        resolved_target = (link_path.parent / raw_target).resolve()
        try:
            resolved_target.relative_to(repo_root)
        except ValueError:
            escaping.append((rel_path, raw_target))
    return escaping


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Resolve @wom root and audit escaping tracked symlinks (T427).")
    parser.add_argument(
        "--require-env",
        action="store_true",
        help="Require W0M_ROOT environment variable to be explicitly set.",
    )
    parser.add_argument(
        "--check-symlinks",
        nargs="*",
        metavar="REPO",
        help="Verify that the given repositories contain zero tracked escaping symlinks.",
    )
    args = parser.parse_args(argv)

    try:
        root = resolve_w0m_root(require_env=args.require_env)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.check_symlinks is not None:
        repos = args.check_symlinks or ["w0m-api", "w0m-cf"]
        violations: list[str] = []
        for repo in repos:
            repo_path = (root / repo) if not Path(repo).is_absolute() else Path(repo)
            for rel_path, target in find_escaping_tracked_symlinks(repo_path):
                violations.append(f"{repo}:{rel_path} -> {target}")
        if violations:
            for v in violations:
                print(f"ESCAPING_SYMLINK: {v}", file=sys.stderr)
            return 1

    print(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
