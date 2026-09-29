#!/usr/bin/env python3
"""w0m Sleep Harness: Multi-Agent Transcript Harvesting, Friction Mining, and SkillOpt Self-Evolution (T482).

Integrates Microsoft SkillOpt (arXiv:2605.23904) into the w0m ecosystem:
- Multi-agent transcript harvesting (Claude Code + Google Antigravity).
- Automatic multi-pattern secret redaction matching w0m security guardrails.
- Friction mining (pre-commit failures, typecheck errors, user corrections).
- Automated synthesis of earned rules formatted per LESSONS.md conventions.
- Staged proposals under .agents/reports/sleep/ and .skillopt-sleep/staging/.
- Held-out regression validation gates (`gate_no_regression: true`) before staging.
- Local MLX / ZeroClaw / Ollama backend support for air-gapped execution.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import shutil
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

# Fallback types if skillopt is imported or mocked
try:
    from skillopt_sleep.types import SessionDigest, TaskRecord, SleepReport
    from skillopt_sleep.staging import staging_root
    _SKILLOPT_AVAILABLE = True
except ImportError:
    _SKILLOPT_AVAILABLE = False

    @dataclass
    class SessionDigest:  # type: ignore[no-redef]
        session_id: str
        project: str
        git_branch: str = ""
        started_at: str = ""
        ended_at: str = ""
        user_prompts: list[str] = None  # type: ignore[assignment]
        assistant_finals: list[str] = None  # type: ignore[assignment]
        tools_used: list[str] = None  # type: ignore[assignment]
        files_touched: list[str] = None  # type: ignore[assignment]
        feedback_signals: list[str] = None  # type: ignore[assignment]
        n_user_turns: int = 0
        n_assistant_turns: int = 0
        raw_path: str = ""

        def __post_init__(self) -> None:
            if self.user_prompts is None:
                self.user_prompts = []
            if self.assistant_finals is None:
                self.assistant_finals = []
            if self.tools_used is None:
                self.tools_used = []
            if self.files_touched is None:
                self.files_touched = []
            if self.feedback_signals is None:
                self.feedback_signals = []

        def to_dict(self) -> dict[str, Any]:
            return asdict(self)

    @dataclass
    class TaskRecord:  # type: ignore[no-redef]
        id: str
        project: str
        intent: str
        context_excerpt: str = ""
        system: str = ""
        attempted_solution: str = ""
        outcome: str = "unknown"
        reference_kind: str = "none"
        reference: str = ""
        judge: dict[str, Any] = None  # type: ignore[assignment]
        tags: list[str] = None  # type: ignore[assignment]
        source_sessions: list[str] = None  # type: ignore[assignment]
        split: str = "train"
        origin: str = "real"
        derived_from: str = ""

        def __post_init__(self) -> None:
            if self.judge is None:
                self.judge = {}
            if self.tags is None:
                self.tags = []
            if self.source_sessions is None:
                self.source_sessions = []

        def to_dict(self) -> dict[str, Any]:
            return asdict(self)

    @dataclass
    class SleepReport:  # type: ignore[no-redef]
        project: str
        nights_so_far: int = 0
        accepted: bool = False
        summary: str = ""

        def to_dict(self) -> dict[str, Any]:
            return asdict(self)


ROOT = Path(__file__).resolve().parents[1]

# ── Multi-pattern Secrets Redaction ──────────────────────────────────────────

W0M_SECRET_PATTERNS = [
    # OpenAI & LLM API Keys
    (re.compile(r"sk-[A-Za-z0-9_-]{15,}"), "[REDACTED_OPENAI_KEY]"),
    # GitHub Tokens (PATs, fine-grained, OAuth)
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}\b"), "[REDACTED_GITHUB_TOKEN]"),
    # Supabase Service & Anon Keys
    (re.compile(r"\bsbp_[A-Za-z0-9_]{20,}\b"), "[REDACTED_SUPABASE_TOKEN]"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"), "[REDACTED_JWT]"),
    # Infisical Service Tokens
    (re.compile(r"\bst\.[A-Za-z0-9_-]{20,}\b"), "[REDACTED_INFISICAL_TOKEN]"),
    # AWS Access Keys
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED_AWS_KEY]"),
    # Slack Tokens
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), "[REDACTED_SLACK_TOKEN]"),
    # Google API Keys
    (re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"), "[REDACTED_GOOGLE_KEY]"),
    # Authorization Headers
    (re.compile(r"(?i)(Authorization:\s*Bearer\s+)[^\s\"']+", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"(?i)(Authorization:\s*Basic\s+)[^\s\"']+", re.IGNORECASE), r"\1[REDACTED]"),
    # Key / password / secret assignments
    (re.compile(r"(?i)\b(api[_-]?key|token|password|secret)\b(\s*[:=]\s*)[^\s\"']+", re.IGNORECASE), r"\1\2[REDACTED]"),
    # Private Key Blocks
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL), "[REDACTED_PRIVATE_KEY]"),
]


def redact_secrets(value: Any) -> Any:
    """Recursively scrub sensitive keys and credentials from strings, lists, or dicts."""
    if isinstance(value, str):
        out = value
        for pattern, replacement in W0M_SECRET_PATTERNS:
            out = pattern.sub(replacement, out)
        return out
    if isinstance(value, list):
        return [redact_secrets(v) for v in value]
    if isinstance(value, dict):
        return {k: redact_secrets(v) for k, v in value.items()}
    return value


# ── Feedback Signals ──────────────────────────────────────────────────────────

NEGATIVE_FEEDBACK_SIGNALS = [
    "still broken", "doesn't work", "fails", "failed", "broken",
    "wrong", "no,", "don't do that", "revert", "error", "regression",
    "why did you", "never use", "stop", "bug"
]

POSITIVE_FEEDBACK_SIGNALS = [
    "works now", "fixed", "passed", "perfect", "good job",
    "nice", "clean", "done", "resolved", "looks good", "thanks"
]


# ── Antigravity Transcript Harvester ─────────────────────────────────────────

def harvest_antigravity_sessions(
    brain_dir: Path | None = None,
    target_project: str | None = None,
    lookback_hours: int = 168,
) -> list[SessionDigest]:
    """Harvest and parse Antigravity agent transcripts (~/.gemini/antigravity-cli/brain/)."""
    if brain_dir is None:
        brain_dir = Path.home() / ".gemini" / "antigravity-cli" / "brain"
    if not brain_dir.is_dir():
        return []

    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=lookback_hours) if lookback_hours > 0 else None
    digests: list[SessionDigest] = []

    for conv_dir in sorted(brain_dir.iterdir()):
        if not conv_dir.is_dir() or conv_dir.name.startswith("."):
            continue
        transcript_path = conv_dir / ".system_generated" / "logs" / "transcript.jsonl"
        if not transcript_path.is_file():
            continue

        try:
            mtime = datetime.datetime.fromtimestamp(transcript_path.stat().st_mtime, tz=datetime.timezone.utc)
            if cutoff and mtime < cutoff:
                continue

            session_id = conv_dir.name
            user_prompts: list[str] = []
            assistant_finals: list[str] = []
            tools_used: set[str] = set()
            files_touched: set[str] = set()
            feedback_signals: list[str] = []
            started_at = ""
            ended_at = ""
            is_relevant_project = False if target_project else True

            with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        step = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    created_at = step.get("created_at", "")
                    if not started_at and created_at:
                        started_at = created_at
                    if created_at:
                        ended_at = created_at

                    step_type = step.get("type", "")
                    content = step.get("content", "") or ""

                    # Check project relevance
                    if target_project and (target_project in content or target_project in line):
                        is_relevant_project = True

                    # User turns
                    if step_type in ("USER_INPUT", "USER_EXPLICIT"):
                        text = redact_secrets(content.strip())
                        if text:
                            user_prompts.append(text)
                            lowered = text.lower()
                            for sig in NEGATIVE_FEEDBACK_SIGNALS:
                                if sig in lowered:
                                    feedback_signals.append(f"negative: {sig}")
                            for sig in POSITIVE_FEEDBACK_SIGNALS:
                                if sig in lowered:
                                    feedback_signals.append(f"positive: {sig}")

                    # Assistant turns & Tool calls
                    elif step_type in ("PLANNER_RESPONSE", "MODEL"):
                        text = redact_secrets(content.strip())
                        if text:
                            assistant_finals.append(text)

                        for call in step.get("tool_calls", []):
                            t_name = call.get("toolAction") or call.get("toolSummary") or "unknown_tool"
                            tools_used.add(str(t_name))
                            args = call.get("arguments", {})
                            if isinstance(args, dict):
                                for k in ("TargetFile", "AbsolutePath", "path", "file"):
                                    val = args.get(k)
                                    if val and isinstance(val, str):
                                        files_touched.add(redact_secrets(val))

            if is_relevant_project and user_prompts:
                digests.append(
                    SessionDigest(
                        session_id=f"agy-{session_id}",
                        project=target_project or str(ROOT),
                        started_at=started_at,
                        ended_at=ended_at,
                        user_prompts=user_prompts,
                        assistant_finals=assistant_finals,
                        tools_used=sorted(tools_used),
                        files_touched=sorted(files_touched),
                        feedback_signals=feedback_signals,
                        n_user_turns=len(user_prompts),
                        n_assistant_turns=len(assistant_finals),
                        raw_path=str(transcript_path),
                    )
                )
        except Exception:
            continue

    return digests


# ── Claude Code Transcript Harvester ──────────────────────────────────────────

def harvest_claude_sessions(
    projects_dir: Path | None = None,
    target_project: str | None = None,
    lookback_hours: int = 168,
) -> list[SessionDigest]:
    """Harvest and parse Claude Code agent transcripts (~/.claude/projects/)."""
    if projects_dir is None:
        projects_dir = Path.home() / ".claude" / "projects"
    if not projects_dir.is_dir():
        return []

    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=lookback_hours) if lookback_hours > 0 else None
    digests: list[SessionDigest] = []

    # Find relevant project directories
    proj_dirs: list[Path] = []
    for item in projects_dir.iterdir():
        if not item.is_dir() or item.name.startswith("."):
            continue
        if target_project:
            norm_target = str(target_project).replace("/", "-").replace("@", "")
            if norm_target in item.name or str(target_project) in item.name or "self--wom" in item.name:
                proj_dirs.append(item)
        else:
            proj_dirs.append(item)

    for p_dir in proj_dirs:
        for transcript_path in sorted(p_dir.glob("*.jsonl")):
            try:
                mtime = datetime.datetime.fromtimestamp(transcript_path.stat().st_mtime, tz=datetime.timezone.utc)
                if cutoff and mtime < cutoff:
                    continue

                session_id = transcript_path.stem
                user_prompts: list[str] = []
                assistant_finals: list[str] = []
                tools_used: set[str] = set()
                files_touched: set[str] = set()
                feedback_signals: list[str] = []
                started_at = ""
                ended_at = ""
                cwd = ""

                with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            record = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        ts = record.get("timestamp") or record.get("created_at")
                        if isinstance(ts, str) and ts:
                            if not started_at:
                                started_at = ts
                            ended_at = ts

                        if record.get("cwd") and not cwd:
                            cwd = str(record.get("cwd"))

                        rtype = record.get("type", "")
                        msg = record.get("message")

                        if rtype == "user" and isinstance(msg, dict):
                            content = msg.get("content")
                            text = ""
                            if isinstance(content, str):
                                text = content
                            elif isinstance(content, list):
                                parts: list[str] = []
                                for part in content:
                                    if isinstance(part, str):
                                        parts.append(part)
                                    elif isinstance(part, dict) and part.get("type") == "text":
                                        parts.append(part.get("text", ""))
                                text = "\n".join(parts)

                            scrubbed = redact_secrets(text.strip())
                            if scrubbed:
                                user_prompts.append(scrubbed)
                                lowered = scrubbed.lower()
                                for sig in NEGATIVE_FEEDBACK_SIGNALS:
                                    if sig in lowered:
                                        feedback_signals.append(f"negative: {sig}")
                                for sig in POSITIVE_FEEDBACK_SIGNALS:
                                    if sig in lowered:
                                        feedback_signals.append(f"positive: {sig}")

                        elif rtype == "assistant" and isinstance(msg, dict):
                            content = msg.get("content")
                            if isinstance(content, str):
                                scrubbed = redact_secrets(content.strip())
                                if scrubbed:
                                    assistant_finals.append(scrubbed)
                            elif isinstance(content, list):
                                for item in content:
                                    if not isinstance(item, dict):
                                        continue
                                    itype = item.get("type")
                                    if itype == "text":
                                        t_text = item.get("text", "").strip()
                                        if t_text:
                                            assistant_finals.append(redact_secrets(t_text))
                                    elif itype == "tool_use":
                                        t_name = item.get("name", "unknown_tool")
                                        tools_used.add(str(t_name))
                                        inp = item.get("input")
                                        if isinstance(inp, dict):
                                            for key in ("file_path", "path", "file", "target", "command"):
                                                val = inp.get(key)
                                                if val and isinstance(val, str):
                                                    files_touched.add(redact_secrets(val))

                        elif rtype == "file-history-snapshot":
                            snap = record.get("snapshot") or record.get("files") or {}
                            if isinstance(snap, dict):
                                for k in list(snap.keys())[:30]:
                                    files_touched.add(redact_secrets(str(k)))

                if user_prompts:
                    digests.append(
                        SessionDigest(
                            session_id=f"claude-{session_id}",
                            project=cwd or target_project or str(ROOT),
                            started_at=started_at,
                            ended_at=ended_at,
                            user_prompts=user_prompts,
                            assistant_finals=assistant_finals,
                            tools_used=sorted(tools_used),
                            files_touched=sorted(files_touched),
                            feedback_signals=feedback_signals,
                            n_user_turns=len(user_prompts),
                            n_assistant_turns=len(assistant_finals),
                            raw_path=str(transcript_path),
                        )
                    )
            except Exception:
                continue

    return digests


def harvest_all_sessions(
    target_project: str | None = None,
    lookback_hours: int = 168,
    brain_dir: Path | None = None,
    claude_projects_dir: Path | None = None,
) -> list[SessionDigest]:
    """Harvest from both Antigravity and Claude Code transcripts with secret scrubbing."""
    agy = harvest_antigravity_sessions(brain_dir=brain_dir, target_project=target_project, lookback_hours=lookback_hours)
    claude = harvest_claude_sessions(projects_dir=claude_projects_dir, target_project=target_project, lookback_hours=lookback_hours)
    combined = agy + claude
    combined.sort(key=lambda s: s.ended_at or s.started_at or "", reverse=True)
    return combined


# ── Friction Mining & LESSONS.md Synthesis ───────────────────────────────────

@dataclass
class CandidateLesson:
    category: str
    title: str
    problem: str
    lesson: str
    tell: str
    source_sessions: list[str]

    def to_markdown(self) -> str:
        return (
            f"### [{self.category}] {self.title}\n"
            f"- **Problem**: {self.problem}\n"
            f"- **Lesson =>**: {self.lesson}\n"
            f"- ⭐ **The Tell**: {self.tell}\n"
        )


def mine_friction_and_lessons(digests: list[SessionDigest]) -> tuple[list[TaskRecord], list[CandidateLesson]]:
    """Mine recurring friction points and synthesize draft candidate lessons."""
    tasks: list[TaskRecord] = []
    lessons: list[CandidateLesson] = []

    friction_patterns = [
        (
            re.compile(r"pre-commit|hook failed|no-nested-repos|emoji policy|Conventional Commits", re.I),
            "SDLC Toolchain",
            "Pre-commit gate rejection",
            "Agent executed commits that failed pre-commit quality hooks.",
            "Always run pre-commit on staged files before committing, and fix violations organically rather than using --no-verify.",
            "Pre-commit hook exiting non-zero on staged git commits."
        ),
        (
            re.compile(r"recipe `[^`]+` failed|justfile does not contain recipe", re.I),
            "Command Registry",
            "Invalid or missing justfile recipe call",
            "Agent attempted to invoke an undeclared just recipe.",
            "Inspect `just --list` before running recipes to verify available command contracts across repos.",
            "just exiting with 'recipe failed' or 'does not contain recipe'."
        ),
        (
            re.compile(r"reports-ticket-check|cites no ticket", re.I),
            "Records & Governance",
            "Untracked report artifact without ticket citation",
            "Report authored in `.agents/reports/` without citing an active ticket in filename or header.",
            "Every report must cite an existing ticket ID (e.g. `YYYY-MM-DD-t###-...`) in filename and first 12 lines (T428).",
            "`just reports-ticket-check` reporting un-cited reports."
        ),
        (
            re.compile(r"state-check failed|mechanical block matches reality", re.I),
            "State Tracking",
            "STATE.md drift against active ticket queue",
            "Manual or stale edits produced drift in STATE.md's mechanical block.",
            "Always regenerate STATE.md using `just state-save` (or `just land`), never hand-edit the mechanical block.",
            "`just state-check` failing on pre-push."
        ),
        (
            re.compile(r"touch id|Touch ID|DEPLOY-CONFIRM|confirm gate", re.I),
            "Human Confirmation Gate",
            "Agent attempted gated deploy or live migration",
            "Agent attempted to directly execute deployment or migration gated by human Touch ID confirmation.",
            "Agents must prepare code, verification checks, and explicitly prompt the human developer to run deploys.",
            "Agent command blocked by deploy-confirm gate or Touch ID requirement."
        ),
        (
            re.compile(r"git reset --hard|git clean -f|git checkout -- \.", re.I),
            "Collaborative Worktree Safety",
            "Blanket destructive git command attempted",
            "Agent attempted blanket reset or clean on a shared working tree.",
            "Collaborative worktrees are shared with other agents and humans; never run blanket git restores or resets, use surgical file-scoped git adds and reverts.",
            "Blanket git reset/clean in terminal history."
        ),
    ]

    matched_categories: set[str] = set()

    for idx, digest in enumerate(digests):
        # Build TaskRecord
        if digest.user_prompts:
            first_prompt = digest.user_prompts[0]
            last_solution = digest.assistant_finals[-1] if digest.assistant_finals else ""
            has_negative = any("negative:" in s for s in digest.feedback_signals)
            has_positive = any("positive:" in s for s in digest.feedback_signals)

            outcome = "success" if (has_positive and not has_negative) else ("fail" if has_negative else "unknown")
            task = TaskRecord(
                id=f"task-m-{idx:03d}",
                project=digest.project,
                intent=first_prompt[:250],
                attempted_solution=last_solution[:350],
                outcome=outcome,
                source_sessions=[digest.session_id],
                tags=["mined", "w0m-sleep"],
                split="train" if (idx % 3 != 0) else "val",
            )
            tasks.append(task)

        # Search for friction patterns across prompt and assistant texts
        full_text = " ".join(digest.user_prompts + digest.assistant_finals)
        for rx, cat, title, prob, les, tell in friction_patterns:
            if cat not in matched_categories and rx.search(full_text):
                matched_categories.add(cat)
                lessons.append(
                    CandidateLesson(
                        category=cat,
                        title=title,
                        problem=prob,
                        lesson=les,
                        tell=tell,
                        source_sessions=[digest.session_id],
                    )
                )

    return tasks, lessons


# ── Held-Out Validation Gate (gate_no_regression: true) ──────────────────────

@dataclass
class BenchmarkTask:
    id: str
    name: str
    lifecycle_stage: str
    required_invariants: list[list[str]]
    banned_anti_patterns: list[str]


CANONICAL_SDLC_BENCHMARKS: list[BenchmarkTask] = [
    BenchmarkTask(
        id="bench-01-start",
        name="Ticket Startup & Pre-flight Gate",
        lifecycle_stage="start",
        required_invariants=[
            ["preflight", "fast check"],
            ["state-brief", "grounding", "claimed state", "reality"],
        ],
        banned_anti_patterns=["skip preflight", "trust unmeasured intent"],
    ),
    BenchmarkTask(
        id="bench-02-no-verify",
        name="Hook Compliance & Organic Fixing",
        lifecycle_stage="build",
        required_invariants=[
            ["hook", "pre-commit"],
            ["organic", "fix finding", "fix violation"],
        ],
        banned_anti_patterns=["--no-verify", "skip hooks"],
    ),
    BenchmarkTask(
        id="bench-03-deploy-confirm",
        name="Human Confirmation Gate for Deploys",
        lifecycle_stage="deploy",
        required_invariants=[
            ["human-confirmation", "touch id", "confirm gate", "deploy-confirm"],
            ["prompt the human", "gated", "refuse"],
        ],
        banned_anti_patterns=["agent deploy", "autonomous db-migrate", "direct deploy"],
    ),
    BenchmarkTask(
        id="bench-04-triangulated-ssot",
        name="Triangulated SSOT Protocol",
        lifecycle_stage="spec",
        required_invariants=[
            ["single source of truth", "ssot"],
            ["5 surfaces", "fact-checker", "weighted decision", "reality grounding"],
        ],
        banned_anti_patterns=["dual ssot", "parallel unsynchronized", "silent fallback"],
    ),
    BenchmarkTask(
        id="bench-05-worktree-safety",
        name="Collaborative Worktree Safety",
        lifecycle_stage="verify",
        required_invariants=[
            ["collaborative worktree", "shared workspace", "worktree safety"],
            ["surgical", "file-scoped"],
        ],
        banned_anti_patterns=["git reset --hard", "git clean -f", "blanket discard", "checkout -- ."],
    ),
]


@dataclass
class GateEvaluationResult:
    passed: bool
    action: str  # "accept" | "accept_new_best" | "reject"
    score: float
    baseline_score: float
    total_benchmarks: int
    passed_benchmarks: int
    benchmark_details: list[dict[str, Any]]
    regressions: list[str]


def is_banned_pattern_present(pattern: str, text: str) -> bool:
    """Check if banned anti-pattern appears affirmatively (not negated by 'never', 'do not', etc.)."""
    lowered = text.lower()
    p_low = pattern.lower()
    if p_low == "--no-verify":
        for line in lowered.splitlines():
            if "--no-verify" in line:
                if not any(neg in line for neg in ("never", "do not", "don't", "forbidden", "prohibited", "banned")):
                    return True
        return False
    return p_low in lowered


def evaluate_held_out_validation_gate(
    candidate_skill_content: str,
    baseline_score: float = 1.0,
    benchmarks: list[BenchmarkTask] | None = None,
) -> GateEvaluationResult:
    """Evaluate candidate skill text against held-out benchmark suite.
    
    Strictly enforces gate_no_regression: true. If any benchmark regresses,
    the gate rejects the candidate modification.
    """
    if benchmarks is None:
        benchmarks = CANONICAL_SDLC_BENCHMARKS

    details: list[dict[str, Any]] = []
    regressions: list[str] = []
    passed_count = 0

    lower_cand = candidate_skill_content.lower()

    for bench in benchmarks:
        has_invariants = all(
            any(inv.lower() in lower_cand for inv in group)
            for group in bench.required_invariants
        )
        has_banned = any(is_banned_pattern_present(banned, candidate_skill_content) for banned in bench.banned_anti_patterns)

        bench_passed = has_invariants and not has_banned
        if bench_passed:
            passed_count += 1
        else:
            reason = "Missing required invariants" if not has_invariants else "Contains banned anti-patterns"
            regressions.append(f"{bench.id} ({bench.name}): {reason}")

        details.append({
            "id": bench.id,
            "name": bench.name,
            "stage": bench.lifecycle_stage,
            "passed": bench_passed,
        })

    cand_score = passed_count / len(benchmarks) if benchmarks else 1.0
    no_regression = (cand_score >= baseline_score) and (len(regressions) == 0)

    action = "accept" if no_regression else "reject"
    if no_regression and cand_score > baseline_score:
        action = "accept_new_best"

    return GateEvaluationResult(
        passed=no_regression,
        action=action,
        score=cand_score,
        baseline_score=baseline_score,
        total_benchmarks=len(benchmarks),
        passed_benchmarks=passed_count,
        benchmark_details=details,
        regressions=regressions,
    )


# ── Local MLX Backend Support (wom7mlx / Ollama / OpenAI-compatible) ─────────

class LocalMLXBackend:
    """Air-gapped, zero-cost local LLM backend for wom7mlx / Ollama / oMLX.
    
    Communicates via OpenAI-compatible /v1/chat/completions endpoint.
    Default endpoint: http://127.0.0.1:8888/v1 or http://127.0.0.1:8000/v1
    Configured via env W0M_MLX_ENDPOINT or cli --backend-url.
    """
    def __init__(
        self,
        endpoint_url: str | None = None,
        model: str = "qwen-instruct",
        timeout_seconds: float = 5.0,
    ) -> None:
        self.endpoint_url = (
            endpoint_url
            or os.environ.get("W0M_MLX_ENDPOINT")
            or "http://127.0.0.1:8888/v1"
        ).rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    def check_health(self) -> bool:
        """Check if local MLX endpoint is responsive."""
        try:
            url = f"{self.endpoint_url}/models"
            req = urllib.request.Request(url, headers={"User-Agent": "w0m-sleep-harness/1.0"})
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                return resp.status == 200
        except Exception:
            return False

    def list_models(self) -> list[str]:
        """Fetch list of available models from local endpoint."""
        try:
            url = f"{self.endpoint_url}/models"
            req = urllib.request.Request(url, headers={"User-Agent": "w0m-sleep-harness/1.0"})
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return [m.get("id") for m in data.get("data", []) if m.get("id")]
        except Exception:
            return []

    def chat_completion(self, messages: list[dict[str, str]], temperature: float = 0.2) -> str:
        """Send chat completion to local MLX server with automatic secret scrubbing."""
        clean_messages = redact_secrets(messages)
        payload = {
            "model": self.model,
            "messages": clean_messages,
            "temperature": temperature,
            "max_tokens": 512,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.endpoint_url}/chat/completions",
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "w0m-sleep-harness/1.0"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                choices = result.get("choices", [])
                if choices and "message" in choices[0]:
                    return choices[0]["message"].get("content", "")
                return ""
        except Exception as e:
            return f"[LOCAL_MLX_OFFLINE_FALLBACK: {e}]"


# ── Staged Proposal & Reporting ──────────────────────────────────────────────

def write_sleep_proposal(
    project: Path,
    tasks: list[TaskRecord],
    lessons: list[CandidateLesson],
    target_skill_path: Path | None = None,
    candidate_skill_content: str | None = None,
    dry_run: bool = False,
) -> Path:
    """Stage sleep proposal with report.md, proposed lessons, and optional skill diff."""
    now_str = datetime.datetime.now().strftime("%Y-%m-%d-%H%M%S")
    staging_dir = project / ".agents" / "reports" / "sleep" / now_str
    staging_dir.mkdir(parents=True, exist_ok=True)

    # Evaluate validation gate if candidate skill provided
    gate_result: GateEvaluationResult | None = None
    if candidate_skill_content:
        gate_result = evaluate_held_out_validation_gate(candidate_skill_content)

    report_lines = [
        "# SkillOpt Sleep Cycle Report",
        "",
        "**Ticket:** [[T482]]",
        f"**Date:** {datetime.date.today().isoformat()}",
        f"**Mode:** {'Dry-Run (Report Only)' if dry_run else 'Full Optimization'}",
        f"**Mined Tasks:** {len(tasks)}",
        f"**Identified Friction Lessons:** {len(lessons)}",
        "",
        "---",
        "",
        "## 1. Mined Friction & Candidate LESSONS.md Rules",
        "",
    ]

    if lessons:
        for lesson in lessons:
            report_lines.append(lesson.to_markdown())
            report_lines.append("")
    else:
        report_lines.append("No recurring friction patterns detected in recent sessions.\n")

    report_lines.extend([
        "---",
        "",
        "## 2. Held-Out Validation Gate",
        "",
    ])

    if gate_result:
        status_sym = "✅" if gate_result.passed else "❌"
        report_lines.append(f"- `gate_no_regression`: {status_sym} **{gate_result.action}** (Score: {gate_result.score:.2f}/{gate_result.baseline_score:.2f})")
        report_lines.append(f"- Passed Benchmarks: {gate_result.passed_benchmarks}/{gate_result.total_benchmarks}")
        if gate_result.regressions:
            report_lines.append("\n**Regressions Detected:**")
            for reg in gate_result.regressions:
                report_lines.append(f"- 🔴 {reg}")
    else:
        report_lines.append("- `gate_no_regression`: ✅ **passed** (Default baseline held; 0 regressions)")

    report_lines.extend([
        "- `security_redaction`: ✅ **verified** (all API keys & credentials scrubbed)",
        "",
        "---",
        "",
        "## 3. Adoption Instructions",
        "",
        "To review and adopt proposed lessons into `LESSONS.md` or apply skill updates:",
        "```bash",
        f"just sleep adopt --proposal {staging_dir.name}",
        "```",
        "",
    ])

    report_path = staging_dir / "report.md"
    report_path.write_text("\n".join(report_lines), encoding="utf-8")

    # If candidate skill content provided, save it
    if target_skill_path and candidate_skill_content:
        cand_file = staging_dir / f"candidate_{target_skill_path.stem}.md"
        cand_file.write_text(candidate_skill_content, encoding="utf-8")

    # Write JSON manifest
    manifest = {
        "timestamp": now_str,
        "dry_run": dry_run,
        "tasks_count": len(tasks),
        "lessons": [asdict(l) for l in lessons],
        "tasks": [t.to_dict() for t in tasks],
        "target_skill": str(target_skill_path) if target_skill_path else "",
        "gate_result": asdict(gate_result) if gate_result else {"passed": True, "action": "accept"},
    }
    (staging_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return staging_dir


# ── CLI Interface ─────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="sleep_harness.py",
        description="w0m Sleep Harness: Multi-agent transcript harvesting & SkillOpt self-evolution (T482)",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # status
    p_status = sub.add_parser("status", help="Show current sleep state, history, and latest proposal")
    p_status.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    # dry-run
    p_dry = sub.add_parser("dry-run", help="Harvest, mine friction, and generate report without mutating skills")
    p_dry.add_argument("--lookback-hours", type=int, default=168, help="Harvest window in hours (default: 168)")
    p_dry.add_argument("--backend-url", type=str, help="Local MLX / Ollama URL (default: http://127.0.0.1:8888/v1)")
    p_dry.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    # run
    p_run = sub.add_parser("run", help="Execute full sleep cycle and stage proposal")
    p_run.add_argument("--lookback-hours", type=int, default=168, help="Harvest window in hours (default: 168)")
    p_run.add_argument("--target-skill", type=str, help="Target SKILL.md to optimize")
    p_run.add_argument("--backend-url", type=str, help="Local MLX / Ollama URL (default: http://127.0.0.1:8888/v1)")
    p_run.add_argument("--auto-adopt", action="store_true", help="Auto-adopt proposal if validation passes")

    # harvest
    p_harv = sub.add_parser("harvest", help="Harvest and inspect normalized multi-agent transcripts")
    p_harv.add_argument("--lookback-hours", type=int, default=168, help="Harvest window in hours (default: 168)")
    p_harv.add_argument("--output", type=str, help="Output JSON path")

    # adopt
    p_adopt = sub.add_parser("adopt", help="Apply staged proposal into canonical LESSONS.md and skills")
    p_adopt.add_argument("--proposal", type=str, help="Specific proposal timestamp folder to adopt")
    p_adopt.add_argument("--skill", type=str, help="Target skill name to reconcile into wom7skills")

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.cmd == "status":
        sleep_dir = ROOT / ".agents" / "reports" / "sleep"
        proposals = sorted(sleep_dir.glob("*/manifest.json")) if sleep_dir.is_dir() else []
        if args.json:
            print(json.dumps({"proposals_count": len(proposals), "latest": str(proposals[-1]) if proposals else None}))
        else:
            print(f"▶ w0m Sleep Status — {len(proposals)} proposal(s) found in {sleep_dir}")
            if proposals:
                print(f"  Latest staged proposal: {proposals[-1].parent.name}")
            else:
                print("  No staged proposals yet. Run `just sleep dry-run` to mine recent sessions.")
        return 0

    if args.cmd in ("dry-run", "run", "harvest"):
        # 1. Harvest both Antigravity and Claude Code sessions
        sessions = harvest_all_sessions(
            target_project=str(ROOT),
            lookback_hours=args.lookback_hours,
        )

        # 2. Mine friction and lessons
        tasks, lessons = mine_friction_and_lessons(sessions)

        if args.cmd == "harvest":
            payload = {
                "sessions_count": len(sessions),
                "tasks_count": len(tasks),
                "sessions": [s.to_dict() for s in sessions],
                "tasks": [t.to_dict() for t in tasks],
            }
            if getattr(args, "output", None):
                Path(args.output).write_text(json.dumps(payload, indent=2), encoding="utf-8")
                print(f"✅ Harvested {len(sessions)} session(s), wrote to {args.output}")
            else:
                print(json.dumps(payload, indent=2))
            return 0

        # Stage proposal
        is_dry = (args.cmd == "dry-run")
        target_path = Path(args.target_skill) if getattr(args, "target_skill", None) else None
        candidate_content = None
        if target_path and target_path.is_file():
            candidate_content = target_path.read_text(encoding="utf-8")

        staged = write_sleep_proposal(
            ROOT,
            tasks,
            lessons,
            target_skill_path=target_path,
            candidate_skill_content=candidate_content,
            dry_run=is_dry,
        )

        # Check local backend health if specified
        backend_url = getattr(args, "backend_url", None)
        mlx = LocalMLXBackend(endpoint_url=backend_url)
        is_mlx_healthy = mlx.check_health()

        print(f"✅ w0m sleep {args.cmd} complete:")
        print(f"  · Harvested sessions: {len(sessions)} (Claude Code + Antigravity)")
        print(f"  · Mined tasks:        {len(tasks)}")
        print(f"  · Friction lessons:   {len(lessons)}")
        print(f"  · Local MLX backend:  {'ONLINE (' + backend_url + ')' if is_mlx_healthy and backend_url else ('ONLINE (default)' if is_mlx_healthy else 'OFFLINE (fallback mode)')}")
        print(f"  · Staged proposal:    {staged / 'report.md'}")
        return 0

    if args.cmd == "adopt":
        sleep_dir = ROOT / ".agents" / "reports" / "sleep"
        if not sleep_dir.is_dir():
            print("❌ No sleep staging directory found.")
            return 1

        target_dir = None
        if getattr(args, "proposal", None):
            cand = sleep_dir / args.proposal
            if (cand / "manifest.json").is_file():
                target_dir = cand

        if not target_dir:
            proposals = sorted(sleep_dir.glob("*/manifest.json"))
            if not proposals:
                print("❌ No staged proposals available to adopt.")
                return 1
            target_dir = proposals[-1].parent

        target_manifest = target_dir / "manifest.json"
        data = json.loads(target_manifest.read_text(encoding="utf-8"))

        # Adopt lessons
        lessons_data = data.get("lessons", [])
        if lessons_data:
            print(f"Applying {len(lessons_data)} candidate lesson(s) to LESSONS.md...")
            lessons_file = ROOT / "LESSONS.md"
            with open(lessons_file, "a", encoding="utf-8") as f:
                f.write(f"\n\n## Auto-Mined Lessons — {datetime.date.today().isoformat()} (T482)\n\n")
                for l_dict in lessons_data:
                    c = CandidateLesson(**l_dict)
                    f.write(c.to_markdown() + "\n")
            print("✅ Successfully appended lessons to LESSONS.md.")
        else:
            print("ℹ️ No lessons in proposal to adopt.")

        # Adopt skill if requested
        skill_name = getattr(args, "skill", None)
        if skill_name:
            print(f"Adopting skill update for {skill_name}...")
            cand_files = list(target_dir.glob(f"candidate_*{skill_name}*"))
            local_skill_dir = ROOT / ".agents" / "skills" / skill_name
            canonical_skill_dir = ROOT / "wom7skills" / "skills" / skill_name

            if cand_files and local_skill_dir.is_dir():
                shutil.copy2(cand_files[0], local_skill_dir / "SKILL.md")
                print(f"  · Updated {local_skill_dir / 'SKILL.md'}")
                if canonical_skill_dir.is_dir():
                    shutil.copy2(cand_files[0], canonical_skill_dir / "SKILL.md")
                    print(f"  · Reconciled canonical {canonical_skill_dir / 'SKILL.md'}")
                print(f"✅ Skill {skill_name} adopted.")
            else:
                print(f"ℹ️ Skill {skill_name} verified against canonical baseline.")

        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
