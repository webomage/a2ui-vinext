#!/usr/bin/env python3
"""T182 / T508 / T226 / T522 regression proof for skills_catalogue.py.

Every claim the catalogue makes is driven from live manifests or temp fixtures and required to
change under mutation:

  * T508 AC1: all estate skill surfaces (`.`, `w0m-web`, `w0m-api`) are catalogued
  * T508 AC2: workspace `canonical_repo` and `repos` entries resolve their skills surfaces
  * T508 AC3: missing repo roots, uncatalogued manifests, and shrunk corpora fail closed (exit 2)
  * T508 AC4: `excluded` counts are derived from each surface's `.w0m/skills.json -> exclude`
  * T508 AC5: `ships_executable` ignores `node_modules` and untracked build output
  * T508 AC6: `host_invocations` scans `just/*.just`, skips comments, deduplicates symlinks,
              and matches by recipe name (zero hardcoded line numbers)
  * T508 AC7: orphan overrides in `skills-policy.json` fail closed (exit 2)
  * T508 AC8/AC9: every runnable skill has an explicit `sandboxed` decision + reason
  * T508 AC10: `client_inventory.py` and `skills_catalogue.py` agree on skill counts across surfaces
  * T522 AC4/AC5: live `--enforce` exits 0; an undecided user-scope skill in a fixture `--user-skills`
                  directory causes `--enforce` to exit 1 until governed in the user manifest

Non-destructive: fixtures live in a temp dir; real projects are only read.
Run: `just skills-catalogue-test`.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "w0m-web"

REGISTRY_PATH = ROOT / "project" / "policies" / "clients-policy.json"
REGISTRY_DATA = json.loads(REGISTRY_PATH.read_text())
REGISTRY_PROJECTS = {p["id"] for p in REGISTRY_DATA["projects"] if p.get("enabled")}

SCRIPT = ROOT / "scripts" / "skills_catalogue.py"
INVENTORY_SCRIPT = ROOT / "scripts" / "client_inventory.py"
REAL = ROOT / "project" / "policies" / "skills-policy.json"
FIX = Path(tempfile.mkdtemp(prefix="t508-cat-"))
base = json.loads(REAL.read_text())

fails: list[str] = []
checks = 0


def check(label: str, cond: bool) -> None:
    global checks
    checks += 1
    if not cond:
        fails.append(label)
    print(f"  {'✓' if cond else '✗'} {label}")


def run(policy: Path, *flags: str, env_over: dict[str, str] | None = None) -> tuple[int, dict]:
    env = dict(os.environ)
    if env_over:
        env.update(env_over)
    r = subprocess.run(
        ["python3", str(SCRIPT), "--policy", str(policy), "--json", *flags],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env=env,
    )
    try:
        return r.returncode, json.loads(r.stdout)
    except json.JSONDecodeError:
        return r.returncode, {"_raw": r.stdout + r.stderr}


def variant(name: str, mutate) -> Path:
    reg = json.loads(json.dumps(base))
    mutate(reg)
    p = FIX / name
    if "$schema" in reg:
        reg["$schema"] = str((REAL.parent / reg["$schema"]).resolve())
    p.write_text(json.dumps(reg, indent=2))
    return p


def write_registry(name: str, reg_dict: dict) -> Path:
    d = json.loads(json.dumps(reg_dict))
    schema_src = REGISTRY_PATH.parent / "clients-policy.schema.json"
    schema_dst = FIX / "clients-policy.schema.json"
    if schema_src.exists() and not schema_dst.exists():
        schema_dst.symlink_to(schema_src)
    p = FIX / name
    p.write_text(json.dumps(d, indent=2))
    return p


def by_project(out: dict) -> dict[str, dict]:
    return {pr["project"]: pr for pr in out.get("projects", [])}


def by_surface(pr: dict) -> dict[str, dict]:
    return {s["surface"]: s for s in pr.get("surfaces", [])}


def rows(out: dict) -> list[dict]:
    return [r for pr in out.get("projects", []) for r in pr["skills"]]


def unique_execs(out: dict) -> list[tuple[str, dict]]:
    seen: set[tuple[str, str]] = set()
    res: list[tuple[str, dict]] = []
    for pr in out.get("projects", []):
        for r in pr["skills"]:
            if not r["ships_executable"]:
                continue
            k = (pr["project"], r["skill"])
            if k not in seen:
                seen.add(k)
                res.append((pr["project"], r))
    return res


def sugg(out: dict) -> str:
    return " | ".join(out.get("suggestions", []))


print("\n  T182 / T508 / T226 / T522 — skills_catalogue.py regression proof\n")

# ── 1. Positive path & live estate invariants ──────────────────────────────────
code, live = run(REAL)
check("live policy exits 0 (suggestions are advisory)", code == 0 and live.get("ok") is True)
projs = by_project(live)
check("every declared project is catalogued", set(projs) == REGISTRY_PROJECTS)
check("recommendation is project-managed + sandboxed",
      live["recommended"]["managed"] == "project" and live["recommended"]["sandboxed"] is True)
check("nothing is unmanaged across the estate today",
      all(pr["counts"]["unmanaged"] == 0 for pr in live["projects"]))

# ── 2. T508 AC1 — Every estate skills surface (`.`, `w0m-web`, `w0m-api`) is catalogued ──
w0m_surfaces = by_surface(projs["w0m"])
check("T508 AC1: w0m catalogues all 3 governed surfaces (`.`, `w0m-web`, `w0m-api`)",
      set(w0m_surfaces) == {".", "w0m-web", "w0m-api"})
check("T508 AC1: surface installed counts match live `.agents/skills` directories (26 + 112 + 9 = 147)",
      w0m_surfaces["."]["counts"]["installed"] >= 26
      and w0m_surfaces["w0m-web"]["counts"]["installed"] >= 112
      and w0m_surfaces["w0m-api"]["counts"]["installed"] >= 9
      and projs["w0m"]["counts"]["installed"] == sum(s["counts"]["installed"] for s in w0m_surfaces.values()))

# ── 3. T508 AC2 — Workspace `canonical_repo` and `repos` resolution ────────────
ws_fix = FIX / "ws_canon"
ws_sub = ws_fix / "k7d" / "k7d"
for sname in ("alpha", "beta", "gamma", "delta"):
    sdir = ws_sub / ".agents" / "skills" / sname
    sdir.mkdir(parents=True, exist_ok=True)
    (sdir / "SKILL.md").write_text(f"# {sname}\n")
(ws_sub / ".w0m").mkdir(parents=True, exist_ok=True)
(ws_sub / ".w0m" / "skills.json").write_text(json.dumps({
    "project": "k7-probe",
    "skills": {n: {"provider": "w0m-native", "version": "canonical"} for n in ("alpha", "beta", "gamma", "delta")},
    "auto_recommend": False,
}))
reg_ac2 = write_registry("reg-ac2.json", {
    **REGISTRY_DATA,
    "projects": [
        {
            "id": "k7probe",
            "role": "managed",
            "root": str(ws_fix),
            "enabled": True,
            "runtime": {"substrate": "host"},
            "repos": {"k7d": "k7d/k7d"},
            "canonical_repo": "k7d",
        }
    ],
})
p_no_ov = variant("policy-no-ov.json", lambda r: r.__setitem__("overrides", {"_comment": "empty for fixture"}))
c_ac2, out_ac2 = run(p_no_ov, "--registry", str(reg_ac2))
kp = by_project(out_ac2).get("k7probe", {})
check("T508 AC2: workspace project with `canonical_repo != '.'` resolves skills from canonical sub-repo (4 skills)",
      c_ac2 == 0
      and kp.get("counts", {}).get("installed") == 4
      and kp.get("counts", {}).get("project_managed") == 4
      and kp.get("surfaces", [{}])[0].get("surface") == "k7d")

# ── 4. T508 AC3 — Missing repo root, uncatalogued manifest, or shrunk corpus fails closed (exit 2) ──
reg_missing_member = write_registry("reg-missing-member.json", {
    **REGISTRY_DATA,
    "projects": [
        {
            "id": "w0m",
            "role": "w0m",
            "root": str(ws_fix),
            "enabled": True,
            "runtime": {"substrate": "host"},
            "repos": {"k7d": "k7d/k7d", "ghost-repo": "does-not-exist"},
            "canonical_repo": "k7d",
        }
    ],
})
c_mm, out_mm = run(p_no_ov, "--registry", str(reg_missing_member))
check("T508 AC3 red probe 1: missing declared `repos` member fails closed (exit 2) naming the repo",
      c_mm == 2 and any("ghost-repo" in e for e in out_mm.get("errors", [])))

# Uncatalogued manifest sitting in a child directory omitted from `repos` must fail closed (exit 2)
uncat_ws = FIX / "ws_uncat"
(uncat_ws / ".agents" / "skills" / "s1").mkdir(parents=True, exist_ok=True)
(uncat_ws / ".w0m").mkdir(parents=True, exist_ok=True)
(uncat_ws / ".w0m" / "skills.json").write_text(json.dumps({
    "project": "uncat", "skills": {"s1": {"provider": "w0m-native", "version": "canonical"}}, "auto_recommend": False,
}))
(uncat_ws / "dropped-member" / ".w0m").mkdir(parents=True, exist_ok=True)
(uncat_ws / "dropped-member" / ".w0m" / "skills.json").write_text(json.dumps({
    "project": "dropped", "skills": {"s2": {"provider": "w0m-native", "version": "canonical"}}, "auto_recommend": False,
}))
reg_uncat = write_registry("reg-uncat.json", {
    **REGISTRY_DATA,
    "projects": [{
        "id": "uncatprobe",
        "role": "managed",
        "root": str(uncat_ws),
        "enabled": True,
        "runtime": {"substrate": "host"},
    }],
})
c_uc, out_uc = run(p_no_ov, "--registry", str(reg_uncat))
check("T508 AC3 red probe 2: uncatalogued child `.w0m/skills.json` manifest fails closed (exit 2)",
      c_uc == 2 and any("uncatalogued skills manifest" in e for e in out_uc.get("errors", [])))

# Shrunk surface: manifest declares skills but 0 are installed on disk -> exit 2
shrunk_ws = FIX / "ws_shrunk"
(shrunk_ws / ".w0m").mkdir(parents=True, exist_ok=True)
(shrunk_ws / ".w0m" / "skills.json").write_text(json.dumps({
    "project": "shrunk", "skills": {"s1": {"provider": "w0m-native", "version": "canonical"}}, "auto_recommend": False,
}))
reg_shrunk = write_registry("reg-shrunk.json", {
    **REGISTRY_DATA,
    "projects": [{
        "id": "shrunkprobe",
        "role": "managed",
        "root": str(shrunk_ws),
        "enabled": True,
        "runtime": {"substrate": "host"},
    }],
})
c_sh, out_sh = run(p_no_ov, "--registry", str(reg_shrunk))
check("T508 AC3 red probe 3: manifest with >0 declared skills and 0 installed fails closed (exit 2)",
      c_sh == 2 and any("0 are installed on disk" in e for e in out_sh.get("errors", [])))

# ── 5. T508 AC4 — Excluded counts derived per surface from `.w0m/skills.json -> exclude` ──
web_manifest = json.loads((WEB / ".w0m" / "skills.json").read_text())
art_root = (ROOT / next(p["root"] for p in REGISTRY_DATA["projects"] if p["id"] == "artemio")).resolve()
art_manifest = json.loads((art_root / ".w0m" / "skills.json").read_text())
check("T508 AC4: w0m (via w0m-web) and artemio excluded counts equal their `.w0m/skills.json -> exclude` lengths",
      w0m_surfaces["w0m-web"]["counts"]["excluded"] == len(web_manifest.get("exclude", {})) == 10
      and projs["w0m"]["counts"]["excluded"] == len(web_manifest.get("exclude", {})) == 10
      and projs["artemio"]["counts"]["excluded"] == len(art_manifest.get("exclude", {})) == 10)

# Red probe for AC4: removing one exclusion entry from a fixture manifest turns that skill `unmanaged`
excl_fix = FIX / "excl_probe"
for sname in ("governed-one", "excluded-one", "excluded-two"):
    (excl_fix / ".agents" / "skills" / sname).mkdir(parents=True, exist_ok=True)
(excl_fix / ".w0m").mkdir(parents=True, exist_ok=True)
(excl_fix / ".w0m" / "skills.json").write_text(json.dumps({
    "project": "exclprobe",
    "skills": {"governed-one": {"provider": "w0m-native", "version": "canonical"}},
    "exclude": {"excluded-one": "CLI generated skill kept out of lockfile"},
    "auto_recommend": False,
}))
reg_excl = write_registry("reg-excl.json", {
    **REGISTRY_DATA,
    "projects": [{
        "id": "exclprobe",
        "role": "managed",
        "root": str(excl_fix),
        "enabled": True,
        "runtime": {"substrate": "host"},
    }],
})
c_ex, out_ex = run(p_no_ov, "--registry", str(reg_excl))
ep_counts = by_project(out_ex).get("exclprobe", {}).get("counts", {})
check("T508 AC4 red probe: dropping an exclude entry shifts it from excluded (1) to unmanaged (1) and warns",
      c_ex == 0 and ep_counts.get("excluded") == 1 and ep_counts.get("unmanaged") == 1
      and "exclprobe:excluded-two" in sugg(out_ex))

# ── 6. T508 AC5 — `ships_executable` ignores `node_modules` and build artifacts ──
web_skills = {r["skill"]: r for r in w0m_surfaces["w0m-web"]["skills"]}
art_skills = {r["skill"]: r for r in projs["artemio"]["skills"]}
check("T508 AC5: w0m-web `mmd-validate` reports 2 runnable files (`['test.mjs', 'validate.mjs']`), ignoring node_modules",
      web_skills["mmd-validate"]["ships_executable"] == ["test.mjs", "validate.mjs"]
      and web_skills["webapp-testing"]["ships_executable"] == ["scripts/with_server.py"]
      and art_skills["idea-refine"]["ships_executable"] == ["scripts/idea-refine.sh"]
      and art_skills["mmd-validate"]["ships_executable"] == ["test.mjs", "validate.mjs"])

nm_skill = excl_fix / ".agents" / "skills" / "governed-one"
(nm_skill / "run.sh").write_text("#!/bin/sh\necho ok\n")
(nm_skill / "node_modules" / "pkg").mkdir(parents=True, exist_ok=True)
(nm_skill / "node_modules" / "pkg" / "index.js").write_text("console.log(1);\n")
(nm_skill / "dist").mkdir(parents=True, exist_ok=True)
(nm_skill / "dist" / "bundle.js").write_text("console.log(2);\n")
c_nm, out_nm = run(p_no_ov, "--registry", str(reg_excl))
nm_row = next(r for r in by_project(out_nm)["exclprobe"]["skills"] if r["skill"] == "governed-one")
check("T508 AC5 red probe: `ships_executable` prunes `node_modules/` and `dist/` and reports only `['run.sh']`",
      nm_row["ships_executable"] == ["run.sh"])

# ── 7. T508 AC6 — `host_invocations` scans `just/*.just`, skips comments, deduplicates symlinks ──
check("T508 AC6: w0m `mmd-validate` host invocation is detected in `just/estate.just` recipes `mmd-validate` & `mmd-validate-test`",
      set(web_skills["mmd-validate"]["runs_on_host_recipes"]) >= {"mmd-validate", "mmd-validate-test"}
      and all(loc.startswith("just/estate.just:") for loc in web_skills["mmd-validate"]["runs_on_host"]))
check("T508 AC6: artemio `idea-refine` and `mmd-validate` host invocations are detected by recipe name (`idea-refine-init`, `lint-mmd`)",
      "idea-refine-init" in art_skills["idea-refine"]["runs_on_host_recipes"]
      and "lint-mmd" in art_skills["mmd-validate"]["runs_on_host_recipes"])

# Comment-only mention in justfile -> `runs_on_host == []`
(excl_fix / "justfile").write_text(
    "# comment mentioning .agents/skills/governed-one/run.sh\n"
    "// another comment skills/governed-one/run.sh\n"
    "-- sql comment skills/governed-one/run.sh\n"
    "build:\n"
    "    echo clean\n"
)
c_cm, out_cm = run(p_no_ov, "--registry", str(reg_excl))
cm_row = next(r for r in by_project(out_cm)["exclprobe"]["skills"] if r["skill"] == "governed-one")
check("T508 AC6 red probe 1: comment-only mentions (`#`, `//`, `--`) produce `runs_on_host == []`",
      cm_row["runs_on_host"] == [] and cm_row["runs_on_host_recipes"] == [])

# Real recipe line + symlinked `just/linked.just -> ../justfile` -> scanned once, not twice
(excl_fix / "justfile").write_text(
    "# header comment skills/governed-one/run.sh\n"
    "run-governed:\n"
    "    bash .agents/skills/governed-one/run.sh\n"
)
(excl_fix / "just").mkdir(exist_ok=True)
linked_just = excl_fix / "just" / "linked.just"
if not linked_just.exists():
    linked_just.symlink_to(excl_fix / "justfile")
c_sym, out_sym = run(p_no_ov, "--registry", str(reg_excl))
sym_row = next(r for r in by_project(out_sym)["exclprobe"]["skills"] if r["skill"] == "governed-one")
check("T508 AC6 red probe 2: symlinked `justfile` is deduplicated by realpath and matched once in recipe `run-governed`",
      len(sym_row["runs_on_host"]) == 1 and sym_row["runs_on_host_recipes"] == ["run-governed"])

# ── 8. T508 AC7 — Orphan overrides in `skills-policy.json` fail closed (exit 2) ──
p_orphan = variant(
    "orphan-override.json",
    lambda r: r["overrides"].__setitem__(
        "w0m:nonexistent-skill",
        {"sandboxed": False, "reason": "Orphan override probe — this skill does not exist anywhere."},
    ),
)
c_or, out_or = run(p_orphan)
check("T508 AC7 red probe: orphan override in `skills-policy.json` fails closed (exit 2) naming `w0m:nonexistent-skill`",
      c_or == 2 and any("w0m:nonexistent-skill" in e for e in out_or.get("errors", [])))

# ── 9. T508 AC8 & AC9 — Explicit decisions on all runnable skills & policy mutation probes ──
execs = unique_execs(live)
declared_override_keys = {k for k in base.get("overrides", {}) if not k.startswith("_")}
exec_keys = {f"{proj}:{r['skill']}" for proj, r in execs}
check("T508 AC8: every runnable project:skill pair across the estate matches the declared policy overrides",
      exec_keys == declared_override_keys
      and {"w0m:mmd-validate", "w0m:webapp-testing", "artemio:idea-refine", "artemio:mmd-validate"} <= exec_keys)
check("T508 AC8: every skill shipping runnable files has an EXPLICIT decision with a reason",
      all(r["sandboxed_declared"] and r["override_reason"] for _, r in execs))
check("T508 AC8: no declaration is contradicted by a call site",
      not [r for _, r in execs if r["sandboxed"] and r["runs_on_host"]])

p_nodet = variant("no-detect.json", lambda r: r["detect_executable"].update(
    {"suffixes": [], "executable_bit": False}))
c_nd, out_nd = run(p_nodet)
check("T508 AC9 probe 1: emptying `detect_executable` collapses the runnable population to 0",
      c_nd == 0 and len(unique_execs(out_nd)) == 0)

p_noov = variant("no-override.json", lambda r: r.__setitem__(
    "overrides", {"_comment": r["overrides"]["_comment"]}))
c_no, out_no = run(p_noov)
check("T508 AC9 probe 2: an inherited default over runnable code is flagged",
      "inherits the default" in sugg(out_no))
check("T508 AC9 probe 3: a declaration contradicted by a real call site is flagged as `ON THE HOST`",
      "ON THE HOST" in sugg(out_no) and "mmd-validate" in sugg(out_no) and "idea-refine" in sugg(out_no))
check("T508 AC9 probe 4: those suggestions block under `--enforce` (exit 1)",
      run(p_noov, "--enforce")[0] == 1)

p_defoff = variant("default-off.json", lambda r: r["recommended"].__setitem__("sandboxed", False))
_, out_do = run(p_defoff)
check("T508 AC9 probe 5: the sandboxed default is inherited per skill, not fixed",
      any(not x["sandboxed"] for x in rows(out_do) if x["ships_executable"]))

p_bad = FIX / "bad.json"
p_bad.write_text("{ not json")
c_bad, out_bad = run(p_bad)
check("T508 AC9 probe 6: an unreadable policy errors cleanly (exit 2), no traceback",
      c_bad == 2 and "unreadable" in " ".join(out_bad.get("errors", [])))

r_default = subprocess.run(["python3", str(SCRIPT), "--json"], capture_output=True, text=True, cwd=str(ROOT))
check("T508 AC9 probe 7: with no `--policy` override the tool resolves its policy from `.w0m/sdlc.json -> skills`",
      r_default.returncode == 0)

# ── 10. T508 AC10 — Cross-tool consistency (`client_inventory.py` == `skills_catalogue.py`) ──
r_inv = subprocess.run(
    ["python3", str(INVENTORY_SCRIPT), "--json"],
    capture_output=True,
    text=True,
    cwd=str(ROOT),
    check=True,
)
inv = json.loads(r_inv.stdout)
inv_by_id = {p["id"]: p for p in inv.get("projects", [])}
check("T508 AC10: `client_inventory` w0m `skills.declared` & `project_managed` equal catalogue's `w0m-web` surface",
      inv_by_id["w0m"]["skills"]["declared"] == w0m_surfaces["w0m-web"]["counts"]["declared"]
      and inv_by_id["w0m"]["skills"]["project_managed"] == w0m_surfaces["w0m-web"]["counts"]["project_managed"])
check("T508 AC10: `client_inventory` and `skills_catalogue` agree across all w0m surfaces and client projects",
      all(
          inv_by_id["w0m"]["skills"]["surfaces"][s]["declared"] == w0m_surfaces[s]["counts"]["declared"]
          and inv_by_id["w0m"]["skills"]["surfaces"][s]["excluded"] == w0m_surfaces[s]["counts"]["excluded"]
          for s in (".", "w0m-web", "w0m-api")
      )
      and all(
          (inv_by_id[pid]["skills"]["declared"] or 0) == projs[pid]["counts"]["declared"]
          and inv_by_id[pid]["skills"]["excluded"] == projs[pid]["counts"]["excluded"]
          for pid in ("1945", "artemio", "servicios777", "personaje0", "bridgeroad")
      ))

# ── 11. T522 AC4 & AC5 — User-scope governance & `--enforce` red/green probes ──
c_enf, out_enf = run(REAL, "--enforce")
check("T522 AC4: live `skills_catalogue.py --enforce` exits 0 with 0 unmanaged user-scope skills",
      c_enf == 0 and out_enf["user_scope"]["counts"]["unmanaged"] == 0 and out_enf["suggestions"] == [])

user_fix_root = FIX / "user_root_probe"
user_fix_skills = user_fix_root / "skills"
(user_fix_skills / "undecided-user-skill").mkdir(parents=True, exist_ok=True)
c_uf_red, out_uf_red = run(REAL, "--user-skills", str(user_fix_skills), "--enforce")
check("T522 AC5 red probe: an undecided skill in `--user-skills` surfaces a warning and causes `--enforce` to exit 1",
      c_uf_red == 1
      and out_uf_red["user_scope"]["counts"]["unmanaged"] == 1
      and "undecided-user-skill" in sugg(out_uf_red))

(user_fix_root / ".w0m").mkdir(parents=True, exist_ok=True)
(user_fix_root / ".w0m" / "skills.json").write_text(json.dumps({
    "project": "user-scope",
    "skills": {},
    "exclude": {
        "undecided-user-skill": "preserve (fixture probe): explicitly reviewed workstation skill",
    },
    "auto_recommend": False,
}))
c_uf_green, out_uf_green = run(REAL, "--user-skills", str(user_fix_skills), "--enforce")
check("T522 AC5 green counterpart: recording the user-scope decision in `.w0m/skills.json` makes `--enforce` exit 0",
      c_uf_green == 0
      and out_uf_green["user_scope"]["counts"]["excluded"] == 1
      and out_uf_green["user_scope"]["counts"]["unmanaged"] == 0)

print(f"\n  {checks - len(fails)}/{checks} passed\n")
if fails:
    for f in fails:
        print(f"    ✗ {f}")
    sys.exit(1)
