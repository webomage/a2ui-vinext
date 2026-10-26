#!/usr/bin/env python3
"""T160 regression proof for run_suites.py — the aggregate must fail for the RIGHT reasons.

The whole point of this tool is that a green run means something. So every way it could report a
false green gets a red case here: an empty registry, a declared suite whose recipe does not exist,
a suite that exits 0 having run nothing, and an advisory/excluded entry with no written reason.

Drives the runner against fixture registries via REGISTRY monkeypatching — no suite is actually
executed except in the two cases that need a real subprocess.

Run: `just run-suites-test`
"""
import json
import os
import subprocess
import sys
import pathlib
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "w0m-web"
SCRIPT = ROOT / "scripts" / "run_suites.py"
TMP = Path(tempfile.mkdtemp(prefix="t160-"))

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'✅' if ok else '❌'} {label}")
    if not ok:
        failures.append(f"{label}{(' — ' + detail) if detail else ''}")


if not SCRIPT.is_file():
    print("❌ run_suites.py missing — the suite cannot prove anything")
    sys.exit(2)


def run_with(registry: dict, *args) -> subprocess.CompletedProcess:
    """Drive the runner against a fixture registry via W0M_SUITES_REGISTRY."""
    p = TMP / "reg.json"
    p.write_text(json.dumps(registry))
    env = {**os.environ, "W0M_SUITES_REGISTRY": str(p)}
    return subprocess.run([sys.executable, str(SCRIPT), *args],
                          capture_output=True, text=True, env=env)


print("\n── the registry must be sane before anything runs ──")

r = run_with({"suites": []})
check("an EMPTY registry fails", r.returncode != 0, r.stdout + r.stderr)
check("...and says why", "refusing" in (r.stdout + r.stderr).lower(), (r.stdout + r.stderr)[-120:])

r = run_with({"suites": [{"name": "x", "recipe": "nope", "tier": "offline",
                          "blocking": False}]})
check("a NON-BLOCKING suite with no reason fails the registry", r.returncode != 0,
      (r.stdout + r.stderr)[-120:])

r = run_with({"suites": [{"name": "a", "recipe": "ac-progress-test", "tier": "offline"}],
              "excluded": [{"recipe": "model-test"}]}, "--drift")
check("an EXCLUDED recipe with no reason fails", r.returncode != 0, (r.stdout + r.stderr)[-120:])

print("\n── a declared suite that cannot run is a FAILURE, never a quiet skip ──")

r = run_with({"suites": [{"name": "ghost", "recipe": "definitely-not-a-recipe", "tier": "offline"}]})
out = r.stdout + r.stderr
check("a MISSING recipe fails the aggregate", r.returncode != 0, out[-120:])
check("...and names the suite", "ghost" in out, out[-160:])

print("\n── counts make 'it passed' falsifiable ──")

r = run_with({"suites": [{"name": "real", "recipe": "ac-progress-test", "tier": "offline"}]})
out = r.stdout + r.stderr
check("a real suite passes and reports a check count", r.returncode == 0 and "check(s)" in out,
      out[-160:])
check("...and the count is non-zero", " 0 check(s)" not in out, out[-160:])

print("\n── tiering ──")

r = run_with({"suites": [{"name": "l", "recipe": "ac-progress-test", "tier": "live"}]}, "--tier", "offline")
check("asking for a tier with no suites fails rather than reporting green",
      r.returncode != 0, (r.stdout + r.stderr)[-120:])

print("\n── the DRIFT MATCHER itself (T195 AC4/AC6) ──")
# Imported rather than driven by subprocess: `drift()` reads the real justfile from a fixed path,
# so the only way to probe the matcher against a fixture is to call it directly.
sys.path.insert(0, str(SCRIPT.parent))
from run_suites import SUITE_BODY, SUITE_NAME, recipes  # noqa: E402


def matches(jf: str) -> set[str]:
    return {n for n, body in recipes(jf).items()
            if SUITE_NAME.search(n) or SUITE_BODY.search(body)}


# 🔴 THE REGRESSION THIS FILE EXISTS FOR. Until 2026-08-13 the matcher was
# `^([a-z][a-z0-9-]*(?:-test|-check)):` — a bare name followed immediately by a colon. Every gate
# taking parameters was therefore invisible to it, INSIDE ITS OWN STATED SCOPE: 14 recipes ending
# -test/-check, among them `authz-blanket-check *args:`. D37's "13 undeclared", its later "20", and
# T195's "27" were all undercounts of the matcher's own definition, and nothing said so because the
# gate was the thing under-reporting.
check("a PARAMETERISED gate is seen (`foo-check *args:`)",
      "foo-check" in matches('foo-check *args:\n    @echo hi\n'))
check("...and one with a DEFAULTED parameter (`bar-check mode=\"\":`)",
      "bar-check" in matches('bar-check mode="":\n    @echo hi\n'))
check("...and a dependency-carrying one (`baz-test: other`)",
      "baz-test" in matches('baz-test: other\n    @echo hi\n'))

check("a suite with an ORDINARY name is found by its BODY",
      "audit" in matches('audit:\n    python3 project/scripts/x.py --check\n'))
check("...including a tests/ script",
      "zzz" in matches('zzz:\n    python3 project/scripts/tests/test_x.py\n'))

# Over-matching is the other way this gate can lie: a report full of non-suites is one people stop
# reading, and `:=` assignments plus comments are the two shapes most likely to be misread.
check("an ASSIGNMENT is not a recipe (`ver := \"1\"`)",
      not matches('ver := "1"\ncheck-nothing := "x-check"\n'))
check("a COMMENT mentioning a -check name is not a recipe",
      not matches('# see foo-check for details\n'))
check("a plain recipe with no gate behaviour is NOT matched",
      not matches('build:\n    pnpm run build\n'))

# AC6 — the drift gate's own red probe: an undeclared recipe must be NAMED, and declaring it must
# clear it. Driven through the real `drift()` against a fixture registry so both directions run.
import run_suites  # noqa: E402

real_jf = "\n".join(
    ln for ln in run_suites._read_justfile_text(run_suites.API / "justfile").splitlines()
    if not ln.startswith("import ")
) + "\n"
probe_jf = real_jf + '\nt195-probe-check *args:\n    @echo probe\n'
orig_read, orig_registry = Path.read_text, run_suites.REGISTRY
try:
    fake = TMP / "jf-probe"
    fake.write_text(probe_jf)
    run_suites.API = fake.parent
    (fake.parent / "justfile").write_text(probe_jf)

    reg = TMP / "reg-probe.json"
    reg.write_text(json.dumps({"suites": [{"name": "a", "recipe": "ac-progress-test",
                                           "tier": "offline"}]}))
    run_suites.REGISTRY = reg
    found = run_suites.drift([{"recipe": "ac-progress-test"}])
    check("an undeclared recipe is NAMED by the drift gate", "t195-probe-check" in found,
          f"got {sorted(found)[:5]}")
    check("...and the report says WHY it matched",
          "name" in found.get("t195-probe-check", ""), str(found.get("t195-probe-check")))

    found2 = run_suites.drift([{"recipe": "ac-progress-test"},
                               {"recipe": "t195-probe-check"}])
    check("...and declaring it clears the finding", "t195-probe-check" not in found2,
          f"still {sorted(found2)[:5]}")
finally:
    run_suites.REGISTRY = orig_registry
    run_suites.API = ROOT

# ── T240 AC1/AC5 — Capability inspection for argument-forwarding recipes ──
# A recipe that forwards arguments to a script accepting --enforce/--check/--drift
# must be detected as a suite even when its name does not end in -test/-check
# and its body does not contain the flag literally.
dummy_script = TMP / "dummy_gate.py"
dummy_script.write_text('import argparse\nap = argparse.ArgumentParser()\nap.add_argument("--enforce", action="store_true")\n')

dummy_util = TMP / "dummy_util.py"
dummy_util.write_text('import argparse\nap = argparse.ArgumentParser()\nap.add_argument("--count", type=int)\n')

cap_jf = real_jf + f'\nforwarding-gate *args:\n    python3 {dummy_script} {{{{args}}}}\n\nforwarding-util *args:\n    python3 {dummy_util} {{{{args}}}}\n'

try:
    fake_cap = TMP / "jf-cap"
    fake_cap.write_text(cap_jf)
    run_suites.API = fake_cap.parent
    (fake_cap.parent / "justfile").write_text(cap_jf)

    reg_cap = TMP / "reg-cap.json"
    reg_cap.write_text(json.dumps({"suites": [{"name": "a", "recipe": "ac-progress-test", "tier": "offline"}], "excluded": []}))
    run_suites.REGISTRY = reg_cap

    found_cap = run_suites.drift([{"recipe": "ac-progress-test"}])
    check("T240 AC1/AC5: an argument-forwarding gate is DETECTED via script capability",
          "forwarding-gate" in found_cap, f"got {sorted(found_cap)[:6]}")
    check("...and the reason mentions the accepted flag",
          "enforce" in str(found_cap.get("forwarding-gate", "")), str(found_cap.get("forwarding-gate")))
    check("...while an argument-forwarding utility is NOT matched",
          "forwarding-util" not in found_cap, f"unexpectedly got forwarding-util in {found_cap}")
finally:
    run_suites.REGISTRY = orig_registry
    run_suites.API = ROOT

# ── T240 AC3 — Tier A vs Tier B differentiation in drift reporting ──
try:
    reg_tier = TMP / "reg-tier.json"
    reg_tier.write_text(json.dumps({
        "suites": [{"name": "authz-admin-client", "recipe": "authz-admin-client-test", "tier": "offline"}],
        "excluded": []
    }))
    run_suites.REGISTRY = reg_tier
    found_tier = run_suites.drift([{"name": "authz-admin-client", "recipe": "authz-admin-client-test"}])
    check("T240 AC3: Tier B is identified when red-proof is declared",
          "[Tier B]" in found_tier.get("authz-admin-client", ""),
          str(found_tier.get("authz-admin-client")))
    check("...and Tier A is identified when no proof is declared",
          "[Tier A]" in found_tier.get("orphan-components", ""),
          str(found_tier.get("orphan-components")))
finally:
    run_suites.REGISTRY = orig_registry
    run_suites.API = ROOT

# ── T247 AC2 — scheduled recipes are drift candidates, and the JSONC scan is string-aware ──
# `tools-weekly` matches neither SUITE_NAME nor SUITE_BODY: it upgrades production tooling on a
# timer and looks nothing like a test. Measured 2026-08-21, ALL FOUR launchd agents were undeclared
# — including the two that take the database backups. The matcher asks a third question now:
# "does anything run unattended that nobody triaged".
#
# The parser is hand-rolled, so it is tested rather than trusted. `//` inside a URL is the exact
# case a regex comment-stripper gets wrong, and this estate has a standing rule against that.
_orig_sched = run_suites.SCHEDULES
try:
    with tempfile.TemporaryDirectory() as _d:
        _f = pathlib.Path(_d) / "s.jsonc"
        run_suites.SCHEDULES = _f

        _f.write_text('{ "agents": [ { "command": "x", "note": "see https://example.com/a" } ] }')
        check("a `//` inside a URL is not treated as a comment",
              run_suites.scheduled_recipes() == {"x"}, str(run_suites.scheduled_recipes()))

        _f.write_text('// lead\n{ "agents": [ { "command": "y" } ] } // tail')
        check("real comments before and after the object are stripped",
              run_suites.scheduled_recipes() == {"y"}, str(run_suites.scheduled_recipes()))

        _f.write_text('{ "agents": [ { "command": "w", "n": "a \\" // not a comment" } ] }')
        check("an escaped quote does not end the string early",
              run_suites.scheduled_recipes() == {"w"}, str(run_suites.scheduled_recipes()))

        _f.write_text("{ not json")
        check("malformed JSONC degrades to empty rather than raising",
              run_suites.scheduled_recipes() == set(), str(run_suites.scheduled_recipes()))

        run_suites.SCHEDULES = pathlib.Path(_d) / "absent.jsonc"
        check("a missing schedule file degrades to empty",
              run_suites.scheduled_recipes() == set(), str(run_suites.scheduled_recipes()))

    # The real schedule must still resolve — a parser that only passes fixtures is not a parser.
    run_suites.SCHEDULES = _orig_sched
    _real = run_suites.scheduled_recipes()
    check("the REAL schedules.jsonc still parses (non-empty)", bool(_real), str(_real))
    check("...and names tools-weekly, the recipe that could hide",
          "tools-weekly" in _real, str(sorted(_real)))

    # 🔴 The inversion: a scheduled recipe absent from the registry must be REPORTED. Without this
    # the widening could be satisfied by a matcher that never fires.
    # REGISTRY must be redirected too: `drift()` reads the real file for its `excluded` list, and
    # `tools-weekly` is legitimately excluded there now — so probing against the real registry
    # proves nothing. (This probe failed exactly that way when first written.)
    with tempfile.TemporaryDirectory() as _d2:
        _reg = pathlib.Path(_d2) / "registry.json"
        _reg.write_text(json.dumps({"suites": [{"recipe": "ac-progress-test"}], "excluded": []}))
        _saved_reg, run_suites.REGISTRY = run_suites.REGISTRY, _reg
        try:
            _found = run_suites.drift([{"recipe": "ac-progress-test"}])
            check("an undeclared SCHEDULED recipe is named by the drift gate",
                  "tools-weekly" in _found, f"got {sorted(_found)[:6]}")
            check("...and the reason says it matched on the SCHEDULE, not on its name",
                  "schedule" in _found.get("tools-weekly", ""), str(_found.get("tools-weekly")))
        finally:
            run_suites.REGISTRY = _saved_reg
finally:
    run_suites.SCHEDULES = _orig_sched

# ── count_checks() must read pytest's own banner-padded summary, not just a bare "N passed" ──
# Found 2026-09-03: `active-work-heads-up-test` runs `pytest -v`, whose summary line is
# `==== 14 passed in 0.17s ====` — a leading `====` banner, not whitespace, so the old
# line-anchored PASSED_N never matched and the suite counted as UNREADABLE despite a normal exit.
check("a bare 'N passed' summary is read",
      run_suites.count_checks("5 passed in 0.01s") == 5)
check("pytest's ==== banner-padded summary is read too",
      run_suites.count_checks("==== 14 passed in 0.17s ====") == 14)

print("\n── T549 AC1: suites-drift resolves every registered recipe against w0m-api/justfile ──")
_real_reg_data = json.loads((WEB / "project" / "test-suites.json").read_text(encoding="utf-8"))
_real_suites = _real_reg_data.get("suites", [])
check("T549 AC1: unmutated tree resolves every registered recipe in w0m-api/justfile",
      run_suites.unresolved_suites(_real_suites) == [])

with tempfile.TemporaryDirectory() as _t549_dir:
    _t549_api = Path(_t549_dir) / "w0m-api"
    _t549_api.mkdir()
    # Mutate w0m-api/justfile by removing a registered recipe (`ac-progress-test`), even if root justfile has it.
    _mutated_jf = "\n".join(
        line for line in real_jf.splitlines()
        if not line.startswith("ac-progress-test:")
    ) + "\n"
    (_t549_api / "justfile").write_text(_mutated_jf, encoding="utf-8")
    _t549_reg = Path(_t549_dir) / "test-suites.json"
    _t549_reg.write_text(json.dumps({
        "suites": [
            {"name": "ac-progress", "recipe": "ac-progress-test", "tier": "offline", "blocking": True},
        ],
        "excluded": [],
    }), encoding="utf-8")
    _env_t549 = {
        **os.environ,
        "W0M_SUITES_REGISTRY": str(_t549_reg),
        "W0M_SUITES_API": str(_t549_api),
    }
    _r_t549 = subprocess.run(
        [sys.executable, str(SCRIPT), "--drift"],
        capture_output=True, text=True, env=_env_t549,
    )
    _out_t549 = _r_t549.stdout + _r_t549.stderr
    check("T549 AC1 (mutation): removing a registered recipe from w0m-api/justfile fails --drift",
          _r_t549.returncode != 0, _out_t549[-200:])
    check("T549 AC1: failure names the suite, recipe, registry entry, and justfile searched",
          "ac-progress" in _out_t549
          and "ac-progress-test" in _out_t549
          and str(_t549_reg) in _out_t549
          and str(_t549_api / "justfile") in _out_t549,
          _out_t549[-240:])

print("\n── T549 AC3: suites-drift flags suites whose output has no countable check dialect ──")
with tempfile.TemporaryDirectory() as _t549_log_dir:
    _log_p = Path(_t549_log_dir)
    (_log_p / "silent-suite.log").write_text("all good, everything worked fine\n", encoding="utf-8")
    (_log_p / "countable-suite.log").write_text("5 passed in 0.02s\n", encoding="utf-8")
    _warn_list = run_suites.uncountable_suites([
        {"name": "silent-suite", "recipe": "ac-progress-test", "tier": "offline"},
        {"name": "countable-suite", "recipe": "ac-progress-test", "tier": "offline"},
        {"name": "inline-silent", "recipe": "ac-progress-test", "tier": "offline", "sample_output": "done."},
    ], log_dir=_log_p)
    _warn_names = {u["name"] for u in _warn_list}
    check("T549 AC3: suite with uncountable log output is flagged",
          "silent-suite" in _warn_names and "inline-silent" in _warn_names, str(_warn_list))
    check("T549 AC3: suite with countable output is not flagged",
          "countable-suite" not in _warn_names, str(_warn_list))
    _t549_reg3 = _log_p / "reg3.json"
    _t549_reg3.write_text(json.dumps({
        "suites": [
            {"name": "silent-suite", "recipe": "ac-progress-test", "tier": "offline"},
        ],
        "excluded": [],
    }), encoding="utf-8")
    _r_ac3 = subprocess.run(
        [sys.executable, str(SCRIPT), "--drift"],
        capture_output=True, text=True,
        env={**os.environ, "W0M_SUITES_REGISTRY": str(_t549_reg3), "W0M_SUITES_LOG_DIR": str(_log_p)},
    )
    _out_ac3 = _r_ac3.stdout + _r_ac3.stderr
    check("T549 AC3: --drift warning names all three accepted check dialects",
          "silent-suite" in _out_ac3
          and "Glyph per-check lines" in _out_ac3
          and "Bracketed text per-check lines" in _out_ac3
          and "Framework summary lines" in _out_ac3,
          _out_ac3[-300:])

print("\n── T328 AC5 & AC6: UNMEASURABLE vs FAIL distinction and [tier/blocking|advisory] tags ──")
with tempfile.TemporaryDirectory() as _t328_dir:
    _t328_api = Path(_t328_dir) / "w0m-api"
    _t328_api.mkdir()
    (_t328_api / "justfile").write_text(
        "unmeasurable-probe:\n"
        "    @echo 'UNMEASURABLE — fixture probe missing prerequisite'\n"
        "    @exit 2\n"
        "\n"
        "failing-probe:\n"
        "    @echo '  ❌ 1 check failed'\n"
        "    @exit 1\n",
        encoding="utf-8",
    )
    _t328_reg_adv = Path(_t328_dir) / "reg-adv.json"
    _t328_reg_adv.write_text(json.dumps({
        "suites": [{
            "name": "unm-adv",
            "recipe": "unmeasurable-probe",
            "tier": "offline",
            "blocking": False,
            "reason": "fixture advisory unmeasurable probe",
        }],
    }), encoding="utf-8")
    _r_adv = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True, text=True,
        env={**os.environ, "W0M_SUITES_REGISTRY": str(_t328_reg_adv), "W0M_SUITES_API": str(_t328_api)},
    )
    _out_adv = _r_adv.stdout + _r_adv.stderr
    check("T328 AC5: advisory suite exiting 2 reports UNMEASURABLE, not FAIL, and exits 0",
          _r_adv.returncode == 0
          and "UNMEASURABLE" in _out_adv
          and "advisory suite(s) unmeasurable" in _out_adv
          and "advisory suite(s) failing" not in _out_adv,
          _out_adv)
    check("T328 AC6: advisory suite line and summary surface [offline/advisory]",
          "[offline/advisory]" in _out_adv, _out_adv)

    _t328_reg_blk = Path(_t328_dir) / "reg-blk.json"
    _t328_reg_blk.write_text(json.dumps({
        "suites": [{
            "name": "unm-blk",
            "recipe": "unmeasurable-probe",
            "tier": "offline",
            "blocking": True,
        }],
    }), encoding="utf-8")
    _r_blk = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True, text=True,
        env={**os.environ, "W0M_SUITES_REGISTRY": str(_t328_reg_blk), "W0M_SUITES_API": str(_t328_api)},
    )
    _out_blk = _r_blk.stdout + _r_blk.stderr
    check("T328 AC5: blocking suite exiting 2 fails the aggregate and reports blocking suite(s) unmeasurable",
          _r_blk.returncode == 1 and "blocking suite(s) unmeasurable" in _out_blk,
          _out_blk)
    check("T328 AC6: blocking suite line surfaces [offline/blocking]",
          "[offline/blocking]" in _out_blk, _out_blk)

print()
if failures:
    print(f"❌ {len(failures)} failure(s):")
    for f in failures:
        print(f"   · {f}")
    sys.exit(1)
print("✅ run-suites: all checks passed")
