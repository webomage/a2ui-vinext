#!/usr/bin/env python3
"""T778 AC3 — offline unit tests for cross-platform launchd + Linux systemd scheduling.

Verifies:
  1. `schedules.jsonc` parses cleanly and declares the 5 governed maintenance jobs.
  2. `systemd_calendar_for()` maps daily and weekly schedules accurately.
  3. `canonical_estate_root()` resolves ephemeral `~/.w0m/work/...` worktrees back to the
     persistent canonical estate checkout and preserves `!` path segments unescaped.
  4. `systemd_service_for()` and `systemd_timer_for()` render valid INI units with
     `Type=oneshot`, canonical `WorkingDirectory`, Linux log directory, and `Persistent=true`.
  5. `plist_for()` keeps macOS launchd XML plist generation intact.
  6. `cmd_install`, `cmd_status`, and `cmd_remove` drive `systemctl --user` cleanly under mock.
  7. `tools_check._refresh_cadence_days()` reads `SYSTEMD_TIMER` (`OnCalendar=`) on Linux.

Run: `just tools-schedule-test`
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import launchd_schedule as ls  # noqa: E402
import tools_check  # noqa: E402


SAMPLE_WEEKLY = {
    "label": "com.w0m.tools-weekly",
    "description": "Refresh outdated-tools cache and apply auto-eligible updates.",
    "cwd": "w0m-api",
    "command": "tools-weekly",
    "schedule": {"weekday": 1, "hour": 10, "minute": 0},
    "log": "~/Library/Logs/w0m-tools-weekly.log",
}

SAMPLE_DAILY = {
    "label": "com.w0m.audit-daily",
    "description": "Daily automated host security posture sweep.",
    "cwd": "w0m-web",
    "command": "audit",
    "schedule": {"hour": 6, "minute": 30},
    "log": "~/Library/Logs/w0m-audit-daily.log",
}


class ScheduleTests(unittest.TestCase):
    def test_load_agents_reads_real_schedules_jsonc(self) -> None:
        agents = ls.load_agents()
        labels = {a["label"] for a in agents}
        self.assertGreaterEqual(len(agents), 5)
        self.assertTrue(
            {
                "com.w0m.tools-weekly",
                "com.w0m.backup-daily",
                "com.w0m.backup-weekly",
                "com.w0m.schema-weekly",
                "com.w0m.audit-daily",
            }.issubset(labels)
        )

    def test_systemd_calendar_mapping(self) -> None:
        self.assertEqual(ls.systemd_calendar_for({"hour": 3, "minute": 15}), "*-*-* 03:15:00")
        self.assertEqual(
            ls.systemd_calendar_for({"weekday": 1, "hour": 10, "minute": 0}),
            "Mon *-*-* 10:00:00",
        )
        self.assertEqual(
            ls.systemd_calendar_for({"weekday": 0, "hour": 4, "minute": 0}),
            "Sun *-*-* 04:00:00",
        )
        self.assertEqual(
            ls.systemd_calendar_for({"weekday": 7, "hour": 4, "minute": 0}),
            "Sun *-*-* 04:00:00",
        )

    def test_canonical_estate_root_resolves_worktree_to_main_checkout(self) -> None:
        worktree_estate = Path("/home/tester/.w0m/work/t778-sample/w0m")
        canonical = Path("/home/tester/Projects/!self/w0m")
        fake_git = subprocess.CompletedProcess(
            args=["git"],
            returncode=0,
            stdout=f"{canonical}/.git\n",
            stderr="",
        )
        with (
            mock.patch.dict(os.environ, {}, clear=False),
            mock.patch.object(ls, "ESTATE", worktree_estate),
            mock.patch("subprocess.run", return_value=fake_git) as run_mock,
        ):
            os.environ.pop("W0M_CANONICAL_ROOT", None)
            resolved = ls.canonical_estate_root()
            self.assertEqual(resolved, canonical.resolve())
            self.assertIn("!self", str(resolved))
            run_mock.assert_called_once()

    def test_systemd_service_and_timer_rendering(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="w0m-sched-unit-"))
        canonical = Path("/home/tester/Projects/!self/w0m")
        try:
            with (
                mock.patch.dict(os.environ, {"W0M_CANONICAL_ROOT": str(canonical)}),
                mock.patch.object(ls, "LINUX_LOG_DIR", tmp / "logs"),
                mock.patch.object(ls, "just_bin", return_value="/home/tester/.local/bin/just"),
                mock.patch.object(Path, "home", return_value=Path("/home/tester")),
            ):
                svc = ls.systemd_service_for(SAMPLE_WEEKLY)
                tmr = ls.systemd_timer_for(SAMPLE_DAILY)

            self.assertIn("Type=oneshot", svc)
            self.assertIn(f"WorkingDirectory={canonical / 'w0m-api'}", svc)
            self.assertIn(f"StandardOutput=append:{tmp / 'logs' / 'w0m-tools-weekly.log'}", svc)
            self.assertIn("ExecStart=/home/tester/.local/bin/just tools-weekly", svc)
            self.assertIn("/home/linuxbrew/.linuxbrew/bin", svc)

            self.assertIn("OnCalendar=*-*-* 06:30:00", tmr)
            self.assertIn("Persistent=true", tmr)
            self.assertIn("Unit=com.w0m.audit-daily.service", tmr)
            self.assertIn("WantedBy=timers.target", tmr)
        finally:
            import shutil

            shutil.rmtree(tmp, ignore_errors=True)

    def test_plist_for_remains_valid_for_macos_launchd(self) -> None:
        plist = ls.plist_for(SAMPLE_WEEKLY)
        self.assertEqual(plist["Label"], "com.w0m.tools-weekly")
        self.assertEqual(plist["StartCalendarInterval"], {"Hour": 10, "Minute": 0, "Weekday": 1})

    def test_systemd_install_status_and_remove_mocked(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="w0m-sched-sysd-"))
        unit_dir = tmp / "systemd-user"
        log_dir = tmp / "logs"

        def fake_run(cmd, capture_output=True, text=True):  # noqa: ANN001, ARG001
            if cmd[:3] == ["systemctl", "--user", "is-active"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="active\n", stderr="")
            if cmd[:3] == ["systemctl", "--user", "is-enabled"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="enabled\n", stderr="")
            if cmd[:3] == ["systemctl", "--user", "show"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="Mon 2026-11-23 10:00:00 EST\n", stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        try:
            with (
                mock.patch.dict(
                    os.environ,
                    {
                        "W0M_SCHEDULER_BACKEND": "systemd",
                        "W0M_CANONICAL_ROOT": str(ROOT),
                    },
                ),
                mock.patch.object(ls, "SYSTEMD_USER_DIR", unit_dir),
                mock.patch.object(ls, "LINUX_LOG_DIR", log_dir),
                mock.patch.object(ls, "just_bin", return_value="/usr/local/bin/just"),
                mock.patch("subprocess.run", side_effect=fake_run),
            ):
                rc_install = ls.cmd_install([SAMPLE_WEEKLY, SAMPLE_DAILY])
                self.assertEqual(rc_install, 0)
                self.assertTrue((unit_dir / "com.w0m.tools-weekly.service").is_file())
                self.assertTrue((unit_dir / "com.w0m.tools-weekly.timer").is_file())
                self.assertTrue((unit_dir / "com.w0m.audit-daily.timer").is_file())

                rc_status = ls.cmd_status([SAMPLE_WEEKLY, SAMPLE_DAILY])
                self.assertEqual(rc_status, 0)

                rc_remove = ls.cmd_remove([SAMPLE_WEEKLY, SAMPLE_DAILY])
                self.assertEqual(rc_remove, 0)
                self.assertFalse((unit_dir / "com.w0m.tools-weekly.timer").exists())
                self.assertFalse((unit_dir / "com.w0m.tools-weekly.service").exists())
        finally:
            import shutil

            shutil.rmtree(tmp, ignore_errors=True)

    def test_tools_check_reads_systemd_timer_cadence_on_linux(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="w0m-cadence-"))
        timer_file = tmp / "com.w0m.tools-weekly.timer"
        try:
            timer_file.write_text("[Timer]\nOnCalendar=*-*-* 10:00:00\n", encoding="utf-8")
            with mock.patch.object(sys, "platform", "linux"), mock.patch.object(
                tools_check, "SYSTEMD_TIMER", timer_file
            ):
                self.assertEqual(tools_check._refresh_cadence_days(), 1)

            timer_file.write_text("[Timer]\nOnCalendar=Mon *-*-* 10:00:00\n", encoding="utf-8")
            with mock.patch.object(sys, "platform", "linux"), mock.patch.object(
                tools_check, "SYSTEMD_TIMER", timer_file
            ):
                self.assertEqual(tools_check._refresh_cadence_days(), 7)
        finally:
            import shutil

            shutil.rmtree(tmp, ignore_errors=True)


class _Result(unittest.TextTestResult):
    """House style (scripts/run_suites.py counts them): one ✅/❌ line per check on stdout."""

    def addSuccess(self, test):  # noqa: N802
        super().addSuccess(test)
        print(f"  \u2705 {test.id().rsplit('.', 2)[-2]}.{test.id().rsplit('.', 1)[-1]}")

    def addFailure(self, test, err):  # noqa: N802
        super().addFailure(test, err)
        print(f"  \u274c {test.id().rsplit('.', 2)[-2]}.{test.id().rsplit('.', 1)[-1]}")

    def addError(self, test, err):  # noqa: N802
        super().addError(test, err)
        print(f"  \u274c {test.id().rsplit('.', 2)[-2]}.{test.id().rsplit('.', 1)[-1]}")


if __name__ == "__main__":
    unittest.main(testRunner=unittest.TextTestRunner(resultclass=_Result, verbosity=1))
