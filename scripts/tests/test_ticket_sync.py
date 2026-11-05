#!/usr/bin/env python3
"""T150 regression proof for sync_github.py — the indexed, reconciling ticket mirror.

Every test drives the REAL module. Network calls go through the module's `RUN` seam, which is
swapped for a recording double, so the suite proves call COUNTS (the whole point of T150) without
touching GitHub.

Discipline this estate now applies to every gate, and which this suite follows:
  * each behaviour is proven RED as well as green — a test that only asserts the happy path cannot
    tell a working check from an absent one;
  * the anti-vacuity meta-test at the bottom fails if the suite runs zero tests. A test runner that
    silently matches nothing exits 0, which has already fooled this project once.

Run: `just sync-tickets-test`.
"""
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ESTATE = Path(__file__).resolve().parents[2]
MODULE = ESTATE / "scripts" / "sync_github.py"

spec = importlib.util.spec_from_file_location("sync_github", MODULE)
sg = importlib.util.module_from_spec(spec)
sys.modules["sync_github"] = sg
spec.loader.exec_module(sg)

results: list[bool] = []


def check(label: str, ok: bool):
    results.append(ok)
    print(f"  {'✅' if ok else '❌'} {label}")


# ── the recording gh double ─────────────────────────────────────────────────────────

MUTATIONS = {
    ("issue", "create"), ("issue", "edit"), ("issue", "close"), ("issue", "reopen"),
    ("label", "create"), ("project", "item-add"), ("project", "create"),
}


class FakeGh:
    def __init__(self, issues: list[dict]):
        self.issues = issues
        self.calls: list[list[str]] = []

    @property
    def mutating(self) -> list[list[str]]:
        return [c for c in self.calls if (c[1], c[2]) in MUTATIONS]

    def count(self, *pair) -> int:
        return sum(1 for c in self.calls if (c[1], c[2]) == pair)

    def __call__(self, args: list[str]):
        self.calls.append(args)
        head = (args[1], args[2]) if len(args) > 2 else ("", "")
        if head == ("auth", "switch"):
            return 0, "", ""
        if head == ("repo", "view"):
            return 0, sg.REPO, ""
        if head == ("issue", "list"):
            return 0, json.dumps(self.issues), ""
        if head == ("project", "list"):
            return 0, json.dumps({"projects": [
                {"title": sg.PROJECT_TITLE, "number": 2, "url": "https://example/2"}]}), ""
        if head == ("issue", "create"):
            return 0, f"https://github.com/{sg.REPO}/issues/999", ""
        return 0, "", ""


def issue(num: int, title: str, labels: list[str], state="OPEN") -> dict:
    return {"number": num, "title": title,
            "labels": [{"name": n} for n in labels], "state": state}


def ticket_md(tid: str, title: str, status="queued", queue="next", prio="P1",
              gh_issue: str | None = "1", summary="Body text.") -> str:
    return (f"---\nid: {tid}\ntitle: \"{title}\"\nstatus: {status}\nqueue: {queue}\n"
            f"priority: {prio}\nrepos: [web]\narea: sdlc\nepic: \"\"\nspec: \"\"\n"
            f"gh_issue: {gh_issue if gh_issue is not None else ''}\ntags: []\n---\n\n"
            f"## Summary\n\n{summary}\n\n## Other\n\nnot projected\n")


class Harness:
    """Point the module at a temp ticket tree + index, with a faked gh."""

    def __init__(self, tickets: dict[str, str], issues: list[dict], index: dict | None = None):
        self.dir = Path(tempfile.mkdtemp(prefix="t150-"))
        (self.dir / "tickets").mkdir()
        for name, body in tickets.items():
            (self.dir / "tickets" / f"{name}.md").write_text(body, encoding="utf-8")
        self.index_path = self.dir / "index.json"
        if index is not None:
            self.index_path.write_text(json.dumps(index), encoding="utf-8")
        self.gh = FakeGh(issues)

    def __enter__(self):
        self._saved = (sg.TICKETS_DIR, sg.MANIFEST, sg.INDEX, sg.RUN,
                       sg.DRY, sg.FORCE_ALL, sg.VERIFY, sg.ISSUES_ONLY, sg.ONLY_TICKETS)
        sg.TICKETS_DIR = self.dir / "tickets"
        sg.MANIFEST = self.dir / "manifest.json"
        sg.INDEX = self.index_path
        sg.RUN = self.gh
        sg.DRY = sg.FORCE_ALL = sg.VERIFY = sg.ISSUES_ONLY = False
        sg.ONLY_TICKETS = None
        return self

    def __exit__(self, *a):
        (sg.TICKETS_DIR, sg.MANIFEST, sg.INDEX, sg.RUN,
         sg.DRY, sg.FORCE_ALL, sg.VERIFY, sg.ISSUES_ONLY, sg.ONLY_TICKETS) = self._saved

    def index_now(self) -> dict:
        return json.loads(self.index_path.read_text())["tickets"]


# ── 1. pure core: label ownership and reconciliation ────────────────────────────────

print("\n▶ label ownership + reconciliation (AC3c)")
check("P1 is owned", sg.is_owned("P1"))
check("status:/area:/repo: are owned",
      all(sg.is_owned(x) for x in ("status:done", "area:sdlc", "repo:web")))
# 🔴 A RETIRED namespace must stay OWNED, and this is the assertion that guarantees the retirement
# mechanism works at all (T228 AC3). `queue:` is no longer produced by `desired_labels()`, but if it
# also stopped being owned, `reconcile_labels()` could never prune it — deleting a namespace from
# the schema would strand every label it ever published instead of removing them.
check("a RETIRED namespace is still owned, so its labels can be pruned",
      sg.is_owned("queue:now") and "queue:" in sg.RETIRED_PREFIXES)
check("…and a retired namespace is never DESIRED",
      not any(l.startswith("queue:") for l in sg.desired_labels(
          {"priority": "P1", "status": "queued", "queue": "now", "repos": ["web"], "area": "sdlc"})))
check("a hand-added label is NOT owned",
      not any(sg.is_owned(x) for x in ("good-first-issue", "Priority-ish", "epic")))

add, remove = sg.reconcile_labels({"status:queued", "P1", "good-first-issue"},
                                  {"status:in-progress", "P1"})
check("old status label is REMOVED (asserting absence, not presence)",
      remove == ["status:queued"])
check("new status label is added", add == ["status:in-progress"])
check("foreign label survives reconciliation", "good-first-issue" not in remove)

# RED probe: the contradictory-label bug is exactly "remove is always empty".
check("RED — an add-only reconciler would leave the stale label",
      sg.reconcile_labels({"status:queued"}, {"status:done"})[1] == ["status:queued"])


# ── 2. pure core: the projection and its hash ───────────────────────────────────────

print("\n▶ projection + hash (AC2)")
t = {"id": "T1", "title": "x", "status": "queued", "queue": "next", "priority": "P1",
     "repos": ["web"], "epic": "", "spec": ""}
p1 = sg.projection_of(t, "summary one")
p2 = sg.projection_of(t, "summary one")
p3 = sg.projection_of(t, "summary TWO")
check("hash is stable for identical projections", sg.projection_hash(p1) == sg.projection_hash(p2))
check("hash moves when the body moves", sg.projection_hash(p1) != sg.projection_hash(p3))
check("title carries the T<id> — prefix the resolver matches on", p1["title"].startswith("T1 — "))
check("done closes, queued does not", sg.projection_of({**t, "status": "done"}, "s")["closed"]
      and not p1["closed"])
check("paused does NOT close (T141: closing it makes the board read Done)",
      not sg.projection_of({**t, "status": "paused"}, "s")["closed"])


# ── 3. pure core: needs_sync ────────────────────────────────────────────────────────

print("\n▶ staleness decision (AC2)")
live_ok = {"title": p1["title"], "labels": set(p1["labels"]), "closed": False}
idx = {"T1": sg.projection_hash(p1)}
check("unchanged ticket is skipped", not sg.needs_sync("T1", p1, idx, live_ok))
check("changed body re-syncs", sg.needs_sync("T1", p3, idx, live_ok))
check("title drifted ON GITHUB re-syncs (self-healing)",
      sg.needs_sync("T1", p1, idx, {**live_ok, "title": "T1 — stale"}))
check("labels drifted on GitHub re-sync",
      sg.needs_sync("T1", p1, idx, {**live_ok, "labels": {"P1", "status:done"}}))
check("closed-state drifted on GitHub re-syncs",
      sg.needs_sync("T1", p1, idx, {**live_ok, "closed": True}))
check("no live issue always re-syncs", sg.needs_sync("T1", p1, idx, None))


# ── 4. the index file ───────────────────────────────────────────────────────────────

print("\n▶ index invalidation (AC2)")
with Harness({"T1": ticket_md("T1", "x")}, []) as h:
    h.index_path.write_text(json.dumps(
        {"projection_version": sg.PROJECTION_VERSION, "tickets": {"T1": "abc"}}))
    check("matching projection_version is honoured", sg.load_index() == {"T1": "abc"})
    h.index_path.write_text(json.dumps(
        {"projection_version": sg.PROJECTION_VERSION + 1, "tickets": {"T1": "abc"}}))
    check("RED — a version bump invalidates EVERY entry", sg.load_index() == {})
    h.index_path.write_text("{ not json")
    check("an unreadable index is treated as fully stale", sg.load_index() == {})


# ── 5. call counts on a real main() run ─────────────────────────────────────────────

print("\n▶ call counts (AC4, AC5)")

TITLE = "T1 — x"

# 🔴 T260. These next two fixtures must carry EXACTLY what the projection desires, because the
# probes below assert a NO-OP — and a no-op is arithmetically impossible while an issue holds a
# label reconciliation is obliged to prune.
#
# They used to read `["P1", "status:queued", "repo:web", "area:sdlc"]`, which was correct until
# **2026-08-20**, when T228 AC5b retired `status:`, `area:` and `queue:` as labels and moved them to
# Projects v2 single-select fields (`status` now lives on 234 board items). Retired namespaces stay
# **owned so they can be pruned** and are excluded from `desired_labels()` so they are never
# re-added — see `tickets-schema.jsonc → github.retired_label_namespaces`, which says so explicitly.
#
# The consequence nobody noticed: every "no-op" run had two labels to remove, so `needs_sync` was
# right to return True, so three probes went red and STAYED red — `just test` exited 1 on every run
# for two days. ⚠️ The live sync was never wrong; only its proof was. That is the combination that
# teaches people to route around the aggregate (T135 AC8).
#
# Other fixtures below deliberately KEEP the retired labels — the pruning probe asserts
# `--remove-label status:queued` — so this is not a search-and-replace.
CLEAN_LABELS = ["P1", "repo:web"]
synced_issue = [issue(1, TITLE, CLEAN_LABELS)]

# 🔬 The guard that would have caught the drift in ONE line instead of three opaque count failures.
# It pins the fixture to the projection rather than to a remembered list, so the next namespace
# retirement fails HERE, saying what changed.
_probe_ticket = {"id": "T1", "title": "x", "status": "queued", "queue": "next", "priority": "P1",
                 "repos": ["web"], "area": "sdlc", "tags": []}
check("CLEAN_LABELS matches what the projection actually desires (drift guard)",
      sorted(CLEAN_LABELS) == sorted(sg.desired_labels(_probe_ticket)))

# A no-op run: index already matches, and GitHub agrees.
with Harness({"T1": ticket_md("T1", "x")}, synced_issue) as h:
    proj = sg.projection_of(sg.load_tickets()[0], "Body text.")
    h.index_path.write_text(json.dumps({"projection_version": sg.PROJECTION_VERSION,
                                        "tickets": {"T1": sg.projection_hash(proj)}}))
    rc = sg.main()
    check("no-op run exits 0", rc == 0)
    check("no-op run makes ZERO mutating calls (AC5)", h.gh.mutating == [])
    check("no-op run makes exactly ONE issue-list fetch (AC4)",
          h.gh.count("issue", "list") == 1)

# One changed ticket among three: exactly one is pushed.
three = {f"T{i}": ticket_md(f"T{i}", f"x{i}", gh_issue=str(i)) for i in (1, 2, 3)}
three_issues = [issue(i, f"T{i} — x{i}", CLEAN_LABELS) for i in (1, 2, 3)]
with Harness(three, three_issues) as h:
    tickets = sg.load_tickets()
    idx = {t["id"]: sg.projection_hash(sg.projection_of(t, "Body text.")) for t in tickets}
    idx["T2"] = "STALE"                      # only T2 differs
    h.index_path.write_text(json.dumps({"projection_version": sg.PROJECTION_VERSION,
                                        "tickets": idx}))
    sg.main()
    check("a 1-ticket change syncs exactly 1 ticket", h.gh.count("issue", "edit") == 1)
    check("…and it is the right one",
          any("2" == c[3] for c in h.gh.calls if (c[1], c[2]) == ("issue", "edit")))
    check("still exactly ONE list fetch across a 3-ticket run",
          h.gh.count("issue", "list") == 1)

# RED probe for AC5: corrupt one hash → exactly that ticket re-syncs.
with Harness(three, three_issues) as h:
    tickets = sg.load_tickets()
    idx = {t["id"]: sg.projection_hash(sg.projection_of(t, "Body text.")) for t in tickets}
    idx["T3"] = "corrupted"
    h.index_path.write_text(json.dumps({"projection_version": sg.PROJECTION_VERSION,
                                        "tickets": idx}))
    sg.main()
    check("RED — corrupting one hash re-syncs exactly that ticket",
          h.gh.count("issue", "edit") == 1)

# A projection_version bump re-syncs everything.
with Harness(three, three_issues) as h:
    h.index_path.write_text(json.dumps({"projection_version": sg.PROJECTION_VERSION - 1,
                                        "tickets": {"T1": "a", "T2": "b", "T3": "c"}}))
    sg.main()
    check("a projection_version bump re-syncs ALL tickets", h.gh.count("issue", "edit") == 3)


# ── 6. the whole projection is pushed (AC2b) ────────────────────────────────────────

print("\n▶ the update path pushes the whole projection (AC2b)")

with Harness({"T1": ticket_md("T1", "x", status="done")},
             [issue(1, TITLE, ["P1", "status:queued", "repo:web", "area:sdlc"])]) as h:
    sg.main()
    edits = [c for c in h.gh.calls if (c[1], c[2]) == ("issue", "edit")]
    check("body is pushed on UPDATE, not only on create",
          bool(edits) and "--body" in edits[0])
    check("stale status label is REMOVED on update",
          any("--remove-label" in c and "status:queued" in c[c.index("--remove-label") + 1]
              for c in edits))
    check("a done ticket CLOSES its open issue", h.gh.count("issue", "close") == 1)

with Harness({"T1": ticket_md("T1", "x", status="in-progress")},
             [issue(1, TITLE, ["P1", "status:done", "repo:web", "area:sdlc"], state="CLOSED")]) as h:
    sg.main()
    check("an un-done ticket REOPENS its closed issue", h.gh.count("issue", "reopen") == 1)

with Harness({"T1": ticket_md("T1", "renamed")},
             [issue(1, "T1 — old name", ["P1", "status:queued", "repo:web", "area:sdlc"])]) as h:
    sg.main()
    edits = [c for c in h.gh.calls if (c[1], c[2]) == ("issue", "edit")]
    check("a retitled ticket pushes --title", bool(edits) and "--title" in edits[0])


# ── 7. AC1 — the recorded number is the key ─────────────────────────────────────────

print("\n▶ recorded issue number (AC1)")

with Harness({"T1": ticket_md("T1", "x", gh_issue="1")}, synced_issue) as h:
    sg.load_tickets()
    check("gh_issue is parsed into the ticket dict", sg.load_tickets()[0]["gh_issue"] == 1)

with Harness({"T1": ticket_md("T1", "x", gh_issue="not-a-number")}, synced_issue) as h:
    check("a non-integer gh_issue is rejected, never passed to gh",
          sg.load_tickets()[0]["gh_issue"] is None)

# RED probe: backfill must INSERT the key, not only replace it. 8 real tickets (T66, T119-T125)
# had no gh_issue line at all, and the original bare re.sub silently did nothing for them.
no_key = ("---\nid: T1\ntitle: \"x\"\nstatus: queued\nqueue: next\npriority: P1\n"
          "repos: [web]\nepic: \"\"\nspec: \"\"\ntags: []\n---\n\n## Summary\n\nBody text.\n\n## X\n\ny\n")
with Harness({"T1": no_key}, [issue(5, TITLE, ["P1", "status:queued", "repo:web", "area:sdlc"])]) as h:
    check("a ticket with NO gh_issue line parses as unrecorded", sg.load_tickets()[0]["gh_issue"] is None)
    sg.backfill("T1", 5)
    written = (h.dir / "tickets" / "T1.md").read_text()
    check("RED — backfill INSERTS a missing gh_issue key", "gh_issue: 5" in written)
    check("…inside the frontmatter, not the body",
          written.split("---")[1].count("gh_issue: 5") == 1)
    check("…and the ticket still parses afterwards", sg.load_tickets()[0]["gh_issue"] == 5)

# Recorded number points at a deleted issue → dropped and re-resolved by title.
with Harness({"T1": ticket_md("T1", "x", gh_issue="404")},
             [issue(7, TITLE, ["P1", "status:queued", "repo:web", "area:sdlc"])]) as h:
    sg.main()
    check("a recorded number that 404s is dropped and re-resolved",
          h.gh.count("issue", "create") == 0 and h.gh.count("issue", "edit") == 1)

# …and when NOTHING matches by title either, the ticket is re-created rather than erroring.
# This is the case T188 mistook for an unhandled crash: it added a branch to raise a diagnosis
# for "recorded number, no live issue", and this test is what proved the branch never runs —
# phase 1 clears the dead number first, so phase 2 only ever sees "create". The branch was
# removed and the invariant moved into the type; this pins the behaviour that actually happens.
# NB: 555, not 999 — the gh double returns issue 999 from `issue create`, so a probe using it
# cannot tell "the dead number was touched" from "the new number was created".
with Harness({"T1": ticket_md("T1", "x", gh_issue="555")}, []) as h:
    rc = sg.main()
    check("a recorded number with NO title match re-creates, and does not fail",
          h.gh.count("issue", "create") == 1 and rc == 0)
    check("…and never edits the dead number",
          h.gh.count("issue", "edit") == 0
          and not any("555" in part for call in h.gh.mutating for part in call))

# --verify mutates nothing.
with Harness({"T1": ticket_md("T1", "x", gh_issue="404")}, synced_issue) as h:
    sg.VERIFY = True
    rc = sg.main()
    check("--verify reports a mismatch (exit 1)", rc == 1)
    check("--verify mutates NOTHING", h.gh.mutating == [])


# ── 8. failure is never silent (AC6) ────────────────────────────────────────────────

print("\n▶ failure visibility (AC6)")

with Harness({"T1": ticket_md("T1", "x")},
             [issue(1, "T1 — stale", ["P1", "status:queued", "repo:web", "area:sdlc"])]) as h:
    def boom(args):
        if (args[1], args[2]) == ("issue", "edit"):
            raise RuntimeError("gh exploded")
        return h.gh(args)
    sg.RUN = boom
    rc = sg.main()
    check("RED — a per-ticket exception makes the run exit NON-ZERO", rc == 1)


# ── 9. truncation guard ─────────────────────────────────────────────────────────────

print("\n▶ truncation guard (AC4)")
with Harness({"T1": ticket_md("T1", "x")},
             [issue(i, f"T{i} — x", []) for i in range(sg.ISSUE_FETCH_LIMIT)]) as h:
    try:
        sg.fetch_issues()
        check("a truncated issue list is REFUSED, not mirrored against", False)
    except RuntimeError:
        check("a truncated issue list is REFUSED, not mirrored against", True)


# ── 10. ticket architecture diagram co-location & projection (T211 AC1, AC2, AC3) ─

print("\n▶ ticket diagram co-location & projection (T211 AC1, AC2, AC3)")
with Harness({"T1": ticket_md("T1", "x")}, []) as h:
    check("ticket with no diagrams returns empty list", sg.ticket_diagrams("T1") == [])
    p_no_diag = sg.projection_of({"id": "T1", "status": "queued"}, "summary")
    h_no_diag = sg.projection_hash(p_no_diag)
    check("ticket with no diagrams has no details block in body",
          "<details open><summary>📊" not in p_no_diag["body"])

    # Create diagrams for T1 and a confusingly named T10 diagram
    t1_mmd = h.dir / "tickets" / "T1.mmd"
    t1_flow = h.dir / "tickets" / "T1-system-flow.mmd"
    t10_mmd = h.dir / "tickets" / "T10.mmd"
    t1_mmd.write_text("graph TD\n  A --> B\n", encoding="utf-8")
    t1_flow.write_text("```mermaid\nsequenceDiagram\n  Alice->>Bob: Hi\n```", encoding="utf-8")
    t10_mmd.write_text("graph LR\n  X --> Y\n", encoding="utf-8")

    diags = sg.ticket_diagrams("T1")
    check("discovers exact T1 diagrams and ignores T10 (no prefix pollution)",
          len(diags) == 2 and [d[0] for d in diags] == ["Architecture Diagram", "System Flow"])
    check("unwraps accidental markdown code fences cleanly",
          diags[1][1] == "sequenceDiagram\n  Alice->>Bob: Hi")

    p_with_diag = sg.projection_of({"id": "T1", "status": "queued"}, "summary")
    h_with_diag = sg.projection_hash(p_with_diag)
    check("hash moves when diagrams are added", h_no_diag != h_with_diag)
    check("body contains formatted details block with summary icon",
          "<details open><summary>📊 Architecture Diagram</summary>\n\n```mermaid\ngraph TD\n  A --> B\n```\n</details>" in p_with_diag["body"])
    check("body contains second diagram with custom title",
          "<details open><summary>📊 System Flow</summary>\n\n```mermaid\nsequenceDiagram\n  Alice->>Bob: Hi\n```\n</details>" in p_with_diag["body"])

    # Modifying diagram content invalidates hash
    t1_mmd.write_text("graph TD\n  A --> C\n", encoding="utf-8")
    p_mod_diag = sg.projection_of({"id": "T1", "status": "queued"}, "summary")
    check("hash moves when diagram content is modified", h_with_diag != sg.projection_hash(p_mod_diag))


# ── 11. T141 — Projects v2 board projection, drift check & non-silent item-add ──────

print("\n▶ T141 — Projects v2 board projection, drift check & non-silent item-add")
bf_paused = sg.desired_board_fields(
    {"id": "T32", "status": "paused", "priority": "P1", "area": "sdlc", "epic": "delivery-record-sync", "repos": ["tooling", "web"]}
)
bf_done = sg.desired_board_fields(
    {"id": "T33", "status": "done", "priority": "P1", "area": "sdlc", "epic": "delivery-record-sync", "repos": ["web"]}
)
check("AC1/AC3: paused maps to 'paused' on the board, distinct from 'done'",
      bf_paused["Status"] == "paused" and bf_done["Status"] == "done" and bf_paused["Status"] != bf_done["Status"])
check("AC4: Priority, Area, Epic, and Repo are projected as board fields",
      bf_paused.get("Priority") == "P1"
      and bf_paused.get("Area") == "sdlc"
      and bf_paused.get("Epic") == "delivery-record-sync"
      and bf_paused.get("Repo") == "tooling,web")

# AC6 & AC8: check_board_drift MUST FAIL on empty input sets (anti-vacuity)
check("RED — AC6/AC8: check_board_drift fails on empty ticket list",
      len(sg.check_board_drift([], [{"issue_number": 1, "fields": {"Status": "queued"}}])) == 1)
check("RED — AC6/AC8: check_board_drift fails on empty board item list",
      len(sg.check_board_drift([{"id": "T1", "gh_issue": 1, "status": "queued"}], [])) == 1)

# AC6 & AC3: check_board_drift catches a paused ticket whose board card reads 'done'
drift_found = sg.check_board_drift(
    [{"id": "T32", "gh_issue": 32, "status": "paused", "priority": "P1", "area": "sdlc", "epic": "e1", "repos": ["web"]}],
    [{"issue_number": 32, "fields": {"Status": "done", "Priority": "P1", "Area": "sdlc", "Epic": "e1", "Repo": "web"}}],
)
check("RED — AC3/AC6: check_board_drift flags a paused ticket showing 'done' on the board",
      len(drift_found) == 1 and "T32" in drift_found[0] and "'paused'" in drift_found[0])

drift_clean = sg.check_board_drift(
    [{"id": "T32", "gh_issue": 32, "status": "paused", "priority": "P1", "area": "sdlc", "epic": "e1", "repos": ["web"]}],
    [{"issue_number": 32, "fields": {"Status": "paused", "Priority": "P1", "Area": "sdlc", "Epic": "e1", "Repo": "web"}}],
)
check("AC6: check_board_drift passes (0 mismatches) when board matches ticket frontmatter",
      drift_clean == [])

# AC8 & AC9: a failing `gh project item-add` is no longer swallowed by check=False
with Harness({"T1": ticket_md("T1", "x")},
             [issue(1, "T1 — stale", ["P1", "status:queued", "repo:web", "area:sdlc"])]) as h:
    def item_add_fails(args):
        if len(args) >= 3 and (args[1], args[2]) == ("project", "item-add"):
            return 1, "", "GraphQL: Resource not accessible by integration"
        return h.gh(args)
    sg.RUN = item_add_fails
    rc = sg.main()
    check("RED — AC8/AC9: a failed `project item-add` makes the sync exit non-zero instead of vanishing",
          rc == 1)


# ── 12. T650 — fail-closed project list, --tickets subset, and --issues-only ────────

print("\n[T650] fail-closed project list, --tickets subset, and --issues-only")
check("T650: ISSUE_FETCH_LIMIT raised >= 5000 for 650+ ticket corpus", sg.ISSUE_FETCH_LIMIT >= 5000)
check("T650: _parse_only_tickets normalises CSV and bare numeric IDs",
      sg._parse_only_tickets(["--tickets", "T650, 651", "--ticket=t12"]) == {"T650", "T651", "T12"}
      and sg._parse_only_tickets(["--check"]) is None)

with Harness({"T1": ticket_md("T1", "x", status="done")},
             [issue(1, TITLE, CLEAN_LABELS, state="OPEN")]) as h:
    def project_list_missing_scope(args):
        if len(args) >= 3 and (args[1], args[2]) == ("project", "list"):
            return 1, "", "error: your authentication token is missing required scopes [read:project]"
        return h.gh(args)
    sg.RUN = project_list_missing_scope
    try:
        sg.main()
        stopped_on_project_list = False
    except SystemExit:
        stopped_on_project_list = True
    check("RED — T650: failed `gh project list` (missing read:project) stops immediately",
          stopped_on_project_list)
    check("RED — T650: failed `gh project list` NEVER falls through to `gh project create`",
          h.gh.count("project", "create") == 0 and h.gh.count("issue", "close") == 0)

# Targeted `--tickets T2` mutates only T2 and preserves T1/T3 hashes in tickets-sync-index.json
with Harness(three,
             [issue(1, "T1 — stale", CLEAN_LABELS),
              issue(2, "T2 — stale", CLEAN_LABELS),
              issue(3, "T3 — stale", CLEAN_LABELS)],
             index={"projection_version": sg.PROJECTION_VERSION,
                    "tickets": {"T1": "keep-t1", "T3": "keep-t3"}}) as h:
    sg.ONLY_TICKETS = {"T2"}
    rc_sub = sg.main()
    idx_after = h.index_now()
    check("T650: --tickets T2 exits 0 and mutates ONLY T2",
          rc_sub == 0 and h.gh.count("issue", "edit") == 1
          and any("2" == c[3] for c in h.gh.calls if (c[1], c[2]) == ("issue", "edit")))
    check("T650: --tickets T2 preserves untouched index hashes for T1 and T3",
          idx_after.get("T1") == "keep-t1" and idx_after.get("T3") == "keep-t3"
          and idx_after.get("T2") not in (None, "keep-t2"))

with Harness({"T1": ticket_md("T1", "x")}, synced_issue) as h:
    sg.ONLY_TICKETS = {"T99999"}
    rc_unknown = sg.main()
    check("RED — T650: --tickets with unknown ID refuses vacuous sync (exit 1, zero mutations)",
          rc_unknown == 1 and h.gh.mutating == [])

# `--issues-only` closes done issues + backfills gh_issue without calling Projects v2 or marking board hash clean
with Harness({"T1": ticket_md("T1", "x", status="done", gh_issue=None)},
             [issue(42, TITLE, CLEAN_LABELS, state="OPEN")],
             index={"projection_version": sg.PROJECTION_VERSION,
                    "tickets": {"T9": "keep-t9"}}) as h:
    sg.ISSUES_ONLY = True
    rc_io = sg.main()
    t1_after = (h.dir / "tickets" / "T1.md").read_text(encoding="utf-8")
    idx_io = h.index_now()
    check("T650: --issues-only closes done issue and backfills gh_issue",
          rc_io == 0 and h.gh.count("issue", "close") == 1 and "gh_issue: 42" in t1_after)
    check("T650: --issues-only makes ZERO project list / project item-add calls",
          h.gh.count("project", "list") == 0 and h.gh.count("project", "item-add") == 0)
    check("T650: --issues-only does NOT record T1 as board-synced in tickets-sync-index.json",
          "T1" not in idx_io and idx_io.get("T9") == "keep-t9")

# `ensure_labels()` skips `gh label create` when `gh label list` already matches color & description
with Harness({"T1": ticket_md("T1", "x")}, []) as h:
    def labels_already_current(args):
        if len(args) >= 3 and (args[1], args[2]) == ("label", "list"):
            return 0, json.dumps([
                {"name": "P1", "color": "d93f0b", "description": "Priority 1"},
                {"name": "repo:web", "color": "ededed", "description": "repo:web"},
            ]), ""
        return h.gh(args)
    sg.RUN = labels_already_current
    sg.ensure_labels(sg.load_tickets())
    check("T650: ensure_labels skips `gh label create` when labels already match on GitHub",
          h.gh.count("label", "create") == 0)


# ── meta ────────────────────────────────────────────────────────────────────────────

print("\n▶ meta")
check("the suite actually ran tests (anti-vacuity)", len(results) >= 40)

passed, total = sum(results), len(results)
print(f"\n{'✅' if passed == total else '❌'} {passed}/{total} checks passed")
sys.exit(0 if passed == total else 1)
