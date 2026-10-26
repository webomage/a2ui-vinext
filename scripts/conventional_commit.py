#!/usr/bin/env python3
"""Canonical commit-msg gate for all w0m estate repos (T129, T386).

Enforces:
1. Conventional Commits format (`type(scope): description`).
2. Structural SDLC ticket reference (`\\bT[0-9]+\\b`) in subject or body for all
   non-trivial commit types (`feat`, `fix`, `refactor`, `perf`, `test`,
   `security`, `build`).
3. Calibrated exemptions (`chore`, `docs`, `style`, `ci`, `revert`) plus
   synthetic git subjects (`Merge `, `Revert `, `fixup!`, `squash!`), with an
   anti-dodge check that refuses unticketed exempt commits when staged files
   touch substantive code, runtime packages, or database migrations (T129 AC2).
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Sequence

ALLOWED_COMMIT_TYPES: tuple[str, ...] = (
    "feat",
    "fix",
    "docs",
    "style",
    "refactor",
    "perf",
    "test",
    "security",
    "build",
    "ci",
    "chore",
    "revert",
)

TICKET_REQUIRED_COMMIT_TYPES: frozenset[str] = frozenset(
    {
        "feat",
        "fix",
        "refactor",
        "perf",
        "test",
        "security",
        "build",
    }
)

EXEMPT_COMMIT_TYPES: frozenset[str] = frozenset(
    {
        "chore",
        "docs",
        "style",
        "ci",
        "revert",
    }
)

SYNTHETIC_SUBJECT_PREFIXES: tuple[str, ...] = (
    "Merge ",
    "Revert ",
    "fixup!",
    "squash!",
)

CC_RE: re.Pattern[str] = re.compile(
    r"^(?P<type>"
    + "|".join(ALLOWED_COMMIT_TYPES)
    + r")(?:\((?P<scope>[^)]+)\))?(?P<breaking>!)?:\s+(?P<desc>.+)$"
)

TICKET_RE: re.Pattern[str] = re.compile(r"\bT[0-9]+\b")

SUBSTANTIVE_CODE_EXTS: frozenset[str] = frozenset(
    {
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".mjs",
        ".cjs",
        ".astro",
        ".svelte",
        ".py",
        ".rs",
        ".go",
        ".sql",
        ".sh",
        ".tf",
        ".tfvars",
    }
)

SUBSTANTIVE_PATH_PREFIXES: tuple[str, ...] = (
    "apps/",
    "packages/",
    "src/",
    "supabase/migrations/",
    "supabase/functions/",
    "worker/",
    "functions/",
    "scripts/",
    "project/scripts/",
    "w0m-web/apps/",
    "w0m-web/packages/",
    "w0m-web/project/scripts/",
    "w0m-api/supabase/migrations/",
    "w0m-api/supabase/functions/",
    "w0m-cf/src/",
    "w0m-ext/extension/",
    "w0m-skills/scripts/",
    "w0m-mlx/w0m-mlx/src/",
)


def strip_comment_lines(raw_text: str) -> str:
    """Strip git commit comment lines starting with `#`."""
    lines = [
        line
        for line in raw_text.splitlines()
        if not line.lstrip().startswith("#")
    ]
    return "\n".join(lines).strip()


def get_staged_files(cwd: Path | None = None) -> list[str]:
    """Return list of staged file paths from git index, or empty list if unavailable."""
    try:
        proc = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            cwd=str(cwd) if cwd is not None else None,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return []
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def classify_substantive_staged_files(staged_files: Sequence[str]) -> list[str]:
    """Return staged paths that represent substantive code, schema, or runtime changes."""
    substantive: list[str] = []
    for raw_path in staged_files:
        norm = raw_path.strip().lstrip("./")
        if not norm:
            continue
        p = Path(norm)
        if p.suffix.lower() in SUBSTANTIVE_CODE_EXTS:
            substantive.append(norm)
            continue
        if any(norm.startswith(prefix) for prefix in SUBSTANTIVE_PATH_PREFIXES):
            substantive.append(norm)
    return substantive


def validate_commit_message(
    raw_text: str,
    *,
    staged_files: Sequence[str] | None = None,
    check_staged: bool = True,
) -> tuple[bool, str]:
    """Validate commit message text against Conventional Commits + T129 T## gate."""
    cleaned = strip_comment_lines(raw_text)
    lines = cleaned.splitlines()
    subject = lines[0].strip() if lines else ""

    if not subject:
        return False, "✗ empty commit message subject"

    if subject.startswith(SYNTHETIC_SUBJECT_PREFIXES):
        return True, ""

    match = CC_RE.match(subject)
    if not match:
        return (
            False,
            f"✗ not a Conventional Commit subject:\n    {subject[:100]}\n"
            "  expected: type(scope): description   e.g. `feat(cp): add tenant switcher (T129)`",
        )

    commit_type = match.group("type")
    has_ticket = bool(TICKET_RE.search(cleaned))

    if commit_type in TICKET_REQUIRED_COMMIT_TYPES:
        if not has_ticket:
            return (
                False,
                f"✗ `{commit_type}` commit requires a ticket reference (T##) in subject or body:\n"
                f"    {subject[:100]}\n"
                "  expected: e.g. `feat(scope): summary (T129)` or `Refs: T129` in commit body.\n"
                "  Rule (T129): create/claim the ticket BEFORE writing or committing non-trivial work.",
            )
        return True, ""

    if commit_type in EXEMPT_COMMIT_TYPES and not has_ticket and check_staged:
        files_to_check = (
            list(staged_files) if staged_files is not None else get_staged_files()
        )
        substantive = classify_substantive_staged_files(files_to_check)
        if substantive:
            sample = ", ".join(substantive[:5])
            more = f" (+{len(substantive) - 5} more)" if len(substantive) > 5 else ""
            return (
                False,
                f"✗ unticketed `{commit_type}:` commit cannot stage substantive code/migration files (T129 anti-dodge):\n"
                f"    subject: {subject[:100]}\n"
                f"    staged:  {sample}{more}\n"
                "  Either reference the governing ticket (`T##`) or use the proper commit type (`feat`/`fix`/`refactor`/`test`) with a ticket.",
            )

    return True, ""


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate commit-msg for Conventional Commits + w0m T## ticket gate (T129, T386)."
    )
    parser.add_argument(
        "message_file",
        help="Path to the git commit message file (e.g. .git/COMMIT_EDITMSG).",
    )
    parser.add_argument(
        "--check-staged",
        dest="check_staged",
        action="store_true",
        default=True,
        help="Inspect staged files on unticketed exempt commit types (default: enabled).",
    )
    parser.add_argument(
        "--no-check-staged",
        dest="check_staged",
        action="store_false",
        help="Disable staged-file inspection (for message-only unit tests).",
    )
    parser.add_argument(
        "--staged-files",
        nargs="*",
        default=None,
        help="Explicit list of staged file paths to evaluate instead of querying `git diff --cached`.",
    )
    args = parser.parse_args(list(argv) if argv is not None else sys.argv[1:])

    msg_path = Path(args.message_file)
    if not msg_path.is_file():
        print(f"✗ commit message file not found: {msg_path}", file=sys.stderr)
        return 1

    raw_text = msg_path.read_text(encoding="utf-8", errors="replace")
    ok, error_msg = validate_commit_message(
        raw_text,
        staged_files=args.staged_files,
        check_staged=args.check_staged,
    )
    if not ok:
        print(error_msg)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
