#!/usr/bin/env python3
"""T669 — Local Hybrid BM25 + Dense Semantic Vector Knowledge Index & Mac Backup Research Rescue.

Implements the 3-Tier Knowledge & Research Storage Architecture (T109, T302, T640, AgDR-0055):
  - Tier 1 (Git Canonical `@wom` Research): Rescues unindexed `@wom`-scoped architectural proposals,
    audits, and MLX benchmarks from Mac backups into `w0m-web/docs/reports/mac-recovery/` while
    enforcing strict `kb-content-policy` client/personal isolation and secret scrubbing.
  - Tier 2 (Local Hybrid FTS5 BM25 + 128-dim LSA/SVD Dense Vector Index): Builds
    `~/.w0m/knowledge-index/corpus.sqlite` with Contextual Prefixing, SQLite FTS5 (`bm25`),
    128-dim `numpy` Randomized SVD unit embeddings, Reciprocal Rank Fusion (`RRF`), and deterministic
    semantic topic clustering ($0 cloud cost, zero Supabase 500 MB cap consumption).
  - Tier 3 (Redacted Cold Backup Catalog): Writes `~/.w0m/knowledge-index/mac-backup-catalog.json`
    with boundary-classified (`w0m_canonical`, `self_product`, `client_confidential`,
    `personal_private`) metadata & headings for Mac backup archives without copying client or
    personal bodies into git.

Commands:
  python3 scripts/w0m_kb_vector.py rescue-mac [--tar PATH] [--out-dir PATH]
  python3 scripts/w0m_kb_vector.py index [--root PATH] [--db PATH]
  python3 scripts/w0m_kb_vector.py search "<query>" [--top-k 10] [--mode hybrid|bm25|vector] [--json]
  python3 scripts/w0m_kb_vector.py clusters [--json]
  python3 scripts/w0m_kb_vector.py stats [--json]
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import sys
import tarfile
import time
from typing import Any

import numpy as np

ESTATE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INDEX_DIR = Path.home() / ".w0m" / "knowledge-index"
DEFAULT_DB_PATH = DEFAULT_INDEX_DIR / "corpus.sqlite"
DEFAULT_MAC_CATALOG_PATH = DEFAULT_INDEX_DIR / "mac-backup-catalog.json"
DEFAULT_MAC_TAR = Path(
    "/home/aleksei/mac_backup_2026-10-31/migration_export_2026-10-31/local_vaults_and_wom_untracked.tar.gz"
)
DEFAULT_MAC_DL_TAR = Path(
    "/home/aleksei/mac_backup_2026-10-31/migration_export_2026-10-31/Downloads_and_Documents.tar.gz"
)
DEFAULT_CHROME_EXPORT = Path("/home/aleksei/mac_backup_2026-11-01/chrome_and_session_buddy_export.md")
DEFAULT_RECOVERY_DIR = ESTATE_ROOT / "w0m-web" / "docs" / "reports" / "mac-recovery"

EMBED_DIM = 128
MAX_VOCAB = 4096
RRF_K = 60

CLIENT_MARKERS = (
    "lahore",
    "evercred",
    "nexrizen",
    "bridgeroad",
    "artemio",
    "openhome",
    "dpoint",
    "infatica",
    "barterbackup",
    "atos",
    "clara",
    "mallow",
    "_proj/",
    "client-projects/",
    "obsidian_and_project_vaults/",
)

PERSONAL_MARKERS = (
    "aleksei_cv",
    "apple_notes",
    "passwords.csv",
    "keychain",
    "safari_bookmarks",
    "chrome_and_session_buddy",
    "arc_exporter",
    "private.md",
    "private.pdf",
)

SELF_PRODUCT_MARKERS = (
    "servicios777",
    "1945/",
    "personaje0/",
    "orql_mvp/",
    "k7tg/",
    "mantrabox",
    "birds-echo",
)

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("openai_or_anthropic_key", re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_\-]{20,}\b")),
    ("github_pat", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{16,}\b")),
    ("jwt_token", re.compile(r"\beyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\b")),
    ("private_key_pem", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY-----")),
)

TOKEN_RE = re.compile(r"[a-z][a-z0-9_\-]{2,28}")
STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "are", "was", "were",
    "have", "has", "had", "not", "but", "you", "all", "can", "her", "his", "one", "our",
    "out", "day", "get", "use", "new", "now", "way", "may", "see", "two", "how", "its",
    "who", "oil", "sit", "set", "run", "eat", "far", "sea", "eye", "ago", "off", "too",
    "any", "say", "man", "try", "ask", "end", "why", "let", "put", "she", "him", "per",
    "via", "also", "when", "will", "more", "than", "then", "them", "some", "what", "only",
    "over", "such", "make", "like", "time", "very", "much", "need", "each", "file", "files",
    "line", "lines", "path", "true", "false", "none", "null", "todo", "done", "should",
    "would", "could", "which", "their", "there", "where", "after", "before", "under",
    "between", "through", "during", "without", "within", "across", "against", "because",
    "while", "about", "other", "these", "those", "every", "first", "second", "third",
    "using", "used", "uses", "must", "does", "did", "been", "being", "both", "same",
    "section", "summary", "overview", "status", "notes", "links", "task", "tasks",
    "ticket", "tickets", "report", "reports", "spec", "specs", "change", "changes",
}


def classify_source_boundary(path_str: str, text_sample: str = "") -> str:
    """Classify a document or archive member into one of the 4 governance tiers."""
    lower_path = path_str.lower().replace("\\", "/")
    lower_head = text_sample[:1000].lower()

    if any(m in lower_path for m in PERSONAL_MARKERS):
        return "personal_private"
    if any(m in lower_path for m in CLIENT_MARKERS):
        return "client_confidential"
    # Check if an archive delivery report is for client artemio
    if "delivery_reports_2026-09" in lower_path and ("artemio" in lower_path or "artemio" in lower_head or "dish" in lower_path):
        return "client_confidential"
    if "lahore" in lower_head or "evercred" in lower_head or "nexrizen" in lower_head:
        if "kb-content-policy" not in lower_head and "excluded from public kb" not in lower_head:
            return "client_confidential"
    if any(m in lower_path for m in SELF_PRODUCT_MARKERS):
        return "self_product"
    return "w0m_canonical"


def scrub_secrets(text: str) -> tuple[str, list[str]]:
    """Redact credential-shaped strings and return `(scrubbed_text, matched_kinds)`."""
    found: list[str] = []
    out = text
    for kind, pat in SECRET_PATTERNS:
        if pat.search(out):
            found.append(kind)
            out = pat.sub(f"[REDACTED:{kind}]", out)
    return out, found


def extract_headings(text: str, limit: int = 8) -> list[str]:
    """Extract markdown `#` headings from text."""
    headings: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("#") and len(s) <= 160:
            headings.append(s)
            if len(headings) >= limit:
                break
    return headings


def extract_title(text: str, fallback: str) -> str:
    """Return the first H1 heading or fallback stem."""
    for line in text.splitlines()[:30]:
        s = line.strip()
        if s.startswith("# "):
            return s[2:].strip()
    return fallback


def chunk_markdown(
    text: str,
    rel_path: str,
    category: str,
    title: str,
    max_chars: int = 1600,
) -> list[dict[str, Any]]:
    """Split a Markdown document into heading-scoped chunks with Contextual Prefixing."""
    lines = text.splitlines()
    sections: list[tuple[str, list[str]]] = []
    current_heading = title
    current_lines: list[str] = []

    for line in lines:
        if line.startswith("## ") or line.startswith("### "):
            if current_lines:
                sections.append((current_heading, current_lines))
                current_lines = []
            current_heading = line.lstrip("#").strip()
        current_lines.append(line)
    if current_lines:
        sections.append((current_heading, current_lines))

    chunks: list[dict[str, Any]] = []
    chunk_idx = 0
    for heading, sec_lines in sections:
        body = "\n".join(sec_lines).strip()
        if not body:
            continue
        # Sub-chunk if section exceeds max_chars
        start = 0
        while start < len(body):
            slice_text = body[start : start + max_chars].strip()
            if slice_text:
                prefix = f"[Doc: {title} | Category: {category} | Section: {heading} | Path: {rel_path}]"
                chunks.append(
                    {
                        "chunk_index": chunk_idx,
                        "heading": heading,
                        "prefix": prefix,
                        "content": slice_text,
                        "prefixed_content": f"{prefix}\n{slice_text}",
                    }
                )
                chunk_idx += 1
            start += max_chars
    if not chunks and text.strip():
        prefix = f"[Doc: {title} | Category: {category} | Section: {title} | Path: {rel_path}]"
        chunks.append(
            {
                "chunk_index": 0,
                "heading": title,
                "prefix": prefix,
                "content": text.strip()[:max_chars],
                "prefixed_content": f"{prefix}\n{text.strip()[:max_chars]}",
            }
        )
    return chunks


def tokenize(text: str) -> list[str]:
    """Tokenize text into normalized unigrams and select high-signal bigrams."""
    raw = [t for t in TOKEN_RE.findall(text.lower()) if t not in STOPWORDS and len(t) >= 2]
    bigrams = [f"{raw[i]}_{raw[i + 1]}" for i in range(len(raw) - 1) if len(raw[i]) >= 3 and len(raw[i + 1]) >= 3]
    return raw + bigrams


def compute_lsa_embeddings(
    chunk_texts: list[str],
    dim: int = EMBED_DIM,
    max_vocab: int = MAX_VOCAB,
) -> tuple[np.ndarray, dict[str, int], np.ndarray, np.ndarray]:
    """Compute sublinear TF-IDF + Randomized SVD unit embeddings in pure numpy.

    Returns:
      - `doc_vecs`: shape `(N, actual_dim)` float32 L2-normalized unit vectors
      - `vocab`: mapping `term -> col_idx`
      - `idf`: shape `(V,)` float32 IDF vector
      - `projection`: shape `(V, actual_dim)` float32 right singular vectors `V_k`
    """
    n_docs = len(chunk_texts)
    if n_docs == 0:
        return (
            np.zeros((0, dim), dtype=np.float32),
            {},
            np.zeros((0,), dtype=np.float32),
            np.zeros((0, dim), dtype=np.float32),
        )

    tokenized_docs = [tokenize(t) for t in chunk_texts]
    df_counter: Counter[str] = Counter()
    for toks in tokenized_docs:
        df_counter.update(set(toks))

    # Filter rare terms (unless corpus is tiny in unit tests)
    min_df = 2 if n_docs >= 20 else 1
    most_common = [term for term, df in df_counter.most_common(max_vocab * 2) if df >= min_df][:max_vocab]
    if not most_common:
        most_common = [term for term, _ in df_counter.most_common(max_vocab)]

    vocab = {term: idx for idx, term in enumerate(most_common)}
    v_size = len(vocab)
    actual_dim = max(1, min(dim, n_docs, v_size))

    idf = np.zeros(v_size, dtype=np.float32)
    for term, idx in vocab.items():
        df = df_counter[term]
        idf[idx] = math.log((1.0 + n_docs) / (1.0 + df)) + 1.0

    tfidf = np.zeros((n_docs, v_size), dtype=np.float32)
    for d_idx, toks in enumerate(tokenized_docs):
        counts = Counter(t for t in toks if t in vocab)
        for term, cnt in counts.items():
            col = vocab[term]
            tfidf[d_idx, col] = (1.0 + math.log(cnt)) * idf[col]

    # Row-normalize TF-IDF
    row_norms = np.linalg.norm(tfidf, axis=1, keepdims=True)
    row_norms[row_norms == 0.0] = 1.0
    tfidf /= row_norms

    # Deterministic Randomized SVD (Halko et al. 2011) with seed=42
    rng = np.random.default_rng(42)
    oversample = min(16, max(2, v_size - actual_dim))
    k_proj = min(v_size, n_docs, actual_dim + oversample)
    omega = rng.standard_normal((v_size, k_proj), dtype=np.float32)
    y_mat = tfidf @ omega
    # 1 power iteration for spectral sharpness
    y_mat = tfidf @ (tfidf.T @ y_mat)
    q_mat, _ = np.linalg.qr(y_mat, mode="reduced")
    b_mat = q_mat.T @ tfidf  # shape (k_proj, v_size)
    u_tilde, s_vals, vt_mat = np.linalg.svd(b_mat, full_matrices=False)
    del u_tilde, s_vals

    projection = vt_mat[:actual_dim, :].T.astype(np.float32)  # shape (v_size, actual_dim)
    doc_vecs = tfidf @ projection  # shape (n_docs, actual_dim)
    vec_norms = np.linalg.norm(doc_vecs, axis=1, keepdims=True)
    vec_norms[vec_norms == 0.0] = 1.0
    doc_vecs = (doc_vecs / vec_norms).astype(np.float32)

    return doc_vecs, vocab, idf, projection


def embed_query(
    query: str,
    vocab: dict[str, int],
    idf: np.ndarray,
    projection: np.ndarray,
) -> np.ndarray:
    """Project a search query into the same LSA unit-vector space."""
    v_size = len(vocab)
    if v_size == 0 or projection.size == 0:
        return np.zeros((projection.shape[1] if projection.ndim == 2 else EMBED_DIM,), dtype=np.float32)
    toks = tokenize(query)
    q_tfidf = np.zeros((v_size,), dtype=np.float32)
    counts = Counter(t for t in toks if t in vocab)
    for term, cnt in counts.items():
        col = vocab[term]
        q_tfidf[col] = (1.0 + math.log(cnt)) * idf[col]
    q_vec = q_tfidf @ projection
    norm = float(np.linalg.norm(q_vec))
    if norm > 0.0:
        q_vec = q_vec / norm
    return q_vec.astype(np.float32)


def cluster_documents(
    doc_vecs: np.ndarray,
    doc_titles: list[str],
    doc_paths: list[str],
    doc_texts: list[str],
    vocab: dict[str, int],
    projection: np.ndarray,
    n_clusters: int = 10,
) -> list[dict[str, Any]]:
    """Run deterministic spherical k-means over document centroid vectors to extract roadmap themes."""
    n_docs = doc_vecs.shape[0]
    if n_docs == 0:
        return []
    k = max(1, min(n_clusters, n_docs))
    # Deterministic farthest-first (k-means++) initialization starting from index 0
    centroids = np.zeros((k, doc_vecs.shape[1]), dtype=np.float32)
    centroids[0] = doc_vecs[0]
    chosen = {0}
    for c_idx in range(1, k):
        sims = doc_vecs @ centroids[:c_idx].T  # (n_docs, c_idx)
        max_sim = np.max(sims, axis=1)
        for ch in chosen:
            max_sim[ch] = 2.0
        next_idx = int(np.argmin(max_sim))
        chosen.add(next_idx)
        centroids[c_idx] = doc_vecs[next_idx]

    labels = np.zeros(n_docs, dtype=np.int32)
    for _ in range(15):
        sims = doc_vecs @ centroids.T
        new_labels = np.argmax(sims, axis=1)
        if np.array_equal(new_labels, labels):
            break
        labels = new_labels
        for c_idx in range(k):
            mask = labels == c_idx
            if np.any(mask):
                mean_vec = np.mean(doc_vecs[mask], axis=0)
                norm = float(np.linalg.norm(mean_vec))
                if norm > 0.0:
                    centroids[c_idx] = mean_vec / norm

    inv_vocab = {idx: term for term, idx in vocab.items()}
    clusters_out: list[dict[str, Any]] = []
    for c_idx in range(k):
        mask = np.where(labels == c_idx)[0]
        if mask.size == 0:
            continue
        c_vec = centroids[c_idx]
        # Top terms in original vocabulary aligned with centroid
        term_weights = projection @ c_vec  # (v_size,)
        top_term_indices = np.argsort(-term_weights)[:8]
        top_terms = [inv_vocab[int(i)] for i in top_term_indices if int(i) in inv_vocab]

        # Representative documents closest to centroid
        doc_sims = doc_vecs[mask] @ c_vec
        rep_order = mask[np.argsort(-doc_sims)[:5]]
        rep_docs = [
            {
                "path": doc_paths[int(i)],
                "title": doc_titles[int(i)],
                "score": round(float(doc_vecs[int(i)] @ c_vec), 4),
            }
            for i in rep_order
        ]
        clusters_out.append(
            {
                "cluster_id": int(c_idx),
                "doc_count": int(mask.size),
                "top_terms": top_terms,
                "label": " / ".join(top_terms[:4]),
                "representative_docs": rep_docs,
            }
        )
    clusters_out.sort(key=lambda x: x["doc_count"], reverse=True)
    for rank, item in enumerate(clusters_out, 1):
        item["rank"] = rank
    return clusters_out


def rescue_mac_backup_research(
    tar_path: Path = DEFAULT_MAC_TAR,
    out_dir: Path = DEFAULT_RECOVERY_DIR,
    catalog_path: Path = DEFAULT_MAC_CATALOG_PATH,
    ledger_path: Path | None = None,
) -> dict[str, Any]:
    """Rescue `@wom`-scoped unindexed research from Mac backups and write the cold catalog.

    Enforces `kb-content-policy` (`T302`):
      - `w0m_canonical` and `wom7mlx` benchmark/architecture docs not already in `_in/ledger.json`
        are scrubbed for secrets and written to `out_dir`.
      - `client_confidential` (`Lahore_*`, `Evercred`, `nexrizen`, `artemio` delivery reports) and
        `personal_private` (`Aleksei_CV_*`, Apple Notes) are NEVER written to `out_dir`; only their
        redacted metadata & headings are recorded in `catalog_path`.
    """
    if ledger_path is None:
        ledger_path = ESTATE_ROOT / "_in" / "ledger.json"
    known_in: set[str] = set()
    if ledger_path.is_file():
        try:
            ledger_data = json.loads(ledger_path.read_text(encoding="utf-8"))
            known_in = {str(it.get("file", "")).strip() for it in ledger_data.get("items", [])}
        except Exception:
            known_in = set()

    out_dir.mkdir(parents=True, exist_ok=True)
    catalog_path.parent.mkdir(parents=True, exist_ok=True)

    rescued_files: list[dict[str, Any]] = []
    catalog_entries: list[dict[str, Any]] = []
    skipped_client_or_personal = 0
    redacted_secret_hits = 0

    if tar_path.is_file():
        with tarfile.open(tar_path, "r:gz") as tf:
            for member in tf.getmembers():
                if not member.isfile():
                    continue
                m_name = member.name
                if not (m_name.endswith(".md") or m_name.endswith(".mmd") or m_name.endswith(".txt")):
                    continue

                f_obj = tf.extractfile(member)
                if f_obj is None:
                    continue
                raw_bytes = f_obj.read()
                text = raw_bytes.decode("utf-8", errors="replace")
                scrubbed, secret_kinds = scrub_secrets(text)
                if secret_kinds:
                    redacted_secret_hits += len(secret_kinds)

                boundary = classify_source_boundary(m_name, scrubbed)
                sha256_hex = hashlib.sha256(raw_bytes).hexdigest()
                headings = extract_headings(scrubbed, limit=6)
                title = extract_title(scrubbed, Path(m_name).stem)

                catalog_entries.append(
                    {
                        "archive": tar_path.name,
                        "member_path": m_name,
                        "boundary": boundary,
                        "size_bytes": member.size,
                        "sha256": sha256_hex,
                        "title": title,
                        "headings": headings,
                        "secrets_scrubbed": secret_kinds,
                    }
                )

                if boundary in ("client_confidential", "personal_private"):
                    skipped_client_or_personal += 1
                    continue

                # Determine if this is an unindexed `@wom` research/architecture artifact to rescue into Tier 1
                fname = Path(m_name).name
                is_unindexed_in = (
                    m_name.startswith("wom_local/_in/")
                    and fname.endswith(".md")
                    and fname not in known_in
                )
                is_wom7mlx_bench = (
                    "wom7mlx/eval-gemma4/" in m_name
                    and fname in ("BENCHMARK_REPORT.md", "results_matrix.md", "matrix_report.md", "implementation_plan.md")
                )
                is_delivery_arch = (
                    m_name.startswith("wom_local/_arch/delivery_reports_2026-09/")
                    and boundary == "w0m_canonical"
                    and fname in (
                        "2026-09-12-delivery-client-obsidian-vault-and-mermaid-linting-enhancements.md",
                        "2026-09-12-delivery-epic-github-sync-and-telegram-multi-manager-system.md",
                        "2026-09-12-t217-jam-gauge-and-w0m-bug-report-widget-delivery-report.md",
                    )
                )

                if is_unindexed_in or is_wom7mlx_bench or is_delivery_arch:
                    target_name = f"wom7mlx-gemma4-{fname}" if is_wom7mlx_bench else fname
                    target_path = out_dir / target_name
                    header_comment = (
                        f"<!-- Rescued by T669 from {tar_path.name}:{m_name} "
                        f"(sha256:{sha256_hex[:12]}, boundary:{boundary}) -->\n"
                    )
                    content_to_write = scrubbed if scrubbed.startswith("<!-- Rescued by T669") else header_comment + scrubbed
                    target_path.write_text(content_to_write, encoding="utf-8")
                    rescued_files.append(
                        {
                            "file": target_name,
                            "source_member": m_name,
                            "title": title,
                            "size_bytes": len(content_to_write.encode("utf-8")),
                            "sha256": sha256_hex[:12],
                            "boundary": boundary,
                        }
                    )

    # Write deterministic INDEX.md inside `out_dir`
    rescued_files.sort(key=lambda x: x["file"])
    index_lines = [
        "# Mac Backup Rescued `@wom` Research & Benchmark Corpus (T669)",
        "",
        "> **Governance (`T109` · `T302` · `AgDR-0055`):** Only `@wom`-scoped (`w0m_canonical`) architectural proposals, audits, and MLX benchmark matrices that were absent from `_in/ledger.json` are rescued here. Client-scoped (`_proj/*`, `Lahore_*`, `Evercred`, `nexrizen`, `artemio`) and personal (`Aleksei_CV_*`, Apple Notes) artifacts are strictly excluded and cataloged metadata-only in `~/.w0m/knowledge-index/mac-backup-catalog.json`.",
        "",
        "| File | Title | Source Archive Member | SHA-256 | Size |",
        "| :--- | :--- | :--- | :--- | ---: |",
    ]
    for rf in rescued_files:
        index_lines.append(
            f"| [`{rf['file']}`](./{rf['file']}) | {rf['title']} | `{rf['source_member']}` | `{rf['sha256']}` | {rf['size_bytes']} B |"
        )
    index_lines.append("")
    (out_dir / "INDEX.md").write_text("\n".join(index_lines), encoding="utf-8")

    summary_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ticket": "T669",
        "tar_source": str(tar_path),
        "total_cataloged": len(catalog_entries),
        "rescued_w0m_count": len(rescued_files),
        "excluded_client_or_personal_count": skipped_client_or_personal,
        "redacted_secret_hits": redacted_secret_hits,
        "rescued_files": rescued_files,
        "boundary_counts": dict(Counter(e["boundary"] for e in catalog_entries)),
        "entries": catalog_entries,
    }
    catalog_path.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")
    return summary_payload


def collect_estate_documents(root: Path = ESTATE_ROOT) -> list[dict[str, Any]]:
    """Collect all canonical `@wom` Markdown documents across the estate for Tier 2 indexing."""
    sources: list[tuple[str, Path]] = [
        ("agent_report", root / ".agents" / "reports"),
        ("web_report", root / "w0m-web" / "docs" / "reports"),
        ("mac_rescued", root / "w0m-web" / "docs" / "reports" / "mac-recovery"),
        ("web_research", root / "w0m-web" / "docs" / "research"),
        ("web_design", root / "w0m-web" / "docs" / "design"),
        ("decision", root / "docs" / "decisions"),
        ("estate_doc", root / "docs"),
        ("ticket", root / ".tasks"),
        ("openspec", root / "w0m-web" / "openspec"),
    ]
    single_files: list[tuple[str, Path]] = [
        ("lessons", root / "LESSONS.md"),
        ("tech_debt", root / "TECH-DEBT.md"),
        ("roadmap", root / "ROADMAP.md"),
    ]

    seen_paths: set[Path] = set()
    docs: list[dict[str, Any]] = []

    def _add_file(category: str, file_path: Path) -> None:
        resolved = file_path.resolve()
        if resolved in seen_paths or not resolved.is_file():
            return
        if resolved.suffix.lower() not in (".md", ".mmd"):
            return
        try:
            rel_path = str(resolved.relative_to(root.resolve())).replace("\\", "/")
        except ValueError:
            rel_path = str(resolved)
        # Skip archived tickets folder if huge or keep top-level tickets
        if "/.tasks/archive/" in f"/{rel_path}":
            return
        raw_text = resolved.read_text(encoding="utf-8", errors="replace")
        boundary = classify_source_boundary(rel_path, raw_text)
        if boundary in ("client_confidential", "personal_private"):
            return
        scrubbed_text, _ = scrub_secrets(raw_text)
        title = extract_title(scrubbed_text, resolved.stem)
        sha256_hex = hashlib.sha256(raw_text.encode("utf-8", errors="replace")).hexdigest()
        seen_paths.add(resolved)
        docs.append(
            {
                "rel_path": rel_path,
                "category": category,
                "boundary": boundary,
                "title": title,
                "sha256": sha256_hex,
                "size_bytes": len(raw_text.encode("utf-8", errors="replace")),
                "text": scrubbed_text,
            }
        )

    for cat, fpath in single_files:
        if fpath.is_file():
            _add_file(cat, fpath)

    # Ensure more specific directories (`mac_rescued`, `decision`) are scanned before parent dirs
    ordered_sources = [
        ("mac_rescued", root / "w0m-web" / "docs" / "reports" / "mac-recovery"),
        ("agent_report", root / ".agents" / "reports"),
        ("web_report", root / "w0m-web" / "docs" / "reports"),
        ("web_research", root / "w0m-web" / "docs" / "research"),
        ("web_design", root / "w0m-web" / "docs" / "design"),
        ("decision", root / "docs" / "decisions"),
        ("estate_doc", root / "docs"),
        ("ticket", root / ".tasks"),
        ("openspec", root / "w0m-web" / "openspec"),
    ]
    del sources
    for cat, dir_path in ordered_sources:
        if not dir_path.is_dir():
            continue
        for p in sorted(dir_path.rglob("*")):
            if p.is_file() and p.suffix.lower() in (".md", ".mmd"):
                _add_file(cat, p)

    return docs


def build_hybrid_index(
    root: Path = ESTATE_ROOT,
    db_path: Path = DEFAULT_DB_PATH,
    embed_dim: int = EMBED_DIM,
    n_clusters: int = 12,
) -> dict[str, Any]:
    """Build the SQLite FTS5 BM25 + 128-dim dense SVD vector index and semantic clusters."""
    t0 = time.monotonic()
    docs = collect_estate_documents(root=root)

    all_chunks: list[dict[str, Any]] = []
    for doc_id, doc in enumerate(docs):
        doc_chunks = chunk_markdown(
            text=doc["text"],
            rel_path=doc["rel_path"],
            category=doc["category"],
            title=doc["title"],
        )
        for ch in doc_chunks:
            ch["doc_id"] = doc_id
            ch["rel_path"] = doc["rel_path"]
            ch["category"] = doc["category"]
            ch["title"] = doc["title"]
            all_chunks.append(ch)

    chunk_texts = [f"{c['title']} {c['heading']}\n{c['content']}" for c in all_chunks]
    chunk_vecs, vocab, idf, projection = compute_lsa_embeddings(chunk_texts, dim=embed_dim)
    actual_dim = int(chunk_vecs.shape[1]) if chunk_vecs.ndim == 2 else embed_dim

    # Compute document-level centroid embeddings for topic clustering
    doc_vecs = np.zeros((len(docs), actual_dim), dtype=np.float32)
    doc_chunk_Lists: dict[int, list[int]] = {i: [] for i in range(len(docs))}
    for c_global_idx, ch in enumerate(all_chunks):
        doc_chunk_Lists[ch["doc_id"]].append(c_global_idx)
    for d_idx, c_indices in doc_chunk_Lists.items():
        if c_indices:
            mean_v = np.mean(chunk_vecs[c_indices], axis=0)
            norm = float(np.linalg.norm(mean_v))
            if norm > 0.0:
                doc_vecs[d_idx] = mean_v / norm

    clusters = cluster_documents(
        doc_vecs=doc_vecs,
        doc_titles=[d["title"] for d in docs],
        doc_paths=[d["rel_path"] for d in docs],
        doc_texts=[d["text"] for d in docs],
        vocab=vocab,
        projection=projection,
        n_clusters=n_clusters,
    )

    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.executescript(
            """
            CREATE TABLE meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE documents (
                doc_id INTEGER PRIMARY KEY,
                rel_path TEXT UNIQUE NOT NULL,
                category TEXT NOT NULL,
                boundary TEXT NOT NULL,
                title TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                embedding BLOB NOT NULL
            );
            CREATE TABLE chunks (
                chunk_id INTEGER PRIMARY KEY,
                doc_id INTEGER NOT NULL REFERENCES documents(doc_id),
                chunk_index INTEGER NOT NULL,
                rel_path TEXT NOT NULL,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                heading TEXT NOT NULL,
                prefix TEXT NOT NULL,
                content TEXT NOT NULL,
                embedding BLOB NOT NULL
            );
            CREATE VIRTUAL TABLE chunks_fts USING fts5(
                title,
                heading,
                content,
                category,
                rel_path,
                tokenize = 'porter unicode61'
            );
            CREATE TABLE clusters (
                cluster_id INTEGER PRIMARY KEY,
                rank INTEGER NOT NULL,
                doc_count INTEGER NOT NULL,
                label TEXT NOT NULL,
                top_terms_json TEXT NOT NULL,
                representative_docs_json TEXT NOT NULL
            );
            """
        )

        conn.executemany(
            """
            INSERT INTO documents (doc_id, rel_path, category, boundary, title, sha256, size_bytes, embedding)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    d_idx,
                    d["rel_path"],
                    d["category"],
                    d["boundary"],
                    d["title"],
                    d["sha256"],
                    d["size_bytes"],
                    doc_vecs[d_idx].tobytes(),
                )
                for d_idx, d in enumerate(docs)
            ],
        )

        conn.executemany(
            """
            INSERT INTO chunks (chunk_id, doc_id, chunk_index, rel_path, category, title, heading, prefix, content, embedding)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    c_idx,
                    ch["doc_id"],
                    ch["chunk_index"],
                    ch["rel_path"],
                    ch["category"],
                    ch["title"],
                    ch["heading"],
                    ch["prefix"],
                    ch["content"],
                    chunk_vecs[c_idx].tobytes(),
                )
                for c_idx, ch in enumerate(all_chunks)
            ],
        )

        conn.executemany(
            """
            INSERT INTO chunks_fts (rowid, title, heading, content, category, rel_path)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    c_idx,
                    ch["title"],
                    ch["heading"],
                    ch["content"],
                    ch["category"],
                    ch["rel_path"],
                )
                for c_idx, ch in enumerate(all_chunks)
            ],
        )

        conn.executemany(
            """
            INSERT INTO clusters (cluster_id, rank, doc_count, label, top_terms_json, representative_docs_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    cl["cluster_id"],
                    cl["rank"],
                    cl["doc_count"],
                    cl["label"],
                    json.dumps(cl["top_terms"]),
                    json.dumps(cl["representative_docs"]),
                )
                for cl in clusters
            ],
        )

        elapsed_s = round(time.monotonic() - t0, 3)
        cat_counts = dict(Counter(d["category"] for d in docs))
        meta_rows = [
            ("built_at", datetime.now(timezone.utc).isoformat()),
            ("ticket", "T669"),
            ("doc_count", str(len(docs))),
            ("chunk_count", str(len(all_chunks))),
            ("embed_dim", str(actual_dim)),
            ("vocab_json", json.dumps(vocab)),
            ("idf_blob_hex", idf.astype(np.float32).tobytes().hex()),
            ("projection_blob_hex", projection.astype(np.float32).tobytes().hex()),
            ("category_counts_json", json.dumps(cat_counts)),
            ("elapsed_seconds", str(elapsed_s)),
        ]
        conn.executemany("INSERT INTO meta (key, value) VALUES (?, ?)", meta_rows)
        conn.commit()
    finally:
        conn.close()

    return {
        "db_path": str(db_path),
        "doc_count": len(docs),
        "chunk_count": len(all_chunks),
        "embed_dim": actual_dim,
        "vocab_size": len(vocab),
        "cluster_count": len(clusters),
        "category_counts": cat_counts,
        "elapsed_seconds": elapsed_s,
        "db_size_bytes": db_path.stat().st_size if db_path.exists() else 0,
    }


def search_hybrid_index(
    query: str,
    db_path: Path = DEFAULT_DB_PATH,
    top_k: int = 10,
    mode: str = "hybrid",
    category: str | None = None,
) -> list[dict[str, Any]]:
    """Run hybrid BM25 + dense cosine similarity search with Reciprocal Rank Fusion (RRF)."""
    if not db_path.is_file():
        raise FileNotFoundError(f"Knowledge index database not found at {db_path}; run `just kb-index` first.")

    conn = sqlite3.connect(str(db_path))
    try:
        meta = dict(conn.execute("SELECT key, value FROM meta").fetchall())
        embed_dim = int(meta.get("embed_dim", EMBED_DIM))
        vocab: dict[str, int] = json.loads(meta.get("vocab_json", "{}"))
        idf = np.frombuffer(bytes.fromhex(meta.get("idf_blob_hex", "")), dtype=np.float32)
        proj_raw = np.frombuffer(bytes.fromhex(meta.get("projection_blob_hex", "")), dtype=np.float32)
        projection = proj_raw.reshape((len(vocab), embed_dim)) if vocab and proj_raw.size else np.zeros((0, embed_dim), dtype=np.float32)

        # 1. FTS5 BM25 lexical search
        fts_terms = [t for t in re.findall(r"[a-zA-Z0-9]+", query.lower()) if t not in STOPWORDS and len(t) >= 2]
        bm25_ranks: dict[int, int] = {}
        bm25_scores: dict[int, float] = {}
        if fts_terms and mode in ("hybrid", "bm25"):
            fts_query = " OR ".join(f'"{t}"' for t in fts_terms[:12])
            sql = """
                SELECT rowid, bm25(chunks_fts, 3.0, 2.0, 1.0, 0.5, 0.5) AS score
                FROM chunks_fts
                WHERE chunks_fts MATCH ?
            """
            params: list[Any] = [fts_query]
            if category:
                sql += " AND category = ?"
                params.append(category)
            sql += " ORDER BY score ASC LIMIT 100"
            for rank_idx, (chunk_id, raw_bm25) in enumerate(conn.execute(sql, params).fetchall(), 1):
                bm25_ranks[int(chunk_id)] = rank_idx
                bm25_scores[int(chunk_id)] = round(float(-raw_bm25), 4)

        # 2. Dense vector cosine similarity search
        vec_ranks: dict[int, int] = {}
        vec_scores: dict[int, float] = {}
        if mode in ("hybrid", "vector") and vocab:
            q_vec = embed_query(query, vocab, idf, projection)
            if float(np.linalg.norm(q_vec)) > 0.0:
                if category:
                    rows = conn.execute(
                        "SELECT chunk_id, embedding FROM chunks WHERE category = ?",
                        (category,),
                    ).fetchall()
                else:
                    rows = conn.execute("SELECT chunk_id, embedding FROM chunks").fetchall()
                if rows:
                    c_ids = [int(r[0]) for r in rows]
                    mat = np.frombuffer(b"".join(r[1] for r in rows), dtype=np.float32).reshape((len(rows), embed_dim))
                    sims = mat @ q_vec
                    top_indices = np.argsort(-sims)[:100]
                    for rank_idx, idx in enumerate(top_indices, 1):
                        cid = c_ids[int(idx)]
                        sim_val = float(sims[int(idx)])
                        if sim_val > 0.0:
                            vec_ranks[cid] = rank_idx
                            vec_scores[cid] = round(sim_val, 4)

        # 3. Combine via Reciprocal Rank Fusion (RRF)
        candidate_ids = set(bm25_ranks.keys()) | set(vec_ranks.keys())
        scored_candidates: list[tuple[float, int]] = []
        for cid in candidate_ids:
            if mode == "bm25":
                if cid not in bm25_ranks:
                    continue
                rrf = 1.0 / (RRF_K + bm25_ranks[cid])
            elif mode == "vector":
                if cid not in vec_ranks:
                    continue
                rrf = 1.0 / (RRF_K + vec_ranks[cid])
            else:
                r_bm25 = 1.0 / (RRF_K + bm25_ranks[cid]) if cid in bm25_ranks else 0.0
                r_vec = 1.0 / (RRF_K + vec_ranks[cid]) if cid in vec_ranks else 0.0
                rrf = r_bm25 + r_vec
            scored_candidates.append((rrf, cid))

        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        top_cids = [cid for _, cid in scored_candidates[:top_k]]
        if not top_cids:
            return []

        placeholders = ",".join("?" for _ in top_cids)
        chunk_rows = {
            int(r[0]): r
            for r in conn.execute(
                f"SELECT chunk_id, rel_path, category, title, heading, content FROM chunks WHERE chunk_id IN ({placeholders})",
                top_cids,
            ).fetchall()
        }

        results: list[dict[str, Any]] = []
        for rrf_score, cid in scored_candidates[:top_k]:
            row = chunk_rows.get(cid)
            if not row:
                continue
            _, rel_path, cat, title, heading, content = row
            snippet = " ".join(content.split())[:260]
            results.append(
                {
                    "chunk_id": cid,
                    "rel_path": rel_path,
                    "category": cat,
                    "title": title,
                    "heading": heading,
                    "rrf_score": round(rrf_score, 6),
                    "bm25_score": bm25_scores.get(cid, 0.0),
                    "cosine_score": vec_scores.get(cid, 0.0),
                    "snippet": snippet,
                }
            )
        return results
    finally:
        conn.close()


def load_clusters(db_path: Path = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    """Read semantic clusters from the SQLite index."""
    if not db_path.is_file():
        raise FileNotFoundError(f"Knowledge index database not found at {db_path}; run `just kb-index` first.")
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT cluster_id, rank, doc_count, label, top_terms_json, representative_docs_json FROM clusters ORDER BY rank ASC"
        ).fetchall()
        return [
            {
                "cluster_id": int(r[0]),
                "rank": int(r[1]),
                "doc_count": int(r[2]),
                "label": r[3],
                "top_terms": json.loads(r[4]),
                "representative_docs": json.loads(r[5]),
            }
            for r in rows
        ]
    finally:
        conn.close()


def load_stats(db_path: Path = DEFAULT_DB_PATH, catalog_path: Path = DEFAULT_MAC_CATALOG_PATH) -> dict[str, Any]:
    """Return index and Mac backup catalog statistics."""
    stats: dict[str, Any] = {"db_exists": db_path.is_file(), "catalog_exists": catalog_path.is_file()}
    if db_path.is_file():
        conn = sqlite3.connect(str(db_path))
        try:
            meta = dict(conn.execute("SELECT key, value FROM meta").fetchall())
            stats["built_at"] = meta.get("built_at")
            stats["doc_count"] = int(meta.get("doc_count", 0))
            stats["chunk_count"] = int(meta.get("chunk_count", 0))
            stats["embed_dim"] = int(meta.get("embed_dim", EMBED_DIM))
            stats["category_counts"] = json.loads(meta.get("category_counts_json", "{}"))
            stats["db_size_bytes"] = db_path.stat().st_size
        finally:
            conn.close()
    if catalog_path.is_file():
        cat = json.loads(catalog_path.read_text(encoding="utf-8"))
        stats["mac_catalog"] = {
            "total_cataloged": cat.get("total_cataloged", 0),
            "rescued_w0m_count": cat.get("rescued_w0m_count", 0),
            "excluded_client_or_personal_count": cat.get("excluded_client_or_personal_count", 0),
            "boundary_counts": cat.get("boundary_counts", {}),
        }
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_rescue = sub.add_parser("rescue-mac", help="Rescue @wom Mac backup research and build cold catalog")
    p_rescue.add_argument("--tar", type=Path, default=DEFAULT_MAC_TAR)
    p_rescue.add_argument("--out-dir", type=Path, default=DEFAULT_RECOVERY_DIR)
    p_rescue.add_argument("--catalog", type=Path, default=DEFAULT_MAC_CATALOG_PATH)
    p_rescue.add_argument("--json", action="store_true")

    p_index = sub.add_parser("index", help="Build hybrid FTS5 BM25 + 128-dim SVD vector index")
    p_index.add_argument("--root", type=Path, default=ESTATE_ROOT)
    p_index.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    p_index.add_argument("--clusters", type=int, default=12)
    p_index.add_argument("--json", action="store_true")

    p_search = sub.add_parser("search", help="Search the hybrid knowledge index")
    p_search.add_argument("query", type=str)
    p_search.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    p_search.add_argument("--top-k", type=int, default=10)
    p_search.add_argument("--mode", choices=("hybrid", "bm25", "vector"), default="hybrid")
    p_search.add_argument("--category", type=str, default=None)
    p_search.add_argument("--json", action="store_true")

    p_clusters = sub.add_parser("clusters", help="Show semantic roadmap topic clusters")
    p_clusters.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    p_clusters.add_argument("--json", action="store_true")

    p_stats = sub.add_parser("stats", help="Show hybrid index and Mac backup catalog stats")
    p_stats.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    p_stats.add_argument("--catalog", type=Path, default=DEFAULT_MAC_CATALOG_PATH)
    p_stats.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)

    if args.cmd == "rescue-mac":
        res = rescue_mac_backup_research(tar_path=args.tar, out_dir=args.out_dir, catalog_path=args.catalog)
        if args.json:
            print(json.dumps({k: v for k, v in res.items() if k != "entries"}, indent=2))
        else:
            print(
                f"Mac backup research rescue complete: {res['rescued_w0m_count']} @wom doc(s) rescued to {args.out_dir}, "
                f"{res['total_cataloged']} archive member(s) cataloged ({res['excluded_client_or_personal_count']} "
                f"client/personal excluded per T302)."
            )
        return 0

    if args.cmd == "index":
        res = build_hybrid_index(root=args.root, db_path=args.db, n_clusters=args.clusters)
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(
                f"Hybrid index built at {res['db_path']} in {res['elapsed_seconds']}s: "
                f"{res['doc_count']} docs, {res['chunk_count']} chunks, "
                f"{res['embed_dim']}-dim LSA vectors, {res['cluster_count']} clusters "
                f"({res['db_size_bytes'] // 1024} KB)."
            )
        return 0

    if args.cmd == "search":
        hits = search_hybrid_index(
            query=args.query,
            db_path=args.db,
            top_k=args.top_k,
            mode=args.mode,
            category=args.category,
        )
        if args.json:
            print(json.dumps(hits, indent=2))
        else:
            print(f"Query: {args.query!r} (mode={args.mode}, hits={len(hits)})")
            for idx, h in enumerate(hits, 1):
                print(
                    f"  {idx:2d}. [{h['category']}] {h['rel_path']} :: {h['heading']} "
                    f"(rrf={h['rrf_score']:.4f}, bm25={h['bm25_score']:.2f}, cos={h['cosine_score']:.3f})"
                )
                print(f"      {h['snippet']}")
        return 0

    if args.cmd == "clusters":
        clusters = load_clusters(db_path=args.db)
        if args.json:
            print(json.dumps(clusters, indent=2))
        else:
            for cl in clusters:
                print(f"Cluster #{cl['rank']:2d} ({cl['doc_count']:3d} docs): {cl['label']}")
                for rep in cl["representative_docs"][:3]:
                    print(f"    - {rep['path']} ({rep['title']}) [cos={rep['score']:.3f}]")
        return 0

    if args.cmd == "stats":
        st = load_stats(db_path=args.db, catalog_path=args.catalog)
        if args.json:
            print(json.dumps(st, indent=2))
        else:
            print(json.dumps(st, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
