#!/usr/bin/env python3
"""ide_trace.py — trace every connected-IDE surface, local and global, and check rule parity (T192).

`openspec init --tools` writes a SEPARATE instruction surface per IDE. The estate has been
governing exactly one of them, and a second is already autoloading rules that contradict it:
`w0m-web/.agent/rules.md` is 1,646 B carrying **none** of CLAUDE.md's six non-negotiables, is
byte-identical to w0m-api's, and points at a `.env` that T119 deleted.

Four questions, in order:

  AC1  DECLARED     which IDEs does each project SAY it connects — read out of
                    `.w0m/sdlc.json -> ide_surfaces`, never inferred from disk. openspec keeps
                    no record of what someone typed at `init --tools` (its `openspec/config.yaml`
                    holds `schema:` and nothing else — measured), so the declaration is the only
                    possible source of truth.
  AC2  PRESENT      which tool surfaces exist, across ALL of openspec's tools — not only the
                    declared ones, because an undeclared surface is invisible by definition.
  AC3  PARITY       does each connected IDE's autoload file carry the canonical non-negotiables?
  AC4  GLOBAL       what loads into every session from $HOME, in no repo and in no review.

🔴 **A surface is identified by its MARKER, never by its directory name.** This ticket's own
filing got that wrong twice — it reported `servicios777/.kilocode` (a node package dir holding
`@kilocode/plugin`, untracked) and `w0m-ext/.agent` (untracked scratch, no rules.md) as IDE
surfaces because the names matched. The marker is openspec's own `opsx` command family, which it
generates into every tool's skillsDir (`.claude/commands/opsx/`, `.agent/workflows/opsx-*.md`) —
one content marker for all 31 tools, needing no per-tool knowledge that could go stale. A
directory without it is reported as `name-only`: present, but not a governed surface. The name
trap is not hypothetical at the wider set either — openspec's skillsDir for `github-copilot` is
`.github`.

🔴 **openspec's registry is read LIVE, never vendored.** The tool→skillsDir map comes from the
installed CLI's own `dist/core/config.js`. If openspec is absent, or renames a directory this
policy pins, the trace FAILS rather than scanning a stale path — a vendored copy of someone
else's registry is the stale-pin shape.

Usage:
    python3 scripts/ide_trace.py            # the trace, advisory
    python3 scripts/ide_trace.py --enforce  # parity + drift block
    python3 scripts/ide_trace.py --json
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from fnmatch import fnmatch
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parent.parent                   # …/@wom
CANONICAL = ROOT / "w0m-web"                 # …/w0m-web
SDLC = ROOT / ".w0m" / "sdlc.json"
REGISTRY = ROOT / "project" / "policies" / "clients-policy.json"
HOME = Path.home()


def read_text(p: Path) -> str | None:
    try:
        return p.read_text()
    except (OSError, UnicodeDecodeError):
        return None


def load_json(p: Path) -> dict | None:
    t = read_text(p)
    if t is None:
        return None
    try:
        v = json.loads(t)
    except json.JSONDecodeError:
        return None
    return v if isinstance(v, dict) else None


def _sh(*args: str) -> tuple[int, str]:
    try:
        r = subprocess.run(args, capture_output=True, text=True)
    except (OSError, ValueError) as e:
        return 127, str(e)
    return r.returncode, (r.stdout or r.stderr)


def openspec_tools() -> tuple[dict[str, str], str | None]:
    """tool value → skillsDir, read from the INSTALLED openspec CLI's own registry.

    Not vendored and not hardcoded: this is another project's data, and a copy of it would go
    stale silently — the exact failure that produced the estate's stale openspec pin.
    """
    candidates = []
    import shutil
    openspec_bin = shutil.which("openspec")
    if openspec_bin:
        try:
            bin_path = Path(openspec_bin).resolve()
            candidates.append(bin_path.parents[1] / "dist" / "core" / "config.js")
            candidates.append(bin_path.parent / "dist" / "core" / "config.js")
            shim_txt = read_text(bin_path)
            if shim_txt:
                m_shim = re.search(r"#\s*cmd-shim-target=(.+)", shim_txt)
                if m_shim:
                    shim_target = Path(m_shim.group(1).strip()).resolve()
                    candidates.append(shim_target.parents[1] / "dist" / "core" / "config.js")
        except Exception:
            pass
    code_npm, out_npm = _sh("npm", "root", "-g")
    if code_npm == 0 and out_npm.strip():
        candidates.append(Path(out_npm.strip()) / "@fission-ai" / "openspec" / "dist" / "core" / "config.js")
    code_pnpm, out_pnpm = _sh("pnpm", "root", "-g")
    if code_pnpm == 0 and out_pnpm.strip():
        candidates.append(Path(out_pnpm.strip()) / "@fission-ai" / "openspec" / "dist" / "core" / "config.js")
    code, out = _sh("node", "-e",
                    "console.log(require.resolve('@fission-ai/openspec/package.json'))")
    if code == 0 and out.strip():
        candidates.append(Path(out.strip()).parent / "dist" / "core" / "config.js")
    for pnpm_global_base in (
        HOME / ".local/share/pnpm/global",
        HOME / "Library/pnpm/global",
    ):
        candidates.append(pnpm_global_base / "5/node_modules/@fission-ai/openspec/dist/core/config.js")
        if pnpm_global_base.is_dir():
            candidates.extend(
                sorted(pnpm_global_base.glob("*/*/node_modules/@fission-ai/openspec/dist/core/config.js"), reverse=True)
            )
    for c in candidates:
        t = read_text(c)
        if t:
            tools = {v: d for _, v, d in
                     re.findall(r"\{ name: '([^']+)', value: '([^']+)'.*?skillsDir: '([^']+)'", t)}
            if tools:
                return tools, None
    return {}, ("cannot read openspec's tool registry — the trace will not guess a tool list, "
                "because scanning a stale set is how an undeclared surface stays invisible")


# ── one scan unit = one filesystem root that autoloads its own instruction surface ──────────────
# The estate is ONE project spanning SEVEN repos under a single `.w0m/sdlc.json`, so its
# declaration is a dict keyed by the `repos` map; a single-root project declares a plain list.

def units(reg: dict, tools: dict[str, str], known: set[str] | None = None) -> tuple[list[dict], list[str], list[str]]:
    out, errors = [], []
    for p in reg.get("projects", []):
        if not p.get("enabled"):
            continue
        proot = (ROOT / p["root"]).resolve()
        if not proot.is_dir():
            errors.append(f"{p['id']}: declared root does not exist — {proot}")
            continue
        canonical = p.get("canonical_repo")
        contract_dir = (proot / canonical).resolve() if canonical else proot
        decl = load_json(contract_dir / ".w0m" / "sdlc.json")
        if decl is None:
            out.append({"id": p["id"], "root": proot, "connected": None,
                        "why": "no .w0m/sdlc.json"})
            continue
        ide = decl.get("ide_surfaces")
        connected = ide.get("connected") if isinstance(ide, dict) else None
        if isinstance(connected, list):
            out.append({"id": p["id"], "root": proot, "connected": connected})
        elif isinstance(connected, dict):
            repos = decl.get("repos") or {}
            base = (proot / decl.get("root", ".")).resolve()
            for key, tlist in connected.items():
                if key.startswith("_"):
                    continue
                if key not in repos:
                    errors.append(f"{p['id']}: ide_surfaces.connected declares repo key "
                                  f"{key!r}, which is not in `repos` — the declaration names a "
                                  "repo the project does not have")
                    continue
                rroot = (base / repos[key]).resolve()
                if not rroot.is_dir():
                    errors.append(f"{p['id']}:{key} — declared repo path does not exist: {rroot}")
                    continue
                out.append({"id": f"{p['id']}:{key}", "root": rroot, "connected": tlist})
        else:
            out.append({"id": p["id"], "root": proot, "connected": None,
                        "why": "`.w0m/sdlc.json -> ide_surfaces.connected` is absent"})
    unit_notes: list[str] = []
    for u in out:
        for t in (u["connected"] or []):
            if t not in tools:
                # 🔑 The old message named two cases — "either a typo or a tool openspec dropped" —
                # and then treated them identically as fatal. They are not the same. openspec 1.11.0
                # DROPPED `windsurf` (renamed to `devin`), but wom7mlx genuinely has `.windsurf/`
                # with rules on disk and Windsurf is on the AGENTS.md supporter list. An IDE openspec
                # stopped generating for is still an IDE in use; only a name the ESTATE'S OWN policy
                # does not know is a typo. Fatal for the second, reported for the first.
                if known is not None and t in known:
                    unit_notes.append(f"{u['id']}: declares IDE {t!r}, which openspec no longer "
                                  "generates for — the policy still knows it, so this is a dropped "
                                  "openspec target, not a typo. openspec writes nothing for it; any "
                                  "surface it has is maintained by hand.")
                else:
                    errors.append(f"{u['id']}: declares IDE {t!r}, which neither openspec nor "
                                  "project/ide-policy.json knows — a typo, or a tool nobody declared")
    return out, errors, unit_notes


def classify(root: Path, skills_dir: str, marker: dict, autoload: str | list | None) -> dict:
    """openspec / foreign / other / autoload-only / absent — decided by CONTENT, never by name.

    `foreign` is the state the first draft did not have, and not having it cost three real
    surfaces: a tool directory can hold live instructions that openspec did not write
    (`.windsurf/workflows/speckit.*` = GitHub Spec Kit; `.gemini/commands/*.toml` = hand-built).
    Those autoload just as hard as openspec's do, so they must be declared; the marker only says
    who maintains them.
    """
    d = root / skills_dir
    has_autoload = autoload is not None and read_autoload(root, autoload)[0] is not None
    if not d.is_dir():
        return {"state": "autoload-only" if has_autoload else "absent",
                "has_autoload": has_autoload}
    try:
        files = [f for f in d.rglob("*") if f.is_file()]
    except OSError:
        files = []
    # Match every path COMPONENT, not just the filename: openspec's current layout puts the
    # marker on a directory (`.claude/commands/opsx/new.md`), the older one on a file
    # (`.cursor/rules/openspec.md`). Matching only the basename sees the second and misses the first.
    managed = any(any(fnmatch(part, g) for part in f.relative_to(d).parts for g in marker["globs"])
                  for f in files)
    idirs, ifiles = set(marker["instruction_dirs"]), set(marker["instruction_files"])
    instructing = [f for f in files
                   if idirs.intersection(f.relative_to(d).parts[:-1]) or f.name in ifiles]
    code, out = _sh("git", "-C", str(root), "ls-files", skills_dir)
    tracked = len([x for x in out.splitlines() if x.strip()]) if code == 0 else 0
    if managed:
        state = "openspec"
    elif instructing:
        state = "foreign"
    elif has_autoload:
        # The dir holds no instructions but the tool's own autoload file is right there — e.g.
        # a client's `.claude/` with settings.local.json only, beside a 10,854 B CLAUDE.md. The
        # tool is plainly connected; the surface is the root file, so don't also call the
        # directory an unruled lookalike and report one truth as two findings.
        state = "autoload-only"
    elif not files:
        state = "absent"                      # an empty directory autoloads nothing
    else:
        state = "other"
    return {"state": state, "files": len(files), "instructing": len(instructing),
            "tracked": tracked, "managed": managed, "has_autoload": has_autoload,
            "real": str(d.resolve()), "linked": d.is_symlink(),
            "sample": sorted(str(f.relative_to(d)) for f in instructing)[:3]}


def read_autoload(root: Path, autoload: str | list) -> tuple[str | None, str]:
    """Read a tool's autoload surface, which is not always ONE file.

    Cursor and Windsurf load a rules DIRECTORY (`.cursor/rules/*.md`), not a root file, and Gemini
    reads both a root `GEMINI.md` and `.gemini/rules/`. Modelling every tool as a single path made
    three of w0m-mlx's four declared surfaces report `[file absent]` against a path they never
    use — measuring the wrong artefact and calling it a finding. So an entry may be a path or a
    glob, and a list of them is concatenated: what the IDE loads is what gets checked.
    """
    entries = autoload if isinstance(autoload, list) else [autoload]
    parts, seen = [], []
    for e in entries:
        if "*" in e:
            for f in sorted(root.glob(e)):
                if f.is_file() and (txt := read_text(f)) is not None:
                    parts.append(txt)
                    seen.append(str(f.relative_to(root)))
        else:
            if (txt := read_text(root / e)) is not None:
                parts.append(txt)
                seen.append(e)
    if not parts:
        return None, " | ".join(str(e) for e in entries)
    return "\n".join(parts), (seen[0] if len(seen) == 1 else f"{seen[0]} +{len(seen) - 1}")


def delegates(start: Path, text: str, rules: dict, deleg: dict | None) -> dict | None:
    """Does this surface point at a file that carries the contract, instead of restating it?

    Satisfying a contract by REFERENCE is what the estate actually chose — five of six sibling
    repos open with *"Canonical conventions live in `../w0m-web/CLAUDE.md`"*, and w0m-mlx points
    at a local `AGENTS.md` hub *"that every agent (Claude, Cursor, Windsurf, Gemini) shares"*.
    A gate with no concept of that scores them all 1/6 and demands they duplicate the canonical
    text, which is the drift it exists to prevent.

    🔴 Two things keep it honest, and both are findings the estate has been bitten by before:
      • the pointer must RESOLVE — a dangling reference looks like compliance (the `$schema`
        defect in project/client-profile.json, where two declarations validated against nothing);
      • the TARGET must actually carry the rules. A chain that ends at a file which carries none
        of them is delegation to nowhere, which is how `.agent/rules.md` came to point at
        `w0m-web/.env` — a file T119 deleted. Followed one hop at a time, `max_hops` deep, with
        cycle detection, because "read X" where X says "read Y" is a real shape here.
    """
    if not deleg:
        return None
    names = sorted(k for k in rules if not k.startswith("_"))
    hops: list[str] = []
    seen: set[Path] = {start.resolve()}
    cur, cur_text = start, text
    for _ in range(int(deleg.get("max_hops", 2))):
        m = re.search(deleg["pattern"], cur_text, re.I)
        if not m:
            break
        ref = m.group(1).strip()
        hops.append(ref)
        target = (cur.parent / ref)
        if not target.is_file():
            return {"chain": hops, "resolves": False, "satisfied": False}
        rt = target.resolve()
        if rt in seen:
            return {"chain": hops, "resolves": True, "satisfied": False, "cycle": True}
        seen.add(rt)
        t = read_text(target)
        if t is None:
            return {"chain": hops, "resolves": False, "satisfied": False}
        missing = [n for n in names if not re.search(rules[n], t, re.I)]
        if not missing:
            return {"chain": hops, "resolves": True, "satisfied": True, "target": str(rt)}
        cur, cur_text = target, t
    if not hops:
        return None
    return {"chain": hops, "resolves": True, "satisfied": False, "target": str(cur.resolve())}


def parity(root: Path, autoload: str | list | None, rules: dict,
           deleg: dict | None = None) -> dict:
    """AC3 — does this IDE's autoload file carry the canonical non-negotiables, or point at them?"""
    names = sorted(k for k in rules if not k.startswith("_"))
    if not autoload:
        return {"file": None, "present": False, "carried": [], "missing": names,
                "unreadable": True, "delegated": None}
    text, where = read_autoload(root, autoload)
    if text is None:
        return {"file": where, "present": False, "carried": [], "missing": names,
                "delegated": None}
    carried: list[str] = []
    missing: list[str] = []
    for name in names:
        (carried if re.search(rules[name], text, re.I) else missing).append(name)
    base = root / (where.split(" +")[0] if where else "CLAUDE.md")
    d = delegates(base, text, rules, deleg) if missing else None
    return {"file": where, "present": True, "bytes": len(text.encode()),
            "carried": carried, "missing": missing, "delegated": d}


def global_surfaces(policy: dict, tools: dict[str, str]) -> tuple[dict, list, list]:
    """AC4 — what loads into every session, lives in no repo, and is reviewed by nothing."""
    rules = policy["non_negotiables"]
    found, findings = {}, []
    declared = {k: v for k, v in policy.get("global_surfaces", {}).items()
                if not k.startswith("_")}
    for tool, rel in declared.items():
        f = Path(rel.replace("~", str(HOME)))
        if not f.is_file():
            findings.append(f"GLOBAL: policy declares {tool} global surface at {rel} — absent")
            continue
        text = read_text(f) or ""
        carried = sorted(n for n, pat in rules.items()
                         if not n.startswith("_") and re.search(pat, text, re.I))
        found[tool] = {"path": str(f), "bytes": len(text.encode()), "carried": carried}
    ruled = {k.lstrip("_") for k in declared} | set(
        re.findall(r"`~/\.([a-z-]+)`", policy.get("global_surfaces", {})
                   .get("_ruled_no_autoload", "")))
    for tool, sdir in tools.items():
        d = HOME / sdir
        if d.is_dir() and tool not in found and sdir.lstrip(".") not in ruled:
            try:
                n = sum(1 for _ in d.iterdir())
            except OSError:
                n = 0
            found[tool] = {"path": str(d), "entries": n, "carried": []}
            findings.append(f"GLOBAL: `~/{sdir}` ({tool}) exists and the policy declares no "
                            "global surface for it — an autoload nobody has ruled on")
    notes = []
    if found:
        notes.append(
            f"GLOBAL: {len(found)} IDE surface(s) in $HOME ({', '.join(sorted(found))}) load into "
            "every session for this developer, are in no repo, and are reviewed by nothing")
    return found, findings, notes


def trace() -> tuple[dict, list[str], list[str]]:
    decl = load_json(SDLC)
    if decl is None:
        return {}, [], [f"cannot read {SDLC}"]
    block = decl.get("ide_surfaces")
    if not isinstance(block, dict):
        return {}, [], ["`.w0m/sdlc.json -> ide_surfaces` is absent — nothing declares which IDEs "
                        "this project connects, and this trace will not guess"]
    policy_path = (ROOT / block.get("policy", "")).resolve()
    policy = load_json(policy_path)
    if policy is None:
        return {}, [], [f"cannot read the IDE policy at {block.get('policy')!r}"]
    # The policy's own `$schema` must RESOLVE and the policy must satisfy it. The estate already
    # carries two declarations whose `$schema` points at a file that does not exist and which have
    # therefore passed every presence check while never being validated (project/client-profile.json
    # records both); this gate is not going to add a third. Mirrors discovery.py's idiom.
    schema_ref = policy.get("$schema", "")
    if schema_ref:
        schema_path = (policy_path.parent / schema_ref).resolve()
        if not schema_path.is_file():
            return {}, [], [f"the IDE policy's $schema points at {schema_ref!r}, which does not "
                            "exist — a dangling schema reference validates nothing"]
        try:
            import jsonschema  # noqa: I001
            try:
                jsonschema.validate(policy, json.loads(read_text(schema_path) or ""))
            except jsonschema.ValidationError as e:
                loc = "/".join(str(p) for p in e.absolute_path) or "<root>"
                return {}, [], [f"IDE policy fails its schema at {loc}: {e.message}"]
        except (ImportError, json.JSONDecodeError):
            pass  # jsonschema unavailable — the structural reads below still fail loudly

    tools, err = openspec_tools()
    if err:
        return {}, [], [err]

    # The policy pins a skills_dir per tool; openspec is the authority. Disagreement is an error,
    # not a silent preference — it means one of them moved.
    ptools = {t: s for t, s in policy["tools"].items() if not t.startswith("_")}
    for t, spec in ptools.items():
        if t in tools and tools[t] != spec["skills_dir"]:
            return {}, [], [f"policy pins {t} → {spec['skills_dir']!r} but openspec says "
                            f"{tools[t]!r} — the registry moved; fix the policy rather than scan "
                            "a path that no longer exists"]

    reg = load_json(REGISTRY)
    if reg is None:
        return {}, [], [f"cannot read the project registry at {REGISTRY}"]
    scan, errors, unit_notes = units(reg, tools, known=set(ptools))
    if errors:
        return {}, [], errors
    if not scan:
        return {}, [], ["no enabled project — a trace over nothing is not a pass"]

    marker = policy["marker"]
    notes: list[str] = list(unit_notes)
    ruled = {k for k in policy.get("known_not_ide_surfaces", {}) if not k.startswith("_")}
    rows, findings = [], []
    for u in scan:
        connected = u["connected"]
        if connected is None:
            findings.append(f"{u['id']}: {u['why']} — the project declares no connected IDEs, so "
                            "nothing can be checked for parity (AC1)")
            connected = []

        surfaces = {}
        for tool, sdir in tools.items():
            spec = ptools.get(tool, {})
            c = classify(u["root"], sdir, marker, spec.get("autoload"))
            if c["state"] != "absent":
                surfaces[tool] = {**c, "dir": sdir}

        governed = sorted(t for t, s in surfaces.items() if s["state"] == "openspec")
        foreign = sorted(t for t, s in surfaces.items() if s["state"] == "foreign")
        loose = sorted(t for t, s in surfaces.items() if s["state"] == "autoload-only")
        nameonly = sorted(t for t, s in surfaces.items() if s["state"] == "other")

        pars = {}
        for tool in connected:
            spec = ptools.get(tool, {})
            if tool not in ptools:
                findings.append(f"{u['id']}: declares `{tool}` connected but the IDE policy has "
                                "no entry for it — its autoload surface is unknown, so parity "
                                "cannot be checked")
                continue
            r = parity(u["root"], spec.get("autoload"), policy["non_negotiables"],
                       policy.get("delegation"))
            pars[tool] = r
            tot = len(r["carried"]) + len(r["missing"])
            d = r.get("delegated")
            if r.get("unreadable"):
                findings.append(f"{u['id']}:{tool} — policy declares no autoload file for this "
                                "tool; a connected IDE whose contract cannot be read cannot be "
                                "governed")
            elif not r["present"]:
                findings.append(f"{u['id']}:{tool} — declared connected but its autoload file "
                                f"`{r['file']}` does not exist: the contract is the empty set")
            elif d and not d["resolves"]:
                findings.append(f"{u['id']}:{tool} — {r['file']} delegates to "
                                f"`{' → '.join(d['chain'])}`, which DOES NOT RESOLVE. A dangling "
                                "pointer reads as compliance and is worse than none; fix the path "
                                "or restate the rules here")
            elif d and not d["satisfied"]:
                findings.append(f"{u['id']}:{tool} — {r['file']} delegates to "
                                f"`{' → '.join(d['chain'])}`, which resolves but carries the rules "
                                "no better than this file does; delegation to nowhere")
            elif d:
                pass  # satisfied by reference — the chain ends at a file carrying every rule
            elif r["missing"]:
                findings.append(f"{u['id']}:{tool} — {r['file']} carries "
                                f"{len(r['carried'])}/{tot} non-negotiables and points at no "
                                f"canonical file; missing {', '.join(r['missing'])}")

        for t in governed:
            if t not in connected:
                findings.append(f"{u['id']}: `{surfaces[t]['dir']}` is an openspec-MANAGED {t} "
                                "surface that the project does not declare as connected")
        for t in foreign:
            if t not in connected:
                findings.append(
                    f"{u['id']}: `{surfaces[t]['dir']}` holds {surfaces[t]['instructing']} "
                    f"instruction file(s) NOT written by openspec ({', '.join(surfaces[t]['sample'])})"
                    f" — a live {t} surface with no generator and no declaration")
        for t in loose:
            # A shared autoload (AGENTS.md) proves nothing about which tool is connected — only a
            # tool-specific directory does. Inferring from it is the name trap wearing a filename.
            if t not in connected and not ptools.get(t, {}).get("autoload_shared"):
                findings.append(f"{u['id']}: `{ptools[t]['autoload']}` autoloads into {t} here, "
                                "and the project does not declare it connected")
        for t in connected:
            if t not in surfaces:
                findings.append(f"{u['id']}: declares `{t}` connected but no surface of any kind "
                                f"exists — neither `{tools.get(t, '?')}` nor its autoload file")
        for t in nameonly:
            key = f"{u['id']}/{surfaces[t]['dir']}"
            if key not in ruled:
                findings.append(f"{u['id']}: `{surfaces[t]['dir']}` holds "
                                f"{surfaces[t]['files']} file(s), none of them instructions and "
                                "no openspec marker — a lookalike nobody has ruled on; record it "
                                f"in known_not_ide_surfaces as `{key}` or declare it")

        rows.append({"id": u["id"], "connected": connected, "governed": governed,
                     "foreign": foreign, "autoload_only": loose, "name_only": nameonly,
                     "surfaces": surfaces, "parity": pars})

    # 🔑 Two units can be ONE surface. `w0m-api/.claude` and `w0m-api/.agent` are SYMLINKS to
    # w0m-web's (set 2026-02-12, same shape as the shared justfile), so a per-unit scan reports one
    # directory twice and a per-unit parity failure twice. This is also the real explanation of
    # T192's founding observation — `.agent/rules.md` was called "byte-identical to w0m-api's, one
    # repo's rules copied into the other". It was never a copy. Identical bytes had a STRUCTURAL
    # cause, and a gate that cannot see the link will keep proposing to fix it twice.
    shared: dict[str, list[str]] = {}
    for row in rows:
        for tool, s in row["surfaces"].items():
            real = s.get("real")          # absent for autoload-only: there is no directory to share
            if real:
                shared.setdefault(f"{tool}\u0000{real}", []).append(row["id"])
    links = {k.split("\u0000")[0]: v for k, v in shared.items() if len(v) > 1}
    for tool, units_sharing in sorted(links.items()):
        notes.append(f"SHARED: `{ptools.get(tool, {}).get('skills_dir', tool)}` is ONE directory "
                        f"serving {', '.join(units_sharing)} (symlink) — a single edit changes the "
                        "rules for all of them, and a per-repo reading of this trace double-counts it")

    glob, gfind, gnotes = global_surfaces(policy, tools)
    findings += gfind
    notes += gnotes

    return {"tools_known": len(tools), "canonical": policy["canonical"],
            "projects": rows, "shared": links, "global": glob,
            "notes": notes}, findings, []


def main() -> int:
    argv = set(sys.argv[1:])
    rep, findings, errors = trace()
    if errors:
        if "--json" in argv:
            print(json.dumps({"ok": False, "errors": errors}, indent=2))
        else:
            print("\n  ✗ ide-trace not run\n")
            for e in errors:
                print(f"     ✗ {e}")
            print()
        return 2
    if "--json" in argv:
        print(json.dumps({"ok": not findings, "findings": findings, **rep}, indent=2,
                         default=str))
        return 1 if ("--enforce" in argv and findings) else 0

    c = rep["canonical"]
    print(f"\n  connected-IDE trace — {rep['tools_known']} tools known to openspec · canonical "
          f"contract: {c['file']} ({c['tool']})\n")
    hdr = (f"  {'unit':16} {'declared':>24} {'openspec-managed':>24} {'other-managed':>22} "
           f"{'lookalike':>12}")
    print(hdr)
    print("  " + "─" * (len(hdr) - 2))
    for p in rep["projects"]:
        print(f"  {p['id']:16} {', '.join(p['connected']) or '—':>24} "
              f"{', '.join(p['governed']) or '—':>24} {', '.join(p['foreign']) or '—':>22} "
              f"{', '.join(p['name_only']) or '—':>12}")

    print("\n  rule parity — does each connected IDE autoload the same contract?")
    for p in rep["projects"]:
        for tool, r in p["parity"].items():
            n, tot = len(r["carried"]), len(r["carried"]) + len(r["missing"])
            d = r.get("delegated")
            ok = not r["missing"] or bool(d and d["satisfied"])
            mark = "✅" if ok else "🔴"
            where = r["file"] or "(no autoload declared)"
            if d and d["satisfied"]:
                extra = f" — delegates to `{' → '.join(d['chain'])}` ✓ which carries all {tot}"
            elif d and not d["resolves"]:
                extra = f" — 🔴 delegates to `{' → '.join(d['chain'])}` which DOES NOT RESOLVE"
            elif d:
                extra = f" — 🔴 delegates to `{' → '.join(d['chain'])}` which carries them no better"
            elif r["missing"]:
                extra = f" — MISSING {', '.join(r['missing'])}"
            else:
                extra = ""
            miss = "" if r["present"] else "  [file absent]"
            print(f"    {mark} {p['id']:18} {tool:12} {where:16} {n}/{tot}{miss}{extra}")

    if rep["global"]:
        print("\n  global surfaces in $HOME (in no repo, reviewed by nothing):")
        for t, g in sorted(rep["global"].items()):
            size = f"{g['bytes']} B" if "bytes" in g else f"{g.get('entries', 0)} entries"
            carried = f"  carries {', '.join(g['carried'])}" if g["carried"] else ""
            print(f"    · {t:12} {g['path']:52} {size:>12}{carried}")

    if rep.get("notes"):
        print(f"\n [INFO] {len(rep['notes'])} standing fact(s) — reported, never blocking:")
        for n in rep["notes"]:
            print(f" [INFO] {n}")

    if findings:
        print(f"\n [WARN] {len(findings)} finding(s):")
        for f in findings:
            print(f" [WARN] {f}")
    else:
        print("\n  ✓ every connected IDE declared, governed and at parity")
    blocking = "--enforce" in argv and findings
    print(f"\n  {'BLOCKING (--enforce)' if blocking else 'advisory — --enforce to block'}\n")
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
