#!/usr/bin/env python3
r"""T256 -- probes for `emoji-check`.

The gate has three tiers and each one can fail in a different direction, so each is probed
separately. The load-bearing probes are the two about the BOUNDARY, because the whole risk in
obeying "prohibit emoji" is over-application:

  * the typographic marks must NOT count. The estate writes `session -> device -> user` with a real
    arrow glyph, and TECH-DEBT uses the section sign. They are single-width, carry no variation
    selector, and no matcher here has ever broken on one. A gate that flagged them would be
    applying the rule's letter against its reason, and would fire thousands of times on prose that
    was never the problem.
  * an emoji in the BODY of a governance doc must not count either. Only headings are the hard
    zone, because a heading is what other files cite by number.

Note what this file is forced to do: it prints its own results with the very glyphs the policy
calls PROTOCOL, because `run_suites.py:44` counts probe results by matching them. That is the
coupling in the flesh -- de-emojify this output and the suite runner reports zero checks and
passes. Which is exactly why the gate asserts the coupling instead of banning the glyph.

Run: `just emoji-check-test`
"""

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "wom7web"
sys.path.insert(0, str(ROOT / "scripts"))

import emoji_policy_check as g  # noqa: E402

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'✅' if ok else '❌'} {label}")
    if not ok:
        failures.append(f"{label} — {detail}")


print("▶ T256 — emoji-check\n")

POL = g.load()
E = g.emoji_re(POL)

# ── the definition: what IS and IS NOT an emoji ─────────────────────────────────────────────────
for glyph, name in [("✅", "check mark"), ("🔴", "red circle"), ("⚠️", "warning sign"),
                    ("🚪", "door"), ("💤", "sleep"), ("▶", "play marker")]:
    check(f"{name} is matched as an emoji", bool(E.search(glyph)), f"{glyph!r} slipped through")

# 🔬 The boundary probe. Over-application is the real risk of this instruction.
for glyph, name in [("→", "arrow"), ("—", "em-dash"), ("·", "middot"), ("§", "section sign"),
                    ("─", "box-drawing rule"), ("«", "guillemet")]:
    check(f"{name} is NOT treated as an emoji",
          not E.search(glyph),
          f"{glyph!r} is typographic, single-width, and no matcher has broken on it — flagging it "
          f"would fire on thousands of lines that were never the problem")

# ── the hard zone: headings only ────────────────────────────────────────────────────────────────
def hard_over(text: str, name: str = "ROADMAP.md"):
    """Run hard_violations() against a fixture file rather than the real governance doc."""
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / name).write_text(text, encoding="utf-8")
        pol = {**POL, "hard": {**POL["hard"], "files": [name]}}
        orig_estate = g.ESTATE
        orig_web = g.WEB
        g.ESTATE = d
        g.WEB = d
        try:
            return g.hard_violations(pol, E)
        finally:
            g.ESTATE = orig_estate
            g.WEB = orig_web


check("an emoji in a HEADING is a violation",
      len(hard_over("## 🚪 33. Client Closed Beta\n")) == 1)
check("a clean heading is not a violation",
      hard_over("## 33. Client Closed Beta\n") == [])
# 🔬 narrowness: the body is the ratchet's business, not the hard zone's.
check("an emoji in the BODY is NOT a hard violation",
      hard_over("## 33. Client Closed Beta\n\n🔴 this matters a lot\n") == [],
      "only headings are cited by number; banning body prose here would make the tier unlandable")
check("a DECLARED governance file that does not exist is itself reported",
      len(hard_over("## fine\n", name="ROADMAP.md")) == 0
      and any("does not exist" in v for v in g.hard_violations(
          {**POL, "hard": {**POL["hard"], "files": ["NO-SUCH-FILE.md"]}}, E)),
      "a policy naming a file that is gone must fail loudly, not silently cover nothing")

# ── the protocol couplings ──────────────────────────────────────────────────────────────────────
check("every declared coupling holds against the REAL parsers",
      g.broken_couplings(POL) == [],
      "a declared parser no longer contains the glyph it is declared to read")

broken = g.broken_couplings({**POL, "protocol": {"couplings": [
    {"parser": "scripts/run_suites.py", "reads": "🦄", "why": "fixture"}]}})
check("a parser MISSING its declared glyph is reported", len(broken) == 1,
      "this is the direction nobody watches: clean up the parser, producers keep emitting, the "
      "matcher silently matches nothing and the suite passes on zero checks")

gone = g.broken_couplings({**POL, "protocol": {"couplings": [
    {"parser": "scripts/no_such_parser.py", "reads": "✅", "why": "fixture"}]}})
check("a declared parser file that is GONE is reported", len(gone) == 1)

# ── the ratchet ─────────────────────────────────────────────────────────────────────────────────
zones = g.count_zones(POL, E)
base = {k: v["baseline"] for k, v in POL["ratchet"]["zones"].items()}
check("the ratchet baselines match the gate's OWN measurement",
      zones == base,
      f"measured {zones} vs declared {base} — a baseline measured a different way than the gate "
      f"measures is how this gate first reported a 754-heading improvement it had not earned")

# ── non-vacuity ─────────────────────────────────────────────────────────────────────────────────
# 🔬 Non-vacuity, restated after T257 AC1 drove script_output to ZERO. The original probe read
# `zones["script_output"] > 100`, which asserted that decorative output emoji must EXIST -- i.e. it
# would have failed at the exact moment the work succeeded. A probe that breaks on success is
# measuring the wrong thing: non-vacuity here means the READER still sees a real corpus, not that
# the corpus still contains offenders.
# ⚠️ The floor was 1000 while the corpus was measured off the FILESYSTEM. Correcting `authored()`
# to skip what the repos ignore (T261, 2026-08-23) removed 2,536 headings that lived in a scraped
# data vault and a Supabase backup, taking the honest count to 476 — so the old floor now asserts
# that the gate must keep counting files nobody wrote. 300 is set below the corrected count and
# well above the "someone broke the walker" range; the paired corpus probes below are what
# actually discriminate, and this stays as the coarse tripwire it was.
check("the reader still measures a substantial corpus (non-vacuous)",
      zones["md_headings_estate"] > 200 and len(g.discovered_couplings(POL, E)) > 20,
      f"got headings={zones['md_headings_estate']}, "
      f"sites={len(g.discovered_couplings(POL, E))}")
check("reaching ZERO in a zone is a pass, not a vacuity failure",
      zones["script_output"] == POL["ratchet"]["zones"]["script_output"]["baseline"],
      "a zone at its baseline is compliant whatever the number — including 0")
check("generated trees are excluded by DECLARATION, not by luck",
      "graphify-out" in POL["exclude_paths"],
      "graphify-out holds 31 emoji headings per generated report; counting them as authored text "
      "is what made the first baseline wrong")
# The real bug this hit: `wom7ext/extension/export.md` is a DIRECTORY named `.md`.
check("a DIRECTORY named *.md does not crash the walk",
      all(p.is_file() for p in g.authored(POL, "*/**/*.md")),
      "IsADirectoryError on wom7ext/extension/export.md killed the first measurement outright")

# ── the DISCOVERY check: declared must be a superset of discovered ──────────────────────────────
# 🔴 These probes exist because the hand-written coupling list was WRONG. It had six entries, then
# seven; a systematic sweep found 18 undeclared matcher sites out of 45, and three were real readers
# -- including run_suites.py's other three dialects, whose glyphs were sitting in the DECORATIVE
# bucket. A remembered list presented as a measurement is the exact defect this gate exists to
# catch, and the list had it. So the list is now derived from a sweep, and these probes hold that.
check("the sweep finds a substantial number of matcher sites (non-vacuous)",
      len(g.discovered_couplings(POL, E)) > 20,
      f"only {len(g.discovered_couplings(POL, E))} — a sweep that finds nothing declares everything safe")
check("every discovered matcher site is declared or explicitly exempt",
      g.undeclared_couplings(POL, E) == [],
      f"{g.undeclared_couplings(POL, E)}")
check("a comment naming a glyph is NOT counted as a matcher",
      not any("#" in site for site in g.discovered_couplings(POL, E)),
      "excluding comments is what stops the sweep flagging the very notes that explain the couplings")
# 🔬 The load-bearing one: run_suites has FOUR dialects and the first declaration named one pair.
check("run_suites' declaration covers every glyph its dialect regexes read",
      all(gl in next(c["reads"] for c in POL["protocol"]["couplings"]
                     if c["parser"].endswith("run_suites.py"))
          for gl in "✅❌ℹ✓✗×"),
      "TICK reads the cross/tick/times trio and NODE_TEST the info glyph; naming only the first "
      "pair left four glyphs classified as decorative, i.e. safe to delete")
check("every exemption carries a stated reason",
      all(len(v) > 40 for k, v in POL["discovery_exempt"].items() if not k.startswith("$")),
      "an exemption without a reason is a suppression")

# ── CORPUS: authored means "not ignored", and the filter must discriminate ──────────────────────
# 🔴 Added 2026-08-23 (T261). `authored()` used to glob the filesystem and call the result
# authored, so a scheduled Supabase Storage backup writing 652 markdown files into a gitignored
# path moved this BLOCKING ratchet by +1 — leaving only two apparent remedies, both wrong: raise
# the baseline, or delete a backup. 2,536 of the then-3,012 counted headings were in trees the
# repos are configured never to keep. These two checks are a pair on purpose: the first proves the
# filter EXCLUDES what git ignores, the second proves it has not simply excluded everything.
def _corpus_paths():
    return {p.resolve() for p in g.authored(POL, "*/**/*.md")}


_corpus = _corpus_paths()
_ignored_sample = WEB / "project" / "data" / "upwork_vault" / "README.md"
_authored_sample = WEB / "README.md"

check("a gitignored markdown file is NOT in the authored corpus",
      not _ignored_sample.exists() or _ignored_sample.resolve() not in _corpus,
      f"{_ignored_sample} is excluded by .gitignore; counting it makes the ratchet move whenever "
      "a scraper or a backup runs, which is a number nobody can act on")
check("a tracked markdown file IS in the authored corpus",
      _authored_sample.resolve() in _corpus,
      "the ignore filter must not swallow the corpus it is meant to clean — an empty corpus "
      "passes every ratchet")

# 🔴 Added 2026-09-05 (T312 follow-up). `@wom/.agents` is a symlink to `wom7web/.agents` (T312,
# multi-agent parity), and the glob traverses it — so the same file was walked twice under two
# different-looking paths and its heading emoji counted twice, moving the ratchet +5 with no new
# content. `authored()` now dedups by `Path.resolve()`; this proves it with a minimal fixture
# rather than trusting the live estate to still contain a reproducing symlink tomorrow.
with tempfile.TemporaryDirectory() as _td:
    _root = Path(_td)
    (_root / "real" / "skill").mkdir(parents=True)
    (_root / "real" / "skill" / "SKILL.md").write_text("## 🔴 heading\n", encoding="utf-8")
    (_root / "alias").symlink_to(_root / "real", target_is_directory=True)
    _real_estate = g.ESTATE
    g.ESTATE = _root
    try:
        _dup_corpus = list(g.authored({"exclude_paths": []}, "*/**/*.md"))
    finally:
        g.ESTATE = _real_estate
    check("a symlinked alias of an already-authored file is counted ONCE, not twice",
          len(_dup_corpus) == 1,
          f"found {len(_dup_corpus)} — a dot-directory symlink (like `.agents`) traversed by the "
          "glob must collapse to the one file it actually is, or the ratchet moves on an alias "
          "with no new content, exactly as T312's `.agents` link did")

# ── MUTATION: prove the hard tier discriminates ─────────────────────────────────────────────────
check("MUTATION: a heading-BLIND rule finds 0 where the real one finds 1",
      len(hard_over("## 🚪 33. x\n")) == 1
      and len([l for l in ["## 🚪 33. x"] if not l.startswith("#") and E.search(l)]) == 0,
      "if the reader stopped anchoring on the heading marker, the tier would silently cover nothing")

# ── T267 AC8 — the STAGED delta mode, and why it is a delta ─────────────────────────────────────
#
# 🔴 The bug it fixes: on 2026-08-24 the whole-tree run blocked a commit over an UNTRACKED file that
# nobody was committing — a second agent's audit report dropped into docs/reports/. Unstaging did
# not help, because `authored()` globs the FILESYSTEM, not the index. A gate that blocks on files
# outside your change leaves `--no-verify` as the only way past, and that is prohibited here.
#
# 🔑 And the obvious narrowing would have DISABLED it. The ratchet compares a whole-corpus COUNT to
# a baseline; counting only the staged files puts every commit trivially under it. So the staged
# mode asks a different question — *does this change make it worse* — per file, against HEAD.

_proto = g.protocol_glyphs(POL)

check("staged mode: a DECORATIVE glyph in a heading counts",
      g._emoji_headings("# \U0001F5C2\uFE0F Catalog\n\nbody\n", _proto, E) == 1)
check("staged mode: a PROTOCOL glyph in a heading does NOT count",
      g._emoji_headings("# \U0001F534 Finding\n\nbody\n", _proto, E) == 0,
      "the red circle is declared — authz_bucket_gate_test.py reads it — so counting it would "
      "demand breaking a parser to go green. This probe was written after a first test used that "
      "very glyph and read the gate's correct silence as a miss.")
check("staged mode: a glyph in BODY text is not a heading violation",
      g._emoji_headings("body \U0001F5C2\uFE0F text\n", _proto, E) == 0,
      "the hard tier is headings; prose typography is a separate, ratcheted concern")

# 🔴 UNMEASURABLE is not zero. If git cannot list the index we fall back to the whole-tree run
# rather than reporting a clean staged set — "I could not tell" must never render as "clean".
_real_run = g.subprocess.run
g.subprocess.run = lambda *a, **k: (_ for _ in ()).throw(OSError("git missing"))
_files = g.staged_files()
g.subprocess.run = _real_run
check("staged mode: an unusable git returns None (UNMEASURABLE), never an empty list",
      _files is None,
      "an empty list would read as 'nothing staged, all clear' and pass the commit silently")

# ⚠️ The repo root, not the estate root. `@wom` is NOT a git repo (D32), so a `git diff --cached`
# rooted there fails on every run — which is exactly what the first implementation did, making the
# staged mode dead on arrival while looking wired.
check("staged mode: the staged diff runs against a real REPO, not the non-repo estate root",
      "cwd=WEB" in (ROOT / "scripts/emoji_policy_check.py").read_text(encoding="utf-8"),
      "D32: the estate root is not a git repo; rooting the diff there returns None every time")

print()
if failures:
    print(f"❌ {len(failures)} failure(s):")
    for f in failures:
        print(f"   · {f}")
    sys.exit(1)
print("✅ headings are hard, couplings are asserted, typography is left alone, zones are ratcheted")
