#!/usr/bin/env python3
"""backfill_post_images — Backfill missing post cover images via Supabase Edge Function (T518 AC2).

Defaults to `--dry-run` unless `--apply` is explicitly passed. Uses stdlib `urllib.request` so
offline tests and CLI execution work without third-party HTTP/Supabase client dependencies.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
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
        with urllib.request.urlopen(req, timeout=120) as resp:
            return int(resp.status), resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read().decode("utf-8", errors="replace")


def fetch_posts_missing_images(
    supabase_url: str,
    service_key: str,
    requester: HttpRequester = _default_requester,
) -> tuple[bool, list[dict[str, Any]], str]:
    if not service_key.strip():
        return False, [], "Missing SUPABASE_SERVICE_ROLE_KEY"
    url = (
        f"{supabase_url.rstrip('/')}/rest/v1/posts"
        "?select=id,slug,title,description,image_url&image_url=is.null"
    )
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Accept": "application/json",
    }
    code, body = requester("GET", url, headers, None)
    if code != 200:
        return False, [], f"HTTP {code}: {body[:160]}"
    rows: list[dict[str, Any]] = cast(list[dict[str, Any]], json.loads(body))
    return True, rows, ""


def generate_image_via_edge_function(
    post_id: str,
    title: str,
    summary: str,
    supabase_url: str,
    service_key: str,
    requester: HttpRequester = _default_requester,
) -> dict[str, Any]:
    function_url = f"{supabase_url.rstrip('/')}/functions/v1/generate-post-image"
    headers = {
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
    }
    payload = json.dumps(
        {
            "post_id": post_id,
            "title": title,
            "summary": summary or "",
            "style": "tech",
        }
    ).encode("utf-8")
    code, body = requester("POST", function_url, headers, payload)
    if code != 200:
        return {"success": False, "error": f"HTTP {code}: {body[:160]}"}
    parsed: dict[str, Any] = cast(dict[str, Any], json.loads(body))
    return parsed


def run_backfill_images(
    supabase_url: str,
    service_key: str,
    apply: bool = False,
    limit: int | None = None,
    fail_fast: bool = False,
    batch_size: int = 10,
    batch_delay: float = 0.0,
    requester: HttpRequester = _default_requester,
) -> tuple[bool, dict[str, int]]:
    ok, posts, err = fetch_posts_missing_images(
        supabase_url=supabase_url, service_key=service_key, requester=requester
    )
    if not ok:
        print(f"[FAIL] {err}")
        return False, {"found": 0, "succeeded": 0, "failed": 1}

    if limit is not None and limit >= 0:
        posts = posts[:limit]

    if not posts:
        print("[PASS] No posts found missing images.")
        return True, {"found": 0, "succeeded": 0, "failed": 0}

    mode_str = "APPLY" if apply else "DRY-RUN"
    print(f"[INFO] Processing {len(posts)} post(s) missing images in {mode_str} mode...")

    succeeded = 0
    failed = 0
    total_batches = (len(posts) + batch_size - 1) // max(1, batch_size)

    for batch_num in range(total_batches):
        start_idx = batch_num * batch_size
        end_idx = min(start_idx + batch_size, len(posts))
        batch = posts[start_idx:end_idx]

        for post in batch:
            post_id = str(post.get("id", ""))
            slug = str(post.get("slug", ""))
            title = str(post.get("title", ""))
            description = str(post.get("description") or "")

            if not apply:
                print(f"[INFO] [dry-run] Would generate cover image for post '{slug}' ({post_id})")
                succeeded += 1
                continue

            res = generate_image_via_edge_function(
                post_id=post_id,
                title=title,
                summary=description,
                supabase_url=supabase_url,
                service_key=service_key,
                requester=requester,
            )
            if res.get("success"):
                print(f"[PASS] Generated image for '{slug}': {res.get('image_url')}")
                succeeded += 1
            else:
                print(f"[FAIL] Failed image generation for '{slug}': {res.get('error')}")
                failed += 1
                if fail_fast:
                    return False, {"found": len(posts), "succeeded": succeeded, "failed": failed}

        if apply and batch_delay > 0 and batch_num < total_batches - 1:
            time.sleep(batch_delay)

    return failed == 0, {"found": len(posts), "succeeded": succeeded, "failed": failed}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="backfill_post_images.py",
        description=(
            "Backfill missing post cover images using the `generate-post-image` Edge Function "
            "(T518 AC2). Defaults to --dry-run unless --apply is passed."
        ),
    )
    parser.add_argument("--limit", type=int, default=None, help="Limit number of posts to process")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Preview posts missing images without calling the Edge Function (default)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Call the Edge Function to generate and store missing cover images",
    )
    parser.add_argument("--fail-fast", action="store_true", help="Exit on first error")
    parser.add_argument("--batch-size", type=int, default=10, help="Batch size (default: 10)")
    parser.add_argument(
        "--batch-delay", type=float, default=5.0, help="Delay in seconds between batches (default: 5)"
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
    ok, _ = run_backfill_images(
        supabase_url=supa_url,
        service_key=svc_key,
        apply=bool(args.apply),
        limit=args.limit,
        fail_fast=bool(args.fail_fast),
        batch_size=int(args.batch_size),
        batch_delay=float(args.batch_delay),
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
