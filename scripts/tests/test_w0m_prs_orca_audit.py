#!/usr/bin/env python3
"""Regression Tests for T669 Upstream PR State Reconciliation in `scripts/w0m_prs.py`."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import w0m_prs  # noqa: E402


class TestW0mPrsOrcaAudit(unittest.TestCase):
    def test_merged_headroom_4597_and_closed_orca_38861_moved_to_internal_or_superseded(self) -> None:
        self.assertNotIn("feat/omlx-proxy-routing", w0m_prs.ACTIVE_OPEN_PR_HEAD_BRANCHES)
        self.assertIn("feat/omlx-proxy-routing", w0m_prs.INTERNAL_OR_SUPERSEDED_BRANCHES)

        self.assertNotIn("perf/terminal-chat-redraw-and-tab-caching", w0m_prs.ACTIVE_OPEN_PR_HEAD_BRANCHES)
        self.assertIn("perf/terminal-chat-redraw-and-tab-caching", w0m_prs.INTERNAL_OR_SUPERSEDED_BRANCHES)

    def test_active_open_pr_head_branches_count_matches_open_portfolio(self) -> None:
        # 35 unique active head branch names across the 36 open PRs (bodhi7packages#10 & bodhi8packages#8 share 1 branch name)
        self.assertEqual(len(w0m_prs.ACTIVE_OPEN_PR_HEAD_BRANCHES), 35)
        self.assertIn("fix/webgl-atlas-version-desync-recovery", w0m_prs.ACTIVE_OPEN_PR_HEAD_BRANCHES)
        self.assertIn("feat/mlx-lm-gemma4-arch", w0m_prs.ACTIVE_OPEN_PR_HEAD_BRANCHES)


if __name__ == "__main__":
    unittest.main()
