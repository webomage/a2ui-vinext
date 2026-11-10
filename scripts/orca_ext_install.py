#!/usr/bin/env python3
"""T710 — Install, stage, and enable the `w0m-ext` MV3 extension inside Orca's Embedded Browser.

Implements deterministic Chromium/Orca unpacked extension ID derivation, clean unpacked staging
into `~/.config/orca/browser-extensions/unpacked/<digest32>`, registration in
`~/.config/orca/browser-extensions/installed.json`, profile enablement + toolbar pinning across
all Orca browser profiles (`browser-session-meta.json`), and `experimentalBrowserExtensions = true`
in `~/.config/orca/profiles/local-default/profile-state.db`.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ESTATE_ROOT = Path(__file__).resolve().parents[1]
LIVE_W0M_ROOT = Path.home() / "Projects" / "!self" / "w0m"
DEFAULT_ORCA_USER_DATA = Path.home() / ".config" / "orca"

EXCLUDED_UNPACKED_NAMES = {
    ".git",
    "node_modules",
    "package",
    "export",
    "export.md",
    "tests",
    "coverage",
    ".turbo",
    ".vite",
}


def resolve_default_extension_dir(estate_root: Path = ESTATE_ROOT) -> Path:
    """Prefer the canonical live checkout path so the unpacked folder path stays stable across worktrees."""
    live_ext = LIVE_W0M_ROOT / "w0m-ext" / "extension"
    if live_ext.is_dir() and (live_ext / "manifest.json").is_file():
        return live_ext
    return estate_root / "w0m-ext" / "extension"


def unpacked_manifest_key(source_directory: Path | str) -> str:
    """Match Orca's `unpackedManifestKey(sourceDirectory)` (`sha256('orca-unpacked:' + resolve(dir))` base64)."""
    resolved = os.path.abspath(str(source_directory))
    digest = hashlib.sha256(f"orca-unpacked:{resolved}".encode("utf-8")).digest()
    return base64.b64encode(digest).decode("ascii")


def chrome_extension_id_from_key(base64_key: str) -> str:
    """Match Chromium/Orca's `chromeExtensionIdFromKey(base64Key)` (`0-f` -> `a-p` over first 32 hex chars)."""
    clean_b64 = "".join(base64_key.split())
    raw_bytes = base64.b64decode(clean_b64)
    hex32 = hashlib.sha256(raw_bytes).hexdigest()[:32]
    return "".join(chr(97 + int(ch, 16)) for ch in hex32)


def browser_extension_id_for_unpacked_folder(source_directory: Path | str) -> str:
    """Compute the deterministic 32-char a-p extension ID for an unpacked extension folder."""
    manifest_path = Path(source_directory) / "manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if isinstance(manifest.get("key"), str) and manifest["key"].strip():
            return chrome_extension_id_from_key(manifest["key"])
    return chrome_extension_id_from_key(unpacked_manifest_key(source_directory))


def unpacked_copy_directory(orca_user_data: Path, source_directory: Path | str) -> Path:
    """Match `BrowserExtensionInstallStore.unpackedCopyDirectory(sourceDirectory)`."""
    resolved = os.path.abspath(str(source_directory))
    digest32 = hashlib.sha256(resolved.encode("utf-8")).hexdigest()[:32]
    return orca_user_data / "browser-extensions" / "unpacked" / digest32


def parse_manifest_summary(source_directory: Path) -> dict[str, Any]:
    manifest_path = source_directory / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"manifest.json not found in {source_directory}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("manifest_version") != 3:
        raise ValueError(f"Expected Manifest V3 in {manifest_path}, got {manifest.get('manifest_version')!r}")

    raw_perms = [p for p in manifest.get("permissions", []) if isinstance(p, str)]
    raw_hosts = [p for p in manifest.get("host_permissions", []) if isinstance(p, str)]
    permissions = [p for p in raw_perms if p != "<all_urls>" and "://" not in p]
    host_permissions = list(dict.fromkeys([p for p in raw_perms if p == "<all_urls>" or "://" in p] + raw_hosts))

    options_page: str | None = None
    if isinstance(manifest.get("options_ui"), dict) and isinstance(manifest["options_ui"].get("page"), str):
        options_page = manifest["options_ui"]["page"]
    elif isinstance(manifest.get("options_page"), str):
        options_page = manifest["options_page"]

    icon_path: str | None = None
    icons = manifest.get("icons")
    if isinstance(icons, dict):
        for size in ("128", "48", "32", "16"):
            cand = icons.get(size)
            if isinstance(cand, str) and (source_directory / cand).is_file():
                icon_path = cand
                break

    return {
        "name": str(manifest.get("name", "W0M Browser Assistant")),
        "version": str(manifest.get("version", "0.1.0")),
        "iconPath": icon_path,
        "permissions": permissions,
        "hostPermissions": host_permissions,
        "optionsPage": options_page,
    }


def stage_unpacked_directory(source_directory: Path, target_directory: Path) -> int:
    """Copy clean unpacked extension assets into Orca's unpacked cache directory."""
    if target_directory.exists():
        shutil.rmtree(target_directory)
    target_directory.parent.mkdir(parents=True, exist_ok=True)

    copied_files = 0
    for root, dirs, files in os.walk(source_directory):
        dirs[:] = [d for d in dirs if d not in EXCLUDED_UNPACKED_NAMES]
        rel_root = Path(root).relative_to(source_directory)
        dest_root = target_directory / rel_root
        dest_root.mkdir(parents=True, exist_ok=True)
        for fname in files:
            if fname in EXCLUDED_UNPACKED_NAMES or fname.endswith(".tsbuildinfo"):
                continue
            src_file = Path(root) / fname
            if src_file.is_symlink() and not src_file.exists():
                continue
            shutil.copy2(src_file, dest_root / fname)
            copied_files += 1
    return copied_files


def update_installed_json(
    orca_user_data: Path,
    source_directory: Path,
    extension_id: str,
    summary: dict[str, Any],
) -> dict[str, Any]:
    ext_root = orca_user_data / "browser-extensions"
    ext_root.mkdir(parents=True, exist_ok=True)
    installed_path = ext_root / "installed.json"
    entries: list[dict[str, Any]] = []
    if installed_path.is_file():
        try:
            loaded = json.loads(installed_path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                entries = [e for e in loaded if isinstance(e, dict)]
        except Exception:
            entries = []

    now_ms = int(time.time() * 1000)
    record: dict[str, Any] = {
        "id": extension_id,
        "name": summary["name"],
        "version": summary["version"],
        "path": os.path.abspath(str(source_directory)),
        "source": "unpacked",
        "iconPath": summary["iconPath"],
        "permissions": summary["permissions"],
        "hostPermissions": summary["hostPermissions"],
        "optionsPage": summary["optionsPage"],
        "installTime": now_ms,
    }

    updated = False
    for idx, entry in enumerate(entries):
        if entry.get("id") == extension_id:
            entries[idx] = record
            updated = True
            break
    if not updated:
        entries.append(record)

    tmp_path = installed_path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(installed_path)
    return record


def update_browser_session_meta(orca_user_data: Path, extension_id: str) -> list[str]:
    meta_path = orca_user_data / "profiles" / "local-default" / "browser-session-meta.json"
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {
        "profiles": [
            {
                "id": "default",
                "label": "Default",
                "partition": "persist:orca-browser",
                "scope": "global",
                "workspaceId": None,
                "color": "#52525b",
            }
        ],
        "defaultProfileId": "default",
        "workspaceDefaultProfileIds": {},
        "enabledExtensionIdsByProfileId": {},
        "pinnedExtensionIdsByProfileId": {},
    }
    if meta_path.is_file():
        try:
            loaded = json.loads(meta_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data.update(loaded)
        except Exception:
            pass

    profiles = data.get("profiles")
    profile_ids: list[str] = ["default"]
    if isinstance(profiles, list):
        for p in profiles:
            if isinstance(p, dict) and isinstance(p.get("id"), str) and p["id"] not in profile_ids:
                profile_ids.append(p["id"])

    enabled_map = data.get("enabledExtensionIdsByProfileId")
    if not isinstance(enabled_map, dict):
        enabled_map = {}
    pinned_map = data.get("pinnedExtensionIdsByProfileId")
    if not isinstance(pinned_map, dict):
        pinned_map = {}

    for pid in profile_ids:
        cur_enabled = [x for x in enabled_map.get(pid, []) if isinstance(x, str)]
        if extension_id not in cur_enabled:
            cur_enabled.append(extension_id)
        enabled_map[pid] = cur_enabled

        cur_pinned = [x for x in pinned_map.get(pid, []) if isinstance(x, str)]
        if extension_id not in cur_pinned:
            cur_pinned.append(extension_id)
        pinned_map[pid] = cur_pinned

    data["enabledExtensionIdsByProfileId"] = enabled_map
    data["pinnedExtensionIdsByProfileId"] = pinned_map
    meta_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return profile_ids


def enable_experimental_browser_extensions_in_db(orca_user_data: Path) -> bool:
    db_path = orca_user_data / "profiles" / "local-default" / "profile-state.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS profile_state_documents (
                domain TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                domain_version INTEGER NOT NULL DEFAULT 1,
                revision INTEGER NOT NULL DEFAULT 1,
                updated_at INTEGER NOT NULL,
                content_hash TEXT NOT NULL
            )
            """
        )
        row = conn.execute(
            "SELECT payload, domain_version, revision FROM profile_state_documents WHERE domain = 'settings'"
        ).fetchone()
        payload: dict[str, Any] = {}
        domain_version = 1
        revision = 1
        if row:
            if row[0]:
                try:
                    parsed = json.loads(row[0])
                    if isinstance(parsed, dict):
                        payload = parsed
                except Exception:
                    payload = {}
            domain_version = int(row[1] or 1)
            revision = int(row[2] or 0) + 1
        payload["experimentalBrowserExtensions"] = True
        payload_json = json.dumps(payload, separators=(",", ":"))
        content_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        now_ms = int(time.time() * 1000)
        conn.execute(
            """
            INSERT INTO profile_state_documents (domain, payload, domain_version, revision, updated_at, content_hash)
            VALUES ('settings', ?, ?, ?, ?, ?)
            ON CONFLICT(domain) DO UPDATE SET
                payload = excluded.payload,
                domain_version = excluded.domain_version,
                revision = excluded.revision,
                updated_at = excluded.updated_at,
                content_hash = excluded.content_hash
            """,
            (payload_json, domain_version, revision, now_ms, content_hash),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def inspect_status(orca_user_data: Path, source_directory: Path) -> dict[str, Any]:
    extension_id = browser_extension_id_for_unpacked_folder(source_directory)
    copy_dir = unpacked_copy_directory(orca_user_data, source_directory)
    installed_path = orca_user_data / "browser-extensions" / "installed.json"
    meta_path = orca_user_data / "profiles" / "local-default" / "browser-session-meta.json"
    db_path = orca_user_data / "profiles" / "local-default" / "profile-state.db"

    installed_entry = None
    if installed_path.is_file():
        try:
            for item in json.loads(installed_path.read_text(encoding="utf-8")):
                if isinstance(item, dict) and item.get("id") == extension_id:
                    installed_entry = item
                    break
        except Exception:
            pass

    enabled_profiles: list[str] = []
    pinned_profiles: list[str] = []
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            for pid, ids in (meta.get("enabledExtensionIdsByProfileId") or {}).items():
                if isinstance(ids, list) and extension_id in ids:
                    enabled_profiles.append(pid)
            for pid, ids in (meta.get("pinnedExtensionIdsByProfileId") or {}).items():
                if isinstance(ids, list) and extension_id in ids:
                    pinned_profiles.append(pid)
        except Exception:
            pass

    exp_enabled = False
    if db_path.is_file():
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute(
                "SELECT payload FROM profile_state_documents WHERE domain = 'settings'"
            ).fetchone()
            if row and row[0]:
                exp_enabled = bool(json.loads(row[0]).get("experimentalBrowserExtensions"))
        except Exception:
            exp_enabled = False
        finally:
            conn.close()

    dist_built = (
        (source_directory / "dist" / "background-service.js").is_file()
        or (source_directory / "dist" / "background" / "index.js").is_file()
    )
    return {
        "extension_id": extension_id,
        "source_directory": os.path.abspath(str(source_directory)),
        "unpacked_copy_directory": str(copy_dir),
        "unpacked_copy_exists": copy_dir.is_dir() and (copy_dir / "manifest.json").is_file(),
        "dist_built": dist_built,
        "installed_registered": installed_entry is not None,
        "experimental_browser_extensions_enabled": exp_enabled,
        "enabled_profiles": enabled_profiles,
        "pinned_profiles": pinned_profiles,
    }


def install_w0m_ext(
    orca_user_data: Path = DEFAULT_ORCA_USER_DATA,
    source_directory: Path | None = None,
    build_if_needed: bool = True,
) -> dict[str, Any]:
    src_dir = source_directory or resolve_default_extension_dir()
    has_dist = (
        (src_dir / "dist" / "background-service.js").is_file()
        or (src_dir / "dist" / "background" / "index.js").is_file()
    )
    if build_if_needed and not has_dist:
        subprocess.run(
            ["pnpm", "--dir", str(src_dir), "run", "build"],
            check=True,
        )

    summary = parse_manifest_summary(src_dir)
    extension_id = browser_extension_id_for_unpacked_folder(src_dir)
    copy_dir = unpacked_copy_directory(orca_user_data, src_dir)
    copied_files = stage_unpacked_directory(src_dir, copy_dir)
    record = update_installed_json(orca_user_data, src_dir, extension_id, summary)
    profiles = update_browser_session_meta(orca_user_data, extension_id)
    enable_experimental_browser_extensions_in_db(orca_user_data)

    status = inspect_status(orca_user_data, src_dir)
    status["copied_files"] = copied_files
    status["installed_record"] = record
    status["updated_profiles"] = profiles
    return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Install, stage, and enable w0m-ext MV3 extension inside Orca's Embedded Browser (T710)."
    )
    parser.add_argument("--apply", action="store_true", help="Stage unpacked bundle and enable across Orca profiles")
    parser.add_argument("--status", action="store_true", help="Inspect current Orca w0m-ext installation status")
    parser.add_argument("--build", action="store_true", help="Force rebuild of w0m-ext before staging")
    parser.add_argument("--orca-user-data", default=str(DEFAULT_ORCA_USER_DATA), help="Path to ~/.config/orca")
    parser.add_argument("--ext-dir", default="", help="Override path to w0m-ext/extension")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args(argv)

    orca_dir = Path(args.orca_user_data).expanduser().resolve()
    src_dir = Path(args.ext_dir).expanduser().resolve() if args.ext_dir else resolve_default_extension_dir()

    if args.build:
        subprocess.run(["pnpm", "--dir", str(src_dir), "run", "build"], check=True)

    if args.apply:
        result = install_w0m_ext(orca_user_data=orca_dir, source_directory=src_dir, build_if_needed=True)
    else:
        result = inspect_status(orca_user_data=orca_dir, source_directory=src_dir)

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    mode = "APPLIED" if args.apply else "STATUS"
    print(
        f"[{mode}] Orca Embedded Browser w0m-ext ({result['extension_id']}): "
        f"registered={result['installed_registered']} · "
        f"experimentalBrowserExtensions={result['experimental_browser_extensions_enabled']} · "
        f"profiles={len(result['enabled_profiles'])}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
