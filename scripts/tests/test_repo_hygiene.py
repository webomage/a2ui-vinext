#!/usr/bin/env python3
"""T135 AC7 — prove `docs-check`, `secrets-check` and `license-check` can actually FAIL.

WHY THIS EXISTS
    AC7 says every gate this ticket added is "proven red, and starts green". The proofs were taken
    — once, by hand — and written into the ticket body. That is not the same as being provable
    again. 19 `*-test` recipes existed in this estate and **none of them covered these three**, so
    a regression in their ability to fail would have been invisible: the gates would go on printing
    ✅ over a clean estate, which is exactly what they print when they are working.

    A gate observed only green is a hypothesis. This makes the red side re-runnable.

WHY A FIXTURE
    Proving these red on the real estate means committing a real violation — a missing README, a
    `dotenv-load` in a tracked justfile, a manifest without `private: true`. So the whole scan is
    retargeted at a throwaway tree via `W0M_HYGIENE_ROOT`, the same hook `state_doctor.py` uses via
    `W0M_STATE_MD`. The fixture stands in for `wom7web`; ROOT and the policy path derive from it
    exactly as they do in the real layout.

THE DISCIPLINE THIS FILE INHERITS (T135 AC7 · T174's review gate)
    * Every probe asserts the gate FAILS **and** that the message names the thing — an exit code
      alone does not distinguish "caught the violation I built" from "fell over for another reason".
    * The control runs FIRST. A red probe over a fixture that was never green proves nothing.
    * The empty-set cases are first-class, because a gate's natural failure mode (nothing to check)
      is indistinguishable from its success condition. `docs-check` shipped exactly that vacuous
      pass in July, with `readme_sections: []` degrading the content bar to a file-exists check.
    * The real estate must be untouched at the end, and that is measured rather than assumed.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]    # …/@wom
WEB = ROOT / "wom7web"
SCRIPT = ROOT / "scripts" / "repo_hygiene.py"
REAL_POLICY = ROOT / "project" / "policies" / "hygiene-policy.json"

failures: list[str] = []
TMP = Path(tempfile.mkdtemp(prefix="w0m-hygiene-test-"))

# Captured BEFORE anything runs, so "the suite did not touch the real tree" is a measurement.
REAL_POLICY_HASH_AT_START = hashlib.sha256(REAL_POLICY.read_bytes()).hexdigest()


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'✅' if ok else '❌'} {label}")
    if not ok:
        failures.append(f"{label}{(' — ' + detail) if detail else ''}")


if not SCRIPT.is_file():
    print("❌ repo_hygiene.py missing — the suite cannot prove anything")
    sys.exit(2)


def run(root: Path, check_name: str) -> subprocess.CompletedProcess:
    """Drive the gate against a fixture. `root` is the stand-in for wom7web."""
    env = {**os.environ, "W0M_HYGIENE_ROOT": str(root)}
    return subprocess.run([sys.executable, str(SCRIPT), check_name],
                          capture_output=True, text=True, env=env)


def out(r: subprocess.CompletedProcess) -> str:
    return r.stdout + r.stderr


def build_fixture(name: str) -> tuple[Path, Path]:
    """A minimal estate that PASSES all three gates. Returns (workspace_root, repo).

    Deliberately built from the REAL policy with only `repos` narrowed. A hand-written policy would
    drift from the one in production and the probes would then be testing a rule nobody ships.
    """
    base = TMP / name
    (base / "project" / "policies").mkdir(parents=True, exist_ok=True)
    policy = json.loads(REAL_POLICY.read_text())
    policy["repos"] = [{"path": "repoA"}]
    (base / "project" / "policies" / "hygiene-policy.json").write_text(json.dumps(policy, indent=2))

    repo = base / "repoA"
    repo.mkdir(parents=True)
    (repo / "README.md").write_text(
        "# repoA\n\n## What is this\nA fixture.\n\n"
        "## How to run\n`just something`\n\n## Where are the docs\nHere.\n")
    (repo / "LICENSE").write_text("Copyright (c) 2026 w0m. All rights reserved.\n")
    (repo / "SECURITY.md").write_text(
        "# Security\n\nReport issues to security@webomage.com — we respond within 72 hours.\n")
    (repo / "CONTRIBUTING.md").write_text("# Contributing\n\nBranch from `beta`, run `just test`.\n")
    (repo / "CODE_OF_CONDUCT.md").write_text("# Code of Conduct\n\nBe decent. Enforced by the owner.\n")
    (repo / "package.json").write_text(
        json.dumps({"name": "repo-a", "private": True, "license": "UNLICENSED"}, indent=2))
    (repo / "justfile").write_text("hello:\n\techo hi\n")

    # The corpus half of secrets-check reads `wom7skills/skills` relative to ROOT.
    skill = base / "wom7skills" / "skills" / "demo"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "# demo\n\nRuns with `infisical run --env=beta --` and reads $API_KEY from the injected env.\n")

    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "fixture"], check=True)
    return base, repo


def set_policy(base: Path, mutate) -> None:
    p = base / "project" / "policies" / "hygiene-policy.json"
    policy = json.loads(p.read_text())
    mutate(policy)
    p.write_text(json.dumps(policy, indent=2))


# ── the control: all three gates must be GREEN before any red probe means anything ──

print("\n── the control: a clean fixture must PASS all three gates ──")

web, repo = build_fixture("control")
for gate in ("docs", "secrets", "license"):
    r = run(web, gate)
    check(f"{gate}-check passes on a clean fixture", r.returncode == 0, out(r)[-400:])

# The fixture must be non-trivial, or every red probe below is running over nothing.
r = run(web, "docs")
check("...and the control actually examined files (not a vacuous green)",
      "checked=" in out(r) and "checked=0" not in out(r), out(r)[-200:])


# ── 🔴 docs-check ──

print("\n── 🔴 docs-check must FAIL on a missing file, a missing section, and an empty one ──")

web, repo = build_fixture("docs-missing")
(repo / "README.md").unlink()
r = run(web, "docs")
check("a MISSING required file fails", r.returncode != 0, f"rc={r.returncode}")
check("...and names the file", "missing README.md" in out(r), out(r)[-300:])

web, repo = build_fixture("docs-section")
(repo / "README.md").write_text("# repoA\n\n## What is this\nA fixture.\n\n## How to run\n`just x`\n")
r = run(web, "docs")
check("a README missing a required SECTION fails", r.returncode != 0, f"rc={r.returncode}")
check("...and names the section id", "where-are-docs" in out(r), out(r)[-300:])

web, repo = build_fixture("docs-empty")
(repo / "SECURITY.md").write_text("   \n")
r = run(web, "docs")
check("a file that EXISTS but is empty fails", r.returncode != 0, f"rc={r.returncode}")
check("...and says empty rather than missing", "empty or unreadable" in out(r), out(r)[-300:])

# The historical vacuous pass, reproduced as a standing probe. With `readme_sections: []` the
# content bar silently degraded to a file-exists check and docs-check reported ✅ over 8 repos.
web, repo = build_fixture("docs-vacuous")
set_policy(web, lambda p: p["docs"].update({"readme_sections": []}))
r = run(web, "docs")
check("an EMPTY readme_sections list refuses to pass vacuously", r.returncode != 0, f"rc={r.returncode}")
check("...and says so, rather than degrading to a file-exists check",
      "vacuous" in out(r).lower(), out(r)[-300:])


# ── 🔴 secrets-check ──

print("\n── 🔴 secrets-check must FAIL on file-based secret access in TRACKED automation ──")

web, repo = build_fixture("secrets-dotenv")
(repo / "justfile").write_text("set dotenv-load := true\n\nhello:\n\techo hi\n")
subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
subprocess.run(["git", "-C", str(repo), "commit", "-qm", "violation"], check=True)
r = run(web, "secrets")
check("`dotenv-load` in a tracked justfile fails", r.returncode != 0, f"rc={r.returncode}")
check("...and names the pattern id and the location",
      "dotenv-load" in out(r) and "justfile" in out(r), out(r)[-300:])

# The scope rule — "only TRACKED automation is in scope" — asserted in BOTH directions, because a
# one-sided version is untrustworthy: a probe that only shows the file is ignored cannot tell
# "correctly out of scope" apart from "the pattern never matched anything anyway".
#
# ⚠️ Note what untracked means here. Overwriting an already-committed file does NOT make it
# untracked — it stays in `git ls-files` and is correctly scanned. The first draft of this probe
# rewrote the committed justfile and then asserted it was ignored; the gate flagged it, and the
# gate was right. The file has to be one git has never seen.
web, repo = build_fixture("secrets-untracked")
scripts = repo / "scripts"
scripts.mkdir()
(scripts / "rogue.py").write_text("from dotenv import load_dotenv\nload_dotenv()\n")
r = run(web, "secrets")
check("an UNTRACKED file matching a scan glob is NOT flagged (only tracked automation is in scope)",
      r.returncode == 0 and "rogue.py" not in out(r), out(r)[-300:])

# …and the positive control that gives that assertion meaning: commit the very same file and the
# gate must now catch it.
subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
subprocess.run(["git", "-C", str(repo), "commit", "-qm", "track the rogue script"], check=True)
r = run(web, "secrets")
check("...and the SAME file, once tracked, IS flagged", r.returncode != 0, f"rc={r.returncode}")
check("...naming the file and the dotenv-library pattern",
      "rogue.py" in out(r) and "dotenv-library" in out(r), out(r)[-300:])

web, repo = build_fixture("secrets-noglobs")
set_policy(web, lambda p: p["secrets"].update({"scan_globs": []}))
r = run(web, "secrets")
check("an EMPTY scan_globs refuses to pass on 'ran nothing'", r.returncode != 0, f"rc={r.returncode}")
check("...and says it scanned 0 files", "scanned 0" in out(r), out(r)[-300:])

web, repo = build_fixture("secrets-corpus")
(TMP / "secrets-corpus" / "wom7skills" / "skills" / "demo" / "SKILL.md").write_text(
    "# demo\n\nExport $DATABASE_PASSWORD directly into the shell before running.\n")
r = run(web, "secrets")
check("a skill CONSUMING a secret without naming the manager fails", r.returncode != 0, f"rc={r.returncode}")


# ── 🔴 license-check ──

print("\n── 🔴 license-check must FAIL on a non-private or wrongly-licensed manifest ──")

web, repo = build_fixture("lic-private")
(repo / "package.json").write_text(
    json.dumps({"name": "repo-a", "license": "UNLICENSED"}, indent=2))   # private: true removed
r = run(web, "license")
check("a manifest without `private: true` fails", r.returncode != 0, f"rc={r.returncode}")
check("...and names private", "private" in out(r).lower(), out(r)[-300:])

web, repo = build_fixture("lic-wrong")
(repo / "package.json").write_text(
    json.dumps({"name": "repo-a", "private": True, "license": "MIT"}, indent=2))
r = run(web, "license")
check("a manifest with the WRONG license fails", r.returncode != 0, f"rc={r.returncode}")
check("...and names the expected license", "UNLICENSED" in out(r), out(r)[-300:])


# ── 🔴 the empty set, for all three ──

print("\n── 🔴 all three must refuse an EMPTY repo set rather than passing over nothing ──")

for gate in ("docs", "secrets", "license"):
    web, repo = build_fixture(f"empty-{gate}")
    set_policy(web, lambda p: p.update({"repos": []}))
    r = run(web, gate)
    check(f"{gate}-check refuses an empty repo set", r.returncode != 0, f"rc={r.returncode}")
    check(f"...and {gate}-check says so rather than reporting clean",
          "empty input set" in out(r), out(r)[-300:])

print("\n── 🔴 a DECLARED repo that is absent is a violation, never a silent skip ──")

web, repo = build_fixture("declared-missing")
shutil.rmtree(repo)
r = run(web, "docs")
check("a declared-but-absent repo fails", r.returncode != 0, f"rc={r.returncode}")
check("...and warns that scope would shrink", "scope would silently shrink" in out(r), out(r)[-300:])


# ── the probes must not have touched the REAL estate ──


# ── AC6: the transitive dependency-license gate (T135, added 2026-08-10) ──────────────────────
#
# Two halves, deliberately proved by different means because they fail differently:
#   • CLASSIFICATION is pure logic and is driven in-process — that is where BOTH first-run bugs
#     lived, and a subprocess probe would have hidden them behind a green exit code.
#   • The POLICY GUARDS are driven through the real CLI on a fixture, because their whole job is
#     to refuse to run.
# The end-to-end red probe stubs `pnpm` itself: constructing a real GPL violation would mean
# installing a GPL package into the estate, which is the thing the gate exists to prevent.

print("\n── AC6: dependency-licence classification (in-process, where the bugs were) ──")

sys.path.insert(0, str(SCRIPT.parent))
import repo_hygiene as rh  # noqa: E402

TIERS = json.loads((REAL_POLICY.parent / "deps-policy.json").read_text())["licenses"]["tiers"]

check("GPL-3.0-only tiers as FAIL", rh._tier("GPL-3.0-only", TIERS) == "fail")
check("AGPL-3.0-or-later tiers as FAIL", rh._tier("AGPL-3.0-or-later", TIERS) == "fail")
check("MIT tiers as advisory", rh._tier("MIT", TIERS) == "advisory")
check("MPL-2.0 tiers as REVIEW, not fail", rh._tier("MPL-2.0", TIERS) == "review")

# 🔴 THE REGRESSION PROBE. The first run of this gate reported the sharp native binary as strong
# copyleft, because an unanchored `GPL-3.0` pattern matched inside `LGPL-3.0-or-later`. Same
# substring family as `\b` matching across hyphens. If someone re-adds an unanchored pattern,
# this is what fails.
check("LGPL-3.0-or-later is REVIEW, not FAIL (unanchored-substring regression)",
      rh._tier("LGPL-3.0-or-later", TIERS) == "review",
      f"got {rh._tier('LGPL-3.0-or-later', TIERS)} — a `GPL` pattern is matching inside `LGPL`")

# An OR is an offer: the permissive branch can be elected, so the package binds nothing.
check("`(MPL-2.0 OR Apache-2.0)` elects the permissive branch → advisory",
      rh._tier("(MPL-2.0 OR Apache-2.0)", TIERS) == "advisory")
check("`(MIT OR GPL-3.0-only)` elects MIT → advisory",
      rh._tier("(MIT OR GPL-3.0-only)", TIERS) == "advisory")
# An AND binds every term — the opposite reading, and getting it backwards would wave GPL through.
check("`MIT AND GPL-3.0-only` binds both → FAIL",
      rh._tier("MIT AND GPL-3.0-only", TIERS) == "fail")

# 🔴 THE FAIL-OPEN PROBE. Every probe above uses a FLAT expression, and that is exactly why the
# first implementation shipped this bug past all of them: it searched the whole string for `OR`
# and, finding one inside the parens, elected the most permissive branch — so a GPL-bound
# expression came back `advisory`. The review gate caught it, not the suite. A gate waving through
# the thing it exists to stop is the worst direction to be wrong in, so it gets its own probes.
check("`(MIT OR Apache-2.0) AND GPL-3.0-only` is FAIL, not advisory (nested fail-open)",
      rh._tier("(MIT OR Apache-2.0) AND GPL-3.0-only", TIERS) == "fail",
      f"got {rh._tier('(MIT OR Apache-2.0) AND GPL-3.0-only', TIERS)} — an OR inside parens is "
      "being read as the whole expression's operator")
check("`(LGPL-3.0-only AND MIT) OR Apache-2.0` elects Apache → advisory (nested precedence)",
      rh._tier("(LGPL-3.0-only AND MIT) OR Apache-2.0", TIERS) == "advisory")
check("a redundantly parenthesised term still resolves",
      rh._tier("((GPL-3.0-only))", TIERS) == "fail")

print("\n── AC6: the gate must REFUSE to run rather than pass vacuously ──")


def dep_fixture(name: str, licenses_block, pnpm_json: str | None = None) -> tuple[Path, Path | None]:
    """A fixture whose deps-policy carries `licenses_block`; optionally stub `pnpm` on PATH."""
    base, repo = build_fixture(name)
    dp = base / "project" / "policies" / "deps-policy.json"
    body = {} if licenses_block is None else {"licenses": licenses_block}
    dp.write_text(json.dumps(body, indent=2))
    if pnpm_json is not None:
        (repo / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n")
        binj = base / f"bin-{name}"
        binj.mkdir(parents=True, exist_ok=True)
        stub = binj / "pnpm"
        stub.write_text("#!/bin/sh\ncat <<'EOF'\n" + pnpm_json + "\nEOF\n")
        stub.chmod(0o755)
        return base, binj
    return base, None


def run_dep(base: Path, binj: Path | None):
    env = {**os.environ, "W0M_HYGIENE_ROOT": str(base)}
    if binj:
        env["PATH"] = f"{binj}:{env['PATH']}"
    return subprocess.run([sys.executable, str(SCRIPT), "dep-licenses"],
                          capture_output=True, text=True, env=env)


REAL = json.loads((REAL_POLICY.parent / "deps-policy.json").read_text())["licenses"]

web, _ = dep_fixture("dep-missing-key", None)
r = run_dep(web, None)
check("a deps-policy with NO `licenses` key fails", r.returncode == 1,
      "hygiene-policy has pointed at that key since it was written; a missing one must not pass")
check("…and the message names the dangling pointer", "reads as coverage" in out(r))

web, _ = dep_fixture("dep-no-patterns", {"tiers": {"fail": {"patterns": []}}, "exempt": {}})
r = run_dep(web, None)
check("a policy with ZERO `fail` patterns fails (vacuous-tier guard)", r.returncode == 1,
      "every dependency would tier advisory and the gate would pass on anything")

web, _ = dep_fixture("dep-no-workspace", REAL)
r = run_dep(web, None)
check("no pnpm workspace among declared repos fails (empty input ≠ clean)", r.returncode == 1)

print("\n── AC6: the gate must BLOCK a real violation ──")

GPL = json.dumps({"GPL-3.0-only": [{"name": "evil-gpl-lib", "versions": ["1.0.0"],
                                    "paths": ["/x"], "license": "GPL-3.0-only"}]})
web, binj = dep_fixture("dep-gpl", REAL, GPL)
r = run_dep(web, binj)
check("a GPL-3.0 PRODUCTION dependency BLOCKS", r.returncode == 1)
check("…and it is named in the finding", "evil-gpl-lib" in out(r))

WEAK = json.dumps({"MPL-2.0": [{"name": "unruled-weak-lib", "versions": ["1.0.0"],
                                "paths": ["/x"], "license": "MPL-2.0"}]})
web, binj = dep_fixture("dep-weak", REAL, WEAK)
r = run_dep(web, binj)
check("weak copyleft with NO exemption BLOCKS", r.returncode == 1)
check("…and the finding says how to rule on it", "deps-policy.json -> licenses.exempt" in out(r))

blank = {**REAL, "exempt": {"unruled-weak-lib": "   "}}
web, binj = dep_fixture("dep-blank-reason", blank, WEAK)
r = run_dep(web, binj)
check("an exemption with an EMPTY reason BLOCKS (AC9)", r.returncode == 1,
      "an unreasoned exemption is itself a finding")

reasoned = {**REAL, "exempt": {"unruled-weak-lib": "build-time only; not distributed"}}
web, binj = dep_fixture("dep-reasoned", reasoned, WEAK)
r = run_dep(web, binj)
check("…and a REASONED exemption passes (the gate can say yes)", r.returncode == 0, out(r))

# A stale exemption silently widens the next scan — the mirror of an unreasoned one.
web, binj = dep_fixture("dep-stale", {**REAL, "exempt": {"gone-from-the-tree": "was needed once"}},
                        json.dumps({"MIT": [{"name": "fine", "versions": ["1"], "paths": ["/x"],
                                             "license": "MIT"}]}))
r = run_dep(web, binj)
check("an exemption for a package no longer present BLOCKS", r.returncode == 1)
check("…and says it would widen the next scan", "widens the next scan" in out(r))
check("…and correctly says the package is GONE, not merely re-licensed",
      "no longer a production dependency anywhere" in out(r))

# The mirror case: the package is STILL a dependency, it just no longer needs an exemption. The
# first draft reported both with the same message, asserting a fact it had not measured.
web, binj = dep_fixture("dep-relicensed", {**REAL, "exempt": {"now-mit": "was MPL once"}},
                        json.dumps({"MIT": [{"name": "now-mit", "versions": ["2"], "paths": ["/x"],
                                             "license": "MIT"}]}))
r = run_dep(web, binj)
check("an exemption for a still-present but RE-LICENSED package BLOCKS", r.returncode == 1)
check("…and does NOT claim the package is gone",
      "no longer carries a licence needing an exemption" in out(r),
      "the message must not assert absence it never measured")

print("\n── the probes must not have touched the REAL estate ──")

check("the real hygiene-policy.json was never written by this suite",
      hashlib.sha256(REAL_POLICY.read_bytes()).hexdigest() == REAL_POLICY_HASH_AT_START,
      "policy hash moved during the run")
check("no fixture escaped into the repo",
      not (WEB / "repoA").exists() and not (WEB.parent / "repoA").exists(),
      "a fixture repo was created inside the real tree")

shutil.rmtree(TMP, ignore_errors=True)

print()
if failures:
    print(f"❌ repo-hygiene: {len(failures)} check(s) failed")
    for f in failures:
        print(f"   · {f}")
    sys.exit(1)
print("✅ repo-hygiene: all checks passed")
