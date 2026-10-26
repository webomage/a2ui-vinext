#!/usr/bin/env python3
"""backfill_news — Backfill daily news posts from Hacker News Algolia API (T518 AC2).

Defaults to `--dry-run` unless `--apply` is explicitly passed. Resolves all paths dynamically
relative to the estate root (`ESTATE_ROOT`) without hardcoded `/Users/proto/...` paths.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Callable, cast
from urllib import request

ESTATE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_POSTS_DIR = ESTATE_ROOT / "w0m-web" / "apps" / "web" / "src" / "content" / "posts"
DEFAULT_GENERATOR_SCRIPT = ESTATE_ROOT / "w0m-api" / "scripts" / "generate_news_post.py"

HnFetcher = Callable[[datetime.date, int], list[dict[str, Any]]]


def get_existing_counts(posts_dir: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    if not posts_dir.exists():
        return counts
    for f in posts_dir.glob("*.md"):
        parts = f.name.split("-")
        if len(parts) > 3:
            date_str = "-".join(parts[:3])
            counts[date_str] = counts.get(date_str, 0) + 1
    return counts


def fetch_hn_stories(date_obj: datetime.date, limit: int = 20) -> list[dict[str, Any]]:
    start_ts = int(
        datetime.datetime(
            date_obj.year, date_obj.month, date_obj.day, tzinfo=datetime.timezone.utc
        ).timestamp()
    )
    end_ts = start_ts + 86400
    url = (
        f"https://hn.algolia.com/api/v1/search_by_date?"
        f"tags=story&numericFilters=created_at_i>{start_ts},created_at_i<{end_ts}&hitsPerPage={limit}"
    )
    try:
        with request.urlopen(url, timeout=15) as resp:
            data: dict[str, Any] = cast(dict[str, Any], json.loads(resp.read().decode("utf-8")))
            hits = data.get("hits", [])
            return cast(list[dict[str, Any]], hits) if isinstance(hits, list) else []
    except Exception as exc:
        print(f"[WARN] Error fetching HN for {date_obj}: {exc}")
        return []


def slugify(text: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in text.lower()).strip("-")


def generate_post(
    story: dict[str, Any],
    date_str: str,
    apply: bool = False,
    generator_script: Path = DEFAULT_GENERATOR_SCRIPT,
) -> bool:
    title = str(story.get("title") or "").strip()
    url = str(story.get("url") or "").strip()
    if not url or not title:
        return False

    slug = slugify(title)[:50]
    cmd = [
        sys.executable,
        str(generator_script),
        "--source-url",
        url,
        "--title-hint",
        title,
        "--slug",
        slug,
        "--categories",
        "news, technology",
        "--tags",
        "tech, ai, devops",
        "--date",
        date_str,
    ]
    if not apply:
        print(f"[INFO] [dry-run] Would generate post for '{title}' ({url}) on {date_str}")
        return True

    print(f"[INFO] Generating post for: {title} ({url})")
    try:
        subprocess.run(cmd, check=True)
        return True
    except subprocess.CalledProcessError as exc:
        print(f"[FAIL] Failed to generate post: {exc}")
        return False


def backfill_range(
    start_date: datetime.date,
    end_date: datetime.date,
    posts_dir: Path = DEFAULT_POSTS_DIR,
    target_per_day: int = 7,
    apply: bool = False,
    fetcher: HnFetcher = fetch_hn_stories,
    generator_script: Path = DEFAULT_GENERATOR_SCRIPT,
) -> dict[str, int]:
    if start_date > end_date:
        raise ValueError(f"start_date ({start_date}) cannot be after end_date ({end_date})")

    existing_counts = get_existing_counts(posts_dir)
    current_date = start_date
    total_planned_or_generated = 0
    days_checked = 0

    while current_date <= end_date:
        days_checked += 1
        date_str = current_date.isoformat()
        count = existing_counts.get(date_str, 0)
        needed = max(0, target_per_day - count)
        print(f"[INFO] Date: {date_str}, Existing: {count}, Needed: {needed}")

        if needed > 0:
            stories = fetcher(current_date, needed * 3)
            generated = 0
            for story in stories:
                if generated >= needed:
                    break
                if not story.get("url"):
                    continue
                if generate_post(
                    story,
                    date_str,
                    apply=apply,
                    generator_script=generator_script,
                ):
                    generated += 1
                    total_planned_or_generated += 1
                    if apply:
                        time.sleep(1)

        current_date += datetime.timedelta(days=1)

    return {"days_checked": days_checked, "posts_processed": total_planned_or_generated}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="backfill_news.py",
        description=(
            "Backfill daily news posts from Hacker News Algolia API (T518 AC2). "
            "Defaults to --dry-run unless --apply is passed."
        ),
    )
    parser.add_argument(
        "--start-date",
        default=datetime.date.today().isoformat(),
        help="Start date in YYYY-MM-DD format (default: today)",
    )
    parser.add_argument(
        "--end-date",
        default=datetime.date.today().isoformat(),
        help="End date in YYYY-MM-DD format (default: today)",
    )
    parser.add_argument(
        "--target-per-day",
        type=int,
        default=7,
        help="Target posts per day (default: 7)",
    )
    parser.add_argument(
        "--posts-dir",
        type=Path,
        default=DEFAULT_POSTS_DIR,
        help="Directory containing markdown posts",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Preview planned posts without invoking generator (default)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Execute post generation for missing daily slots",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if "WEBOMAGE_SITE_PATH" not in os.environ:
        os.environ["WEBOMAGE_SITE_PATH"] = str(ESTATE_ROOT / "w0m-web")

    try:
        start_d = datetime.date.fromisoformat(str(args.start_date))
        end_d = datetime.date.fromisoformat(str(args.end_date))
        summary = backfill_range(
            start_date=start_d,
            end_date=end_d,
            posts_dir=Path(args.posts_dir),
            target_per_day=int(args.target_per_day),
            apply=bool(args.apply),
        )
    except ValueError as exc:
        print(f"[FAIL] {exc}")
        return 1

    mode_str = "APPLY" if args.apply else "DRY-RUN"
    print(
        f"[PASS] backfill_news ({mode_str}): checked {summary['days_checked']} day(s), "
        f"processed {summary['posts_processed']} post(s)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
