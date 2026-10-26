#!/usr/bin/env python3
"""Regression proof for annotations_doctor (T342).

Asserts:
  1. Synthetic files with each category of annotation are correctly parsed and counted:
     - overrides: @ts-ignore, @ts-expect-error, @ts-nocheck, as any, type: ignore
     - hacks: HACK, WORKAROUND, XXX, TEMP, TEMPORARY
     - ignores: eslint-disable, prettier-ignore, biome-ignore, noqa, type: ignore, golangci-lint
     - todos: TODO, FIXME
     - hotfixes: HOTFIX, QUICKFIX, PATCH
     - lintexcludes: lintexclude, skipcq, linter:disable
  2. Skip directories (node_modules, dist, target, .superpowers) are excluded from scan.
  3. Empty-input-set rule: fails closed with exit 1 on empty candidate corpus.
  4. Gating mode: --enforce exits 1 when annotations exist.
  5. Machine-readable: --json outputs valid JSON.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "annotations_doctor.py"
failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'✅' if ok else '❌'} {label}")
    if not ok:
        failures.append(f"{label}{(' — ' + detail) if detail else ''}")


def run_doctor(args: list[str], env: dict | None = None) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(SCRIPT)] + args
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


def test_categories_detection() -> None:
    print("\n▶ test_categories_detection — verify detection of each annotation category")
    with tempfile.TemporaryDirectory(prefix="w0m-annotations-test-") as tmp:
        base = Path(tmp)
        web = base / "w0m-web"
        web_project = web / "project"
        web_project.mkdir(parents=True)

        policy = {
            "repos": [
                {"path": "w0m-web"}
            ]
        }
        (web_project / "hygiene-policy.json").write_text(json.dumps(policy, indent=2))

        # Sample code file with annotations
        sample_code = """
// @ts-ignore
const x: number = "hello" as any;
// @ts-expect-error
const y = 1;
// @ts-nocheck

# HACK: temporary workaround
# XXX: check this later
# TEMP: remove after release
# WORKAROUND for upstream bug
# TEMPORARY hack

/* eslint-disable no-console */
// prettier-ignore
// biome-ignore lint/suspicious
# ruff: noqa
# noqa: E501
// golangci-lint:ignore errcheck

// TODO: implement this
// FIXME: broken edge case

// HOTFIX: patch for live bug
// QUICKFIX: temporary patch
// PATCH: manual hotfix applied

// lintexclude: rule-123
// skipcq: JS-001
// linter:disable all
"""
        (web / "test.ts").write_text(sample_code)

        env = {**os.environ, "W0M_HYGIENE_ROOT": str(base)}
        res = run_doctor(["--json"], env=env)
        check("exit 0 on valid scan", res.returncode == 0, res.stderr)

        data = json.loads(res.stdout)
        summary = data["summary"]
        check("detects overrides", summary.get("overrides", 0) >= 4, f"got {summary.get('overrides')}")
        check("detects hacks", summary.get("hacks", 0) >= 5, f"got {summary.get('hacks')}")
        check("detects ignores", summary.get("ignores", 0) >= 5, f"got {summary.get('ignores')}")
        check("detects todos", summary.get("todos", 0) >= 2, f"got {summary.get('todos')}")
        check("detects hotfixes", summary.get("hotfixes", 0) >= 3, f"got {summary.get('hotfixes')}")
        check("detects lintexcludes", summary.get("lintexcludes", 0) >= 3, f"got {summary.get('lintexcludes')}")


def test_skip_directories() -> None:
    print("\n▶ test_skip_directories — verify excluded trees are ignored")
    with tempfile.TemporaryDirectory(prefix="w0m-annotations-skip-") as tmp:
        base = Path(tmp)
        web = base / "w0m-web"
        web_project = web / "project"
        web_project.mkdir(parents=True)

        policy = {"repos": [{"path": "w0m-web"}]}
        (web_project / "hygiene-policy.json").write_text(json.dumps(policy, indent=2))

        # Root file with 1 TODO
        (web / "valid.ts").write_text("// TODO: legitimate\n")

        # Excluded directories with markers that should NOT be counted
        (web / "node_modules").mkdir()
        (web / "node_modules" / "pkg.ts").write_text("// TODO: should be skipped\n// HACK: skip\n")

        (web / "dist").mkdir()
        (web / "dist" / "bundle.js").write_text("// HACK: compiled\n")

        (web / ".superpowers").mkdir()
        (web / ".superpowers" / "scratch.ts").write_text("// TODO: agent scratch\n")

        env = {**os.environ, "W0M_HYGIENE_ROOT": str(base)}
        res = run_doctor(["--json"], env=env)
        data = json.loads(res.stdout)

        check("only valid file scanned", data["total_files"] == 1, f"scanned {data['total_files']} files")
        check("only valid annotations counted", data["total_matches"] == 1, f"found {data['total_matches']}")


def test_empty_input_set_fails() -> None:
    print("\n▶ test_empty_input_set_fails — verify empty corpus rule")
    with tempfile.TemporaryDirectory(prefix="w0m-annotations-empty-") as tmp:
        base = Path(tmp)
        web = base / "w0m-web"
        web_project = web / "project"
        web_project.mkdir(parents=True)

        policy = {"repos": [{"path": "w0m-web"}]}
        (web_project / "hygiene-policy.json").write_text(json.dumps(policy, indent=2))

        # Empty repo with no code files
        env = {**os.environ, "W0M_HYGIENE_ROOT": str(base)}
        res = run_doctor([], env=env)
        check("empty corpus exits non-zero", res.returncode != 0)
        check("reports EMPTY CORPUS error", "EMPTY CORPUS" in res.stderr or "EMPTY CORPUS" in res.stdout)


def test_enforce_mode() -> None:
    print("\n▶ test_enforce_mode — verify --enforce flag fails on annotations")
    with tempfile.TemporaryDirectory(prefix="w0m-annotations-enforce-") as tmp:
        base = Path(tmp)
        web = base / "w0m-web"
        web_project = web / "project"
        web_project.mkdir(parents=True)

        policy = {"repos": [{"path": "w0m-web"}]}
        (web_project / "hygiene-policy.json").write_text(json.dumps(policy, indent=2))

        (web / "code.ts").write_text("// TODO: must fail enforce\n")

        env = {**os.environ, "W0M_HYGIENE_ROOT": str(base)}
        res = run_doctor(["--enforce"], env=env)
        check("--enforce exits 1 on finding", res.returncode == 1)
        check("names ENFORCE failure", "ENFORCE" in res.stderr)


def main() -> int:
    test_categories_detection()
    test_skip_directories()
    test_empty_input_set_fails()
    test_enforce_mode()

    if failures:
        print(f"\n❌ {len(failures)} probe(s) failed:")
        for f in failures:
            print(f"  • {f}")
        return 1

    print("\n✅ all annotations_doctor regression probes passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
