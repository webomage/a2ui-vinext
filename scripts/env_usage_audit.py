#!/usr/bin/env python3
"""Audit environment & Infisical secret variable names against executable code readers (T729).

Classifies every candidate environment variable across all estate git repositories into:
  - `ACTIVE_RUNTIME`     : read in shipping app, package, Worker, Edge Function, extension, or MLX runtime code
  - `ACTIVE_CLI_OR_SYNC` : read only in `justfile`, `just/*.just`, `scripts/`, `project/scripts/`, or `wrangler*.jsonc`
  - `TESTS_E2E_ONLY`     : read only in Playwright/Vitest/Pytest/Deno test files
  - `DEAD_UNUSED`        : 0 executable readers across runtime, CLI/sync, and tests (safe to prune/delete)

Security invariant (`AgDR-0025`, `T729 AC1`):
  - NEVER reads, hashes, stores, or logs secret values (`os.environ[k]` / `os.getenv(k)`).
  - Inspects variable **names** (`list(os.environ.keys())` and static source declarations) ONLY.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

DEFAULT_INFISICAL_PROJECT_ID = "87a1718d-17c6-4c5e-b0c1-f8bb2fd9d13c"
DEFAULT_ESTATE_REPOS: tuple[str, ...] = (
    ".",
    "w0m-web",
    "w0m-api",
    "w0m-cf",
    "w0m-ext",
    "w0m-sec",
    "w0m-skills",
    "w0m-mlx/w0m-mlx",
)

ENV_NAME_RE = re.compile(r"\b[A-Z][A-Z0-9_]{2,}\b")

SKIP_SUFFIXES: tuple[str, ...] = (
    ".md",
    ".mdx",
    ".html",
    ".mmd",
    ".d.ts",
    ".svg",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".lock",
    ".sum",
    ".snap",
    ".map",
    ".wasm",
    ".pdf",
)

META_SKIP_SUBSTRINGS: tuple[str, ...] = (
    "secret_flow_check.py",
    "secret_history_check.py",
    "rotate_leaked_secrets.py",
    "test_rotate_leaked_secrets.py",
    "env_usage_audit.py",
    "test_env_usage_audit.py",
    "env_prune_dead.py",
    "test_env_prune_dead.py",
    "w0m_audit.py",
    "seo-geo-scanner.ts",
    "advanced-audit.ts",
    "host_surface_check",
    "authz_edge_fns.py",
    "worker-configuration.d.ts",
    "env.d.ts",
    "STATUS-DASHBOARD.html",
    ".tasks/",
    "docs/",
    "openspec/",
    "state-archive/",
    "AUDIT-",
    "TECH-DEBT.md",
    "LESSONS.md",
    "STATE.md",
    ".agents/",
    ".state/",
    "plan-history.jsonl",
    "tickets.json",
    "test-suites.json",
    "catalog-info.yaml",
    "ast_grep_test.py",
    "guard-test-admin.sh",
    "design-system/_ref/",
)

CONFIG_DECL_MARKERS: tuple[str, ...] = (
    "turbo.json",
    ".env.example",
    ".properties",
    "services-policy",
    "hygiene-policy",
    "clients-policy",
    "tools-policy",
    "sdlc.json",
    ".tf",
    ".sql",
)

TEST_PATH_MARKERS: tuple[str, ...] = (
    "playwright",
    "/e2e/",
    ".spec.",
    ".test.",
    "/tests/",
    "__tests__",
    "_steps.ts",
    "/test_",
)

CLI_OR_SYNC_MARKERS: tuple[str, ...] = (
    "justfile",
    "just/",
    "/scripts/",
    "project/scripts/",
    "wrangler",
)

HISTORICAL_DIGEST_LEAK_KEYS: frozenset[str] = frozenset(
    {
        "ADMIN_PASSWORD",
        "AWS_ACCESS_KEY",
        "AWS_ACCESS_SECRET",
        "CRON_SECRET",
        "CRYPTO_KEY",
        "E2E_ACCESS_SECRET",
        "GEMINI_API_KEY",
        "GITHUB_APP_CLIENT_SECRET",
        "GITHUB_APP_PRIVATE_KEY",
        "GITHUB_APP_WEBHOOK_SECRET",
        "GITHUB_TOKEN",
        "LINKEDIN_APP_SECRET",
        "MEMBER_PASSWORD",
        "MISTRAL_API_KEY",
        "MISTRAL_API_KEY_W0M",
        "POSTHOG_API_KEY",
        "RESEND_API_KEY",
        "SMTP_PASS",
        "UPWORK_API_KEY",
        "UPWORK_API_SECRET",
    }
)


def _should_skip_rel_path(rel_path: str) -> bool:
    lower = rel_path.lower()
    if lower.endswith(SKIP_SUFFIXES):
        return True
    return any(marker in rel_path for marker in META_SKIP_SUBSTRINGS)


def _classify_file_bucket(rel_path: str) -> str:
    norm = "/" + rel_path.lower().lstrip("/")
    if any(m in norm for m in CONFIG_DECL_MARKERS):
        return "config_decl_only"
    if any(m in norm for m in TEST_PATH_MARKERS):
        return "tests_only"
    if any(m in norm for m in CLI_OR_SYNC_MARKERS) or rel_path.startswith("scripts/"):
        return "sync_or_cli"
    return "prod_readers"


def _extract_active_tokens(text: str, candidate_set: frozenset[str] | None = None) -> set[str]:
    tokens: set[str] = set()
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith(("//", "#", "--", "*", "/*")):
            continue
        for match in ENV_NAME_RE.finditer(stripped):
            tok = match.group(0)
            if candidate_set is not None and tok not in candidate_set:
                continue
            # Skip pure TypeScript interface property declarations (`KEY?: string;`)
            if ":" in stripped and re.match(
                rf"^(?:readonly\s+)?{re.escape(tok)}\??\s*:\s*[^=;]+[;,]?\s*(?://.*)?$",
                stripped,
            ):
                continue
            tokens.add(tok)
    return tokens


def _list_repo_files(repo_dir: Path) -> list[str]:
    if (repo_dir / ".git").exists():
        proc = subprocess.run(
            ["git", "-C", str(repo_dir), "ls-files"],
            capture_output=True,
            text=True,
            env={"PATH": os.environ.get("PATH", ""), "LC_ALL": "C", "GIT_TERMINAL_PROMPT": "0"},
            check=False,
        )
        if proc.returncode == 0:
            return [ln for ln in proc.stdout.splitlines() if ln]
    return [
        p.relative_to(repo_dir).as_posix()
        for p in sorted(repo_dir.rglob("*"))
        if p.is_file() and ".git" not in p.parts and "node_modules" not in p.parts
    ]


def index_estate_env_tokens(
    estate_root: Path,
    repos: Sequence[str] = DEFAULT_ESTATE_REPOS,
    candidate_set: frozenset[str] | None = None,
) -> dict[str, dict[str, list[str]]]:
    """Build an inverted index `TOKEN -> {bucket -> [rel_paths]}` across all estate repos."""
    root = estate_root.resolve()
    inverted: dict[str, dict[str, list[str]]] = {}

    for repo_rel in repos:
        repo_dir = root if repo_rel == "." else (root / repo_rel)
        if not repo_dir.is_dir():
            continue
        for file_in_repo in _list_repo_files(repo_dir):
            rel = file_in_repo if repo_rel == "." else f"{repo_rel}/{file_in_repo}"
            if _should_skip_rel_path(rel):
                continue
            fp = root / rel
            if fp.is_symlink() or not fp.is_file():
                continue
            try:
                if fp.stat().st_size > 1_500_000:
                    continue
                content = fp.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            bucket = _classify_file_bucket(rel)
            for tok in _extract_active_tokens(content, candidate_set=candidate_set):
                entry = inverted.setdefault(
                    tok,
                    {
                        "prod_readers": [],
                        "sync_or_cli": [],
                        "tests_only": [],
                        "config_decl_only": [],
                    },
                )
                entry[bucket].append(rel)

    return inverted


def discover_static_candidate_keys(estate_root: Path) -> list[str]:
    """Collect declared env/secret variable names from static manifests without touching secret values."""
    root = estate_root.resolve()
    found: set[str] = set(HISTORICAL_DIGEST_LEAK_KEYS)

    rot_script = root / "w0m-api" / "scripts" / "rotate_leaked_secrets.py"
    if rot_script.is_file():
        txt = rot_script.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(r'"name"\s*:\s*"([A-Z][A-Z0-9_]{2,})"', txt):
            found.add(m.group(1))

    sync_script = root / "w0m-api" / "scripts" / "sync_supabase_secrets.py"
    if sync_script.is_file():
        txt = sync_script.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(r'"([A-Z][A-Z0-9_]{3,})"', txt):
            found.add(m.group(1))

    turbo_json = root / "w0m-web" / "turbo.json"
    if turbo_json.is_file():
        try:
            doc = json.loads(turbo_json.read_text(encoding="utf-8"))
            for k in doc.get("globalEnv") or []:
                if isinstance(k, str) and ENV_NAME_RE.fullmatch(k):
                    found.add(k)
            for task_cfg in (doc.get("tasks") or {}).values():
                if isinstance(task_cfg, dict):
                    for k in task_cfg.get("env") or []:
                        if isinstance(k, str) and ENV_NAME_RE.fullmatch(k):
                            found.add(k)
        except ValueError:
            pass

    svc_policy = root / "project" / "policies" / "services-policy.json"
    if svc_policy.is_file():
        txt = svc_policy.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(r'"([A-Z][A-Z0-9_]{3,})"', txt):
            tok = m.group(1)
            if any(
                frag in tok
                for frag in ("_KEY", "_SECRET", "_TOKEN", "_URL", "_ID", "_PASS", "_DSN", "_HASH", "_EMAIL", "_PORT")
            ):
                found.add(tok)

    return sorted(found)


def discover_infisical_key_names(
    estate_root: Path,
    *,
    project_id: str = DEFAULT_INFISICAL_PROJECT_ID,
    infisical_env: str = "beta",
) -> list[str]:
    """Return ONLY the key names injected by Infisical (diffed against host env key names). Never reads values."""
    host_keys = set(os.environ.keys())
    cwd = estate_root / "w0m-web" if (estate_root / "w0m-web").is_dir() else estate_root
    out = subprocess.check_output(
        [
            "infisical",
            "run",
            f"--projectId={project_id}",
            f"--env={infisical_env}",
            "--silent",
            "--",
            sys.executable,
            "-c",
            "import json, os; print(json.dumps(sorted(os.environ.keys())))",
        ],
        cwd=str(cwd),
        text=True,
    )
    injected = set(json.loads(out))
    return sorted(injected - host_keys - {"INFISICAL_SIGN_IN_AUTOMATIC"})


def audit_env_keys(
    estate_root: Path,
    keys: Iterable[str],
    *,
    repos: Sequence[str] = DEFAULT_ESTATE_REPOS,
) -> dict[str, Any]:
    """Classify each key in `keys` against executable code across `estate_root`."""
    unique_keys = sorted({k.strip() for k in keys if k and k.strip()})
    inverted = index_estate_env_tokens(
        estate_root,
        repos=repos,
        candidate_set=frozenset(unique_keys),
    )

    rows: list[dict[str, Any]] = []
    for key in unique_keys:
        buckets = inverted.get(
            key,
            {
                "prod_readers": [],
                "sync_or_cli": [],
                "tests_only": [],
                "config_decl_only": [],
            },
        )
        prod_readers = sorted(set(buckets["prod_readers"]))
        sync_or_cli = sorted(set(buckets["sync_or_cli"]))
        tests_only = sorted(set(buckets["tests_only"]))
        config_decl_only = sorted(set(buckets["config_decl_only"]))

        if prod_readers:
            status = "ACTIVE_RUNTIME"
        elif sync_or_cli:
            status = "ACTIVE_CLI_OR_SYNC"
        elif tests_only:
            status = "TESTS_E2E_ONLY"
        else:
            status = "DEAD_UNUSED"

        rows.append(
            {
                "key": key,
                "status": status,
                "leaked_in_git_history": key in HISTORICAL_DIGEST_LEAK_KEYS,
                "prod_readers": prod_readers,
                "sync_or_cli": sync_or_cli,
                "tests_only": tests_only,
                "config_decl_only": config_decl_only,
            }
        )

    counts = Counter(r["status"] for r in rows)
    dead_historical = [r["key"] for r in rows if r["leaked_in_git_history"] and r["status"] == "DEAD_UNUSED"]
    return {
        "total_keys": len(rows),
        "counts": {
            "ACTIVE_RUNTIME": counts.get("ACTIVE_RUNTIME", 0),
            "ACTIVE_CLI_OR_SYNC": counts.get("ACTIVE_CLI_OR_SYNC", 0),
            "TESTS_E2E_ONLY": counts.get("TESTS_E2E_ONLY", 0),
            "DEAD_UNUSED": counts.get("DEAD_UNUSED", 0),
        },
        "dead_historical_leak_keys": dead_historical,
        "keys": rows,
    }


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1], help="Estate root path")
    ap.add_argument("--infisical", action="store_true", help="Audit live Infisical key names (key names only)")
    ap.add_argument("--infisical-env", default="beta", help="Infisical environment slug (default: beta)")
    ap.add_argument("--project-id", default=DEFAULT_INFISICAL_PROJECT_ID, help="Infisical project ID")
    ap.add_argument("--key", action="append", default=[], help="Audit specific key name(s) (repeatable)")
    ap.add_argument("--json", action="store_true", help="Emit JSON report")
    return ap


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root.resolve()

    if args.key:
        keys = list(args.key)
        source = "explicit-cli"
    elif args.infisical:
        keys = discover_infisical_key_names(root, project_id=args.project_id, infisical_env=args.infisical_env)
        source = f"infisical:{args.infisical_env}"
    else:
        keys = discover_static_candidate_keys(root)
        source = "static-manifests"

    report = audit_env_keys(root, keys)
    report["source"] = source

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    c = report["counts"]
    print(
        f"[PASS] env-usage-audit ({source}): audited {report['total_keys']} key(s) — "
        f"ACTIVE_RUNTIME={c['ACTIVE_RUNTIME']}, ACTIVE_CLI_OR_SYNC={c['ACTIVE_CLI_OR_SYNC']}, "
        f"TESTS_E2E_ONLY={c['TESTS_E2E_ONLY']}, DEAD_UNUSED={c['DEAD_UNUSED']}"
    )
    if report["dead_historical_leak_keys"]:
        print(
            f"[PASS] env-usage-audit: {len(report['dead_historical_leak_keys'])} historical-leak key(s) have "
            f"0 code readers (delete from Infisical instead of rotating): "
            f"{', '.join(report['dead_historical_leak_keys'])}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
