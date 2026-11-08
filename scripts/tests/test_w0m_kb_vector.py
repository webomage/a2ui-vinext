#!/usr/bin/env python3
"""Unit and Red-Probe Tests for `scripts/w0m_kb_vector.py` (T669)."""

from __future__ import annotations

import io
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import w0m_kb_vector as kb  # noqa: E402


class TestW0mKbVector(unittest.TestCase):
    def test_red_probe_secret_scrubber_catches_credentials(self) -> None:
        fake_ant = "sk-" + "ant-" + ("A" * 28)
        fake_gh = "ghp" + "_" + ("B" * 32)
        fake_jwt = ".".join(["eyJ" + ("a" * 22), "eyJ" + ("b" * 22), "c" * 20])
        raw = f"Normal text with Anthropic key {fake_ant} and GitHub PAT {fake_gh} and JWT {fake_jwt}"
        scrubbed, kinds = kb.scrub_secrets(raw)
        self.assertIn("openai_or_anthropic_key", kinds)
        self.assertIn("github_pat", kinds)
        self.assertIn("jwt_token", kinds)
        self.assertNotIn("sk-ant-", scrubbed)
        self.assertNotIn("ghp_", scrubbed)
        self.assertIn("[REDACTED:openai_or_anthropic_key]", scrubbed)

    def test_red_probe_boundary_classifier_blocks_client_and_personal(self) -> None:
        self.assertEqual(
            kb.classify_source_boundary("wom_local/_in/Lahore_project.md", "# Proposal"),
            "client_confidential",
        )
        self.assertEqual(
            kb.classify_source_boundary("wom_local/_in/notes.md", "Client Evercred vault sync"),
            "client_confidential",
        )
        self.assertEqual(
            kb.classify_source_boundary("wom_local/_arch/cv_2026-08/Aleksei_CV_2026-08_Private.md", "# CV"),
            "personal_private",
        )
        self.assertEqual(
            kb.classify_source_boundary("home_dirs/orca/workspaces/servicios777.mx/roadmap.md", "# Roadmap"),
            "self_product",
        )
        self.assertEqual(
            kb.classify_source_boundary(
                "wom_local/_in/2026-09-02-proposal-hermes-learning-loop-for-w0m-zeroclaw.md",
                "# Proposal: Hermes-Style Auto-Learning for w0m",
            ),
            "w0m_canonical",
        )

    def test_red_probe_rescue_mac_backup_excludes_client_and_personal_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            tar_path = tmp_path / "mock_mac_backup.tar.gz"
            out_dir = tmp_path / "mac-recovery"
            cat_path = tmp_path / "catalog.json"
            ledger_path = tmp_path / "ledger.json"
            ledger_path.write_text('{"items": [{"file": "already-adopted.md"}]}', encoding="utf-8")

            members = {
                "wom_local/_in/2026-09-02-w0m-arch-proposal.md": (
                    "# Proposal: w0m Hybrid Vector Architecture\n\n## Summary\nPure @wom research with token ghp_1234567890abcdefghijklmnopqrstuv."
                ),
                "wom_local/_in/already-adopted.md": "# Already in ledger\nShould not be re-rescued.",
                "wom_local/_in/Lahore_proposal.md": "# Confidential Client Proposal\nMust never enter git.",
                "wom_local/_arch/cv_2026-08/Aleksei_CV_2026-08_Private.md": "# Personal CV\nMust never enter git.",
            }
            with tarfile.open(tar_path, "w:gz") as tf:
                for name, body in members.items():
                    data = body.encode("utf-8")
                    info = tarfile.TarInfo(name=name)
                    info.size = len(data)
                    tf.addfile(info, io.BytesIO(data))

            summary = kb.rescue_mac_backup_research(
                tar_path=tar_path,
                out_dir=out_dir,
                catalog_path=cat_path,
                ledger_path=ledger_path,
            )
            self.assertEqual(summary["rescued_w0m_count"], 1)
            self.assertEqual(summary["excluded_client_or_personal_count"], 2)
            self.assertEqual(summary["redacted_secret_hits"], 1)
            rescued_file = out_dir / "2026-09-02-w0m-arch-proposal.md"
            self.assertTrue(rescued_file.is_file())
            self.assertFalse((out_dir / "Lahore_proposal.md").exists())
            self.assertFalse((out_dir / "Aleksei_CV_2026-08_Private.md").exists())
            rescued_text = rescued_file.read_text(encoding="utf-8")
            self.assertIn("[REDACTED:github_pat]", rescued_text)
            self.assertTrue((out_dir / "INDEX.md").is_file())

    def test_hybrid_index_search_and_clustering_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".agents" / "reports").mkdir(parents=True)
            (root / "docs" / "decisions").mkdir(parents=True)
            (root / ".tasks").mkdir(parents=True)

            (root / ".agents" / "reports" / "2026-11-08-t669-orca-webgl.md").write_text(
                "# Orca WebGL Atlas & Terminal Redraw Audit\n\n"
                "## WebGL Texture Atlas\n"
                "Upstream stablyai/orca #39715 caps WebGL texture atlas pages and fixes link layer bounds.\n\n"
                "## Mobile Offline Send Queue\n"
                "Mobile native chat persists offline queued messages in durable draft rows.\n",
                encoding="utf-8",
            )
            (root / "docs" / "decisions" / "AgDR-0055-free-tier.md").write_text(
                "# AgDR-0055: Free-Tier-First Resource Allocation\n\n"
                "## Decision\n"
                "Allocate edge compute and R2 storage on Cloudflare Free Tier first and keep Supabase under 500 MB.\n",
                encoding="utf-8",
            )
            (root / ".tasks" / "T669.md").write_text(
                "# T669 — Hybrid BM25 and LSA Vector Knowledge Index\n\n"
                "## Summary\n"
                "Build SQLite FTS5 BM25 lexical search combined with 128-dim SVD dense vectors and Reciprocal Rank Fusion.\n",
                encoding="utf-8",
            )

            db_path = root / "corpus.sqlite"
            res = kb.build_hybrid_index(root=root, db_path=db_path, embed_dim=16, n_clusters=2)
            self.assertEqual(res["doc_count"], 3)
            self.assertGreaterEqual(res["chunk_count"], 4)

            hits_hybrid = kb.search_hybrid_index("WebGL texture atlas stablyai orca", db_path=db_path, top_k=3, mode="hybrid")
            self.assertGreaterEqual(len(hits_hybrid), 1)
            self.assertIn("2026-11-08-t669-orca-webgl.md", hits_hybrid[0]["rel_path"])

            hits_vec = kb.search_hybrid_index("Cloudflare R2 storage 500 MB database cap", db_path=db_path, top_k=3, mode="vector")
            self.assertGreaterEqual(len(hits_vec), 1)
            self.assertIn("AgDR-0055-free-tier.md", hits_vec[0]["rel_path"])

            clusters = kb.load_clusters(db_path=db_path)
            self.assertEqual(len(clusters), 2)
            stats = kb.load_stats(db_path=db_path, catalog_path=root / "nonexistent.json")
            self.assertTrue(stats["db_exists"])
            self.assertEqual(stats["doc_count"], 3)


if __name__ == "__main__":
    unittest.main()
