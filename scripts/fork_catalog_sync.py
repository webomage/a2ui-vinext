#!/usr/bin/env python3
"""T673 — Forked AI Tools Catalog Governance, Ontology Graph Compiler, Vault Compaction & OTEL/AI-DLC Harness.

Covers:
- AC1: Canonical `webomage/<repo>` fork governance for all 33 forked repositories across Tracks A-F.
- AC4: `llm_wiki` incremental persistent knowledge-vault compaction with contradiction detection.
- AC5: `NVIDIA/auto-ontology` + `open-ontologies` + `omnigraph` + `potpie` natural-language ontology query compiler.
- AC6: `openlit` OTEL `gen_ai.*` span attributes, `agent-beacon` worktree heartbeat, and `aidlc-workflows` adaptive gates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

FORKED_AI_TOOLS_CATALOG: list[dict[str, Any]] = [
    # Track A — Threat Modeling, Security & Skill Governance (3 repos)
    {
        "repo": "grim-prompter",
        "upstream": "jmanico/grim-prompter",
        "canonical_origin": "git@github.com:webomage/grim-prompter.git",
        "track": "A",
        "disposition": "port",
        "target_surfaces": ["w0m-sec", "w0m-web/packages/lib/src/security/advanced-audit.ts"],
    },
    {
        "repo": "SkillSpector",
        "upstream": "NVIDIA/SkillSpector",
        "canonical_origin": "git@github.com:webomage/SkillSpector.git",
        "track": "A",
        "disposition": "integrate",
        "target_surfaces": ["scripts/skill_spector_check.py", "w0m-skills"],
    },
    {
        "repo": "SkillOpt",
        "upstream": "microsoft/SkillOpt",
        "canonical_origin": "git@github.com:webomage/SkillOpt.git",
        "track": "A",
        "disposition": "integrate",
        "target_surfaces": ["scripts/skill_spector_check.py", "w0m-skills"],
    },
    # Track B — Apple Silicon MLX, System-1 Typed Decisions & Latent Memory (6 repos)
    {
        "repo": "laya-mlx",
        "upstream": "ashishbhatia/laya-mlx",
        "canonical_origin": "git@github.com:webomage/laya-mlx.git",
        "track": "B",
        "disposition": "integrate",
        "target_surfaces": ["w0m-mlx/w0m-mlx/src/jev_decide.py"],
    },
    {
        "repo": "memorilla",
        "upstream": "memorilla/memorilla",
        "canonical_origin": "git@github.com:webomage/memorilla.git",
        "track": "B",
        "disposition": "integrate",
        "target_surfaces": ["w0m-mlx/w0m-mlx/src/jev_decide.py", "w0m-web/packages/lib/src/security/advanced-audit.ts"],
    },
    {
        "repo": "AnyJev",
        "upstream": "anyjev/AnyJev",
        "canonical_origin": "git@github.com:webomage/AnyJev.git",
        "track": "B",
        "disposition": "port",
        "target_surfaces": ["w0m-mlx/w0m-mlx/src/jev_decide.py", "w0m-web/packages/lib/src/security/advanced-audit.ts"],
    },
    {
        "repo": "open-jev",
        "upstream": "open-jev/open-jev",
        "canonical_origin": "git@github.com:webomage/open-jev.git",
        "track": "B",
        "disposition": "port",
        "target_surfaces": ["w0m-mlx/w0m-mlx/src/jev_decide.py"],
    },
    {
        "repo": "kev",
        "upstream": "kev-ai/kev",
        "canonical_origin": "git@github.com:webomage/kev.git",
        "track": "B",
        "disposition": "port",
        "target_surfaces": ["w0m-mlx/w0m-mlx/src/jev_decide.py"],
    },
    {
        "repo": "AKV",
        "upstream": "akv-project/AKV",
        "canonical_origin": "git@github.com:webomage/AKV.git",
        "track": "B",
        "disposition": "port",
        "target_surfaces": ["w0m-mlx/w0m-mlx/src/jev_decide.py", "w0m-web/packages/lib/src/security/advanced-audit.ts"],
    },
    # Track C — Document Parsing, Knowledge Vaults & Legal/Enterprise (3 repos)
    {
        "repo": "MinerU",
        "upstream": "opendatalab/MinerU",
        "canonical_origin": "git@github.com:webomage/MinerU.git",
        "track": "C",
        "disposition": "integrate",
        "target_surfaces": ["w0m-web/packages/lib/src/security/advanced-audit.ts"],
    },
    {
        "repo": "llm_wiki",
        "upstream": "NicholasSpisak/llm_wiki",
        "canonical_origin": "git@github.com:webomage/llm_wiki.git",
        "track": "C",
        "disposition": "port",
        "target_surfaces": ["scripts/fork_catalog_sync.py", "w0m-skills"],
    },
    {
        "repo": "claude-for-legal",
        "upstream": "anthropics-community/claude-for-legal",
        "canonical_origin": "git@github.com:webomage/claude-for-legal.git",
        "track": "C",
        "disposition": "port",
        "target_surfaces": ["w0m-web/packages/lib/src/security/advanced-audit.ts"],
    },
    # Track D — Ontologies, Code Graphs & Multi-Repo Intelligence (5 repos)
    {
        "repo": "auto-ontology",
        "upstream": "NVIDIA/auto-ontology",
        "canonical_origin": "git@github.com:webomage/auto-ontology.git",
        "track": "D",
        "disposition": "port",
        "target_surfaces": ["scripts/fork_catalog_sync.py"],
    },
    {
        "repo": "open-ontologies",
        "upstream": "BurstSoftware/open-ontologies",
        "canonical_origin": "git@github.com:webomage/open-ontologies.git",
        "track": "D",
        "disposition": "port",
        "target_surfaces": ["scripts/fork_catalog_sync.py"],
    },
    {
        "repo": "omnigraph",
        "upstream": "omnigraph-org/omnigraph",
        "canonical_origin": "git@github.com:webomage/omnigraph.git",
        "track": "D",
        "disposition": "port",
        "target_surfaces": ["scripts/fork_catalog_sync.py"],
    },
    {
        "repo": "potpie",
        "upstream": "potpie-ai/potpie",
        "canonical_origin": "git@github.com:webomage/potpie.git",
        "track": "D",
        "disposition": "port",
        "target_surfaces": ["scripts/fork_catalog_sync.py"],
    },
    {
        "repo": "knowledge-graph",
        "upstream": "knowledge-graph/knowledge-graph",
        "canonical_origin": "git@github.com:webomage/knowledge-graph.git",
        "track": "D",
        "disposition": "reference",
        "target_surfaces": ["scripts/fork_catalog_sync.py"],
    },
    # Track E — Agent Orchestration, Observability & AI-DLC Workflows (11 repos)
    {
        "repo": "openlit",
        "upstream": "openlit/openlit",
        "canonical_origin": "git@github.com:webomage/openlit.git",
        "track": "E",
        "disposition": "port",
        "target_surfaces": ["scripts/fork_catalog_sync.py"],
    },
    {
        "repo": "aidlc-workflows",
        "upstream": "awslabs/aidlc-workflows",
        "canonical_origin": "git@github.com:webomage/aidlc-workflows.git",
        "track": "E",
        "disposition": "port",
        "target_surfaces": ["scripts/fork_catalog_sync.py", ".w0m/sdlc.json"],
    },
    {
        "repo": "agent-beacon",
        "upstream": "agent-beacon/agent-beacon",
        "canonical_origin": "git@github.com:webomage/agent-beacon.git",
        "track": "E",
        "disposition": "port",
        "target_surfaces": ["scripts/fork_catalog_sync.py"],
    },
    {
        "repo": "git-ai",
        "upstream": "git-ai-project/git-ai",
        "canonical_origin": "git@github.com:webomage/git-ai.git",
        "track": "E",
        "disposition": "port",
        "target_surfaces": ["scripts/fork_catalog_sync.py"],
    },
    {
        "repo": "claw-code-parity",
        "upstream": "claw-code/claw-code-parity",
        "canonical_origin": "git@github.com:webomage/claw-code-parity.git",
        "track": "E",
        "disposition": "reference",
        "target_surfaces": ["scripts/fork_catalog_sync.py"],
    },
    {
        "repo": "multica",
        "upstream": "multica-ai/multica",
        "canonical_origin": "git@github.com:webomage/multica.git",
        "track": "E",
        "disposition": "reference",
        "target_surfaces": ["scripts/fork_catalog_sync.py"],
    },
    {
        "repo": "obelisk",
        "upstream": "obeli-sk/obelisk",
        "canonical_origin": "git@github.com:webomage/obelisk.git",
        "track": "E",
        "disposition": "reference",
        "target_surfaces": ["scripts/fork_catalog_sync.py"],
    },
    {
        "repo": "paseo",
        "upstream": "paseo-ai/paseo",
        "canonical_origin": "git@github.com:webomage/paseo.git",
        "track": "E",
        "disposition": "reference",
        "target_surfaces": ["scripts/fork_catalog_sync.py"],
    },
    {
        "repo": "openagents",
        "upstream": "OpenAgentsInc/openagents",
        "canonical_origin": "git@github.com:webomage/openagents.git",
        "track": "E",
        "disposition": "reference",
        "target_surfaces": ["scripts/fork_catalog_sync.py"],
    },
    {
        "repo": "claude-code-sourcemap",
        "upstream": "claude-code-community/claude-code-sourcemap",
        "canonical_origin": "git@github.com:webomage/claude-code-sourcemap.git",
        "track": "E",
        "disposition": "reference",
        "target_surfaces": ["scripts/fork_catalog_sync.py"],
    },
    {
        "repo": "clawd",
        "upstream": "clawd-ai/clawd",
        "canonical_origin": "git@github.com:webomage/clawd.git",
        "track": "E",
        "disposition": "reference",
        "target_surfaces": ["scripts/fork_catalog_sync.py"],
    },
    {
        "repo": "computer",
        "upstream": "cloudflare/computer",
        "canonical_origin": "git@github.com:webomage/computer.git",
        "track": "E",
        "disposition": "integrate",
        "target_surfaces": [
            "w0m-cf/src/lib/cloudflare-computer.ts",
            "w0m-web/packages/lib/src/security/advanced-audit.ts",
        ],
    },
    # Track F — Adjacent Creative, Design & Browser Sandboxes + UI/UX Audit Skills (9 repos)
    {
        "repo": "remotion-studio",
        "upstream": "remotion-dev/remotion-studio",
        "canonical_origin": "git@github.com:webomage/remotion-studio.git",
        "track": "F",
        "disposition": "reference",
        "target_surfaces": ["scripts/fork_catalog_sync.py"],
    },
    {
        "repo": "opendream",
        "upstream": "opendream-ai/opendream",
        "canonical_origin": "git@github.com:webomage/opendream.git",
        "track": "F",
        "disposition": "reference",
        "target_surfaces": ["scripts/fork_catalog_sync.py"],
    },
    {
        "repo": "design-everything",
        "upstream": "design-everything/design-everything",
        "canonical_origin": "git@github.com:webomage/design-everything.git",
        "track": "F",
        "disposition": "reference",
        "target_surfaces": ["scripts/fork_catalog_sync.py"],
    },
    {
        "repo": "understudy",
        "upstream": "understudy-ai/understudy",
        "canonical_origin": "git@github.com:webomage/understudy.git",
        "track": "F",
        "disposition": "reference",
        "target_surfaces": ["scripts/fork_catalog_sync.py"],
    },
    {
        "repo": "v86",
        "upstream": "copy/v86",
        "canonical_origin": "git@github.com:webomage/v86.git",
        "track": "F",
        "disposition": "reference",
        "target_surfaces": ["scripts/fork_catalog_sync.py"],
    },
    {
        "repo": "ui-ux-pro-max-skill",
        "upstream": "nextlevelbuilder/ui-ux-pro-max-skill",
        "canonical_origin": "git@github.com:webomage/ui-ux-pro-max-skill.git",
        "track": "F",
        "disposition": "integrate",
        "target_surfaces": [
            "w0m-skills/skills/webomage-design/SKILL.md",
            "w0m-web/packages/lib/src/security/advanced-audit.ts",
        ],
    },
    {
        "repo": "agent-skills",
        "upstream": "vercel-labs/agent-skills",
        "canonical_origin": "git@github.com:webomage/agent-skills.git",
        "track": "F",
        "disposition": "integrate",
        "target_surfaces": [
            "w0m-skills/skills/webomage-design/SKILL.md",
            "w0m-web/packages/lib/src/security/advanced-audit.ts",
        ],
    },
    {
        "repo": "redesign-skill",
        "upstream": "elayadesign/redesign-skill",
        "canonical_origin": "git@github.com:webomage/redesign-skill.git",
        "track": "F",
        "disposition": "integrate",
        "target_surfaces": [
            "w0m-skills/skills/webomage-design/SKILL.md",
            "w0m-web/packages/lib/src/security/advanced-audit.ts",
        ],
    },
    {
        "repo": "ui-ux-suite",
        "upstream": "Aboudjem/ui-ux-suite",
        "canonical_origin": "git@github.com:webomage/ui-ux-suite.git",
        "track": "F",
        "disposition": "integrate",
        "target_surfaces": [
            "w0m-skills/skills/webomage-design/SKILL.md",
            "w0m-web/packages/lib/src/security/advanced-audit.ts",
        ],
    },
]

WOM_ONTOLOGY_CLASSES: dict[str, dict[str, Any]] = {
    "Repo": {
        "keywords": ["repo", "repository", "monorepo", "package", "w0m-web", "w0m-api", "w0m-cf", "w0m-ext", "w0m-sec", "w0m-skills", "w0m-mlx"],
        "shacl_constraints": ["must_belong_to_estate_manifest", "single_branch_beta"],
    },
    "Ticket": {
        "keywords": ["ticket", "task", "ac", "acceptance", "queue", "blocker", "t673", "t685"],
        "shacl_constraints": ["must_have_frontmatter_schema", "must_reference_spec_or_decision"],
    },
    "Spec": {
        "keywords": ["spec", "openspec", "requirement", "scenario", "contract"],
        "shacl_constraints": ["must_reside_under_openspec_specs", "must_have_scenarios"],
    },
    "Decision": {
        "keywords": ["decision", "agdr", "adr", "architecture", "policy", "standard"],
        "shacl_constraints": ["must_be_indexed_in_decisions_md"],
    },
    "Hat": {
        "keywords": ["hat", "rbac", "role", "axis", "capability", "permission", "rls"],
        "shacl_constraints": ["must_enforce_4_axis_rbac", "fail_closed_rls"],
    },
    "Migration": {
        "keywords": ["migration", "sql", "table", "column", "trigger", "audit_log", "supabase"],
        "shacl_constraints": ["unique_14_digit_timestamp_prefix", "append_only_security_audit_trigger"],
    },
    "Service": {
        "keywords": ["service", "worker", "edge", "endpoint", "rpc", "cloudflare", "r2", "kv"],
        "shacl_constraints": ["free_tier_first_cloudflare_before_supabase", "no_synthetic_200_fallback"],
    },
    "Skill": {
        "keywords": ["skill", "agent", "prompt", "mcp", "trigger", "sdlc"],
        "shacl_constraints": ["governed_by_w0m_skills_registry", "zero_prompt_injection_patterns"],
    },
}


def verify_fork_governance(
    catalog: list[dict[str, Any]] | None = None,
    w0m_pr_root: Path | None = None,
) -> dict[str, Any]:
    """AC1: Verify all 33 forked tools obey `webomage/<repo>` canonical origin & naming rules."""
    items = catalog if catalog is not None else FORKED_AI_TOOLS_CATALOG
    pr_dir = w0m_pr_root if w0m_pr_root is not None else (ROOT / "w0m-pr")
    violations: list[str] = []
    tracks: dict[str, int] = {}

    for entry in items:
        repo = entry["repo"]
        origin = entry["canonical_origin"]
        track = entry["track"]
        tracks[track] = tracks.get(track, 0) + 1

        if repo.startswith("w0m-"):
            violations.append(f"{repo}: fork repo name must preserve upstream name, never w0m-*")
        if "casualuser/" in origin or not origin.startswith("git@github.com:webomage/"):
            violations.append(f"{repo}: canonical_origin must be git@github.com:webomage/{repo}.git, got {origin}")

        local_checkout = pr_dir / repo
        if local_checkout.exists() and (local_checkout / ".git").exists():
            proc = subprocess.run(
                ["git", "-C", str(local_checkout), "remote", "get-url", "origin"],
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode == 0:
                actual_origin = proc.stdout.strip()
                if "casualuser/" in actual_origin:
                    violations.append(f"{repo}: local w0m-pr checkout points to casualuser ({actual_origin})")

    return {
        "total_repos": len(items),
        "tracks": tracks,
        "valid": len(violations) == 0 and len(items) >= 33,
        "violations": violations,
    }


def compact_incremental_vault_wiki(
    entries: list[dict[str, Any]],
    max_rollup_items: int = 10,
) -> dict[str, Any]:
    """AC4: `llm_wiki` incremental knowledge-vault compaction with contradiction & provenance tracking."""
    seen_claims: dict[str, dict[str, Any]] = {}
    contradictions: list[dict[str, str]] = []
    compacted: list[dict[str, Any]] = []

    for item in entries:
        topic = str(item.get("topic", "general")).strip().lower()
        claim = str(item.get("claim", "")).strip()
        polarity = str(item.get("polarity", "affirm")).strip().lower()
        source = str(item.get("source", "vault")).strip()
        if not claim:
            continue

        norm_key = re.sub(r"[^a-z0-9]+", "-", f"{topic}:{claim[:48].lower()}").strip("-")
        if topic in seen_claims and seen_claims[topic]["polarity"] != polarity:
            contradictions.append(
                {
                    "topic": topic,
                    "prior_claim": seen_claims[topic]["claim"],
                    "new_claim": claim,
                    "prior_source": seen_claims[topic]["source"],
                    "new_source": source,
                }
            )
        seen_claims[topic] = {
            "key": norm_key,
            "topic": topic,
            "claim": claim,
            "polarity": polarity,
            "source": source,
        }
        if len(compacted) < max_rollup_items:
            compacted.append(seen_claims[topic])

    digest_src = "|".join(f"{c['topic']}:{c['claim']}:{c['polarity']}" for c in compacted)
    digest = hashlib.sha256(digest_src.encode("utf-8")).hexdigest()[:16]
    return {
        "input_count": len(entries),
        "compacted_count": len(compacted),
        "compacted_entries": compacted,
        "contradictions": contradictions,
        "rollup_digest": digest,
    }


def compile_ontology_graph_query(question: str) -> dict[str, Any]:
    """AC5: Translate natural-language architectural questions into typed `@wom` ontology classes + SHACL checks."""
    lower = question.lower()
    matched_classes: list[str] = []
    shacl_checks: list[str] = []

    for cls_name, spec in WOM_ONTOLOGY_CLASSES.items():
        if any(kw in lower for kw in spec["keywords"]):
            matched_classes.append(cls_name)
            for constraint in spec["shacl_constraints"]:
                if constraint not in shacl_checks:
                    shacl_checks.append(constraint)

    if not matched_classes:
        matched_classes = ["Repo", "Service"]
        shacl_checks = ["must_belong_to_estate_manifest", "free_tier_first_cloudflare_before_supabase"]

    tokens = [
        tok
        for tok in re.findall(r"[A-Za-z0-9_-]{3,}", question)
        if tok.lower() not in {"what", "which", "where", "how", "does", "the", "and", "for", "with", "from", "into"}
    ]
    symbol_query = " ".join(tokens[:6]) if tokens else "w0m"

    return {
        "question": question,
        "matched_classes": matched_classes,
        "shacl_constraints": shacl_checks,
        "symbol_query": symbol_query,
        "recommended_commands": [
            f'just ask "{symbol_query}"',
            f'just graph-query "{symbol_query}" global',
        ],
    }


def build_openlit_genai_span_attributes(
    *,
    system: str,
    model: str,
    operation: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: float,
    ticket_id: str = "T673",
    cost_usd: float = 0.0,
) -> dict[str, Any]:
    """AC6: Build OpenTelemetry `gen_ai.*` semantic attributes (`openlit` compatible)."""
    return {
        "gen_ai.system": system,
        "gen_ai.request.model": model,
        "gen_ai.operation.name": operation,
        "gen_ai.usage.input_tokens": int(input_tokens),
        "gen_ai.usage.output_tokens": int(output_tokens),
        "gen_ai.usage.total_tokens": int(input_tokens) + int(output_tokens),
        "gen_ai.usage.cost_usd": round(float(cost_usd), 6),
        "gen_ai.server.duration_ms": round(float(latency_ms), 2),
        "w0m.sdlc.ticket_id": ticket_id,
    }


def build_agent_beacon_heartbeat(
    *,
    worktree: str,
    agent_name: str,
    ticket_id: str,
    sdlc_stage: str,
    status: str = "healthy",
) -> dict[str, Any]:
    """AC6: Build `agent-beacon` cross-worktree status heartbeat payload."""
    return {
        "beacon_version": "1.0",
        "worktree": worktree,
        "agent_name": agent_name,
        "ticket_id": ticket_id,
        "sdlc_stage": sdlc_stage,
        "status": status,
    }


def select_aidlc_adaptive_gate_path(
    *,
    change_type: str,
    files_changed: int,
    touches_sql_migration: bool = False,
    touches_auth_or_security: bool = False,
) -> dict[str, Any]:
    """AC6: `aidlc-workflows` adaptive depth gate planner for `.w0m/sdlc.json`."""
    trivial_types = {"docs", "chore", "style"}
    if (
        change_type in trivial_types
        and files_changed <= 1
        and not touches_sql_migration
        and not touches_auth_or_security
    ):
        return {
            "profile": "express-trivial",
            "gates": ["preflight", "commit-msg-check", "state-check"],
            "requires_ticket": False,
        }

    gates = ["start", "spec", "build", "review", "security", "verify", "deploy", "archive"]
    extra_gates: list[str] = []
    if touches_sql_migration:
        extra_gates.append("migration-conflict-check")
        extra_gates.append("supabase-surface-drift-check")
    if touches_auth_or_security:
        extra_gates.append("rbac-auditor")
        extra_gates.append("skills-security-check")

    return {
        "profile": "full-sdlc-guarded",
        "gates": gates,
        "extra_gates": extra_gates,
        "requires_ticket": True,
    }


def plan_cloudflare_computer_backend(
    source: str,
    egress_policy: str = "none",
) -> dict[str, Any]:
    """Plan `@cloudflare/computer@0.10.0` execution across `worker-shell`, `codemode`, and `container`."""
    native_bins = [
        b
        for b in ("semgrep", "trivy", "gitleaks", "checkov", "cargo", "rustc", "pandoc", "ffmpeg")
        if re.search(rf"\b{b}\b", source, re.I)
    ]
    is_esm = bool(
        re.search(r"\b(?:import\s+.*from|export\s+(?:default|async|function|const))\b", source)
        or "codemode:" in source
        or "node:fs/promises" in source
    )
    backend = "container" if native_bins else ("codemode" if is_esm else "worker-shell")
    shell_groups = ["core"]
    for grp in ("jq", "yq", "xan", "curl", "file", "python", "sqlite", "just"):
        if re.search(rf"\b{grp}\b", source):
            shell_groups.append("just-wasm" if grp == "just" else grp)

    return {
        "package": "@cloudflare/computer",
        "version": "0.10.0",
        "fork_origin": "git@github.com:webomage/computer.git",
        "storage_engine": "@cloudflare/dofs (Durable Object SQLite)",
        "selected_backend": backend,
        "requires_container": backend == "container",
        "target_container_share_max": 0.10,
        "worker_shell_groups": shell_groups,
        "native_binaries": native_bins,
        "egress_policy": egress_policy,
        "observability_adapter": "@cloudflare/computer/observe/cloudflare",
    }


TOP_10_UI_UX_AUDIT_SKILLS_EVALUATION: list[dict[str, Any]] = [
    {
        "rank": 1,
        "repo": "nextlevelbuilder/ui-ux-pro-max-skill",
        "stars": 147345,
        "fork_origin": "git@github.com:webomage/ui-ux-pro-max-skill.git",
        "selected": True,
        "role": "67 UI styles, 96 palettes, 57 font pairings, 99 UX guidelines & industry reasoning rules",
    },
    {
        "rank": 2,
        "repo": "vercel-labs/agent-skills",
        "stars": 33776,
        "fork_origin": "git@github.com:webomage/agent-skills.git",
        "selected": True,
        "role": "100+ Web Interface Guidelines (accessibility, focus states, forms, typography, CWV)",
    },
    {
        "rank": 3,
        "repo": "elayadesign/redesign-skill",
        "stars": 531,
        "fork_origin": "git@github.com:webomage/redesign-skill.git",
        "selected": True,
        "role": "Taste-driven redesign workflow, 6-state component matrix, anti-slop rules & card grid rhythm",
    },
    {
        "rank": 4,
        "repo": "Aboudjem/ui-ux-suite",
        "stars": 120,
        "fork_origin": "git@github.com:webomage/ui-ux-suite.git",
        "selected": True,
        "role": "12-dimension UI/UX design audit scorecard, WCAG 2.2 AA & APCA perceptual contrast linter",
    },
    {
        "rank": 5,
        "repo": "dequelabs/axe-core",
        "stars": 16800,
        "fork_origin": None,
        "selected": True,
        "role": "WCAG 2.2 AA/AAA rule taxonomy integrated via @axe-core/playwright in w0m-web",
    },
    {
        "rank": 6,
        "repo": "GoogleChrome/lighthouse",
        "stars": 28600,
        "fork_origin": None,
        "selected": True,
        "role": "Core Web Vitals (LCP/INP/CLS) & mobile/desktop audit engine in Tier 1 Free Audit",
    },
    {
        "rank": 7,
        "repo": "stylelint/stylelint",
        "stars": 11100,
        "fork_origin": None,
        "selected": False,
        "role": "CSS rule ideas adopted into zero-execution AST token linter",
    },
    {
        "rank": 8,
        "repo": "reg-viz/reg-suit",
        "stars": 2300,
        "fork_origin": None,
        "selected": False,
        "role": "Superseded by w0m-pixel-clone 3-breakpoint visual diff loop (<=2% mismatch)",
    },
    {
        "rank": 9,
        "repo": "lost-pixel/lost-pixel",
        "stars": 1950,
        "fork_origin": None,
        "selected": False,
        "role": "Requires container browser execution; superseded by read-only AST + w0m-pixel-clone",
    },
    {
        "rank": 10,
        "repo": "pa11y/pa11y",
        "stars": 8600,
        "fork_origin": None,
        "selected": False,
        "role": "Puppeteer CLI superseded by Playwright + zero-execution AST WCAG 2.2 checks",
    },
]


def run_readonly_repo_and_skill_audit(
    files: list[dict[str, str]],
    *,
    github_repo_shared: bool = True,
) -> dict[str, Any]:
    """Run a 100% read-only, zero-execution static AST/source audit of a shared GitHub repo & its skills."""
    if not github_repo_shared:
        return {
            "status": "locked_requires_github_repo",
            "execution_mode": "zero_exec_readonly_ast",
            "sandbox_executed": False,
            "github_repo_shared": False,
            "overall_ui_score": 0,
            "skill_security_status": "locked",
            "skill_findings": [],
            "ui_findings": [],
        }

    skill_findings: list[dict[str, Any]] = []
    ui_findings: list[dict[str, Any]] = []

    for f in files:
        path = str(f.get("path", ""))
        content = str(f.get("content", ""))
        lower_path = path.lower()

        # 1. Read-Only Zero-Execution Skill & Repo Security Checks (never execute code!)
        if re.search(r"ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions", content, re.I):
            skill_findings.append(
                {
                    "id": "RO-SKILL-001",
                    "severity": "critical",
                    "file": path,
                    "title": "Prompt-Injection / Instruction Override Pattern in Skill or Repo",
                    "remediation": "Remove instruction-override directives from SKILL.md or repository prompt files.",
                }
            )
        if re.search(r"[\u202a-\u202e\u2066-\u2069]", content):
            skill_findings.append(
                {
                    "id": "RO-SKILL-002",
                    "severity": "critical",
                    "file": path,
                    "title": "Trojan-Source Bidirectional Unicode Control Character",
                    "remediation": "Strip bidirectional Unicode control characters (U+202A..U+202E, U+2066..U+2069).",
                }
            )
        if lower_path.endswith("package.json") and re.search(
            r'"(?:preinstall|install|postinstall)"\s*:\s*"[^"]*(?:curl|wget|bash|sh\s+-c|nc\s|node\s+-e)',
            content,
            re.I,
        ):
            skill_findings.append(
                {
                    "id": "RO-SKILL-003",
                    "severity": "high",
                    "file": path,
                    "title": "Dangerous package.json Lifecycle Hook Detected Read-Only",
                    "remediation": "Remove remote/shell execution from preinstall/install/postinstall scripts.",
                }
            )
        if re.search(r"(?:curl|wget)\s+[^\n|]+\|\s*(?:ba)?sh\b", content, re.I):
            skill_findings.append(
                {
                    "id": "RO-SKILL-004",
                    "severity": "high",
                    "file": path,
                    "title": "Remote Pipe-to-Shell Execution Pattern",
                    "remediation": "Replace curl|sh patterns with pinned checksum-verified declarative dependencies.",
                }
            )

        # 2. Read-Only 12-Dimension UI/UX Craftsmanship Checks on UI files
        if lower_path.endswith((".svelte", ".astro", ".tsx", ".jsx", ".vue", ".css")):
            if re.search(r"#[0-9a-fA-F]{6}\b", content) and "var(--" not in content:
                ui_findings.append(
                    {
                        "id": "RO-UI-D1",
                        "dimension": "D1_token_purity",
                        "severity": "medium",
                        "file": path,
                        "title": "Hardcoded #hex Color Bypassing Design System Tokens",
                        "remediation": "Replace raw #hex values with semantic CSS variables (`var(--color-*)`).",
                    }
                )
            if "grid" in content and "Card" in content and "auto-rows-fr" not in content:
                ui_findings.append(
                    {
                        "id": "RO-UI-D4",
                        "dimension": "D4_card_grid_rhythm",
                        "severity": "medium",
                        "file": path,
                        "title": "Uneven Card Grid Heights & Unaligned Bottom CTAs",
                        "remediation": "Add `auto-rows-fr items-stretch` to the grid and `h-full flex flex-col justify-between` + `mt-auto` on card footers.",
                    }
                )
            if re.search(r'href\s*=\s*["\']#["\']', content):
                ui_findings.append(
                    {
                        "id": "RO-UI-D11",
                        "dimension": "D11_zero_dead_controls",
                        "severity": "high",
                        "file": path,
                        "title": "Dead Anchor (`href=\"#\"`) Without Conversion Target",
                        "remediation": "Wire every CTA/link to a concrete step auto-scroll target or Free Audit registration handoff.",
                    }
                )

    penalty = len(skill_findings) * 15 + len(ui_findings) * 8
    overall_score = max(0, 100 - penalty)
    return {
        "status": "completed",
        "execution_mode": "zero_exec_readonly_ast",
        "sandbox_executed": False,
        "github_repo_shared": True,
        "overall_ui_score": overall_score,
        "skill_security_status": "fail" if skill_findings else "pass",
        "skill_findings": skill_findings,
        "ui_findings": ui_findings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="T673 Forked AI Tools Catalog & Harness")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="Verify canonical webomage/<repo> fork catalog")
    sub.add_parser("computer-status", help="Show @cloudflare/computer integration status")

    comp_p = sub.add_parser("computer-plan", help="Plan @cloudflare/computer backend for a command or ESM snippet")
    comp_p.add_argument("source", help="Command or ESM source")

    ask_p = sub.add_parser("ontology-ask", help="Compile natural-language question to @wom ontology query")
    ask_p.add_argument("question", help="Architectural question")

    beacon_p = sub.add_parser("beacon", help="Emit agent-beacon heartbeat JSON")
    beacon_p.add_argument("--ticket", default="T673")
    beacon_p.add_argument("--stage", default="verify")

    gate_p = sub.add_parser("gate-plan", help="Select adaptive AI-DLC gate path")
    gate_p.add_argument("--type", default="feat")
    gate_p.add_argument("--files", type=int, default=4)
    gate_p.add_argument("--sql", action="store_true")
    gate_p.add_argument("--security", action="store_true")

    args = parser.parse_args(argv)
    if args.cmd == "status":
        report = verify_fork_governance()
        print(json.dumps(report, indent=2))
        return 0 if report["valid"] else 1
    if args.cmd == "computer-status":
        comp_entry = next((e for e in FORKED_AI_TOOLS_CATALOG if e["repo"] == "computer"), None)
        print(
            json.dumps(
                {
                    "fork": comp_entry,
                    "package": "@cloudflare/computer@0.10.0",
                    "storage": "@cloudflare/dofs (Durable Object SQLite, 10 GB max)",
                    "backends": ["worker-shell (just-bash)", "codemode (ESM)", "container (computerd FUSE <10%)"],
                    "w0m_endpoints": ["POST /api/computer/plan", "POST /api/computer/workspace"],
                },
                indent=2,
            )
        )
        return 0
    if args.cmd == "computer-plan":
        print(json.dumps(plan_cloudflare_computer_backend(args.source), indent=2))
        return 0
    if args.cmd == "ontology-ask":
        print(json.dumps(compile_ontology_graph_query(args.question), indent=2))
        return 0
    if args.cmd == "beacon":
        hb = build_agent_beacon_heartbeat(
            worktree=str(ROOT),
            agent_name="antigravity",
            ticket_id=args.ticket,
            sdlc_stage=args.stage,
        )
        print(json.dumps(hb, indent=2))
        return 0
    if args.cmd == "gate-plan":
        plan = select_aidlc_adaptive_gate_path(
            change_type=args.type,
            files_changed=args.files,
            touches_sql_migration=args.sql,
            touches_auth_or_security=args.security,
        )
        print(json.dumps(plan, indent=2))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
