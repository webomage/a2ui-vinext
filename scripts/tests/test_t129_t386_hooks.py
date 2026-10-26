#!/usr/bin/env python3
"""T129 & T386 — Commit-msg T## gate, anti-dodge calibration, and unified just hook runner tests."""
from __future__ import annotations

import io
import json
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

ESTATE_ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = ESTATE_ROOT / "wom7web"
SCRIPTS_DIR = ESTATE_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import conventional_commit as cc  # noqa: E402
import hooks_check as hc  # noqa: E402

JUST_ENTRY_RE = re.compile(r"^just\s+([a-zA-Z0-9_-]+)(?:\s+.*)?$")
JUSTFILE_RECIPE_RE = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_-]*)(?:\s+[^:]*)?:(?!=)", re.MULTILINE)
UNIVERSAL_HOOK_IDS = {"gitleaks", "osv-scanner", "codegraph-sync"}


def parse_local_hooks(cfg_path: Path) -> list[dict[str, str]]:
    """Extract hook id and entry pairs from a .pre-commit-config.yaml file."""
    hooks: list[dict[str, str]] = []
    cur: dict[str, str] | None = None
    for raw_line in cfg_path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m_id = re.match(r"^-\s+id:\s*(\S+)", stripped)
        if m_id:
            if cur is not None:
                hooks.append(cur)
            cur = {"id": m_id.group(1), "entry": ""}
            continue
        if cur is not None:
            m_entry = re.match(r"^entry:\s*(.+)$", stripped)
            if m_entry:
                cur["entry"] = m_entry.group(1).strip()
    if cur is not None:
        hooks.append(cur)
    return hooks


class TestT129CommitMsgGate(unittest.TestCase):
    """T129 AC1–AC5: Commit-msg T## ticket enforcement + staged-file anti-dodge calibration."""

    def test_ac1_non_trivial_commit_types_require_ticket(self) -> None:
        """feat/fix/refactor/perf/test/security/build without T## must fail."""
        for ctype in ("feat", "fix", "refactor", "perf", "test", "security", "build"):
            ok, err = cc.validate_commit_message(
                f"{ctype}(cp): add button",
                staged_files=[],
            )
            self.assertFalse(ok, f"{ctype} without T## should fail")
            self.assertIn("requires a ticket reference (T##)", err)

    def test_ac1_non_trivial_commit_passes_with_ticket_in_subject_or_body(self) -> None:
        """T## in subject or body satisfies the gate for non-trivial commit types."""
        ok_subj, err_subj = cc.validate_commit_message(
            "feat(cp): add button (T129)",
            staged_files=["apps/cp/src/pages/index.astro"],
        )
        self.assertTrue(ok_subj, err_subj)

        ok_body, err_body = cc.validate_commit_message(
            "fix(api): prevent null deref\n\nCloses T129 and T386.",
            staged_files=["wom7api/src/index.ts"],
        )
        self.assertTrue(ok_body, err_body)

    def test_ac1_exempt_commit_types_and_synthetic_subjects_pass(self) -> None:
        """chore/docs/style/ci/revert on non-code files and Merge/Revert/fixup!/squash! pass."""
        ok_chore, err_chore = cc.validate_commit_message(
            "chore(state): refresh STATE.md",
            staged_files=["STATE.md"],
        )
        self.assertTrue(ok_chore, err_chore)

        ok_docs, err_docs = cc.validate_commit_message(
            "docs(readme): fix typo in overview",
            staged_files=["README.md", "docs/ARCHITECTURE.md"],
        )
        self.assertTrue(ok_docs, err_docs)

        for synthetic in (
            "Merge branch 'beta' into agent/agy-batch",
            'Revert "feat(cp): add button (T129)"',
            "fixup! feat(cp): add button (T129)",
            "squash! feat(cp): add button (T129)",
        ):
            ok_syn, err_syn = cc.validate_commit_message(synthetic, staged_files=[])
            self.assertTrue(ok_syn, f"{synthetic} should pass: {err_syn}")

    def test_ac2_anti_dodge_rejects_unticketed_chore_or_docs_staging_substantive_code(self) -> None:
        """Unticketed chore:/docs: commits staging code or SQL migrations must fail."""
        for msg, bad_files in (
            ("chore(cp): quick tweak", ["apps/cp/src/pages/index.astro"]),
            ("docs(db): update migration note", ["supabase/migrations/20261022_init.sql"]),
            ("style(scripts): format helper", ["scripts/conventional_commit.py"]),
        ):
            ok, err = cc.validate_commit_message(msg, staged_files=bad_files)
            self.assertFalse(ok, f"Unticketed exempt commit with {bad_files} must fail")
            self.assertIn("cannot stage substantive code/migration files", err)

        ok_with_t, err_with_t = cc.validate_commit_message(
            "chore(cp): quick tweak (T129)",
            staged_files=["apps/cp/src/pages/index.astro"],
        )
        self.assertTrue(ok_with_t, err_with_t)

    def test_ac3_ac4_sdlc_json_and_agent_surfaces_declare_policy(self) -> None:
        """Verify .w0m/sdlc.json and agent instruction surfaces declare T129 rules."""
        sdlc: dict[str, Any] = json.loads(
            (ESTATE_ROOT / ".w0m" / "sdlc.json").read_text(encoding="utf-8")
        )
        conv = sdlc.get("conventions", {})
        self.assertTrue(conv.get("reference_ticket_in_commit"))
        self.assertTrue(conv.get("ticket_before_code"))
        self.assertTrue(conv.get("anti_retroactive_ticket"))

        cc_policy = sdlc.get("change_classification", {})
        self.assertIn("non_trivial", cc_policy)
        self.assertIn("trivial", cc_policy)
        self.assertIn("anti_retroactive_rule", cc_policy)
        self.assertEqual(
            cc_policy.get("commit_msg_gate", {}).get("recipe"),
            "just commit-msg-check",
        )

        for rel_surface in (
            "AGENTS.md",
            ".agents/rules/sdlc.md",
            "wom7web/CLAUDE.md",
            "wom7web/AGENTS.md",
        ):
            text = (ESTATE_ROOT / rel_surface).read_text(encoding="utf-8")
            self.assertIn(
                "never backfill tickets retroactively",
                text,
                f"{rel_surface} missing anti-retroactive ticket rule (T129 AC4)",
            )

    def test_ac5_cli_execution_and_all_8_repos_unified(self) -> None:
        """Verify CLI invocation via scripts/conventional_commit.py and all 8 repos' hook configs."""
        with tempfile.TemporaryDirectory() as tmp:
            msg_file = Path(tmp) / "COMMIT_EDITMSG"

            msg_file.write_text("feat(cp): add button\n", encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                rc_fail = cc.main([str(msg_file), "--no-check-staged"])
            self.assertEqual(rc_fail, 1)

            msg_file.write_text("feat(cp): add button (T129)\n", encoding="utf-8")
            rc_pass = cc.main([str(msg_file), "--no-check-staged"])
            self.assertEqual(rc_pass, 0)

            msg_file.write_text("chore(state): refresh STATE.md\n", encoding="utf-8")
            rc_chore = cc.main([str(msg_file), "--staged-files", "STATE.md"])
            self.assertEqual(rc_chore, 0)

        husky_commit_msg = (WEB_ROOT / ".husky" / "commit-msg").read_text(encoding="utf-8")
        self.assertIn("just commit-msg-check", husky_commit_msg)
        self.assertNotIn("grep -qE", husky_commit_msg)

        pre_commit_configs = [
            ESTATE_ROOT / ".pre-commit-config.yaml",
            WEB_ROOT / ".pre-commit-config.yaml",
            ESTATE_ROOT / "wom7api" / ".pre-commit-config.yaml",
            ESTATE_ROOT / "wom7func" / ".pre-commit-config.yaml",
            ESTATE_ROOT / "wom7ext" / ".pre-commit-config.yaml",
            ESTATE_ROOT / "wom7sec" / ".pre-commit-config.yaml",
            ESTATE_ROOT / "wom7skills" / ".pre-commit-config.yaml",
            ESTATE_ROOT / "wom7mlx" / "wom7mlx" / ".pre-commit-config.yaml",
        ]
        for cfg_path in pre_commit_configs:
            self.assertTrue(cfg_path.is_file(), f"Missing {cfg_path}")
            content = cfg_path.read_text(encoding="utf-8")
            self.assertNotIn(
                "grep -qE",
                content,
                f"{cfg_path} still contains inline grep -qE commit-msg duplicate (T386 AC4)",
            )
            self.assertTrue(
                "conventional_commit.py" in content or "just commit-msg-check" in content,
                f"{cfg_path} must delegate commit-msg to conventional_commit.py or just commit-msg-check",
            )


class TestT386UnifiedHooksContract(unittest.TestCase):
    """T386 AC1–AC6: Single just runner contract across .pre-commit-config.yaml + stacks-policy.json."""

    def test_ac1_ac2_wom7web_pre_commit_hooks_all_route_through_just(self) -> None:
        """Every local hook in wom7web/.pre-commit-config.yaml invokes `just <recipe>`."""
        hooks = parse_local_hooks(WEB_ROOT / ".pre-commit-config.yaml")
        justfile_text = (ESTATE_ROOT / "justfile").read_text(encoding="utf-8") + "\n" + (ESTATE_ROOT / "just" / "estate.just").read_text(encoding="utf-8")
        recipes = set(JUSTFILE_RECIPE_RE.findall(justfile_text))
        checked = 0
        for h in hooks:
            if h["id"] in UNIVERSAL_HOOK_IDS:
                continue
            entry = h.get("entry", "")
            m = JUST_ENTRY_RE.match(entry)
            self.assertIsNotNone(
                m,
                f"wom7web hook `{h['id']}` has raw entry `{entry!r}` instead of `just <recipe>`",
            )
            assert m is not None
            recipe_name = m.group(1)
            self.assertIn(
                recipe_name,
                recipes,
                f"wom7web hook `{h['id']}` calls `just {recipe_name}` which is missing from wom7api/justfile",
            )
            checked += 1
        self.assertGreaterEqual(checked, 15)

    def test_ac5_ac6_hooks_check_and_closed_debt_d52_d67(self) -> None:
        """hooks_check.main() returns 0 and D52/D67 are in Closed-Debt Ledger."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = hc.main()
        self.assertEqual(rc, 0, f"hooks_check failed:\n{buf.getvalue()}")

        debt_text = (ESTATE_ROOT / "TECH-DEBT.md").read_text(encoding="utf-8")
        active_part, _, closed_part = debt_text.partition("## Closed-Debt Ledger")
        self.assertNotIn("| D52 |", active_part)
        self.assertNotIn("| D67 |", active_part)
        self.assertIn("| D52 |", closed_part)
        self.assertIn("| D67 |", closed_part)


if __name__ == "__main__":
    unittest.main(verbosity=2)
