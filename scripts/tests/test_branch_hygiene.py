#!/usr/bin/env python3
"""Regression and red-probe suite for scripts/branch_hygiene.py (T148 AC1-AC7)."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "branch_hygiene.py"


def load_module():
    spec = importlib.util.spec_from_file_location("branch_hygiene", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def git_run(cwd: Path, args: list[str], env_extra: dict[str, str] | None = None) -> None:
    env = os.environ.copy()
    env.setdefault("GIT_AUTHOR_NAME", "Test User")
    env.setdefault("GIT_AUTHOR_EMAIL", "test@example.com")
    env.setdefault("GIT_COMMITTER_NAME", "Test User")
    env.setdefault("GIT_COMMITTER_EMAIL", "test@example.com")
    if env_extra:
        env.update(env_extra)
    res = subprocess.run(
        ["git", "-C", str(cwd), *args],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        raise RuntimeError(f"git {args} failed: {res.stderr}")


def test_sdlc_branch_model_contract() -> None:
    mod = load_module()
    model = mod.load_branch_model(ROOT)
    assert model["canonical_branch"] == "beta"
    assert model["agent_branch_prefix"] == "agent/"
    assert model["release_tag_prefix"] == "release/"
    assert int(model["stale_days"]) == 14
    assert set(model["single_branch_by_design"]) == {"@wom", "wom7func", "wom7skills"}
    assert set(model["legacy_main_repos"]) == {"wom7web", "wom7api", "wom7ext", "wom7sec"}
    assert model["excluded_repos"] == ["wom7mlx/wom7mlx"]
    api_meta = model["legacy_main_status"]["wom7api"]
    assert api_meta["diverged_pre_rewrite_do_not_merge"] is True
    print("  \u2705 test_sdlc_branch_model_contract")


def test_red_probe_planted_stale_branch_and_no_upstream() -> None:
    with tempfile.TemporaryDirectory(prefix="t148_stale_") as tmp:
        repo = Path(tmp)
        git_run(repo, ["init", "-b", "beta"])
        (repo / "README.md").write_text("base\n", encoding="utf-8")
        git_run(repo, ["add", "README.md"])
        git_run(repo, ["commit", "-m", "initial commit"])
        head_sha = subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
        ).strip()
        git_run(repo, ["update-ref", "refs/remotes/origin/beta", head_sha])

        # Plant a stale branch backdated to 2025-01-01 (>14 days old) with no upstream
        git_run(repo, ["checkout", "-b", "feature/stale-planted"])
        (repo / "stale.txt").write_text("old work\n", encoding="utf-8")
        git_run(repo, ["add", "stale.txt"])
        old_date = "2025-01-01T00:00:00Z"
        git_run(
            repo,
            ["commit", "-m", "old commit"],
            env_extra={"GIT_AUTHOR_DATE": old_date, "GIT_COMMITTER_DATE": old_date},
        )

        res = subprocess.run(
            [sys.executable, str(SCRIPT), "--repo", str(repo), "--json"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert res.returncode == 0, res.stderr
        payload = json.loads(res.stdout)
        assert payload["summary"]["vacuous"] is False
        assert payload["summary"]["stale_branch_count"] >= 1
        rinfo = payload["repos"][0]
        by_ref = {b["refname"]: b for b in rinfo["branches"]}
        planted = by_ref["refs/heads/feature/stale-planted"]
        assert planted["stale"] is True
        assert planted["upstream_configured"] is False
        assert planted["ahead_of_stage"] == 1
        assert planted["merged_into_stage"] is False
    print("  \u2705 test_red_probe_planted_stale_branch_and_no_upstream")


def test_red_probe_planted_main_beta_divergence() -> None:
    with tempfile.TemporaryDirectory(prefix="t148_diverge_") as tmp:
        repo = Path(tmp)
        git_run(repo, ["init", "-b", "beta"])
        (repo / "file.txt").write_text("root\n", encoding="utf-8")
        git_run(repo, ["add", "file.txt"])
        git_run(repo, ["commit", "-m", "merge base"])

        # Advance main by 3 commits
        git_run(repo, ["checkout", "-b", "main"])
        for idx in range(3):
            (repo / f"main_{idx}.txt").write_text(f"m{idx}\n", encoding="utf-8")
            git_run(repo, ["add", f"main_{idx}.txt"])
            git_run(repo, ["commit", "-m", f"main commit {idx}"])
        main_sha = subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
        ).strip()
        git_run(repo, ["update-ref", "refs/remotes/origin/main", main_sha])

        # Advance beta by 2 commits from merge-base
        git_run(repo, ["checkout", "beta"])
        for idx in range(2):
            (repo / f"beta_{idx}.txt").write_text(f"b{idx}\n", encoding="utf-8")
            git_run(repo, ["add", f"beta_{idx}.txt"])
            git_run(repo, ["commit", "-m", f"beta commit {idx}"])
        beta_sha = subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
        ).strip()
        git_run(repo, ["update-ref", "refs/remotes/origin/beta", beta_sha])

        res = subprocess.run(
            [sys.executable, str(SCRIPT), "--repo", str(repo), "--json"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert res.returncode == 0, res.stderr
        payload = json.loads(res.stdout)
        rinfo = payload["repos"][0]
        assert rinfo["diverged"] is True
        assert rinfo["main_status"] == "DIVERGED"
        assert rinfo["beta_ahead_of_main"] == 2
        assert rinfo["main_ahead_of_beta"] == 3
    print("  \u2705 test_red_probe_planted_main_beta_divergence")


def test_vacuity_guard_fails_on_zero_branches() -> None:
    with tempfile.TemporaryDirectory(prefix="t148_empty_") as tmp:
        empty_repo = Path(tmp)
        git_run(empty_repo, ["init", "-b", "beta"])
        res = subprocess.run(
            [sys.executable, str(SCRIPT), "--repo", str(empty_repo)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert res.returncode != 0, "Expected non-zero exit on 0-branch repository"
        assert "[FAIL] Vacuous branch report" in res.stdout
    print("  \u2705 test_vacuity_guard_fails_on_zero_branches")


def test_readonly_whitelist_and_live_estate_non_mutation() -> None:
    mod = load_module()
    for forbidden in ("fetch", "push", "merge", "reset", "branch", "checkout", "update-ref"):
        raised = False
        try:
            mod.run_git_readonly(ROOT, [forbidden])
        except ValueError:
            raised = True
        assert raised, f"Expected ValueError for forbidden subcommand {forbidden}"

    before_refs = subprocess.check_output(
        ["git", "-C", str(ROOT), "for-each-ref"], text=True
    )
    res = subprocess.run(
        [sys.executable, str(SCRIPT), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    after_refs = subprocess.check_output(
        ["git", "-C", str(ROOT), "for-each-ref"], text=True
    )
    assert res.returncode == 0, res.stderr
    assert before_refs == after_refs, "branch_hygiene mutated git refs!"
    payload = json.loads(res.stdout)
    assert payload["read_only"] is True
    assert payload["summary"]["governed_repo_count"] == 7
    assert payload["summary"]["excluded_repo_count"] == 1
    assert payload["summary"]["vacuous"] is False
    repos_by_name = {r["repo"]: r for r in payload["repos"]}
    assert repos_by_name["wom7api"]["main_status"] == "DIVERGED_PRE_REWRITE_DO_NOT_MERGE"
    assert repos_by_name["wom7api"]["main_ahead_of_beta"] == 180
    assert repos_by_name["wom7mlx/wom7mlx"]["excluded"] is True
    print("  \u2705 test_readonly_whitelist_and_live_estate_non_mutation")


def main() -> int:
    test_sdlc_branch_model_contract()
    test_red_probe_planted_stale_branch_and_no_upstream()
    test_red_probe_planted_main_beta_divergence()
    test_vacuity_guard_fails_on_zero_branches()
    test_readonly_whitelist_and_live_estate_non_mutation()
    return 0


if __name__ == "__main__":
    sys.exit(main())
