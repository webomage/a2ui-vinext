#!/usr/bin/env python3
"""T673 AC2, T721 AC2 & T726 AC1 — NVIDIA/SkillSpector v2.12.0 CLI Integration, SHA-256 Skill Cache & microsoft/SkillOpt Trigger Optimizer."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any, cast

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASELINE = ROOT / ".skillspector-baseline.yaml"
CACHE_SCHEMA_VERSION = 1
MAX_FILES_PER_COLLECTION_BATCH = 140
EXCLUDED_STAGE_DIRS: frozenset[str] = frozenset(
    {
        "node_modules",
        ".git",
        "__pycache__",
        ".venv",
        ".pytest_cache",
        "dist",
        ".cache",
        ".next",
        ".turbo",
    }
)

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


def resolve_cache_file() -> Path:
    override = (os.environ.get("W0M_SKILLSPECTOR_CACHE_FILE") or "").strip()
    if override:
        p = Path(override)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    cache_dir = Path.home() / ".cache" / "w0m"
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        cache_dir = Path("/tmp/w0m-skillspector-cache")
        cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "skillspector-v1.json"


def iter_clean_skill_files(skill_dir: Path) -> list[Path]:
    """Return sorted regular files under `skill_dir`, skipping dependency/build directories (`node_modules`, `.git`, etc.)."""
    files: list[Path] = []
    for p in sorted(skill_dir.rglob("*")):
        rel_parts = p.relative_to(skill_dir).parts
        if any(part in EXCLUDED_STAGE_DIRS for part in rel_parts):
            continue
        if p.is_symlink() or not p.is_file():
            continue
        files.append(p)
    return files


def compute_skill_tree_sha256(skill_dir: Path) -> tuple[str, int]:
    """Compute a deterministic SHA-256 digest and file count over all clean files in `skill_dir`."""
    files = iter_clean_skill_files(skill_dir)
    h = hashlib.sha256()
    for p in files:
        rel = p.relative_to(skill_dir).as_posix()
        h.update(rel.encode("utf-8") + b"\0")
        h.update(p.read_bytes() + b"\0")
    return h.hexdigest(), len(files)


def stage_clean_skill_tree(src_dir: Path, dst_dir: Path) -> int:
    """Copy only clean authored/vendored skill files (excluding `node_modules/`, `.git/`, etc.) into `dst_dir`."""
    files = iter_clean_skill_files(src_dir)
    for src_file in files:
        rel = src_file.relative_to(src_dir)
        target_file = dst_dir / rel
        target_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, target_file)
    return len(files)


def load_skill_cache(cache_path: Path) -> dict[str, dict[str, Any]]:
    if not cache_path.is_file():
        return {}
    try:
        raw = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict) or raw.get("schema") != CACHE_SCHEMA_VERSION:
        return {}
    entries = raw.get("entries")
    return dict(entries) if isinstance(entries, dict) else {}


def save_skill_cache(cache_path: Path, entries: dict[str, dict[str, Any]]) -> None:
    payload = {
        "schema": CACHE_SCHEMA_VERSION,
        "entries": entries,
    }
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(cache_path)
    except OSError:
        pass


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
    sc9_exclusions = [
        str(cast(dict[str, Any], item.get("location") or {}).get("file", ""))
        for item in issues
        if str(item.get("id", "")).upper() == "SC9"
    ]
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
        or str(item.get("id", "")).upper() == "SC9"
    ]
    score = int(risk.get("score") or 0)
    exec_ok = bool(payload.get("execution_successful", True))
    is_collection = target.is_dir() and not (target / "SKILL.md").exists()
    verdict = (
        ("REJECT" if len(crit_or_high) > 0 else "APPROVE")
        if is_collection
        else classify_inspector_verdict(score, len(crit_or_high))
    )
    passed = exec_ok and len(crit_or_high) == 0 and len(sc9_exclusions) == 0
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
        "sc9_excluded_count": len(sc9_exclusions),
        "sc9_excluded_files": sc9_exclusions,
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
    """Invoke the real `NVIDIA/SkillSpector` CLI (`skillspector scan --no-llm --format json`) on a clean staged copy."""
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
            "sc9_excluded_count": 0,
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
            "sc9_excluded_count": 0,
            "critical_or_high_count": 0,
            "unsuppressed_high_or_critical": [],
        }

    with tempfile.TemporaryDirectory(prefix="w0m-skillspector-") as tmp_dir:
        tmp_root = Path(tmp_dir)
        scan_path = target
        if target.is_dir():
            scan_path = tmp_root / "staged"
            scan_path.mkdir(parents=True, exist_ok=True)
            stage_clean_skill_tree(target, scan_path)

        out_path = tmp_root / "report.json"
        cmd: list[str] = [
            binary,
            "scan",
            str(scan_path),
            "--no-llm",
            "--format",
            "json",
            "--output",
            str(out_path),
        ]
        if recursive:
            cmd.append("--recursive")
        if baseline is not None and baseline.exists() and not recursive:
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
                "sc9_excluded_count": 0,
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
                "sc9_excluded_count": 0,
                "critical_or_high_count": 0,
                "unsuppressed_high_or_critical": [],
            }

        raw_payload = cast(dict[str, Any], json.loads(out_path.read_text(encoding="utf-8")))
        summary = summarize_skillspector_payload(
            raw_payload,
            target=target,
            scanner_binary=binary,
            baseline=baseline if (baseline is not None and baseline.exists() and not recursive) else None,
        )
        return summary


def discover_skill_dirs(roots: list[Path]) -> list[tuple[str, Path, str, int]]:
    """Discover unique `(slot_key, skill_dir, tree_sha256, file_count)` entries across `roots`, deduplicating identical SHA-256 skill trees."""
    by_digest: dict[str, tuple[str, Path, str, int]] = {}
    used_slots: set[str] = set()
    for root_dir in roots:
        if not root_dir.is_dir():
            continue
        for child in sorted(root_dir.iterdir()):
            if not child.is_dir() or not (child / "SKILL.md").exists():
                continue
            digest, file_count = compute_skill_tree_sha256(child)
            if digest in by_digest:
                continue
            slot = child.name
            idx = 2
            while slot in used_slots:
                slot = f"{child.name}__{idx}"
                idx += 1
            used_slots.add(slot)
            by_digest[digest] = (slot, child, digest, file_count)
    return sorted(by_digest.values(), key=lambda x: x[0])


def run_estate_deep_scan(
    *,
    estate_root: Path | None = None,
    extra_roots: list[Path] | None = None,
    baseline: Path | None = None,
    no_cache: bool = False,
    cache_file: Path | None = None,
    scanner_fn: Any = None,
) -> dict[str, Any]:
    """Scan all unique skill trees across `w0m-skills/skills` and `.agents/skills` without `node_modules` cap exhaustion (`0` SC9 skips)."""
    base = estate_root if estate_root is not None else ROOT
    binary = resolve_skillspector_binary()
    if binary is None and scanner_fn is None:
        return {
            "passed": False,
            "verdict": "REJECT",
            "target": str(base),
            "scanner_binary": None,
            "error": "NVIDIA/SkillSpector CLI (`skillspector`) not found on PATH.",
            "total_unique_skills": 0,
            "cached_skills": 0,
            "scanned_skills": 0,
            "sc9_excluded_count": 0,
            "critical_or_high_count": 0,
            "unsuppressed_high_or_critical": [],
        }

    roots = [
        base / "w0m-skills" / "skills",
        base / ".agents" / "skills",
    ]
    if extra_roots:
        roots.extend(extra_roots)

    baseline_path = baseline if (baseline is not None and baseline.exists()) else None
    baseline_sha = (
        hashlib.sha256(baseline_path.read_bytes()).hexdigest()[:16]
        if baseline_path is not None
        else "no-baseline"
    )
    scanner_id = str(binary or "custom-scanner")
    cache_path = cache_file if cache_file is not None else resolve_cache_file()
    cache_entries = {} if no_cache else load_skill_cache(cache_path)

    unique_skills = discover_skill_dirs(roots)
    if not unique_skills:
        return {
            "passed": False,
            "verdict": "REJECT",
            "target": str(base),
            "scanner_binary": scanner_id,
            "error": f"No skills discovered across {[str(r) for r in roots]}",
            "total_unique_skills": 0,
            "cached_skills": 0,
            "scanned_skills": 0,
            "sc9_excluded_count": 0,
            "critical_or_high_count": 0,
            "unsuppressed_high_or_critical": [],
        }

    uncached: list[tuple[str, Path, str, int]] = []
    cached_count = 0
    for item in unique_skills:
        slot, sdir, digest, fcount = item
        ckey = f"{digest}:{baseline_sha}"
        hit = cache_entries.get(ckey)
        if isinstance(hit, dict) and hit.get("passed") is True:
            cached_count += 1
        else:
            uncached.append(item)

    all_crit_high: list[dict[str, Any]] = []
    sc9_total = 0
    suppressed_total = 0
    active_issues_total = 0
    batches_run = 0

    # Chunk uncached skills into bounded-file collection batches (`<= MAX_FILES_PER_COLLECTION_BATCH`)
    # so `NVIDIA/SkillSpector` compiles YARA + tree-sitter once per batch and NEVER hits SC9 file-count caps.
    batches: list[list[tuple[str, Path, str, int]]] = []
    cur_batch: list[tuple[str, Path, str, int]] = []
    cur_files = 0
    for item in uncached:
        fcount = item[3]
        if cur_batch and (cur_files + fcount > MAX_FILES_PER_COLLECTION_BATCH):
            batches.append(cur_batch)
            cur_batch = [item]
            cur_files = fcount
        else:
            cur_batch.append(item)
            cur_files += fcount
    if cur_batch:
        batches.append(cur_batch)

    run_scan = scanner_fn if scanner_fn is not None else run_nvidia_skillspector_cli
    cache_dirty = False

    for batch in batches:
        batches_run += 1
        with tempfile.TemporaryDirectory(prefix="w0m-skillspector-batch-") as tmp_dir:
            stage_root = Path(tmp_dir) / "collection"
            stage_root.mkdir(parents=True, exist_ok=True)
            for slot, sdir, _digest, _fcount in batch:
                stage_clean_skill_tree(sdir, stage_root / slot)

            res = run_scan(stage_root, baseline=baseline_path, recursive=False)
            if "error" in res:
                return {
                    "passed": False,
                    "verdict": "REJECT",
                    "target": str(base),
                    "scanner_binary": scanner_id,
                    "error": str(res["error"]),
                    "total_unique_skills": len(unique_skills),
                    "cached_skills": cached_count,
                    "scanned_skills": len(uncached),
                    "sc9_excluded_count": int(res.get("sc9_excluded_count") or 0),
                    "critical_or_high_count": int(res.get("critical_or_high_count") or 0),
                    "unsuppressed_high_or_critical": list(res.get("unsuppressed_high_or_critical") or []),
                }

            batch_crit = list(res.get("unsuppressed_high_or_critical") or [])
            batch_sc9 = int(res.get("sc9_excluded_count") or 0)
            sc9_total += batch_sc9
            suppressed_total += int(res.get("suppressed_count") or 0)
            active_issues_total += int(res.get("active_issues_count") or 0)
            all_crit_high.extend(batch_crit)

            offending_slots = {
                str(item.get("file", "")).split("/", 1)[0]
                for item in batch_crit
                if str(item.get("file", ""))
            }
            if batch_sc9 == 0 and res.get("execution_successful", True):
                for slot, sdir, digest, fcount in batch:
                    if slot not in offending_slots:
                        cache_entries[f"{digest}:{baseline_sha}"] = {
                            "passed": True,
                            "skill": sdir.name,
                            "files": fcount,
                        }
                        cache_dirty = True

    if cache_dirty:
        merged_cache = load_skill_cache(cache_path) if no_cache else {}
        merged_cache.update(cache_entries)
        save_skill_cache(cache_path, merged_cache)

    passed = len(all_crit_high) == 0 and sc9_total == 0
    return {
        "passed": passed,
        "verdict": "APPROVE" if passed else "REJECT",
        "target": str(base),
        "baseline": str(baseline_path) if baseline_path is not None else None,
        "scanner_binary": scanner_id,
        "total_unique_skills": len(unique_skills),
        "cached_skills": cached_count,
        "scanned_skills": len(uncached),
        "batches_run": batches_run,
        "suppressed_count": suppressed_total,
        "active_issues_count": active_issues_total,
        "sc9_excluded_count": sc9_total,
        "critical_or_high_count": len(all_crit_high),
        "unsuppressed_high_or_critical": all_crit_high,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="NVIDIA/SkillSpector v2.12.0 & microsoft/SkillOpt Gate")
    parser.add_argument("--optimize-report", action="store_true", help="Print SkillOpt trigger report")
    parser.add_argument(
        "--deep",
        action="store_true",
        help="Run full NVIDIA/SkillSpector v2.12.0 AST/taint/YARA/MCP scan across clean staged w0m skills (with SHA-256 caching)",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Bypass SHA-256 per-skill verdict cache in --deep mode",
    )
    parser.add_argument(
        "--user-skills",
        action="store_true",
        help="Include ~/.gemini/skills in --deep scan",
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

    if args.target:
        target_path = Path(args.target).resolve()
        baseline_path: Path | None = Path(args.baseline).resolve() if args.baseline else None
        cli_report = run_nvidia_skillspector_cli(
            target_path,
            baseline=baseline_path,
            recursive=bool(args.recursive),
        )
        if args.json:
            print(json.dumps(cli_report, indent=2))
        elif "error" in cli_report:
            print(f"[FAIL] SkillSpector: {cli_report['error']}", file=sys.stderr)
        else:
            status_tag = "[PASS]" if cli_report["passed"] else "[FAIL]"
            print(
                f"  {status_tag} NVIDIA/SkillSpector [{cli_report['verdict']}]: target={cli_report['target']} "
                f"score={cli_report['score']}/100 ({cli_report['severity']} · {cli_report['recommendation']}) "
                f"crit/high={cli_report['critical_or_high_count']} "
                f"sc9_excluded={cli_report['sc9_excluded_count']} "
                f"active={cli_report['active_issues_count']} "
                f"suppressed={cli_report['suppressed_count']}"
            )
            if cli_report["unsuppressed_high_or_critical"]:
                print(json.dumps(cli_report["unsuppressed_high_or_critical"], indent=2))
        return 0 if cli_report["passed"] else 1

    if args.deep:
        deep_baseline: Path | None = None
        if args.baseline:
            deep_baseline = Path(args.baseline).resolve()
        elif DEFAULT_BASELINE.exists():
            deep_baseline = DEFAULT_BASELINE

        extra: list[Path] = []
        if args.user_skills:
            user_dir = Path.home() / ".gemini" / "skills"
            if user_dir.is_dir():
                extra.append(user_dir)

        deep_report = run_estate_deep_scan(
            estate_root=ROOT,
            extra_roots=extra,
            baseline=deep_baseline,
            no_cache=bool(args.no_cache),
        )
        if args.json:
            print(json.dumps(deep_report, indent=2))
        elif "error" in deep_report:
            print(f"[FAIL] SkillSpector: {deep_report['error']}", file=sys.stderr)
        else:
            status_tag = "[PASS]" if deep_report["passed"] else "[FAIL]"
            print(
                f"  {status_tag} NVIDIA/SkillSpector [{deep_report['verdict']}]: "
                f"unique_skills={deep_report['total_unique_skills']} "
                f"(cached={deep_report['cached_skills']}, scanned={deep_report['scanned_skills']}, "
                f"batches={deep_report['batches_run']}) "
                f"crit/high={deep_report['critical_or_high_count']} "
                f"sc9_excluded={deep_report['sc9_excluded_count']} "
                f"suppressed={deep_report['suppressed_count']}"
            )
            if deep_report["unsuppressed_high_or_critical"]:
                print(json.dumps(deep_report["unsuppressed_high_or_critical"], indent=2))
        return 0 if deep_report["passed"] else 1

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
    status_tag = "[PASS]" if report["passed"] else "[FAIL]"
    print(
        f"  {status_tag} SkillSpector static gate: {report['scanned_skills']} skills scanned, "
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
