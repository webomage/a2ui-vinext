#!/usr/bin/env python3
"""Unit tests for `scripts/hook_pin_drift_check.py` (T767).

Contract under test (T767): every estate repo's pinned security-scanner hook rev
(`osv-scanner`, `gitleaks`) must match the gate binary's major.minor. Patch-level
lag is allowed but DECLARED (reported, never silent). A repo whose gate binary is
unresolvable is UNMEASURABLE: exit 2, never a silent pass. No pin is ever
auto-bumped: the check reports with a named repo + rev; the human commits the bump
(T112).

Fixture-based only. No estate repo files are touched, and no real security
binary is required (version probing is injected).

Exit vocabulary (aligned with `scripts/hooks_check.py`, T767 AC4):
  0 conformant - 1 findings - 2 unmeasurable/config error.
"""

from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hook_pin_drift_check import (
    OK_VERDICT,
    compare_rev_to_gate,
    check_estate,
    main,
    parse_gate_version,
    parse_pin_rev,
)

CONFIG_TEMPLATE = """\
repos:
  - repo: https://github.com/gitleaks/gitleaks
    rev: {gitleaks_rev}
    hooks:
      - id: gitleaks
  - repo: https://github.com/google/osv-scanner
    rev: {osv_rev}
    hooks:
      - id: osv-scanner
"""


def make_estate(root: Path, names: "list[str]") -> None:
    """Fixture estate: .w0m/sdlc.json declaring the repo dirs created below."""
    (root / ".w0m").mkdir(parents=True, exist_ok=True)
    (root / ".w0m" / "sdlc.json").write_text(
        json.dumps({"repos": {n: n for n in names}}), encoding="utf-8"
    )


def write_repo(
    root: Path, name: str, *, osv_rev: Optional[str], gitleaks_rev: Optional[str]
) -> Path:
    rdir = root / name
    rdir.mkdir(parents=True)
    make_estate(root, [name])
    text = CONFIG_TEMPLATE
    if osv_rev is None:
        text = strip_hook(text, "osv-scanner")
    if gitleaks_rev is None:
        text = strip_hook(text, "gitleaks")
    text = text.format(
        osv_rev=osv_rev or "PLACEHOLDER", gitleaks_rev=gitleaks_rev or "PLACEHOLDER"
    )
    (rdir / ".pre-commit-config.yaml").write_text(text, encoding="utf-8")
    (rdir / ".git").mkdir(exist_ok=True)
    return rdir


def strip_hook(text: str, hook_id: str) -> str:
    lines_out: list[str] = []
    skipping = 0
    for line in text.split("\n"):
        if f"- id: {hook_id}" in line:
            skipping = 1
            # also drop the rev line directly above
            if lines_out and lines_out[-1].strip() == "":
                pass
            lines_out.pop() if lines_out and "rev:" in lines_out[-1] else None
            continue
        if skipping and line.strip():
            skipping = 0
        elif skipping:
            continue
        lines_out.append(line)
    return "\n".join(lines_out)


def run_main(root: Path, resolvers: dict) -> "tuple[int, str, str]":
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(argv=["--estate-root", str(root)], version_resolvers=resolvers)
    return code, out.getvalue(), err.getvalue()


class ParsePinRevTests(unittest.TestCase):
    def test_finds_rev_of_named_hook_without_cross_repo_bleed(self) -> None:
        text = CONFIG_TEMPLATE.format(gitleaks_rev="v8.30.0", osv_rev="v2.7.0")
        self.assertEqual(parse_pin_rev(text, "osv-scanner"), "v2.7.0")
        self.assertEqual(parse_pin_rev(text, "gitleaks"), "v8.30.0")
        self.assertIsNone(parse_pin_rev("repos: []\n", "osv-scanner"))

    def test_tolerates_crlf(self) -> None:
        text = (
            "repos:\r\n  - repo: x\r\n    rev: v2.7.0\r\n"
            "    hooks:\r\n      - id: osv-scanner\r\n"
        )
        self.assertEqual(parse_pin_rev(text, "osv-scanner"), "v2.7.0")


class ParseGateVersionTests(unittest.TestCase):
    def test_prefix_and_bare_semver_forms(self) -> None:
        self.assertEqual(parse_gate_version("osv-scanner version: 2.7.1"), "2.7.1")
        self.assertEqual(parse_gate_version("8.30.1"), "8.30.1")
        self.assertEqual(parse_gate_version("gitleaks version 8.30.1\n"), "8.30.1")
        self.assertIsNone(parse_gate_version("usage: try --help"))
        self.assertIsNone(parse_gate_version(""))


class CompareRevTests(unittest.TestCase):
    def test_match_patch_lag_and_drift(self) -> None:
        self.assertEqual(compare_rev_to_gate("v2.7.0", "2.7.0"), OK_VERDICT)
        self.assertEqual(compare_rev_to_gate("v2.7.0", "2.7.1"), "PATCH_LAG")
        self.assertEqual(compare_rev_to_gate("v2.4.0", "2.7.1"), "MAJOR_MINOR_DRIFT")
        self.assertEqual(compare_rev_to_gate("not-a-version", "2.7.1"), "UNPARSEABLE")


class CheckEstateTests(unittest.TestCase):
    def test_red_exit_one_when_pin_reverted_to_v2_4_0(self) -> None:
        """T767 AC1 red: the T766 pre-fix state (pin v2.4.0 vs gate 2.7.x) must fail."""
        with TemporaryDirectory() as td:
            root = Path(td)
            write_repo(root, "alpha", osv_rev="v2.4.0", gitleaks_rev="v8.30.0")
            code, out, _ = run_main(root, {"osv-scanner": "2.7.1", "gitleaks": "8.30.1"})
            self.assertEqual(code, 1, "drifted pin must exit 1")
            self.assertIn("alpha", out)
            self.assertIn("v2.4.0", out)
            self.assertIn("2.7.1", out)

    def test_green_when_pins_share_gate_major_minor(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            write_repo(root, "alpha", osv_rev="v2.7.0", gitleaks_rev="v8.30.0")
            code, out, _ = run_main(root, {"osv-scanner": "2.7.1", "gitleaks": "8.30.1"})
            self.assertEqual(code, 0)
            self.assertIn("PATCH_LAG", out, "patch lag must be reported, declared")

    def test_exact_match_is_silent_green(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            write_repo(root, "alpha", osv_rev="v2.7.1", gitleaks_rev="v8.30.1")
            code, out, _ = run_main(root, {"osv-scanner": "2.7.1", "gitleaks": "8.30.1"})
            self.assertEqual(code, 0)
            self.assertNotIn("PATCH_LAG", out)

    def test_unmeasurable_when_no_resolvable_gate_binary(self) -> None:
        """T767 AC3: a missing binary is UNMEASURABLE: exit 2, named, never silent."""
        with TemporaryDirectory() as td:
            root = Path(td)
            write_repo(root, "alpha", osv_rev="v2.7.0", gitleaks_rev="v8.30.0")
            code, out, _ = run_main(root, {"osv-scanner": "2.7.1", "gitleaks": None})
            self.assertEqual(code, 2)
            self.assertIn("UNMEASURABLE", out)
            self.assertIn("gitleaks", out)

    def test_repo_without_security_hooks_is_skipped_not_failed(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            write_repo(root, "bare", osv_rev=None, gitleaks_rev=None)
            code, out, _ = run_main(root, {"osv-scanner": "2.7.1", "gitleaks": "8.30.1"})
            self.assertEqual(code, 0)
            self.assertIn("bare", out, "skipped repos are named, not hidden")

    def test_missing_binaries_everywhere_is_unmeasurable(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            write_repo(root, "alpha", osv_rev="v2.7.0", gitleaks_rev="v8.30.0")
            code, _, _ = run_main(root, {"osv-scanner": None, "gitleaks": None})
            self.assertEqual(code, 2)


class MainWiringTests(unittest.TestCase):
    def test_arguments_rejected_cleanly_exit_two(self) -> None:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv=["--estate-root", "/definitely/not/a/place"])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
