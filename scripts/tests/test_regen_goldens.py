#!/usr/bin/env python3
"""Unit tests for scripts/regen_goldens.py (T487 AC2/AC3 / AgDR-0053)."""
from __future__ import annotations

import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import regen_goldens as rg  # noqa: E402


def _make_png(width: int = 1440, height: int = 900, fill: bytes = b"\x00") -> bytes:
    """Create a valid minimal PNG with exact IHDR dimensions."""
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    ihdr_crc = struct.pack(">I", zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF)
    ihdr_chunk = struct.pack(">I", len(ihdr_data)) + b"IHDR" + ihdr_data + ihdr_crc
    raw = zlib.compress(fill * 32)
    idat_crc = struct.pack(">I", zlib.crc32(b"IDAT" + raw) & 0xFFFFFFFF)
    idat_chunk = struct.pack(">I", len(raw)) + b"IDAT" + raw + idat_crc
    iend_crc = struct.pack(">I", zlib.crc32(b"IEND") & 0xFFFFFFFF)
    iend_chunk = struct.pack(">I", 0) + b"IEND" + iend_crc
    return rg.PNG_MAGIC + ihdr_chunk + idat_chunk + iend_chunk


class TestRegenGoldens(unittest.TestCase):
    def test_collect_golden_refs_parses_tables_and_skips_retired_comments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            specs_dir = Path(tmp) / "specs"
            specs_dir.mkdir()
            (specs_dir / "sample.spec").write_text(
                "# Sample Goldens\n\n"
                "|path|name|\n"
                "|---|---|\n"
                "|/|job_home|\n"
                "|/jobs/|job_list|\n\n"
                "## Page matches visual golden snapshot\n"
                '* I open the subdomain URL "job" path "<path>"\n'
                '* the page should match the golden snapshot "<name>"\n\n'
                "## Section golden\n"
                "|selector|viewport|name|\n"
                "|---|---|---|\n"
                "|main > section|desktop|home_hero|\n"
                "|main > section|mobile-portrait|home_services|\n"
                "* the <selector> should match the <viewport> golden snapshot <name>\n\n"
                "// RETIRED: obsolete golden\n"
                '// * the page should match the "desktop" golden snapshot "dashboard"\n',
                encoding="utf-8",
            )
            refs = rg.collect_golden_refs(specs_dir)
            filenames = [r.filename for r in refs]
            self.assertEqual(
                filenames,
                [
                    "en-desktop-job_home.png",
                    "en-desktop-job_list.png",
                    "en-desktop-home_hero.png",
                    "en-mobile-portrait-home_services.png",
                ],
            )

    def test_check_goldens_fails_closed_on_missing_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            specs_dir = Path(tmp) / "specs"
            goldens_dir = Path(tmp) / "goldens"
            specs_dir.mkdir()
            goldens_dir.mkdir()
            (specs_dir / "visual.spec").write_text(
                "# Visual\n\n"
                "## Home\n"
                '* the page should match the "desktop" golden snapshot "home"\n'
                '* the page should match the "mobile" golden snapshot "home"\n',
                encoding="utf-8",
            )
            (goldens_dir / "en-desktop-home.png").write_bytes(_make_png(1440, 900))
            # Missing en-mobile-home.png -> must fail closed (rc == 1)
            self.assertEqual(rg.check_goldens(specs_dir, goldens_dir), 1)

            # Once en-mobile-home.png exists -> passes (rc == 0)
            (goldens_dir / "en-mobile-home.png").write_bytes(_make_png(390, 844))
            self.assertEqual(rg.check_goldens(specs_dir, goldens_dir), 0)

    def test_format_diff_summary_reports_created_modified_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d1 = Path(tmp) / "before"
            d2 = Path(tmp) / "after"
            d1.mkdir()
            d2.mkdir()
            (d1 / "en-desktop-home.png").write_bytes(_make_png(1440, 900, b"\x01"))
            (d1 / "en-desktop-old.png").write_bytes(_make_png(1440, 900, b"\x02"))

            (d2 / "en-desktop-home.png").write_bytes(_make_png(1440, 920, b"\x03"))
            (d2 / "en-desktop-new.png").write_bytes(_make_png(1440, 900, b"\x04"))

            before = rg.snapshot_goldens(d1)
            after = rg.snapshot_goldens(d2)
            lines, changed = rg.format_diff_summary(before, after)
            summary_text = "\n".join(lines)
            self.assertEqual(changed, 3)
            self.assertIn("1 created · 1 modified · 1 deleted · 0 unchanged", summary_text)
            self.assertIn("+ CREATED   en-desktop-new.png", summary_text)
            self.assertIn("~ MODIFIED  en-desktop-home.png", summary_text)
            self.assertIn("- DELETED   en-desktop-old.png", summary_text)


if __name__ == "__main__":
    unittest.main()
