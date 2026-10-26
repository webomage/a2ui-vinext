#!/usr/bin/env python3
"""client_profile_check.py — AC2's exit criterion, made mechanical (T182).

AC2 says: *every key in the `client` profile names its enforcing gate, and a profile key with
no gate fails this AC*. Prose cannot hold that — a gate can be renamed, a reader deleted, a
recipe dropped, and the profile would go on claiming enforcement it no longer has. So this
re-derives the claim from source on every run:

  1. the profile validates against its own schema (structure: no key without a gate);
  2. **coverage** — required ∪ optional ∪ excluded == the estate contract's key set, exactly.
     A contract key in no tier is a failure, so no key can be quietly dropped, and a profile
     key that no longer exists in the contract is equally a failure;
  3. **the named recipe exists** in the live justfile (`just --summary`);
  4. **the named script exists and provably READS the key** — the profile's central claim,
     checked against the file rather than trusted;
  5. **no required key has a fail-open gate** (`on_absent: skip`). A required key whose gate
     skips when it is absent is precisely the vacuous declaration this profile exists against;
  6. **$schema references resolve** for every project the client registry declares. Presence
     is not validation: w0m's and Artemio's both point at `./sdlc.schema.json`, which does not
     exist — so both pass any presence check while having never been validated.

Step 6 reports rather than blocks by default: it is a finding about existing projects, not a
defect in the profile. `--enforce` makes every finding blocking.

Usage:
    python3 scripts/client_profile_check.py            # report, exit non-zero on profile defects
    python3 scripts/client_profile_check.py --enforce  # dangling $schema also blocks
    python3 scripts/client_profile_check.py --json
    python3 scripts/client_profile_check.py --profile <path>   # drive a fixture (tests)
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]                       # …/@wom
CANONICAL = ROOT / "w0m-web"                 # …/w0m-web
PROFILE = CANONICAL / "project" / "client-profile.json"
PROFILE_SCHEMA = CANONICAL / "project" / "client-profile.schema.json"
REGISTRY = ROOT / "project" / "policies" / "clients-policy.json"
JUSTFILE = ROOT / "justfile"


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


def just_recipes() -> set[str]:
    """Recipe names from the live justfile. `--summary` executes nothing."""
    try:
        r = subprocess.run(["just", "--justfile", str(JUSTFILE), "--summary"],
                           capture_output=True, text=True)
    except (OSError, ValueError):
        return set()
    return set(r.stdout.split()) if r.returncode == 0 else set()


def resolve_script(rel: str) -> Path:
    """Profile scripts are recorded estate-relative (`w0m-api/scripts/x.py`) or
    w0m-web-relative (`project/scripts/x.py`). Try both, so the profile can name a gate in
    either repo without encoding a repo prefix it would then have to keep in sync."""
    for base in (ROOT, CANONICAL):
        p = base / rel
        if p.is_file():
            return p
    return ROOT / rel


def reads_key(script: Path, key: str) -> bool:
    """Does this file actually READ this key out of a parsed declaration?

    🔑 A bare quoted-literal match is not good enough, and the red probe proved it: pointed at
    a script that merely contains `CANONICAL / "project" / …` (a path segment) and
    `f"{'project':10}"` (a table header), the naive version reported the key as read. That is
    the estate's recorded *never match on a name the inspected thing supplies* trap wearing a
    different hat — the string was real, the reading was not.

    So the match requires a dict-ACCESS form: `.get("key")`, `["key"]`, or `"key" in …`. Those
    are the three ways every gate here reaches into the parsed json. A gate that reads its key
    some other way will be reported as not reading it, which is the safe direction to be wrong
    in: it under-claims enforcement rather than inventing it.
    """
    text = read_text(script)
    if text is None:
        return False
    k = re.escape(key)
    q = r'["\']' + k + r'["\']'
    patterns = (
        r'\.get\(\s*' + q,          # cfg.get("state_surface")
        r'\[\s*' + q + r'\s*\]',    # decl["commands"]
        q + r'\s*(?:not\s+)?in\b',  # "mcp" in decl
    )
    return any(re.search(p, text) for p in patterns)


def check() -> tuple[list[str], list[str], dict]:
    """Returns (errors, findings, summary)."""
    errors: list[str] = []
    findings: list[str] = []

    profile = load_json(PROFILE)
    if profile is None:
        return [f"profile unreadable or not an object: {PROFILE}"], [], {}

    # 1 — structure
    schema = load_json(PROFILE_SCHEMA)
    if schema is None:
        errors.append(f"profile schema unreadable: {PROFILE_SCHEMA}")
    else:
        try:
            import jsonschema
        except ImportError:
            findings.append("jsonschema not installed — structural validation skipped "
                            "(the source-derived checks below still ran)")
        else:
            try:
                jsonschema.validate(profile, schema)
            except jsonschema.ValidationError as e:
                errors.append(f"profile does not validate against its schema: {e.message}")

    keys = profile.get("keys", {})
    excluded = profile.get("excluded", {})
    if not keys:
        errors.append("profile declares no keys — an empty profile is not a pass")

    # 2 — coverage against the live contract
    contract_path = ROOT / profile.get("contract_source", "")
    contract_decl = load_json(contract_path)
    if contract_decl is None:
        errors.append(f"contract source unreadable: {contract_path}")
        contract = set()
    else:
        contract = set(contract_decl)
        accounted = set(keys) | set(excluded)
        unaccounted = contract - accounted
        phantom = accounted - contract
        if unaccounted:
            errors.append(f"{len(unaccounted)} contract key(s) in no tier — a key must be "
                          f"required, optional or explicitly excluded: {', '.join(sorted(unaccounted))}")
        if phantom:
            errors.append(f"{len(phantom)} profile key(s) absent from the contract: "
                          f"{', '.join(sorted(phantom))}")
        overlap = set(keys) & set(excluded)
        if overlap:
            errors.append(f"key(s) both in the profile and excluded: {', '.join(sorted(overlap))}")

    # 3-5 — every profile key's gate, verified from source
    recipes = just_recipes()
    if not recipes:
        errors.append("could not read any recipe from the justfile — the recipe check would "
                      "pass vacuously, so it fails instead")
    verified = []
    for key, spec in keys.items():
        gate = spec.get("gate", {})
        recipe, script_rel = gate.get("recipe", ""), gate.get("script", "")
        # A recipe may carry flags ("discovery --enforce"); the recipe is the first token.
        recipe_name = recipe.split()[0] if recipe else ""
        if recipes and recipe_name not in recipes:
            errors.append(f"{key}: gate recipe `{recipe_name}` is not a recipe in the justfile")
        script = resolve_script(script_rel)
        if not script.is_file():
            errors.append(f"{key}: gate script does not exist — {script_rel}")
        elif not reads_key(script, key):
            errors.append(f"{key}: gate script {script_rel} does NOT read the key — the profile "
                          "claims enforcement the gate does not provide")
        else:
            verified.append(key)
        if spec.get("tier") == "required" and gate.get("on_absent") == "skip":
            errors.append(f"{key}: required, but its gate FAILS OPEN (on_absent: skip) — a "
                          "required key whose gate skips on absence is a vacuous declaration")
        # A `client_scoped: true` claim must be supported by the script: it has to take a project
        # selector (a --project flag, or the clients registry). Otherwise the profile would assert
        # enforcement at a client that cannot happen there.
        if gate.get("client_scoped") and script.is_file():
            body = read_text(script) or ""
            if not re.search(r"clients-policy\.json|--project", body):
                errors.append(
                    f"{key}: claims client_scoped, but {script_rel} takes no project selector — "
                    "it can only ever check the estate's own declaration")

    # 6 — do the declared projects' $schema references resolve?
    schema_rows = []
    reg = load_json(REGISTRY)
    for p in (reg or {}).get("projects", []):
        if not p.get("enabled"):
            continue
        decl_path = ROOT / p["root"] / ".w0m" / "sdlc.json"
        decl = load_json(decl_path)
        if decl is None:
            continue
        ref = decl.get("$schema")
        if not ref:
            schema_rows.append({"id": p["id"], "ref": None, "resolves": False})
            findings.append(f"{p['id']}: no $schema — nothing has ever validated its declaration")
            continue
        target = (decl_path.parent / ref).resolve() if not ref.startswith("http") else None
        ok = True if target is None else target.is_file()
        row = {"id": p["id"], "ref": ref, "resolves": ok, "drifted": False}
        schema_rows.append(row)
        if not ok:
            findings.append(f"{p['id']}: $schema `{ref}` DANGLES ({target}) — present, and never "
                            "validated. A presence check passes on it.")
        elif target is not None and p.get("role") in ("managed", "client"):
            # 🔴 A client that VENDORS the profile schema can drift from it silently — the exact
            # shape that produced the estate's stale openspec pin. Resolving is necessary and not
            # sufficient: the copy must still BE the profile schema.
            canonical = read_text(CANONICAL / profile.get("sdlc_schema", ""))
            local = read_text(target)
            if canonical is not None and local is not None and canonical != local:
                row["drifted"] = True
                findings.append(
                    f"{p['id']}: $schema resolves but its vendored copy has DRIFTED from "
                    f"{profile.get('sdlc_schema')} — it validates against a schema the estate no "
                    "longer publishes, which is worse than not validating at all")

    # ── Phase 7 — validate each declared CLIENT against the profile, not just the profile
    # against itself. This is the difference between "the profile is coherent" and "this client
    # conforms", and until it existed the profile could not answer the ticket's own question.
    required = sorted(k for k, v in keys.items() if v.get("tier") == "required")
    client_capable = sorted(k for k in required if keys[k]["gate"].get("client_scoped"))
    clients = []
    for p in (reg or {}).get("projects", []):
        if not p.get("enabled") or p.get("role") not in ("managed", "client"):
            continue
        decl = load_json(ROOT / p["root"] / ".w0m" / "sdlc.json")
        present = set(decl or {})
        missing = [k for k in required if k not in present]
        clients.append({
            "id": p["id"],
            "missing_required": missing,
            "conforms": not missing,
            # Of the keys this client DOES declare, how many can actually be checked here.
            "enforceable_here": sorted(k for k in required if k in present and k in client_capable),
        })
        if missing:
            findings.append(
                f"{p['id']}: missing {len(missing)} profile-required key(s) — "
                f"{', '.join(missing)}")

    if required and not client_capable:
        errors.append("no required key has a client-capable gate — the profile could not be "
                      "enforced at any client, which makes it a checklist")

    summary = {
        "profile_keys": len(keys),
        "required": required,
        "optional": sorted(k for k, v in keys.items() if v.get("tier") == "optional"),
        "excluded": sorted(excluded),
        "contract_keys": len(contract),
        "gates_verified": sorted(verified),
        "client_capable_required": client_capable,
        "estate_scoped_required": [k for k in required if k not in client_capable],
        "schema_refs": schema_rows,
        "clients": clients,
    }
    return errors, findings, summary


def main() -> int:
    argv = sys.argv[1:]
    global PROFILE
    if "--profile" in argv:
        i = argv.index("--profile")
        if i + 1 >= len(argv):
            print("  ✗ --profile needs a path")
            return 2
        PROFILE = Path(argv[i + 1]).resolve()

    errors, findings, summary = check()

    if "--json" in argv:
        print(json.dumps({"ok": not errors, "errors": errors, "findings": findings,
                          **summary}, indent=2))
        return 1 if errors or ("--enforce" in argv and findings) else 0

    print("\n  client profile — every key must name a gate that provably reads it\n")
    if summary:
        print(f"  contract {summary['contract_keys']} keys → "
              f"{len(summary['required'])} required · {len(summary['optional'])} optional · "
              f"{len(summary['excluded'])} excluded")
        print(f"    required: {', '.join(summary['required'])}")
        print(f"    optional: {', '.join(summary['optional'])}")
        print(f"    excluded: {', '.join(summary['excluded'])}")
        print(f"\n  {len(summary['gates_verified'])}/{summary['profile_keys']} gates verified "
              "from source (recipe exists · script exists · script reads the key)")

        # 🔴 The number that says whether this is a gate or a checklist.
        cc, es = summary["client_capable_required"], summary["estate_scoped_required"]
        print(f"\n  enforcement AT A CLIENT: {len(cc)}/{len(summary['required'])} required keys "
              "have a gate that can be pointed at one")
        print(f"    client-capable: {', '.join(cc) or '—'}")
        print(f"    estate-scoped only (checks w0m, cannot check a client): {', '.join(es) or '—'}")

        if summary["clients"]:
            print("\n  clients vs the profile:")
            for c in summary["clients"]:
                mark = "✓ conforms" if c["conforms"] else f"✗ missing {len(c['missing_required'])}"
                print(f"    {c['id']:10} {mark}"
                      + (f" — {', '.join(c['missing_required'])}" if c["missing_required"] else ""))

    if findings:
        print(f"\n [WARN] {len(findings)} finding(s) about declared projects:")
        for f in findings:
            print(f" [WARN] {f}")
    if errors:
        print(f"\n  ✗ {len(errors)} profile defect(s):")
        for e in errors:
            print(f"     ✗ {e}")
        print()
        return 1
    print("\n  ✓ profile intact — no key claims a gate it does not have\n")
    return 1 if ("--enforce" in argv and findings) else 0


if __name__ == "__main__":
    sys.exit(main())
