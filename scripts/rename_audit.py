#!/usr/bin/env python3
"""rename_audit — Multi-surface verification tool for renames, refactors, and decommissions.

Tracked by T409. Audits 5 distinct surfaces across the estate:
1. code_and_templates (TS/JS/Py/Rust/Go + .astro, .svelte, .vue)
2. governance_and_skills (.agents/skills/, AGENTS.md, CLAUDE.md, README.md, TASKS.md)
3. configs_and_tooling (justfile, .gitignore, package.json, .w0m/sdlc.json, policy JSONs)
4. build_and_artifacts (out/, build/, makefiles, native bindings with hardcoded old paths)
5. symlinks_and_paths (directories or symlinks named with old term)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

SURFACES = (
    "code_and_templates",
    "governance_and_skills",
    "configs_and_tooling",
    "build_and_artifacts",
    "symlinks_and_paths",
)

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".svgz", ".pdf",
    ".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".pyc", ".pyo",
    ".pyd", ".so", ".dylib", ".dll", ".exe", ".bin", ".wasm", ".woff",
    ".woff2", ".ttf", ".eot", ".otf", ".mp3", ".mp4", ".mov", ".wav",
    ".avi", ".webm", ".dmg", ".iso", ".pkg", ".deb", ".rpm", ".parquet",
    ".arrow", ".avro", ".db", ".sqlite", ".sqlite3",
}

SKIP_DIRS = {
    ".git",
    "node_modules",
    "target",
    ".serena",
    ".pytest_cache",
    ".cache",
    "graphify-out",
    ".smart-env",
    ".quartz-engine",
    ".astro",
    ".headroom",
    ".playwright-mcp",
    "__pycache__",
    "reports",
    "worktrees",
    ".gauge",
    ".ruff_cache",
    ".turbo",
    ".next",
    ".nuxt",
    ".output",
    "dist",
    "venv",
    ".venv",
}

DEFAULT_EXEMPT_SUBSTRINGS = [
    "DECOMMISSIONED.md",
    "project/state-archive",
    "project/tickets/archive",
    "_t99_arc",
    "_in/",
    "_arch/",
    "docs/reports/",
    "docs/decisions/",
    "docs/DECISIONS.md",
    "docs/proposals/",
    "docs/STATUS-DASHBOARD.html",
    "docs/manuals/TOOLING-AND-FEATURES-OVERVIEW.md",
    "openspec/changes/archive",
    "openspec/changes/2026-09-20-rename-and-decommission-tooling-suite",
    "scripts/w0m_prs.py",
    "scripts/tests/test_w0m_prs.py",
    "scripts/rename_audit.py",
    "scripts/tests/test_rename_audit.py",
    ".tasks/",
    "project/tickets.json",
    "project/policies/emoji-policy.json",
    "RESEARCH-ZEROCLAW-ORCA.md",
    "w0m-pr/README.md",
    "TASKS.md",
    "ROADMAP.md",
    "STATE.md",
]


def is_binary_file(file_path: Path) -> bool:
    if file_path.suffix.lower() in BINARY_EXTENSIONS:
        return True
    if not file_path.is_file():
        return False
    try:
        with open(file_path, "rb") as f:
            chunk = f.read(1024)
            return b"\x00" in chunk
    except Exception:
        return False


def classify_file(rel_path: Path) -> str:
    path_str = str(rel_path).replace("\\", "/")
    parts = path_str.split("/")
    filename = parts[-1].lower()

    # 1. Build and artifacts
    if any(p in ("out", "build", "dist", ".pnpm") for p in parts[:-1]):
        return "build_and_artifacts"
    if filename in ("makefile",) or filename.endswith((".mk", ".target.mk")):
        return "build_and_artifacts"

    # 2. Configs & Tooling
    if filename in (
        ".gitignore",
        "package.json",
        "justfile",
        "pnpm-lock.yaml",
        "tsconfig.json",
        "wrangler.jsonc",
        "sdlc.json",
    ) or filename.endswith(("-policy.json", "-baseline.json", ".toml", ".yaml", ".yml", ".jsonc")):
        return "configs_and_tooling"
    if any(p in (".w0m", "project") for p in parts[:-1]) and filename.endswith(".json"):
        return "configs_and_tooling"

    # 3. Governance & Skills
    if any(p in (".agents", ".claude", "skills") for p in parts):
        return "governance_and_skills"
    if filename.endswith(".md"):
        return "governance_and_skills"

    # 4. Code & Templates (default for known extensions)
    if filename.endswith((".astro", ".svelte", ".vue", ".html", ".ts", ".tsx", ".js", ".mjs", ".cjs", ".py", ".rs", ".go", ".sh")):
        return "code_and_templates"

    return "configs_and_tooling"


def run_audit(
    old_term: str,
    new_term: Optional[str] = None,
    root: Optional[Path] = None,
    exempt_paths: Optional[List[str]] = None,
) -> Dict[str, Any]:
    if root is None:
        script_dir = Path(__file__).resolve().parent
        root = script_dir.parent  # @wom umbrella root

    all_exempt = list(DEFAULT_EXEMPT_SUBSTRINGS)
    if exempt_paths:
        all_exempt.extend(exempt_paths)

    surfaces_map: Dict[str, List[Dict[str, Any]]] = {s: [] for s in SURFACES}
    exempted_hits: List[Dict[str, Any]] = []

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        # Prune skipped directories
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".git")]

        curr_dir = Path(dirpath)
        try:
            rel_dir = curr_dir.relative_to(root)
        except ValueError:
            rel_dir = curr_dir

        # Check directory names & symlinks
        for d in dirnames:
            if old_term in d:
                d_rel = (rel_dir / d) if str(rel_dir) != "." else Path(d)
                surfaces_map["symlinks_and_paths"].append({
                    "path": str(d_rel),
                    "type": "directory",
                    "preview": f"Directory name contains '{old_term}'",
                })

        for f in filenames:
            file_path = curr_dir / f
            try:
                rel_file = file_path.relative_to(root)
            except ValueError:
                rel_file = file_path
            rel_file_str = str(rel_file).replace("\\", "/")

            if file_path.is_symlink():
                link_target = str(os.readlink(file_path))
                if old_term in link_target or old_term in f:
                    surfaces_map["symlinks_and_paths"].append({
                        "path": rel_file_str,
                        "type": "symlink",
                        "preview": f"Symlink target '{link_target}' contains '{old_term}'",
                    })
                continue

            # Check file content
            is_exempt = any(ex in rel_file_str for ex in all_exempt)

            if is_binary_file(file_path):
                if old_term in f:
                    hit_bin: Dict[str, Any] = {
                        "path": rel_file_str,
                        "type": "binary_file",
                        "preview": f"Binary filename contains '{old_term}'",
                    }
                    if is_exempt:
                        exempted_hits.append(hit_bin)
                    else:
                        surf = "symlinks_and_paths"
                        hit_bin["surface"] = surf
                        surfaces_map[surf].append(hit_bin)
                continue

            if old_term in f:
                hit_fn: Dict[str, Any] = {
                    "path": rel_file_str,
                    "type": "file_path",
                    "preview": f"Filename contains '{old_term}'",
                }
                if is_exempt:
                    exempted_hits.append(hit_fn)
                else:
                    surf = "symlinks_and_paths"
                    hit_fn["surface"] = surf
                    surfaces_map[surf].append(hit_fn)

            try:
                # Read text file line by line
                with open(file_path, "r", encoding="utf-8", errors="ignore") as fp:
                    for line_no, line in enumerate(fp, start=1):
                        if old_term in line:
                            preview = line.strip()
                            if len(preview) > 120:
                                preview = preview[:117] + "..."
                            hit_record: Dict[str, Any] = {
                                "path": rel_file_str,
                                "line": line_no,
                                "preview": preview,
                            }
                            if is_exempt:
                                exempted_hits.append(hit_record)
                            else:
                                surf = classify_file(rel_file)
                                hit_record["surface"] = surf
                                surfaces_map[surf].append(hit_record)
            except Exception:
                pass

    total_violations = sum(len(v) for v in surfaces_map.values())
    total_hits = total_violations + len(exempted_hits)

    return {
        "old_term": old_term,
        "new_term": new_term or "",
        "root": str(root),
        "surfaces": surfaces_map,
        "total_violations": total_violations,
        "total_hits": total_hits,
        "exempted": exempted_hits,
    }


def print_report(res: Dict[str, Any], verbose: bool = False) -> None:
    old = res["old_term"]
    new = res.get("new_term")
    title = f"Rename & Decommission Audit: '{old}'" + (f" -> '{new}'" if new else "")
    print(title)
    print("=" * len(title))

    total_viols = res["total_violations"]
    for surf, items in res["surfaces"].items():
        status_glyph = "✅" if len(items) == 0 else "🔴"
        print(f"\n{status_glyph} Surface: {surf} ({len(items)} occurrence(s))")
        if items:
            for it in items[:15]:
                if "line" in it:
                    print(f"   · {it['path']}:{it['line']} -> {it['preview']}")
                else:
                    print(f"   · {it['path']} -> {it['preview']}")
            if len(items) > 15:
                print(f"   ... and {len(items) - 15} more item(s)")

    if res.get("exempted"):
        print(f"\n⚪ Allowed / Exempted: {len(res['exempted'])} occurrence(s)")
        if verbose:
            for it in res["exempted"]:
                print(f"   · {it['path']}:{it.get('line', '-')} (exempted)")

    print("\n" + "─" * 60)
    if total_viols == 0:
        print("✅ Clean: zero lingering references found across all surfaces.")
    else:
        print(f"🔴 Drift detected: {total_viols} lingering occurrence(s) across {sum(1 for s in res['surfaces'].values() if s)} surface(s).")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit lingering references to old names/paths across all estate surfaces.")
    parser.add_argument("old", help="Old identifier, namespace, or directory name to audit for absence")
    parser.add_argument("new", nargs="?", default=None, help="Target new replacement name (optional, for contextual reporting)")
    parser.add_argument("--root", default=None, help="Root path to audit (defaults to workspace umbrella)")
    parser.add_argument("--strict", action="store_true", help="Exit with code 1 if any unexempted occurrences are found")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON format")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output including exempted lines")
    parser.add_argument("--exempt", action="append", default=[], help="Additional path substrings to exempt")

    args = parser.parse_args()

    root_path = Path(args.root) if args.root else None
    res = run_audit(args.old, args.new, root=root_path, exempt_paths=args.exempt)

    if args.json:
        print(json.dumps(res, indent=2))
    else:
        print_report(res, verbose=args.verbose)

    if args.strict and res["total_violations"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
