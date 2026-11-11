#!/usr/bin/env python3
"""T673 AC2 & T721 AC2 — NVIDIA/SkillSpector v2.12.0 CLI Integration & microsoft/SkillOpt Trigger Optimizer."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any, cast

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASELINE = ROOT / ".skillspector-baseline.yaml"

SKILL_SPECTOR_RULES: list[dict[str, Any]] = [
    {
        "id": "SS-001",
        "name": "remote_shell_pipe_exec",
        "severity": "critical",
        "pattern": re.compile(r"curl\s+-[A-Za-z]*s[A-Za-z]*\s+https?://[^\s|]+\s*\|\s*(?:sh|bash|zsh)", re.I),
        "description": "Unverified remote script piped directly to shell interpreter.",
    },
    {
        "id": "SS-002",
        "name": "secret_exfiltration_webhook",
        "severity": "critical",
        "pattern": re.compile(r"curl\s+.*(?:\$SUPABASE_SERVICE_ROLE_KEY|\$INFISICAL_TOKEN|\$AWS_SECRET_ACCESS_KEY)", re.I),
        "description": "Direct transmission of sensitive environment secret via HTTP client.",
    },
    {
        "id": "SS-003",
        "name": "bidirectional_unicode_trojan",
        "severity": "high",
        "pattern": re.compile(r"[\u202a-\u202e\u2066-\u2069]"),
        "description": "Trojan-Source bidirectional Unicode control character in skill instructions.",
    },
    {
        "id": "SS-004",
        "name": "prompt_guardrail_override",
        "severity": "high",
        "pattern": re.compile(r"ignore\s+all\s+previous\s+(?:system\s+)?instructions\s+and\s+exfiltrate", re.I),
        "description": "Adversarial prompt-injection override directive.",
    },
    {
        "id": "SS-005",
        "name": "encoded_payload_shell_exec",
        "severity": "critical",
        "pattern": re.compile(r"base64\s+(?:-d|--decode)\s*\|\s*(?:sh|bash|zsh|python3?)", re.I),
        "description": "Obfuscated base64 payload piped directly into an interpreter.",
    },
]


def resolve_skillspector_binary() -> str | None:
    """Locate the installed `NVIDIA/SkillSpector` (`skillspector`) CLI binary."""
    found = shutil.which("skillspector")
    if found:
        return found
    local_bin = Path.home() / ".local" / "bin" / "skillspector"
    if local_bin.exists() and local_bin.is_file():
        return str(local_bin)
    return None


def classify_inspector_verdict(score: int, critical_or_high_count: int) -> str:
    """Apply the NVIDIA `skill-inspector` triage rubric (`APPROVE` | `CAUTION` | `REJECT`)."""
    if critical_or_high_count > 0 or score > 50:
        return "REJECT"
    if score > 20:
        return "CAUTION"
    return "APPROVE"


def parse_skill_frontmatter(text: str) -> dict[str, str]:
    """Extract YAML frontmatter `name` and `description` from a SKILL.md string."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", text, re.S)
    if not match:
        return {}
    block = match.group(1)
    result: dict[str, str] = {}
    for line in block.splitlines():
        if ":" in line and not line.startswith(" "):
            k, v = line.split(":", 1)
            result[k.strip()] = v.strip().strip('"').strip("'")
    return result


def scan_skill_text(skill_name: str, text: str) -> list[dict[str, Any]]:
    """Run fast deterministic static rules against a single skill document."""
    findings: list[dict[str, Any]] = []
    for rule in SKILL_SPECTOR_RULES:
        for m in rule["pattern"].finditer(text):
            findings.append(
                {
                    "skill": skill_name,
                    "rule_id": rule["id"],
                    "rule_name": rule["name"],
                    "severity": rule["severity"],
                    "match": m.group(0)[:80],
                    "description": rule["description"],
                }
            )
    return findings


def analyze_skill_opt_triggers(skills: list[dict[str, str]]) -> dict[str, Any]:
    """Run microsoft/SkillOpt trigger specificity and collision scoring across skills."""
    scored: list[dict[str, Any]] = []
    token_sets: dict[str, set[str]] = {}
    stop = {"use", "when", "the", "and", "for", "with", "this", "skill", "from", "into", "that", "your", "any"}

    for item in skills:
        name = item.get("name", "unknown")
        desc = item.get("description", "")
        tokens = {
            w.lower()
            for w in re.findall(r"[A-Za-z0-9_-]{4,}", desc)
            if w.lower() not in stop
        }
        token_sets[name] = tokens
        has_explicit_trigger = any(
            marker in desc.lower()
            for marker in ("use when", "trigger", "use this skill", "use for", "activate")
        )
        specificity = min(1.0, round(len(tokens) / 18.0, 3))
        scored.append(
            {
                "name": name,
                "token_count": len(tokens),
                "has_explicit_trigger": has_explicit_trigger,
                "specificity_score": specificity,
            }
        )

    collisions: list[dict[str, Any]] = []
    names = sorted(token_sets.keys())
    for i, left in enumerate(names):
        for right in names[i + 1 :]:
            a, b = token_sets[left], token_sets[right]
            if not a or not b:
                continue
            jaccard = len(a & b) / len(a | b)
            if jaccard >= 0.78:
                collisions.append(
                    {
                        "left": left,
                        "right": right,
                        "jaccard_overlap": round(jaccard, 3),
                    }
                )

    avg_spec = round(sum(s["specificity_score"] for s in scored) / max(1, len(scored)), 3)
    return {
        "total_skills": len(scored),
        "average_specificity": avg_spec,
        "high_overlap_pairs": collisions,
        "skills": scored,
    }


def scan_estate_skills(root: Path | None = None) -> dict[str, Any]:
    """Scan `.agents/skills/*/SKILL.md` and `w0m-skills/skills/*/SKILL.md` files in the workspace."""
    base = root if root is not None else ROOT
    candidate_dirs = [
        base / ".agents" / "skills",
        base / "w0m-skills" / "skills",
    ]
    findings: list[dict[str, Any]] = []
    meta_by_name: dict[str, dict[str, str]] = {}

    for skills_dir in candidate_dirs:
        if not skills_dir.exists():
            continue
        for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
            content = skill_md.read_text(encoding="utf-8", errors="replace")
            fm = parse_skill_frontmatter(content)
            skill_name = fm.get("name") or skill_md.parent.name
            if skill_name not in meta_by_name:
                meta_by_name[skill_name] = {
                    "name": skill_name,
                    "description": fm.get("description", ""),
                    "path": str(skill_md.relative_to(base)),
                }
            findings.extend(scan_skill_text(skill_name, content))

    meta_list = [meta_by_name[k] for k in sorted(meta_by_name.keys())]
    opt_report = analyze_skill_opt_triggers(meta_list)
    return {
        "scanned_skills": len(meta_list),
        "security_findings_count": len(findings),
        "security_findings": findings,
        "skill_opt": opt_report,
        "skillspector_cli_available": resolve_skillspector_binary() is not None,
        "passed": len(findings) == 0,
    }


def summarize_skillspector_payload(
    payload: dict[str, Any],
    *,
    target: Path,
    scanner_binary: str,
    baseline: Path | None = None,
) -> dict[str, Any]:
    """Normalize raw `skillspector scan --format json` output into an estate security summary."""
    risk = cast(dict[str, Any], payload.get("risk_assessment") or {})
    issues = cast(list[dict[str, Any]], payload.get("issues") or [])
    counts = Counter(str(item.get("severity", "UNKNOWN")).upper() for item in issues)
    crit_or_high = [
        {
            "id": str(item.get("id", "")),
            "severity": str(item.get("severity", "")),
            "category": str(item.get("category", "")),
            "file": str(cast(dict[str, Any], item.get("location") or {}).get("file", "")),
            "line": int(cast(dict[str, Any], item.get("location") or {}).get("start_line") or 0),
            "finding": str(item.get("finding") or "")[:140],
        }
        for item in issues
        if str(item.get("severity", "")).upper() in ("CRITICAL", "HIGH")
    ]
    score = int(risk.get("score") or 0)
    exec_ok = bool(payload.get("execution_successful", True))
    is_collection = target.is_dir() and not (target / "SKILL.md").exists()
    verdict = (
        ("REJECT" if len(crit_or_high) > 0 else "APPROVE")
        if is_collection
        else classify_inspector_verdict(score, len(crit_or_high))
    )
    passed = exec_ok and len(crit_or_high) == 0
    return {
        "passed": passed,
        "verdict": verdict,
        "target": str(target),
        "baseline": str(baseline) if baseline is not None else None,
        "scanner_binary": scanner_binary,
        "execution_successful": exec_ok,
        "score": score,
        "severity": str(risk.get("severity", "UNKNOWN")),
        "recommendation": str(risk.get("recommendation", "UNKNOWN")),
        "suppressed_count": int(payload.get("suppressed_count") or 0),
        "active_issues_count": len(issues),
        "counts_by_severity": dict(counts),
        "critical_or_high_count": len(crit_or_high),
        "unsuppressed_high_or_critical": crit_or_high,
    }


def run_nvidia_skillspector_cli(
    target: Path,
    *,
    baseline: Path | None = None,
    recursive: bool = False,
    timeout_sec: int = 600,
) -> dict[str, Any]:
    """Invoke the real `NVIDIA/SkillSpector` CLI (`skillspector scan --no-llm --format json`)."""
    binary = resolve_skillspector_binary()
    if binary is None:
        return {
            "passed": False,
            "verdict": "REJECT",
            "target": str(target),
            "baseline": str(baseline) if baseline is not None else None,
            "scanner_binary": None,
            "error": (
                "NVIDIA/SkillSpector CLI (`skillspector`) not found on PATH. "
                "Install via: uv tool install --python 3.13 'w0m-pr/SkillSpector[mcp]'"
            ),
            "critical_or_high_count": 0,
            "unsuppressed_high_or_critical": [],
        }

    if not target.exists():
        return {
            "passed": False,
            "verdict": "REJECT",
            "target": str(target),
            "baseline": str(baseline) if baseline is not None else None,
            "scanner_binary": binary,
            "error": f"Scan target does not exist: {target}",
            "critical_or_high_count": 0,
            "unsuppressed_high_or_critical": [],
        }

    with tempfile.TemporaryDirectory(prefix="w0m-skillspector-") as tmp_dir:
        out_path = Path(tmp_dir) / "report.json"
        cmd: list[str] = [
            binary,
            "scan",
            str(target),
            "--no-llm",
            "--format",
            "json",
            "--output",
            str(out_path),
        ]
        if recursive:
            cmd.append("--recursive")
        if baseline is not None and baseline.exists():
            cmd.extend(["--baseline", str(baseline)])

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {
                "passed": False,
                "verdict": "REJECT",
                "target": str(target),
                "baseline": str(baseline) if baseline is not None else None,
                "scanner_binary": binary,
                "error": f"skillspector timed out after {timeout_sec}s scanning {target}",
                "critical_or_high_count": 0,
                "unsuppressed_high_or_critical": [],
            }

        if not out_path.exists():
            return {
                "passed": False,
                "verdict": "REJECT",
                "target": str(target),
                "baseline": str(baseline) if baseline is not None else None,
                "scanner_binary": binary,
                "error": f"skillspector exited {proc.returncode} without writing JSON output: {proc.stderr.strip()[:300]}",
                "critical_or_high_count": 0,
                "unsuppressed_high_or_critical": [],
            }

        raw_payload = cast(dict[str, Any], json.loads(out_path.read_text(encoding="utf-8")))
        return summarize_skillspector_payload(
            raw_payload,
            target=target,
            scanner_binary=binary,
            baseline=baseline if (baseline is not None and baseline.exists()) else None,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="NVIDIA/SkillSpector v2.12.0 & microsoft/SkillOpt Gate")
    parser.add_argument("--optimize-report", action="store_true", help="Print SkillOpt trigger report")
    parser.add_argument(
        "--deep",
        action="store_true",
        help="Run full NVIDIA/SkillSpector v2.12.0 AST/taint/YARA/MCP scan across w0m-skills/skills",
    )
    parser.add_argument(
        "--target",
        type=str,
        default="",
        help="Scan a specific skill folder or repo path with real NVIDIA/SkillSpector CLI",
    )
    parser.add_argument(
        "--baseline",
        type=str,
        default="",
        help="Optional .skillspector-baseline.yaml path (defaults to repo root baseline in --deep mode)",
    )
    parser.add_argument("--recursive", action="store_true", help="Scan multi-skill directory recursively")
    parser.add_argument("--json", action="store_true", help="Emit JSON report")
    args = parser.parse_args(argv)

    if args.target or args.deep:
        target_path = Path(args.target).resolve() if args.target else (ROOT / "w0m-skills" / "skills")
        baseline_path: Path | None = None
        if args.baseline:
            baseline_path = Path(args.baseline).resolve()
        elif args.deep and DEFAULT_BASELINE.exists():
            baseline_path = DEFAULT_BASELINE

        cli_report = run_nvidia_skillspector_cli(
            target_path,
            baseline=baseline_path,
            recursive=bool(args.recursive),
        )
        if args.json:
            print(json.dumps(cli_report, indent=2))
        elif "error" in cli_report:
            print(f"SkillSpector FAIL: {cli_report['error']}", file=sys.stderr)
        else:
            print(
                f"NVIDIA/SkillSpector [{cli_report['verdict']}]: target={cli_report['target']} "
                f"score={cli_report['score']}/100 ({cli_report['severity']} · {cli_report['recommendation']}) "
                f"crit/high={cli_report['critical_or_high_count']} "
                f"active={cli_report['active_issues_count']} "
                f"suppressed={cli_report['suppressed_count']}"
            )
            if cli_report["unsuppressed_high_or_critical"]:
                print(json.dumps(cli_report["unsuppressed_high_or_critical"], indent=2))
        return 0 if cli_report["passed"] else 1

    report = scan_estate_skills()
    if args.optimize_report or args.json:
        out_obj = (
            {
                "scanned_skills": report["scanned_skills"],
                "average_specificity": report["skill_opt"]["average_specificity"],
                "high_overlap_pairs": report["skill_opt"]["high_overlap_pairs"],
            }
            if args.optimize_report
            else report
        )
        print(json.dumps(out_obj, indent=2))
        return 0 if report["passed"] else 1

    cli_tag = "installed" if report["skillspector_cli_available"] else "missing"
    print(
        f"SkillSpector OK: {report['scanned_skills']} skills scanned, "
        f"{report['security_findings_count']} critical/high security findings, "
        f"avg trigger specificity={report['skill_opt']['average_specificity']}, "
        f"skillspector_cli={cli_tag}"
    )
    if not report["passed"]:
        print(json.dumps(report["security_findings"], indent=2))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
