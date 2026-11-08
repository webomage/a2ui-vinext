#!/usr/bin/env python3
"""Unit tests for `scripts/just_overlay_sync.py`."""

from __future__ import annotations

import json
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import just_overlay_sync as jos


def test_default_overlay_config_contains_four_branches() -> None:
    cfg = jos.DEFAULT_OVERLAY_CONFIG
    assert cfg["upstreamRepo"] == "casey/just"
    assert cfg["forkRepo"] == "webomage/just"
    assert cfg["overlayBranch"] == "beta"
    assert cfg["baseTag"] == "1.59.0"
    branches = [b["branch"] for b in cfg["branches"]]
    assert branches == [
        "fix/fmt-preserve-recipe-header-comment",
        "feat/multiline-doc-comments",
        "feat/list-fallback-recipes",
        "feat/wildcard-imports",
    ]


def test_write_and_load_overlay_config_roundtrip(tmp_path: Path) -> None:
    fork_dir = tmp_path / "just"
    written = jos.write_overlay_config(fork_dir)
    assert written.is_file()
    loaded = jos.load_overlay_config(fork_dir)
    assert loaded["baseTag"] == "1.59.0"
    assert len(loaded["branches"]) == 4


def test_collect_all_overlays_status_reads_custom_fork_entries(tmp_path: Path) -> None:
    policy_path = tmp_path / "tools-policy.json"
    policy_path.write_text(
        json.dumps(
            {
                "tools": {
                    "just": {
                        "min": "1.40.0",
                        "known_good": "1.59.0",
                        "custom_fork": "webomage/just@beta",
                        "linux_source": "cargo-overlay (~/.local/bin/just + just just-apply)",
                        "macos_source": "cargo-overlay (~/.local/bin/just + just just-apply)",
                    },
                    "orca": {
                        "min": "1.1.0",
                        "known_good": "1.1.7",
                        "custom_fork": "webomage/orca@beta",
                        "linux_source": "gh-release (webomage/orca)",
                        "macos_source": "gh-release (webomage/orca)",
                    },
                    "jq": {
                        "min": "1.6",
                        "known_good": "1.8.2",
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    rows = jos.collect_all_overlays_status(tools_policy_path=policy_path, estate_root=tmp_path)
    tools = [r["tool"] for r in rows]
    assert tools == ["just", "orca"]
    assert rows[0]["customFork"] == "webomage/just@beta"
    assert rows[0]["knownGood"] == "1.59.0"


def test_build_tablinux_wasm_package_creates_tarball_and_updates_index(tmp_path: Path) -> None:
    linuxontab_dir = tmp_path / "w0m-pr" / "linuxontab"
    (linuxontab_dir / "packages").mkdir(parents=True, exist_ok=True)
    (linuxontab_dir / "packages" / "index.json").write_text(
        json.dumps({"version": 1, "generated": "2026-01-01T00:00:00Z", "packages": {}}),
        encoding="utf-8",
    )

    result = jos.build_tablinux_just_wasm_package(
        linuxontab_dir=linuxontab_dir,
        version="1.59.0-w0m.1",
    )
    tar_path = Path(result["tarball"])
    assert tar_path.is_file()
    assert result["size"] > 0
    assert len(result["sha256"]) == 64

    with tarfile.open(tar_path, "r:gz") as tf:
        names = set(tf.getnames())
    assert "pkg-just/usr/local/bin/just" in names
    assert "pkg-just/usr/local/lib/just/just.wasm" in names

    idx = json.loads((linuxontab_dir / "packages" / "index.json").read_text(encoding="utf-8"))
    assert "just" in idx["packages"]
    assert idx["packages"]["just"]["version"] == "1.59.0-w0m.1"
    assert idx["packages"]["just"]["url"].endswith("just-1.59.0-w0m.1.tar.gz")
