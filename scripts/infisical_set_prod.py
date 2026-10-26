#!/usr/bin/env python3
"""infisical_set_prod.py — Push rotated secrets into Infisical (`prod` or `beta`) safely (T516 AC4/AC6).

Reads KEY=VALUE pairs from a local, gitignored file (e.g. `/tmp/rotate.env`) and creates/updates
them in the w0m Infisical workspace via the Infisical API. Secret *values* are NEVER printed —
only key name + create/update + [PASS]/[FAIL].

Defaults to `--dry-run` unless `--apply` is explicitly passed. Refuses to run if the input file
is inside a git repository and not gitignored.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Callable, cast
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_WORKSPACE_ID = "87a1718d-17c6-4c5e-b0c1-f8bb2fd9d13c"
ALLOWED_ENVS = ("prod", "beta")
DEFAULT_BASE_URL = "https://app.infisical.com"

ApiCaller = Callable[[str, str, str, dict[str, Any] | None], tuple[int, str]]


def _default_api_caller(
    token: str, method: str, url: str, body: dict[str, Any] | None = None
) -> tuple[int, str]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return int(resp.status), resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read().decode("utf-8", errors="replace")


def is_safe_secret_file(path: Path) -> tuple[bool, str]:
    """Verify the input file exists and is NOT an unignored file inside a git worktree."""
    if not path.is_file():
        return False, f"File not found: {path}"
    parent = str(path.resolve().parent)
    in_repo = (
        subprocess.run(
            ["git", "-C", parent, "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        == "true"
    )
    if in_repo:
        ignored = (
            subprocess.run(
                ["git", "-C", parent, "check-ignore", str(path.resolve())],
                capture_output=True,
                check=False,
            ).returncode
            == 0
        )
        if not ignored:
            return (
                False,
                f"Refusing: {path} is inside a git repo and NOT gitignored. "
                "Move it to /tmp or add it to .gitignore first.",
            )
    return True, ""


def parse_env_file(path: Path) -> dict[str, str]:
    secrets: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$", s)
        if not m:
            continue
        k, v = m.group(1), m.group(2).strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        secrets[k] = v
    return secrets


def sync_infisical_secrets(
    env_file: Path,
    token: str,
    target_env: str = "beta",
    apply: bool = False,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    base_url: str = DEFAULT_BASE_URL,
    api_caller: ApiCaller = _default_api_caller,
    skip_git_check: bool = False,
) -> tuple[bool, dict[str, int]]:
    if target_env not in ALLOWED_ENVS:
        print(f"[FAIL] Invalid target environment '{target_env}'. Allowed: {ALLOWED_ENVS}")
        return False, {"created": 0, "updated": 0, "failed": 1}

    if not token.strip():
        print("[FAIL] Set INFISICAL_TOKEN first: export INFISICAL_TOKEN='<token>'")
        return False, {"created": 0, "updated": 0, "failed": 1}

    if not skip_git_check:
        safe, reason = is_safe_secret_file(env_file)
        if not safe:
            print(f"[FAIL] {reason}")
            return False, {"created": 0, "updated": 0, "failed": 1}
    elif not env_file.is_file():
        print(f"[FAIL] File not found: {env_file}")
        return False, {"created": 0, "updated": 0, "failed": 1}

    secrets = parse_env_file(env_file)
    if not secrets:
        print(f"[FAIL] No KEY=VALUE lines found in {env_file}")
        return False, {"created": 0, "updated": 0, "failed": 1}

    query = urllib.parse.urlencode(
        {"workspaceId": workspace_id, "environment": target_env, "secretPath": "/"}
    )
    st, body = api_caller("token-check" if False else token, "GET", f"{base_url}/api/v3/secrets/raw?{query}", None)
    if st == 401:
        print("[FAIL] HTTP 401 from Infisical — token invalid or expired.")
        return False, {"created": 0, "updated": 0, "failed": 1}

    existing: set[str] = set()
    if st == 200 and body.strip():
        payload: dict[str, Any] = cast(dict[str, Any], json.loads(body))
        raw_list = payload.get("secrets", [])
        if isinstance(raw_list, list):
            existing = {
                str(x["secretKey"])
                for x in raw_list
                if isinstance(x, dict) and "secretKey" in x
            }

    print(
        f"[INFO] project=w0m | env={target_env} | input_keys={len(secrets)} | "
        f"already_in_{target_env}={len(existing)}"
    )

    created = 0
    updated = 0
    failed = 0
    for k in sorted(secrets):
        action = "update" if k in existing else "create"
        if not apply:
            print(f"  [dry-run] would {action}: {k} (env={target_env})")
            if action == "create":
                created += 1
            else:
                updated += 1
            continue

        if action == "create":
            st_w, _ = api_caller(
                token,
                "POST",
                f"{base_url}/api/v3/secrets/raw/{k}",
                {
                    "workspaceId": workspace_id,
                    "environment": target_env,
                    "secretPath": "/",
                    "secretValue": secrets[k],
                    "type": "shared",
                },
            )
            if st_w >= 400:
                st_w, _ = api_caller(
                    token,
                    "PATCH",
                    f"{base_url}/api/v3/secrets/raw/{k}",
                    {
                        "workspaceId": workspace_id,
                        "environment": target_env,
                        "secretPath": "/",
                        "secretValue": secrets[k],
                    },
                )
        else:
            st_w, _ = api_caller(
                token,
                "PATCH",
                f"{base_url}/api/v3/secrets/raw/{k}",
                {
                    "workspaceId": workspace_id,
                    "environment": target_env,
                    "secretPath": "/",
                    "secretValue": secrets[k],
                },
            )

        if 200 <= st_w < 300:
            if action == "create":
                created += 1
            else:
                updated += 1
            print(f"  [PASS] {action:6} {k:34} (env={target_env})")
        else:
            failed += 1
            print(f"  [FAIL] {action:6} {k:34} HTTP {st_w}")

    if apply:
        print(f"[INFO] Done: created={created}, updated={updated}, failed={failed}")
    else:
        print(f"[INFO] Dry run complete — re-run with --apply to push to {target_env}.")
    return failed == 0, {"created": created, "updated": updated, "failed": failed}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="infisical_set_prod.py",
        description=(
            "Push rotated secrets from a local gitignored KEY=VALUE file into Infisical "
            "(T516 AC4/AC6). Defaults to --dry-run unless --apply is passed; never prints values."
        ),
    )
    parser.add_argument(
        "env_file",
        type=Path,
        help="Path to local gitignored KEY=VALUE file (prefer /tmp/rotate.env)",
    )
    parser.add_argument(
        "--env",
        default="beta",
        choices=ALLOWED_ENVS,
        help="Target Infisical environment (default: beta, the verified active environment; prod also supported)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Preview which keys would be created/updated without writing (default)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write secrets to the target Infisical environment",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    token = os.environ.get("INFISICAL_TOKEN", "")
    ok, _ = sync_infisical_secrets(
        env_file=Path(args.env_file),
        token=token,
        target_env=str(args.env),
        apply=bool(args.apply),
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
