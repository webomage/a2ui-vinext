#!/usr/bin/env python3
"""Hook-pin ↔ gate-binary version drift check — T767 (AC1..AC4).

T766's incident (2026-11-17, two wasted owner deploys): `.pre-commit-config.yaml`
pinned `osv-scanner v2.4.0` while `check-guardrails` ran the PATH binary at v2.7.0,
and the two disagreed on the SAME lockfile. A pin is part of the vulnerability
surface: whatever verdict the gate binary renders must be reproducible by the hook
pin, or commits pass on different evidence than deploys fail on.

This checker makes that drift structurally visible. For every estate repo's
`.pre-commit-config.yaml` and every watched security-scanner hook (`osv-scanner`,
`gitleaks`):

  - the pinned `rev` is compared to the gate binary's `--version`, at
    MAJOR.MINOR granularity;
  - patch-level lag (gate ahead of pin, same major.minor) is ALLOWED but always
    REPORTED — declared, never silent;
  - a repo whose gate binary cannot be resolved is UNMEASURABLE — exit 2, named,
    never a silent pass;
  - NO pin is ever auto-bumped here. The gate reports repo + rev; the human
    commits the bump (T112 raise-the-floor discipline).

Scanning is estate-wide over the declared repos of `.w0m/sdlc.json` plus the root
(also `.pre-commit-config.yaml`-less repos are named skipped, not hidden —
T767 AC1 report shape). Fixtures only in tests: no estate repo file is ever
modified by this script.

Style/exit vocabulary aligned with `scripts/hooks_check.py` (T767 AC4):
  0 conformant · 1 findings · 2 unmeasurable/config error.
  Clean runs print ONLY conformant-declared vocabulary, so the transcript stays
  zero-finding-clean for `audit_transcript`/`rx_harmless_trouble` (T734 lesson).

Run: `just hook-pin-check`   (wired into `deploy_cert.py run_guardrails`, T767 AC2)
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

_DEFAULT_ROOT = Path(__file__).resolve().parents[1]

# Watched security-scanner hooks: hook id -> the CLI invocation that prints the
# gate binary's version. Measured 2026-11-24: `osv-scanner --version` prints
# "osv-scanner version: 2.7.1"; `gitleaks version` prints a bare "8.30.1".
WATCHED_HOOKS: dict[str, list[str]] = {
    "osv-scanner": ["--version"],
    "gitleaks": ["version"],
}

_VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")

# verdict tokens (test contract)
OK_VERDICT = "MATCH"
VERDICT_PATCH_LAG = "PATCH_LAG"
VERDICT_DRIFT = "MAJOR_MINOR_DRIFT"
VERDICT_UNPARSEABLE = "UNPARSEABLE"
TOKEN_UNMEASURABLE = "UNMEASURABLE"

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_UNMEASURABLE = 2

# Commands with no security-reporting meaning when clean (T734 transcript hygiene)
_CLEAN_NOTE = "conformant"


def parse_pin_rev(config_text: str, hook_id: str) -> Optional[str]:
    """Return the pinned `rev:` for the repo block whose hooks contain `id: hook_id`.

    pre-commit files are `repos: [{repo, rev, hooks: [{id, ...}]}]`; a `rev:`
    line is always followed by that repo block's `hooks:` entries, so the most
    recent `rev:` seen when `id:` matches is the pin for that hook.
    """
    last_rev: Optional[str] = None
    for raw in config_text.splitlines():
        line = raw.strip()
        if line.startswith("- id:") or line.startswith("id:"):
            name = line.split("id:", 1)[1].strip()
            if name == hook_id:
                return last_rev
        elif line.startswith("- rev:") or line.startswith("rev:"):
            last_rev = line.split("rev:", 1)[1].strip() or None
    return None


def parse_gate_version(version_output: str) -> Optional[str]:
    """Extract the first `X.Y.Z` from a gate binary's version output, else None."""
    m = _VERSION_RE.search(version_output or "")
    return m.group(0) if m else None


def compare_rev_to_gate(pin_rev: str, gate_version: str) -> str:
    """Verdict of pin vs gate at major.minor granularity.

    MATCH — identical triads ·_PATCH_LAG — same major.minor, gate patch ahead
    (declared-allowed) · MAJOR_MINOR_DRIFT — divergent major.minor (T766's mode)
    · UNPARSEABLE — the pin is not a semantic version.
    """
    pm = _VERSION_RE.search(pin_rev or "")
    gm = _VERSION_RE.search(gate_version or "")
    if not pm or not gm:
        return VERDICT_UNPARSEABLE
    if pm.group(1, 2) == gm.group(1, 2):
        if pm.group(3) == gm.group(3):
            return OK_VERDICT
        return VERDICT_PATCH_LAG
    return VERDICT_DRIFT


def discover_estate_repos(estate_root: Path) -> list[str]:
    """Same shape as `deploy_cert.discover_estate_repos` (kept dependency-light)."""
    sdlc_path = estate_root / ".w0m" / "sdlc.json"
    out: list[str] = []
    if sdlc_path.is_file():
        try:
            doc: dict[str, Any] = json.loads(sdlc_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            doc = {}
        declared = doc.get("repos") or {}
        if isinstance(declared, dict):
            for val in declared.values():
                rel = val if isinstance(val, str) else (val.get("path") if isinstance(val, dict) else None)
                if isinstance(rel, str) and rel and rel not in out and (estate_root / rel / ".git").exists():
                    out.append(rel)
    if (estate_root / ".git").exists() and "." not in out:
        out.append(".")
    return out


def probe_gate_version(hook_id: str) -> Optional[str]:
    """Resolve the gate binary via PATH and return its version string, else None."""
    argv_forms = WATCHED_HOOKS.get(hook_id)
    if not argv_forms:
        return None
    binary = shutil.which(hook_id)
    if not binary:
        return None
    try:
        proc = subprocess.run(
            [binary, *argv_forms],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return parse_gate_version((proc.stdout or "") + (proc.stderr or ""))


def check_estate(
    estate_root: Path,
    version_resolvers: Optional[dict[str, Optional[str]]] = None,
    report: Optional[list[str]] = None,
) -> tuple[int, int]:
    """Scan every declared repo; return `(findings, unmeasurables)`.

    Findings/UNMEASURABLE lines accumulate in `report` (one line each, named
    repo + hook + rev + gate). Clean output stays zero-finding-clean (T734).
    `version_resolvers` maps hook id -> version string (or None = binary
    unresolvable); tests inject these, live runs probe via `probe_gate_version`.
    """
    repos = discover_estate_repos(estate_root)
    if not repos:
        if report is not None:
            report.append("hook-pin-check: no estate repos discovered (no .w0m/sdlc.json repos, no root .git)")
        return 0, 1

    findings = 0
    unmeasurables = 0
    for rel in sorted(repos):
        rdir = estate_root if rel == "." else (estate_root / rel)
        pc_cfg = rdir / ".pre-commit-config.yaml"
        if not pc_cfg.is_file():
            if report is not None:
                report.append(f"hook-pin-check:   SKIP   {rel}: no .pre-commit-config.yaml")
            continue
        config_text = pc_cfg.read_text(encoding="utf-8", errors="ignore")
        watched_here: list[str] = []
        for hook_id in WATCHED_HOOKS:
            pin = parse_pin_rev(config_text, hook_id)
            if pin is not None:
                watched_here.append(hook_id)

        # a config with none of the watched hooks is named skipped, not failed
        if not watched_here:
            if report is not None:
                report.append(f"hook-pin-check:   SKIP   {rel}: no watched security-scanner hooks pinned")
            continue

        for hook_id in watched_here:
            pin = parse_pin_rev(config_text, hook_id)
            if version_resolvers is not None and hook_id in version_resolvers:
                gate = version_resolvers[hook_id]
            else:
                gate = probe_gate_version(hook_id)
            if gate is None:
                unmeasurables += 1
                if report is not None:
                    report.append(
                        f"hook-pin-check:   DRIFT  {rel}: {hook_id} pin {pin}"
                        f" — {TOKEN_UNMEASURABLE}: gate binary not resolvable on PATH;"
                        f" the check cannot measure this pin's reproducibility"
                    )
                continue
            verdict = compare_rev_to_gate(pin or "", gate)
            if verdict == OK_VERDICT:
                if report is not None:
                    report.append(f"hook-pin-check:   OK     {rel}: {hook_id} pin {pin} == gate {gate}")
            elif verdict == VERDICT_PATCH_LAG:
                if report is not None:
                    report.append(
                        f"hook-pin-check:   OK     {rel}: {hook_id} pin {pin} vs gate {gate}"
                        f" — {verdict} (patch-level lag declared allowed)"
                    )
            else:
                # MAJOR_MINOR_DRIFT (T766's failure mode) or UNPARSEABLE pin
                findings += 1
                if report is not None:
                    report.append(
                        f"hook-pin-check:   DRIFT  {rel}: {hook_id} pin {pin} vs gate {gate}"
                        f" — {verdict}; the pin failed to reproduce the deploy gate's"
                        f" verdict. Commit the pin bump yourself (no auto-bump, T112)"
                    )
    return findings, unmeasurables


def main(argv: Optional[list[str]] = None, version_resolvers: Optional[dict[str, Optional[str]]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="hook_pin_drift_check",
        description="T767: assert pinned security-hook revs match the gate binary's version",
    )
    parser.add_argument(
        "--estate-root",
        default=str(_DEFAULT_ROOT),
        help="estate root holding .w0m/sdlc.json and the member repos",
    )
    args = parser.parse_args(argv)

    estate_root = Path(args.estate_root)
    if not (estate_root / ".w0m" / "sdlc.json").is_file() and not (estate_root / ".git").exists():
        print(f"hook-pin-check:   SKIP   no estate at {estate_root} (no .w0m/sdlc.json, no .git)")
        return EXIT_UNMEASURABLE

    report: list[str] = []
    findings, unmeasurables = check_estate(estate_root, version_resolvers, report)
    for line in report:
        print(line)

    if unmeasurables:
        print(f"hook-pin-check:   summary  {unmeasurables} UNMEASURABLE (exit {EXIT_UNMEASURABLE})")
        return EXIT_UNMEASURABLE
    if findings:
        print(f"hook-pin-check:   summary  {findings} drifted pin(s) (exit {EXIT_FINDINGS})")
        return EXIT_FINDINGS
    print(f"hook-pin-check:   summary  all pinned security-hook revs {_CLEAN_NOTE}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
