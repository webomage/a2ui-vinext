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
        os.replace(tmp_path, appimage_path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
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
                print(f"Already up to date: {appimage_path} matches {overlay_repo}@{tag}")
                print(f"  SHA-512 verified OK ({current_b64[:24]}...)")
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
        if appimage_path.is_file() and not backup_path.is_file():
            shutil.copy2(appimage_path, backup_path)
            print(f"Saved stock AppImage backup -> {backup_path}")

        os.replace(staged_appimage, appimage_path)

    print(f"Installed {overlay_repo}@{tag} -> {appimage_path}")
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
    parser.add_argument("--restore-stock", action="store_true", help="Restore stock AppImage from .stock.bak")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    appimage_path = _default_appimage_path()
    backup_path = Path(f"{appimage_path}.stock.bak")
    overlay_repo = _overlay_repo()

    if args.status:
        return show_status(appimage_path, backup_path, overlay_repo)
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
