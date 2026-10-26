#!/usr/bin/env python3
"""T110 AC4 — prove the ticket-trace gate can FAIL.

AC4's whole claim is that *instruction is not enforcement*. A gate asserting that, which has only
ever been observed green, would be making exactly the mistake it names. So every case runs against
a throwaway git repo built per-probe via `W0M_TRACE_ROOT` — proving it red on the real estate would
mean committing the ad-hoc work the gate exists to catch.

The cases are chosen from a MEASUREMENT, not from taste. Over 455 T-id commits since 2026-07-20,
31% moved no tracking surface, but the great majority of those were `chore`/`docs` — STATE.md
refreshes and ticket-mirror syncs. That is why `chore` is out of scope and is asserted here: a gate
that fires on its own bookkeeping is one people learn to route around.

Run: `just sdlc-trace-test`
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "wom7web"
SCRIPT = ROOT / "scripts" / "sdlc_trace.py"

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'✅' if ok else '❌'} {label}")
    if not ok:
        failures.append(f"{label}{(' — ' + detail) if detail else ''}")


if not SCRIPT.is_file():
    print("❌ sdlc_trace.py missing — the suite cannot prove anything")
    sys.exit(2)


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def fixture(commits: list[tuple[str, dict[str, str]]]) -> Path:
    """A repo with a baseline commit, then one commit per (subject, {path: content})."""
    repo = Path(tempfile.mkdtemp(prefix="t110-ac4-"))
    (repo / "project" / "tickets").mkdir(parents=True)
    (repo / "TASKS.md").write_text("| ticket | prio |\n")
    (repo / "src.py").write_text("x = 0\n")
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "t@t")
    git(repo, "config", "user.name", "t")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "chore: baseline")
    for subj, files in commits:
        for rel, body in files.items():
            p = repo / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(body)
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", subj)
    return repo


def run(repo: Path, rng: str = "HEAD~1..HEAD") -> subprocess.CompletedProcess:
    env = {**os.environ, "W0M_TRACE_ROOT": str(repo)}
    return subprocess.run([sys.executable, str(SCRIPT), "--range", rng],
                          capture_output=True, text=True, env=env)


def out(r: subprocess.CompletedProcess) -> str:
    return r.stdout + r.stderr


print("\n── the control: a feat that DOES move its ticket must pass ──")

repo = fixture([("feat(T42): add the thing",
                 {"src.py": "x = 1\n", "project/tickets/T42.md": "# T42\nprogress\n"})])
r = run(repo)
check("a feat that moves its ticket passes", r.returncode == 0, out(r)[-240:])
check("...and the check reports its scope, not just a verdict",
      "commit(s) in" in out(r) and "naming a ticket" in out(r), out(r)[-240:])

print("\n── 🔴 the RED case AC4 names: behaviour changed, the record did not ──")

repo = fixture([("feat(T42): add the thing", {"src.py": "x = 1\n"})])
r = run(repo)
check("a feat naming a ticket that moves NOTHING fails", r.returncode != 0, f"rc={r.returncode}")
check("...and names the commit and the ticket",
      "T42" in out(r) and "without moving its record" in out(r), out(r)[-300:])
check("...and tells the author how to fix it, not just that they are wrong",
      "Fix:" in out(r), out(r)[-300:])

repo = fixture([("fix(T7): correct the thing", {"src.py": "x = 2\n"})])
r = run(repo)
check("`fix` is in scope too, not just `feat`", r.returncode != 0, f"rc={r.returncode}")

print("\n── the board is an acceptable record, not only the ticket file ──")

repo = fixture([("feat(T42): add the thing", {"src.py": "x = 1\n", "TASKS.md": "| T42 | P1 |\n"})])
r = run(repo)
check("moving TASKS.md alone satisfies the rule", r.returncode == 0, out(r)[-240:])

print("\n── the check must not cry wolf ──")

# Measured: chore/docs dominated the raw 31%. A gate that fires on STATE.md refreshes and mirror
# syncs is one people learn to route around, so their exclusion is asserted rather than assumed.
repo = fixture([("chore: refresh the STATE.md block after T42", {"src.py": "x = 1\n"})])
r = run(repo)
check("a `chore` naming a ticket is OUT of scope", r.returncode == 0, out(r)[-240:])

repo = fixture([("docs(T42): session handoff", {"src.py": "x = 1\n"})])
r = run(repo)
check("a `docs` commit naming a ticket is OUT of scope", r.returncode == 0, out(r)[-240:])

repo = fixture([("feat: add a thing with no ticket", {"src.py": "x = 1\n"})])
r = run(repo)
check("a feat naming NO ticket is out of scope", r.returncode == 0, out(r)[-240:])

print("\n── push-level, not same-commit: split work passes but is ADVISED ──")

repo = fixture([("feat(T42): add the thing", {"src.py": "x = 1\n"}),
                ("chore(T42): update the ticket", {"project/tickets/T42.md": "# T42\ndone\n"})])
r = run(repo, "HEAD~2..HEAD")
check("ticket moved in a LATER commit of the same push passes", r.returncode == 0, out(r)[-240:])
check("...but is reported as advice, since CLAUDE.md asks for the same commit",
      "same commit" in out(r), out(r)[-300:])

print("\n── the empty set must SAY so, not pass silently ──")

repo = fixture([("chore: nothing to see", {"src.py": "x = 9\n"})])
r = run(repo, "HEAD..HEAD")
check("an empty range exits 0 but says it examined nothing", r.returncode == 0, f"rc={r.returncode}")
check("...and refuses to imply the rule was verified",
      "NOT evidence" in out(r), out(r)[-300:])

print()
if failures:
    print(f"❌ sdlc-trace: {len(failures)} check(s) failed")
    for f in failures:
        print(f"   · {f}")
    sys.exit(1)
print("✅ sdlc-trace: all checks passed")
