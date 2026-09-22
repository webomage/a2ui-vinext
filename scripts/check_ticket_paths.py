#!/usr/bin/env python3
"""Verify the file paths a ticket names actually exist (T119 AC3).

WHY
    Tickets accumulate paths that were right once. A ticket saying
    `src/components/admin/AdminPDFPageEditor.svelte` when the file sits at
    `src/components/AdminPDFPageEditor.svelte` sends the next agent to grep for a
    file that moved, and the drift is invisible until someone tries to open it.

WHAT IT DOES
    Extracts path-looking tokens from a ticket, checks them against the git tree of
    each configured repo, and for misses tries a basename match to propose the real
    location. Reports; it does NOT rewrite. Auto-correcting a path the author meant
    differently is worse than a stale one, because it looks authoritative.

Usage:
    python3 scripts/check_ticket_paths.py T117
    python3 scripts/check_ticket_paths.py T117 --quiet   # only drift
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

def find_workspace_root(start_path: Path | None = None) -> Path:
    """Find the workspace root containing .tasks and .w0m/sdlc.json."""
    cur = (start_path or Path(__file__)).resolve()
    for parent in [cur] + list(cur.parents):
        if (parent / ".tasks").is_dir() and (parent / ".w0m").is_dir():
            return parent
        if (parent / ".git").exists() and (parent / "wom7web").is_dir():
            return parent
    return Path(__file__).resolve().parents[1]


WOM = find_workspace_root()
CANONICAL = WOM / "wom7web"
SDLC_JSON = WOM / ".w0m" / "sdlc.json"

# A path token: has a slash and a file-ish extension. Deliberately conservative —
# false positives cost more attention than the check saves.
# ⚠️ `.` `~` `@` are in the negative lookbehind for a measured reason: without them the scan
# starts MID-TOKEN. `~/.claude/CLAUDE.md` yielded `claude/CLAUDE.md` and `@wom/.mcp.json` yielded
# `wom/.mcp.json` — paths nobody wrote, reported as MISSING against repos they were never in.
# A checker that invents the path it then fails to find is the loudest possible false alarm.
PATH_RE = re.compile(
    r"(?<![\w/.~@])((?:\.{1,2}/)?[\w.-]+(?:/[\w.-]+)+"
    r"\.(?:tsx|ts|json|jsonc|mjs|cjs|js|astro|svelte|py|sql|mmd|md|yaml|yml|sh|toml))(?![\w])"
)

# Tokens that look like paths but are not repo files.
# T186 (2026-08-08): the `../wom7md/` and `wom7md:` entries were REMOVED with the repo. They made
# this gate structurally blind to exactly the drift T186 had to clean up by hand — a ticket citing
# a wom7md path was skipped rather than resolved, so the checker could never have reported the
# stale references. An ignore rule for a live repo is a coverage hole with a reason attached.
IGNORE = re.compile(r"^(https?:|node_modules/|package\.json$)")


def repos() -> list[Path]:
    """Resolve every estate repo from `sdlc.json → repos`.

    🔴 **`repos` maps ALIAS → DIRECTORY** — `{"web": "wom7web", "mlx": "wom7mlx/wom7mlx", …}`.
    Iterating it yields the ALIASES, and `@wom/web` is not a directory, so the original
    `for name in cfg.get("repos")` matched **nothing** and fell through to a silent
    `return out or [CANONICAL]`. ⇒ **This checker searched 1 repo of 7 while printing
    "no file of that name in any repo".** Fixed 2026-08-08; iterate `.values()`.

    ⚠️ **No silent fallback.** A degraded enumeration that still returns a plausible answer is
    indistinguishable from success — the estate's signature defect, and the exact mechanism that
    hid this bug. An empty or unreadable registry is a broken tool, not a clean result: raise.
    """
    try:
        cfg = json.loads(SDLC_JSON.read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise SystemExit(f"❌ cannot read {SDLC_JSON}: {e}")

    declared = (cfg.get("repos") or {})
    if not declared:
        raise SystemExit(f"❌ {SDLC_JSON} declares no `repos` — refusing to report on an empty set")

    out: list[Path] = []
    absent: list[Path] = []
    for dirname in declared.values():
        p = WOM / dirname
        (out if (p / ".git").exists() else absent).append(p)
    if absent:
        names = ", ".join(p.name for p in absent)
        raise SystemExit(f"❌ declared repo(s) not on disk: {names} — fix `sdlc.json → repos` first")
    return out


def tracked(repo: Path) -> set[str]:
    """Git-tracked paths, repo-relative.

    ⚠️ `-z` and `splitlines()`-free parsing are deliberate: `git ls-files` separates with
    newlines and **filenames may contain spaces** (15 do in `wom7web`). The original
    `stdout.split()` shredded those into fragments, so they could never resolve *and* their
    pieces polluted the basename index.
    """
    r = subprocess.run(["git", "-C", str(repo), "ls-files", "-z"], capture_output=True, text=True)
    if r.returncode != 0:
        return set()
    return {p for p in r.stdout.split("\0") if p}


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: check_ticket_paths.py <TICKET-ID> [--quiet]", file=sys.stderr)
        return 2
    quiet = "--quiet" in sys.argv
    tid = sys.argv[1].upper()

    ticket = WOM / ".tasks" / f"{tid}.md"
    if not ticket.is_file():
        print(f"❌ no ticket at {ticket}", file=sys.stderr)
        return 1

    repo_paths = repos()
    index: dict[str, set[str]] = {r.name: tracked(r) for r in repo_paths}
    roots: dict[str, Path] = {r.name: r for r in repo_paths}
    # Two accepted qualifiers per repo: its estate-relative directory AND its bare name. They
    # differ only for the nested `wom7mlx/wom7mlx`, and tickets legitimately use both — T135
    # writes `wom7mlx/Cargo.toml` and says so explicitly ("relative to the declared repo root").
    # Longest first so `wom7mlx/wom7mlx` is stripped before the bare `wom7mlx` would swallow it.
    prefixes = sorted(
        {(str(r.relative_to(WOM)), r.name) for r in repo_paths}
        | {(r.name, r.name) for r in repo_paths},
        key=lambda t: -len(t[0]),
    )

    # Display with the estate-relative directory, never the bare name: for `wom7mlx` the bare
    # name yields `wom7mlx/Cargo.toml`, which is not a path that exists on disk.
    reldir = {r.name: str(r.relative_to(WOM)) for r in repo_paths}
    by_basename: dict[str, list[str]] = {}
    for repo, files in index.items():
        for f in files:
            by_basename.setdefault(f.rsplit("/", 1)[-1], []).append(f"{reldir[repo]}/{f}")

    candidates = {m for m in PATH_RE.findall(ticket.read_text(encoding="utf-8"))
                  if not IGNORE.match(m)}

    def resolve(norm: str) -> bool:
        """Tracked anywhere, as written or repo-qualified?

        🔑 The index is **repo-relative**, but tickets routinely cite repo-QUALIFIED paths
        (`wom7web/project/scripts/w0m_audit.py`). Testing the qualified string against
        repo-relative entries never matched, so an exact hit fell through to the basename
        lookup — which returned the identical path and printed it as `DRIFT`. A tool that
        reports a correct path as drift teaches you to ignore it.
        """
        if any(norm in files for files in index.values()):
            return True
        for prefix, key in prefixes:
            if norm.startswith(prefix + "/") and norm[len(prefix) + 1:] in index[key]:
                return True
        return False

    def on_disk(norm: str) -> str | None:
        """Present on disk but not tracked → deliberately ignored, or simply never added."""
        for prefix, key in prefixes:
            if norm.startswith(prefix + "/") and (WOM / norm).is_file():
                return norm
        for name, root in roots.items():
            if (root / norm).is_file():
                return f"{name}/{norm}"
        return None

    ok: list[str] = []
    untracked: list[tuple[str, str]] = []
    # Both hold (candidate, matches) and are filled through a conditional-expression
    # append below — `drift.append` does not appear in this file, which is why they read
    # as never-populated to a grep and as un-inferrable to mypy.
    drift: list[tuple[str, list[str]]] = []
    unknown: list[tuple[str, list[str]]] = []
    for c in sorted(candidates):
        norm = c[2:] if c.startswith("./") else c
        # A leading `../` is relative to a base this file cannot know; every repo is searched
        # anyway, so strip it rather than guaranteeing a miss.
        while norm.startswith("../"):
            norm = norm[3:]
        if resolve(norm):
            ok.append(c)
            continue
        found = on_disk(norm)
        if found:
            untracked.append((c, found))
            continue
        matches = by_basename.get(norm.rsplit("/", 1)[-1], [])
        (drift if matches else unknown).append((c, matches))

    if not quiet:
        print(f"🔎 {tid}: {len(candidates)} path(s) referenced — {len(ok)} resolve "
              f"({len(index)} repo(s) searched: {', '.join(sorted(index))})")
    for c, matches in drift:
        # A basename like `spec.md` exists everywhere; listing 30 candidates is noise, not a lead.
        if len(matches) > 3:
            print(f"  ⚠  DRIFT  {c}\n           basename is too common ({len(matches)} matches) "
                  f"to propose a correction — check by hand")
        else:
            print(f"  ⚠  DRIFT  {c}\n           basename found at: {', '.join(matches)}")
    for c, found in untracked:
        print(f"  ℹ  UNTRACKED {c} — exists at {found} but is not in git "
              f"(gitignored or never added). Not drift; the path is correct.")
    for c, _ in unknown:
        print(f"  ⚠  MISSING {c} — no tracked file of that name in any of the "
              f"{len(index)} repo(s) (renamed, deleted, planned, or outside the estate?)")

    if drift or unknown:
        print("     Paths are reported, never rewritten — confirm before editing the ticket.")
    elif not quiet:
        print("  ✓ every referenced path resolves")
    return 0


if __name__ == "__main__":
    sys.exit(main())
