#!/usr/bin/env python3
"""test_dod_check.py — Bidirectional unit & non-vacuity probes for `scripts/dod_check.py` (T616 AC2).

Verifies:
  1. Empty or nonexistent ticket directory fails closed with `exit 2` (`UNMEASURABLE`, AgDR-0025),
     never producing a vacuous `0current / 0missing` pass (the T411 `.tasks/` regression).
  2. Single-ticket `--ticket` mode catches `[MISSING]` and `[SHARED]` boilerplate (`exit 1`) and
     passes `[OK]` (`exit 0`) on a distinct domain-grounded Definition of Done.
  3. Unreadable baseline JSON fails closed with `exit 2`.

Run: `python3 scripts/tests/test_dod_check.py`
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "dod_check.py"

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        failures.append(f"{label} — {detail}")


def _init_git_tickets_repo(base: Path) -> Path:
    tdir = base / ".tasks"
    tdir.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=str(base), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(base), check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(base), check=True)

    (tdir / "T1.md").write_text(
        """---
id: T1
status: done
---
# T1
## Acceptance criteria
- [x] AC1 — Distinct domain criterion one

## Definition of Done
Distinct domain verification proof for T1 with concrete schema and endpoint assertions.
""",
        encoding="utf-8",
    )
    (tdir / "T2.md").write_text(
        """---
id: T2
status: queued
---
# T2
## Acceptance criteria
- [ ] AC1 — Missing DoD criterion
""",
        encoding="utf-8",
    )
    shared_dod = (
        "This shared boilerplate Definition of Done text is longer than forty characters and duplicated verbatim."
    )
    for idx in (3, 4):
        (tdir / f"T{idx}.md").write_text(
            f"""---
id: T{idx}
status: queued
---
# T{idx}
## Acceptance criteria
- [ ] AC1 — Shared template test {idx}

## Definition of Done
{shared_dod}
""",
            encoding="utf-8",
        )
    subprocess.run(["git", "add", "."], cwd=str(base), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "feat: seed T1..T4"], cwd=str(base), check=True)
    return tdir


def run_dod(args: list[str], env_extra: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, **env_extra}
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def main() -> int:
    print("▶ test_dod_check.py — DoD Gate Non-Vacuity & Red/Green Probes\n")

    with tempfile.TemporaryDirectory() as tmp:
        empty_dir = Path(tmp) / "missing_dir"
        r_empty = run_dod([], {"W0M_DOD_TICKETS_DIR": str(empty_dir)})
        check(
            "Missing tickets dir fails closed with exit 2 (never vacuous green)",
            r_empty.returncode == 2 and "UNMEASURABLE" in r_empty.stdout,
            f"rc={r_empty.returncode}, out={r_empty.stdout!r}",
        )

        repo_base = Path(tmp) / "repo"
        tdir = _init_git_tickets_repo(repo_base)

        r_ok = run_dod(["--ticket", "T1"], {"W0M_DOD_TICKETS_DIR": str(tdir)})
        check(
            "--ticket T1 with distinct DoD exits 0 ([OK])",
            r_ok.returncode == 0 and "[OK] T1" in r_ok.stdout,
            f"rc={r_ok.returncode}, out={r_ok.stdout!r}",
        )

        r_missing = run_dod(["--ticket", "T2"], {"W0M_DOD_TICKETS_DIR": str(tdir)})
        check(
            "--ticket T2 without DoD exits 1 ([MISSING])",
            r_missing.returncode == 1 and "[MISSING] T2" in r_missing.stdout,
            f"rc={r_missing.returncode}, out={r_missing.stdout!r}",
        )

        r_shared = run_dod(["--ticket", "T3"], {"W0M_DOD_TICKETS_DIR": str(tdir)})
        check(
            "--ticket T3 with duplicated template DoD exits 1 ([SHARED])",
            r_shared.returncode == 1 and "[SHARED]  T3" in r_shared.stdout,
            f"rc={r_shared.returncode}, out={r_shared.stdout!r}",
        )

        bad_baseline = Path(tmp) / "nonexistent_baseline.json"
        r_bad_base = run_dod(
            [],
            {"W0M_DOD_TICKETS_DIR": str(tdir), "W0M_DOD_BASELINE_FILE": str(bad_baseline)},
        )
        check(
            "Unreadable baseline JSON fails closed with exit 2",
            r_bad_base.returncode == 2 and "UNMEASURABLE" in r_bad_base.stdout,
            f"rc={r_bad_base.returncode}",
        )

    print()
    if failures:
        print(f"FAILED: {len(failures)} assertion(s) failed:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("ALL DOD PROBES PASSED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
