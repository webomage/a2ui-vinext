#!/usr/bin/env python3
"""T164 AC1–AC6 — red/green regression suite for host CLI toolchain governance and health reporting.

Proves both layers (per the T164 AC6 anti-vacuity lesson):
  1. Fact collection (`ver_tuple`, `installed_version`, `resolve_policy_path`, `_refresh_cadence_days`,
     and `tool_usage_probe.scan_usage` command-position vs variable-assignment discrimination).
  2. Gate evaluation & RED failure proofs (`min: "999.9.9"`, missing required tool, malformed or
     violated `out_of_scope` coverage, advisory default vs `--strict` exit codes, and
     `w0m-api/scripts/healthcheck.py --toolchain-only` rendering and failure propagation).
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
from typing import Any
import unittest
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "w0m-web" / "project" / "scripts"))

import tool_usage_probe  # noqa: E402
import tools_check  # noqa: E402


def _load_healthcheck() -> Any:
    hc_path = ROOT / "w0m-api" / "scripts" / "healthcheck.py"
    spec = importlib.util.spec_from_file_location("w0m_api_healthcheck", hc_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FactCollectionTests(unittest.TestCase):
    def test_ver_tuple_parses_real_cli_version_formats(self) -> None:
        self.assertEqual(tools_check.ver_tuple("jq-1.7.1"), (1, 7, 1))
        self.assertEqual(tools_check.ver_tuple("jq-1.6"), (1, 6, 0))
        self.assertEqual(
            tools_check.ver_tuple("uv 0.13.4 (Homebrew 2026-10-20 x86_64-unknown-linux-gnu)"),
            (0, 13, 4),
        )
        self.assertEqual(tools_check.ver_tuple("psql (PostgreSQL) 18.6 (Homebrew)"), (18, 6, 0))
        self.assertEqual(
            tools_check.ver_tuple("Docker version 29.9.0, build f415da838b"),
            (29, 9, 0),
        )
        self.assertEqual(tools_check.ver_tuple("no version here"), (0, 0, 0))

    def test_live_installed_version_collects_real_host_python3_version(self) -> None:
        ver = tools_check.installed_version("python3", "--version")
        self.assertIsNotNone(ver, "python3 must be discoverable on PATH")
        parsed = tools_check.ver_tuple(ver or "")
        self.assertEqual(parsed[0], sys.version_info.major)
        self.assertEqual(parsed[1], sys.version_info.minor)

    def test_uvx_source_uses_version_cmd_without_requiring_binary_on_path(self) -> None:
        spec = {
            "source": "uvx",
            "version_cmd": "python3 -c 'print(\"serena 1.7.0\")'",
        }
        ver = tools_check.installed_version("__not_on_path_serena__", "--version", spec)
        self.assertEqual(ver, "1.7.0")

    def test_resolve_policy_path_reads_sdlc_json_and_supports_custom_project(self) -> None:
        resolved = tools_check.resolve_policy_path(ROOT)
        self.assertEqual(resolved, ROOT / "project" / "policies" / "tools-policy.json")
        self.assertTrue(resolved.is_file())

        with tempfile.TemporaryDirectory() as d:
            proj = Path(d)
            (proj / ".w0m").mkdir()
            (proj / ".w0m" / "sdlc.json").write_text(
                json.dumps({"toolchain": {"policy": "custom/my-tools.json"}}),
                encoding="utf-8",
            )
            self.assertEqual(
                tools_check.resolve_policy_path(proj),
                proj / "custom" / "my-tools.json",
            )

    def test_multi_os_refresh_cadence_does_not_read_launchd_on_linux(self) -> None:
        with mock.patch.object(sys, "platform", "linux"), mock.patch.object(
            tools_check, "LAUNCH_AGENT", Path("/nonexistent/com.w0m.tools-weekly.plist")
        ):
            self.assertEqual(tools_check._refresh_cadence_days(), 7)


class GateRedGreenTests(unittest.TestCase):
    def _run_main(self, policy_data: dict[str, Any], *flags: str) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as d:
            pol_file = Path(d) / "tools-policy.json"
            pol_file.write_text(json.dumps(policy_data), encoding="utf-8")
            buf = io.StringIO()
            with (
                mock.patch.object(tools_check, "POLICY", pol_file),
                mock.patch.object(sys, "argv", ["tools_check.py", *flags]),
                contextlib.redirect_stdout(buf),
            ):
                rc = tools_check.main()
            return rc, buf.getvalue()

    def test_deliberately_bad_min_version_produces_red_under_strict_and_advisory_default(self) -> None:
        bad_policy = {
            "tools": {
                "python3": {
                    "min": "999.9.9",
                    "known_good": "999.9.9",
                    "required": True,
                    "source": "pyenv",
                    "auto": "none",
                    "note": "deliberately unreachable floor for T164 AC6 red probe",
                }
            },
            "out_of_scope": {"bat": "0 uses — interactive pager"},
        }
        rc_adv, out_adv = self._run_main(bad_policy)
        self.assertEqual(rc_adv, 0, "advisory mode exits 0 by design")
        self.assertIn("1 required tool problem(s)", out_adv)
        self.assertIn("below min 999.9.9", out_adv)

        rc_strict, out_strict = self._run_main(bad_policy, "--strict")
        self.assertEqual(rc_strict, 1, "--strict must exit 1 on a required tool below min")
        self.assertIn("strict: FAIL", out_strict)
        self.assertIn("1 required-problem(s)", out_strict)

    def test_missing_required_binary_produces_red_under_strict(self) -> None:
        missing_policy = {
            "tools": {
                "no-such-required-cli-t164": {
                    "min": "1.0.0",
                    "known_good": "1.0.0",
                    "required": True,
                    "source": "brew",
                    "auto": "none",
                    "note": "missing required binary probe",
                }
            }
        }
        rc_strict, out_strict = self._run_main(missing_policy, "--strict")
        self.assertEqual(rc_strict, 1)
        self.assertIn("MISSING (required)", out_strict)
        self.assertIn("1 required-problem(s)", out_strict)

    def test_optional_tool_below_min_warns_without_failing_strict(self) -> None:
        opt_policy = {
            "tools": {
                "python3": {
                    "min": "999.9.9",
                    "known_good": "999.9.9",
                    "required": False,
                    "source": "pyenv",
                    "auto": "none",
                }
            }
        }
        rc_strict, out_strict = self._run_main(opt_policy, "--strict")
        self.assertEqual(rc_strict, 0)
        self.assertIn("[WARN] below min (optional tools)", out_strict)
        self.assertIn("1 warn", out_strict)


class ProbeAndOutOfScopeCoverageTests(unittest.TestCase):
    def test_probe_distinguishes_real_commands_from_python_assignments_and_comments(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            jf = root / "justfile"
            jf.write_text(
                "# tree and bat in a comment must not count\n"
                "db-check:\n"
                "    @infisical run -- sh -c 'psql \"$DATABASE_URL\" -c \"SELECT 1\"'\n"
                "    @echo ok | jq .\n",
                encoding="utf-8",
            )
            py = root / "worker.py"
            py.write_text(
                "import os, subprocess\n"
                "fd = os.open('/tmp/x', os.O_RDONLY)\n"
                "rg = {'status': 'ok'}\n"
                "tree = 'scripts'\n"
                "subprocess.run(['docker', 'info'], check=True)\n",
                encoding="utf-8",
            )
            scanned, hits = tool_usage_probe.scan_usage(
                tools=["psql", "jq", "docker", "fd", "rg", "tree", "bat"],
                files=[jf, py],
                root=root,
            )
            self.assertEqual(scanned, 2)
            self.assertEqual(sum(n for n, _ in hits["psql"]), 1)
            self.assertEqual(sum(n for n, _ in hits["jq"]), 1)
            self.assertEqual(sum(n for n, _ in hits["docker"]), 1)
            for false_pos in ("fd", "rg", "tree", "bat"):
                self.assertEqual(
                    sum(n for n, _ in hits[false_pos]),
                    0,
                    f"{false_pos} variable/comment must not be counted as a CLI invocation",
                )

    def test_estate_tools_policy_covers_all_27_candidates_with_zero_problems(self) -> None:
        policy_path = tools_check.resolve_policy_path(ROOT)
        policy: dict[str, Any] = json.loads(policy_path.read_text(encoding="utf-8"))
        self.assertEqual(tools_check.validate_out_of_scope(policy), [])

        scanned, hits = tool_usage_probe.scan_usage()
        self.assertGreater(scanned, 500, "estate corpus must not be vacuous")
        problems = tool_usage_probe.verify_policy_coverage(policy, hits)
        self.assertEqual(problems, [])

    def test_verify_policy_coverage_fails_on_unaccounted_or_used_out_of_scope_cli(self) -> None:
        policy = {
            "tools": {"jq": {"min": "1.6", "known_good": "1.8.2", "required": True}},
            "out_of_scope": {
                "psql": "wrongly marked out of scope while actually used",
                "bat": "",
            },
        }
        hits = {
            "jq": [(1, "justfile")],
            "psql": [(5, "w0m-api/justfile")],
            "bat": [],
            "ncdu": [],
        }
        problems = tool_usage_probe.verify_policy_coverage(
            policy, hits, candidates=["jq", "psql", "bat", "ncdu"]
        )
        joined = "\n".join(problems)
        self.assertIn("psql: recorded in `out_of_scope` but has 5 real", joined)
        self.assertIn("bat: `out_of_scope` entry must have a non-empty written reason", joined)
        self.assertIn("ncdu: unaccounted candidate CLI", joined)


class HealthcheckIntegrationTests(unittest.TestCase):
    def test_healthcheck_toolchain_only_renders_table_and_propagates_required_failures(self) -> None:
        hc = _load_healthcheck()
        with tempfile.TemporaryDirectory() as d:
            pol_ok = Path(d) / "ok-policy.json"
            ver = tools_check.installed_version("python3", "--version") or "3.12.0"
            pol_ok.write_text(
                json.dumps(
                    {
                        "tools": {
                            "python3": {
                                "min": "3.0.0",
                                "known_good": ver,
                                "required": True,
                                "source": "pyenv",
                                "auto": "none",
                            }
                        },
                        "out_of_scope": {"bat": "0 uses — interactive pager"},
                    }
                ),
                encoding="utf-8",
            )
            buf_ok = io.StringIO()
            with contextlib.redirect_stdout(buf_ok):
                rc_ok = hc.main(["--toolchain-only", "--policy", str(pol_ok)])
            out_ok = buf_ok.getvalue()
            self.assertEqual(rc_ok, 0, out_ok)
            self.assertIn("Toolchain Health (T164", out_ok)
            self.assertIn("python3", out_ok)
            self.assertIn("1 out-of-scope documented", out_ok)

            pol_bad = Path(d) / "bad-policy.json"
            pol_bad.write_text(
                json.dumps(
                    {
                        "tools": {
                            "python3": {
                                "min": "999.9.9",
                                "known_good": "999.9.9",
                                "required": True,
                                "source": "pyenv",
                                "auto": "none",
                            }
                        },
                        "out_of_scope": {"bat": "0 uses — interactive pager"},
                    }
                ),
                encoding="utf-8",
            )
            buf_bad = io.StringIO()
            with contextlib.redirect_stdout(buf_bad):
                rc_bad = hc.main(["--toolchain-only", "--policy", str(pol_bad)])
            out_bad = buf_bad.getvalue()
            self.assertEqual(rc_bad, 1, "healthcheck --toolchain-only must exit 1 on a required tool failure")
            self.assertIn("FAIL (<min)", out_bad)

    def test_two_health_surfaces_document_division_of_labour_and_cross_reference(self) -> None:
        hc_api = (ROOT / "w0m-api" / "scripts" / "healthcheck.py").read_text(encoding="utf-8")
        hc_web = (ROOT / "scripts" / "health_check.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("just health-check", hc_api)
        self.assertIn("scripts/health_check.py", hc_api)
        self.assertIn("Toolchain Health (T164", hc_api)

        self.assertIn("just health", hc_web)
        self.assertIn("w0m-api/scripts/healthcheck.py", hc_web)
        self.assertIn("T164", hc_web)

    def test_t517_cf_workers_ai_probe_resolves_w0m_llm_personnel_and_rejects_retired_model(self) -> None:
        hc = _load_healthcheck()
        model_id = hc.resolve_cf_ai_model("w0m-llm-personnel")
        self.assertEqual(model_id, "@cf/meta/llama-4-scout-17b-16e-instruct")
        with tempfile.TemporaryDirectory() as d:
            bad_just = Path(d) / "bad-ai-models.json"
            bad_just.write_text(
                json.dumps(
                    {
                        "chat_models": {
                            "w0m-llm-personnel": {
                                "model_id": "@cf/meta/llama-2-7b-chat-int8",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                hc.resolve_cf_ai_model("w0m-llm-personnel", justifications_path=bad_just)


class _Result(unittest.TextTestResult):
    """House style (scripts/run_suites.py counts them): one ✅/❌ line per check on stdout."""

    def addSuccess(self, test: unittest.TestCase) -> None:  # noqa: N802
        super().addSuccess(test)
        print(f"  \u2705 {test.id().rsplit('.', 2)[-2]}.{test.id().rsplit('.', 1)[-1]}")

    def addFailure(self, test: unittest.TestCase, err: Any) -> None:  # noqa: N802
        super().addFailure(test, err)
        print(f"  \u274c {test.id().rsplit('.', 2)[-2]}.{test.id().rsplit('.', 1)[-1]}")

    def addError(self, test: unittest.TestCase, err: Any) -> None:  # noqa: N802
        super().addError(test, err)
        print(f"  \u274c {test.id().rsplit('.', 2)[-2]}.{test.id().rsplit('.', 1)[-1]}")


if __name__ == "__main__":
    unittest.main(testRunner=unittest.TextTestRunner(resultclass=_Result, verbosity=1))
