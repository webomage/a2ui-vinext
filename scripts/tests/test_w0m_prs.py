#!/usr/bin/env python3
"""Offline test suite for T345: w0m-prs tool (AC1-AC6)."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import w0m_prs

checks = 0
fails = []

def check(label: str, cond: bool) -> None:
    global checks
    checks += 1
    if not cond:
        fails.append(label)
    print(f"  {'✓' if cond else '✗'} {label}")

def main() -> int:
    print("w0m-prs Test Suite (T345)")
    print("─" * 60)

    # 1. Existence and presets
    check("w0m_prs.py exists", (SCRIPTS / "w0m_prs.py").is_file())
    check("preset w0m-pr defined", "w0m-pr" in w0m_prs.PRESET_REPOS)
    check("preset wom7open alias defined", "wom7open" in w0m_prs.PRESET_REPOS)
    check("preset includes orca", "stablyai/orca" in w0m_prs.PRESET_REPOS["w0m-pr"])
    check("preset includes tart-guest-agent", "openai/tart-guest-agent" in w0m_prs.PRESET_REPOS["w0m-pr"])
    check("preset includes omlx", "jundot/omlx" in w0m_prs.PRESET_REPOS["w0m-pr"])
    check("preset includes mlx-vlm", "Blaizzy/mlx-vlm" in w0m_prs.PRESET_REPOS["w0m-pr"])
    check("preset includes tart", "cirruslabs/tart" in w0m_prs.PRESET_REPOS["w0m-pr"])
    check("preset includes harness2", "google-research/harness2" in w0m_prs.PRESET_REPOS["w0m-pr"])
    check("preset includes graphify", "Graphify-Labs/graphify" in w0m_prs.PRESET_REPOS["w0m-pr"])

    # 2. Search mock
    mock_res = MagicMock()
    mock_res.returncode = 0
    mock_res.stdout = json.dumps([
        {"number": 1, "title": "Test PR", "state": "OPEN", "url": "https://github.com/a/b/pull/1"}
    ])
    with patch("w0m_prs.run_cmd", return_value=mock_res):
        results = w0m_prs.search_prs(author="casualuser", limit=1)
        check("search_prs returns items", len(results) == 1)
        check("search_prs item title matches", results[0].get("title") == "Test PR")

    # 3. Audit mock
    mock_audit = MagicMock()
    mock_audit.returncode = 0
    mock_audit.stdout = json.dumps({
        "number": 62,
        "title": "feat: clipboard",
        "state": "OPEN",
        "mergeable": "MERGEABLE",
        "reviewDecision": "REVIEW_REQUIRED",
        "comments": [],
        "reviews": [{"state": "COMMENTED"}],
        "statusCheckRollup": [{"conclusion": "SUCCESS"}],
        "url": "https://github.com/openai/tart-guest-agent/pull/62"
    })
    with patch("w0m_prs.run_cmd", return_value=mock_audit):
        info = w0m_prs.audit_pr("openai/tart-guest-agent", 62)
        check("audit_pr extracts mergeable", info.get("mergeable") == "MERGEABLE")
        check("audit_pr extracts reviewDecision", info.get("reviewDecision") == "REVIEW_REQUIRED")
        check("audit_pr extracts ciStatus", info.get("ciStatus") == "PASS")
        check("audit_pr extracts feedback", "feedback" in info)

    # 3b. Feedback parsing tests
    comments_sample = [
        {"author": {"login": "casualuser"}, "body": "My own PR update?"},
        {"author": {"login": "opcode81"}, "body": "Does this support JSX? Also consider this."},
        {"author": {"login": "coderabbitai"}, "body": "```suggestion\nconst x = 1;\n```"},
    ]
    reviews_sample = [
        {"author": {"login": "AmirF194"}, "body": "I suggest replacing asserts with exceptions.", "state": "COMMENTED"}
    ]
    fb = w0m_prs.parse_feedback(comments_sample, reviews_sample, author="casualuser")
    check("parse_feedback detects human questions", fb["human_questions"] == 1)
    check("parse_feedback detects human suggestions", fb["human_suggestions"] == 1)
    check("parse_feedback detects human reviewers", "opcode81" in fb["human_reviewers"] and "AmirF194" in fb["human_reviewers"])
    check("parse_feedback detects bot suggestions", fb["bot_suggestions"] == 1)
    check("parse_feedback formats summary with badges", "❓ 1" in fb["summary"] and "💡 1" in fb["summary"])

    # 4. Report generation with Mermaid checks
    mock_report_prs = [
        {"repository": {"nameWithOwner": "stablyai/orca"}, "number": 100, "title": "Open PR", "state": "open", "createdAt": "2026-09-01T00:00:00Z"},
        {"repository": {"nameWithOwner": "openai/tart-guest-agent"}, "number": 62, "title": "Merged PR", "state": "merged", "createdAt": "2026-08-20T00:00:00Z"},
        {"repository": {"nameWithOwner": "bulwarkid/virtual-fido"}, "number": 10, "title": "Closed PR", "state": "closed", "createdAt": "2026-08-10T00:00:00Z"},
    ]
    with patch("w0m_prs.search_prs", return_value=mock_report_prs):
        captured_out = []
        args = MagicMock()
        args.author = "testuser"
        args.out = None
        with patch("builtins.print", side_effect=lambda x="": captured_out.append(str(x))):
            w0m_prs.cmd_report(args)
        report_text = "\n".join(captured_out)
        check("report contains flowchart TD", "flowchart TD" in report_text)
        check("report contains xychart-beta", "xychart-beta" in report_text)
        check("report contains flowchart LR", "flowchart LR" in report_text)
        check("report contains master table", "| Repository | # | Title | State | Created |" in report_text)

    # 5. Table generation check
    with patch("w0m_prs.search_prs", return_value=mock_report_prs):
        with patch("w0m_prs.audit_pr", return_value={"title": "Open PR", "state": "OPEN", "mergeable": "MERGEABLE", "reviewDecision": "NONE", "ciStatus": "PASS", "feedback": "❓ 1 💬 2", "url": "https://github.com/stablyai/orca/pull/100"}):
            captured_table = []
            args_table = MagicMock()
            args_table.author = "testuser"
            args_table.preset = "w0m7open"
            args_table.repo = None
            args_table.all = False
            args_table.limit = 10
            args_table.markdown = False
            with patch("builtins.print", side_effect=lambda x="": captured_table.append(str(x))):
                w0m_prs.cmd_table(args_table)
            table_text = "\n".join(captured_table)
            check("table contains headers", "Repository" in table_text and "Mergeable" in table_text and "Feedback" in table_text)
            check("table contains entry", "stablyai/orca" in table_text and "#100" in table_text and "❓ 1 💬 2" in table_text)

            # Test Markdown table mode
            captured_md = []
            args_table.markdown = True
            with patch("builtins.print", side_effect=lambda x="": captured_md.append(str(x))):
                w0m_prs.cmd_table(args_table)
            md_text = "\n".join(captured_md)
            check("markdown table contains Feedback column", "| Feedback |" in md_text)

    # 6. Fork inspection & cmd_forks mock
    mock_fork_info = {
        "repo": "orca",
        "branch": "feat/worktree",
        "upstream_ref": "upstream/main",
        "ahead_upstream": 2,
        "behind_upstream": 0,
        "has_origin_branch": True,
        "ahead_origin": 0,
        "behind_origin": 0,
        "dirty_count": 0,
        "status": "ahead upstream +2",
        "is_synced": True,
    }
    with patch("w0m_prs.inspect_fork", return_value=mock_fork_info):
        captured_forks = []
        args_forks = MagicMock()
        args_forks.dir = None
        args_forks.no_fetch = True
        args_forks.strict = False
        args_forks.markdown = False
        args_forks.json = False
        with patch("builtins.print", side_effect=lambda x="": captured_forks.append(str(x))):
            w0m_prs.cmd_forks(args_forks)
        forks_output = "\n".join(captured_forks)
        check("cmd_forks prints table header", "Repository" in forks_output and "vs Upstream" in forks_output)
        check("cmd_forks prints repo status", "orca" in forks_output and "ahead upstream +2" in forks_output)

    # 7. Fork helpers mock: fetch_fork, get_fork_info, update_fork
    mock_fetch_res = MagicMock()
    mock_fetch_res.returncode = 0
    mock_fetch_res.stdout = "origin\nupstream"
    with patch("w0m_prs.run_cmd", return_value=mock_fetch_res):
        fetch_result = w0m_prs.fetch_fork(Path("/fake/repo"))
        check("fetch_fork runs without errors", fetch_result["success"] is True)
        check("fetch_fork records remotes", "origin" in fetch_result["fetched"])

    mock_info_dict = {
        "repo": "testrepo",
        "branch": "main",
        "upstream_ref": "upstream/main",
        "ahead_upstream": 0,
        "behind_upstream": 3,
        "has_origin_branch": True,
        "ahead_origin": 0,
        "behind_origin": 0,
        "dirty_count": 0,
        "status": "behind upstream by 3",
        "is_synced": False,
    }
    with patch("w0m_prs.inspect_fork", return_value=mock_info_dict):
        with patch("w0m_prs.run_cmd", return_value=mock_fetch_res):
            info_res = w0m_prs.get_fork_info(Path("/fake/repo"))
            check("get_fork_info returns repo name", info_res["repo"] == "testrepo")
            check("get_fork_info has remotes dict", isinstance(info_res["remotes"], dict))

    # Test update_fork: dirty rejection
    mock_dirty_dict = dict(mock_info_dict, dirty_count=2)
    with patch("w0m_prs.inspect_fork", return_value=mock_dirty_dict):
        up_dirty = w0m_prs.update_fork(Path("/fake/repo"), fetch=False)
        check("update_fork rejects dirty worktree", up_dirty["success"] is False and up_dirty["action"] == "skipped_dirty")

    # Test update_fork: fast-forward on clean main
    with patch("w0m_prs.inspect_fork", return_value=mock_info_dict):
        with patch("w0m_prs.run_cmd", return_value=mock_fetch_res):
            up_clean = w0m_prs.update_fork(Path("/fake/repo"), fetch=False)
            check("update_fork fast-forwards clean branch", up_clean["success"] is True and up_clean["action"] == "fast_forwarded")

    # 8. Digest & Rising Projects tests (T583)
    mock_log_res = MagicMock()
    mock_log_res.returncode = 0
    mock_log_res.stdout = "a1b2c3d|Alice|2 days ago|feat(agent): add multi-agent task bus\nb2c3d4e|Bob|3 days ago|fix(ui): resolve layout shift"
    with patch("w0m_prs.inspect_fork", return_value=mock_info_dict):
        with patch("w0m_prs.run_cmd", return_value=mock_log_res):
            repo_digest = w0m_prs.compile_repo_digest(Path("/fake/testrepo"), days=7)
            check("compile_repo_digest returns paragraph_1 and paragraph_2", bool(repo_digest["paragraph_1"]) and bool(repo_digest["paragraph_2"]))
            check("compile_repo_digest formats 2-paragraph recent_updates_summary", "\n\n" in repo_digest["recent_updates_summary"])
            check("compile_repo_digest counts window commits", repo_digest["commits_window_count"] == 2)

    sample_trending_html = """
    <article class="Box-row">
      <h2 class="h3 lh-condensed"><a href="/stablyai/orca">stablyai / orca</a></h2>
      <p class="col-9 color-fg-muted my-1 pr-4">AI Agent Developer Desktop &amp; IDE</p>
      <span itemprop="programmingLanguage">TypeScript</span>
      <a href="/stablyai/orca/stargazers"><svg></svg> 4,620 </a>
      <a href="/stablyai/orca/forks"><svg></svg> 380 </a>
      <span class="d-inline-block float-sm-right">610 stars this week</span>
    </article>
    """
    parsed_trending = w0m_prs.parse_github_trending_html(sample_trending_html, period="weekly")
    check("parse_github_trending_html extracts repo", len(parsed_trending) == 1 and parsed_trending[0]["repo"] == "stablyai/orca")
    check("parse_github_trending_html extracts stars and velocity", parsed_trending[0]["stars"] == 4620 and parsed_trending[0]["velocity_stars"] == 610)
    check("parse_github_trending_html marks participating repo", parsed_trending[0]["participating"] is True)

    rising_offline = w0m_prs.fetch_rising_projects(period="weekly", limit=6, offline=True)
    check("fetch_rising_projects offline returns projects list", len(rising_offline["projects"]) == 6)
    check("fetch_rising_projects includes sources metadata", len(rising_offline["sources"]) >= 3)
    check("fetch_rising_projects includes star_history_url", all("star-history.com" in p["star_history_url"] for p in rising_offline["projects"]))

    # 8c. Feature Voting & Roadmap Board (T584)
    check(
        "compute_issue_vote_score weights reactions",
        w0m_prs.compute_issue_vote_score(10, 2, 1, 2) == 10 + 2 * 2 + 1 * 2 + 2,
    )
    check(
        "classify_issue_column detects shipped when closed",
        w0m_prs.classify_issue_column("CLOSED", [], None, []) == "shipped",
    )
    check(
        "classify_issue_column detects in_progress when open PR linked",
        w0m_prs.classify_issue_column("OPEN", ["enhancement"], None, [{"number": 21157, "state": "OPEN"}]) == "in_progress",
    )
    check(
        "classify_issue_column detects planned with milestone",
        w0m_prs.classify_issue_column("OPEN", ["enhancement"], "v1.2", []) == "planned",
    )
    check(
        "classify_issue_column defaults to proposed",
        w0m_prs.classify_issue_column("OPEN", ["enhancement"], None, []) == "proposed",
    )
    check(
        "classify_issue_category tags Agent & AI",
        w0m_prs.classify_issue_category("Add ZeroClaw agent connector", "MCP skill", ["agent"]) == "Agent & AI",
    )
    cleaned_summary = w0m_prs.distill_issue_card_summary(
        "Preserve effort level",
        "<kbd>[![Author](https://cdn.discordapp.com/avatars/1.png)](https://discord.com/1)</kbd>\n\nWhen resuming a Claude or Codex session, Orca should preserve the selected reasoning effort level.",
        ["enhancement"],
        [{"number": 21157, "state": "OPEN"}],
    )
    check(
        "distill_issue_card_summary strips Discord kbd badge and appends PR",
        "kbd" not in cleaned_summary and "#21157" in cleaned_summary,
    )
    board_offline = w0m_prs.fetch_repo_feature_board(repo="stablyai/orca", limit=15, offline=True)
    check("fetch_repo_feature_board enforces github_account_required policy", board_offline.get("auth_policy") == "github_account_required")
    check("fetch_repo_feature_board returns items and 4 columns", len(board_offline.get("items", [])) >= 5 and set(board_offline.get("columns", {}).keys()) == {"proposed", "planned", "in_progress", "shipped"})
    unauth_vote = w0m_prs.vote_github_issue("stablyai/orca", 190, token="")
    check("vote_github_issue rejects unauthenticated vote with 401 and github_auth_required", unauth_vote.get("ok") is False and unauth_vote.get("status") == 401 and unauth_vote.get("github_auth_required") is True)

    # 8d. Tap-Sync & Version Extraction (T595 / AgDR-0052)
    with tempfile.TemporaryDirectory() as tmp_tap_root:
        tmp_pkg = Path(tmp_tap_root) / "demo"
        tmp_pkg.mkdir()
        (tmp_pkg / "pyproject.toml").write_text('name = "demo"\nversion = "0.7.3rc1"\n', encoding="utf-8")
        check("_extract_fork_version strips rc suffix from pyproject.toml", w0m_prs._extract_fork_version(tmp_pkg) == "0.7.3")

    # 8e. New PR & Fork Branch Discovery, Zero-Token Delta Check, and Orca Sync (T599)
    sample_discovered = {
        "generatedAt": "2026-11-01T12:00:00Z",
        "author": "casualuser",
        "preset": "w0m-pr",
        "openPrCount": 1,
        "openPrs": [
            {
                "repo": "stablyai/orca",
                "number": 21157,
                "title": "feat(worktree): support macOS deep-link protocol",
                "state": "OPEN",
                "mergeable": "MERGEABLE",
                "reviewDecision": "NONE",
                "ciStatus": "PASS",
                "feedback": "-",
                "commentsCount": 2,
                "reviewsCount": 1,
                "url": "https://github.com/stablyai/orca/pull/21157",
            }
        ],
        "pendingBranchCount": 1,
        "pendingBranches": [
            {
                "fork": "laya-mlx",
                "upstream_repo": "mizorewww/laya-mlx",
                "branch": "fix/native-serve-tests-and-torchless-calibration",
                "head_sha": "baeb7b0",
                "subject": "fix: add native serve contract tests and torchless calibration fallback",
                "ahead_upstream": 1,
                "behind_upstream": 0,
                "open_prs_in_repo": 0,
                "compare_url": "https://github.com/mizorewww/laya-mlx/compare/main...webomage:fix/native-serve-tests-and-torchless-calibration?expand=1",
            }
        ],
    }
    with tempfile.TemporaryDirectory() as tmp_state_dir:
        state_file = Path(tmp_state_dir) / "prs-watch-state.json"
        d1 = w0m_prs.check_prs_delta(state_path=state_file, current_override=sample_discovered)
        check("check_prs_delta detects initial baseline as changed", d1["changed"] is True and d1["deltaCount"] == 2)
        d2 = w0m_prs.check_prs_delta(state_path=state_file, current_override=sample_discovered)
        check("check_prs_delta returns changed=False when state is unchanged", d2["changed"] is False and d2["deltaCount"] == 0)

        mutated = json.loads(json.dumps(sample_discovered))
        mutated["openPrs"][0]["commentsCount"] = 3
        d3 = w0m_prs.check_prs_delta(state_path=state_file, current_override=mutated)
        check("check_prs_delta detects comment count delta", d3["changed"] is True and "commentsCount: 2 -> 3" in d3["deltas"][0])

    orca_sync_dry = w0m_prs.sync_prs_to_orca(dry_run=True, discovered_override=sample_discovered)
    check(
        "sync_prs_to_orca dry-run builds reference URLs, task title, and precheck command",
        orca_sync_dry["ok"] is True
        and orca_sync_dry["dryRun"] is True
        and "https://github.com/stablyai/orca/pull/21157" in orca_sync_dry["referenceUrls"]
        and "check-delta" in orca_sync_dry["precheck"],
    )

    # 8e-2. T610 AC1 & AC2: Concurrent search/audit fan-out & run-use --id flag
    import time as _time

    def _slow_search_cmd(cmd, check=False, cwd=None, timeout=None):
        _time.sleep(0.05)
        m = MagicMock()
        m.returncode = 0
        repo_idx = cmd.index("-R") + 1 if "-R" in cmd else -1
        repo_str = cmd[repo_idx] if repo_idx > 0 else "unknown/repo"
        m.stdout = json.dumps([
            {"number": 10, "title": f"PR for {repo_str}", "state": "OPEN", "url": f"https://github.com/{repo_str}/pull/10"}
        ])
        return m

    t0 = _time.monotonic()
    with patch("w0m_prs.run_cmd", side_effect=_slow_search_cmd):
        preset_prs = w0m_prs.search_prs(author="casualuser", preset="w0m-pr", limit=5)
    elapsed_search = _time.monotonic() - t0
    expected_repos = w0m_prs.PRESET_REPOS["w0m-pr"]
    actual_repos = [p["repository"]["nameWithOwner"] for p in preset_prs]
    check(
        "search_prs preset runs concurrently (<0.40s for 13x50ms calls) and preserves repo order",
        elapsed_search < 0.40 and actual_repos == expected_repos,
    )

    def _slow_audit_pr(repo_name: str, pr_num: int):
        _time.sleep(0.05)
        return {
            "repo": repo_name,
            "number": pr_num,
            "title": f"Title {pr_num}",
            "state": "OPEN",
            "mergeable": "MERGEABLE",
            "reviewDecision": "NONE",
            "ciStatus": "PASS",
            "feedback": "-",
            "commentsCount": 0,
            "reviewsCount": 0,
            "url": f"https://github.com/{repo_name}/pull/{pr_num}",
        }

    eight_prs = [
        {"repository": {"nameWithOwner": "stablyai/orca"}, "number": 100 + i, "title": f"T{i}", "state": "OPEN"}
        for i in range(8)
    ]
    with tempfile.TemporaryDirectory() as empty_forks_dir:
        t1 = _time.monotonic()
        with (
            patch("w0m_prs.search_prs", return_value=eight_prs),
            patch("w0m_prs.audit_pr", side_effect=_slow_audit_pr),
            patch("w0m_prs.discover_worktrees_summary", return_value=[]),
        ):
            disc_fast = w0m_prs.discover_new_prs_and_branches(forks_dir=Path(empty_forks_dir), fetch=False)
        elapsed_audit = _time.monotonic() - t1
    check(
        "discover_new_prs_and_branches audits PRs concurrently (<0.25s for 8x50ms calls) and preserves PR order",
        elapsed_audit < 0.25 and [p["number"] for p in disc_fast["openPrs"]] == [100 + i for i in range(8)],
    )

    rich_prs = [
        {
            "repository": {"nameWithOwner": "stablyai/orca"},
            "number": 201,
            "title": "Rich Ready PR",
            "state": "OPEN",
            "author": {"login": "casualuser"},
            "mergeable": "MERGEABLE",
            "reviewDecision": "APPROVED",
            "comments": [{"author": {"login": "reviewer1"}, "body": "Looks good?"}],
            "reviews": [],
            "statusCheckRollup": [{"name": "ci", "conclusion": "SUCCESS"}],
            "url": "https://github.com/stablyai/orca/pull/201",
        },
        {
            "repository": {"nameWithOwner": "stablyai/orca"},
            "number": 202,
            "title": "Lazy Unknown Mergeable PR",
            "state": "OPEN",
            "author": {"login": "casualuser"},
            "mergeable": "UNKNOWN",
            "reviewDecision": "",
            "comments": [],
            "reviews": [],
            "statusCheckRollup": [],
            "url": "https://github.com/stablyai/orca/pull/202",
        },
        {
            "repository": {"nameWithOwner": "openai/tart-guest-agent"},
            "number": 203,
            "title": "100+ Reviews Cap PR",
            "state": "OPEN",
            "author": {"login": "casualuser"},
            "mergeable": "MERGEABLE",
            "reviewDecision": "REVIEW_REQUIRED",
            "comments": [],
            "reviews": [{"author": {"login": "github-actions"}, "body": "ok", "state": "COMMENTED"}] * 100,
            "statusCheckRollup": [],
            "url": "https://github.com/openai/tart-guest-agent/pull/203",
        },
    ]
    audit_calls = []

    def _recording_audit(repo_name: str, pr_num: int):
        audit_calls.append((repo_name, pr_num))
        return _slow_audit_pr(repo_name, pr_num)

    with tempfile.TemporaryDirectory() as empty_forks_dir2:
        with (
            patch("w0m_prs.search_prs", return_value=rich_prs),
            patch("w0m_prs.audit_pr", side_effect=_recording_audit),
            patch("w0m_prs.discover_worktrees_summary", return_value=[]),
        ):
            disc_rich = w0m_prs.discover_new_prs_and_branches(forks_dir=Path(empty_forks_dir2), fetch=False)
    check(
        "rich gh pr list payloads skip redundant audit_pr calls unless mergeable is UNKNOWN or nested connection hits 100-item cap",
        audit_calls == [("stablyai/orca", 202), ("openai/tart-guest-agent", 203)]
        and disc_rich["openPrs"][0]["reviewDecision"] == "APPROVED"
        and disc_rich["openPrs"][0]["ciStatus"] == "PASS"
        and "❓ 1" in disc_rich["openPrs"][0]["feedback"]
        and disc_rich["openPrs"][1]["mergeable"] == "MERGEABLE",
    )

    recorded_orca_cmds = []

    def _fake_orca_run_cmd(cmd, check=False, cwd=None, timeout=None):
        recorded_orca_cmds.append(list(cmd))
        m = MagicMock()
        m.returncode = 0
        m.stderr = ""
        if "run-list" in cmd:
            m.stdout = json.dumps({"ok": True, "result": {"runs": [{"id": "run_t610", "objective": "w0m Upstream PRs Tracker"}]}})
        elif "task-list" in cmd:
            m.stdout = json.dumps({"ok": True, "result": {"tasks": []}})
        elif "task-create" in cmd:
            m.stdout = json.dumps({"ok": True, "result": {"task": {"id": "task_t610"}}})
        elif "automations" in cmd and "list" in cmd:
            m.stdout = json.dumps({
                "ok": True,
                "result": {"automations": [{"id": "auto_t610", "name": "w0m Upstream PRs & Fork Branches Monitor", "agentId": "antigravity"}]},
            })
        else:
            m.stdout = json.dumps({"ok": True, "result": {}})
        return m

    with tempfile.TemporaryDirectory() as tmp_orca_state:
        tmp_state_path = Path(tmp_orca_state) / "state.json"
        with (
            patch("w0m_prs.run_cmd", side_effect=_fake_orca_run_cmd),
            patch("w0m_prs.resolve_orca_bin", return_value="/tmp/orca-shim"),
            patch("w0m_prs.resolve_agent_provider", return_value="antigravity"),
            patch("w0m_prs.check_prs_delta", side_effect=lambda **kw: {"changed": False}),
        ):
            live_sync = w0m_prs.sync_prs_to_orca(dry_run=False, discovered_override=sample_discovered)
        run_use_cmds = [c for c in recorded_orca_cmds if "run-use" in c]
        check(
            "sync_prs_to_orca binds existing run with `orchestration run-use --id <run_id>` (not --run)",
            len(run_use_cmds) == 1
            and "--id" in run_use_cmds[0]
            and "run_t610" in run_use_cmds[0]
            and "--run" not in run_use_cmds[0]
            and live_sync["orchestrationTaskId"] == "task_t610",
        )

    # 8f. Contribution Proposals & Owner-Confirmed Submission Gate (T593, T608, T621)
    proposals_list = w0m_prs.build_pr_proposals()
    check(
        "build_pr_proposals returns 27 contribution proposals including T608, T618, T621, T635, and T638 PRs",
        len(proposals_list) == 27
        and any(p["key"] == "stablyai/orca:feat/nested-subfolder-git-and-sdlc-repo" for p in proposals_list)
        and any(p["key"] == "stablyai/orca:feat/mobile-session-tab-reorder" for p in proposals_list)
        and any(p["key"] == "stablyai/orca:feat/mobile-terminal-triple-tap-enter" for p in proposals_list),
    )
    check(
        "build_pr_proposals formats structured Why / What For / How markdown body",
        all(
            "## Why (Rationale & Problem)" in p["body"]
            and "## What For (Use Cases & Value)" in p["body"]
            and "## How (Implementation, Invariants & Verification)" in p["body"]
            for p in proposals_list
        ),
    )
    triple_tap_props = w0m_prs.build_pr_proposals(branch_filter="triple-tap")
    t621_props = w0m_prs.build_pr_proposals(branch_filter="t621")
    check(
        "build_pr_proposals resolves case-insensitive keyword ('triple-tap') and ticket ('t621') filters cleanly",
        len(triple_tap_props) == 1
        and triple_tap_props[0]["key"] == "stablyai/orca:feat/mobile-terminal-triple-tap-enter"
        and len(t621_props) == 1
        and t621_props[0]["key"] == "stablyai/orca:feat/mobile-terminal-triple-tap-enter",
    )
    submit_dry = w0m_prs.submit_prepared_prs(dry_run=True)
    check(
        "submit_prepared_prs dry-run marks matched branch DRY_RUN_READY",
        submit_dry["ok"] is True
        and submit_dry["dryRun"] is True
        and any(r["key"] == "mizorewww/laya-mlx:fix/native-serve-tests-and-torchless-calibration" and r["status"] == "DRY_RUN_READY" for r in submit_dry["results"]),
    )
    with patch.dict("os.environ", {"CLAUDECODE": "1"}, clear=False):
        submit_agent_refused = w0m_prs.submit_prepared_prs(dry_run=False)
        check(
            "submit_prepared_prs live mode refuses agent sessions (T435 gate)",
            submit_agent_refused["ok"] is False and "REFUSED-AGENT" in str(submit_agent_refused.get("error", "")),
        )

    # 8g. Post-rebase PR obsolescence, fork alignment, collapsed launch reports & settled run close (T613)
    with tempfile.TemporaryDirectory() as tmp_git_root:
        groot = Path(tmp_git_root)
        upstream_repo = groot / "upstream"
        fork_repo = groot / "fork"
        upstream_repo.mkdir()
        subprocess.run(["git", "-C", str(upstream_repo), "init", "-b", "main"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(upstream_repo), "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(upstream_repo), "config", "user.name", "Test"], check=True)
        (upstream_repo / "app.txt").write_text("line1\nline2\nline3\nline4\nline5\n", encoding="utf-8")
        (upstream_repo / "old_workflow.yml").write_text("legacy: true\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(upstream_repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(upstream_repo), "commit", "-m", "init"], check=True, capture_output=True)

        subprocess.run(["git", "clone", "--quiet", str(upstream_repo), str(fork_repo)], check=True)
        subprocess.run(["git", "-C", str(fork_repo), "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(fork_repo), "config", "user.name", "Test"], check=True)
        subprocess.run(["git", "-C", str(fork_repo), "remote", "add", "upstream", str(upstream_repo)], check=True)

        # Branch 1: patch-equivalent (cherry-merged upstream)
        subprocess.run(["git", "-C", str(fork_repo), "checkout", "-q", "-b", "feat/patch-eq", "main"], check=True)
        (fork_repo / "feature.txt").write_text("hello world\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(fork_repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(fork_repo), "commit", "-m", "feat: add feature"], check=True, capture_output=True)

        # Branch 2: empty-after-rebase (upstream lands identical result via two commits so patch-id differs)
        subprocess.run(["git", "-C", str(fork_repo), "checkout", "-q", "-b", "feat/tree-eq", "main"], check=True)
        (fork_repo / "same.txt").write_text("partA\npartB\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(fork_repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(fork_repo), "commit", "-m", "feat: combined same"], check=True, capture_output=True)

        # Branch 3: cleanly rebaseable (even when upstream deletes unrelated old_workflow.yml)
        subprocess.run(["git", "-C", str(fork_repo), "checkout", "-q", "-b", "feat/clean-rebase", "main"], check=True)
        (fork_repo / "independent.txt").write_text("independent\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(fork_repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(fork_repo), "commit", "-m", "feat: independent"], check=True, capture_output=True)

        # Branch 3b: cleanly rebaseable with non-overlapping edit in app.txt
        subprocess.run(["git", "-C", str(fork_repo), "checkout", "-q", "-b", "feat/clean-same-file", "main"], check=True)
        (fork_repo / "app.txt").write_text("line1\nline2\nline3\nline4\nfork-line5\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(fork_repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(fork_repo), "commit", "-m", "feat: edit line5"], check=True, capture_output=True)

        # Branch 4: conflicting with upstream
        subprocess.run(["git", "-C", str(fork_repo), "checkout", "-q", "-b", "feat/conflict", "main"], check=True)
        (fork_repo / "app.txt").write_text("fork-conflicting-line1\nline2\nline3\nline4\nline5\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(fork_repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(fork_repo), "commit", "-m", "feat: conflicting change"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(fork_repo), "checkout", "-q", "main"], check=True)

        # Advance upstream: merge patch-eq content, delete old_workflow.yml, land same.txt in 2 commits, and modify app.txt line1
        (upstream_repo / "feature.txt").write_text("hello world\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(upstream_repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(upstream_repo), "commit", "-m", "upstream: feature"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(upstream_repo), "rm", "-q", "old_workflow.yml"], check=True)
        subprocess.run(["git", "-C", str(upstream_repo), "commit", "-m", "upstream: drop old workflow"], check=True, capture_output=True)
        (upstream_repo / "same.txt").write_text("partA\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(upstream_repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(upstream_repo), "commit", "-m", "upstream: partA"], check=True, capture_output=True)
        (upstream_repo / "same.txt").write_text("partA\npartB\n", encoding="utf-8")
        (upstream_repo / "app.txt").write_text("upstream-line1\nline2\nline3\nline4\nline5\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(upstream_repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(upstream_repo), "commit", "-m", "upstream: partB and app"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(fork_repo), "fetch", "upstream", "--quiet"], check=True)

        objs_before = subprocess.run(
            ["git", "-C", str(fork_repo), "count-objects"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        align_patch = w0m_prs.evaluate_pr_alignment(fork_repo, "feat/patch-eq", "upstream/main")
        check(
            "evaluate_pr_alignment detects OBSOLETE_PATCH_EQUIVALENT",
            align_patch["isObsolete"] is True and align_patch["alignmentStatus"] == "OBSOLETE_PATCH_EQUIVALENT",
        )
        align_tree = w0m_prs.evaluate_pr_alignment(fork_repo, "feat/tree-eq", "upstream/main")
        check(
            "evaluate_pr_alignment detects OBSOLETE_EMPTY_AFTER_REBASE via 3-way merge-tree",
            align_tree["isObsolete"] is True and align_tree["alignmentStatus"] == "OBSOLETE_EMPTY_AFTER_REBASE",
        )
        align_clean = w0m_prs.evaluate_pr_alignment(fork_repo, "feat/clean-rebase", "upstream/main")
        check(
            "evaluate_pr_alignment detects CLEAN_REBASEABLE when upstream deletes unrelated files",
            align_clean["isObsolete"] is False and align_clean["alignmentStatus"] == "CLEAN_REBASEABLE",
        )
        align_same_file = w0m_prs.evaluate_pr_alignment(fork_repo, "feat/clean-same-file", "upstream/main")
        objs_after = subprocess.run(
            ["git", "-C", str(fork_repo), "count-objects"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        check(
            "evaluate_pr_alignment resolves non-overlapping same-file merge without writing loose objects",
            align_same_file["isObsolete"] is False
            and align_same_file["alignmentStatus"] == "CLEAN_REBASEABLE"
            and objs_before == objs_after,
        )
        align_conf = w0m_prs.evaluate_pr_alignment(fork_repo, "feat/conflict", "upstream/main")
        check(
            "evaluate_pr_alignment detects CONFLICTING_NEEDS_REBASE",
            align_conf["isObsolete"] is False and align_conf["alignmentStatus"] == "CONFLICTING_NEEDS_REBASE",
        )

        # Launch report formatting: collapsed-by-default <details> without open attribute
        report_md = w0m_prs.format_launch_report(
            {
                "runNumber": 32,
                "timestamp": "2026-11-02T19:45:00Z",
                "status": "completed",
                "deltas": [{"type": "OBSOLETE_PR", "summary": "stablyai/orca#99999 became OBSOLETE_PATCH_EQUIVALENT"}],
                "forkUpdates": [{"repo": "graphify", "action": "fast_forward", "message": "Fast-forwarded 36 commits"}],
                "obsoletePrs": [
                    {
                        "repo": "stablyai/orca",
                        "number": 99999,
                        "branch": "feat/patch-eq",
                        "alignmentStatus": "OBSOLETE_PATCH_EQUIVALENT",
                        "closeCommand": "gh pr close 99999 -R stablyai/orca --comment 'Superseded upstream'",
                    }
                ],
                "closedSessions": [{"handle": "term_old_30", "reason": "completed_automation_run"}],
                "openPrs": [
                    {
                        "repo": "stablyai/orca",
                        "number": 37511,
                        "url": "https://github.com/stablyai/orca/pull/37511",
                        "mergeable": "MERGEABLE",
                        "alignmentStatus": "UP_TO_DATE",
                        "reviewDecision": "NONE",
                        "ciStatus": "PASS",
                        "feedback": "-",
                    }
                ],
                "candidateBranches": [],
                "worktrees": [],
            }
        )
        check(
            "format_launch_report wraps sections in collapsed-by-default <details> blocks",
            "<details>" in report_md
            and "<details open" not in report_md
            and "<summary><b>" in report_md
            and "OBSOLETE_PATCH_EQUIVALENT" in report_md
            and "term_old_30" in report_md,
        )

        # Settled automation terminal self-close safety check
        close_calls: list[list[str]] = []

        def _fake_settle_cmd(cmd: list[str], check=False, cwd=None, timeout=None):
            m = MagicMock()
            m.returncode = 0
            m.stderr = ""
            if "automations" in cmd and "runs" in cmd:
                m.stdout = json.dumps(
                    {
                        "ok": True,
                        "result": {
                            "runs": [
                                {
                                    "id": "run_32",
                                    "runNumber": 32,
                                    "status": "completed",
                                    "terminalSessionId": "tab-32",
                                    "terminalPaneKey": "tab-32:leaf-32",
                                    "outputSnapshot": {"content": "saved report"},
                                }
                            ]
                        },
                    }
                )
            elif "terminal" in cmd and "list" in cmd:
                m.stdout = json.dumps(
                    {
                        "ok": True,
                        "result": {
                            "terminals": [
                                {"handle": "term_32", "tabId": "tab-32", "leafId": "leaf-32"}
                            ]
                        },
                    }
                )
            elif "terminal" in cmd and "close" in cmd:
                close_calls.append(cmd)
                m.stdout = json.dumps({"ok": True})
            else:
                m.stdout = json.dumps({"ok": True})
            return m

        with (
            patch("w0m_prs.run_cmd", side_effect=_fake_settle_cmd),
            patch("w0m_prs.resolve_orca_bin", return_value="/tmp/orca-shim"),
        ):
            settled_res = w0m_prs.close_run_when_settled(
                automation_id="auto_1",
                terminal_handle="term_32",
                hook_status_dir=groot / "empty_hooks",
                max_wait_sec=2.0,
                poll_interval_sec=0.05,
            )
        check(
            "close_run_when_settled closes automation terminal after outputSnapshot is persisted",
            settled_res["closed"] is True and len(close_calls) == 1 and "term_32" in close_calls[0],
        )

        # Must abort without closing if hook reports session is actively working
        hooks_dir = groot / "active_hooks"
        hooks_dir.mkdir()
        (hooks_dir / "active.json").write_text(
            json.dumps({"paneKey": "tab-32:leaf-32", "payload": {"state": "working"}}),
            encoding="utf-8",
        )
        close_calls.clear()
        with (
            patch("w0m_prs.run_cmd", side_effect=_fake_settle_cmd),
            patch("w0m_prs.resolve_orca_bin", return_value="/tmp/orca-shim"),
        ):
            busy_res = w0m_prs.close_run_when_settled(
                automation_id="auto_1",
                terminal_handle="term_32",
                hook_status_dir=hooks_dir,
                max_wait_sec=0.2,
                poll_interval_sec=0.05,
            )
        check(
            "close_run_when_settled aborts when user/agent starts a new working turn",
            busy_res["closed"] is False and len(close_calls) == 0,
        )

        # v2 hook schema: {"version": 2, "entries": {"<paneKey>": {...}}}
        hooks_v2_dir = groot / "active_hooks_v2"
        hooks_v2_dir.mkdir()
        (hooks_v2_dir / "last-status.json").write_text(
            json.dumps(
                {
                    "version": 2,
                    "entries": {
                        "tab-32:leaf-32": {
                            "paneKey": "tab-32:leaf-32",
                            "tabId": "tab-32",
                            "payload": {"state": "working"},
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        close_calls.clear()
        with (
            patch("w0m_prs.run_cmd", side_effect=_fake_settle_cmd),
            patch("w0m_prs.resolve_orca_bin", return_value="/tmp/orca-shim"),
        ):
            busy_v2_res = w0m_prs.close_run_when_settled(
                automation_id="auto_1",
                terminal_handle="term_32",
                hook_status_dir=hooks_v2_dir,
                max_wait_sec=0.2,
                poll_interval_sec=0.05,
            )
        check(
            "close_run_when_settled unwraps v2 last-status.json entries dict and aborts while working",
            busy_v2_res["closed"] is False and busy_v2_res.get("reason") == "session_working" and len(close_calls) == 0,
        )

        # 8h. Cgroup-safe --daemon closer, canonical precheck path, --fresh-session & --ignore-worktrees (T615 AC4)
        fake_host_estate = groot / "Projects" / "!self" / "w0m"
        (fake_host_estate / "scripts").mkdir(parents=True)
        (fake_host_estate / "scripts" / "w0m_prs.py").write_text("# stub\n", encoding="utf-8")
        fake_worktree_estate = groot / ".w0m" / "work-prs" / "prs-obsolete-session-ui" / "w0m"
        (fake_worktree_estate / "scripts").mkdir(parents=True)
        resolved_canon = w0m_prs.resolve_canonical_estate_root(
            workspace_root=fake_worktree_estate, home_dir=groot
        )
        check(
            "resolve_canonical_estate_root maps ephemeral ~/.w0m/work* trees back to live host estate",
            resolved_canon == fake_host_estate,
        )

        # Detached --daemon closer via systemd-run --user --collect on Linux + Popen fallback
        sd_calls: list[list[str]] = []

        def _fake_sd_run(cmd: list[str], check=False, cwd=None, timeout=None):
            sd_calls.append(cmd)
            m = MagicMock()
            m.returncode = 0
            m.stdout = "Running as unit: run-test.service\n"
            m.stderr = ""
            return m

        with (
            patch("w0m_prs.sys.platform", "linux"),
            patch("w0m_prs.shutil.which", side_effect=lambda b: "/usr/bin/systemd-run" if b == "systemd-run" else None),
            patch("w0m_prs.run_cmd", side_effect=_fake_sd_run),
            patch.dict("os.environ", {"ORCA_CLI_COMMAND": "/tmp/orca-shim"}, clear=False),
        ):
            daemon_sd = w0m_prs.spawn_detached_closer(
                terminal_handle="term_42",
                automation_id="auto_1",
                initial_delay_sec=2.0,
                max_wait_sec=60.0,
                poll_interval_sec=0.5,
            )
        check(
            "spawn_detached_closer uses systemd-run --user --collect on Linux to escape tool-runner cgroup",
            daemon_sd["ok"] is True
            and daemon_sd["mechanism"] == "systemd-run"
            and len(sd_calls) == 1
            and "--user" in sd_calls[0]
            and "--collect" in sd_calls[0]
            and any(a.startswith("--setenv=ORCA_CLI_COMMAND=") for a in sd_calls[0]),
        )

        popen_calls: list[tuple[list[str], dict]] = []

        def _fake_popen(cmd: list[str], **kwargs):
            popen_calls.append((cmd, kwargs))
            p = MagicMock()
            p.pid = 42424
            return p

        with (
            patch("w0m_prs.shutil.which", return_value=None),
            patch("w0m_prs.subprocess.Popen", side_effect=_fake_popen),
        ):
            daemon_fb = w0m_prs.spawn_detached_closer(
                terminal_handle="term_42",
                initial_delay_sec=2.0,
                max_wait_sec=60.0,
                poll_interval_sec=0.5,
            )
        check(
            "spawn_detached_closer falls back to Popen(start_new_session=True) when systemd-run is absent",
            daemon_fb["ok"] is True
            and daemon_fb["mechanism"] == "setsid"
            and len(popen_calls) == 1
            and popen_calls[0][1].get("start_new_session") is True,
        )

        # check_prs_delta: include_worktrees=False ignores WORKTREE_DELTA + pending_deltas handoff to reconcile
        delta_state_file = groot / "delta_handoff_state.json"
        base_disc = {
            "openPrCount": 1,
            "openPrs": [
                {
                    "repo": "stablyai/orca",
                    "number": 37511,
                    "title": "feat: mobile tabs",
                    "state": "OPEN",
                    "mergeable": "MERGEABLE",
                    "alignmentStatus": "UP_TO_DATE",
                    "isObsolete": False,
                    "reviewDecision": "NONE",
                    "ciStatus": "PASS",
                    "commentsCount": 2,
                    "reviewsCount": 0,
                    "feedback": "-",
                }
            ],
            "obsoletePrCount": 0,
            "obsoletePrs": [],
            "pendingBranchCount": 0,
            "pendingBranches": [],
            "agentTreeCount": 1,
            "agentTrees": [{"name": "t615-work", "clean": False, "dirty_repos": ["."]}],
        }
        w0m_prs.check_prs_delta(
            state_path=delta_state_file, current_override=base_disc, include_worktrees=False
        )
        wt_only_disc = {
            **base_disc,
            "agentTrees": [{"name": "t615-work", "clean": False, "dirty_repos": [".", "w0m-web", "w0m-api"]}],
        }
        wt_delta_res = w0m_prs.check_prs_delta(
            state_path=delta_state_file,
            current_override=wt_only_disc,
            include_worktrees=False,
            record_pending_deltas=True,
        )
        check(
            "check_prs_delta(include_worktrees=False) ignores unrelated agent worktree dirty-repo churn",
            wt_delta_res["changed"] is False and wt_delta_res["deltaCount"] == 0,
        )
        pr_changed_disc = {
            **wt_only_disc,
            "openPrs": [{**base_disc["openPrs"][0], "reviewDecision": "APPROVED"}],
        }
        pr_precheck_res = w0m_prs.check_prs_delta(
            state_path=delta_state_file,
            current_override=pr_changed_disc,
            include_worktrees=False,
            record_pending_deltas=True,
        )
        # Subsequent reconcile call sees identical state_file snapshot — must consume pending_deltas!
        reconcile_delta_res = w0m_prs.check_prs_delta(
            state_path=delta_state_file,
            current_override=pr_changed_disc,
            include_worktrees=False,
            consume_pending_deltas=True,
        )
        check(
            "check_prs_delta hands off precheck pending_deltas to subsequent reconcile run",
            pr_precheck_res["changed"] is True
            and reconcile_delta_res["changed"] is True
            and reconcile_delta_res["deltaCount"] == 1
            and "APPROVED" in reconcile_delta_res["deltas"][0],
        )

        # sync_prs_to_orca uses --fresh-session, --enabled, canonical precheck path & --daemon prompt
        recorded_t615_cmds: list[list[str]] = []

        def _fake_t615_orca_cmd(cmd: list[str], check=False, cwd=None, timeout=None):
            recorded_t615_cmds.append(cmd)
            m = MagicMock()
            m.returncode = 0
            m.stderr = ""
            if "automations" in cmd and "list" in cmd:
                m.stdout = json.dumps(
                    {
                        "ok": True,
                        "result": {
                            "automations": [
                                {"id": "auto_existing", "name": "w0m Upstream PRs & Fork Branches Monitor"}
                            ]
                        },
                    }
                )
            else:
                m.stdout = json.dumps({"ok": True, "result": {}})
            return m

        with (
            patch("w0m_prs.run_cmd", side_effect=_fake_t615_orca_cmd),
            patch("w0m_prs.resolve_orca_bin", return_value="/tmp/orca-shim"),
            patch("w0m_prs.resolve_agent_provider", return_value="antigravity"),
            patch("w0m_prs.resolve_canonical_estate_root", return_value=fake_host_estate),
            patch("w0m_prs.check_prs_delta", side_effect=lambda **kw: {"changed": False}),
        ):
            sync_t615 = w0m_prs.sync_prs_to_orca(dry_run=False, discovered_override=sample_discovered)
        edit_cmds = [c for c in recorded_t615_cmds if "automations" in c and "edit" in c]
        check(
            "sync_prs_to_orca configures --fresh-session, --enabled, canonical precheck --ignore-worktrees, and --daemon closer",
            len(edit_cmds) == 1
            and "--fresh-session" in edit_cmds[0]
            and "--reuse-session" not in edit_cmds[0]
            and "--enabled" in edit_cmds[0]
            and str(fake_host_estate / "scripts" / "w0m_prs.py") in sync_t615["precheck"]
            and "--ignore-worktrees" in sync_t615["precheck"]
            and "--daemon" in " ".join(edit_cmds[0]),
        )

    # 9. Skill check
    skill_md = ROOT / "w0m-skills/skills/w0m-prs/SKILL.md"
    check("w0m-prs SKILL.md exists in w0m-skills", skill_md.is_file())

    # 10. T618 Linux distro & developer tooling forks + proposals
    check(
        "preset w0m-pr includes moksha and Bodhi packaging repos",
        all(
            r in w0m_prs.PRESET_REPOS["w0m-pr"]
            for r in (
                "JeffHoogland/moksha",
                "BodhiDev/bodhi-profile-iso",
                "BodhiDev/bodhi7packages",
                "BodhiDev/bodhi8packages",
            )
        ),
    )
    check(
        "FORK_UPSTREAM_MAP maps moksha and Bodhi packaging forks",
        w0m_prs.FORK_UPSTREAM_MAP.get("moksha") == "JeffHoogland/moksha"
        and w0m_prs.FORK_UPSTREAM_MAP.get("bodhi-profile-iso") == "BodhiDev/bodhi-profile-iso"
        and w0m_prs.FORK_UPSTREAM_MAP.get("bodhi7packages") == "BodhiDev/bodhi7packages"
        and w0m_prs.FORK_UPSTREAM_MAP.get("bodhi8packages") == "BodhiDev/bodhi8packages",
    )
    t618_proposals = [p for p in w0m_prs.build_pr_proposals(forks_dir=Path("/nonexistent-forks")) if p["ticket"] == "T618"]
    check("build_pr_proposals renders all 9 T618 proposals", len(t618_proposals) == 9)
    moksha_snap_prop = next(
        (p for p in t618_proposals if p["key"] == "JeffHoogland/moksha:feat/eight-zone-window-snapping"),
        None,
    )
    check(
        "Moksha 8-zone proposal targets master base branch and documents Top Half default rationale",
        moksha_snap_prop is not None
        and moksha_snap_prop["base_branch"] == "master"
        and "compare/master...webomage:feat/eight-zone-window-snapping" in moksha_snap_prop["compare_url"]
        and "Top Half (`E_MAXIMIZE_TOP`) is proposed as the default" in moksha_snap_prop["body"],
    )
    check(
        "INTERNAL_OR_SUPERSEDED_BRANCHES excludes T619 feat/w0m-overlay-updater-feed internal branch",
        "feat/w0m-overlay-updater-feed" in w0m_prs.INTERNAL_OR_SUPERSEDED_BRANCHES,
    )
    t633_proposals = [
        p for p in w0m_prs.build_pr_proposals(forks_dir=Path("/nonexistent-forks")) if p["ticket"] == "T635"
    ]
    check(
        "build_pr_proposals renders all 3 T635 Orca proposals (4-tap Alt+M, 4-side edge arrows, smooth resize)",
        len(t633_proposals) == 3
        and {p["key"] for p in t633_proposals}
        == {
            "stablyai/orca:feat/mobile-terminal-4-tap-alt-m",
            "stablyai/orca:feat/mobile-four-side-edge-arrows",
            "stablyai/orca:fix/terminal-smooth-resize-and-replay",
        },
    )

    t638_proposals = [
        p for p in w0m_prs.build_pr_proposals(forks_dir=Path("/nonexistent-forks")) if p["ticket"] == "T638"
    ]
    check(
        "build_pr_proposals renders T638 Orca system and Docker monitors proposal",
        len(t638_proposals) == 1
        and t638_proposals[0]["key"] == "stablyai/orca:feat/system-and-docker-monitors"
        and "lazydocker" in t638_proposals[0]["body"],
    )

    print("─" * 60)
    print(f"Results: {checks - len(fails)}/{checks} passed")
    if fails:
        print("\nFailed checks:")
        for f in fails:
            print(f"  ✗ {f}")
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
