#!/usr/bin/env python3
"""Regression tests for T427 — Cross-repo escaping symlink cutover & fail-closed W0M_ROOT resolver."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import w0m_root  # noqa: E402


def test_w0m_root_resolves_explicit_env_var() -> None:
    resolved = w0m_root.resolve_w0m_root(
        require_env=True,
        env={"W0M_ROOT": str(ROOT)},
    )
    assert resolved == ROOT.resolve()
    assert (resolved / ".w0m" / "sdlc.json").is_file()


def test_w0m_root_fails_closed_when_require_env_and_unset() -> None:
    with pytest.raises(RuntimeError, match="W0M_ROOT environment variable is unset"):
        w0m_root.resolve_w0m_root(require_env=True, env={})


def test_w0m_root_fails_closed_when_env_points_to_invalid_dir() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        with pytest.raises(RuntimeError, match="Invalid w0m estate root from W0M_ROOT"):
            w0m_root.resolve_w0m_root(require_env=True, env={"W0M_ROOT": tmpdir})


def test_wom7api_and_wom7func_have_zero_escaping_tracked_symlinks() -> None:
    for repo in ("wom7api", "wom7func", "wom7ext", "wom7sec", "wom7skills", "wom7mlx/wom7mlx"):
        repo_path = ROOT / repo
        escaping = w0m_root.find_escaping_tracked_symlinks(repo_path)
        assert escaping == [], f"{repo} still contains escaping tracked symlinks: {escaping}"


def test_justfiles_export_w0m_root_and_wom7func_justfile_is_not_symlink() -> None:
    func_justfile = ROOT / "wom7func" / "justfile"
    assert func_justfile.is_file()
    assert not func_justfile.is_symlink(), "wom7func/justfile must be a real file, not a symlink"

    for jf in (ROOT / "justfile", ROOT / "wom7api" / "justfile", func_justfile):
        content = jf.read_text(encoding="utf-8")
        assert "export W0M_ROOT :=" in content, f"{jf} must export W0M_ROOT"


def test_removed_escaping_symlinks_remain_absent() -> None:
    removed_api = [".agent", ".codex", ".gemini", ".kilocode"]
    for rel in removed_api:
        p = ROOT / "wom7api" / rel
        assert not p.exists() and not p.is_symlink(), f"wom7api/{rel} must remain removed"

    removed_web = [
        "project/doc-format-policy.json",
        "project/hygiene-policy.schema.json",
        "project/ide-policy.schema.json",
        "project/mcp-health-policy.json",
        "project/skills-policy.schema.json",
        "project/stacks-policy.schema.json",
        "project/templates/decision.md",
        "project/templates/ticket.md",
    ]
    for rel in removed_web:
        p = ROOT / "wom7web" / rel
        assert not p.exists() and not p.is_symlink(), f"wom7web/{rel} must remain removed"
