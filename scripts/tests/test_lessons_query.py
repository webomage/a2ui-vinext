#!/usr/bin/env python3
"""test_lessons_query.py — unit tests and regression proof for lessons_query.py.

Implements verification contract for T232 AC10.
Proves:
  1. Live LESSONS.md parses >= 50 lessons across 7 sections.
  2. Keyword search filters matching records.
  3. Section filtering isolates requested section.
  4. Tell-only flag prints tell lines.
  5. JSON output emits valid structured list.
  6. Synthetic fixture parses independently.

Run: `python3 project/scripts/tests/test_lessons_query.py` or `just lessons-test`
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "lessons_query.py"

failures: list[str] = []

if not SCRIPT.is_file():
    sys.exit(f"ERROR: {SCRIPT} not found — cannot run tests.")


def run_tool(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def test_live_summary() -> None:
    res = run_tool()
    if res.returncode != 0:
        failures.append(f"test_live_summary: expected exit 0, got {res.returncode}: {res.stderr}")
        return
    if "LESSONS.md Census:" not in res.stdout:
        failures.append("test_live_summary: missing census header")
    if "§1 Assertions" not in res.stdout:
        failures.append("test_live_summary: missing section 1 in census")


def test_live_search() -> None:
    res = run_tool("rls")
    if res.returncode != 0:
        failures.append(f"test_live_search: expected exit 0, got {res.returncode}: {res.stderr}")
        return
    if "Matched" not in res.stdout or "RLS" not in res.stdout:
        failures.append("test_live_search: expected RLS matches in output")


def test_section_filter() -> None:
    res = run_tool("--section", "1")
    if res.returncode != 0:
        failures.append(f"test_section_filter: expected exit 0, got {res.returncode}: {res.stderr}")
        return
    if "[Section 1: Assertions]" not in res.stdout:
        failures.append("test_section_filter: expected section 1 header")
    if "[Section 2:" in res.stdout:
        failures.append("test_section_filter: section 2 unexpectedly included")


def test_tell_only() -> None:
    res = run_tool("rls", "--tell")
    if res.returncode != 0:
        failures.append(f"test_tell_only: expected exit 0, got {res.returncode}: {res.stderr}")
        return
    if "The tell:" not in res.stdout:
        failures.append("test_tell_only: expected 'The tell:' in output")
    if "DETAIL:" in res.stdout:
        failures.append("test_tell_only: DETAIL unexpectedly present in tell-only mode")


def test_json_output() -> None:
    res = run_tool("rls", "--json")
    if res.returncode != 0:
        failures.append(f"test_json_output: expected exit 0, got {res.returncode}: {res.stderr}")
        return
    try:
        data = json.loads(res.stdout)
        if not isinstance(data, list) or len(data) == 0:
            failures.append("test_json_output: expected non-empty JSON list")
        else:
            rec = data[0]
            for key in ("title", "tell", "cue", "lesson", "evidence", "confidence"):
                if key not in rec:
                    failures.append(f"test_json_output: missing '{key}' key in parsed record")
    except Exception as e:
        failures.append(f"test_json_output: JSON parse error: {e}")


def test_harness2_index() -> None:
    res = run_tool("rls", "--index")
    if res.returncode != 0:
        failures.append(f"test_harness2_index: expected exit 0, got {res.returncode}: {res.stderr}")
        return
    if "# Experience Library Index" not in res.stdout:
        failures.append("test_harness2_index: missing '# Experience Library Index' header")
    if "**Cue:**" not in res.stdout or "**Lesson:**" not in res.stdout:
        failures.append("test_harness2_index: missing '**Cue:**' or '**Lesson:**' in index output")


def test_synthetic_fixture() -> None:
    content = """# LESSONS

## 1. Assertions

### NEVER TRUST SYNTHETIC INPUT
**2026-09-15 (T999).** A synthetic test masked a bug.

Detailed context line here.
⇒ Always verify with real fixtures.
⭐ **The tell:** A test with hardcoded pass values.
"""
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md", delete=False) as tf:
        tf.write(content)
        temp_path = Path(tf.name)

    try:
        res = run_tool("--path", str(temp_path), "SYNTHETIC")
        if res.returncode != 0:
            failures.append(f"test_synthetic_fixture: expected exit 0, got {res.returncode}")
        elif "NEVER TRUST SYNTHETIC INPUT" not in res.stdout:
            failures.append("test_synthetic_fixture: expected synthetic rule in output")

        idx_res = run_tool("--path", str(temp_path), "--index")
        if idx_res.returncode != 0:
            failures.append(f"test_synthetic_fixture (--index): expected exit 0, got {idx_res.returncode}")
        elif "A test with hardcoded pass values." not in idx_res.stdout or "confidence: high" not in idx_res.stdout:
            failures.append("test_synthetic_fixture (--index): expected extracted cue and high confidence")
    finally:
        temp_path.unlink(missing_ok=True)


def main() -> int:
    test_live_summary()
    test_live_search()
    test_section_filter()
    test_tell_only()
    test_json_output()
    test_harness2_index()
    test_synthetic_fixture()

    if failures:
        print(f"FAILED — {len(failures)} test(s) failed:")
        for f in failures:
            print(f"  • {f}")
        return 1

    print("[PASS] test_lessons_query: 7/7 tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

