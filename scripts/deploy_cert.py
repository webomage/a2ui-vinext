#!/usr/bin/env python3
"""Content-addressed estate tree-set certification for session-complete & deploy gates (T650, AgDR-0057).

Computes a SHA-256 `tree_set_digest` across:
  1. Every repository in `.w0m/sdlc.json -> repos` plus the umbrella (`.`), mapped to its exact `HEAD` commit SHA.
  2. `policy_digest` (SHA-256 over `w0m-web/project/test-suites.json` + certified stage schema).

Invariants (`AgDR-0025`, `AgDR-0057`, `T503`):
  - **Fail-closed on dirty trees**: Any repo with modified or staged tracked files (`git status --porcelain --untracked-files=no`)
    is refused certification (`certify` exits 1) and never matches a cached certificate (`MISS: dirty_tree`).
  - **Shift-left in `session-complete`**: `session-complete` certifies the committed 10-repo tree-set BEFORE pushing to
    `origin/beta` (blocking broken `vitest`, `py-typecheck`, `deno`, or `check-guardrails` runs before landing), and
    re-certifies `canonical_root` automatically if `agent_tree.py land` rebases onto a concurrent push.
  - **Deploy-only cache consumption**: Standalone `just test` and `just check-guardrails` invoked interactively outside a
    deploy (`W0M_DEPLOY_LOGGED`, `W0M_RELEASE_WORKTREE`, and `W0M_USE_DEPLOY_CERT` all unset) ALWAYS execute uncached.
    Inside `deploy` / `deploy-all`, verified `HIT`s complete in <0.2s while `state-check`, `check-warp`, `check-infisical`,
    `_assert-provisioned`, and `smoke-live` always execute live.
  - **Zero-duplication uncached fallback**: On an uncached deploy (`MISS`), `preflight` records `"prepush": true` so `test`
    runs `run_suites.py --tier offline --level medium --skip-prepush` instead of executing the 16 `prepush` suites twice.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
INLINE_CRED_RE = r"(postgres|postgresql|mysql|mongodb|redis|amqp)://[A-Za-z0-9._%+-]+:[A-Za-z0-9._%+~!-]{6,}@"

CommandRunner = Callable[[Sequence[str], Path, Mapping[str, str] | None], int]


@dataclass(frozen=True)
class TreeSetState:
    estate_root: str
    repos: dict[str, str]
    dirty_repos: list[str]
    policy_digest: str
    tree_set_digest: str

    @property
    def is_clean(self) -> bool:
        return bool(self.repos) and len(self.dirty_repos) == 0


def _truthy_env(name: str, env: Mapping[str, str]) -> bool:
    raw = (env.get(name) or "").strip().lower()
    if not raw or raw in ("0", "false", "no"):
        return False
    if raw in ("1", "true", "yes"):
        return True
    raise SystemExit(f"{name} must be 0 or 1, got {raw!r}")


def reset_requested(env: Mapping[str, str] | None = None) -> bool:
    environ: Mapping[str, str] = os.environ if env is None else env
    return _truthy_env("W0M_DEPLOY_CERT_RESET", environ)


def deploy_cert_context_active(env: Mapping[str, str] | None = None) -> bool:
    environ: Mapping[str, str] = os.environ if env is None else env
    return any(
        _truthy_env(k, environ)
        for k in ("W0M_DEPLOY_LOGGED", "W0M_RELEASE_WORKTREE", "W0M_USE_DEPLOY_CERT")
    )


def get_cache_dir(env: Mapping[str, str] | None = None) -> Path:
    environ: Mapping[str, str] = os.environ if env is None else env
    override = (environ.get("W0M_DEPLOY_CERT_CACHE_DIR") or "").strip()
    p = Path(override) if override else (Path.home() / ".cache" / "w0m" / "deploy-cert")
    try:
        p.mkdir(parents=True, exist_ok=True)
    except OSError:
        p = Path("/tmp/w0m-deploy-cert")
        p.mkdir(parents=True, exist_ok=True)
    return p


def discover_estate_repos(estate_root: Path) -> list[str]:
    """Return `['.']` plus sorted declared member repos in `.w0m/sdlc.json` that exist as git checkouts."""
    sdlc_path = estate_root / ".w0m" / "sdlc.json"
    if not sdlc_path.is_file():
        raise SystemExit(f"deploy-cert: missing {sdlc_path}")
    sdlc_doc: dict[str, Any] = json.loads(sdlc_path.read_text(encoding="utf-8"))
    declared = sdlc_doc.get("repos") or {}
    paths: list[str] = []
    if isinstance(declared, dict):
        for val in declared.values():
            rel = val if isinstance(val, str) else (val.get("path") if isinstance(val, dict) else None)
            if isinstance(rel, str) and rel and rel not in paths and (estate_root / rel / ".git").exists():
                paths.append(rel)
    out: list[str] = []
    if (estate_root / ".git").exists():
        out.append(".")
    out.extend(sorted(paths))
    if not out:
        raise SystemExit(f"deploy-cert: no git repositories found under {estate_root}")
    return out


def compute_policy_digest(estate_root: Path) -> str:
    h = hashlib.sha256()
    h.update(f"deploy-cert-schema-v{SCHEMA_VERSION}\n".encode("utf-8"))
    suites_path = estate_root / "w0m-web" / "project" / "test-suites.json"
    if suites_path.is_file():
        h.update(suites_path.read_bytes())
    else:
        h.update(b"<no-test-suites-json>")
    return h.hexdigest()[:24]


def _git_capture(repo_dir: Path, *args: str) -> tuple[int, str]:
    proc = subprocess.run(
        ["git", "-C", str(repo_dir), *args],
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "LC_ALL": "C",
            "GIT_TERMINAL_PROMPT": "0",
        },
        check=False,
    )
    return proc.returncode, proc.stdout.strip()


def inspect_tree_set(estate_root: Path) -> TreeSetState:
    root = estate_root.resolve()
    repo_paths = discover_estate_repos(root)
    repos: dict[str, str] = {}
    dirty: list[str] = []
    for rel in repo_paths:
        rdir = root if rel == "." else (root / rel)
        rc_sha, sha = _git_capture(rdir, "rev-parse", "HEAD")
        if rc_sha != 0 or not re.fullmatch(r"[0-9a-f]{40}", sha):
            dirty.append(rel)
            repos[rel] = "unresolved"
            continue
        repos[rel] = sha
        rc_st, st = _git_capture(rdir, "status", "--porcelain", "--untracked-files=no")
        if rc_st != 0 or bool(st):
            dirty.append(rel)
    policy_digest = compute_policy_digest(root)
    canonical_payload = json.dumps(
        {
            "schema": SCHEMA_VERSION,
            "policy_digest": policy_digest,
            "repos": repos,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()
    return TreeSetState(
        estate_root=str(root),
        repos=repos,
        dirty_repos=dirty,
        policy_digest=policy_digest,
        tree_set_digest=digest,
    )


def cert_file_path(tree_set_digest: str, env: Mapping[str, str] | None = None) -> Path:
    return get_cache_dir(env) / f"{tree_set_digest}.json"


@contextlib.contextmanager
def _cert_lock(tree_set_digest: str, env: Mapping[str, str] | None = None) -> Iterator[None]:
    lock_path = get_cache_dir(env) / f"{tree_set_digest}.lock"
    try:
        fh = lock_path.open("w", encoding="utf-8")
    except OSError:
        yield
        return
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        with contextlib.suppress(OSError):
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        fh.close()


def load_cert_record(state: TreeSetState, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    if not state.is_clean:
        return {}
    path = cert_file_path(state.tree_set_digest, env)
    if not path.is_file():
        return {}
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    if raw.get("schema") != SCHEMA_VERSION:
        return {}
    if raw.get("tree_set_digest") != state.tree_set_digest:
        return {}
    if raw.get("policy_digest") != state.policy_digest:
        return {}
    if raw.get("repos") != state.repos:
        return {}
    return raw


def update_cert_stage(
    state: TreeSetState,
    *,
    stage: str,
    source: str,
    env: Mapping[str, str] | None = None,
    reset_first: bool = False,
) -> dict[str, Any]:
    if not state.is_clean:
        return {}
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    with _cert_lock(state.tree_set_digest, env):
        existing = {} if reset_first else load_cert_record(state, env)
        stages_raw = existing.get("stages")
        stages: dict[str, Any] = dict(stages_raw) if isinstance(stages_raw, dict) else {}
        stages[stage] = {"passed": True, "at": now, "source": source}
        if stage == "offline_medium":
            stages["prepush"] = {"passed": True, "at": now, "source": source}
            stages["offline_medium_rest"] = {"passed": True, "at": now, "source": source}
        elif stage == "offline_medium_rest" and bool((stages.get("prepush") or {}).get("passed")):
            stages["offline_medium"] = {"passed": True, "at": now, "source": source}

        has_guardrails = bool((stages.get("guardrails") or {}).get("passed"))
        has_medium = bool((stages.get("offline_medium") or {}).get("passed"))
        certified = has_guardrails and has_medium

        record: dict[str, Any] = {
            "schema": SCHEMA_VERSION,
            "tree_set_digest": state.tree_set_digest,
            "policy_digest": state.policy_digest,
            "repos": state.repos,
            "stages": stages,
            "certified": certified,
            "updated_at": now,
            "certified_at": existing.get("certified_at") or (now if certified else None),
        }
        if certified and reset_first:
            record["certified_at"] = now
        path = cert_file_path(state.tree_set_digest, env)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(path)
        return record


def _default_runner(
    cmd: Sequence[str],
    cwd: Path,
    extra_env: Mapping[str, str] | None = None,
) -> int:
    merged_env = dict(os.environ)
    if extra_env:
        merged_env.update(extra_env)
    proc = subprocess.run(list(cmd), cwd=str(cwd), env=merged_env, check=False)
    return proc.returncode


def ensure_cert_dependencies(
    estate_root: Path,
    *,
    canonical_root: Path | None = None,
    runner: CommandRunner = _default_runner,
) -> None:
    """Ensure member repo `node_modules` exist before running offline suites in an agent tree."""
    if canonical_root is not None and canonical_root.resolve() != estate_root.resolve():
        for repo_name, rel_nm in (
            ("w0m-skills", "skills/mmd-validate/node_modules"),
            ("w0m-skills", "node_modules"),
            ("w0m-api", "node_modules"),
            ("w0m-cf", "node_modules"),
            ("w0m-ext", "node_modules"),
            ("w0m-ext", "extension/node_modules"),
        ):
            src = canonical_root / repo_name / rel_nm
            dst = estate_root / repo_name / rel_nm
            if src.exists() and not dst.exists() and (estate_root / repo_name).is_dir():
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.symlink_to(src)

        gen_src = canonical_root / "w0m-web" / "apps" / "web" / "src" / ".generated"
        gen_dst = estate_root / "w0m-web" / "apps" / "web" / "src" / ".generated"
        if gen_src.is_dir() and (estate_root / "w0m-web").is_dir():
            gen_dst.mkdir(parents=True, exist_ok=True)
            for gf in gen_src.glob("*.json"):
                target = gen_dst / gf.name
                if not target.exists():
                    shutil.copy2(gf, target)

    web_dir = estate_root / "w0m-web"
    if (web_dir / "pnpm-lock.yaml").is_file() and not (web_dir / "node_modules" / ".modules.yaml").is_file():
        print("[deploy-cert] Installing w0m-web/node_modules from local pnpm store ...", flush=True)
        rc = runner(["pnpm", "install", "--frozen-lockfile", "--prefer-offline"], web_dir, None)
        if rc != 0:
            raise RuntimeError(f"pnpm install in {web_dir} failed with exit {rc}")


def run_guardrails_raw(
    estate_root: Path,
    *,
    runner: CommandRunner = _default_runner,
) -> int:
    print("🛡  Pre-deploy security gate (secrets + test-admin + connection-strings)...", flush=True)
    steps: list[tuple[Sequence[str], Path]] = []
    if (estate_root / "w0m-api" / ".git").exists():
        steps.append((["pre-commit", "run", "gitleaks", "--all-files"], estate_root / "w0m-api"))
    if (estate_root / "w0m-web" / ".git").exists():
        steps.append((["pre-commit", "run", "gitleaks", "--all-files"], estate_root / "w0m-web"))
        steps.append((["pre-commit", "run", "guard-test-admin", "--all-files"], estate_root / "w0m-web"))

    for cmd, cwd in steps:
        rc = runner(cmd, cwd, None)
        if rc != 0:
            return rc

    print("🔑 Inline-credential connection-string scan (gitleaks gap — T32)...", flush=True)
    for sub in ("w0m-api", "w0m-web"):
        rdir = estate_root / sub
        if not (rdir / ".git").exists():
            continue
        proc = subprocess.run(
            ["git", "-C", str(rdir), "--no-pager", "grep", "-nEI", INLINE_CRED_RE, "--", ":!*.md"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            print(proc.stdout, end="", flush=True)
            print("❌ inline credential in tracked files — remove + rotate (see T32)", flush=True)
            return 1

    print("✅ security gate passed", flush=True)
    return 0


def cmd_certify(
    estate_root: Path,
    *,
    canonical_root: Path | None = None,
    force_reset: bool = False,
    source: str = "certify",
    env: Mapping[str, str] | None = None,
    runner: CommandRunner = _default_runner,
) -> tuple[int, dict[str, Any]]:
    environ: Mapping[str, str] = os.environ if env is None else env
    state = inspect_tree_set(estate_root)
    if not state.is_clean:
        detail = {
            "ok": False,
            "reason": "dirty_tree",
            "dirty_repos": state.dirty_repos,
            "tree_set_digest": state.tree_set_digest,
        }
        return 1, detail

    do_reset = force_reset or reset_requested(environ)
    if not do_reset:
        existing = load_cert_record(state, environ)
        if existing.get("certified") is True:
            print(
                f"  ✅ deploy-cert [certify]: tree-set {state.tree_set_digest[:12]} already certified "
                f"({len(state.repos)} repo(s), {existing.get('certified_at')})",
                flush=True,
            )
            return 0, {"ok": True, "cached": True, "record": existing}

    ensure_cert_dependencies(estate_root, canonical_root=canonical_root, runner=runner)

    rc_g = run_guardrails_raw(estate_root, runner=runner)
    if rc_g != 0:
        return rc_g, {"ok": False, "reason": "guardrails_failed", "tree_set_digest": state.tree_set_digest}
    update_cert_stage(state, stage="guardrails", source=source, env=environ, reset_first=do_reset)

    rc_m = runner(
        [sys.executable, str(estate_root / "scripts" / "run_suites.py"), "--tier", "offline", "--level", "medium"],
        estate_root,
        {"W0M_PRELAND_CERTIFY": "1"},
    )
    if rc_m != 0:
        return rc_m, {"ok": False, "reason": "offline_medium_failed", "tree_set_digest": state.tree_set_digest}

    # Re-verify tree-set did not become dirty during the suite run before sealing certificate.
    post_state = inspect_tree_set(estate_root)
    if not post_state.is_clean or post_state.tree_set_digest != state.tree_set_digest:
        return 1, {
            "ok": False,
            "reason": "tree_mutated_during_certify",
            "dirty_repos": post_state.dirty_repos,
            "tree_set_digest": post_state.tree_set_digest,
        }

    rec = update_cert_stage(post_state, stage="offline_medium", source=source, env=environ)
    print(
        f"  ✅ deploy-cert [certified]: sealed tree-set {post_state.tree_set_digest[:12]} "
        f"across {len(post_state.repos)} repo(s)",
        flush=True,
    )
    return 0, {"ok": True, "cached": False, "record": rec}


def cmd_preflight(
    estate_root: Path,
    *,
    env: Mapping[str, str] | None = None,
    runner: CommandRunner = _default_runner,
) -> int:
    environ: Mapping[str, str] = os.environ if env is None else env
    state = inspect_tree_set(estate_root)
    if state.is_clean and not reset_requested(environ):
        rec = load_cert_record(state, environ)
        stages = rec.get("stages") or {}
        if rec.get("certified") is True or bool((stages.get("prepush") or {}).get("passed")):
            stamp = rec.get("certified_at") or rec.get("updated_at") or "certified"
            print(
                f"  ✅ deploy-cert [preflight]: tree-set {state.tree_set_digest[:12]} certified "
                f"({len(state.repos)} repo(s), {stamp}) — skipping duplicate prepush pass",
                flush=True,
            )
            return 0

    rc = runner([sys.executable, str(estate_root / "scripts" / "run_suites.py"), "--prepush"], estate_root, None)
    if rc == 0:
        post = inspect_tree_set(estate_root)
        if post.is_clean and post.tree_set_digest == state.tree_set_digest:
            update_cert_stage(
                post,
                stage="prepush",
                source="deploy-preflight",
                env=environ,
                reset_first=reset_requested(environ),
            )
    return rc


def cmd_guardrails(
    estate_root: Path,
    *,
    env: Mapping[str, str] | None = None,
    runner: CommandRunner = _default_runner,
) -> int:
    environ: Mapping[str, str] = os.environ if env is None else env
    state = inspect_tree_set(estate_root)
    if deploy_cert_context_active(environ) and state.is_clean and not reset_requested(environ):
        rec = load_cert_record(state, environ)
        stages = rec.get("stages") or {}
        if rec.get("certified") is True or bool((stages.get("guardrails") or {}).get("passed")):
            stamp = rec.get("certified_at") or rec.get("updated_at") or "certified"
            print(
                f"  ✅ deploy-cert [check-guardrails]: tree-set {state.tree_set_digest[:12]} certified "
                f"({stamp}) — skipping duplicate secret/guardrail scan",
                flush=True,
            )
            return 0

    rc = run_guardrails_raw(estate_root, runner=runner)
    if rc == 0:
        post = inspect_tree_set(estate_root)
        if post.is_clean and post.tree_set_digest == state.tree_set_digest:
            update_cert_stage(post, stage="guardrails", source="check-guardrails", env=environ)
    return rc


def cmd_test(
    estate_root: Path,
    *,
    level: str = "medium",
    env: Mapping[str, str] | None = None,
    runner: CommandRunner = _default_runner,
) -> int:
    environ: Mapping[str, str] = os.environ if env is None else env
    state = inspect_tree_set(estate_root)
    in_deploy = deploy_cert_context_active(environ)
    do_reset = reset_requested(environ)

    if in_deploy and level == "medium" and state.is_clean and not do_reset:
        rec = load_cert_record(state, environ)
        stages = rec.get("stages") or {}
        if rec.get("certified") is True or bool((stages.get("offline_medium") or {}).get("passed")):
            stamp = rec.get("certified_at") or rec.get("updated_at") or "certified"
            print(
                f"  ✅ deploy-cert [test]: tree-set {state.tree_set_digest[:12]} certified "
                f"({len(state.repos)} repo(s), {stamp}) — skipping duplicate offline medium suite run",
                flush=True,
            )
            return 0
        if bool((stages.get("prepush") or {}).get("passed")):
            rc_rest = runner(
                [
                    sys.executable,
                    str(estate_root / "scripts" / "run_suites.py"),
                    "--tier",
                    "offline",
                    "--level",
                    "medium",
                    "--skip-prepush",
                ],
                estate_root,
                None,
            )
            if rc_rest == 0:
                post = inspect_tree_set(estate_root)
                if post.is_clean and post.tree_set_digest == state.tree_set_digest:
                    update_cert_stage(post, stage="offline_medium_rest", source="deploy-gates", env=environ)
            return rc_rest

    rc = runner(
        [sys.executable, str(estate_root / "scripts" / "run_suites.py"), "--tier", "offline", "--level", level],
        estate_root,
        None,
    )
    if rc == 0 and level in ("medium", "full"):
        post = inspect_tree_set(estate_root)
        if post.is_clean and post.tree_set_digest == state.tree_set_digest:
            update_cert_stage(post, stage="offline_medium", source=f"test-{level}", env=environ)
    return rc


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1], help="Estate root path")
    sub = ap.add_subparsers(dest="subcmd", required=True)

    p_cert = sub.add_parser("certify", help="Certify clean 10-repo tree-set (guardrails + offline/medium)")
    p_cert.add_argument("--canonical-root", type=Path, default=None, help="Canonical root for node_modules linking")
    p_cert.add_argument("--reset", action="store_true", help="Ignore existing cache and re-certify from scratch")
    p_cert.add_argument("--source", default="certify", help="Provenance label recorded in certificate")
    p_cert.add_argument("--json", action="store_true", help="Print JSON summary")

    p_stat = sub.add_parser("status", help="Inspect current tree-set digest and certification status")
    p_stat.add_argument("--json", action="store_true", help="Print JSON status")

    sub.add_parser("preflight", help="Run _deploy-preflight ratchets or skip on verified tree-set HIT")
    sub.add_parser("guardrails", help="Run check-guardrails (cached inside deploy context, uncached standalone)")

    p_test = sub.add_parser("test", help="Run offline suites (cached inside deploy context, uncached standalone)")
    p_test.add_argument("--level", default="medium", choices=["critical", "medium", "full"])

    return ap


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root.resolve()

    if args.subcmd == "status":
        state = inspect_tree_set(root)
        rec = load_cert_record(state) if state.is_clean else {}
        certified = bool(rec.get("certified"))
        payload: dict[str, Any] = {
            "state": asdict(state),
            "is_clean": state.is_clean,
            "certified": certified,
            "record": rec or None,
        }
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            clean_str = "clean" if state.is_clean else f"DIRTY ({', '.join(state.dirty_repos)})"
            verdict = f"CERTIFIED ({rec.get('certified_at')})" if certified else "UNCERTIFIED"
            print(
                f"deploy-cert: {verdict} · digest={state.tree_set_digest[:12]} · "
                f"repos={len(state.repos)} · tree={clean_str}"
            )
        return 0

    if args.subcmd == "certify":
        rc, summary = cmd_certify(
            root,
            canonical_root=args.canonical_root,
            force_reset=bool(args.reset),
            source=str(args.source),
        )
        if args.json:
            print(json.dumps(summary, indent=2, sort_keys=True))
        elif rc != 0:
            print(f"❌ deploy-cert certify failed: {summary}", file=sys.stderr)
        return rc

    if args.subcmd == "preflight":
        return cmd_preflight(root)

    if args.subcmd == "guardrails":
        return cmd_guardrails(root)

    if args.subcmd == "test":
        return cmd_test(root, level=str(args.level))

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
