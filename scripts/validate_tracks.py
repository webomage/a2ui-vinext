#!/usr/bin/env python3
"""validate_tracks — Validate `w0m-api/design/tracks.yml` schema and stage offerings (T518 AC3)."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any, cast

import yaml

ESTATE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TRACKS_FILE = ESTATE_ROOT / "w0m-api" / "design" / "tracks.yml"


def validate_track(track: dict[str, Any]) -> None:
    required_keys = ["id", "name", "stages"]
    for k in required_keys:
        if k not in track or track[k] is None or str(track[k]).strip() == "":
            raise ValueError(f"Track missing required key: {k}")

    stages = track["stages"]
    if not isinstance(stages, list) or not stages:
        raise ValueError(f"Track '{track['id']}' stages must be a non-empty list")

    for stage in stages:
        if not isinstance(stage, dict):
            raise ValueError(f"Track '{track['id']}' has a non-dict stage entry")
        if "name" not in stage or not str(stage["name"]).strip():
            raise ValueError(f"Track '{track['id']}' has a stage without a name")
        if "offerings" not in stage:
            raise ValueError(f"Stage '{stage['name']}' in track '{track['id']}' missing offerings")
        if not isinstance(stage["offerings"], list):
            raise ValueError(
                f"Offerings for stage '{stage['name']}' in track '{track['id']}' must be a list"
            )


def validate_tracks_file(tracks_file: Path = DEFAULT_TRACKS_FILE) -> tuple[bool, list[str]]:
    if not tracks_file.is_file():
        return False, [f"Tracks file not found: {tracks_file}"]

    try:
        raw = yaml.safe_load(tracks_file.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, [f"Error parsing YAML in {tracks_file}: {exc}"]

    if not isinstance(raw, dict) or "tracks" not in raw:
        return False, ["Root 'tracks' key missing"]

    tracks = raw["tracks"]
    if not isinstance(tracks, list) or not tracks:
        return False, ["'tracks' must be a non-empty list"]

    validated_ids: list[str] = []
    try:
        for item in tracks:
            if not isinstance(item, dict):
                return False, ["Track item must be a mapping"]
            track_dict = cast(dict[str, Any], item)
            validate_track(track_dict)
            validated_ids.append(str(track_dict["id"]))
    except ValueError as exc:
        return False, [str(exc)]

    return True, validated_ids


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="validate_tracks.py",
        description="Validate `w0m-api/design/tracks.yml` schema and stage offerings (T518 AC3).",
    )
    parser.add_argument(
        "--file",
        type=Path,
        default=DEFAULT_TRACKS_FILE,
        help="Path to tracks.yml (default: w0m-api/design/tracks.yml)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    ok, items = validate_tracks_file(Path(args.file))
    if not ok:
        for err in items:
            print(f"[FAIL] {err}")
        return 1
    for tid in items:
        print(f"  [PASS] Track '{tid}' OK")
    print(f"[PASS] All {len(items)} track(s) validated successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
