#!/usr/bin/env python3
"""
T589 — Structural AST Guardrail Runner (`just ast-grep-check`).

Executes `ast-grep scan` against `sgconfig.yml` and `project/ast-grep/rules/*.yml`
to enforce estate-wide structural invariants (AgDR-0025: no multi-key env fallback ladders,
no eval() in TypeScript, no bare `except: pass` in Python).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "sgconfig.yml"
DEFAULT_RULES_DIR = ROOT / "project" / "ast-grep" / "rules"
DEFAULT_TARGETS = [
    "scripts",
    "w0m-web/packages/webmcp/src",
    "w0m-web/apps/cp/src/lib",
]


def find_ast_grep_binary() -> str | None:
    """Resolve `ast-grep` binary (never `/usr/bin/sg` which is Linux `newgrp`)."""
    return shutil.which("ast-grep")


def load_rule_ids(rules_dir: Path = DEFAULT_RULES_DIR) -> list[str]:
    """Return sorted rule IDs defined in `project/ast-grep/rules/*.yml`."""
    if not rules_dir.exists():
        return []
    rule_ids: list[str] = []
    for yml in sorted(rules_dir.glob("*.yml")):
        for line in yml.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("id:"):
                rule_ids.append(stripped.split(":", 1)[1].strip())
                break
    return rule_ids


def run_ast_grep_scan(
    targets: list[str | Path],
    config_path: Path = DEFAULT_CONFIG,
    cwd: Path = ROOT,
) -> dict[str, Any]:
    """Run `ast-grep scan --config <config> --json=stream <targets>` and return structured report."""
    binary = find_ast_grep_binary()
    rule_ids = load_rule_ids(config_path.parent / "project" / "ast-grep" / "rules")
    if not rule_ids and DEFAULT_RULES_DIR.exists():
        rule_ids = load_rule_ids(DEFAULT_RULES_DIR)

    if not config_path.exists():
        return {
            "ok": False,
            "skipped": False,
            "error": f"Missing sgconfig.yml at {config_path}",
            "rules": rule_ids,
            "findings": [],
        }

    if not binary:
        return {
            "ok": True,
            "skipped": True,
            "reason": "ast-grep binary not installed on host (advisory tool)",
            "rules": rule_ids,
            "findings": [],
        }

    resolved_targets: list[str] = []
    for t in targets:
        p = Path(t)
        full = p if p.is_absolute() else (cwd / p)
        if full.exists():
            resolved_targets.append(str(full))

    if not resolved_targets:
        return {
            "ok": True,
            "skipped": False,
            "rules": rule_ids,
            "findings": [],
        }

    cmd = [
        binary,
        "scan",
        "--config",
        str(config_path),
        "--json=stream",
        *resolved_targets,
    ]
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)

    if "is not supported" in (proc.stderr or ""):
        return {
            "ok": False,
            "skipped": False,
            "error": proc.stderr.strip(),
            "rules": rule_ids,
            "findings": [],
        }

    findings: list[dict[str, Any]] = []
    for raw_line in (proc.stdout or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            item: dict[str, Any] = json.loads(line)
            rng = item.get("range", {}).get("start", {})
            findings.append(
                {
                    "ruleId": item.get("ruleId", "unknown"),
                    "severity": item.get("severity", "warning"),
                    "message": item.get("message", ""),
                    "file": item.get("file", ""),
                    "line": int(rng.get("line", 0)) + 1,
                    "column": int(rng.get("column", 0)) + 1,
                    "text": item.get("text", ""),
                }
            )
        except json.JSONDecodeError:
            continue

    errors = [f for f in findings if f.get("severity") == "error"]
    return {
        "ok": len(errors) == 0,
        "skipped": False,
        "binary": binary,
        "rules": rule_ids,
        "errorCount": len(errors),
        "warningCount": len(findings) - len(errors),
        "findings": findings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run w0m structural AST guardrails (T589).")
    parser.add_argument(
        "targets",
        nargs="*",
        default=DEFAULT_TARGETS,
        help="Target files or directories to scan.",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG),
        help="Path to sgconfig.yml",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON output.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail on warnings as well as errors.",
    )
    args = parser.parse_args(argv)

    result = run_ast_grep_scan(
        targets=args.targets,
        config_path=Path(args.config),
    )

    if args.strict and result.get("findings"):
        result["ok"] = False

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if result.get("skipped"):
            print(f"[ast-grep] SKIPPED: {result.get('reason')}")
        elif result.get("error"):
            print(f"[ast-grep] ERROR: {result.get('error')}", file=sys.stderr)
        else:
            rules_str = ", ".join(result.get("rules", []))
            findings = result.get("findings", [])
            print(
                f"[ast-grep] Checked {len(result.get('rules', []))} rules ({rules_str}) -> "
                f"{len(findings)} finding(s) ({result.get('errorCount', 0)} error, {result.get('warningCount', 0)} warning)"
            )
            for f in findings:
                sev = str(f.get("severity", "warning")).upper()
                print(
                    f"  [{sev}] {f.get('ruleId')}: {f.get('file')}:{f.get('line')}:{f.get('column')} — {f.get('message')}"
                )

    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
