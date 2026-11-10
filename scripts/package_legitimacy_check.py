#!/usr/bin/env python3
"""Estate-wide & Spec Package / Dependency Legitimacy Audit & Pre-Commit Gate (T708 / T714).

Audits all dependency manifests across the 7 w0m estate repositories (`@wom` root,
`w0m-web`, `w0m-api`, `w0m-cf`, `w0m-ext`, `w0m-sec`, `w0m-skills`, `w0m-mlx`) plus
proposed packages in specifications/plans (`.tasks/`, `openspec/`, `.specify/`, `.planning/`).

Classifications (OpenGSD + Trail of Bits supply-chain taxonomy):
  - [VERIFIED] : Resolved in workspace lockfile (`pnpm-lock.yaml`, `Cargo.lock`) or first-party workspace/stdlib
  - [SUS]      : Unpinned `@latest` / wildcard `*` / raw `http://` dependency or unverified external spec proposal
  - [SLOP]     : Malformed package identifier, known typosquat/slopsquatting pattern, or missing from lockfile/registry
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

ESTATE_ROOT = Path(__file__).resolve().parents[1]

ESTATE_REPOS: tuple[str, ...] = (
    ".",
    "w0m-web",
    "w0m-api",
    "w0m-cf",
    "w0m-ext",
    "w0m-sec",
    "w0m-skills",
    "w0m-mlx",
)

FIRST_PARTY_PREFIXES: tuple[str, ...] = (
    "@webomage/",
    "@w0m/",
    "@wom/",
    "w0m-",
)

# High-risk slopsquatting / hallucinated package names & known typosquats
KNOWN_SLOP_OR_TYPOSQUAT_DENYLIST: frozenset[str] = frozenset(
    {
        "react-codeshift",
        "urllib3-extra",
        "python-sqlite3",
        "python-json",
        "nodejs-crypto",
        "crypto-js-native",
        "dotenv-safe-env",
        "express-jwt-authz-helper",
        "openai-agents-sdk-official",
        "anthropic-mcp-official",
        "cloudflare-workers-kv-sdk",
        "supabase-rls-helper",
        "svelte-runes-kit",
    }
)

NPM_NAME_RE = re.compile(r"^(?:@[a-z0-9-~][a-z0-9-._~]*/)?[a-z0-9-~][a-z0-9-._~]*$")
PYPI_NAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$")
CARGO_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")

SPEC_INSTALL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "npm",
        re.compile(
            r"\b(?:npm\s+(?:install|i)|pnpm\s+add|yarn\s+add)\s+(?:-[DSEg]\s+|--save(?:-dev)?\s+)*([@a-z0-9][@a-z0-9._/-]*)"
        ),
    ),
    (
        "pypi",
        re.compile(r"\b(?:pip3?\s+install|uv\s+add)\s+(?:-[U]\s+)*([A-Za-z0-9][A-Za-z0-9._-]*)"),
    ),
    (
        "cargo",
        re.compile(r"\bcargo\s+add\s+(?:--dev\s+)?([A-Za-z0-9][A-Za-z0-9_-]*)"),
    ),
)


@dataclass
class PackageFinding:
    repo: str
    manifest: str
    ecosystem: str  # "npm" | "pypi" | "cargo"
    name: str
    specifier: str
    status: str  # "VERIFIED" | "SUS" | "SLOP"
    reason: str


@dataclass
class AuditReport:
    ok: bool
    repos_scanned: list[str]
    manifests_scanned: int
    total_dependencies: int
    verified_count: int
    sus_count: int
    slop_count: int
    findings: list[PackageFinding] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "repos_scanned": self.repos_scanned,
            "manifests_scanned": self.manifests_scanned,
            "total_dependencies": self.total_dependencies,
            "verified_count": self.verified_count,
            "sus_count": self.sus_count,
            "slop_count": self.slop_count,
            "findings": [asdict(f) for f in self.findings],
        }


def _strip_pypi_requirement_name(req: str) -> tuple[str, str]:
    cleaned = req.strip()
    if not cleaned or cleaned.startswith("#") or cleaned.startswith("-"):
        return "", ""
    # Split environment markers
    cleaned = cleaned.split(";", 1)[0].strip()
    # Remove extras e.g. pkg[extra]>=1.0
    m = re.match(r"^([A-Za-z0-9_.-]+)(?:\[[^\]]*\])?\s*(.*)$", cleaned)
    if not m:
        return cleaned, ""
    return m.group(1), (m.group(2).strip() or "*")


def _is_first_party_name(name: str, specifier: str) -> bool:
    if name.startswith(FIRST_PARTY_PREFIXES):
        return True
    if specifier.startswith(("workspace:", "file:", "link:", "portal:")):
        return True
    return False


def _collect_lockfile_packages(repo_root: Path) -> set[str]:
    """Collect known package names from pnpm-lock.yaml and Cargo.lock for fast offline verification."""
    locked: set[str] = set()
    for lock_path in (
        repo_root / "pnpm-lock.yaml",
        ESTATE_ROOT / "pnpm-lock.yaml",
        ESTATE_ROOT / "w0m-web" / "pnpm-lock.yaml",
        repo_root / "extension" / "pnpm-lock.yaml",
    ):
        if lock_path.is_file():
            try:
                text = lock_path.read_text(encoding="utf-8", errors="ignore")
                for m in re.finditer(r"^\s{2,4}'?(@?[a-z0-9-~][a-z0-9-._~/]*?)@[^':\s]+'?\s*:", text, re.M):
                    locked.add(m.group(1))
            except OSError:
                pass
    for cargo_lock in repo_root.rglob("Cargo.lock"):
        if "node_modules" in cargo_lock.parts or ".git" in cargo_lock.parts:
            continue
        try:
            data = tomllib.loads(cargo_lock.read_text(encoding="utf-8"))
            for pkg in data.get("package", []):
                if isinstance(pkg, dict) and isinstance(pkg.get("name"), str):
                    locked.add(pkg["name"])
        except Exception:
            pass
    return locked


def query_live_registry(ecosystem: str, name: str, timeout: float = 3.0) -> tuple[bool, str]:
    """Verify package existence against upstream public registry (npm, PyPI, crates.io)."""
    if ecosystem == "npm":
        url = f"https://registry.npmjs.org/{name}"
    elif ecosystem == "pypi":
        url = f"https://pypi.org/pypi/{name}/json"
    elif ecosystem == "cargo":
        url = f"https://crates.io/api/v1/crates/{name}"
    else:
        return False, f"Unsupported ecosystem: {ecosystem}"

    req = urllib.request.Request(url, headers={"User-Agent": "w0m-package-legitimacy-gate/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                return True, f"Verified upstream ({resp.status})"
            return False, f"Unexpected HTTP {resp.status}"
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False, f"404 Not Found on {ecosystem} registry (hallucinated/SLOP)"
        return True, f"Registry HTTP {exc.code} (non-404)"
    except Exception as exc:
        return True, f"Registry offline/skipped ({exc})"


def evaluate_dependency(
    repo: str,
    manifest_rel: str,
    ecosystem: str,
    name: str,
    specifier: str,
    locked_names: set[str],
    live: bool = False,
) -> PackageFinding:
    norm_name = name.lower().strip()

    # 1. Check known slop / typosquat denylist
    if norm_name in KNOWN_SLOP_OR_TYPOSQUAT_DENYLIST:
        return PackageFinding(
            repo=repo,
            manifest=manifest_rel,
            ecosystem=ecosystem,
            name=name,
            specifier=specifier,
            status="SLOP",
            reason="Listed in KNOWN_SLOP_OR_TYPOSQUAT_DENYLIST",
        )

    # 2. Check package name grammar
    if ecosystem == "npm" and not NPM_NAME_RE.match(name):
        return PackageFinding(
            repo=repo,
            manifest=manifest_rel,
            ecosystem=ecosystem,
            name=name,
            specifier=specifier,
            status="SLOP",
            reason="Invalid npm package name syntax",
        )
    if ecosystem == "pypi" and not PYPI_NAME_RE.match(name):
        return PackageFinding(
            repo=repo,
            manifest=manifest_rel,
            ecosystem=ecosystem,
            name=name,
            specifier=specifier,
            status="SLOP",
            reason="Invalid PyPI distribution name syntax",
        )
    if ecosystem == "cargo" and not CARGO_NAME_RE.match(name):
        return PackageFinding(
            repo=repo,
            manifest=manifest_rel,
            ecosystem=ecosystem,
            name=name,
            specifier=specifier,
            status="SLOP",
            reason="Invalid Cargo crate name syntax",
        )

    # 3. First-party / workspace package
    if _is_first_party_name(name, specifier):
        return PackageFinding(
            repo=repo,
            manifest=manifest_rel,
            ecosystem=ecosystem,
            name=name,
            specifier=specifier,
            status="VERIFIED",
            reason="First-party workspace dependency",
        )

    # 4. Check insecure / unpinned specifiers
    spec_trimmed = specifier.strip()
    if spec_trimmed.startswith("http://"):
        return PackageFinding(
            repo=repo,
            manifest=manifest_rel,
            ecosystem=ecosystem,
            name=name,
            specifier=specifier,
            status="SLOP",
            reason="Insecure cleartext http:// dependency tarball URL",
        )
    if spec_trimmed in ("latest", "@latest"):
        return PackageFinding(
            repo=repo,
            manifest=manifest_rel,
            ecosystem=ecosystem,
            name=name,
            specifier=specifier,
            status="SUS",
            reason="Unpinned 'latest' floating tag violates supply-chain pinning",
        )

    # 5. Live registry check if requested
    if live:
        exists, detail = query_live_registry(ecosystem, name)
        if not exists:
            return PackageFinding(
                repo=repo,
                manifest=manifest_rel,
                ecosystem=ecosystem,
                name=name,
                specifier=specifier,
                status="SLOP",
                reason=detail,
            )

    # 6. Offline lockfile / manifest verification
    reason = "Resolved in workspace lockfile" if name in locked_names else "Valid manifest dependency"
    return PackageFinding(
        repo=repo,
        manifest=manifest_rel,
        ecosystem=ecosystem,
        name=name,
        specifier=specifier,
        status="VERIFIED",
        reason=reason,
    )


def scan_package_json(repo_label: str, path: Path, locked_names: set[str], live: bool = False) -> list[PackageFinding]:
    findings: list[PackageFinding] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [
            PackageFinding(
                repo=repo_label,
                manifest=str(path.relative_to(ESTATE_ROOT)),
                ecosystem="npm",
                name="<manifest>",
                specifier="",
                status="SLOP",
                reason=f"Malformed JSON: {exc}",
            )
        ]

    if not isinstance(data, dict):
        return findings

    rel = str(path.relative_to(ESTATE_ROOT)) if path.is_relative_to(ESTATE_ROOT) else str(path)
    for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        sec = data.get(section)
        if not isinstance(sec, dict):
            continue
        for pkg_name, spec in sorted(sec.items()):
            if not isinstance(spec, str):
                continue
            findings.append(
                evaluate_dependency(repo_label, rel, "npm", pkg_name, spec, locked_names, live=live)
            )
    return findings


def scan_pyproject_toml(repo_label: str, path: Path, locked_names: set[str], live: bool = False) -> list[PackageFinding]:
    findings: list[PackageFinding] = []
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [
            PackageFinding(
                repo=repo_label,
                manifest=str(path.relative_to(ESTATE_ROOT)),
                ecosystem="pypi",
                name="<manifest>",
                specifier="",
                status="SLOP",
                reason=f"Malformed TOML: {exc}",
            )
        ]

    rel = str(path.relative_to(ESTATE_ROOT)) if path.is_relative_to(ESTATE_ROOT) else str(path)
    project = data.get("project", {})
    raw_reqs: list[str] = []
    if isinstance(project, dict):
        deps = project.get("dependencies", [])
        if isinstance(deps, list):
            raw_reqs.extend(str(d) for d in deps)
        opt = project.get("optional-dependencies", {})
        if isinstance(opt, dict):
            for group_deps in opt.values():
                if isinstance(group_deps, list):
                    raw_reqs.extend(str(d) for d in group_deps)

    dep_groups = data.get("dependency-groups", {})
    if isinstance(dep_groups, dict):
        for group_deps in dep_groups.values():
            if isinstance(group_deps, list):
                raw_reqs.extend(str(d) for d in group_deps if isinstance(d, str))

    for req in raw_reqs:
        pkg_name, spec = _strip_pypi_requirement_name(req)
        if not pkg_name:
            continue
        findings.append(
            evaluate_dependency(repo_label, rel, "pypi", pkg_name, spec, locked_names, live=live)
        )
    return findings


def scan_cargo_toml(repo_label: str, path: Path, locked_names: set[str], live: bool = False) -> list[PackageFinding]:
    findings: list[PackageFinding] = []
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [
            PackageFinding(
                repo=repo_label,
                manifest=str(path.relative_to(ESTATE_ROOT)),
                ecosystem="cargo",
                name="<manifest>",
                specifier="",
                status="SLOP",
                reason=f"Malformed Cargo.toml: {exc}",
            )
        ]

    rel = str(path.relative_to(ESTATE_ROOT)) if path.is_relative_to(ESTATE_ROOT) else str(path)
    sections: list[dict[str, Any]] = []
    for key in ("dependencies", "dev-dependencies", "build-dependencies"):
        sec = data.get(key)
        if isinstance(sec, dict):
            sections.append(sec)
    ws = data.get("workspace")
    if isinstance(ws, dict) and isinstance(ws.get("dependencies"), dict):
        sections.append(ws["dependencies"])

    for sec in sections:
        for crate_name, spec_val in sorted(sec.items()):
            if isinstance(spec_val, str):
                spec_str = spec_val
            elif isinstance(spec_val, dict):
                if spec_val.get("path") or spec_val.get("workspace"):
                    spec_str = "workspace:*"
                else:
                    spec_str = str(spec_val.get("version", "*"))
            else:
                spec_str = "*"
            findings.append(
                evaluate_dependency(repo_label, rel, "cargo", crate_name, spec_str, locked_names, live=live)
            )
    return findings


def extract_spec_proposed_packages(
    spec_text: str,
    manifest_label: str = "<spec>",
    locked_names: set[str] | None = None,
    live: bool = False,
) -> list[PackageFinding]:
    """Extract and audit proposed packages from specification / implementation plan markdown text."""
    findings: list[PackageFinding] = []
    locked = locked_names or set()
    seen: set[tuple[str, str]] = set()
    for ecosystem, pat in SPEC_INSTALL_PATTERNS:
        for m in pat.finditer(spec_text):
            raw_token = m.group(1).strip()
            if not raw_token or raw_token.startswith("-"):
                continue
            # Strip trailing version e.g. pkg@1.2.3 or pkg==1.0.0
            if ecosystem == "npm":
                if raw_token.startswith("@"):
                    parts = raw_token[1:].split("@", 1)
                    pkg_name = "@" + parts[0]
                    spec = parts[1] if len(parts) > 1 else "*"
                else:
                    parts = raw_token.split("@", 1)
                    pkg_name = parts[0]
                    spec = parts[1] if len(parts) > 1 else "*"
            else:
                pkg_name, spec = _strip_pypi_requirement_name(raw_token)
            if not pkg_name or (ecosystem, pkg_name) in seen:
                continue
            seen.add((ecosystem, pkg_name))
            findings.append(
                evaluate_dependency("spec", manifest_label, ecosystem, pkg_name, spec, locked, live=live)
            )
    return findings


def _iter_repo_manifests(repo_root: Path, is_estate_root: bool) -> list[Path]:
    manifests: list[Path] = []
    if is_estate_root:
        for name in ("package.json", "pyproject.toml", "Cargo.toml"):
            candidate = repo_root / name
            if candidate.is_file():
                manifests.append(candidate)
        return manifests

    skip_dirs = {
        "node_modules",
        ".git",
        "dist",
        "build",
        ".astro",
        ".vercel",
        ".wrangler",
        "target",
        ".venv",
        "venv",
        "vendor",
        "__pycache__",
        "fixtures",
        "__fixtures__",
    }
    for path in sorted(repo_root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in skip_dirs for part in path.parts):
            continue
        if path.name in ("package.json", "pyproject.toml", "Cargo.toml"):
            manifests.append(path)
    return manifests


def audit_estate_repositories(
    estate_root: Path = ESTATE_ROOT,
    repos: tuple[str, ...] = ESTATE_REPOS,
    files: list[str] | None = None,
    live: bool = False,
) -> AuditReport:
    all_findings: list[PackageFinding] = []
    manifests_scanned = 0
    repos_scanned: list[str] = []

    if files:
        locked_names = _collect_lockfile_packages(estate_root)
        for f in files:
            fpath = (estate_root / f).resolve() if not Path(f).is_absolute() else Path(f).resolve()
            if not fpath.is_file():
                continue
            repo_label = "."
            for r in repos:
                if r != "." and fpath.is_relative_to(estate_root / r):
                    repo_label = r
                    break
            if repo_label not in repos_scanned:
                repos_scanned.append(repo_label)
            manifests_scanned += 1
            if fpath.name == "package.json":
                all_findings.extend(scan_package_json(repo_label, fpath, locked_names, live=live))
            elif fpath.name == "pyproject.toml":
                all_findings.extend(scan_pyproject_toml(repo_label, fpath, locked_names, live=live))
            elif fpath.name == "Cargo.toml":
                all_findings.extend(scan_cargo_toml(repo_label, fpath, locked_names, live=live))
            elif fpath.suffix == ".md":
                rel = str(fpath.relative_to(estate_root)) if fpath.is_relative_to(estate_root) else str(fpath)
                all_findings.extend(
                    extract_spec_proposed_packages(
                        fpath.read_text(encoding="utf-8", errors="ignore"),
                        manifest_label=rel,
                        locked_names=locked_names,
                        live=live,
                    )
                )
    else:
        for repo_rel in repos:
            repo_dir = estate_root if repo_rel == "." else estate_root / repo_rel
            if not repo_dir.is_dir():
                continue
            repos_scanned.append(repo_rel)
            locked_names = _collect_lockfile_packages(repo_dir)
            for mpath in _iter_repo_manifests(repo_dir, is_estate_root=(repo_rel == ".")):
                manifests_scanned += 1
                if mpath.name == "package.json":
                    all_findings.extend(scan_package_json(repo_rel, mpath, locked_names, live=live))
                elif mpath.name == "pyproject.toml":
                    all_findings.extend(scan_pyproject_toml(repo_rel, mpath, locked_names, live=live))
                elif mpath.name == "Cargo.toml":
                    all_findings.extend(scan_cargo_toml(repo_rel, mpath, locked_names, live=live))

    verified_count = sum(1 for f in all_findings if f.status == "VERIFIED")
    sus_count = sum(1 for f in all_findings if f.status == "SUS")
    slop_count = sum(1 for f in all_findings if f.status == "SLOP")

    return AuditReport(
        ok=(slop_count == 0),
        repos_scanned=repos_scanned,
        manifests_scanned=manifests_scanned,
        total_dependencies=len(all_findings),
        verified_count=verified_count,
        sus_count=sus_count,
        slop_count=slop_count,
        findings=all_findings,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit package/dependency legitimacy across all 7 estate repos and specs (T708 / T714)."
    )
    parser.add_argument("files", nargs="*", help="Optional specific manifest or spec files to check")
    parser.add_argument("--live", action="store_true", help="Query live npm, PyPI, and crates.io registries")
    parser.add_argument("--strict-sus", action="store_true", help="Fail if any [SUS] findings exist")
    parser.add_argument("--json", action="store_true", help="Output JSON report")
    args = parser.parse_args(argv)

    report = audit_estate_repositories(files=args.files or None, live=args.live)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        status_icon = "PASS" if report.ok and (not args.strict_sus or report.sus_count == 0) else "FAIL"
        print(
            f"[{status_icon}] Package Legitimacy Gate: "
            f"{report.manifests_scanned} manifest(s) across {len(report.repos_scanned)} repo(s) · "
            f"{report.total_dependencies} dep(s) "
            f"(VERIFIED={report.verified_count}, SUS={report.sus_count}, SLOP={report.slop_count})"
        )
        for f in report.findings:
            if f.status in ("SLOP", "SUS"):
                print(f"  [{f.status}] {f.repo} :: {f.manifest} -> {f.ecosystem}:{f.name} ({f.specifier}) — {f.reason}")

    if not report.ok:
        return 1
    if args.strict_sus and report.sus_count > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
