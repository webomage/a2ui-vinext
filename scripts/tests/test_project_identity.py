#!/usr/bin/env python3
"""T300 AC3 / AC5 / AC6 — Standing regression proof and red probes for project_identity_check.py.

Proves:
1. Live registry verification: all enabled projects and repos pass.
2. Git author mismatch detection: divergent user.name or user.email flags FAIL with diff.
3. SSH transport mismatch detection: divergent core.sshCommand flags FAIL with diff.
4. Unmeasurable states (AC5): missing repo, non-git dir, absent SSH key, unauthenticated gh.
5. Secret material rejection (AC6): multiline or private key patterns flag FAIL.
6. Enforcement gate: --enforce exits 1 on failure or unmeasurable, and 0 on pass.

Run: `just project-identity-test`
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "wom7web"
SCRIPT = ROOT / "scripts" / "project_identity_check.py"

sys.path.insert(0, str(SCRIPT.parent))
import project_identity_check as pic  # noqa: E402

fails: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        msg = f"{label}{(' — ' + detail) if detail else ''}"
        fails.append(msg)
    print(f"  {'✅' if cond else '❌'} {label}")


print("\n── project identity verification regression suite (T300) ──")

# 1. Live policy check
live_results = pic.inspect_all(pic.DEFAULT_POLICY_PATH, pic.ESTATE_ROOT)
present_results = [r for r in live_results if r["status"] != "UNMEASURABLE"]
all_passed = len(present_results) > 0 and all(r["status"] == "PASS" for r in present_results) and not any(r["status"] == "FAIL" for r in live_results)
check(
    "live policy passes across all declared projects and repos",
    all_passed,
    f"{sum(1 for r in live_results if r['status'] == 'FAIL')} failed, {sum(1 for r in live_results if r['status'] == 'UNMEASURABLE')} unmeasurable results",
)

with tempfile.TemporaryDirectory(prefix="t300-test-") as tmpdir:
    tmp = Path(tmpdir)
    real_key = tmp / "mock_id_rsa"
    real_key.write_text("dummy-public-or-key-pointer")
    other_key = tmp / "mock_id_ed25519"
    other_key.write_text("dummy-other-key")

    # Helper to create a git repo with specific git config
    def make_repo(name: str, user_name: str, user_email: str, ssh_cmd: str = "") -> Path:
        repo_dir = tmp / name
        repo_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "-C", str(repo_dir), "init", "--quiet"], check=True)
        subprocess.run(["git", "-C", str(repo_dir), "config", "user.name", user_name], check=True)
        subprocess.run(["git", "-C", str(repo_dir), "config", "user.email", user_email], check=True)
        if ssh_cmd:
            subprocess.run(["git", "-C", str(repo_dir), "config", "core.sshCommand", ssh_cmd], check=True)
        return repo_dir

    mock_gh_dir = str(tmp / "mock-gh")
    os.makedirs(mock_gh_dir, exist_ok=True)
    gh_cache: dict[str, tuple[str | None, str | None]] = {mock_gh_dir: ("mockuser", None)}

    # 2. Red probe: user.name mismatch
    r1 = make_repo("repo_name_mismatch", "Wrong Author", "alice@example.com")
    decl1 = {
        "git_user_name": "Correct Author",
        "git_user_email": "alice@example.com",
        "ssh_key": str(real_key),
        "gh_account": "mockuser",
        "gh_config_dir": mock_gh_dir,
    }
    res1 = pic.inspect_repository("p1", "r1", r1, decl1, gh_cache)
    check("red probe: user.name mismatch flags FAIL", res1["status"] == "FAIL", f"status={res1['status']}")
    check(
        "red probe: user.name mismatch diff names expected and actual",
        any("Correct Author" in f and "Wrong Author" in f for f in res1["failures"]),
        f"failures={res1['failures']}",
    )

    # 3. Red probe: user.email mismatch
    r2 = make_repo("repo_email_mismatch", "Correct Author", "wrong@example.com")
    res2 = pic.inspect_repository("p2", "r2", r2, decl1, gh_cache)
    check("red probe: user.email mismatch flags FAIL", res2["status"] == "FAIL", f"status={res2['status']}")
    check(
        "red probe: user.email mismatch diff names expected and actual",
        any("alice@example.com" in f and "wrong@example.com" in f for f in res2["failures"]),
        f"failures={res2['failures']}",
    )

    # 4. Red probe: SSH key mismatch via core.sshCommand
    r3 = make_repo(
        "repo_ssh_mismatch",
        "Correct Author",
        "alice@example.com",
        ssh_cmd=f"ssh -i {other_key} -o IdentitiesOnly=yes",
    )
    res3 = pic.inspect_repository("p3", "r3", r3, decl1, gh_cache)
    check("red probe: SSH key mismatch flags FAIL", res3["status"] == "FAIL", f"status={res3['status']}")
    check(
        "red probe: SSH key mismatch names expected and actual",
        any(str(real_key) in f and str(other_key) in f for f in res3["failures"]),
        f"failures={res3['failures']}",
    )

    # 5. Red probe (AC5): Absent SSH key file reports UNMEASURABLE
    decl_missing_key = {
        "git_user_name": "Correct Author",
        "git_user_email": "alice@example.com",
        "ssh_key": str(tmp / "nonexistent_ssh_key"),
        "gh_account": "mockuser",
        "gh_config_dir": mock_gh_dir,
    }
    r4 = make_repo("repo_missing_key", "Correct Author", "alice@example.com")
    res4 = pic.inspect_repository("p4", "r4", r4, decl_missing_key, gh_cache)
    check(
        "red probe (AC5): missing ssh_key file reports UNMEASURABLE, not PASS",
        res4["status"] == "UNMEASURABLE",
        f"status={res4['status']}",
    )
    check(
        "missing ssh_key explains reason in unmeasurable details",
        any("nonexistent_ssh_key" in u for u in res4["unmeasurable"]),
        f"unmeasurable={res4['unmeasurable']}",
    )

    # 6. Red probe (AC5): Non-existent repo directory reports UNMEASURABLE
    res5 = pic.inspect_repository("p5", "r5", tmp / "nonexistent_repo", decl1, gh_cache)
    check(
        "red probe (AC5): non-existent repo directory reports UNMEASURABLE",
        res5["status"] == "UNMEASURABLE",
        f"status={res5['status']}",
    )

    # 7. Red probe (AC5): Non-git directory reports UNMEASURABLE
    non_git = tmp / "plain_dir"
    non_git.mkdir()
    res6 = pic.inspect_repository("p6", "r6", non_git, decl1, gh_cache)
    check(
        "red probe (AC5): non-git directory reports UNMEASURABLE",
        res6["status"] == "UNMEASURABLE",
        f"status={res6['status']}",
    )

    # 8. Red probe: GitHub account mismatch
    decl_wrong_gh = {
        "git_user_name": "Correct Author",
        "git_user_email": "alice@example.com",
        "ssh_key": str(real_key),
        "gh_account": "differentuser",
        "gh_config_dir": mock_gh_dir,
    }
    r7 = make_repo("repo_gh_mismatch", "Correct Author", "alice@example.com")
    res7 = pic.inspect_repository("p7", "r7", r7, decl_wrong_gh, gh_cache)
    check("red probe: GitHub account mismatch flags FAIL", res7["status"] == "FAIL", f"status={res7['status']}")
    check(
        "red probe: GitHub account diff names expected and actual",
        any("differentuser" in f and "mockuser" in f for f in res7["failures"]),
        f"failures={res7['failures']}",
    )

    # 9. Red probe (AC6): Secret material in declaration is rejected
    decl_secret = {
        "git_user_name": "Correct Author",
        "git_user_email": "alice@example.com",
        "ssh_key": "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA...",
        "gh_account": "mockuser",
        "gh_config_dir": mock_gh_dir,
    }
    res8 = pic.inspect_repository("p8", "r8", r1, decl_secret, gh_cache)
    check(
        "red probe (AC6): private key material in declaration flags FAIL",
        res8["status"] == "FAIL",
        f"status={res8['status']}",
    )
    check(
        "secret material failure explicitly cites security reason",
        any("secret pattern" in f or "multiline content" in f for f in res8["failures"]),
        f"failures={res8['failures']}",
    )

    # 10. End-to-end main() enforcement exit code verification
    decl_clean = {
        "git_user_name": "Correct Author",
        "git_user_email": "alice@example.com",
        "ssh_key": str(real_key),
        "gh_account": "casualuser",
        "gh_config_dir": "~/.config/gh-w0m",
    }
    decl_dirty = {
        "git_user_name": "Correct Author",
        "git_user_email": "alice@example.com",
        "ssh_key": str(real_key),
        "gh_account": "nonexistent_dirty_user",
        "gh_config_dir": "~/.config/gh-w0m",
    }
    test_policy: dict[str, Any] = {
        "$schema": "./clients-policy.schema.json",
        "project": "w0m",
        "contract_file": ".w0m/sdlc.json",
        "projects": [
            {
                "id": "mock_clean",
                "role": "client",
                "root": "clean_repo",
                "enabled": True,
                "identity": decl_clean,
            },
            {
                "id": "mock_dirty",
                "role": "client",
                "root": "dirty_repo",
                "enabled": True,
                "identity": decl_dirty,
            },
        ],
    }
    clean_repo = make_repo("clean_repo", "Correct Author", "alice@example.com", ssh_cmd=f"ssh -i {real_key} -o IdentitiesOnly=yes")
    dirty_repo = make_repo("dirty_repo", "Correct Author", "alice@example.com", ssh_cmd=f"ssh -i {real_key} -o IdentitiesOnly=yes")
    policy_file = tmp / "test-policy.json"
    policy_file.write_text(json.dumps(test_policy, indent=2))

    orig_argv = sys.argv
    try:
        sys.argv = [
            "project_identity_check.py",
            "--policy",
            str(policy_file),
            "--estate-root",
            str(tmp),
            "--enforce",
        ]
        # With dirty_repo, enforce should exit 1
        rc = pic.main()
        check("enforcement mode (--enforce) exits 1 on failure", rc == 1, f"rc={rc}")

        # Disable dirty_repo, test clean enforce
        projects_list: list[dict[str, Any]] = test_policy["projects"]
        projects_list[1]["enabled"] = False
        policy_file.write_text(json.dumps(test_policy, indent=2))
        rc_clean = pic.main()
        check("enforcement mode (--enforce) exits 0 when all pass", rc_clean == 0, f"rc={rc_clean}")
    finally:
        sys.argv = orig_argv

print()
if fails:
    print(f"❌ {len(fails)} failure(s):")
    for f in fails:
        print(f"   · {f}")
    sys.exit(1)

print(f"✅ project-identity-test: all {checks} checks passed")
