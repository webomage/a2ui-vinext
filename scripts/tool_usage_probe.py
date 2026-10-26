#!/usr/bin/env python3
"""T164 AC1 — which host CLIs does the estate ACTUALLY invoke, and are all candidates accounted for?

`project/policies/tools-policy.json` (configured in `.w0m/sdlc.json -> toolchain.policy`) must be
filtered by real usage, not by what happens to be installed on a workstation. This is the probe
that decides, kept re-runnable so the answer can be re-derived instead of trusted.

Method, and why it is not a grep
--------------------------------
A naive `grep -c '<tool>'` over the estate reported **tree=73** and **uv=67**. Both were prose:
"worktree" matches `tree`, "uvx" matches `uv`, and Python/TS locals named `tree`, `fd`, `rg`, `sg`
matched too.

So a tool counts only where it is invoked as a command:
1. In shell/justfile/Makefile/hook/YAML files: command position — start of line, or after a pipe,
   `&&`, `||`, `;`, backtick, `$(`, `xargs`, `sudo`, `then`/`do`/`else`, or `sh -c '...'`, on
   non-comment lines, and not followed by `:` or `=` (which are YAML keys or variable assignments).
2. In Python/JS/TS scripts (excluding test fixtures and this probe): argv0 of `subprocess.*`,
   `execFileSync`/`execSync`/`spawn*`, `shutil.which`, or local `sh([...])`/`run([...])` helpers.

Symlinked files (e.g. `wom7web/justfile -> ../wom7api/justfile`) are deduplicated by resolved path
so canonical `justfile` invocations are counted once.

Every candidate in `TOOLS` must be either:
- governed in `tools-policy.json -> tools` (with `min`, `known_good`, `required`, `source`, `auto`, `note`), or
- recorded in `tools-policy.json -> out_of_scope` with a non-empty written reason and 0 measured uses.

Exits non-zero on an empty corpus or when `--check` detects an unaccounted or misclassified tool.
"""
from __future__ import annotations

import argparse
from collections.abc import Iterable, Iterator
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

# scripts/ -> the estate root
ROOT = Path(__file__).resolve().parents[1]
SDLC_JSON = ROOT / ".w0m" / "sdlc.json"

REPOS = [
    ".",
    "wom7web",
    "wom7api",
    "wom7func",
    "wom7ext",
    "wom7skills",
    "wom7sec",
    "wom7mlx/wom7mlx",
]

# Full T164 candidate CLI surface (20 host inventory candidates + 7 initial probe candidates).
TOOLS = [
    "ansible",
    "ast-grep",
    "bat",
    "cargo",
    "cmake",
    "direnv",
    "docker",
    "fd",
    "go",
    "helm",
    "java",
    "jq",
    "kubectl",
    "ncdu",
    "pip3",
    "podman",
    "psql",
    "redis-cli",
    "rg",
    "ruff",
    "rustc",
    "sg",
    "sqlite3",
    "tree",
    "uv",
    "wget",
    "yq",
]

SHELL_SUFFIXES = {".sh", ".bash", ".zsh", ".just", ".yml", ".yaml"}
CODE_SUFFIXES = {".py", ".mjs", ".js", ".ts"}
SUFFIXES = SHELL_SUFFIXES | CODE_SUFFIXES
NAMES = {"justfile", "Makefile", "pre-commit", "pre-push", "commit-msg", "post-commit"}

SHELL_PREFIX = r"(?:^|\|\||&&|[|;`]|\$\(|\b(?:xargs|sudo|then|do|else)\s+|\bsh\s+-c\s+[\"\x27])\s*"


def resolve_policy_path(root: Path | None = None) -> Path:
    """Resolve `tools-policy.json` from `.w0m/sdlc.json -> toolchain.policy` (AC5)."""
    base = root or ROOT
    sdlc_file = base / ".w0m" / "sdlc.json"
    if sdlc_file.is_file():
        try:
            cfg: dict[str, Any] = json.loads(sdlc_file.read_text(encoding="utf-8"))
            tc = cfg.get("toolchain")
            if isinstance(tc, dict):
                rel = tc.get("policy")
                if isinstance(rel, str) and rel.strip():
                    return base / rel.strip()
        except (OSError, ValueError):
            pass
    return base / "project" / "policies" / "tools-policy.json"


def candidate_files(root: Path | None = None) -> Iterator[Path]:
    """Yield deduplicated git-tracked script/justfile/hook files across the estate."""
    base = root or ROOT
    seen: set[Path] = set()
    for repo in REPOS:
        d = base if repo == "." else (base / repo)
        if not (d / ".git").exists():
            continue
        out = subprocess.run(
            ["git", "-C", str(d), "ls-files"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.split("\n")
        for rel in out:
            if not rel:
                continue
            p = d / rel
            if p.name in NAMES or p.suffix in SUFFIXES:
                try:
                    real = p.resolve()
                except OSError:
                    continue
                if real not in seen:
                    seen.add(real)
                    yield p
        hooks = d / ".git" / "hooks"
        if hooks.is_dir():
            for p in hooks.iterdir():
                if p.is_file() and not p.name.endswith(".sample"):
                    try:
                        real = p.resolve()
                    except OSError:
                        continue
                    if real not in seen:
                        seen.add(real)
                        yield p


def _is_test_or_self(path: Path) -> bool:
    s = path.as_posix()
    return (
        path.name == "tool_usage_probe.py"
        or "/tests/" in s
        or s.endswith("_test.py")
        or s.endswith(".test.ts")
        or s.endswith(".spec.ts")
    )


def scan_usage(
    tools: list[str] | None = None,
    files: Iterable[Path] | None = None,
    root: Path | None = None,
) -> tuple[int, dict[str, list[tuple[int, str]]]]:
    """Scan `files` once and return `(scanned_file_count, {tool: [(count, rel_path), ...]})`."""
    base = root or ROOT
    target_tools = list(tools) if tools is not None else list(TOOLS)
    alt = "|".join(re.escape(t) for t in sorted(target_tools, key=len, reverse=True))
    shell_pat = re.compile(
        SHELL_PREFIX + rf"(?P<tool>{alt})(?=\s|$|[\"\x27])(?!\s*[:=])",
        re.M,
    )
    code_pat = re.compile(
        r"(?:subprocess\.(?:run|Popen|call|check_output|check_call)|execFileSync|execSync|spawnSync|spawn|shutil\.which|\bsh|\brun)\s*\(\s*\[?\s*[\"\x27](?P<tool>"
        + alt
        + r")[\"\x27]"
    )
    hits: dict[str, list[tuple[int, str]]] = {t: [] for t in target_tools}
    scanned = 0

    iterable = files if files is not None else candidate_files(base)
    for p in iterable:
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        scanned += 1
        if _is_test_or_self(p):
            continue
        try:
            rel_str = str(p.relative_to(base))
        except ValueError:
            rel_str = str(p)

        is_shell = p.name in NAMES or p.suffix in SHELL_SUFFIXES
        if is_shell:
            clean_shell = "\n".join(
                ln.lstrip()
                for ln in text.splitlines()
                if ln.strip() and not ln.lstrip().startswith(("#", "//"))
            )
            counts: dict[str, int] = {}
            for m in shell_pat.finditer(clean_shell):
                t = m.group("tool")
                counts[t] = counts.get(t, 0) + 1
            for t, n in counts.items():
                hits[t].append((n, rel_str))
        elif p.suffix in CODE_SUFFIXES:
            counts_code: dict[str, int] = {}
            for m in code_pat.finditer(text):
                t = m.group("tool")
                counts_code[t] = counts_code.get(t, 0) + 1
            for t, n in counts_code.items():
                hits[t].append((n, rel_str))

    return scanned, hits


def verify_policy_coverage(
    policy: dict[str, Any],
    hits: dict[str, list[tuple[int, str]]],
    candidates: list[str] | None = None,
) -> list[str]:
    """Verify every candidate CLI is either governed in `tools` or reasoned in `out_of_scope` (AC1)."""
    problems: list[str] = []
    governed = policy.get("tools")
    out_of_scope = policy.get("out_of_scope")
    if not isinstance(governed, dict) or not governed:
        return ["tools-policy.json: `tools` map is missing or empty"]
    if not isinstance(out_of_scope, dict) or not out_of_scope:
        return ["tools-policy.json: `out_of_scope` map is missing or empty"]

    overlap = sorted(set(governed) & set(out_of_scope))
    if overlap:
        problems.append(
            f"tools-policy.json: tool(s) declared in BOTH `tools` and `out_of_scope`: {', '.join(overlap)}"
        )

    for tool, reason in sorted(out_of_scope.items()):
        if tool.startswith("_"):
            continue
        if not isinstance(reason, str) or not reason.strip():
            problems.append(f"{tool}: `out_of_scope` entry must have a non-empty written reason")

    target_candidates = candidates if candidates is not None else list(TOOLS)
    for t in target_candidates:
        total = sum(n for n, _ in hits.get(t, []))
        in_gov = t in governed
        in_oos = t in out_of_scope
        if not in_gov and not in_oos:
            problems.append(
                f"{t}: unaccounted candidate CLI (uses={total}) — must be governed in `tools` or documented in `out_of_scope`"
            )
        elif in_oos and total > 0:
            problems.append(
                f"{t}: recorded in `out_of_scope` but has {total} real command/subprocess invocation(s) — govern it in `tools`"
            )
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="T164 AC1 — Host CLI command-position usage probe")
    ap.add_argument("--check", action="store_true", help="verify 100%% candidate coverage in tools-policy.json")
    ap.add_argument("--json", action="store_true", help="emit JSON report")
    ap.add_argument("--policy", type=Path, default=None, help="override tools-policy.json path")
    args = ap.parse_args(argv)

    scanned, hits = scan_usage()
    if not scanned:
        print("EMPTY CORPUS — refusing to report zeros as evidence", file=sys.stderr)
        return 2

    policy_path = args.policy or resolve_policy_path(ROOT)
    try:
        policy: dict[str, Any] = json.loads(policy_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"CANNOT READ POLICY {policy_path}: {exc}", file=sys.stderr)
        return 2

    problems = verify_policy_coverage(policy, hits)
    governed = policy.get("tools", {})
    out_of_scope = policy.get("out_of_scope", {})

    if args.json:
        summary = {
            "scanned_files": scanned,
            "policy_path": str(policy_path),
            "candidates": {
                t: {
                    "uses": sum(n for n, _ in hits[t]),
                    "files": len(hits[t]),
                    "disposition": (
                        "governed"
                        if t in governed
                        else ("out_of_scope" if t in out_of_scope else "unaccounted")
                    ),
                }
                for t in TOOLS
            },
            "problems": problems,
        }
        print(json.dumps(summary, indent=2))
        return 1 if problems else 0

    print(f"scanned {scanned} files across {len(REPOS)} repos (policy: {policy_path.relative_to(ROOT) if policy_path.is_relative_to(ROOT) else policy_path})\n")
    for t in TOOLS:
        total = sum(n for n, _ in hits[t])
        where = ", ".join(f"{f}×{n}" for n, f in sorted(hits[t], reverse=True)[:4]) or "—"
        if t in governed:
            req = "req" if governed[t].get("required") else "opt"
            disp = f"governed[{req}]"
        elif t in out_of_scope:
            disp = "out-of-scope"
        else:
            disp = "UNACCOUNTED"
        print(f"{t:10} {disp:14} uses={total:<4} files={len(hits[t]):<3} {where}")

    if problems:
        print(f"\n✗ {len(problems)} coverage problem(s):", file=sys.stderr)
        for prob in problems:
            print(f"  - {prob}", file=sys.stderr)
        if args.check:
            return 1
    else:
        print(f"\n✓ all {len(TOOLS)} candidate CLIs accounted for ({sum(1 for t in TOOLS if t in governed)} governed, {sum(1 for t in TOOLS if t in out_of_scope)} out_of_scope)")
    return 1 if (args.check and problems) else 0


if __name__ == "__main__":
    sys.exit(main())
