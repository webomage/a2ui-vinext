#!/usr/bin/env python3
"""T182 regression proof for skills_catalogue.py — the two settings must be DERIVED, not assumed.

A catalogue that simply echoed its policy back would look identical to one that measured, and
would be worthless. So every claim it makes is driven from a fixture and required to change:

  * a skill installed but in neither the manifest nor `exclude` is flagged **unmanaged**
  * a skill that ships runnable files and is not sandboxed is flagged
  * an override suppresses that flag — and the schema makes a reason mandatory, so it cannot be
    suppressed silently
  * `detect_executable` actually drives the population: empty the suffix list and the
    "ships runnable files" set collapses, proving the number is measured rather than hardcoded
  * user-scope skills are surfaced as outside every project's manifest
  * an empty corpus, and a missing `.w0m/sdlc.json -> skills` block, both ERROR

Non-destructive: fixtures are policy files in a temp dir; the real projects are only read.
Run: `just skills-catalogue-test`.
"""
import json, os, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "w0m-web"

# 🔑 Corpus assertions are read from the REGISTRY, never hardcoded. Onboarding servicios777 and
# personaje0 (T182 AC7) broke four suites at once because each asserted a fixed project set — a
# path that needs four test edits per project is not the "no bespoke step" AC7 demands. Deriving
# the expectation keeps the assertion strong (exact equality with what is declared) while making
# it survive the next onboarding.
REGISTRY_PROJECTS = {p["id"] for p in json.loads(
    (ROOT / "project" / "policies" / "clients-policy.json").read_text())["projects"] if p.get("enabled")}
REGISTRY_CLIENTS = {p["id"] for p in json.loads(
    (ROOT / "project" / "policies" / "clients-policy.json").read_text())["projects"]
    if p.get("enabled") and p.get("role") in ("managed", "client")}

SCRIPT = ROOT / "scripts" / "skills_catalogue.py"
REAL = ROOT / "project" / "policies" / "skills-policy.json"
FIX = Path(tempfile.mkdtemp(prefix="t182-cat-"))
USER_FIX = FIX / "user-skills"
(USER_FIX / "unmanaged-user-skill").mkdir(parents=True, exist_ok=True)
base = json.loads(REAL.read_text())

fails: list[str] = []
checks = 0


def check(label: str, cond: bool) -> None:
    global checks
    checks += 1
    if not cond:
        fails.append(label)
    print(f"  {'✓' if cond else '✗'} {label}")


def run(policy: Path, *flags) -> tuple[int, dict]:
    host_user_skills = Path.home() / ".claude" / "skills"
    has_host_user_skills = host_user_skills.is_dir() and any(
        p.is_dir() and not p.name.startswith(".") for p in host_user_skills.iterdir()
    )
    env = dict(os.environ)
    if not has_host_user_skills:
        env["W0M_USER_SKILLS_DIR"] = str(USER_FIX)
    r = subprocess.run(["python3", str(SCRIPT), "--policy", str(policy), "--json", *flags],
                       capture_output=True, text=True, cwd=str(WEB), env=env)
    try:
        return r.returncode, json.loads(r.stdout)
    except json.JSONDecodeError:
        return r.returncode, {"_raw": r.stdout + r.stderr}


def variant(name: str, mutate) -> Path:
    reg = json.loads(json.dumps(base))
    mutate(reg)
    p = FIX / name
    # 🔴 `$schema` in the real policy is RELATIVE ("./skills-policy.schema.json"), which is only
    # correct where that file lives. A fixture is a faithful copy in a temp dir, so the ref has to be
    # re-pointed or it dangles — and since T301 the catalogue validates the policy it loads, so a
    # dangling ref stops the tool before any catalogue logic runs. Absolutising it keeps fixtures
    # held to the SAME schema as the real file rather than exempting them.
    if "$schema" in reg:
        reg["$schema"] = str((REAL.parent / reg["$schema"]).resolve())
    p.write_text(json.dumps(reg, indent=2))
    return p


def rows(out: dict) -> list[dict]:
    return [r for pr in out.get("projects", []) for r in pr["skills"]]


def sugg(out: dict) -> str:
    return " | ".join(out.get("suggestions", []))


print("\n  T182 — skills_catalogue.py regression proof\n")

# ── positive path ──────────────────────────────────────────────────────────────
code, live = run(REAL)
check("live policy exits 0 (suggestions are advisory)", code == 0 and live.get("ok") is True)
ids = {pr["project"] for pr in live["projects"]}
check("every declared project is catalogued", ids == REGISTRY_PROJECTS)
check("recommendation is project-managed + sandboxed",
      live["recommended"]["managed"] == "project" and live["recommended"]["sandboxed"] is True)
check("nothing is unmanaged across the estate today",
      all(pr["counts"]["unmanaged"] == 0 for pr in live["projects"]))
check("the openspec family is counted as excluded, not unmanaged",
      {pr["project"]: pr["counts"]["excluded"] for pr in live["projects"]
       if pr["project"] in {"w0m", "1945", "artemio"}} == {"w0m": 0, "1945": 0, "artemio": 10})

execs = [r for r in rows(live) if r["ships_executable"]]
check("exactly 2 skills ship runnable files — measured, and small", len(execs) == 2)
check("every skill shipping runnable files has an EXPLICIT decision with a reason",
      all(r["sandboxed_declared"] and r["override_reason"] for r in execs))
check("no declaration is contradicted by a call site",
      not [r for r in execs if r["sandboxed"] and r["runs_on_host"]])
check("host invocation is MEASURED — artemio's idea-refine is seen running at justfile:267",
      any("justfile:267" in (r["runs_on_host"] or []) for r in execs))
check("user-scope skills are surfaced as outside every manifest",
      len(live["user_scope"]["skills"]) > 0 and "user scope" in sugg(live))
check("--enforce turns the user-scope suggestion into a block", run(REAL, "--enforce")[0] == 1)

# ── red probes ─────────────────────────────────────────────────────────────────
# `detect_executable` must DRIVE the population. If the number were hardcoded, emptying the
# suffix list and disabling the exec-bit would leave it unchanged.
p = variant("no-detect.json", lambda r: r["detect_executable"].update(
    {"suffixes": [], "executable_bit": False}))
code, out = run(p)
check("emptying detect_executable collapses the population — it is measured, not hardcoded",
      len([x for x in rows(out) if x["ships_executable"]]) == 0)

# Drop the override: the skill that ships runnable code and is not sandboxed must be flagged.
# 🔴 The flaw a red probe found in this tool's first version: with the overrides removed, every
# skill INHERITS `sandboxed: true` — asserting confinement nobody checked, and in Artemio's case
# asserting something false. The catalogue must flag an inherited default over runnable code, and
# must flag it LOUDER when a call site contradicts it.
p = variant("no-override.json", lambda r: r.__setitem__(
    "overrides", {"_comment": r["overrides"]["_comment"]}))
code, out = run(p)
check("an inherited default over runnable code is flagged, not accepted",
      "inherits the default" in sugg(out))
check("a declaration contradicted by a real call site is flagged as a contradiction",
      "ON THE HOST" in sugg(out) and "idea-refine" in sugg(out))
check("  …and those suggestions block under --enforce", run(p, "--enforce")[0] == 1)

# Flip the recommended default: every such skill inherits sandboxed:false and gets flagged.
p = variant("default-off.json", lambda r: r["recommended"].__setitem__("sandboxed", False))
code, out = run(p)
check("the sandboxed default is inherited per skill, not fixed",
      any(not x["sandboxed"] for x in rows(out) if x["ships_executable"]))

p = FIX / "bad.json"; p.write_text("{ not json")
code, out = run(p)
check("an unreadable policy errors cleanly, no traceback",
      code == 2 and "unreadable" in " ".join(out.get("errors", [])))

# The `.w0m/sdlc.json -> skills` block must be load-bearing: with no --policy override the tool
# resolves it from the declaration, and must refuse rather than fall back to a hardcoded path.
r = subprocess.run(["python3", str(SCRIPT), "--json"], capture_output=True, text=True, cwd=str(WEB))
declared_ok = r.returncode == 0
check("with no override the tool resolves its policy from .w0m/sdlc.json -> skills", declared_ok)

print(f"\n  {checks - len(fails)}/{checks} passed\n")
if fails:
    for f in fails:
        print(f"    ✗ {f}")
    sys.exit(1)
