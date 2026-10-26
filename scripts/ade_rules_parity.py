#!/usr/bin/env python3
"""Do agents in OTHER ADEs read the same rules as Claude?

`ide-trace` (T192) answers two questions: is an ADE DECLARED, and does its autoload file CARRY the
non-negotiable rules. Both inspect the working checkout. Neither asks the question this does:

    🔑 is that surface REACHABLE in the context the agent actually runs in?

Orca is not an ADE with its own rules — it is a RUNNER. It provisions a git worktree and executes a
CLI agent (`opencode`) inside it (`w0m-web/ORCA_INTEGRATION.md`). A worktree contains TRACKED files
only, so a rule surface reaches it iff:

  1. git tracks it, AND
  2. if it is a symlink, its target resolves INSIDE the repo — a relative link to a sibling repo is
     tracked, and dangles the moment the worktree is not beside that sibling.

Both failures are silent. The agent does not error; it simply never sees the rule, and behaves like
one that was never given it. That is the difference between "the rules are written down" and "the
agent read them", and only the second one governs anything.

Computed statically from git — no worktree is created — and validated against real worktrees of
w0m-web and w0m-api on 2026-08-29.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

ESTATE = pathlib.Path(__file__).resolve().parents[1]
REPO = ESTATE / "w0m-web"
POLICY = ESTATE / "project" / "policies" / "ide-policy.json"
SDLC = ESTATE / ".w0m" / "sdlc.json"


def git(repo: pathlib.Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""


def tracked(repo: pathlib.Path, path: str) -> int:
    out = git(repo, "ls-files", "-z", "--", path)
    return len([p for p in out.split("\0") if p])


def reachable_in_worktree(repo: pathlib.Path, rel: str) -> tuple[str, str]:
    """Would an agent running in a `git worktree` of this repo see `rel`?

    Three states, never two — the same discipline T242 forced on the authz probes. A surface is
    `reach` (git carries it and it resolves anywhere), `no` (git does not carry it at all), or
    🔑 `fragile`: git carries the LINK but its target is outside the repo, so whether it resolves
    depends on WHERE the worktree was placed. Beside the target it works; anywhere else it dangles.
    Collapsing `fragile` into `no` was this gate's first bug — its own red probes caught it, by
    building a worktree next to the target and watching the link resolve.
    """
    p = repo / rel
    n = tracked(repo, rel)
    if n == 0:
        if p.exists():
            return "no", "exists on disk but git tracks NOTHING under it — never reaches a worktree or a clone"
        return "no", "absent"
    if p.is_symlink():
        target = os.readlink(p)
        # A worktree places the LINK, not what it points at. Relative escape = dangling there.
        resolved = (p.parent / target).resolve()
        try:
            resolved.relative_to(repo.resolve())
        except ValueError:
            return "fragile", (f"SYMLINK -> {target} — the target is OUTSIDE the repo, so it resolves "
                               f"ONLY if the worktree is placed beside it, and dangles anywhere else")
        return "reach", f"symlink inside the repo ({n} tracked)"
    # 🔴 Reaching the worktree is not the same as reaching it WHOLE. A directory surface can be
    # tracked and still deliver a fraction of itself: measured 2026-08-29, w0m-web/.agent holds
    # 1,644 files on disk and git carries 515 — an Antigravity agent in a worktree gets the
    # directory and 31% of the rules in it. Partial delivery is the same failure as none, quieter.
    if p.is_dir():
        # 🔴 Compare against untracked-and-NOT-IGNORED only. A first version counted every file on
        # disk and reported w0m-web/.agent as 31% delivered — all 1,129 "missing" files were
        # `.agent/deployments/` build logs, deliberately gitignored. Deliberate exclusion is not a
        # delivery failure, and a gate that calls it one is the kind nobody reads for long.
        stray = [x for x in git(repo, "ls-files", "--others", "--exclude-standard", "--", rel).splitlines() if x]
        if stray:
            return "no", (f"{n} tracked, but {len(stray)} file(s) here are untracked and NOT ignored "
                           f"— they exist for Claude locally and reach no worktree, clone or teammate "
                           f"(e.g. {stray[0]})")
    return "reach", f"{n} tracked file(s)"


def main() -> int:
    enforce = "--enforce" in sys.argv
    if not POLICY.exists() or not SDLC.exists():
        print("❌ UNMEASURABLE — ide-policy.json or .w0m/sdlc.json not found"); return 2

    pol = json.loads(POLICY.read_text())
    sdlc = json.loads(SDLC.read_text())
    tools = {k: v for k, v in pol["tools"].items() if not k.startswith("_")}
    connected = {k: v for k, v in sdlc["ide_surfaces"]["connected"].items() if not k.startswith("_")}
    repos = {k: v for k, v in sdlc.get("repos", {}).items() if not k.startswith("_")}
    if not connected or not repos:
        print("❌ UNMEASURABLE — no connected IDEs or no repos declared"); return 2

    print("\n▶ ADE rule parity — is each ADE's surface REACHABLE where the agent actually runs?")
    print("  (Orca runs agents in a git WORKTREE, so a surface reaches them only if git carries it.)\n")

    findings: list[str] = []
    checked = 0
    for repo_key, rel_repo in sorted(repos.items()):
        repo = (ESTATE / rel_repo).resolve() if rel_repo != "." else REPO
        if not (repo / ".git").exists():
            continue
        ades = connected.get(repo_key) or []
        if not ades:
            continue
        print(f"  {repo.name}  — declared: {', '.join(sorted(ades))}")
        # The policy names TWO surfaces per tool and they fail differently: `autoload` is the file
        # the ADE reads unprompted, `skills_dir` is the executable-instruction tree it loads from.
        # Both are read from the policy rather than restated here, so this cannot drift from it.
        surfaces: dict[str, list[str]] = {}
        for ade in sorted(ades):
            spec = tools.get(ade, {})
            for key in ("autoload", "skills_dir"):
                v = spec.get(key)
                # `autoload` is a string for most tools and a LIST for the ones that read several
                # files (cursor, windsurf). Both shapes are real in the policy; normalise rather
                # than assume, or the tools with the MOST surfaces are the ones that crash.
                for s in ([v] if isinstance(v, str) else (v or [])):
                    if s:
                        surfaces.setdefault(s, []).append(ade)
        for s, owners in sorted(surfaces.items()):
            checked += 1
            state, why = reachable_in_worktree(repo, s)
            mark = {"reach": "  ok ", "no": "🔴 NO", "fragile": "🟠 FRA"}[state]
            print(f"      {mark}  {s:<16} [{','.join(owners)}]  {why}")
            if state != "reach" and why != "absent":
                findings.append(f"{repo.name}: `{s}` ({','.join(owners)}) [{state}] — {why}")
        print()

    # ── delegation targets ──────────────────────────────────────────────────────────────────
    # 🔑 The estate satisfies the contract by POINTING: five of six repos open with "Canonical
    # conventions live in ../w0m-web/CLAUDE.md", and `ide-trace` correctly counts that as carrying
    # the rules. It does — for an agent in the normal checkout. In a WORKTREE `../w0m-web/` does not
    # exist, so the agent gets the 1-2 rules its own file states plus a pointer to nothing. This is
    # the estate's deliberate design failing silently in the one context Orca creates.
    import re
    ESCAPE = re.compile(r"\.\./[A-Za-z0-9_/.-]*(?:CLAUDE|AGENTS)\.md")
    print("  delegation targets — a pointer only carries rules if the agent can open it:")
    for repo_key, rel_repo in sorted(repos.items()):
        repo = (ESTATE / rel_repo).resolve() if rel_repo != "." else REPO
        if not (repo / ".git").exists():
            continue
        for surface in ("CLAUDE.md", "AGENTS.md"):
            f = repo / surface
            if not f.exists():
                continue
            for m in set(ESCAPE.findall(f.read_text(encoding="utf-8", errors="replace"))):
                # Skip a file naming its OWN path. w0m-web/CLAUDE.md is the canonical file and
                # quotes `../w0m-web/CLAUDE.md` when telling sibling repos where to point — that
                # resolves to itself, so reporting it as a broken delegation is a false finding.
                if (repo / m).resolve() == f.resolve():
                    continue
                print(f"      🔴 NO  {repo.name}/{surface} -> {m}  escapes the repo — absent in a worktree")
                findings.append(f"{repo.name}: `{surface}` delegates to `{m}`, which is outside the "
                                f"repo and absent from any worktree — the pointer carries nothing there")
    print()

    if checked == 0:
        print("❌ UNMEASURABLE — no surfaces were checked; the policy declares none for these ADEs")
        return 2

    if findings:
        print(f"  🔴 {len(findings)} surface(s) Claude reads in the checkout that a worktree-run agent does NOT:")
        for f in findings:
            print(f"     · {f}")
        print("\n  Each is a rule that is written down, passes `ide-trace`, and never reaches the agent.")
        return 1 if enforce else 0

    print(f"  ✅ every declared surface ({checked}) reaches a worktree — same rules, every ADE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
