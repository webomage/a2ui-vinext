#!/usr/bin/env python3
"""T241 — Scoped OpenSpec validation in pre-push `w0m_audit.py` (`check_drift`).

Proves all 6 ACs of T241:
  - AC1: `check_drift(scope_diff=...)` wires `scope_diff` to BOTH `spec_drift_gate.py` and
    `openspec validate` (covering tracked `openspec/changes/<id>`, tracked `openspec/specs/<id>`,
    and `.tasks/T*.md` ticket-linked specs/changes), ignoring untracked directories on disk.
  - AC2: `w0m-web/.husky/pre-push` (`w0m audit (scoped drift + openspec)`) and `scripts/w0m_audit.py`
    (`--scope-diff` CLI help + `check_drift`) agree on scoped behaviour.
  - AC3: Scoped OpenSpec output explicitly prints both the count validated and the count skipped
    (`validated K touched item(s), skipped M untouched item(s) (scope: <ref>); N untracked ignored`),
    never silently narrowing coverage.
  - AC4: Unscoped `check_drift(scope_diff=None)` (`just audit`) continues running
    `openspec validate --all --strict` across the entire tree.
  - AC5: Red/green probes in both directions:
    * An invalid untracked (or untouched tracked) OpenSpec change OUTSIDE the push diff does NOT
      block `check_drift(scope_diff=...)`.
    * An invalid OpenSpec change or spec INSIDE the push diff DOES fail `check_drift(scope_diff=...)`.
    * Unscoped `check_drift(scope_diff=None)` catches the invalid change via `--all --strict`.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

MONO_ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = MONO_ROOT / "w0m-web"
SCRIPTS_DIR = MONO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import w0m_audit as wa  # noqa: E402


def _init_git_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "beta"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@w0m.io"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "w0m Test"], cwd=path, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=path, check=True)
    subprocess.run(["git", "config", "tag.gpgSign", "false"], cwd=path, check=True)


def _write_fake_openspec_cli(bin_path: Path) -> None:
    """Create a deterministic executable `openspec` stub that validates directories on disk.

    Mimics `@fission-ai/openspec validate`:
      - `--all --strict`: scans ALL `openspec/changes/*` (except `archive`) and `openspec/specs/*`
        on disk (including untracked directories!), failing if any contains `INVALID_OPENSPEC`.
      - `<item> --strict`: validates the named change or spec directory on disk, failing if it
        contains `INVALID_OPENSPEC` or is missing required files.
    """
    script = """#!/usr/bin/env python3
import sys
from pathlib import Path

args = sys.argv[1:]
cwd = Path.cwd()
changes_dir = cwd / "openspec" / "changes"
specs_dir = cwd / "openspec" / "specs"

def is_valid_dir(d: Path) -> tuple[bool, str]:
    if not d.is_dir():
        return False, f"Item '{d.name}' not found"
    for f in d.rglob("*"):
        if f.is_file() and "INVALID_OPENSPEC" in f.read_text(encoding="utf-8", errors="ignore"):
            return False, f"Validation failed for '{d.name}': missing required SHALL/scenario block"
    return True, f"'{d.name}' is valid"

if "--all" in args:
    items = []
    if changes_dir.is_dir():
        items.extend(sorted([d for d in changes_dir.iterdir() if d.is_dir() and d.name != "archive"]))
    if specs_dir.is_dir():
        items.extend(sorted([d for d in specs_dir.iterdir() if d.is_dir()]))
    failed = []
    for d in items:
        ok, msg = is_valid_dir(d)
        if not ok:
            failed.append(msg)
    if failed:
        for m in failed:
            print(m, file=sys.stderr)
        print(f"Totals: {len(items) - len(failed)} passed, {len(failed)} failed ({len(items)} items)")
        sys.exit(1)
    print(f"Totals: {len(items)} passed, 0 failed ({len(items)} items)")
    sys.exit(0)
else:
    item_names = [a for a in args if not a.startswith("-") and a != "validate"]
    if not item_names:
        print("No item specified", file=sys.stderr)
        sys.exit(1)
    name = item_names[0]
    target = changes_dir / name
    if not target.is_dir():
        target = specs_dir / name
    ok, msg = is_valid_dir(target)
    if not ok:
        print(msg, file=sys.stderr)
        sys.exit(1)
    print(msg)
    sys.exit(0)
"""
    bin_path.parent.mkdir(parents=True, exist_ok=True)
    bin_path.write_text(script, encoding="utf-8")
    bin_path.chmod(bin_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


class TestT241ScopedOpenSpec(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp(prefix="w0m-t241-test-"))
        self.orig_mono = wa.MONO_ROOT
        self.orig_web = wa.WEB_ROOT
        self.orig_results = list(wa.results)

        self.mono = self.tmpdir / "mono"
        self.web = self.mono / "w0m-web"
        _init_git_repo(self.mono)
        (self.mono / ".gitignore").write_text("w0m-web/\n", encoding="utf-8")

        # Provide minimal spec_drift_gate.py in self.mono/scripts so check_drift runs cleanly
        (self.mono / "scripts").mkdir(parents=True, exist_ok=True)
        (self.mono / "scripts" / "spec_drift_gate.py").write_text(
            "#!/usr/bin/env python3\nimport sys\nprint('spec-drift-gate OK')\nsys.exit(0)\n",
            encoding="utf-8",
        )
        (self.mono / ".tasks").mkdir(parents=True, exist_ok=True)
        (self.mono / ".tasks" / "T100.md").write_text(
            "---\nid: T100\nstatus: in-progress\nspec: openspec/changes/2026-08-01-valid-change\n---\n# T100\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "."], cwd=self.mono, check=True)
        subprocess.run(["git", "commit", "-qm", "chore: base mono"], cwd=self.mono, check=True)
        subprocess.run(["git", "tag", "base-ref"], cwd=self.mono, check=True)

        _init_git_repo(self.web)

        # Create fake openspec binary at WEB_ROOT/node_modules/.bin/openspec
        _write_fake_openspec_cli(self.web / "node_modules" / ".bin" / "openspec")

        # Create 2 valid tracked OpenSpec items (1 change + 1 spec) at base-ref
        c_valid = self.web / "openspec" / "changes" / "2026-08-01-valid-change"
        c_valid.mkdir(parents=True, exist_ok=True)
        (c_valid / "proposal.md").write_text("# Valid Change\n", encoding="utf-8")
        (c_valid / "tasks.md").write_text("- [ ] 1.1 Task\n", encoding="utf-8")

        s_valid = self.web / "openspec" / "specs" / "valid-domain-spec"
        s_valid.mkdir(parents=True, exist_ok=True)
        (s_valid / "spec.md").write_text("# Valid Spec\n", encoding="utf-8")

        (self.web / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.web, check=True)
        subprocess.run(["git", "commit", "-qm", "chore: base web"], cwd=self.web, check=True)
        subprocess.run(["git", "tag", "base-ref"], cwd=self.web, check=True)

        wa.MONO_ROOT = self.mono
        wa.WEB_ROOT = self.web
        wa.results.clear()

    def tearDown(self) -> None:
        wa.MONO_ROOT = self.orig_mono
        wa.WEB_ROOT = self.orig_web
        wa.results.clear()
        wa.results.extend(self.orig_results)
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _openspec_result(self) -> tuple[str, str, str, str]:
        matches = [r for r in wa.results if r[1] == "spec" and r[2].startswith("openspec validate")]
        self.assertEqual(len(matches), 1, f"Expected 1 openspec result, got: {wa.results}")
        return matches[0]

    def test_ac1_ac3_ac5_untracked_invalid_change_outside_push_does_not_block_scoped(self) -> None:
        """An untracked half-written invalid OpenSpec change does NOT block scoped pre-push, and counts are printed."""
        # Push commit touches an unrelated app file
        (self.web / "app.ts").write_text("export const x = 1;\n", encoding="utf-8")
        subprocess.run(["git", "add", "app.ts"], cwd=self.web, check=True)
        subprocess.run(["git", "commit", "-qm", "feat: touch app.ts"], cwd=self.web, check=True)

        # Another agent creates an untracked, invalid OpenSpec change directory on disk
        untracked_bad = self.web / "openspec" / "changes" / "2026-08-20-untracked-broken"
        untracked_bad.mkdir(parents=True, exist_ok=True)
        (untracked_bad / "proposal.md").write_text("INVALID_OPENSPEC half-written draft\n", encoding="utf-8")

        wa.results.clear()
        wa.check_drift(scope_diff="base-ref")
        lvl, _sec, name, detail = self._openspec_result()

        self.assertEqual(lvl, wa.PASS, f"Untracked invalid change should not fail scoped check: {detail}")
        self.assertEqual(name, "openspec validate (scoped)")
        self.assertIn("validated 0 touched item(s)", detail)
        self.assertIn("skipped 2 untouched item(s) (scope: base-ref)", detail)
        self.assertIn("1 untracked ignored", detail)

        # AC4 + AC5: Unscoped check_drift(scope_diff=None) runs --all --strict and DOES fail on the untracked broken dir
        wa.results.clear()
        wa.check_drift(scope_diff=None)
        lvl_full, _sec, name_full, detail_full = self._openspec_result()
        self.assertEqual(lvl_full, wa.FAIL, "Unscoped audit must still catch the invalid untracked change")
        self.assertEqual(name_full, "openspec validate --all --strict")

    def test_ac5_untouched_tracked_invalid_change_outside_push_does_not_block_scoped(self) -> None:
        """A tracked invalid OpenSpec change committed before base-ref (untouched in push) is skipped in scoped mode."""
        untouched_bad = self.web / "openspec" / "changes" / "2026-07-01-preexisting-invalid"
        untouched_bad.mkdir(parents=True, exist_ok=True)
        (untouched_bad / "proposal.md").write_text("INVALID_OPENSPEC legacy\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.web, check=True)
        subprocess.run(["git", "commit", "-qm", "chore: legacy invalid change"], cwd=self.web, check=True)
        subprocess.run(["git", "tag", "-f", "base-ref"], cwd=self.web, check=True)

        # Push commit only touches app.ts
        (self.web / "app.ts").write_text("export const x = 2;\n", encoding="utf-8")
        subprocess.run(["git", "add", "app.ts"], cwd=self.web, check=True)
        subprocess.run(["git", "commit", "-qm", "feat: unrelated push"], cwd=self.web, check=True)

        wa.results.clear()
        wa.check_drift(scope_diff="base-ref")
        lvl, _sec, _name, detail = self._openspec_result()
        self.assertEqual(lvl, wa.PASS)
        self.assertIn("validated 0 touched item(s)", detail)
        self.assertIn("skipped 3 untouched item(s) (scope: base-ref)", detail)

    def test_ac5_invalid_change_inside_push_blocks_scoped(self) -> None:
        """RED probe: an invalid OpenSpec change modified INSIDE the push diff MUST fail check_drift(scope_diff=...)."""
        in_push_bad = self.web / "openspec" / "changes" / "2026-10-22-in-push-invalid"
        in_push_bad.mkdir(parents=True, exist_ok=True)
        (in_push_bad / "proposal.md").write_text("INVALID_OPENSPEC broken in this push\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.web, check=True)
        subprocess.run(["git", "commit", "-qm", "feat: add broken openspec change"], cwd=self.web, check=True)

        wa.results.clear()
        wa.check_drift(scope_diff="base-ref")
        lvl, _sec, name, detail = self._openspec_result()
        self.assertEqual(lvl, wa.FAIL, f"Invalid change inside push diff must fail scoped check: {detail}")
        self.assertEqual(name, "openspec validate (scoped)")
        self.assertIn("2026-10-22-in-push-invalid", detail)
        self.assertIn("missing required SHALL/scenario block", detail)
        self.assertIn("validated 1 touched item(s), skipped 2 untouched item(s)", detail)

    def test_ac1_ac5_invalid_spec_inside_push_blocks_scoped(self) -> None:
        """RED probe: an invalid OpenSpec spec (`openspec/specs/<id>`) modified in the push MUST also fail scoped check."""
        spec_file = self.web / "openspec" / "specs" / "valid-domain-spec" / "spec.md"
        spec_file.write_text("INVALID_OPENSPEC broken spec requirement\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.web, check=True)
        subprocess.run(["git", "commit", "-qm", "feat: break domain spec"], cwd=self.web, check=True)

        wa.results.clear()
        wa.check_drift(scope_diff="base-ref")
        lvl, _sec, _name, detail = self._openspec_result()
        self.assertEqual(lvl, wa.FAIL, f"Invalid spec inside push diff must fail scoped check: {detail}")
        self.assertIn("valid-domain-spec", detail)
        self.assertIn("missing required SHALL/scenario block", detail)
        self.assertIn("validated 1 touched item(s), skipped 1 untouched item(s)", detail)

    def test_ac1_ac3_valid_touched_change_and_ticket_link_pass_and_print_skipped(self) -> None:
        """Touching a valid change or its owning `.tasks/T*.md` ticket validates that item and prints skipped count."""
        # Touch only .tasks/T100.md in MONO_ROOT (which links to 2026-08-01-valid-change)
        t100 = self.mono / ".tasks" / "T100.md"
        t100.write_text(
            "---\nid: T100\nstatus: done\nspec: openspec/changes/2026-08-01-valid-change\n---\n# T100 done\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "."], cwd=self.mono, check=True)
        subprocess.run(["git", "commit", "-qm", "feat(T100): close T100"], cwd=self.mono, check=True)

        wa.results.clear()
        wa.check_drift(scope_diff="base-ref")
        lvl, _sec, _name, detail = self._openspec_result()
        self.assertEqual(lvl, wa.PASS)
        self.assertIn("validated 1 touched item(s), skipped 1 untouched item(s) (scope: base-ref)", detail)

    def test_ac2_hook_comment_and_audit_script_agree(self) -> None:
        """`.husky/pre-push` and `scripts/w0m_audit.py` agree on scoped drift + openspec behaviour."""
        pre_push = (WEB_ROOT / ".husky" / "pre-push").read_text(encoding="utf-8")
        audit_py = (MONO_ROOT / "scripts" / "w0m_audit.py").read_text(encoding="utf-8")

        self.assertIn("w0m audit (scoped drift + openspec)", pre_push)
        self.assertIn("--scope-diff origin/beta", pre_push)
        self.assertIn("scope spec-drift and openspec validate to changes vs REF", audit_py)
        self.assertIn("_openspec_scope_plan(scope_diff)", audit_py)


if __name__ == "__main__":
    unittest.main()
