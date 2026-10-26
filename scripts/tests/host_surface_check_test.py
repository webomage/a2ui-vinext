#!/usr/bin/env python3
"""Regression test suite and RED probe proof for host_surface_check.py (T196).

Exercises:
  - Red proof against quarantined OpenClaw gateway plist
  - Synthetic dead executable detection
  - Synthetic plaintext credential detection (keys and high-entropy JWT/Telegram shapes)
  - Clean plist verification
  - Missing surfaces / graceful handling
"""

import os
import plistlib
import sys
import tempfile
import unittest
from pathlib import Path

# Add project/scripts to path
SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

import host_surface_check  # noqa: E402


class TestHostSurfaceCheck(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_quarantined_openclaw_plist_red_proof(self):
        """AC3: Proven RED on the quarantined OpenClaw gateway plist artefact."""
        quarantine_file = Path(os.path.expanduser("~/.w0m-quarantine/openclaw-gateway.plist.2026-08-10"))
        if not quarantine_file.exists():
            self.skipTest(f"Quarantined fixture {quarantine_file} not found on this machine")

        findings = host_surface_check.scan_host(target=quarantine_file, include_crontab=False)
        self.assertTrue(len(findings) >= 5, f"Expected at least 5 findings, got {len(findings)}")

        dead_progs = [f for f in findings if f["type"] == "DEAD_PROGRAM"]
        self.assertEqual(len(dead_progs), 1)
        self.assertIn("node/25.8.0/bin/node", dead_progs[0]["detail"])

        secret_keys = {f.get("key") for f in findings if f["type"] in ("SECRET_KEY_EXPOSURE", "SECRET_VALUE_EXPOSURE")}
        expected_keys = {
            "OPENCLAW_GATEWAY_TOKEN",
            "MISTRAL_API_KEY",
            "HATCHET_CLIENT_TOKEN",
            "TELEGRAM_BOT_TOKEN",
        }
        self.assertTrue(expected_keys.issubset(secret_keys), f"Missing expected keys: {expected_keys - secret_keys}")

    def test_clean_plist_passes(self):
        """A plist pointing to a real binary with benign env vars passes with 0 findings."""
        clean_file = self.dir_path / "com.clean.plist"
        payload = {
            "Label": "com.clean",
            "Program": "/bin/sh",
            "EnvironmentVariables": {
                "HOME": "/Users/proto",
                "PORT": "8080",
                "STAGE": "production",
            },
        }
        with open(clean_file, "wb") as f:
            plistlib.dump(payload, f)

        findings = host_surface_check.scan_host(target=clean_file, include_crontab=False)
        self.assertEqual(len(findings), 0, f"Expected 0 findings on clean plist, got: {findings}")

    def test_dead_executable_detection(self):
        """A plist pointing to a non-existent binary is flagged."""
        dead_file = self.dir_path / "com.dead.plist"
        payload = {
            "Label": "com.dead",
            "ProgramArguments": ["/usr/local/bin/nonexistent_dummy_binary_xyz_123"],
        }
        with open(dead_file, "wb") as f:
            plistlib.dump(payload, f)

        findings = host_surface_check.scan_host(target=dead_file, include_crontab=False)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["type"], "DEAD_PROGRAM")

    def test_secret_key_exposure_detection(self):
        """Environment variables with secret-like names are flagged."""
        secret_file = self.dir_path / "com.secrets.plist"
        payload = {
            "Label": "com.secrets",
            "Program": "/bin/sh",
            "EnvironmentVariables": {
                "SUPABASE_SERVICE_ROLE_KEY": "dummy-val",
                "DATABASE_PASSWORD": "dummy-val",
                "AUTH_TOKEN": "dummy-val",
            },
        }
        with open(secret_file, "wb") as f:
            plistlib.dump(payload, f)

        findings = host_surface_check.scan_host(target=secret_file, include_crontab=False)
        keys_flagged = {f.get("key") for f in findings}
        self.assertEqual(keys_flagged, {"SUPABASE_SERVICE_ROLE_KEY", "DATABASE_PASSWORD", "AUTH_TOKEN"})

    def test_high_entropy_token_value_detection(self):
        """Environment variables with JWT or token values under generic names are flagged."""
        jwt_file = self.dir_path / "com.jwt.plist"
        # Dynamically constructed mock JWT payload
        import base64
        hdr = base64.urlsafe_b64encode(b'{"alg":"none"}').decode().rstrip("=")
        body = base64.urlsafe_b64encode(b'{"sub":"test1234567890"}').decode().rstrip("=")
        mock_jwt = f"{hdr}.{body}.dummy_signature_1234567890"
        payload = {
            "Label": "com.jwt",
            "Program": "/bin/sh",
            "EnvironmentVariables": {
                "APP_CONFIG_DATA": mock_jwt,
            },
        }
        with open(jwt_file, "wb") as f:
            plistlib.dump(payload, f)

        findings = host_surface_check.scan_host(target=jwt_file, include_crontab=False)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["type"], "SECRET_VALUE_EXPOSURE")
        self.assertEqual(findings[0]["key"], "APP_CONFIG_DATA")

    def test_absent_paths_handled_gracefully(self):
        """Non-existent file or directory target returns empty list without crashing."""
        nonexistent = self.dir_path / "does_not_exist.plist"
        findings = host_surface_check.scan_host(target=nonexistent, include_crontab=False)
        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
