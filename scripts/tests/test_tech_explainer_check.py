#!/usr/bin/env python3
"""Unit and Red-Probe Tests for `scripts/tech_explainer_check.py` (T736)."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SCRIPT_DIR = Path(__file__).resolve().parents[1]
ESTATE_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import tech_explainer_check as check  # noqa: E402


MINIMAL_VALID_HTML = """<!doctype html>
<html lang="en" data-theme="dark">
<head>
<style>
@media (prefers-reduced-motion: reduce) { * { animation: none; } }
</style>
</head>
<body>
  <button data-audience="novice">Novice</button>
  <button data-audience="junior">Junior</button>
  <button data-audience="product">Product</button>
  <button data-audience="executive">Executive</button>
  <button id="theme-toggle">Theme</button>
  <div id="live-status" aria-live="polite"></div>
  <svg class="topo" role="group" aria-label="Architecture">
    <path class="edge" data-from="n1" data-to="n2" d="M 0 0 L 10 10"></path>
    <g class="node" data-node="n1" role="button" tabindex="0" aria-label="Node One"></g>
    <g class="node" data-node="n2" role="button" tabindex="0" aria-label="Node Two"></g>
  </svg>
  <script type="application/json" id="explainer-data">
    {
      "NODES": {"n1": {"title": "Node One"}, "n2": {"title": "Node Two"}},
      "FLOWS": [{"id": "f1", "steps": [{"nodes": ["n1", "n2"], "edges": [["n1", "n2"]]}]}]
    }
  </script>
  <script>
    const status = document.getElementById('live-status');
  </script>
</body>
</html>
"""


class TestTechExplainerCheck(unittest.TestCase):
    def test_valid_live_explainer_passes(self) -> None:
        errors = check.validate_explainer_html(ESTATE_ROOT)
        self.assertEqual(errors, [], f"Live explainer validation failed: {errors}")

    def _write_fixture(self, root: Path, html_text: str) -> None:
        target = root / check.PRIMARY_REL
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(html_text, encoding="utf-8")

    def test_red_probe_rejects_external_cdn_script(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bad = MINIMAL_VALID_HTML.replace("</head>", '<script src="https://cdn.example.com/lib.js"></script>\n</head>')
            self._write_fixture(root, bad)
            errors = check.validate_explainer_html(root)
            self.assertTrue(any("external tag src/href" in e for e in errors), errors)

    def test_red_probe_rejects_css_url_and_fetch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bad = MINIMAL_VALID_HTML.replace("</style>", "body { background: url('https://cdn.example.com/bg.png'); }\n</style>")
            bad = bad.replace("document.getElementById('live-status');", "fetch('https://api.example.com/data');")
            self._write_fixture(root, bad)
            errors = check.validate_explainer_html(root)
            self.assertTrue(any("external CSS url()" in e for e in errors), errors)
            self.assertTrue(any("runtime fetch/dynamic import" in e for e in errors), errors)

    def test_red_probe_rejects_svg_role_img_and_broken_edge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bad = MINIMAL_VALID_HTML.replace('role="group"', 'role="img"').replace('["n1", "n2"]', '["n1", "n999"]')
            self._write_fixture(root, bad)
            errors = check.validate_explainer_html(root)
            self.assertTrue(any('role="img"' in e for e in errors), errors)
            self.assertTrue(any("unknown SVG edge ['n1', 'n999']" in e for e in errors), errors)

    def test_red_probe_rejects_duplicate_mirror_and_ticket_leak(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bad = MINIMAL_VALID_HTML.replace("Node One", "Node T735 Decision AgDR-0032")
            self._write_fixture(root, bad)
            dup = root / check.DEPRECATED_REL
            dup.parent.mkdir(parents=True, exist_ok=True)
            dup.write_text("duplicate", encoding="utf-8")
            errors = check.validate_explainer_html(root)
            self.assertTrue(any("Deprecated duplicate explainer" in e for e in errors), errors)
            self.assertTrue(any("T667" in e for e in errors), errors)


if __name__ == "__main__":
    unittest.main()
