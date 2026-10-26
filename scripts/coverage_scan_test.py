#!/usr/bin/env python3
"""Prove the coverage scan REFUSES and goes RED — T147 AC6.

Same two axes AC6 asks for, and the second is the one that matters here:

  1. a real gap is actually reported (an uncovered code file reaches the worklist);
  2. every EMPTY input REFUSES instead of printing a confident 100%.

Axis 2 is not hypothetical for this particular scan — its arithmetic is
`covered / total`, so an empty stack registry reports every file uncovered and an empty
corpus reports `0/0`. Both would render as a clean, plausible number. `0 managed skill(s)
match the lockfile ✓` (T127) and the five instances T149 catalogued are the same shape.

Every case drives `scan()` against a REAL temporary git checkout rather than a mocked
lister, because the corpus claim in the report is *"git-tracked"* — a fixture that faked
`git ls-files` would prove the arithmetic while leaving the claim untested.

Nothing here asserts the happy path against the live estate; `just coverage-scan` does that,
and a suite that only proves the happy path is how a check that can never fire gets shipped.

Run: `just coverage-scan-test`
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import coverage_scan as cs  # noqa: E402

PASS, FAIL = "✅", "❌"
results: list[tuple[bool, str]] = []


def case(name: str, fn) -> None:
    try:
        fn()
        results.append((True, name))
    except AssertionError as exc:
        results.append((False, f"{name} — {exc}"))
    except Exception as exc:  # noqa: BLE001
        results.append((False, f"{name} — unexpected {exc!r}"))


def expect_refuse(why: str, **kw) -> None:
    """Must raise Refuse — not return a result whose numbers merely look fine."""
    try:
        got = cs.scan(**kw)
    except cs.Refuse:
        return
    raise AssertionError(
        f"{why}: expected Refuse, got total={got['total']} covered={got['covered']}"
    )


def make_estate(tmp: Path, repos: dict[str, list[str]]) -> Path:
    """Build a throwaway estate of real git checkouts. `repos` maps dir name → files to track."""
    estate = tmp / "estate"
    for name, files in repos.items():
        repo = estate / name
        repo.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        for rel in files:
            f = repo / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("x\n")
        if files:
            subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    return estate


def conf_files(tmp: Path, repos: dict, stacks: dict, extra: dict | None = None) -> tuple[Path, Path]:
    sdlc = tmp / "sdlc.json"
    stacks_f = tmp / "stacks-policy.json"
    sdlc.write_text(json.dumps({"repos": repos}))
    payload = {"stacks": stacks}
    payload.update(extra or {})
    stacks_f.write_text(json.dumps(payload))
    return sdlc, stacks_f


# ── empty-input guards: the vacuous-green cases ────────────────────────────────────────

def t_no_repos():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        sdlc, stacks_f = conf_files(tmp, {}, {"web": {"repo": "r", "path": "src"}})
        expect_refuse("empty repos map", estate=tmp, sdlc=sdlc, stacks_file=stacks_f)


def t_no_stacks():
    """Zero stacks means zero claims, so 100% of files report uncovered — a number that
    reads as a catastrophic finding rather than as a broken input. Refuse instead."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        estate = make_estate(tmp, {"r": ["src/a.ts"]})
        sdlc, stacks_f = conf_files(tmp, {"r": "r"}, {})
        expect_refuse("empty stack registry", estate=estate, sdlc=sdlc, stacks_file=stacks_f)


def t_empty_corpus():
    """A git repo with nothing committed: 0 files, 0 uncovered — the perfect vacuous green."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        estate = make_estate(tmp, {"r": []})
        sdlc, stacks_f = conf_files(tmp, {"r": "r"}, {"web": {"repo": "r", "path": "src"}})
        expect_refuse("zero tracked files", estate=estate, sdlc=sdlc, stacks_file=stacks_f)


def t_missing_sdlc():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        _, stacks_f = conf_files(tmp, {"r": "r"}, {"web": {"repo": "r", "path": "src"}})
        expect_refuse("missing sdlc.json", estate=tmp, sdlc=tmp / "nope.json", stacks_file=stacks_f)


def t_missing_registry():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        sdlc, _ = conf_files(tmp, {"r": "r"}, {"web": {"repo": "r", "path": "src"}})
        expect_refuse("missing stacks-policy", estate=tmp, sdlc=sdlc, stacks_file=tmp / "nope.json")


def t_repo_absent_from_disk():
    """A declared repo that isn't there must refuse — skipping it shrinks the denominator
    and turns a missing checkout into a better-looking coverage percentage."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        estate = make_estate(tmp, {"r": ["src/a.ts"]})
        sdlc, stacks_f = conf_files(
            tmp, {"r": "r", "ghost": "not-on-disk"}, {"web": {"repo": "r", "path": "src"}})
        expect_refuse("declared repo absent", estate=estate, sdlc=sdlc, stacks_file=stacks_f)


def t_not_a_git_checkout():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        estate = tmp / "estate"
        (estate / "r").mkdir(parents=True)
        (estate / "r" / "a.ts").write_text("x\n")
        sdlc, stacks_f = conf_files(tmp, {"r": "r"}, {"web": {"repo": "r", "path": "src"}})
        expect_refuse("non-git directory", estate=estate, sdlc=sdlc, stacks_file=stacks_f)


def t_stack_without_path():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        estate = make_estate(tmp, {"r": ["src/a.ts"]})
        sdlc, stacks_f = conf_files(tmp, {"r": "r"}, {"web": {"repo": "r"}})
        expect_refuse("stack declaring no path", estate=estate, sdlc=sdlc, stacks_file=stacks_f)


def t_exemption_without_reason():
    """T135's rule, applied to the new noun: an exemption recorded as a bare name cannot be
    re-evaluated by whoever finds it next."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        estate = make_estate(tmp, {"r": ["src/a.ts", "docs/b.ts"]})
        sdlc, stacks_f = conf_files(
            tmp, {"r": "r"}, {"web": {"repo": "r", "path": "src"}},
            extra={"coverage_exempt": {"r/docs": ""}})
        expect_refuse("reasonless exemption", estate=estate, sdlc=sdlc, stacks_file=stacks_f)


def t_exemption_wrong_type():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        estate = make_estate(tmp, {"r": ["src/a.ts", "docs/b.ts"]})
        sdlc, stacks_f = conf_files(
            tmp, {"r": "r"}, {"web": {"repo": "r", "path": "src"}},
            extra={"coverage_exempt": ["r/docs"]})
        expect_refuse("exemption as a bare list", estate=estate, sdlc=sdlc, stacks_file=stacks_f)


# ── real-fault cases: the scan must actually REPORT the gap ────────────────────────────

def t_uncovered_code_is_reported():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        estate = make_estate(tmp, {"r": ["src/a.ts", "packages/ui/b.ts"]})
        sdlc, stacks_f = conf_files(tmp, {"r": "r"}, {"web": {"repo": "r", "path": "src"}})
        got = cs.scan(estate=estate, sdlc=sdlc, stacks_file=stacks_f)
        assert got["uncovered_code"] == 1, got
        assert got["covered"] == 1, got
        assert dict(got["code_groups"])["r/packages/ui"] == 1, got["code_groups"]


def t_non_code_is_not_in_the_worklist():
    """1,730 uncovered markdown files must not bury 15 real ones."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        estate = make_estate(tmp, {"r": ["src/a.ts", "docs/x.md", "docs/y.png"]})
        sdlc, stacks_f = conf_files(tmp, {"r": "r"}, {"web": {"repo": "r", "path": "src"}})
        got = cs.scan(estate=estate, sdlc=sdlc, stacks_file=stacks_f)
        assert got["uncovered_code"] == 0, got
        assert got["uncovered_other"] == 2, got


def t_reasoned_exemption_suppresses():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        estate = make_estate(tmp, {"r": ["src/a.ts", "vendor/b.ts"]})
        sdlc, stacks_f = conf_files(
            tmp, {"r": "r"}, {"web": {"repo": "r", "path": "src"}},
            extra={"coverage_exempt": {"r/vendor": "third-party, upstream owns its gates"}})
        got = cs.scan(estate=estate, sdlc=sdlc, stacks_file=stacks_f)
        assert got["uncovered_code"] == 0, got
        assert got["exempted"] == 1, got


def t_group_keys_on_directory_not_prefix():
    """🔴 REGRESSION PROBE. `_group` first returned the path's first two segments, which made
    every file sitting directly in `scripts/` its own 'group' — the live run printed 40 rows of
    `w0m-web/scripts/<file>` that read as 40 findings for what is one directory and one
    decision. A worklist that inflates its own row count is precisely the defect this scan
    exists to find. Reverting `_group` to `parts[:2]` turns this case red."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        estate = make_estate(tmp, {"r": ["src/a.ts", "scripts/one.js", "scripts/two.js",
                                         "scripts/three.js"]})
        sdlc, stacks_f = conf_files(tmp, {"r": "r"}, {"web": {"repo": "r", "path": "src"}})
        got = cs.scan(estate=estate, sdlc=sdlc, stacks_file=stacks_f)
        groups = dict(got["code_groups"])
        assert groups == {"r/scripts": 3}, f"three files in one dir must be ONE group, got {groups}"


def t_nested_repo_path_resolves():
    """`mlx` declares the nested `w0m-mlx/w0m-mlx`; a claim keyed on the whole string would
    match no repo and silently report the entire repo as uncovered."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        estate = make_estate(tmp, {"outer": ["inner/src/a.ts"]})
        sdlc, stacks_f = conf_files(
            tmp, {"mlx": "outer"}, {"mlx": {"repo": "outer/inner", "path": "inner/src"}})
        got = cs.scan(estate=estate, sdlc=sdlc, stacks_file=stacks_f)
        assert got["covered"] == 1 and got["uncovered_code"] == 0, got


def t_exit_code_is_report_only():
    """AC5: a long worklist still exits 0. If this ever returns non-zero the scan has quietly
    become a gate, and the pre-push hooks gain a blocker nobody agreed to."""
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parent / "coverage_scan.py")],
        capture_output=True, text=True, timeout=180,
    )
    assert proc.returncode == 0, f"must exit 0 on a live scan, got {proc.returncode}"
    assert "uncovered" in proc.stdout, "must actually report"


CASES = [
    ("empty repos map refuses", t_no_repos),
    ("empty stack registry refuses", t_no_stacks),
    ("zero tracked files refuses", t_empty_corpus),
    ("missing sdlc.json refuses", t_missing_sdlc),
    ("missing stacks-policy refuses", t_missing_registry),
    ("declared-but-absent repo refuses", t_repo_absent_from_disk),
    ("non-git directory refuses", t_not_a_git_checkout),
    ("stack with no path refuses", t_stack_without_path),
    ("reasonless exemption refuses", t_exemption_without_reason),
    ("exemption as a bare list refuses", t_exemption_wrong_type),
    ("uncovered code reaches the worklist", t_uncovered_code_is_reported),
    ("non-code stays out of the worklist", t_non_code_is_not_in_the_worklist),
    ("reasoned exemption suppresses", t_reasoned_exemption_suppresses),
    ("groups key on directory, not prefix (regression)", t_group_keys_on_directory_not_prefix),
    ("nested repo path resolves", t_nested_repo_path_resolves),
    ("report-only: exits 0 (AC5)", t_exit_code_is_report_only),
]


def main() -> int:
    if not CASES:
        print("✗ coverage-scan-test: no cases — refusing to report a green over nothing")
        return 2
    for name, fn in CASES:
        case(name, fn)
    for ok, name in results:
        print(f"  {PASS if ok else FAIL} {name}")
    bad = [n for ok, n in results if not ok]
    print(f"\n{'✅' if not bad else '❌'} coverage-scan-test — "
          f"{len(results) - len(bad)}/{len(results)} passed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
