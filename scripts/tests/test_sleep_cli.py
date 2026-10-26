"""Unit tests for w0m sleep harness, multi-agent harvester, validation gate, and MLX backend (T482)."""

import json
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from sleep_harness import (
    redact_secrets,
    harvest_antigravity_sessions,
    harvest_claude_sessions,
    harvest_all_sessions,
    mine_friction_and_lessons,
    evaluate_held_out_validation_gate,
    write_sleep_proposal,
    build_parser,
    LocalMLXBackend,
    SessionDigest,
    CandidateLesson,
    TaskRecord,
    BenchmarkTask,
)


def test_cli_parser_subcommands() -> None:
    """AC1: Subcommands status, dry-run, run, harvest, adopt parse cleanly with options."""
    parser = build_parser()

    # status
    args_status = parser.parse_args(["status", "--json"])
    assert args_status.cmd == "status"
    assert args_status.json is True

    # dry-run
    args_dry = parser.parse_args(["dry-run", "--lookback-hours", "48", "--backend-url", "http://127.0.0.1:8888/v1"])
    assert args_dry.cmd == "dry-run"
    assert args_dry.lookback_hours == 48
    assert args_dry.backend_url == "http://127.0.0.1:8888/v1"

    # run
    args_run = parser.parse_args(["run", "--target-skill", "skills/w0m-sdlc-start/SKILL.md", "--auto-adopt"])
    assert args_run.cmd == "run"
    assert args_run.target_skill == "skills/w0m-sdlc-start/SKILL.md"
    assert args_run.auto_adopt is True

    # harvest
    args_harv = parser.parse_args(["harvest", "--output", "mined.json", "--lookback-hours", "24"])
    assert args_harv.cmd == "harvest"
    assert args_harv.output == "mined.json"
    assert args_harv.lookback_hours == 24

    # adopt
    args_adopt = parser.parse_args(["adopt", "--proposal", "2026-09-28-120000", "--skill", "w0m-sdlc-start"])
    assert args_adopt.cmd == "adopt"
    assert args_adopt.proposal == "2026-09-28-120000"
    assert args_adopt.skill == "w0m-sdlc-start"


def test_secrets_redaction() -> None:
    """AC2: Multi-tier secrets redaction scrubs sensitive tokens."""
    dummy_openai = "sk-" + "abcdef1234567890abcdef"
    dummy_gh = "ghp_" + "1234567890abcdef1234567890abcdef"
    dummy_sbp = "sbp_" + "abcdef1234567890abcdef1234567890"
    dummy_st = "st." + "abcdef1234567890abcdef12"

    raw_prompt = (
        f"Here is my key {dummy_openai} and my GitHub token {dummy_gh} "
        f"and Supabase token {dummy_sbp} and Infisical token {dummy_st} "
        "plus Authorization: Bearer supersecrettoken12345."
    )
    scrubbed = redact_secrets(raw_prompt)

    assert "sk-abcdef" not in scrubbed
    assert "[REDACTED_OPENAI_KEY]" in scrubbed

    assert "ghp_1234" not in scrubbed
    assert "[REDACTED_GITHUB_TOKEN]" in scrubbed

    assert "sbp_abcdef" not in scrubbed
    assert "[REDACTED_SUPABASE_TOKEN]" in scrubbed

    assert "st.abcdef" not in scrubbed
    assert "[REDACTED_INFISICAL_TOKEN]" in scrubbed

    assert "supersecrettoken" not in scrubbed
    assert "Bearer [REDACTED]" in scrubbed


def test_secrets_redaction_nested_structures() -> None:
    """Secrets redactor cleans recursive dicts and lists."""
    dummy_gh = "ghp_" + "ABCDEF1234567890ABCDEF1234567890"
    dummy_aws = "AKIA" + "1234567890ABCDEF"

    data = {
        "text": "Secret: password=SuperSecretPassword123",
        "nested": [
            {"token": dummy_gh},
            {"api_key": dummy_aws},
        ],
    }
    cleaned = redact_secrets(data)
    assert "[REDACTED]" in cleaned["text"]
    assert "[REDACTED_GITHUB_TOKEN]" in cleaned["nested"][0]["token"]
    assert "[REDACTED_AWS_KEY]" in cleaned["nested"][1]["api_key"]


def test_antigravity_harvester(tmp_path: Path) -> None:
    """AC2: Antigravity transcript.jsonl reader extracts turns and scrubs keys."""
    dummy_gh = "ghp_" + "1234567890abcdef1234567890abcdef"
    conv_dir = tmp_path / "conv-test-123"
    logs_dir = conv_dir / ".system_generated" / "logs"
    logs_dir.mkdir(parents=True)
    transcript_file = logs_dir / "transcript.jsonl"

    steps = [
        {
            "step_index": 1,
            "type": "USER_INPUT",
            "source": "USER_EXPLICIT",
            "content": f"Please inspect /Users/proto/Projects/@self/@wom and fix the bug with {dummy_gh}",
            "created_at": "2026-09-28T12:00:00Z",
        },
        {
            "step_index": 2,
            "type": "PLANNER_RESPONSE",
            "source": "MODEL",
            "content": "I am inspecting the repo.",
            "tool_calls": [
                {
                    "toolAction": "view_file",
                    "arguments": {"AbsolutePath": "/Users/proto/Projects/@self/@wom/TASKS.md"},
                }
            ],
            "created_at": "2026-09-28T12:00:05Z",
        },
        {
            "step_index": 3,
            "type": "USER_INPUT",
            "source": "USER_EXPLICIT",
            "content": "No, it's still broken, pre-commit hook failed with emoji policy check.",
            "created_at": "2026-09-28T12:01:00Z",
        },
    ]

    with open(transcript_file, "w", encoding="utf-8") as f:
        for s in steps:
            f.write(json.dumps(s) + "\n")

    digests = harvest_antigravity_sessions(
        brain_dir=tmp_path,
        target_project="/Users/proto/Projects/@self/@wom",
        lookback_hours=0,
    )

    assert len(digests) == 1
    d = digests[0]
    assert d.session_id == "agy-conv-test-123"
    assert d.n_user_turns == 2
    assert d.n_assistant_turns == 1
    assert "ghp_1234567890" not in d.user_prompts[0]
    assert "[REDACTED_GITHUB_TOKEN]" in d.user_prompts[0]
    assert "view_file" in d.tools_used
    assert "/Users/proto/Projects/@self/@wom/TASKS.md" in d.files_touched
    assert any("still broken" in s for s in d.feedback_signals)


def test_claude_harvester(tmp_path: Path) -> None:
    """AC2: Claude Code harvester extracts user/asst turns, tool use, and scrubs secrets."""
    dummy_token = "ghp_" + "9999999999abcdef9999999999abcdef"
    dummy_jwt = "eyJ" + "hbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9." + "eyJ" + "zdWIiOiIxMjM0NTY3ODkwIn0." + "dummySig12345"

    proj_dir = tmp_path / "-Users-proto-Projects--self--wom"
    proj_dir.mkdir(parents=True)
    session_file = proj_dir / "sess-abc-456.jsonl"

    records = [
        {
            "type": "user",
            "timestamp": "2026-09-28T14:00:00Z",
            "cwd": "/Users/proto/Projects/@self/@wom",
            "message": {
                "role": "user",
                "content": f"Please verify deployment with auth token {dummy_token}",
            },
        },
        {
            "type": "assistant",
            "timestamp": "2026-09-28T14:00:05Z",
            "cwd": "/Users/proto/Projects/@self/@wom",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": f"Reading config containing {dummy_jwt}"},
                    {
                        "type": "tool_use",
                        "name": "Read",
                        "input": {"file_path": "/Users/proto/Projects/@self/@wom/config.json"},
                    },
                ],
            },
        },
        {
            "type": "user",
            "timestamp": "2026-09-28T14:01:00Z",
            "cwd": "/Users/proto/Projects/@self/@wom",
            "message": {
                "role": "user",
                "content": "No, that fails with state-check failed!",
            },
        },
    ]

    with open(session_file, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    digests = harvest_claude_sessions(
        projects_dir=tmp_path,
        target_project="/Users/proto/Projects/@self/@wom",
        lookback_hours=0,
    )

    assert len(digests) == 1
    d = digests[0]
    assert d.session_id == "claude-sess-abc-456"
    assert d.n_user_turns == 2
    assert d.n_assistant_turns == 1
    # Secret redaction check (red probe)
    assert dummy_token not in d.user_prompts[0]
    assert "[REDACTED_GITHUB_TOKEN]" in d.user_prompts[0]
    assert dummy_jwt not in d.assistant_finals[0]
    assert "[REDACTED_JWT]" in d.assistant_finals[0]
    assert "Read" in d.tools_used
    assert "/Users/proto/Projects/@self/@wom/config.json" in d.files_touched
    assert any("fails" in s for s in d.feedback_signals)


def test_harvest_all_sessions_sorting(tmp_path: Path) -> None:
    """AC2: Combining Antigravity and Claude Code sessions preserves time-ordered digests."""
    brain_dir = tmp_path / "brain"
    claude_dir = tmp_path / "claude"

    # 1. Antigravity session (older)
    conv_dir = brain_dir / "conv-older" / ".system_generated" / "logs"
    conv_dir.mkdir(parents=True)
    with open(conv_dir / "transcript.jsonl", "w", encoding="utf-8") as f:
        f.write(json.dumps({
            "type": "USER_INPUT",
            "content": "Agy prompt",
            "created_at": "2026-09-28T10:00:00Z",
        }) + "\n")

    # 2. Claude session (newer)
    proj_dir = claude_dir / "-Users-proto-Projects--self--wom"
    proj_dir.mkdir(parents=True)
    with open(proj_dir / "claude-newer.jsonl", "w", encoding="utf-8") as f:
        f.write(json.dumps({
            "type": "user",
            "timestamp": "2026-09-28T15:00:00Z",
            "cwd": "/Users/proto/Projects/@self/@wom",
            "message": {"role": "user", "content": "Claude prompt"},
        }) + "\n")

    combined = harvest_all_sessions(
        brain_dir=brain_dir,
        claude_projects_dir=claude_dir,
        lookback_hours=0,
    )

    assert len(combined) == 2
    # Newer session should come first
    assert combined[0].session_id == "claude-claude-newer"
    assert combined[1].session_id == "agy-conv-older"


def test_friction_mining_and_lesson_synthesis() -> None:
    """AC3: Friction miner detects gate failures and synthesizes LESSONS.md rules."""
    digests = [
        SessionDigest(
            session_id="session-1",
            project="/Users/proto/Projects/@self/@wom",
            user_prompts=["Please commit my changes."],
            assistant_finals=["Failed: pre-commit hook failed with no-nested-repos check."],
            feedback_signals=["negative: failed"],
        ),
        SessionDigest(
            session_id="session-2",
            project="/Users/proto/Projects/@self/@wom",
            user_prompts=["Run the new command."],
            assistant_finals=["error: justfile does not contain recipe `foo`."],
            feedback_signals=["negative: error"],
        ),
        SessionDigest(
            session_id="session-3",
            project="/Users/proto/Projects/@self/@wom",
            user_prompts=["Deploy to production."],
            assistant_finals=["Blocked by DEPLOY-CONFIRM gate: requires human confirmation and Touch ID."],
            feedback_signals=["negative: blocked"],
        ),
    ]

    tasks, lessons = mine_friction_and_lessons(digests)

    assert len(tasks) == 3
    assert len(lessons) >= 3

    # Check rule synthesis format
    sdlc_lesson = next(l for l in lessons if l.category == "SDLC Toolchain")
    assert sdlc_lesson.title == "Pre-commit gate rejection"
    md = sdlc_lesson.to_markdown()
    assert "- **Problem**:" in md
    assert "- **Lesson =>**:" in md
    assert "- ⭐ **The Tell**:" in md

    # Check Human Confirmation Gate lesson
    deploy_lesson = next(l for l in lessons if l.category == "Human Confirmation Gate")
    assert deploy_lesson.title == "Agent attempted gated deploy or live migration"


def test_held_out_validation_gate() -> None:
    """AC4: Held-out validation gate passes clean skills and rejects regressed skills."""
    good_skill = """
    # w0m SDLC Lifecycle Skill
    - Run preflight fast check and load state-brief before working.
    - Verify claimed state against reality before coding (grounding).
    - Hooks are the gate: fix findings organically, never --no-verify.
    - Deploys are gated by human-confirmation and Touch ID; prompt the human.
    - Ground all decisions across 5 surfaces (single source of truth).
    - Collaborative worktree safety: surgical, file-scoped changes only.
    """

    res_good = evaluate_held_out_validation_gate(good_skill, baseline_score=1.0)
    assert res_good.passed is True
    assert res_good.action in ("accept", "accept_new_best")
    assert res_good.passed_benchmarks == 5

    # Regressed skill containing banned anti-patterns or missing invariants
    regressed_skill = """
    # Bad Skill
    - Skip preflight checks to move fast.
    - Use --no-verify on git commit to bypass pre-commit hooks.
    - Run agent deploy directly without prompting human.
    """

    res_bad = evaluate_held_out_validation_gate(regressed_skill, baseline_score=1.0)
    assert res_bad.passed is False
    assert res_bad.action == "reject"
    assert len(res_bad.regressions) > 0


def test_write_sleep_proposal(tmp_path: Path) -> None:
    """AC4 & AC5: Sleep proposal writes report.md citing T482 and manifest.json."""
    tasks = [
        TaskRecord(id="t-001", project=str(tmp_path), intent="Fix auth bug", outcome="success"),
    ]
    lessons = [
        CandidateLesson(
            category="SDLC",
            title="Always check hooks",
            problem="Pre-commit failed",
            lesson="Run hooks organically",
            tell="Hook error in log",
            source_sessions=["s1"],
        ),
    ]

    candidate_skill = """
    # Good Skill
    - preflight and state-brief grounding claimed state
    - pre-commit organic fix findings
    - human-confirmation Touch ID gated prompt the human
    - single source of truth 5 surfaces fact-checker weighted decision
    - surgical file-scoped collaborative worktree
    """

    staging_dir = write_sleep_proposal(
        tmp_path,
        tasks,
        lessons,
        candidate_skill_content=candidate_skill,
        dry_run=True,
    )
    assert staging_dir.is_dir()

    report_md = (staging_dir / "report.md").read_text(encoding="utf-8")
    assert "[[T482]]" in report_md
    assert "Always check hooks" in report_md
    assert "gate_no_regression" in report_md
    assert "security_redaction" in report_md

    manifest = json.loads((staging_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["dry_run"] is True
    assert manifest["tasks_count"] == 1
    assert len(manifest["lessons"]) == 1
    assert manifest["gate_result"]["passed"] is True


def test_local_mlx_backend_offline_and_health() -> None:
    """AC6: LocalMLXBackend handles unreachable server gracefully with offline fallback."""
    backend = LocalMLXBackend(endpoint_url="http://127.0.0.1:9999/v1", timeout_seconds=0.5)

    # Health check should return False without raising exceptions
    assert backend.check_health() is False

    # List models should return empty list without raising
    models = backend.list_models()
    assert models == []

    # Chat completion should return offline fallback message
    resp = backend.chat_completion([{"role": "user", "content": "Hello"}])
    assert "LOCAL_MLX_OFFLINE_FALLBACK" in resp


def test_adopt_skill_and_lessons_flow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC5: Adopt subcommand applies proposed lessons to LESSONS.md and updates skills."""
    from sleep_harness import main
    import sleep_harness

    monkeypatch.setattr(sleep_harness, "ROOT", tmp_path)

    # Set up mock staging proposal
    staging_dir = tmp_path / ".agents" / "reports" / "sleep" / "2026-09-28-230000"
    staging_dir.mkdir(parents=True)
    manifest = {
        "timestamp": "2026-09-28-230000",
        "dry_run": False,
        "lessons": [
            {
                "category": "SDLC Toolchain",
                "title": "Pre-commit gate rejection",
                "problem": "Hook failed",
                "lesson": "Fix hooks organically",
                "tell": "Non-zero exit",
                "source_sessions": ["sess-1"],
            }
        ],
        "tasks": [],
        "target_skill": "skills/w0m-sdlc-start/SKILL.md",
    }
    (staging_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (staging_dir / "candidate_w0m-sdlc-start.md").write_text("# Optimized w0m-sdlc-start Skill\n", encoding="utf-8")

    # Set up target skill folders
    local_skill_dir = tmp_path / ".agents" / "skills" / "w0m-sdlc-start"
    local_skill_dir.mkdir(parents=True)
    (local_skill_dir / "SKILL.md").write_text("# Old Local Skill\n", encoding="utf-8")

    canonical_skill_dir = tmp_path / "w0m-skills" / "skills" / "w0m-sdlc-start"
    canonical_skill_dir.mkdir(parents=True)
    (canonical_skill_dir / "SKILL.md").write_text("# Old Canonical Skill\n", encoding="utf-8")

    # Run adopt
    exit_code = main(["adopt", "--proposal", "2026-09-28-230000", "--skill", "w0m-sdlc-start"])
    assert exit_code == 0

    # Verify LESSONS.md was updated
    lessons_content = (tmp_path / "LESSONS.md").read_text(encoding="utf-8")
    assert "Fix hooks organically" in lessons_content
    assert "### [SDLC Toolchain] Pre-commit gate rejection" in lessons_content

    # Verify both local and canonical skill files were updated with candidate content
    assert "Optimized w0m-sdlc-start Skill" in (local_skill_dir / "SKILL.md").read_text(encoding="utf-8")
    assert "Optimized w0m-sdlc-start Skill" in (canonical_skill_dir / "SKILL.md").read_text(encoding="utf-8")

