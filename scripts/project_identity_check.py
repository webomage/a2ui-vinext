#!/usr/bin/env python3
"""T300 AC2 / AC5 — Active runtime project identity verification probe.

Verifies that the ACTUAL, effective identity configured for git, SSH transport,
and GitHub CLI matches the identity declared in `project/clients-policy.json`.

Checks:
1. Git author: `git -C <repo> config user.name` and `user.email`
2. SSH transport: `git -C <repo> config core.sshCommand` resolves declared `ssh_key`
3. GitHub CLI: `gh api user` under declared `GH_CONFIG_DIR` resolves declared `gh_account`
4. Guards: Distinguishes PASS, FAIL, and UNMEASURABLE.
5. Secret guardrail (AC6): Confirms zero secret material in declarations.

Usage:
  just project-identity-check
  just project-identity-check --enforce
  just project-identity-check --json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ESTATE_ROOT = Path(__file__).resolve().parents[1]
WEB = ESTATE_ROOT / "wom7web"
DEFAULT_POLICY_PATH = ESTATE_ROOT / "project" / "policies" / "clients-policy.json"

SECRET_PATTERNS = [
    re.compile(r"-----BEGIN[ A-Z0-9_-]*PRIVATE KEY-----"),
    re.compile(r"ghp_[a-zA-Z0-9]{36}"),
    re.compile(r"github_pat_[a-zA-Z0-9_]{82}"),
]


def extract_ssh_key_from_command(cmd: str) -> str:
    """Extract identity key path from a core.sshCommand string, or default."""
    if not cmd:
        return "~/.ssh/id_rsa"
    m = re.search(r"-i\s+([^\s]+)", cmd)
    if m:
        return m.group(1)
    return "~/.ssh/id_rsa"


def check_no_secret_material(identity: Dict[str, Any], project_id: str) -> List[str]:
    """Ensure declared identity contains no private keys or secret tokens (AC6)."""
    errors = []
    for key, val in identity.items():
        if not isinstance(val, str):
            continue
        if "\n" in val or "\r" in val:
            errors.append(f"{project_id} identity.{key} contains multiline content (possible key material)")
        for pat in SECRET_PATTERNS:
            if pat.search(val):
                errors.append(f"{project_id} identity.{key} matches secret pattern")
    return errors


def resolve_gh_login(gh_config_dir: str, cache: Dict[str, Tuple[Optional[str], Optional[str]]]) -> Tuple[Optional[str], Optional[str]]:
    """Query `gh api user --jq .login` with isolated GH_CONFIG_DIR, caching results."""
    expanded_dir = os.path.expanduser(gh_config_dir)
    if expanded_dir in cache:
        return cache[expanded_dir]

    res: Tuple[Optional[str], Optional[str]]
    if not os.path.isdir(expanded_dir):
        res = (None, f"gh_config_dir does not exist: {gh_config_dir}")
        cache[expanded_dir] = res
        return res

    env = dict(os.environ, GH_CONFIG_DIR=expanded_dir)
    try:
        proc = subprocess.run(
            ["gh", "api", "user", "--jq", ".login"],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode != 0:
            err = proc.stderr.strip() or f"exit code {proc.returncode}"
            res = (None, f"gh api user failed: {err}")
        else:
            login = proc.stdout.strip()
            res = (login, None)
    except FileNotFoundError:
        res = (None, "gh CLI binary not found on PATH")
    except subprocess.TimeoutExpired:
        res = (None, "gh api user timed out")
    except Exception as e:
        res = (None, f"gh api error: {e}")

    cache[expanded_dir] = res
    return res


def inspect_repository(
    project_id: str,
    repo_name: str,
    repo_path: Path,
    declared_identity: Optional[Dict[str, Any]],
    gh_cache: Dict[str, Tuple[Optional[str], Optional[str]]],
) -> Dict[str, Any]:
    """Inspect actual effective git, ssh, and gh identities for a repository."""
    result: Dict[str, Any] = {
        "project": project_id,
        "repo": repo_name,
        "path": str(repo_path),
        "status": "PASS",
        "failures": [],
        "unmeasurable": [],
        "actual": {},
        "declared": declared_identity or {},
    }

    if not declared_identity:
        result["status"] = "UNMEASURABLE"
        result["unmeasurable"].append("No identity declared in policy")
        return result

    # AC6 secret material check
    sec_errs = check_no_secret_material(declared_identity, f"{project_id}:{repo_name}")
    if sec_errs:
        result["status"] = "FAIL"
        result["failures"].extend(sec_errs)
        return result

    # Check path existence and git repo validity
    if not repo_path.exists():
        result["status"] = "UNMEASURABLE"
        result["unmeasurable"].append(f"Directory does not exist: {repo_path}")
        return result

    try:
        git_check = subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if git_check.returncode != 0:
            result["status"] = "UNMEASURABLE"
            result["unmeasurable"].append(f"Not a git work tree: {repo_path}")
            return result
    except Exception as e:
        result["status"] = "UNMEASURABLE"
        result["unmeasurable"].append(f"Cannot inspect git work tree: {e}")
        return result

    # 1. Effective git author
    try:
        name_proc = subprocess.run(
            ["git", "-C", str(repo_path), "config", "user.name"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        email_proc = subprocess.run(
            ["git", "-C", str(repo_path), "config", "user.email"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        actual_name = name_proc.stdout.strip()
        actual_email = email_proc.stdout.strip()
    except Exception as e:
        result["status"] = "UNMEASURABLE"
        result["unmeasurable"].append(f"Error querying git config: {e}")
        return result

    result["actual"]["git_user_name"] = actual_name
    result["actual"]["git_user_email"] = actual_email

    exp_name = declared_identity.get("git_user_name")
    exp_email = declared_identity.get("git_user_email")

    if not actual_name:
        result["failures"].append("git user.name is empty / unconfigured")
    elif exp_name and actual_name != exp_name:
        result["failures"].append(f"git user.name: expected {exp_name!r}, got {actual_name!r}")

    if not actual_email:
        result["failures"].append("git user.email is empty / unconfigured")
    elif exp_email and actual_email != exp_email:
        result["failures"].append(f"git user.email: expected {exp_email!r}, got {actual_email!r}")

    # 2. Effective SSH transport command and key
    try:
        ssh_cmd_proc = subprocess.run(
            ["git", "-C", str(repo_path), "config", "core.sshCommand"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        actual_ssh_cmd = ssh_cmd_proc.stdout.strip()
    except Exception as e:
        actual_ssh_cmd = ""

    actual_key = extract_ssh_key_from_command(actual_ssh_cmd)
    result["actual"]["core_ssh_command"] = actual_ssh_cmd
    result["actual"]["ssh_key"] = actual_key

    exp_key = declared_identity.get("ssh_key")
    if exp_key:
        exp_expanded = os.path.expanduser(exp_key)
        actual_expanded = os.path.expanduser(actual_key)

        # Verify key file existence on disk (AC5)
        if not os.path.exists(exp_expanded):
            result["unmeasurable"].append(f"Declared ssh_key file does not exist: {exp_key}")
        elif exp_expanded != actual_expanded:
            result["failures"].append(f"ssh_key: expected {exp_key!r}, got {actual_key!r} (via core.sshCommand={actual_ssh_cmd!r})")

    # 3. Effective GitHub account
    gh_cfg = declared_identity.get("gh_config_dir")
    exp_gh_acc = declared_identity.get("gh_account")
    if gh_cfg and exp_gh_acc:
        actual_login, gh_err = resolve_gh_login(gh_cfg, gh_cache)
        result["actual"]["gh_account"] = actual_login
        result["actual"]["gh_config_dir"] = gh_cfg
        if gh_err:
            result["unmeasurable"].append(f"GitHub identity unmeasurable: {gh_err}")
        elif actual_login != exp_gh_acc:
            result["failures"].append(f"gh account: expected {exp_gh_acc!r}, got {actual_login!r} (under {gh_cfg})")

    # Aggregate status
    if result["failures"]:
        result["status"] = "FAIL"
    elif result["unmeasurable"]:
        result["status"] = "UNMEASURABLE"
    else:
        result["status"] = "PASS"

    return result


def inspect_all(policy_path: Path, estate_root: Path) -> List[Dict[str, Any]]:
    """Inspect all declared and enabled projects in clients-policy.json."""
    if not policy_path.is_file():
        raise FileNotFoundError(f"Policy file not found: {policy_path}")

    policy = json.loads(policy_path.read_text())
    gh_cache: Dict[str, Tuple[Optional[str], Optional[str]]] = {}
    results = []

    for project in policy.get("projects", []):
        if not project.get("enabled", True):
            continue

        pid = project["id"]
        p_identity = project.get("identity")
        repo_identities = project.get("repo_identities", {})
        root_str = project.get("root", ".")
        resolved_root = (estate_root / root_str).resolve()
        host_estates = (
            Path.home() / "Projects" / "!self" / "w0m",
            Path.home() / "Projects" / "@self" / "@wom",
            Path.home() / "Projects" / "w0m",
        )
        if not resolved_root.is_dir():
            for host_estate in host_estates:
                alt = (host_estate / root_str).resolve()
                if alt.is_dir():
                    resolved_root = alt
                    break

        repos_dict = project.get("repos")
        if repos_dict:
            if project.get("canonical_repo") == ".":
                res = inspect_repository(pid, ".", resolved_root, p_identity, gh_cache)
                results.append(res)
            for r_name, r_rel in repos_dict.items():
                r_path = (resolved_root / r_rel).resolve()
                if not r_path.is_dir():
                    for host_estate in host_estates:
                        alt_r = (host_estate / root_str / r_rel).resolve()
                        if alt_r.is_dir():
                            r_path = alt_r
                            break
                r_id = repo_identities.get(r_name, p_identity)
                res = inspect_repository(pid, r_name, r_path, r_id, gh_cache)
                results.append(res)
        else:
            res = inspect_repository(pid, ".", resolved_root, p_identity, gh_cache)
            results.append(res)

    return results


def print_report(results: List[Dict[str, Any]]) -> Tuple[int, int, int]:
    """Print human-readable report conforming to w0m test suite check formats."""
    passes = 0
    fails = 0
    unmeasurables = 0

    print("── Project Identity Verification (T300 AC2) ──")
    for r in results:
        target = f"{r['project']}:{r['repo']}"
        status = r["status"]
        if status == "PASS":
            passes += 1
            act = r["actual"]
            summary = f"git={act.get('git_user_email')} ssh={act.get('ssh_key')} gh={act.get('gh_account')}"
            print(f"  ✅ [PASS] {target} ({summary})")
        elif status == "FAIL":
            fails += 1
            reasons = "; ".join(r["failures"])
            print(f"  ❌ [FAIL] {target}: {reasons}")
        else:
            unmeasurables += 1
            reasons = "; ".join(r["unmeasurable"])
            print(f"  ⚠️ [UNKNOWN] {target} (UNMEASURABLE): {reasons}")

    total = len(results)
    print(f"\nSummary: {passes}/{total} passed · {fails} failed · {unmeasurables} unmeasurable")
    return passes, fails, unmeasurables


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify active project git/SSH/GitHub identities against clients-policy.json")
    parser.add_argument("--policy", type=Path, default=None, help="Path to clients-policy.json")
    parser.add_argument("--estate-root", type=Path, default=None, help="Path to estate root (@wom)")
    parser.add_argument("--enforce", action="store_true", help="Exit non-zero on any FAIL or UNMEASURABLE result")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    args = parser.parse_args()

    policy_path = args.policy or Path(os.environ.get("W0M_CLIENTS_REGISTRY") or DEFAULT_POLICY_PATH)
    estate_root = args.estate_root or (policy_path.parent.parent.parent if "wom7web" in str(policy_path) else ESTATE_ROOT)

    try:
        results = inspect_all(policy_path, estate_root)
    except Exception as e:
        print(f"❌ Error loading policy: {e}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(results, indent=2))
        if args.enforce and any(r["status"] != "PASS" for r in results):
            return 1
        return 0

    passes, fails, unmeasurables = print_report(results)

    if args.enforce:
        if fails > 0 or unmeasurables > 0:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
