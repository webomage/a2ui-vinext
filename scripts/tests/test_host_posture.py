#!/usr/bin/env python3
"""
Unit tests and offline red probes for macOS Host Posture and Startup Baseline (T233).
Verifies that all host security checks fail when controls are mutated/disabled,
and that TCC fails closed to NOT MEASURED when unreadable.
"""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import host_posture




class TestHostPostureProbes(unittest.TestCase):

    # ── Host Controls (AC2) ──────────────────────────────────────────────────

    def test_firewall_enabled_passes(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="Firewall is enabled. (State = 1)\n"),
                MagicMock(returncode=0, stdout="Firewall stealth mode is on\n"),
            ]
            res = host_posture.check_firewall()
            self.assertEqual(res["status"], host_posture.PASS)
            self.assertTrue(res["enabled"])
            self.assertTrue(res["stealth"])

    def test_firewall_disabled_fails(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="Firewall is disabled. (State = 0)\n"),
                MagicMock(returncode=0, stdout="Firewall stealth mode is off\n"),
            ]
            res = host_posture.check_firewall()
            self.assertEqual(res["status"], host_posture.FAIL)
            self.assertFalse(res["enabled"])

    def test_firewall_stealth_disabled_warns_or_fails(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="Firewall is enabled. (State = 1)\n"),
                MagicMock(returncode=0, stdout="Firewall stealth mode is off\n"),
            ]
            res = host_posture.check_firewall()
            self.assertEqual(res["status"], host_posture.FAIL)
            self.assertFalse(res["stealth"])

    def test_filevault_on_passes(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="FileVault is On.\n")
            res = host_posture.check_filevault()
            self.assertEqual(res["status"], host_posture.PASS)
            self.assertTrue(res["enabled"])

    def test_filevault_off_fails(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="FileVault is Off.\n")
            res = host_posture.check_filevault()
            self.assertEqual(res["status"], host_posture.FAIL)
            self.assertFalse(res["enabled"])

    def test_sip_enabled_passes(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="System Integrity Protection status: enabled.\n")
            res = host_posture.check_sip()
            self.assertEqual(res["status"], host_posture.PASS)
            self.assertTrue(res["enabled"])

    def test_sip_disabled_fails(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="System Integrity Protection status: disabled.\n")
            res = host_posture.check_sip()
            self.assertEqual(res["status"], host_posture.FAIL)
            self.assertFalse(res["enabled"])

    def test_gatekeeper_enabled_passes(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="assessments enabled\n")
            res = host_posture.check_gatekeeper()
            self.assertEqual(res["status"], host_posture.PASS)
            self.assertTrue(res["enabled"])

    def test_gatekeeper_disabled_fails(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="assessments disabled\n")
            res = host_posture.check_gatekeeper()
            self.assertEqual(res["status"], host_posture.FAIL)
            self.assertFalse(res["enabled"])

    # ── Network Exposure & Postgres Binding (AC2) ────────────────────────────

    def test_postgres_loopback_passes(self):
        lsof_output = (
            "COMMAND     PID   USER   FD   TYPE             DEVICE SIZE/OFF NODE NAME\n"
            "postgres  12345  proto    7u  IPv4 0x12345678      0t0  TCP 127.0.0.1:5432 (LISTEN)\n"
            "postgres  12345  proto    8u  IPv6 0x12345679      0t0  TCP [::1]:5432 (LISTEN)\n"
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=lsof_output)
            res = host_posture.check_postgres_binding()
            self.assertEqual(res["status"], host_posture.PASS)
            self.assertTrue(res["is_loopback_only"])
            self.assertEqual(len(res["listeners"]), 2)

    def test_postgres_not_running_passes_clean(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            res = host_posture.check_postgres_binding()
            self.assertEqual(res["status"], host_posture.PASS)
            self.assertTrue(res["is_loopback_only"])
            self.assertEqual(len(res["listeners"]), 0)

    def test_postgres_wildcard_binding_fails(self):
        lsof_output = (
            "COMMAND     PID   USER   FD   TYPE             DEVICE SIZE/OFF NODE NAME\n"
            "postgres  12345  proto    7u  IPv4 0x12345678      0t0  TCP *:5432 (LISTEN)\n"
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=lsof_output)
            res = host_posture.check_postgres_binding()
            self.assertEqual(res["status"], host_posture.FAIL)
            self.assertFalse(res["is_loopback_only"])

    def test_postgres_external_ip_binding_fails(self):
        lsof_output = (
            "COMMAND     PID   USER   FD   TYPE             DEVICE SIZE/OFF NODE NAME\n"
            "postgres  12345  proto    7u  IPv4 0x12345678      0t0  TCP 192.168.1.50:5432 (LISTEN)\n"
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=lsof_output)
            res = host_posture.check_postgres_binding()
            self.assertEqual(res["status"], host_posture.FAIL)
            self.assertFalse(res["is_loopback_only"])

    # ── Startup Surface & Baseline Ratchet (AC3) ─────────────────────────────

    def test_startup_surface_clean_passes(self):
        baseline = {
            "login_items": {"WARP": "VPN client"},
            "root_daemons": {"com.foo.daemon": "approved daemon"},
            "user_launch_agents": {
                "com.w0m.backup": {"status": "loaded", "reason": "backup agent"},
                "com.dead.agent": {"status": "dead_but_present", "reason": "legacy"}
            },
            "limits": {"unregistered_daemons_max": 0, "unregistered_login_items_max": 0, "unregistered_agents_max": 0}
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json") as f:
            json.dump(baseline, f)
            f.flush()

            with patch("host_posture.scan_login_items", return_value=["WARP"]), \
                 patch("host_posture.scan_root_daemons", return_value=["com.foo.daemon"]), \
                 patch("host_posture.scan_user_launch_agents", return_value=["com.w0m.backup", "com.dead.agent"]), \
                 patch("host_posture.get_loaded_launch_labels", return_value={"com.w0m.backup"}):

                res = host_posture.check_startup_surface(baseline_path=Path(f.name))
                self.assertEqual(res["status"], host_posture.PASS)
                self.assertEqual(len(res["unregistered_daemons"]), 0)
                self.assertEqual(len(res["dead_but_present_agents"]), 1)

    def test_startup_unregistered_daemon_fails(self):
        baseline = {
            "login_items": {},
            "root_daemons": {"com.known.daemon": "approved"},
            "user_launch_agents": {},
            "limits": {"unregistered_daemons_max": 0, "unregistered_login_items_max": 0, "unregistered_agents_max": 0}
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json") as f:
            json.dump(baseline, f)
            f.flush()

            with patch("host_posture.scan_login_items", return_value=[]), \
                 patch("host_posture.scan_root_daemons", return_value=["com.known.daemon", "com.malicious.backdoor"]), \
                 patch("host_posture.scan_user_launch_agents", return_value=[]), \
                 patch("host_posture.get_loaded_launch_labels", return_value=set()):

                res = host_posture.check_startup_surface(baseline_path=Path(f.name))
                self.assertEqual(res["status"], host_posture.FAIL)
                self.assertIn("com.malicious.backdoor", res["unregistered_daemons"])

    def test_startup_missing_baseline_fails_closed(self):
        res = host_posture.check_startup_surface(baseline_path=Path("/tmp/nonexistent_baseline_123.json"))
        self.assertEqual(res["status"], host_posture.FAIL)
        self.assertIn("Missing baseline file", res["detail"])

    # ── TCC Grants & Fail-Closed Behavior (AC4) ──────────────────────────────

    def test_tcc_unreadable_reports_not_measured(self):
        with patch.object(Path, "exists", return_value=True), \
             patch("sqlite3.connect", side_effect=sqlite3.OperationalError("unable to open database file: authorization denied")):
            res = host_posture.check_tcc_grants()
            self.assertEqual(res["status"], host_posture.NOT_MEASURED)
            self.assertIn("FDA required", res["detail"])
            self.assertFalse(res.get("is_clean_claim", False))

    def test_tcc_readable_enumerates_grants(self):
        with tempfile.NamedTemporaryFile("w", suffix=".db") as f:
            conn = sqlite3.connect(f.name)
            conn.execute("CREATE TABLE access (service TEXT, client TEXT, allowed INTEGER);")
            conn.execute("INSERT INTO access VALUES ('kTCCServiceCamera', 'com.apple.FaceTime', 1);")
            conn.execute("INSERT INTO access VALUES ('kTCCServiceMicrophone', 'us.zoom.xos', 1);")
            conn.execute("INSERT INTO access VALUES ('kTCCServiceSystemPolicyAllFiles', 'com.google.Chrome', 1);")
            conn.commit()
            conn.close()

            res = host_posture.check_tcc_grants(db_path=Path(f.name))
            self.assertEqual(res["status"], host_posture.PASS)
            self.assertIn("com.apple.FaceTime", res["grants"]["kTCCServiceCamera"])
            self.assertIn("us.zoom.xos", res["grants"]["kTCCServiceMicrophone"])
            self.assertIn("com.google.Chrome", res["grants"]["kTCCServiceSystemPolicyAllFiles"])

    # ── Unmeasured Dimensions (AC6) ──────────────────────────────────────────

    def test_unmeasured_dimensions_present(self):
        unmeasured = host_posture.check_unmeasured_dimensions()
        self.assertIn("outbound_network_traffic", unmeasured)
        self.assertIn("browser_extensions", unmeasured)
        for key, entry in unmeasured.items():
            self.assertEqual(entry["status"], host_posture.NOT_MEASURED)
            self.assertTrue(len(entry["reason"]) > 10)


if __name__ == "__main__":
    unittest.main()
