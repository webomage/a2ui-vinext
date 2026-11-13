#!/usr/bin/env python3
"""Unit and Red-Probe Tests for `scripts/w0m_kb_vector.py` (T669 / T736)."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import sqlite3
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

SCRIPT_DIR = Path(__file__).resolve().parents[1]
ESTATE_ROOT = SCRIPT_DIR.parent
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
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            policy_dir = root / "project" / "policies"
            policy_dir.mkdir(parents=True)
            (policy_dir / "clients-policy.json").write_text(
                json.dumps(
                    {
                        "projects": [
                            {"id": "w0m", "role": "w0m", "root": "."},
                            {"id": "acmeclient", "role": "self-managed", "root": "../../!proj/acmeclient"},
                            {"id": "myproduct", "role": "managed", "root": "../../_self/myproduct"},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            synth_sha = hashlib.sha256(b"synthlegacyclient").hexdigest()
            with mock.patch.object(kb, "LEGACY_CLIENT_TOKEN_SHA256", frozenset({synth_sha})):
                self.assertEqual(
                    kb.classify_source_boundary("wom_local/_in/acmeclient_project.md", "# Proposal", root=root),
                    "client_confidential",
                )
                self.assertEqual(
                    kb.classify_source_boundary("archives/synthlegacyclient_notes.md", "# Proposal", root=root),
                    "client_confidential",
                )
                # Body mentions only filter when is_untrusted_archive=True or kb_policy frontmatter is set
                self.assertEqual(
                    kb.classify_source_boundary(
                        "wom_local/_in/notes.md",
                        "Client acmeclient vault sync",
                        is_untrusted_archive=True,
                        root=root,
                    ),
                    "client_confidential",
                )
                self.assertEqual(
                    kb.classify_source_boundary(
                        "w0m-web/docs/architecture/IDENTITY-ISOLATION.md",
                        "Architecture comparison mentioning acmeclient and synthlegacyclient isolation.",
                        is_untrusted_archive=False,
                        root=root,
                    ),
                    "w0m_canonical",
                )
                self.assertEqual(
                    kb.classify_source_boundary(
                        "w0m-web/docs/private-note.md",
                        "---\nkb_policy: client\n---\n# Scoped Note",
                        root=root,
                    ),
                    "client_confidential",
                )
                # Substring safety on canonical paths (`declaration`, `endpoints`, `datos`, `marshmallow`)
                for safe_path in (
                    "w0m-web/openspec/specs/project-runtime-declaration/spec.md",
                    "w0m-web/docs/endpoints/marshmallow-datos.md",
                    "w0m_local/_in/2026-09-02-proposal-hermes-learning-loop-for-w0m-zeroclaw.md",
                ):
                    self.assertEqual(
                        kb.classify_source_boundary(safe_path, "# Canonical Doc", root=root),
                        "w0m_canonical",
                    )
                self.assertEqual(
                    kb.classify_source_boundary("personal_exports/private.md", "# Notes", root=root),
                    "personal_private",
                )
                self.assertEqual(
                    kb.classify_source_boundary("home_dirs/orca/workspaces/myproduct/roadmap.md", "# Roadmap", root=root),
                    "self_product",
                )

    def test_red_probe_rescue_mac_backup_excludes_client_and_personal_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            tar_path = tmp_path / "mock_mac_backup.tar.gz"
            out_dir = tmp_path / "mac-recovery"
            cat_path = tmp_path / "catalog.json"
            ledger_path = tmp_path / "ledger.json"
            ledger_path.write_text('{"items": [{"file": "already-adopted.md"}]}', encoding="utf-8")

            synth_sha = hashlib.sha256(b"synthbackupclient").hexdigest()
            members = {
                "wom_local/_in/2026-09-02-w0m-arch-proposal.md": (
                    "# Proposal: w0m Hybrid Vector Architecture\n\n## Summary\nPure @wom research with token ghp_1234567890abcdefghijklmnopqrstuv."
                ),
                "wom_local/_in/already-adopted.md": "# Already in ledger\nShould not be re-rescued.",
                "wom_local/_proj/client_proposal.md": "# Confidential Client Proposal\nMust never enter git.",
                "wom_local/_in/untrusted_body_match.md": "Notes for synthbackupclient onboarding.",
                "wom_local/_arch/personal/private.md": "# Personal Export\nMust never enter git.",
            }
            with tarfile.open(tar_path, "w:gz") as tf:
                for name, body in members.items():
                    data = body.encode("utf-8")
                    info = tarfile.TarInfo(name=name)
                    info.size = len(data)
                    tf.addfile(info, io.BytesIO(data))

            with mock.patch.object(kb, "LEGACY_CLIENT_TOKEN_SHA256", frozenset({synth_sha})):
                summary = kb.rescue_mac_backup_research(
                    tar_path=tar_path,
                    out_dir=out_dir,
                    catalog_path=cat_path,
                    ledger_path=ledger_path,
                )
            self.assertEqual(summary["rescued_w0m_count"], 1)
            self.assertEqual(summary["excluded_client_or_personal_count"], 3)
            self.assertEqual(summary["redacted_secret_hits"], 1)
            rescued_file = out_dir / "2026-09-02-w0m-arch-proposal.md"
            self.assertTrue(rescued_file.is_file())
            self.assertFalse((out_dir / "client_proposal.md").exists())
            self.assertFalse((out_dir / "untrusted_body_match.md").exists())
            self.assertFalse((out_dir / "private.md").exists())
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

    def test_collect_estate_documents_indexes_web_docs_and_entrypoints_while_skipping_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir(parents=True)
            (root / "w0m-web" / "docs" / "backend").mkdir(parents=True)
            (root / "w0m-web" / "docs" / "archive").mkdir(parents=True)

            (root / "AGENTS.md").write_text("# Root Agents Entrypoint\nCanonical invariants.\n", encoding="utf-8")
            (root / "docs" / "TECH-LANDSCAPE.md").write_text(
                "# Webomage Tech Landscape\nEdge-first architecture.\n", encoding="utf-8"
            )
            (root / "w0m-web" / "docs" / "CODEMAP.md").write_text(
                "# Workspace Codemap\nApps and shared packages.\n", encoding="utf-8"
            )
            (root / "w0m-web" / "docs" / "backend" / "KB-INDEX.md").write_text(
                "# Backend KB Index\nSupabase migrations and Edge Functions.\n", encoding="utf-8"
            )
            (root / "w0m-web" / "docs" / "backend" / "archive").mkdir(parents=True)
            (root / "w0m-web" / "docs" / "archive" / "retired-draft.md").write_text(
                "# Archived Draft\nMust be skipped from live KB.\n", encoding="utf-8"
            )
            (root / "w0m-web" / "docs" / "backend" / "archive" / "nested-retired.md").write_text(
                "# Nested Archived Draft\nMust also be skipped.\n", encoding="utf-8"
            )

            collected = kb.collect_estate_documents(root=root)
            by_rel = {d["rel_path"]: d["category"] for d in collected}
            self.assertEqual(by_rel.get("AGENTS.md"), "estate_entry")
            self.assertEqual(by_rel.get("docs/TECH-LANDSCAPE.md"), "estate_doc")
            self.assertEqual(by_rel.get("w0m-web/docs/CODEMAP.md"), "web_doc")
            self.assertEqual(by_rel.get("w0m-web/docs/backend/KB-INDEX.md"), "web_doc")
            self.assertNotIn("w0m-web/docs/archive/retired-draft.md", by_rel)
            self.assertNotIn("w0m-web/docs/backend/archive/nested-retired.md", by_rel)

    def test_collect_estate_documents_deduplicates_mirrored_reports_by_sha256(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".agents" / "reports").mkdir(parents=True)
            (root / "w0m-web" / "docs" / "reports").mkdir(parents=True)

            body = "# T734 Tech Overview\nIdentical mirrored report content.\n"
            (root / ".agents" / "reports" / "t734-overview.md").write_text(body, encoding="utf-8")
            (root / "w0m-web" / "docs" / "reports" / "t734-overview.md").write_text(body, encoding="utf-8")

            collected = kb.collect_estate_documents(root=root)
            self.assertEqual(len(collected), 1)
            self.assertEqual(collected[0]["rel_path"], ".agents/reports/t734-overview.md")
            self.assertEqual(collected[0]["category"], "agent_report")

    def test_openspec_archive_curation_weight_cap_and_no_archive_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            canonical_dir = root / "w0m-web" / "openspec" / "specs" / "cap-alpha"
            superseded_dir = root / "w0m-web" / "openspec" / "changes" / "archive" / "2026-09-01-alpha" / "specs" / "cap-alpha"
            unique_dir = root / "w0m-web" / "openspec" / "changes" / "archive" / "2026-09-02-beta" / "specs" / "cap-unique"
            docs_dir = root / "docs"
            for d in (canonical_dir, superseded_dir, unique_dir, docs_dir):
                d.mkdir(parents=True)

            shared_body = (
                "# Capability Alpha Routing\n\n"
                "Deterministic multi-region gateway failover with Cloudflare KV lease coordination.\n"
            )
            (canonical_dir / "spec.md").write_text(shared_body, encoding="utf-8")
            (superseded_dir / "spec.md").write_text(shared_body + "\nSuperseded archived delta.\n", encoding="utf-8")
            (superseded_dir.parents[1] / "tasks.md").write_text("# Tasks\n- [x] Old checklist noise.\n", encoding="utf-8")
            (unique_dir / "spec.md").write_text(
                "# Unique Unpromoted Capability\n\nZero-egress R2 batching pipeline with gateway failover.\n",
                encoding="utf-8",
            )
            (unique_dir.parents[1] / "proposal.md").write_text(
                "# Proposal Beta\n\nCloudflare KV lease coordination historical context.\n",
                encoding="utf-8",
            )
            # Large multi-section doc + second doc to verify max_chunks_per_doc=2 diversity
            (docs_dir / "MULTI.md").write_text(
                "# Multi Section Gateway Guide\n\n"
                + "\n\n".join(
                    f"## Section {i}\nCloudflare gateway failover lease coordination details part {i}.\n"
                    + ("extra padding words " * 90)
                    for i in range(1, 5)
                ),
                encoding="utf-8",
            )

            db_path = root / "corpus.sqlite"
            res = kb.build_hybrid_index(root=root, db_path=db_path, embed_dim=8, n_clusters=2)
            # Retained: specs/cap-alpha/spec.md, unique proposal.md, unique cap-unique/spec.md, MULTI.md = 4
            self.assertEqual(res["doc_count"], 4)

            conn = sqlite3.connect(str(db_path))
            try:
                paths = {r[0]: r[1] for r in conn.execute("SELECT DISTINCT rel_path, category FROM chunks").fetchall()}
            finally:
                conn.close()
            self.assertEqual(paths.get("w0m-web/openspec/specs/cap-alpha/spec.md"), "openspec")
            self.assertEqual(paths.get("w0m-web/openspec/changes/archive/2026-09-02-beta/specs/cap-unique/spec.md"), "openspec_archive")
            self.assertNotIn("w0m-web/openspec/changes/archive/2026-09-01-alpha/tasks.md", paths)
            self.assertNotIn("w0m-web/openspec/changes/archive/2026-09-01-alpha/specs/cap-alpha/spec.md", paths)

            hits_default = kb.search_hybrid_index("Zero-egress R2 batching cap-unique", db_path=db_path, top_k=5)
            self.assertTrue(any(h["category"] == "openspec_archive" for h in hits_default))

            hits_no_archive = kb.search_hybrid_index(
                "Zero-egress R2 batching cap-unique", db_path=db_path, top_k=5, include_archive=False
            )
            self.assertFalse(any(h["category"] == "openspec_archive" for h in hits_no_archive))

            # Diversity: no single rel_path occupies > 2 slots when top_k >= 3
            hits_diverse = kb.search_hybrid_index("Cloudflare gateway failover lease coordination", db_path=db_path, top_k=5)
            multi_count = sum(1 for h in hits_diverse if h["rel_path"] == "docs/MULTI.md")
            self.assertLessEqual(multi_count, 2)

    def test_collect_estate_documents_symlink_escape_raw_bytes_and_blocked_sha256(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_outside, tempfile.TemporaryDirectory() as tmp_root:
            outside_file = Path(tmp_outside) / "escape.md"
            outside_file.write_text("# Outside\nSecret outside workspace.\n", encoding="utf-8")

            root = Path(tmp_root)
            (root / ".agents" / "reports").mkdir(parents=True)
            (root / "w0m-web" / "docs" / "reports" / "mac-recovery").mkdir(parents=True)
            (root / "docs").mkdir(parents=True)

            # Symlink escape attempt must be rejected
            (root / "docs" / "escaped-link.md").symlink_to(outside_file)

            # Identical copy of a kb_policy:client file must be blocked via blocked_sha256
            client_payload = "---\nkb_policy: client\n---\n# Scoped Content\nConfidential body.\n"
            (root / "docs" / "a-client.md").write_text(client_payload, encoding="utf-8")
            (root / "docs" / "z-copy.md").write_text(client_payload, encoding="utf-8")

            # Raw bytes preserve CRLF vs LF distinction
            (root / "docs" / "lf.md").write_bytes(b"# Line Ending LF\nLine one\n")
            (root / "docs" / "crlf.md").write_bytes(b"# Line Ending CRLF\r\nLine one\r\n")

            # Canonical `.agents/reports` takes precedence over mac-recovery and web_report mirrors
            mirrored = "# Priority Report\nIdentical mirror body.\n"
            (root / ".agents" / "reports" / "priority.md").write_text(mirrored, encoding="utf-8")
            (root / "w0m-web" / "docs" / "reports" / "mac-recovery" / "priority.md").write_text(mirrored, encoding="utf-8")
            (root / "w0m-web" / "docs" / "reports" / "priority.md").write_text(mirrored, encoding="utf-8")

            docs = kb.collect_estate_documents(root=root)
            by_rel = {d["rel_path"]: d for d in docs}
            self.assertNotIn("docs/escaped-link.md", by_rel)
            self.assertNotIn("docs/a-client.md", by_rel)
            self.assertNotIn("docs/z-copy.md", by_rel)
            self.assertIn("docs/lf.md", by_rel)
            self.assertIn("docs/crlf.md", by_rel)
            self.assertNotEqual(by_rel["docs/lf.md"]["sha256"], by_rel["docs/crlf.md"]["sha256"])
            self.assertIn(".agents/reports/priority.md", by_rel)
            self.assertEqual(by_rel[".agents/reports/priority.md"]["category"], "agent_report")
            self.assertNotIn("w0m-web/docs/reports/mac-recovery/priority.md", by_rel)
            self.assertNotIn("w0m-web/docs/reports/priority.md", by_rel)


if __name__ == "__main__":
    unittest.main()
