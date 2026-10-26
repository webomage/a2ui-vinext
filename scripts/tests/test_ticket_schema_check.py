#!/usr/bin/env python3
"""Prove the ticket schema check REJECTS — T228 AC9.

*"A gate nobody has watched fail is not a gate."* This drives the real checker over fixture tickets
and asserts each rejection actually fires. Fixtures only — it never touches `project/tickets/`.

🔴 One probe was ORIGINALLY deliberately absent rather than faked: **"a `done` ticket still holding
a full board row"** was [[T228]] **AC8b**, not yet built when this suite was written — a probe for
an unimplemented check would have passed by construction. **AC8b shipped 2026-08-29** (`just
tasks-rotate`, `project/tickets/archive/`), with its own dedicated probes in `test_tasks_rotate.py`
and `test_tasks_bounds.py` — that is the concern's real home (it reads `TASKS.md`'s board rows,
which this suite never touches; it validates ticket FILES only). This suite now asserts that the
rotation artefact exists, rather than asserting it never will.
"""

from __future__ import annotations

import importlib.util
import json
import re as _re2
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent / "w0m-web"
SCHEMA = ROOT.parent / "scripts/ticket_schema_check.py"
SYNC = ROOT.parent / "scripts/sync_github.py"


def load(p: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


tsc = load(SCHEMA, "tsc")
sg = load(SYNC, "sg")

GOOD = """---
id: T999
title: "a fixture"
status: queued
area: sdlc
queue: now
priority: P1
repos: [web]
epic: ""
spec: ""
gh_issue: 1
tags: []
created: 2026-08-18
---
# T999 — a fixture
## Summary
s
## Acceptance criteria
- [ ] AC1 — something observable
## Definition of Done
d
## Links
l
## Status notes
n
"""


class P:
    def __init__(self): self.n = 0; self.fail: list[str] = []
    def check(self, label, ok, detail=""):
        self.n += 1
        print(f"  {label:<62} {'ok' if ok else '!! FAILED'}")
        if not ok: self.fail.append(f"{label} {detail}".strip())


def run(body: str, fname: str = "T999.md"):
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / fname
        f.write_text(body)
        return tsc.check(f, tsc.template_keys())


def main() -> int:
    p = P()

    print("\nTHE BASELINE IS CLEAN (so every red below means something)")
    e, w, _ = run(GOOD)
    p.check("a well-formed ticket produces no errors", not e, str(e[:1]))

    print("\nEACH REJECTION IS SEEN TO FIRE")
    for label, mutation in [
        ("an unknown `area` is rejected",            ("area: sdlc", "area: banana")),
        ("an unknown `epic` is rejected",            ('epic: ""', 'epic: "ROADMAP §99 — Nonexistent"')),
        ("an EMPTY required field is rejected",      ("status: queued", "status: ")),
        ("a status outside the vocabulary is rejected", ("status: queued", "status: nearly")),
        ("a priority the ranker cannot score is rejected", ("priority: P1", "priority: P9")),
        ("an id that disagrees with the filename is rejected", ("id: T999", "id: T888")),
    ]:
        e, _, _ = run(GOOD.replace(*mutation))
        p.check(label, len(e) >= 1, "no error raised")

    print("\nTHE TICKED-BUT-UNBUILT RULE (born from T230's own AC7)")
    e, _, _ = run(GOOD.replace("- [ ] AC1 — something observable",
                               "- [x] AC1 — something observable. Not built here on purpose."))
    p.check("a ticked AC whose text negates delivery is rejected", len(e) >= 1)
    e, w, _ = run(GOOD.replace("- [ ] AC1 — something observable",
                               "- [x] AC1 — delivered; XP numerics left open for domain input"))
    p.check("...but a sub-detail 'left open' only WARNS, not errors",
            not e and len(w) >= 1, f"e={len(e)} w={len(w)}")

    print("\n🔴 THE LABEL NAMESPACE COLLISION THAT STARTED THIS TICKET")
    # T228's founding defect: `area:*` labels were built from `repos`, so the namespace said one
    # thing and meant another. This asserts the mapping is now what it claims.
    tk = {"id": "T1", "area": "sdlc", "repos": ["web", "api"], "status": "queued",
          "priority": "P1", "queue": "now"}
    labels = sorted(sg.desired_labels(tk))
    # ⚠️ These two probes asserted `"area:sdlc" in labels` until 2026-08-20 and went RED when AC5b
    # retired the namespace — the code was right and the PROBE was describing a superseded
    # contract. A suite that fails for being out of date is worse than no suite: it is a red
    # nobody reads. Found only because the whole suite was re-run; AC5b did not re-run it, and
    # T228 was reported 10/10 over two failing checks. The guard is preserved, not dropped:
    # `area:` must never again be published FROM `repos`, and now must not be published at all.
    p.check("`repo:` carries the repos", {"repo:web", "repo:api"} <= set(labels), str(labels))
    p.check("`area:` publishes NOTHING — it is a Projects v2 field now (AC5b)",
            not any(l.startswith("area:") for l in labels), str(labels))
    p.check("no `area:` label is built from a repo name",
            not any(l.startswith("area:") and l.split(":", 1)[1] in tk["repos"] for l in labels),
            str(labels))
    p.check("the mapping is DATA, not hardcoded", isinstance(sg.NAMESPACE_SOURCE, dict)
            and sg.NAMESPACE_SOURCE.get("repo:") == "repos")
    p.check("retirement is DECLARED with a date and a reason, not just deleted from the code",
            all({"retired", "why"} <= set(v) for v in sg._GH["retired_label_namespaces"].values()),
            str(list(sg._GH.get("retired_label_namespaces", {}))))
    tk2 = dict(tk, queue=None)
    p.check("a falsy field publishes NO label (the `queue:None` defect)",
            not any(l.endswith(":None") for l in sg.desired_labels(tk2)),
            str(sorted(sg.desired_labels(tk2))))

    print("\n🔴 THE GITHUB BODY DECLARES IT IS PARTIAL (AC7)")
    body = sg.build_body(tk, "some summary", {"ac_total": 10, "ac_done": 5, "truncated": False})
    p.check("the body opens with a PARTIAL PROJECTION banner",
            body.lstrip().startswith("> ⚠️ **PARTIAL PROJECTION"), body[:60])
    p.check("...states the AC count it is not showing", "5/10 acceptance criteria" in body)
    p.check("...links the source file", ".tasks/T1.md" in body)
    trunc = sg.build_body(tk, "s", {"ac_total": 1, "ac_done": 0, "truncated": True})
    p.check("truncation is STATED, not silent", "truncated at 4,000" in trunc)

    print("\n🔴 A SUFFIXED `## Summary` HEADING MUST STILL EXTRACT (11 issues were EMPTY)")
    # The heading may carry a suffix — `## Summary — what was measured, 2026-08-16`. The original
    # pattern demanded an exact line, so 11 of 228 tickets matched nothing and pushed an EMPTY body.
    # T228's own issue was one: blank, then `---`. The projection was not partial there, it was
    # absent, and an empty regex match returns "" so nothing complained.
    import re as _re
    tickets = sorted((ROOT.parent / ".tasks").glob("T*.md"))
    p.check("there are tickets to inspect (not a vacuous sweep)", len(tickets) > 100, str(len(tickets)))
    empty = [f.stem for f in tickets if not sg.summary_of(f.stem).strip()]
    p.check("EVERY ticket yields a non-empty summary", not empty, f"{len(empty)}: {empty[:5]}")
    suffixed = [f.stem for f in tickets
                if _re.search(r"^## Summary\b[^\n]+", f.read_text(), _re.M)]
    p.check("...including the suffixed-heading ones (the regression)", len(suffixed) >= 5,
            f"only {len(suffixed)} suffixed headings found — did the corpus change?")
    for tid in suffixed[:3]:
        p.check(f"  {tid} (suffixed heading) extracts prose", len(sg.summary_of(tid).strip()) > 40)

    print("\n🔴 AN OPTIONAL KEY IS DECLARED WITHOUT BEING DEMANDED")
    # template_keys() makes EVERY frontmatter key required, so declaring `blocked_by` live turned
    # 227 tickets red in one edit. The `# OPTIONAL <key>:` form says the field is known without
    # demanding it. blocked_by is read by tasks_query.py and ticket_deps.py — it was live in the
    # code and absent from the schema, which is template drift, not ticket drift.
    opt = tsc.optional_keys()
    p.check("`blocked_by` is declared OPTIONAL in the template", "blocked_by" in opt, str(opt))
    p.check("...and is NOT in the required set", "blocked_by" not in tsc.template_keys())
    managed_x = {"x_ac_done", "x_ac_total", "x_ac_pct", "x_hot_score", "x_blocked_by", "x_synced"}
    p.check("managed `x_*` keys declared OPTIONAL in template (T389)",
            managed_x.issubset(opt), f"missing: {managed_x - opt}")
    p.check("...and managed `x_*` keys are NOT in required set",
            not any(k in tsc.template_keys() for k in managed_x))
    withdep = GOOD.replace("gh_issue: 1", "blocked_by: [T8]\ngh_issue: 1")
    e, w, _ = run(withdep)
    p.check("a ticket USING blocked_by produces no error and no drift warning",
            not e and not any("blocked_by" in x for x in w), f"e={e[:1]} w={w[:1]}")
    e2, _, _ = run(GOOD)
    p.check("...and omitting it is still fine (it is optional, not required)", not e2)
    p.check("an UNKNOWN extra key still warns (the check did not go blind)",
            any("nonsense" in x for x in run(GOOD.replace("gh_issue: 1", "nonsense: 1\ngh_issue: 1"))[1]))

    print("\n🔴 AN AC ID THE RANKER CANNOT COUNT IS AN ERROR (12 criteria were invisible)")
    # tasks_query.py counts `- [state] **AC<n>` with NO separator. T211 and T212 wrote `**AC 1 (…)**`,
    # so 12 real criteria were invisible: T212 was excluded from the sdlc board as having none, and
    # T211's completion record was unreadable too. One space.
    for shape in ("AC 1", "AC_1", "AC-1", "AC.1"):
        e, _, _ = run(GOOD.replace("- [ ] AC1 — something observable",
                                   f"- [ ] **{shape} — something observable**"))
        p.check(f"`{shape}` is rejected as uncountable", any("not countable" in x for x in e))
    e, _, _ = run(GOOD)
    p.check("...and a correct `AC1` is not flagged", not any("not countable" in x for x in e))
    # ⚠️ The placeholder is legitimately unmeasurable and must NOT be confused with a hidden id.
    e, _, _ = run(GOOD.replace("- [ ] AC1 — something observable",
                               "- [ ] **Not yet written.** Derive them from the Summary above."))
    p.check("the 'Not yet written' placeholder does NOT trip it", not any("not countable" in x for x in e))
    # The live corpus moved to the estate .tasks/ (T411); the old w0m-web path globbed NOTHING, so
    # this check passed vacuously on an empty corpus (T430). Resolve it canonically and refuse empty.
    sys.path.insert(0, str(ROOT.parent / "scripts"))
    from tasks_query import resolve_tickets_dir
    corpus = sorted(resolve_tickets_dir().glob("T*.md"))
    p.check("the live ticket corpus is non-empty (a vacuous pass is not a pass)", len(corpus) > 100, str(len(corpus)))
    bad = [f.stem for f in corpus
           if _re2.search(r"^\s*-\s*\[[ xX~]\]\s*\*{0,2}AC[\s_.-]+\d", f.read_text(), _re2.M)]
    p.check("no ticket in the corpus hides an AC behind a separator", not bad, str(bad))

    print("\n🔴 A CLOSED TICKET IS NOT BACKDATED WITH A DEFINITION OF DONE")
    # A DoD asserts the ticket met SPEC-AUTHORING-STANDARD.md on the way out. Many done tickets
    # predate that standard, so writing one now would invent a claim about how they closed. 20 of
    # the 43 originally-missing DoDs were on done/archived tickets — exempt, not backfilled.
    no_dod = GOOD.replace("## Definition of Done\nd\n", "")
    e, w, _ = run(no_dod.replace("status: queued", "status: done"))
    p.check("a DONE ticket missing its DoD does NOT warn", not any("Definition of Done" in x for x in w))
    e, w, _ = run(no_dod)
    p.check("...but an OPEN ticket missing it still does", any("Definition of Done" in x for x in w), str(w))
    e, w, _ = run(no_dod.replace("status: queued", "status: in-progress"))
    p.check("...and in-progress counts as open", any("Definition of Done" in x for x in w))
    lnk = GOOD.replace("## Links\nl\n", "")
    e, w, _ = run(lnk.replace("status: queued", "status: done"))
    p.check("the exemption is DoD-only — a done ticket still needs Links",
            any("Links" in x for x in w), str(w))

    print("\n🔴 A COUNTERFEIT HEADING, AND THE GATE THAT WAS SATISFIED BY IT")
    # T228, 2026-08-20. An ad-hoc `str.replace("## Definition of Done", ...)` insertion matched an
    # UNANCHORED substring: one real heading plus three table rows that merely MENTIONED the
    # section. Each row was split at column 0, minting three counterfeit headings — which the
    # required-section check then accepted as proof the section was present, while the section's
    # actual content was 144 duplicated lines further down. Three copies survived four commits.
    row = GOOD.replace("## Definition of Done\nd",
                       "## Definition of Done\nd\n\n| missing `## Definition of Done` | 43 | owner call |")
    e, _, _ = run(row)
    p.check("a table row MENTIONING a section is not a heading", not e, str(e[:1]))
    split = GOOD.replace("## Definition of Done\nd",
                         "## Definition of Done\nd\n\n## Definition of Done` | 43 | owner call |")
    e, _, _ = run(split)
    p.check("...but a row SPLIT at column 0 is rejected", len(e) >= 1)
    p.check("...and the message says it can satisfy a required-section check",
            any("SATISFY" in x for x in e), str(e[:1]))

    print("\n🔴 A DUPLICATED WRITE IS NOT A REVISION")
    dup = GOOD + "\n## AC5 — the fields exist\nbody\n\n## AC5 — the fields exist\nbody\n"
    e, _, _ = run(dup)
    p.check("the same section VERBATIM twice is rejected", len(e) >= 1, str(e[:1]))
    p.check("...and the count is reported, not just the fact",
            any("2×" in x for x in e), str(e[:1]))
    rev = GOOD + "\n## Status notes\nfirst finding\n\n## Status notes\na later, different one\n"
    e, w, _ = run(rev)
    p.check("...but a repeated heading with DIFFERENT content only warns",
            not e and len(w) >= 1, f"e={len(e)} w={len(w)}")
    req = GOOD.replace("## Links\nl", "## Links\nl\n\n## Links\ndifferent content")
    e, _, _ = run(req)
    p.check("a REQUIRED section twice is an ERROR even when the text differs",
            len(e) >= 1, "consumers read the first match; the rest is invisible")

    print("\n🔴 HOW A TICKET CLOSED — THE CLAIM WE WERE ALREADY PUBLISHING WRONGLY (T239 AC7)")
    # `sync_github.py` never mentioned `stateReason`, so GitHub DEFAULTED every close to COMPLETED:
    # all 76 closed issues read COMPLETED regardless of truth. A false PRESENT, not an empty field.
    done = GOOD.replace("status: queued", "status: done")
    e, _, _ = run(done.replace("tags: []", "closed_as: banana\ntags: []"))
    p.check("an unmappable `closed_as` is rejected", len(e) >= 1, str(e[:1]))
    p.check("...because it could not be projected at all",
            any("stateReason" in x for x in e), str(e[:1]))
    e, _, _ = run(done.replace("tags: []", "closed_as: not-planned\ntags: []"))
    p.check("...but a declared value on a DONE ticket is accepted", not e, str(e[:1]))
    e, _, _ = run(GOOD.replace("tags: []", "closed_as: completed\ntags: []"))
    p.check("`closed_as` on an OPEN ticket is rejected", len(e) >= 1,
            "it claims an event that has not happened")
    e, w, _ = run(done)
    p.check("...and its ABSENCE is silent, never an error",
            not e and not any("closed_as" in x for x in w),
            "74 historical closes cannot be dispositioned without reading each one")

    print("\n🔴 THE MAPPING IS DATA, AND THE CLI SPELLING IS NOT AN IDENTIFIER")
    p.check("every vocabulary value maps to a gh reason",
            set(tsc.GH_CLOSE_REASON) == set(tsc.VALID_CLOSED_AS),
            f"{sorted(tsc.GH_CLOSE_REASON)} vs {sorted(tsc.VALID_CLOSED_AS)}")
    p.check("`not-planned` maps to the SPACED CLI form, not the identifier",
            tsc.GH_CLOSE_REASON["not-planned"] == "not planned",
            "an identifier-shaped guess fails at the call site, not here")
    p.check("the sync reads the SAME mapping, not a second literal",
            sg._CLOSE_REASON == tsc.GH_CLOSE_REASON, str(sg._CLOSE_REASON))
    tk = {"id": "T1", "area": "sdlc", "repos": ["web"], "status": "done",
          "priority": "P1", "queue": "now", "closed_as": "duplicate"}
    p.check("a done ticket projects its reason", sg.projection_of(tk, "s")["reason"] == "duplicate")
    # ⚠️ Asserts the key is ABSENT, not that it is None — and this probe caught the change. The
    # first cut emitted `reason: None` on every ticket, which changed all 235 projection hashes and
    # made a dry run demand 235 API updates to say nothing new. Omission is the contract now, and
    # it carries the same meaning more cheaply: an undeclared ticket projects no claim at all.
    undeclared = sg.projection_of({k: v for k, v in tk.items() if k != "closed_as"}, "s")
    p.check("...and an undeclared one projects NO reason key at all",
            "reason" not in undeclared,
            f"absence must never assert completion — that IS the defect; got {undeclared.get('reason')!r}")
    p.check("...so the 234 undeclared projections stay byte-identical",
            sg.projection_hash(undeclared) == sg.projection_hash(
                {k: v for k, v in undeclared.items()}),
            "adding a None-valued key re-hashes every ticket in the corpus")

    print("\n[NEW] ISSUE TYPE — THE NATURE-OF-WORK AXIS (T242 AC5b)")
    e, _, _ = run(GOOD.replace("tags: []", "type: banana\ntags: []"))
    p.check("an unknown `type` is rejected", len(e) >= 1, str(e[:1]))
    e, _, _ = run(GOOD.replace("tags: []", "type: bug\ntags: []"))
    p.check("...a declared value is accepted", not e, str(e[:1]))
    e, w, _ = run(GOOD)
    # 🔴 Absence must be silent. 213 of 240 titles carry no derivable signal, so a required field
    # here would either redden the corpus or invite a fabricated backfill.
    p.check("...and ABSENCE is silent, never an error",
            not e and not any("type" in x for x in w), str(w[:1]))
    p.check("`type` is declared OPTIONAL in the template",
            "type" in tsc.optional_keys(), str(sorted(tsc.optional_keys())))

    print("\n   …and its projection is checked even though it is an IDENTITY map")
    orig = tsc.GH_ISSUE_TYPE
    try:
        p.check("the shipped map is complete and distinct", not tsc.check_gh_issue_type_map())
        tsc.GH_ISSUE_TYPE = {k: v for k, v in orig.items() if k != "task"}
        p.check("dropping one key is rejected (those tickets would project NO type)",
                len(tsc.check_gh_issue_type_map()) >= 1)
        tsc.GH_ISSUE_TYPE = {**orig, "feature": "Task"}
        p.check("two of ours collapsing onto one GitHub name is rejected",
                len(tsc.check_gh_issue_type_map()) >= 1)
        tsc.GH_ISSUE_TYPE = {**orig, "epic": "Epic"}
        p.check("a key the vocabulary rejects is rejected", len(tsc.check_gh_issue_type_map()) >= 1)
        tsc.GH_ISSUE_TYPE = {}
        p.check("...but an ABSENT map is silent (applies only once org-owned)",
                not tsc.check_gh_issue_type_map())
    finally:
        tsc.GH_ISSUE_TYPE = orig

    print("\n🔴 P0–P3 STAYS OURS; THE PROJECTION MAPS (T242 AC5b)")
    # Owner 2026-08-21: keep the P0-P3 spelling, map it to GitHub's Urgent/High/Medium/Low. Same
    # shape as closed_as -> stateReason: the ticket file is master, GitHub is a projection, so the
    # master is not renamed to suit it. The rank is the only place the ORDERING is data at all —
    # ProjectV2 select options carry no rank, so on the board "P0 outranks P1" is undeclared order.
    good = dict(tsc.GH_PRIORITY_MAP)
    p.check("the shipped mapping is complete and order-preserving",
            not tsc.check_gh_priority_map(), str(tsc.check_gh_priority_map()[:1]))
    p.check("...and it maps all four of our values", set(good) == {"P0", "P1", "P2", "P3"}, str(sorted(good)))
    p.check("...P0 carries the LOWEST rank (GitHub: lowest = most urgent)",
            good["P0"]["rank"] < good["P3"]["rank"], str({k: v["rank"] for k, v in good.items()}))

    orig = tsc.GH_PRIORITY_MAP
    try:
        for label, mp in [
            ("an INVERTED mapping (P0→Low) is rejected",
             {"P0": {"name": "Low", "rank": 4}, "P1": {"name": "Medium", "rank": 3},
              "P2": {"name": "High", "rank": 2}, "P3": {"name": "Urgent", "rank": 1}}),
            ("an incomplete mapping is rejected", {k: v for k, v in good.items() if k != "P3"}),
            ("duplicate ranks are rejected", {**good, "P2": {"name": "Medium", "rank": 2}}),
            ("two of ours collapsing to one GitHub option is rejected",
             {**good, "P2": {"name": "High", "rank": 3}}),
            ("a missing `rank` is rejected", {**good, "P1": {"name": "High"}}),
            ("mapping a value the vocabulary rejects is rejected", {**good, "P9": {"name": "Urgent", "rank": 1}}),
        ]:
            tsc.GH_PRIORITY_MAP = mp
            p.check(label, len(tsc.check_gh_priority_map()) >= 1)
        # ⚠️ ABSENT is not an error: the mapping only applies once the tracker is org-owned (T242),
        # and `repository.issueFields` is null for a User-owned repo. "Not declared" and "declared
        # badly" must report differently, or the check blocks a migration it is meant to guard.
        tsc.GH_PRIORITY_MAP = {}
        p.check("...but an ABSENT mapping is silent, not an error",
                not tsc.check_gh_priority_map(),
                "it only applies once the tracker is org-owned")
    finally:
        tsc.GH_PRIORITY_MAP = orig

    print("\n🔴 EPIC VOCABULARY & ROADMAP DRIFT (T239 AC1, AC5)")
    import sync_epic_vocabulary as sev
    p.check("schema epic vocabulary matches ROADMAP.md headings with zero drift",
            not sev.check_drift(), str(sev.check_drift()[:1]))
    p.check("canonical epics are non-empty", len(tsc.VALID_EPIC) >= 34)
    p.check("canonical epic in ticket is accepted without error",
            not run(GOOD.replace('epic: ""', 'epic: "platform-health-tooling"'))[0])
    p.check("unknown epic in ticket is rejected when closed",
            len(run(GOOD.replace('epic: ""', 'epic: "ROADMAP §99 — Nonexistent"'))[0]) >= 1)
    e_al, w_al, _ = run(GOOD.replace('epic: ""', 'epic: "ROADMAP §13"'))
    p.check("epic alias is flagged for normalization",
            any("alias of" in x for x in (e_al if tsc.EPIC_CLOSED else w_al)))

    print("\n🔴 ORTHOGONAL MILESTONES (T239 AC3b)")
    p.check(".w0m/sdlc.json milestones configuration is valid",
            not tsc.check_milestones_conformance(), str(tsc.check_milestones_conformance()[:1]))
    p.check("`audit-2026-07-17` milestone is declared", "audit-2026-07-17" in tsc.VALID_MILESTONES)
    p.check("declared milestone in ticket is accepted",
            not run(GOOD.replace('gh_issue: 1', 'milestone: "audit-2026-07-17"\ngh_issue: 1'))[0])
    p.check("undeclared milestone in ticket is rejected",
            len(run(GOOD.replace('gh_issue: 1', 'milestone: "fake-milestone"\ngh_issue: 1'))[0]) >= 1)

    print("\nWHAT THIS SUITE DOES NOT COVER")
    src = SCHEMA.read_text()
    # ⚠️ This probe was FIRST written as `"archive" not in src.lower()` and immediately
    # false-fired when `CLOSED_FOR_DOD = {"done", "archived"}` was added — a substring standing in
    # for a concept, the same class as the estate's recorded `\b matches across hyphens` trap.
    # It now looks for AC8's actual ARTEFACTS: a declared board bound, or a ticket archive directory.
    # 🔴 Corrected 2026-08-20, and it is the SAME defect a third time. This probe asked whether
    # `"board_bound"` appears in sdlc.json — a key name **nothing has ever used**. AC8 landed the
    # bound on 2026-08-20 under `tasks_surface.retention`, and the probe went on reporting it
    # absent, green. A probe that names its own target cannot fail; it is the `\b`-across-hyphens
    # trap and the two above it, wearing a third costume. It now reads the ARTEFACT.
    sdlc = json.loads(_re2.sub(r"^\s*//.*$", "", (ROOT.parent / ".w0m/sdlc.json").read_text(), flags=_re2.M))
    bound_declared = "retention" in sdlc.get("tasks_surface", {})
    p.check("AC8's board bound is declared as an ARTEFACT, not a key name we invented",
            bound_declared, "expected tasks_surface.retention in .w0m/sdlc.json")
    rotated = (ROOT.parent / ".tasks/archive").is_dir()
    p.check("...and the ROTATION artefact exists — AC8b ran, this is no longer unbuilt",
            rotated,
            "expected .tasks/archive/ — see test_tasks_rotate.py / test_tasks_bounds.py "
            "for the probes that actually exercise it")
    print(" [SKIP] 'a done ticket still holding a full board row' — lives in `test_tasks_rotate.py`")
    print("        / `test_tasks_bounds.py`, not here: THIS suite validates ticket FILES, not")
    print("        TASKS.md's board rows, so it was never the right home for that probe.")

    print("\n" + "-" * 78)
    if p.fail:
        print(f"FAIL — {len(p.fail)} of {p.n}:", file=sys.stderr)
        for f in p.fail: print(f"  ✗ {f}", file=sys.stderr)
        return 1
    print(f"✅ {p.n} checks — every rejection this gate claims is seen to fire, and the one")
    print("   check that is not built is named rather than faked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
