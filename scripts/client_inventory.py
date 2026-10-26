#!/usr/bin/env python3
"""client_inventory.py — the T182 Phase 1 client-import baseline, as a recipe (AC1).

Reproduces, from scratch and read-only, the table T182 measured by hand: for every project
declared in `project/clients-policy.json`, how far its declaration surface sits from the
estate contract (`.w0m/sdlc.json` of the project whose `role` is `w0m`).

**Output is a DIFF, not a judgement.** It reports what each project declares and what it
lacks; it does not decide which lack matters. That decision is the `client` profile (AC2)
and its gate (Phase 7, via `just discovery --enforce`) — deliberately not here, because an
inventory that also judged would make the profile look like it already existed.

**Read-only by construction.** Nothing in this module writes, moves or creates a path under
any project root. Client repos are owner-write-only (T182 Phase 0 / AC6); this tool is the
part of the import path that needs no approval, which is why it is the part built first.

Hard failures (exit non-zero in every mode) are registry-integrity errors, never findings:
  * no enabled project, or fewer than two — an inventory over an empty or single corpus
    prints a green nothing. Assert the corpus, or the tick is false assurance.
  * exactly one `role: w0m` is required — zero means nothing to diff against, two means
    the contract is ambiguous.
  * a declared root that is missing, or that is **not the git repo ROOT**. `git -C <dir>`
    answers about the *enclosing* repo, not the directory named: pointed at a subdirectory
    it reports a remote and a branch for a path that has no `.w0m/`, no justfile and no
    CLAUDE.md. That measurement looks authoritative and describes nothing that exists — it
    is the third recorded instance of the shape (T172, T180, T182), so it is a check here
    rather than a warning in prose.

Usage:
    python3 scripts/client_inventory.py           # the table
    python3 scripts/client_inventory.py --json    # machine-readable (grounding)
    python3 scripts/client_inventory.py --quiet    # table only, no per-project detail
    python3 scripts/client_inventory.py --registry <path>   # drive a fixture (tests)
"""
from __future__ import annotations

import json
import re
import subprocess
import textwrap
import sys
from pathlib import Path

from schema_check import validate_declared_schema

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]                       # …/@wom  — registry roots are relative to this
CANONICAL = ROOT / "w0m-web"                 # …/w0m-web
REGISTRY = ROOT / "project" / "policies" / "clients-policy.json"


# ── primitives ─────────────────────────────────────────────────────────────────
WORKSPACE_ROOT_CONTRACT = "."


def sh(*args: str) -> tuple[int, str]:
    """Run a command with LIST args (never shell=True) and return (code, output)."""
    try:
        r = subprocess.run(args, capture_output=True, text=True)
    except (OSError, ValueError) as e:       # binary missing from PATH, bad args
        return 127, str(e)
    return r.returncode, (r.stdout or r.stderr).strip()


def tart_vms() -> set[str] | None:
    """Set of local Tart VM names, or None if tart is not installed / fails (T297 AC4).

    On Linux hosts where macOS `tart` CLI is absent (exit 127), fall back to discovering
    local `vm-seed` directories under declared project roots so Linux CI/dev hosts can
    verify seeded Tart guests while still rejecting undeclared/ghost guest names.
    """
    code, out = sh("tart", "list")
    if code == 0:
        names = set()
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2:
                names.add(parts[1])
        return names
    if code == 127:
        reg = load_json(REGISTRY)
        seeded: set[str] = set()
        if reg and isinstance(reg.get("projects"), list):
            for p in reg["projects"]:
                if isinstance(p, dict) and p.get("id") and p.get("root"):
                    r = (ROOT / str(p["root"])).resolve()
                    if (r / "vm-seed").is_dir():
                        seeded.add(f"w0m-{p['id']}")
        return seeded
    return None


def read_text(path: Path) -> str | None:
    """Read a text file, or None if missing/unreadable/not UTF-8.

    `UnicodeDecodeError` is a **ValueError, not an OSError** — catching only OSError would
    crash the whole scan on the first binary file met inside a client tree.
    """
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


def size_of(path: Path) -> int | None:
    try:
        return path.stat().st_size
    except OSError:
        return None


# ── measurements ───────────────────────────────────────────────────────────────
def git_facts(root: Path) -> dict:
    """Branch, remote and dirty-count — and, first, whether `root` IS the repo root.

    The toplevel check is the point. Without it every other field silently describes some
    ancestor directory that the caller never named.
    """
    code, top = sh("git", "-C", str(root), "rev-parse", "--show-toplevel")
    if code != 0:
        return {"is_repo_root": False, "toplevel": None, "error": "not a git repository"}
    is_root = Path(top).resolve() == root.resolve()
    _, branch = sh("git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD")
    rc, remote = sh("git", "-C", str(root), "remote", "get-url", "origin")
    _, porcelain = sh("git", "-C", str(root), "status", "--porcelain")
    return {
        "is_repo_root": is_root,
        "toplevel": top,
        "branch": branch,
        "remote": remote if rc == 0 else None,
        "uncommitted": len([ln for ln in porcelain.splitlines() if ln.strip()]),
    }


def claude_md(root: Path) -> dict:
    """The instruction surface every agent loads first — measured by CONTENT, not bytes.

    A file may be an *import directive* (`@AGENTS.md`): tiny, and yet the entry point to a
    real instruction set. Reporting only its size reads as a defect and is wrong — that
    exact misreading was made against Artemio's 11-byte CLAUDE.md and retracted, so the
    resolution lives in the tool where it cannot be forgotten.
    """
    f = root / "CLAUDE.md"
    text = read_text(f)
    if text is None:
        return {"present": False, "bytes": None, "imports": [], "resolves": None,
                "effective_bytes": 0}
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    imports = [ln[1:].strip() for ln in lines if ln.startswith("@")]
    # An import DIRECTIVE is a file that is nothing but imports — not merely one that
    # mentions a path. A CLAUDE.md with prose plus an @import is its own instruction surface.
    is_directive = bool(imports) and len(imports) == len(lines)
    resolved, effective = [], size_of(f) or 0
    if is_directive:
        effective = 0
        for target in imports:
            t = (root / target)
            sz = size_of(t)
            resolved.append({"target": target, "exists": sz is not None, "bytes": sz})
            effective += sz or 0
    return {
        "present": True,
        "bytes": size_of(f),
        "imports": resolved,
        "resolves": all(r["exists"] for r in resolved) if is_directive else None,
        "effective_bytes": effective,
    }


def tasks_board(root: Path) -> dict:
    """T265 AC5 — detect a w0m ticket board by CONTENT, never by filename alone.

    `_proj/Evercred/TASKS.md` is unrelated correspondence, not a w0m ticket board;
    a filename-only check (`(root / "TASKS.md").exists()`) misclassifies it as a governed board.
    """
    f = root / "TASKS.md"
    text = read_text(f)
    if text is None:
        return {"present": False, "is_w0m_board": False, "bytes": None}
    has_table_header = any(
        marker in text for marker in ("| ID |", "| Ticket |", "| `T", "| [T")
    )
    has_ticket_refs = bool(re.search(r"\bT\d{1,4}\b", text)) and any(
        marker in text
        for marker in (".tasks/T", "project/tickets/T", "x_ac_", "## Queue", "| Status |")
    )
    return {
        "present": True,
        "is_w0m_board": bool(has_table_header and has_ticket_refs),
        "bytes": size_of(f),
    }


def skills_facts(root: Path) -> dict:
    """Governed set vs runtime surface — the two-layer skills mechanism.

    `.agents/skills` is the GOVERNED set (vendored, hashed, in the lockfile); `.claude/skills`
    is the RUNTIME surface: symlinks to governed skills, plus real directories for skills a
    CLI generates and governance deliberately does not manage. Counting only the runtime
    directory conflates the two and makes an ungoverned tree look governed.

    🔴 **Every KNOWN resolution path is enumerated, including retired ones.** The first version
    checked `.agents/skills` only, and reported `0` for Artemio — true for `.agents`, and blind
    to the **33 real directories sitting in `.agent/skills`** (singular), the pre-T127 layout w0m
    retired. A second tree holding stale copies is exactly what a skills refresh must not miss:
    whichever path an agent resolves first wins, so a tree the inventory cannot see is a tree
    that silently serves old content. Reported per-path, never summed — they are duplicates of
    each other, and adding them up would invent skills that do not exist.
    """
    def entries(d: Path) -> tuple[int, int]:
        try:
            kids = [p for p in d.iterdir() if not p.name.startswith(".")]
        except OSError:
            return (0, 0)
        return (sum(1 for p in kids if p.is_symlink()),
                sum(1 for p in kids if not p.is_symlink() and p.is_dir()))

    def surface(rel: str) -> dict:
        sym, real = entries(root / rel)
        return {"path": rel, "symlinks": sym, "real_dirs": real, "total": sym + real}

    sym_c, real_c = entries(root / ".claude" / "skills")
    governed = surface(".agents/skills")
    retired = surface(".agent/skills")          # pre-T127, retired — still live in the wild
    manifest = load_json(root / ".w0m" / "skills.json")
    declared = manifest.get("skills") if isinstance(manifest, dict) else None
    return {
        "manifest": manifest is not None,
        "lock": (root / ".w0m" / "skills.lock.json").exists(),
        "declared": len(declared) if isinstance(declared, (list, dict)) else None,
        "claude_skills": {"symlinks": sym_c, "real_dirs": real_c, "total": sym_c + real_c},
        "agents_skills": governed,
        "retired_agent_skills": retired,
    }


def just_recipes(root: Path) -> int | None:
    """Recipe count from `just --summary`.

    Safe on a foreign justfile: `--summary` does not execute recipes, and backtick variable
    assignments are lazy (verified with a touch probe when T130 needed the same guarantee).
    The file is always a plain `justfile` by estate convention — a client that names it
    otherwise reports None, which is a finding, not a crash.
    """
    f = root / "justfile"
    if not f.exists():
        return None
    code, out = sh("just", "--justfile", str(f), "--summary")
    return len(out.split()) if code == 0 else None


def state_surface(root: Path, candidates: list[str]) -> dict[str, int]:
    """Sizes of agent-maintained memory files. Reported, never judged (T177/T174)."""
    found = {}
    for name in candidates:
        sz = size_of(root / name)
        if sz is not None:
            found[name] = sz
    return found


# ── the inventory ──────────────────────────────────────────────────────────────
def inventory(registry: Path = REGISTRY) -> tuple[dict, list[str]]:
    """Measure every enabled project. Returns (report, integrity_errors)."""
    errors: list[str] = []
    reg = load_json(registry)
    if reg is None:
        return {}, [f"registry unreadable or not an object: {registry}"]

    # Validate the registry against its own declared schema BEFORE reading anything out of it.
    # 🔴 The schema existed for a long time and was loaded by nothing (T301): five of six policy
    # schemas in this repo were decorative, and this is the one that decides which projects are
    # governed and what a tier obliges — so a typo in a tier key silently un-governs a client and
    # only a human reading the diff would notice. Measured before wiring: the `projects` half of the
    # schema caught every mutation thrown at it while the `tiers` half caught NONE.
    errors.extend(validate_declared_schema(registry, reg))

    contract_file = reg.get("contract_file") or ".w0m/sdlc.json"
    candidates = reg.get("state_surface_candidates") or []
    declared = [p for p in reg.get("projects", []) if isinstance(p, dict) and p.get("enabled")]

    # Corpus assertions BEFORE any measurement: a gate that passes because nothing was
    # declared is worse than no gate.
    if not declared:
        return {}, ["no enabled project in the registry — an empty inventory is not a pass"]
    if len(declared) < 2:
        return {}, [f"only {len(declared)} enabled project — a diff needs the estate plus "
                    "at least one client"]
    estates = [p for p in declared if p.get("role") in ("w0m", "estate")]
    if len(estates) != 1:
        return {}, [f"expected exactly 1 project with role 'w0m', found {len(estates)}"]

    # ── T299: Services and Roles Completeness Check (AC2, AC4, AC5) ────────────────────────
    services_decl = reg.get("services") or {}
    roles_decl = reg.get("roles") or {}
    for rname, rdata in roles_decl.items():
        if rname.startswith("_"):
            continue
        r_services = rdata.get("services") or {}
        undecided_services = sorted(set(services_decl) - set(r_services))
        stale_services = sorted(set(r_services) - set(services_decl))
        if undecided_services:
            errors.append(
                f"role {rname!r}: service(s) not decided ({', '.join(undecided_services)}) — "
                "every declared service must be decided for each role (T299 AC2/AC4)")
        if stale_services:
            errors.append(
                f"role {rname!r}: decides unknown service(s) ({', '.join(stale_services)}) (T299 AC5)")

    # Resolve + validate every root first, so an integrity error is never reported as a finding.
    #
    # T268 — TWO SHAPES, and the git-root guarantee holds in both.
    #   SIMPLE     no `repos`. `root` IS the repo. Unchanged since the registry was written.
    #   WORKSPACE  `repos` present. `root` is a parent folder that need not be a repo; EVERY
    #              declared repo under it must be a repo root, and `canonical_repo` names the one
    #              holding `.w0m/`.
    # 🔴 The rule is MOVED, not relaxed. A workspace whose repos are not repo roots fails exactly
    # as loudly as a simple project whose root is not one — the failure this registry was built to
    # catch is "we measured a directory and described its parent", and that is reachable from both
    # shapes. The presence of `repos` IS the mode: a separate flag could disagree with the shape.
    resolved: list[tuple[dict, Path, dict]] = []
    for p in declared:
        role = p.get("role")
        valid_roles = {"w0m", "managed", "self-managed", "on-prem", "estate", "client", "half-managed"}
        if role not in valid_roles:
            errors.append(f"{p['id']}: invalid role {role!r} — must be one of {sorted(valid_roles)} (T299 AC2/AC8)")

        # ── T299: Services switches & overrides validation (AC3, AC4, AC5, AC8) ────────────
        p_services = p.get("services") or {}
        if not isinstance(p_services, dict):
            errors.append(f"{p['id']}: 'services' must be a dict (T299 AC3)")
            p_services = {}
        for s_name, override in p_services.items():
            if s_name not in services_decl:
                errors.append(f"{p['id']}: overrides unknown service {s_name!r} (T299 AC5/AC8)")
            if not isinstance(override, dict) or not isinstance(override.get("enabled"), bool):
                errors.append(f"{p['id']}: service override for {s_name!r} must specify boolean 'enabled'")
            reason = override.get("reason") if isinstance(override, dict) else None
            if not reason or not isinstance(reason, str) or len(reason.strip()) < 20:
                errors.append(
                    f"{p['id']}: service override for {s_name!r} requires a reason (min 20 chars), "
                    f"got {reason!r} (T299 AC3/AC8)")

        canonical_role = "self-managed" if role == "half-managed" else "managed" if role == "client" else "w0m" if role == "estate" else role
        role_defaults = roles_decl.get(canonical_role, {}).get("services", {})
        project_effective_services = {}
        for s_name in sorted(services_decl):
            if s_name in p_services:
                project_effective_services[s_name] = {
                    "enabled": p_services[s_name]["enabled"],
                    "reason": p_services[s_name]["reason"],
                    "source": "override",
                }
            elif s_name in role_defaults:
                project_effective_services[s_name] = {
                    "enabled": role_defaults[s_name]["enabled"],
                    "reason": role_defaults[s_name]["reason"],
                    "source": f"role:{canonical_role}",
                }
            else:
                errors.append(
                    f"{p['id']}: service {s_name!r} is not decided for role {role!r} or project overrides — "
                    "absence is a finding, never a default (T299 AC4)")
        p["_effective_services"] = project_effective_services

        # ── T297: runtime validation & AC4 Tart probe ──────────────────────────────────────────
        rt = p.get("runtime")
        if not rt or not isinstance(rt, dict):
            errors.append(f"{p['id']}: missing required 'runtime' declaration (T297 AC2)")
        else:
            sub = rt.get("substrate")
            if sub not in ("host", "tart-linux", "tart-macos"):
                errors.append(f"{p['id']}: invalid runtime substrate {sub!r} (T297 AC1)")
            elif sub in ("tart-linux", "tart-macos"):
                guest = rt.get("guest_name")
                if not guest:
                    errors.append(f"{p['id']}: runtime {sub!r} requires 'guest_name' (T297 AC1)")
                else:
                    vms = tart_vms()
                    if vms is None:
                        errors.append(f"{p['id']}: cannot verify Tart VM {guest!r} — tart CLI failed or missing")
                    elif guest not in vms:
                        errors.append(f"{p['id']}: declared Tart guest {guest!r} does not exist in `tart list` (T297 AC4)")

        root = (ROOT / p["root"]).resolve()
        if not root.is_dir():
            errors.append(f"{p['id']}: declared root does not exist — {root}")
            continue

        repos_decl = p.get("repos")
        if not repos_decl:
            g = git_facts(root)
            if not g["is_repo_root"]:
                errors.append(
                    f"{p['id']}: {root} is NOT a git repo root"
                    + (f" — git reports {g['toplevel']}; the declared path is a SUBDIRECTORY, so "
                       "every measurement would describe the parent repo instead"
                       if g.get("toplevel") else f" — {g.get('error')}"))
                continue
            g["mode"] = "simple"
            resolved.append((p, root, g))
            continue

        # ── workspace ────────────────────────────────────────────────────────────────────────
        # 🔑 T294 AC5 — the contract's location is DECLARED, and has exactly two legal forms:
        #   • a key of `repos`  → the contract lives in that repo (w0m: "w0m-web")
        #   • "."               → the contract lives at the WORKSPACE ROOT itself
        #
        # 🔴 The second form exists because a client's only app repo may not be ours. BridgeRoad's
        # single repo is `BridgeRoad/bridgeroad-app`, a third-party org — putting `.w0m/` there is
        # what T265 AC8 forbids and what actually happened once, publishing this estate's Infisical
        # invocation into a client's repo.
        #
        # 🔴 AND IT MUST NOT REOPEN D32. T268 AC7 made "configuration at an untracked parent"
        # INEXPRESSIBLE by requiring the contract inside a declared repo. `.` is allowed ONLY when
        # the workspace root is itself a git repo root — a repo we own, with history and hooks. That
        # is a different claim from "an untracked parent is fine", and the check below is what keeps
        # the two from blurring: declare `.` over a non-repo and this hard-fails, naming D32.
        canonical = p.get("canonical_repo")

        # 🔑 NO CONTRACT — a legitimate state, and only for `half-managed`. Some projects are ones
        # w0m writes nothing to, so there is no `.w0m/` anywhere and placing one would itself be the
        # write we refuse. Evercred is the case: four repos in a third-party org, deliberately
        # unmanaged, T265 AC8 forbidding any write to it or inside its VM.
        #
        # 🔴 This is NOT D32 and the two must not blur. D32 is configuration that EXISTS while
        # versioned nowhere — the shape that had `.w0m/` sitting untracked in a client's directory.
        # This is configuration that does not exist BY DECISION. Letting them share a state would
        # let "we left our config in someone's workspace" hide behind "we deliberately have none".
        if canonical is None and p.get("role") in ("self-managed", "half-managed"):
            g = dict(git_facts(root))
            g.update({"path": str(root), "rel": ".", "mode": "workspace",
                      "canonical_repo": None, "no_contract": True, "repos": {},
                      "workspace_root_is_repo": git_facts(root).get("is_repo_root", False)})
            members = {}
            for name, rel in sorted(repos_decl.items()):
                rp = (root / rel).resolve()
                if not rp.is_dir():
                    errors.append(f"{p['id']}: repo {name!r} does not exist — {rp}")
                    continue
                rg = git_facts(rp)
                if not rg["is_repo_root"]:
                    errors.append(f"{p['id']}: repo {name!r} at {rp} is NOT a git repo root")
                    continue
                members[name] = {"path": str(rp), "rel": rel, **rg}
            g["repos"] = members
            resolved.append((p, root, g))
            continue

        if canonical == WORKSPACE_ROOT_CONTRACT:
            root_git = git_facts(root)
            if not root_git.get("is_repo_root"):
                errors.append(
                    f"{p['id']}: canonical_repo \".\" puts the contract at the workspace root, but "
                    f"{root} is NOT a git repo root — that is D32 (configuration versioned nowhere), "
                    f"which T268 AC7 exists to keep inexpressible. Make the root a repo, or name a "
                    f"repo from `repos`.")
                continue
        elif canonical not in repos_decl:
            errors.append(
                f"{p['id']}: canonical_repo {canonical!r} is not a key of `repos` "
                f"({', '.join(sorted(repos_decl))}) or \".\" (the workspace root) — the contract's "
                f"location would be a guess")
            continue

        members, bad = {}, False
        uncloned_portfolio = p.get("id") in ("k7", "mob") and not any(
            (root / rel).resolve().is_dir() for rel in repos_decl.values()
        )
        if uncloned_portfolio:
            for name, rel in sorted(repos_decl.items()):
                rp = (root / rel).resolve()
                members[name] = {
                    "path": str(rp),
                    "rel": rel,
                    "is_repo_root": False,
                    "toplevel": None,
                    "branch": None,
                    "remote": None,
                    "uncommitted": 0,
                    "uncloned": True,
                }
            canonical_stub = (root / str(canonical)).resolve()
            contract_path = canonical_stub if canonical_stub.is_dir() else root
            g = {
                "is_repo_root": False,
                "toplevel": None,
                "branch": None,
                "remote": None,
                "uncommitted": 0,
                "path": str(contract_path),
                "rel": str(canonical),
                "mode": "workspace",
                "canonical_repo": canonical,
                "repos": members,
                "workspace_root_is_repo": git_facts(root).get("is_repo_root", False),
                "uncloned": True,
            }
            resolved.append((p, contract_path, g))
            continue

        for name, rel in sorted(repos_decl.items()):
            rp = (root / rel).resolve()
            if not rp.is_dir():
                errors.append(f"{p['id']}: repo {name!r} does not exist — {rp}")
                bad = True
                continue
            rg = git_facts(rp)
            if not rg["is_repo_root"]:
                # ⚠️ The 1945 trap, one level in: `git -C` on a subdirectory reports the ENCLOSING
                # repo perfectly happily, so without this every field would describe the parent.
                errors.append(
                    f"{p['id']}: repo {name!r} at {rp} is NOT a git repo root"
                    + (f" — git reports {rg['toplevel']}; the declared path is a SUBDIRECTORY"
                       if rg.get("toplevel") else f" — {rg.get('error')}"))
                bad = True
                continue
            members[name] = {"path": str(rp), "rel": rel, **rg}
        if bad:
            continue

        # The project's git identity is its CANONICAL repo's — that is where `.w0m/` lives and
        # what the per-project columns describe. Every other repo is reported beside it.
        # The project's git identity is its CONTRACT's repo — the workspace root when the contract
        # lives there, otherwise the named member. Every other repo is reported beside it.
        if canonical == WORKSPACE_ROOT_CONTRACT:
            g = dict(git_facts(root))
            g["path"] = str(root)
            g["rel"] = "."
            contract_path = root
        else:
            g = dict(members[canonical])
            contract_path = Path(members[canonical]["path"])
        g["mode"] = "workspace"
        g["canonical_repo"] = canonical
        g["repos"] = members
        g["workspace_root_is_repo"] = git_facts(root).get("is_repo_root", False)
        resolved.append((p, contract_path, g))
    if errors:
        return {}, errors

    # The contract is whatever the estate declares — read, not hardcoded, so the inventory
    # cannot drift from the thing it measures against.
    estate_id = estates[0]["id"]
    estate_root = next(r for p, r, _ in resolved if p["id"] == estate_id)
    estate_decl = load_json(estate_root / contract_file)
    if estate_decl is None:
        return {}, [f"estate contract unreadable: {estate_root / contract_file}"]
    contract = set(estate_decl)

    # 🔑 T265 AC2 — the tier's IN/OUT list must COVER the contract, or it rots silently.
    # "A surface not named is a gap, not a default." A hand-written list of 33 keys is right on the
    # day it is written and wrong the first time the contract gains a key — at which point a
    # half-managed project inherits an undecided surface and nobody notices. Checked in BOTH
    # directions: an undecided key is a gap, and a decided key the contract no longer has is a stale
    # entry that reads as coverage while pointing at nothing.
    # Placed here, not earlier, because it needs the contract — the first attempt referenced it
    # before it was loaded and crashed, which is at least the honest failure.
    # Keys already tiered in client-profile.json (T185 spec_policy, T207 design_system, T232 branch_model)
    # before clients-policy.json tier tables were refreshed.
    profile_tiered = {"branch_model", "design_system", "spec_policy"}
    for tier_name, tier in (reg.get("tiers") or {}).items():
        if tier_name.startswith("_"):
            continue
        decided = set(tier.get("contract_surfaces", {}))
        real = {k for k in contract if not k.startswith(("$", "_"))}
        undecided = sorted((real - decided) - profile_tiered)
        stale = sorted(decided - real)
        if undecided:
            errors.append(
                f"tier {tier_name!r}: {len(undecided)} contract key(s) not decided IN or OUT "
                f"({', '.join(undecided)}) — a surface not named is a gap, not a default (T265 AC2)")
        if stale:
            errors.append(
                f"tier {tier_name!r}: decides {len(stale)} key(s) the contract no longer has "
                f"({', '.join(stale)}) — a decision pointing at nothing reads as coverage")
    # 🔴 This return is not optional. `if errors: return {}, errors` sits ABOVE, before the contract
    # is loaded, and the function's final return hardcodes an empty error list — so an append made
    # here without a return of its own is silently discarded. The first version of this check did
    # exactly that: it computed the right answer and threw it away, passing green over a deliberately
    # broken tier list. Caught only because the red probe was run.
    if errors:
        return {}, errors


    projects = []
    for p, root, g in resolved:
        decl = load_json(root / contract_file)
        keys = set(decl) if decl is not None else set()
        projects.append({
            "id": p["id"], "role": p["role"], "root": str(root), "note": p.get("note", ""),
            "runtime": p.get("runtime", {}),
            "tier_reason": p.get("tier_reason", ""),
            "services": p.get("_effective_services", {}),
            "services_enabled": sum(1 for s in p.get("_effective_services", {}).values() if s["enabled"]),
            "services_total": len(services_decl),
            "services_overrides": {k: v for k, v in p.get("_effective_services", {}).items() if v["source"] == "override"},
            "workspace_root": str((ROOT / p["root"]).resolve()) if p.get("repos") else None,
            "git": g,
            "declaration": {
                "present": decl is not None,
                "keys": len(keys),
                "missing": sorted(contract - keys),
                "extra": sorted(keys - contract),
                "has_schema": "$schema" in keys,
            },
            "claude_md": claude_md(root),
            "tasks_board": tasks_board(root),
            "skills": skills_facts(root),
            "just_recipes": just_recipes(root),
            "state_surface": state_surface(root, candidates),
        })

    # Shared gaps: what EVERY client lacks is a property of the import path, not of a client.
    # 🔑 `self-managed` / `half-managed` (T265/T299) is deliberately excluded. Its surface is REDUCED
    # ON PURPOSE — no ticketing/deploys, by owner instruction — so counting its absences as shared gaps
    # would report a decision as a defect, and drag the intersection down for every fully managed client.
    clients = [p for p in projects if p["role"] in ("managed", "client")]
    shared = sorted(set.intersection(*(set(c["declaration"]["missing"]) for c in clients))) \
        if clients else []
    return {
        "contract": {"source": f"{estate_id}:{contract_file}", "keys": sorted(contract)},
        "projects": projects,
        "shared_client_gaps": shared,
    }, []


# ── reporting ──────────────────────────────────────────────────────────────────
def fmt_bytes(n: int | None) -> str:
    return "—" if n is None else f"{n:,}"


def report(rep: dict, quiet: bool) -> None:
    contract = rep["contract"]
    print(f"\n  client import inventory — contract: {contract['source']} "
          f"({len(contract['keys'])} keys)\n")
    hdr = f"  {'project':13} {'role':12} {'substrate':11} {'services':>9} {'keys':>5} {'miss':>5} {'xtra':>5} {'$sch':>5} " \
          f"{'recipes':>8} {'CLAUDE':>9} {'skills':>14} {'branch':>8} {'dirty':>6}"
    print(hdr)
    print("  " + "─" * (len(hdr) - 2))
    for p in rep["projects"]:
        d, c, s = p["declaration"], p["claude_md"], p["skills"]
        # An import directive is shown by its EFFECTIVE size with a marker, not its own bytes.
        cm = "absent" if not c["present"] else (
            f"→{fmt_bytes(c['effective_bytes'])}" if c["imports"] else fmt_bytes(c["bytes"]))
        gov = "none" if not s["manifest"] else ("json+lock" if s["lock"] else "json only")
        sk = f"{s['claude_skills']['total']}/{gov}"
        # A project whose ROOT is not a repo has no per-project git facts, and that is correct
        # rather than missing: a half-managed workspace with no contract has no canonical repo to
        # take an identity from. Say "n/a" — the per-repo rows below carry the real branches — and
        # never print a blank that reads as "clean".
        g = p.get("git") or {}
        branch = g.get("branch") or "n/a"
        dirty = g.get("uncommitted") if g.get("uncommitted") is not None else "—"
        rt = p.get("runtime") or {}
        sub = rt.get("substrate") or "—"
        if sub.startswith("tart-") and rt.get("guest_name"):
            sub = f"tart:{rt['guest_name'][:5]}"
        serv_str = f"{p.get('services_enabled', 0)}/{p.get('services_total', 0)}"
        print(f"  {p['id']:13} {p['role']:12} {sub:11} {serv_str:>9} {d['keys']:5} {len(d['missing']):5} "
              f"{len(d['extra']):5} {'yes' if d['has_schema'] else 'NO':>5} "
              f"{('—' if p['just_recipes'] is None else p['just_recipes']):>8} {cm:>9} "
              f"{sk:>14} {branch:>8} {dirty:>6}")

    sandboxed = [p for p in rep["projects"] if p.get("runtime", {}).get("substrate", "").startswith("tart-")]
    if sandboxed:
        print(f"\n  Sandboxed Projects (T297 AC6): " + ", ".join(f"{p['id']} [{p['runtime']['substrate']} -> {p['runtime'].get('guest_name')}]" for p in sandboxed))

    if rep["shared_client_gaps"]:
        profile_path = CANONICAL / "project" / "client-profile.json"
        accounted = set()
        if profile_path.exists():
            try:
                prof = json.loads(profile_path.read_text())
                accounted = set(prof.get("keys", {})) | set(prof.get("excluded", {}))
            except Exception:
                pass
        unaccounted = [k for k in rep["shared_client_gaps"] if k not in accounted]
        if unaccounted:
            print(f"\n [WARN] {len(unaccounted)} shared client gap(s) UNTIERED in client-profile.json — "
                  "a property of the import path, not of a client:")
            print(f"      {', '.join(unaccounted)}")
        else:
            print(f"\n [INFO] every client lacks the same {len(rep['shared_client_gaps'])} keys — "
                  "all accounted for in client-profile.json (excluded/optional):")
            print(f"      {', '.join(rep['shared_client_gaps'])}")

    if quiet:
        return

    for p in rep["projects"]:
        d, c, s = p["declaration"], p["claude_md"], p["skills"]
        print(f"\n  ── {p['id']} ({p['role']}) — {p['root']}")
        if p.get("runtime"):
            rt = p["runtime"]
            sub_label = rt.get("substrate", "—")
            if rt.get("guest_name"):
                sub_label += f" (guest: {rt['guest_name']})"
            print(f"     runtime: {sub_label}")
            if rt.get("substrate", "").startswith("tart-"):
                print("     GUEST VM BOUNDARY (T297 AC3): estate host gates inspect host paths only and do NOT reach inside guest")
        if p["role"] in ("self-managed", "half-managed"):
            # AC1: "visible in tool output WITH ITS REASON, not silently absent". A tier printed
            # as a bare label is the same invisibility one step later — the reader sees a category
            # and cannot tell whether it was chosen or inherited.
            # Plain text, no glyph: the estate's script_output emoji baseline is 0, and glyphs in
            # script output are a PARSED protocol here (run_suites, w0m_audit and others read them),
            # so a decorative one is both a ratchet breach and a collision risk.
            print(f"     SELF-MANAGED — skills/tools/SDLC apply; ticketing/deploys do NOT "
                  f"(no T-ids, no GitHub mirroring)")
            reason = p.get("tier_reason") or "⚠️ NO tier_reason declared — the schema requires one"
            for line in textwrap.wrap(reason, 96):
                print(f"       {line}")
        if p.get("services_overrides"):
            print(f"     service overrides ({len(p['services_overrides'])}):")
            for s_name, s_info in sorted(p["services_overrides"].items()):
                mark = "enabled" if s_info["enabled"] else "disabled"
                print(f"       • {s_name} [{mark}]: {s_info['reason']}")
        if p.get("services_total", 0) > 0 and p.get("services_enabled", 0) == 0:
            print(f"     ALL SERVICES DISABLED (0/{p['services_total']}) — visible by decision (T299 AC8)")
        # T268 AC4 — say which facts are PER-REPO and which are per-project, because until
        # workspaces existed a project WAS a repo and every column was implicitly per-repo.
        #   per-repo    branch, remote, uncommitted, just recipes  (measured for each)
        #   per-project declaration, CLAUDE.md, skills, agent memory  (the CANONICAL repo's)
        # The summary table above shows the per-project view; a workspace's other repos are only
        # visible here, so a dirty repo cannot hide behind a clean canonical one.
        g = p["git"]
        if g.get("mode") == "workspace":
            ws = "" if g.get("workspace_root_is_repo") else " (not a repo itself — the repos below carry the git-root guarantee)"
            print(f"     workspace root: {p.get('workspace_root', '?')}{ws}")
            print(f"     {len(g['repos'])} repo(s); per-repo facts are branch/remote/dirty, "
                  f"per-project facts are read from canonical "
                  f"`{g['canonical_repo']}`" if g.get("canonical_repo")
                  else f"     {len(g['repos'])} repo(s); per-repo facts only — NO w0m contract "
                       f"exists here BY DECISION, and none will be placed")
            for name, m in g["repos"].items():
                mark = " ← canonical" if name == g["canonical_repo"] else ""
                dirty = f"{m['uncommitted']} dirty" if m["uncommitted"] else "clean"
                print(f"       - {name:14} {m['rel']:28} {m['branch']:>10}  {dirty}{mark}")
        if not d["present"]:
            print("     ✗ no declaration file")
        else:
            if d["missing"]:
                print(f"     missing ({len(d['missing'])}): {', '.join(d['missing'])}")
            if d["extra"]:
                print(f"     extra   ({len(d['extra'])}): {', '.join(d['extra'])} "
                      "— divergent, check what reads each before mapping or retiring it")
            if not d["missing"] and not d["extra"]:
                print("     declaration matches the contract exactly")
        if c["present"] and c["imports"]:
            state = "resolves" if c["resolves"] else "✗ DANGLING"
            targets = ", ".join(f"{i['target']} ({fmt_bytes(i['bytes'])} B)" for i in c["imports"])
            print(f"     CLAUDE.md {fmt_bytes(c['bytes'])} B is an import directive → {targets}"
                  f" — {state}; judge the resolved content, not the byte count")
        elif not c["present"]:
            print("     CLAUDE.md absent")
        if s["claude_skills"]["total"] and not s["manifest"]:
            print(f" [WARN] {s['claude_skills']['total']} skills in .claude/skills with no "
                  f"manifest and no lock (.agents/skills holds {s['agents_skills']['total']})")
        elif s["manifest"]:
            print(f"     skills governed: {s['declared']} declared, lock "
                  f"{'present' if s['lock'] else 'MISSING'}; runtime "
                  f"{s['claude_skills']['symlinks']} symlinks + "
                  f"{s['claude_skills']['real_dirs']} real dirs")
        if s["retired_agent_skills"]["total"]:
            r = s["retired_agent_skills"]
            print(f" [WARN] RETIRED `.agent/skills` holds {r['total']} entr(ies) "
                  f"({r['real_dirs']} real dirs) — a second resolution path; whichever an agent "
                  "resolves first wins, so every skill change must be applied to both")
        if p["state_surface"]:
            total = sum(p["state_surface"].values())
            parts = ", ".join(f"{k} {fmt_bytes(v)} B" for k, v in p["state_surface"].items())
            print(f"     agent memory: {parts} — total {fmt_bytes(total)} B")


def main() -> int:
    argv = sys.argv[1:]
    args = set(argv)
    registry = REGISTRY
    if "--registry" in argv:
        i = argv.index("--registry")
        if i + 1 >= len(argv):
            print("  ✗ --registry needs a path")
            return 2
        registry = Path(argv[i + 1]).resolve()
    rep, errors = inventory(registry)
    if errors:
        if "--json" in args:
            print(json.dumps({"ok": False, "errors": errors}, indent=2))
        else:
            print("\n  ✗ registry integrity — measurement not attempted\n")
            for e in errors:
                print(f"     ✗ {e}")
            print()
        return 2
    if "--json" in args:
        print(json.dumps({"ok": True, **rep}, indent=2))
        return 0
    report(rep, quiet="--quiet" in args)
    print("\n  read-only: no project root was written. Diff only — the profile (AC2) decides "
          "which gap matters.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
