#!/usr/bin/env python3
"""Unit tests for `scripts/env_prune_dead.py` (T730 AC1, T731 AC1-AC3)."""

from __future__ import annotations

import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import env_prune_dead as epd  # noqa: E402


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

    def test_encrypted_backup_roundtrip_zero_plaintext_and_tamper_rejection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backup_dir = Path(tmp) / "infisical-backups"
            sample_a = "fixture-alpha-value-98765"
            sample_b = "fixture-bravo-value-54321"
            meta = epd.write_encrypted_backup_from_mapping(
                secret_map={"CRON_SECRET": sample_a, "OCI_VM_OCPUS": sample_b},
                backup_dir=backup_dir,
                project_id="proj-test-123",
                infisical_env="beta",
            )

            archive_path = Path(meta["archive_path"])
            manifest_path = Path(meta["manifest_path"])
            key_path = backup_dir / "master.key"
            self.assertTrue(archive_path.is_file())
            self.assertTrue(manifest_path.is_file())
            self.assertTrue(key_path.is_file())
            self.assertTrue(meta["roundtrip_verified"])
            self.assertEqual(meta["backed_up_count"], 2)

            self.assertEqual(stat.S_IMODE(backup_dir.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(key_path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(archive_path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(manifest_path.stat().st_mode), 0o600)

            archive_text = archive_path.read_text(encoding="utf-8")
            manifest_text = manifest_path.read_text(encoding="utf-8")
            for raw in (archive_text, manifest_text, json.dumps(meta)):
                self.assertNotIn(sample_a, raw)
                self.assertNotIn(sample_b, raw)

            verified = epd.verify_encrypted_backup(archive_path, backup_dir=backup_dir)
            self.assertTrue(verified["verified"])
            self.assertEqual(verified["key_count"], 2)
            self.assertEqual(verified["key_names"], ["CRON_SECRET", "OCI_VM_OCPUS"])
            self.assertNotIn(sample_a, json.dumps(verified))

            tampered_doc = json.loads(archive_text)
            tampered_doc["infisical_env"] = "prod"
            tampered_path = backup_dir / "tampered.aesgcm"
            tampered_path.write_text(json.dumps(tampered_doc), encoding="utf-8")
            with self.assertRaises(ValueError):
                epd.verify_encrypted_backup(tampered_path, backup_dir=backup_dir)

    def test_apply_requires_verified_backup_and_aborts_deletion_on_backup_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "estate"
            backup_dir = Path(tmp) / "backups"
            self._make_mini_estate(root)

            delete_calls: list[list[str]] = []

            def fake_run(cmd: list[str], **kwargs: object) -> object:
                delete_calls.append(list(cmd))

                class _Res:
                    returncode = 0

                return _Res()

            with (
                patch("subprocess.run", side_effect=fake_run),
                patch.object(
                    epd,
                    "capture_infisical_encrypted_backup",
                    side_effect=RuntimeError("simulated backup failure"),
                ),
            ):
                with self.assertRaises(RuntimeError):
                    epd.prune_dead_infisical_keys(
                        root=root,
                        candidate_keys=["PUBLIC_SUPABASE_URL", "CRON_SECRET"],
                        repos=(".", "w0m-web"),
                        infisical_env="beta",
                        project_id="proj-test-123",
                        backup_dir=backup_dir,
                        apply=True,
                    )
            self.assertEqual(delete_calls, [])

            pre_backup = epd.write_encrypted_backup_from_mapping(
                secret_map={"CRON_SECRET": "val-1", "SIGNOZ_API_KEY": "val-2"},
                backup_dir=backup_dir,
                project_id="proj-test-123",
                infisical_env="beta",
            )
            with patch("subprocess.run", side_effect=fake_run):
                result = epd.prune_dead_infisical_keys(
                    root=root,
                    candidate_keys=["PUBLIC_SUPABASE_URL", "CRON_SECRET", "SIGNOZ_API_KEY"],
                    repos=(".", "w0m-web"),
                    infisical_env="beta",
                    project_id="proj-test-123",
                    backup_dir=backup_dir,
                    backup_archive=Path(pre_backup["archive_path"]),
                    apply=True,
                )

            self.assertEqual(result["mode"], "applied")
            self.assertEqual(result["deleted_keys"], ["CRON_SECRET", "SIGNOZ_API_KEY"])
            self.assertTrue(result["backup"]["verified"])
            self.assertEqual(len(delete_calls), 1)
            self.assertEqual(
                delete_calls[0],
                [
                    "infisical",
                    "secrets",
                    "delete",
                    "CRON_SECRET",
                    "SIGNOZ_API_KEY",
                    "--type=shared",
                    "--env=beta",
                    "--projectId=proj-test-123",
                    "--silent",
                ],
            )
            self.assertNotIn("PUBLIC_SUPABASE_URL", delete_calls[0])

    def test_restore_encrypted_backup_dry_run_and_selective_apply(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backup_dir = Path(tmp) / "backups"
            sample_cron = "restore-fixture-cron-111"
            sample_oci = "restore-fixture-oci-222"
            meta = epd.write_encrypted_backup_from_mapping(
                secret_map={"CRON_SECRET": sample_cron, "OCI_VM_OCPUS": sample_oci},
                backup_dir=backup_dir,
                project_id="proj-test-123",
                infisical_env="beta",
            )
            archive_path = Path(meta["archive_path"])

            with patch("subprocess.run") as mock_run:
                dry = epd.restore_encrypted_backup(
                    archive_path=archive_path,
                    backup_dir=backup_dir,
                    keys=["CRON_SECRET"],
                    apply=False,
                )
                mock_run.assert_not_called()
            self.assertEqual(dry["mode"], "dry-run")
            self.assertEqual(dry["selected_keys"], ["CRON_SECRET"])
            self.assertEqual(dry["restored_keys"], [])
            self.assertNotIn(sample_cron, json.dumps(dry))

            set_calls: list[list[str]] = []

            def fake_set(cmd: list[str], **kwargs: object) -> object:
                set_calls.append(list(cmd))

                class _Res:
                    returncode = 0
                    stderr = ""

                return _Res()

            with patch("subprocess.run", side_effect=fake_set):
                applied = epd.restore_encrypted_backup(
                    archive_path=archive_path,
                    backup_dir=backup_dir,
                    keys=["CRON_SECRET"],
                    infisical_env="beta",
                    project_id="proj-test-123",
                    apply=True,
                )

            self.assertEqual(applied["mode"], "restored")
            self.assertEqual(applied["restored_keys"], ["CRON_SECRET"])
            self.assertNotIn(sample_cron, json.dumps(applied))
            self.assertEqual(len(set_calls), 1)
            self.assertEqual(
                set_calls[0],
                [
                    "infisical",
                    "secrets",
                    "set",
                    f"CRON_SECRET={sample_cron}",
                    "--type=shared",
                    "--env=beta",
                    "--projectId=proj-test-123",
                    "--silent",
                ],
            )


if __name__ == "__main__":
    unittest.main()
