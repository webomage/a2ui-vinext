#!/usr/bin/env python3
"""client_check.py — ONE command that runs every profile gate against a declared client (T182).

Phase 7 asks for a gate that answers *imported / not imported* per project. The gates now exist
and are all project-scoped, but running them meant four separate invocations across two repos,
each with its own flag spelling. That is a checklist with extra steps — so this composes them.

For the project named on the command line it runs, in order:

    $schema · skills · state_surface   client-profile-check / skills-catalogue / state-bounds
    mcp · repos                        preflight --project
    secrets · toolchain                sdlc-doctor --project
    stacks                             discovery --project

🔑 **The gate list is DERIVED from the profile, not hardcoded here.** Each required key names its
own recipe in `project/client-profile.json`, and this reads that. Hardcoding the list would let
the profile and the runner drift — and the runner would keep reporting green over a key whose
gate had been renamed or removed.

🔴 A gate that cannot run is a FAILURE, not a skip. The whole point of the profile is that a
missing declaration is visible; a runner that quietly omitted an unrunnable gate would restore
exactly the blindness it exists to remove.

Usage:
    python3 scripts/client_check.py artemio
    python3 scripts/client_check.py 1945 --json
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]                      # …/@wom
CANONICAL = ROOT / "w0m-web"                # …/w0m-web
REGISTRY = ROOT / "project" / "policies" / "clients-policy.json"
PROFILE = CANONICAL / "project" / "client-profile.json"

# How each profile recipe is invoked for a project. Keyed by the recipe name the profile records,
# so an unknown recipe is an explicit error rather than a silent omission.
INVOCATIONS: dict[str, list[str]] = {
    "preflight --project":   ["python3", "../scripts/preflight.py", "--project", "{root}"],
    "sdlc-doctor --project": ["python3", "../scripts/sdlc_doctor.py", "--project", "{root}"],
    "discovery --project":   ["python3", "../scripts/discovery.py", "--project", "{root}"],
    "state-bounds":          ["python3", "../scripts/state_bounds.py"],
    "skills-catalogue":      ["python3", "../scripts/skills_catalogue.py"],
    "client-profile-check":  ["python3", "../scripts/client_profile_check.py"],
    "design-system-check":   ["python3", "project/scripts/design_system_check.py", "--project", "{root}"],
    # The mode gate. `--dry-run` because this RUNNER must never mutate the project it is
    # measuring: the installer writes skills, and a conformance check that installs things
    # is not a check. It still exercises the real refusal path, which is what `profile` gates.
    "skills-install-generic": ["pnpm", "--dir", "../w0m-skills", "exec", "tsx",
                               "scripts/install_generic.ts", "{root}", "--dry-run"],
}


def load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    as_json = "--json" in sys.argv
    if len(args) != 1:
        print("usage: client_check.py <project-id> [--json]")
        return 2
    pid = args[0]

    reg = load_json(REGISTRY) or {}
    match = [p for p in reg.get("projects", []) if p.get("id") == pid and p.get("enabled")]
    if not match:
        ids = [p["id"] for p in reg.get("projects", []) if p.get("enabled")]
        print(f"  ✗ '{pid}' is not an enabled project in the registry — have: {', '.join(ids)}")
        return 2
    root = (ROOT / match[0]["root"]).resolve()

    profile = load_json(PROFILE) or {}
    keys = profile.get("keys", {})
    required = sorted(k for k, v in keys.items() if v.get("tier") == "required")
    if not required:
        print("  ✗ the profile declares no required keys — nothing to check")
        return 2

    # recipe → the keys it covers, so one invocation is not run once per key it happens to gate.
    # T183 AC10: also run optional client_scoped gates when the project explicitly declares the key.
    declared_now = set(load_json(root / ".w0m" / "sdlc.json") or {})
    optional_declared = sorted(
        k for k, v in keys.items()
        if v.get("tier") == "optional" and v.get("gate", {}).get("client_scoped") and k in declared_now
    )
    by_recipe: dict[str, list[str]] = {}
    for k in [*required, *optional_declared]:
        by_recipe.setdefault(keys[k]["gate"]["recipe"], []).append(k)

    results: list[dict] = []
    for recipe, covered in sorted(by_recipe.items()):
        argv = INVOCATIONS.get(recipe)
        if argv is None:
            results.append({"recipe": recipe, "keys": covered, "ok": False,
                            "detail": "no invocation recorded for this recipe — the profile names "
                                      "a gate this runner does not know how to run"})
            continue
        cmd = [a.replace("{root}", str(root)) for a in argv]
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(CANONICAL))
        out = (proc.stdout or proc.stderr).strip().splitlines()
        results.append({
            "recipe": recipe, "keys": covered, "ok": proc.returncode == 0,
            "exit": proc.returncode,
            "detail": next((ln.strip() for ln in reversed(out) if ln.strip()), "(no output)"),
        })

    # 🔴 Found by the AC7 COLD RUN, and only findable there. Some gates are advisory by design —
    # `skills-catalogue` and `state-bounds` exit 0 and report. Run against a project that declares
    # NOTHING they returned 0, so the composite printed ✅ for them and "3/6 gates clean" over a
    # repo with no `.w0m/` at all. A green tick for a key the project never declared is exactly
    # the false assurance this whole profile exists to remove.
    #
    # So a gate whose keys are ALL undeclared is reported as `n/a`, never as clean. The two warm
    # imports could not surface this: both already declared enough that every gate had something
    # to check.
    declared_now = set(load_json(root / ".w0m" / "sdlc.json") or {})
    for r in results:
        if not any(k in declared_now for k in r["keys"]):
            r["applicable"] = False
            r["ok"] = False
            r["detail"] = (f"n/a — {', '.join(r['keys'])} undeclared, so this gate had nothing to "
                           "check. Not a pass.")
        else:
            r["applicable"] = True

    # Declaration-level view: which required keys the project actually declares.
    decl = load_json(root / ".w0m" / "sdlc.json") or {}
    missing = [k for k in required if k not in decl]

    ok = not missing and all(r["ok"] for r in results)
    if as_json:
        print(json.dumps({"project": pid, "root": str(root), "conforms": ok,
                          "missing_required": missing, "gates": results}, indent=2))
        return 0 if ok else 1

    print(f"\n  client check — {pid}  ({root})\n")
    print(f"  profile: {len(required)} required key(s) — "
          f"{len(required) - len(missing)} declared, {len(missing)} missing")
    if missing:
        print(f"    ✗ missing: {', '.join(missing)}")
    print()
    for r in results:
        mark = "✅" if r["ok"] else ("⏭ " if not r.get("applicable", True) else "⚠️ ")
        print(f"  {mark} {r['recipe']:24} [{', '.join(r['keys'])}]")
        print(f"       {r['detail'][:150]}")
    applicable = [r for r in results if r.get("applicable", True)]
    print(f"\n {'✅ CONFORMS' if ok else '[WARN] DOES NOT CONFORM'} — "
          f"{sum(1 for r in applicable if r['ok'])}/{len(applicable)} applicable gate(s) clean"
          + (f", {len(results) - len(applicable)} n/a" if len(applicable) != len(results) else "")
          + f", {len(missing)} key(s) undeclared\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
