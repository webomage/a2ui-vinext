#!/usr/bin/env python3
"""w0m_cli.py — Unified `w0m` CLI for Skills, Multi-Project, Agent & Session Management (T598).

Provides a single, globally installable `w0m` entrypoint (`~/.local/bin/w0m`) unifying:
1. `w0m skill` (alias `skills`):
   - `list [--project <dir>] [--registry] [--json]`
   - `search <query> [--json]`
   - `check [--project <dir>]`
   - `sync [--project <dir>] [--check]`
   - `add <id> [flags]`, `remove <name>`, `update [name]`, `relock`, `audit`
2. `w0m project` (alias `projects`):
   - `list [--orca] [--json]`
   - `show <id> [--json]`
   - `check [<id>] [--json]`
   - `init [<dir>] [--retention]`
   - `link-remote <dir-or-id> <remote-url>`
3. `w0m agent`:
   - `whoami`, `set`, `claim`, `release`, `tag`, `claims`, `rename` (via `agent_identity.py`)
4. `w0m tree`:
   - `new`, `list`, `land`, `remove`, `prune` (via `agent_tree.py`)
5. `w0m session` (alias `sessions`):
   - `list`, `attach`, `doctor` (via `orca_sessions.py` / `orca terminal`)
6. `w0m tasks`, `w0m status`, `w0m preflight`, `w0m prs`, `w0m install`.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any

HERE = Path(__file__).resolve()
ESTATE_ROOT = HERE.parents[1]
SKILLS_REPO = ESTATE_ROOT / "w0m-skills"
PORTABLE_CLI = SKILLS_REPO / "tools" / "w0m_portable_cli.py"
CLIENTS_POLICY = ESTATE_ROOT / "project" / "policies" / "clients-policy.json"
AGENT_IDENTITY_SCRIPT = ESTATE_ROOT / "w0m-web" / "project" / "scripts" / "agent_identity.py"
AGENT_TREE_SCRIPT = ESTATE_ROOT / "w0m-web" / "project" / "scripts" / "agent_tree.py"
ORCA_SESSIONS_SCRIPT = ESTATE_ROOT / "scripts" / "orca_sessions.py"
TASKS_QUERY_SCRIPT = ESTATE_ROOT / "scripts" / "tasks_query.py"
PREFLIGHT_SCRIPT = ESTATE_ROOT / "scripts" / "preflight.py"
PRS_SCRIPT = ESTATE_ROOT / "scripts" / "w0m_prs.py"
CLIENT_CHECK_SCRIPT = ESTATE_ROOT / "scripts" / "client_check.py"
CLIENT_INVENTORY_SCRIPT = ESTATE_ROOT / "scripts" / "client_inventory.py"
CATALOG_SYNC_SCRIPT = ESTATE_ROOT / "w0m-web" / "project" / "scripts" / "catalog_sync.py"
CATALOG_JSON_FILE = ESTATE_ROOT / "w0m-web" / "project" / "catalog-entities.json"


def _run_catalog_sync(mode: str = "--check") -> int:
    if not CATALOG_SYNC_SCRIPT.is_file():
        return 0
    uv_bin = shutil.which("uv")
    if uv_bin:
        cmd = [uv_bin, "run", "--with", "pyyaml", "--with", "jsonschema", "python", str(CATALOG_SYNC_SCRIPT), mode]
    else:
        cmd = [sys.executable, str(CATALOG_SYNC_SCRIPT), mode]
    return subprocess.run(cmd, cwd=str(ESTATE_ROOT)).returncode


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _git_remote_origin(repo_dir: Path) -> str:
    if not (repo_dir / ".git").exists():
        return ""
    try:
        res = subprocess.run(
            ["git", "-C", str(repo_dir), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        return res.stdout.strip() if res.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def derive_orca_project_id(remote_url: str, fallback_id: str = "local") -> str:
    """Derive canonical Orca project ID (`github:<owner>/<repo>`, `git:<key>`, or `repo:<id>`) from git remote."""
    raw = remote_url.strip()
    if not raw:
        return f"repo:{fallback_id}"
    # Match github.com[:/]owner/repo(.git)
    m_gh = re.search(r"github\.com[:/]([^/]+)/([^/\s]+?)(?:\.git)?$", raw, re.IGNORECASE)
    if m_gh:
        return f"github:{m_gh.group(1)}/{m_gh.group(2)}"
    # Generic git host/path
    m_git = re.search(r"(?:@|https?://)([^:/]+)[:/](.+?)(?:\.git)?$", raw)
    if m_git:
        host = m_git.group(1).lower()
        path = m_git.group(2).strip("/")
        return f"git:{host}/{path}"
    return f"repo:{fallback_id}"


def _extract_skill_description(skill_md: Path) -> str:
    if not skill_md.is_file():
        return ""
    try:
        text = skill_md.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end != -1:
            fm = text[4:end]
            for line in fm.splitlines():
                m = re.match(r"^description:\s*(.+)$", line.strip())
                if m:
                    return m.group(1).strip().strip("\"'")
    for line in text.splitlines():
        s = line.strip()
        if s and not s.startswith("#") and not s.startswith("---"):
            return s[:120]
    return ""


# ── 1. `w0m skill` ───────────────────────────────────────────────────────────


def skill_list_data(
    project_dir: Path,
    *,
    include_registry: bool = False,
    skills_repo: Path = SKILLS_REPO,
) -> dict[str, Any]:
    proj = project_dir.resolve()
    manifest_path = proj / ".w0m" / "skills.json"
    lock_path = proj / ".w0m" / "skills.lock.json"
    manifest = _load_json(manifest_path)
    lock = _load_json(lock_path)

    declared_raw = manifest.get("skills") if isinstance(manifest.get("skills"), dict) else {}
    locked_raw = lock.get("skills") if isinstance(lock.get("skills"), dict) else {}
    excluded_raw = manifest.get("exclude") if isinstance(manifest.get("exclude"), dict) else {}

    rows: list[dict[str, Any]] = []
    all_names = sorted(set(declared_raw.keys()) | set(locked_raw.keys()))
    for name in all_names:
        dec = declared_raw.get(name) if isinstance(declared_raw.get(name), dict) else {}
        lck = locked_raw.get(name) if isinstance(locked_raw.get(name), dict) else {}
        rows.append(
            {
                "name": name,
                "provider": dec.get("provider") or lck.get("provider") or "unknown",
                "version": dec.get("version") or lck.get("resolved") or "*",
                "locked": bool(lck),
                "integrity": (lck.get("integrity") or "")[:19],
                "path": lck.get("path") or f".agents/skills/{name}",
            }
        )

    out: dict[str, Any] = {
        "project": manifest.get("project") or proj.name,
        "project_dir": str(proj),
        "manifest_exists": manifest_path.is_file(),
        "lockfile_exists": lock_path.is_file(),
        "declared_count": len(declared_raw),
        "locked_count": len(locked_raw),
        "excluded_count": len(excluded_raw),
        "skills": rows,
    }

    if include_registry:
        reg_data = _load_json(skills_repo / "skills-registry.json")
        reg_skills = reg_data.get("skills") if isinstance(reg_data.get("skills"), dict) else {}
        canonical: list[dict[str, Any]] = []
        for sname, sinfo in sorted(reg_skills.items()):
            info = sinfo if isinstance(sinfo, dict) else {}
            desc = _extract_skill_description(skills_repo / "skills" / sname / "SKILL.md")
            canonical.append(
                {
                    "name": sname,
                    "origin": info.get("origin", "unknown"),
                    "version": info.get("version", ""),
                    "upstream": info.get("upstream", ""),
                    "description": desc,
                }
            )
        out["canonical_registry"] = canonical
        out["canonical_count"] = len(canonical)

    return out


def skill_search_data(query: str, *, skills_repo: Path = SKILLS_REPO) -> list[dict[str, Any]]:
    q = query.strip().lower()
    reg_data = _load_json(skills_repo / "skills-registry.json")
    reg_skills = reg_data.get("skills") if isinstance(reg_data.get("skills"), dict) else {}
    skills_dir = skills_repo / "skills"

    candidates = set(reg_skills.keys())
    if skills_dir.is_dir():
        for d in skills_dir.iterdir():
            if d.is_dir() and (d / "SKILL.md").is_file():
                candidates.add(d.name)

    matches: list[dict[str, Any]] = []
    for name in sorted(candidates):
        info = reg_skills.get(name) if isinstance(reg_skills.get(name), dict) else {}
        desc = _extract_skill_description(skills_dir / name / "SKILL.md")
        haystack = f"{name} {info.get('origin', '')} {info.get('upstream', '')} {desc}".lower()
        if not q or q in haystack:
            matches.append(
                {
                    "name": name,
                    "origin": info.get("origin", "w0m-native"),
                    "version": info.get("version", ""),
                    "description": desc,
                }
            )
    return matches


def _run_tsx_or_fallback(ts_file: Path, ts_args: list[str], cwd: Path) -> int:
    tsx_bin = shutil.which("tsx") or str(SKILLS_REPO / "node_modules" / ".bin" / "tsx")
    if Path(tsx_bin).is_file() or shutil.which("tsx"):
        res = subprocess.run([tsx_bin, str(ts_file), *ts_args], cwd=str(cwd))
        return res.returncode
    pnpm_bin = shutil.which("pnpm")
    if pnpm_bin and (SKILLS_REPO / "package.json").is_file():
        res = subprocess.run(
            [pnpm_bin, "--dir", str(SKILLS_REPO), "exec", "tsx", str(ts_file), *ts_args],
            cwd=str(cwd),
        )
        return res.returncode
    print(f"[ERR] tsx runtime not found to execute {ts_file}", file=sys.stderr)
    return 2


def handle_skill(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="w0m skill", description="Manage w0m skills, manifests, and sync surfaces")
    ap.add_argument("subcmd", nargs="?", default="list", help="list | search | check | sync | add | remove | update | relock | audit")
    ap.add_argument("rest", nargs=argparse.REMAINDER)
    ap.add_argument("--project", default=None, help="Target project directory (default: cwd)")
    ap.add_argument("--registry", action="store_true", help="Include canonical w0m-skills registry in list")
    ap.add_argument("--check", action="store_true", help="Verify sync without writing (for `sync`)")
    ap.add_argument("--json", action="store_true", help="Emit JSON output")
    args = ap.parse_args(argv)

    proj = Path(args.project).resolve() if args.project else Path.cwd().resolve()
    sub = args.subcmd.lower()

    if sub == "list":
        data = skill_list_data(proj, include_registry=args.registry)
        if args.json:
            print(json.dumps(data, indent=2))
            return 0
        print(
            f"▶ Project Skills ({data['project']} @ {data['project_dir']}): "
            f"{data['declared_count']} declared, {data['locked_count']} locked, {data['excluded_count']} excluded"
        )
        for s in data["skills"]:
            lock_badge = "locked" if s["locked"] else "UNLOCKED"
            print(f"  • {s['name']:<28} {s['provider']:<12} {s['version']:<18} [{lock_badge}] {s['integrity']}")
        if args.registry and "canonical_registry" in data:
            print(f"\n▶ Canonical w0m-skills Registry ({data['canonical_count']} skills):")
            for c in data["canonical_registry"]:
                print(f"  • {c['name']:<28} {c['origin']:<12} {c['description'][:68]}")
        return 0

    if sub == "search":
        q = " ".join(r for r in args.rest if not r.startswith("-")).strip()
        matches = skill_search_data(q)
        if args.json:
            print(json.dumps({"query": q, "count": len(matches), "matches": matches}, indent=2))
            return 0
        print(f"▶ Skill Search '{q}' ({len(matches)} match(es)):")
        for m in matches:
            print(f"  • {m['name']:<28} [{m['origin']}] {m['description'][:72]}")
        return 0

    if sub == "sync":
        sync_args: list[str] = []
        is_check = bool(args.check or "--check" in args.rest)
        if is_check:
            sync_args.append("--check")
        rc = _run_tsx_or_fallback(SKILLS_REPO / "skills.ts", sync_args, ESTATE_ROOT)
        if rc == 0 and not is_check and proj.resolve() == ESTATE_ROOT.resolve():
            _run_catalog_sync("--write")
        return rc

    if sub == "audit":
        return _run_tsx_or_fallback(SKILLS_REPO / "skill_audit.ts", args.rest, SKILLS_REPO)

    if sub == "check":
        if PORTABLE_CLI.is_file() and not shutil.which("tsx") and not (SKILLS_REPO / "node_modules" / ".bin" / "tsx").is_file():
            res = subprocess.run([sys.executable, str(PORTABLE_CLI), "--project", str(proj), "skill-check"])
            return res.returncode
        return _run_tsx_or_fallback(
            SKILLS_REPO / "w0m_skill.ts",
            ["check", "--project", str(proj), *args.rest],
            proj,
        )

    if sub in ("add", "remove", "update", "relock"):
        rc = _run_tsx_or_fallback(
            SKILLS_REPO / "w0m_skill.ts",
            [sub, *args.rest, "--project", str(proj)],
            proj,
        )
        if rc == 0 and proj.resolve() == ESTATE_ROOT.resolve():
            _run_catalog_sync("--write")
        return rc

    print(f"[ERR] Unknown `w0m skill` subcommand '{sub}'.", file=sys.stderr)
    return 2


# ── 2. `w0m project` ─────────────────────────────────────────────────────────


def _primary_estate_root(estate_root: Path) -> Path:
    """Resolve the primary checkout root when running inside a `~/.w0m/work/<set>/w0m` worktree."""
    try:
        res = subprocess.run(
            ["git", "-C", str(estate_root), "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if res.returncode == 0 and res.stdout.strip():
            common_parent = Path(res.stdout.strip()).resolve().parent
            if common_parent.is_dir():
                return common_parent
    except (OSError, subprocess.SubprocessError):
        pass
    return estate_root.resolve()


def project_list_data(
    *,
    estate_root: Path = ESTATE_ROOT,
    policy_path: Path | None = None,
    extra_proj_Root: Path | None = None,
) -> list[dict[str, Any]]:
    pol_file = policy_path or (estate_root / "project" / "policies" / "clients-policy.json")
    pol = _load_json(pol_file)
    declared = pol.get("projects") if isinstance(pol.get("projects"), list) else []
    primary_root = _primary_estate_root(estate_root)

    rows: list[dict[str, Any]] = []
    seen_roots: set[Path] = set()

    for p in declared:
        if not isinstance(p, dict) or not p.get("id"):
            continue
        pid = str(p["id"])
        raw_root = str(p.get("root", "."))
        abs_root = (estate_root / raw_root).resolve()
        if not abs_root.is_dir() and primary_root != estate_root.resolve():
            alt_root = (primary_root / raw_root).resolve()
            if alt_root.is_dir():
                abs_root = alt_root
        seen_roots.add(abs_root)
        exists = abs_root.is_dir()
        remote = _git_remote_origin(abs_root) if exists else ""
        if not remote and isinstance(p.get("vcs"), dict) and p["vcs"].get("repo"):
            remote = f"git@github.com:{p['vcs']['repo']}.git"
        elif not remote and p.get("org_slug") and p.get("project_slug") and pid == "w0m":
            remote = f"git@github.com:{p['org_slug']}/{p['project_slug']}.git"

        skills_manifest = _load_json(abs_root / ".w0m" / "skills.json") if exists else {}
        skills_count = len(skills_manifest.get("skills", {})) if isinstance(skills_manifest.get("skills"), dict) else 0
        sdlc_exists = (abs_root / ".w0m" / "sdlc.json").is_file() if exists else False
        runtime = p.get("runtime") if isinstance(p.get("runtime"), dict) else {}

        rows.append(
            {
                "id": pid,
                "role": str(p.get("role", "managed")),
                "enabled": bool(p.get("enabled", True)),
                "root": str(abs_root),
                "exists": exists,
                "substrate": str(runtime.get("substrate", "host")),
                "git_remote": remote,
                "orca_project_id": derive_orca_project_id(remote, fallback_id=pid),
                "skills_count": skills_count,
                "has_sdlc_json": sdlc_exists,
            }
        )

    # Also scan sibling !proj directory for local checkouts not yet in clients-policy.json (e.g. pandatransfer)
    proj_scan = (
        extra_proj_Root
        if extra_proj_Root is not None
        else (primary_root.parents[1] / "!proj" if len(primary_root.parents) >= 2 else None)
    )
    if proj_scan and proj_scan.is_dir():
        for child in sorted(proj_scan.iterdir()):
            if not child.is_dir() or child.name.startswith("."):
                continue
            resolved_child = child.resolve()
            if resolved_child in seen_roots:
                continue
            if not (resolved_child / ".git").exists():
                continue
            remote = _git_remote_origin(resolved_child)
            skills_manifest = _load_json(resolved_child / ".w0m" / "skills.json")
            skills_count = len(skills_manifest.get("skills", {})) if isinstance(skills_manifest.get("skills"), dict) else 0
            rows.append(
                {
                    "id": child.name.lower(),
                    "role": "local-checkout",
                    "enabled": True,
                    "root": str(resolved_child),
                    "exists": True,
                    "substrate": "host",
                    "git_remote": remote,
                    "orca_project_id": derive_orca_project_id(remote, fallback_id=child.name.lower()),
                    "skills_count": skills_count,
                    "has_sdlc_json": (resolved_child / ".w0m" / "sdlc.json").is_file(),
                }
            )

    return rows


def link_project_remote(
    target: str,
    remote_url: str,
    *,
    estate_root: Path = ESTATE_ROOT,
    policy_path: Path | None = None,
) -> dict[str, Any]:
    """Set or update the `origin` Git remote on a project directory or project ID so Orca merges it across hosts."""
    projects = project_list_data(estate_root=estate_root, policy_path=policy_path)
    by_id = {p["id"]: p for p in projects}
    if target in by_id:
        repo_dir = Path(by_id[target]["root"])
    else:
        repo_dir = Path(target).expanduser().resolve()

    if not (repo_dir / ".git").exists():
        raise ValueError(f"Target '{repo_dir}' is not a Git repository.")

    existing = _git_remote_origin(repo_dir)
    if existing:
        res = subprocess.run(
            ["git", "-C", str(repo_dir), "remote", "set-url", "origin", remote_url.strip()],
            capture_output=True,
            text=True,
            check=False,
        )
    else:
        res = subprocess.run(
            ["git", "-C", str(repo_dir), "remote", "add", "origin", remote_url.strip()],
            capture_output=True,
            text=True,
            check=False,
        )
    if res.returncode != 0:
        raise RuntimeError(f"git remote update failed: {(res.stderr or res.stdout).strip()}")

    updated_remote = _git_remote_origin(repo_dir)
    return {
        "root": str(repo_dir),
        "previous_remote": existing,
        "git_remote": updated_remote,
        "orca_project_id": derive_orca_project_id(updated_remote, fallback_id=repo_dir.name),
    }


def handle_project(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="w0m project", description="Manage estate and client projects, SDLC contracts, and Orca project identity")
    ap.add_argument("subcmd", nargs="?", default="list", help="list | show | check | init | link-remote")
    ap.add_argument("rest", nargs=argparse.REMAINDER)
    ap.add_argument("--retention", action="store_true", help="Also initialize state retention during `init`")
    ap.add_argument("--json", action="store_true", help="Emit JSON output")
    args = ap.parse_args(argv)

    sub = args.subcmd.lower()
    if sub == "list":
        rows = project_list_data()
        if args.json:
            print(json.dumps({"projects": rows}, indent=2))
            return 0
        print(f"▶ w0m Projects & Workspaces ({len(rows)} total):")
        print(f"  {'ID':<15} {'ROLE':<15} {'LOCAL':<6} {'SKILLS':<7} {'SDLC':<5} {'ORCA PROJECT ID':<34} {'ROOT'}")
        for r in rows:
            loc = "yes" if r["exists"] else "no"
            sdlc = "yes" if r["has_sdlc_json"] else "no"
            print(
                f"  {r['id']:<15} {r['role']:<15} {loc:<6} {r['skills_count']:<7} "
                f"{sdlc:<5} {r['orca_project_id']:<34} {r['root']}"
            )
        return 0

    if sub == "show":
        if not args.rest:
            print("[ERR] Usage: w0m project show <project-id>", file=sys.stderr)
            return 2
        target_id = args.rest[0].strip()
        rows = project_list_data()
        found = next((r for r in rows if r["id"] == target_id), None)
        if not found:
            print(f"[ERR] Unknown project '{target_id}'. Run `w0m project list`.", file=sys.stderr)
            return 2
        if args.json or "--json" in args.rest:
            print(json.dumps(found, indent=2))
        else:
            for k, v in found.items():
                print(f"{k:<18}: {v}")
        return 0

    if sub == "check":
        target_args = [a for a in args.rest if a != "--json"]
        if args.json or "--json" in args.rest:
            target_args.append("--json")
        if target_args and not target_args[0].startswith("-"):
            res = subprocess.run([sys.executable, str(CLIENT_CHECK_SCRIPT), *target_args], cwd=str(ESTATE_ROOT))
        else:
            res = subprocess.run([sys.executable, str(CLIENT_INVENTORY_SCRIPT), *target_args], cwd=str(ESTATE_ROOT))
        return res.returncode

    if sub == "init":
        target_dir = Path(args.rest[0]).resolve() if args.rest and not args.rest[0].startswith("-") else Path.cwd().resolve()
        rc = subprocess.run([sys.executable, str(PORTABLE_CLI), "--project", str(target_dir), "init"]).returncode
        if rc == 0 and (args.retention or "--retention" in args.rest):
            rc = subprocess.run([sys.executable, str(PORTABLE_CLI), "--project", str(target_dir), "init-retention"]).returncode
        return rc

    if sub == "link-remote":
        clean_rest = [a for a in args.rest if a != "--json"]
        if len(clean_rest) < 2:
            print("[ERR] Usage: w0m project link-remote <project-id-or-dir> <git-remote-url>", file=sys.stderr)
            return 2
        try:
            info = link_project_remote(clean_rest[0], clean_rest[1])
        except (ValueError, RuntimeError) as exc:
            print(f"[ERR] {exc}", file=sys.stderr)
            return 2
        if args.json or "--json" in args.rest:
            print(json.dumps(info, indent=2))
        else:
            print(f"[OK] Linked {info['root']} -> {info['git_remote']} (Orca ID: {info['orca_project_id']})")
        return 0

    print(f"[ERR] Unknown `w0m project` subcommand '{sub}'.", file=sys.stderr)
    return 2


# ── 3. `w0m install` ─────────────────────────────────────────────────────────


def install_w0m_shim(bin_dir: Path | None = None, *, target_script: Path = HERE) -> Path:
    dest_dir = (bin_dir or (Path.home() / ".local" / "bin")).expanduser().resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)
    shim = dest_dir / "w0m"
    content = (
        "#!/bin/sh\n"
        f"# Auto-generated by w0m_cli.py (T598)\n"
        f'exec python3 "{target_script}" "$@"\n'
    )
    shim.write_text(content, encoding="utf-8")
    shim.chmod(0o755)
    return shim


def handle_catalog(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="w0m catalog", description="Inspect and synchronize Backstage IDP catalog entities (AgDR-0026)")
    ap.add_argument("subcmd", nargs="?", default="list", help="list | check | sync")
    ap.add_argument("--kind", default=None, help="Filter by Backstage entity kind (System, Component, API, AiResource, Group, User)")
    ap.add_argument("--json", action="store_true", help="Emit JSON output")
    args = ap.parse_args(argv)

    sub = args.subcmd.lower()
    if sub == "check":
        return _run_catalog_sync("--check")
    if sub in ("sync", "write"):
        return _run_catalog_sync("--write")
    if sub == "list":
        data = _load_json(CATALOG_JSON_FILE)
        entities = data.get("entities") if isinstance(data.get("entities"), list) else []
        if args.kind:
            k_low = args.kind.lower()
            entities = [e for e in entities if isinstance(e, dict) and str(e.get("kind", "")).lower() == k_low]
        if args.json:
            print(json.dumps({"count": len(entities), "entities": entities}, indent=2))
            return 0
        print(f"▶ w0m Backstage IDP Catalog ({len(entities)} entities from catalog-entities.json):")
        for e in entities:
            if not isinstance(e, dict):
                continue
            kind = str(e.get("kind", ""))
            meta = e.get("metadata") if isinstance(e.get("metadata"), dict) else {}
            spec = e.get("spec") if isinstance(e.get("spec"), dict) else {}
            name = str(meta.get("name", ""))
            etype = str(spec.get("type", "-"))
            title = str(meta.get("title") or meta.get("description") or "")[:54]
            print(f"  • {kind:<12} {name:<32} {etype:<16} {title}")
        return 0

    print(f"[ERR] Unknown `w0m catalog` subcommand '{sub}'.", file=sys.stderr)
    return 2


# ── 4. `w0m track` (QuestTrack Registry & Orca Tab Claiming) ─────────────────

CANONICAL_QUEST_TRACKS: tuple[dict[str, Any], ...] = (
    {
        "id": "track-a",
        "code": "Track A",
        "title": "Backstage Catalog, DORA Telemetry, Project RBAC & Agent Identity",
        "epic": "Raid: Platform Governance & Catalog",
        "milestone": "Adventure: Backstage Catalog, DORA Telemetry & T596 Claim Registry",
        "tickets": ["T448", "T64", "T520", "T432", "T525", "T534", "T596"],
        "status": "in_progress",
        "xp_reward": 650,
        "rarity": "epic",
        "assigned_developer": "aleksei@webomage.com",
        "attached_agent": "antigravity",
        "agent_id": "agy:agy-t596",
        "host_id": "local",
        "worktree": "agent/agy-t596",
        "session_title": "Track A · T596 · Agent Identity & Claim Registry [agy-t596]",
    },
    {
        "id": "track-b",
        "code": "Track B",
        "title": "Connector Surface, Cal.com Webhooks & Open WebUI SSO",
        "epic": "Raid: Integrations & Identity Federation",
        "milestone": "Adventure: Webhook Verification & Federated Auth",
        "tickets": ["T292", "T59", "T51", "T141", "T144"],
        "status": "completed",
        "xp_reward": 550,
        "rarity": "epic",
        "assigned_developer": "aleksei@webomage.com",
        "attached_agent": "antigravity",
        "agent_id": "agy:ant-track-a-b",
        "host_id": "local",
        "worktree": "agent/ant-track-a-b",
        "session_title": "Track B · T292 · Connector Surface & Open WebUI SSO [ant-track-a-b]",
    },
    {
        "id": "track-c",
        "code": "Track C",
        "title": "Orca Multi-Host Pairing, Tab Mobility, Google AX & Unified w0m CLI",
        "epic": "Raid: Multi-Host Agent Substrate & Developer Platform",
        "milestone": "Adventure: Remote Host Pairing, Cross-Workspace Tab DnD, Google AX & w0m CLI",
        "tickets": ["T597", "T598", "T564", "T171"],
        "status": "in_progress",
        "xp_reward": 650,
        "rarity": "epic",
        "assigned_developer": "aleksei@webomage.com",
        "attached_agent": "antigravity",
        "agent_id": "agy:agy-orca",
        "host_id": "local",
        "worktree": "agent/agy-orca",
        "session_title": "Track C · T597 · Orca Tab DnD & AX Specs [agy-orca]",
    },
    {
        "id": "track-d",
        "code": "Track D",
        "title": "Connector Credential Vault, Blueprint Catalog & ZeroClaw",
        "epic": "Raid: Zero-Trust Security & Catalog Hygiene",
        "milestone": "Adventure: OAuth Ciphertext Vault & Blueprint 1:1 Sync",
        "tickets": ["T99", "T114", "T219", "T333"],
        "status": "completed",
        "xp_reward": 500,
        "rarity": "epic",
        "assigned_developer": "aleksei@webomage.com",
        "attached_agent": "antigravity",
        "agent_id": "agy:ant-track-d",
        "host_id": "local",
        "worktree": "agent/ant-track-d",
        "session_title": "Track D · T333 · Bounty & Agent Quest Tracks [ant-track-d]",
    },
    {
        "id": "track-e",
        "code": "Track E",
        "title": "Knowledge Graph, Telemetry & Estate Tooling (agy-batch)",
        "epic": "Raid: Developer Experience & Observability",
        "milestone": "Adventure: Codegraph, Sentry & Estate Automation",
        "tickets": ["T284", "T30", "T344", "T560"],
        "status": "in_progress",
        "xp_reward": 450,
        "rarity": "rare",
        "assigned_developer": "aleksei@webomage.com",
        "attached_agent": "antigravity",
        "agent_id": "agy:agy-batch",
        "host_id": "local",
        "worktree": "agent/agy-batch",
        "session_title": "Track E · T284 · Graph Tooling & Telemetry [agy-batch]",
    },
    {
        "id": "track-f",
        "code": "Track F",
        "title": "Upwork GraphQL Live Sync & Freelancer Discovery",
        "epic": "Raid: Commercial Acquisition & Talent Pipeline",
        "milestone": "Adventure: Upwork Live OAuth & Job Feed Sync",
        "tickets": ["T43", "T55"],
        "status": "open",
        "xp_reward": 350,
        "rarity": "rare",
        "assigned_developer": None,
        "attached_agent": None,
        "agent_id": None,
        "host_id": None,
        "worktree": None,
        "session_title": None,
    },
    {
        "id": "track-g",
        "code": "Track G",
        "title": "Local Apple MLX Inference & Voice Pipeline",
        "epic": "Raid: Local AI & Multi-Modal Inference",
        "milestone": "Adventure: Apple Silicon MLX & Voice Synthesis",
        "tickets": ["T208", "T252"],
        "status": "open",
        "xp_reward": 400,
        "rarity": "epic",
        "assigned_developer": None,
        "attached_agent": None,
        "agent_id": None,
        "host_id": None,
        "worktree": None,
        "session_title": None,
    },
)


def track_list_data() -> list[dict[str, Any]]:
    return [dict(item) for item in CANONICAL_QUEST_TRACKS]


def handle_track(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="w0m track", description="Inspect and claim w0m Agent Quest Tracks (T333 / T596 / T597)")
    ap.add_argument("subcmd", nargs="?", default="list", help="list | show | claim")
    ap.add_argument("rest", nargs=argparse.REMAINDER)
    ap.add_argument("--ticket", default=None, help="Explicit ticket ID (T##) to claim on the track")
    ap.add_argument("--agent", default=None, help="Explicit agent identity (<harness>:<handle>)")
    ap.add_argument("--json", action="store_true", help="Emit JSON output")
    args = ap.parse_args(argv)

    sub = args.subcmd.lower()
    is_json = bool(args.json or "--json" in args.rest)
    tracks = track_list_data()

    if sub == "list":
        if is_json:
            print(json.dumps({"count": len(tracks), "tracks": tracks}, indent=2))
            return 0
        print(f"▶ w0m Agent Quest Tracks ({len(tracks)} canonical tracks):")
        print(f"  {'ID':<10} {'CODE':<9} {'STATUS':<12} {'AGENT ID':<18} {'HOST':<11} {'WORKTREE':<18} {'TITLE'}")
        for t in tracks:
            aid = str(t.get("agent_id") or "-")
            hst = str(t.get("host_id") or "-")
            wt = str(t.get("worktree") or "-")
            print(f"  {t['id']:<10} {t['code']:<9} {t['status']:<12} {aid:<18} {hst:<11} {wt:<18} {t['title'][:44]}")
        return 0

    if sub == "show":
        if not args.rest:
            print("[ERR] Usage: w0m track show <track-id>", file=sys.stderr)
            return 2
        tid = args.rest[0].strip().lower()
        found = next((t for t in tracks if t["id"] == tid or t["code"].lower() == tid), None)
        if not found:
            print(f"[ERR] Unknown quest track '{tid}'. Run `w0m track list`.", file=sys.stderr)
            return 2
        if args.json or "--json" in args.rest:
            print(json.dumps(found, indent=2))
        else:
            for k, v in found.items():
                print(f"{k:<20}: {v}")
        return 0

    if sub == "claim":
        if not args.rest:
            print("[ERR] Usage: w0m track claim <track-id> [--ticket T##]", file=sys.stderr)
            return 2
        tid = args.rest[0].strip().lower()
        found = next((t for t in tracks if t["id"] == tid or t["code"].lower() == tid), None)
        if not found:
            print(f"[ERR] Unknown quest track '{tid}'. Run `w0m track list`.", file=sys.stderr)
            return 2
        ticket_id = args.ticket
        for idx, tok in enumerate(args.rest):
            if tok == "--ticket" and idx + 1 < len(args.rest):
                ticket_id = args.rest[idx + 1]
        if not ticket_id:
            tickets = found.get("tickets") or []
            ticket_id = tickets[0] if tickets else None
        if not ticket_id:
            print(f"[ERR] Track '{found['id']}' has no default ticket; pass `--ticket T##`.", file=sys.stderr)
            return 2
        cmd = [sys.executable, str(AGENT_IDENTITY_SCRIPT), "claim", str(ticket_id), "--track", str(found["code"])]
        if args.agent:
            cmd.extend(["--agent", str(args.agent)])
        if args.json or "--json" in args.rest:
            cmd.append("--json")
        return subprocess.run(cmd, cwd=str(ESTATE_ROOT)).returncode

    print(f"[ERR] Unknown `w0m track` subcommand '{sub}'.", file=sys.stderr)
    return 2


# ── 5. `w0m automation` (Zero-Token Precheck Bridge for T171 & Orca) ─────────

AUTOMATION_TEMPLATES: tuple[dict[str, Any], ...] = (
    {
        "id": "in-triage-watch",
        "name": "w0m Inbound Tray Triage (_in/)",
        "cron": "*/30 * * * *",
        "executionMode": "background",
        "precheck": "python3 scripts/in_triage.py --check",
        "prompt": "Run `just in-triage` to inspect new drops in `_in/INDEX.md`, match against open tickets/specs, and report findings.",
        "ticket": "T171",
    },
    {
        "id": "prs-review-watch",
        "name": "w0m Upstream Open-Source PR Health (w0m-pr/)",
        "cron": "0 */4 * * *",
        "executionMode": "background",
        "precheck": "python3 scripts/w0m_prs.py --json | python3 -c \"import json,sys; d=json.load(sys.stdin); sys.exit(0 if any(p.get('reviewDecision')=='CHANGES_REQUESTED' for p in d.get('prs',[])) else 1)\"",
        "prompt": "Run `w0m prs` to audit upstream PR review requests or CI failures in `w0m-pr/` and prepare fixes.",
        "ticket": "T171",
    },
    {
        "id": "beta-drift-watch",
        "name": "w0m Multi-Host origin/beta Sync Check",
        "cron": "0 * * * *",
        "executionMode": "background",
        "precheck": "git fetch origin beta --quiet && test \"$(git rev-parse HEAD)\" != \"$(git rev-parse origin/beta)\"",
        "prompt": "Fast-forward live checkout to `origin/beta` with `git merge --ff-only origin/beta` and verify `w0m catalog check`.",
        "ticket": "T597",
    },
    {
        "id": "catalog-drift-watch",
        "name": "w0m Backstage IDP Catalog & Skills Drift Gate",
        "cron": "0 */6 * * *",
        "executionMode": "background",
        "precheck": "! python3 scripts/w0m_cli.py catalog check >/dev/null 2>&1",
        "prompt": "Investigate Backstage catalog drift via `w0m catalog check` and regenerate via `w0m catalog sync` if needed.",
        "ticket": "T598",
    },
)


def automation_templates_data() -> list[dict[str, Any]]:
    return [dict(t) for t in AUTOMATION_TEMPLATES]


def handle_automation(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        prog="w0m automation",
        description="Zero-token shell precheck templates & Orca AutomationService bridge (T171 AC5/AC6)",
    )
    ap.add_argument("subcmd", nargs="?", default="templates", help="templates | list | precheck")
    ap.add_argument("rest", nargs=argparse.REMAINDER)
    ap.add_argument("--json", action="store_true", help="Emit JSON output")
    args = ap.parse_args(argv)

    sub = args.subcmd.lower()
    is_json = bool(args.json or "--json" in args.rest)
    templates = automation_templates_data()

    if sub in ("templates", "list"):
        if is_json:
            print(json.dumps({"count": len(templates), "templates": templates}, indent=2))
            return 0
        print(f"▶ w0m Zero-Token Precheck Automation Templates ({len(templates)} templates, T171 ↔ Orca AutomationService):")
        for t in templates:
            print(f"  • {t['id']:<22} [{t['cron']:<11}] ({t['executionMode']}) — {t['name']}")
            print(f"    precheck: {t['precheck']}")
        return 0

    if sub == "precheck":
        if not args.rest:
            print("[ERR] Usage: w0m automation precheck <template-id>", file=sys.stderr)
            return 2
        tid = args.rest[0].strip().lower()
        found = next((t for t in templates if t["id"] == tid), None)
        if not found:
            print(f"[ERR] Unknown automation template '{tid}'. Run `w0m automation templates`.", file=sys.stderr)
            return 2
        res = subprocess.run(found["precheck"], shell=True, cwd=str(ESTATE_ROOT), capture_output=True, text=True)
        should_wake = res.returncode == 0
        payload = {
            "id": found["id"],
            "precheck": found["precheck"],
            "returncode": res.returncode,
            "should_wake_agent": should_wake,
            "tokens_spent": 0,
        }
        if args.json or "--json" in args.rest:
            print(json.dumps(payload, indent=2))
        else:
            state = "WAKE AGENT (precheck exited 0)" if should_wake else "SKIP AGENT (precheck non-zero, 0 LLM tokens spent)"
            print(f"▶ Precheck [{found['id']}]: {state}")
        return 0

    print(f"[ERR] Unknown `w0m automation` subcommand '{sub}'.", file=sys.stderr)
    return 2


# ── 6. `w0m gh` (Orca GitHub Tasks Auth, Scopes & Worktree Visibility Sync) ──

REQUIRED_GH_SCOPES: tuple[str, ...] = ("repo", "read:org", "project")


def _parse_gh_auth_status(raw: str) -> dict[str, Any]:
    user = ""
    active = False
    scopes: list[str] = []
    for line in raw.splitlines():
        m_user = re.search(r"Logged in to \S+ account (\S+)", line)
        if m_user and not user:
            user = m_user.group(1)
        m_act = re.search(r"Active account:\s*(true|false)", line, re.I)
        if m_act:
            active = m_act.group(1).lower() == "true"
        m_sc = re.search(r"Token scopes:\s*(.+)$", line, re.I)
        if m_sc:
            scopes = [s.strip().strip("'\"") for s in m_sc.group(1).split(",") if s.strip()]
    missing = [s for s in REQUIRED_GH_SCOPES if s not in scopes]
    return {
        "authenticated": bool(user),
        "user": user or None,
        "active": active,
        "scopes": scopes,
        "missing_scopes": missing,
        "issues_ready": "repo" in scopes,
        "projects_v2_ready": "project" in scopes and "read:org" in scopes,
    }


def inspect_gh_host_status(host: str = "local") -> dict[str, Any]:
    if host == "local":
        gh_bin = shutil.which("gh")
        if not gh_bin:
            return {"host": "local", "gh_available": False, "authenticated": False, "missing_scopes": list(REQUIRED_GH_SCOPES)}
        res = subprocess.run([gh_bin, "auth", "status"], capture_output=True, text=True, timeout=6.0)
        parsed = _parse_gh_auth_status(f"{res.stdout}\n{res.stderr}")
        parsed["host"] = "local"
        parsed["gh_available"] = True
        parsed["gh_path"] = gh_bin
        return parsed

    remote_cmd = (
        "if [ ! -x ~/.local/bin/gh ] && [ -x /home/linuxbrew/.linuxbrew/bin/gh ]; then "
        "mkdir -p ~/.local/bin && ln -sf /home/linuxbrew/.linuxbrew/bin/gh ~/.local/bin/gh; fi; "
        "GH_BIN=$(command -v gh || echo ~/.local/bin/gh); "
        "if [ -x \"$GH_BIN\" ]; then echo \"GH_PATH=$GH_BIN\"; \"$GH_BIN\" auth status 2>&1 || true; "
        "else echo \"GH_MISSING\"; fi"
    )
    try:
        res = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", host, remote_cmd],
            capture_output=True,
            text=True,
            timeout=8.0,
        )
        out = f"{res.stdout}\n{res.stderr}"
        if "GH_MISSING" in out or res.returncode != 0 and "Logged in to" not in out:
            return {"host": host, "gh_available": False, "authenticated": False, "missing_scopes": list(REQUIRED_GH_SCOPES)}
        gh_path = ""
        for line in out.splitlines():
            if line.startswith("GH_PATH="):
                gh_path = line.split("=", 1)[1].strip()
        parsed = _parse_gh_auth_status(out)
        parsed["host"] = host
        parsed["gh_available"] = True
        parsed["gh_path"] = gh_path
        return parsed
    except (OSError, subprocess.SubprocessError) as exc:
        return {"host": host, "gh_available": False, "authenticated": False, "error": str(exc)[:200], "missing_scopes": list(REQUIRED_GH_SCOPES)}


ORCA_SYNC_SNIPPET = r"""
import json, os, socket, sys, uuid
from pathlib import Path

user = sys.argv[1] if len(sys.argv) > 1 else "casualuser"
home = Path.home()
if sys.platform.startswith("darwin"):
    orca_dir = home / "Library" / "Application Support" / "orca"
else:
    orca_dir = Path(os.environ.get("XDG_CONFIG_HOME") or (home / ".config")) / "orca"

meta_path = orca_dir / "orca-runtime.json"
if not meta_path.is_file():
    print(json.dumps({"ok": False, "error": f"Missing {meta_path}"}))
    sys.exit(0)

meta = json.loads(meta_path.read_text(encoding="utf-8"))
endpoint = next((t["endpoint"] for t in (meta.get("transports") or []) if t.get("kind") == "unix"), None)

def rpc(method, params=None):
    req_id = str(uuid.uuid4())
    req = {"id": req_id, "authToken": meta.get("authToken"), "method": method}
    if params is not None:
        req["params"] = params
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(5.0)
        s.connect(endpoint)
        s.sendall((json.dumps(req) + "\n").encode("utf-8"))
        buf = b""
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if not line.strip():
                    continue
                frame = json.loads(line.decode("utf-8", errors="replace"))
                if frame.get("_keepalive"):
                    continue
                if frame.get("id") == req_id:
                    return frame
    return {"ok": False}

repos_res = rpc("repo.list", {})
repos = (repos_res.get("result") or {}).get("repos", []) if repos_res.get("ok") else []
updated = []
for r in repos:
    if r.get("kind") != "git":
        continue
    updates = {
        "ghAccount": {"host": "github.com", "user": user},
        "issueSourcePreference": "origin",
    }
    if r.get("displayName") == "w0m":
        updates.update({
            "worktreeBasePath": f"{home}/.w0m/work",
            "externalWorktreeVisibility": "hide",
            "customWorktreeVisibilitySources": [
                {"id": "w0m-work", "rootPath": f"{home}/.w0m/work"},
                {"id": "w0m-releases", "rootPath": f"{home}/.w0m/releases"},
            ],
            "worktreeVisibilitySourcePreferences": {
                "custom": {
                    "w0m-work": "show",
                    "w0m-releases": "hide",
                }
            },
        })
    u_res = rpc("repo.update", {"repo": r["id"], "updates": updates})
    updated.append({
        "id": r["id"],
        "displayName": r.get("displayName"),
        "ok": bool(u_res.get("ok")),
        "ghAccount": (u_res.get("result") or {}).get("repo", {}).get("ghAccount"),
    })
print(json.dumps({"ok": True, "updated_repos": updated}))
"""


def sync_orca_gh_and_worktrees(host: str = "local", user: str = "casualuser") -> dict[str, Any]:
    if host == "local":
        res = subprocess.run(
            [sys.executable, "-c", ORCA_SYNC_SNIPPET, user],
            capture_output=True,
            text=True,
            timeout=8.0,
        )
        payload: dict[str, Any] = {"host": "local", "ok": False}
        if res.returncode == 0 and res.stdout.strip():
            try:
                payload = {"host": "local", **json.loads(res.stdout.strip().splitlines()[-1])}
            except ValueError:
                payload = {"host": "local", "ok": False, "error": res.stdout.strip()[:200]}
        if AGENT_TREE_SCRIPT.is_file():
            subprocess.run(
                [sys.executable, str(AGENT_TREE_SCRIPT), "sync-orca", "--json"],
                capture_output=True,
                text=True,
                timeout=8.0,
            )
        return payload

    try:
        res = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", host, "python3", "-", user],
            input=ORCA_SYNC_SNIPPET,
            capture_output=True,
            text=True,
            timeout=10.0,
        )
        if res.returncode == 0 and res.stdout.strip():
            return {"host": host, **json.loads(res.stdout.strip().splitlines()[-1])}
        return {"host": host, "ok": False, "error": (res.stderr or res.stdout).strip()[:200]}
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        return {"host": host, "ok": False, "error": str(exc)[:200]}


def handle_gh(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        prog="w0m gh",
        description="Inspect & synchronize GitHub CLI (`gh`) auth, scopes, and Orca repo bindings across hosts",
    )
    ap.add_argument("subcmd", nargs="?", default="status", help="status | sync-orca")
    ap.add_argument("rest", nargs=argparse.REMAINDER)
    ap.add_argument("--host", default="all", help="Target host: all, local, linux-host (default: all)")
    ap.add_argument("--user", default="casualuser", help="GitHub account login to bind in Orca (default: casualuser)")
    ap.add_argument("--json", action="store_true", help="Emit JSON output")
    args = ap.parse_args(argv)

    sub = args.subcmd.lower()
    is_json = bool(args.json or "--json" in args.rest)
    hosts = ["local", "linux-host"] if args.host == "all" else [h.strip() for h in args.host.split(",") if h.strip()]

    if sub == "status":
        rows = [inspect_gh_host_status(h) for h in hosts]
        if is_json:
            print(json.dumps({"hosts": rows}, indent=2))
            return 0
        print("▶ GitHub CLI (`gh`) & Orca Tasks Auth Status:")
        for r in rows:
            avail = "yes" if r.get("gh_available") else "NO"
            user = r.get("user") or "-"
            scopes = ", ".join(r.get("scopes") or []) or "-"
            missing = ", ".join(r.get("missing_scopes") or []) or "none"
            issues_ok = "READY" if r.get("issues_ready") else "MISSING_SCOPE"
            proj_ok = "READY" if r.get("projects_v2_ready") else "NEEDS `project` SCOPE"
            print(
                f"  • {r['host']:<12} gh={avail:<4} user={user:<12} issues={issues_ok:<6} "
                f"projects_v2={proj_ok:<21} scopes=[{scopes}] (missing: {missing})"
            )
        if any(r.get("missing_scopes") for r in rows):
            print(
                "\n  💡 To enable GitHub Projects v2 in Orca Tasks UI, run in your terminal:\n"
                "     gh auth refresh --hostname github.com -s project,read:org,repo && w0m gh sync-orca"
            )
        return 0

    if sub == "sync-orca":
        status_by_host = {h: inspect_gh_host_status(h) for h in hosts}
        # If local has `project` scope and linux-host is missing it, propagate token automatically
        if (
            "local" in status_by_host
            and "linux-host" in status_by_host
            and status_by_host["local"].get("projects_v2_ready")
            and not status_by_host["linux-host"].get("projects_v2_ready")
        ):
            tok_res = subprocess.run(
                ["gh", "auth", "token", "--hostname", "github.com", "--user", args.user],
                capture_output=True,
                text=True,
                timeout=5.0,
            )
            if tok_res.returncode == 0 and tok_res.stdout.strip():
                subprocess.run(
                    [
                        "ssh",
                        "-o",
                        "BatchMode=yes",
                        "linux-host",
                        "~/.local/bin/gh auth login --hostname github.com --git-protocol ssh --with-token",
                    ],
                    input=tok_res.stdout.strip() + "\n",
                    capture_output=True,
                    text=True,
                    timeout=8.0,
                )

        sync_rows = [sync_orca_gh_and_worktrees(h, user=args.user) for h in hosts]
        if is_json:
            print(json.dumps({"hosts": sync_rows}, indent=2))
            return 0
        print(f"▶ Synchronized Orca `ghAccount` ({args.user}@github.com) & Worktree Visibility Sources:")
        for sr in sync_rows:
            repos = sr.get("updated_repos") or []
            r_names = ", ".join(f"{r.get('displayName')}({'ok' if r.get('ok') else 'err'})" for r in repos) or "-"
            print(f"  • {sr['host']:<12} ok={sr.get('ok')} repos=[{r_names}]")
        return 0

    print(f"[ERR] Unknown `w0m gh` subcommand '{sub}'.", file=sys.stderr)
    return 2


# ── 4. Top-Level Dispatcher ──────────────────────────────────────────────────


HELP_TEXT = """\
w0m — Unified CLI for Skills, Projects, Catalog, Virtual Agents & Multi-Host Sessions (T598)

Usage:
  w0m <group> [subcommand] [options]

Command Groups:
  skill, skills      Manage project & canonical skills (`list`, `search`, `check`, `sync`, `add`, `remove`, `update`, `relock`, `audit`)
  project, projects  Manage estate & client projects (`list`, `show`, `check`, `init`, `link-remote`)
  catalog            Manage Backstage IDP catalog entities (`list [--kind <Kind>]`, `check`, `sync`) (AgDR-0026)
  track, tracks      Manage Agent Quest Tracks & claim tracks with Orca tab naming (`list`, `show`, `claim`) (T333/T597)
  automation         Zero-token shell precheck templates & Orca AutomationService bridge (`templates`, `precheck`) (T171)
  gh                 GitHub CLI auth & Orca Tasks/Worktree visibility sync (`status`, `sync-orca`)
  agent              Virtual Agent ID, ticket claims & Orca tab naming (`whoami`, `claim`, `rename`, `release`, `tag`, `claims`)
  tree               Isolated agent worktree sets (`new [--spawn-session]`, `list`, `sync-orca`, `land`, `remove`, `prune`)
  session, sessions  Multi-host Orca agent sessions (`list`, `spawn`, `attach`, `worktrees`, `hosts`)
  tasks              Query ranked w0m ticket queue (`hot`, `sdlc`, `plan`, `board`, `wip`)
  status             Consolidated portable project status
  preflight          Run estate preflight checks (`--fast`)
  prs                Audit upstream open-source PRs (`w0m-pr/`)
  vm, k8s, cloud     Portable infrastructure & FinOps commands (`w0m_portable_cli.py`)
  llm, spec, notify  Portable LLM, OpenSpec & Telegram telemetry commands (`w0m_portable_cli.py`)
  install            Install `~/.local/bin/w0m` executable shim on PATH
"""

PORTABLE_PASSTHROUGH_SUBCOMMANDS = frozenset({
    "vm",
    "k8s",
    "cloud",
    "llm",
    "spec",
    "notify",
    "lessons",
    "state-brief",
    "state-check",
    "state-save",
    "state-rotate",
    "state-bounds",
    "skill-check",
    "sync-tickets",
    "init",
    "init-retention",
})


def main(argv: list[str] | None = None) -> int:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    if not raw_args or raw_args[0] in ("-h", "--help", "help"):
        print(HELP_TEXT)
        return 0

    # Support optional leading `--project <dir>` or `--project=<dir>` before the command group
    project_override: str | None = None
    cleaned_args: list[str] = []
    i = 0
    while i < len(raw_args):
        tok = raw_args[i]
        if tok == "--project" and i + 1 < len(raw_args):
            project_override = raw_args[i + 1]
            i += 2
            continue
        if tok.startswith("--project="):
            project_override = tok.split("=", 1)[1]
            i += 1
            continue
        cleaned_args.append(tok)
        i += 1

    if not cleaned_args:
        print(HELP_TEXT)
        return 0

    group = cleaned_args[0].lower()
    rest = cleaned_args[1:]
    proj_dir = project_override or str(Path.cwd())

    if group in ("skill", "skills"):
        if project_override and "--project" not in rest:
            rest = [*rest, "--project", project_override]
        return handle_skill(rest)

    if group in ("project", "projects"):
        return handle_project(rest)

    if group == "catalog":
        return handle_catalog(rest)

    if group in ("track", "tracks"):
        return handle_track(rest)

    if group in ("automation", "automations"):
        return handle_automation(rest)

    if group == "gh":
        return handle_gh(rest)

    if group == "agent":
        return subprocess.run([sys.executable, str(AGENT_IDENTITY_SCRIPT), *rest]).returncode

    if group == "tree":
        return subprocess.run([sys.executable, str(AGENT_TREE_SCRIPT), *rest]).returncode

    if group in ("session", "sessions"):
        if ORCA_SESSIONS_SCRIPT.is_file():
            return subprocess.run([sys.executable, str(ORCA_SESSIONS_SCRIPT), *rest]).returncode
        print("[ERR] scripts/orca_sessions.py not found in this checkout.", file=sys.stderr)
        return 2

    if group == "tasks":
        if project_override and Path(project_override).resolve() != ESTATE_ROOT.resolve():
            return subprocess.run([sys.executable, str(PORTABLE_CLI), "--project", proj_dir, "tasks", *rest]).returncode
        return subprocess.run([sys.executable, str(TASKS_QUERY_SCRIPT), *rest], cwd=str(ESTATE_ROOT)).returncode

    if group == "status":
        return subprocess.run([sys.executable, str(PORTABLE_CLI), "--project", proj_dir, "status", *rest]).returncode

    if group in PORTABLE_PASSTHROUGH_SUBCOMMANDS:
        return subprocess.run([sys.executable, str(PORTABLE_CLI), "--project", proj_dir, group, *rest]).returncode

    if group == "preflight":
        return subprocess.run([sys.executable, str(PREFLIGHT_SCRIPT), *rest], cwd=str(ESTATE_ROOT)).returncode

    if group == "prs":
        return subprocess.run([sys.executable, str(PRS_SCRIPT), *rest], cwd=str(ESTATE_ROOT)).returncode

    if group == "install":
        ap = argparse.ArgumentParser(prog="w0m install")
        ap.add_argument("--bin-dir", default=None, help="Directory to install `w0m` shim (default: ~/.local/bin)")
        a = ap.parse_args(rest)
        shim = install_w0m_shim(Path(a.bin_dir) if a.bin_dir else None)
        print(f"[OK] Installed w0m CLI shim at {shim}")
        return 0

    print(f"[ERR] Unknown w0m command group '{group}'. Run `w0m --help`.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
