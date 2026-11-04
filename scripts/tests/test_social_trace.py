#!/usr/bin/env python3
"""Unit tests for scripts/social_trace.py (T624)."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import social_trace  # noqa: E402


class SocialTraceCliTests(unittest.TestCase):
    def test_parse_linkedin_export_csv_with_disclaimer_line(self) -> None:
        raw = "\n".join(
            [
                "Note: LinkedIn Member Data Archive",
                "Date,SavedItem,Description",
                '2026-11-03 10:00:00,https://www.linkedin.com/posts/123,"MCP server security patterns"',
            ]
        )
        signals = social_trace.parse_linkedin_export_csv(raw)
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["platform"], "linkedin")
        self.assertEqual(signals[0]["signal_kind"], "bookmark")

        recs = social_trace.synthesize_recommendations(signals)
        self.assertEqual(recs[0]["suggested_kind"], "task")

    def test_cli_json_mode_with_linkedin_csv(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as tmp:
            tmp.write("Date,ShareLink,ShareCommentary\n")
            tmp.write('2026-11-03,https://www.linkedin.com/feed/update/urn:li:share:1,"New agent SDK release"\n')
            tmp_path = Path(tmp.name)
        try:
            from io import StringIO
            from contextlib import redirect_stdout

            buf = StringIO()
            with redirect_stdout(buf):
                rc = social_trace.main(["--linkedin-csv", str(tmp_path), "--json"])
            self.assertEqual(rc, 0)
            parsed = json.loads(buf.getvalue())
            self.assertTrue(parsed["ok"])
            self.assertEqual(parsed["count"], 1)
        finally:
            tmp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
