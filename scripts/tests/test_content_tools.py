#!/usr/bin/env python3
"""Offline unit & red-probe suite for T518 content & tracks tools:
- `scripts/backfill_news.py`
- `scripts/backfill_post_images.py`
- `scripts/validate_content.py`
- `scripts/validate_tracks.py`
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "w0m-api" / "scripts"))

import ai_tools  # noqa: E402
import backfill_news  # noqa: E402
import backfill_post_images  # noqa: E402
import validate_content  # noqa: E402
import validate_tracks  # noqa: E402


def _check(name: str, ok: bool, detail: str = "") -> bool:
    tag = "[PASS]" if ok else "[FAIL]"
    suffix = f" ({detail})" if detail else ""
    print(f"  {tag} {name}{suffix}")
    return ok


def main() -> int:
    print("T518 AC2/AC3 — content & tracks tools offline unit & red-probe suite\n")
    failures = 0

    # 1. CLI --help checks on all 4 scripts
    for script_name in (
        "backfill_news.py",
        "backfill_post_images.py",
        "validate_content.py",
        "validate_tracks.py",
    ):
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / script_name), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        if not _check(f"{script_name} --help exits 0", proc.returncode == 0):
            failures += 1

    # 2. backfill_news: dry-run default + red probe on invalid date range
    with tempfile.TemporaryDirectory() as tmp:
        pdir = Path(tmp)
        (pdir / "2026-10-20-existing.md").write_text("---\ntitle: T\n---\n", encoding="utf-8")
        d = datetime.date(2026, 10, 20)
        summary = backfill_news.backfill_range(
            start_date=d,
            end_date=d,
            posts_dir=pdir,
            target_per_day=2,
            apply=False,
            fetcher=lambda _d, _lim: [{"title": "Sample Story", "url": "https://example.com/a"}],
        )
        if not _check(
            "backfill_news dry-run computes needed daily slots without writing files",
            summary["days_checked"] == 1 and summary["posts_processed"] == 1,
        ):
            failures += 1

        try:
            backfill_news.backfill_range(
                start_date=datetime.date(2026, 10, 25),
                end_date=datetime.date(2026, 10, 20),
                posts_dir=pdir,
            )
            red_date = False
        except ValueError:
            red_date = True
        if not _check(
            "RED PROBE: backfill_news rejects start_date after end_date",
            red_date,
        ):
            failures += 1

    # 3. backfill_post_images: dry-run default + red probe on Edge Function failure
    edge_calls: list[str] = []

    def fake_img_req(
        method: str, url: str, headers: dict[str, str], body: bytes | None
    ) -> tuple[int, str]:
        if method == "GET" and "/rest/v1/posts" in url:
            return 200, json.dumps(
                [{"id": "p-1", "slug": "post-one", "title": "Post One", "description": "Desc"}]
            )
        if method == "POST" and "/functions/v1/generate-post-image" in url:
            edge_calls.append(url)
            return 500, "Edge failure"
        return 404, "{}"

    ok_dry, stats_dry = backfill_post_images.run_backfill_images(
        supabase_url="https://example.supabase.co",
        service_key="fake-service-key",
        apply=False,
        requester=fake_img_req,
    )
    if not _check(
        "backfill_post_images dry-run does not invoke generate-post-image Edge Function",
        ok_dry and stats_dry["found"] == 1 and len(edge_calls) == 0,
    ):
        failures += 1

    ok_red_img, stats_red_img = backfill_post_images.run_backfill_images(
        supabase_url="https://example.supabase.co",
        service_key="fake-service-key",
        apply=True,
        requester=fake_img_req,
    )
    if not _check(
        "RED PROBE: backfill_post_images --apply fails when Edge Function returns HTTP 500",
        not ok_red_img and stats_red_img["failed"] == 1 and len(edge_calls) == 1,
    ):
        failures += 1

    # 4. validate_content: green against real blueprints + red probe on forbidden layout / missing title
    real_bp_errors = validate_content.validate_blueprints(validate_content.DEFAULT_BLUEPRINTS_DIR)
    if not _check(
        "validate_content passes against tracked w0m-web blueprints",
        len(real_bp_errors) == 0,
        f"errors={real_bp_errors[:2]}",
    ):
        failures += 1

    with tempfile.TemporaryDirectory() as tmp_bp:
        bp_dir = Path(tmp_bp)
        (bp_dir / "bad.md").write_text(
            "---\ntitle: Bad\nlayout: BaseLayout\n---\n# Bad\n", encoding="utf-8"
        )
        errs = validate_content.validate_blueprints(bp_dir)
        if not _check(
            "RED PROBE: validate_content flags forbidden 'layout' and missing 'blueprint_id'/'segment'",
            len(errs) == 3 and any("forbidden 'layout'" in e for e in errs),
        ):
            failures += 1

    # 5. validate_tracks: green against real w0m-api/design/tracks.yml + red probe on malformed track
    ok_tracks, track_ids = validate_tracks.validate_tracks_file()
    if not _check(
        "validate_tracks passes against tracked w0m-api/design/tracks.yml",
        ok_tracks and len(track_ids) >= 3,
        f"tracks={track_ids}",
    ):
        failures += 1

    with tempfile.TemporaryDirectory() as tmp_tr:
        bad_yml = Path(tmp_tr) / "tracks.yml"
        bad_yml.write_text(
            "tracks:\n  - id: broken\n    name: Broken\n    stages:\n      - name: Stage1\n",
            encoding="utf-8",
        )
        ok_bad_tr, bad_tr_errs = validate_tracks.validate_tracks_file(bad_yml)
        if not _check(
            "RED PROBE: validate_tracks fails when stage is missing 'offerings' list",
            not ok_bad_tr and any("missing offerings" in e for e in bad_tr_errs),
        ):
            failures += 1

    # 6. T83 AC3/AC5/AC6: ai_tools.py local image generation helper & 32 GB Apple Silicon budget guard
    budget = ai_tools.validate_image_memory_budget("512x512")
    if not _check(
        "ai_tools.validate_image_memory_budget validates 512x512 within 24 GB Apple Silicon budget",
        budget["width"] == 512
        and budget["height"] == 512
        and float(budget["estimated_memory_gb"]) <= 24.0,
    ):
        failures += 1

    skipped = ai_tools.generate_image("Architecture diagram", size="512x512")
    if not _check(
        "ai_tools.generate_image skips cleanly when USE_LOCAL_IMAGE_GEN is false (T184 P3 compliance)",
        skipped.get("status") == "skipped_optional_p3",
    ):
        failures += 1

    try:
        ai_tools.validate_image_memory_budget("2048x2048")
        red_img_dim = False
    except ValueError:
        red_img_dim = True
    if not _check(
        "RED PROBE: ai_tools.validate_image_memory_budget rejects dimensions exceeding 1536x1536 cap",
        red_img_dim,
    ):
        failures += 1

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
