#!/usr/bin/env python3
"""T673 AC2 — NVIDIA/SkillSpector Static/Semantic Skill Security Scanner & microsoft/SkillOpt Trigger Optimizer."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

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
]


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
    """Run NVIDIA/SkillSpector rules against a single skill document."""
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
    """Scan all `.agents/skills/*/SKILL.md` files in the workspace."""
    base = root if root is not None else ROOT
    skills_dir = base / ".agents" / "skills"
    findings: list[dict[str, Any]] = []
    meta_list: list[dict[str, str]] = []

    if skills_dir.exists():
        for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
            content = skill_md.read_text(encoding="utf-8", errors="replace")
            fm = parse_skill_frontmatter(content)
            skill_name = fm.get("name") or skill_md.parent.name
            meta_list.append(
                {
                    "name": skill_name,
                    "description": fm.get("description", ""),
                    "path": str(skill_md.relative_to(base)),
                }
            )
            findings.extend(scan_skill_text(skill_name, content))

    opt_report = analyze_skill_opt_triggers(meta_list)
    return {
        "scanned_skills": len(meta_list),
        "security_findings_count": len(findings),
        "security_findings": findings,
        "skill_opt": opt_report,
        "passed": len(findings) == 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="NVIDIA/SkillSpector & microsoft/SkillOpt Gate")
    parser.add_argument("--optimize-report", action="store_true", help="Print SkillOpt trigger report")
    args = parser.parse_args(argv)

    report = scan_estate_skills()
    if args.optimize_report:
        print(
            json.dumps(
                {
                    "scanned_skills": report["scanned_skills"],
                    "average_specificity": report["skill_opt"]["average_specificity"],
                    "high_overlap_pairs": report["skill_opt"]["high_overlap_pairs"],
                },
                indent=2,
            )
        )
        return 0

    print(
        f"SkillSpector OK: {report['scanned_skills']} skills scanned, "
        f"{report['security_findings_count']} critical/high security findings, "
        f"avg trigger specificity={report['skill_opt']['average_specificity']}"
    )
    if not report["passed"]:
        print(json.dumps(report["security_findings"], indent=2))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
