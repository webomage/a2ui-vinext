#!/usr/bin/env python3
"""T182 AC2 regression proof for client_profile_check.py.

AC2's whole value is that a profile key cannot claim a gate it does not have. That claim is
only worth something if the check is observed REJECTING each way it can be false, so every
defect below is manufactured and required to fail:

  * a profile key whose gate names a recipe that does not exist
  * a profile key whose gate script does not read the key   <- the central claim
  * a required key whose gate is fail-open (`on_absent: skip`)
  * a contract key left in no tier, and a profile key absent from the contract
  * a key both in the profile and excluded
  * an empty profile

Plus the positive path on the live profile, and the reporting of dangling `$schema` refs.

Non-destructive: fixtures are derived from the live profile into a temp dir.
Run: `just client-profile-test`.
"""
import json, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "wom7web"

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

SCRIPT = ROOT / "scripts" / "client_profile_check.py"
REAL = WEB / "project" / "client-profile.json"
FIX = Path(tempfile.mkdtemp(prefix="t182-ac2-"))
base = json.loads(REAL.read_text())

fails: list[str] = []
checks = 0


def check(label: str, cond: bool) -> None:
    global checks
    checks += 1
    if not cond:
        fails.append(label)
    print(f"  {'✓' if cond else '✗'} {label}")


def run(profile: Path, *flags) -> tuple[int, dict]:
    r = subprocess.run(
        ["python3", str(SCRIPT), "--profile", str(profile), "--json", *flags],
        capture_output=True, text=True, cwd=str(WEB),
    )
    try:
        return r.returncode, json.loads(r.stdout)
    except json.JSONDecodeError:
        return r.returncode, {"_raw": r.stdout + r.stderr}


def variant(name: str, mutate) -> Path:
    reg = json.loads(json.dumps(base))       # deep copy
    mutate(reg)
    p = FIX / name
    p.write_text(json.dumps(reg, indent=2))
    return p


def errs(out: dict) -> str:
    return " | ".join(out.get("errors", []))


print("\n  T182 AC2 — client_profile_check.py regression proof\n")

# ── positive path ──────────────────────────────────────────────────────────────
code, live = run(REAL)
check("live profile passes", code == 0 and live.get("ok") is True)
# `profile` joined the required tier on 2026-08-30 (two declared base modes), making it 9.
check("required tier is the 9 keys with a verified fail-closed gate",
      live["required"] == ["$schema", "mcp", "profile", "repos", "secrets", "skills", "stacks",
                           "state_surface", "toolchain"])
# `skills` earned the required tier the same way as the rest: its gate refuses to guess a policy
# path and stops when the block is absent — observed doing exactly that before the key existed.
check("`skills` is required — the catalogue gate fails closed on its absence",
      "skills" in live["required"])
# The corrections the red probes forced. `project` LOOKED like the best-gated key in the
# contract (a quoted-word scan reported 19 readers); every one was the `project/` directory
# path. `commands` is enforced, but through stacks-policy.json, not the declaration.
check("`project` is excluded — its apparent readers were all path segments",
      "project" in live["excluded"])
check("`commands` is excluded — read from stacks-policy.json, not the declaration",
      "commands" in live["excluded"])
check("required + optional + excluded covers the contract exactly",
      len(live["required"]) + len(live["optional"]) + len(live["excluded"])
      == live["contract_keys"])
check("every profile key's gate verified from source",
      len(live["gates_verified"]) == live["profile_keys"])
check("`preflight` is excluded, not required — it has no reader at all",
      "preflight" in live["excluded"] and "preflight" not in live["required"])
check("`iac` is optional, not required — its gate fails open",
      "iac" in live["optional"])

# A vendored profile schema must not merely RESOLVE — it must still BE the profile schema. A
# copy that drifts validates against something the estate no longer publishes, which is the
# stale-pin shape. Artemio vendors it, so the row exists and must report no drift.
art_row = next((r for r in live["schema_refs"] if r["id"] == "artemio"), None)
check("a client's vendored $schema resolves and has not drifted",
      art_row is not None and art_row["resolves"] and art_row["drifted"] is False)

# The dangling-$schema finding: reported, and blocking only under --enforce.
dangling = [r for r in live["schema_refs"] if not r["resolves"]]
# w0m resolved via .w0m/sdlc.schema.json (T301) and Artemio vendors the schema; 1945 still has none.
check("the still-unvalidated declaration (1945) is reported",
      len(dangling) == 1 and dangling[0]["id"] == "1945")
check("findings are advisory by default", code == 0 and live.get("findings"))
code_e, _ = run(REAL, "--enforce")
check("--enforce makes the dangling $schema block", code_e == 1)

# 🔴 Phase 7 — the profile must validate CLIENTS, not just itself, and must be honest about how
# much of it can even be enforced at one. Measured 2026-08-09: only 2 of 8 required keys have a
# gate that takes a project selector; the other 6 read w0m's own sdlc.json from a constant, so
# they enforce their key FOR W0M and cannot check a client at all.
# 2026-08-09: all five remaining gates were made project-scoped; `profile` was added 2026-08-30
# (gated at install time by `skills-install-generic` / `install_generic.ts` rather than `--project`).
check("every CLI-gated required key has a gate that can be pointed at a client",
      live["client_capable_required"] == [k for k in live["required"] if k != "profile"])
check("only `profile` (install-time gate) is outside --project CLI scope",
      live["estate_scoped_required"] == ["profile"])
# `state_surface` moved from `state-check` to `state-bounds` on 2026-08-09: state_doctor enforces
# it for w0m only, so naming it claimed enforcement that could never reach a client.
check("state_surface's gate is the client-capable one, not state_doctor",
      base["keys"]["state_surface"]["gate"]["recipe"] == "state-bounds")
check("every declared client is validated against the profile",
      {c["id"] for c in live["clients"]} == REGISTRY_CLIENTS)
# 🟢 Artemio became the FIRST client to satisfy the profile (2026-08-09). The assertion is now
# per-client rather than "they all fail", so the milestone is pinned and a regression in either
# direction shows up: Artemio silently losing a key, or 1945 silently appearing to pass.
by_client = {c["id"]: c for c in live["clients"]}
check("artemio CONFORMS — every required key declared",
      by_client["artemio"]["conforms"] and by_client["artemio"]["missing_required"] == [])
check("1945 does not, and its missing keys are named",
      not by_client["1945"]["conforms"]
      and by_client["1945"]["missing_required"] == ["$schema", "mcp", "profile", "stacks",
                                                    "state_surface", "toolchain"])

# ── red probes: each defect manufactured and required to fail ──────────────────
def set_recipe(reg, key, recipe):
    reg["keys"][key]["gate"]["recipe"] = recipe

p = variant("bad-recipe.json", lambda r: set_recipe(r, "stacks", "no-such-recipe-xyz"))
code, out = run(p)
check("a gate naming a NON-EXISTENT recipe fails", code == 1 and "not a recipe" in errs(out))

p = variant("wrong-script.json",
            lambda r: r["keys"]["stacks"]["gate"].update(
                {"script": "scripts/version_doctor.py"}))
code, out = run(p)
check("a gate script that does NOT read its key fails",
      code == 1 and "does NOT read the key" in errs(out))

# 🔑 The false positive that forced the tightened matcher. client_inventory.py contains the
# string "project" twice — as a PATH SEGMENT (CANONICAL / "project" / …) and as a table
# header (f"{'project':10}") — and the first version of reads_key() accepted both as a read.
# A gate must not be credited for merely containing the word.
p = variant("path-segment.json", lambda r: r["keys"].__setitem__("stacks", {
    **r["keys"]["stacks"],
    "gate": {"recipe": "client-inventory", "script": "scripts/client_inventory.py"}}))
code, out = run(p)
check("a script that only MENTIONS the key (path segment / header) is not a reader",
      code == 1 and "does NOT read the key" in errs(out))

p = variant("missing-script.json",
            lambda r: r["keys"]["stacks"]["gate"].update({"script": "scripts/nope.py"}))
code, out = run(p)
check("a gate script that does not exist fails", code == 1 and "does not exist" in errs(out))

p = variant("failopen.json",
            lambda r: r["keys"]["secrets"]["gate"].update({"on_absent": "skip"}))
code, out = run(p)
check("a REQUIRED key with a fail-open gate fails",
      code == 1 and "FAILS OPEN" in errs(out))

p = variant("uncovered.json", lambda r: r["excluded"].pop("preflight"))
code, out = run(p)
check("a contract key left in NO tier fails", code == 1 and "in no tier" in errs(out))

p = variant("phantom.json", lambda r: r["excluded"].update(
    {"not_a_real_key": {"reason": "x", "promote_when": "y"}}))
code, out = run(p)
check("a profile key absent from the contract fails",
      code == 1 and "absent from the contract" in errs(out))

p = variant("overlap.json", lambda r: r["excluded"].update(
    {"stacks": {"reason": "x", "promote_when": "y"}}))
code, out = run(p)
check("a key both in the profile and excluded fails",
      code == 1 and "both in the profile and excluded" in errs(out))

p = variant("empty.json", lambda r: r.update({"keys": {}}))
code, out = run(p)
check("an EMPTY profile fails rather than passing vacuously",
      code == 1 and "declares no keys" in errs(out))


# A `client_scoped: true` claim must be supported by the script. `iac`'s gate, w0m_audit.py,
# reads w0m's declaration from a module constant and takes no project selector — verified here
# rather than assumed, because the original probe used sdlc_doctor.py and stopped firing the day
# that script GAINED --project. A red probe that silently stops being red is worse than none.
assert "--project" not in (ROOT / "scripts/w0m_audit.py").read_text(), \
    "w0m_audit.py gained --project — this probe needs a different unscoped script"
p = variant("false-client-scope.json",
            lambda r: r["keys"]["iac"]["gate"].__setitem__("client_scoped", True))
code, out = run(p)
check("a false client_scoped claim is rejected",
      code == 1 and "takes no project selector" in errs(out))

# If NO required key had a client-capable gate, the profile would be a checklist wearing a
# gate's clothes — that must be an error, not a quiet pass.
def strip_scope(r):
    for k in r["keys"]:
        r["keys"][k]["gate"]["client_scoped"] = False
p = variant("no-client-gate.json", strip_scope)
code, out = run(p)
check("a profile with NO client-capable gate errors — it would be a checklist",
      code == 1 and "checklist" in errs(out))

bad = FIX / "bad.json"; bad.write_text("{ not json")
code, out = run(bad)
check("an unreadable profile errors cleanly, no traceback",
      code == 1 and "unreadable" in errs(out))

print(f"\n  {checks - len(fails)}/{checks} passed\n")
if fails:
    for f in fails:
        print(f"    ✗ {f}")
    sys.exit(1)
