#!/usr/bin/env python3
"""Deterministic 4-Identity Selector & Verifier for Git, SSH, and GitHub CLI (T306).

Reads `project/policies/clients-policy.json -> identities_catalog` and `projects`
to support deterministic selection across all 4 identities:
  1. `aleksei-personal` (`casualuser`, `~/.config/gh-w0m`, `~/.ssh/id_ed25519_aleksei`)
  2. `elena-personal`   (`Shinagawa-monkey`, `~/.config/gh-elena`, `~/.ssh/id_ed25519_elena`)
  3. `aleksei-work`     (`casualuser`, `~/.config/gh-aleksei-work`, `~/.ssh/id_ed25519_aleksei_work`)
  4. `elena-work`       (`elena-w0m`, `~/.config/gh-elena-work`, `~/.ssh/id_ed25519_elena_work`)

Eliminates reliance on the global `~/.config/gh` active account (which flips across
sessions) by scoping `GH_CONFIG_DIR`, `GIT_SSH_COMMAND`, and `GIT_AUTHOR_*` /
`GIT_COMMITTER_*` per identity or project.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ESTATE_ROOT = Path(__file__).resolve().parent.parent
POLICY_PATH = ESTATE_ROOT / "project" / "policies" / "clients-policy.json"
MIGRATIONS_DIR = ESTATE_ROOT / "wom7api" / "supabase" / "migrations"

REQUIRED_IDENTITIES = (
    "aleksei-personal",
    "elena-personal",
    "aleksei-work",
    "elena-work",
)


@dataclass
class IdentitySelection:
    identity_key: str
    operator: str
    scope: str
    git_user_name: str
    git_user_email: str
    ssh_key: str
    gh_account: str
    gh_config_dir: str
    provisioning_status: str

    def resolved_ssh_key(self) -> Path:
        return Path(os.path.expanduser(self.ssh_key))

    def resolved_gh_config_dir(self) -> Path:
        return Path(os.path.expanduser(self.gh_config_dir))

    def to_env_exports(self) -> dict[str, str]:
        gh_dir = str(self.resolved_gh_config_dir())
        ssh_key = str(self.resolved_ssh_key())
        return {
            "W0M_IDENTITY_KEY": self.identity_key,
            "GH_CONFIG_DIR": gh_dir,
            "GIT_AUTHOR_NAME": self.git_user_name,
            "GIT_AUTHOR_EMAIL": self.git_user_email,
            "GIT_COMMITTER_NAME": self.git_user_name,
            "GIT_COMMITTER_EMAIL": self.git_user_email,
            "GIT_SSH_COMMAND": f"ssh -i {shlex.quote(ssh_key)} -o IdentitiesOnly=yes",
        }

    def format_shell_exports(self) -> str:
        lines = [
            f"export {k}={shlex.quote(v)}" for k, v in self.to_env_exports().items()
        ]
        return "\n".join(lines)


@dataclass
class VerificationReport:
    ok: bool
    identities: dict[str, dict[str, Any]] = field(default_factory=dict)
    offices_verified: bool = False
    bridgeroad_roles_verified: bool = False
    no_private_keys_verified: bool = False
    pending_owner_actions: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "identities": self.identities,
            "offices_verified": self.offices_verified,
            "bridgeroad_roles_verified": self.bridgeroad_roles_verified,
            "no_private_keys_verified": self.no_private_keys_verified,
            "pending_owner_actions": self.pending_owner_actions,
            "errors": self.errors,
        }


def load_policy(policy_path: Path = POLICY_PATH) -> dict[str, Any]:
    if not policy_path.is_file():
        raise FileNotFoundError(f"Policy file not found: {policy_path}")
    parsed: dict[str, Any] = json.loads(policy_path.read_text(encoding="utf-8"))
    return parsed


def parse_identity(key: str, raw: dict[str, Any]) -> IdentitySelection:
    return IdentitySelection(
        identity_key=key,
        operator=str(raw["operator"]),
        scope=str(raw["scope"]),
        git_user_name=str(raw["git_user_name"]),
        git_user_email=str(raw["git_user_email"]),
        ssh_key=str(raw["ssh_key"]),
        gh_account=str(raw["gh_account"]),
        gh_config_dir=str(raw["gh_config_dir"]),
        provisioning_status=str(raw["provisioning_status"]),
    )


def select_identity(
    *,
    identity_key: str | None = None,
    project_id: str | None = None,
    operator: str | None = None,
    policy_path: Path = POLICY_PATH,
) -> IdentitySelection:
    data = load_policy(policy_path)
    catalog = data.get("identities_catalog") or {}

    if identity_key:
        if identity_key not in catalog:
            raise KeyError(
                f"Unknown identity {identity_key!r}; valid keys: {sorted(catalog.keys())}"
            )
        return parse_identity(identity_key, catalog[identity_key])

    if project_id:
        projects = {p.get("id"): p for p in data.get("projects") or [] if isinstance(p, dict)}
        proj = projects.get(project_id)
        if not proj:
            raise KeyError(f"Unknown project {project_id!r} in clients-policy.json")
        role_assignments = proj.get("role_assignments") or {}
        if operator and operator in role_assignments:
            target_key = role_assignments[operator].get("identity_key")
            if target_key in catalog:
                return parse_identity(target_key, catalog[target_key])
        # Match by project.identity gh_account
        proj_ident = proj.get("identity") or {}
        gh_acct = proj_ident.get("gh_account")
        for k, entry in catalog.items():
            if entry.get("gh_account") == gh_acct:
                return parse_identity(k, entry)

    raise ValueError("Must provide --select <identity_key> or --project <project_id>")


def provision_work_dirs(policy_path: Path = POLICY_PATH) -> list[str]:
    """Ensure every declared GH_CONFIG_DIR directory exists on disk with 0700 permissions."""
    data = load_policy(policy_path)
    catalog = data.get("identities_catalog") or {}
    created_or_verified: list[str] = []
    for key, raw in catalog.items():
        ident = parse_identity(key, raw)
        d = ident.resolved_gh_config_dir()
        d.mkdir(parents=True, exist_ok=True)
        try:
            d.chmod(0o700)
        except OSError:
            pass
        created_or_verified.append(str(d))
    return created_or_verified


def verify_identities(
    *,
    policy_path: Path = POLICY_PATH,
    migrations_dir: Path = MIGRATIONS_DIR,
) -> VerificationReport:
    errors: list[str] = []
    pending_owner_actions: list[str] = []
    identities_out: dict[str, dict[str, Any]] = {}

    try:
        data = load_policy(policy_path)
    except Exception as exc:
        return VerificationReport(ok=False, errors=[str(exc)])

    catalog = data.get("identities_catalog")
    if not isinstance(catalog, dict):
        return VerificationReport(
            ok=False,
            errors=["Missing `identities_catalog` object in clients-policy.json"],
        )

    for req_key in REQUIRED_IDENTITIES:
        if req_key not in catalog:
            errors.append(f"Missing required identity {req_key!r} in identities_catalog")

    seen_ssh_keys: dict[str, str] = {}
    seen_gh_dirs: dict[str, str] = {}
    for key, raw in catalog.items():
        if not isinstance(raw, dict):
            errors.append(f"Identity {key!r} must be an object")
            continue
        ident = parse_identity(key, raw)
        ssh_path = ident.resolved_ssh_key()
        gh_dir = ident.resolved_gh_config_dir()
        ssh_exists = ssh_path.exists()
        gh_dir_exists = gh_dir.is_dir()
        gh_hosts_exists = (gh_dir / "hosts.yml").is_file()

        if not ssh_exists:
            errors.append(f"Identity {key!r} SSH key does not exist on host: {ssh_path}")
        else:
            real_ssh = str(ssh_path.resolve())
            if real_ssh in seen_ssh_keys:
                errors.append(
                    f"AC1 VIOLATION: Identity {key!r} shares SSH key material ({real_ssh}) with {seen_ssh_keys[real_ssh]!r}"
                )
            else:
                seen_ssh_keys[real_ssh] = key

        if not gh_dir_exists:
            errors.append(f"Identity {key!r} GH_CONFIG_DIR does not exist on host: {gh_dir}")
        else:
            real_gh = str(gh_dir.resolve())
            if real_gh in seen_gh_dirs:
                errors.append(
                    f"AC2 VIOLATION: Identity {key!r} shares GH_CONFIG_DIR ({real_gh}) with {seen_gh_dirs[real_gh]!r}"
                )
            else:
                seen_gh_dirs[real_gh] = key

        if ident.scope == "work" and not gh_hosts_exists:
            pending_owner_actions.append(
                f"{key}: GH_CONFIG_DIR={gh_dir} provisioned; awaiting owner `GH_CONFIG_DIR={gh_dir} gh auth login` for {ident.gh_account} ({ident.git_user_email})"
            )

        identities_out[key] = {
            "operator": ident.operator,
            "scope": ident.scope,
            "gh_account": ident.gh_account,
            "git_user_email": ident.git_user_email,
            "ssh_key": ident.ssh_key,
            "ssh_key_exists": ssh_exists,
            "gh_config_dir": ident.gh_config_dir,
            "gh_dir_exists": gh_dir_exists,
            "gh_hosts_authenticated": gh_hosts_exists,
            "provisioning_status": ident.provisioning_status,
        }

    # AC4: Verify canonical offices (`tech.lead` / `tl` and `project.manager` / `pm`) and retirement of `tpm`
    offices_ok = False
    cap_mig = migrations_dir / "20260720180000_capabilities_and_offices.sql"
    dedup_mig = migrations_dir / "20260905120000_t319_dedup_delivery_roles.sql"
    if cap_mig.is_file() and dedup_mig.is_file():
        cap_text = cap_mig.read_text(encoding="utf-8")
        dedup_text = dedup_mig.read_text(encoding="utf-8")
        if (
            "'tech.lead'" in cap_text
            and "'project.manager'" in cap_text
            and "tpm (duplicate of tech-lead)" in dedup_text
        ):
            offices_ok = True
        else:
            errors.append(
                "AC4: Expected 'tech.lead' and 'project.manager' in 20260720180000_capabilities_and_offices.sql and tpm dedup in 20260905120000_t319_dedup_delivery_roles.sql"
            )
    else:
        errors.append(
            f"AC4: Canonical office migrations not found under {migrations_dir}"
        )

    # AC7: Verify BridgeRoad role assignments (Aleksei = tl/tech.lead, Elena = pm/project.manager + dev/developer, no tpm)
    bridgeroad_ok = False
    projects = {p.get("id"): p for p in data.get("projects") or [] if isinstance(p, dict)}
    br = projects.get("bridgeroad")
    if isinstance(br, dict):
        ra = br.get("role_assignments") or {}
        aleksei_hats = set((ra.get("aleksei") or {}).get("hats") or [])
        elena_hats = set((ra.get("elena") or {}).get("hats") or [])
        if (
            "tl" in aleksei_hats
            and "pm" in elena_hats
            and "dev" in elena_hats
            and "tpm" not in aleksei_hats
            and "tpm" not in elena_hats
        ):
            bridgeroad_ok = True
        else:
            errors.append(
                f"AC7: BridgeRoad role_assignments invalid (aleksei={sorted(aleksei_hats)}, elena={sorted(elena_hats)})"
            )
    else:
        errors.append("AC7: Project 'bridgeroad' not found in clients-policy.json")

    # AC6: Verify no private key material is present in policy or selector script
    no_priv_keys = True
    priv_marker = "BEGIN " + "OPENSSH PRIVATE KEY"
    rsa_marker = "BEGIN " + "RSA PRIVATE KEY"
    for check_file in (policy_path, Path(__file__).resolve()):
        if check_file.is_file():
            content = check_file.read_text(encoding="utf-8")
            if priv_marker in content or rsa_marker in content:
                no_priv_keys = False
                errors.append(f"AC6 VIOLATION: Private key material found in {check_file}")

    return VerificationReport(
        ok=len(errors) == 0,
        identities=identities_out,
        offices_verified=offices_ok,
        bridgeroad_roles_verified=bridgeroad_ok,
        no_private_keys_verified=no_priv_keys,
        pending_owner_actions=pending_owner_actions,
        errors=errors,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Select and verify the 4 personal/work Git & GitHub CLI identities (T306)."
    )
    parser.add_argument(
        "--select",
        metavar="IDENTITY_KEY",
        help="Output shell export statements for the given identity key (e.g. aleksei-personal, elena-work).",
    )
    parser.add_argument(
        "--project",
        metavar="PROJECT_ID",
        help="Select identity by project id from clients-policy.json (e.g. bridgeroad, w0m).",
    )
    parser.add_argument(
        "--operator",
        choices=["aleksei", "elena"],
        help="Optional operator filter when selecting by --project.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all 4 declared identities and their paths.",
    )
    parser.add_argument(
        "--provision-work-dirs",
        action="store_true",
        help="Ensure all 4 GH_CONFIG_DIR directories exist with 0700 permissions.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify all 4 identities, SSH key paths, GH_CONFIG_DIRs, office seeds, and BridgeRoad role assignments.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON output.",
    )
    args = parser.parse_args(argv)

    if args.provision_work_dirs:
        dirs = provision_work_dirs()
        if args.json:
            print(json.dumps({"provisioned_gh_config_dirs": dirs}, indent=2))
        else:
            for d in dirs:
                print(f"PROVISIONED_GH_CONFIG_DIR: {d}")
        if not (args.verify or args.list or args.select or args.project):
            return 0

    if args.select or args.project:
        try:
            sel = select_identity(
                identity_key=args.select,
                project_id=args.project,
                operator=args.operator,
            )
        except Exception as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps(sel.to_env_exports(), indent=2))
        else:
            print(sel.format_shell_exports())
        return 0

    if args.list:
        data = load_policy()
        catalog = data.get("identities_catalog") or {}
        if args.json:
            print(json.dumps(catalog, indent=2))
        else:
            for k, v in catalog.items():
                print(
                    f"{k}: gh_account={v.get('gh_account')} email={v.get('git_user_email')} "
                    f"ssh_key={v.get('ssh_key')} gh_config_dir={v.get('gh_config_dir')} "
                    f"status={v.get('provisioning_status')}"
                )
        return 0

    # Default or --verify: run verification
    report = verify_identities()
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
        return 0 if report.ok else 1

    if report.ok:
        print(
            f"GH_IDENTITY_VERIFY_OK: {len(report.identities)} identities verified "
            f"(offices_verified={report.offices_verified}, "
            f"bridgeroad_roles_verified={report.bridgeroad_roles_verified}, "
            f"no_private_keys_verified={report.no_private_keys_verified})"
        )
        for k, info in report.identities.items():
            print(
                f"  - {k}: ssh_key_exists={info['ssh_key_exists']} "
                f"gh_dir_exists={info['gh_dir_exists']} "
                f"gh_hosts_authenticated={info['gh_hosts_authenticated']}"
            )
        for pending in report.pending_owner_actions:
            print(f"  - [PENDING_OWNER_ACTION] {pending}")
        return 0

    for err in report.errors:
        print(f"GH_IDENTITY_VERIFY_FAIL: {err}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
