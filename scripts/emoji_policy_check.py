#!/usr/bin/env python3
r"""emoji-check -- emoji are forbidden where a matcher breaks, asserted where a parser depends on
them, and ratcheted everywhere else.

Owner instruction 2026-08-22: prohibit emoji in logs and reports, because they cause parsing
problems. The instruction was earned the same day it was given: a grep for `ROADMAP` section 33
reported NO MATCH, because the heading carries a pictograph between the hashes and the number.
Seven tickets cite that section and every one of them was correct.

Two measurements decided the shape of this gate rather than the wording of the instruction:

  * 4266 emoji sit in markdown headings across 2178 files, and 918 output lines across 141
    scripts carry one. A gate that fires 4266 times is a gate somebody switches off (T135 AC8).
  * EIGHT parsers read emoji AS DATA. `run_suites.py:44` counts every probe's pass/fail with
    `re.compile(r"^\s*[<glyphs>]\s")`. Stripping emoji from script output without editing that
    regex would make every suite report ZERO checks and pass vacuously -- the exact false-green
    this estate keeps shipping, introduced by obeying a cleanup instruction literally.

So the rule is three-tiered, and the tiers are declared in `project/policies/emoji-policy.json`:

  HARD      markdown headings in the governance docs -> zero, enforced now. This is the position
            that actually broke. Verified safe first: `epic_completeness.py:22` matches
            `^##\s+(?:\S+\s+)?(\d+)\.` with the pictograph group ALREADY OPTIONAL.
  PROTOCOL  a glyph a parser reads. Not a violation. The gate asserts the coupling still holds
            and prints it every run -- an acknowledgement that vanishes is a gate that stopped
            looking (T246 AC5).
  RATCHET   everything else. The count may fall, never rise.

Exit codes: 0 clean * 1 a violation * 2 could not measure (never 0 on an unmeasurable corpus).

Run it as `just emoji-check`.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POLICY = ROOT / "project" / "policies" / "emoji-policy.json"
ESTATE = ROOT
WEB = ROOT / "w0m-web"


def load() -> dict:
    """The declaration. Raises nothing the caller cannot turn into exit 2.

    ⚠️ Written after a malformed edit made this gate die with a JSONDecodeError traceback. A gate
    that crashes is *safe* here only by accident -- `just` reported a non-zero exit, so nothing
    passed falsely. But a traceback says "this tool is broken" when the truth is "your policy is
    broken", and the two need different fixes. So the failure is now named.
    """
    return json.loads(POLICY.read_text(encoding="utf-8"))


def emoji_re(pol: dict) -> re.Pattern:
    """Build the pictograph matcher from the DECLARED ranges, never from a re-typed literal.

    The declaration also records what is deliberately NOT an emoji -- the arrow, the em-dash, the
    middot. Those are single-width, carry no variation selector, and no matcher here has broken on
    one. Banning them would be applying the rule's letter against its reason.
    """
    parts = []
    for r in pol["definition"]["ranges"]:
        if "-" in r:
            a, b = r.split("-")
            parts.append(f"\\U{int(a,16):08X}-\\U{int(b,16):08X}")
        else:
            parts.append(f"\\U{int(r,16):08X}")
    return re.compile("[" + "".join(parts) + "]")


def _ignored(paths: list[Path]) -> set[Path]:
    """The subset of `paths` that their own repository ignores.

    🔴 This exists because the docstring below used to be a claim, not a filter. `authored()`
    globbed the FILESYSTEM and named the result "authored", so anything sitting on disk counted --
    including 652 markdown files written by the scheduled Supabase Storage backup into
    `w0m-api/supabase/backups/`, a path that repo's own `.gitignore` excludes on line 117. One of
    them carried an emoji heading, so a backup running at 09:00 moved a BLOCKING ratchet by +1 and
    the only apparent remedies were to raise the baseline (prohibited) or to delete a backup. The
    measured number was never stable: it rose and fell with whether a backup had run.
    ⚠️ The test is IGNORED, not UNTRACKED. A file an author has just written and not yet committed
    is authored; a file the repo is configured never to keep is not.
    (Same error class the estate already recorded once: a preflight that globbed the filesystem
    instead of asking git counted a gitignored manifest and reported 4 where the truth was 18.)
    """
    by_repo: dict[Path, list[Path]] = {}
    for p in paths:
        for parent in p.parents:
            if (parent / ".git").exists():
                by_repo.setdefault(parent, []).append(p)
                break
        # A path in no git repository (the estate root holds unversioned authored docs) is kept.
    ignored: set[Path] = set()
    for repo, group in by_repo.items():
        try:
            proc = subprocess.run(
                ["git", "check-ignore", "--stdin", "-z"],
                cwd=repo,
                input="\0".join(str(p) for p in group) + "\0",
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            continue  # no git on PATH: fall back to counting everything, loudly wrong but not silent
        for line in proc.stdout.split("\0"):
            if line:
                ignored.add(Path(line) if Path(line).is_absolute() else repo / line)
    return ignored


def _pruned_glob(pattern: str, skip: set[str]):
    """`ESTATE.glob(pattern)` for a `<prefix>/**/<name-glob>` pattern, never entering a `skip` dir.

    T477: `ESTATE.glob("*/**/*.md")` walked every `node_modules` in the estate and only then
    dropped what it found there -- 28s of a push, 221s under pre-push contention. Every path under
    an excluded component is discarded by `authored()` anyway, so not descending into one yields
    exactly the same list. Symlinks match `Path.glob` too: followed where `<prefix>` matches one
    (`@wom/.agents`), not followed inside `**` -- the equivalence was measured file-for-file.
    """
    prefix, sep, name = pattern.partition("/**/")
    if not sep or "/" in name:
        raise ValueError(f"_pruned_glob: {pattern!r} is not a '<prefix>/**/<name-glob>' pattern")
    for top in ESTATE.glob(prefix):
        if not top.is_dir() or any(s in top.relative_to(ESTATE).parts for s in skip):
            continue
        for dirpath, dirnames, filenames in os.walk(top):
            dirnames[:] = [d for d in dirnames if d not in skip]
            base = Path(dirpath)
            for entry in (*dirnames, *filenames):
                if fnmatch.fnmatchcase(entry, name):
                    yield base / entry


def authored(pol: dict, pattern: str):
    """Every authored file matching `pattern` -- generated, vendored and IGNORED trees excluded.

    🔴 Dedup by REAL path, not by the `Path` the glob happened to yield. `@wom/.agents` is a
    symlink to `w0m-web/.agents` (T312, multi-agent parity) and the glob traverses it, so the
    same inode is walked twice under two different-looking paths -- the estate root's alias and
    w0m-web's own copy. Without this, 3 SKILL.md files with a heading emoji were counted TWICE,
    moving the ratchet +5 with no new content. Excluding `.agents` in `exclude_paths` (the k7
    remedy) was tried and rejected: that filter matches a bare component anywhere in the path, so
    it also dropped w0m-web's real, non-symlinked copy and under-counted. Resolving and deduping
    here fixes this alias and any future one -- `.claude/skills`, or a symlink not yet added --
    without a per-symlink entry to maintain.
    """
    skip = set(pol["exclude_paths"])
    candidates = [
        p
        for p in _pruned_glob(pattern, skip)
        # `w0m-ext/extension/export.md` is a DIRECTORY named .md
        if not any(s in p.parts for s in skip) and p.is_file()
    ]
    ignored = _ignored(candidates)
    seen_real: set[Path] = set()
    for p in candidates:
        if p in ignored:
            continue
        real = p.resolve()
        if real in seen_real:
            continue
        seen_real.add(real)
        yield p


def protocol_glyphs(pol: dict) -> set[str]:
    """Every glyph a declared parser reads, as a set of characters.

    These are EXCLUDED from the script-output ratchet, and the reason is not convenience. The
    probe for this gate found it: writing a test that prints its results raised the count the
    ratchet measures, because the estate's suite runner counts results BY those glyphs. A ratchet
    that counts protocol glyphs is a ratchet whose only way to go green is to break the parser.
    So the zone measures DECORATIVE emoji in output -- which is precisely what the owner asked to
    prohibit -- and the protocol tier handles the rest.
    """
    return {ch for c in pol["protocol"]["couplings"] for ch in c["reads"]}


def staged_files() -> list[Path] | None:
    """Paths staged for commit (added/copied/modified/renamed). None if git cannot answer.

    🔴 None is not an empty list. A git failure means we could not scope the change, and the caller
    must fall back to the whole-tree measurement rather than pass over nothing — the same
    unmeasurable-is-not-zero rule the deploy hook now follows (T242, T267).
    """
    # 🔴 cwd=WEB, NOT ESTATE. Corrected 2026-09-08: `@wom` IS a git repo now (casualuser/w0m,
    # tracked 2026-09-02, T312 paid down D32 and its row is gone). The fallback below is still
    # right and still needed — it must fire whenever `git diff --cached` cannot scope a change,
    # for ANY reason, not just a repo-less cwd. Originally written as: "`@wom` is not a git repo
    # — that is recorded debt D32" — so
    # `git diff --cached` there exits non-zero and this returns None. Written with cwd=ESTATE the
    # first time and it did exactly that: the fallback fired on every run and the staged mode never
    # executed. The estate's own documented trap, walked into while fixing a scoping bug.
    # ⚠️ This measures W0M_WEB's index, which is where `.husky/pre-commit` lives and where the
    # corpus's governance docs are. A commit in a sibling repo falls back to the whole-tree run.
    try:
        r = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"],
                           capture_output=True, text=True, cwd=WEB, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    return [WEB / n for n in r.stdout.split("\0") if n]


def _emoji_headings(text: str, proto: set[str], E: re.Pattern) -> int:
    return sum(1 for line in text.splitlines()
               if line.startswith("#") and any(ch not in proto for ch in E.findall(line)))


def staged_delta(pol: dict, E: re.Pattern) -> tuple[list[str], str | None]:
    """(regressions, unmeasurable_reason) — files whose emoji headings INCREASED vs HEAD.

    🔑 Why a DELTA and not a count. The ratchet compares a whole-corpus total to a baseline. Count
    only the staged files and the total is trivially under the baseline, so the gate would pass on
    everything — that is not narrowing it, it is switching it off. The question a pre-commit run can
    honestly answer is *does this change make it worse*, which is per-file and needs HEAD to compare
    against.

    ⚠️ A file new to the index has no HEAD version, so its baseline is 0 and any non-protocol emoji
    heading is a regression. That is intended: new files are where new headings come from.
    """
    files = staged_files()
    if files is None:
        return [], "git could not list the staged set"
    proto = protocol_glyphs(pol)
    skip = set(pol["exclude_paths"])
    out: list[str] = []
    for f in files:
        if f.suffix != ".md" or any(s in f.parts for s in skip):
            continue
        try:
            now = _emoji_headings(f.read_text(encoding="utf-8", errors="replace"), proto, E)
        except OSError:
            continue
        rel = f.relative_to(ESTATE)
        # ⚠️ `git show` against the file's OWN repo, not the estate — the estate root is not a repo
        # (D32), and `HEAD:` there resolves to nothing. Resolve the repo from the path.
        repo = f
        while repo != ESTATE and not (repo / ".git").exists():
            repo = repo.parent
        inner = f.relative_to(repo) if repo != ESTATE else rel
        h = subprocess.run(["git", "show", f"HEAD:{inner}"],
                           capture_output=True, text=True, cwd=repo)
        before = _emoji_headings(h.stdout, proto, E) if h.returncode == 0 else 0
        if now > before:
            out.append(f"{rel}: {before} -> {now} non-protocol emoji heading(s)")
    return out, None


def count_zones(pol: dict, E: re.Pattern) -> dict[str, int]:
    """The two ratchet zones, measured the same way every run."""
    proto = protocol_glyphs(pol)
    heads = 0
    for p in authored(pol, "*/**/*.md"):
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            # Same rule as the output zone, for the same reason. `## <star> PICK UP HERE` is a
            # heading whose glyph `state_doctor.py` READS -- the ratchet counting it would demand
            # that state rotation be broken to go green. Found when writing a handoff pushed this
            # zone +1 and the gate, correctly, refused.
            if line.startswith("#") and any(ch not in proto for ch in E.findall(line)):
                heads += 1
    out = 0
    emit = re.compile(r"\b(print|log|echo)\b")
    for p in authored(pol, "*/project/scripts/**/*.py"):
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            if not emit.search(line):
                continue
            # Count only NON-protocol pictographs. A line whose only emoji are declared protocol
            # is the parser's contract being honoured, not decoration to remove.
            if any(ch not in proto for ch in E.findall(line)):
                out += 1
    return {"md_headings_estate": heads, "script_output": out}


def hard_violations(pol: dict, E: re.Pattern) -> list[str]:
    """Emoji in a governance doc's headings. Zero tolerance, because this is what broke."""
    bad = []
    for rel in pol["hard"]["files"]:
        f = ESTATE / rel
        if not f.exists():
            bad.append(f"{rel}: DECLARED in the policy but does not exist -- fix the declaration")
            continue
        for i, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if line.startswith("#") and E.search(line):
                bad.append(f"{rel}:{i}: {line[:72]}")
    return bad


#: A glyph is READ AS DATA when it sits in a matcher position: a regex character class, a
#: `startswith` tuple, a dict key, a set membership test, an equality comparison, a `split`
#: argument. This is deliberately broad — a false positive costs one declaration line, a false
#: negative costs a silently-green gate.
MATCHER_CTX = re.compile(
    r"re\.compile|re\.match|re\.search|re\.findall|startswith|endswith|removeprefix|"
    r"lstrip|strip\(|in \(|in \[|in \{|== |!= |\.split\(|GLYPH|MARKER"
)


def discovered_couplings(pol: dict, E: re.Pattern) -> dict[str, set[str]]:
    """{ "file.py:line": {glyphs} } for every glyph sitting in a matcher position.

    🔴 **Why this exists, and it is the sharpest lesson of T256.** The `protocol.couplings` list was
    written from what I found by grepping and reading — six entries, then a seventh when a handoff
    heading broke. Then a systematic sweep found **ten undeclared load-bearing glyphs across roughly
    fifteen files**. `✗` alone is read by `run_suites.py`, `tools_check.py`, `tools_upgrade.py` and
    `w0m_audit.py`, and every one of those sites was in the bucket the gate called *decorative* —
    i.e. safe to clean up. Cleaning them would have stopped four suites counting their checks.

    🔑 So the hand-written list committed exactly the defect the gate exists to catch: **it was a
    remembered list presented as a measurement.** This function makes it a measurement. Declared
    must now be a SUPERSET of discovered, and the gate fails otherwise — which means a new matcher
    cannot be added without declaring it, and no future sweep can find something the policy missed.
    """
    out: dict[str, set[str]] = {}
    for base, sub in ((ESTATE, ESTATE / "scripts"), (WEB, WEB / "project" / "scripts")):
        if not sub.is_dir():
            continue
        for p in sorted(sub.rglob("*.py")):
            for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if not MATCHER_CTX.search(line):
                    continue
                if line.lstrip().startswith("#"):
                    # A comment naming a glyph is documentation, not a matcher. Excluding it is what
                    # keeps this from flagging the very comments that explain the couplings.
                    continue
                glyphs = {c for c in E.findall(line)}
                if glyphs:
                    out[f"{p.relative_to(base)}:{i}"] = glyphs
    return out


def undeclared_couplings(pol: dict, E: re.Pattern) -> list[str]:
    """Matcher sites whose glyphs are not covered by any declaration. Declared ⊇ discovered."""
    declared = protocol_glyphs(pol)
    # Top-level, beside `exclude_paths`: an exemption is a statement about a SITE, not about
    # the protocol, and nesting it under `protocol` implied the opposite.
    #
    # A key may be `path/to/file.py:LINE` or bare `path/to/file.py`.
    #
    # 🔬 Both forms exist because the line form proved brittle the first time it was used: adding
    # five probes ABOVE two exempt fixtures moved them from :128/:129 to :154/:155 and the gate went
    # red on entries that had not changed. That failure is in the right DIRECTION -- loud, not
    # silent -- but for a probe file whose fixture lines churn by nature it is pure noise. So a
    # probe file is exempt whole, and a production false positive stays pinned to its line, where
    # precision matters and edits are rare.
    exempt = {k for k in pol.get("discovery_exempt", {}) if not k.startswith("$")}
    bad = []
    for site, glyphs in discovered_couplings(pol, E).items():
        if site in exempt or site.rsplit(":", 1)[0] in exempt:
            continue
        missing = sorted(g for g in glyphs if g not in declared)
        if missing:
            bad.append(f"{site}: reads {''.join(missing)} in a matcher position, undeclared")
    return bad


def broken_couplings(pol: dict) -> list[str]:
    """A declared parser that no longer contains the glyph it is declared to read.

    This fires in the direction nobody watches: someone 'cleans up' the PARSER, the producers keep
    emitting the glyph, and the parser silently matches nothing. That is how a suite runner starts
    reporting zero checks and passing.
    """
    broken = []
    for c in pol["protocol"]["couplings"]:
        f = ESTATE / c["parser"]
        if not f.exists():
            broken.append(f"{c['parser']}: declared as a parser but the file is gone")
            continue
        body = f.read_text(encoding="utf-8", errors="replace")
        missing = [g for g in c["reads"] if g not in body]
        if missing:
            broken.append(
                f"{c['parser']}: no longer contains {''.join(missing)} -- it is declared to read "
                f"it ({c['why']}). Either the parser stopped matching, or the declaration is stale."
            )
    return broken


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    ap.add_argument(
        "--staged", action="store_true",
        help="PRE-COMMIT mode (T267 AC8): measure the DELTA on staged files instead of the "
             "whole-tree ratchet. Answers 'does this change make it worse', which is the only "
             "question a commit can honestly be held to. The whole-corpus ratchet still runs at "
             "pre-push, where the invariant belongs.")
    a = ap.parse_args()

    if not POLICY.exists():
        print("emoji-check: project/policies/emoji-policy.json is missing -- cannot measure, not passing.")
        return 2
    try:
        pol = load()
    except json.JSONDecodeError as e:
        print(f"emoji-check: project/policies/emoji-policy.json does not parse ({e}). The POLICY is broken, "
              f"not this gate -- fix the JSON. Not passing.")
        return 2
    E = emoji_re(pol)

    # ── PRE-COMMIT: the delta on the staged change only ─────────────────────────────────────
    # 🔴 This mode exists because the whole-tree run blocked a commit over an UNTRACKED file that
    # nobody was committing (2026-08-24, an audit report a second agent dropped into docs/reports).
    # Unstaging did not help — the corpus is a filesystem glob, not the index. A gate that blocks on
    # files outside your change leaves `--no-verify` as the only exit, and that is prohibited here.
    # ⚠️ It does NOT replace the ratchet. The whole-corpus count runs at pre-push; see .husky/.
    if a.staged:
        regressions, unmeasurable = staged_delta(pol, E)
        if unmeasurable:
            # Could not scope the change -> fall back to the full measurement rather than pass.
            # "I could not tell" must never render as "clean".
            print(f"emoji-check --staged: {unmeasurable}; falling back to the whole-tree ratchet.")
        else:
            hard = hard_violations(pol, E)
            if hard:
                print("\nemoji-check (staged) -- HARD ZONE violation(s):")
                for h in hard:
                    print(f"      {h}")
                return 1
            if regressions:
                print("\nemoji-check (staged) -- this change ADDS non-protocol emoji heading(s):")
                for r in regressions:
                    print(f"      {r}")
                print("\n  Headings in governance docs are a hard zero, and the estate-wide count "
                      "only ever falls.\n  Remove the glyph -- the heading text carries the "
                      "meaning. Raising the baseline is the\n  same act as deleting a failing "
                      "test.")
                return 1
            print(f"emoji-check (staged) -- {len(staged_files() or [])} staged file(s), no new "
                  f"emoji headings. The whole-corpus ratchet runs at pre-push.")
            return 0

    zones = count_zones(pol, E)
    if not any(zones.values()):
        # An empty measurement is a broken reader, not a clean estate (T240).
        print("emoji-check: measured 0 emoji in BOTH zones. The estate had 5184 on 2026-08-22; a "
              "zero here means the matcher or the walk is broken, so this is a failure, not a pass.")
        return 2

    hard = hard_violations(pol, E)
    broken = broken_couplings(pol)
    undeclared = undeclared_couplings(pol, E)
    rose = {k: (v, pol["ratchet"]["zones"][k]["baseline"])
            for k, v in zones.items() if v > pol["ratchet"]["zones"][k]["baseline"]}
    fell = {k: (v, pol["ratchet"]["zones"][k]["baseline"])
            for k, v in zones.items() if v < pol["ratchet"]["zones"][k]["baseline"]}

    if a.json:
        print(json.dumps({"zones": zones, "hard": hard, "broken_couplings": broken,
                          "undeclared_couplings": undeclared,
                          "discovered_sites": len(discovered_couplings(pol, E)),
                          "rose": rose, "fell": fell}, indent=2))
        return 1 if (hard or broken or undeclared or rose) else 0

    print(f"emoji-check -- {zones['md_headings_estate']} heading occurrence(s), "
          f"{zones['script_output']} script-output line(s)")

    print(f"\n  PROTOCOL -- {len(pol['protocol']['couplings'])} declaration(s) covering "
          f"{len(discovered_couplings(pol, E))} discovered matcher site(s), printed every run "
          f"because the dependency is invisible in the code:")
    for c in pol["protocol"]["couplings"]:
        print(f"      {c['parser']} reads {c['reads']}  -- {c['why']}")

    for k, (now, base) in fell.items():
        print(f"\n  RATCHET IMPROVED  {k}: {now} < baseline {base}. Lower the baseline to {now} "
              f"in emoji-policy.json, or the gate stops holding the ground you just took.")

    if broken:
        print(f"\n  BROKEN COUPLING -- {len(broken)}:")
        for b in broken:
            print(f"      {b}")

    if undeclared:
        print(f"\n  UNDECLARED COUPLING -- {len(undeclared)} matcher site(s) read a glyph the "
              f"policy does not declare:")
        for u in undeclared:
            print(f"      {u}")
        print("\n  A glyph read in a matcher position is PROTOCOL whether or not anyone wrote it")
        print("  down, and an undeclared one sits in the 'decorative' bucket -- i.e. the bucket")
        print("  something will eventually 'clean up', stopping that reader silently. Declare it")
        print("  with the reason, or add the site to `discovery_exempt` if it is a false")
        print("  positive (a glyph in a print on a line that merely also contains a comparison).")

    if rose:
        print(f"\n  RATCHET BREACHED -- {len(rose)}:")
        for k, (now, base) in rose.items():
            print(f"      {k}: {now} > baseline {base} (+{now - base})")
        print("     Raising a baseline to go green is the same act as deleting a failing test.")

    if hard:
        print(f"\n  HARD ZONE -- {len(hard)} emoji in a governance doc's headings:")
        for h in hard:
            print(f"      {h}")
        print("\n  A heading is cited by number from other files. A pictograph between the hashes")
        print("  and the number is why a grep for section 33 reported no match while seven tickets")
        print("  correctly cited it. Remove the emoji; the section text stays.")

    if hard or broken or undeclared or rose:
        return 1
    print("\n  [OK] governance headings are clean, every declared coupling holds, no zone rose.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
