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
        "rich gh pr list payloads skip redundant audit_pr calls unless mergeable is UNKNOWN",
        audit_calls == [("stablyai/orca", 202)]
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

    # 8f. Contribution Proposals & Owner-Confirmed Submission Gate (T593, T608)
    proposals_list = w0m_prs.build_pr_proposals()
    check(
        "build_pr_proposals returns 13 contribution proposals including T608 Orca PRs",
        len(proposals_list) == 13
        and any(p["key"] == "stablyai/orca:feat/nested-subfolder-git-and-sdlc-repo" for p in proposals_list)
        and any(p["key"] == "stablyai/orca:feat/mobile-session-tab-reorder" for p in proposals_list),
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

    # 9. Skill check
    skill_md = ROOT / "w0m-skills/skills/w0m-prs/SKILL.md"
    check("w0m-prs SKILL.md exists in w0m-skills", skill_md.is_file())

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
