#!/usr/bin/env python3
"""T130 regression proof for discovery.py — drives it on fixtures, asserts exit codes + JSON.

Covers: AC2 (command→recipe hard-fail, in any mode), AC3 (used-not-declared /
declared-not-used, both directions), advisory-vs-block, the `enforce_raw` opt-in, `exempt`
handling, the raw-scan false-positive guard, the MCP surface, clean reporting of a
malformed registry (no KeyError traceback), and JSONC parsing.

Non-destructive: fixtures are written to a temp dir derived from the LIVE registry, so the
detect signals still resolve against the real code tree. Run: `just discovery-test`.
"""
import json, subprocess, sys, shutil, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "w0m-web"
REAL = ROOT / "project" / "policies" / "stacks-policy.json"
SCHEMA = ROOT / "project" / "policies" / "stacks-policy.schema.json"
FIX = Path(tempfile.mkdtemp(prefix="t130-"))
FIX.mkdir(exist_ok=True)
shutil.copy(SCHEMA, FIX / "stacks-policy.schema.json")
base = json.loads(REAL.read_text())


def write(name, reg):
    p = FIX / name
    p.write_text(json.dumps(reg, indent=2))
    return p


def run(policy, *flags):
    """Return (exit_code, parsed_json)."""
    r = subprocess.run(
        ["python3", str(ROOT / "scripts" / "discovery.py"), "--policy", str(policy), "--json", *flags],
        capture_output=True, text=True, cwd=str(WEB),
    )
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        data = {"_raw": r.stdout + r.stderr}
    return r.returncode, data


def clone():
    return json.loads(json.dumps(base))


results = []
def check(label, cond):
    results.append(bool(cond))
    print(f"  {'PASS' if cond else 'FAIL'}  {label}")


def has(items, needle):
    return any(needle in x for x in items)


# discovery.py imported in-process, so rules can be driven directly on input this test controls
# instead of only through a subprocess against the live tree. Cases 0b, 8, 9, 10, 11 and 23 use it.
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location("discovery", ROOT / "scripts" / "discovery.py")
_disc = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_disc)

# 0) clean registry
code, d = run(REAL)
check("clean advisory → exit 0, no problems", code == 0 and not d["problems"])
code, d = run(REAL, "--enforce")
check("clean --enforce → exit 0 (raw advisory, not blocking)", code == 0 and not d["problems"])
# The REAL hook layer is now CLEAN — that is T149 AC3's end state: `.husky/pre-push` calls
# `just typecheck` where it used to run a raw `pnpm … astro check` loop. Asserting zero here is
# only worth anything because the detector's POSITIVE path is proved separately, on a synthetic
# hook this test controls (case 0b). Until 2026-07-31 these two checks anchored on the live
# `pre-push:25`, so when T149 removed that line they went red — and, far worse, nothing was left
# exercising the detector at all: it could have been broken outright and `just discovery` would
# still have printed "conformant". A gate proved only by input someone else maintains is a gate
# that silently stops being proved.
check("clean --enforce: the REAL hook layer has zero raw invocations (T149 AC3's end state)",
      d["raw_invocations"] == [])

# 0b) THE DETECTOR'S POSITIVE PATH, on a synthetic hook layer this test owns.
# `scan_raw_invocations` walks `ROOT.glob("wom7*")/.husky/*`, so pointing ROOT at a fixture estate
# drives the real function over input we control — no live file, nothing to rot when a hook is
# edited, and every skip rule gets its own line rather than being inferred from one live example.
_EST = FIX / "estate"
_HOOKS = _EST / "wom7fixture" / ".husky"
_HOOKS.mkdir(parents=True)
(_EST / "wom7fixture" / ".git").mkdir()
(_HOOKS / "_").mkdir()                      # husky internals — must never be scanned
(_HOOKS / "_" / "husky.sh").write_text("pnpm exec whatever\n")
(_HOOKS / "pre-push").write_text(
    "#!/usr/bin/env sh\n"
    "# pnpm exec astro check   <- a comment, not a call\n"
    'echo "run pnpm install first"\n'
    'printf "%s\\n" "npx tsc --noEmit"\n'
    "just typecheck\n"
    "pnpm --filter web exec astro check\n"      # line 6: the real offender
    'MSG="deno task build"; echo "$MSG"\n'
)


def scan_fixture(recipes):
    """Run the REAL scanner over the fixture estate. ROOT is restored even on failure — a test
    that leaves it patched would make every later case read the wrong tree."""
    real, _disc.ROOT = _disc.ROOT, _EST
    try:
        return _disc.scan_raw_invocations(recipes)
    finally:
        _disc.ROOT = real


_raw = scan_fixture({"w0m-api/justfile": {"typecheck"}})
_none = scan_fixture({})                       # no recipes parsed → nothing to route TO

check("detector FIRES on a raw invocation in a synthetic hook, naming file, line and tool",
      len(_raw) == 1 and has(_raw, "pre-push:6") and has(_raw, "raw `pnpm`"))
check("detector skips a commented-out call (line 2)", not has(_raw, "pre-push:2"))
check("detector skips an echo line (line 3)", not has(_raw, "pre-push:3"))
check("detector skips a printf line (line 4)", not has(_raw, "pre-push:4"))
check("detector skips a tool name inside a quoted string (line 7)", not has(_raw, "pre-push:7"))
# The property is NON-RECURSION, not the `p.name != "_"` guard: husky's generated `_` shims are
# full of raw tool calls, so the day someone swaps `iterdir()` for `rglob("*")` the scan starts
# flagging husky's own internals. Verified by mutation — that swap turns this line red.
check("detector does not descend into husky's generated `_` shims", not has(_raw, "husky.sh"))
check("no known recipes → no findings (nothing to route the tool TO)", _none == [])
# Each RAW_TOOLS token must actually match: the alternation is built by string-joining, so a typo
# there would silently retire one tool from the scan with every other check still green.
_multi = _HOOKS / "post-merge"
for _tool, _line in (("pnpm", "pnpm install"), ("npx", "npx tsc -p ."), ("tsc", "tsc --noEmit"),
                     ("deno", "deno task build"), ("wrangler", "wrangler deploy"),
                     ("mlx_lm (bare)", "mlx_lm --model x"),
                     # mlx ships DOTTED console scripts and this is the documented entry point.
                     # `mlx_\\w+` stopped at `mlx_lm` and then demanded whitespace it could never
                     # find — the most common real form was unmatchable until 2026-07-31.
                     ("mlx_lm.generate (dotted)", "mlx_lm.generate --model x")):
    _multi.write_text(f"#!/bin/sh\n{_line}\n")
    check(f"detector matches `{_tool}`", has(scan_fixture({"j": {"typecheck"}}), "post-merge:2"))
_multi.unlink()

# 1) used-not-declared: drop astro from web.techs (astro still in deps)
r = clone()
r["stacks"]["web"]["techs"] = [t for t in r["stacks"]["web"]["techs"] if t["name"] != "astro"]
f1 = write("used-not-declared.json", r)
code, d = run(f1)
check("used-not-declared: astro flagged, advisory exit 0",
      code == 0 and has(d["drift"], "used-not-declared `astro`"))
code, d = run(f1, "--enforce")
check("used-not-declared: --enforce BLOCKS drift → exit 1", code == 1 and has(d["drift"], "astro"))

# 2) declared-not-used: phantom framework in web.techs
r = clone()
r["stacks"]["web"]["techs"].append({"name": "phantom-fw", "detect": "dep:phantom-fw-xyz-000"})
f2 = write("declared-not-used.json", r)
code, d = run(f2)
check("declared-not-used: phantom flagged, advisory exit 0",
      code == 0 and has(d["drift"], "declared-not-used `phantom-fw`"))

# 3) command→recipe HARD FAIL: bind web.typecheck to a missing recipe
r = clone()
r["stacks"]["web"]["commands"]["typecheck"] = "no-such-recipe-zzz"
f3 = write("bad-recipe.json", r)
code, d = run(f3)
check("bad recipe: HARD FAIL without --enforce → exit 1",
      code == 1 and has(d["problems"], "does not exist"))

# 4) enforce_raw opt-in — the BLOCKING decision, which is `enforce and enforce_raw and raw`.
# The hook layer is clean now, so there is no live finding to trigger it; the seam is the scan
# itself, stubbed to return one finding while `main()` runs against the real registry and tree.
# Stubbing the measurement and asserting the DECISION keeps this honest: case 0b already proves
# the measurement, and a check that needed a real offender to exist could only be kept alive by
# never fixing one.
import contextlib as _ctx, io as _io


def main_with_raw(policy, *flags, findings=("x/.husky/pre-push:1 raw `pnpm` — route via a `just` recipe",)):
    real_scan, real_argv = _disc.scan_raw_invocations, sys.argv
    _disc.scan_raw_invocations = lambda _recipes: list(findings)
    sys.argv = ["discovery.py", "--policy", str(policy), "--json", *flags]
    try:
        buf = _io.StringIO()
        with _ctx.redirect_stdout(buf):
            code = _disc.main()
        return code, json.loads(buf.getvalue())
    finally:
        _disc.scan_raw_invocations, sys.argv = real_scan, real_argv


r = clone()
r["enforce_raw"] = True
f4 = write("enforce-raw.json", r)
code, d = main_with_raw(f4, "--enforce")
check("enforce_raw=true + --enforce: a raw invocation BLOCKS → exit 1",
      code == 1 and has(d["raw_invocations"], "raw `pnpm`"))
code, d = main_with_raw(f4)
# Red first, and it caught a live defect: the scan used to run ONLY under --enforce, so plain
# `just discovery` could never report a raw invocation — contradicting both the module docstring
# ("advisory always") and the comment at the call site. Invisible while the hook layer was clean.
check("enforce_raw=true WITHOUT --enforce: advisory only → exit 0, still REPORTED",
      code == 0 and d["raw_invocations"])
code, d = main_with_raw(REAL, "--enforce")
check("enforce_raw absent (the default): --enforce does NOT block on raw → exit 0",
      code == 0 and d["raw_invocations"])

# 5) exempt honored: exempt web raises no web findings, exit 0
r = clone()
r["exempt"]["web"] = "temporarily exempt for the proof"
f5 = write("exempt.json", r)
code, d = run(f5, "--enforce")
web_findings = has(d["drift"], "`web`") or ("web" in d.get("stacks", {}))
check("exempt stack: web skipped, exit 0", code == 0 and not web_findings)

# 6) mcp surface echoed for grounding
code, d = run(REAL)
check("mcp_enabled surfaced (codegraph among them)", "codegraph" in d.get("mcp_enabled", []))

# 7) review-gate hardening: a structurally broken registry reports cleanly (no KeyError)
bad = write("broken.json", {"project": "x", "stacks": {"web": {"runtime": "node", "techs": [],
                                                              "commands": {}, "enabled": True}}})
code, d = run(bad)
check("malformed registry: clean problems, exit 1, no traceback",
      code == 1 and has(d.get("problems", []), "missing required field") and "_raw" not in d)

# 8) JSONC (comments + trailing commas) parses; URLs with // survive
_p = FIX / "sample.jsonc"
_p.write_text('{ // c\n "imports": { "drizzle-orm/": "npm:d@1", "x": "https://esm.sh/x", },\n}')
_parsed = _disc.load_jsonc(_p)
check("JSONC: comments/trailing commas stripped, URL intact",
      set(_parsed["imports"]) == {"drizzle-orm/", "x"} and _parsed["imports"]["x"] == "https://esm.sh/x")

# 9) security-gate hardening: non-UTF-8 input must not crash the gate.
# UnicodeDecodeError is a ValueError, NOT an OSError — `except OSError` alone let a binary
# file in any scanned path (.husky hook, source tree, manifest) kill the run with a traceback.
_bin = FIX / "binary.json"
_bin.write_bytes(b"\x00\xff\xfe\x80")
check("binary/non-UTF-8 file: read_text -> None, node_deps -> empty, no crash",
      _disc.read_text(_bin) is None and _disc.node_deps(FIX) == set())

# 10) a missing binary degrades instead of raising
check("sh() on a missing binary returns (127, msg) instead of raising",
      _disc.sh("definitely-not-a-real-binary-xyz", "--version")[0] == 127)

# 11) the JSONC comment regex is linear (no catastrophic backtracking)
import time as _time
_line = '// ' + 'a"b"' * 4000 + 'c"'
_t0 = _time.time(); _disc.re.sub(r'(?<!:)//(?=(?:[^"]*"[^"]*")*[^"]*$).*$', "", _line); _dt = _time.time() - _t0
check(f"JSONC comment regex stays linear on 8k quotes ({_dt*1000:.1f} ms)", _dt < 1.0)

# ── T135 section 1: the `gates` phase map + reasoned exemptions ───────────────
# These assert the RED direction permanently. Task 1.6 was proved by hand against the live
# registry before `gates` existed; once the registry satisfies the rule that proof is gone,
# and a rule nobody can see fail is indistinguishable from a rule that never fires.
#
# Every case below is checked WITHOUT --enforce: a malformed registry is a hard problem, not
# advisory drift, so it must block in any mode.

# 12) unphased command role → hard fail (task 1.2 / AC4: there is no implicit default)
r = clone()
del r["stacks"]["web"]["gates"]["typecheck"]
code, d = run(write("unphased-role.json", r))
check("unphased role `typecheck` → exit 1, names the role",
      code == 1 and has(d["problems"], "command role `typecheck` has no phase"))

# 13) `gates` missing entirely → hard fail, and the message quantifies what is ungated.
# The expected count is DERIVED from the fixture, not hardcoded: asserting a literal made this
# check fail the moment a legitimate new role (`fmt-check`) was declared, which is a maintenance
# tax that teaches nothing.
r = clone()
n_roles = len(r["stacks"]["mlx"]["commands"])
del r["stacks"]["mlx"]["gates"]
code, d = run(write("no-gates.json", r))
check("missing `gates` → exit 1, reports how many roles are ungated",
      code == 1 and has(d["problems"], f"{n_roles} declared command role(s) have no phase"))

# 14) orphan phase: a gate for a role that is not declared → hard fail.
# This reads as coverage while gating nothing, so it is the mirror of case 12.
r = clone()
r["stacks"]["worker"]["gates"]["test"] = "pre-push"
code, d = run(write("orphan-phase.json", r))
check("orphan phase (gates role absent from commands) → exit 1",
      code == 1 and has(d["problems"], "orphan phase gates nothing"))

# 15) `manual` without a reason → hard fail (AC8: a deferral must carry its cause)
r = clone()
r["stacks"]["mlx"]["gates"]["lint"] = "manual"          # shorthand = no reason
code, d = run(write("manual-no-reason.json", r))
check("bare `manual` → exit 1 (deferral without a cause)",
      code == 1 and has(d["problems"], "deferred to `manual` without a reason"))

# 16) `manual` with a substantive reason → accepted
r = clone()
r["stacks"]["mlx"]["gates"]["lint"] = {
    "phase": "manual",
    "reason": "clippy needs compilation and the vendored mlx-rs clone does not compile",
}
code, d = run(write("manual-with-reason.json", r))
check("`manual` + reason → exit 0", code == 0 and not d["problems"])

# 17) an invalid phase name → hard fail (catches a typo like "precommit")
r = clone()
r["stacks"]["worker"]["gates"]["typecheck"] = "precommit"
code, d = run(write("bad-phase.json", r))
check("invalid phase `precommit` → exit 1", code == 1 and has(d["problems"], "invalid phase"))

# 18) an unknown command role → hard fail even though `gates` phases it consistently
r = clone()
r["stacks"]["worker"]["commands"]["typecheque"] = "typecheck-worker"
r["stacks"]["worker"]["gates"]["typecheque"] = "pre-push"
code, d = run(write("bad-role.json", r))
check("unknown command role → exit 1", code == 1 and has(d["problems"], "unknown command role"))

# 19-22) exemptions must carry a substantive, non-restating reason (task 1.3)
r = clone(); r["exempt"]["w0m-ext"] = ""
code, d = run(write("exempt-empty.json", r))
check("exempt with empty reason → exit 1", code == 1 and has(d["problems"], "missing a reason"))

r = clone(); r["exempt"]["w0m-ext"] = "w0m-ext"
code, d = run(write("exempt-restates.json", r))
check("exempt reason restating the key → exit 1",
      code == 1 and has(d["problems"], "merely restates the key"))

r = clone(); r["exempt"]["w0m-ext"] = "no build yet"
code, d = run(write("exempt-terse.json", r))
check("exempt reason too terse → exit 1", code == 1 and has(d["problems"], "record the condition"))

# A bare LIST of names is the shape the rule exists to reject — it records no decision at all.
r = clone(); r["exempt"] = ["wom7md", "w0m-ext"]
code, d = run(write("exempt-list.json", r))
check("exempt as a bare list → exit 1", code == 1 and has(d["problems"], "records no decision"))

# 23) These rules must hold when `jsonschema` is NOT importable. load_registry swallows
# ImportError and skips schema validation entirely, so a rule living only in the schema
# would silently stop applying on any host without the library — the vacuous-gate failure
# mode in AC7. check_structure is the always-run path; assert it directly.
_probs: list = []
_disc.check_structure(
    {"exempt": {"wom7md": "x"},
     "stacks": {"s": {"repo": "r", "path": ".", "runtime": "node", "justfile": "j",
                      "enabled": True, "commands": {"lint": "lint"}, "gates": {}}}},
    _probs,
)
check("rules fire via check_structure alone (no jsonschema needed)",
      has(_probs, "has no phase in `gates`") and has(_probs, "exempt `wom7md`"))

ok = all(results)
print(f"\n{'ALL PASS' if ok else 'FAILURES PRESENT'}  ({sum(results)}/{len(results)})")
sys.exit(0 if ok else 1)
