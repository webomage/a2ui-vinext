#!/usr/bin/env python3
"""get_keys.py (`just keys-verify`) — Verify Supabase project API keys without printing secret values (T516 AC5).

Queries `https://api.supabase.com/v1/projects/{project_ref}/api-keys` using `SUPABASE_ACCESS_TOKEN`
from the environment and prints ONLY:
  - key `name`
  - key `type` (`legacy` / `publishable` / `secret` / role)
  - SHA-256 fingerprint (`sha256:<16-hex-prefix>`) of `api_key`

Plaintext API key values are NEVER printed to stdout, stderr, or JSON output.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from typing import Any, Callable, cast
import urllib.error
import urllib.request

DEFAULT_PROJECT_REF = "pqbbjgeapylcengbuvee"
HttpRequester = Callable[[str, dict[str, str]], tuple[int, str]]


def _default_requester(url: str, headers: dict[str, str]) -> tuple[int, str]:
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return int(resp.status), resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read().decode("utf-8", errors="replace")


def redact_and_hash_keys(raw_keys: list[Any]) -> list[dict[str, str]]:
    """Convert raw Supabase `/api-keys` items into safe `{name, type, sha256}` records."""
    safe_rows: list[dict[str, str]] = []
    for item in raw_keys:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("description") or "unnamed")
        ktype = str(item.get("type") or item.get("role") or "unknown")
        raw_val = str(item.get("api_key") or item.get("key") or "")
        digest = (
            f"sha256:{hashlib.sha256(raw_val.encode('utf-8')).hexdigest()[:16]}"
            if raw_val
            else "sha256:empty"
        )
        safe_rows.append(
            {
                "name": name,
                "type": ktype,
                "sha256": digest,
            }
        )
    return safe_rows


def verify_supabase_keys(
    access_token: str,
    project_ref: str = DEFAULT_PROJECT_REF,
    requester: HttpRequester = _default_requester,
) -> tuple[bool, list[dict[str, str]], str]:
    if not access_token.strip():
        return (
            False,
            [],
            "SUPABASE_ACCESS_TOKEN is not set. Run via Infisical: "
            "infisical run --env=beta --silent -- just keys-verify",
        )
    url = f"https://api.supabase.com/v1/projects/{project_ref}/api-keys"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }
    code, body = requester(url, headers)
    if code != 200:
        return False, [], f"Failed to retrieve keys (HTTP {code})"
    raw_list: Any = json.loads(body)
    if not isinstance(raw_list, list):
        return False, [], "Unexpected non-list response from Supabase /api-keys"
    return True, redact_and_hash_keys(raw_list), ""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="get_keys.py",
        description=(
            "Verify Supabase project API keys by printing only key name, type, and SHA-256 "
            "fingerprint — never raw key values (T516 AC5)."
        ),
    )
    parser.add_argument(
        "--project-ref",
        default=os.environ.get("SUPABASE_PROJECT_REF", DEFAULT_PROJECT_REF),
        help=f"Supabase project ref (default: {DEFAULT_PROJECT_REF})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit redacted JSON array ([{{name, type, sha256}}])",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    pat = os.environ.get("SUPABASE_ACCESS_TOKEN", "")
    ok, rows, err = verify_supabase_keys(
        access_token=pat,
        project_ref=str(args.project_ref),
    )
    if not ok:
        print(f"[FAIL] {err}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(rows, indent=2))
        return 0

    print(f"[PASS] Verified {len(rows)} Supabase API key(s) for project {args.project_ref}:")
    print(f"  {'NAME':<24} {'TYPE':<16} {'FINGERPRINT'}")
    print("  " + "-" * 64)
    for r in rows:
        print(f"  {r['name']:<24} {r['type']:<16} {r['sha256']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
