#!/usr/bin/env python3
"""Idempotently detach retired Cloudflare Worker Custom Domains (T648).

When a Worker Custom Domain (`custom_domain: true` in a retired `wrangler.jsonc`) is replaced by a
proxied `AAAA 100::` DNS record + dynamic `301` redirect ruleset in Terraform (`records.tf` +
`redirects.tf`), Cloudflare keeps a `read_only: true` `AAAA 100::` record bound to `origin_worker_id`
until the Worker Custom Domain attachment is deleted via `/accounts/{id}/workers/domains/{domain_id}`.

Run inside `just cf-apply` (after human `_confirm "cf-apply"`) right before `terraform apply` so DNS
record creation never collides with `81058: An identical record already exists`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from typing import Any, cast

CF_API_BASE = "https://api.cloudflare.com/client/v4"


def _cf_json(
    method: str,
    url: str,
    token: str,
) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
            if not raw.strip():
                return {"success": True, "result": None}
            return cast(dict[str, Any], json.loads(raw))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Cloudflare API {method} {url} failed ({exc.code}): {body[:300]}") from exc


def retire_worker_domains(
    account_id: str,
    token: str,
    hostnames: Sequence[str],
    *,
    dry_run: bool = False,
    requester: Callable[[str, str, str], dict[str, Any]] = _cf_json,
) -> list[dict[str, str]]:
    """List Worker Custom Domains on `account_id` and detach any matching `hostnames`."""
    wanted = {h.strip().lower() for h in hostnames if h.strip()}
    if not wanted:
        return []

    listing = requester("GET", f"{CF_API_BASE}/accounts/{account_id}/workers/domains", token)
    if not listing.get("success", False):
        raise RuntimeError(f"Cloudflare workers/domains list returned success=false: {listing}")

    rows: list[dict[str, Any]] = list(listing.get("result") or [])
    detached: list[dict[str, str]] = []
    for row in rows:
        hostname = str(row.get("hostname") or "").strip().lower()
        domain_id = str(row.get("id") or "").strip()
        service = str(row.get("service") or "").strip()
        if hostname not in wanted or not domain_id:
            continue
        if not dry_run:
            requester(
                "DELETE",
                f"{CF_API_BASE}/accounts/{account_id}/workers/domains/{domain_id}",
                token,
            )
        detached.append({"id": domain_id, "hostname": hostname, "service": service})
    return detached


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("hostnames", nargs="+", help="Retired Worker custom-domain hostnames to detach")
    parser.add_argument("--dry-run", action="store_true", help="Inspect live domains without deleting")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    if not token or not account_id:
        print(
            "❌ CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID are required in environment.",
            file=sys.stderr,
        )
        return 1

    hits = retire_worker_domains(
        account_id,
        token,
        args.hostnames,
        dry_run=bool(args.dry_run),
    )
    if not hits:
        print(f"ℹ️  worker-domains: 0 retired custom domain(s) attached ({', '.join(args.hostnames)})")
        return 0

    verb = "would detach" if args.dry_run else "detached"
    for h in hits:
        print(f"✅ worker-domains: {verb} {h['hostname']} -> {h['service']} (id={h['id']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
