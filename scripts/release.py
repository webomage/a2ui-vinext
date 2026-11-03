#!/usr/bin/env python3
"""T473 — release tags across every estate repo, and an isolated worktree to deploy them from.

    just release-cut                  tag origin/beta of every repo as release/<version> (local tags, one version)
    just release-worktree <version>   check that release out, detached, under ~/.w0m/releases/<version>/w0m
    just release-deploy <version>     verify the worktree is untouched, deploy FROM it, then publish the tags
    just release-list | release-prune
    just e2e-stable [--no-sync]       full local regression in stable, which is synced to origin/beta first
    just stable-promote               fast-forward ~/.w0m/confirmed/w0m to the last passing e2e-stable commit set
    just deploy-all                   cut, deploy; with release.e2e_before_deploy (or W0M_DEPLOY_E2E=1) e2e runs first

Why (owner, 2026-09-27): the main checkouts are shared by people and agents and can be dirty at any moment; four
deploys in a row tested and shipped another session's uncommitted drafts. A release is cut from what is PUSHED
(`origin/beta` after a fetch), never from a working tree, so a dirty or mid-edit main checkout cannot reach it.
The worktree is detached at the tag; `verify` refuses to deploy if any repo there moved or has a change.

Fail closed: a repo without `origin/beta`, a tag that already points elsewhere, or a worktree that drifted stops
the command, naming the repo. Nothing here deploys: `release-deploy` runs the existing gated chain (Touch ID).
"""
from __future__ import annotations

import contextlib
import datetime
import io
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from unittest import mock
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve()
ESTATE = HERE.parents[1]                     # @wom (the umbrella checkout)
RELEASES = Path.home() / ".w0m" / "releases"
STABLE = Path.home() / ".w0m" / "stable"
STABLE_ROOT = STABLE / "w0m"
STABLE_LOCK = STABLE / ".lock"
STABLE_LOCKFILES = STABLE / ".lockfiles.json"
STABLE_E2E_RESULT = STABLE / "e2e-result.json"
CONFIRMED = Path.home() / ".w0m" / "confirmed"
CONFIRMED_ROOT = CONFIRMED / "w0m"
CONFIRMED_LOCKFILES = CONFIRMED / ".lockfiles.json"
CONFIRMED_PROMOTED = CONFIRMED / "promoted.json"
TAG_PREFIX = "release/"
BRANCH = "beta"
VERSION_RE = re.compile(json.loads((ESTATE / ".w0m" / "sdlc.json").read_text())["versioning"]["regex"])
# gitignored inputs the deploy chain reads (project links, not secrets: secrets arrive by `infisical run`)
UNTRACKED_INPUTS = (".infisical.yaml", "supabase/.temp")
APPS_POLICY = ESTATE / "project" / "policies" / "release-apps.json"
RECORDS = ESTATE / "releases"                 # committed, one JSON per DEPLOYED release (D1); READ them from origin/beta (committed_records), never from this working tree
PENDING_RECORDS = Path.home() / ".w0m" / "state" / "pending-release-records"   # a record that could not land yet (T554): machine-level, outside every tree


def stable_root() -> Path:
    return STABLE_ROOT


def confirmed_root() -> Path:
    return CONFIRMED_ROOT


def is_pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


@contextmanager
def stable_lock(cmd: str):
    lock_file = STABLE_LOCK
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    if lock_file.exists():
        try:
            info = json.loads(lock_file.read_text())
            pid = info.get("pid")
            if pid and is_pid_running(pid):
                raise SystemExit(
                    f"stable worktree is locked by pid {pid} ({info.get('cmd')} started {info.get('started_at')}); "
                    f"refusing concurrent {cmd}"
                )
            else:
                print(f"⚠️  cleaning up stale lock from terminated pid {pid}", file=sys.stderr)
                lock_file.unlink(missing_ok=True)
        except (json.JSONDecodeError, OSError):
            lock_file.unlink(missing_ok=True)

    lock_data = {
        "pid": os.getpid(),
        "cmd": cmd,
        "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    lock_file.write_text(json.dumps(lock_data, indent=2) + "\n")
    try:
        yield
    finally:
        try:
            if lock_file.exists():
                curr = json.loads(lock_file.read_text())
                if curr.get("pid") == os.getpid():
                    lock_file.unlink(missing_ok=True)
        except Exception:
            lock_file.unlink(missing_ok=True)


def get_lockfile_hash(lockfile: Path) -> str:
    import hashlib
    return hashlib.sha256(lockfile.read_bytes()).hexdigest()


def check_lockfile_changed(repo_path: str, repo_dir: Path, cache: dict[str, str]) -> tuple[bool, str | None]:
    lockfile = repo_dir / "pnpm-lock.yaml"
    if not lockfile.exists():
        return False, None
    h = get_lockfile_hash(lockfile)
    node_modules = repo_dir / "node_modules"
    if not node_modules.exists() or cache.get(repo_path) != h:
        return True, h
    return False, h


def load_e2e_result() -> dict | None:
    res_file = STABLE_E2E_RESULT
    if res_file.exists():
        try:
            return json.loads(res_file.read_text())
        except Exception:
            return None
    return None


def load_confirmed_result() -> dict | None:
    res_file = CONFIRMED_PROMOTED
    if res_file.exists():
        try:
            return json.loads(res_file.read_text())
        except Exception:
            return None
    return None


def evaluate_e2e(manifest_shas: dict[str, str], e2e_res: dict | None) -> dict:
    if not e2e_res:
        return {"tested": False, "reason": "no e2e result found in stable"}
    result_repos = e2e_res.get("repos", {})
    differ = [p for p, sha in manifest_shas.items() if result_repos.get(p) != sha]
    passed = e2e_res.get("passed", 0)
    failed = e2e_res.get("failed", 0)
    ts = e2e_res.get("timestamp") or e2e_res.get("time")
    if differ:
        return {"tested": False, "reason": f"commits differ in {', '.join(differ[:3])}",
                "passed": passed, "failed": failed, "time": ts}
    return {"tested": True, "passed": passed, "failed": failed, "time": ts}


def evaluate_confirmed(manifest_shas: dict[str, str], confirmed_res: dict | None) -> dict:
    if not confirmed_res:
        return {"confirmed": False, "reason": "confirmed worktree has not been promoted yet (run `just stable-promote`)"}
    promoted_repos = confirmed_res.get("repos", {})
    differ = [p for p, sha in manifest_shas.items() if promoted_repos.get(p) != sha]
    if differ:
        return {"confirmed": False, "reason": f"confirmed is behind origin/{BRANCH} in {', '.join(differ[:3])}",
                "promoted_at": confirmed_res.get("promoted_at")}
    return {"confirmed": True, "promoted_at": confirmed_res.get("promoted_at")}


def release_config() -> dict:
    """The `release` block of the estate's `.w0m/sdlc.json`: `e2e_gate` and `e2e_before_deploy`."""
    return json.loads((ESTATE / ".w0m" / "sdlc.json").read_text()).get("release", {})


def e2e_before_deploy_enabled(env: Mapping[str, str] | None = None, cfg: dict | None = None) -> bool:
    """Should `ship` run the full local regression BEFORE it cuts a release? Default OFF.

    `W0M_DEPLOY_E2E=1|0` overrides `release.e2e_before_deploy` in sdlc.json for one run. Anything else is refused,
    not guessed: an option that silently reads as "off" would let a typo skip the check the owner asked for."""
    environ: Mapping[str, str] = os.environ if env is None else env
    config: dict = release_config() if cfg is None else cfg
    raw = (environ.get("W0M_DEPLOY_E2E") or "").strip().lower()
    if raw in ("1", "true"):
        return True
    if raw in ("0", "false"):
        return False
    if raw:
        raise SystemExit(f"W0M_DEPLOY_E2E must be 1 or 0, got {raw!r}")
    value = config.get("e2e_before_deploy", False)
    if not isinstance(value, bool):
        raise SystemExit(f"release.e2e_before_deploy in .w0m/sdlc.json must be true or false, got {value!r}")
    return value


def check_e2e_gate(e2e: dict, version: str, confirmed: dict | None = None, cfg: dict | None = None) -> None:
    config = release_config() if cfg is None else cfg
    gate_mode = config.get("e2e_gate", "record")
    is_clean = e2e.get("tested") and e2e.get("failed", 0) == 0
    conf_ok = True if confirmed is None else bool(confirmed.get("confirmed"))
    if gate_mode == "require" and (not is_clean or not conf_ok):
        raise SystemExit(
            f"❌ release {version} refused by e2e_gate=require: regression suite / confirmed tier not clean on these commits (e2e={e2e}, confirmed={confirmed})"
        )
    elif not is_clean:
        fail_cnt = e2e.get("failed")
        reason = e2e.get("reason") or f"failed={fail_cnt}"
        print(f"⚠️  WARNING: release {version} e2e status: {reason}")
    elif not conf_ok and confirmed is not None:
        print(f"⚠️  WARNING: release {version} confirmed status: {confirmed.get('reason')}")


@dataclass(frozen=True)
class Repo:
    path: str          # relative to the estate root; "." is the umbrella

    def abs(self, root: Path = ESTATE) -> Path:
        return root if self.path == "." else root / self.path


def git(repo: Path, *args: str, check: bool = True) -> str:
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                       env={"LC_ALL": "C", "PATH": "/usr/bin:/bin:/opt/homebrew/bin", "HOME": str(Path.home()),
                            "GIT_TERMINAL_PROMPT": "0"})
    if check and p.returncode != 0:
        raise SystemExit(f"git -C {repo} {' '.join(args)} failed: {p.stderr.strip()[:300]}")
    return p.stdout.strip()


def estate_repos(estate: Path | None = None) -> list[Repo]:
    """The umbrella plus every declared repo in .w0m/sdlc.json that is a git checkout here (deduplicated). `estate` defaults to this checkout (agent trees pass their own root)."""
    estate = estate or ESTATE
    declared = json.loads((estate / ".w0m" / "sdlc.json").read_text()).get("repos", {})
    paths: list[str] = []
    for v in declared.values():
        p = v if isinstance(v, str) else v.get("path")
        if p and p not in paths and (estate / p / ".git").exists():
            paths.append(p)
    if not paths:
        raise SystemExit("no declared repos found (.w0m/sdlc.json → repos)")
    return [Repo(".")] + [Repo(p) for p in sorted(paths)]


def new_version() -> str:
    """The release version comes from the ONE declared producer (`just version`, T131), never minted here."""
    out = subprocess.run(["just", "version"], cwd=ESTATE, capture_output=True, text=True, check=True).stdout.strip()
    return check_version(out.splitlines()[-1])


def check_version(v: str) -> str:
    if not VERSION_RE.match(v):
        raise SystemExit(f"not a release version: {v!r} (expected YYYY.MM.DD-<unix>)")
    return v


def manifest_text(version: str, shas: dict[str, str]) -> str:
    lines = [f"w0m release {version}", "", "Cut from origin/beta of every repo (T473):"]
    lines += [f"  {path:<18} {sha}" for path, sha in shas.items()]
    return "\n".join(lines) + "\n"


# ── app fingerprints (D2/D3) ───────────────────────────────────────────────────────────────────────────────────────
def load_apps() -> dict:
    return json.loads(APPS_POLICY.read_text())


def fingerprint(repo_sha: str, umbrella_sha: str, repo: str, inputs: list[str]) -> str:
    """sha256 over the git content id of every input at the release commit. Same inputs, same fingerprint."""
    import hashlib
    parts = []
    for inp in inputs:
        if inp.startswith("@umbrella:"):
            where, sha, path = ESTATE, umbrella_sha, inp.split(":", 1)[1]
        else:
            where, sha, path = ESTATE / repo, repo_sha, inp
        oid = git(where, "rev-parse", "--verify", "--quiet", f"{sha}:{path}", check=False)
        if not oid:
            raise SystemExit(f"release-apps.json: input {inp!r} of {repo} does not exist at {sha[:10]}; fix the policy")
        parts.append(f"{inp}={oid}")
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def app_fingerprints(shas: dict[str, str]) -> dict[str, dict]:
    pol = load_apps()
    out: dict[str, dict] = {}
    for group, deployable in (("apps", True), ("tracked_not_deployed", False)):
        for name, a in pol.get(group, {}).items():
            if name.startswith("_"):
                continue
            if a["repo"] not in shas:
                raise SystemExit(f"release-apps.json: {name} names repo {a['repo']!r}, which is not in the release")
            out[name] = {"fingerprint": fingerprint(shas[a["repo"]], shas["."], a["repo"], a["inputs"]),
                         "deployable": deployable, "deploy": a.get("deploy")}
    return out


def committed_records(estate: Path | None = None) -> dict[str, dict]:
    """version -> record, for every committed release record on `origin/beta` of the umbrella (T554).

    Read from the remote-tracking ref, not from the working tree: the live checkout is shared and can be behind, ahead or diverged at any moment, and a record that
    landed from another tree must be visible to the next cut. Callers fetch first (`cut` does). Fails closed without `origin/beta`: "no records" must not mean "could not look"."""
    estate = estate or ESTATE
    if not git(estate, "rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{BRANCH}^{{commit}}", check=False):
        raise SystemExit(f"{estate}: no origin/{BRANCH}; cannot read the release records (fetch it first)")
    names = git(estate, "ls-tree", "-r", "--name-only", f"origin/{BRANCH}", "--", "releases/", check=False).splitlines()
    out: dict[str, dict] = {}
    for name in sorted(n for n in names if n.endswith(".json")):
        out[Path(name).stem] = json.loads(git(estate, "show", f"origin/{BRANCH}:{name}"))
    return out


def committed_record_names(estate: Path | None = None) -> set[str]:
    return set(committed_records(estate))


def last_deployed(estate: Path | None = None) -> dict | None:
    """The newest committed release record that was DEPLOYED, read from origin/beta (T554)."""
    recs = committed_records(estate)
    for v in sorted(recs, reverse=True):
        if recs[v].get("deployed"):
            return recs[v]
    return None


def mark_changes(apps: dict[str, dict], previous: dict | None) -> dict[str, dict]:
    prev_apps = (previous or {}).get("apps", {})
    for name, a in apps.items():
        before = prev_apps.get(name, {}).get("fingerprint")
        a["changed"] = before != a["fingerprint"]
        a["previous"] = before
    return apps


# ── cut ────────────────────────────────────────────────────────────────────────────────────────────────────────────
def cut(version: str | None = None) -> str:
    v = check_version(version or new_version())
    repos = estate_repos()
    shas: dict[str, str] = {}
    for r in repos:
        git(r.abs(), "fetch", "--quiet", "origin", BRANCH)
        sha = git(r.abs(), "rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{BRANCH}^{{commit}}", check=False)
        if not sha:
            raise SystemExit(f"{r.path}: no origin/{BRANCH}; refusing to cut a partial release")
        existing = git(r.abs(), "rev-parse", "--verify", "--quiet", f"refs/tags/{TAG_PREFIX}{v}^{{commit}}", check=False)
        if existing and existing != sha:
            raise SystemExit(f"{r.path}: tag {TAG_PREFIX}{v} already points at {existing[:10]}, not {sha[:10]}")
        shas[r.path] = sha
    msg = manifest_text(v, shas)
    for r in repos:
        if not git(r.abs(), "tag", "--list", f"{TAG_PREFIX}{v}"):
            git(r.abs(), "tag", "-a", f"{TAG_PREFIX}{v}", shas[r.path], "-m", msg)
    out = RELEASES / v
    out.mkdir(parents=True, exist_ok=True)
    previous = last_deployed()
    apps = mark_changes(app_fingerprints(shas), previous)
    manifest = {"version": v, "branch": BRANCH, "repos": shas, "apps": apps,
                "previous_release": (previous or {}).get("version")}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(msg, end="")
    changed = [n for n, a in apps.items() if a["changed"]]
    print(f"changed since {(previous or {}).get('version') or 'the first release'}: {', '.join(changed) or 'nothing'}")
    print(f"tagged {len(repos)} repo(s) locally as {TAG_PREFIX}{v}; next: just release-worktree {v}")
    return v


# ── worktree ───────────────────────────────────────────────────────────────────────────────────────────────────────
def root_of(v: str) -> Path:
    return RELEASES / v / "w0m"


def load_manifest(v: str) -> dict[str, str]:
    f = RELEASES / v / "manifest.json"
    if not f.exists():
        raise SystemExit(f"no manifest for {v}; cut it first (just release-cut)")
    return json.loads(f.read_text())["repos"]


# Relative subdirectories within repos that maintain an independent pnpm-lock.yaml (outside a pnpm-workspace.yaml).
NESTED_PNPM_DIRS: dict[str, tuple[str, ...]] = {
    "w0m-ext": ("extension",),
}


def pnpm_lock_targets(repo_path: str, repo_dir: Path) -> list[tuple[str, Path]]:
    return [
        (repo_path, repo_dir),
        *((f"{repo_path}/{sub}", repo_dir / sub) for sub in NESTED_PNPM_DIRS.get(repo_path, ())),
    ]


def provision_worktree_fixtures(root: Path, estate: Path | None = None, *, link_node_modules: bool = True) -> None:
    """Pass through read-only gitignored fixtures and dependencies needed by offline suites.

    When `link_node_modules=True` (agent trees and `--no-install` worktrees), member-repo `pnpm`
    `node_modules` trees are symlinked from `estate` for instant offline suite readiness.
    When `link_node_modules=False` (`release`, `stable`, and `confirmed` worktrees with `install=True`),
    `pnpm`-managed `node_modules` are NOT symlinked so `pnpm install --frozen-lockfile` runs hermetically
    from the checked-out lockfiles (`T617`). Standalone npm-locked skill fixtures (`mmd-validate`) remain linked.
    """
    estate = estate or ESTATE
    # 1. External dependencies / pinned binaries (_ext is gitignored in root .gitignore)
    ext_src, ext_dst = estate / "_ext", root / "_ext"
    if ext_src.exists() and not ext_dst.exists():
        ext_dst.symlink_to(ext_src)

    # 2. Deploy logs (deploy-logs is gitignored in root .gitignore)
    logs_src, logs_dst = estate / "deploy-logs", root / "deploy-logs"
    if logs_src.exists():
        logs_dst.mkdir(exist_ok=True)
        for f in logs_src.glob("*.log"):
            df = logs_dst / f.name
            if not df.exists():
                shutil.copy2(f, df)

    # 3. Credential snapshot (gitignored in w0m-web/.gitignore)
    cred_src = Repo("w0m-web").abs(estate) / "project" / "credential-snapshot.json"
    cred_dst = Repo("w0m-web").abs(root) / "project" / "credential-snapshot.json"
    if cred_src.exists() and not cred_dst.exists():
        shutil.copy2(cred_src, cred_dst)

    # 4. Audit reports (gitignored in w0m-web/.gitignore)
    audit_src = Repo("w0m-web").abs(estate) / "docs" / "audit_and_research"
    audit_dst = Repo("w0m-web").abs(root) / "docs" / "audit_and_research"
    if audit_src.exists():
        audit_dst.mkdir(parents=True, exist_ok=True)
        for f in audit_src.glob("W0M-STATUS-*.md"):
            df = audit_dst / f.name
            if not df.exists():
                shutil.copy2(f, df)

    # 5. Member repo node_modules needed by offline typecheck/deno/vitest suites (gitignored via unslashed `node_modules`)
    nm_links: list[tuple[str, str]] = [("w0m-skills", "skills/mmd-validate/node_modules")]
    if link_node_modules:
        nm_links.extend([
            ("w0m-skills", "node_modules"),
            ("w0m-api", "node_modules"),
            ("w0m-cf", "node_modules"),
            ("w0m-ext", "node_modules"),
            ("w0m-ext", "extension/node_modules"),
        ])
    for repo_name, rel_nm in nm_links:
        nm_src = Repo(repo_name).abs(estate) / rel_nm
        nm_dst = Repo(repo_name).abs(root) / rel_nm
        if nm_src.exists() and not nm_dst.exists():
            nm_dst.parent.mkdir(parents=True, exist_ok=True)
            nm_dst.symlink_to(nm_src)

    # 6. apps/web/src/.generated snapshots (gitignored in w0m-web/.gitignore)
    gen_src = Repo("w0m-web").abs(estate) / "apps" / "web" / "src" / ".generated"
    gen_dst = Repo("w0m-web").abs(root) / "apps" / "web" / "src" / ".generated"
    if gen_src.exists():
        gen_dst.mkdir(parents=True, exist_ok=True)
        for f in gen_src.glob("*.json"):
            df = gen_dst / f.name
            if not df.exists():
                shutil.copy2(f, df)


def worktree(v: str, install: bool = True) -> Path:
    check_version(v)
    shas = load_manifest(v)
    root = root_of(v)
    for path in shas:                       # umbrella first ("." sorts first in the manifest)
        r = Repo(path)
        dest = r.abs(root)
        if (dest / ".git").exists():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        git(r.abs(), "worktree", "add", "--detach", str(dest), f"{TAG_PREFIX}{v}")
    for path in shas:
        for rel in UNTRACKED_INPUTS:
            src, dst = Repo(path).abs() / rel, Repo(path).abs(root) / rel
            if src.exists() and not dst.exists():
                (shutil.copytree if src.is_dir() else shutil.copy2)(src, dst)
    provision_worktree_fixtures(root, link_node_modules=not install)
    if install:
        for path in shas:
            for label, target_dir in pnpm_lock_targets(path, Repo(path).abs(root)):
                if (target_dir / "pnpm-lock.yaml").exists() and not (target_dir / "node_modules").exists():
                    print(f"installing dependencies in {label} …", flush=True)
                    subprocess.run(["pnpm", "install", "--frozen-lockfile", "--prefer-offline"], cwd=target_dir, check=True)
    print(f"release {v} checked out at {root}; next: just release-deploy {v}")
    return root


# ── verify / publish ───────────────────────────────────────────────────────────────────────────────────────────────
def drift(v: str) -> list[str]:
    """Every way the release worktree differs from its tags. Empty = untouched."""
    shas = load_manifest(v)
    root = root_of(v)
    problems: list[str] = []
    for path, sha in shas.items():
        d = Repo(path).abs(root)
        if not (d / ".git").exists():
            problems.append(f"{path}: not checked out (just release-worktree {v})")
            continue
        head = git(d, "rev-parse", "HEAD")
        if head != sha:
            problems.append(f"{path}: HEAD {head[:10]} is not the release commit {sha[:10]}")
        dirty = git(d, "status", "--porcelain")
        if dirty:
            # Expected deploy/test artifacts:
            # 1. root: deploy_logged regenerates CHANGELOG.md upon successful deploy
            # 2. w0m-web: smoke-live / goldens generate or update Gauge audit screenshots
            real_dirty = [
                ln for ln in dirty.splitlines()
                if not (path == "." and ln.strip().endswith("CHANGELOG.md"))
                and not (path == "w0m-web" and ("screenshots/audit/" in ln or "screenshots/" in ln))
            ]
            if real_dirty:
                problems.append(f"{path}: changed since checkout: " + ", ".join(real_dirty[:5]))
    return problems


def verify(v: str, print_root: bool = False) -> int:
    check_version(v)
    problems = drift(v)
    if problems:
        print("release worktree is NOT the release:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 1
    print(root_of(v) if print_root else f"release {v}: every repo at its tag, nothing changed")
    return 0


_SSH_KEEPALIVE = "ssh -o ServerAliveInterval=15 -o ServerAliveCountMax=6"


def publish(v: str, *, max_attempts: int = 3) -> None:
    check_version(v)
    root = root_of(v)
    push_env = {"GIT_SSH_COMMAND": _SSH_KEEPALIVE, **__import__("os").environ}
    for path in load_manifest(v):
        repo_dir = Repo(path).abs(root)
        if not repo_dir.exists():
            repo_dir = Repo(path).abs()
        cmd = ["git", "-C", str(repo_dir), "push", "--quiet", "origin", f"refs/tags/{TAG_PREFIX}{v}"]
        for attempt in range(1, max_attempts + 1):
            r = subprocess.run(cmd, env=push_env)
            if r.returncode == 0:
                break
            if attempt == max_attempts:
                raise subprocess.CalledProcessError(r.returncode, cmd)
            print(f"  ↻ retrying tag push for {path} ({attempt}/{max_attempts}) after transient disconnect …", flush=True)
            _backoff(2.0)
    print(f"published {TAG_PREFIX}{v} to origin in every repo")


MODES = ("deploy", "deploy-all")


def selected_apps(manifest: dict, force_all: bool) -> list[str]:
    apps = manifest.get("apps", {})
    return [n for n, a in apps.items() if a.get("deployable") and (force_all or a.get("changed"))]


@dataclass
class Landing:
    status: str            # landed | already | pending | failed
    commit: str | None = None
    attempts: int = 0
    note: str = ""


_RECORD_PATH = re.compile(r"^(releases/[0-9A-Za-z][0-9A-Za-z._-]*\.json|CHANGELOG\.md)$")
_RACE = re.compile(r"non-fast-forward|fetch first|Broken pipe|unexpected disconnect|hung up unexpectedly")


def _backoff(seconds: float) -> None:
    """Wait between landing attempts. Not `time.sleep`: this file never imports the clock (the version and every date come from `just version`, T131)."""
    threading.Event().wait(seconds)


def _git_bytes(repo: Path, args: list[str], *, env: dict | None = None, input: bytes | None = None) -> subprocess.CompletedProcess:
    base = {
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin:/opt/homebrew/bin",
        "HOME": str(Path.home()),
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_SSH_COMMAND": _SSH_KEEPALIVE,
    }
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, env={**base, **(env or {})}, input=input)


def _park(state_dir: Path, v: str, files: dict[str, bytes], message: str) -> Path:
    d = state_dir / v
    d.mkdir(parents=True, exist_ok=True)
    payload = {"version": v, "message": message, "files": {k: base64.b64encode(b).decode() for k, b in files.items()}}
    tmp = d / "payload.json.tmp"
    tmp.write_text(json.dumps(payload, indent=2) + "\n")
    tmp.replace(d / "payload.json")
    return d


def _plumb(estate: Path, args: list[str], what: str, *, env: dict | None = None, input: bytes | None = None) -> str:
    r = _git_bytes(estate, args, env=env, input=input)
    if r.returncode != 0:
        raise SystemExit(f"{what} failed: {r.stderr.decode().strip()[:300]}")
    return r.stdout.decode().strip()


def land_release_record(estate: Path, v: str, files: dict[str, bytes], message: str, *, state_dir: Path | None = None,
                        max_attempts: int = 4, sleep=_backoff, _between_fetch_and_push=None) -> Landing:
    """Land `files` (releases/<v>.json and CHANGELOG.md only) on origin/beta as ONE commit, however many agents are landing there (T554).

    Built with git plumbing directly on the freshly fetched tip: a private index, no working tree, no checkout, so the live checkout, its index and its local branch are
    never touched and nothing is stranded on it. A lost race (non-fast-forward) refetches and rebuilds on the new tip; any other refusal is not retried. When it cannot land,
    the payload is parked in machine-level state and the note names the exact retry command. The push still runs the repo's pre-push hook (`--no-verify` is prohibited)."""
    if not re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z._-]*", v):
        raise SystemExit(f"refusing to record release {v!r}: not a plain version string")
    for path in files:
        if ".." in path.split("/") or not _RECORD_PATH.match(path):
            raise SystemExit(f"refusing to record {path!r}: only releases/<version>.json and CHANGELOG.md belong in a release record")
    state = state_dir or PENDING_RECORDS
    for attempt in range(1, max_attempts + 1):
        _plumb(estate, ["fetch", "--quiet", "origin", BRANCH], f"fetch of origin/{BRANCH}")
        tip = git(estate, "rev-parse", f"refs/remotes/origin/{BRANCH}^{{commit}}")
        for path, content in files.items():
            if path.startswith("releases/"):
                have = _git_bytes(estate, ["cat-file", "blob", f"{tip}:{path}"])
                if have.returncode == 0 and have.stdout != content:
                    raise SystemExit(f"{path} already exists with different content on origin/{BRANCH}; refusing to overwrite a deploy record")
        with tempfile.TemporaryDirectory(prefix="release-record-index-") as tmp:
            env = {"GIT_INDEX_FILE": str(Path(tmp) / "index")}
            _plumb(estate, ["read-tree", tip], "git read-tree", env=env)
            for path, content in files.items():
                blob = _plumb(estate, ["hash-object", "-w", "--stdin"], "git hash-object", input=content)
                _plumb(estate, ["update-index", "--add", "--cacheinfo", f"100644,{blob},{path}"], f"git update-index {path}", env=env)
            tree_id = _plumb(estate, ["write-tree"], "git write-tree", env=env)
        if tree_id == git(estate, "rev-parse", f"{tip}^{{tree}}"):
            if (state / v).exists():
                shutil.rmtree(state / v, ignore_errors=True)
            return Landing("already", tip, attempt, f"the record is already on origin/{BRANCH}")
        sha = _plumb(estate, ["commit-tree", tree_id, "-p", tip, "-m", message], "git commit-tree (is user.name/user.email set?)")
        if _between_fetch_and_push:
            _between_fetch_and_push(attempt)
        push = _git_bytes(estate, ["push", "--quiet", "origin", f"{sha}:refs/heads/{BRANCH}"])
        if push.returncode == 0:
            if (state / v).exists():
                shutil.rmtree(state / v, ignore_errors=True)
            return Landing("landed", sha, attempt, "")
        err = push.stderr.decode().strip()
        if not _RACE.search(err):
            _park(state, v, files, message)
            return Landing("failed", sha, attempt, f"push refused (not a race, not retried): {err[:400]}. Parked in {state / v}; retry: just release-record {v}")
        sleep(min(2 ** attempt, 8))
    _park(state, v, files, message)
    return Landing("pending", None, max_attempts,
                   f"origin/{BRANCH} moved on every one of {max_attempts} attempts. The record is parked in {state / v}; land it with: just release-record {v}")


def retry_pending_record(estate: Path, v: str, *, state_dir: Path | None = None, max_attempts: int = 4, sleep=_backoff) -> Landing:
    """Land a parked release record (T554)."""
    state = state_dir or PENDING_RECORDS
    f = state / v / "payload.json"
    if not f.exists():
        raise SystemExit(f"nothing parked for {v} in {state}")
    payload = json.loads(f.read_text())
    files = {k: base64.b64decode(b) for k, b in payload["files"].items()}
    r = land_release_record(estate, v, files, payload["message"], state_dir=state, max_attempts=max_attempts, sleep=sleep)
    if r.status in ("landed", "already"):
        shutil.rmtree(state / v, ignore_errors=True)
    return r


def fast_forward_estate(estate: Path) -> bool:
    """Best effort: move the live checkout's local beta to origin/beta so the next catch-up is trivial. Never forces, never stashes, never raises (T554).
    False when it cannot (not on beta, diverged, or uncommitted changes in a file the merge would touch)."""
    if git(estate, "symbolic-ref", "--short", "-q", "HEAD", check=False) != BRANCH:
        return False
    return _git_bytes(estate, ["merge", "--ff-only", "--quiet", f"refs/remotes/origin/{BRANCH}"]).returncode == 0


def record_release(v: str, manifest: dict, selected: list[str], changelog_src: Path | None = None) -> Landing:
    """D1: land releases/<version>.json and CHANGELOG.md on origin/beta as one commit (T554: no longer committed in the shared live checkout, which stranded the
    commit when another agent landed first). The changelog is regenerated from `deploy_log` at the END of a successful deploy (only then does this release's row
    exist), so it rides in the release-record commit and the next cut carries it. It is read from the release worktree, never copied into the live checkout."""
    e2e_eval = evaluate_e2e(manifest.get("repos", {}), load_e2e_result())
    confirmed_eval = evaluate_confirmed(manifest.get("repos", {}), load_confirmed_result())
    rec = {**manifest, "deployed": True, "deployed_apps": selected, "e2e": e2e_eval, "confirmed": confirmed_eval}
    files = {f"releases/{v}.json": (json.dumps(rec, indent=2) + "\n").encode()}
    cl = changelog_src if changelog_src is not None else root_of(v) / "CHANGELOG.md"
    if cl.exists():
        files["CHANGELOG.md"] = cl.read_bytes()
    message = f"chore(T473): release {v} deployed ({', '.join(selected) or 'no app changed'})"
    landing = land_release_record(ESTATE, v, files, message)
    if landing.status in ("landed", "already"):
        caught_up = fast_forward_estate(ESTATE)
        print(f"recorded releases/{v}.json on origin/{BRANCH} ({landing.status}, {landing.attempts} attempt(s))"
              + ("" if caught_up else f"; the live checkout was not fast-forwarded: git fetch && git merge --ff-only origin/{BRANCH}"))
    else:
        print(f"\n❌ release {v} IS DEPLOYED and its tags are published, but its release record is NOT on origin/{BRANCH}: {landing.note}", flush=True)
    return landing


def deploy_from(v: str, mode: str, force_all: bool = False) -> int:
    """Run the gated deploy chain INSIDE the release worktree; publish the tags only if it succeeds."""
    if mode not in MODES:
        raise SystemExit(f"mode must be one of {MODES}, got {mode!r}")
    if verify(v) != 0:
        return 1
    root = root_of(v)
    manifest = json.loads((RELEASES / v / "manifest.json").read_text())
    
    # Check E2E and Confirmed tier gate (AC6, AC9)
    e2e_eval = evaluate_e2e(manifest.get("repos", {}), load_e2e_result())
    confirmed_eval = evaluate_confirmed(manifest.get("repos", {}), load_confirmed_result())
    check_e2e_gate(e2e_eval, v, confirmed_eval)

    selected = selected_apps(manifest, force_all)
    per_app = {f"W0M_APP_VERSION_{n.upper()}": a["fingerprint"][:12] for n, a in manifest.get("apps", {}).items()}
    print(f"apps to deploy: {', '.join(selected) or 'none (nothing changed; tests, migrations and smoke still run)'}"
          + (" [--all]" if force_all else ""), flush=True)
    env = {**__import__("os").environ, **per_app,
           "W0M_RELEASE_APPS": " ".join(selected),  # the chain deploys only these (T473 D2)
           "W0M_RELEASE_WORKTREE": "1",               # the worktree's `just deploy` runs the chain, not another release
           "W0M_DEPLOY_VERSION": v,                   # the release version IS the deploy version (deploy_log, /api/health)
           "W0M_DEPLOY_LOGS": str(ESTATE / "deploy-logs")}   # logs stay in the main estate, one place
    env.pop("W0M_DEPLOY_LOCAL", None)
    print(f"deploying release {v} from {root} ({mode}) …", flush=True)
    with stable_lock(f"deploy {v} {mode}"):
        try:
            rc = subprocess.run(["just", mode], cwd=root, env=env).returncode    # inherits the tty: Touch ID prompts work
            if rc != 0:
                print(f"\n❌ {mode} failed (exit {rc}); release {v} was NOT published. Worktree kept at {root}.\n"
                      f"   Fix on beta and cut a new release (just {mode}), or retry this one: just release-deploy {v} {mode}")
                return rc
            if verify(v) != 0:
                print(f"❌ the deploy changed the release worktree; tags NOT published — inspect {root}")
                return 1
            publish(v)
            landing = record_release(v, manifest, selected, changelog_src=root / "CHANGELOG.md")
            return 0 if landing.status in ("landed", "already") else 2
        finally:
            try:
                subprocess.run([sys.executable, str(HERE.parent / "confirm_step.py"), "--clear"],
                               cwd=ESTATE, check=False, capture_output=True, text=True, timeout=10)
            except (OSError, subprocess.SubprocessError):
                pass


def stable_sync(install: bool = True) -> Path:
    """AC1: move stable to origin/beta of every estate repo (fetch, detached checkout),
    creating it on first use. Refuses when any stable repo has a change, and reinstalls a repo's
    dependencies only when its lockfile changed since the last install."""
    with stable_lock("stable-sync"):
        return _stable_sync_unlocked(install)


def _stable_sync_unlocked(install: bool) -> Path:
    """The sync itself, for a caller that already holds the stable lock (the lock refuses re-entry, even from the
    same pid, so `e2e-stable` cannot call `stable_sync` while it holds it)."""
    s_root = stable_root()
    s_root.mkdir(parents=True, exist_ok=True)
    repos = estate_repos()

    # Check for uncommitted changes first across all existing stable repos
    for r in repos:
        dest = r.abs(s_root)
        if (dest / ".git").exists():
            dirty = git(dest, "status", "--porcelain")
            if dirty:
                raise SystemExit(f"stable repo {r.path} has uncommitted changes; refusing to sync:\n{dirty}")

    # Fetch and checkout detached HEAD at origin/beta
    for r in repos:
        dest = r.abs(s_root)
        git(r.abs(), "fetch", "--quiet", "origin", BRANCH)
        if not (dest / ".git").exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            git(r.abs(), "worktree", "add", "--detach", str(dest), f"origin/{BRANCH}")
        else:
            git(dest, "checkout", "--detach", f"origin/{BRANCH}")

    # Provision inputs and fixtures
    for r in repos:
        for rel in UNTRACKED_INPUTS:
            src, dst = r.abs() / rel, r.abs(s_root) / rel
            if src.exists() and not dst.exists():
                (shutil.copytree if src.is_dir() else shutil.copy2)(src, dst)
    provision_worktree_fixtures(s_root, link_node_modules=not install)

    # Lockfile-driven dependency installation
    if install:
        lock_cache_file = STABLE_LOCKFILES
        cache = {}
        if lock_cache_file.exists():
            try:
                cache = json.loads(lock_cache_file.read_text())
            except Exception:
                cache = {}
        new_cache = dict(cache)
        for r in repos:
            for label, target_dir in pnpm_lock_targets(r.path, r.abs(s_root)):
                changed, h = check_lockfile_changed(label, target_dir, cache)
                if changed:
                    print(f"installing dependencies in {label} (lockfile changed) …", flush=True)
                    subprocess.run(["pnpm", "install", "--frozen-lockfile", "--prefer-offline"], cwd=target_dir, check=True)
                    if h:
                        new_cache[label] = h
                else:
                    if h:
                        print(f"dependencies in {label} up to date (lockfile unchanged)")
        lock_cache_file.write_text(json.dumps(new_cache, indent=2) + "\n")

    print(f"stable worktree synchronized at {s_root}")
    return s_root


def stable_promote(install: bool = True) -> Path:
    """AC9: fast-forward the persistent confirmed worktree (~/.w0m/confirmed/w0m) to the commit set of the last
    PASSING e2e-stable result, and refuse otherwise."""
    with stable_lock("stable-promote"):
        return _stable_promote_unlocked(install)


def _stable_promote_unlocked(install: bool) -> Path:
    e2e_res = load_e2e_result()
    if not e2e_res:
        raise SystemExit("no e2e-stable result found; run `just e2e-stable` before `just stable-promote`")
    exit_code = e2e_res.get("exit_code", 0 if e2e_res.get("failed", 1) == 0 and e2e_res.get("passed", 0) > 0 else 1)
    if exit_code != 0 or e2e_res.get("failed", 1) != 0 or e2e_res.get("passed", 0) <= 0:
        raise SystemExit(
            f"last e2e-stable result is not passing (passed={e2e_res.get('passed')}, failed={e2e_res.get('failed')}, "
            f"exit_code={exit_code}); refusing to promote to confirmed"
        )
    repos = estate_repos()
    shas = e2e_res.get("repos", {})
    missing = [r.path for r in repos if not shas.get(r.path)]
    if missing:
        raise SystemExit(f"e2e-stable result is missing commit SHAs for {', '.join(missing)}; refusing to promote")

    c_root = confirmed_root()
    c_root.mkdir(parents=True, exist_ok=True)
    for r in repos:
        dest = r.abs(c_root)
        if (dest / ".git").exists():
            dirty = git(dest, "status", "--porcelain")
            if dirty:
                raise SystemExit(f"confirmed repo {r.path} has uncommitted changes; refusing to promote:\n{dirty}")

    for r in repos:
        dest = r.abs(c_root)
        sha = shas[r.path]
        if not (dest / ".git").exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            git(r.abs(), "worktree", "add", "--detach", str(dest), sha)
        else:
            git(dest, "checkout", "--detach", sha)

    for r in repos:
        for rel in UNTRACKED_INPUTS:
            src, dst = r.abs() / rel, r.abs(c_root) / rel
            if src.exists() and not dst.exists():
                (shutil.copytree if src.is_dir() else shutil.copy2)(src, dst)
    provision_worktree_fixtures(c_root, link_node_modules=not install)

    if install:
        lock_cache_file = CONFIRMED_LOCKFILES
        cache = {}
        if lock_cache_file.exists():
            try:
                cache = json.loads(lock_cache_file.read_text())
            except Exception:
                cache = {}
        new_cache = dict(cache)
        for r in repos:
            for label, target_dir in pnpm_lock_targets(r.path, r.abs(c_root)):
                changed, h = check_lockfile_changed(label, target_dir, cache)
                if changed:
                    print(f"installing dependencies in confirmed/{label} (lockfile changed) …", flush=True)
                    subprocess.run(["pnpm", "install", "--frozen-lockfile", "--prefer-offline"], cwd=target_dir, check=True)
                    if h:
                        new_cache[label] = h
                else:
                    if h:
                        print(f"dependencies in confirmed/{label} up to date (lockfile unchanged)")
        lock_cache_file.write_text(json.dumps(new_cache, indent=2) + "\n")

    promoted = {
        "repos": {r.path: shas[r.path] for r in repos},
        "passed": e2e_res.get("passed", 0),
        "failed": 0,
        "e2e_timestamp": e2e_res.get("timestamp") or e2e_res.get("time"),
        "promoted_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    CONFIRMED_PROMOTED.parent.mkdir(parents=True, exist_ok=True)
    CONFIRMED_PROMOTED.write_text(json.dumps(promoted, indent=2) + "\n")
    print(f"confirmed worktree promoted at {c_root}")
    return c_root


def run_e2e_stable(args: list[str]) -> int:
    """AC3: Run the full local regression inside stable, after moving stable to origin/beta.

    The sync is the DEFAULT (owner, 2026-09-30): measured that day, stable sat at a commit two days behind beta, so
    a bare run tested old code and the recorded result could never match a release's commits. `--no-sync` opts out,
    for re-running one spec on exactly what stable holds; stable must already exist then."""
    sync = "--no-sync" not in args
    args = [a for a in args if a != "--no-sync"]
    with stable_lock("e2e-stable"):
        s_root = stable_root()
        if sync:
            _stable_sync_unlocked(install=True)
        elif not (s_root / ".git").exists():
            raise SystemExit("--no-sync, but the stable worktree does not exist yet; run `just stable-sync` first")
        print(f"running local regression in {s_root} …", flush=True)
        cmd = ["just", "e2e-local"] + args
        import datetime
        start_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
        rc = subprocess.run(cmd, cwd=s_root).returncode
        # Capture commit SHAs across stable repos
        repos_sha = {}
        for r in estate_repos():
            d = r.abs(s_root)
            if (d / ".git").exists():
                repos_sha[r.path] = git(d, "rev-parse", "HEAD")

        res = {
            "repos": repos_sha,
            "passed": 1 if rc == 0 else 0,
            "failed": 0 if rc == 0 else 1,
            "exit_code": rc,
            "timestamp": start_time,
        }
        res_file = STABLE_E2E_RESULT
        res_file.write_text(json.dumps(res, indent=2) + "\n")
        print(f"e2e-stable finished (exit {rc}); recorded to {res_file}")
        return rc


def ship(mode: str, force_all: bool = False, e2e: bool | None = None) -> int:
    """The default deploy: cut a release from origin/beta, check it out in isolation, deploy it, publish its tags.

    With `release.e2e_before_deploy` (default off) or `--e2e`, the full local regression runs FIRST, in stable after a
    sync, before anything is cut. A failure stops here whatever `e2e_gate` says: the owner asked for the run, so a red
    result is not a warning to deploy past. The `e2e_gate` check at deploy time still runs and compares the result's
    commits with the release's, so a push that lands between the two is reported there."""
    if e2e is None:
        e2e = e2e_before_deploy_enabled()
    if e2e:
        print("e2e_before_deploy: running the full local regression in stable first (this can take a long time) …", flush=True)
        rc = run_e2e_stable([])
        if rc != 0:
            print(f"\n❌ e2e failed (exit {rc}); nothing was cut or deployed.")
            return rc
    with stable_lock("release-prune"):      # refuses while another deploy holds the lock
        prune_releases(reserve=1)           # room for the release cut below: at most `keep_worktrees` on disk, always
    v = cut()
    worktree(v)
    return deploy_from(v, mode, force_all)


def local_warning() -> None:
    """Printed by `just deploy-local`: what a forced local deploy will ship that is not on origin/beta."""
    print("⚠️  FORCED LOCAL DEPLOY — building from the working trees as they are, not from a release (T473).")
    for r in estate_repos():
        d = r.abs()
        dirty = git(d, "status", "--porcelain", check=False).splitlines()
        ahead = git(d, "rev-list", "--count", f"origin/{BRANCH}..HEAD", check=False) or "?"
        if dirty or ahead not in ("0", "?"):
            print(f"   {r.path}: {len(dirty)} uncommitted file(s), {ahead} unpushed commit(s)")
            for line in dirty[:8]:
                print(f"      {line}")
    print("   The safe default is `just deploy` (a tagged release in its own worktree).", flush=True)


def list_releases() -> None:
    """D4: every release — deployed ones from the committed records (with the apps they changed), plus local ones."""
    seen: set[str] = set()
    recs = committed_records()
    for v in sorted(recs, reverse=True):
        rec = recs[v]
        seen.add(rec["version"])
        print(f"{rec['version']}  deployed  apps: {', '.join(rec.get('deployed_apps') or []) or 'none changed'}")
    for d in sorted(RELEASES.glob("*"), reverse=True):
        if (d / "manifest.json").exists() and d.name not in seen:
            m = json.loads((d / "manifest.json").read_text())
            changed = [n for n, a in m.get("apps", {}).items() if a.get("changed")]
            state = "worktree" if (d / "w0m" / ".git").exists() else "tags only"
            print(f"{d.name}  not deployed ({state})  would change: {', '.join(changed) or 'nothing'}")


def remove_worktree(v: str) -> None:
    """Remove release `v`'s worktree in every repo; its tags and manifest stay. No-op when already removed."""
    d = RELEASES / v
    if not (d / "w0m").exists():
        return
    for path in reversed(list(load_manifest(v))):        # members before the umbrella
        dest = Repo(path).abs(root_of(v))
        if dest.exists():
            git(Repo(path).abs(), "worktree", "remove", "--force", str(dest), check=False)
    shutil.rmtree(d / "w0m", ignore_errors=True)
    for path in load_manifest(v):
        git(Repo(path).abs(), "worktree", "prune", check=False)
    print(f"removed worktree of {v} (tags and manifest kept)")


def retention_keep(cfg: dict | None = None) -> int:
    """The most release worktrees allowed on disk: `release.keep_worktrees` in sdlc.json (default 5, owner 2026-10-01).

    At least 2: one for the release about to be cut and one older, so that a successful release can be kept beside a
    newest one that failed."""
    config: dict = release_config() if cfg is None else cfg
    value = config.get("keep_worktrees", 5)
    if isinstance(value, bool) or not isinstance(value, int) or value < 2:
        raise SystemExit(f"release.keep_worktrees in .w0m/sdlc.json must be an integer >= 2, got {value!r}")
    return value


def prune_plan(releases: list[tuple[str, bool, bool]], keep: int) -> tuple[list[str], list[str]]:
    """Which release worktrees survive and which go. `releases` is (version, has_worktree, deployed).

    Owner 2026-10-01: "5 last deploys max (success or not), and at least one of these 5 is a preserved successful
    deploy". So at most `keep` survive in TOTAL: the newest `keep` releases, success or not; when none of them is a
    successful one that still has a worktree, the OLDEST of them gives its place to the newest successful one that does
    (the total stays `keep`). Releases without a worktree take a place in the window but are never listed for removal.
    Versions sort by time. Returns (kept, removed)."""
    ordered = sorted(releases, reverse=True)
    kept = [v for v, _, _ in ordered[:keep]]
    if not any(has_wt and ok for v, has_wt, ok in ordered if v in kept):
        best = next((v for v, has_wt, ok in ordered if has_wt and ok), None)
        if best is not None:
            kept = kept[: keep - 1] + [best]
    removed = sorted(v for v, has_wt, _ in releases if has_wt and v not in kept)
    return sorted(kept), removed


def prune_releases(keep: int | None = None, reserve: int = 0) -> list[str]:
    """Apply the retention rule to ~/.w0m/releases: remove the worktrees `prune_plan` drops. Tags, manifests and the
    committed deploy records stay for every release. The caller holds the stable lock (a deploy may be running).

    `reserve` leaves room for releases about to be cut: `ship` passes 1, so the new release is the last of the
    `release.keep_worktrees` and the disk never holds more, even mid-deploy or after an interrupted one."""
    keep = retention_keep() - reserve if keep is None else keep
    if keep < 1:
        raise SystemExit(f"keep must be at least 1, got {keep}")
    deployed = committed_record_names()
    rows = [(d.name, (d / "w0m").exists(), d.name in deployed) for d in sorted(RELEASES.glob("*"))
            if (d / "manifest.json").exists()]
    kept, removed = prune_plan(rows, keep)
    for v in removed:
        remove_worktree(v)
    held = sum(1 for v, has_wt, _ in rows if has_wt and v in kept)
    print(f"release worktrees: kept {held}, removed {len(removed)} (at most {keep}: the newest, success or not, "
          f"with a successful one among them)")
    return removed


# ── offline red probes ─────────────────────────────────────────────────────────────────────────────────────────────
def self_test() -> int:
    global RELEASES, STABLE, STABLE_LOCK
    cases: list[tuple[str, bool]] = []
    v = new_version()
    cases.append(("the version comes from `just version` and matches the declared regex", VERSION_RE.match(v) is not None))
    code = HERE.read_text().split("def self_test")[0]
    cases.append(("release.py does not format dates itself", "strftime" not in code and "import time" not in code))
    for bad in ("latest", "2026-09-27", "2026.09.27", "../x", "2026.09.27-1; rm"):
        try:
            check_version(bad)
            cases.append((f"rejects version {bad!r}", False))
        except SystemExit:
            cases.append((f"rejects version {bad!r}", True))
    m = manifest_text(v, {".": "a" * 40, "w0m-web": "b" * 40})
    cases.append(("the tag message names every repo and its commit", "w0m-web" in m and "b" * 40 in m and "a" * 40 in m))
    repos = estate_repos()
    cases.append(("the umbrella is always part of a release, first", repos[0].path == "."))
    cases.append(("declared repos are included (web, api)", {"w0m-web", "w0m-api"} <= {r.path for r in repos}))
    cases.append(("the release root is under ~/.w0m/releases, never a main checkout",
                  str(root_of(v)).startswith(str(RELEASES)) and not str(root_of(v)).startswith(str(Path.home() / "Projects"))))
    cases.append(("cut reads origin/beta, never HEAD or the working tree", "refs/remotes/origin/" in HERE.read_text()
                  and '"rev-parse", "HEAD"' not in HERE.read_text().split("def cut")[1].split("def root_of")[0]))
    apps = {"web": {"fingerprint": "a", "deployable": True}, "cp": {"fingerprint": "b", "deployable": True},
            "db": {"fingerprint": "c", "deployable": False}}
    marked = mark_changes({k: dict(x) for k, x in apps.items()},
                          {"apps": {"web": {"fingerprint": "a"}, "cp": {"fingerprint": "OLD"}, "db": {"fingerprint": "OLD"}}})
    cases.append(("an unchanged fingerprint is not a change; a moved one is",
                  marked["web"]["changed"] is False and marked["cp"]["changed"] is True))
    cases.append(("only changed DEPLOYABLE apps are selected (db is tracked, never selected)",
                  selected_apps({"apps": marked}, False) == ["cp"]))
    cases.append(("--all selects every deployable app", selected_apps({"apps": marked}, True) == ["web", "cp"]))
    first = mark_changes({k: dict(x) for k, x in apps.items()}, None)
    cases.append(("with no previous release every app is a change", all(a["changed"] for a in first.values())))
    rel = app_fingerprints({".": git(ESTATE, "rev-parse", "HEAD"), **{r.path: git(r.abs(), "rev-parse", "HEAD")
                                                                        for r in estate_repos() if r.path != "."}})
    cases.append(("every app in release-apps.json fingerprints at HEAD (inputs exist)",
                  {"api", "web", "cp", "join", "job", "demo", "db"} <= set(rel)))
    cases.append(("fingerprints are stable for the same commit", rel["cp"]["fingerprint"] == app_fingerprints(
        {".": git(ESTATE, "rev-parse", "HEAD"), **{r.path: git(r.abs(), "rev-parse", "HEAD")
                                                  for r in estate_repos() if r.path != "."}})["cp"]["fingerprint"]))
    try:
        deploy_from(v, "deploy-everything")
        cases.append(("an unknown deploy mode is refused before anything runs", False))
    except SystemExit:
        cases.append(("an unknown deploy mode is refused before anything runs", True))
    body = HERE.read_text().split("def deploy_from")[1].split("def ship")[0]
    cases.append(("tags are published only after a successful deploy and a clean re-verify",
                  body.index("publish(v)") > body.index("if rc != 0") > 0 and body.count("verify(v)") == 2))
    cases.append(("the worktree deploy sets W0M_RELEASE_WORKTREE and the release version",
                  '"W0M_RELEASE_WORKTREE": "1"' in body and '"W0M_DEPLOY_VERSION": v' in body))
    ship_body = HERE.read_text().split("def ship")[1].split("def local_warning")[0]
    cases.append(("retention runs once, in ship BEFORE the cut; deploy_from never prunes",
                  "prune_releases" not in body and ship_body.index("prune_releases(reserve=1)") < ship_body.index("cut()")))
    rec_body = HERE.read_text().split("def record_release")[1].split("def deploy_from")[0]
    cases.append(("the release record lands CHANGELOG.md and releases/<version>.json through land_release_record, never by committing in the live checkout (T554)",
                  '"CHANGELOG.md"' in rec_body and "land_release_record(" in rec_body and '"commit"' not in rec_body))
    import tempfile

    def raises(fn) -> bool:
        try:
            fn()
        except SystemExit:
            return True
        return False

    # Retention (owner 2026-10-01): at most N worktrees in total, the newest ones, with a successful one among them.
    vs = [f"2026.09.2{i}-{i}" for i in range(1, 9)]                      # v1 .. v8, oldest first
    allwt = [(v, True, False) for v in vs]

    def plan(deployed: set, keep: int = 5, with_wt: set | None = None) -> tuple[list, list]:
        rows = [(v, with_wt is None or v in with_wt, v in deployed) for v in vs]
        return prune_plan(rows, keep)

    kept, gone = plan({vs[7]})
    cases.append(("retention keeps the newest 5 and removes the older ones", kept == vs[3:] and gone == vs[:3]))
    kept, gone = plan({vs[1]})
    cases.append(("an older successful release takes the place of the OLDEST of the newest 5: still 5 in total",
                  len(kept) == 5 and vs[1] in kept and vs[3] in gone and vs[4:] == [k for k in kept if k != vs[1]]))
    kept, gone = plan({vs[5]})
    cases.append(("a successful release inside the newest 5 changes nothing", kept == vs[3:] and gone == vs[:3]))
    kept, gone = plan(set())
    cases.append(("with nothing deployed, only the newest 5 are kept", kept == vs[3:] and gone == vs[:3]))
    cases.append(("with fewer releases than the limit nothing is removed", prune_plan(allwt[:3], 5)[1] == []))
    kept, gone = plan({vs[0], vs[1]}, with_wt={vs[1], *vs[3:]})
    cases.append(("a record without a worktree is not a successful release to keep: the next one that HAS one is",
                  vs[1] in kept and vs[0] not in gone and gone == [vs[3]]))
    kept, gone = plan({vs[0], vs[1]}, with_wt={vs[0], *vs[3:]})
    cases.append(("the newest successful release that has a worktree is kept", vs[0] in kept and gone == [vs[3]]))
    cases.append(("a release with no worktree is never listed for removal", plan(set(), with_wt={vs[7]})[1] == []))
    kept, gone = plan({vs[0], vs[1]})
    cases.append(("of two older successful releases the NEWER one is kept and the older one goes",
                  vs[1] in kept and vs[0] in gone and len(kept) == 5))
    kept, gone = prune_plan([("a", True, True), ("b", True, False)], 2)
    cases.append(("with room for 2 a failed newest release keeps the successful one beside it", kept == ["a", "b"] and gone == []))
    kept, gone = prune_plan([("a", True, True), ("b", True, False), ("c", True, False)], 2)
    cases.append(("with room for 2 and two failures after a success, the older failure goes, not the success",
                  kept == ["a", "c"] and gone == ["b"]))

    def lifecycle(seq: str, keep: int = 5) -> tuple[int, int, int]:
        """The real order in `ship`: prune with room for one, cut, deploy. S success, F failure, X interrupted (nothing
        after the deploy runs). Returns (worst count on disk, runs with no successful worktree on disk, runs over keep)."""
        rows: list[list] = []
        worst = no_success = over = 0
        for n, outcome in enumerate(seq, 1):
            kept_now, _ = prune_plan([(r[0], r[1], r[2]) for r in rows], keep - 1)
            for r in rows:
                r[1] = r[0] in kept_now
            rows.append([f"2026.09.30-{n:04d}", True, outcome == "S"])
            on_disk = sum(1 for r in rows if r[1])
            worst = max(worst, on_disk)
            over += on_disk > keep
            no_success += any(r[2] for r in rows) and not any(r[1] and r[2] for r in rows)
        return worst, no_success, over

    import itertools

    sims = [lifecycle("".join(seq)) for seq in itertools.product("SFX", repeat=7)]
    cases.append((f"over all {len(sims)} sequences of success, failure and interruption, the disk never holds more than 5",
                  max(w for w, _, _ in sims) == 5 and sum(o for _, _, o in sims) == 0))
    cases.append(("over those sequences a successful release is on disk whenever one has ever succeeded",
                  sum(n for _, n, _ in sims) == 0))
    cases.append(("a run of interrupted deploys does not grow the disk", lifecycle("X" * 12)[0] == 5))
    cases.append(("retention_keep defaults to 5", retention_keep({}) == 5))
    cases.append(("retention_keep accepts 2", retention_keep({"keep_worktrees": 2}) == 2))
    cases.append(("retention_keep rejects 0, 1, a string and a bool",
                  all(raises(lambda v=v: retention_keep({"keep_worktrees": v})) for v in (0, 1, "5", True))))
    cases.append(("the live sdlc.json declares keep_worktrees", release_config().get("keep_worktrees") == 5))
    removed_calls: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        rel_dir, rec_dir = base / "releases-dir", base / "records"
        rel_dir.mkdir()
        rec_dir.mkdir()
        for name in vs + ["no-manifest"]:
            (rel_dir / name).mkdir()
            if name != "no-manifest":
                (rel_dir / name / "manifest.json").write_text("{}")
                (rel_dir / name / "w0m").mkdir()
        (rec_dir / f"{vs[1]}.json").write_text("{}")
        with mock.patch.multiple(sys.modules[__name__], RELEASES=rel_dir, RECORDS=rec_dir, committed_record_names=lambda *a, **k: {vs[1]},
                                 remove_worktree=lambda v: removed_calls.append(v)):
            with contextlib.redirect_stdout(io.StringIO()):
                result = prune_releases(5)
                with_room = prune_releases(reserve=1)
        cases.append(("prune_releases removes exactly the planned worktrees and never a dir without a manifest",
                      result == [vs[0], vs[2], vs[3]] and removed_calls[:3] == [vs[0], vs[2], vs[3]]))
        cases.append(("prune_releases(reserve=1) holds one place for the release about to be cut",
                      with_room == [vs[0], vs[2], vs[3], vs[4]]))
        cases.append(("prune_releases refuses keep below 1", raises(lambda: prune_releases(0))))

    # T481 probes: stable root, lock, lockfile change caching, and e2e gate evaluation
    cases.append(("stable root is under ~/.w0m/stable, never a main checkout",
                  str(stable_root()).startswith(str(STABLE)) and not str(stable_root()).startswith(str(Path.home() / "Projects"))))
    real_stable, real_stable_lock = STABLE, STABLE_LOCK
    with tempfile.TemporaryDirectory() as tmp_l:
        fake_stable = Path(tmp_l)
        STABLE = fake_stable
        STABLE_LOCK = fake_stable / ".lock"
        try:
            with stable_lock("test-holder"):
                lock_content = json.loads((fake_stable / ".lock").read_text())
                cases.append(("stable lock records pid and command", lock_content["pid"] == os.getpid() and lock_content["cmd"] == "test-holder"))
                try:
                    with stable_lock("test-concurrent"):
                        cases.append(("stable lock refuses concurrent execution", False))
                except SystemExit as exc:
                    cases.append(("stable lock refuses concurrent execution", "test-holder" in str(exc)))
            cases.append(("stable lock released on context exit", not (fake_stable / ".lock").exists()))
            # Stale lock cleanup
            (fake_stable / ".lock").write_text(json.dumps({"pid": 99999999, "cmd": "dead-cmd", "started_at": "old"}))
            with stable_lock("test-stale"):
                cases.append(("stable lock cleans up stale locks from dead pids", json.loads((fake_stable / ".lock").read_text())["pid"] == os.getpid()))
        finally:
            STABLE = real_stable
            STABLE_LOCK = real_stable_lock

    with tempfile.TemporaryDirectory() as tmp_lf:
        fake_repo = Path(tmp_lf)
        lf = fake_repo / "pnpm-lock.yaml"
        lf.write_text("lock-v1")
        nm = fake_repo / "node_modules"
        nm.mkdir()
        h1 = get_lockfile_hash(lf)
        changed, _ = check_lockfile_changed("test", fake_repo, {})
        cases.append(("lockfile detector flags missing cache as changed", changed is True))
        changed, _ = check_lockfile_changed("test", fake_repo, {"test": h1})
        cases.append(("lockfile detector skips when hash matches and node_modules exists", changed is False))
        lf.write_text("lock-v2")
        changed, _ = check_lockfile_changed("test", fake_repo, {"test": h1})
        cases.append(("lockfile detector detects modified lockfile content", changed is True))

    manifest_shas = {".": "aaa", "w0m-web": "bbb"}
    e1 = evaluate_e2e(manifest_shas, None)
    cases.append(("evaluate_e2e reports untested when no result", e1["tested"] is False))
    e2 = evaluate_e2e(manifest_shas, {"repos": {".": "aaa", "w0m-web": "bbb"}, "passed": 50, "failed": 0})
    cases.append(("evaluate_e2e reports tested when repos match", e2["tested"] is True and e2["passed"] == 50))
    e3 = evaluate_e2e(manifest_shas, {"repos": {".": "aaa", "w0m-web": "ccc"}, "passed": 50, "failed": 0})
    cases.append(("evaluate_e2e reports untested when repos differ", e3["tested"] is False and "commits differ" in e3["reason"]))

    # Owner 2026-09-30: e2e-stable syncs first by default, and deploy-all can run e2e first (off by default).
    cases.append(("e2e_before_deploy is OFF with nothing set", e2e_before_deploy_enabled({}, {}) is False))
    cases.append(("e2e_before_deploy follows the config when no env is set",
                  e2e_before_deploy_enabled({}, {"e2e_before_deploy": True}) is True))
    cases.append(("W0M_DEPLOY_E2E=0 overrides a config of true",
                  e2e_before_deploy_enabled({"W0M_DEPLOY_E2E": "0"}, {"e2e_before_deploy": True}) is False))
    cases.append(("W0M_DEPLOY_E2E=1 overrides a config of false",
                  e2e_before_deploy_enabled({"W0M_DEPLOY_E2E": "1"}, {"e2e_before_deploy": False}) is True))
    cases.append(("a typo in W0M_DEPLOY_E2E is refused, not read as off",
                  raises(lambda: e2e_before_deploy_enabled({"W0M_DEPLOY_E2E": "yes"}, {}))))
    cases.append(("a non-boolean e2e_before_deploy in sdlc.json is refused",
                  raises(lambda: e2e_before_deploy_enabled({}, {"e2e_before_deploy": "false"}))))
    cases.append(("the live sdlc.json declares e2e_before_deploy as false",
                  release_config().get("e2e_before_deploy") is False))

    calls: list[str] = []
    me = sys.modules[__name__]

    def recording(label: str, rc: int = 0):
        def fn(*a: object, **k: object) -> int:
            calls.append(label)
            return rc
        return fn

    def boom_cut(*a: object, **k: object) -> str:
        calls.append("cut")
        return "v"

    with tempfile.TemporaryDirectory() as tmp_e, contextlib.ExitStack() as stack:
        fake = Path(tmp_e)

        def fake_sync(install: bool) -> Path:
            calls.append("sync")
            (fake / "w0m" / ".git").mkdir(parents=True, exist_ok=True)
            return fake / "w0m"

        def fake_run(cmd: object, **kw: object) -> subprocess.CompletedProcess:
            calls.append("e2e")
            return subprocess.CompletedProcess([], 0)

        stack.enter_context(mock.patch.multiple(
            me, STABLE=fake, STABLE_LOCK=fake / ".lock", STABLE_ROOT=fake / "w0m", STABLE_E2E_RESULT=fake / "r.json",
            estate_repos=lambda: [], _stable_sync_unlocked=fake_sync))
        stack.enter_context(mock.patch.object(subprocess, "run", fake_run))

        raises(lambda: run_e2e_stable([]))                  # a regression must show as a named failed probe, not a crash
        cases.append(("e2e-stable syncs stable BEFORE it runs the suite, by default", calls == ["sync", "e2e"]))
        calls.clear()
        (fake / "w0m" / ".git").mkdir(parents=True, exist_ok=True)     # this probe's own stable, whatever the one above did
        raises(lambda: run_e2e_stable(["--no-sync"]))
        cases.append(("--no-sync runs the suite on what stable holds, with no sync", calls == ["e2e"]))
        calls.clear()
        shutil.rmtree(fake / "w0m")
        cases.append(("--no-sync with no stable worktree is refused, not silently created",
                      raises(lambda: run_e2e_stable(["--no-sync"])) and calls == []))
        cases.append(("the stable lock is free after a run", not (fake / ".lock").exists()))

        # ship: e2e off -> never runs it; on and green -> runs it then cuts; on and red -> stops before the cut
        stack.enter_context(mock.patch.multiple(me, cut=boom_cut, worktree=recording("worktree"), deploy_from=recording("deploy"),
                                                 prune_releases=recording("prune")))
        calls.clear()
        ship("deploy", False, e2e=False)
        cases.append(("ship with e2e off never runs it; it prunes, then cuts", calls == ["prune", "cut", "worktree", "deploy"]))
        with mock.patch.object(me, "run_e2e_stable", recording("e2e", 0)):
            calls.clear()
            ship("deploy", False, e2e=True)
            cases.append(("ship with e2e on and green runs e2e first, then cuts and deploys",
                          calls == ["e2e", "prune", "cut", "worktree", "deploy"]))
        with mock.patch.object(me, "run_e2e_stable", recording("e2e", 1)):
            calls.clear()
            with contextlib.redirect_stdout(io.StringIO()):     # ship prints a failure line that the suite runner would count
                rc = ship("deploy", False, e2e=True)
            cases.append(("ship with e2e on and RED stops before anything is cut", rc == 1 and calls == ["e2e"]))

    # T481 AC9 probes: confirmed root, evaluate_confirmed, stable-promote refusal on missing/red e2e, and promotion on passing e2e
    cases.append(("confirmed root is under ~/.w0m/confirmed, never a main checkout",
                  str(confirmed_root()).startswith(str(CONFIRMED)) and not str(confirmed_root()).startswith(str(Path.home() / "Projects"))))
    c1 = evaluate_confirmed(manifest_shas, None)
    cases.append(("evaluate_confirmed reports unpromoted when no promoted.json", c1["confirmed"] is False and "stable-promote" in c1["reason"]))
    c2 = evaluate_confirmed(manifest_shas, {"repos": {".": "aaa", "w0m-web": "bbb"}, "promoted_at": "2026-10-18T00:00:00Z"})
    cases.append(("evaluate_confirmed reports confirmed when repos match", c2["confirmed"] is True))
    c3 = evaluate_confirmed(manifest_shas, {"repos": {".": "aaa", "w0m-web": "ccc"}, "promoted_at": "2026-10-18T00:00:00Z"})
    cases.append(("evaluate_confirmed reports behind origin/beta when repos differ", c3["confirmed"] is False and "behind origin/beta" in c3["reason"]))
    cases.append(("check_e2e_gate under require refuses when confirmed is behind origin/beta even if e2e passed",
                  raises(lambda: check_e2e_gate({"tested": True, "failed": 0}, "2026.10.18-1", c3, cfg={"e2e_gate": "require"}))))

    with tempfile.TemporaryDirectory() as tmp_c, contextlib.ExitStack() as stack_c:
        fake_c = Path(tmp_c)
        fake_e2e = fake_c / "e2e-result.json"
        fake_conf = fake_c / "confirmed"
        fake_promoted = fake_conf / "promoted.json"
        git_calls: list[tuple[str, ...]] = []

        def fake_git(repo: Path, *args: str, check: bool = True) -> str:
            git_calls.append((repo.name, *args))
            if args[:2] == ("worktree", "add"):
                (Path(args[3]) / ".git").mkdir(parents=True, exist_ok=True)
            return ""

        stack_c.enter_context(mock.patch.multiple(
            me, STABLE=fake_c, STABLE_LOCK=fake_c / ".lock", STABLE_E2E_RESULT=fake_e2e,
            CONFIRMED=fake_conf, CONFIRMED_ROOT=fake_conf / "w0m",
            CONFIRMED_LOCKFILES=fake_conf / ".lockfiles.json", CONFIRMED_PROMOTED=fake_promoted,
            estate_repos=lambda: [Repo("."), Repo("w0m-web")],
            provision_worktree_fixtures=lambda *a, **kw: None,
            git=fake_git))

        cases.append(("stable-promote refuses when no e2e-stable result exists", raises(lambda: stable_promote(install=False))))
        fake_e2e.write_text(json.dumps({"repos": {".": "aaa", "w0m-web": "bbb"}, "passed": 10, "failed": 1, "exit_code": 1}))
        cases.append(("stable-promote refuses when last e2e-stable result failed", raises(lambda: stable_promote(install=False))))
        fake_e2e.write_text(json.dumps({"repos": {".": "aaa"}, "passed": 10, "failed": 0, "exit_code": 0}))
        cases.append(("stable-promote refuses when e2e-stable result is missing a repo SHA", raises(lambda: stable_promote(install=False))))
        fake_e2e.write_text(json.dumps({"repos": {".": "aaa", "w0m-web": "bbb"}, "passed": 10, "failed": 0, "exit_code": 0, "timestamp": "2026-10-18T00:00:00Z"}))
        with contextlib.redirect_stdout(io.StringIO()):
            promoted_path = stable_promote(install=False)
        promoted_data = json.loads(fake_promoted.read_text()) if fake_promoted.exists() else {}
        cases.append(("stable-promote advances confirmed worktree and writes promoted.json when e2e-stable passed",
                      promoted_path == fake_conf / "w0m" and promoted_data.get("repos") == {".": "aaa", "w0m-web": "bbb"}))

    # T617 probes: symlink-safe .gitignore across governed JS repos + hermetic vs symlinked node_modules provisioning
    with tempfile.TemporaryDirectory() as tmp_gi:
        base_gi = Path(tmp_gi)
        ext_target = base_gi / "shared_nm"
        ext_target.mkdir()
        gi_dirty: list[str] = []
        for repo_name, rel_links in (
            ("w0m-api", ("node_modules",)),
            ("w0m-cf", ("node_modules",)),
            ("w0m-ext", ("node_modules", "extension/node_modules")),
            ("w0m-skills", ("node_modules", "skills/mmd-validate/node_modules")),
            ("w0m-web", ("node_modules",)),
            ("w0m-sec", ("node_modules",)),
        ):
            src_gi = ESTATE / repo_name / ".gitignore"
            if not src_gi.exists():
                continue
            rdir = base_gi / repo_name
            rdir.mkdir(parents=True)
            git(rdir, "init", "--quiet")
            shutil.copy2(src_gi, rdir / ".gitignore")
            git(rdir, "add", ".gitignore")
            for rel_nm in rel_links:
                dst_nm = rdir / rel_nm
                dst_nm.parent.mkdir(parents=True, exist_ok=True)
                dst_nm.symlink_to(ext_target)
            st = [ln for ln in git(rdir, "status", "--porcelain").splitlines() if not ln.startswith("A  .gitignore")]
            if st:
                gi_dirty.append(f"{repo_name}: {st}")
        cases.append(("every governed JS .gitignore ignores symlinked node_modules (0 untracked in git status, T617)",
                      gi_dirty == []))

    with tempfile.TemporaryDirectory() as tmp_pf:
        base_pf = Path(tmp_pf)
        fake_est = base_pf / "estate"
        for repo_name, rel_nm in (
            ("w0m-skills", "node_modules"),
            ("w0m-skills", "skills/mmd-validate/node_modules"),
            ("w0m-api", "node_modules"),
            ("w0m-cf", "node_modules"),
            ("w0m-ext", "node_modules"),
            ("w0m-ext", "extension/node_modules"),
        ):
            (fake_est / repo_name / rel_nm).mkdir(parents=True, exist_ok=True)
        (fake_est / "_ext").mkdir(parents=True, exist_ok=True)

        wt_agent = base_pf / "agent_wt"
        wt_agent.mkdir()
        provision_worktree_fixtures(wt_agent, estate=fake_est, link_node_modules=True)
        cases.append(("provision_worktree_fixtures(link_node_modules=True) links pnpm and mmd-validate node_modules for agent trees (T617)",
                      (wt_agent / "w0m-api" / "node_modules").is_symlink()
                      and (wt_agent / "w0m-cf" / "node_modules").is_symlink()
                      and (wt_agent / "w0m-ext" / "extension" / "node_modules").is_symlink()
                      and (wt_agent / "w0m-skills" / "skills" / "mmd-validate" / "node_modules").is_symlink()))

        wt_rel = base_pf / "release_wt"
        wt_rel.mkdir()
        provision_worktree_fixtures(wt_rel, estate=fake_est, link_node_modules=False)
        cases.append(("provision_worktree_fixtures(link_node_modules=False) skips pnpm node_modules symlinks so frozen-lockfile install runs hermetically (T617)",
                      not (wt_rel / "w0m-api" / "node_modules").exists()
                      and not (wt_rel / "w0m-cf" / "node_modules").exists()
                      and not (wt_rel / "w0m-ext" / "extension" / "node_modules").exists()
                      and (wt_rel / "w0m-skills" / "skills" / "mmd-validate" / "node_modules").is_symlink()))

    with tempfile.TemporaryDirectory() as tmp_wt, contextlib.ExitStack() as stack_wt:
        base_wt = Path(tmp_wt)
        fake_rel = base_wt / "releases"
        ver = "2026.11.03-1793713000"
        (fake_rel / ver).mkdir(parents=True)
        (fake_rel / ver / "manifest.json").write_text(json.dumps({
            "repos": {".": "1111111111", "w0m-api": "2222222222", "w0m-ext": "3333333333"}
        }))
        fake_est_wt = base_wt / "estate"
        (fake_est_wt / "w0m-api" / "node_modules").mkdir(parents=True)
        (fake_est_wt / "w0m-ext" / "extension" / "node_modules").mkdir(parents=True)
        pnpm_cwds: list[Path] = []

        def fake_wt_git(repo: Path, *args: str, check: bool = True) -> str:
            if args[:2] == ("worktree", "add"):
                dest = Path(args[3])
                (dest / ".git").mkdir(parents=True, exist_ok=True)
                if dest.name == "w0m-api":
                    (dest / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n")
                elif dest.name == "w0m-ext":
                    (dest / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n")
                    (dest / "extension").mkdir(parents=True, exist_ok=True)
                    (dest / "extension" / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n")
            return ""

        def fake_pnpm_run(cmd: object, **kw: object) -> subprocess.CompletedProcess:
            cwd = Path(str(kw.get("cwd", "")))
            pnpm_cwds.append(cwd)
            (cwd / "node_modules").mkdir(parents=True, exist_ok=True)
            return subprocess.CompletedProcess(cmd, 0)  # type: ignore[arg-type]

        stack_wt.enter_context(mock.patch.multiple(me, RELEASES=fake_rel, ESTATE=fake_est_wt, git=fake_wt_git))
        stack_wt.enter_context(mock.patch.object(subprocess, "run", fake_pnpm_run))
        with contextlib.redirect_stdout(io.StringIO()):
            wt_out = worktree(ver, install=True)
        cases.append(("worktree(install=True) installs root and nested w0m-ext/extension lockfiles hermetically without symlinks (T617)",
                      pnpm_cwds == [wt_out / "w0m-api", wt_out / "w0m-ext", wt_out / "w0m-ext" / "extension"]
                      and not (wt_out / "w0m-api" / "node_modules").is_symlink()
                      and not (wt_out / "w0m-ext" / "extension" / "node_modules").is_symlink()))

    for name, ok in cases:
        print(f"  {'✅' if ok else '❌'} {name}")
    failed = sum(not ok for _, ok in cases)
    print(f"{len(cases) - failed}/{len(cases)} probes pass")
    return 1 if failed else 0


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "--test":
        return self_test()
    if cmd == "cut":
        cut(rest[0] if rest else None)
        return 0
    if cmd == "stable-sync":
        stable_sync(install="--no-install" not in rest)
        return 0
    if cmd == "stable-promote":
        stable_promote(install="--no-install" not in rest)
        return 0
    if cmd == "e2e-stable":
        return run_e2e_stable(rest)
    if cmd == "worktree":
        worktree(rest[0], install="--no-install" not in rest)
        return 0
    if cmd == "verify":
        return verify(rest[0], print_root="--print-root" in rest)
    if cmd == "publish":
        publish(rest[0])
        manifest = json.loads((RELEASES / rest[0] / "manifest.json").read_text())
        selected = selected_apps(manifest, False)
        return 0 if record_release(rest[0], manifest, selected).status in ("landed", "already") else 2
    if cmd == "record":
        # T554: land (or re-land) a release record: a parked one first, otherwise build it from the release manifest.
        if (PENDING_RECORDS / rest[0] / "payload.json").exists():
            landing = retry_pending_record(ESTATE, rest[0])
        else:
            manifest = json.loads((RELEASES / rest[0] / "manifest.json").read_text())
            landing = record_release(rest[0], manifest, selected_apps(manifest, False))
        print(f"release record {rest[0]}: {landing.status}" + (f" ({landing.note})" if landing.note else ""))
        return 0 if landing.status in ("landed", "already") else 2
    force_all = "--all" in rest
    e2e_flag = True if "--e2e" in rest else False if "--no-e2e" in rest else None
    rest = [a for a in rest if a not in ("--all", "--e2e", "--no-e2e")]
    if cmd == "ship":
        return ship(rest[0] if rest else "deploy", force_all, e2e_flag)
    if cmd == "deploy":
        return deploy_from(rest[0], rest[1] if len(rest) > 1 else "deploy", force_all)
    if cmd == "local-warning":
        local_warning()
        return 0
    if cmd == "list":
        list_releases()
        return 0
    if cmd == "prune":
        with stable_lock("release-prune"):
            prune_releases(int(rest[0]) if rest and rest[0] else None)
        return 0
    raise SystemExit(f"unknown command {cmd!r}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
