"""Unit tests for w0m sleep harness and transcript harvester (T482)."""

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
    mine_friction_and_lessons,
    write_sleep_proposal,
    build_parser,
    SessionDigest,
    CandidateLesson,
    TaskRecord,
)


def test_cli_parser_subcommands() -> None:
    """AC1: Subcommands status, dry-run, run, harvest, adopt parse cleanly."""
    parser = build_parser()

    # status
    args_status = parser.parse_args(["status", "--json"])
    assert args_status.cmd == "status"
    assert args_status.json is True

    # dry-run
    args_dry = parser.parse_args(["dry-run", "--lookback-hours", "48"])
    assert args_dry.cmd == "dry-run"
    assert args_dry.lookback_hours == 48

    # run
    args_run = parser.parse_args(["run", "--target-skill", "skills/w0m-sdlc-start/SKILL.md", "--auto-adopt"])
    assert args_run.cmd == "run"
    assert args_run.target_skill == "skills/w0m-sdlc-start/SKILL.md"
    assert args_run.auto_adopt is True

    # harvest
    args_harv = parser.parse_args(["harvest", "--output", "mined.json"])
    assert args_harv.cmd == "harvest"
    assert args_harv.output == "mined.json"

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
    ]

    tasks, lessons = mine_friction_and_lessons(digests)

    assert len(tasks) == 2
    assert len(lessons) >= 2

    # Check rule synthesis format
    sdlc_lesson = next(l for l in lessons if l.category == "SDLC Toolchain")
    assert sdlc_lesson.title == "Pre-commit gate rejection"
    md = sdlc_lesson.to_markdown()
    assert "- **Problem**:" in md
    assert "- **Lesson =>**:" in md
    assert "- ⭐ **The Tell**:" in md


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

    staging_dir = write_sleep_proposal(tmp_path, tasks, lessons, dry_run=True)
    assert staging_dir.is_dir()

    report_md = (staging_dir / "report.md").read_text(encoding="utf-8")
    assert "[[T482]]" in report_md
    assert "Always check hooks" in report_md
    assert "gate_no_regression" in report_md

    manifest = json.loads((staging_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["dry_run"] is True
    assert manifest["tasks_count"] == 1
    assert len(manifest["lessons"]) == 1
