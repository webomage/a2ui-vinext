#!/usr/bin/env python3
"""Code annotations & debt markers doctor (T342).

Audits and reports code annotations and suppressions across all 7 estate repositories:
  · overrides:     @ts-ignore, @ts-expect-error, @ts-nocheck, as any, type: ignore
  · hacks:         HACK, WORKAROUND, XXX, TEMP, TEMPORARY
  · ignores:       eslint-disable, prettier-ignore, biome-ignore, noqa, type: ignore, golangci-lint
  · todos:         TODO, FIXME
  · hotfixes:      HOTFIX, QUICKFIX, PATCH
  · lintexcludes:  lintexclude, skipcq, linter:disable

Driven by `project/policies/hygiene-policy.json`. Supports:
    python3 scripts/annotations_doctor.py                 # Summary table & report (exit 0)
    python3 scripts/annotations_doctor.py --json          # Machine-readable output
    python3 scripts/annotations_doctor.py --repo web      # Scoped to a specific repo
    python3 scripts/annotations_doctor.py --category hacks # Scoped to a specific category
    python3 scripts/annotations_doctor.py --enforce       # Fails closed on any findings

Empty-Input-Set Rule:
    Fails closed (exit 1) if candidate file set is empty across declared repos.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("W0M_HYGIENE_ROOT") or Path(__file__).resolve().parents[1])
CANONICAL = ROOT / "w0m-web"
POLICY_PATH = ROOT / "project" / "policies" / "hygiene-policy.json"

SKIP_DIRS = frozenset({
    "node_modules", ".git", "dist", "build", ".venv", "target", ".next",
    ".astro", ".svelte-kit", ".quartz-engine", "graphify-out", ".turbo",
    ".superpowers", "_ext", "_in", "_arch", "ext", "vendor"
})

CODE_EXTS = frozenset({
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".svelte", ".astro",
    ".py", ".rs", ".sh", ".bash", ".zsh", ".sql", ".yaml", ".yml",
    ".jsonc", ".toml", ".html", ".css"
})

PATTERNS = {
    "overrides": re.compile(r"(@ts-ignore|@ts-expect-error|@ts-nocheck|\btype:\s*ignore\b|\bas\s+any\b)"),
    "hacks": re.compile(r"\b(HACK|WORKAROUND|XXX|TEMP|TEMPORARY)\b"),
    "ignores": re.compile(
        r"(eslint-disable(?:-next-line|-line)?|prettier-ignore|biome-ignore|stylelint-disable|"
        r"#\s*noqa|ruff:\s*noqa|golangci-lint:ignore|clippy::allow)"
    ),
    "todos": re.compile(r"\b(TODO|FIXME)\b"),
    "hotfixes": re.compile(r"\b(HOTFIX|QUICKFIX|PATCH)\b"),
    "lintexcludes": re.compile(r"\b(lintexclude|skipcq|linter:disable)\b"),
}


def load_policy() -> dict:
    if not POLICY_PATH.is_file():
        return {"repos": [{"path": "w0m-web"}]}
    try:
        return json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        sys.exit(f"Error reading {POLICY_PATH}: {exc}")


def get_repo_files(repo_path: Path) -> list[Path]:
    """Retrieve code files in repo, preferring git ls-files if available."""
    if not repo_path.is_dir():
        return []

    # Attempt git ls-files
    res = subprocess.run(
        ["git", "ls-files"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=False
    )
    if res.returncode == 0 and res.stdout.strip():
        files: list[Path] = []
        for line in res.stdout.splitlines():
            parts = line.split("/")
            if any(part in SKIP_DIRS for part in parts):
                continue
            p = repo_path / line
            if p.suffix in CODE_EXTS and p.is_file():
                files.append(p)
        return files

    # Fallback to filesystem walk
    files = []
    for p in repo_path.rglob("*"):
        if not p.is_file():
            continue
        rel_parts = p.relative_to(repo_path).parts
        if any(part in SKIP_DIRS for part in rel_parts):
            continue
        if p.suffix in CODE_EXTS:
            files.append(p)
    return files


def audit_annotations(
    root: Path | None = None,
    policy: dict | None = None,
    target_repo: str | None = None,
    target_category: str | None = None
) -> dict[str, Any]:
    """Run full code annotations audit across declared repos."""
    root_path = root or ROOT
    pol = policy or load_policy()
    repos_spec = pol.get("repos", [])

    findings_list: list[dict[str, Any]] = []
    by_repo_dict: dict[str, dict[str, Any]] = {}

    category_keys = [target_category] if target_category and target_category in PATTERNS else list(PATTERNS.keys())
    total_files_scanned = 0

    for entry in repos_spec:
        rel_path = entry.get("path", "")
        repo_name = rel_path.split("/")[-1] if "/" in rel_path else rel_path
        if target_repo and target_repo not in (rel_path, repo_name):
            continue

        repo_dir = root_path / rel_path
        if not repo_dir.is_dir():
            continue

        files = get_repo_files(repo_dir)
        total_files_scanned += len(files)

        repo_counts = {cat: 0 for cat in category_keys}
        repo_findings = []

        for f in files:
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            lines = content.splitlines()
            rel_file = str(f.relative_to(root_path))

            for idx, line in enumerate(lines, 1):
                # Skip massive minified lines or data URIs
                if len(line) > 1000:
                    continue
                for cat in category_keys:
                    rx = PATTERNS[cat]
                    m = rx.search(line)
                    if m:
                        repo_counts[cat] += 1
                        finding = {
                            "repo": rel_path,
                            "file": rel_file,
                            "line": idx,
                            "category": cat,
                            "match": m.group(0),
                            "snippet": line.strip()[:140]
                        }
                        repo_findings.append(finding)
                        findings_list.append(finding)

        by_repo_dict[rel_path] = {
            "files_scanned": len(files),
            "counts": repo_counts,
            "total": sum(repo_counts.values())
        }

    total_matches = sum(
        r["total"] for r in by_repo_dict.values()
    )

    summary_counts = {cat: 0 for cat in category_keys}
    for r in by_repo_dict.values():
        for cat, cnt in r["counts"].items():
            summary_counts[cat] += cnt

    return {
        "summary": summary_counts,
        "by_repo": by_repo_dict,
        "total_files": total_files_scanned,
        "total_matches": total_matches,
        "findings": findings_list,
    }


def print_report(results: dict[str, Any], verbose: bool = False) -> None:
    print("\n▶ code annotations doctor — 7 estate repos")
    print(f"  scanned {results['total_files']} files across {len(results['by_repo'])} repositories")
    print(f"  total markers found: {results['total_matches']}\n")

    # Header
    cols = ["Repo", "Files", "Overrides", "Hacks", "Ignores", "Todos", "Hotfixes", "Lintexcl", "Total"]
    fmt = "{:<16} {:>6} {:>10} {:>7} {:>9} {:>7} {:>9} {:>9} {:>8}"
    print(fmt.format(*cols))
    print("-" * 88)

    for repo, data in sorted(results["by_repo"].items()):
        c = data["counts"]
        print(fmt.format(
            repo[:16],
            data["files_scanned"],
            c.get("overrides", 0),
            c.get("hacks", 0),
            c.get("ignores", 0),
            c.get("todos", 0),
            c.get("hotfixes", 0),
            c.get("lintexcludes", 0),
            data["total"]
        ))

    print("-" * 88)
    s = results["summary"]
    print(fmt.format(
        "TOTAL",
        results["total_files"],
        s.get("overrides", 0),
        s.get("hacks", 0),
        s.get("ignores", 0),
        s.get("todos", 0),
        s.get("hotfixes", 0),
        s.get("lintexcludes", 0),
        results["total_matches"]
    ))
    print()

    if verbose and results["findings"]:
        print("── sample findings (first 20) ──")
        for item in results["findings"][:20]:
            print(f"  [{item['category']}] {item['file']}:{item['line']} — {item['match']}")
            print(f"    {item['snippet']}")
        print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit overrides, hacks, ignores, todos, hotfixes across the estate.")
    parser.add_argument("--enforce", action="store_true", help="Fail with exit 1 if any annotations exist.")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format.")
    parser.add_argument("--repo", type=str, help="Scope check to a specific repo name.")
    parser.add_argument("--category", type=str, choices=list(PATTERNS.keys()), help="Scope check to a category.")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print sample findings.")
    args = parser.parse_args()

    results = audit_annotations(
        root=ROOT,
        target_repo=args.repo,
        target_category=args.category
    )

    # Empty Input Set Rule
    if results["total_files"] == 0:
        print("❌ EMPTY CORPUS: 0 files were inspected. Refusing vacuous pass.", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(results, indent=2))
        if args.enforce and results["total_matches"] > 0:
            print(f"❌ ENFORCE: {results['total_matches']} annotations found.", file=sys.stderr)
            return 1
        return 0

    print_report(results, verbose=args.verbose)

    if args.enforce and results["total_matches"] > 0:
        print(f"❌ ENFORCE: {results['total_matches']} annotations found.", file=sys.stderr)
        return 1

    print("✅ code annotations doctor passed (advisory report).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
