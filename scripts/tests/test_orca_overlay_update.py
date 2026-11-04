#!/usr/bin/env python3
"""Hermetic regression tests for scripts/orca_overlay_update.py (T627)."""

from __future__ import annotations

import base64
import hashlib
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "orca_overlay_update.py"


def _sha512_b64(data: bytes) -> str:
    return base64.b64encode(hashlib.sha512(data).digest()).decode("ascii")


class OrcaOverlayUpdateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.bin_dir = self.root / "bin"
        self.apps_dir = self.root / "Apps"
        self.fixtures_dir = self.root / "fixtures"
        self.bin_dir.mkdir()
        self.apps_dir.mkdir()
        self.fixtures_dir.mkdir()

        self.appimage_path = self.apps_dir / "orca-linux.AppImage"
        self.backup_path = self.apps_dir / "orca-linux.AppImage.stock.bak"
        self.gh_log = self.root / "gh.log"

        self.stock_bytes = b"STOCK-ORCA-1.4.247\n"
        self.overlay_v1_bytes = b"OVERLAY-ORCA-1.4.249-w0m.1\n"
        self.overlay_v2_bytes = b"OVERLAY-ORCA-1.4.249-w0m.2\n"

        self.appimage_path.write_bytes(self.stock_bytes)
        self.appimage_path.chmod(0o755)
        self._stage_release("v1.4.249-w0m.1", self.overlay_v1_bytes)
        self._install_stub_gh()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _stage_release(self, tag: str, payload: bytes, *, yml_sha512: str | None = None) -> None:
        (self.fixtures_dir / "tag.txt").write_text(tag, encoding="utf-8")
        (self.fixtures_dir / "orca-linux.AppImage").write_bytes(payload)
        digest = yml_sha512 if yml_sha512 is not None else _sha512_b64(payload)
        yml = (
            f"version: {tag.lstrip('v')}\n"
            f"files:\n"
            f"  - url: orca-linux.AppImage\n"
            f"    sha512: {digest}\n"
            f"path: orca-linux.AppImage\n"
            f"sha512: {digest}\n"
        )
        (self.fixtures_dir / "latest-linux.yml").write_text(yml, encoding="utf-8")

    def _install_stub_gh(self) -> None:
        gh_stub = self.bin_dir / "gh"
        gh_stub.write_text(
            f"""#!/usr/bin/env bash
set -euo pipefail
echo "$*" >> "{self.gh_log}"
FIXTURES="{self.fixtures_dir}"
TAG="$(cat "$FIXTURES/tag.txt")"

if [[ "${{1:-}}" == "api" ]]; then
  endpoint="${{2:-}}"
  if [[ "$endpoint" == *"/releases/latest" ]]; then
    if [[ "${{3:-}}" == "--jq" ]]; then
      echo "v1.4.248"
    else
      printf '{{"tag_name":"%s","published_at":"2026-11-04T03:09:30Z","html_url":"https://github.com/webomage/orca/releases/tag/%s"}}\\n' "$TAG" "$TAG"
    fi
    exit 0
  fi
fi

if [[ "${{1:-}}" == "run" && "${{2:-}}" == "list" ]]; then
  if [[ "$*" == *"--json"* ]]; then
    echo ""
  else
    printf 'completed\\tsuccess\\tw0m Overlay Release\\t41764577088\\n'
  fi
  exit 0
fi

if [[ "${{1:-}}" == "release" && "${{2:-}}" == "download" ]]; then
  dest=""
  patterns=()
  shift 2
  while (( $# > 0 )); do
    case "$1" in
      -R) shift 2 ;;
      -D) dest="$2"; shift 2 ;;
      -p) patterns+=("$2"); shift 2 ;;
      *) shift ;;
    esac
  done
  for p in "${{patterns[@]}}"; do
    cp -f "$FIXTURES/$p" "$dest/$p"
  done
  exit 0
fi

echo "Unexpected gh invocation: $*" >&2
exit 1
""",
            encoding="utf-8",
        )
        gh_stub.chmod(0o755)

    def _run_script(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["HOME"] = str(self.root)
        env["ORCA_APPIMAGE_PATH"] = str(self.appimage_path)
        env["ORCA_OVERLAY_REPO"] = "webomage/orca"
        env["PATH"] = f"{self.bin_dir}:{env.get('PATH', '')}"
        return subprocess.run(
            [sys.executable, str(SCRIPT_PATH), *args],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def _leftover_temp_dirs(self) -> list[Path]:
        return list(self.apps_dir.glob(".orca-overlay-dl.*"))

    def test_apply_installs_overlay_creates_stock_backup_and_exits_zero_without_unbound_var(self) -> None:
        proc = self._run_script("--apply", "--wait")
        self.assertEqual(proc.returncode, 0, msg=f"stderr={proc.stderr}\nstdout={proc.stdout}")
        self.assertNotIn("unbound variable", proc.stderr)
        self.assertEqual(self.appimage_path.read_bytes(), self.overlay_v1_bytes)
        self.assertTrue(bool(self.appimage_path.stat().st_mode & stat.S_IXUSR))
        self.assertTrue(self.backup_path.is_file())
        self.assertEqual(self.backup_path.read_bytes(), self.stock_bytes)
        self.assertEqual(self._leftover_temp_dirs(), [])

    def test_second_apply_uses_sha512_fast_path_without_redownloading_appimage(self) -> None:
        first = self._run_script("--apply")
        self.assertEqual(first.returncode, 0, msg=first.stderr)
        self.gh_log.write_text("", encoding="utf-8")

        second = self._run_script("--apply", "--wait")
        self.assertEqual(second.returncode, 0, msg=f"stderr={second.stderr}\nstdout={second.stdout}")
        self.assertIn("Already up to date:", second.stdout)
        self.assertNotIn("unbound variable", second.stderr)
        log_text = self.gh_log.read_text(encoding="utf-8")
        self.assertIn("-p latest-linux.yml", log_text)
        self.assertNotIn("-p orca-linux.AppImage", log_text)
        self.assertEqual(self.backup_path.read_bytes(), self.stock_bytes)
        self.assertEqual(self._leftover_temp_dirs(), [])

    def test_upgrade_to_newer_overlay_preserves_original_stock_backup(self) -> None:
        self.assertEqual(self._run_script("--apply").returncode, 0)
        self._stage_release("v1.4.249-w0m.2", self.overlay_v2_bytes)

        upgrade = self._run_script("--apply")
        self.assertEqual(upgrade.returncode, 0, msg=upgrade.stderr)
        self.assertEqual(self.appimage_path.read_bytes(), self.overlay_v2_bytes)
        self.assertEqual(self.backup_path.read_bytes(), self.stock_bytes)
        self.assertEqual(self._leftover_temp_dirs(), [])

    def test_sha512_mismatch_aborts_cleanly_and_removes_temp_dir(self) -> None:
        bad_digest = _sha512_b64(b"corrupted-payload")
        self._stage_release("v1.4.249-w0m.1", self.overlay_v1_bytes, yml_sha512=bad_digest)

        proc = self._run_script("--apply")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("SHA-512 mismatch", proc.stderr)
        self.assertNotIn("unbound variable", proc.stderr)
        self.assertEqual(self.appimage_path.read_bytes(), self.stock_bytes)
        self.assertFalse(self.backup_path.exists())
        self.assertEqual(self._leftover_temp_dirs(), [])

    def test_restore_stock_and_status_exit_zero(self) -> None:
        self.assertEqual(self._run_script("--apply").returncode, 0)
        restored = self._run_script("--restore-stock")
        self.assertEqual(restored.returncode, 0, msg=restored.stderr)
        self.assertEqual(self.appimage_path.read_bytes(), self.stock_bytes)

        status = self._run_script("--status")
        self.assertEqual(status.returncode, 0, msg=status.stderr)
        self.assertIn("v1.4.249-w0m.1", status.stdout)


if __name__ == "__main__":
    unittest.main()
