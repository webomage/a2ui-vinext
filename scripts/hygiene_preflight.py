#!/usr/bin/env python3
"""Repo-hygiene preflight measurement (T135, tasks.md section 0).

Answers, for the whole w0m estate, the questions that have now been got wrong
three times by measuring at the wrong directory level:

  * which paths are actually git repos, and where is each repo's toplevel
  * where does each repo's hooks directory REALLY live (core.hooksPath)
  * where is every `package.json`, and what does each declare for
    `private` / `license` / `name`
  * which human-facing files exist per repo

It is deliberately a measurement tool, not a gate: it prints and exits 0. The
gates that consume these facts live behind `just` recipes. Re-run this rather
than trusting a recorded count -- that is the entire lesson of section 0.

Usage:
    python3 scripts/hygiene_preflight.py            # human summary
    python3 scripts/hygiene_preflight.py --json     # machine readable
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

# The estate root, relative to this file: scripts/ -> ..
ROOT = Path(__file__).resolve().parents[1]

# Candidate repo paths. `w0m-mlx` (outer) is listed ON PURPOSE: it is NOT a git
# repo but a workspace of upstream clones, and an earlier matrix reported
# "w0m-mlx has zero hooks" by measuring it. Keeping it here makes that visible
# instead of assumed.
CANDIDATES = (
    "w0m-web",
    "w0m-api",
    "w0m-cf",
    "w0m-skills",
    "w0m-ext",
    "w0m-sec",
    "w0m-mlx",
    "w0m-mlx/w0m-mlx",
)

SKIP_DIRS = frozenset(
    {"node_modules", ".git", "dist", "build", ".venv", "target", ".next", ".astro"}
)

HUMAN_FACING = (
    "README.md",
    "LICENSE",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
)

# Vendored third-party manifests: first-party hygiene rules (private: true,
# license: UNLICENSED) must NEVER be written into these -- doing so relicenses
# code we do not own. Matched as a path substring against the repo-relative path.
VENDORED_MANIFEST_MARKERS = ("/vendor/", "extension/package/")


def git(path: Path, *args: str) -> str | None:
    """Run git in `path`; return stripped stdout, or None on non-zero exit."""
    proc = subprocess.run(
        ["git", "-C", str(path), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout.strip() if proc.returncode == 0 else None


def is_vendored(rel_path: str) -> bool:
    return any(marker in rel_path for marker in VENDORED_MANIFEST_MARKERS)


def find_manifests(repo: Path) -> list[dict]:
    """Every TRACKED package.json in the repo, excluding build/dependency output.

    ⚠️ Tracked, not just present. The first version of this function globbed the filesystem and
    reported 19 manifests; one of them (`w0m-ext/extension-ff/package.json`) is GITIGNORED, so
    the real number is 18. This function was written to stop exactly that class of error and
    then committed it — measuring the filesystem when the question was about the repo.
    """
    tracked = {
        line for line in (git(repo, "ls-files") or "").splitlines()
        if line.endswith("package.json")
    }
    found: list[dict] = []
    for manifest in sorted(repo.rglob("package.json")):
        rel = manifest.relative_to(repo)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if str(rel) not in tracked:
            continue
        entry: dict = {"path": str(rel), "vendored": is_vendored(str(rel))}
        try:
            data = json.loads(manifest.read_text())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            # UnicodeDecodeError is NOT an OSError -- it must be caught by name.
            entry["error"] = f"{type(exc).__name__}: {exc}"
            found.append(entry)
            continue
        entry["name"] = data.get("name")
        entry["private"] = data.get("private")
        entry["license"] = data.get("license")
        found.append(entry)
    return found


def hooks_state(repo: Path) -> dict:
    """Resolve where hooks REALLY are. A .pre-commit-config.yaml is not a gate."""
    configured = git(repo, "config", "--get", "core.hooksPath")
    effective = repo / (configured or ".git/hooks")
    installed: list[str] = []
    if effective.is_dir():
        installed = sorted(
            h.name
            for h in effective.iterdir()
            if h.is_file() and not h.name.endswith(".sample")
        )
    return {
        "core_hooks_path": configured,
        "effective_dir": str(effective.relative_to(repo)) if effective.exists() else None,
        "installed_hooks": installed,
        "has_precommit_config": (repo / ".pre-commit-config.yaml").exists(),
    }


def measure() -> dict:
    report: dict = {"root": str(ROOT), "repos": {}, "absent": [], "not_a_repo": []}

    for name in CANDIDATES:
        path = ROOT / name
        if not path.is_dir():
            report["absent"].append(name)
            continue

        toplevel = git(path, "rev-parse", "--show-toplevel")
        # A path inside another repo reports THAT repo's toplevel -- only an
        # exact match means this path is its own repo.
        if toplevel != str(path):
            report["not_a_repo"].append({"path": name, "reports_toplevel": toplevel})
            continue

        report["repos"][name] = {
            "branch": git(path, "rev-parse", "--abbrev-ref", "HEAD"),
            "head": git(path, "rev-parse", "--short", "HEAD"),
            "tracked_files": len((git(path, "ls-files") or "").splitlines()),
            "hooks": hooks_state(path),
            "manifests": find_manifests(path),
            "has_cargo_toml": (path / "Cargo.toml").exists(),
            "has_pyproject": (path / "pyproject.toml").exists(),
            "has_justfile": (path / "justfile").exists(),
            "has_infisical": (path / ".infisical.yaml").exists() or (path / ".infisical.json").exists(),
            "human_facing": {f: (path / f).exists() for f in HUMAN_FACING},
        }

    return report


def summarise(report: dict) -> None:
    repos = report["repos"]
    print(f"estate root: {report['root']}")
    print(f"git repos:   {len(repos)}")
    for entry in report["not_a_repo"]:
        print(f"  NOT a repo:  {entry['path']}  (reports {entry['reports_toplevel']})")
    if report["absent"]:
        print(f"  absent:      {', '.join(report['absent'])}")

    print("\n-- hooks (a .pre-commit-config.yaml is NOT a gate) --")
    for name, r in repos.items():
        h = r["hooks"]
        redirect = h["core_hooks_path"] or "(none -> .git/hooks)"
        print(f"  {name:<20} hooksPath={redirect:<12} installed={len(h['installed_hooks'])}")

    print("\n-- human-facing files --")
    for f in HUMAN_FACING:
        have = [n for n, r in repos.items() if r["human_facing"][f]]
        missing = [n for n, r in repos.items() if not r["human_facing"][f]]
        print(f"  {f:<20} {len(have)}/{len(repos)}" + (f"   missing: {', '.join(missing)}" if missing else ""))

    all_manifests = [
        (name, m) for name, r in repos.items() for m in r["manifests"]
    ]
    first_party = [(n, m) for n, m in all_manifests if not m["vendored"]]
    vendored = [(n, m) for n, m in all_manifests if m["vendored"]]

    print(f"\n-- manifests: {len(all_manifests)} total "
          f"({len(first_party)} first-party, {len(vendored)} vendored) --")
    print(f"  {'manifest':<52} {'name':<26} {'private':<8} license")
    for name, m in all_manifests:
        flag = "  [VENDORED - do not rewrite]" if m["vendored"] else ""
        full = f"{name}/{m['path']}"
        print(f"  {full:<52} {str(m.get('name')):<26} "
              f"{str(m.get('private')):<8} {m.get('license') or '-'}{flag}")

    no_private = [f"{n}/{m['path']}" for n, m in first_party if m.get("private") is not True]
    no_license = [f"{n}/{m['path']}" for n, m in first_party if not m.get("license")]
    print(f"\n  first-party missing private:true : {len(no_private)}/{len(first_party)}")
    print(f"  first-party missing license      : {len(no_license)}/{len(first_party)}")
    if vendored:
        print("  vendored (EXCLUDED from both sweeps):")
        for n, m in vendored:
            print(f"    {n}/{m['path']}  license={m.get('license') or 'NONE'}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit raw JSON")
    args = parser.parse_args()

    report = measure()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        summarise(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
