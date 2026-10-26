#!/usr/bin/env python3
"""What is in these repos that NO stack claims? — T147 AC3.

Owner ask 2026-07-26: *"on start scan if sdlc match the stack or something from repo not
covered by sdlc"*. The first half already exists; this is the second half.

THE INVERSE OF `just discovery`, AND THAT IS THE WHOLE POINT. `discovery` walks the REGISTRY and
asks whether each declared thing is real (declared-not-used / used-not-declared, `--enforce`
hard-fails a declared command with no recipe). It is green today — 8 stacks, 28/28. But a registry
walk can only ever find things the registry already knows to look at, which is [[T149]]'s organising
finding verbatim: *"a gate reports zero because it only looks where it already knows to look."*
This walks the CODE instead and asks the question no registry walk can: what is here that nobody
declared? Measured on the estate's first run, the answer was **4,235 of 8,905 tracked files** —
against a registry reporting fully green.

REPORTS, NEVER GATES (AC5). Uncovered is not a failure. `wom7web/src` is 352 markdown content
files; the design-system export is prose and PNGs; screenshots are screenshots. None of that wants
a stack, and a scan that called it drift would be routed around inside a week. Exit is 0 whether
the worklist is empty or long. `skill check`, `discovery --enforce` and `state-check` own the
blocking, and a second blocking gate here would just be a slower push.

WHAT IT CLAIMS, EXACTLY — and this is the line the estate keeps crossing. It reports that **no
stack DECLARES a path**. It does NOT report that the path is ungated: `pnpm-workspace.yaml` globs
`packages/*`, so `just typecheck` almost certainly does reach `packages/ui` even though no stack
entry mentions it. Both statements are true and they are different statements. Registry coverage is
the one that matters here because the registry is what the gates read — incidental coverage by a
workspace-wide command is coverage nobody declared and nobody can rely on.

THE CORPUS IS GIT-TRACKED (`git ls-files`), not the filesystem. Named because the estate has
already been bitten by the difference — a preflight globbed the disk and counted a gitignored file,
and `.astro` is 210 tracked against 220 on disk, with live docs quoting both. An untracked file is
not repo content the SDLC owns.

NO VACUOUS GREEN (AC6). "Nothing uncovered ✓" is the exact shape this estate has shipped
repeatedly, so every empty input REFUSES rather than passing: no repos, no stacks, no tracked
files, an unreadable registry, or an exemption with no reason.

Exit: 0 scan ran (the report is a worklist) · 2 the scan could not run (an input is missing/empty).

Run: `just coverage-scan` · `--json` · `--all` (list non-code groups too)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # discovery lives in estate scripts/ (T419)
from discovery import load_jsonc  # noqa: E402  — the JSONC parser with the `https://` guard

ESTATE = Path(__file__).resolve().parents[1]
ROOT = ESTATE / "wom7web"  # wom7web/
SDLC = ESTATE / ".w0m" / "sdlc.json"
STACKS = ESTATE / "project" / "policies" / "stacks-policy.json"

# Extensions that make a file CODE for this scan's purposes — i.e. something a stack could
# plausibly typecheck, lint, test or build. Everything else is prose/asset/data and is summarised
# rather than listed, because burying 15 real findings under 1,730 markdown files is how a
# worklist becomes wallpaper.
#
# ⚠️ `.sql` is deliberately CODE. 228 uncovered migrations were the single largest code finding on
# the first run, and they are governed (db-migrate + the wom_ddl_guard event trigger) by machinery
# that no stack entry mentions — precisely the kind of gap that is invisible until someone asks.
# `.json`/`.yaml` are deliberately NOT code: config travels with whatever claims its directory.
CODE_EXT = {
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".astro", ".svelte", ".vue",
    ".py", ".rs", ".go", ".sh", ".bash",
    ".sql",
}


class Refuse(Exception):
    """An input is missing or empty — the scan cannot run, as opposed to running and finding
    nothing. The two must never print the same thing."""


def _tracked(repo: Path) -> list[str]:
    """Git-tracked paths, repo-relative. A repo that is not a git checkout REFUSES rather than
    contributing zero files to a total that would then read as 'scanned'."""
    if not (repo / ".git").exists():
        raise Refuse(f"{repo.name}: not a git checkout — cannot enumerate a tracked corpus")
    out = subprocess.run(
        ["git", "-C", str(repo), "ls-files"],
        capture_output=True, text=True, check=False,
    )
    if out.returncode != 0:
        raise Refuse(f"{repo.name}: `git ls-files` failed — {out.stderr.strip()[:200]}")
    return [line for line in out.stdout.splitlines() if line]


def _claims(stacks: dict) -> dict[str, list[tuple[str, str]]]:
    """repo-dir-name → [(stack name, claimed path), …].

    The registry types `path` as a single string and models one stack = one repo (T189 chose a
    second `tooling-api` entry over a path list for exactly this reason), so a claim is one
    prefix. `mlx` declares the nested `wom7mlx/wom7mlx`, so the repo key is split off the front
    rather than assumed to be a bare directory name.
    """
    out: dict[str, list[tuple[str, str]]] = {}
    for name, spec in stacks.items():
        if not isinstance(spec, dict):
            raise Refuse(f"stack `{name}` is not an object — the registry is malformed")
        repo = spec.get("repo")
        path = spec.get("path")
        if not repo or path is None:
            raise Refuse(f"stack `{name}` declares no repo/path — it claims nothing, silently")
        out.setdefault(str(repo).split("/", 1)[0], []).append((name, str(path)))
    return out


def _covered_by(rel: str, claimed: list[tuple[str, str]]) -> str | None:
    for name, path in claimed:
        if path in (".", ""):
            return name
        stem = path.rstrip("/")
        if rel == stem or rel.startswith(stem + "/"):
            return name
    return None


def _exemptions(reg: dict) -> dict[str, str]:
    """`coverage_exempt`: "<repo>/<path-prefix>" → reason.

    Separate from the registry's `exempt` (which exempts whole STACKS from drift) because this
    exempts a PATH from needing a stack at all — a different decision about a different noun.
    Same discipline though, per T135: a reasonless exemption REFUSES. An exemption recorded as a
    bare name cannot be re-evaluated by whoever finds it next.
    """
    ex = reg.get("coverage_exempt")
    if ex is None:
        return {}
    if not isinstance(ex, dict):
        raise Refuse(
            "`coverage_exempt` must be an object mapping <repo>/<prefix> to a reason, "
            f"not {type(ex).__name__} — a bare name records no decision"
        )
    for key, reason in ex.items():
        if not isinstance(reason, str) or not reason.strip():
            raise Refuse(f"coverage_exempt `{key}`: missing a reason — an exemption without a cause cannot be re-evaluated")
    return dict(ex)


def _group(rel: str) -> str:
    """The file's DIRECTORY, truncated to two segments.

    Deep enough to separate `packages/ui` from `packages/crawler`, shallow enough to stay
    readable. 🔴 It must key on the dirname, not on the first two segments of the path: doing the
    latter turned every file directly inside `scripts/` into its own one-line "group" and printed
    40 rows of `wom7web/scripts/<file>` reading as 40 findings, when it is one directory and one
    decision. A worklist that inflates its own row count is the defect this scan exists to find,
    committed by the scan — caught only by reading its first real output.
    """
    parts = rel.split("/")[:-1]          # drop the filename
    if not parts:
        return "<root>"
    return "/".join(parts[:2])


def scan(estate: Path = ESTATE, sdlc: Path = SDLC, stacks_file: Path = STACKS) -> dict:
    try:
        conf = json.loads(sdlc.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise Refuse(f"cannot read {sdlc} — {exc}") from exc
    try:
        reg = load_jsonc(stacks_file)
    except (OSError, json.JSONDecodeError) as exc:
        raise Refuse(f"cannot read {stacks_file} — {exc}") from exc

    repos = conf.get("repos") or {}
    if not repos:
        raise Refuse("`.w0m/sdlc.json → repos` is empty — there is no corpus to scan")
    stacks = reg.get("stacks") or {}
    if not stacks:
        raise Refuse("`stacks-policy.json → stacks` is empty — every file would report as uncovered")

    claims = _claims(stacks)
    exempt = _exemptions(reg)

    total = 0
    covered = 0
    code_groups: Counter = Counter()
    other_groups: Counter = Counter()
    other_ext: Counter = Counter()
    exempted = 0
    missing: list[str] = []

    for _alias, rel_repo in sorted(repos.items()):
        repo_dir = estate / rel_repo
        if not repo_dir.is_dir():
            missing.append(rel_repo)
            continue
        key = str(rel_repo).split("/", 1)[0]
        claimed = claims.get(key, [])
        for rel in _tracked(repo_dir):
            total += 1
            if _covered_by(rel, claimed):
                covered += 1
                continue
            full = f"{key}/{rel}"
            if any(full == p or full.startswith(p.rstrip('/') + "/") for p in exempt):
                exempted += 1
                continue
            name = rel.rsplit("/", 1)[-1]
            ext = ("." + name.rsplit(".", 1)[1]).lower() if "." in name else ""
            bucket = f"{key}/{_group(rel)}"
            if ext in CODE_EXT:
                code_groups[bucket] += 1
            else:
                other_groups[bucket] += 1
                other_ext[ext or "<noext>"] += 1

    if missing:
        raise Refuse(
            "declared repo(s) absent from disk: " + ", ".join(missing)
            + " — a scan that skipped them would under-report coverage gaps as green"
        )
    if total == 0:
        raise Refuse("zero tracked files across all declared repos — the corpus is empty, not clean")

    return {
        "corpus": "git-tracked (`git ls-files`)",
        "repos": len(repos),
        "stacks": len(stacks),
        "total": total,
        "covered": covered,
        "exempted": exempted,
        "uncovered_code": sum(code_groups.values()),
        "uncovered_other": sum(other_groups.values()),
        "code_groups": code_groups.most_common(),
        "other_groups": other_groups.most_common(),
        "other_ext": other_ext.most_common(),
    }


def render(res: dict, show_all: bool) -> str:
    pct = 100.0 * res["covered"] / res["total"]
    lines = [
        f"▶ SDLC coverage scan — {res['total']} {res['corpus']} files across "
        f"{res['repos']} repos vs {res['stacks']} declared stacks",
        f"  covered by a stack : {res['covered']:>5}  ({pct:.1f}%)",
        f"  uncovered — code   : {res['uncovered_code']:>5}  ← the worklist",
        f"  uncovered — other  : {res['uncovered_other']:>5}  (prose/assets/config; usually fine)",
    ]
    if res["exempted"]:
        lines.append(f"  exempt (w/ reason) : {res['exempted']:>5}")
    lines.append("")
    if res["code_groups"]:
        lines.append("  CODE claimed by no stack — each is a stack entry someone has to decide on:")
        for group, n in res["code_groups"]:
            lines.append(f"    {n:>5}  {group}")
    else:
        lines.append("  ✅ no code group sits outside every stack.")
    if show_all and res["other_groups"]:
        lines.append("")
        lines.append("  non-code claimed by no stack (--all):")
        for group, n in res["other_groups"]:
            lines.append(f"    {n:>5}  {group}")
    lines += [
        "",
        "  ⚠️  'uncovered' means NO STACK DECLARES THE PATH — not 'ungated'. A workspace-wide",
        "      recipe may still reach these files; that is coverage nobody declared and nobody",
        "      can rely on. Reports only: uncovered is a worklist, never a failure (T147 AC5).",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="T147 AC3 — repo content no stack claims")
    ap.add_argument("--json", action="store_true", help="machine-readable")
    ap.add_argument("--all", action="store_true", help="also list non-code groups")
    args = ap.parse_args()
    try:
        res = scan()
    except Refuse as exc:
        print(f"[FAIL] coverage scan REFUSED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(res, indent=2) if args.json else render(res, args.all))
    return 0


if __name__ == "__main__":
    sys.exit(main())
