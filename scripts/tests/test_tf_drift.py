"""Unit tests for scripts/tf_drift_check.py (T787 AC2)."""

import os
import sys
from pathlib import Path

# Ensure scripts dir is on sys.path
SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import unittest
from unittest.mock import MagicMock, patch

import tf_drift_check
from tf_drift_check import (
    DEFAULT_ADMIN_ID,
    format_telegram_alert,
    main,
    parse_plan_output,
    send_telegram_alert,
)

MOCK_DRIFT_STDOUT = """
data.cloudflare_zone.w0m: Reading...
data.cloudflare_zone.this: Reading...
data.cloudflare_zone.w0m: Read complete after 1s [id=6ef3055469ff713dc17c5ce6b461b69e]
data.cloudflare_zone.this: Read complete after 1s [id=b6bbac925ac5f37e7da05a703c17d669]

Terraform used the selected providers to generate the following execution plan.
Resource actions are indicated with the following symbols:
  + create
  ~ update in-place

Terraform will perform the following actions:

  # cloudflare_email_routing_settings.w0m_xyz will be created
  + resource "cloudflare_email_routing_settings" "w0m_xyz" {
      + enabled = true
      + zone_id = "6ef3055469ff713dc17c5ce6b461b69e"
    }

  # cloudflare_record.w0m_xyz_mx_route1 will be updated in-place
  ~ resource "cloudflare_record" "w0m_xyz_mx_route1" {
        name = "w0m.xyz"
        priority = 70
    }

Plan: 1 to add, 1 to change, 0 to destroy.
"""

MOCK_CLEAN_STDOUT = """
data.cloudflare_zone.w0m: Read complete after 1s [id=6ef3055469ff713dc17c5ce6b461b69e]
data.cloudflare_zone.this: Read complete after 1s [id=b6bbac925ac5f37e7da05a703c17d669]

No changes. Your infrastructure matches the configuration.

Terraform has compared your real infrastructure against your configuration
and found no differences, so no changes are needed.
"""


class TestTfDriftCheck(unittest.TestCase):
    def test_parse_plan_output_drift(self):
        info = parse_plan_output(MOCK_DRIFT_STDOUT)
        self.assertTrue(info["has_drift"])
        self.assertIn("1 to add, 1 to change, 0 to destroy", info["summary"])
        self.assertEqual(len(info["changes"]), 2)
        types = [c["type"] for c in info["changes"]]
        self.assertIn("cloudflare_email_routing_settings", types)
        self.assertIn("cloudflare_record", types)

    def test_parse_plan_output_clean(self):
        info = parse_plan_output(MOCK_CLEAN_STDOUT)
        self.assertFalse(info["has_drift"])
        self.assertIn("No changes.", info["summary"])
        self.assertEqual(len(info["changes"]), 0)

    def test_format_telegram_alert(self):
        info = parse_plan_output(MOCK_DRIFT_STDOUT)
        msg = format_telegram_alert(info)
        self.assertIn("🚨 *Cloudflare Terraform Drift Detected*", msg)
        self.assertIn("1 to add, 1 to change, 0 to destroy", msg)
        self.assertIn("cloudflare_email_routing_settings.w0m_xyz", msg)
        self.assertIn("`just tf-plan`", msg)

    @patch("urllib.request.urlopen")
    def test_send_telegram_alert_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"ok": true, "result": {"message_id": 999}}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        res = send_telegram_alert("test message", token="mock-token", chat_id="123456")
        self.assertTrue(res)

    def test_send_telegram_alert_dry_run(self):
        res = send_telegram_alert(
            "test message",
            token="mock-token",
            chat_id="123456",
            dry_run=True,
        )
        self.assertTrue(res)

    def test_send_telegram_alert_missing_token(self):
        with patch.dict(os.environ, {}, clear=True):
            res = send_telegram_alert("test message", token="", chat_id="123456")
            self.assertFalse(res)

    @patch("tf_drift_check.run_terraform_plan")
    def test_main_clean(self, mock_run):
        mock_run.return_value = (0, MOCK_CLEAN_STDOUT, "")
        code = main(["--check"])
        self.assertEqual(code, 0)

    @patch("tf_drift_check.run_terraform_plan")
    def test_main_drift_alert(self, mock_run):
        mock_run.return_value = (2, MOCK_DRIFT_STDOUT, "")
        with patch("tf_drift_check.send_telegram_alert") as mock_send:
            mock_send.return_value = True
            code = main(["--alert"])
            self.assertEqual(code, 2)
            mock_send.assert_called_once()

    @patch("tf_drift_check.run_terraform_plan")
    def test_main_error(self, mock_run):
        mock_run.return_value = (1, "", "Terraform crashed")
        code = main(["--check"])
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
