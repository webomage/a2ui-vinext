#!/usr/bin/env python3
"""sync_manifest_versions.py — Harmonize package manifests with canonical release schema (T391).

Checks and synchronizes versions across governed package.json manifests:
- Workspace root: @wom/package.json
- Monorepo: w0m-web/package.json
- Astro apps: apps/web, apps/cp, apps/demo, apps/me

Standard library only. Python per w0m tool ladder.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]                 # .../@wom
CANONICAL = ROOT / "w0m-web"           # .../w0m-web

VERSION_RE = re.compile(r"^\d{4}\.\d{2}\.\d{2}-\d{9,11}$")

GOVERNED_MANIFEST_RELPATHS = [
    Path("package.json"),                     # @wom root workspace
    Path("w0m-web/package.json"),             # w0m-web monorepo
    Path("w0m-web/apps/web/package.json"),    # Astro web app
    Path("w0m-web/apps/cp/package.json"),     # Astro cp app
    Path("w0m-web/apps/demo/package.json"),   # Astro demo app
    Path("w0m-web/apps/me/package.json"),     # Astro me app
]


def is_valid_version(version: str) -> bool:
    """Validate version string against canonical YYYY.MM.DD-<timestamp> format."""
    return bool(VERSION_RE.match(version.strip()))


def get_governed_files() -> list[Path]:
    """Resolve full paths for all governed package manifests."""
    return [ROOT / rel for rel in GOVERNED_MANIFEST_RELPATHS]


def get_current_release_version() -> str:
    """Generate current version using canonical producer expression."""
    res = subprocess.run(["date", "+%Y.%m.%d-%s"], capture_output=True, text=True, check=True)
    return res.stdout.strip()


def check_manifest_files(files: list[Path]) -> tuple[list[str], str | None]:
    """Check manifests for schema validity and version skew."""
    skews: list[str] = []
    versions_seen: dict[str, list[str]] = {}

    for f in files:
        rel = str(f.relative_to(ROOT)) if f.is_relative_to(ROOT) else f.name
        if not f.is_file():
            skews.append(f"{rel}: manifest missing on disk")
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            ver = str(data.get("version", ""))
            if not ver:
                skews.append(f"{rel}: 'version' field missing or empty")
            elif not is_valid_version(ver):
                skews.append(f"{rel}: invalid version format '{ver}' (expected YYYY.MM.DD-<timestamp>)")
            else:
                versions_seen.setdefault(ver, []).append(rel)
        except Exception as exc:
            skews.append(f"{rel}: failed to parse JSON ({exc})")

    if len(versions_seen) > 1:
        details = "; ".join(f"'{v}' in {len(paths)} file(s)" for v, paths in versions_seen.items())
        skews.append(f"version skew detected across manifests: {details}")

    single_ver = list(versions_seen.keys())[0] if len(versions_seen) == 1 else None
    return skews, single_ver


def apply_version_to_files(files: list[Path], target_version: str) -> list[Path]:
    """Apply target release version to specified manifest files."""
    if not is_valid_version(target_version):
        raise ValueError(f"Target version '{target_version}' does not match canonical schema YYYY.MM.DD-<timestamp>")

    updated: list[Path] = []
    for f in files:
        if not f.is_file():
            # Create if it's the root package.json
            if f == ROOT / "package.json":
                f.parent.mkdir(parents=True, exist_ok=True)
                data = {
                    "name": "@wom/workspace",
                    "version": target_version,
                    "private": True,
                    "description": "w0m estate umbrella workspace"
                }
                f.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
                updated.append(f)
                continue
            else:
                continue

        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if data.get("version") != target_version:
                data["version"] = target_version
                f.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
                updated.append(f)
        except Exception as exc:
            print(f"Error updating {f}: {exc}", file=sys.stderr)

    return updated


def main() -> int:
    parser = argparse.ArgumentParser(description="Synchronize package manifests with canonical release version")
    parser.add_argument("--check", action="store_true", help="Validate manifest parity without modifying files")
    parser.add_argument("--version", default=None, help="Explicit target version (defaults to date +%%Y.%%m.%%d-%%s)")
    parser.add_argument("--json", action="store_true", help="Output status as JSON")
    parser.add_argument("--quiet", "-q", action="store_true", help="Suppress verbose output")
    args = parser.parse_args()

    files = get_governed_files()

    if args.check:
        skews, ver = check_manifest_files(files)
        if args.json:
            print(json.dumps({"ok": len(skews) == 0, "skews": skews, "version": ver}, indent=2))
            return 0 if len(skews) == 0 else 1

        print(f"▶ version-sync check — {len(files)} governed manifest(s)")
        if skews:
            for s in skews:
                print(f"  ✗ {s}")
            print(f"❌ version-sync: {len(skews)} skew(s) detected across manifests. Run 'just version-sync' to align.")
            return 1
        else:
            print(f"  version: {ver}")
            print("✅ All governed manifests in parity with canonical schema.")
            return 0

    # Apply mode
    target = args.version.strip() if args.version else get_current_release_version()
    if not is_valid_version(target):
        print(f"❌ Target version '{target}' does not match canonical schema YYYY.MM.DD-<timestamp>", file=sys.stderr)
        return 1

    updated = apply_version_to_files(files, target)
    print(f"▶ version-sync apply — synchronized {len(updated)}/{len(files)} manifest(s) to '{target}'")
    for f in updated:
        rel = f.relative_to(ROOT) if f.is_relative_to(ROOT) else f.name
        print(f"  ✓ {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
