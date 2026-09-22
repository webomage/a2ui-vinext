#!/usr/bin/env python3
"""Audit: does every ticket match the ACTIVE ticket schema? (T163)

`ac_trace_check.py` answers "can the ranker see this ticket's AC state". It says nothing
about the rest of the file — frontmatter keys, enum values, required sections. A ticket can
be perfectly countable and still carry a `queue:` value no board section exists for, or be
missing `## Definition of Done` entirely. That drift is invisible until someone greps for it.

The schema of record is `project/templates/ticket.md`. This reads the template's own
frontmatter to derive the required key set, so the check CANNOT drift from the template the
way a hardcoded list would — the estate's most-repeated defect is a check that only looks
where it already knows to look.

    ticket_schema_check.py            advisory report, exit 0
    ticket_schema_check.py --enforce  exit 1 on any ERROR
    ticket_schema_check.py --json     machine-readable

ERROR vs WARN: an ERROR is a value nothing downstream can interpret (unknown status, a
`queue` no board section matches). A WARN is a documented-shape gap — a missing optional
section, or a key used widely but absent from the template, which is drift in the TEMPLATE
rather than in the ticket.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "wom7web"
TICKETS = ROOT / ".tasks"
if not TICKETS.is_dir():
    sys.exit(f"FATAL: Canonical tickets directory not found at {TICKETS} (AgDR-0025: zero silent fallbacks)")
TEMPLATE = ROOT / "project" / "templates" / "ticket.md"
if not TEMPLATE.is_file():
    sys.exit(f"FATAL: Canonical ticket template not found at {TEMPLATE} (AgDR-0025: zero silent fallbacks)")
SCHEMA_FILE = WEB / "project" / "tickets-schema.jsonc"
if not SCHEMA_FILE.is_file():
    sys.exit(f"FATAL: Canonical ticket schema not found at {SCHEMA_FILE} (AgDR-0025: zero silent fallbacks)")
SDLC_FILE = ROOT / ".w0m" / "sdlc.json"

# Enum values that downstream ACTUALLY understands — derived from the CONSUMER, not from the
# template's prose comments. Both of the first two checks written here were wrong precisely
# because they trusted the template: it says `P0 | P1 | P2 | (blank)`, while the ranker has
# scored `P3` all along (`PRIORITY_WEIGHT["P3"] = 10`). A schema check sourced from a comment
# is a check that only looks where it already knows to look.
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(WEB / "project" / "scripts"))
import tasks_query as tq  # noqa: E402
from authz_blanket_gate import strip_jsonc  # noqa: E402  (one JSONC reader, not two)

# ── the schema of record (T228 AC1) ──────────────────────────────────────────
# The vocabularies below USED to be literals here. They now come from one declared file that
# `sync_github.py` reads as well, because the defect that motivated it was invisible while each
# consumer held its own copy: the sync builds `area:*` labels from `repos`, so that namespace has
# always meant something different from the field it is named after, and no file said otherwise.
#
# 🔴 A declared vocabulary is a CLAIM, not a fact. `reconcile_consumers()` below checks it against
# the code that actually acts on these values, and an unreconciled schema is reported as an ERROR —
# the whole point is that the file cannot quietly diverge from the ranker the way the template did.
SCHEMA = json.loads(strip_jsonc(SCHEMA_FILE.read_text()))
_VOCAB = SCHEMA["vocabularies"]

CLOSED_FOR_DOD = {"done", "archived"}
# ⚠️ Same VALUES as CLOSED_FOR_DOD today, deliberately a separate name: that set answers "is this
# exempt from needing a Definition of Done", this one answers "has this ticket closed". They can
# diverge — if `archived` ever stops being DoD-exempt, only one of them should move — and collapsing
# two questions into one constant is how a rule gets applied where it was never decided.
CLOSED_STATUSES = {"done", "archived"}
VALID_STATUS = set(_VOCAB["status"]["values"])
VALID_PRIORITY = set(_VOCAB["priority"]["values"]) | ({""} if _VOCAB["priority"].get("allow_empty") else set())
KNOWN_QUEUE = set(_VOCAB["queue"]["values"])
VALID_AREA = set(_VOCAB["area"]["values"])
# T239 AC7. ⚠️ Read the mapping too, not just the values: `sync_github.py` needs the exact string
# `gh issue close --reason` accepts, and "not planned" carries a SPACE — an identifier-shaped guess
# would fail at the call site instead of here.
# T242 AC5b — our P0–P3 spelling stays canonical; GitHub's org issue field is the projection. Read
# here so the correspondence can be CHECKED rather than trusted: a silent inversion (P0 -> Low) is
# the one edit that is both easy and catastrophic, and GitHub's `rank` is the only place the ordering
# is data at all (ProjectV2 select options carry no rank).
GH_PRIORITY_MAP: dict[str, dict] = dict(
    (_VOCAB["priority"].get("gh_issue_field") or {}).get("map") or {})
# T242 AC5b — the NATURE-of-work axis. Adopted with GitHub's names, so the "map" is identity by
# design rather than by accident; the reader below still checks it, because an identity mapping that
# quietly loses a value is exactly as broken as a scrambled one.
VALID_ISSUE_TYPE = set(_VOCAB["issue_type"]["values"])
GH_ISSUE_TYPE: dict[str, str] = dict(_VOCAB["issue_type"].get("gh_issue_type") or {})
VALID_CLOSED_AS = set(_VOCAB["closed_as"]["values"])
GH_CLOSE_REASON: dict[str, str] = dict(_VOCAB["closed_as"]["gh_reason"])
AREA_ALIASES = _VOCAB["area"].get("aliases", {})
AREA_CLOSED = bool(_VOCAB["area"].get("closed"))
# 🔴 ADDED 2026-08-25. `repos` was declared `vocabulary: "repo"` in the schema and checked by
# NOTHING — the field had a contract and no reader, which is the same shape as a gate that cannot
# fail. Found while adopting T282, whose `research` LOOKED undeclared against `.w0m/sdlc.json`
# (7 real repos) and is in fact one of the vocabulary's 17 values. ⚠️ That mis-reading is the
# reason this check exists: measuring against the wrong source produced a confident wrong verdict,
# and only a check pinned to the DECLARED vocabulary can settle it.
VALID_REPO = set(_VOCAB["repo"]["values"])

# ── epic & milestone (T239 AC1, AC3b, AC5) ──────────────────────────────────
VALID_EPIC = set((_VOCAB.get("epic") or {}).get("values", []))
EPIC_ALIASES = (_VOCAB.get("epic") or {}).get("aliases", {})
EPIC_CLOSED = bool((_VOCAB.get("epic") or {}).get("closed"))

try:
    _SDLC = json.loads(strip_jsonc(SDLC_FILE.read_text(encoding="utf-8")))
except Exception:
    _SDLC = {}
VALID_MILESTONES = {m["id"]: m for m in _SDLC.get("milestones", []) if "id" in m}


def check_milestones_conformance() -> list[str]:
    """Check .w0m/sdlc.json milestones configuration (T239 AC3b)."""
    errs: list[str] = []
    for m in _SDLC.get("milestones", []):
        mid = m.get("id", "")
        mem = m.get("membership", "")
        if not mid:
            errs.append("SDLC: milestone has no `id`")
        if mem not in ("declared", "derived"):
            errs.append(f"SDLC: milestone `{mid}` membership `{mem}` not in ('declared', 'derived')")
        if mem == "declared":
            tickets = m.get("tickets", [])
            for tid in tickets:
                if ALL_TICKET_IDS and tid not in ALL_TICKET_IDS:
                    errs.append(f"SDLC: declared milestone `{mid}` cites ticket `{tid}` which does not exist")
        elif mem == "derived" and "tickets" in m:
            errs.append(f"SDLC: derived milestone `{mid}` should not specify a `tickets` list (membership is derived from ticket frontmatter)")
    return errs

# 🔴 ADDED 2026-08-25 with the ticket-entity standard. Five declared fields had NO reader —
# `created`, `epic`, `spec`, `tags`, `title` — so a contract could be declared and never checked.
# `tags` stays unchecked BY DESIGN (113 of 153 appear exactly once; it is a search hint, not a
# taxonomy) and `title` is a judgement no gate can make. The other three are mechanical.
_ROADMAP = ROOT / "ROADMAP.md"


def _roadmap_sections() -> set[str]:
    try:
        t = _ROADMAP.read_text(encoding="utf-8")
    except OSError:
        return set()          # unreadable -> check nothing rather than fail everything
    return (set(re.findall(r"^#{2,4}\s*(\d+(?:\.\d+)?)\.", t, re.M))
            | set(re.findall(r"\*\*(\d+\.\d+)\s", t)))


ROADMAP_SECTIONS = _roadmap_sections()
ALL_TICKET_IDS = {f.stem for f in TICKETS.glob("T*.md")}
REPO_CLOSED = bool(_VOCAB["repo"].get("closed"))


def reconcile_consumers() -> list[str]:
    """Check the declared vocabularies against the code that consumes them.

    Returns ERROR strings. Each relation is declared in the schema's `reconcile` block with its
    reasoning, because the two relations are NOT interchangeable and getting that wrong has already
    produced a false report:

      equal    — the consumer's domain IS the whole domain (priority: the ranker scores every value)
      superset — the schema legitimately knows more (status: STATUS_WEIGHT scores only ACTIONABLE
                 states, so `done` is absent by design; demanding equality flagged 40 finished
                 tickets as invalid)
    """
    errs: list[str] = []
    consumers = {
        "tasks_query.PRIORITY_WEIGHT": set(tq.PRIORITY_WEIGHT),
        "tasks_query.STATUS_WEIGHT": set(getattr(tq, "STATUS_WEIGHT", {})),
    }
    for rule in SCHEMA.get("reconcile", []):
        name, cname, rel = rule["vocabulary"], rule["consumer"], rule["relation"]
        if cname not in consumers:
            continue  # not statically importable (e.g. the sync's label builder) — checked there
        declared = set(_VOCAB[name]["values"])
        if name == "priority" and _VOCAB[name].get("allow_empty"):
            declared.add("")
        actual = consumers[cname]
        if rel == "equal" and declared != actual:
            errs.append(
                f"SCHEMA/CONSUMER DRIFT: `{name}` declares {sorted(declared)} but {cname} "
                f"has {sorted(actual)} (relation=equal) — one of them is wrong"
            )
        elif rel == "superset" and not actual <= declared:
            errs.append(
                f"SCHEMA/CONSUMER DRIFT: {cname} accepts {sorted(actual - declared)} which "
                f"`{name}` does not declare (relation=superset)"
            )
    try:
        import sync_epic_vocabulary as sev
        errs.extend(sev.check_drift())
    except Exception as ex:
        errs.append(f"EPIC VOCABULARY DRIFT CHECK FAILED: {ex}")
    errs.extend(check_milestones_conformance())
    return errs

def check_gh_issue_type_map() -> list[str]:
    """Every declared `issue_type` must project onto exactly one GitHub type name, and distinctly.

    ⚠️ The map is an IDENTITY (bug->Bug), which is the easiest kind to leave unchecked and the
    easiest to break silently: drop one key and those tickets project no type at all, while every
    other verdict stays green. Absent is not a failure — it applies only once the tracker is
    org-owned — but declared-and-incomplete is.
    """
    if not GH_ISSUE_TYPE:
        return []
    errs: list[str] = []
    missing = sorted(VALID_ISSUE_TYPE - set(GH_ISSUE_TYPE))
    if missing:
        errs.append(f"SCHEMA: issue_type.gh_issue_type omits {missing} — those tickets would project "
                    f"no type at all while everything else reports green")
    extra = sorted(set(GH_ISSUE_TYPE) - VALID_ISSUE_TYPE)
    if extra:
        errs.append(f"SCHEMA: issue_type.gh_issue_type declares {extra}, which the vocabulary rejects")
    names = list(GH_ISSUE_TYPE.values())
    if len(set(names)) != len(names):
        errs.append(f"SCHEMA: two issue_types collapse onto one GitHub name {names} — the projection "
                    f"loses information")
    return errs


def check_gh_priority_map() -> list[str]:
    """The P0–P3 -> Urgent/High/Medium/Low projection must be COMPLETE and ORDER-PRESERVING.

    🔴 Order is the whole point. `P0` means *most urgent* and GitHub's `rank` is *lowest = most
    urgent*, so the mapping is order-preserving only if sorting our values by their own severity
    yields ranks in ascending order. An inversion would be a one-character edit, would look
    plausible in review, and would silently invert severity everywhere the projection is read.
    ⚠️ Absent is NOT a failure — the mapping only applies once the tracker is org-owned (T242).
    But a mapping that EXISTS and is wrong must fail, so "not declared" and "declared badly" are
    reported as different things.
    """
    if not GH_PRIORITY_MAP:
        return []
    errs: list[str] = []
    declared = [v for v in _VOCAB["priority"]["values"]]          # P0..P3, most urgent first
    missing = [v for v in declared if v not in GH_PRIORITY_MAP]
    if missing:
        errs.append(f"SCHEMA: priority.gh_issue_field.map omits {missing} — a partial projection "
                    f"sends some tickets to GitHub with no priority at all")
    extra = [k for k in GH_PRIORITY_MAP if k not in declared]
    if extra:
        errs.append(f"SCHEMA: priority.gh_issue_field.map declares {extra}, which `priority` does "
                    f"not — mapping a value the vocabulary rejects")
    raw_ranks = [GH_PRIORITY_MAP[v].get("rank") for v in declared if v in GH_PRIORITY_MAP]
    if any(r is None for r in raw_ranks):
        errs.append("SCHEMA: a priority mapping has no `rank` — the rank IS the ordering; without "
                    "it the projection cannot be checked for inversion")
        return errs      # a missing rank makes every ordering claim below unmeasurable
    ranks: list[int] = [int(r) for r in raw_ranks if r is not None]
    if ranks != sorted(ranks):
        errs.append(f"SCHEMA: priority mapping is NOT order-preserving — {declared} maps to ranks "
                    f"{ranks}; P0 must carry the LOWEST rank (GitHub: lowest = most urgent). A "
                    f"silent inversion here inverts severity everywhere it is read")
    if len(set(ranks)) != len(ranks):
        errs.append(f"SCHEMA: duplicate ranks {ranks} — two priorities cannot share one position")
    names = [GH_PRIORITY_MAP[v].get("name") for v in declared if v in GH_PRIORITY_MAP]
    if len(set(names)) != len(names):
        errs.append(f"SCHEMA: duplicate target names {names} — two of our values collapse into one "
                    f"GitHub option, so the projection loses information")
    return errs


# Sections the template defines. `Status notes` is genuinely optional (a fresh ticket has no
# history yet); the other three carry meaning the SDLC gates read.
REQUIRED_SECTIONS = ["Summary", "Acceptance criteria", "Definition of Done", "Links"]
OPTIONAL_SECTIONS = ["Status notes"]

FM = re.compile(r"^---\n(.*?)\n---\n", re.S)
KEY = re.compile(r"^([a-z_]+):\s*(.*?)\s*$")


def frontmatter(text: str) -> dict[str, str] | None:
    m = FM.match(text)
    if not m:
        return None
    out: dict[str, str] = {}
    for line in m.group(1).splitlines():
        km = KEY.match(line)
        if km:
            # strip a trailing `# enum | comment` without eating a value containing '#'
            out[km.group(1)] = re.sub(r"\s+#.*$", "", km.group(2)).strip()
    return out


def template_keys() -> list[str]:
    """Required keys ARE whatever the template declares — never a second hardcoded list."""
    fm = frontmatter(TEMPLATE.read_text())
    return list(fm) if fm else []


def optional_keys() -> set[str]:
    """Keys the template DECLARES but does not REQUIRE, written as `# OPTIONAL <key>:`.

    🔴 Needed because `template_keys()` makes every frontmatter key mandatory. `blocked_by` is read
    by tasks_query.py and ticket_deps.py, so tickets using it were warned as "not in the template" —
    but adding it as a live key turned **227 tickets red in a single edit** (measured 2026-08-18).
    A field can be known without being demanded, and this is how that is said.
    """
    return set(re.findall(r"^#\s*OPTIONAL\s+(\w+)\s*:", TEMPLATE.read_text(), re.M))


# An AC line that is ticked, plus its text up to the next AC/blank-line boundary.
AC_TICKED = re.compile(r"^- \[x\]\s*(?P<body>AC\d+.*?)(?=^- \[[ x]\]|^\S|\Z)", re.M | re.S | re.I)
# Phrases that mean "this was NOT delivered", split by STRENGTH — because the first version could
# not tell the two apart and produced a false positive on T34 AC4, whose deliverables all exist and
# whose caveat is "XP-threshold numerics left open for domain input": one PARAMETER of a delivered
# AC, not the AC. "not built"/"not implemented" NEGATE delivery; "left open" routinely qualifies a
# sub-detail of something that was in fact delivered. So the first errors and the second only warns
# — a human reads the warn. A rule that cannot distinguish these must not be the one that blocks.
UNBUILT_STRONG = ("not built", "not implemented", "not delivered", "not done here")
UNBUILT_WEAK = ("left open", "deliberately open")


def check(path: Path, required: list[str]) -> tuple[list[str], list[str], dict]:
    text = path.read_text()
    errors: list[str] = []
    warns: list[str] = []
    fm = frontmatter(text)
    if fm is None:
        return [f"no YAML frontmatter"], [], {}

    for k in required:
        if k not in fm:
            errors.append(f"missing frontmatter key `{k}`")
    extra = [k for k in fm if k not in required and k not in optional_keys()]
    for k in extra:
        warns.append(f"key `{k}` not in the template (template drift, not ticket drift)")

    st, q, pr = fm.get("status", ""), fm.get("queue", ""), fm.get("priority", "")
    if st not in VALID_STATUS:
        errors.append(f"status `{st}` not in {sorted(VALID_STATUS)}")
    if q not in KNOWN_QUEUE:
        warns.append(f"queue `{q or '(empty)'}` not a known value — but nothing reads `queue`, "
                     f"so this breaks nothing; the field is vestigial")
    if pr not in VALID_PRIORITY:
        errors.append(f"priority `{pr}` not scored by the ranker "
                       f"{sorted(v for v in VALID_PRIORITY if v)} (or blank)")

    # ── issue type (T242 AC5b) ───────────────────────────────────────────────
    ity = fm.get("type", "")
    if ity and ity not in VALID_ISSUE_TYPE:
        # 🔬 CORRECTED 2026-08-25 — and the correction is narrower than it first looked.
        # The reason read "it projects onto a GitHub issue type, so an unknown value cannot be
        # projected at all", in the PRESENT tense. Measured: `repository.issueTypes` is null and
        # 60/60 issues have none. But the estate already knew — `tickets-schema.jsonc` records
        # `applies_when: "the tracker repo is owned by an ORGANISATION"`, and `updateIssueIssueType`
        # was already proven on a probe issue. ⇒ The projection is BUILT and WAITING, not missing.
        # 🔑 So the defect was only the tense: a message asserting as current fact something its own
        # schema records as conditional. Naming the precondition is what a reader can act on —
        # "not today" alone would send them looking for unwritten code.
        errors.append(f"type `{ity}` not in {sorted(VALID_ISSUE_TYPE)} — the vocabulary that "
                      f"projects onto a GitHub issue type ONCE THE TRACKER IS ORG-OWNED "
                      f"(`tickets-schema.jsonc -> issue_type.applies_when`; `repository.issueTypes` "
                      f"is null for a User-owned repo, so nothing projects it today). The mapping "
                      f"and mutation are already proven — see T242")

    # ── closed_as (T239 AC7) ─────────────────────────────────────────────────
    ca = fm.get("closed_as", "")
    if ca and ca not in VALID_CLOSED_AS:
        errors.append(f"closed_as `{ca}` not in {sorted(VALID_CLOSED_AS)} — it maps to GitHub's "
                      f"stateReason enum, so an unknown value cannot be projected at all")
    if ca and st not in CLOSED_STATUSES:
        errors.append(f"closed_as `{ca}` on a `{st}` ticket — it says HOW a ticket closed, so on an "
                      f"open one it is a claim about an event that has not happened")

    # ── area (T228 AC4) ──────────────────────────────────────────────────────
    # ⚠️ Reported as a WARN while `closed: false`, and that is deliberate, not laziness. Twenty
    # spellings are in use; erroring today would fail a large share of the corpus at once, which is
    # the un-passable gate T135 AC8 forbids. The schema's `closed` flag flips as part of the
    # normalisation migration, and this promotes to an ERROR with it — one edit, in the data.
    ar = fm.get("area", "")
    if ar not in VALID_AREA:
        alias = AREA_ALIASES.get(ar)
        if alias:
            msg = f"area `{ar}` is an alias of `{alias['to']}` ({alias['why']}) — normalise it"
        else:
            msg = f"area `{ar or '(empty)'}` is not a declared area {sorted(VALID_AREA)}"
        (errors if AREA_CLOSED else warns).append(msg)

    # ── repos against the DECLARED vocabulary, not against the real repo list ──────────
    # ⚠️ Warns rather than errors while `repo.closed` is false, matching `area` above: the
    # vocabulary deliberately holds non-repos (`research`, `branding`, `recruit`, `tooling`) and
    # its own `why_open` defers closing to a decision, not to this file. Promotes with the flag.
    # 🔴 `frontmatter()` returns dict[str, str] — EVERY value is a string. Iterating `repos`
    # directly walks CHARACTERS, which took the warning count from 15 to 3278 on the first run and
    # is why that number is worth reading rather than glancing at.
    for rp in [x.strip().strip("\"'") for x in (fm.get("repos") or "").strip("[]").split(",") if x.strip()]:
        if rp not in VALID_REPO:
            (errors if REPO_CLOSED else warns).append(
                f"repo `{rp}` is not in the declared repo vocabulary {sorted(VALID_REPO)}")

    # ── epic (T239 AC1, AC5) ───────────────────────────────────────────────────
    # Validates against the declared closed vocabulary in tickets-schema.jsonc (derived from ROADMAP.md).
    _unq = lambda v: v.strip().strip('"\'').strip()
    ep = _unq(fm.get("epic", ""))
    if ep:
        if VALID_EPIC and ep not in VALID_EPIC:
            alias = EPIC_ALIASES.get(ep)
            if alias:
                msg = f"epic `{ep}` is an alias of `{alias['to']}` ({alias['why']}) — normalise it"
            else:
                msg = f"epic `{ep}` is not in the declared epic vocabulary (ROADMAP.md sections §1–§34)"
            (errors if EPIC_CLOSED else warns).append(msg)
        elif not VALID_EPIC and ROADMAP_SECTIONS:
            m_ep = re.search(r"§\s*(\d+(?:\.\d+)?)", ep)
            if m_ep and m_ep.group(1) not in ROADMAP_SECTIONS:
                warns.append(f"epic cites `§{m_ep.group(1)}`, which is not a section in ROADMAP.md")

    # ── milestone (T239 AC3b) ──────────────────────────────────────────────────
    # Flat primitive declared in .w0m/sdlc.json -> milestones.
    ms = _unq(fm.get("milestone", ""))
    if ms:
        if VALID_MILESTONES and ms not in VALID_MILESTONES:
            errors.append(f"milestone `{ms}` is not declared in .w0m/sdlc.json -> milestones {sorted(VALID_MILESTONES)}")

    # ── spec points at a file that exists ──────────────────────────────────────────────
    sp = _unq(fm.get("spec", ""))
    if sp and not ((WEB / sp).exists() or (ROOT / sp).exists()):
        warns.append(f"spec `{sp}` does not resolve to a path")

    # ── a Summary, and cross-references that resolve ───────────────────────────────────
    if "## Summary" not in text:
        warns.append("no `## Summary` — the section that says why the ticket exists")
    for ref in sorted(set(re.findall(r"\[\[(T\d+)\]\]", text))):
        if ALL_TICKET_IDS and ref not in ALL_TICKET_IDS:
            # ERROR, not a warning: this is 0 today, so it can only ever mean new breakage.
            errors.append(f"`[[{ref}]]` points at a ticket that does not exist")

    # id must match the filename, or cross-references silently point at the wrong ticket.
    if fm.get("id") and fm["id"] != path.stem:
        errors.append(f"id `{fm['id']}` does not match filename `{path.stem}`")

    # ── a ticked AC may not declare itself unbuilt (found on T230, 2026-08-18) ──────────
    # 🔴 The `sdlc` board scores a ticket by counting `- [x]`. T230's AC7 was ticked while its own
    # text said "Not built here on purpose", and while BOTH the ticket's status note and its
    # TASKS.md row said 6/7 — so the board reported a PLAN-MONITORING ticket at 100%, by the exact
    # failure mode that ticket exists to prevent. The tick is the cheapest thing in a ticket to get
    # wrong and the only thing the ranking reads, so it is worth a machine check.
    for m in AC_TICKED.finditer(text):
        body = m.group("body")
        low = body.lower()
        strong = next((w for w in UNBUILT_STRONG if w in low), None)
        weak = next((w for w in UNBUILT_WEAK if w in low), None)
        if strong:
            errors.append(f"AC ticked `[x]` but its text says {strong!r} — the sdlc board counts "
                          f"checkboxes, so this inflates the ticket's completion: "
                          f"{body.strip()[:70]}…")
        elif weak:
            warns.append(f"AC ticked `[x]` and its text says {weak!r} — check whether that refers "
                         f"to the AC or only to a detail inside it: {body.strip()[:70]}…")

    # ── an AC-shaped line the RANKER cannot count (T228, found 2026-08-19) ──────────────
    # 🔴 `tasks_query.py` counts `- [state] **AC<n>` with NO space between AC and the digit. T211
    # and T212 wrote `**AC 1 (…)**`, so **12 real criteria were invisible**: T212 was scored as
    # "no acceptance criteria" and excluded from the sdlc board entirely, and T211's completion
    # record could not be read either. One space.
    # ⚠️ This is the inverse of the placeholder case and must not be confused with it: 20 tickets
    # legitimately carry `- [ ] **Not yet written.**` and are CORRECTLY unmeasurable. The defect is
    # only when a criterion IS written and the id shape hides it.
    for m in re.finditer(r"^\s*-\s*\[[ xX~]\]\s*\*{0,2}(AC[\s_.-]+\d)", text, re.M):
        errors.append(f"acceptance criterion id {m.group(1)!r} is not countable — the ranker matches "
                      f"`AC<n>` with no separator, so this criterion is INVISIBLE to the board")

    # 🔴 Sections are parsed as (heading, body) PAIRS, not collected into a set. A set was the
    # defect: it silently collapsed duplicates, so T228's own record carried **three verbatim
    # 144-line copies** of its AC5/AC8/AC5b sections and this check reported it green (T228,
    # 2026-08-20). The copies came from an ad-hoc `str.replace("## Definition of Done", ...)`
    # insertion — an UNANCHORED substring rewrite. It hit the one real heading plus three table
    # rows that merely *mentioned* the section, split each row at column 0, and thereby minted
    # three counterfeit headings that this very check then accepted as evidence the required
    # section was present. **A gate satisfied by the corruption it should have caught.**
    parts = re.split(r"^(##+\s*.+?)\s*$", text, flags=re.M)
    sections = [(parts[i].strip(), parts[i + 1]) for i in range(1, len(parts) - 1, 2)]
    heads = {h.split(None, 1)[1] if " " in h else h for h, _ in sections}

    # Rule 1 — a heading is a HEADING, never a fragment of a table or a sentence. A `|` or an odd
    # backtick count means the line is prose that a rewrite broke, and such a line can SATISFY the
    # required-section test below, which is why this is an ERROR and not a cosmetic warning.
    for h, _ in sections:
        txt = h.lstrip("#").strip()
        if "|" in txt or txt.count("`") % 2:
            errors.append(f"heading {txt[:60]!r} is not a section — it is a table row or sentence "
                          f"split at column 0. It can SATISFY a required-section check while "
                          f"carrying none of the content")

    # Rule 2 — the same section twice with the same content. Always a duplicated write; never
    # authored. ⚠️ Compared on STRIPPED bodies: a first cut compared raw text and the probe for
    # this very rule failed, because the last copy in a file carries one less trailing newline
    # than the ones an anchor follows. Byte-identity would have missed a duplicate that differs
    # only in whitespace — which is most of them.
    seen: dict[tuple[str, str], int] = {}
    for h, b in sections:
        sect_key = (h, b.strip())          # not `k`: reused as a str above, and mypy caught it
        seen[sect_key] = seen.get(sect_key, 0) + 1
    for (h, _), n in seen.items():
        if n > 1:
            errors.append(f"section {h.lstrip('#').strip()[:50]!r} appears {n}× VERBATIM — "
                          f"a duplicated write, not a revision")

    # Rule 3 vs 4 — a REQUIRED section must be unique, because every consumer reads the first
    # match and the rest is content nobody will ever see. A repeated *narrative* heading with
    # DIFFERENT text is how these tickets legitimately accumulate dated findings, so that warns.
    counts: dict[str, int] = {}
    for h, _ in sections:
        counts[h] = counts.get(h, 0) + 1
    for h, n in counts.items():
        if n < 2 or seen.get((h, next(b for hh, b in sections if hh == h).strip()), 0) > 1:
            continue   # already reported by Rule 2 as a verbatim duplicate
        txt = h.lstrip("#").strip()
        if any(txt.lower().startswith(s.lower()) for s in REQUIRED_SECTIONS):
            errors.append(f"required section `{txt[:40]}` appears {n}× — consumers read the "
                          f"first, so the other {n - 1} are invisible")
        else:
            warns.append(f"heading `{txt[:40]}` appears {n}× with differing content")

    for s in REQUIRED_SECTIONS:
        if any(s.lower() in h.lower() for h in heads):
            continue
        # 🔴 A CLOSED ticket cannot acquire a Definition of Done retroactively. The DoD asserts the
        # ticket met `SPEC-AUTHORING-STANDARD.md` on the way out — and many done tickets predate
        # that standard, so writing one now would be inventing a claim about how they closed, not
        # recording one. 20 of the 43 originally-missing DoDs were on done/archived tickets; those
        # are exempt rather than backfilled. Every OPEN ticket still needs one (T228, 2026-08-19).
        if s.lower().startswith("definition of done") and st in CLOSED_FOR_DOD:
            continue
        warns.append(f"missing section `## {s}`")

    return errors, warns, {"status": st, "queue": q, "priority": pr}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--enforce", action="store_true", help="exit 1 on any ERROR")
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args()

    required = template_keys()
    if not required:
        print("❌ cannot read the template's frontmatter — no schema to check against",
              file=sys.stderr)
        return 1

    files = sorted(TICKETS.glob("T*.md"), key=lambda p: int(re.sub(r"\D", "", p.stem) or 0))
    if not files:
        # An empty corpus is a failure, not a pass — the estate's standing rule.
        print("❌ no ticket files found — refusing to report green over an empty set",
              file=sys.stderr)
        return 1

    # The schema is checked against its consumers BEFORE any ticket is read. If the two disagree,
    # every per-ticket verdict below was measured against a vocabulary that is already wrong, and
    # reporting 223 green tickets under a broken schema is the exact vacuous-green shape this
    # estate keeps rediscovering.
    # T242 AC5b — the P0–P3 -> GitHub projection is checked here for the same reason: a mapping that
    # inverts severity would make every per-ticket priority verdict below meaningless.
    schema_errs = reconcile_consumers() + check_gh_priority_map() + check_gh_issue_type_map()

    # Annotated, not inferred. Adding the SCHEMA row below narrowed mypy's element type and broke
    # the loops further down — the same shape as the T188 note there: a container whose type is
    # inferred from its first literal is a container that changes meaning when you add a second.
    report: list[dict[str, Any]] = []
    n_err, n_warn = len(schema_errs), 0
    if schema_errs:
        report.append({"ticket": "SCHEMA", "errors": schema_errs, "warnings": []})
    for f in files:
        e, w, meta = check(f, required)
        n_err += len(e)
        n_warn += len(w)
        if e or w:
            report.append({"ticket": f.stem, "errors": e, "warnings": w, **meta})

    if args.as_json:
        print(json.dumps({"checked": len(files), "errors": n_err,
                          "warnings": n_warn, "rows": report}, indent=2))
        return 1 if (args.enforce and n_err) else 0

    print(f"▶ ticket schema — {len(files)} tickets against {TEMPLATE.relative_to(ROOT)}\n")
    errs = [r for r in report if r["errors"]]
    if errs:
        print(f"── 🔴 ERRORS ({sum(len(r['errors']) for r in errs)}) — values nothing downstream can interpret ──")
        for r in errs:
            for e in r["errors"]:
                print(f"  {r['ticket']:<6} {e}")
        print()
    # Group warnings by kind: 159 copies of one line is noise, the COUNT is the signal.
    kinds: dict[str, list[str]] = {}
    for r in report:
        # `warning`, not `w`: `w` is already bound above as the warnings LIST
        # (`e, w, meta = check(...)`). Re-using it for a single warning string made
        # `setdefault` look like it was keyed on a list (T188).
        for warning in r["warnings"]:
            kinds.setdefault(warning, []).append(r["ticket"])
    if kinds:
        print(f"── [WARN] WARNINGS ({n_warn}), grouped ──")
        for warning, ts in sorted(kinds.items(), key=lambda kv: -len(kv[1])):
            shown = ", ".join(ts[:6]) + (f" +{len(ts)-6} more" if len(ts) > 6 else "")
            print(f"  {len(ts):>4}×  {warning}\n         {shown}")
        print()
    if not n_err and not n_warn:
        print("✅ every ticket matches the active schema")
    else:
        print(f"{n_err} error(s), {n_warn} warning(s)")
    return 1 if (args.enforce and n_err) else 0


if __name__ == "__main__":
    raise SystemExit(main())
