#!/usr/bin/env python3
"""Offline red/green unit tests for T234 (`ai_memory_pin_check.py`).

Verifies all three independent drift axes plus fail-closed exit-2 probes:
1. Live tree (`wom7web/project/ai-memory-pin.json` against `_ext/ai-memory`) passes (`0`).
2. Validated temp git checkout + binary sha256 + `--version` output passes (`0`).
3. Commit mismatch (`git HEAD` differs from `pin.commit`) fails (`1`).
4. Binary SHA-256 mismatch (`target/release/ai-memory` bytes modified) fails (`1`).
5. Reported version mismatch (`--version` output differs from `pin.reported_version`) fails (`1`).
6. Missing pin file or missing checkout `.git` exits `2` (unknown/unmeasured, never silently clean).
"""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import ai_memory_pin_check as amp


def _init_fixture_repo(base: Path, *, reported_version: str = "1.29.0") -> tuple[Path, Path, dict[str, object]]:
    """Create a temporary estate with a git-initialized `_ext/ai-memory` checkout and stub binary."""
    estate = base / "estate"
    repo = estate / "_ext" / "ai-memory"
    repo.mkdir(parents=True)

    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@w0m.local"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "w0m test"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "commit.gpgsign", "false"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "tag.gpgSign", "false"], check=True)
    (repo / "README.md").write_text("# ai-memory stub\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "init"], check=True)
    subprocess.run(["git", "-C", str(repo), "tag", "-a", "v1.29.0", "-m", "v1.29.0"], check=True)

    commit = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    bin_dir = repo / "target" / "release"
    bin_dir.mkdir(parents=True)
    binary = bin_dir / "ai-memory"
    binary.write_text(f"#!/usr/bin/env sh\necho 'ai-memory {reported_version}'\n", encoding="utf-8")
    binary.chmod(0o755)
    sha256 = hashlib.sha256(binary.read_bytes()).hexdigest()

    pin_data: dict[str, object] = {
        "repo": "casualuser/ai-memory",
        "upstream": "akitaonrails/ai-memory",
        "checkout": "_ext/ai-memory",
        "commit": commit,
        "describe": "v1.29.0",
        "freeze_tag": "w0m-validated-2026-08-19",
        "reported_version": "1.29.0",
        "binary_sha256": sha256,
        "validated_on": "2026-08-19",
        "auto_update": False,
        "tag": "v1.29.0",
    }
    pin_path = base / "ai-memory-pin.json"
    pin_path.write_text(json.dumps(pin_data, indent=2), encoding="utf-8")
    return estate, pin_path, pin_data


class TestAiMemoryPinCheck(unittest.TestCase):
    def test_live_pin_is_green(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = amp.main([])
        self.assertEqual(rc, 0, buf.getvalue())
        self.assertIn("ai-memory", buf.getvalue())

    def test_green_when_commit_sha256_and_version_all_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            estate, pin_path, _ = _init_fixture_repo(Path(tmp))
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = amp.main(["--pin", str(pin_path), "--estate", str(estate)])
            self.assertEqual(rc, 0, buf.getvalue())
            self.assertIn("matches the validated build", buf.getvalue())

    def test_red_on_commit_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            estate, pin_path, pin_data = _init_fixture_repo(Path(tmp))
            pin_data["commit"] = "0000000000000000000000000000000000000000"
            pin_path.write_text(json.dumps(pin_data), encoding="utf-8")

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = amp.main(["--pin", str(pin_path), "--estate", str(estate)])
            self.assertEqual(rc, 1, buf.getvalue())
            self.assertIn("commit drift", buf.getvalue())

    def test_red_on_binary_sha256_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            estate, pin_path, _ = _init_fixture_repo(Path(tmp))
            binary = estate / "_ext" / "ai-memory" / "target" / "release" / "ai-memory"
            binary.write_text("#!/usr/bin/env sh\necho 'ai-memory 1.29.0'\n# tampered\n", encoding="utf-8")
            binary.chmod(0o755)

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = amp.main(["--pin", str(pin_path), "--estate", str(estate)])
            self.assertEqual(rc, 1, buf.getvalue())
            self.assertIn("binary drift", buf.getvalue())

    def test_red_on_reported_version_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            estate, pin_path, _ = _init_fixture_repo(Path(tmp), reported_version="1.28.1")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = amp.main(["--pin", str(pin_path), "--estate", str(estate)])
            self.assertEqual(rc, 1, buf.getvalue())
            self.assertIn("version drift", buf.getvalue())

    def test_exit_2_when_pin_file_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing_pin = Path(tmp) / "nonexistent-pin.json"
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = amp.main(["--pin", str(missing_pin), "--estate", str(tmp)])
            self.assertEqual(rc, 2, buf.getvalue())
            self.assertIn("no pin file", buf.getvalue())

    def test_exit_2_when_checkout_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            estate, pin_path, _ = _init_fixture_repo(Path(tmp))
            empty_estate = Path(tmp) / "empty-estate"
            empty_estate.mkdir()
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = amp.main(["--pin", str(pin_path), "--estate", str(empty_estate)])
            self.assertEqual(rc, 2, buf.getvalue())
            self.assertIn("checkout missing", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
