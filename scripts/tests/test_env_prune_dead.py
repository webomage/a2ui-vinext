#!/usr/bin/env python3
"""Unit tests for `scripts/env_prune_dead.py` (T730 AC1)."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import env_prune_dead as epd  # type: ignore[import-not-found]  # noqa: E402


class TestEnvPruneDead(unittest.TestCase):
    def _make_mini_estate(self, root: Path) -> None:
        (root / "w0m-web" / "apps" / "web" / "src").mkdir(parents=True, exist_ok=True)
        (root / "w0m-web" / "apps" / "web" / "src" / "live.ts").write_text(
            "export const url = import.meta.env.PUBLIC_SUPABASE_URL;\n",
            encoding="utf-8",
        )
        (root / "justfile").write_text(
            "check:\n    echo $ADMIN_PASSWORD\n",
            encoding="utf-8",
        )

    def test_dry_run_groups_dead_keys_and_never_invokes_infisical_delete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make_mini_estate(root)
            candidates = [
                "PUBLIC_SUPABASE_URL",
                "ADMIN_PASSWORD",
                "CRON_SECRET",
                "SIGNOZ_API_KEY",
                "OCI_COMPARTMENT_OCID",
            ]
            with patch("subprocess.run") as mock_run:
                result = epd.prune_dead_infisical_keys(
                    root=root,
                    candidate_keys=candidates,
                    repos=(".", "w0m-web"),
                    infisical_env="beta",
                    apply=False,
                )
                mock_run.assert_not_called()

            self.assertEqual(result["mode"], "dry-run")
            self.assertEqual(
                result["dead_keys"],
                ["CRON_SECRET", "OCI_COMPARTMENT_OCID", "SIGNOZ_API_KEY"],
            )
            self.assertIn("PUBLIC_SUPABASE_URL", result["protected_active_keys"])
            self.assertIn("ADMIN_PASSWORD", result["protected_active_keys"])
            self.assertIn("historical_leak_dead", result["groups"])
            self.assertIn("CRON_SECRET", result["groups"]["historical_leak_dead"])

    def test_refuses_explicit_target_key_that_still_has_readers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make_mini_estate(root)
            with self.assertRaises(ValueError):
                epd.prune_dead_infisical_keys(
                    root=root,
                    candidate_keys=["PUBLIC_SUPABASE_URL", "CRON_SECRET"],
                    explicit_targets=["PUBLIC_SUPABASE_URL"],
                    repos=(".", "w0m-web"),
                    infisical_env="beta",
                    apply=True,
                )

    def test_apply_deletes_only_verified_zero_reader_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make_mini_estate(root)
            calls: list[list[str]] = []

            def fake_run(cmd: list[str], **kwargs: object) -> object:
                calls.append(list(cmd))

                class _Res:
                    returncode = 0

                return _Res()

            with patch("subprocess.run", side_effect=fake_run):
                result = epd.prune_dead_infisical_keys(
                    root=root,
                    candidate_keys=["PUBLIC_SUPABASE_URL", "CRON_SECRET", "MEMBER_PASSWORD"],
                    repos=(".", "w0m-web"),
                    infisical_env="beta",
                    project_id="proj-test-123",
                    apply=True,
                )

            self.assertEqual(result["mode"], "applied")
            self.assertEqual(result["deleted_keys"], ["CRON_SECRET", "MEMBER_PASSWORD"])
            self.assertEqual(len(calls), 2)
            for cmd in calls:
                self.assertEqual(cmd[:3], ["infisical", "secrets", "delete"])
                self.assertNotIn("PUBLIC_SUPABASE_URL", cmd)
                self.assertIn("--env=beta", cmd)
                self.assertIn("--projectId=proj-test-123", cmd)


if __name__ == "__main__":
    unittest.main()
