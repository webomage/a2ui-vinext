#!/usr/bin/env python3
"""T33 AC3 — prove the spec-authoring gate can actually FAIL.

T33 AC1 shipped `SPEC-AUTHORING-STANDARD.md` in July and nothing ever checked it. The result,
measured 2026-08-02: **0 of 110** requirements in active changes conform. That is what an
unenforced standard costs, and it is exactly why this gate must be shown failing before it is
trusted — a ratchet that cannot fire is a rubber stamp with a progress bar.

Driven against a FIXTURE estate via `W0M_SPEC_ROOT`, because planting a deliberately malformed
requirement in a real spec would mean committing the defect the gate exists to catch.

Run: `just spec-standard-test`
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "wom7web"
SCRIPT = ROOT / "scripts" / "spec_standard_check.py"

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'✅' if ok else '❌'} {label}")
    if not ok:
        failures.append(f"{label}{(' — ' + detail) if detail else ''}")


if not SCRIPT.is_file():
    print("❌ spec_standard_check.py missing — the suite cannot prove anything")
    sys.exit(2)

CONFORMING = """## Purpose
### Requirement: Fully Formed
The system SHALL do the thing.

**Feature:** Context, who it serves, non-goals.

#### Scenario: happy path
- **WHEN** a thing **THEN** another thing

**Acceptance criteria** (binary, testable):
- [ ] observable condition

**Verify with** `test-driven-development` · `verify`.
"""

BARE = """## Purpose
### Requirement: Bare
The system SHALL do the thing.

#### Scenario: happy path
- **WHEN** a thing **THEN** another thing
"""


def estate(files: dict[str, str]) -> Path:
    root = Path(tempfile.mkdtemp(prefix="t33-ac3-"))
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    return root


def run(root: Path, *args) -> subprocess.CompletedProcess:
    env = {**os.environ, "W0M_SPEC_ROOT": str(root)}
    return subprocess.run([sys.executable, str(SCRIPT), *args],
                          capture_output=True, text=True, env=env)


def baseline(root: Path, n: int) -> None:
    (root.parent / "spec-standard-baseline.json").write_text(json.dumps({"non_conforming": n}))


print("\n── the control: a fully formed requirement PASSES ──")

root = estate({"chg/specs/cap/spec.md": CONFORMING})
baseline(root, 0)
r = run(root)
out = r.stdout + r.stderr
check("a conforming requirement passes", r.returncode == 0, out[-200:])
check("...and is counted as conforming", "conforming: 1/1" in out, out[-200:])

print("\n── 🔴 the RED case: a requirement missing the block must FAIL the ratchet ──")

root = estate({"chg/specs/cap/spec.md": CONFORMING, "chg2/specs/cap/spec.md": BARE})
baseline(root, 0)
r = run(root)
out = r.stdout + r.stderr
check("a bare requirement pushes the count above the ceiling", r.returncode == 1, f"rc={r.returncode}")
check("...and the failure names the rise", "rose 0 → 1" in out, out[-260:])

r = run(root, "--verbose")
out = r.stdout + r.stderr
check("...and --verbose names the missing parts",
      "Feature" in out and "Acceptance criteria" in out and "Verify with" in out, out[-300:])

print("\n── the ratchet must not fire on unchanged debt, and must notice improvement ──")

baseline(root, 1)
r = run(root)
check("holding at the ceiling passes", r.returncode == 0, (r.stdout + r.stderr)[-200:])

baseline(root, 5)
r = run(root)
out = r.stdout + r.stderr
check("a DROP below the ceiling passes", r.returncode == 0, f"rc={r.returncode}")
check("...and prompts to re-baseline rather than silently drifting",
      "improved 5 → 1" in out, out[-220:])

print("\n── an empty corpus must FAIL, not report a clean estate ──")

r = run(estate({}))
out = r.stdout + r.stderr
check("no spec files at all is a FAILURE", r.returncode != 0, f"rc={r.returncode}")
check("...and it says the corpus is empty rather than passing",
      "empty" in out.lower() or "no requirements" in out.lower(), out[-200:])

print("\n── archived changes are out of scope ──")

root = estate({"chg/specs/cap/spec.md": CONFORMING, "archive/old/specs/cap/spec.md": BARE})
baseline(root, 0)
r = run(root)
check("a bare requirement under archive/ does NOT fail the gate", r.returncode == 0,
      (r.stdout + r.stderr)[-220:])

print()
if failures:
    print(f"❌ {len(failures)} failure(s):")
    for f in failures:
        print(f"   · {f}")
    sys.exit(1)
print("✅ spec-standard: all checks passed")
