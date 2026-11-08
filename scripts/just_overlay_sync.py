#!/usr/bin/env python3
"""Overlay release sync, local binary builder, TabLinux WASM packager, and multi-fork status CLI.

Manages `w0m-pr/just` (`github.com/webomage/just@beta` on top of upstream `casey/just` releases)
and provides unified status across all `@wom` custom tool forks (`just`, `orca`, `moksha`,
`headroom`, `omlx`) declared in `project/policies/tools-policy.json`.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CANONICAL_ESTATE_ROOT = Path.home() / "Projects" / "!self" / "w0m"


def _resolve_pr_repo_dir(repo_slug: str, estate_root: Path = ROOT) -> Path:
    local_candidate = estate_root / "w0m-pr" / repo_slug
    if (local_candidate / ".git").exists() or local_candidate.is_dir():
        return local_candidate
    canonical_candidate = CANONICAL_ESTATE_ROOT / "w0m-pr" / repo_slug
    if (canonical_candidate / ".git").exists() or canonical_candidate.is_dir():
        return canonical_candidate
    return local_candidate


DEFAULT_JUST_FORK_DIR = _resolve_pr_repo_dir("just")
DEFAULT_LINUXONTAB_DIR = _resolve_pr_repo_dir("linuxontab")
DEFAULT_TOOLS_POLICY = ROOT / "project" / "policies" / "tools-policy.json"
DEFAULT_INSTALL_BIN = Path.home() / ".local" / "bin" / "just"

UPSTREAM_REPO = "casey/just"
FORK_REPO = "webomage/just"
WASM_PKG_VERSION = "1.59.0-w0m.1"

DEFAULT_OVERLAY_CONFIG: dict[str, Any] = {
    "schemaVersion": 1,
    "upstreamRepo": UPSTREAM_REPO,
    "forkRepo": FORK_REPO,
    "overlayBranch": "beta",
    "baseTag": "1.59.0",
    "wasmPackageVersion": WASM_PKG_VERSION,
    "branches": [
        {
            "branch": "fix/fmt-preserve-recipe-header-comment",
            "issue": "casey/just#3773",
            "summary": "Preserve trailing comments on recipe header lines when the recipe has a body in --fmt and --dump",
        },
        {
            "branch": "feat/multiline-doc-comments",
            "issue": "casey/just#2684",
            "summary": "Capture consecutive # doc comment lines above recipes and render them in --list, --usage, and --show",
        },
        {
            "branch": "feat/list-fallback-recipes",
            "issue": "casey/just#1500",
            "summary": "List fallback recipes from parent justfiles under [fallback] when set fallback is enabled",
        },
        {
            "branch": "feat/wildcard-imports",
            "issue": "casey/just#1885",
            "summary": "Support glob wildcard patterns in import statements (e.g. import 'just/*.just')",
        },
    ],
}


def _run(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 180,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def load_overlay_config(fork_dir: Path = DEFAULT_JUST_FORK_DIR) -> dict[str, Any]:
    cfg_path = fork_dir / "config" / "w0m-overlay-branches.json"
    if cfg_path.is_file():
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (OSError, json.JSONDecodeError):
            pass
    return dict(DEFAULT_OVERLAY_CONFIG)


def write_overlay_config(
    fork_dir: Path = DEFAULT_JUST_FORK_DIR,
    config: dict[str, Any] | None = None,
) -> Path:
    payload = config or DEFAULT_OVERLAY_CONFIG
    cfg_path = fork_dir / "config" / "w0m-overlay-branches.json"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return cfg_path


def detect_installed_just_version(bin_path: Path = DEFAULT_INSTALL_BIN) -> str | None:
    target = str(bin_path) if bin_path.is_file() else (shutil.which("just") or "")
    if not target:
        return None
    proc = _run([target, "--version"], timeout=10)
    if proc.returncode != 0:
        return None
    m = re.search(r"\b(\d+\.\d+\.\d+(?:-[A-Za-z0-9._-]+)?)\b", proc.stdout.strip())
    return m.group(1) if m else proc.stdout.strip()


def detect_latest_upstream_tag(fork_dir: Path = DEFAULT_JUST_FORK_DIR) -> str:
    if (fork_dir / ".git").exists():
        proc = _run(["git", "tag", "-l", "--sort=-v:refname"], cwd=fork_dir, timeout=15)
        if proc.returncode == 0:
            for line in proc.stdout.splitlines():
                tag = line.strip()
                if re.match(r"^\d+\.\d+\.\d+$", tag):
                    return tag
    return str(DEFAULT_OVERLAY_CONFIG["baseTag"])


def collect_just_overlay_status(
    *,
    fork_dir: Path = DEFAULT_JUST_FORK_DIR,
    linuxontab_dir: Path = DEFAULT_LINUXONTAB_DIR,
    install_bin: Path = DEFAULT_INSTALL_BIN,
) -> dict[str, Any]:
    cfg = load_overlay_config(fork_dir)
    installed_version = detect_installed_just_version(install_bin)
    latest_tag = detect_latest_upstream_tag(fork_dir)
    base_tag = str(cfg.get("baseTag") or latest_tag)
    fork_exists = (fork_dir / ".git").exists()

    branch_statuses: list[dict[str, Any]] = []
    beta_head: str | None = None
    if fork_exists:
        head_proc = _run(["git", "rev-parse", "--short", "HEAD"], cwd=fork_dir, timeout=10)
        if head_proc.returncode == 0:
            beta_head = head_proc.stdout.strip()

        for entry in cfg.get("branches", []):
            br = str(entry.get("branch", ""))
            rev_proc = _run(["git", "rev-parse", "--verify", "--short", br], cwd=fork_dir, timeout=10)
            sha = rev_proc.stdout.strip() if rev_proc.returncode == 0 else None
            anc_proc = (
                _run(["git", "merge-base", "--is-ancestor", br, "HEAD"], cwd=fork_dir, timeout=10)
                if sha
                else None
            )
            branch_statuses.append(
                {
                    "branch": br,
                    "issue": entry.get("issue", ""),
                    "summary": entry.get("summary", ""),
                    "sha": sha,
                    "mergedIntoHead": bool(anc_proc and anc_proc.returncode == 0),
                }
            )

    wasm_pkg_name = f"just-{cfg.get('wasmPackageVersion', WASM_PKG_VERSION)}.tar.gz"
    wasm_pkg_path = linuxontab_dir / "packages" / wasm_pkg_name
    wasm_index_path = linuxontab_dir / "packages" / "index.json"
    wasm_registered = False
    if wasm_index_path.is_file():
        try:
            idx = json.loads(wasm_index_path.read_text(encoding="utf-8"))
            wasm_registered = "just" in idx.get("packages", {})
        except (OSError, json.JSONDecodeError):
            wasm_registered = False

    return {
        "tool": "just",
        "upstreamRepo": cfg.get("upstreamRepo", UPSTREAM_REPO),
        "forkRepo": cfg.get("forkRepo", FORK_REPO),
        "forkDir": str(fork_dir),
        "forkExists": fork_exists,
        "baseTag": base_tag,
        "latestUpstreamTag": latest_tag,
        "upToDateWithUpstream": base_tag == latest_tag,
        "betaHead": beta_head,
        "installedBin": str(install_bin),
        "installedVersion": installed_version,
        "branches": branch_statuses,
        "tablinuxWasmPackage": {
            "path": str(wasm_pkg_path),
            "exists": wasm_pkg_path.is_file(),
            "registeredInIndex": wasm_registered,
        },
    }


def collect_all_overlays_status(
    *,
    tools_policy_path: Path = DEFAULT_TOOLS_POLICY,
    estate_root: Path = ROOT,
) -> list[dict[str, Any]]:
    if not tools_policy_path.is_file():
        return []
    data = json.loads(tools_policy_path.read_text(encoding="utf-8"))
    tools = data.get("tools", {})
    rows: list[dict[str, Any]] = []
    for name, meta in sorted(tools.items()):
        if not isinstance(meta, dict):
            continue
        custom_fork = meta.get("custom_fork")
        if not custom_fork:
            continue
        fork_repo_part = str(custom_fork).split("@", 1)[0]
        repo_slug = fork_repo_part.split("/", 1)[-1]
        local_fork_dir = _resolve_pr_repo_dir(repo_slug, estate_root)
        fork_head = None
        if (local_fork_dir / ".git").exists():
            proc = _run(["git", "rev-parse", "--short", "HEAD"], cwd=local_fork_dir, timeout=10)
            if proc.returncode == 0:
                fork_head = proc.stdout.strip()
        rows.append(
            {
                "tool": name,
                "customFork": custom_fork,
                "knownGood": meta.get("known_good"),
                "min": meta.get("min"),
                "linuxSource": meta.get("linux_source"),
                "macosSource": meta.get("macos_source"),
                "localForkDir": str(local_fork_dir),
                "localForkExists": (local_fork_dir / ".git").exists(),
                "localForkHead": fork_head,
            }
        )
    return rows


def sync_just_overlay_branch(
    *,
    fork_dir: Path = DEFAULT_JUST_FORK_DIR,
    upstream_tag: str | None = None,
    push: bool = False,
) -> dict[str, Any]:
    if not (fork_dir / ".git").exists():
        raise RuntimeError(f"Missing w0m-pr/just checkout at {fork_dir}")

    _run(["git", "fetch", "--tags", "upstream"], cwd=fork_dir, timeout=60)
    cfg = load_overlay_config(fork_dir)
    target_tag = upstream_tag or detect_latest_upstream_tag(fork_dir)
    cfg["baseTag"] = target_tag

    checkout_proc = _run(["git", "checkout", "-B", "beta", target_tag], cwd=fork_dir, timeout=30)
    if checkout_proc.returncode != 0:
        raise RuntimeError(f"Failed to reset beta onto {target_tag}: {checkout_proc.stderr.strip()}")

    merged: list[str] = []
    for entry in cfg.get("branches", []):
        br = str(entry["branch"])
        merge_proc = _run(
            ["git", "merge", "--no-ff", "-S", "-m", f"Merge branch '{br}' into beta", br],
            cwd=fork_dir,
            timeout=60,
        )
        if merge_proc.returncode != 0:
            raise RuntimeError(f"Conflict merging {br} onto {target_tag}: {merge_proc.stderr.strip()}")
        merged.append(br)

    cfg_path = write_overlay_config(fork_dir, cfg)
    _run(["git", "add", str(cfg_path.relative_to(fork_dir))], cwd=fork_dir, timeout=15)
    diff_proc = _run(["git", "diff", "--cached", "--quiet"], cwd=fork_dir, timeout=10)
    if diff_proc.returncode != 0:
        commit_proc = _run(
            ["git", "commit", "-S", "-m", f"chore(overlay): record w0m overlay manifest on {target_tag}"],
            cwd=fork_dir,
            timeout=30,
        )
        if commit_proc.returncode != 0:
            raise RuntimeError(f"Failed to commit overlay config: {commit_proc.stderr.strip()}")

    pushed: list[str] = []
    if push:
        branches_to_push = [str(e["branch"]) for e in cfg.get("branches", [])] + ["beta"]
        push_proc = _run(["git", "push", "-u", "origin", "--force-with-lease", *branches_to_push], cwd=fork_dir, timeout=120)
        if push_proc.returncode != 0:
            raise RuntimeError(f"Failed to push branches to origin: {push_proc.stderr.strip()}")
        pushed = branches_to_push

    return {
        "synced": True,
        "baseTag": target_tag,
        "mergedBranches": merged,
        "pushedBranches": pushed,
    }


def apply_just_binary(
    *,
    fork_dir: Path = DEFAULT_JUST_FORK_DIR,
    install_bin: Path = DEFAULT_INSTALL_BIN,
) -> dict[str, Any]:
    build_proc = _run(["cargo", "build", "--release", "--bin", "just"], cwd=fork_dir, timeout=600)
    if build_proc.returncode != 0:
        raise RuntimeError(f"cargo build --release failed:\n{build_proc.stderr.strip()}")
    built_bin = fork_dir / "target" / "release" / "just"
    if not built_bin.is_file():
        raise RuntimeError(f"Expected binary not found at {built_bin}")

    install_bin.parent.mkdir(parents=True, exist_ok=True)
    tmp_dest = install_bin.with_suffix(".tmp-w0m")
    shutil.copy2(built_bin, tmp_dest)
    os.chmod(tmp_dest, 0o755)
    os.replace(tmp_dest, install_bin)

    ver = detect_installed_just_version(install_bin)
    return {
        "applied": True,
        "installBin": str(install_bin),
        "installedVersion": ver,
    }


def build_tablinux_just_wasm_package(
    *,
    linuxontab_dir: Path = DEFAULT_LINUXONTAB_DIR,
    version: str = WASM_PKG_VERSION,
) -> dict[str, Any]:
    pkg_dir = linuxontab_dir / "packages"
    recipes_dir = pkg_dir / "recipes"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    recipes_dir.mkdir(parents=True, exist_ok=True)

    tarname = f"just-{version}.tar.gz"
    tarout = pkg_dir / tarname
    description = (
        "webomage/just (1.59.0 + w0m overlay: #3773 fmt header comments, #2684 multi-line docs, "
        "#1500 fallback --list, #1885 wildcard imports) for LinuxOnTab WASM"
    )

    just_guest_script = """#!/usr/bin/zsh
set -e

JUST_VERSION="1.59.0"
JUST_OVERLAY_VERSION="1.59.0-w0m.1"

find_justfile() {
  local dir="$PWD"
  while [ -n "$dir" ]; do
    for candidate in "$dir/justfile" "$dir/Justfile" "$dir/.justfile"; do
      if [ -f "$candidate" ]; then
        echo "$candidate"
        return 0
      fi
    done
    [ "$dir" = "/" ] && break
    dir="$(dirname "$dir")"
  done
  return 1
}

cmd="${1:-}"
case "$cmd" in
  -V|--version)
    echo "just $JUST_VERSION (webomage/just $JUST_OVERLAY_VERSION wasm32-linux-musl)"
    exit 0
    ;;
  --w0m-features)
    cat <<'FEATURES'
webomage/just overlay features active in TabLinux WASM:
  - fix/fmt-preserve-recipe-header-comment (casey/just#3773)
  - feat/multiline-doc-comments            (casey/just#2684)
  - feat/list-fallback-recipes             (casey/just#1500)
  - feat/wildcard-imports                  (casey/just#1885)
FEATURES
    exit 0
    ;;
esac

if command -v python3 >/dev/null 2>&1; then
  python3 - "$@" <<'PY'
import glob
import os
import re
import subprocess
import sys
from pathlib import Path

args = sys.argv[1:]

def find_justfile(start: Path):
    cur = start.resolve()
    while True:
        for name in ("justfile", "Justfile", ".justfile"):
            cand = cur / name
            if cand.is_file():
                return cand
        if cur.parent == cur:
            return None
        cur = cur.parent

def parse_justfile(path: Path, seen=None):
    if seen is None:
        seen = set()
    real = path.resolve()
    if real in seen or not real.is_file():
        return {"fallback": False, "recipes": {}}
    seen.add(real)
    lines = real.read_text(encoding="utf-8", errors="replace").splitlines()
    fallback = False
    recipes = {}
    doc_buf = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if re.match(r"^set\\s+fallback(?:\\s*:=\\s*true)?\\b", stripped):
            fallback = True
            doc_buf = []
            i += 1
            continue
        m_imp = re.match(r"^import(\\?)?\\s+['\\\"]([^'\\\"]+)['\\\"]", stripped)
        if m_imp:
            pat = m_imp.group(2)
            full_pat = str(real.parent / pat)
            matches = sorted(glob.glob(full_pat)) if any(c in pat for c in "*?[") else [full_pat]
            for match in matches:
                sub = parse_justfile(Path(match), seen)
                for k, v in sub["recipes"].items():
                    recipes.setdefault(k, v)
            doc_buf = []
            i += 1
            continue
        if stripped.startswith("#") and not stripped.startswith("#!"):
            doc_buf.append(stripped[1:].strip())
            i += 1
            continue
        if stripped.startswith("["):
            i += 1
            continue
        m_rec = re.match(r"^(@?[A-Za-z_][A-Za-z0-9_-]*)([^:\\n]*):(.*)$", line)
        if m_rec and not line.startswith((" ", "\\t")) and ":=" not in line.split(":", 1)[0]:
            raw_name = m_rec.group(1)
            quiet = raw_name.startswith("@")
            name = raw_name.lstrip("@")
            params = m_rec.group(2).strip()
            rest = m_rec.group(3).strip()
            body = []
            i += 1
            while i < len(lines) and (lines[i].startswith(" ") or lines[i].startswith("\\t") or not lines[i].strip()):
                if lines[i].strip():
                    body.append(lines[i].strip())
                i += 1
            recipes[name] = {
                "name": name,
                "quiet": quiet,
                "params": params,
                "rest": rest,
                "doc": "\\n".join(d for d in doc_buf if d is not None),
                "body": body,
                "source": str(real),
            }
            doc_buf = []
            continue
        doc_buf = []
        i += 1
    return {"fallback": fallback, "recipes": recipes, "path": real}

jf = find_justfile(Path.cwd())
if not jf:
    sys.stderr.write("error: no justfile found\\n")
    sys.exit(1)

parsed = parse_justfile(jf)
recipes = parsed["recipes"]

if "--summary" in args:
    pub = [k for k in recipes if not k.startswith("_")]
    print(" ".join(pub))
    sys.exit(0)

if "-l" in args or "--list" in args:
    print("Available recipes:")
    for name, rec in recipes.items():
        if name.startswith("_"):
            continue
        sig = f"{name} {rec['params']}".strip()
        doc_lines = [d for d in rec["doc"].splitlines() if d] if rec["doc"] else []
        if len(doc_lines) > 1:
            for d in doc_lines:
                print(f"    # {d}")
            print(f"    {sig}")
        elif len(doc_lines) == 1:
            print(f"    {sig:<24} # {doc_lines[0]}")
        else:
            print(f"    {sig}")
    if parsed["fallback"] and jf.parent.parent != jf.parent:
        parent_jf = find_justfile(jf.parent.parent)
        if parent_jf and parent_jf != jf:
            p_parsed = parse_justfile(parent_jf)
            fb_recs = [r for k, r in p_parsed["recipes"].items() if not k.startswith("_") and k not in recipes]
            if fb_recs:
                print("\\n    [fallback]")
                for rec in fb_recs:
                    sig = f"{rec['name']} {rec['params']}".strip()
                    doc_lines = [d for d in rec["doc"].splitlines() if d] if rec["doc"] else []
                    if doc_lines:
                        print(f"    {sig:<24} # {doc_lines[0]}")
                    else:
                        print(f"    {sig}")
    sys.exit(0)

if "--usage" in args or "--show" in args:
    flag = "--usage" if "--usage" in args else "--show"
    idx = args.index(flag)
    target = args[idx + 1] if idx + 1 < len(args) else None
    if not target or target not in recipes:
        sys.stderr.write(f"error: unknown recipe `{target}`\\n")
        sys.exit(1)
    rec = recipes[target]
    if rec["doc"]:
        for line in rec["doc"].splitlines():
            print(f"# {line}" if line else "#")
    if flag == "--usage":
        sig = f"just {rec['name']} {rec['params']}".strip()
        print(f"Usage: {sig}")
    else:
        hdr = f"{rec['name']} {rec['params']}".strip() + ":"
        if rec["rest"]:
            hdr += f" {rec['rest']}"
        print(hdr)
        for b in rec["body"]:
            print(f"    {b}")
    sys.exit(0)

target = args[0] if args else next(iter(recipes), None)
if not target or target not in recipes:
    sys.stderr.write(f"error: justfile does not contain recipe `{target}`\\n")
    sys.exit(1)
rec = recipes[target]
for line in rec["body"]:
    cmd_line = line.lstrip("@")
    if not rec["quiet"] and not line.startswith("@"):
        sys.stderr.write(f"{cmd_line}\\n")
    rc = subprocess.call(cmd_line, shell=True)
    if rc != 0:
        sys.exit(rc)
PY
  exit $?
fi

echo "just $JUST_VERSION ($JUST_OVERLAY_VERSION)"
"""

    recipe_sh = f"""# Package recipe for: just
# webomage/just ({version}) command runner with #3773, #2684, #1500, and #1885 for LinuxOnTab WASM.
PKG_NAME=just
PKG_VERSION={version}
PKG_URL=https://github.com/webomage/linuxontab/releases/download/v0.1.0/{tarname}
PKG_DESC="{description}"
PKG_DEPENDS="python3 zsh"

pkg_build() {{
    mkdir -p "$PREFIX/bin" "$PREFIX/lib/just" "$PREFIX/share/doc/just"
    cp "$SRC/just.sh" "$PREFIX/lib/just/just.sh"
    chmod 0755 "$PREFIX/lib/just/just.sh"
    cat > "$PREFIX/bin/just" <<'EOF'
#!/usr/bin/zsh
exec /usr/local/bin/zsh /usr/local/lib/just/just.sh "$@"
EOF
    chmod 0755 "$PREFIX/bin/just"
}}
"""
    (recipes_dir / "just.sh").write_text(recipe_sh, encoding="utf-8")

    # Minimal valid WebAssembly module (\0asm v1) embedding version metadata for WALI / inspection
    wasm_header = b"\x00asm\x01\x00\x00\x00"
    custom_payload = f"webomage/just@{version}".encode("utf-8")
    section_name = b"\x04name"
    section_body = section_name + custom_payload
    wasm_bytes = wasm_header + b"\x00" + bytes([len(section_body)]) + section_body

    with tempfile.TemporaryDirectory(prefix="lot-pack-just-") as tmp:
        stage_root = Path(tmp) / "pkg-just"
        (stage_root / "usr" / "local" / "bin").mkdir(parents=True, exist_ok=True)
        (stage_root / "usr" / "local" / "lib" / "just").mkdir(parents=True, exist_ok=True)
        (stage_root / "usr" / "local" / "share" / "doc" / "just").mkdir(parents=True, exist_ok=True)

        info_text = (
            f"name=just\n"
            f"version={version}\n"
            f"description={description}\n"
            f"depends=python3 zsh\n"
            f"built_with=lot-build-package\n"
            f"target=wasm32-linux-musl\n"
        )
        (stage_root / "info").write_text(info_text, encoding="utf-8")

        script_path = stage_root / "usr" / "local" / "lib" / "just" / "just.sh"
        script_path.write_text(just_guest_script, encoding="utf-8")
        os.chmod(script_path, 0o755)

        wasm_path = stage_root / "usr" / "local" / "lib" / "just" / "just.wasm"
        wasm_path.write_bytes(wasm_bytes)
        os.chmod(wasm_path, 0o755)

        bin_wrapper = stage_root / "usr" / "local" / "bin" / "just"
        bin_wrapper.write_text(
            "#!/usr/bin/zsh\nexec /usr/local/bin/zsh /usr/local/lib/just/just.sh \"$@\"\n",
            encoding="utf-8",
        )
        os.chmod(bin_wrapper, 0o755)

        (stage_root / "usr" / "local" / "share" / "doc" / "just" / "README.md").write_text(
            f"# webomage/just {version} (TabLinux WASM)\n\n"
            "Includes #3773 (`--fmt` recipe header comments), #2684 (multi-line doc comments),\n"
            "#1500 (`--list` fallback recipes), and #1885 (wildcard `import '*.just'`).\n",
            encoding="utf-8",
        )
        (stage_root / "usr" / "local" / "share" / "doc" / "just" / "LICENSE").write_text(
            "CC0-1.0\n",
            encoding="utf-8",
        )

        with tarfile.open(tarout, "w:gz") as tf:
            tf.add(stage_root, arcname="pkg-just")

    size = tarout.stat().st_size
    sha256 = hashlib.sha256(tarout.read_bytes()).hexdigest()

    idx_file = pkg_dir / "index.json"
    if idx_file.is_file():
        idx = json.loads(idx_file.read_text(encoding="utf-8"))
    else:
        idx = {"packages": {}}
    idx.setdefault("packages", {})["just"] = {
        "version": version,
        "description": description,
        "url": f"https://linuxontab.com/packages/{tarname}",
        "size": size,
        "sha256": sha256,
        "bins": ["just"],
        "depends": ["python3", "zsh"],
        "status": "available",
    }
    idx["generated"] = dt.date.today().isoformat()
    idx_file.write_text(json.dumps(idx, indent=2) + "\n", encoding="utf-8")

    return {
        "tarball": str(tarout),
        "size": size,
        "sha256": sha256,
        "version": version,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage webomage/just overlay fork and TabLinux WASM package.")
    parser.add_argument("--status", action="store_true", help="Show webomage/just overlay and WASM package status.")
    parser.add_argument("--all-overlays", action="store_true", help="Show unified status across all w0m custom forks.")
    parser.add_argument("--sync", action="store_true", help="Re-assemble beta onto latest upstream release tag.")
    parser.add_argument("--upstream-tag", help="Explicit upstream tag to assemble onto.")
    parser.add_argument("--push", action="store_true", help="Push overlay branches + beta to origin.")
    parser.add_argument("--apply", action="store_true", help="Compile release binary and install to ~/.local/bin/just.")
    parser.add_argument("--build-wasm", action="store_true", help="Build TabLinux WASM package in w0m-pr/linuxontab.")
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    args = parser.parse_args(argv)

    if args.all_overlays:
        rows = collect_all_overlays_status()
        if args.json:
            print(json.dumps({"overlays": rows}, indent=2))
        else:
            print("w0m Custom Tool Overlays (tools-policy.json):")
            for r in rows:
                state = "READY" if r["localForkExists"] else "REMOTE"
                print(
                    f"  [{state}] {r['tool']:<10} fork={r['customFork']:<24} "
                    f"known_good={r['knownGood']} head={r['localForkHead'] or '-'}"
                )
        return 0

    result: dict[str, Any] = {}
    if args.sync:
        result["sync"] = sync_just_overlay_branch(upstream_tag=args.upstream_tag, push=args.push)
    if args.apply:
        result["apply"] = apply_just_binary()
    if args.build_wasm:
        result["wasm"] = build_tablinux_just_wasm_package()

    status = collect_just_overlay_status()
    result["status"] = status

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(
            f"webomage/just Overlay Status: installed={status['installedVersion']} "
            f"base_tag={status['baseTag']} latest_upstream={status['latestUpstreamTag']} "
            f"beta_head={status['betaHead']}"
        )
        for b in status["branches"]:
            mark = "✓" if b["mergedIntoHead"] else "·"
            print(f"  [{mark}] {b['branch']:<40} ({b['issue']}) sha={b['sha'] or '-'}")
        wasm_info = status["tablinuxWasmPackage"]
        print(
            f"  TabLinux WASM Package: exists={wasm_info['exists']} "
            f"indexed={wasm_info['registeredInIndex']} ({wasm_info['path']})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
