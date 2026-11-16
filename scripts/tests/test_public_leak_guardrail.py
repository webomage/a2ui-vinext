#!/usr/bin/env python3
"""Deterministic unit + red-probe test suite for `public_leak_guardrail.py` (`T749` AC3)."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import public_leak_guardrail as plg  # noqa: E402


checks = 0
fails: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        fails.append(f"{label}{': ' + detail if detail else ''}")
    print(f"  {'✓' if cond else '✗'} {label}")


def _git(cwd: Path, *args: str) -> str:
    cp = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True)
    return cp.stdout.strip()


def _init_upstream_pr_fixture(repo_dir: Path, *, leak_kind: str) -> None:
    repo_dir.mkdir(parents=True, exist_ok=True)
    _git(repo_dir, "init", "-b", "main")
    _git(repo_dir, "config", "user.name", "Test User")
    _git(repo_dir, "config", "user.email", "test@example.com")
    (repo_dir / "README.md").write_text("# Upstream Repo\n", encoding="utf-8")
    _git(repo_dir, "add", "README.md")
    _git(repo_dir, "commit", "-m", "chore: initial upstream commit")
    base_sha = _git(repo_dir, "rev-parse", "HEAD")
    _git(repo_dir, "update-ref", "refs/remotes/upstream/main", base_sha)

    if leak_kind == "diff-removal-only":
        # Upstream already had a stale string, PR branch REMOVES it -> should pass
        (repo_dir / "cleanup.txt").write_text("stale .w0m/sdlc.json line\n", encoding="utf-8")
        _git(repo_dir, "add", "cleanup.txt")
        _git(repo_dir, "commit", "-m", "chore: seed line to delete later")
        _git(repo_dir, "update-ref", "refs/remotes/upstream/main", _git(repo_dir, "rev-parse", "HEAD"))
        _git(repo_dir, "checkout", "-b", "fix/cleanup")
        (repo_dir / "cleanup.txt").write_text("clean generic line\n", encoding="utf-8")
        _git(repo_dir, "add", "cleanup.txt")
        _git(repo_dir, "commit", "-m", "fix: replace stale configuration note")
        return

    _git(repo_dir, "checkout", "-b", "feat/sample")
    if leak_kind == "clean":
        (repo_dir / "feature.ts").write_text("export function discoverNested() { return true }\n", encoding="utf-8")
        _git(repo_dir, "add", "feature.ts")
        _git(repo_dir, "commit", "-m", "feat(projects): discover nested repositories")
    elif leak_kind == "dot-w0m-file":
        (repo_dir / ".w0m").mkdir(parents=True, exist_ok=True)
        (repo_dir / ".w0m/sdlc.json").write_text('{"repo": "internal"}\n', encoding="utf-8")
        _git(repo_dir, "add", ".w0m/sdlc.json")
        _git(repo_dir, "commit", "-m", "feat: add config")
    elif leak_kind == "k7-in-code":
        (repo_dir / "feature.ts").write_text("const board = 'k7hub/internal'\n", encoding="utf-8")
        _git(repo_dir, "add", "feature.ts")
        _git(repo_dir, "commit", "-m", "feat: add board constant")
    elif leak_kind == "ticket-in-commit":
        (repo_dir / "feature.ts").write_text("export const ready = true\n", encoding="utf-8")
        _git(repo_dir, "add", "feature.ts")
        _git(repo_dir, "commit", "-m", "feat(ui): implement T749 helper")
    elif leak_kind == "behind-upstream-clean":
        # Branch cuts early and stays behind upstream commits containing internal-looking tokens,
        # proving three-dot (`upstream/main...HEAD`) ignores upstream commits not touched by branch.
        (repo_dir / "pr_file.ts").write_text("export const cleanPr = 1\n", encoding="utf-8")
        _git(repo_dir, "add", "pr_file.ts")
        _git(repo_dir, "commit", "-m", "feat: clean pr commit")
        pr_sha = _git(repo_dir, "rev-parse", "HEAD")
        _git(repo_dir, "checkout", "main")
        (repo_dir / "upstream_other.txt").write_text("upstream k7hub mention unrelated to pr\n", encoding="utf-8")
        _git(repo_dir, "add", "upstream_other.txt")
        _git(repo_dir, "commit", "-m", "chore: unrelated upstream commit")
        _git(repo_dir, "update-ref", "refs/remotes/upstream/main", _git(repo_dir, "rev-parse", "HEAD"))
        _git(repo_dir, "checkout", pr_sha)


def main() -> int:
    print("Public Leak Guardrail Test Suite (T749)")
    print("─" * 60)

    # 1. Upstream PR bundle unit probes
    clean_bundle = plg.scan_upstream_pr_bundle(
        title="feat(project-groups): discover nested git repositories",
        body="Discovers nested `.git` directories inside umbrella workspaces.\n![Demo](https://raw.githubusercontent.com/webomage/orca/pr-assets/demo.png)\n",
        commit_messages="feat(project-groups): clean commit\n",
        diff_text="+++ b/src/main/discovery.ts\n+export const ok = true;\n",
    )
    check("clean PR bundle + pr-assets URL passes with zero findings", len(clean_bundle) == 0, str(clean_bundle))

    leaked_diff = plg.scan_upstream_pr_bundle(
        title="feat(projects): generic title",
        body="Generic PR body.",
        diff_text=(
            "--- a/old.ts\n"
            "+++ b/.w0m/sdlc.json\n"
            "+{\"project\": \"bridgeroad-app\"}\n"
            "-const old = 'ignored removal k7hub w0m-web /home/aleksei T749';\n"
        ),
    )
    rules_hit = {f.rule for f in leaked_diff}
    locs_hit = {f.location for f in leaked_diff}
    check(
        "upstream PR scanner flags added `.w0m/` path + `bridgeroad` and ignores `-` diff removals",
        "internal-w0m-dotdir" in rules_hit
        and "internal-client-bridgeroad" in rules_hit
        and any(loc.startswith("diff-path:") for loc in locs_hit)
        and "internal-k7-token" not in rules_hit
        and "personal-workstation-path" not in rules_hit,
        str(leaked_diff),
    )

    unallowlisted_org = plg.scan_upstream_pr_bundle(
        title="docs(ecosystem): add @webomage/a2ui-vinext",
        body="Lists https://github.com/webomage/a2ui-vinext.",
    )
    check(
        "unallowlisted `webomage` in prose/title fails closed",
        any(f.rule == "unallowlisted-webomage" for f in unallowlisted_org),
    )
    allowlisted_org = plg.scan_upstream_pr_bundle(
        title="docs(ecosystem): add @webomage/a2ui-vinext",
        body="Lists https://github.com/webomage/a2ui-vinext.",
        allow_tokens=("webomage",),
    )
    check("explicitly allowlisted `webomage` passes", len(allowlisted_org) == 0, str(allowlisted_org))

    # 2. Git branch range checks (clean, leaked file path, leaked code, leaked commit msg, behind-upstream 3-dot)
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        clean_repo = tmp / "clean"
        _init_upstream_pr_fixture(clean_repo, leak_kind="clean")
        res_clean = plg.scan_git_branch_upstream_pr(
            clean_repo, "refs/heads/feat/sample", "upstream/main",
            title="feat(projects): discover nested repos", body="Clean summary text.",
        )
        check("clean git branch passes scan_git_branch_upstream_pr", res_clean["ok"] is True, str(res_clean))

        w0m_repo = tmp / "dotw0m"
        _init_upstream_pr_fixture(w0m_repo, leak_kind="dot-w0m-file")
        res_w0m = plg.scan_git_branch_upstream_pr(
            w0m_repo, "refs/heads/feat/sample", "upstream/main",
            title="feat: sample", body="Clean summary.",
        )
        check(
            "added `.w0m/sdlc.json` in git branch diff fails closed",
            res_w0m["ok"] is False and any(f["rule"] == "internal-w0m-dotdir" for f in res_w0m["findings"]),
            str(res_w0m),
        )

        k7_repo = tmp / "k7"
        _init_upstream_pr_fixture(k7_repo, leak_kind="k7-in-code")
        res_k7 = plg.scan_git_branch_upstream_pr(k7_repo, "refs/heads/feat/sample", "upstream/main")
        check(
            "`k7hub` added in source file fails closed",
            res_k7["ok"] is False and any(f["rule"] == "internal-k7-token" for f in res_k7["findings"]),
            str(res_k7),
        )

        msg_repo = tmp / "ticketmsg"
        _init_upstream_pr_fixture(msg_repo, leak_kind="ticket-in-commit")
        res_msg = plg.scan_git_branch_upstream_pr(msg_repo, "refs/heads/feat/sample", "upstream/main")
        check(
            "internal `T749` ticket ID in commit message fails closed",
            res_msg["ok"] is False and any(f["rule"] == "internal-ticket-or-agdr" for f in res_msg["findings"]),
            str(res_msg),
        )

        rem_repo = tmp / "removal"
        _init_upstream_pr_fixture(rem_repo, leak_kind="diff-removal-only")
        res_rem = plg.scan_git_branch_upstream_pr(rem_repo, "refs/heads/fix/cleanup", "upstream/main")
        check("PR removing stale `.w0m/sdlc.json` line passes", res_rem["ok"] is True, str(res_rem))

        behind_repo = tmp / "behind"
        _init_upstream_pr_fixture(behind_repo, leak_kind="behind-upstream-clean")
        res_behind = plg.scan_git_branch_upstream_pr(behind_repo, "HEAD", "upstream/main")
        check("three-dot diff ignores upstream commits after merge-base", res_behind["ok"] is True, str(res_behind))

        missing_ref = plg.scan_git_branch_upstream_pr(clean_repo, "refs/heads/does-not-exist", "upstream/main")
        check("missing git ref fails closed (`ok=False`)", missing_ref["ok"] is False and bool(missing_ref["error"]))

        # 3. CV/web surface scan (`public-cv` profile)
        web_root = tmp / "web"
        (web_root / "apps/web/public").mkdir(parents=True, exist_ok=True)
        (web_root / "apps/web/src/content/pages").mkdir(parents=True, exist_ok=True)
        (web_root / "apps/web/public/_headers").write_text(
            "# Internal T749 comment ignored in Cloudflare _headers\n"
            "/*\n"
            "  Content-Security-Policy: connect-src 'self' https://*.w0m.xyz\n",
            encoding="utf-8",
        )
        (web_root / "apps/web/src/content/pages/cv.md").write_text(
            "---\ntitle: CV\n---\nCloudflare Workers & Astro engineer.\n",
            encoding="utf-8",
        )
        cv_ok = plg.scan_cv_root(web_root)
        check("`*.w0m.xyz` CSP directive and clean CV page pass `scan_cv_root`", cv_ok["ok"] is True, str(cv_ok))

        (web_root / "apps/web/src/content/pages/leak.md").write_text(
            "Internal tooling: `.w0m/sdlc.json`, `k7hub`, `bridgeroad-app`, `T749`.\n",
            encoding="utf-8",
        )
        cv_red = plg.scan_cv_root(web_root)
        cv_rules = {f["rule"] for f in cv_red["findings"]}
        check(
            "served `.w0m/`, `k7hub`, `bridgeroad`, and `T749` all fail `scan_cv_root`",
            cv_red["ok"] is False
            and {"internal-w0m-dotdir", "internal-k7-token", "internal-client-bridgeroad", "internal-ticket-or-agdr"} <= cv_rules,
            str(cv_red),
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
    raise SystemExit(main())
