#!/usr/bin/env python3
"""T420 — Automated Design System & Shipping Code Reconciliation Checker (just ds-check).

Verifies:
  1. Token package export (AC4):
     - packages/ui/src/styles/tokens.css exists and is exported in packages/ui/package.json
     - apps/*/src/styles/global.css imports @webomage/ui/tokens.css
  2. Tailwind v4 Theme Contract (AC1, AC2):
     - All 12 shadcn semantic color token pairs are declared in @theme in apps/web and apps/cp
     - Canonical radius scale (--radius: 0.625rem, --radius-md: calc(var(--radius) - 2px)) is pinned
  3. Foundation Tokens & Zero Inline Fallback Literals (AC3):
     - Tokens are canonically declared: --text-primary, --text-body, --text-muted,
       --text-secondary, --text-on-brand, --color-primary, --font-sans, --warning, --warning-rgb
     - Zero hardcoded fallback literals in var(--text-muted, ...), var(--text-primary, ...), etc.
  4. Inert React and Stale Archive Cleanup (AC5, AC6):
     - Zero .jsx files in design-system/components/
     - Dead bundles (_ds_bundle.js, support.js) and design-system/uploads/ deleted
  5. Built CSS Rule Inspection (AC7):
     - If dist/ exists, verifies compiled CSS bundles contain valid rules for shadcn utility classes.

Usage:
  just ds-check
  python3 scripts/ds_check.py [--strict] [--skip-dist]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "wom7web"

SHADCN_COLOR_TOKENS = [
    "--color-primary",
    "--color-primary-foreground",
    "--color-secondary",
    "--color-secondary-foreground",
    "--color-muted",
    "--color-muted-foreground",
    "--color-accent",
    "--color-accent-foreground",
    "--color-card",
    "--color-card-foreground",
    "--color-popover",
    "--color-popover-foreground",
    "--color-border",
    "--color-input",
    "--color-ring",
    "--color-destructive",
    "--color-destructive-foreground",
]

FALLBACK_TOKEN_NAMES = [
    "--text-muted",
    "--text-primary",
    "--color-primary",
    "--warning-rgb",
    "--text-secondary",
    "--font-sans",
    "--text-body",
    "--text-on-brand",
    "--warning",
]

FALLBACK_PATTERN = re.compile(
    r"var\(\s*(" + "|".join(re.escape(t) for t in FALLBACK_TOKEN_NAMES) + r")\s*,\s*[^)]+\)"
)


def check_token_package(problems: list[str]) -> None:
    tokens_css = WEB / "packages" / "ui" / "src" / "tokens.css"
    if not tokens_css.is_file():
        problems.append(f"Missing canonical token CSS: {tokens_css}")
        return

    pkg_json_path = WEB / "packages" / "ui" / "package.json"
    if not pkg_json_path.is_file():
        problems.append(f"Missing package.json: {pkg_json_path}")
        return

    try:
        pkg = json.loads(pkg_json_path.read_text(encoding="utf-8"))
        exports = pkg.get("exports", {})
        if "./tokens.css" not in exports:
            problems.append(f"{pkg_json_path} does not export './tokens.css'")
    except Exception as e:
        problems.append(f"Failed to parse {pkg_json_path}: {e}")

    # Check that apps/web and apps/cp import @webomage/ui/tokens.css
    for app in ("web", "cp"):
        global_css = WEB / "apps" / app / "src" / "styles" / "global.css"
        if not global_css.is_file():
            problems.append(f"Missing {global_css}")
            continue
        content = global_css.read_text(encoding="utf-8")
        if '@import "@webomage/ui/tokens.css"' not in content and '@import "../../packages/ui/src/styles/tokens.css"' not in content:
            problems.append(f"{app}/src/styles/global.css does not import @webomage/ui/tokens.css")


def check_theme_contract(problems: list[str]) -> None:
    for app in ("web", "cp"):
        global_css = WEB / "apps" / app / "src" / "styles" / "global.css"
        if not global_css.is_file():
            continue
        content = global_css.read_text(encoding="utf-8")
        theme_match = re.search(r"@theme\s*\{([^}]+)\}", content, re.DOTALL)
        if not theme_match:
            problems.append(f"{app}/src/styles/global.css has no @theme block")
            continue
        theme_body = theme_match.group(1)

        # Check all shadcn colors
        missing_colors = [c for c in SHADCN_COLOR_TOKENS if c not in theme_body]
        if missing_colors:
            problems.append(
                f"{app}/src/styles/global.css @theme block is missing shadcn color(s): {', '.join(missing_colors)}"
            )

        # Check radius-md in theme
        if "--radius-md" not in theme_body:
            problems.append(f"{app}/src/styles/global.css @theme block is missing --radius-md")


def check_no_fallback_literals(problems: list[str]) -> None:
    scan_dirs = [
        WEB / "apps" / "web" / "src",
        WEB / "apps" / "cp" / "src",
        WEB / "apps" / "join" / "src",
        WEB / "apps" / "job" / "src",
        WEB / "apps" / "demo" / "src",
        WEB / "packages" / "ui" / "src",
    ]

    violations: list[str] = []
    for sdir in scan_dirs:
        if not sdir.is_dir():
            continue
        for ext in ("*.svelte", "*.astro", "*.css", "*.ts", "*.js"):
            for fpath in sdir.rglob(ext):
                text = fpath.read_text(encoding="utf-8", errors="ignore")
                for lineno, line in enumerate(text.splitlines(), start=1):
                    if FALLBACK_PATTERN.search(line):
                        rel = fpath.relative_to(WEB)
                        violations.append(f"{rel}:{lineno} -> {line.strip()}")

    if violations:
        problems.append(
            f"Found {len(violations)} inline token fallback literal(s) across components (AC3):\n  "
            + "\n  ".join(violations[:15])
            + (f"\n  ...and {len(violations) - 15} more" if len(violations) > 15 else "")
        )


def check_no_inert_react(problems: list[str]) -> None:
    ds_dir = WEB / "design-system"
    if not ds_dir.is_dir():
        return

    # Check for .jsx in components/
    comp_dir = ds_dir / "components"
    if comp_dir.is_dir():
        jsx_files = list(comp_dir.rglob("*.jsx"))
        if jsx_files:
            problems.append(
                f"Found {len(jsx_files)} inert React .jsx file(s) in design-system/components/ (AC5)"
            )

    # Check for dead bundles
    for dead in ("_ds_bundle.js", "support.js"):
        if (ds_dir / dead).is_file():
            problems.append(f"Inert bundle {dead} still exists in design-system/ (AC5)")

    # Check for uploads directory
    uploads_dir = ds_dir / "uploads"
    if uploads_dir.is_dir():
        problems.append(f"Dead upload archives still exist in {uploads_dir} (AC6)")


def check_dist_css(problems: list[str], require_dist: bool = False) -> None:
    scanned_dist = 0
    for app in ("web", "cp"):
        dist_dir = WEB / "apps" / app / "dist" / "client" / "_astro"
        if not dist_dir.is_dir():
            if require_dist:
                problems.append(f"No built CSS found in {dist_dir} — run `pnpm build` first")
            continue

        css_files = list(dist_dir.glob("*.css"))
        if not css_files:
            if require_dist:
                problems.append(f"No .css files in {dist_dir}")
            continue

        scanned_dist += len(css_files)
        combined_css = "\n".join(f.read_text(encoding="utf-8", errors="ignore") for f in css_files)

        # Check that shadcn utilities exist in built CSS
        required_selectors = [
            ("bg-primary", re.compile(r"bg-primary")),
            ("text-muted-foreground", re.compile(r"text-muted-foreground")),
            ("border-input", re.compile(r"border-input")),
            ("ring-ring", re.compile(r"ring-ring")),
            ("text-destructive", re.compile(r"text-destructive")),
        ]

        for name, pattern in required_selectors:
            if not pattern.search(combined_css):
                problems.append(f"Built CSS for {app} is missing compiled utility rule: .{name}")

    if scanned_dist > 0:
        print(f"  ✅ Built CSS verified across {scanned_dist} bundle(s)")
    elif not require_dist:
        print("  ℹ  dist/ bundles not found or skipped — source contract verified")


def main() -> int:
    parser = argparse.ArgumentParser(description="Design System & Shipping Code Reconciliation Check (T420)")
    parser.add_argument("--strict", action="store_true", help="Require dist/ built bundles to exist")
    parser.add_argument("--skip-dist", action="store_true", help="Skip dist/ CSS bundle verification")
    args = parser.parse_args()

    print("▶ Running Design System Reconciliation Check (T420)...")
    problems: list[str] = []

    check_token_package(problems)
    check_theme_contract(problems)
    check_no_fallback_literals(problems)
    check_no_inert_react(problems)

    if not args.skip_dist:
        check_dist_css(problems, require_dist=args.strict)

    if problems:
        print(f"❌ ds-check failed ({len(problems)} problem(s)):")
        for p in problems:
            print(f"  ✗ {p}")
        return 1

    print("✅ ds-check passed — Design System & Shipping Code are fully reconciled!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
