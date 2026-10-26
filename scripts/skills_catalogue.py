#!/usr/bin/env python3
"""skills_catalogue.py — the installed-skill catalogue for the SDLC tools surface.

Answers, for every project the estate declares, the question nothing else did: **what agent
skills are actually installed here, who manages them, and does anything they ship get to run on
the host?** Skills are executable instructions loaded into every agent session — a supply-chain
surface — and until now they were governed per project (`w0m skill check`) but never *catalogued*
across the estate beside the other tool surfaces.

Two settings per skill, from `project/policies/skills-policy.json`:

  managed    project | user | unmanaged
             `project` — vendored into the repo, declared in the manifest, hashed in the lockfile.
             `user`    — installed in ~/.claude/skills. Governed by ~/.claude/.w0m/skills.json +
                         skills.lock.json (T147 AC4 / T522). Undecided user-scope skills load into
                         that developer's sessions invisible to review and to every gate.
             `unmanaged` — present in the project or user scope, in neither the manifest nor the
                           exclude list.

  sandboxed  Whether the skill's SHIPPED CODE is confined to an isolated environment rather than
             run on the host. Only load-bearing for skills that ship runnable files; the catalogue
             measures that rather than assuming it, and says how few qualify.

The recommendation is `managed: project` + `sandboxed: true`. Deviations are REPORTED and exit 0;
`--enforce` makes them block.

Usage:
    python3 scripts/skills_catalogue.py                        # the catalogue + suggestions
    python3 scripts/skills_catalogue.py --enforce              # deviations block
    python3 scripts/skills_catalogue.py --json
    python3 scripts/skills_catalogue.py --policy <path>        # drive a policy fixture (tests)
    python3 scripts/skills_catalogue.py --registry <path>      # drive a registry fixture (tests)
    python3 scripts/skills_catalogue.py --user-skills <path>   # drive a user-scope fixture (tests)
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from schema_check import validate_declared_schema

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]                      # …/@wom
CANONICAL = ROOT / "w0m-web"                # …/w0m-web
SDLC = ROOT / ".w0m" / "sdlc.json"
DEFAULT_REGISTRY = ROOT / "project" / "policies" / "clients-policy.json"

POLICY: Path | None = None                  # resolved from .w0m/sdlc.json -> skills.policy or --policy
REGISTRY_OVERRIDE: Path | None = None       # --registry <path> (tests)
USER_SKILLS_OVERRIDE: Path | None = None    # --user-skills <path> (tests)

IGNORED_SKILL_DIRS = {
    "node_modules",
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
    ".next",
    ".svelte-kit",
    ".turbo",
    ".venv",
    "venv",
    "coverage",
}

RECIPE_HEADER_RE = re.compile(r"^@?([a-zA-Z_][a-zA-Z0-9_-]*)(?:\s+[^:=]*)?:(?!=)")
COMMENT_PREFIXES = ("#", "//", "--")


def resolve_user_skills_dir() -> Path:
    if USER_SKILLS_OVERRIDE is not None:
        return USER_SKILLS_OVERRIDE
    env_dir = os.environ.get("W0M_USER_SKILLS_DIR")
    if env_dir:
        return Path(env_dir).resolve()
    env_root = os.environ.get("W0M_USER_ROOT")
    if env_root:
        return (Path(env_root).resolve() / "skills")
    return Path.home() / ".claude" / "skills"


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
    runtime layer is symlinks into the governed set and a link is not its own content.
    Prunes dependency and build output trees (`node_modules`, `dist`, `build`, `__pycache__`,
    `.venv`, etc.) in-place during `os.walk` so third-party packages never inflate the count
    (T508 AC5)."""
    out: list[str] = []
    try:
        real_root = skill_dir.resolve()
        if not real_root.is_dir():
            return []
        for dirpath, dirnames, filenames in os.walk(real_root, followlinks=True):
            dirnames[:] = sorted(
                d for d in dirnames
                if not d.startswith(".") and d not in IGNORED_SKILL_DIRS
            )
            dp = Path(dirpath)
            for fname in sorted(filenames):
                if fname.startswith("."):
                    continue
                f = dp / fname
                if not f.is_file():
                    continue
                try:
                    is_exec = use_bit and bool(f.stat().st_mode & 0o111)
                except OSError:
                    is_exec = False
                if f.suffix in suffixes or is_exec:
                    out.append(f.relative_to(real_root).as_posix())
    except OSError:
        pass
    return sorted(out)


def host_invocations(
    surface_root: Path,
    skill: str,
    execs: list[str],
    project_root: Path | None = None,
) -> tuple[list[str], list[str]]:
    """Places in the project that invoke this skill's shipped code DIRECTLY — i.e. on the host.

    🔑 This is what turns `sandboxed` from an assertion into a measurement. A default of
    `sandboxed: true` inherited by every skill would declare something nobody checked — and it
    would have been FALSE here: Artemio's `just idea-refine-init` runs the skill's shipped script
    with `bash`, on the host, which is the opposite of sandboxed. A declaration that a call site
    contradicts is worse than no declaration, so the contradiction is reported.

    Scans tracked, human-authored surfaces (`justfile`, `Makefile`, `just/*.just`, `scripts/*`),
    deduplicating symlinked files by realpath and skipping comment lines (`#`, `//`, `--`) (T508 AC6).
    Returns `(locations, recipes)`.
    """
    if not execs:
        return [], []
    names = {Path(e).name for e in execs}
    raw_candidates: list[Path] = []
    roots = [surface_root]
    if project_root is not None:
        try:
            if project_root.resolve() != surface_root.resolve():
                roots.append(project_root)
        except OSError:
            pass
    for r in roots:
        raw_candidates.extend([r / "justfile", r / "Makefile"])
        just_dir = r / "just"
        if just_dir.is_dir():
            raw_candidates.extend(sorted(p for p in just_dir.glob("*.just") if p.is_file()))
        if r == surface_root and (r / "scripts").is_dir():
            raw_candidates.extend(sorted(p for p in (r / "scripts").glob("*") if p.is_file()))

    seen_real: set[Path] = set()
    candidates: list[Path] = []
    for c in raw_candidates:
        try:
            real = c.resolve()
        except OSError:
            continue
        if real == HERE or real in seen_real or not real.is_file():
            continue
        seen_real.add(real)
        candidates.append(c)

    found: list[str] = []
    recipes: list[str] = []
    skill_path_re = re.compile(r"(?:^|[/\s\"'])skills/([a-zA-Z0-9_-]+)/")
    for f in candidates:
        text = read_text(f)
        if text is None:
            continue
        is_just = f.name in ("justfile", "Makefile") or f.suffix == ".just"
        label_base = f"just/{f.name}" if f.parent.name == "just" else f.name
        current_recipe: str | None = None
        for i, line in enumerate(text.splitlines(), 1):
            stripped = line.lstrip()
            if not stripped or stripped.startswith(COMMENT_PREFIXES):
                continue
            if is_just and not line[0].isspace():
                m = RECIPE_HEADER_RE.match(line)
                if m:
                    current_recipe = m.group(1)
            if "skills/" in line and any(n in line for n in names):
                explicit_skills = skill_path_re.findall(line)
                if explicit_skills and skill not in explicit_skills:
                    continue
                found.append(f"{label_base}:{i}")
                if current_recipe and current_recipe not in recipes:
                    recipes.append(current_recipe)
    return found, recipes


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


def has_skills_surface(root: Path) -> bool:
    return (
        (root / ".w0m" / "skills.json").is_file()
        or bool(skill_dirs(root / ".agents" / "skills"))
        or bool(skill_dirs(root / ".claude" / "skills"))
    )


def discover_project_surfaces(p: dict, root: Path) -> tuple[list[tuple[str, Path]], list[str]]:
    """Discover and validate all skill surfaces for a project entry in `clients-policy.json` (T508 AC1-AC3)."""
    pid = p["id"]
    repos_decl = p.get("repos") or {}
    canonical = p.get("canonical_repo")
    errors: list[str] = []

    uncloned_portfolio = pid in ("k7", "mob") and bool(repos_decl) and not any(
        (root / rel).resolve().is_dir() for rel in repos_decl.values()
    )

    raw_candidates: list[tuple[str, Path]] = [(".", root)]
    if not uncloned_portfolio:
        if canonical and canonical != ".":
            if repos_decl:
                if canonical not in repos_decl:
                    return [], [
                        f"{pid}: canonical_repo {canonical!r} is not a key of `repos` "
                        f"({', '.join(sorted(repos_decl))}) or '.'"
                    ]
                cp = (root / repos_decl[canonical]).resolve()
            else:
                cp = (root / str(canonical)).resolve()
            if not cp.is_dir():
                return [], [f"{pid}: declared canonical_repo {canonical!r} does not exist — {cp}"]
            raw_candidates.append((str(canonical), cp))

        for rname, rel in sorted(repos_decl.items()):
            rp = (root / rel).resolve()
            if not rp.is_dir():
                errors.append(f"{pid}: declared repo {rname!r} does not exist — {rp}")
                continue
            raw_candidates.append((rname, rp))
        if errors:
            return [], errors
    else:
        if canonical and canonical != ".":
            canonical_stub = (root / str(canonical)).resolve()
            if canonical_stub.is_dir():
                raw_candidates.append((str(canonical), canonical_stub))

    deduped: list[tuple[str, Path]] = []
    seen_paths: set[Path] = set()
    for label, sp in raw_candidates:
        real = sp.resolve()
        if real in seen_paths:
            continue
        seen_paths.add(real)
        deduped.append((label, sp))

    with_skills = [(label, sp) for label, sp in deduped if has_skills_surface(sp)]
    if with_skills:
        active = with_skills
    else:
        primary = next(
            ((label, sp) for label, sp in deduped if canonical and label == str(canonical)),
            deduped[0],
        )
        active = [primary]

    # T508 AC3 — refuse a silent corpus shrink: any `.w0m/skills.json` sitting in `root` or a direct
    # child directory of `root` that is not in `active` means a live skills surface was dropped.
    if not uncloned_portfolio:
        active_roots = {sp.resolve() for _, sp in active}
        manifest_candidates = [root / ".w0m" / "skills.json", *sorted(root.glob("*/.w0m/skills.json"))]
        for mf in manifest_candidates:
            if not mf.is_file():
                continue
            m_root = mf.parent.parent.resolve()
            if m_root not in active_roots:
                errors.append(
                    f"{pid}: uncatalogued skills manifest at {mf} — surface {m_root.name!r} is "
                    "not in the declared project surfaces"
                )
    return active, errors


def catalogue_surface(
    pid: str,
    surface: str,
    s_root: Path,
    project_root: Path,
    policy: dict,
    role: str = "managed",
) -> dict:
    """Every skill installed for one project surface, with both settings resolved."""
    det = policy.get("detect_executable", {})
    suffixes = set(det.get("suffixes", []))
    use_bit = bool(det.get("executable_bit"))
    overrides = {k: v for k, v in policy.get("overrides", {}).items() if not k.startswith("_")}
    defaults = {k: v for k, v in policy.get("defaults", {}).items() if not k.startswith("_")}
    rec = policy.get("recommended", {})

    manifest = load_json(s_root / ".w0m" / "skills.json") or {}
    manifest_declared = set(manifest.get("skills") or {})
    declared = set(manifest_declared)
    if role in ("self-managed", "half-managed"):
        declared |= load_portable_skills()
    excluded = set(manifest.get("exclude") or {})
    lock_path = s_root / ".w0m" / "skills.lock.json"
    lock = load_json(lock_path) or {}
    locked = set(lock.get("skills") or {})

    # Governed layer first: it is what integrity is computed over. The runtime layer adds
    # whatever is NOT a link into it — CLI-generated families, and accidental writes, which look
    # identical from here and are told apart by the manifest's exclude list.
    governed = skill_dirs(s_root / ".agents" / "skills")
    runtime = skill_dirs(s_root / ".claude" / "skills")
    installed: dict[str, Path] = {**runtime, **governed}

    rows = []
    for name, path in sorted(installed.items()):
        if name in declared:
            managed = "project"
        elif name in excluded:
            managed = "excluded"
        else:
            managed = "unmanaged"
        ov = overrides.get(f"{pid}/{surface}:{name}") or overrides.get(f"{pid}:{name}", {})
        execs = ships_executable(path, suffixes, use_bit)
        # `sandboxed` is only ever DECLARED — nothing here can prove confinement. What can be
        # measured is the opposite: evidence the code runs on the host. So the inherited default
        # is recorded as `declared: False`, never dressed up as a finding.
        sandbox_declared = "sandboxed" in ov      # NOT `declared` — that is the manifest set
        sandboxed = ov.get("sandboxed", rec.get("sandboxed", True))
        on_host, on_host_recipes = host_invocations(s_root, name, execs, project_root=project_root)
        rows.append({
            "skill": name,
            "surface": surface,
            "managed": managed,
            "default": name in defaults,
            "in_lock": name in locked,
            "sandboxed": sandboxed,
            "sandboxed_declared": sandbox_declared,
            "override_reason": ov.get("reason"),
            "ships_executable": execs,
            "runs_on_host": on_host,
            "runs_on_host_recipes": on_host_recipes,
            "layer": "governed" if name in governed else "runtime-only",
        })
    return {
        "surface": surface,
        "root": str(s_root),
        "manifest": bool(manifest),
        "lock": lock_path.is_file(),
        "counts": {
            "declared": len(manifest_declared),
            "excluded_declared": len(excluded),
            "installed": len(rows),
            "project_managed": sum(1 for r in rows if r["managed"] == "project"),
            "defaults_installed": sum(1 for r in rows if r["default"]),
            "excluded": sum(1 for r in rows if r["managed"] == "excluded"),
            "unmanaged": sum(1 for r in rows if r["managed"] == "unmanaged"),
            "ships_executable": sum(1 for r in rows if r["ships_executable"]),
        },
        "skills": rows,
    }


def catalogue_project(
    pid: str,
    root: Path,
    surfaces: list[dict],
    canonical_repo: str | None = None,
) -> dict:
    """Roll up one or more catalogued surfaces into a project entry."""
    all_rows = [r for s in surfaces for r in s["skills"]]
    distinct_installed = len({r["skill"] for r in all_rows})
    distinct_execs = len({r["skill"] for r in all_rows if r["ships_executable"]})
    primary_root = str(root)
    if canonical_repo and canonical_repo != ".":
        for s in surfaces:
            if s["surface"] == canonical_repo:
                primary_root = s["root"]
                break
    elif len(surfaces) == 1:
        primary_root = surfaces[0]["root"]

    return {
        "project": pid,
        "root": primary_root,
        "manifest": any(s["manifest"] for s in surfaces),
        "surfaces": surfaces,
        "counts": {
            "surfaces": len(surfaces),
            "declared": sum(s["counts"]["declared"] for s in surfaces),
            "installed": sum(s["counts"]["installed"] for s in surfaces),
            "distinct_installed": distinct_installed,
            "project_managed": sum(s["counts"]["project_managed"] for s in surfaces),
            "defaults_installed": sum(s["counts"]["defaults_installed"] for s in surfaces),
            "excluded": sum(s["counts"]["excluded"] for s in surfaces),
            "unmanaged": sum(s["counts"]["unmanaged"] for s in surfaces),
            "ships_executable": distinct_execs,
        },
        "skills": all_rows,
    }


def resolve_policy() -> tuple[Path | None, str | None]:
    """The policy path comes from `.w0m/sdlc.json -> skills.policy`, never from a constant."""
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
    if err or policy_path is None:
        return {}, [], [err or "no skills policy path resolved"]
    policy = load_json(policy_path)
    if policy is None:
        return {}, [], [f"policy unreadable or not an object: {policy_path}"]
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

    reg_path = REGISTRY_OVERRIDE or DEFAULT_REGISTRY
    reg = load_json(reg_path)
    if reg is None:
        return {}, [], [f"project registry unreadable: {reg_path}"]

    projects = []
    for p in reg.get("projects", []):
        if not p.get("enabled"):
            continue
        pid = p["id"]
        root = (ROOT / p["root"]).resolve()
        if not root.is_dir():
            return {}, [], [f"{pid}: declared root does not exist — {root}"]
        surface_specs, surf_errors = discover_project_surfaces(p, root)
        if surf_errors:
            return {}, [], surf_errors
        repos_decl = p.get("repos") or {}
        uncloned_portfolio = pid in ("k7", "mob") and bool(repos_decl) and not any(
            (root / rel).resolve().is_dir() for rel in repos_decl.values()
        )
        surfaces = []
        for s_label, s_root in surface_specs:
            s_cat = catalogue_surface(pid, s_label, s_root, root, policy, role=p.get("role", "managed"))
            if not uncloned_portfolio and s_cat["counts"]["declared"] > 0 and s_cat["counts"]["installed"] == 0:
                return {}, [], [
                    f"{pid} ({s_label}): manifest declares {s_cat['counts']['declared']} skill(s) "
                    f"at {s_root}, but 0 are installed on disk — refusing silent corpus shrink"
                ]
            surfaces.append(s_cat)
        projects.append(catalogue_project(pid, root, surfaces, canonical_repo=p.get("canonical_repo")))

    if not projects:
        return {}, [], ["no enabled project — a catalogue over nothing is not a catalogue"]

    total = sum(pr["counts"]["installed"] for pr in projects)
    if total == 0:
        return {}, [], ["zero skills catalogued across every project — refusing to report a "
                        "clean catalogue over an empty corpus"]

    # T508 AC7 — orphan overrides in skills-policy.json fail closed (exit 2).
    overrides = {k: v for k, v in policy.get("overrides", {}).items() if not k.startswith("_")}
    installed_keys = {
        f"{pr['project']}:{r['skill']}"
        for pr in projects
        for r in pr["skills"]
    } | {
        f"{pr['project']}/{r['surface']}:{r['skill']}"
        for pr in projects
        for r in pr["skills"]
    }
    orphan_overrides = sorted(k for k in overrides if k not in installed_keys)
    if orphan_overrides:
        return {}, [], [
            f"orphan override(s) in {policy_path.name} match no installed skill across any "
            f"catalogued surface: {', '.join(orphan_overrides)}"
        ]

    # USER scope (T147 AC4 / T522): governed by ~/.claude/.w0m/skills.json + skills.lock.json.
    user_skills_dir = resolve_user_skills_dir()
    user_root = user_skills_dir.parent
    user_manifest_path = user_root / ".w0m" / "skills.json"
    user_lock_path = user_root / ".w0m" / "skills.lock.json"
    user_manifest = load_json(user_manifest_path) or {}
    user_declared = set(user_manifest.get("skills") or {})
    user_excluded = {
        k: v for k, v in (user_manifest.get("exclude") or {}).items()
        if isinstance(v, str) and v.strip()
    }
    user = sorted(skill_dirs(user_skills_dir))
    user_managed = [u for u in user if u in user_declared]
    user_excluded_installed = [u for u in user if u not in user_declared and u in user_excluded]
    user_unmanaged = [u for u in user if u not in user_declared and u not in user_excluded]

    rec = policy.get("recommended", {})
    suggestions: list[str] = []
    seen_exec_checks: set[tuple[str, str]] = set()
    for pr in projects:
        for r in pr["skills"]:
            surf_tag = f" ({r['surface']})" if len(pr["surfaces"]) > 1 else ""
            if r["managed"] == "unmanaged":
                suggestions.append(
                    f"{pr['project']}:{r['skill']}{surf_tag} — installed but in neither the manifest nor "
                    f"`exclude`; suggest managed: {rec.get('managed', 'project')} (declare it, or "
                    "exclude it with a reason)")
            if not r["ships_executable"]:
                continue
            exec_key = (pr["project"], r["skill"])
            if exec_key in seen_exec_checks:
                continue
            seen_exec_checks.add(exec_key)
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
    if user_unmanaged:
        suggestions.append(
            f"user scope — {len(user_unmanaged)} skill(s) in {user_skills_dir} load into this "
            "developer's sessions and are in NO manifest or `exclude`: invisible to review, to "
            f"hashing and to every gate ({', '.join(user_unmanaged[:4])}"
            f"{' …' if len(user_unmanaged) > 4 else ''}); suggest managed: "
            f"{rec.get('managed', 'project')} or record a decision in {user_manifest_path}")

    return {
        "recommended": rec,
        "defaults": defaults,
        "projects": projects,
        "user_scope": {
            "path": str(user_skills_dir),
            "manifest": bool(user_manifest),
            "lock": user_lock_path.is_file(),
            "counts": {
                "installed": len(user),
                "managed": len(user_managed),
                "excluded": len(user_excluded_installed),
                "unmanaged": len(user_unmanaged),
            },
            "skills": user,
            "managed_skills": user_managed,
            "excluded_skills": user_excluded_installed,
            "unmanaged_skills": user_unmanaged,
        },
    }, suggestions, []


def unique_exec_rows(projects: list[dict]) -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    seen: set[tuple[str, str]] = set()
    for pr in projects:
        for r in pr["skills"]:
            if not r["ships_executable"]:
                continue
            key = (pr["project"], r["skill"])
            if key in seen:
                continue
            seen.add(key)
            out.append((pr["project"], r))
    return out


def main() -> int:
    argv = sys.argv[1:]
    global POLICY, REGISTRY_OVERRIDE, USER_SKILLS_OVERRIDE
    if "--policy" in argv:
        i = argv.index("--policy")
        if i + 1 >= len(argv):
            print("  ✗ --policy needs a path")
            return 2
        POLICY = Path(argv[i + 1]).resolve()
    if "--registry" in argv:
        i = argv.index("--registry")
        if i + 1 >= len(argv):
            print("  ✗ --registry needs a path")
            return 2
        REGISTRY_OVERRIDE = Path(argv[i + 1]).resolve()
    if "--user-skills" in argv:
        i = argv.index("--user-skills")
        if i + 1 >= len(argv):
            print("  ✗ --user-skills needs a path")
            return 2
        USER_SKILLS_OVERRIDE = Path(argv[i + 1]).resolve()

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
    hdr = (f"  {'project':14} {'installed':>9} {'managed':>8} {'excluded':>8} {'unmanaged':>9} "
           f"{'ships code':>10}")
    print(hdr)
    print("  " + "─" * (len(hdr) - 2))
    for pr in cat["projects"]:
        c = pr["counts"]
        print(f"  {pr['project']:14} {c['installed']:9} {c['project_managed']:8} "
              f"{c['excluded']:8} {c['unmanaged']:9} {c['ships_executable']:10}")
        if len(pr["surfaces"]) > 1:
            for s in pr["surfaces"]:
                sc = s["counts"]
                label = f"  └ {s['surface']}"
                print(f"  {label:14} {sc['installed']:9} {sc['project_managed']:8} "
                      f"{sc['excluded']:8} {sc['unmanaged']:9} {sc['ships_executable']:10}")

    u = cat["user_scope"]
    uc = u["counts"]
    print(
        f"\n  user scope ({u['path']}): {uc['installed']} installed — "
        f"{uc['managed']} managed · {uc['excluded']} excluded · {uc['unmanaged']} unmanaged"
    )

    execs = unique_exec_rows(cat["projects"])
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
