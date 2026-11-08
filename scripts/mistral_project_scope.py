#!/usr/bin/env python3
"""Per-project Mistral Free-Tier account & Obsidian private project-data scope manager (`T677`).

Enforces strict tenant isolation (`AgDR-0025`, `AgDR-0055`, `T302`) for Mistral Free-Tier
accounts connected to Obsidian vaults (`RAIT-09/obsidian-agent-client`, `vibe-acp`, and `@wom`
AI endpoints):
  - 1 project = 1 project e-mail (`<project_id>@webomage.com`)
  - 1 project = 1 isolated Infisical secret (`MISTRAL_API_KEY_<PROJECT_UPPER>`)
  - 1 project = 1 private data scope (`w0m-web/projects/<vault_slug>/vault` + `r2_prefix`)
  - Zero cross-project vault reads and zero global-key fallback for non-`w0m` client projects.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Sequence

ESTATE_ROOT = Path(__file__).resolve().parents[1]
CLIENTS_POLICY_PATH = ESTATE_ROOT / "project" / "policies" / "clients-policy.json"
DEFAULT_EMAIL_DOMAIN = "webomage.com"
DEFAULT_CHAT_MODEL = "mistral-small-latest"
DEFAULT_EMBED_MODEL = "mistral-embed"
DEFAULT_EMBED_DIM = 1024


@dataclass(frozen=True)
class ProjectMistralScope:
    project_id: str
    role: str
    org_slug: str
    account_email: str
    infisical_secret_key: str
    vault_slug: str | None
    engagement_public_id: str | None
    corpus_root: str | None
    r2_bucket: str | None
    r2_prefix: str | None
    allowed_prefixes: tuple[str, ...]
    denied_prefixes: tuple[str, ...]
    strict_tenant_isolation: bool
    allow_global_key_fallback: bool
    chat_model: str
    embed_model: str
    embed_dim: int


def sanitize_env_suffix(project_id: str) -> str:
    """Convert `project_id` (e.g. `artemio`, `1945`, `w0m`) to uppercase env suffix."""
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", project_id.strip()).strip("_").upper()
    return cleaned or "UNKNOWN"


def secret_key_for_project(project_id: str) -> str:
    """Return canonical Infisical secret key name `MISTRAL_API_KEY_<PROJECT_UPPER>`."""
    return f"MISTRAL_API_KEY_{sanitize_env_suffix(project_id)}"


def email_for_project(project_id: str, domain: str = DEFAULT_EMAIL_DOMAIN) -> str:
    """Return canonical per-project registration email `<project_id>@webomage.com`."""
    slug = project_id.strip().lower()
    return f"{slug}@{domain}"


def fingerprint_secret(value: str) -> str:
    """Return 12-char SHA-256 fingerprint of a secret without exposing plaintext."""
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"sha256:{digest[:12]}"


def load_project_scopes(policy_path: Path = CLIENTS_POLICY_PATH) -> list[ProjectMistralScope]:
    """Load all enabled project Mistral private-data scopes from `clients-policy.json`."""
    raw = json.loads(policy_path.read_text(encoding="utf-8"))
    scopes: list[ProjectMistralScope] = []
    for proj in raw.get("projects", []):
        if not proj.get("enabled", True):
            continue
        pid = str(proj["id"]).strip()
        role = str(proj.get("role", "managed")).strip()
        org_slug = str(proj.get("org_slug") or pid).strip()
        kh = proj.get("knowledge_hub") or {}
        vault_slug = str(kh["vault_slug"]).strip() if kh.get("vault_slug") else None
        engagement_id = (
            str(kh["engagement_public_id"]).strip() if kh.get("engagement_public_id") else None
        )
        corpus_root = str(kh["corpus_root"]).strip() if kh.get("corpus_root") else None
        r2_bucket = str(kh["r2_bucket"]).strip() if kh.get("r2_bucket") else None
        r2_prefix = str(kh["r2_prefix"]).strip() if kh.get("r2_prefix") else None
        allowed = tuple(str(x) for x in (kh.get("allowed_prefixes") or []))
        denied = tuple(str(x) for x in (kh.get("denied_prefixes") or []))

        scopes.append(
            ProjectMistralScope(
                project_id=pid,
                role=role,
                org_slug=org_slug,
                account_email=email_for_project(pid),
                infisical_secret_key=secret_key_for_project(pid),
                vault_slug=vault_slug,
                engagement_public_id=engagement_id,
                corpus_root=corpus_root,
                r2_bucket=r2_bucket,
                r2_prefix=r2_prefix,
                allowed_prefixes=allowed,
                denied_prefixes=denied,
                strict_tenant_isolation=True,
                allow_global_key_fallback=(pid == "w0m"),
                chat_model=DEFAULT_CHAT_MODEL,
                embed_model=DEFAULT_EMBED_MODEL,
                embed_dim=DEFAULT_EMBED_DIM,
            )
        )
    return scopes


def get_project_scope(
    project_id: str,
    policy_path: Path = CLIENTS_POLICY_PATH,
) -> ProjectMistralScope:
    """Resolve a single project's Mistral scope or raise `KeyError` (fail-closed)."""
    target = project_id.strip().lower()
    for sc in load_project_scopes(policy_path=policy_path):
        if sc.project_id.lower() == target or (sc.vault_slug and sc.vault_slug.lower() == target):
            return sc
    raise KeyError(f"Unknown or disabled project_id: {project_id!r}")


def validate_project_data_access(
    scope: ProjectMistralScope,
    candidate_path: str,
) -> tuple[bool, str]:
    """Verify whether `candidate_path` is permitted under `scope`'s private project data boundary.

    Fail-closed (`AgDR-0025` / `T302`):
      1. Project must have a declared `corpus_root`.
      2. Path must not contain `..` traversal segments.
      3. Path must reside inside `scope.corpus_root`.
      4. Relative path inside `corpus_root` must not match any `denied_prefixes`
         (`inbox/`, `.obsidian/`, `internal/`, `.w0m/`, `openspec/`).
      5. Relative path inside `corpus_root` must match at least one `allowed_prefixes`.
    """
    if not scope.corpus_root:
        return False, f"project {scope.project_id!r} has no declared Obsidian vault corpus_root"

    norm = candidate_path.strip().replace("\\", "/").lstrip("/")
    if not norm:
        return False, "empty candidate path"

    parts = [p for p in norm.split("/") if p]
    if ".." in parts or "." in parts:
        return False, "path traversal segments are forbidden"

    corpus_prefix = scope.corpus_root.strip().replace("\\", "/").strip("/")
    if norm == corpus_prefix:
        return False, "directory root without file target is not a valid note path"

    if norm.startswith(corpus_prefix + "/"):
        inner_rel = norm[len(corpus_prefix) + 1 :]
    else:
        return (
            False,
            f"cross-project data access denied: {norm!r} is outside {corpus_prefix!r}",
        )

    for denied in scope.denied_prefixes:
        d_clean = denied.strip("/")
        if inner_rel == d_clean or inner_rel.startswith(d_clean + "/") or f"/{d_clean}/" in f"/{inner_rel}":
            return (
                False,
                f"private scope denied prefix {denied!r} matched for {inner_rel!r}",
            )

    if scope.allowed_prefixes:
        matched_allowed = False
        for allowed in scope.allowed_prefixes:
            if allowed.endswith("/"):
                if inner_rel.startswith(allowed):
                    matched_allowed = True
                    break
            elif inner_rel == allowed:
                matched_allowed = True
                break
        if not matched_allowed:
            return (
                False,
                f"path {inner_rel!r} is not in allowed_prefixes {list(scope.allowed_prefixes)}",
            )

    return True, f"allowed within {corpus_prefix}/{inner_rel}"


def resolve_project_mistral_key_from_env(
    scope: ProjectMistralScope,
    env_map: dict[str, str],
) -> tuple[str | None, str]:
    """Resolve the isolated Mistral API key for `scope` from `env_map` without cross-tenant leakage."""
    dedicated = (env_map.get(scope.infisical_secret_key) or "").strip()
    if dedicated:
        return dedicated, scope.infisical_secret_key

    if scope.allow_global_key_fallback:
        global_key = (env_map.get("MISTRAL_API_KEY") or "").strip()
        if global_key:
            return global_key, "MISTRAL_API_KEY"

    return (
        None,
        f"missing {scope.infisical_secret_key} (global fallback disabled for tenant {scope.project_id!r})",
    )


def build_obsidian_acp_profile(
    scope: ProjectMistralScope,
    *,
    infisical_env: str = "dev",
) -> dict[str, Any]:
    """Build the Obsidian ACP (`obsidian-agent-client` / `vibe-acp`) + Mistral private vault config."""
    vault_dir = (
        str(ESTATE_ROOT / scope.corpus_root)
        if scope.corpus_root
        else str(ESTATE_ROOT)
    )
    return {
        "schema": "w0m.obsidian.mistral-private-scope.v1",
        "project_id": scope.project_id,
        "org_slug": scope.org_slug,
        "account_email": scope.account_email,
        "infisical_env": infisical_env,
        "infisical_secret_key": scope.infisical_secret_key,
        "chat_model": scope.chat_model,
        "embed_model": scope.embed_model,
        "embed_dim": scope.embed_dim,
        "private_data_scope": {
            "isolation_mode": "strict_per_project_tenant",
            "cross_project_access": False,
            "allow_global_key_fallback": scope.allow_global_key_fallback,
            "vault_slug": scope.vault_slug,
            "engagement_public_id": scope.engagement_public_id,
            "corpus_root": scope.corpus_root,
            "r2_bucket": scope.r2_bucket,
            "r2_prefix": scope.r2_prefix,
            "allowed_prefixes": list(scope.allowed_prefixes),
            "denied_prefixes": list(scope.denied_prefixes),
        },
        "obsidian_acp_client": {
            "plugin": "obsidian-agent-client",
            "agent_id": f"mistral-vibe-{scope.project_id}",
            "display_name": f"Mistral Vibe ({scope.project_id}@webomage.com)",
            "cwd": vault_dir,
            "command": "infisical",
            "args": [
                "run",
                f"--env={infisical_env}",
                "--silent",
                "--",
                "sh",
                "-c",
                (
                    (
                        f'MISTRAL_API_KEY="${{{scope.infisical_secret_key}:-${{MISTRAL_API_KEY:-}}}}" '
                        if scope.allow_global_key_fallback
                        else f'MISTRAL_API_KEY="${{{scope.infisical_secret_key}:?missing dedicated project Mistral key}}" '
                    )
                    + f'W0M_PROJECT_DATA_SCOPE="{scope.project_id}" '
                    + 'W0M_MISTRAL_STRICT_TENANT="1" '
                    + "exec vibe-acp"
                ),
            ],
        },
    }


def _fetch_infisical_env_map(env_slug: str) -> dict[str, str]:
    try:
        proc = subprocess.run(
            ["infisical", "export", f"--env={env_slug}", "--format=json"],
            cwd=ESTATE_ROOT,
            capture_output=True,
            text=True,
            timeout=15.0,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    if proc.returncode != 0 or not proc.stdout.strip():
        return {}
    try:
        rows = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {}
    out: dict[str, str] = {}
    if isinstance(rows, list):
        for item in rows:
            if isinstance(item, dict) and item.get("key"):
                out[str(item["key"])] = str(item.get("value") or "")
    return out


def inspect_infisical_status(
    scopes: Sequence[ProjectMistralScope],
    *,
    env_slug: str = "dev",
    env_map_override: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Inspect per-project Mistral key provisioning status in Infisical (`env_slug`)."""
    env_map = env_map_override if env_map_override is not None else _fetch_infisical_env_map(env_slug)
    rows: list[dict[str, Any]] = []
    for sc in scopes:
        val, source_key = resolve_project_mistral_key_from_env(sc, env_map)
        dedicated_present = bool((env_map.get(sc.infisical_secret_key) or "").strip())
        status = (
            "ACTIVE_DEDICATED"
            if dedicated_present
            else ("ACTIVE_GLOBAL_FALLBACK" if val else "PENDING_REGISTRATION")
        )
        rows.append(
            {
                "project_id": sc.project_id,
                "account_email": sc.account_email,
                "secret_key": sc.infisical_secret_key,
                "vault_slug": sc.vault_slug or "-",
                "corpus_root": sc.corpus_root or "-",
                "r2_prefix": sc.r2_prefix or "-",
                "status": status,
                "source_key": source_key if val else "-",
                "fingerprint": fingerprint_secret(val) if val else "-",
                "strict_tenant_isolation": sc.strict_tenant_isolation,
            }
        )
    return rows


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Manage per-project Mistral Free-Tier accounts & Obsidian private project data scopes (T677)."
    )
    sub = ap.add_subparsers(dest="cmd")

    p_status = sub.add_parser("status", help="Show per-project Mistral account & private scope status")
    p_status.add_argument("--env", default="dev", help="Infisical environment slug (default: dev)")
    p_status.add_argument("--offline", action="store_true", help="Skip live Infisical export query")
    p_status.add_argument("--json", action="store_true", help="Emit JSON output")

    p_profile = sub.add_parser(
        "obsidian-profile",
        help="Emit Obsidian ACP (vibe-acp) + Mistral private scope profile for a project",
    )
    p_profile.add_argument("project", help="Project ID (e.g. w0m, artemio, servicios777, solar)")
    p_profile.add_argument("--env", default="dev", help="Infisical environment slug")

    p_check = sub.add_parser(
        "check-access",
        help="Verify whether a file path is allowed inside a project's private Mistral data scope",
    )
    p_check.add_argument("project", help="Project ID")
    p_check.add_argument("path", help="Candidate repo-relative file path")

    args = ap.parse_args(list(argv) if argv is not None else None)
    cmd = args.cmd or "status"

    scopes = load_project_scopes()

    if cmd == "obsidian-profile":
        sc = get_project_scope(args.project)
        prof = build_obsidian_acp_profile(sc, infisical_env=args.env)
        print(json.dumps(prof, indent=2))
        return 0

    if cmd == "check-access":
        sc = get_project_scope(args.project)
        ok, reason = validate_project_data_access(sc, args.path)
        verdict = "[OK]" if ok else "[DENIED]"
        print(f"{verdict} project={sc.project_id} path={args.path} -> {reason}")
        return 0 if ok else 1

    env_slug = getattr(args, "env", "dev")
    offline = bool(getattr(args, "offline", False))
    rows = inspect_infisical_status(
        scopes,
        env_slug=env_slug,
        env_map_override={} if offline else None,
    )
    if getattr(args, "json", False):
        print(json.dumps({"env": env_slug, "projects": rows}, indent=2))
        return 0

    print(
        f"{'PROJECT':14} {'ACCOUNT EMAIL':26} {'INFISICAL SECRET KEY':30} "
        f"{'VAULT / CORPUS ROOT':34} {'STATUS':22} {'FINGERPRINT'}"
    )
    print("-" * 148)
    for r in rows:
        print(
            f"{r['project_id']:14} {r['account_email']:26} {r['secret_key']:30} "
            f"{r['corpus_root']:34} {r['status']:22} {r['fingerprint']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
