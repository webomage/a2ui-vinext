#!/usr/bin/env python3
"""Every `just <recipe>` inside a recipe body must name a recipe THAT justfile defines.

WHY THIS EXISTS
    T421 moved the deploy machinery to the estate-root justfile and carried
    `_post-deploy-knowledge` over verbatim: its body ran `just knowledge-light`, a recipe that
    exists only in `wom7api/justfile`. Every other root recipe delegates explicitly
    (`just --justfile wom7api/justfile …`); this one did not, and its `-` prefix turned
    `error: justfile does not contain recipe` into a green step. The owner's deploy-all on
    2026-09-24 printed the error and still ended `✅ exited 0` — the post-deploy knowledge refresh
    had not run once since the move (T431 run 7).

    `just` validates recipe DEPENDENCIES at parse time, but a body line is only a shell string, so
    nothing checks it until it runs — and a `-`-prefixed line never fails even then.

WHAT COUNTS AS A CALL
    A bare `just <name>` in a body line. Skipped, because they resolve against another justfile:
    `--justfile`/`-f`/`--working-directory`/`-d`, a `cd <dir> &&` earlier on the line, and names
    built from `{{ … }}` interpolation (not statically knowable — counted and reported, not guessed).

Exit 0 = every call resolves · 1 = at least one does not · 2 = could not measure (no recipes read).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# `just` + optional flags + the recipe token. Anchored so `adjust`/`justfile` never match.
CALL_RE = re.compile(r"(?<![\w./-])just((?:\s+-[^\s]+(?:\s+(?!-)[^\s-][^\s]*)?)*)\s+([A-Za-z_{][\w{}\s.-]*?)(?=\s|$|;|\)|&|\|)")
DELEGATING_FLAGS = ("--justfile", "-f", "--working-directory", "-d")


def dump(justfile: Path) -> dict | None:
    try:
        r = subprocess.run(["just", "--justfile", str(justfile), "--dump", "--dump-format", "json"],
                           cwd=justfile.parent, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    return json.loads(r.stdout)


def body_lines(recipe: dict) -> list[str]:
    # Each line is a list of fragments: plain strings, or nested lists for `{{ … }}`.
    # An interpolation is kept as a `{{}}` marker so a name built from one is recognisable.
    return ["".join(f if isinstance(f, str) else "{{}}" for f in line) for line in recipe["body"]]


def executable(line: str) -> str:
    """The part of a body line the shell would run as a command: no comment, no quoted text.

    The first run against wom7api flagged 4 "calls" that were English — `# … just like a real
    absence`, `echo "  just do <recipe>"`. A comment or a quoted string is not a call, and a check
    that cries wolf on prose gets switched off.
    """
    s = line.lstrip().lstrip("@-").lstrip()
    if s.startswith("#"):
        return ""
    return re.sub(r"'[^']*'|\"[^\"]*\"", "''", s)


def scan(data: dict) -> tuple[int, int, int, list[str]]:
    names = set(data["recipes"]) | set(data.get("aliases", {}))
    calls = dynamic = 0
    bad: list[str] = []
    for rname, recipe in sorted(data["recipes"].items()):
        for line in map(executable, body_lines(recipe)):
            for m in CALL_RE.finditer(line):
                flags, target = m.group(1), m.group(2).strip()
                if any(f in flags.split() for f in DELEGATING_FLAGS):
                    continue
                if re.search(r"\bcd\s+\S+.*&&", line[: m.start()]):
                    continue
                if "{{" in target:
                    dynamic += 1
                    continue
                target = target.split()[0]
                calls += 1
                if target not in names:
                    bad.append(f"{rname}: `just {target}` — no such recipe in this justfile")
    return len(data["recipes"]), calls, dynamic, bad


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--justfile", action="append", type=Path,
                    help="justfile to scan (repeatable); default: the estate root and wom7api")
    args = ap.parse_args()
    targets = args.justfile or [ROOT / "justfile", ROOT / "wom7api" / "justfile"]

    failed = unmeasured = False
    for jf in targets:
        data = dump(jf)
        if not data or not data.get("recipes"):
            print(f"❌ {jf}: could not read its recipes — cannot measure, so not passing")
            unmeasured = True
            continue
        n, calls, dynamic, bad = scan(data)
        for b in bad:
            print(f"  ✗ {b}")
        verdict = "❌" if bad else "✅"
        print(f"{verdict} {jf.relative_to(ROOT) if jf.is_relative_to(ROOT) else jf}: {calls} bare "
              f"`just` call(s) across {n} recipe(s), {len(bad)} unresolved, "
              f"{dynamic} dynamic (not checked)")
        failed |= bool(bad)
    return 2 if unmeasured else (1 if failed else 0)


if __name__ == "__main__":
    sys.exit(main())
