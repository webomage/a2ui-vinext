#!/usr/bin/env python3
"""Hook-layer conformance — T149 AC3 (declared ⇒ wired) + T150 AC3b (forge allowlist).

TWO checks, ONE script, deliberately. T149's task 3.4 and T150's AC3b describe the same audit of the
same files; building it twice would be a second declaration of one contract, which is the drift this
epic exists to remove.

────────────────────────────────────────────────────────────────────────────────────────────────
CHECK 1 — DECLARED ⇒ WIRED.  `project/stacks-policy.json` declares, per stack, a `gates` phase for
each command role. A phase is a CLAIM; the hook is the MECHANISM (T135 §4). A role declared
`pre-commit`/`pre-push` whose recipe no hook actually invokes advertises coverage nobody is getting.

⚠️ WHY THE SEARCH IS ESTATE-WIDE, not per-repo. A gate can legitimately be wired from a DIFFERENT
repo's hook — w0m-web's pre-push graphs the whole workspace, and w0m-api's own config says as much.
Searching only the declaring repo would fail those correctly-wired gates. So a recipe found in ANY
repo's hook layer counts as wired, and the report names WHERE, so cross-repo wiring is visible
rather than implied.

────────────────────────────────────────────────────────────────────────────────────────────────
CHECK 2 — FORGE ALLOWLIST.  The owner's rule is that git hooks stay legacy git. T150 then made ONE
exception: the GitHub ticket mirror in `w0m-web/.husky/pre-push`. That inverts the check from a ban
("no forge call in any hook" — trivially verifiable) to an allowlist ("exactly one sanctioned call
site"), and an allowlist with no mechanism is a rule that drifts.

⚠️ Scope is HOOK FILES ONLY, never the repo. `sync_github.py` and any workflow are *allowed* to be
GitHub-specific — a repo-wide scan would fire on the very mirror this permits.

Exit: 0 conformant · 1 findings · 2 config error.
Run: `just hooks-check`
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import os

_DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("W0M_HOOKS_ROOT") or _DEFAULT_ROOT)   # …/@wom
WEB = ROOT / "w0m-web"        # …/w0m-web
# Overridable for the same reason ROOT is: check 3 (T135 AC4) reads its facts from the POLICY, not
# from the hook files, so a fixture that can only vary hooks cannot drive it red. Proving "a stack
# claiming `mode: local` with no pre-push role fails" on the real policy would mean committing that
# false claim to the estate's own config.
POLICY = Path(os.environ.get("W0M_STACKS_POLICY") or (_DEFAULT_ROOT / "project" / "policies" / "stacks-policy.json"))

GATED_PHASES = {"pre-commit", "pre-push"}

# Roles whose hook may legitimately NOT call `just <recipe>`, each with a REASON. Modelled on the
# estate's other gates: an exemption without a reason is a blocking finding, so an exemption can
# never quietly hide a defect. Keyed "stack/role".
CONTRACT_EXEMPT = {
    "edge/typecheck": (
        "The hook runs from the REPO ROOT on staged files, where deno cannot discover the "
        "functions' import map — hence its explicit `--config supabase/functions/deno.json`. The "
        "recipe `cd`s into the functions dir instead, so it needs no flag. Same intent, different "
        "mechanics, and the divergence is documented in the hook itself. Routing the hook through "
        "the recipe would also lose per-staged-file scoping and type-check every function on every "
        "commit."),
}

# The single sanctioned forge call site (T150). A SECOND one anywhere is a finding.
FORGE_ALLOWLIST = {"w0m-web/.husky/pre-push"}

# `gh <verb>` or a GitHub API host. Deliberately narrow: `github.com` in a URL comment is not a call,
# and flagging prose would train people to ignore this check.
FORGE_PATTERN = re.compile(r"\bgh\s+(issue|pr|api|project|label|repo|auth|run|workflow|release)\b"
                           r"|api\.github\.com")


def hook_files(repo: Path) -> list[Path]:
    """Every file that git or pre-commit will actually execute for this repo.

    `.husky/_` is EXCLUDED: it is husky's generated shim directory, regenerated on install, and
    treating a generated wrapper as a hook would report husky's own plumbing as project content.
    """
    out: list[Path] = []
    husky = repo / ".husky"
    if husky.is_dir():
        out += [f for f in husky.iterdir() if f.is_file() and not f.name.startswith(".")]
    cfg = repo / ".pre-commit-config.yaml"
    if cfg.is_file():
        out.append(cfg)
    rpp = repo / "scripts" / "root_pre_push.py"
    if rpp.is_file():
        out.append(rpp)
    return out


def _split_top_level_alt(expr: str) -> list[str]:
    """Split a regex string on top-level `|` (depth 0 outside `(...)` and `[...]`)."""
    parts: list[str] = []
    cur: list[str] = []
    depth = 0
    in_class = False
    i = 0
    while i < len(expr):
        ch = expr[i]
        if ch == "\\" and i + 1 < len(expr):
            cur.append(expr[i : i + 2])
            i += 2
            continue
        if ch == "[" and not in_class:
            in_class = True
        elif ch == "]" and in_class:
            in_class = False
        elif not in_class:
            if ch == "(":
                depth += 1
            elif ch == ")" and depth > 0:
                depth -= 1
            elif ch == "|" and depth == 0:
                parts.append("".join(cur))
                cur = []
                i += 1
                continue
        cur.append(ch)
        i += 1
    parts.append("".join(cur))
    return [p for p in parts if p]


def _find_matching_paren(expr: str, open_idx: int) -> int:
    """Return index of matching `)` for `(` at `open_idx`, or -1."""
    depth = 0
    in_class = False
    i = open_idx
    while i < len(expr):
        ch = expr[i]
        if ch == "\\" and i + 1 < len(expr):
            i += 2
            continue
        if ch == "[" and not in_class:
            in_class = True
        elif ch == "]" and in_class:
            in_class = False
        elif not in_class:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    return -1


def _literal_prefix_of_branch(branch: str) -> str:
    """Extract the leading literal path segments from a single anchored regex branch."""
    b = branch.strip()
    if b.endswith("$"):
        b = b[:-1]
    literal_segs: list[str] = []
    for seg in b.split("/"):
        if not seg:
            break
        unescaped = seg.replace(r"\.", ".").replace(r"\-", "-")
        if any(ch in unescaped for ch in ("[", "]", "(", ")", "*", "+", "?", "{", "}", "^", "$", "|", "\\")):
            break
        literal_segs.append(unescaped)
    return "/".join(literal_segs)


def _extract_anchored_prefixes(raw_pattern: str) -> list[str]:
    """Extract literal repo-relative path prefixes from an anchored (`^...`) hook regex (T527 AC3)."""
    pat = raw_pattern.strip().strip("'\"")
    if not pat.startswith("^"):
        return []
    pat = pat[1:]
    if pat.endswith("$"):
        pat = pat[:-1]
    if pat.startswith("(.*") or pat.startswith(".*"):
        return []

    branches: list[str] = []
    if pat.startswith("("):
        close_idx = _find_matching_paren(pat, 0)
        if close_idx != -1:
            inner = pat[1:close_idx]
            rest = pat[close_idx + 1 :]
            if rest in ("", ".*"):
                branches = _split_top_level_alt(inner)
            else:
                branches = [f"{b}{rest}" for b in _split_top_level_alt(inner)]
        else:
            branches = _split_top_level_alt(pat)
    else:
        open_idx = pat.find("(")
        if open_idx != -1:
            lead = pat[:open_idx]
            lead_clean = lead.replace(r"\.", ".").replace(r"\-", "-")
            close_idx = _find_matching_paren(pat, open_idx)
            if close_idx != -1 and not any(
                c in lead_clean for c in ("[", "]", "*", "+", "?", "{", "}", "^", "$", "|", "\\")
            ):
                inner = pat[open_idx + 1 : close_idx]
                rest = pat[close_idx + 1 :]
                branches = [f"{lead}{b}{rest}" for b in _split_top_level_alt(inner)]
            else:
                branches = _split_top_level_alt(pat)
        else:
            branches = _split_top_level_alt(pat)

    out: list[str] = []
    for br in branches:
        pref = _literal_prefix_of_branch(br)
        if pref and pref not in out:
            out.append(pref)
    return out


def _path_exists_in_repo(
    repo_dir: Path,
    rel_prefix: str,
    *,
    allow_cross_repo_symlink: bool = True,
) -> bool:
    """Return True if `rel_prefix` exists inside `repo_dir`."""
    candidate = repo_dir / rel_prefix
    if not (candidate.exists() or candidate.is_symlink()):
        return False
    if not allow_cross_repo_symlink and candidate.is_symlink():
        try:
            resolved = candidate.resolve()
            resolved.relative_to(repo_dir.resolve())
        except (ValueError, OSError):
            return False
    return True


def _repo_label(root: Path, repo_dir: Path) -> str:
    try:
        rel = repo_dir.resolve().relative_to(root.resolve())
        return "@wom" if str(rel) == "." else str(rel)
    except ValueError:
        return str(repo_dir)


def check_hook_scope_paths(root: Path, corpus: dict[str, str] | None = None) -> list[str]:
    """T527 AC3 — verify that paths a hook greps for or filters by exist in the repo whose range it reads."""
    if corpus is None:
        corpus = {}
        for f in hook_files(root):
            corpus[str(f.relative_to(root))] = f.read_text(encoding="utf-8", errors="replace")
        for sub in sorted([*root.glob("w0m-*"), *root.glob("wom" + "7*")]):
            if sub.is_dir():
                for f in hook_files(sub):
                    corpus[str(f.relative_to(root))] = f.read_text(encoding="utf-8", errors="replace")

    scope_findings: list[str] = []
    for rel_path, text in sorted(corpus.items()):
        full_path = root / rel_path
        if full_path.parent.name in (".husky", "scripts"):
            hook_repo = full_path.parent.parent
        else:
            hook_repo = full_path.parent

        if full_path.name == ".pre-commit-config.yaml":
            repo_lbl = _repo_label(root, hook_repo)
            for i, line in enumerate(text.splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                m_files = re.match(r"^\s*files:\s*(.+?)\s*$", line)
                if not m_files:
                    continue
                prefixes = _extract_anchored_prefixes(m_files.group(1))
                if not prefixes:
                    continue
                existing = [
                    p for p in prefixes if _path_exists_in_repo(hook_repo, p, allow_cross_repo_symlink=True)
                ]
                if "project/tickets" in prefixes or not existing:
                    missing = [
                        p
                        for p in prefixes
                        if not _path_exists_in_repo(hook_repo, p, allow_cross_repo_symlink=True)
                    ]
                    scope_findings.append(
                        f"{rel_path}:{i}: pre-commit `files:` scope references non-existent path(s) "
                        f"{missing} in `{repo_lbl}` (T527 AC3)"
                    )
        elif full_path.parent.name == ".husky":
            var_target_repo: dict[str, Path] = {}
            for i, line in enumerate(text.splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                m_assign = re.search(r"(\w+)=\$\(\s*git\s+(?:-C\s+(\S+)\s+)?diff\b", line)
                if m_assign:
                    vname, c_dir = m_assign.group(1), m_assign.group(2)
                    var_target_repo[vname] = (hook_repo / c_dir).resolve() if c_dir else hook_repo

                has_inline_diff = bool(re.search(r"\bgit\s+(?:-C\s+\S+\s+)?diff\b", line))
                used_vars = [v for v in var_target_repo if f"${v}" in line or f"${{{v}}}" in line]
                if not has_inline_diff and not used_vars:
                    continue

                if has_inline_diff:
                    m_inline = re.search(r"\bgit\s+-C\s+(\S+)\s+diff\b", line)
                    target_repo = (hook_repo / m_inline.group(1)).resolve() if m_inline else hook_repo
                else:
                    target_repo = var_target_repo[used_vars[0]]

                target_lbl = _repo_label(root, target_repo)
                for m_grep in re.finditer(r"""grep\s+-[A-Za-z]*E[A-Za-z]*\s+['"](\^[^'"]+)['"]""", line):
                    prefixes = _extract_anchored_prefixes(m_grep.group(1))
                    for pref in prefixes:
                        if not _path_exists_in_repo(target_repo, pref, allow_cross_repo_symlink=False):
                            scope_findings.append(
                                f"{rel_path}:{i}: hook scope greps for `{pref}` in `{target_lbl}`, "
                                f"which does not exist in that repo (T527 AC3)"
                            )
        elif full_path.name == "root_pre_push.py":
            target_lbl = _repo_label(root, hook_repo)
            for i, line in enumerate(text.splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                m_re = re.search(r"""TRACKING_SCOPE_RE\s*=\s*re\.compile\(\s*r?['"](\^[^'"]+)['"]""", line)
                if m_re:
                    for pref in _extract_anchored_prefixes(m_re.group(1)):
                        if not _path_exists_in_repo(hook_repo, pref, allow_cross_repo_symlink=False):
                            scope_findings.append(
                                f"{rel_path}:{i}: hook scope regex references `{pref}` in `{target_lbl}`, "
                                f"which does not exist in that repo (T527 AC3)"
                            )

    return scope_findings



def phases_of(path: str, text: str) -> set[str]:
    """Which phase(s) can this hook file actually run at?

    A husky hook's phase IS its filename. A pre-commit config can carry several, so its phases are
    whatever `stages:` declares. Used to catch a subtler defect than "unwired": a role declared
    `pre-push` but wired only somewhere that runs at `pre-commit` still runs — just not when the
    registry says. A reader trusting the registry believes it gates the push. It does not.
    """
    name = path.rsplit("/", 1)[-1]
    if name in GATED_PHASES:
        return {name}
    if name == "root_pre_push.py":
        return {"pre-push"}
    if name == ".pre-commit-config.yaml":
        # One pass. The earlier `set(findall(...)) and {…}` form scanned twice and read as a bug —
        # it relied on an empty set being falsy to return an empty set, which is correct but opaque.
        return {st.strip() for m in re.findall(r"stages:\s*\[([^\]]*)\]", text)
                for st in m.split(",") if st.strip()}
    return set()


def main() -> int:
    if not POLICY.is_file():
        print(f"✗ hooks-check: {POLICY} not found", file=sys.stderr)
        return 2
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    stacks = policy.get("stacks", {})
    if not stacks:
        # An empty registry must FAIL, not report a clean estate — the vacuous-gate failure mode.
        print("✗ hooks-check: stacks registry is empty — nothing could be checked", file=sys.stderr)
        return 2

    # Build the estate-wide hook corpus once, and NAME it (this epic's own rule).
    corpus: dict[str, str] = {}
    # `repo` is the repo DIRECTORY; `path` is a sub-path WITHIN it (apps, src,
    # supabase/functions). Preferring `path` resolved to nothing — the empty-corpus guard
    # below caught that, which is precisely why it exists.
    for repo_dir in sorted({st.get("repo", "") for st in stacks.values() if st.get("repo")}):
        rp = ROOT / repo_dir
        for f in hook_files(rp):
            corpus[str(f.relative_to(ROOT))] = f.read_text(encoding="utf-8", errors="replace")
    for f in hook_files(ROOT):
        corpus[str(f.relative_to(ROOT))] = f.read_text(encoding="utf-8", errors="replace")
    if not corpus:
        print("✗ hooks-check: no hook files found across the estate — refusing to report clean",
              file=sys.stderr)
        return 2

    findings: list[str] = []
    warnings: list[str] = []
    checked = wired = 0

    # ── check 1: declared ⇒ wired ────────────────────────────────────────────────
    for name, st in stacks.items():
        commands = st.get("commands", {})
        for role, decl in (st.get("gates") or {}).items():
            phase = decl["phase"] if isinstance(decl, dict) else decl
            if phase not in GATED_PHASES:
                continue
            recipe = commands.get(role)
            if not recipe:
                findings.append(f"stack `{name}`: role `{role}` is gated at {phase} but declares no recipe")
                continue
            checked += 1
            # ⚠️ NOT \b — a hyphen IS a word boundary, so `\btypecheck\b` matches inside
            # `skills-typecheck` and `typecheck-worker`, reporting a role as wired by a DIFFERENT
            # recipe. A false "wired" is the worst possible result here: it certifies coverage that
            # does not exist, which is the defect this check was written to find.
            # Match the INVOCATION `just <recipe>`, not the bare recipe name. Two reasons:
            #  1. `\b` treats `-` as a boundary, so `\btypecheck\b` matches inside
            #     `skills-typecheck` / `typecheck-worker` — a role reported wired by a DIFFERENT
            #     recipe. A false "wired" certifies coverage that does not exist, which is exactly
            #     the defect this check exists to find.
            #  2. Generic names like `typecheck` appear as bare words in unrelated config prose.
            # T130 mandates every stack tool run through `just`, so the invocation IS the contract.
            pat = rf"just\s+(?:--\S+\s+)*{re.escape(recipe)}(?![\w-])"
            hits = [p for p, text in corpus.items() if re.search(pat, text)]
            if hits:
                wired += 1
                where = hits[0]
                if not where.startswith(st.get("repo", "")):
                    print(f" [INFO] {name}/{role} ({phase}) wired from ANOTHER repo: {where}")
                # Phase accuracy — wired, but is it wired WHERE the registry says?
                reachable = set().union(*(phases_of(h, corpus[h]) for h in hits)) or set()
                if reachable and phase not in reachable:
                    warnings.append(
                        f"stack `{name}`: role `{role}` is declared `{phase}` but its only wiring "
                        f"({where}) runs at {sorted(reachable)} — it DOES run, just not when the "
                        f"registry claims. Fix the declaration or add the missing hook.")
            else:
                # Distinguish "absent" from "present but bypassing the contract". A hook whose id
                # matches the recipe but whose entry runs the raw command (npx/deno/tsc) DOES gate —
                # it just duplicates the recipe inline, which T130 forbids precisely because the two
                # then drift. Reporting that as "not wired" would send the next agent to add a
                # SECOND hook for work already being done.
                bypass = [p for p, text in corpus.items()
                          if re.search(rf"id:\s*{re.escape(recipe)}(?![\w-])", text)]
                key = f"{name}/{role}"
                if bypass and key in CONTRACT_EXEMPT:
                    wired += 1
                    print(f" [INFO] {key} exempt from the `just` contract — {CONTRACT_EXEMPT[key][:70]}…")
                elif bypass:
                    findings.append(
                        f"stack `{name}`: role `{role}` ({phase}) has a hook `{recipe}` in "
                        f"{bypass[0]} but it runs the RAW command, not `just {recipe}` — T130 "
                        f"forbids raw npx/deno/tsc in place of the recipe, because the hook and the "
                        f"recipe then drift. Point the hook at the recipe.")
                else:
                    findings.append(
                        f"stack `{name}`: role `{role}` declares phase `{phase}` but NO hook in the "
                        f"estate runs it at all — a phase is a claim; the hook is the mechanism")

    # ── check 2: forge allowlist ─────────────────────────────────────────────────
    for path, text in sorted(corpus.items()):
        for i, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue                       # a comment documenting the rule is not a call
            if FORGE_PATTERN.search(line) and path not in FORGE_ALLOWLIST:
                findings.append(
                    f"{path}:{i}: forge-specific call in a hook — only {sorted(FORGE_ALLOWLIST)[0]} "
                    f"is sanctioned (T150). Hooks stay legacy git.")

    # ── check 3: pre-push coverage is a DECISION, not an accident (T135 AC4) ─────
    #
    # Only `web` has a pre-push hook. That is defensible — the estate-wide gates all live there and
    # enumerate every repo — but "defensible" and "decided" are different things, and before this
    # check the difference was invisible: a repo with no push gate looked exactly like a repo nobody
    # had thought about. So every stack must DECLARE how it is covered.
    #
    # 🔑 The load-bearing half is that `local` is FALSIFIABLE. A stack claiming its own pre-push
    # gate while declaring no role at phase `pre-push` is caught here — otherwise the declaration
    # would be the same kind of unverified claim the whole T149 "declared ⇒ wired" check exists to
    # kill, just moved up a level. `central` and `none` are choices rather than claims, so what they
    # owe instead is a REASON a reviewer can disagree with.
    push_modes: dict[str, int] = {}
    for name, st in stacks.items():
        if st.get("enabled") is False:
            continue
        pg = st.get("push_gate")
        if not isinstance(pg, dict) or not pg.get("mode"):
            findings.append(
                f"stack `{name}`: no `push_gate` declared — pre-push coverage must be a recorded "
                "decision, not an accident (T135 AC4). Declare mode local/central/none.")
            continue
        mode = pg["mode"]
        push_modes[mode] = push_modes.get(mode, 0) + 1
        has_push_role = any(
            (d.get("phase") if isinstance(d, dict) else d) == "pre-push"
            for d in (st.get("gates") or {}).values())
        if mode == "local" and not has_push_role:
            findings.append(
                f"stack `{name}`: declares `push_gate.mode = local` but NO role declares phase "
                "`pre-push` — a claimed gate that does not exist is worse than a recorded gap")
        if mode != "local" and not (pg.get("reason") or "").strip():
            findings.append(
                f"stack `{name}`: `push_gate.mode = {mode}` carries no reason — an ungated repo has "
                "to be a choice someone can argue with, not a silence")
        if mode == "central":
            by = pg.get("covered_by")
            if not by:
                findings.append(f"stack `{name}`: `push_gate.mode = central` must name `covered_by`")
            elif by not in stacks:
                findings.append(
                    f"stack `{name}`: `push_gate.covered_by = {by}` is not a declared stack")
            elif not any((d.get("phase") if isinstance(d, dict) else d) == "pre-push"
                         for d in (stacks[by].get("gates") or {}).values()):
                findings.append(
                    f"stack `{name}`: covered_by `{by}`, but `{by}` itself declares no pre-push "
                    "role — the coverage it is relied on for does not exist")

    # ── check 4: hook scope paths exist in the inspected repo (T527 AC3) ─────────
    findings.extend(check_hook_scope_paths(ROOT, corpus))

    # Name the enumerated set — a count without its scope is this epic's organising defect.
    print(f"▶ hooks-check — {len(corpus)} hook file(s) across {len(stacks)} stack(s); "
          f"{checked} gated role(s) declared, {wired} wired; "
          f"push-gate {', '.join(f'{k}={v}' for k, v in sorted(push_modes.items())) or 'NONE DECLARED'}; "
          f"forge allowlist = {sorted(FORGE_ALLOWLIST)[0]}")

    for w in warnings:
        print(f" [WARN] {w}")
    if findings:
        # `finding`, not `f`: `f` is a Path elsewhere in this module (hook files). Distinct
        # types, distinct names (T188).
        for finding in findings:
            print(f"  ✗  {finding}")
        print(f"\n❌ hooks-check failed — {len(findings)} finding(s)")
        return 1
    suffix = f" ({len(warnings)} warning(s))" if warnings else ""
    print(f"✅ hooks-check passed — every gated role is wired, and no unsanctioned forge call "
          f"in any hook{suffix}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
