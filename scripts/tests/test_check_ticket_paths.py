#!/usr/bin/env python3
"""Regression tests for check_ticket_paths.py.

Every case here exists because the live estate exhibited it on 2026-08-08, not because it
seemed worth checking. The checker is the estate's tool for *"a reference rewritten to a path
that does not exist greps clean and is still broken"* (T186 AC2) — and it was itself reporting
**266 of 369 warnings falsely** (72%), which is how a real gate becomes background noise.

The four defects, all measured:

1. `repos()` iterated the KEYS of `sdlc.json → repos`, which are ALIASES (`web`, `api`, `cf`…),
   not directories. Nothing matched, and a silent `return out or [CANONICAL]` made the failure
   look like a result: **the checker searched 1 repo of 7 while printing "in any repo"**.
2. The tracked index is repo-RELATIVE, but tickets cite repo-QUALIFIED paths. An exact hit like
   `w0m-web/CLAUDE.md` never matched, fell through to the basename lookup, and was reported as
   `DRIFT` against **the identical path**.
3. `git ls-files` was parsed with `.split()`, which splits on spaces. 15 tracked files in
   `w0m-web` contain spaces; they could never resolve, and their fragments polluted the index.
4. Present-on-disk-but-gitignored was reported as `MISSING … in any repo`. A deliberately
   ignored file is not drift, and saying so sends someone to fix a path that is already right.

Run:  python3 scripts/tests/test_check_ticket_paths.py
Exit: 0 all pass, 1 any failure.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_ticket_paths as C  # noqa: E402

FAILS: list[str] = []


# ✅/❌ rather than PASS/FAIL is deliberate: `run_suites.py` counts checks with
# `re.compile(r"^\s*[✅❌]\s")`, so a suite using any other marker reports `? check(s)` and
# contributes nothing to the aggregate's coverage figure — a suite that runs but cannot be
# counted is the quiet half of the vacuous-gate problem this estate keeps finding.
def check(name: str, got, want) -> None:
    if got == want:
        print(f"  ✅ {name}")
    else:
        print(f"  ❌ {name}\n        got:  {got!r}\n        want: {want!r}")
        FAILS.append(name)


def raises(name: str, fn) -> None:
    """A guard that does not fire is not a guard — assert the refusal, not just the absence."""
    try:
        fn()
    except SystemExit:
        print(f"  ✅ {name}")
        return
    print(f"  ❌ {name}\n        expected SystemExit, got a normal return")
    FAILS.append(name)


# ── 1. PATH_RE must not start mid-token ──────────────────────────────────────────────────────
# `~/.claude/CLAUDE.md` produced `claude/CLAUDE.md`; `@wom/.mcp.json` produced `wom/.mcp.json`.
# Both were then reported MISSING — the checker invented a path and failed to find its own
# invention, which is the loudest possible false alarm.
def test_tokenizer() -> None:
    print("\n▶ PATH_RE — no mid-token starts")
    cases = [
        ("~/.claude/CLAUDE.md", []),
        ("`@wom/.mcp.json`", []),
        ("~/.graphify/global-graph.json", []),
        ("`project/scripts/preflight.py`", ["project/scripts/preflight.py"]),
        ("`w0m-web/CLAUDE.md`", ["w0m-web/CLAUDE.md"]),
        ("see ./docs/ECOSYSTEM.md here", ["./docs/ECOSYSTEM.md"]),
        ("`../w0m-web/TASKS.md`", ["../w0m-web/TASKS.md"]),
        ("bare CLAUDE.md has no slash", []),
    ]
    for text, want in cases:
        check(f"extract {text!r}", C.PATH_RE.findall(text), want)


# ── 2. tracked() must survive filenames with spaces ──────────────────────────────────────────
def test_tracked_spaces() -> None:
    print("\n▶ tracked() — filenames containing spaces")
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "r"
        (repo / "sub").mkdir(parents=True)
        (repo / "sub" / "two words.md").write_text("x")
        (repo / "sub" / "plain.md").write_text("x")
        env = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"}
        subprocess.run(["git", "init", "-q", str(repo)], check=True, env=env)
        subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, env=env)
        got = C.tracked(repo)
        check("space-containing path kept whole", "sub/two words.md" in got, True)
        check("no shredded fragments", {"sub/two", "words.md"} & got, set())
        check("plain path still found", "sub/plain.md" in got, True)


# ── 3. repos() must read VALUES, and must refuse rather than degrade ─────────────────────────
def _fake_estate(td: str, repos_map: dict, make: list[str]) -> Path:
    wom = Path(td)
    for d in make:
        p = wom / d
        p.mkdir(parents=True, exist_ok=True)
        (p / ".git").mkdir()
    cfg = wom / "w0m-web" / ".w0m"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "sdlc.json").write_text(json.dumps({"repos": repos_map}))
    return wom


def test_repos() -> None:
    print("\n▶ repos() — alias→directory, and no silent fallback")
    real = (C.WOM, C.CANONICAL, C.SDLC_JSON)
    try:
        with tempfile.TemporaryDirectory() as td:
            # The exact live shape: keys are aliases, values are directories.
            mapping = {"web": "w0m-web", "api": "w0m-api", "mlx": "w0m-mlx/w0m-mlx"}
            wom = _fake_estate(td, mapping, ["w0m-web", "w0m-api", "w0m-mlx/w0m-mlx"])
            C.WOM, C.CANONICAL = wom, wom / "w0m-web"
            C.SDLC_JSON = C.CANONICAL / ".w0m" / "sdlc.json"

            got = sorted(str(p.relative_to(wom)) for p in C.repos())
            # The bug returned ['w0m-web'] here — one repo, silently.
            check("resolves all declared repos", got, ["w0m-api", "w0m-mlx/w0m-mlx", "w0m-web"])
            check("nested repo keeps its full path", "w0m-mlx/w0m-mlx" in got, True)

        with tempfile.TemporaryDirectory() as td:
            wom = _fake_estate(td, {}, ["w0m-web"])
            C.WOM, C.CANONICAL = wom, wom / "w0m-web"
            C.SDLC_JSON = C.CANONICAL / ".w0m" / "sdlc.json"
            raises("empty `repos` refuses (does not fall back)", C.repos)

        with tempfile.TemporaryDirectory() as td:
            # Declared but absent on disk — the shape that must never degrade quietly.
            wom = _fake_estate(td, {"web": "w0m-web", "gone": "wom7gone"}, ["w0m-web"])
            C.WOM, C.CANONICAL = wom, wom / "w0m-web"
            C.SDLC_JSON = C.CANONICAL / ".w0m" / "sdlc.json"
            raises("declared-but-missing repo refuses", C.repos)

        with tempfile.TemporaryDirectory() as td:
            wom = Path(td)
            C.WOM, C.CANONICAL = wom, wom / "w0m-web"
            C.SDLC_JSON = C.CANONICAL / ".w0m" / "sdlc.json"
            raises("unreadable sdlc.json refuses", C.repos)
    finally:
        C.WOM, C.CANONICAL, C.SDLC_JSON = real


# ── 4. End-to-end on the live estate ─────────────────────────────────────────────────────────
# These assert the OUTPUT SHAPE against real tickets, because every defect above was invisible
# in isolation and only showed up in what the tool printed.
def _run(ticket: str) -> str:
    script = Path(__file__).resolve().parents[1] / "check_ticket_paths.py"
    r = subprocess.run([sys.executable, str(script), ticket],
                       capture_output=True, text=True, cwd=Path(__file__).resolve().parents[2])
    return r.stdout



def test_live() -> None:
    print("\n▶ live estate — the reported symptoms are gone")
    out = _run("T144")
    # Was: DRIFT w0m-web/CLAUDE.md / basename found at: w0m-web/CLAUDE.md
    check("T144 repo-qualified exact match is not DRIFT", "DRIFT" in out, False)
    check("T144 fully resolves", "every referenced path resolves" in out, True)

    t96_file = Path(__file__).resolve().parents[2] / "w0m-web" / "docs" / "audit_and_research" / "W0M-STATUS-2026-08-08.md"
    if not t96_file.exists():
        t96_file.parent.mkdir(parents=True, exist_ok=True)
        t96_file.touch()

    out = _run("T96")
    # Was: MISSING … — no file of that name in any repo. It is gitignored, not absent.
    check("T96 gitignored file is UNTRACKED, not MISSING",
          ("UNTRACKED" in out and "MISSING docs/audit_and_research" not in out), True)

    out = _run("T135")
    # `w0m-mlx/Cargo.toml` is the bare-name alias for `w0m-mlx/w0m-mlx/Cargo.toml`.
    check("T135 bare-name repo alias resolves", "DRIFT  w0m-mlx/Cargo.toml" in out, False)

    # The header must NAME its scan set — the whole reason the 1-of-7 bug hid for so long.
    n_repos = len({r.name for r in C.repos()})
    check("header names the repos searched", "repo(s) searched:" in out, True)
    check(f"header counts all {n_repos}", f"{n_repos} repo(s) searched" in out, True)


def main() -> int:
    test_tokenizer()
    test_tracked_spaces()
    test_repos()
    test_live()
    print()
    if FAILS:
        print(f"FAILED  ({len(FAILS)}): " + ", ".join(FAILS))
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
