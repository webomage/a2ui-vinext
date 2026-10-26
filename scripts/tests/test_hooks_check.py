#!/usr/bin/env python3
"""T150 AC3b — prove the forge allowlist actually FIRES.

AC3b inverted the old rule. "No forge call in any hook" was trivially checkable; the rule now is
"exactly ONE sanctioned forge call, in wom7web/.husky/pre-push, and nowhere else". The AC closes
with: *"🔴 Prove it RED by planting a `gh` call in a second hook."*

That was never done. `hooks_check.py` implemented the allowlist and shipped green, and green is all
anyone ever saw — so a guardrail whose whole value is catching a second call site had never been
shown to catch one. Worse, it is one of the suites in `just test`, contributing a check that could
only ever pass.

Planting a `gh` call in a real hook would mean committing the violation the check exists to
prevent, so the estate root is overridden (`W0M_HOOKS_ROOT`) and the checks run against a FIXTURE
estate built per-case.

Run: `just hooks-check-test`
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "wom7web"
SCRIPT = ROOT / "scripts" / "hooks_check.py"

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'✅' if ok else '❌'} {label}")
    if not ok:
        failures.append(f"{label}{(' — ' + detail) if detail else ''}")


if not SCRIPT.is_file():
    print("❌ hooks_check.py missing — the suite cannot prove anything")
    sys.exit(2)


def estate(hooks: dict[str, str]) -> Path:
    """Build a fixture estate: {'wom7web/.husky/pre-push': 'body', ...}."""
    root = Path(tempfile.mkdtemp(prefix="t150-ac3b-"))
    for rel, body in hooks.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    return root


def run(root: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, "W0M_HOOKS_ROOT": str(root)}
    return subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True, env=env)


SANCTIONED = "wom7web/.husky/pre-push"
GH_CALL = "#!/bin/sh\ngh issue list --limit 1\n"
CLEAN = "#!/bin/sh\njust typecheck\n"

print("\n── the sanctioned call site is allowed ──")

r = run(estate({SANCTIONED: GH_CALL}))
out = r.stdout + r.stderr
check("a `gh` call in the ALLOWLISTED hook is not a finding",
      "forge-specific call" not in out, out[-200:])

print("\n── 🔴 the RED case AC3b demanded and nobody ran ──")

r = run(estate({SANCTIONED: GH_CALL, "wom7api/.husky/pre-commit": GH_CALL}))
out = r.stdout + r.stderr
check("a `gh` call in a SECOND hook is reported", "forge-specific call" in out, out[-240:])
check("...and the offending file is named", "wom7api/.husky/pre-commit" in out, out[-240:])
check("...and it FAILS the check", r.returncode != 0, f"rc={r.returncode}")

print("\n── the check must not cry wolf ──")

r = run(estate({SANCTIONED: GH_CALL,
                "wom7api/.husky/pre-commit": "#!/bin/sh\n# gh issue list — documenting the rule\njust lint\n"}))
out = r.stdout + r.stderr
check("a `gh` call inside a COMMENT is not a finding", "forge-specific call" not in out, out[-200:])

r = run(estate({SANCTIONED: GH_CALL, "wom7api/.husky/pre-commit": CLEAN}))
out = r.stdout + r.stderr
check("a hook with no forge call is not a finding", "forge-specific call" not in out, out[-200:])

print("\n── an empty corpus must fail, not report a clean estate ──")

r = run(estate({}))
out = r.stdout + r.stderr
check("no hooks at all is a FAILURE", r.returncode != 0, f"rc={r.returncode} {out[-160:]}")

print("\n── 🔴 T135 AC4: pre-push coverage must be a DECISION, not an accident ──")

# These drive the POLICY rather than the hook files, so they need the second fixture hook
# (W0M_STACKS_POLICY). Proving them against the real policy would mean committing the very false
# claims they exist to catch — a stack asserting a pre-push gate it does not have.
REAL_POLICY = ROOT / "project" / "policies" / "stacks-policy.json"


def with_policy(mutate) -> subprocess.CompletedProcess:
    """Run hooks-check against a mutated COPY of the real policy, on the real hook corpus."""
    policy = json.loads(REAL_POLICY.read_text())
    mutate(policy)
    tmp = Path(tempfile.mkdtemp(prefix="t135-ac4-")) / "stacks-policy.json"
    tmp.write_text(json.dumps(policy))
    env = {**os.environ, "W0M_STACKS_POLICY": str(tmp)}
    return subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True, env=env)


r = with_policy(lambda p: None)
out = r.stdout + r.stderr
check("the control: the unmodified policy still passes", r.returncode == 0, out[-240:])
check("...and the push-gate decision is REPORTED, not silent", "push-gate " in out, out[-240:])

r = with_policy(lambda p: p["stacks"]["worker"].pop("push_gate", None))
out = r.stdout + r.stderr
check("a stack with NO push_gate declaration fails", r.returncode != 0, f"rc={r.returncode}")
check("...and says the coverage must be a recorded decision",
      "not an accident" in out, out[-240:])

# The load-bearing one: `local` is a falsifiable CLAIM, not a preference.
r = with_policy(lambda p: p["stacks"]["worker"].update(
    {"push_gate": {"mode": "local", "reason": "x" * 30}}))
out = r.stdout + r.stderr
check("`mode: local` with NO pre-push role fails — a claimed gate that does not exist",
      r.returncode != 0, f"rc={r.returncode}")
check("...and names the stack and the missing phase",
      "worker" in out and "pre-push" in out, out[-240:])

r = with_policy(lambda p: p["stacks"]["worker"].update(
    {"push_gate": {"mode": "central", "covered_by": "web"}}))
out = r.stdout + r.stderr
check("`central` with no reason fails — an ungated repo must be arguable, not silent",
      r.returncode != 0, f"rc={r.returncode}")

r = with_policy(lambda p: p["stacks"]["worker"].update(
    {"push_gate": {"mode": "central", "covered_by": "sec", "reason": "y" * 30}}))
out = r.stdout + r.stderr
check("`central` pointing at a stack with no pre-push role fails (the coverage does not exist)",
      r.returncode != 0, f"rc={r.returncode}")

r = with_policy(lambda p: p["stacks"]["worker"].update(
    {"push_gate": {"mode": "central", "covered_by": "nope", "reason": "z" * 30}}))
check("`covered_by` naming an undeclared stack fails", r.returncode != 0, f"rc={r.returncode}")

print("\n── 🔴 T527 AC3: hook scope paths must exist in the repo whose range is read ──")

STALE_SCOPE_HOOK = (
    "#!/bin/sh\n"
    "_pushed_files=$(git diff --name-only origin/beta HEAD)\n"
    'if echo "$_pushed_files" | grep -qE "^(STATE\\.md|TASKS\\.md|project/tickets/|\\.tasks/|ROADMAP\\.md)"; then\n'
    "  just state-check\n"
    "fi\n"
)
r = run(estate({SANCTIONED: STALE_SCOPE_HOOK}))
out = r.stdout + r.stderr
check("T527 AC3: a hook grepping for `project/tickets/` in wom7web is flagged",
      "project/tickets" in out and "does not exist in that repo" in out, out[-300:])
check("...and exits non-zero", r.returncode != 0, f"rc={r.returncode}")

STALE_PRECOMMIT = (
    "repos:\n"
    "  - repo: local\n"
    "    hooks:\n"
    "      - id: stale-tickets\n"
    "        name: stale\n"
    "        entry: echo ok\n"
    "        language: system\n"
    "        files: ^project/tickets/T\\d+\\.md$\n"
)
r = run(estate({"wom7web/.pre-commit-config.yaml": STALE_PRECOMMIT}))
out = r.stdout + r.stderr
check("T527 AC3: a pre-commit `files:` filter targeting `project/tickets/` in wom7web is flagged",
      "project/tickets" in out and "T527 AC3" in out, out[-300:])


def test_hooks_check_all() -> None:
    """Pytest entrypoint verifying all script checks above and check_hook_scope_paths directly."""
    assert not failures, f"hooks-check failures: {failures}"


def test_t527_ac3_scope_paths_probe() -> None:
    """T527 AC3: check_hook_scope_paths flags `project/tickets/` in wom7web and passes on real layout."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import hooks_check as hc

    # Real estate passes with 0 scope findings
    assert hc.check_hook_scope_paths(ROOT) == []

    # Fixture where wom7web/.husky/pre-push greps wom7web's own diff for project/tickets/ fails
    fx = estate({SANCTIONED: STALE_SCOPE_HOOK})
    findings = hc.check_hook_scope_paths(fx)
    assert any("project/tickets" in f and "wom7web" in f for f in findings), findings


print()
if failures:
    print(f"❌ {len(failures)} failure(s):")
    for f in failures:
        print(f"   · {f}")
    sys.exit(1)
print("✅ hooks-check: all checks passed")
