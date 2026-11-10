#!/usr/bin/env python3
"""Unit tests for `scripts/orca_ext_install.py` (T710)."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import orca_ext_install as oei  # noqa: E402


def test_deterministic_chrome_extension_id_matches_orca_vitest_vector() -> None:
    """Matches `browser-extension-load-directory.test.ts` line 50 vector (`orca-unpacked:/some/folder`)."""
    key = oei.unpacked_manifest_key("/some/folder")
    assert oei.chrome_extension_id_from_key(key) == "facfjoldjaombbaheilnbchaiimdhcbk"


def test_install_w0m_ext_stages_clean_bundle_and_enables_profiles(tmp_path: Path) -> None:
    ext_dir = tmp_path / "w0m-ext" / "extension"
    (ext_dir / "dist" / "background").mkdir(parents=True)
    (ext_dir / "dist" / "content").mkdir(parents=True)
    (ext_dir / "node_modules" / "fake-pkg").mkdir(parents=True)
    (ext_dir / ".git").mkdir(parents=True)

    (ext_dir / "manifest.json").write_text(
        json.dumps(
            {
                "manifest_version": 3,
                "name": "W0M Browser Assistant",
                "version": "0.1.0",
                "permissions": ["activeTab", "scripting", "storage"],
                "host_permissions": ["<all_urls>"],
                "background": {"service_worker": "dist/background/index.js", "type": "module"},
                "options_ui": {"page": "src/options/options.html", "open_in_tab": True},
            }
        ),
        encoding="utf-8",
    )
    (ext_dir / "dist" / "background" / "index.js").write_text("self.ready = true;\n", encoding="utf-8")
    (ext_dir / "dist" / "content" / "index.js").write_text("console.log('w0m');\n", encoding="utf-8")
    (ext_dir / "node_modules" / "fake-pkg" / "index.js").write_text("module.exports = {};\n", encoding="utf-8")
    (ext_dir / ".git" / "HEAD").write_text("ref: refs/heads/beta\n", encoding="utf-8")

    orca_data = tmp_path / "orca-config"
    profiles_dir = orca_data / "profiles" / "local-default"
    profiles_dir.mkdir(parents=True)
    (profiles_dir / "browser-session-meta.json").write_text(
        json.dumps(
            {
                "profiles": [
                    {"id": "default", "label": "Default", "partition": "persist:orca-browser"},
                    {"id": "w0m-profile", "label": "Workspace: w0m", "partition": "persist:orca-w0m"},
                ],
                "defaultProfileId": "default",
                "enabledExtensionIdsByProfileId": {},
                "pinnedExtensionIdsByProfileId": {},
            }
        ),
        encoding="utf-8",
    )

    result = oei.install_w0m_ext(orca_user_data=orca_data, source_directory=ext_dir, build_if_needed=False)
    assert result["installed_registered"] is True
    assert result["experimental_browser_extensions_enabled"] is True
    assert result["unpacked_copy_exists"] is True
    assert set(result["enabled_profiles"]) == {"default", "w0m-profile"}
    assert set(result["pinned_profiles"]) == {"default", "w0m-profile"}

    copy_dir = Path(result["unpacked_copy_directory"])
    assert (copy_dir / "manifest.json").is_file()
    assert (copy_dir / "dist" / "background" / "index.js").is_file()
    assert not (copy_dir / "node_modules").exists()
    assert not (copy_dir / ".git").exists()
