#!/usr/bin/env python3
"""skills_catalogue.py — the installed-skill catalogue for the SDLC tools surface.

Answers, for every project the estate declares, the question nothing else did: **what agent
skills are actually installed here, who manages them, and does anything they ship get to run on
the host?** Skills are executable instructions loaded into every agent session — a supply-chain
surface — and until now they were governed per project (`w0m skill check`) but never *catalogued*
across the estate beside the other tool surfaces.

Two settings per skill, from `project/skills-policy.json`:

  managed    project | user | unmanaged
             `project` — vendored into the repo, declared in the manifest, hashed in the lockfile.
             `user`    — installed in ~/.claude/skills. Loads into that ONE developer's sessions,
                         invisible to the repo and to every gate: it cannot be diffed, hashed or
                         reviewed, so two developers can run the same prompt against different
                         instructions with nothing to detect it.
             `unmanaged` — present in the project but in neither the manifest nor the exclude list.

  sandboxed  Whether the skill's SHIPPED CODE is confined to an isolated environment rather than
             run on the host. Only load-bearing for skills that ship runnable files; the catalogue
             measures that rather than assuming it, and says how few qualify.

The recommendation is `managed: project` + `sandboxed: true`. Deviations are REPORTED and exit 0;
`--enforce` makes them block. That split is deliberate: the user-scope corpus lives on a
developer's own machine, and a gate that hard-failed on it would be unactionable in CI.

Usage:
    python3 scripts/skills_catalogue.py            # the catalogue + suggestions
    python3 scripts/skills_catalogue.py --enforce  # deviations block
    python3 scripts/skills_catalogue.py --json
    python3 scripts/skills_catalogue.py --policy <path>   # drive a fixture (tests)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from schema_check import validate_declared_schema

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]                      # …/@wom
CANONICAL = ROOT / "w0m-web"                # …/w0m-web
SDLC = ROOT / ".w0m" / "sdlc.json"
REGISTRY = ROOT / "project" / "policies" / "clients-policy.json"
USER_SKILLS = Path(os.environ.get("W0M_USER_SKILLS_DIR") or (Path.home() / ".claude" / "skills"))
POLICY: Path | None = None            # resolved from .w0m/sdlc.json -> skills.policy


def read_text(path: Path) -> str | None:
    try:
        return path.read_text()
    except (OSError, UnicodeDecodeError):
        return None


def load_json(path: Path) -> dict | None:
    text = read_text(path)
    if text is None:
        return None
    try:
        v = json.loads(text)
    except json.JSONDecodeError:
        return None
    return v if isinstance(v, dict) else None


def ships_executable(skill_dir: Path, suffixes: set[str], use_bit: bool) -> list[str]:
    """Files in the skill that something could RUN. Resolved through symlinks, because the
    runtime layer is symlinks into the governed set and a link is not its own content."""
    out = []
    try:
        for f in sorted(skill_dir.rglob("*")):
            if not f.is_file():
                continue
            try:
                is_exec = use_bit and bool(f.stat().st_mode & 0o111)
            except OSError:
                is_exec = False
            if f.suffix in suffixes or is_exec:
                out.append(f.relative_to(skill_dir).as_posix())
    except OSError:
        pass
    return out


def host_invocations(root: Path, skill: str, execs: list[str]) -> list[str]:
    """Places in the project that invoke this skill's shipped code DIRECTLY — i.e. on the host.

    🔑 This is what turns `sandboxed` from an assertion into a measurement. A default of
    `sandboxed: true` inherited by every skill would declare something nobody checked — and it
    would have been FALSE here: Artemio's `just idea-refine-init` runs the skill's shipped script
    with `bash`, on the host, which is the opposite of sandboxed. A declaration that a call site
    contradicts is worse than no declaration, so the contradiction is reported.

    Scans tracked, human-authored surfaces (justfile, scripts, docs) for the script's path. Not
    exhaustive — it cannot see a path built at runtime — so it can only ever ADD evidence of host
    execution, never prove its absence. Reported that way.
    """
    if not execs:
        return []
    names = {Path(e).name for e in execs}
    found: list[str] = []
    candidates = [root / "justfile", root / "Makefile"]
    candidates += [p for p in (root / "scripts").glob("*") if p.is_file()] \
        if (root / "scripts").is_dir() else []
    for f in candidates:
        text = read_text(f)
        if text is None:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if "skills/" in line and any(n in line for n in names):
                found.append(f"{f.name}:{i}")
    return found


def skill_dirs(base: Path) -> dict[str, Path]:
    """Installed skills at a base path, keyed by name. Symlinks included — the runtime layer is
    made of them, and a symlinked skill is every bit as loaded as a real one."""
    out: dict[str, Path] = {}
    try:
        for p in sorted(base.iterdir()):
            if p.name.startswith(".") or not p.is_dir():
                continue
            out[p.name] = p
    except OSError:
        pass
    return out


def load_portable_skills() -> set[str]:
    text = read_text(ROOT / "w0m-skills" / "skill-portability.jsonc")
    if text is None:
        return set()
    lines = [line for line in text.splitlines() if not line.lstrip().startswith("//")]
    try:
        v: dict[str, object] = json.loads("\n".join(lines))
    except json.JSONDecodeError:
        return set()
    raw_portable = v.get("portable") if isinstance(v, dict) else None
    portable = raw_portable if isinstance(raw_portable, dict) else {}
    return {k for k in portable if not k.startswith("//")}


def catalogue_project(pid: str, root: Path, policy: dict, role: str = "managed") -> dict:
    """Every skill installed for one project, with both settings resolved."""
    det = policy.get("detect_executable", {})
    suffixes = set(det.get("suffixes", []))
    use_bit = bool(det.get("executable_bit"))
    overrides = {k: v for k, v in policy.get("overrides", {}).items() if not k.startswith("_")}
    defaults = {k: v for k, v in policy.get("defaults", {}).items() if not k.startswith("_")}
    rec = policy.get("recommended", {})

    manifest = load_json(root / ".w0m" / "skills.json") or {}
    declared = set(manifest.get("skills") or {})
    if role in ("self-managed", "half-managed"):
        declared |= load_portable_skills()
    excluded = set(manifest.get("exclude") or {})
    lock = load_json(root / ".w0m" / "skills.lock.json") or {}
    locked = set(lock.get("skills") or {})

    # Governed layer first: it is what integrity is computed over. The runtime layer adds
    # whatever is NOT a link into it — CLI-generated families, and accidental writes, which look
    # identical from here and are told apart by the manifest's exclude list.
    governed = skill_dirs(root / ".agents" / "skills")
    runtime = skill_dirs(root / ".claude" / "skills")
    installed: dict[str, Path] = {**runtime, **governed}

    rows = []
    for name, path in sorted(installed.items()):
        if name in declared:
            managed = "project"
        elif name in excluded:
            managed = "excluded"
        else:
            managed = "unmanaged"
        ov = overrides.get(f"{pid}:{name}", {})
        execs = ships_executable(path, suffixes, use_bit)
        # `sandboxed` is only ever DECLARED — nothing here can prove confinement. What can be
        # measured is the opposite: evidence the code runs on the host. So the inherited default
        # is recorded as `declared: False`, never dressed up as a finding.
        sandbox_declared = "sandboxed" in ov      # NOT `declared` — that is the manifest set
        sandboxed = ov.get("sandboxed", rec.get("sandboxed", True))
        on_host = host_invocations(root, name, execs)
        rows.append({
            "skill": name,
            "managed": managed,
            "default": name in defaults,
            "in_lock": name in locked,
            "sandboxed": sandboxed,
            "sandboxed_declared": sandbox_declared,
            "override_reason": ov.get("reason"),
            "ships_executable": execs,
            "runs_on_host": on_host,
            "layer": "governed" if name in governed else "runtime-only",
        })
    return {
        "project": pid,
        "root": str(root),
        "manifest": bool(manifest),
        "counts": {
            "installed": len(rows),
            "project_managed": sum(1 for r in rows if r["managed"] == "project"),
            "defaults_installed": sum(1 for r in rows if r["default"]),
            "excluded": sum(1 for r in rows if r["managed"] == "excluded"),
            "unmanaged": sum(1 for r in rows if r["managed"] == "unmanaged"),
            "ships_executable": sum(1 for r in rows if r["ships_executable"]),
        },
        "skills": rows,
    }


def resolve_policy() -> tuple[Path | None, str | None]:
    """The policy path comes from `.w0m/sdlc.json -> skills.policy`, never from a constant.

    That is what makes the `skills` key load-bearing instead of decorative: remove it and this
    tool stops, rather than quietly carrying on against a hardcoded path. There is deliberately
    NO fallback — a declaration the code can route around is the vacuous shape the estate keeps
    re-learning."""
    if POLICY is not None:                       # --policy, for fixtures
        return POLICY, None
    decl = load_json(SDLC)
    if decl is None:
        return None, f"declaration unreadable: {SDLC}"
    block = decl.get("skills")
    if not isinstance(block, dict):
        return None, f"`.w0m/sdlc.json -> skills` is absent — nothing declares where the skills " \
                     "policy lives, and this catalogue will not guess"
    rel = block.get("policy")
    if not rel:
        return None, "`.w0m/sdlc.json -> skills.policy` is absent"
    return ROOT / rel, None


def build() -> tuple[dict, list[str], list[str]]:
    """Returns (catalogue, suggestions, errors)."""
    policy_path, err = resolve_policy()
    # Both arms checked explicitly: `err` and a None path are separate states in the signature,
    # so narrowing on one does not narrow the other. Making the pair unrepresentable would be the
    # nicer fix; an explicit branch is the honest one until the signature changes.
    if err or policy_path is None:
        return {}, [], [err or "no skills policy path resolved"]
    policy = load_json(policy_path)
    if policy is None:
        return {}, [], [f"policy unreadable or not an object: {policy_path}"]
    # T301 AC2. The schema was already complete — 10 of 10 mutations caught, including the
    # mandatory `reason` on an override — and loaded by nothing, which is the same as absent.
    schema_errors = validate_declared_schema(policy_path, policy)
    if schema_errors:
        return {}, [], schema_errors
    raw_defaults = policy.get("defaults")
    if not isinstance(raw_defaults, dict):
        return {}, [], ["policy missing `defaults` object (stack-independent baseline skills)"]
    defaults = {k: v for k, v in raw_defaults.items() if not k.startswith("_")}
    for d_name, d_meta in defaults.items():
        if not isinstance(d_meta, dict):
            return {}, [], [f"defaults.{d_name}: expected object, got {type(d_meta).__name__}"]
        if "detect" in d_meta:
            return {}, [], [f"defaults.{d_name}: default baseline skills are stack-independent and must not define `detect` rules"]
    reg = load_json(REGISTRY)
    if reg is None:
        return {}, [], [f"project registry unreadable: {REGISTRY}"]

    projects = []
    for p in reg.get("projects", []):
        if not p.get("enabled"):
            continue
        root = (ROOT / p["root"]).resolve()
        if not root.is_dir():
            return {}, [], [f"{p['id']}: declared root does not exist — {root}"]
        projects.append(catalogue_project(p["id"], root, policy, role=p.get("role", "managed")))
    if not projects:
        return {}, [], ["no enabled project — a catalogue over nothing is not a catalogue"]

    total = sum(pr["counts"]["installed"] for pr in projects)
    if total == 0:
        return {}, [], ["zero skills catalogued across every project — refusing to report a "
                        "clean catalogue over an empty corpus"]

    # USER scope: real, loaded into sessions, and invisible to every project's gates.
    user = sorted(skill_dirs(USER_SKILLS))

    rec = policy.get("recommended", {})
    suggestions: list[str] = []
    for pr in projects:
        for r in pr["skills"]:
            if r["managed"] == "unmanaged":
                suggestions.append(
                    f"{pr['project']}:{r['skill']} — installed but in neither the manifest nor "
                    f"`exclude`; suggest managed: {rec.get('managed', 'project')} (declare it, or "
                    "exclude it with a reason)")
            if not r["ships_executable"]:
                continue
            # 🔴 The strongest finding: a declaration a call site CONTRADICTS.
            if r["sandboxed"] and r["runs_on_host"]:
                suggestions.append(
                    f"{pr['project']}:{r['skill']} — declared sandboxed: true, but its shipped "
                    f"code is invoked directly at {', '.join(r['runs_on_host'])}, which runs it "
                    "ON THE HOST. Either stop invoking it directly, or declare sandboxed: false "
                    "with a reason — the current declaration is contradicted by the call site")
            if not r["sandboxed_declared"]:
                suggestions.append(
                    f"{pr['project']}:{r['skill']} — ships {len(r['ships_executable'])} runnable "
                    f"file(s) ({', '.join(r['ships_executable'][:2])}) and inherits the default "
                    f"sandboxed: {r['sandboxed']} rather than declaring it. An inherited default "
                    "over runnable code asserts something nobody decided — declare it explicitly")
    if user:
        suggestions.append(
            f"user scope — {len(user)} skill(s) in {USER_SKILLS} load into this developer's "
            "sessions and are in NO project's manifest or lockfile: invisible to review, to "
            f"hashing and to every gate ({', '.join(user[:4])}"
            f"{' …' if len(user) > 4 else ''}); suggest managed: "
            f"{rec.get('managed', 'project')}")

    return {"recommended": rec, "defaults": defaults, "projects": projects,
            "user_scope": {"path": str(USER_SKILLS), "skills": user}}, suggestions, []


def main() -> int:
    argv = sys.argv[1:]
    global POLICY
    if "--policy" in argv:
        i = argv.index("--policy")
        if i + 1 >= len(argv):
            print("  ✗ --policy needs a path")
            return 2
        POLICY = Path(argv[i + 1]).resolve()

    cat, suggestions, errors = build()
    if errors:
        if "--json" in argv:
            print(json.dumps({"ok": False, "errors": errors}, indent=2))
        else:
            print("\n  ✗ catalogue not built\n")
            for e in errors:
                print(f"     ✗ {e}")
            print()
        return 2

    if "--json" in argv:
        print(json.dumps({"ok": True, "suggestions": suggestions, **cat}, indent=2))
        return 1 if ("--enforce" in argv and suggestions) else 0

    rec = cat["recommended"]
    print(f"\n  installed-skill catalogue — recommended: managed: {rec.get('managed')} · "
          f"sandboxed: {rec.get('sandboxed')}\n")
    hdr = (f"  {'project':10} {'installed':>9} {'managed':>8} {'excluded':>8} {'unmanaged':>9} "
           f"{'ships code':>10}")
    print(hdr)
    print("  " + "─" * (len(hdr) - 2))
    for pr in cat["projects"]:
        c = pr["counts"]
        print(f"  {pr['project']:10} {c['installed']:9} {c['project_managed']:8} "
              f"{c['excluded']:8} {c['unmanaged']:9} {c['ships_executable']:10}")

    u = cat["user_scope"]
    print(f"\n  user scope ({u['path']}): {len(u['skills'])} skill(s) — outside every project's "
          "manifest and lockfile")

    # The skills for which `sandboxed` is load-bearing. Naming them beats a bare count: the
    # setting applies to a small population, and pretending otherwise would oversell the gate.
    execs = [(pr["project"], r) for pr in cat["projects"] for r in pr["skills"]
             if r["ships_executable"]]
    print(f"\n  skills that ship runnable files — the population `sandboxed` governs: {len(execs)}")
    for proj, r in execs:
        mark = "sandboxed" if r["sandboxed"] else "NOT sandboxed"
        how = "declared" if r["sandboxed_declared"] else "inherited default"
        host = f" · RUNS ON HOST at {', '.join(r['runs_on_host'])}" if r["runs_on_host"] else ""
        note = f"\n         reason: {r['override_reason'][:110]}…" if r["override_reason"] else ""
        print(f"     · {proj}:{r['skill']} ({', '.join(r['ships_executable'])}) — "
              f"{mark} ({how}){host}{note}")

    if suggestions:
        print(f"\n [WARN] {len(suggestions)} suggestion(s):")
        for s in suggestions:
            print(f" [WARN] {s}")
    else:
        print("\n  ✓ every catalogued skill matches the recommended settings")

    blocking = "--enforce" in argv and suggestions
    print(f"\n  {'BLOCKING (--enforce)' if blocking else 'advisory — suggestions do not block'}\n")
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
