#!/usr/bin/env python3
"""Where does a NAME live? — the inventory to run BEFORE and AFTER renaming a repo, worker, service or env var.

    just name-refs wom7func                 # inventory by surface class, across every estate repo
    just name-refs wom7func --files         # also list every hit line (default: counts + first 3 per class)
    just name-refs wom7func --outside       # also scan machine-level places outside the repos (paths only, never lines)
    just name-refs wom7cfworkers --gate     # exit 1 if any LIVE reference remains (history is allowed to keep the old name)

Why: renaming wom7cfworkers -> wom7func was declared "complete" while a live default host in a health check, three
dangling `../wom7cfworkers/CLAUDE.md` pointers, the architecture docs and a deploy step still named it (measured
2026-09-29: 283 hits in 6 repos, ~20 of them live). A grep of one file type finds one surface; a name lives in ELEVEN,
and only some of them are text you can grep.

Surface classes (what each demands):
  code        source that runs                                   -> change with the rename, tests prove it
  env-default a fallback VALUE inside an env read                -> `os.environ.get("X", "https://old-name...")` is a
                                                                    hard-coded copy of the name; it survives a secret update
  config      json/toml/yaml/justfile/hooks/wrangler/ignore files -> change with the rename
  spec        openspec (live) and Gauge/`.spec` files            -> change with the rename
  docs        current-state prose and diagrams                   -> change with the rename
  note        a line that SAYS it is history ("was named X until   -> MAY keep; counted and shown so the heuristic cannot
              2026-08", "formerly", "renamed from", "decommissioned")   silently mask a live reference
  record      tickets, LESSONS, STATE, ADRs                      -> MAY keep the old name (they describe the past); do not rewrite
  history     migrations, archived specs, archived tickets       -> IMMUTABLE; never rewrite
  generated   graphify-out, DECISIONS.md, TASKS.md, CHANGELOG    -> regenerate, never hand-edit
  path        a file or directory whose NAME contains it          -> `git mv`
  symlink     a tracked symlink whose TARGET contains it         -> re-point
  remote      a git remote URL that contains it                  -> the GitHub repo name
Not greppable (printed as a checklist, `--outside` scans the local ones): the deployed worker/script name and its
workers.dev host, secrets whose VALUE is a URL of the renamed thing (names of candidates are listed from the code that
reads them), the Infisical project path, GitHub repo settings, launchd plists, editor/MCP configs, shell rc files.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

# The classes a rename must fix (a hit here fails --gate) vs the ones allowed to keep history.
LIVE = ("code", "env-default", "config", "spec", "docs", "path", "symlink", "remote")
KEEP = ("note", "record", "history")
REGENERATE = ("generated",)
ORDER = LIVE + REGENERATE + KEEP

CODE_EXT = {".ts", ".tsx", ".js", ".mjs", ".cjs", ".py", ".svelte", ".astro", ".rs", ".go", ".sh", ".swift", ".sql"}
CONFIG_EXT = {".json", ".jsonc", ".toml", ".yaml", ".yml", ".cfg", ".ini", ".plist", ".code-workspace"}
CONFIG_NAMES = {"justfile", ".gitignore", ".graphifyignore", ".pre-commit-config.yaml", ".gitattributes", "dockerfile"}
DOC_EXT = {".md", ".mmd", ".html", ".txt", ".rst"}

# An env READ with a fallback: the fallback is a hard-coded copy of whatever it names.
ENV_READ = re.compile(
    r"(environ\.get\(|os\.getenv\(|process\.env\.|Deno\.env\.get\(|import\.meta\.env\.|\benv\.[A-Z_]{3,}\b|getenv\()"
)
ENV_NAME = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b")
URLISH = re.compile(r"(_URL|_HOST|_ENDPOINT|_DOMAIN|_ORIGIN|_BASE_URL|WEBHOOK_URL)$")
# A line that states it is talking about the past. Deliberately narrow, and its count is always printed.
HISTORICAL = re.compile(
    r"(formerly|was named|were named|renamed (?:from|to)|until \d{4}-\d{2}|since \d{4}-\d{2}-\d{2}|then named|"
    r"decommission|superseded|retired|no longer exist|used to be|migrated from|stale|dir no longer)", re.I)


def classify(path: str, line: str, name: str) -> str:
    """Pure: which surface class does this hit belong to? `path` is repo-relative, '/'-separated."""
    p = path.lower()
    base = p.rsplit("/", 1)[-1]
    ext = "." + base.rsplit(".", 1)[-1] if "." in base else ""

    # History first: immutable by construction, even when the file type looks live.
    if ("/migrations/" in "/" + p or "/archive/" in "/" + p or p.startswith(".tasks/archive/")
            or "/state-archive/" in "/" + p or "/baseline/" in "/" + p or p.endswith("supabase/schema.sql")):
        return "history"
    if (p.startswith("graphify-out/") or "/graphify-out/" in p or base in ("decisions.md", "tasks.md", "changelog.md",
                                                                          "status-dashboard.html", "tickets.json",
                                                                          "skills.lock.json", "pnpm-lock.yaml",
                                                                          "package-lock.json", "deno.lock")):
        return "generated"
    if (p.startswith(".tasks/") or base in ("lessons.md", "state.md", "push_log.md") or "/decisions/agdr-" in "/" + p
            or p.startswith("docs/sessions/") or "/reports/" in "/" + p or "/audit_and_research/" in p
            or re.match(r".*(audit|report)[^/]*\.md$", p)):
        return "record"
    if p.startswith("openspec/") or "/openspec/" in p or "/specs/" in "/" + p or ext in (".spec", ".feature"):
        return "spec"
    if ENV_READ.search(line) and re.search(r"([\"'`])[^\"'`\n]*" + re.escape(name) + r"[^\"'`\n]*\1", line, re.I):
        return "env-default"
    if line and HISTORICAL.search(line):
        return "note"
    if base in CONFIG_NAMES or ext in CONFIG_EXT or p.startswith(".husky/") or base.startswith("wrangler."):
        return "config"
    if ext in CODE_EXT:
        return "code"
    if ext in DOC_EXT or base in ("readme", "license"):
        return "docs"
    return "docs"


def sh(cmd: list[str], cwd: Path) -> str:
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env={**os.environ, "LC_ALL": "C"})
    return r.stdout


def discover_repos(root: Path) -> list[Path]:
    """The root repo plus every direct child that is its own git repo (wom7mlx nests one level deeper)."""
    repos = [root] if (root / ".git").exists() else []
    for d in sorted(root.iterdir()):
        if d.is_dir() and not d.name.startswith((".", "_")) and d.name != "node_modules":
            if (d / ".git").exists():
                repos.append(d)
            elif d.name == "wom7mlx" and (d / "wom7mlx" / ".git").exists():
                repos.append(d / "wom7mlx")
    return repos


def scan_repo(repo: Path, name: str, root: Path) -> list[dict]:
    label = "." if repo == root else str(repo.relative_to(root))
    hits: list[dict] = []
    out = sh(["git", "--no-pager", "grep", "-n", "-I", "-i", "-F", "-e", name], repo)
    for raw in out.splitlines():
        m = re.match(r"^(.*?):(\d+):(.*)$", raw)
        if not m:
            continue
        path, ln, text = m.group(1), int(m.group(2)), m.group(3)
        hits.append({"repo": label, "path": path, "line": ln, "text": text.strip()[:200],
                     "class": classify(path, text, name)})
    for path in sh(["git", "ls-files"], repo).splitlines():
        if name.lower() in path.lower():
            c = classify(path, "", name)
            hits.append({"repo": label, "path": path, "line": 0, "text": "(file name)",
                         "class": c if c in ("history", "record", "generated") else "path"})
    for entry in sh(["git", "ls-files", "-s"], repo).splitlines():
        meta, _, path = entry.partition("\t")
        if meta.startswith("120000"):
            target = sh(["git", "cat-file", "-p", meta.split()[1]], repo).strip()
            if name.lower() in target.lower():
                hits.append({"repo": label, "path": path, "line": 0, "text": f"-> {target}", "class": "symlink"})
    for remote in sh(["git", "remote", "-v"], repo).splitlines():
        if name.lower() in remote.lower():
            hits.append({"repo": label, "path": "(git remote)", "line": 0, "text": remote.strip(), "class": "remote"})
    # A tracked directory at the root of the estate named like it (the repo folder itself).
    if repo == root and (root / name).is_dir():
        hits.append({"repo": label, "path": name + "/", "line": 0, "text": "(estate directory)", "class": "path"})
    return hits


def env_candidates(hits: list[dict], root: Path) -> list[str]:
    """Env var NAMES read in files that mention the name and that look URL/host-shaped: their live VALUE may embed it."""
    found: set[str] = set()
    seen_files: set[tuple[str, str]] = set()
    for h in hits:
        if h["class"] not in LIVE and h["class"] != "env-default":
            continue
        key = (h["repo"], h["path"])
        if key in seen_files or h["line"] == 0:
            continue
        seen_files.add(key)
        f = (root / h["repo"] / h["path"]) if h["repo"] != "." else root / h["path"]
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            if ENV_READ.search(line):
                for n in ENV_NAME.findall(line):
                    if URLISH.search(n):
                        found.add(n)
    return sorted(found)


def outside_scan(name: str) -> list[tuple[str, int]]:
    """Machine-level files that mention the name. Paths and counts ONLY: these files can hold secrets."""
    home = Path.home()
    targets = [home / "Library/LaunchAgents", home / ".claude.json", home / ".claude/settings.json",
               home / ".claude/settings.local.json", home / ".zshrc", home / ".zprofile", home / ".bashrc",
               home / ".config", home / ".gemini/config", home / ".codex", home / ".orca"]
    res: list[tuple[str, int]] = []
    pat = re.compile(re.escape(name), re.I)
    for t in targets:
        files = [t] if t.is_file() else (list(t.rglob("*")) if t.is_dir() else [])
        for f in files[:5000]:
            if not f.is_file() or f.stat().st_size > 2_000_000:
                continue
            try:
                n = len(pat.findall(f.read_text(encoding="utf-8", errors="ignore")))
            except OSError:
                continue
            if n:
                res.append((str(f).replace(str(home), "~"), n))
    return res


CHECKLIST = [
    "Cloudflare: the deployed worker/script NAME (wrangler.jsonc `name`), its <name>.<account>.workers.dev host, routes, cron triggers,"
    " Workflows bound to that script, and every secret set on it (write-only: verify behaviourally).",
    "Secrets whose VALUE is a URL of the renamed thing (candidates printed above): Supabase secrets (SHA-256 digests are readable),"
    " Infisical `beta`, Cloudflare. A code rename does not move a secret value.",
    "GitHub: the repo name, the remote URL in every clone/worktree (`git remote -v`), Project #2 links, branch protection.",
    "Infisical: project path/folder names and any env var NAME containing the old name.",
    "Editor/agent configs: *.code-workspace, ~/.claude.json + MCP server args, launchd plists (`--outside` scans these).",
    "Generated files to REGENERATE after the rename: `just decisions`, `just tasks-render`, graphify/codegraph indexes, `just state-save`.",
    "Prove it: `just name-refs <old> --gate` must exit 0 (history/records may keep the old name).",
]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name")
    ap.add_argument("--files", action="store_true", help="list every hit line")
    ap.add_argument("--outside", action="store_true", help="scan machine-level files (paths + counts only)")
    ap.add_argument("--gate", action="store_true", help="exit 1 if any LIVE reference remains")
    ap.add_argument("--root", type=Path)
    a = ap.parse_args(argv)
    if len(a.name) < 4:
        print("❌ name too short to search meaningfully (would match noise).", file=sys.stderr)
        return 2
    root = a.root or Path(__file__).resolve().parents[1]
    repos = discover_repos(root)
    if not repos:
        print(f"❌ no git repos found under {root}", file=sys.stderr)
        return 2
    hits: list[dict] = []
    for r in repos:
        hits += scan_repo(r, a.name, root)

    by: dict[str, list[dict]] = defaultdict(list)
    for h in hits:
        by[h["class"]].append(h)
    print(f"── name-refs {a.name!r} · {len(hits)} hit(s) in {len(repos)} repo(s) ──")
    for cls in ORDER:
        rows = by.get(cls, [])
        tag = "MUST FIX" if cls in LIVE else ("regenerate" if cls in REGENERATE else "may keep")
        print(f"\n[{cls}] {len(rows)}  ({tag})")
        files = defaultdict(int)
        for h in rows:
            files[(h["repo"], h["path"])] += 1
        shown = 0
        for h in rows:
            if a.files or shown < 3:
                where = f"{h['repo']}/{h['path']}" + (f":{h['line']}" if h["line"] else "")
                print(f"    {where}  {h['text'][:110]}")
                shown += 1
        if not a.files and len(rows) > 3:
            print(f"    … {len(rows) - 3} more in {len(files)} file(s); --files lists all")

    cands = env_candidates(hits, root)
    if cands:
        print("\nenv vars read near a hit that look URL/host-shaped (their live VALUE may embed the name):")
        print("    " + ", ".join(cands))
    if a.outside:
        print("\noutside the repos (path : mentions):")
        for path, n in outside_scan(a.name):
            print(f"    {path} : {n}")
    print("\nnot greppable — check by hand:")
    for c in CHECKLIST:
        print(f"  - {c}")

    live = sum(len(by.get(c, [])) for c in LIVE)
    print(f"\n{live} live reference(s) · {sum(len(by.get(c, [])) for c in REGENERATE)} to regenerate · "
          f"{sum(len(by.get(c, [])) for c in KEEP)} allowed to keep")
    if a.gate:
        if live:
            print(f"❌ --gate: {live} live reference(s) to {a.name!r} remain.", file=sys.stderr)
            return 1
        print(f"✅ --gate: no live reference to {a.name!r}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
