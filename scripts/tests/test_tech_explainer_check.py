#!/usr/bin/env python3
"""Unit and Red-Probe Tests for `scripts/tech_explainer_check.py` (T736)."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT_DIR = Path(__file__).resolve().parents[1]
ESTATE_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import tech_explainer_check as check

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

    def test_open_in_orca_browser_creates_and_focuses_new_tab(self) -> None:
        target = ESTATE_ROOT / check.PRIMARY_REL
        calls: list[list[str]] = []

        def fake_runner(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append(cmd)
            if cmd[1:3] == ["tab", "list"]:
                return subprocess.CompletedProcess(cmd, 0, '{"ok": true, "result": {"tabs": []}}', "")
            if cmd[1:3] == ["tab", "create"]:
                return subprocess.CompletedProcess(
                    cmd,
                    0,
                    '{"ok": true, "result": {"browserPageId": "page-99"}}',
                    "",
                )
            if cmd[1:3] == ["tab", "switch"]:
                return subprocess.CompletedProcess(cmd, 0, '{"ok": true}', "")
            raise AssertionError(f"Unexpected cmd: {cmd}")

        ok, detail = check.open_in_orca_browser(target, orca_bin="/fake/orca", runner=fake_runner)
        self.assertTrue(ok)
        self.assertEqual(detail, "orca:page-99:created")
        self.assertEqual(
            calls,
            [
                ["/fake/orca", "tab", "list", "--json"],
                ["/fake/orca", "tab", "create", "--url", target.resolve().as_uri(), "--json"],
                ["/fake/orca", "tab", "switch", "--page", "page-99", "--focus", "--json"],
            ],
        )

    def test_open_in_orca_browser_reuses_and_reloads_existing_tab(self) -> None:
        target = ESTATE_ROOT / check.PRIMARY_REL
        target_uri = target.resolve().as_uri()
        calls: list[list[str]] = []

        def fake_runner(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append(cmd)
            if cmd[1:3] == ["tab", "list"]:
                payload = f'{{"ok": true, "result": {{"tabs": [{{"browserPageId": "page-7", "url": "{target_uri}#sec", "active": false}}]}}}}'
                return subprocess.CompletedProcess(cmd, 0, payload, "")
            if cmd[1:3] == ["tab", "switch"]:
                return subprocess.CompletedProcess(cmd, 0, '{"ok": true}', "")
            if cmd[1] == "reload":
                return subprocess.CompletedProcess(cmd, 0, '{"ok": true}', "")
            raise AssertionError(f"Unexpected cmd: {cmd}")

        ok, detail = check.open_in_orca_browser(target, orca_bin="/fake/orca", runner=fake_runner)
        self.assertTrue(ok)
        self.assertEqual(detail, "orca:page-7:reused")
        self.assertEqual(
            calls,
            [
                ["/fake/orca", "tab", "list", "--json"],
                ["/fake/orca", "tab", "switch", "--page", "page-7", "--focus", "--json"],
                ["/fake/orca", "reload", "--page", "page-7", "--json"],
            ],
        )

    def test_open_in_orca_browser_split_pane(self) -> None:
        target = ESTATE_ROOT / check.PRIMARY_REL
        calls: list[list[str]] = []

        def fake_runner(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append(cmd)
            return subprocess.CompletedProcess(
                cmd,
                0,
                '{"ok": true, "data": {"browserPageId": "page-split"}}',
                "",
            )

        ok, detail = check.open_in_orca_browser(
            target, split="right", orca_bin="/fake/orca", runner=fake_runner
        )
        self.assertTrue(ok)
        self.assertEqual(detail, "orca:page-split:split-right")
        self.assertEqual(
            calls,
            [
                ["/fake/orca", "tab", "create", "--url", target.resolve().as_uri(), "--split", "right", "--json"],
            ],
        )

    def test_main_fails_closed_inside_orca_session_without_system_fallback(self) -> None:
        with (
            mock.patch.dict("os.environ", {"ORCA_CLI_COMMAND": "/fake/orca"}, clear=False),
            mock.patch.object(check, "open_in_orca_browser", return_value=(False, "daemon down")),
            mock.patch.object(check, "_open_in_system_browser") as sys_open,
        ):
            rc = check.main(["--root", str(ESTATE_ROOT), "--mode", "open"])
            self.assertEqual(rc, 1)
            sys_open.assert_not_called()

            rc_orca = check.main(["--root", str(ESTATE_ROOT), "--mode", "orca"])
            self.assertEqual(rc_orca, 1)
            sys_open.assert_not_called()

    def test_main_falls_back_to_system_only_outside_orca(self) -> None:
        with (
            mock.patch.dict("os.environ", {"ORCA_CLI_COMMAND": "", "ORCA_TAB_ID": ""}, clear=False),
            mock.patch.object(check, "open_in_orca_browser", return_value=(False, "orca not running")),
            mock.patch.object(check, "_open_in_system_browser") as sys_open,
        ):
            rc = check.main(["--root", str(ESTATE_ROOT), "--mode", "open"])
            self.assertEqual(rc, 0)
            sys_open.assert_called_once()


if __name__ == "__main__":
    unittest.main()
