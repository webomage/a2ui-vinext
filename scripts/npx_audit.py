#!/usr/bin/env python3
"""npx_audit.py — Audit tracked files for unauthorized runnable npx invocations (T398).

Enforces stack policy (project/stacks-policy.json, T130) by ensuring no runnable
scripts, package manifests, or recipes execute `npx` instead of native `pnpm exec`
or `pnpm dlx`.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # /Users/proto/Projects/@self/@wom
REPOS = ["wom7web", "wom7api", "wom7skills", "wom7ext", "wom7sec", "wom7func"]

# Paths that are allowed to mention npx in documentation, rules, tests, or legacy definitions
ALLOWLIST_SUBSTRINGS = [
    "scripts/discovery.py",
    "scripts/tests/test_discovery.py",
    "scripts/tests/test_npx_audit.py",
    "scripts/npx_audit.py",
    "project/scripts/quartz_patch_ofm.py",
    "openspec/",
    "docs/",
    "README",
    "AGENTS.md",
    "CLAUDE.md",
    "CONTRIBUTING.md",
    "skills.schema.json",
    "blueprints.json",
    "blueprint",
    ".cache/",
    ".serena/",
    "archive/",
]


def is_allowlisted(path_str: str) -> bool:
    for sub in ALLOWLIST_SUBSTRINGS:
        if sub in path_str:
            return True
    return False


def check_package_manifest(pkg_path: Path) -> list[str]:
    findings = []
    try:
        data = json.loads(pkg_path.read_text(encoding="utf-8"))
        scripts = data.get("scripts", {})
        for name, cmd in scripts.items():
            if re.search(r"(?:^|[;&|\s])npx\s+", cmd):
                findings.append(f"{pkg_path}: script '{name}' invokes npx: {cmd}")
    except Exception:
        pass
    return findings


def check_file_lines(file_path: Path) -> list[str]:
    findings = []
    try:
        lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
        for i, line in enumerate(lines, start=1):
            stripped = line.strip()
            # Strip inline comments
            if "//" in stripped:
                stripped = stripped.split("//", 1)[0].strip()
            if "#" in stripped and not stripped.startswith("#!"):
                stripped = stripped.split("#", 1)[0].strip()

            if (
                stripped.startswith("#")
                or stripped.startswith("//")
                or stripped.startswith("*")
                or stripped.startswith('echo "')
                or stripped.startswith("@echo \"")
                or stripped.startswith("print(")
                or stripped.startswith("console.log(")
            ):
                continue
            if re.search(r"(?:^|[;&|\s])npx\s+", stripped):
                findings.append(f"{file_path}:{i}: {stripped}")
    except Exception:
        pass
    return findings


def get_tracked_files(repo_path: Path) -> list[Path]:
    try:
        res = subprocess.run(
            ["git", "ls-files"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        return [repo_path / line.strip() for line in res.stdout.splitlines() if line.strip()]
    except Exception:
        return []


def audit_estate(root: Path = ROOT) -> int:
    print("▶ npx-audit: scanning tracked automation and manifests...")
    findings: list[str] = []

    target_repos = [root / r for r in REPOS if (root / r).is_dir()]
    if not target_repos:
        target_repos = [root]

    for repo in target_repos:
        for f in get_tracked_files(repo):
            rel = str(f.relative_to(root))
            if is_allowlisted(rel):
                continue

            if f.name == "package.json":
                findings.extend(check_package_manifest(f))
            elif f.suffix in (".py", ".ts", ".js", ".mjs", ".sh") or f.name == "justfile":
                findings.extend(check_file_lines(f))

    if findings:
        print(f"❌ Found {len(findings)} unauthorized runnable npx invocation(s):", file=sys.stderr)
        for finding in findings:
            print(f"  · {finding}", file=sys.stderr)
        return 1

    print("✅ Clean: zero unauthorized runnable npx invocations found across estate.")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Audit tracked files for unauthorized runnable npx invocations.")
    args = parser.parse_args()
    sys.exit(audit_estate())


if __name__ == "__main__":
    main()
