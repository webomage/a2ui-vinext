#!/usr/bin/env python3
"""upwork-poller-status — Inspect Upwork poller state and Storage `upwork` bucket objects (T517 AC5).

Replaces `w0m-api/scripts/fetch-upwork.js` (archived to `_arch/fetch-upwork/`) without hardcoded
contract file paths. Reads credentials from environment (`SUPABASE_URL` / `PUBLIC_SUPABASE_URL`
and `SUPABASE_SERVICE_ROLE_KEY`).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Callable, cast
import urllib.error
import urllib.request

DEFAULT_SUPABASE_URL = "https://pqbbjgeapylcengbuvee.supabase.co"
HttpRequester = Callable[[str, str, dict[str, str], bytes | None], tuple[int, str]]


def _default_requester(
    method: str, url: str, headers: dict[str, str], body: bytes | None
) -> tuple[int, str]:
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return int(resp.status), resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read().decode("utf-8", errors="replace")


def fetch_poller_status(
    supabase_url: str,
    service_key: str,
    prefix: str = "contracts",
    limit: int = 20,
    requester: HttpRequester = _default_requester,
) -> tuple[bool, dict[str, Any]]:
    """Query `upwork_poller_state` table and Storage `upwork` bucket `prefix` objects."""
    if not service_key.strip():
        return False, {"error": "Missing SUPABASE_SERVICE_ROLE_KEY"}

    base = supabase_url.rstrip("/")
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
    }

    state_url = f"{base}/rest/v1/upwork_poller_state?select=*"
    st_code, st_body = requester("GET", state_url, headers, None)
    if st_code != 200:
        return False, {"error": f"upwork_poller_state returned HTTP {st_code}: {st_body[:160]}"}
    poller_rows: list[dict[str, Any]] = cast(list[dict[str, Any]], json.loads(st_body))

    list_url = f"{base}/storage/v1/object/list/upwork"
    payload = json.dumps(
        {
            "prefix": prefix,
            "limit": limit,
            "offset": 0,
            "sortBy": {"column": "name", "order": "asc"},
        }
    ).encode("utf-8")
    ls_code, ls_body = requester("POST", list_url, headers, payload)
    if ls_code != 200:
        return False, {"error": f"storage list (upwork/{prefix}) returned HTTP {ls_code}: {ls_body[:160]}"}
    objects: list[dict[str, Any]] = cast(list[dict[str, Any]], json.loads(ls_body))

    return True, {
        "prefix": prefix,
        "poller_state": poller_rows,
        "storage_objects": [str(obj.get("name", "")) for obj in objects if isinstance(obj, dict)],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="upwork_poller_status.py",
        description=(
            "Inspect `upwork_poller_state` rows and `upwork` Storage bucket prefix objects "
            "without hardcoded contract paths (T517 AC5)."
        ),
    )
    parser.add_argument(
        "--prefix",
        default="contracts",
        help="Storage prefix inside the `upwork` bucket (default: contracts)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum storage objects to list (default: 20)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON output",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    supa_url = (
        os.environ.get("SUPABASE_URL")
        or os.environ.get("PUBLIC_SUPABASE_URL")
        or DEFAULT_SUPABASE_URL
    )
    svc_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    ok, result = fetch_poller_status(
        supabase_url=supa_url,
        service_key=svc_key,
        prefix=str(args.prefix),
        limit=int(args.limit),
    )
    if args.json:
        print(json.dumps(result, indent=2))
        return 0 if ok else 1

    if not ok:
        print(f"[FAIL] upwork-poller-status: {result.get('error', 'unknown error')}")
        return 1

    poller_rows = cast(list[dict[str, Any]], result.get("poller_state", []))
    storage_objs = cast(list[str], result.get("storage_objects", []))
    print(f"[PASS] upwork_poller_state rows: {len(poller_rows)}")
    for row in poller_rows:
        print(f"  - {json.dumps(row, sort_keys=True)}")
    print(f"[PASS] Storage bucket `upwork/{result.get('prefix')}` objects ({len(storage_objs)}):")
    for name in storage_objs:
        print(f"  - {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
