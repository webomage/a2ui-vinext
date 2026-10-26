#!/usr/bin/env python3
"""T182 AC1 regression proof for client_inventory.py — drives it on fixtures, asserts exits.

The point of this file is that every integrity check is **observed failing**. A guard that
has never been seen to fire is not evidence that it works; the estate has repeatedly shipped
gates that were structurally incapable of failing, so each one here gets a red probe:

  * the SUBDIRECTORY trap — a declared root that is a subdirectory of a real repo. `git -C`
    happily reports a branch and a remote for it. This must HARD FAIL, not measure the parent.
  * the EMPTY corpus, and the single-project corpus — both must error, never print a green
    nothing.
  * zero estates and two estates — the contract must be unambiguous.
  * a missing root, and an unreadable registry.

Plus the positive path: the live registry reproduces the three-project baseline, resolves an
import-directive CLAUDE.md by content, and separates governed skills from the runtime surface.

Non-destructive: fixtures live in a temp dir and point at real repos read-only.
Run: `just client-inventory-test`.
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

SCRIPT = ROOT / "scripts" / "client_inventory.py"
REAL = ROOT / "project" / "policies" / "clients-policy.json"
FIX = Path(tempfile.mkdtemp(prefix="t182-"))
base = json.loads(REAL.read_text())

fails: list[str] = []
checks = 0


def check(label: str, cond: bool) -> None:
    global checks
    checks += 1
    if not cond:
        fails.append(label)
    print(f"  {'✓' if cond else '✗'} {label}")


def write(name: str, reg: dict) -> Path:
    p = FIX / name
    p.write_text(json.dumps(reg, indent=2))
    return p


def run(registry: Path) -> tuple[int, dict]:
    r = subprocess.run(
        ["python3", str(SCRIPT), "--registry", str(registry), "--json"],
        capture_output=True, text=True, cwd=str(WEB),
    )
    try:
        return r.returncode, json.loads(r.stdout)
    except json.JSONDecodeError:
        return r.returncode, {"_raw": r.stdout + r.stderr}


def projects(reg: dict) -> list[dict]:
    return [dict(p) for p in reg["projects"]]


print("\n  T182 AC1 — client_inventory.py regression proof\n")

# ── positive path: the live registry ───────────────────────────────────────────
code, live = run(REAL)
check("live registry exits 0", code == 0)
check("live registry reports ok", live.get("ok") is True)
by_id = {p["id"]: p for p in live.get("projects", [])}
check("every declared project is measured — set read from the registry",
      set(by_id) == REGISTRY_PROJECTS)
check("contract is read from the estate",
      len(live.get("contract", {}).get("keys", [])) >= 24)
check("estate declaration matches the contract exactly (0 missing, 0 extra)",
      by_id["w0m"]["declaration"]["missing"] == [] and by_id["w0m"]["declaration"]["extra"] == [])
check("w0m role is 'w0m' and has all 14 services enabled",
      by_id["w0m"]["role"] == "w0m" and by_id["w0m"].get("services_enabled") == 14)
check("1945 has deploys disabled with reason",
      by_id["1945"]["services"].get("deploys", {}).get("enabled") is False
      and "Owner-write-only" in by_id["1945"]["services"].get("deploys", {}).get("reason", ""))
check("bridgeroad role is self-managed with 4 enabled services",
      by_id["bridgeroad"]["role"] == "self-managed" and by_id["bridgeroad"].get("services_enabled") == 4)
# 1945 was remediated to full client-profile conformance in T279/T280 (0 divergent keys, $schema present).
check("1945 reports 0 divergent keys and has $schema",
      len(by_id["1945"]["declaration"]["extra"]) == 0
      and by_id["1945"]["declaration"]["has_schema"] is True)
# T182 AC9: every shared client gap must be accounted for in client-profile.json
profile_data = json.loads((WEB / "project" / "client-profile.json").read_text())
accounted = set(profile_data.get("keys", {})) | set(profile_data.get("excluded", {}))
unaccounted = set(live.get("shared_client_gaps", [])) - accounted
check("shared client gaps are all accounted for in client-profile.json (0 unaccounted)",
      len(unaccounted) == 0)

# The retracted-claim guard: an 11-byte CLAUDE.md that is an import directive must be
# reported by what it RESOLVES to, not by its own size.
art = by_id["artemio"]["claude_md"]
check("artemio CLAUDE.md is recognised as an import directive", len(art["imports"]) == 1)
check("the import resolves", art["resolves"] is True)
check("effective size is the resolved target, not the 11 bytes",
      art["bytes"] == 11 and art["effective_bytes"] > 3000)

# A CLAUDE.md of real prose must NOT be mistaken for a directive.
check("prose CLAUDE.md is not treated as a directive",
      by_id["w0m"]["claude_md"]["imports"] == []
      and by_id["w0m"]["claude_md"]["resolves"] is None)

# Governed set vs runtime surface must not be conflated.
# Artemio's skills are governed under manifest + lock (56 declared real dirs in .agents/skills,
# and .claude/skills holds 56 symlinks + 10 openspec real dirs).
art_decl = by_id["artemio"]["skills"]["declared"]
check("artemio's runtime skills are governed — manifest + lock, 56 declared",
      by_id["artemio"]["skills"]["manifest"] is True
      and by_id["artemio"]["skills"]["lock"] is True
      and art_decl == 56
      and by_id["artemio"]["skills"]["claude_skills"]["total"] == art_decl + 10)
check("governed skills in .agents/skills are separated from runtime symlinks and CLI-owned real dirs",
      by_id["w0m"]["skills"]["agents_skills"]["real_dirs"] >= by_id["w0m"]["skills"]["declared"]
      and by_id["artemio"]["skills"]["claude_skills"]["symlinks"] > 0
      and by_id["artemio"]["skills"]["claude_skills"]["real_dirs"] > 0)

# 🔴 The blind spot this tool shipped with. It checked `.agents/skills` only and reported 0 for
# Artemio — true for `.agents`, and blind to the 33 real dirs in `.agent/skills` (singular), the
# retired pre-T127 layout. A second tree holding stale copies is precisely what a refresh must
# not miss, since whichever path an agent resolves first wins.
check("the retired path is ENUMERATED for every project — the field exists, not omitted",
      all("retired_agent_skills" in by_id[p]["skills"] for p in by_id))
check("no project still carries a retired .agent/skills tree",
      all(by_id[p]["skills"]["retired_agent_skills"]["total"] == 0 for p in by_id))
# Artemio was migrated to the two-layer layout: 56 governed real dirs in
# .agents/skills, and .claude/skills as 56 symlinks + the 10 openspec real dirs.
check("artemio now matches the estate layout — 56 governed, 56 symlinks + 10 real dirs",
      by_id["artemio"]["skills"]["agents_skills"]["total"] == art_decl
      and by_id["artemio"]["skills"]["claude_skills"]["symlinks"] == art_decl
      and by_id["artemio"]["skills"]["claude_skills"]["real_dirs"] == 10)

# ── red probes: every integrity check observed FAILING ─────────────────────────
# The subdirectory trap. `project/` sits inside w0m-web, a real repo — git answers about
# the parent. Measuring it would look authoritative and describe nothing declared.
sub = dict(base)
sub["projects"] = projects(base)
sub["projects"][0]["root"] = "w0m-web/project"
code, out = run(write("subdir.json", sub))
check("SUBDIRECTORY root hard-fails (does not measure the parent repo)", code == 2)
check("  …and the error names it as a subdirectory",
      any("SUBDIR" in e.upper() or "subdirectory" in e.lower() for e in out.get("errors", [])))

empty = dict(base); empty["projects"] = []
code, out = run(write("empty.json", empty))
check("EMPTY corpus errors instead of printing a green nothing", code == 2)

single = dict(base); single["projects"] = projects(base)[:1]
code, _ = run(write("single.json", single))
check("SINGLE-project corpus errors (a diff needs something to diff)", code == 2)

no_estate = dict(base); no_estate["projects"] = projects(base)
for p in no_estate["projects"]:
    p["role"] = "managed"
code, _ = run(write("no-estate.json", no_estate))
check("ZERO estates errors (nothing to diff against)", code == 2)

two_estates = dict(base); two_estates["projects"] = projects(base)
two_estates["projects"][1]["role"] = "w0m"
code, _ = run(write("two-estates.json", two_estates))
check("TWO estates errors (ambiguous contract)", code == 2)

missing = dict(base); missing["projects"] = projects(base)
missing["projects"][1]["root"] = "../../_self/does-not-exist"
code, _ = run(write("missing.json", missing))
check("MISSING root hard-fails", code == 2)

# A disabled project is skipped, but disabling down to one still trips the corpus assertion —
# so `enabled: false` cannot be used to quietly empty the gate.
disabled = dict(base); disabled["projects"] = projects(base)
for p in disabled["projects"][1:]:
    p["enabled"] = False
code, _ = run(write("disabled.json", disabled))
check("disabling clients down to one still errors (no quiet opt-out)", code == 2)

# ── T268 — the WORKSPACE shape, and the git-root guarantee moving rather than relaxing ───────
#
# 🔴 Every probe here has a paired opposite. A workspace mode that only ever passes would be
# indistinguishable from deleting the check, which is the failure this whole file exists against.
schema_file = ROOT / "project" / "policies" / "clients-policy.schema.json"
if schema_file.exists() and not (FIX / "clients-policy.schema.json").exists():
    (FIX / "clients-policy.schema.json").symlink_to(schema_file)

ws_non_repo = FIX / "ws_non_repo"
ws_non_repo.mkdir(exist_ok=True)
if not (ws_non_repo / "web").exists():
    (ws_non_repo / "web").symlink_to(WEB)
if not (ws_non_repo / "api").exists():
    (ws_non_repo / "api").symlink_to(WEB.parent / "w0m-api")

def ws_project(**over):
    """A workspace-shaped entry pointing at a real non-repo workspace root."""
    d = {"id": "wsprobe", "role": "client", "root": str(ws_non_repo), "enabled": True,
         "runtime": {"substrate": "host"},
         "repos": {"web": "web", "api": "api"}, "canonical_repo": "web"}
    d.update(over)
    return d

def with_ws(name, **over):
    reg = dict(base); reg["projects"] = projects(base) + [ws_project(**over)]
    return write(name, reg)

code, out = run(with_ws("ws-ok.json"))
check("WORKSPACE: a root that is NOT a repo is accepted when its repos are", code == 0)
_ws = next((x for x in out.get("projects", []) if x["id"] == "wsprobe"), {})
_wg = _ws.get("git", {})
check("WORKSPACE: the mode is recorded on the project", _wg.get("mode") == "workspace")
check("WORKSPACE: every declared repo is measured, not just the canonical one",
      set(_wg.get("repos", {})) == {"web", "api"})
check("WORKSPACE: the canonical repo is named", _wg.get("canonical_repo") == "web")
check("WORKSPACE: a non-repo workspace root is reported as such, not hidden",
      _wg.get("workspace_root_is_repo") is False)
check("WORKSPACE: per-project facts come from the CANONICAL repo",
      _ws.get("root", "").endswith("web"))

code, _ = run(with_ws("ws-badrepo.json", repos={"web": "web", "nope": "web/project"}))
check("WORKSPACE: a declared repo that is a SUBDIRECTORY hard-fails", code == 2)

code, _ = run(with_ws("ws-missingrepo.json", repos={"web": "web", "ghost": "does-not-exist"}))
check("WORKSPACE: a declared repo that does not exist hard-fails", code == 2)

code, _ = run(with_ws("ws-badcanon.json", canonical_repo="nosuch"))
check("WORKSPACE: canonical_repo outside `repos` hard-fails", code == 2)

code, _ = run(with_ws("ws-nomode.json", repos=None))
check("CONTROL: the same root (.) with NO `repos` still hard-fails as simple", code == 2)

bad = FIX / "bad.json"; bad.write_text("{ not json")
code, out = run(bad)
check("unreadable registry errors cleanly, no traceback", code == 2 and "errors" in out)

# ── T297: project execution runtime & sandboxing tests ──────────────────────────
# AC1/AC2: Project lacking runtime block fails schema validation
def without_runtime(name):
    reg = dict(base)
    projs = projects(base)
    for p in projs:
        p.pop("runtime", None)
    reg["projects"] = projs
    return write(name, reg)

code, out = run(without_runtime("missing-runtime.json"))
check("T297 AC2: project lacking explicit runtime fails validation", code != 0)

# AC1: Invalid substrate enum fails schema validation
def with_bad_substrate(name):
    reg = dict(base)
    p0 = dict(reg["projects"][0])
    p0["runtime"] = {"substrate": "cloud-docker"}
    reg["projects"] = [p0] + reg["projects"][1:]
    return write(name, reg)

code, out = run(with_bad_substrate("bad-substrate.json"))
check("T297 AC1: invalid substrate enum fails validation", code != 0)

# AC4: Tart runtime naming non-existent guest VM hard-fails
def with_missing_guest(name):
    reg = dict(base)
    p0 = dict(reg["projects"][0])
    p0["runtime"] = {"substrate": "tart-linux", "guest_name": "ghost-vm-does-not-exist-9999"}
    reg["projects"] = [p0] + reg["projects"][1:]
    return write(name, reg)

code, out = run(with_missing_guest("missing-guest.json"))
check("T297 AC4: tart-* runtime naming missing guest VM hard-fails", code != 0)
# ── T299: Base role plus per-service switches (AC8 Red Probes) ─────────────────
# AC8 probe 1: project declaring unknown service fails validation
def with_unknown_service(name):
    reg = dict(base)
    projs = projects(base)
    projs[1]["services"] = {
        "quantum_teleportation": {
            "enabled": True,
            "reason": "Quantum teleportation is required for superluminal deployments.",
        }
    }
    reg["projects"] = projs
    return write(name, reg)

code, out = run(with_unknown_service("unknown-service.json"))
check("T299 AC8 probe 1: project declaring unknown service fails validation",
      code == 2 and any("overrides unknown service 'quantum_teleportation'" in e for e in out.get("errors", [])))

# AC8 probe 2: override without reason (or reason < 20 chars) fails validation
def with_short_reason(name):
    reg = dict(base)
    projs = projects(base)
    projs[1]["services"] = {
        "deploys": {
            "enabled": False,
            "reason": "too short",
        }
    }
    reg["projects"] = projs
    return write(name, reg)

code, out = run(with_short_reason("short-reason.json"))
check("T299 AC8 probe 2: service override without reason (min 20 chars) fails validation",
      code == 2 and any("requires a reason (min 20 chars)" in e for e in out.get("errors", [])))

# AC8 probe 3: project declaring role outside enum fails validation
def with_invalid_role(name):
    reg = dict(base)
    projs = projects(base)
    projs[1]["role"] = "super-admin-tier"
    reg["projects"] = projs
    return write(name, reg)

code, out = run(with_invalid_role("invalid-role.json"))
check("T299 AC8 probe 3: project declaring role outside enum fails validation",
      code == 2 and any("invalid role 'super-admin-tier'" in e for e in out.get("errors", [])))

# AC8 probe 4: project with 0 services enabled is legal and distinct from absent (exits 0, services_enabled == 0)
def with_zero_services(name):
    reg = dict(base)
    projs = projects(base)
    zero_services = {
        s: {
            "enabled": False,
            "reason": f"Explicitly disabled service {s} for testing zero-services contract posture.",
        }
        for s in reg.get("services", {})
    }
    projs[1]["services"] = zero_services
    reg["projects"] = projs
    return write(name, reg)

code, out = run(with_zero_services("zero-services.json"))
p1 = next((p for p in out.get("projects", []) if p["id"] == base["projects"][1]["id"]), None) if code == 0 else None
check("T299 AC8 probe 4: project with 0 services enabled is legal and distinct from absent",
      code == 0 and p1 is not None and p1.get("services_enabled") == 0 and p1.get("services_total") == 14)


print(f"\n  {checks - len(fails)}/{checks} passed\n")
if fails:
    for f in fails:
        print(f"    ✗ {f}")
    sys.exit(1)
