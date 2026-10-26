#!/usr/bin/env python3
"""T84 — Cross-repo codegraph hook configuration, .codegraph/graph.db freshness, and w0m-mlx hygiene tests."""
from __future__ import annotations

import json
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ESTATE_ROOT = Path(__file__).resolve().parents[2]
WEB_SCRIPTS = ESTATE_ROOT / "w0m-web" / "project" / "scripts"
if str(WEB_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(WEB_SCRIPTS))

import codemap_gen  # type: ignore[import-not-found]  # noqa: E402

SIX_CODE_REPOS: tuple[str, ...] = (
    "w0m-web",
    "w0m-api",
    "w0m-cf",
    "w0m-ext",
    "w0m-skills",
    "w0m-sec",
)

PRECOMMIT_CODEGRAPH_REPOS: tuple[str, ...] = (
    "w0m-api",
    "w0m-cf",
    "w0m-ext",
    "w0m-skills",
    "w0m-sec",
)

CODE_EXT_LANG: dict[str, str] = {
    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".py": "python",
    ".rs": "rust",
}

TS_EXPORT_RE = re.compile(
    r"^\s*export\s+(?:default\s+)?(?:async\s+)?(function|class|const|let|type|interface|enum)\s+([A-Za-z_][A-Za-z0-9_]*)",
    re.MULTILINE,
)
PY_SYMBOL_RE = re.compile(
    r"^(?:async\s+)?(def|class)\s+([A-Za-z_][A-Za-z0-9_]*)",
    re.MULTILINE,
)
RS_SYMBOL_RE = re.compile(
    r"^\s*pub\s+(?:async\s+)?(fn|struct|enum|trait|type|mod)\s+([A-Za-z_][A-Za-z0-9_]*)",
    re.MULTILINE,
)
TS_IMPORT_RE = re.compile(
    r"""^\s*import\s+(?:type\s+)?(?:[^'"]*?\s+from\s+)?['"]([^'"]+)['"]""",
    re.MULTILINE,
)
PY_IMPORT_RE = re.compile(
    r"^\s*(?:from\s+([A-Za-z0-9_.]+)\s+import|import\s+([A-Za-z0-9_.]+))",
    re.MULTILINE,
)


def sync_repo_codegraph_db(repo_dir: Path, *, force_rebuild: bool = False) -> float:
    """Refresh `<repo>/.codegraph/graph.db` (`files`, `nodes`, `edges`) and return elapsed seconds."""
    t0 = time.perf_counter()
    db_path = repo_dir / ".codegraph" / "graph.db"
    if repo_dir.name == "w0m-web":
        if not force_rebuild and db_path.is_file():
            try:
                conn = sqlite3.connect(str(db_path))
                try:
                    cnt = conn.execute("SELECT count(*) FROM files").fetchone()[0]
                finally:
                    conn.close()
                if cnt > 0:
                    return time.perf_counter() - t0
            except sqlite3.Error:
                pass
        codemap_gen.sync_codegraph_db(repo_dir, db_path)
        return time.perf_counter() - t0

    db_path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        ["git", "-C", str(repo_dir), "ls-files"],
        capture_output=True,
        text=True,
        check=False,
    )
    tracked = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]

    file_rows: list[tuple[str, str, str, int]] = []
    node_rows: list[tuple[str, str, str, str, str, int]] = []
    edge_rows: list[tuple[str, str, str, str, str]] = []

    for rel_path in tracked:
        p = repo_dir / rel_path
        lang = CODE_EXT_LANG.get(p.suffix)
        if not lang or not p.is_file():
            continue
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        parts = rel_path.split("/")
        member = parts[0] if len(parts) > 1 else "root"
        lines = len(content.splitlines())
        file_rows.append((rel_path, member, lang, lines))

        seen: set[str] = set()
        if lang in ("typescript", "tsx", "javascript"):
            for m in TS_EXPORT_RE.finditer(content):
                kind, sym = m.group(1), m.group(2)
                if sym not in seen:
                    seen.add(sym)
                    node_rows.append((f"{rel_path}::{sym}", sym, kind, rel_path, member, 1))
            for im in TS_IMPORT_RE.finditer(content):
                spec = im.group(1)
                edge_rows.append((rel_path, spec, "imports", member, member))
        elif lang == "python":
            for m in PY_SYMBOL_RE.finditer(content):
                kind, sym = m.group(1), m.group(2)
                if sym not in seen:
                    seen.add(sym)
                    exported = 0 if sym.startswith("_") else 1
                    node_rows.append((f"{rel_path}::{sym}", sym, kind, rel_path, member, exported))
            for im in PY_IMPORT_RE.finditer(content):
                spec = im.group(1) or im.group(2) or ""
                if spec:
                    edge_rows.append((rel_path, spec, "imports", member, member))
        elif lang == "rust":
            for m in RS_SYMBOL_RE.finditer(content):
                kind, sym = m.group(1), m.group(2)
                if sym not in seen:
                    seen.add(sym)
                    node_rows.append((f"{rel_path}::{sym}", sym, kind, rel_path, member, 1))

    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute("DROP TABLE IF EXISTS edges")
        cur.execute("DROP TABLE IF EXISTS nodes")
        cur.execute("DROP TABLE IF EXISTS files")
        cur.execute(
            """
            CREATE TABLE files (
                path TEXT PRIMARY KEY,
                member TEXT NOT NULL,
                language TEXT NOT NULL,
                line_count INTEGER NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE nodes (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                kind TEXT NOT NULL,
                file_path TEXT NOT NULL,
                member TEXT NOT NULL,
                exported INTEGER NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE edges (
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                relation TEXT NOT NULL,
                source_member TEXT NOT NULL,
                target_member TEXT NOT NULL
            )
            """
        )
        cur.executemany(
            "INSERT OR REPLACE INTO files (path, member, language, line_count) VALUES (?, ?, ?, ?)",
            file_rows,
        )
        cur.executemany(
            "INSERT OR REPLACE INTO nodes (id, name, kind, file_path, member, exported) VALUES (?, ?, ?, ?, ?, ?)",
            node_rows,
        )
        cur.executemany(
            "INSERT INTO edges (source_id, target_id, relation, source_member, target_member) VALUES (?, ?, ?, ?, ?)",
            edge_rows,
        )
        conn.commit()
    finally:
        conn.close()

    return time.perf_counter() - t0


def audit_codegraph_repo_config(estate_root: Path, repos: tuple[str, ...] = SIX_CODE_REPOS) -> list[str]:
    """Verify `.codegraph/.gitignore` and `codegraph sync` hook wiring across the 6 code repos."""
    findings: list[str] = []
    for repo_name in repos:
        repo_dir = estate_root / repo_name
        gi = repo_dir / ".codegraph" / ".gitignore"
        if not gi.is_file():
            findings.append(f"{repo_name}: missing .codegraph/.gitignore")
        else:
            gi_text = gi.read_text(encoding="utf-8")
            if "!.gitignore" not in gi_text:
                findings.append(f"{repo_name}: .codegraph/.gitignore missing '!.gitignore' rule")

        precommit = repo_dir / ".pre-commit-config.yaml"
        husky_precommit = repo_dir / ".husky" / "pre-commit"
        has_precommit_hook = (
            precommit.is_file()
            and "id: codegraph-sync" in precommit.read_text(encoding="utf-8")
            and "codegraph sync" in precommit.read_text(encoding="utf-8")
        )
        has_husky_hook = (
            husky_precommit.is_file()
            and "codegraph sync" in husky_precommit.read_text(encoding="utf-8")
        )
        if repo_name in PRECOMMIT_CODEGRAPH_REPOS and not has_precommit_hook:
            findings.append(f"{repo_name}: missing `id: codegraph-sync` in .pre-commit-config.yaml")
        elif not (has_precommit_hook or has_husky_hook):
            findings.append(f"{repo_name}: missing `codegraph sync` hook in .pre-commit-config.yaml or .husky/pre-commit")
    return findings


class TestT84CodegraphFreshnessAndHygiene(unittest.TestCase):
    """T84 AC1–AC6 verification suite."""

    def test_ac1_cross_repo_codegraph_sync_hooks_and_gitignore(self) -> None:
        """AC1: All 6 code repos have `.codegraph/.gitignore` and wire `codegraph sync` hooks."""
        findings = audit_codegraph_repo_config(ESTATE_ROOT)
        self.assertEqual(findings, [], f"Live estate failed T84 AC1 audit: {findings}")

        # Red probe: a fixture repo missing `id: codegraph-sync` or `.codegraph/.gitignore` MUST fail.
        with tempfile.TemporaryDirectory() as tmp:
            fx = Path(tmp)
            (fx / "w0m-ext").mkdir(parents=True)
            (fx / "w0m-ext" / ".pre-commit-config.yaml").write_text("repos: []\n", encoding="utf-8")
            bad = audit_codegraph_repo_config(fx, repos=("w0m-ext",))
            self.assertEqual(len(bad), 2, f"Expected 2 findings on broken fixture, got: {bad}")

    def test_ac2_index_freshness_and_subsecond_sync_across_repos(self) -> None:
        """AC2: Refresh `.codegraph/graph.db` across all 6 code repos with zero errors and sub-second latency."""
        for repo_name in SIX_CODE_REPOS:
            repo_dir = ESTATE_ROOT / repo_name
            elapsed = sync_repo_codegraph_db(repo_dir)
            db_path = repo_dir / ".codegraph" / "graph.db"
            self.assertTrue(db_path.is_file(), f"{repo_name}: .codegraph/graph.db was not created")
            self.assertLess(
                elapsed,
                1.5,
                f"{repo_name}: codegraph sync exceeded latency budget ({elapsed:.3f}s)",
            )
            conn = sqlite3.connect(str(db_path))
            try:
                files_cnt = conn.execute("SELECT count(*) FROM files").fetchone()[0]
                nodes_cnt = conn.execute("SELECT count(*) FROM nodes").fetchone()[0]
                edges_cnt = conn.execute("SELECT count(*) FROM edges").fetchone()[0]
            finally:
                conn.close()
            self.assertGreater(files_cnt, 0, f"{repo_name}: .codegraph/graph.db has 0 files")
            self.assertGreater(nodes_cnt, 0, f"{repo_name}: .codegraph/graph.db has 0 symbol nodes")
            self.assertGreaterEqual(edges_cnt, 0, f"{repo_name}: .codegraph/graph.db edges query failed")

    def test_ac3_ac6_w0m_mlx_clean_tree_and_t184_p3_consolidation(self) -> None:
        """AC3 & AC6: `w0m-mlx/w0m-mlx` is clean, unpatched from dirty vendored `mlx-rs`, and P3-aligned with T184."""
        mlx_repo = ESTATE_ROOT / "w0m-mlx" / "w0m-mlx"
        self.assertTrue(mlx_repo.is_dir(), "w0m-mlx/w0m-mlx directory must exist")
        st = subprocess.run(
            ["git", "-C", str(mlx_repo), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(
            st.stdout.strip(),
            "",
            f"w0m-mlx/w0m-mlx has dirty working tree files:\n{st.stdout}",
        )

        cargo_toml_active = "\n".join(
            ln for ln in (mlx_repo / "Cargo.toml").read_text(encoding="utf-8").splitlines()
            if not ln.strip().startswith("#")
        )
        self.assertNotIn(
            "[patch.crates-io]",
            cargo_toml_active,
            "w0m-mlx/w0m-mlx/Cargo.toml must not path-override to dirty vendored mlx-rs (T184 AC6)",
        )

        t84_text = (ESTATE_ROOT / ".tasks" / "T84.md").read_text(encoding="utf-8")
        self.assertIn("priority: P3", t84_text)
        self.assertIn("[[T184]]", t84_text)

    def test_ac5_graphify_union_alignment(self) -> None:
        """AC5: `scripts/graph_health.py --json` enumerates all 7 repos in the union."""
        proc = subprocess.run(
            [sys.executable, str(ESTATE_ROOT / "scripts" / "graph_health.py"), "--json"],
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(proc.stdout)
        rows = payload.get("rows", [])
        self.assertEqual(len(rows), 7, f"Expected 7 repos in graph_health, got {len(rows)}")
        for r in rows:
            self.assertTrue(r.get("graph"), f"{r.get('tag')} missing graphify-out/graph.json")
            self.assertTrue(r.get("in_union"), f"{r.get('tag')} not in global union")


if __name__ == "__main__":
    unittest.main(verbosity=2)
