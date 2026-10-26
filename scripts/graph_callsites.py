#!/usr/bin/env python3
"""T151 AC1 — enumerate what actually invokes graphify vs codegraph across the estate.

Answers one question: *before changing which code-graph tool the estate reaches for,
what is currently wired to call each one?*

Three things this deliberately does that a naive grep does not:

1. **Dedupes by RESOLVED path.** `wom7web/justfile` and `wom7cfworkers/justfile` are both
   symlinks to `wom7api/justfile`. `git ls-files` lists all three and reading them follows
   the link, so a tracked-path scan reports three call sites where there is one. The first
   pass of this audit made exactly that error — the estate's signature failure mode,
   committed by the tool hunting it.

2. **Scans the out-of-repo surfaces.** `~/.claude/CLAUDE.md`, `~/.claude/skills/` and the
   MCP registration in `~/.claude.json` are invisible to a repo-scoped scan but are the
   most load-bearing call sites there are: an MCP server reaches every agent session in
   every directory. Omitting them repeats T149 instance 4.

3. **Proves its corpus is non-empty.** A zero-hit surface is only evidence if files were
   actually read. `--corpus` reports what each sweep enumerated, so "no hits" can be
   distinguished from "no input" — this estate has shipped that confusion five times.

Usage:
    python3 project/scripts/graph_callsites.py            # the enumeration
    python3 project/scripts/graph_callsites.py --corpus   # + corpus sizes (anti-vacuity)

Exit codes: 0 = enumerated, 2 = configuration/environment error (never a "finding" count).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

# .../@wom/scripts/graph_callsites.py -> parents[1] is the ESTATE root (relocated in T516).
ESTATE = Path(__file__).resolve().parents[1]
REPOS = [
    "wom7web", "wom7api", "wom7func",
    "wom7skills", "wom7ext", "wom7sec", "wom7mlx/wom7mlx",
]

TOOLS = {
    "graphify": re.compile(r"graphify", re.I),
    "codegraph": re.compile(r"codegraph", re.I),
}

# The graph artifacts themselves are output, not call sites.
SKIP = re.compile(r"(^|/)(graphify-out|\.codegraph)/")

SURFACES = [
    ("git-hook", re.compile(r"(^|/)(\.husky/|\.git/hooks/|\.pre-commit-config\.yaml)")),
    ("just-recipe", re.compile(r"(^|/)justfile$", re.I)),
    ("sdlc-config", re.compile(r"(^|/)\.w0m/")),
    ("skill", re.compile(r"SKILL\.md$")),
    ("agent-instr", re.compile(r"(^|/)(CLAUDE\.md|AGENTS\.md|\.agents/|\.claude/)")),
    ("policy", re.compile(r"(stacks|tools|deps)-policy")),
    ("script", re.compile(r"\.(py|ts|js|mjs|cjs|sh)$")),
    ("docs", re.compile(r"\.mdx?$")),
]
SURFACE_ORDER = [name for name, _ in SURFACES] + ["other"]


def surface_of(rel: str) -> str:
    for name, pat in SURFACES:
        if pat.search(rel):
            return name
    return "other"


def git(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(repo), *args],
                         capture_output=True, text=True)
    return out.stdout if out.returncode == 0 else ""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="graph_callsites.py",
        description=__doc__,
    )
    ap.add_argument("--corpus", action="store_true",
                    help="report corpus sizes so a zero-hit sweep is distinguishable "
                         "from a sweep that read nothing")
    ap.add_argument(
        "--target",
        action="append",
        default=None,
        help="restrict or customize target tool/symbol regex(es) to enumerate (default: graphify, codegraph)",
    )
    ap.add_argument(
        "--estate-root",
        type=Path,
        default=None,
        help="override estate root path (for offline testing)",
    )
    args = ap.parse_args(argv)

    estate_root = Path(args.estate_root).resolve() if args.estate_root else ESTATE
    if not (estate_root / "wom7web").is_dir():
        print(f"error: estate root not found at {estate_root}", file=sys.stderr)
        return 2

    active_tools: dict[str, re.Pattern[str]] = (
        {t: re.compile(re.escape(t), re.I) for t in args.target}
        if args.target
        else dict(TOOLS)
    )

    hits: list[tuple[str, str, str, str, int]] = []
    seen: set[Path] = set()          # dedupe key: RESOLVED path
    corpus = {"tracked": 0, "deduped_away": 0, "hooks": 0, "external": 0}

    def scan(path: Path, label: str, rel: str) -> None:
        try:
            real = path.resolve()
        except OSError:
            return
        if real in seen:
            corpus["deduped_away"] += 1
            return
        seen.add(real)
        # Name the file that will actually be read. Reporting a symlink under the repo that
        # merely points at it is how "one justfile" reads as three separate call sites.
        if real != path.absolute():
            try:
                rel = f"{rel} -> {real.relative_to(estate_root)}"
            except ValueError:
                rel = f"{rel} -> {real}"
        try:
            text = path.read_text(errors="ignore")
        except (OSError, UnicodeDecodeError):
            return
        for tool, pat in active_tools.items():
            n = len(pat.findall(text))
            if n:
                hits.append((tool, label, surface_of(rel), rel, n))

    # 1. tracked files, all repos
    for r in REPOS:
        repo = estate_root / r
        if not repo.is_dir():
            continue
        for rel in git(repo, "ls-files").splitlines():
            if not rel or SKIP.search(rel):
                continue
            corpus["tracked"] += 1
            scan(repo / rel, r, rel)

    # 2. live hooks — untracked, so `git ls-files` structurally cannot see them
    for r in REPOS:
        repo = estate_root / r
        if not repo.is_dir():
            continue
        hp = git(repo, "config", "core.hooksPath").strip()
        for d in [repo / ".git" / "hooks"] + ([repo / hp] if hp else []):
            if not d.is_dir():
                continue
            for f in sorted(d.iterdir()):
                if f.is_dir() or f.name.endswith(".sample"):
                    continue
                corpus["hooks"] += 1
                scan(f, r, f"{d.name}/{f.name}")

    # 3. out-of-repo agent surfaces
    home = Path.home()
    for p in [home / ".claude" / "CLAUDE.md", home / ".claude" / "settings.json"]:
        if p.exists():
            corpus["external"] += 1
            scan(p, "GLOBAL", p.name)
    skills_dir = home / ".claude" / "skills"
    if skills_dir.is_dir():
        for p in skills_dir.rglob("SKILL.md"):
            corpus["external"] += 1
            scan(p, "GLOBAL", str(p.relative_to(skills_dir.parent)))

    # 4. MCP registration — a runtime fact, in no repo, and the most load-bearing of all
    mcp: dict[str, list[str]] = {}
    cfg = home / ".claude.json"
    if cfg.exists():
        try:
            cfg_data: dict[str, Any] = cast(dict[str, Any], json.loads(cfg.read_text(encoding="utf-8")))
            servers = cfg_data.get("mcpServers", {})
            for tool in active_tools:
                mcp[tool] = sorted(n for n in servers if tool in n.lower())
        except (OSError, json.JSONDecodeError, AttributeError):
            mcp = {}

    print(f"corpus: tracked={corpus['tracked']} hooks={corpus['hooks']} "
          f"external={corpus['external']} deduped_away={corpus['deduped_away']}")
    if corpus["tracked"] == 0:
        print("error: empty corpus — an enumeration over nothing is not evidence",
              file=sys.stderr)
        return 2
    if args.corpus:
        print(f"  unique files read: {len(seen)}")
    print(f"hits: {len(hits)}\n")

    for tool in active_tools:
        rows = [h for h in hits if h[0] == tool]
        reg = mcp.get(tool) or []
        print(f"===== {tool.upper()} — {len(rows)} file(s) =====")
        print(f"  [mcp-runtime] {'REGISTERED: ' + ', '.join(reg) if reg else 'not registered'}")
        by_surface: dict[str, list[tuple[str, str, int]]] = {}
        # `repo_name`, not `repo`: earlier in this function `repo` is bound to a Path
        # (`ESTATE / r`, lines ~124/133). Re-using the name here for the repo's NAME meant the
        # 3-tuple below was declared `tuple[str, str, int]` while typing as `tuple[Path, ...]`.
        # Distinct types deserve distinct names (T188).
        for _, repo_name, surface, rel, n in rows:
            by_surface.setdefault(surface, []).append((repo_name, rel, n))
        for s in SURFACE_ORDER:
            if s not in by_surface:
                continue
            print(f"  [{s}] {len(by_surface[s])}")
            for repo_name, rel, n in sorted(by_surface[s]):
                print(f"      {repo_name:<18} {rel}  (x{n})")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
