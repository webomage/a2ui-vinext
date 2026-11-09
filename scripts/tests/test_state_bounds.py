#!/usr/bin/env python3
"""T182 regression proof for state_bounds.py (Phase 5 / AC5).

The one thing this gate must not do is treat an UNDECLARED project as fine. That is exactly how
T177 recurred: nothing obliged a client to declare `state_surface`, so T174's retention fix had
nothing to attach to, and every tool that skipped undeclared projects reported the estate as
healthy while 1945 grew past half a megabyte.

So the probes are:
  * an undeclared project is reported as a finding, not skipped
  * bounds come from each project's OWN declaration — change the estate's and the client verdicts
    do not move; the estate's own does
  * an over-budget file is caught, and blocks under --enforce
  * an empty candidate list, and a missing root, ERROR rather than reporting health

Non-destructive: fixtures are registries in a temp dir; real projects are only read.
Run: `just state-bounds-test`.
"""
import json, subprocess, sys, tempfile
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

SCRIPT = ROOT / "scripts" / "state_bounds.py"
REG = ROOT / "project" / "policies" / "clients-policy.json"
FIX = Path(tempfile.mkdtemp(prefix="t182-sb-"))

fails: list[str] = []
checks = 0


def check(label: str, cond: bool) -> None:
    global checks
    checks += 1
    if not cond:
        fails.append(label)
    print(f"  {'✓' if cond else '✗'} {label}")


def run(*flags) -> tuple[int, dict]:
    r = subprocess.run(["python3", str(SCRIPT), "--json", *flags],
                       capture_output=True, text=True, cwd=str(WEB))
    try:
        return r.returncode, json.loads(r.stdout)
    except json.JSONDecodeError:
        return r.returncode, {"_raw": r.stdout + r.stderr}


print("\n  T182 — state_bounds.py regression proof\n")

code, live = run()
by = {p["project"]: p for p in live.get("projects", [])}
check("exits 0 by default — advisory", code == 0)
check("every declared project is audited", set(by) == REGISTRY_PROJECTS)

# 🔴 The probe that matters. Flattened k7 umbrella now declares bounds and is measured within them.
check("k7 declares state_surface bounds and is measured within them", by["k7"]["verdict"] == "within")
# 🔴 The OVER probe is a FIXTURE, not an assertion about a live client. It used to read
# `by["artemio"]["verdict"] == "over"` — true when it was written on 2026-08-09, and RED by
# 2026-08-14 because Artemio was rotated down to 50,850 B under its 81,920 B bound. That is the
# gate SUCCEEDING, and the probe reported it as the tool breaking. A regression probe pinned to
# mutable third-party data inverts its own signal: the greener the estate gets, the redder it goes.
# ⇒ The registry-derived lesson at the top of this file (never hardcode the corpus) applies one
# level deeper — never hardcode a VERDICT either. See the fixture block below for the real probe.
check("client projects are MEASURED — the files are named and sized",
      by["1945"]["largest_bytes"] > 10_000 and by["artemio"]["largest_bytes"] > 0)
check("the estate, which declares bounds, is judged against them",
      by["w0m"]["declared"] is True and by["w0m"]["max_bytes"] == 81920)
check("1945's three memory files are all counted, not just STATE.md",
      len(by["1945"]["files"]) == 3 and by["1945"]["total_bytes"] > 100_000)
check("--enforce blocks while any project is undeclared or over", run("--enforce")[0] == 1)

# Bounds must come from each project's OWN declaration, not a constant in the tool.
check("each project's limit is read from its own sdlc.json",
      by["w0m"]["max_bytes"] == 81920 and by["1945"]["max_bytes"] == 81920
      and by["bridgeroad"]["max_bytes"] == 65536 and by["k7"]["max_bytes"] == 65536)

# ── red probes: the corpus assertions ──────────────────────────────────────────
import shutil
reg = json.loads(REG.read_text())


def with_registry(name: str, mutate):
    """state_bounds reads the registry from a fixed path, so drive it by swapping the file in a
    copy of the tree… which is heavy. Instead assert the guards directly on the loaded module."""
    r = json.loads(json.dumps(reg))
    mutate(r)
    p = FIX / name
    p.write_text(json.dumps(r, indent=2))
    return p


sys.path.insert(0, str(ROOT / "scripts"))
import state_bounds as sb  # noqa: E402

orig = sb.REGISTRY
try:
    sb.REGISTRY = with_registry("no-candidates.json",
                                lambda r: r.__setitem__("state_surface_candidates", []))
    rows, errs = sb.audit()
    check("an EMPTY candidate list errors — it would inspect nothing and call it health",
          not rows and any("inspect nothing" in e for e in errs))

    sb.REGISTRY = with_registry("no-projects.json", lambda r: r.__setitem__("projects", []))
    rows, errs = sb.audit()
    check("an EMPTY project set errors", not rows and any("not a pass" in e for e in errs))

    def break_root(r):
        for p in r["projects"]:
            if p["id"] == "artemio":
                p["root"] = "../../_self/does-not-exist"
    sb.REGISTRY = with_registry("bad-root.json", break_root)
    rows, errs = sb.audit()
    check("a MISSING root errors rather than being skipped",
          not rows and any("does not exist" in e for e in errs))

    # The OVER verdict, proven against a project built for the purpose: a declared bound of 1 byte
    # and a file larger than it. Deterministic, and it cannot be turned green by anyone tidying
    # their STATE.md.
    breach = FIX / "breaching-project"
    (breach / ".w0m").mkdir(parents=True, exist_ok=True)
    (breach / ".w0m" / "sdlc.json").write_text(json.dumps(
        {"state_surface": {"file": "STATE.md", "retention": {"max_bytes": 1, "max_lines": 1}}}))
    (breach / "STATE.md").write_text("x" * 4096)

    def point_at_breach(r):
        for p_ in r["projects"]:
            if p_["id"] == "artemio":
                p_["root"] = str(breach)
    sb.REGISTRY = with_registry("breaching.json", point_at_breach)
    rows, errs = sb.audit()
    row = next((x for x in rows if x["project"] == "artemio"), None)
    check("a declared-but-breaching project is reported OVER, not passed",
          row is not None and row["verdict"] == "over" and row["over"])
    check("...and --enforce is what makes that finding block",
          row is not None and row["declared"] is True and row["max_bytes"] == 1)

    sb.REGISTRY = FIX / "unreadable.json"
    (FIX / "unreadable.json").write_text("{ not json")
    rows, errs = sb.audit()
    check("an unreadable registry errors cleanly", not rows and errs)
finally:
    sb.REGISTRY = orig

print(f"\n  {checks - len(fails)}/{checks} passed\n")
if fails:
    for f in fails:
        print(f"    ✗ {f}")
    sys.exit(1)
