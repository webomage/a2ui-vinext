#!/usr/bin/env python3
"""Unit and RED-probe tests for AI-DLC & SDLC multi-layer knowledge provisioning, read, update, and guard."""

from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
import sys

if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))
if str(ROOT / "w0m-web" / "project" / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "w0m-web" / "project" / "scripts"))

import automation_health as ah  # noqa: E402
import context_tree as ct  # noqa: E402
import release as rel_mod  # noqa: E402
import session_complete as sc  # noqa: E402
import ticket_new as tn  # noqa: E402
import w0m_prs  # noqa: E402


class TestAidlcDataLayers(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="w0m-aidlc-layers-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_ac1_provision_worktree_fixtures_copies_codegraph_and_graphify(self) -> None:
        estate = self.tmp_dir / "estate"
        wt = self.tmp_dir / "worktree"
        for repo in ("w0m-web", "w0m-api", "w0m-skills"):
            cg_dir = estate / repo / ".codegraph"
            gf_dir = estate / repo / "graphify-out"
            cg_dir.mkdir(parents=True, exist_ok=True)
            gf_dir.mkdir(parents=True, exist_ok=True)
            (cg_dir / "graph.db").write_bytes(b"SQLite format 3\x00test")
            (gf_dir / "graph.json").write_text('{"built_at_commit": "abcdef1"}', encoding="utf-8")
            (gf_dir / "GRAPH_REPORT.md").write_text("# Report\n", encoding="utf-8")
            (wt / repo).mkdir(parents=True, exist_ok=True)

        rel_mod.provision_worktree_fixtures(wt, estate, link_node_modules=False)

        for repo in ("w0m-web", "w0m-api", "w0m-skills"):
            self.assertTrue((wt / repo / ".codegraph" / "graph.db").is_file())
            self.assertTrue((wt / repo / "graphify-out" / "graph.json").is_file())
            self.assertTrue((wt / repo / "graphify-out" / "GRAPH_REPORT.md").is_file())

    def test_ac2_sdlc_json_and_justfile_ask_cover_all_6_codegraph_repos_and_kb_vector(self) -> None:
        sdlc = json.loads((ROOT / ".w0m" / "sdlc.json").read_text(encoding="utf-8"))
        indexed = sdlc.get("codegraph", {}).get("indexed", [])
        self.assertEqual(
            indexed,
            ["w0m-web", "w0m-api", "w0m-cf", "w0m-skills", "w0m-ext", "w0m-sec"],
        )
        jf_text = (ROOT / "justfile").read_text(encoding="utf-8")
        self.assertIn("for r in root w0m-web w0m-api w0m-cf w0m-skills w0m-ext w0m-sec;", jf_text)
        self.assertIn("python3 scripts/w0m_kb_vector.py search", jf_text)

    def test_ac3_context_tree_supports_draft_and_populates_multi_layer_files(self) -> None:
        ws = self.tmp_dir / "ws"
        (ws / ".tasks").mkdir(parents=True, exist_ok=True)
        (ws / ".w0m").mkdir(parents=True, exist_ok=True)
        (ws / "docs").mkdir(parents=True, exist_ok=True)
        (ws / "docs" / "DECISIONS.md").write_text("| AgDR-0032 | Agent worktrees |\n", encoding="utf-8")

        tid, tpath = tn.allocate_ticket(
            "Test Multi-Layer Context",
            repo_dir=ws,
            draft_slug="test-layers",
            why="Follows AgDR-0032 and edits `scripts/session_complete.py`.",
        )
        self.assertEqual(tid, "DRAFT-test-layers")
        self.assertTrue(tpath.is_file())

        bundle = ct.build_context_tree("DRAFT-test-layers", workspace_root=ws)
        self.assertEqual(bundle.ticket_id, "DRAFT-test-layers")
        rel_paths = [f.rel_path for f in bundle.files]
        for expected in (
            "INDEX.md",
            "task.md",
            "diff.patch",
            "decisions/related.md",
            "lessons/related.md",
            "kb/related.md",
            "graph/symbols.md",
            "suites/summary.json",
        ):
            self.assertIn(expected, rel_paths)
        symbols_md = (Path(bundle.root_dir) / "graph" / "symbols.md").read_text(encoding="utf-8")
        self.assertIn("scripts/session_complete.py", symbols_md)

    def test_ac4_and_ac5_refresh_canonical_graph_union_passes_zero_stale_limit(self) -> None:
        canon = self.tmp_dir / "canon"
        (canon / "scripts").mkdir(parents=True, exist_ok=True)
        (canon / "scripts" / "graph_global.py").write_text("#!/usr/bin/env python3\n", encoding="utf-8")
        (canon / "w0m-web" / ".codegraph").mkdir(parents=True, exist_ok=True)

        calls: list[list[str]] = []

        def fake_run(cmd: list[str], cwd: Path, check: bool = False) -> mock.MagicMock:
            calls.append([str(c) for c in cmd])
            m = mock.MagicMock()
            m.returncode = 0
            m.stdout = "ok"
            m.stderr = ""
            return m

        with (
            mock.patch.object(sc.shutil, "which", return_value="/usr/bin/true"),
            mock.patch.object(sc, "_run", side_effect=fake_run),
        ):
            res = sc.refresh_canonical_graph_union(canon)

        self.assertTrue(res["refreshed"])
        self.assertIn("w0m-web", res["codegraphSynced"])
        graph_calls = [c for c in calls if any("graph_global.py" in part for part in c)]
        self.assertEqual(len(graph_calls), 1)
        self.assertIn("--stale-limit", graph_calls[0])
        self.assertIn("0", graph_calls[0])

    def test_ac6_automation_health_kb_vector_ceiling_red_and_green(self) -> None:
        estate = self.tmp_dir / "estate"
        tasks_dir = estate / ".tasks"
        tasks_dir.mkdir(parents=True, exist_ok=True)
        for i in range(1, 6):
            (tasks_dir / f"T{i}.md").write_text(f"---\nid: T{i}\n---\n", encoding="utf-8")

        db_path = self.tmp_dir / "corpus.sqlite"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE documents (doc_id TEXT PRIMARY KEY, category TEXT)")
        conn.execute("INSERT INTO documents VALUES ('ticket:T1', 'ticket')")
        conn.execute("INSERT INTO documents VALUES ('ticket:T2', 'ticket')")
        conn.commit()
        conn.close()

        # 2 indexed out of 5 total => lag 3 > max_lag 1 (RED)
        ok_red, detail_red = ah.check_kb_vector_ceiling(estate, max_lag=1, db_path=db_path)
        self.assertFalse(ok_red)
        self.assertIn("exceeds ceiling", detail_red)

        # lag 3 <= max_lag 5 (GREEN)
        ok_green, detail_green = ah.check_kb_vector_ceiling(estate, max_lag=5, db_path=db_path)
        self.assertTrue(ok_green)
        self.assertIn("within ceiling", detail_green)

    def test_casey_just_registered_in_upstream_contribution_rules(self) -> None:
        rule = w0m_prs.UPSTREAM_CONTRIBUTION_RULES.get("casey/just")
        self.assertIsNotNone(rule)
        assert rule is not None
        self.assertEqual(rule["automation_mode"], "banned")
        self.assertIn("3227", rule["policy_note"])


if __name__ == "__main__":
    unittest.main()
