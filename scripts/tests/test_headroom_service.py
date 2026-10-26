#!/usr/bin/env python3
"""Automated regression test suite for Headroom Process & Service Manager (T456).

Verifies:
1. Port listener parsing and multi-port tracking (8787 primary, 8788 legacy)
2. Process classification across Homebrew, LaunchAgent, and CLI runners
3. Homebrew service detection and legacy LaunchAgent audit
4. HTTP health parsing and error resilience
5. Command exit codes and status reporting
"""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

HERE = Path(__file__).resolve().parent
SCRIPTS_DIR = HERE.parent
SERVICE_SCRIPT = SCRIPTS_DIR / "headroom_service.py"

spec = importlib.util.spec_from_file_location("headroom_service", SERVICE_SCRIPT)
headroom_service = importlib.util.module_from_spec(spec)
sys.modules["headroom_service"] = headroom_service
spec.loader.exec_module(headroom_service)


class TestHeadroomService(unittest.TestCase):
    @patch("subprocess.run")
    def test_get_port_listeners(self, mock_run):
        # Test empty listener output
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        self.assertEqual(headroom_service.get_port_listeners(8787), [])

        # Test active listener output
        mock_run.return_value = MagicMock(
            stdout="COMMAND   PID USER   FD   TYPE             DEVICE SIZE/OFF NODE NAME\npython3 88298 proto   15u  IPv4 0x1234567890abcdef      0t0  TCP localhost:8787 (LISTEN)\n",
            returncode=0,
        )
        listeners = headroom_service.get_port_listeners(8787)
        self.assertEqual(len(listeners), 1)
        self.assertEqual(listeners[0]["command"], "python3")
        self.assertEqual(listeners[0]["pid"], "88298")

    @patch("subprocess.run")
    def test_get_headroom_processes(self, mock_run):
        ps_output = (
            "  PID  PPID COMMAND\n"
            "    1     0 launchd\n"
            "88298     1 /opt/homebrew/Cellar/python@3.12/3.12.14/Frameworks/Python.framework/Versions/3.12/Resources/Python.app/Contents/MacOS/Python -m headroom.cli proxy --host 127.0.0.1 --port 8787\n"
            "25145     1 /usr/local/bin/headroom proxy --port 8788 --anthropic-api-url http://127.0.0.1:8888\n"
            "99999 12345 /Users/proto/.pyenv/versions/3.12.9/bin/python3 -m headroom.cli proxy --port 8787\n"
            "77777     1 python3 /Users/proto/scripts/headroom_service.py status\n"
        )
        mock_run.return_value = MagicMock(stdout=ps_output, returncode=0)
        procs = headroom_service.get_headroom_processes()

        # Should find the 3 real headroom processes, filtering out headroom_service.py
        self.assertEqual(len(procs), 3)
        modes = [p["mode"] for p in procs]
        self.assertIn("Homebrew Daemon", modes)
        self.assertIn("LaunchAgent Daemon", modes)
        self.assertIn("Standalone CLI", modes)

    @patch("subprocess.run")
    def test_is_brew_service_loaded(self, mock_run):
        mock_run.return_value = MagicMock(stdout="88298\t0\tsh.brew.headroom\n", returncode=0)
        self.assertTrue(headroom_service.is_brew_service_loaded())

        mock_run.return_value = MagicMock(stdout="88298\t0\thomebrew.mxcl.headroom\n", returncode=0)
        self.assertTrue(headroom_service.is_brew_service_loaded())

        mock_run.return_value = MagicMock(stdout="12345\t0\tcom.apple.other\n", returncode=0)
        self.assertFalse(headroom_service.is_brew_service_loaded())

    @patch("subprocess.run")
    def test_get_loaded_legacy_services(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout="31909\t0\tcom.headroom.default\n25145\t-9\tsh.brew.headroom-local\n",
            returncode=0,
        )
        legacy = headroom_service.get_loaded_legacy_services()
        self.assertIn("com.headroom.default", legacy)
        self.assertIn("sh.brew.headroom-local", legacy)

        mock_run.return_value = MagicMock(stdout="88298\t0\tsh.brew.headroom\n", returncode=0)
        legacy = headroom_service.get_loaded_legacy_services()
        self.assertEqual(legacy, [])

    @patch("http.client.HTTPConnection")
    def test_probe_http_health_healthy(self, mock_conn_cls):
        mock_conn = MagicMock()
        mock_conn_cls.return_value = mock_conn

        mock_resp = MagicMock()
        mock_resp.status = 200
        health_payload = {
            "status": "healthy",
            "ready": True,
            "version": "0.39.0",
            "uptime_seconds": 123.4,
            "checks": {"upstream": {"url": "https://api.anthropic.com"}},
            "config": {"backend": "anthropic"},
        }
        mock_resp.read.return_value = json.dumps(health_payload).encode("utf-8")
        mock_conn.getresponse.return_value = mock_resp

        health = headroom_service.probe_http_health(8787)
        self.assertIsNotNone(health)
        self.assertEqual(health["status"], "healthy")
        self.assertTrue(health["ready"])
        self.assertEqual(health["version"], "0.39.0")
        self.assertEqual(health["upstream_url"], "https://api.anthropic.com")

    @patch("http.client.HTTPConnection")
    def test_probe_http_health_offline(self, mock_conn_cls):
        mock_conn_cls.side_effect = ConnectionRefusedError("Offline")
        health = headroom_service.probe_http_health(8787)
        self.assertIsNone(health)

    @patch("headroom_service.get_port_listeners")
    @patch("headroom_service.get_headroom_processes")
    @patch("headroom_service.is_brew_service_loaded")
    @patch("headroom_service.get_loaded_legacy_services")
    @patch("headroom_service.probe_http_health")
    def test_cmd_status_healthy(
        self, mock_probe, mock_legacy, mock_brew, mock_procs, mock_listeners
    ):
        mock_listeners.side_effect = lambda port: [{"command": "python", "pid": "123"}] if port == 8787 else []
        mock_procs.return_value = [{"pid": "123", "ppid": "1", "command": "headroom", "mode": "Homebrew Daemon"}]
        mock_brew.return_value = True
        mock_legacy.return_value = []
        mock_probe.return_value = {
            "status": "healthy",
            "ready": True,
            "version": "0.39.0",
            "upstream_url": "https://api.anthropic.com",
            "uptime_seconds": 45.0,
        }

        ret = headroom_service.cmd_status()
        self.assertEqual(ret, 0)


if __name__ == "__main__":
    unittest.main()
