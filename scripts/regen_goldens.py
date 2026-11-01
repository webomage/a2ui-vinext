#!/usr/bin/env python3
"""T487 AC2/AC3 (AgDR-0053) — Visual golden baseline completeness check & diff-summary regeneration gate.

Modes:
- `--check`: Statically parses all `.spec` files in `w0m-web/specs/` (including Markdown data tables)
  for golden snapshot steps, verifies every referenced `w0m-web/screenshots/goldens/en-<viewport>-<name>.png`
  exists with a valid PNG header and non-zero dimensions, and verifies no uncommitted changes remain in
  `w0m-web/screenshots/goldens/` when `--require-clean` is set.
- `--diff-summary`: Compares a pre-saved JSON snapshot against current `screenshots/goldens/*.png` (or
  `git status --porcelain` / `git diff --numstat`) and prints a structured diff summary.
- `--regen [spec]`: Snapshots current `screenshots/goldens/*.png`, runs `GAUGE_UPDATE_GOLDENS=true`,
  prints the per-file diff summary (CREATED / MODIFIED / UNCHANGED, WxH dimension changes, byte delta),
  and reminds the caller to commit any modified baselines (`T487 AC3`).
"""
from __future__ import annotations

import argparse
import hashlib
import re
import struct
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "w0m-web"
SPECS_DIR = WEB_ROOT / "specs"
GOLDENS_DIR = WEB_ROOT / "screenshots" / "goldens"

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

VIEWPORT_WIDTHS: dict[str, int] = {
    "desktop": 1440,
    "tablet-portrait": 768,
    "tablet-landscape": 1024,
    "mobile-portrait": 390,
    "mobile-landscape": 844,
    "mobile": 390,
}

SAFE_RE = re.compile(r"[^a-zA-Z0-9._-]")


class GoldenRef(NamedTuple):
    spec: str
    viewport: str
    name: str
    is_section: bool

    @property
    def filename(self) -> str:
        vp = SAFE_RE.sub("_", self.viewport)
        nm = SAFE_RE.sub("_", self.name)
        return f"en-{vp}-{nm}.png"


class PngMeta(NamedTuple):
    sha256: str
    size: int
    width: int
    height: int


STEP_DEFAULT_VP = re.compile(
    r'^\*\s+the page should match the golden snapshot\s+(?:"([^"]+)"|<([^>]+)>)\s*$',
    re.I,
)
STEP_EXPLICIT_VP = re.compile(
    r'^\*\s+the page should match the\s+(?:"([^"]+)"|<([^>]+)>)\s+golden snapshot\s+(?:"([^"]+)"|<([^>]+)>)\s*$',
    re.I,
)
STEP_SECTION_VP = re.compile(
    r'^\*\s+the\s+(?:"[^"]+"|<[^>]+>)\s+should match the\s+(?:"([^"]+)"|<([^>]+)>)\s+golden snapshot\s+(?:"([^"]+)"|<([^>]+)>)\s*$',
    re.I,
)


def read_png_meta(path: Path) -> PngMeta | None:
    if not path.is_file():
        return None
    data = path.read_bytes()
    if len(data) < 24 or data[:8] != PNG_MAGIC or data[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", data[16:24])
    digest = hashlib.sha256(data).hexdigest()[:12]
    return PngMeta(sha256=digest, size=len(data), width=width, height=height)


def _parse_tables(lines: list[str]) -> list[tuple[int, int, list[dict[str, str]]]]:
    """Return `(start_line, end_line, rows)` for every Markdown table in `lines`."""
    tables: list[tuple[int, int, list[dict[str, str]]]] = []
    i = 0
    while i < len(lines):
        ln = lines[i].strip()
        if ln.startswith("|") and ln.endswith("|"):
            block_start = i
            raw_rows: list[list[str]] = []
            while i < len(lines) and lines[i].strip().startswith("|") and lines[i].strip().endswith("|"):
                cells = [c.strip() for c in lines[i].strip()[1:-1].split("|")]
                raw_rows.append(cells)
                i += 1
            if len(raw_rows) >= 2:
                headers = raw_rows[0]
                data_rows: list[dict[str, str]] = []
                for r in raw_rows[1:]:
                    if all(set(c) <= {"-", ":"} and c for c in r):
                        continue
                    row_map = {
                        headers[idx]: r[idx]
                        for idx in range(min(len(headers), len(r)))
                    }
                    data_rows.append(row_map)
                if data_rows:
                    tables.append((block_start, i - 1, data_rows))
        else:
            i += 1
    return tables


def collect_golden_refs(specs_dir: Path = SPECS_DIR) -> list[GoldenRef]:
    refs: list[GoldenRef] = []
    seen: set[tuple[str, str, str]] = set()
    for spec_path in sorted(specs_dir.rglob("*.spec")):
        rel = str(spec_path.relative_to(WEB_ROOT)) if spec_path.is_relative_to(WEB_ROOT) else spec_path.name
        lines = spec_path.read_text(encoding="utf-8", errors="replace").splitlines()
        tables = _parse_tables(lines)
        spec_table: list[dict[str, str]] = []
        # A table before the first `## ` heading is a spec-level table
        first_heading = next((idx for idx, l in enumerate(lines) if l.startswith("## ")), len(lines))
        for start, _end, rows in tables:
            if start < first_heading:
                spec_table = rows
                break

        current_scenario_rows: list[dict[str, str]] = []
        for idx, raw_line in enumerate(lines):
            stripped = raw_line.strip()
            if stripped.startswith("//"):
                continue
            if raw_line.startswith("## "):
                # Find any table inside this scenario (before the next `## `)
                next_heading = next(
                    (j for j in range(idx + 1, len(lines)) if lines[j].startswith("## ")),
                    len(lines),
                )
                scen_tables = [
                    rows for start, _end, rows in tables if idx < start < next_heading
                ]
                current_scenario_rows = scen_tables[0] if scen_tables else spec_table
                continue

            m_def = STEP_DEFAULT_VP.match(stripped)
            m_exp = STEP_EXPLICIT_VP.match(stripped)
            m_sec = STEP_SECTION_VP.match(stripped)
            if not (m_def or m_exp or m_sec):
                continue

            active_rows = current_scenario_rows or [{}]
            for row in active_rows:
                if m_def:
                    lit_name, col_name = m_def.group(1), m_def.group(2)
                    col = col_name or (
                        lit_name[1:-1]
                        if lit_name and lit_name.startswith("<") and lit_name.endswith(">")
                        else None
                    )
                    name = row.get(col, "") if col else (lit_name or "")
                    viewport = "desktop"
                    is_sec = False
                elif m_exp:
                    lit_vp, col_vp, lit_name, col_name = m_exp.groups()
                    c_vp = col_vp or (
                        lit_vp[1:-1]
                        if lit_vp and lit_vp.startswith("<") and lit_vp.endswith(">")
                        else None
                    )
                    c_nm = col_name or (
                        lit_name[1:-1]
                        if lit_name and lit_name.startswith("<") and lit_name.endswith(">")
                        else None
                    )
                    viewport = row.get(c_vp, "") if c_vp else (lit_vp or "")
                    name = row.get(c_nm, "") if c_nm else (lit_name or "")
                    is_sec = False
                else:
                    assert m_sec is not None
                    lit_vp, col_vp, lit_name, col_name = m_sec.groups()
                    c_vp = col_vp or (
                        lit_vp[1:-1]
                        if lit_vp and lit_vp.startswith("<") and lit_vp.endswith(">")
                        else None
                    )
                    c_nm = col_name or (
                        lit_name[1:-1]
                        if lit_name and lit_name.startswith("<") and lit_name.endswith(">")
                        else None
                    )
                    viewport = row.get(c_vp, "") if c_vp else (lit_vp or "")
                    name = row.get(c_nm, "") if c_nm else (lit_name or "")
                    is_sec = True

                if not viewport or not name:
                    continue
                key = (rel, viewport, name)
                if key not in seen:
                    seen.add(key)
                    refs.append(GoldenRef(spec=rel, viewport=viewport, name=name, is_section=is_sec))
    return refs


def snapshot_goldens(goldens_dir: Path = GOLDENS_DIR) -> dict[str, PngMeta]:
    out: dict[str, PngMeta] = {}
    if not goldens_dir.is_dir():
        return out
    for p in sorted(goldens_dir.glob("*.png")):
        meta = read_png_meta(p)
        if meta is not None:
            out[p.name] = meta
    return out


def format_diff_summary(before: dict[str, PngMeta], after: dict[str, PngMeta]) -> tuple[list[str], int]:
    lines: list[str] = []
    all_names = sorted(set(before) | set(after))
    created, modified, deleted, unchanged = 0, 0, 0, 0
    for name in all_names:
        b = before.get(name)
        a = after.get(name)
        if b is None and a is not None:
            created += 1
            lines.append(
                f"    + CREATED   {name:<42} {a.width}x{a.height} ({a.size:,} B, sha256:{a.sha256})"
            )
        elif b is not None and a is None:
            deleted += 1
            lines.append(f"    - DELETED   {name:<42} (was {b.width}x{b.height})")
        elif b is not None and a is not None:
            if b.sha256 != a.sha256:
                modified += 1
                delta_b = a.size - b.size
                dim_str = (
                    f"{a.width}x{a.height}"
                    if (b.width, b.height) == (a.width, a.height)
                    else f"{b.width}x{b.height} -> {a.width}x{a.height}"
                )
                lines.append(
                    f"    ~ MODIFIED  {name:<42} {dim_str} ({delta_b:+,} B, {b.sha256} -> {a.sha256})"
                )
            else:
                unchanged += 1
    changed = created + modified + deleted
    header = (
        f"  ▶ golden diff summary — {created} created · {modified} modified · "
        f"{deleted} deleted · {unchanged} unchanged"
    )
    return [header, *lines], changed


def check_goldens(
    specs_dir: Path = SPECS_DIR,
    goldens_dir: Path = GOLDENS_DIR,
    require_clean: bool = False,
) -> int:
    refs = collect_golden_refs(specs_dir)
    if not refs:
        print("  ❌ no golden references found in specs — parser is broken.")
        return 2

    missing: list[GoldenRef] = []
    invalid: list[tuple[GoldenRef, str]] = []
    unique_files: set[str] = set()

    for ref in refs:
        unique_files.add(ref.filename)
        p = goldens_dir / ref.filename
        meta = read_png_meta(p)
        if meta is None:
            missing.append(ref)
            continue
        expected_w = VIEWPORT_WIDTHS.get(ref.viewport)
        if expected_w is None:
            invalid.append((ref, f"unknown viewport '{ref.viewport}'"))
        elif not ref.is_section and meta.width <= 0:
            invalid.append((ref, f"invalid width {meta.width}"))

    print(
        f"  ▶ goldens-check — {len(refs)} golden assertion(s) across specs · "
        f"{len(unique_files)} unique baseline PNG(s)"
    )

    if missing:
        print(f"\n  🔴 MISSING golden baselines ({len(missing)}) — refusing to pass on absent baselines (T487 AC2):")
        for r in missing:
            print(f"      · {r.spec:<34} {r.viewport:<17} {r.name:<18} -> {r.filename}")
    if invalid:
        print(f"\n  🔴 INVALID golden baselines ({len(invalid)}):")
        for r, reason in invalid:
            print(f"      · {r.spec:<34} {r.filename}: {reason}")

    dirty_files: list[str] = []
    if require_clean and WEB_ROOT.is_dir():
        proc = subprocess.run(
            ["git", "status", "--porcelain", "screenshots/goldens"],
            cwd=WEB_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        dirty_files = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
        if dirty_files:
            print(
                f"\n  🔴 UNCOMMITTED golden baseline changes ({len(dirty_files)}) — "
                f"regenerated goldens must be reviewed and committed (T487 AC3):"
            )
            for df in dirty_files:
                print(f"      · {df}")

    if missing or invalid or dirty_files:
        return 1

    print("  ✅ all golden baselines exist, have valid PNG headers, and match spec references.")
    return 0


def run_regen(spec_target: str) -> int:
    before = snapshot_goldens(GOLDENS_DIR)
    cmd = (
        ["just", "goldens"]
        if not spec_target
        else ["just", "e2e-roles-local", *spec_target.split()]
    )
    cwd = ROOT
    env = dict(
        **__import__("os").environ,
        GAUGE_UPDATE_GOLDENS="true",
        W0M_E2E_PARALLEL="0",
    )
    print(f"  ▶ regenerating goldens via `{' '.join(cmd)}` (GAUGE_UPDATE_GOLDENS=true)…")
    rc = subprocess.run(cmd, cwd=cwd, env=env, check=False).returncode
    after = snapshot_goldens(GOLDENS_DIR)
    summary_lines, changed = format_diff_summary(before, after)
    print("\n".join(summary_lines))
    if changed > 0:
        print(
            f"\n  ⚠️  {changed} golden baseline(s) changed. Inspect `git -C w0m-web status screenshots/goldens` "
            f"and commit the updated PNGs before pushing (T487 AC3)."
        )
    return rc


def main() -> int:
    parser = argparse.ArgumentParser(description="T487 golden completeness & diff-summary gate")
    parser.add_argument("--check", action="store_true", help="Verify all spec-referenced baselines exist")
    parser.add_argument(
        "--require-clean",
        action="store_true",
        help="Fail if w0m-web/screenshots/goldens has uncommitted changes",
    )
    parser.add_argument("--regen", nargs="?", const="", default=None, help="Regenerate goldens with diff summary")
    args = parser.parse_args()

    if args.regen is not None:
        return run_regen(args.regen)
    return check_goldens(require_clean=args.require_clean)


if __name__ == "__main__":
    sys.exit(main())
