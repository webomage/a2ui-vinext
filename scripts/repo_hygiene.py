#!/usr/bin/env python3
"""Repo-hygiene gates (T135) — `docs`, `license`, `secrets`.

Driven by `project/hygiene-policy.json`. Each subcommand is a read-only check that exits 0 when
clean and 1 on any violation. Reached through `just docs-check` / `just license-check` /
`just secrets-check`, declared in `project/stacks-policy.json` under the matching `commands` role
with an explicit `gates` phase.

    python3 scripts/repo_hygiene.py docs
    python3 scripts/repo_hygiene.py license
    python3 scripts/repo_hygiene.py secrets
    python3 scripts/repo_hygiene.py all --json

THE EMPTY-INPUT-SET RULE (AC7 / tasks.md 7.2)
---------------------------------------------
Every check FAILS when it has nothing to inspect. This is not defensive coding, it is the
specific defect this change exists to stop shipping: T127 printed
`0 managed skill(s) match the lockfile ✓` and T130's `enforce_raw` guarded a scan that found
nothing, and in both cases a green tick meant "ran nothing", not "found nothing wrong". A
scope that silently shrinks to zero is worse than a missing gate, because it reports success.
So: a declared repo that is not on disk is a hard failure, not a skip; and a check whose
candidate set is empty fails with `no <thing> to check`.

Licensing note: the license check classifies FIRST-PARTY vs VENDORED before asserting anything.
Writing `license: UNLICENSED` into a vendored third-party manifest would relicense code we do
not own — the estate has exactly such a manifest (`@mcp-b/websocket-bridge`, correctly MIT with
a tracked LICENSE), and an unclassified sweep would have converted it to proprietary.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# Overridable so the gates can be driven against a FIXTURE tree (T135 AC7). Without this hook the
# three gates this ticket added — docs, secrets, license — could only ever be observed GREEN on the
# real estate, because constructing a real violation would mean committing one. Their red proofs
# were therefore run once by hand and written into the ticket body, which means a regression in
# their ability to FAIL would be invisible. `state_doctor.py` solved the same problem with
# `W0M_STATE_MD`; this is that pattern, one layer up.
# Point it at a directory that STANDS IN FOR w0m-web — ROOT and the policy path both derive from
# it exactly as they do in the real layout, so a fixture is `<tmp>/w0m-web` with sibling repo dirs.
ROOT = Path(os.environ.get("W0M_HYGIENE_ROOT") or Path(__file__).resolve().parent.parent)
POLICY_PATH = ROOT / "project" / "policies" / "hygiene-policy.json"

SKIP_DIRS = frozenset(
    {"node_modules", ".git", "dist", "build", ".venv", "target", ".next", ".astro", ".svelte-kit"}
)


# ── helpers ──────────────────────────────────────────────────────────────────

def read_text(path: Path) -> str | None:
    """Text of `path`, or None if unreadable.

    UnicodeDecodeError is a ValueError, NOT an OSError — catching only OSError let a binary
    file anywhere in a scanned tree kill the run with a traceback (see test_discovery case 9).
    """
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def load_policy() -> dict:
    raw = read_text(POLICY_PATH)
    if raw is None:
        sys.exit(f"cannot read {POLICY_PATH}")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        sys.exit(f"{POLICY_PATH} is not valid JSON: {exc}")


def declared_repos(policy: dict) -> tuple[list[tuple[str, Path]], list[str]]:
    """(present, missing). A declared repo that is absent is a violation, never a skip."""
    present: list[tuple[str, Path]] = []
    missing: list[str] = []
    for entry in policy.get("repos", []):
        rel = entry["path"]
        path = ROOT / rel
        if path.is_dir():
            present.append((rel, path))
        else:
            missing.append(rel)
    return present, missing


def markdown_headings(text: str) -> list[str]:
    """ATX headings, lowercased and stripped of markup/trailing punctuation.

    Fenced code blocks are skipped so a `# comment` inside a shell example cannot satisfy a
    required section.
    """
    headings: list[str] = []
    in_fence = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence or not stripped.startswith("#"):
            continue
        heading = stripped.lstrip("#").strip()
        heading = re.sub(r"[*_`]", "", heading)         # inline markup
        heading = re.sub(r"^[\W_]+", "", heading)       # leading emoji/punctuation
        headings.append(heading.strip().rstrip(":").lower())
    return headings


def is_vendored(rel_path: str, markers: list[str]) -> bool:
    return any(marker in rel_path for marker in markers)


# Comment openers by extension. A secrets gate that fires on prose DOCUMENTING good hygiene is
# worse than useless: the first run flagged 12 "violations" that were all comments recording
# T119 AC2b's removal of `dotenv-load`, which would have blocked every commit until someone
# deleted the documentation to appease the gate.
COMMENT_PREFIXES = {
    ".py": ("#",), ".sh": ("#",), ".yml": ("#",), ".yaml": ("#",),
    ".js": ("//",), ".ts": ("//",), ".mjs": ("//",), ".cjs": ("//",),
}
_DEFAULT_COMMENT_PREFIXES = ("#",)          # justfile, .husky/* hooks
_QUOTED = re.compile(r"""(['"])(?:\\.|(?!\1).)*\1""")


def _comment_prefixes(path: Path) -> tuple[str, ...]:
    return COMMENT_PREFIXES.get(path.suffix, _DEFAULT_COMMENT_PREFIXES)


def code_match(line: str, rx: re.Pattern, prefixes: tuple[str, ...],
               match_in_string: bool = False) -> bool:
    """True only if `rx` matches EXECUTABLE code on this line.

    Two exclusions, both from real false positives on the first run:
      * whole-line comments — prose about a pattern is not a use of it;
      * matches inside a single-line string literal — `add(SKIP, "infisical export failed")`
        is a diagnostic message, not an export.

    ⚠️ Quoted-span blanking must NOT be so aggressive that it hides argv lists. The genuine
    offender in this estate is `subprocess.run(["infisical", "export", …])`, where every token
    is quoted. So the blanking replaces only the quote CHARACTERS and inter-token punctuation
    with spaces, leaving the token text visible; a pattern whose separator class allows quotes
    and commas then still matches the call while prose inside one string does not.

    🔴 `match_in_string` exists because that string-literal exclusion made one pattern
    STRUCTURALLY VACUOUS — it could never fire, in any file, ever. `secret-file-read` looks for a
    plaintext credential FILENAME (`dev_secrets.json`), and a filename in real code is always
    written as a string literal — so it was always "wholly inside one quoted span" and always
    skipped. Caught only by running the red probe of task 6.4 and getting exit 0 where 1 was
    expected. ⇒ Whether a string literal is prose or the offence itself is a PER-PATTERN fact, not
    a global rule. Patterns that name a file set `match_in_string: true`; prose protection for them
    comes from the comment and docstring stripping instead.
    """
    stripped = line.strip()
    if not stripped or stripped.startswith(prefixes):
        return False

    spans = [] if match_in_string else [m.span() for m in _QUOTED.finditer(line)]
    for match in rx.finditer(line):
        start, end = match.span()
        # Wholly inside ONE quoted span => prose ("infisical export failed (session?)").
        # Crossing a quote boundary => an argv list (["infisical", "export", …]) => real code.
        if any(s <= start and end <= e for s, e in spans):
            continue
        return True
    return False


def strip_docstrings(body: str, path: Path) -> list[str | None]:
    """Lines of `body`, with lines inside triple-quoted blocks replaced by None.

    Needed because the first fix caught single-line strings but not docstrings, and this
    estate documents its own secret-handling rules in module docstrings — including a warning
    that `infisical secrets --plain` prints values, which the gate then reported as a
    violation of the very rule it was quoting.
    """
    lines: list[str | None] = list(body.splitlines())
    if path.suffix not in {".py"}:
        return lines
    in_doc: str | None = None
    for idx, line in enumerate(lines):
        text = line or ""
        if in_doc:
            lines[idx] = None
            if in_doc in text:
                in_doc = None
            continue
        for quote in ('"""', "'''"):
            first = text.find(quote)
            if first == -1:
                continue
            # A docstring that opens and closes on one line is handled by _QUOTED-style logic.
            if text.count(quote) == 1:
                in_doc = quote
                lines[idx] = None
            break
    return lines


def discover_manifests(repo: Path, markers: list[str]) -> list[dict]:
    """Every TRACKED package.json in the repo (task 5.9: discover, never hardcode).

    A hardcoded list of 4 (later 'corrected' to 7) missed most of the ones that exist.

    ⚠️ Tracked, not merely present on disk. Globbing the filesystem picked up
    `w0m-ext/extension-ff/package.json`, which is GITIGNORED (.gitignore:62) — so the gate
    would have demanded `private: true` and a licence in a file that is not part of the repo
    and whose edits could never be committed. Asking git what is in the repo, rather than
    asking the filesystem what is on disk, is the same lesson as resolving the git boundary
    before measuring anything.
    """
    # T477: iterate git's list, not `repo.rglob` — the walk entered every `node_modules` only to
    # discard it here, 30s of a push. A tracked manifest deleted from the worktree is skipped,
    # as the walk never found it either.
    tracked = sorted(
        repo / line for line in tracked_files(repo) if Path(line).name == "package.json"
    )
    out: list[dict] = []
    for manifest in tracked:
        rel = manifest.relative_to(repo)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if not os.path.lexists(manifest):
            continue
        entry: dict = {
            "rel": str(rel),
            "path": manifest,
            "vendored": is_vendored(str(rel), markers),
        }
        raw = read_text(manifest)
        if raw is None:
            entry["error"] = "unreadable"
        else:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                entry["error"] = f"invalid JSON: {exc}"
            else:
                entry["name"] = data.get("name")
                entry["private"] = data.get("private")
                entry["license"] = data.get("license")
        out.append(entry)
    return out


def tracked_files(repo: Path) -> list[str]:
    proc = subprocess.run(
        ["git", "-C", str(repo), "ls-files"], capture_output=True, text=True, check=False
    )
    return proc.stdout.splitlines() if proc.returncode == 0 else []


# ── docs (AC5) ───────────────────────────────────────────────────────────────

def check_docs(policy: dict) -> tuple[list[str], dict]:
    cfg = policy["docs"]
    required = cfg["required_files"]
    sections = cfg["readme_sections"]
    present, missing_repos = declared_repos(policy)

    problems = [f"declared repo `{r}` is not on disk — scope would silently shrink" for r in missing_repos]
    if not present:
        return problems + ["no repos to check — refusing to pass on an empty input set"], {}
    if not required:
        return problems + ["policy declares no required files — refusing to pass vacuously"], {}

    # 🔴 These two guards were MISSING until 2026-07-26 (T135 task 4.8), and their absence was a
    # live vacuous pass — found by testing the empty-input case deliberately, which is the only way
    # it surfaces. With `readme_sections: []` the whole content bar silently degenerated to a
    # file-exists check and `docs-check` reported ✅ over 8 repos. That is *precisely* the gate this
    # change exists to replace, reproduced inside the replacement.
    # The asymmetry is the lesson: `present` and `required` were both guarded, `sections` was not.
    # An empty-set guard has to cover EVERY collection the check iterates, not the obvious ones.
    if not sections:
        return problems + [
            "policy declares no README sections — refusing to pass vacuously. Without these the "
            "README bar degrades to a file-exists check, which is the gate this one replaces"
        ], {}
    if not any(spec["name"] == "README.md" for spec in required):
        return problems + [
            "README.md is not in `required_files`, so the README section bar can never run — "
            "declared sections that are never evaluated read as coverage while checking nothing"
        ], {}

    stats = {
        "repos": len(present),
        "required_files": len(required),
        "readme_sections": len(sections),
        "checked": 0,
    }

    for name, repo in present:
        for spec in required:
            filename = spec["name"]
            target = repo / filename
            stats["checked"] += 1
            if not target.is_file():
                problems.append(f"{name}: missing {filename}")
                continue
            body = read_text(target)
            if body is None or not body.strip():
                problems.append(f"{name}/{filename}: empty or unreadable")
                continue
            pattern = spec.get("must_match")
            if pattern and not re.search(pattern, body):
                problems.append(
                    f"{name}/{filename}: does not match required content /{pattern}/ "
                    "— a file that exists but says nothing is the vacuous pass this gate replaces"
                )
            if filename == "README.md":
                found = markdown_headings(body)
                if not found:
                    problems.append(f"{name}/README.md: no headings at all — cannot satisfy the section bar")
                for section in sections:
                    pats = section["any_heading_matching"]
                    if not any(re.search(p, h) for h in found for p in pats):
                        problems.append(
                            f"{name}/README.md: no heading for required section `{section['id']}` "
                            f"(need one matching: {', '.join(pats)})"
                        )
    return problems, stats


# ── license (AC6, AC11) ──────────────────────────────────────────────────────

def check_license(policy: dict) -> tuple[list[str], dict]:
    cfg = policy["licenses"]
    markers = cfg.get("vendored_markers", [])
    notice_files = cfg.get("vendored_notice_files", [])
    want_license = cfg["first_party_license"]
    require_private = cfg.get("require_private", True)
    exempt = {k: v for k, v in cfg.get("vendored_exempt", {}).items() if not k.startswith("_")}

    present, missing_repos = declared_repos(policy)
    problems = [f"declared repo `{r}` is not on disk — scope would silently shrink" for r in missing_repos]
    if not present:
        return problems + ["no repos to check — refusing to pass on an empty input set"], {}

    all_manifests: list[tuple[str, dict]] = []
    for name, repo in present:
        for m in discover_manifests(repo, markers):
            all_manifests.append((name, m))

    if not all_manifests:
        return problems + ["no manifests discovered — refusing to pass on an empty input set"], {}

    first_party = [(n, m) for n, m in all_manifests if not m["vendored"]]
    vendored = [(n, m) for n, m in all_manifests if m["vendored"]]
    if not first_party:
        return problems + ["no first-party manifests discovered — the classifier is mis-scoped"], {}

    stats = {
        "manifests": len(all_manifests),
        "first_party": len(first_party),
        "vendored": len(vendored),
    }

    # First-party publication safety (AC11).
    for name, m in first_party:
        where = f"{name}/{m['rel']}"
        if "error" in m:
            problems.append(f"{where}: {m['error']}")
            continue
        if require_private and m.get("private") is not True:
            problems.append(f"{where}: missing `private: true` — publishable by accident")
        if m.get("license") != want_license:
            problems.append(
                f"{where}: license is {m.get('license')!r}, must be {want_license!r}"
            )

    # Vendored trees keep their upstream notice (AC6). We assert the notice EXISTS; we never
    # rewrite the licence of code we do not own.
    for name, m in vendored:
        where = f"{name}/{m['rel']}"
        if m.get("license") is None:
            problems.append(f"{where}: vendored manifest declares no license — record the upstream one")

    checked_trees = 0
    # ONE `seen` set across every repo. Deduping per-repo cannot catch the case that actually
    # bit here: `w0m-api/.claude` is a symlink to `w0m-web/.claude`, so the identical 86 skill
    # directories were reported once under each repo name — 86 of 211 findings were the same
    # files twice, and no amount of per-repo care would have noticed.
    seen_trees: set[Path] = set()
    for name, repo in present:
        try:
            trees = vendored_trees(repo, cfg.get("vendored_trees", []), seen_trees)
        except ProvenanceUnavailable as e:
            # A tree we cannot classify is a finding, not a crash and not a silent pass.
            problems.append(f"{name}: {e}")
            continue
        for tree, why in trees:
            rel = str(tree.relative_to(repo))
            key = f"{name}/{rel}"
            if key in exempt:
                continue
            checked_trees += 1
            if not any((tree / n).is_file() for n in notice_files):
                problems.append(
                    f"{key}: vendored {why} has no {'/'.join(notice_files[:3])} — "
                    "upstream notice must be retained in copies"
                )
    stats["vendored_trees"] = checked_trees
    return problems, stats


class ProvenanceUnavailable(RuntimeError):
    """A vendored tree declares a provenance manifest that is not readable."""


def _first_party_skills(repo: Path, spec: dict) -> set[str]:
    """Skill names this project OWNS, from the T127 governance manifest.

    Provenance is already recorded per skill (`provider`), so read it. Classifying by path
    instead would mark all ~70 skills third-party — including the 13 w0m-native ones — and
    demand an "upstream notice" for code we wrote ourselves.
    """
    manifest = repo / spec["provenance"]
    raw = read_text(manifest)
    if raw is None:
        # FAIL LOUD, not open-into-noise. Returning an empty set here means "nothing is ours",
        # so every skill in the tree gets reported as a third-party drop owing an upstream
        # notice — including ones we wrote this week. That is exactly what happened to w0m-api,
        # which has no `.w0m/` at all: 86 false findings, indistinguishable from real ones.
        raise ProvenanceUnavailable(
            f"{spec['provenance']} is missing in {repo.name} — provenance cannot be resolved, "
            f"so this tree cannot be classified. Declare the manifest, or exclude the tree with "
            f"a reason; do NOT let it default to all-third-party."
        )
    try:
        skills = json.loads(raw).get("skills", {})
    except json.JSONDecodeError:
        raise ProvenanceUnavailable(f"{spec['provenance']} in {repo.name} is not valid JSON")
    want = spec.get("first_party_provider")
    return {name for name, meta in skills.items() if meta.get("provider") == want}


def vendored_trees(repo: Path, specs: list[dict], seen: set[Path] | None = None) -> list[tuple[Path, str]]:
    """(tree, description) for each vendored third-party drop in this repo.

    Only the TOP of each drop is reported: one notice at the root covers it, and walking deeper
    would demand a LICENSE in every subdirectory. Where a `provenance` manifest is declared,
    first-party entries are excluded — the tree is mixed, and only the parts we did not write
    carry an upstream notice obligation.
    """
    found: list[tuple[Path, str]] = []
    # Deduplicate on the RESOLVED path, the same discipline `check_secrets` already applies to the
    # symlinked justfiles. `w0m-api/.claude` is a symlink to `w0m-web/.claude`, and w0m-web's own
    # `.claude/skills` entries are symlinks into `.agents/skills` — so without this the identical
    # file is reported two or three times over. That both inflates the count and makes ONE fix
    # look like three, which is how a gate stops being read.
    seen = seen if seen is not None else set()
    for spec in specs:
        if "path" in spec:
            target = repo / spec["path"]
            if target.is_dir() and target.resolve() not in seen:
                seen.add(target.resolve())
                found.append((target, "tree"))
            continue
        parent = repo / spec["children_of"]
        if not parent.is_dir():
            continue
        # A tree that resolves OUTSIDE this repo belongs to another repo, which checks it under
        # its own provenance manifest. `w0m-api/.claude` is a symlink to `w0m-web/.claude`:
        # classifying it here asks w0m-api for a `.w0m/skills.json` it has no reason to own, and
        # answering that question wrongly is what produced 86 false "third-party" findings against
        # skills we wrote ourselves. Ownership follows the real path, not the symlink.
        try:
            parent.resolve().relative_to(repo.resolve())
        except ValueError:
            continue
        first_party = _first_party_skills(repo, spec) if "provenance" in spec else set()
        for child in sorted(parent.iterdir()):
            if not child.is_dir() or child.name in SKIP_DIRS:
                continue
            if child.name in first_party:
                continue
            real = child.resolve()
            if real in seen:
                continue
            seen.add(real)
            found.append((child, "third-party drop"))
    return found


# ── secrets (AC10) ───────────────────────────────────────────────────────────

def check_secrets(policy: dict) -> tuple[list[str], dict]:
    cfg = policy["secrets"]
    patterns = [
        (p["id"], re.compile(p["regex"]), p.get("note", ""), bool(p.get("match_in_string")))
        for p in cfg.get("forbidden_patterns", [])
    ]
    globs = cfg.get("scan_globs", [])
    present, missing_repos = declared_repos(policy)

    problems = [f"declared repo `{r}` is not on disk — scope would silently shrink" for r in missing_repos]
    if not present:
        return problems + ["no repos to check — refusing to pass on an empty input set"], {}
    if not patterns:
        return problems + ["policy declares no forbidden patterns — refusing to pass vacuously"], {}

    scanned = 0
    # w0m-web/justfile and w0m-cf/justfile are SYMLINKS to w0m-api/justfile. Scanning by
    # path reported the same three findings three times over, which both inflates the count and
    # makes one fix look like three. Deduplicate on the resolved inode.
    seen: set[Path] = set()
    for name, repo in present:
        tracked = set(tracked_files(repo))
        for pattern in globs:
            for candidate in repo.glob(pattern):
                if not candidate.is_file():
                    continue
                rel = str(candidate.relative_to(repo))
                if rel not in tracked:
                    continue  # only TRACKED automation is in scope
                real = candidate.resolve()
                if real in seen:
                    continue
                seen.add(real)
                body = read_text(candidate)
                if body is None:
                    continue
                scanned += 1
                prefixes = _comment_prefixes(candidate)
                code_lines = strip_docstrings(body, candidate)
                for pid, rx, note, in_string in patterns:
                    for lineno, line in enumerate(code_lines, 1):
                        if line is not None and code_match(line, rx, prefixes, in_string):
                            problems.append(
                                f"{name}/{rel}:{lineno} file-based secret access `{pid}` — {note}"
                            )

    if scanned == 0:
        problems.append(
            "scanned 0 tracked automation files — the glob set matches nothing, so a pass here "
            "would mean 'ran nothing'. Fix `secrets.scan_globs`."
        )

    corpus_problems, corpus_stats = check_skills_corpus(cfg)
    problems.extend(corpus_problems)
    return problems, {"scanned_files": scanned, **corpus_stats}


def check_skills_corpus(cfg: dict) -> tuple[list[str], dict]:
    """AC10's corpus half — TWO TIERS. The DENOMINATOR is stated in policy and echoed here.

    CONSUMING a secret (a variable-shaped reference, or `secrets.run` — an instruction to inject)
    obliges a skill to name the manager. Merely MENTIONING the topic in prose does not: the previous
    single-tier rule flagged a skill for the rule "never log secrets" and another for the words
    "Invalid Credentials" in an example Gherkin scenario. Punishing a document for describing good
    hygiene trains people to delete the documentation to appease the gate.

    "Names the manager" accepts the `{secrets.run}` config indirection as well as the literal
    `infisical`, because CLAUDE.md REQUIRES the project-agnostic skills to read the command from
    `.w0m/sdlc.json` rather than hardcode it. Demanding the literal string would have made appeasing
    this gate and following the conventions mutually exclusive.

    Empty-set discipline (AC7 / task 7.2): EVERY collection this iterates is guarded — the corpus
    itself and each configured regex. `docs-check` shipped a vacuous pass precisely because it
    guarded two collections out of three.
    """
    corpus_cfg = cfg.get("skills_corpus")
    if not corpus_cfg:
        return [], {}
    root = ROOT / corpus_cfg["root"]
    if not root.is_dir():
        return [f"skills corpus root `{corpus_cfg['root']}` is missing — cannot assess conformance"], {}

    # Guard every configured collection, not just the file list. A blank regex compiles happily and
    # then matches EVERYTHING (consume) or NOTHING (manager) — either way the gate stops meaning
    # what it says while still exiting 0.
    for key in ("secret_signal_regex", "prose_mention_regex", "manager_signal_regex"):
        if not (corpus_cfg.get(key) or "").strip():
            return [f"skills corpus `{key}` is empty — refusing to assess on an unset pattern"], {}

    consume_rx = re.compile(corpus_cfg["secret_signal_regex"])
    prose_rx = re.compile(corpus_cfg["prose_mention_regex"])
    manager_rx = re.compile(corpus_cfg["manager_signal_regex"])
    skills = sorted(root.rglob("SKILL.md"))
    if not skills:
        return ["skills corpus is empty — refusing to pass on an empty input set"], {}

    offenders: list[str] = []
    consuming = 0
    prose_only = 0
    for skill in skills:
        body = read_text(skill)
        if body is None:
            continue
        if consume_rx.search(body):
            consuming += 1
            if not manager_rx.search(body):
                offenders.append(str(skill.relative_to(ROOT)))
        elif prose_rx.search(body):
            prose_only += 1

    problems = [
        f"{path}: consumes a secret but never names the manager (`infisical` or `{{secrets.run}}`)"
        for path in offenders
    ]
    if consuming == 0:
        problems.append(
            f"0 of {len(skills)} skills read as consuming a secret — the signal matches nothing, so "
            "a pass here would mean 'assessed nothing'. Fix `secret_signal_regex`."
        )
    return problems, {
        "corpus_unit": corpus_cfg["unit"],
        "corpus_total": len(skills),
        "corpus_consuming": consuming,
        "corpus_prose_only": prose_only,
        "corpus_offenders": len(offenders),
    }


# ── driver ───────────────────────────────────────────────────────────────────

def _split_top(expr: str, op: str) -> list[str]:
    """Split on `op` at PAREN DEPTH ZERO only."""
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    tokens = re.split(r"(\(|\)|\s+)", expr)
    for tok in tokens:
        if tok == "(":
            depth += 1
        elif tok == ")":
            depth -= 1
        if depth == 0 and tok.strip().upper() == op:
            parts.append("".join(buf))
            buf = []
            continue
        buf.append(tok)
    parts.append("".join(buf))
    return [p.strip() for p in parts if p.strip()]


def _tier(expr: str, tiers: dict) -> str:
    """Evaluate an SPDX expression to fail / review / advisory.

    🔴 Written twice. The first version searched the WHOLE string for `OR` and, if it found one,
    took the most permissive branch — so `(MIT OR Apache-2.0) AND GPL-3.0-only` came back
    **advisory** while being GPL-bound. That is a FAIL-OPEN: the gate waving through exactly what
    it exists to stop, caught by the review gate rather than by the 20 probes, because every probe
    used a flat expression. ⇒ Parenthesised sub-expressions must be evaluated as sub-expressions,
    not pattern-matched inside the parent string.

    The semantics, which are opposite for the two operators and easy to invert:
      • `OR`  is an OFFER — the licensee elects one branch, so the MOST PERMISSIVE wins.
      • `AND` is CONJUNCTIVE — every term binds, so the MOST RESTRICTIVE wins.
    """
    order = {"advisory": 0, "review": 1, "fail": 2}
    e = expr.strip()
    while e.startswith("(") and e.endswith(")") and _split_top(e[1:-1], "NOPE") == [e[1:-1].strip()]:
        inner = e[1:-1].strip()
        if inner.count("(") == inner.count(")"):
            e = inner
        else:
            break

    ands = _split_top(e, "AND")
    if len(ands) > 1:
        return max((_tier(x, tiers) for x in ands), key=lambda g: order[g])
    ors = _split_top(e, "OR")
    if len(ors) > 1:
        return min((_tier(x, tiers) for x in ors), key=lambda g: order[g])

    term = e.strip("()").strip()
    for name in ("fail", "review"):
        for pat in tiers.get(name, {}).get("patterns", []):
            if re.search(pat, term, re.I):
                return name
    return "advisory"


def pnpm_licenses(repo: Path, prod_only: bool) -> tuple[dict, str | None]:
    """Read the licence set from pnpm itself — never a vendored list.

    A copied list is stale on the next install, which is the same stale-pin shape the openspec
    registry read avoids in ide_trace.py. If pnpm cannot answer, that is an ERROR: an empty
    licence set must never read as a clean one (T147 AC6).
    """
    argv = ["pnpm", "licenses", "list", "--json"] + (["--prod"] if prod_only else [])
    try:
        r = subprocess.run(argv, cwd=repo, capture_output=True, text=True)
    except (OSError, ValueError) as exc:
        return {}, f"cannot run pnpm in {repo.name}: {exc}"
    if r.returncode != 0:
        return {}, (f"`pnpm licenses list` failed in {repo.name} (exit {r.returncode}) — refusing "
                    "to report a clean licence set from a command that did not run")
    out = r.stdout.strip()
    # ⚠️ A workspace with no PRODUCTION dependencies is a real empty set, not a broken run: pnpm
    # exits 0 and prints "No licenses in packages found" as prose. w0m-skills is exactly this
    # (devDeps only). The distinction matters in both directions — treating it as an error makes
    # the gate permanently red on a conformant repo, and treating a genuine failure as empty
    # reports a clean licence set for a scan that never happened.
    if not out or "No licenses in packages found" in out:
        return {}, None
    try:
        data = json.loads(out)
    except json.JSONDecodeError as exc:
        return {}, f"pnpm returned unparseable JSON in {repo.name}: {exc}"
    return (data if isinstance(data, dict) else {}), None


def check_dep_licenses(policy: dict) -> tuple[list[str], dict]:
    """AC6 — the TRANSITIVE dependency-license audit.

    Three tiers (owner decision 2026-08-10): GPL/AGPL family FAILS outright; LGPL/MPL/EUPL/CDDL
    FAIL unless the package carries a written exemption with a reason (AC9); everything else is
    advisory. ⚠️ `prod` here means *pnpm classifies it as a production dependency*, NOT *it is in
    a shipped bundle* — see `deps-policy.json -> licenses._scope_limit`. The gate reports the
    dependency type it can measure and leaves the distribution question to the exemption reason.
    """
    deps_path = ROOT / "project" / "policies" / "deps-policy.json"
    raw = read_text(deps_path)
    if raw is None:
        return [f"cannot read {deps_path} — the licence policy it holds is what this gate is"], {}
    try:
        cfg = json.loads(raw).get("licenses")
    except json.JSONDecodeError as exc:
        return [f"deps-policy.json is unparseable: {exc}"], {}
    if not isinstance(cfg, dict):
        return ["`deps-policy.json -> licenses` is absent — hygiene-policy.json has pointed at "
                "this key since it was written; a pointer to a missing key reads as coverage"], {}

    tiers = cfg.get("tiers", {})
    if not tiers.get("fail", {}).get("patterns"):
        return ["the licence policy declares no `fail` patterns — every dependency would tier as "
                "advisory and the gate would pass on anything, which is not a pass"], {}
    exempt = {k: v for k, v in cfg.get("exempt", {}).items() if not k.startswith("_")}

    present, missing = declared_repos(policy)
    problems = [f"declared repo `{r}` is not on disk — scope would silently shrink" for r in missing]
    if not present:
        return problems + ["no repos to check — refusing to pass on an empty input set"], {}

    workspaces = [(n, p) for n, p in present if (p / "pnpm-lock.yaml").is_file()]
    if not workspaces:
        return problems + ["no pnpm workspace among the declared repos — an empty scan is a "
                           "missing input, not a clean result"], {}

    counts = {"fail": 0, "review": 0, "advisory": 0}
    scanned = 0
    empty: list[str] = []
    # Two different reasons an exemption can go stale, and the first draft reported both with the
    # SAME message — "no longer a production dependency" — which is a false statement when the
    # package is still there and merely re-licensed. Track presence separately from tier.
    seen_any: set[str] = set()
    unused = set(exempt)
    for name, repo in workspaces:
        data, err = pnpm_licenses(repo, prod_only=True)
        if err:
            problems.append(err)
            continue
        if not data:
            empty.append(name)          # zero prod deps — declared, not hidden
            continue
        for expr, pkgs in data.items():
            tier = _tier(expr, tiers)
            for pkg in pkgs:
                scanned += 1
                counts[tier] += 1
                seen_any.add(pkg.get("name", "?"))
                if tier == "advisory":
                    continue
                pname = pkg.get("name", "?")
                unused.discard(pname)
                if tier == "review" and pname in exempt:
                    if not str(exempt[pname]).strip():
                        problems.append(f"{pname} ({expr}) is exempted with an EMPTY reason — an "
                                        "unreasoned exemption is itself a finding (AC9)")
                    continue
                verb = "is strong copyleft" if tier == "fail" else "is weak copyleft with no exemption"
                problems.append(
                    f"{name}: `{pname}` {expr} {verb} and is a PRODUCTION dependency — "
                    + ("this estate is proprietary; resolve or replace it"
                       if tier == "fail" else
                       f"rule on it in deps-policy.json -> licenses.exempt with a reason"))
    for pname in sorted(unused):
        if ("-darwin-" in pname and sys.platform != "darwin") or \
           ("-linux-" in pname and not sys.platform.startswith("linux")) or \
           ("-win32-" in pname and sys.platform != "win32"):
            continue
        why = ("is no longer a production dependency anywhere" if pname not in seen_any
               else "is still a dependency but no longer carries a licence needing an exemption")
        problems.append(f"`{pname}` is exempted in deps-policy.json but {why} — a stale exemption "
                        "silently widens the next scan; remove it")
    if scanned == 0:
        problems.append("scanned 0 packages — an empty corpus is not a clean corpus")
    stats = {"workspaces": len(workspaces), "no_prod_deps": len(empty), "packages": scanned,
             "fail": counts["fail"], "review": counts["review"], "advisory": counts["advisory"],
             "exempt": len(exempt)}
    return problems, stats


def check_annotations(policy: dict) -> tuple[list[str], dict]:
    """Annotations & debt markers doctor check (T342)."""
    try:
        import annotations_doctor
        audit_fn = annotations_doctor.audit_annotations
    except ImportError:
        import importlib.util
        script_path = ROOT / "w0m-web" / "project" / "scripts" / "annotations_doctor.py"
        spec = importlib.util.spec_from_file_location("annotations_doctor", script_path)
        if spec is None or spec.loader is None:
            return ["cannot load annotations_doctor"], {}
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        audit_fn = module.audit_annotations

    results = audit_fn(root=ROOT, policy=policy)
    problems = []
    if results["total_files"] == 0:
        problems.append("no files to check (empty candidate set across declared repos)")

    summary = results.get("summary", {})
    stats = {
        "files": results["total_files"],
        "overrides": summary.get("overrides", 0),
        "hacks": summary.get("hacks", 0),
        "ignores": summary.get("ignores", 0),
        "todos": summary.get("todos", 0),
        "hotfixes": summary.get("hotfixes", 0),
        "lintexcludes": summary.get("lintexcludes", 0),
        "total": results["total_matches"]
    }
    return problems, stats


CHECKS = {"docs": check_docs, "license": check_license, "secrets": check_secrets,
          "dep-licenses": check_dep_licenses, "annotations": check_annotations}


def main() -> int:
    parser = argparse.ArgumentParser(description="w0m repo-hygiene gates (T135)")
    parser.add_argument("check", choices=[*CHECKS, "all"])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    policy = load_policy()
    selected = list(CHECKS) if args.check == "all" else [args.check]

    report: dict = {}
    failed = False
    for name in selected:
        problems, stats = CHECKS[name](policy)
        report[name] = {"problems": problems, "stats": stats}
        failed = failed or bool(problems)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for name in selected:
            problems, stats = report[name]["problems"], report[name]["stats"]
            detail = ", ".join(f"{k}={v}" for k, v in stats.items())
            if problems:
                print(f"❌ {name}-check failed ({len(problems)} problem(s)){' — ' + detail if detail else ''}:")
                for problem in problems:
                    print(f"  ✗  {problem}")
            else:
                print(f"✅ {name}-check passed{' — ' + detail if detail else ''}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
