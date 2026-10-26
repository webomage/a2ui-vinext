#!/usr/bin/env python3
"""validate_content — Validate frontmatter schema of content blueprints and posts (T518 AC2).

Resolves paths dynamically relative to the estate root (`ESTATE_ROOT`) without hardcoded
`/Users/proto/...` paths. Uses `yaml.safe_load` to parse Markdown YAML frontmatter blocks.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any, cast

import yaml

ESTATE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BLUEPRINTS_DIR = ESTATE_ROOT / "w0m-web" / "apps" / "web" / "src" / "content" / "blueprints"
DEFAULT_POSTS_DIR = ESTATE_ROOT / "w0m-web" / "apps" / "web" / "src" / "content" / "posts"


def parse_frontmatter(md_path: Path) -> dict[str, Any]:
    text = md_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("Missing opening YAML frontmatter delimiter '---'")
    end_idx: int | None = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end_idx = idx
            break
    if end_idx is None:
        raise ValueError("Missing closing YAML frontmatter delimiter '---'")
    raw_yaml = "\n".join(lines[1:end_idx])
    parsed = yaml.safe_load(raw_yaml)
    if not isinstance(parsed, dict):
        raise ValueError("Frontmatter block did not parse as a YAML mapping")
    return cast(dict[str, Any], parsed)


def validate_posts(posts_dir: Path) -> list[str]:
    errors: list[str] = []
    if not posts_dir.is_dir():
        return errors
    for filepath in sorted(posts_dir.glob("*.md")):
        filename = filepath.name
        try:
            meta = parse_frontmatter(filepath)
            if "title" not in meta or not str(meta["title"]).strip():
                errors.append(f"{filename}: missing required 'title'")
            if "date" not in meta:
                errors.append(f"{filename}: missing required 'date'")
            if "layout" in meta:
                errors.append(f"{filename}: forbidden 'layout' field present")
            date_val = meta.get("date")
            if date_val is not None and not (
                isinstance(date_val, str) or hasattr(date_val, "strftime")
            ):
                errors.append(f"{filename}: 'date' has invalid type {type(date_val).__name__}")
        except Exception as exc:
            errors.append(f"{filename}: parse error ({exc})")
    return errors


def validate_blueprints(blueprints_dir: Path) -> list[str]:
    errors: list[str] = []
    if not blueprints_dir.is_dir():
        errors.append(f"Blueprints directory not found: {blueprints_dir}")
        return errors
    md_files = sorted(blueprints_dir.glob("*.md"))
    if not md_files:
        errors.append(f"No markdown files found in {blueprints_dir}")
        return errors

    for filepath in md_files:
        filename = filepath.name
        try:
            meta = parse_frontmatter(filepath)
            if "layout" in meta:
                errors.append(f"{filename}: forbidden 'layout' field present")
            for req in ("title", "blueprint_id", "segment"):
                if req not in meta or not str(meta[req]).strip():
                    errors.append(f"{filename}: missing required '{req}'")
        except Exception as exc:
            errors.append(f"{filename}: parse error ({exc})")
    return errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="validate_content.py",
        description="Validate frontmatter of markdown blueprints and posts (T518 AC2).",
    )
    parser.add_argument(
        "--blueprints-dir",
        type=Path,
        default=DEFAULT_BLUEPRINTS_DIR,
        help="Path to blueprints content directory",
    )
    parser.add_argument(
        "--posts-dir",
        type=Path,
        default=DEFAULT_POSTS_DIR,
        help="Path to posts content directory (validated when present on disk)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    bp_errors = validate_blueprints(Path(args.blueprints_dir))
    post_errors = validate_posts(Path(args.posts_dir))
    all_errors = bp_errors + post_errors

    if all_errors:
        for err in all_errors:
            print(f"[FAIL] {err}")
        print(f"[FAIL] Content validation failed with {len(all_errors)} error(s).")
        return 1

    bp_count = len(list(Path(args.blueprints_dir).glob("*.md")))
    post_count = (
        len(list(Path(args.posts_dir).glob("*.md"))) if Path(args.posts_dir).is_dir() else 0
    )
    print(
        f"[PASS] Validated {bp_count} blueprint(s) and {post_count} post(s) with 0 errors."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
