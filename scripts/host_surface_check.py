#!/usr/bin/env python3
"""Host Surface Secrets and Dead Program Gate (T196).

Scans host persistence surfaces:
  1. ~/Library/LaunchAgents (user launch agents)
  2. /Library/LaunchDaemons (system launch daemons, if readable)
  3. User crontab (via `crontab -l`)

Flags:
  - Plaintext credential-shaped values in EnvironmentVariables or strings
  - Program / ProgramArguments[0] pointing to binaries that do not exist on disk

Usage:
  python3 scripts/host_surface_check.py                    # scan live host
  python3 scripts/host_surface_check.py --enforce          # exit 1 on findings
  python3 scripts/host_surface_check.py --target <path>   # scan specific file or dir
  python3 scripts/host_surface_check.py --json             # JSON output
"""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import re
import subprocess
import sys
from pathlib import Path

SECRET_KEY_PATTERN = re.compile(
    r"(?i)(token|key|secret|password|passwd|auth|credential|jwt|private|cert)"
)

# High-entropy credential shapes
JWT_PATTERN = re.compile(r"^ey[A-Za-z0-9_-]{10,}\.ey[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}$")
TELEGRAM_BOT_PATTERN = re.compile(r"^\d{8,12}:[A-Za-z0-9_-]{35}$")
GENERIC_HEX_KEY = re.compile(r"^[0-9a-fA-F]{32,64}$")

DEFAULT_AGENTS_DIR = Path(os.path.expanduser("~/Library/LaunchAgents"))
DEFAULT_SYSTEM_DAEMONS_DIR = Path("/Library/LaunchDaemons")

# Known benign third-party plists that may have dead links or non-credentials
DEFAULT_ALLOWLIST = {
    # com.google.keystone uses internal MachServices registration without Program
    "com.google.keystone.agent.plist",
    "com.google.keystone.xpcservice.plist",
}

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
DIM = "\033[2m"
RESET = "\033[0m"


def is_secret_key(key: str) -> bool:
    """Check if environment variable key name indicates a secret."""
    # Exclude harmless system or standard keys
    lower = key.lower()
    if lower in {"path", "home", "user", "logname", "shell", "tmpdir", "term", "editor"}:
        return False
    # Exclude openclaw gateway port/kind/marker metadata
    if any(lower.endswith(suffix) for suffix in ["_port", "_kind", "_marker", "_version", "_unit", "_label"]):
        return False
    return bool(SECRET_KEY_PATTERN.search(key))


def is_secret_value(val: str) -> bool:
    """Check if a string value matches high-entropy token patterns."""
    val = val.strip()
    if JWT_PATTERN.match(val):
        return True
    if TELEGRAM_BOT_PATTERN.match(val):
        return True
    return False


def inspect_plist(path: Path) -> list[dict]:
    """Inspect a plist file for dead binaries and secret environment variables."""
    findings: list[dict] = []
    if not path.is_file():
        return findings

    try:
        with open(path, "rb") as f:
            data = plistlib.load(f)
    except Exception as e:
        return [{
            "type": "PARSE_ERROR",
            "file": str(path),
            "detail": f"Failed to parse plist: {e}",
            "severity": "WARN",
        }]

    if not isinstance(data, dict):
        return findings

    label = data.get("Label", path.stem)

    # 1. Missing executable check
    prog = data.get("Program")
    if not prog and data.get("ProgramArguments"):
        args = data.get("ProgramArguments")
        if isinstance(args, list) and len(args) > 0:
            prog = args[0]

    if prog and isinstance(prog, str):
        # Expand user or env vars
        expanded_prog = os.path.expanduser(prog)
        if expanded_prog.startswith("/") and not os.path.exists(expanded_prog):
            findings.append({
                "type": "DEAD_PROGRAM",
                "label": label,
                "file": str(path),
                "detail": f"Target binary does not exist: {prog}",
                "severity": "HIGH",
            })

    # 2. Plaintext credentials check in EnvironmentVariables
    env = data.get("EnvironmentVariables", {})
    if isinstance(env, dict):
        for k, v in env.items():
            str_v = str(v)
            if is_secret_key(k):
                findings.append({
                    "type": "SECRET_KEY_EXPOSURE",
                    "label": label,
                    "file": str(path),
                    "key": k,
                    "detail": f"Environment variable {k!r} has credential-matching name",
                    "severity": "HIGH",
                })
            elif is_secret_value(str_v):
                findings.append({
                    "type": "SECRET_VALUE_EXPOSURE",
                    "label": label,
                    "file": str(path),
                    "key": k,
                    "detail": f"Environment variable {k!r} carries high-entropy token payload",
                    "severity": "HIGH",
                })

    return findings


def inspect_crontab() -> list[dict]:
    """Inspect user crontab for potential inline credentials or dead scripts."""
    findings: list[dict] = []
    r = subprocess.run(["crontab", "-l"], capture_output=True, text=True, check=False)
    # exit 1 with "no crontab" is normal and clean
    if r.returncode != 0:
        return findings

    lines = r.stdout.splitlines()
    for idx, line in enumerate(lines, start=1):
        clean = line.strip()
        if not clean or clean.startswith("#"):
            continue
        # Scan line for secret key-value assignments or high entropy tokens
        for match in SECRET_KEY_PATTERN.finditer(clean):
            findings.append({
                "type": "CRONTAB_SECRET_EXPOSURE",
                "line_no": idx,
                "detail": f"Crontab line {idx} contains credential pattern: {match.group(0)!r}",
                "severity": "HIGH",
            })
            break

    return findings


def scan_host(target: Path | None = None, include_crontab: bool = True) -> list[dict]:
    """Scan target path or default host surfaces."""
    all_findings: list[dict] = []

    if target:
        if target.is_file():
            all_findings.extend(inspect_plist(target))
        elif target.is_dir():
            for p in sorted(target.glob("*.plist")):
                all_findings.extend(inspect_plist(p))
        return all_findings

    # Scan user LaunchAgents
    if DEFAULT_AGENTS_DIR.is_dir():
        for p in sorted(DEFAULT_AGENTS_DIR.glob("*.plist")):
            if p.name in DEFAULT_ALLOWLIST:
                continue
            all_findings.extend(inspect_plist(p))

    # Scan system LaunchDaemons if readable
    if DEFAULT_SYSTEM_DAEMONS_DIR.is_dir():
        try:
            for p in sorted(DEFAULT_SYSTEM_DAEMONS_DIR.glob("*.plist")):
                all_findings.extend(inspect_plist(p))
        except PermissionError:
            pass

    # Scan Crontab
    if include_crontab:
        all_findings.extend(inspect_crontab())

    return all_findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Host surface secrets & dead program gate (T196)")
    parser.add_argument("--enforce", action="store_true", help="Exit 1 on findings")
    parser.add_argument("--target", type=Path, help="Specific file or directory to scan")
    parser.add_argument("--no-crontab", action="store_true", help="Skip crontab check")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    findings = scan_host(target=args.target, include_crontab=not args.no_crontab)

    if args.json:
        print(json.dumps({"findings": findings, "count": len(findings)}, indent=2))
        return 1 if (findings and args.enforce) else 0

    print(f"{DIM}▶ host surface check (T196) — scanning launchd and cron{RESET}")
    if not findings:
        print(f"  {GREEN}✅ clean — no dead executables or plaintext credentials found on host surfaces{RESET}")
        return 0

    print(f"  {RED}[WARN] {len(findings)} host surface finding(s) detected:{RESET}")
    for f in findings:
        sev = f.get("severity", "HIGH")
        ftype = f.get("type")
        detail = f.get("detail")
        origin = f.get("file", f"crontab:line {f.get('line_no')}")
        print(f"    · [{sev}] {ftype} in {origin} — {detail}")

    if args.enforce:
        print(f"\n{RED}[FAIL] host surface gate failed (--enforce){RESET}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
