#!/usr/bin/env python3
"""Unit tests for canonical Multi-Agent CLI & Orca Provider Abstraction (`T609` AC5)."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import agent_provider as ap  # noqa: E402


class TestAgentProvider(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_auto_selects_antigravity_when_claude_missing(self) -> None:
        fake_bins = {"agy": "/home/user/.local/bin/agy"}
        resolved = ap.resolve_agent_provider(
            "auto",
            env={},
            which_fn=lambda name: fake_bins.get(name),
            extra_dirs=(),
        )
        self.assertEqual(resolved, "antigravity")

    def test_auto_honors_active_agent_env_marker_when_installed(self) -> None:
        fake_bins = {
            "agy": "/home/user/.local/bin/agy",
            "codex": "/usr/local/bin/codex",
        }
        resolved = ap.resolve_agent_provider(
            "auto",
            env={"CODEX_CLI": "1"},
            which_fn=lambda name: fake_bins.get(name),
            extra_dirs=(),
        )
        self.assertEqual(resolved, "codex")

    def test_explicit_missing_provider_fails_closed(self) -> None:
        fake_bins = {"agy": "/home/user/.local/bin/agy"}
        with self.assertRaises(RuntimeError) as ctx:
            ap.resolve_agent_provider(
                "claude",
                env={},
                which_fn=lambda name: fake_bins.get(name),
                extra_dirs=(),
            )
        self.assertIn("claude", str(ctx.exception))
        self.assertIn("antigravity", str(ctx.exception))

    def test_alias_normalization_and_resume_commands(self) -> None:
        self.assertEqual(ap.normalize_provider_id("agy"), "antigravity")
        self.assertEqual(ap.normalize_provider_id("claude-code"), "claude")
        self.assertEqual(
            ap.build_agent_resume_command("conv-123", "antigravity"),
            "agy --conversation=conv-123 --dangerously-skip-permissions",
        )
        self.assertEqual(
            ap.build_agent_resume_command("sess-456", "claude"),
            "claude --resume sess-456 --dangerously-skip-permissions",
        )
        self.assertEqual(
            ap.build_agent_resume_command("sess-789", "codex"),
            "codex resume sess-789",
        )
        self.assertEqual(
            ap.build_agent_resume_command("sess-000", "opencode"),
            "opencode --session sess-000",
        )

    def test_resolve_orca_bin_supports_linux_shim(self) -> None:
        shim_dir = self.tmp_dir / ".config" / "orca" / "linux-orca-cli-shim"
        shim_dir.mkdir(parents=True)
        shim = shim_dir / "orca"
        shim.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        os.chmod(shim, 0o755)

        resolved = ap.resolve_orca_bin(which_fn=lambda _: None, home_dir=self.tmp_dir)
        self.assertEqual(resolved, str(shim))

    def test_resolve_orca_bin_honors_orca_cli_command_env(self) -> None:
        custom = self.tmp_dir / "orca-custom"
        custom.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        os.chmod(custom, 0o755)

        resolved = ap.resolve_orca_bin(
            env={"ORCA_CLI_COMMAND": str(custom)},
            which_fn=lambda name: "/usr/bin/orca" if name == "orca" else None,
            home_dir=self.tmp_dir,
        )
        self.assertEqual(resolved, str(custom))

    def test_resolve_orca_bin_skips_gnome_screen_reader(self) -> None:
        shim_dir = self.tmp_dir / ".config" / "orca" / "linux-orca-cli-shim"
        shim_dir.mkdir(parents=True)
        shim = shim_dir / "orca"
        shim.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        os.chmod(shim, 0o755)

        # Even if /usr/bin/orca (GNOME screen reader) is on PATH, prefer the Orca IDE shim
        resolved_shim = ap.resolve_orca_bin(
            env={},
            which_fn=lambda name: "/usr/bin/orca" if name == "orca" else None,
            home_dir=self.tmp_dir,
        )
        self.assertEqual(resolved_shim, str(shim))

        # Without shim, prefer orca-ide over /usr/bin/orca
        empty_home = self.tmp_dir / "empty-home"
        empty_home.mkdir()
        resolved_ide = ap.resolve_orca_bin(
            env={},
            which_fn=lambda name: (
                "/usr/local/bin/orca-ide"
                if name == "orca-ide"
                else ("/usr/bin/orca" if name == "orca" else None)
            ),
            home_dir=empty_home,
        )
        self.assertEqual(resolved_ide, "/usr/local/bin/orca-ide")

        # Never return /usr/bin/orca or /bin/orca even if nothing else is found
        resolved_fallback = ap.resolve_orca_bin(
            env={},
            which_fn=lambda name: "/usr/bin/orca" if name == "orca" else None,
            home_dir=empty_home,
        )
        self.assertNotIn(resolved_fallback, ("/usr/bin/orca", "/bin/orca"))


if __name__ == "__main__":
    unittest.main()
