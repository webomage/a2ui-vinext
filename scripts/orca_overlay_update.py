#!/usr/bin/env python3
"""Bootstrap, status, manual trigger, and rollback CLI for the webomage/orca overlay AppImage feed.

Once ~/Apps/orca-linux.AppImage is cut over onto a webomage/orca overlay release,
Orca's native in-app electron-updater pulls subsequent overlay builds automatically.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

UPSTREAM_REPO = "stablyai/orca"
WORKFLOW_FILE = "w0m-overlay-release.yml"
SHA512_RE = re.compile(r"^\s*sha512:\s*([A-Za-z0-9+/=]+)\s*$", re.MULTILINE)
CACHE_KEY_RE = re.compile(r"^[0-9a-f]{24}$")
DISPATCHER_MARKER = "# orca-serve-bare-orca-dispatcher"
LAUNCHER_MARKER = "# orca-appimage-stable-launcher"
CACHE_NAMESPACE_VERSION = "generation-lease-v1"
APPIMAGE_SOURCE_RECORD_NAME = "source-appimage"
LEGACY_FUSE_MOUNT_TOKEN = "/tmp/.mount_orca-"


def _quote_posix_double_quoted_apostrophe(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _cache_digest_24(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def _resolve_appimage_cache_root(home_dir: Path) -> Path:
    xdg_cache = os.environ.get("XDG_CACHE_HOME", "")
    cache_base = Path(xdg_cache) if xdg_cache and os.path.isabs(xdg_cache) else home_dir / ".cache"
    return (cache_base / "orca" / "appimage").resolve()


def _resolve_user_config_orca_dir(home_dir: Path) -> Path:
    xdg_config = os.environ.get("XDG_CONFIG_HOME", "")
    config_base = Path(xdg_config) if xdg_config and os.path.isabs(xdg_config) else home_dir / ".config"
    return (config_base / "orca").resolve()


def _is_extractable_appimage(appimage_path: Path) -> bool:
    if not appimage_path.is_file():
        return False
    try:
        with appimage_path.open("rb") as handle:
            head = handle.read(4096)
    except OSError:
        return False
    return head.startswith(b"\x7fELF") or b"--appimage-extract" in head


def _build_stable_launcher_script(launcher_dir: Path) -> str:
    quoted_dir = _quote_posix_double_quoted_apostrophe(str(launcher_dir))
    return (
        "#!/usr/bin/env bash\n"
        f"{LAUNCHER_MARKER}\n"
        "shopt -s execfail\n"
        f"launcher_dir={quoted_dir}\n"
        "deadline=$((SECONDS + 5))\n"
        "while (( SECONDS <= deadline )); do\n"
        '  launcher="$launcher_dir/installed"\n'
        '  if [[ -f "$launcher" && -x "$launcher" ]]; then\n'
        '    exec "$launcher" "$@"\n'
        "  fi\n"
        "  sleep 0.1\n"
        "done\n"
        "printf 'Orca CLI is not ready; reopen Orca or register the CLI again.\\n' >&2\n"
        "exit 1\n"
    )


def _build_bare_orca_dispatcher_script(stable_launcher_path: Path) -> str:
    quoted_launcher = _quote_posix_double_quoted_apostrophe(str(stable_launcher_path))
    quoted_marker = _quote_posix_double_quoted_apostrophe(DISPATCHER_MARKER)
    return (
        "#!/usr/bin/env bash\n"
        f"{DISPATCHER_MARKER}\n"
        f"launcher={quoted_launcher}\n"
        "gone() {\n"
        "  printf 'orca: Orca is no longer installed at %s. Remove %s to stop this message.\\n'"
        ' "$launcher" "${BASH_SOURCE[0]}" >&2\n'
        "  exit 127\n"
        "}\n"
        'if [ -n "${ORCA_CLI_BIN_DIR-}${ORCA_PANE_KEY-}${ORCA_USER_DATA_PATH-}" ]; then\n'
        '  [ -x "$launcher" ] && exec "$launcher" "$@"\n'
        "  gone\n"
        "fi\n"
        'IFS=: read -r -a path_dirs <<< "${PATH-}"\n'
        'for dir in "${path_dirs[@]}"; do\n'
        '  case "$dir" in /*) ;; *) continue ;; esac\n'
        '  candidate="$dir/orca"\n'
        '  if [ -f "$candidate" ] && [ -x "$candidate" ] && ! [ "$candidate" -ef "${BASH_SOURCE[0]}" ]; then\n'
        '    marker=""\n'
        '    { IFS= read -r _ && IFS= read -r marker; } < "$candidate" 2>/dev/null\n'
        f'    if [ "$marker" != {quoted_marker} ]; then\n'
        '      exec "$candidate" "$@"\n'
        "    fi\n"
        "  fi\n"
        "done\n"
        '[ -x "$launcher" ] && exec "$launcher" "$@"\n'
        "gone\n"
    )


def _build_bare_orca_cli_shim_script(stable_launcher_path: Path) -> str:
    quoted_launcher = _quote_posix_double_quoted_apostrophe(str(stable_launcher_path))
    return f"#!/usr/bin/env bash\nexec {quoted_launcher} \"$@\"\n"


def _atomic_write_executable(target_path: Path, content: str) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target_path.with_name(f".{target_path.name}.{os.getpid()}.tmp")
    try:
        tmp_path.write_text(content, encoding="utf-8")
        tmp_path.chmod(0o755)
        os.replace(tmp_path, target_path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def _atomic_symlink(target: str, link_path: Path) -> None:
    link_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_link = link_path.with_name(f".{link_path.name}.{os.getpid()}.lnk")
    try:
        if tmp_link.exists() or tmp_link.is_symlink():
            tmp_link.unlink()
        os.symlink(target, tmp_link)
        os.replace(tmp_link, link_path)
    finally:
        if tmp_link.exists() or tmp_link.is_symlink():
            tmp_link.unlink()


def _can_replace_bare_orca_dispatcher(dispatcher_path: Path) -> bool:
    if dispatcher_path.is_symlink():
        try:
            link_target = os.readlink(dispatcher_path)
        except OSError:
            return False
        return "orca" in link_target
    if not dispatcher_path.exists():
        return True
    if not dispatcher_path.is_file():
        return False
    try:
        text = dispatcher_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    lines = text.splitlines()
    if len(lines) > 1 and lines[1] == DISPATCHER_MARKER:
        return True
    if LEGACY_FUSE_MOUNT_TOKEN in text:
        return True
    return False


def repair_local_orca_cli(appimage_path: Path, *, home_dir: Path | None = None) -> bool:
    """Extract the AppImage CLI runtime and repair ~/.local/bin/orca + linux-orca-cli-shim."""
    if os.environ.get("ORCA_SKIP_CLI_REPAIR") == "1" or not _is_extractable_appimage(appimage_path):
        return False

    resolved_home = (home_dir or Path.home()).resolve()
    resolved_appimage = appimage_path.resolve()
    cache_root = _resolve_appimage_cache_root(resolved_home)
    namespace_key = _cache_digest_24(f"{CACHE_NAMESPACE_VERSION}\0{resolved_appimage}")
    st = resolved_appimage.stat()
    mtime_ms = st.st_mtime_ns // 1_000_000
    generation_key = _cache_digest_24(f"{st.st_dev}\0{st.st_ino}\0{st.st_size}\0{mtime_ms}")

    namespace_dir = cache_root / namespace_key
    gen_root = namespace_dir / generation_key
    payload_launcher = gen_root / "resources" / "bin" / "orca-ide"

    if not (payload_launcher.is_file() and os.access(payload_launcher, os.X_OK)):
        namespace_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=namespace_dir, prefix=".extract-") as staging_str:
            staging_dir = Path(staging_str)
            nice_bin = shutil.which("nice")
            cmd = (
                [nice_bin, "-n", "19", str(resolved_appimage), "--appimage-extract"]
                if nice_bin
                else [str(resolved_appimage), "--appimage-extract"]
            )
            res = subprocess.run(
                cmd,
                cwd=str(staging_dir),
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
            extracted_root = staging_dir / "squashfs-root"
            extracted_launcher = extracted_root / "resources" / "bin" / "orca-ide"
            if res.returncode != 0 or not extracted_launcher.is_file():
                err = (res.stderr or res.stdout).strip()
                print(
                    f"Warning: failed to extract CLI runtime from {resolved_appimage}: {err}",
                    file=sys.stderr,
                )
                return False
            if gen_root.exists():
                shutil.rmtree(gen_root, ignore_errors=True)
            os.replace(extracted_root, gen_root)

    source_record = namespace_dir / APPIMAGE_SOURCE_RECORD_NAME
    source_tmp = namespace_dir / f".{APPIMAGE_SOURCE_RECORD_NAME}.{os.getpid()}.tmp"
    try:
        source_tmp.write_text(str(resolved_appimage), encoding="utf-8")
        source_tmp.chmod(0o600)
        os.replace(source_tmp, source_record)
    finally:
        if source_tmp.exists():
            source_tmp.unlink()

    launcher_dir = cache_root / "launcher"
    stable_launcher = launcher_dir / "orca-ide"
    if not stable_launcher.exists() or (
        stable_launcher.is_file()
        and LAUNCHER_MARKER in stable_launcher.read_text(encoding="utf-8", errors="replace")
    ):
        _atomic_write_executable(stable_launcher, _build_stable_launcher_script(launcher_dir))
    _atomic_symlink(str(payload_launcher), launcher_dir / "installed")

    for child in namespace_dir.iterdir():
        if (
            child.name != generation_key
            and CACHE_KEY_RE.match(child.name)
            and child.is_dir()
            and not child.is_symlink()
        ):
            shutil.rmtree(child, ignore_errors=True)

    local_bin = resolved_home / ".local" / "bin"
    orca_ide_bin = local_bin / "orca-ide"
    if not orca_ide_bin.exists() or orca_ide_bin.is_symlink():
        _atomic_symlink(str(stable_launcher), orca_ide_bin)

    dispatcher_path = local_bin / "orca"
    if _can_replace_bare_orca_dispatcher(dispatcher_path):
        if dispatcher_path.is_symlink():
            dispatcher_path.unlink()
        _atomic_write_executable(dispatcher_path, _build_bare_orca_dispatcher_script(stable_launcher))

    shim_dir = _resolve_user_config_orca_dir(resolved_home) / "linux-orca-cli-shim"
    shim_bin = shim_dir / "orca"
    if shim_dir.is_dir() or shim_bin.is_file():
        _atomic_write_executable(shim_bin, _build_bare_orca_cli_shim_script(stable_launcher))

    return True


def _default_appimage_path() -> Path:
    env_path = os.environ.get("ORCA_APPIMAGE_PATH")
    if env_path:
        return Path(env_path).expanduser()
    return Path.home() / "Apps" / "orca-linux.AppImage"


def _overlay_repo() -> str:
    return os.environ.get("ORCA_OVERLAY_REPO", "webomage/orca")


def _human_size(path: Path) -> str:
    if not path.is_file():
        return "missing"
    size = float(path.stat().st_size)
    for unit in ("B", "K", "M", "G"):
        if size < 1024.0 or unit == "G":
            return f"{size:.0f}{unit}" if unit in ("B", "K", "M") else f"{size:.1f}{unit}"
        size /= 1024.0
    return f"{size:.1f}G"


def _local_cli_version() -> str:
    orca_bin = Path.home() / ".local" / "bin" / "orca"
    if not orca_bin.is_file() or not os.access(orca_bin, os.X_OK):
        return "unknown"
    res = subprocess.run([str(orca_bin), "--version"], capture_output=True, text=True, check=False)
    if res.returncode == 0 and res.stdout.strip():
        return res.stdout.splitlines()[0].strip()
    return "unknown"


def _expected_sha512_from_yml(yml_path: Path) -> str:
    yml_text = yml_path.read_text(encoding="utf-8")
    match = SHA512_RE.search(yml_text)
    if not match:
        raise RuntimeError(f"Failed to parse sha512 from {yml_path}")
    return match.group(1)


def _compute_sha512_b64(file_path: Path) -> str:
    digest = hashlib.sha512()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return base64.b64encode(digest.digest()).decode("ascii")


def _gh_json(endpoint: str) -> dict[str, Any] | None:
    res = subprocess.run(["gh", "api", endpoint], capture_output=True, text=True, check=False)
    if res.returncode != 0 or not res.stdout.strip():
        return None
    parsed: dict[str, Any] = json.loads(res.stdout)
    return parsed


def show_status(appimage_path: Path, backup_path: Path, overlay_repo: str) -> int:
    print("=== Local Orca Installation ===")
    print(f"  AppImage path : {appimage_path} ({_human_size(appimage_path)})")
    print(f"  Running CLI   : {_local_cli_version()}")
    print(f"  Stock backup  : {backup_path} ({'present' if backup_path.is_file() else 'none'})")
    print()

    print(f"=== Upstream Stable ({UPSTREAM_REPO}) ===")
    upstream = _gh_json(f"repos/{UPSTREAM_REPO}/releases/latest")
    print(f"  Latest tag    : {upstream.get('tag_name', 'unavailable') if upstream else 'unavailable'}")
    print()

    print(f"=== w0m Overlay Feed ({overlay_repo}) ===")
    overlay = _gh_json(f"repos/{overlay_repo}/releases/latest")
    if overlay:
        print(f"  Latest tag    : {overlay.get('tag_name', 'unknown')}")
        print(f"  Published at  : {overlay.get('published_at', 'unknown')}")
        print(f"  Release URL   : {overlay.get('html_url', 'unknown')}")
    else:
        print("  Latest tag    : (no published release yet)")
    print()

    print("=== Latest Overlay CI Run ===")
    runs = subprocess.run(
        ["gh", "run", "list", "-R", overlay_repo, "-w", WORKFLOW_FILE, "--limit", "3"],
        capture_output=True,
        text=True,
        check=False,
    )
    if runs.returncode == 0 and runs.stdout.strip():
        print(runs.stdout.rstrip())
    else:
        print(f"  (no overlay workflow runs found on https://github.com/{overlay_repo}/actions)")
    return 0


def trigger_overlay_build(overlay_repo: str) -> int:
    print(f"Dispatching {WORKFLOW_FILE} on {overlay_repo} (ref: beta)...")
    res = subprocess.run(
        ["gh", "workflow", "run", WORKFLOW_FILE, "-R", overlay_repo, "--ref", "beta"],
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        err = (res.stderr or res.stdout).strip()
        print(err, file=sys.stderr)
        if "Actions has been disabled" in err:
            print(
                "\nAction required (one-time GitHub org toggle):\n"
                f"  1. Enable GitHub Actions for '{overlay_repo}' at "
                "https://github.com/organizations/webomage/settings/actions\n"
                "  2. Re-run: just orca-apply",
                file=sys.stderr,
            )
        return 1
    print(f"Dispatched {WORKFLOW_FILE} successfully.")
    return 0


def restore_stock(appimage_path: Path, backup_path: Path) -> int:
    if not backup_path.is_file():
        print(f"Error: stock backup not found at {backup_path}", file=sys.stderr)
        return 1
    tmp_path = appimage_path.with_name(f"{appimage_path.name}.restore.{os.getpid()}")
    try:
        shutil.copy2(backup_path, tmp_path)
        tmp_path.chmod(0o755)
        now_sec = int(time.time())
        os.utime(tmp_path, (now_sec, now_sec))
        os.replace(tmp_path, appimage_path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
    repair_local_orca_cli(appimage_path)
    print(f"Restored stock AppImage from {backup_path} -> {appimage_path}")
    print("Restart Orca to resume stock stablyai/orca auto-updates.")
    return 0


def _active_ci_run_id(overlay_repo: str) -> str:
    res = subprocess.run(
        [
            "gh",
            "run",
            "list",
            "-R",
            overlay_repo,
            "-w",
            WORKFLOW_FILE,
            "--limit",
            "5",
            "--json",
            "databaseId,status",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0 or not res.stdout.strip():
        return ""
    try:
        runs: list[dict[str, Any]] = json.loads(res.stdout)
    except json.JSONDecodeError:
        return ""
    for run in runs:
        if run.get("status") != "completed" and run.get("databaseId"):
            return str(run["databaseId"])
    return ""


def apply_overlay(
    appimage_path: Path,
    backup_path: Path,
    overlay_repo: str,
    *,
    wait_for_ci: bool,
    force_download: bool,
) -> int:
    if wait_for_ci:
        in_progress_id = _active_ci_run_id(overlay_repo)
        if not in_progress_id and _gh_json(f"repos/{overlay_repo}/releases/latest") is None:
            rc = trigger_overlay_build(overlay_repo)
            if rc != 0:
                return rc
            for _ in range(5):
                time.sleep(3)
                in_progress_id = _active_ci_run_id(overlay_repo)
                if in_progress_id:
                    break
        if in_progress_id:
            print(f"Waiting for active overlay CI run #{in_progress_id} on {overlay_repo}...")
            watch = subprocess.run(
                ["gh", "run", "watch", in_progress_id, "-R", overlay_repo, "--exit-status"],
                check=False,
            )
            if watch.returncode != 0:
                return watch.returncode

    release = _gh_json(f"repos/{overlay_repo}/releases/latest")
    if not release or not release.get("tag_name"):
        print(
            f"No published overlay release found yet on https://github.com/{overlay_repo}/releases.\n"
            "Check build progress with: just orca-status",
            file=sys.stderr,
        )
        return 2

    tag = str(release["tag_name"])
    print(f"Found latest overlay release: {overlay_repo}@{tag}")

    appimage_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=appimage_path.parent, prefix=".orca-overlay-dl.") as tmp_str:
        workdir = Path(tmp_str)
        yml_dl = subprocess.run(
            ["gh", "release", "download", tag, "-R", overlay_repo, "-D", str(workdir), "-p", "latest-linux.yml"],
            check=False,
        )
        if yml_dl.returncode != 0:
            return yml_dl.returncode

        expected_b64 = _expected_sha512_from_yml(workdir / "latest-linux.yml")

        if not force_download and appimage_path.is_file():
            current_b64 = _compute_sha512_b64(appimage_path)
            if current_b64 == expected_b64:
                repaired = repair_local_orca_cli(appimage_path)
                print(f"Already up to date: {appimage_path} matches {overlay_repo}@{tag}")
                print(f"  SHA-512 verified OK ({current_b64[:24]}...)")
                if repaired:
                    print(f"  Local CLI verified ({_local_cli_version()})")
                print("Restart Orca once if still running an older session.")
                return 0

        print(f"Downloading orca-linux.AppImage from {overlay_repo}@{tag}...")
        bin_dl = subprocess.run(
            ["gh", "release", "download", tag, "-R", overlay_repo, "-D", str(workdir), "-p", "orca-linux.AppImage"],
            check=False,
        )
        if bin_dl.returncode != 0:
            return bin_dl.returncode

        staged_appimage = workdir / "orca-linux.AppImage"
        print("Verifying SHA-512 digest against latest-linux.yml...")
        actual_b64 = _compute_sha512_b64(staged_appimage)
        if actual_b64 != expected_b64:
            print(
                f"SHA-512 mismatch!\n  expected: {expected_b64}\n  actual:   {actual_b64}",
                file=sys.stderr,
            )
            return 1
        print(f"  SHA-512 verified OK ({actual_b64[:24]}...)")

        staged_appimage.chmod(0o755)
        now_sec = int(time.time())
        os.utime(staged_appimage, (now_sec, now_sec))
        if appimage_path.is_file() and not backup_path.is_file():
            shutil.copy2(appimage_path, backup_path)
            print(f"Saved stock AppImage backup -> {backup_path}")

        os.replace(staged_appimage, appimage_path)

    repaired = repair_local_orca_cli(appimage_path)
    print(f"Installed {overlay_repo}@{tag} -> {appimage_path}")
    if repaired:
        print(f"Repaired local CLI -> {_local_cli_version()}")
    print("Restart Orca once to activate the overlay build and automatic webomage/orca updates.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="orca-overlay-update",
        description=(
            "One-time bootstrap, status, and rollback helper for the self-healing "
            "webomage/orca AppImage feed (subsequent updates run via Orca's native auto-updater)."
        ),
    )
    parser.add_argument("--status", action="store_true", help="Show local version, backup, release, and CI status")
    parser.add_argument("--trigger", action="store_true", help="Dispatch w0m-overlay-release.yml on webomage/orca")
    parser.add_argument("--apply", action="store_true", help="Download, SHA-512 verify, and install AppImage (default)")
    parser.add_argument("--wait", action="store_true", help="Wait for active CI build before applying")
    parser.add_argument("--force", action="store_true", help="Re-download even if local AppImage SHA-512 matches")
    parser.add_argument("--repair-cli", action="store_true", help="Extract AppImage CLI and repair ~/.local/bin/orca")
    parser.add_argument("--restore-stock", action="store_true", help="Restore stock AppImage from .stock.bak")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    appimage_path = _default_appimage_path()
    backup_path = Path(f"{appimage_path}.stock.bak")
    overlay_repo = _overlay_repo()

    if args.status:
        return show_status(appimage_path, backup_path, overlay_repo)
    if args.repair_cli:
        if not repair_local_orca_cli(appimage_path):
            print(f"Error: failed to repair Orca CLI from {appimage_path}", file=sys.stderr)
            return 1
        print(f"Repaired local Orca CLI ({_local_cli_version()}) from {appimage_path}")
        return 0
    if args.restore_stock:
        return restore_stock(appimage_path, backup_path)
    if args.trigger and not args.apply and not args.wait:
        return trigger_overlay_build(overlay_repo)

    if args.trigger:
        rc = trigger_overlay_build(overlay_repo)
        if rc != 0:
            return rc
        if args.wait:
            for _ in range(6):
                if _active_ci_run_id(overlay_repo):
                    break
                time.sleep(3)

    return apply_overlay(
        appimage_path,
        backup_path,
        overlay_repo,
        wait_for_ci=args.wait,
        force_download=args.force,
    )


if __name__ == "__main__":
    raise SystemExit(main())
