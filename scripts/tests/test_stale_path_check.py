#!/usr/bin/env python3
"""Red and green unit tests for T509 Unit U0 (`scripts/stale_path_check.py`).

Covers all 5 carriers, false-positive exclusions, exemption discipline, and fail-closed exit-2:
  1. Justfile recipe bodies (missing script path + dangling `--justfile <path> <recipe>` target + `\\` continuations + echo/comment prose exclusions).
  2. JSON/JSONC policy and profile files (both keys like `file.py:line` and string values).
  3. Hook configs (`.pre-commit-config.yaml`, `.husky/*`, `scripts/hooks/*`).
  4. Test-runner config (`test-suites.json`).
  5. Host-level launchd plists (`com.w0m.*.plist`).
  6. Exit 2 on unmeasurable/corrupt inputs (never silently 0).
  7. Live repository verification (`main([]) == 0`).
"""

from __future__ import annotations

import io
import json
import plistlib
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import stale_path_check as spc


class TestStalePathCheck(unittest.TestCase):
    def test_live_repo_is_green(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = spc.main([])
        self.assertEqual(rc, 0, buf.getvalue())
        self.assertIn("0 stale paths", buf.getvalue())

    def test_red_missing_script_in_justfile_recipe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            jf = root / "justfile"
            jf.write_text(
                "check:\n"
                "    @python3 scripts/nonexistent_gate.py --strict\n",
                encoding="utf-8",
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = spc.main(["--root", str(root), "--justfile", str(jf)])
            self.assertEqual(rc, 1, buf.getvalue())
            self.assertIn("scripts/nonexistent_gate.py", buf.getvalue())

    def test_red_dangling_justfile_delegate_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sub = root / "w0m-web"
            sub.mkdir()
            (sub / "justfile").write_text("existing-recipe:\n    @echo ok\n", encoding="utf-8")
            jf = root / "justfile"
            jf.write_text(
                "forward-missing:\n"
                "    @just --justfile w0m-web/justfile missing-target\n",
                encoding="utf-8",
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = spc.main(["--root", str(root), "--justfile", str(jf), "--strict-forwarders"])
            self.assertEqual(rc, 1, buf.getvalue())
            self.assertIn("dangling `--justfile w0m-web/justfile missing-target`", buf.getvalue())

    def test_green_justfile_with_continuations_cd_and_echo_prose(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            (root / "scripts" / "real_tool.py").write_text("#!/usr/bin/env python3\n", encoding="utf-8")
            sub = root / "w0m-web" / "project" / "scripts"
            sub.mkdir(parents=True)
            (sub / "web_tool.py").write_text("#!/usr/bin/env python3\n", encoding="utf-8")
            (root / "w0m-web" / "justfile").write_text("sub-ok:\n    @echo ok\n", encoding="utf-8")

            jf = root / "justfile"
            jf.write_text(
                "all:\n"
                "    # comment mentioning python3 scripts/comment_only.py\n"
                "    @echo \"Run python3 scripts/prose_only.py; then check\"\n"
                "    @python3 scripts/real_tool.py\n"
                "    @cd w0m-web \\\n"
                "      && python3 project/scripts/web_tool.py\n"
                "    @just --justfile w0m-web/justfile sub-ok\n",
                encoding="utf-8",
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = spc.main(["--root", str(root), "--justfile", str(jf), "--strict-forwarders"])
            self.assertEqual(rc, 0, buf.getvalue())

    def test_red_missing_script_in_json_policy_key_and_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            (root / "scripts" / "present.py").write_text("", encoding="utf-8")
            pol = root / "policy.json"
            pol.write_text(
                json.dumps(
                    {
                        "_comment": "python3 scripts/ignored_in_comment.py",
                        "script": "scripts/present.py",
                        "broken_val": "scripts/missing_from_val.py",
                        "discovery_exempt": {
                            "project/scripts/missing_from_key.py:120": "exempt reason",
                        },
                    }
                ),
                encoding="utf-8",
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = spc.main(["--root", str(root), "--json-file", str(pol)])
            self.assertEqual(rc, 1, buf.getvalue())
            self.assertIn("scripts/missing_from_val.py", buf.getvalue())
            self.assertIn("project/scripts/missing_from_key.py", buf.getvalue())
            self.assertNotIn("ignored_in_comment.py", buf.getvalue())

    def test_red_missing_script_in_hook_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            (root / "scripts" / "good_hook.py").write_text("", encoding="utf-8")
            hook = root / ".pre-commit-config.yaml"
            hook.write_text(
                "# comment scripts/ignored_comment.py\n"
                "- id: good\n"
                "  entry: python3 scripts/good_hook.py\n"
                "- id: bad\n"
                "  entry: python3 scripts/missing_hook.py\n",
                encoding="utf-8",
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = spc.main(["--root", str(root), "--hook-file", str(hook)])
            self.assertEqual(rc, 1, buf.getvalue())
            self.assertIn("scripts/missing_hook.py", buf.getvalue())
            self.assertNotIn("good_hook.py", buf.getvalue())

    def test_red_missing_script_in_test_suites_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            suites = root / "test-suites.json"
            suites.write_text(
                json.dumps(
                    {
                        "suites": [
                            {
                                "name": "broken-suite",
                                "recipe": "broken-suite",
                                "command": "python3 scripts/missing_suite_runner.py",
                                "reason": "scripts/ignored_in_reason.py",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = spc.main(["--root", str(root), "--test-suites", str(suites)])
            self.assertEqual(rc, 1, buf.getvalue())
            self.assertIn("scripts/missing_suite_runner.py", buf.getvalue())
            self.assertNotIn("ignored_in_reason.py", buf.getvalue())

    def test_red_and_green_launchd_plist_carrier(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            (root / "scripts" / "agent_ok.py").write_text("", encoding="utf-8")
            ldir = root / "LaunchAgents"
            ldir.mkdir()

            bad_plist = ldir / "com.w0m.bad.plist"
            bad_plist.write_bytes(
                plistlib.dumps(
                    {
                        "Label": "com.w0m.bad",
                        "WorkingDirectory": str(root),
                        "ProgramArguments": ["/usr/bin/python3", "scripts/agent_missing.py"],
                    }
                )
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc_red = spc.main(["--root", str(root), "--launchd-dir", str(ldir)])
            self.assertEqual(rc_red, 1, buf.getvalue())
            self.assertIn("scripts/agent_missing.py", buf.getvalue())

            bad_plist.unlink()
            ok_plist = ldir / "com.w0m.ok.plist"
            ok_plist.write_bytes(
                plistlib.dumps(
                    {
                        "Label": "com.w0m.ok",
                        "WorkingDirectory": str(root),
                        "ProgramArguments": ["/usr/bin/python3", "scripts/agent_ok.py"],
                    }
                )
            )
            buf_ok = io.StringIO()
            with redirect_stdout(buf_ok):
                rc_green = spc.main(["--root", str(root), "--launchd-dir", str(ldir)])
            self.assertEqual(rc_green, 0, buf_ok.getvalue())

    def test_exemptions_require_reason_and_reject_stale_exemption(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            (root / "scripts" / "now_exists.py").write_text("", encoding="utf-8")

            remaining, _ = spc.check_exemptions(
                ["[json x] stale script path `scripts/unreasoned.py`"],
                exemptions={"scripts/unreasoned.py": "   "},
                root=root,
            )
            self.assertTrue(any("missing written `why` reason" in r for r in remaining))

            remaining_stale, _ = spc.check_exemptions(
                [],
                exemptions={"scripts/now_exists.py": "T509 temporary exemption"},
                root=root,
            )
            self.assertTrue(any("stale exemption" in r for r in remaining_stale))

    def test_exit_2_on_unmeasurable_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bad_jf = root / "justfile"
            bad_jf.write_text("not a valid justfile ::: {{\n", encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = spc.main(["--root", str(root), "--justfile", str(bad_jf)])
            self.assertEqual(rc, 2, buf.getvalue())

            empty_suites = root / "test-suites.json"
            empty_suites.write_text(json.dumps({"suites": []}), encoding="utf-8")
            buf2 = io.StringIO()
            with redirect_stdout(buf2):
                rc2 = spc.main(["--root", str(root), "--test-suites", str(empty_suites)])
            self.assertEqual(rc2, 2, buf2.getvalue())


if __name__ == "__main__":
    unittest.main()
