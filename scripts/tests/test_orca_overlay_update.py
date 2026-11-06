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
        env.pop("XDG_CACHE_HOME", None)
        env.pop("XDG_CONFIG_HOME", None)
        env.pop("ORCA_CLI_BIN_DIR", None)
        env.pop("ORCA_PANE_KEY", None)
        env.pop("ORCA_USER_DATA_PATH", None)
        env["ORCA_APPIMAGE_PATH"] = str(self.appimage_path)
        env["ORCA_OVERLAY_REPO"] = "webomage/orca"
        env["PATH"] = f"{self.bin_dir}:/usr/local/bin:/usr/bin:/bin"
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

    def _fake_appimage_bytes(self, version: str) -> bytes:
        script = f"""#!/usr/bin/env bash
set -euo pipefail
if [[ "${{1:-}}" == "--appimage-extract" ]]; then
  mkdir -p squashfs-root/resources/bin
  cat > squashfs-root/resources/bin/orca-ide <<'EOF'
#!/usr/bin/env bash
if [[ "${{1:-}}" == "--version" ]]; then
  echo "{version}"
  exit 0
fi
echo "orca-ide:{version}:$*"
EOF
  chmod 755 squashfs-root/resources/bin/orca-ide
  exit 0
fi
echo "appimage:{version}"
"""
        return script.encode("utf-8")

    def test_apply_extracts_cli_heals_legacy_fuse_wrapper_and_shim_and_prunes_old_generations(self) -> None:
        local_bin = self.root / ".local" / "bin"
        local_bin.mkdir(parents=True)
        legacy_orca = local_bin / "orca"
        legacy_orca.write_text(
            "#!/usr/bin/env bash\n"
            "MOUNT=$(ls -1dt /tmp/.mount_orca-* 2>/dev/null | head -n 1 || true)\n"
            'echo "orca runtime mount not found under /tmp/.mount_orca-*" >&2\n'
            "exit 1\n",
            encoding="utf-8",
        )
        legacy_orca.chmod(0o755)

        shim_dir = self.root / ".config" / "orca" / "linux-orca-cli-shim"
        shim_dir.mkdir(parents=True)
        shim_orca = shim_dir / "orca"
        shim_orca.write_text(
            "#!/usr/bin/env bash\nruntime_root='/tmp/.mount_orca-stale'\nexit 1\n",
            encoding="utf-8",
        )
        shim_orca.chmod(0o755)

        self._stage_release("v1.4.251-w0m.1", self._fake_appimage_bytes("1.4.251-w0m.1"))
        first = self._run_script("--apply")
        self.assertEqual(first.returncode, 0, msg=f"stderr={first.stderr}\nstdout={first.stdout}")

        clean_env = {"HOME": str(self.root), "PATH": "/usr/local/bin:/usr/bin:/bin"}
        cli_v1 = subprocess.run([str(legacy_orca), "--version"], env=clean_env, capture_output=True, text=True, check=False)
        self.assertEqual(cli_v1.returncode, 0, msg=cli_v1.stderr)
        self.assertEqual(cli_v1.stdout.strip(), "1.4.251-w0m.1")
        self.assertIn("# orca-serve-bare-orca-dispatcher", legacy_orca.read_text(encoding="utf-8"))

        shim_v1 = subprocess.run([str(shim_orca), "--version"], env=clean_env, capture_output=True, text=True, check=False)
        self.assertEqual(shim_v1.returncode, 0, msg=shim_v1.stderr)
        self.assertEqual(shim_v1.stdout.strip(), "1.4.251-w0m.1")

        self._stage_release("v1.4.251-w0m.2", self._fake_appimage_bytes("1.4.251-w0m.2"))
        second = self._run_script("--apply")
        self.assertEqual(second.returncode, 0, msg=second.stderr)

        cli_v2 = subprocess.run([str(legacy_orca), "--version"], env=clean_env, capture_output=True, text=True, check=False)
        self.assertEqual(cli_v2.returncode, 0, msg=cli_v2.stderr)
        self.assertEqual(cli_v2.stdout.strip(), "1.4.251-w0m.2")

        cache_root = self.root / ".cache" / "orca" / "appimage"
        namespaces = [p for p in cache_root.iterdir() if p.is_dir() and p.name != "launcher"]
        self.assertEqual(len(namespaces), 1)
        generations = [p for p in namespaces[0].iterdir() if p.is_dir()]
        self.assertEqual(len(generations), 1)

    def test_repair_cli_preserves_foreign_orca_binary(self) -> None:
        local_bin = self.root / ".local" / "bin"
        local_bin.mkdir(parents=True)
        foreign_orca = local_bin / "orca"
        foreign_content = "#!/usr/bin/env bash\necho gnome-orca-screen-reader\n"
        foreign_orca.write_text(foreign_content, encoding="utf-8")
        foreign_orca.chmod(0o755)

        self.appimage_path.write_bytes(self._fake_appimage_bytes("1.4.251-w0m.2"))
        self.appimage_path.chmod(0o755)
        proc = self._run_script("--repair-cli")
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        self.assertEqual(foreign_orca.read_text(encoding="utf-8"), foreign_content)
        orca_ide_bin = local_bin / "orca-ide"
        self.assertTrue(orca_ide_bin.is_symlink())


if __name__ == "__main__":
    unittest.main()
