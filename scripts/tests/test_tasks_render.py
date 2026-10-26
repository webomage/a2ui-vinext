#!/usr/bin/env python3
"""`just tasks` renders for a terminal — aligned columns, working links, no markdown leak.

Reported by the owner 2026-08-22: *"formatting broken in `just tasks`, and links for T* tickets not
clickable in terminal, while GH yes."*

🔴 **The obvious reading of that report was wrong, and it cost two rounds.** *"GH yes"* looked like
proof that OSC 8 worked and only the `file://` target was malformed, so the fix was to add the host
— `file://b0x.local/path`. Still dead. Guessing again would have been the third attempt, so
`project/scripts/link_probe.py` printed the SAME target in nine forms and the owner clicked.

**The measurement:** only **OSC 8 with an `https://` target** and a **bare `https://` URL** are
followed. `file://host/path`, `file:///path`, `vscode://file/…`, a bare absolute path and
`path:line` are ALL inert, with any modifier key. ⇒ A local file path cannot be made clickable in
this terminal at all, by any encoding. The ticket link now points at the GitHub **blob** — the copy
of the file that has an https URL.

Three defects, one cause: the boards were built as markdown and printed straight at a human.

  ① columns never aligned — a pipe table with no padding is noise with punctuation in it;
  ② the ticket target was a `file://` URL, which this terminal does not follow in any form;
  ③ 🔴 the latent one nobody reported: `_link()` branched on `sys.stdout.isatty()`, and
    `state_doctor.py` **imports `markdown_hot`/`markdown_sdlc` directly** to build STATE.md's
    managed block. A `just state-save` run by a human at a terminal would have written OSC 8
    escape sequences into a TRACKED FILE. It measured clean only because the last save happened
    to run under a pipe.

⚠️ The ordering probe below is the one that matters. Aligning before converting links measured
`[T2](/Users/…/T2.md)` as a 70-column cell for a 2-column label, spent the terminal on paths, and
then truncated INTO the OSC 8 sequence — printing garbage and yielding a dead link. It looked like
a width bug and was an ordering bug.

Run: `just tasks-render-test`
"""

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "wom7web"
sys.path.insert(0, str(ROOT / "scripts"))

import tasks_query as tq  # noqa: E402

tasks_query_bin = ROOT / "scripts" / "tasks_query.py"
failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'✅' if ok else '❌'} {label}")
    if not ok:
        failures.append(f"{label} — {detail}")


def run(mode: str, cols: str = "150", *args: str) -> str:
    env = {**os.environ, "W0M_TASKS_RENDER": mode, "COLUMNS": cols}
    out = subprocess.run(
        [sys.executable, str(tasks_query_bin), *args],
        capture_output=True, text=True, env=env, timeout=180, cwd=WEB,
    )
    if out.returncode != 0:
        raise SystemExit(f"tasks_query exited {out.returncode}: {out.stderr[-400:]}")
    return out.stdout


print("▶ just tasks — terminal rendering\n")

# ── width: len() is wrong twice over on these boards ────────────────────────────────────────────
check("an emoji is TWO columns", tq._vis_width("📄") == 2)
check("a VS16 emoji (⚠️) is TWO columns", tq._vis_width("⚠️") == 2,
      f"got {tq._vis_width(chr(0x26a0) + chr(0xfe0f))}")
check("a block-drawing bar is ONE column each", tq._vis_width("██████████") == 10)
check("an OSC 8 hyperlink is only its LABEL wide",
      tq._vis_width("\033]8;;file://h/x\033\\T2\033]8;;\033\\") == 2,
      "counting the target's bytes right-pads short cells and destroys the alignment")
check("SGR bold is zero columns", tq._vis_width("\033[1mstage-0\033[22m") == 7)

# ── the builders are markdown-only, whatever stdout is ──────────────────────────────────────────
# ③ — this is the STATE.md leak. Asserted on the function, not the CLI, because that is how
# state_doctor.py reaches it.
_all = tq.load()
rows = tq.rank(_all, 3)
# Each builder gets the ranking it was written for — `markdown_sdlc` reads `ac_pct`, which only
# `rank_sdlc` computes. Handing it hot rows raises KeyError, which is how this line was written
# the first time.
for fn, src in ((tq.markdown_hot, rows), (tq.markdown_sdlc, tq.rank_sdlc(_all, 3))):
    block = fn(src)
    check(f"{fn.__name__}() returns NO escape sequences (STATE.md safety)",
          "\033" not in block,
          "state_doctor.py embeds this verbatim into a tracked file")
check("markdown_hot() still emits real markdown links",
      "](/" in tq.markdown_hot(rows) and "](https://" in tq.markdown_hot(rows))
check("markdown_hot() includes Area column",
      "| Area |" in tq.markdown_hot(rows))
check("markdown_sdlc() includes Area column",
      "| Area |" in tq.markdown_sdlc(tq.rank_sdlc(_all, 3)))
check("plan_summary() includes Area column",
      "| Area |" in tq.plan_summary(_all))

# ── ① alignment ─────────────────────────────────────────────────────────────────────────────────
INVIS = re.compile("\033\\]8;;[^\033]*\033\\\\|\033\\[[0-9;]*m")


def table_lines(out: str) -> list[str]:
    return [ln for ln in out.split("\n") if "│" in ln or "┼" in ln]


tty = run("tty")
lines = table_lines(tty)
check("the tty form produces tables at all (non-vacuous)", len(lines) > 20, f"got {len(lines)}")
# ⚠️ Grouped by CONTIGUOUS RUN, which is how terminalise() actually works — one alignment per
# table. Grouping by column COUNT was the first attempt and it is wrong: the plan table has 8
# columns and the sdlc table 9, so a count of 8 separators mixes rows from two differently-sized
# tables and reports drift that does not exist. The probe failed on its own arithmetic, twice —
# the second time on a one-liner clever enough to be unreadable and wrong.
runs: list[list[str]] = []
current: list[str] = []
for ln in tty.split("\n"):
    if "│" in ln or "┼" in ln:
        current.append(ln)
    else:
        if len(current) > 1:
            runs.append(current)
        current = []
if len(current) > 1:
    runs.append(current)


def sep_cols(line: str) -> frozenset[int]:
    """Separator positions in DISPLAY COLUMNS, not string indices.

    🔬 Third arithmetic error in this probe, and the most instructive: measuring with
    `enumerate()` counts `🔴` as ONE position while the padder spends TWO columns on it, so any row
    carrying an emoji reported its separators one place early — a shift of exactly the emoji count
    (1 for `🔴 T8`, 2 for `🔒 ✅`). It read as a genuine misalignment in the renderer.
    🔑 **The probe committed the exact defect it exists to catch** — confusing character count with
    display width, which is the whole reason `_vis_width` had to be written.
    """
    cols, out = 0, []
    for ch in INVIS.sub("", line):
        if ch in "│┼":
            out.append(cols)
        cols += tq._vis_width(ch)
    return frozenset(out)


misaligned = [n for n, r in enumerate(runs) if len({sep_cols(ln) for ln in r}) > 1]
# Three tables on the default board: hot, sdlc, plan. `unspecified` prints as a comma list there.
check("separators land on identical columns within each table",
      not misaligned and len(runs) == 3,
      f"{len(runs)} table(s) found, misaligned: {misaligned}")
check("no table row exceeds the terminal width",
      all(tq._vis_width(ln) <= 150 for ln in lines),
      f"widest {max(tq._vis_width(ln) for ln in lines)} of 150")

# ── ② links ─────────────────────────────────────────────────────────────────────────────────────
# 🔬 MEASURED by `project/scripts/link_probe.py`, after two wrong guesses: in this estate's
# terminal, **only** OSC 8 with an `https://` target and a bare `https://` URL are followed.
# `file://host/path`, `file:///path`, `vscode://file/…`, a bare absolute path and `path:line` are
# all inert with any modifier key. A local path therefore CANNOT be made clickable here, so the
# ticket link points at the GitHub blob — the copy of the file that has an https URL.
# The branch segment may contain slashes: an agent tree is on `agent/<name>` (AgDR-0032) and GitHub accepts that in a blob URL. `[^/]+` here made this red in every agent tree.
check("ticket links target the GitHub blob, the only clickable form measured",
      re.search(r"\033\]8;;https://github\.com/[^/]+/[^/]+/blob/[^\033]+?/\.tasks/T\d+\.md",
                tty) is not None,
      "file:// in any form is inert in this terminal — probe row 3 vs rows 1/2/4/5/7/8")
check("the blob URL carries a REPO-RELATIVE path, never /Users/…",
      "/Users/" not in re.sub(r"\033\[[0-9;]*m", "", tty).split("\n")[0]
      and not re.search(r"\033\]8;;https://github\.com[^\033]*/Users/", tty),
      "pasting the absolute path into a GitHub URL yields a 404 that looks like a missing ticket")
check("GitHub links are left as https://",
      "\033]8;;https://github.com/" in tty)
check("the visible label is the bare id, not the path",
      re.search(r"\033]8;;file://[^\033]+\033\\\\?T\d+\033\]8;;", tty) is not None
      or re.search(r"\033\\T\d+\033\]8;;", tty) is not None,
      "the point of OSC 8 here is that the link gets SHORTER as it gets more correct")
LIVE_ROOT = tq.live_workspace_root()
override = run("tty", "150") if False else subprocess.run(
    [sys.executable, str(tasks_query_bin), "hot", "-n", "2"],
    capture_output=True, text=True, timeout=180, cwd=WEB,
    env={**os.environ, "W0M_TASKS_RENDER": "tty", "COLUMNS": "150",
         "W0M_TICKET_URL": "vscode://file"},
).stdout
check("W0M_TICKET_URL overrides the whole prefix, keeping the ABSOLUTE path for a local scheme",
      f"\033]8;;vscode://file{LIVE_ROOT}/" in override and "/.w0m/work/" not in override,
      "a non-https base addresses the local disk under the live root, so it must not be relativised or point into an agent tree")

# ── ⚠️ the ordering regression: a narrow terminal must not cut into a link ───────────────────────
narrow = run("tty", "60", "hot", "-n", "3")
check("at COLUMNS=60 the OSC 8 sequences are still INTACT",
      narrow.count("\033]8;;") == narrow.count("\033]8;;\033\\") * 2,
      "every hyperlink is an open+close pair; an odd count means one was truncated mid-sequence")
check("at COLUMNS=60 no path fragment leaks into the visible text",
      str(ROOT) not in INVIS.sub("", narrow) and str(LIVE_ROOT) not in INVIS.sub("", narrow),
      "this is exactly what the align-before-convert version printed")

# ── markdown mode stays the paste-able form ─────────────────────────────────────────────────────
md = run("markdown")
check("markdown mode emits pipe tables and no escapes",
      "|---|" in md and "\033" not in md)
check("markdown mode keeps the ABSOLUTE live-root ticket path (never .w0m/work/)",
      f"]({LIVE_ROOT}/" in md and "/.w0m/work/" not in md,
      "a relative path resolves only for a reader already inside wom7web; an agent-tree path dies on removal")

# ── emphasis is stripped only when PAIRED ──────────────────────────────────────────────────────
check("paired **bold** becomes SGR, not asterisks",
      "**" not in INVIS.sub("", tty) and "\033[1m" in tty)
# Asserted on TABLE CELLS, not the whole stream. The footnote prose is printed directly rather
# than through emit(), and its backticks are deliberate: `hot` and `sdlc` read as command names
# there. Measured — all three surviving backticks are in prose, none in a cell.
check("paired `code` loses its fences inside table cells",
      all("`" not in INVIS.sub("", ln) for ln in lines),
      "the bars rendered as `██████████` on screen")
check("an UNBALANCED marker is left exactly as written",
      tq.terminalise("| a | 2 * 3 and `unclosed |").count("*") == 1,
      "half-eating a title is worse than leaving the marker visible")

# ── the Blocked by column names tickets, so its ids are links too ───────────────────────────────
# Owner report 2026-09-07: the Ticket column was clickable and the blocker ids beside it were not.
# That is backwards. A blocker's own row is usually ABSENT from a top-10 board — it ranks low
# precisely because it is unblocked work nobody has started — so the id the reader most needs to
# follow was the one id with no way to follow it.
_linkable = [t["id"] for t in _all if (tq.TICKETS / f"{t['id']}.md").exists()][:2]
if len(_linkable) < 2:
    check("UNMEASURABLE: fewer than two ticket files on disk", False,
          "cannot exercise _id_links against real ids")
else:
    _one = tq._id_links([_linkable[0]])
    check("a blocker id becomes a markdown link to its own ticket file",
          _one == f"[{_linkable[0]}]({tq._ticket_href(_linkable[0])})", f"got {_one!r}")
    _two = tq._id_links(_linkable)
    check("EVERY id in a multi-blocker list is linked, comma-joined",
          _two.count("](/") == 2 and ", " in _two, f"got {_two!r}")

# The guard, proven by mutation rather than asserted: an id with no file on disk must degrade to
# plain text. A link that opens nothing is worse than an unlinked id.
check("an id with NO ticket file degrades to plain text",
      tq._id_links(["T9999999"]) == "T9999999",
      "the .exists() guard is not doing anything")

# The cell as the board actually prints it. Non-vacuity is ASSERTED, not assumed: if nothing in
# the ranking is blocked today this says UNMEASURABLE instead of passing quietly — a check over an
# empty set is not a passing check.
_sdlc_md = tq.markdown_sdlc(tq.rank_sdlc(_all, 10))
_blocked = [ln for ln in _sdlc_md.split("\n") if "🔴 " in ln or "🟠 " in ln]
if not _blocked:
    print("  ⚪ UNMEASURABLE: no ranked ticket is blocked today — cell-level check not exercised")
else:
    check("a rendered Blocked by cell carries a real link",
          all("](/" in ln.split("🔴 ")[-1].split("🟠 ")[-1] for ln in _blocked),
          f"{len(_blocked)} blocked row(s), and at least one has an unlinked id")
    check("terminalise() converts blocker ids to OSC 8 as well",
          "\033]8;;" in tq.terminalise(_blocked[0]),
          "the column is markdown-correct but still dead in a terminal")

# ── Dynamic plan projections & new commands (T232) ──────────────────────────────
_epic_plan = tq.load_plan(epic="13.8", tickets=_all)
check("load_plan(epic='13.8') builds a dynamic plan",
      bool(_epic_plan and _epic_plan.get("stages")),
      "dynamic epic projection returned empty plan")
check("dynamic epic plan includes T232 in its stages",
      any("T232" in st.get("tickets", []) for st in _epic_plan.get("stages", [])),
      "T232 not found in §13.8 stages")

_tset_plan = tq.load_plan(tickets_filter=["T232", "T192"], tickets=_all)
check("load_plan(tickets_filter) builds plan with exact tickets",
      bool(_tset_plan and any("T232" in st.get("tickets", []) for st in _tset_plan.get("stages", []))),
      "ticket-set projection failed")

_tag_plan = tq.load_plan(tag="ide-surfaces", tickets=_all)
check("load_plan(tag='ide-surfaces') builds plan for tagged tickets",
      bool(_tag_plan and any("T232" in st.get("tickets", []) for st in _tag_plan.get("stages", []))),
      "tag projection failed")

_next_out = run("tty", "150", "next")
check("just tasks next prints recommended ticket and pickup command",
      "NEXT RECOMMENDED TICKET" in _next_out and "just sdlc-start" in _next_out)

_wip_out = run("tty", "150", "wip")
_active_ids = [t.get("id") for t in _all if t.get("status") == "in-progress"]
check("just tasks wip lists active tickets",
      "IN PROGRESS" in _wip_out and (
          any(tid in _wip_out for tid in _active_ids if tid)
          if _active_ids
          else "(no tickets currently in-progress)" in _wip_out
      ))

_tree_out = run("tty", "150", "tree", "--ticket", "T101")
check("just tasks tree renders bidirectional blockers and dependents",
      "DEPENDENCY TREE — T101" in _tree_out and "blocked by" in _tree_out)

_epic_out = run("tty", "150", "epic")
# The no-argument epic is resolved from the LAST COMMIT's ticket id (resolve_current_ticket), so which epic —
# and whether it maps to a ROADMAP section — depends on git state. Asserting "ROADMAP" here broke deploy-all
# on 2026-09-25 the moment the last commit named T444 (epic `platform-core-settings`, no section). The
# roadmap mapping is pinned below with an explicit epic instead.
check("just tasks epic prints active epic board with ▶ EPIC header", "▶ EPIC" in _epic_out)
_epic26_out = run("tty", "150", "epic", "--epic", "26")
check("just tasks epic --epic 26 rolls the board up to ROADMAP §26",
      "▶ EPIC" in _epic26_out and "ROADMAP §26" in _epic26_out)

_current_out = run("tty", "150", "current")
_plan_name = (tq.load_plan() or {}).get("name", "")
check("just tasks current prints active milestone board with ▶ EPIC header",
      "▶ EPIC" in _current_out and _plan_name in _current_out)

_area_out = run("tty", "150", "area")
check("just tasks area renders Area Breakdown Summary and grouped tables",
      "TASK REGISTRY — GROUPED BY AREA" in _area_out and "Area Breakdown Summary" in _area_out)

_area_filter = run("tty", "150", "area", "--area", "tools")
check("just tasks area --area tools filters strictly to target area",
      "Area: tools" in _area_filter and "Area: product" not in _area_filter)

# ── T158 AC1–AC4: missing GitHub mirror & missing repo slug visibility ──────────────────────────
from unittest import mock as _mock  # noqa: E402

_sample_with_issue = {
    "id": "T158", "title": "Mirrored ticket", "status": "queued", "priority": "P2",
    "area": "sdlc", "score": 35, "rowless": False, "spec": "", "gh_issue": "158",
    "ac_done": 3, "ac_total": 6, "ac_pct": 50, "blockers": {"declared": [], "inferred": []},
}
_sample_no_issue = {
    **_sample_with_issue, "id": "T537", "title": "Unmirrored ticket", "gh_issue": "0",
}

with _mock.patch.object(tq, "_repo_slug", return_value="webomage/wom7board"):
    _hot_i_s = tq.markdown_hot([_sample_with_issue])
    _sdlc_i_s = tq.markdown_sdlc([_sample_with_issue])
    check("T158 (issue+slug): renders both local ticket link and GitHub issue link in hot & sdlc",
          f"[T158]({tq._ticket_href('T158')})" in _hot_i_s
          and "[#158](https://github.com/webomage/wom7board/issues/158)" in _hot_i_s
          and "[#158](https://github.com/webomage/wom7board/issues/158)" in _sdlc_i_s
          and tq.MISSING_SLUG_NOTE not in _hot_i_s)

    _hot_ni_s = tq.markdown_hot([_sample_no_issue])
    _sdlc_ni_s = tq.markdown_sdlc([_sample_no_issue])
    check("T158 AC1 (no-issue+slug): renders explicit '⚠️ not mirrored' in both markdown_hot and markdown_sdlc",
          tq.MISSING_MIRROR_MARKER in _hot_ni_s
          and tq.MISSING_MIRROR_MARKER in _sdlc_ni_s
          and f"[T537]({tq._ticket_href('T537')})" in _hot_ni_s
          and f"[T537]({tq._ticket_href('T537')})" in _sdlc_ni_s
          and tq.MISSING_SLUG_NOTE not in _hot_ni_s)

with _mock.patch.object(tq, "_repo_slug", return_value=""):
    _hot_i_ns = tq.markdown_hot([_sample_with_issue])
    _sdlc_i_ns = tq.markdown_sdlc([_sample_with_issue])
    check("T158 AC2 (issue+no-slug): preserves #158 without false 'not mirrored' and emits once-per-table slug note",
          "| #158 |" in _hot_i_ns
          and "| #158 |" in _sdlc_i_ns
          and tq.MISSING_MIRROR_MARKER not in _hot_i_ns
          and _hot_i_ns.count(tq.MISSING_SLUG_NOTE) == 1
          and _sdlc_i_ns.count(tq.MISSING_SLUG_NOTE) == 1
          and f"[T158]({tq._ticket_href('T158')})" in _hot_i_ns)

    _hot_ni_ns = tq.markdown_hot([_sample_no_issue])
    _sdlc_ni_ns = tq.markdown_sdlc([_sample_no_issue])
    check("T158 AC3/AC4 (neither: no-issue+no-slug): keeps local ticket link, marks unmirrored, and emits slug note",
          f"[T537]({tq._ticket_href('T537')})" in _hot_ni_ns
          and f"[T537]({tq._ticket_href('T537')})" in _sdlc_ni_ns
          and tq.MISSING_MIRROR_MARKER in _hot_ni_ns
          and tq.MISSING_MIRROR_MARKER in _sdlc_ni_ns
          and _hot_ni_ns.count(tq.MISSING_SLUG_NOTE) == 1
          and _sdlc_ni_ns.count(tq.MISSING_SLUG_NOTE) == 1)

# T158 AC4 RED proof: reverting _issue_link to the old silent '—' fallback must be caught
with _mock.patch.object(tq, "_issue_link", side_effect=lambda t: "—"):
    _mutant_hot = tq.markdown_hot([_sample_no_issue])
    check("T158 AC4 RED: reverting _issue_link to '—' fails the missing-mirror assertion",
          tq.MISSING_MIRROR_MARKER not in _mutant_hot)

# ── T548 AC2: synthetic agent-tree path never leaks .w0m/work/ into links ───────────────────────
import tempfile as _tempfile  # noqa: E402
with _tempfile.TemporaryDirectory(prefix="t548-") as _td:
    _fake_tree_tickets = Path(_td) / ".w0m" / "work" / "agy-temp" / "w0m" / ".tasks"
    _fake_tree_tickets.mkdir(parents=True)
    with _mock.patch.object(tq, "TICKETS", _fake_tree_tickets):
        _href = tq._ticket_href("T468")
        _hot_tree = tq.markdown_hot([_sample_with_issue])
        check("T548 AC2: _ticket_href from an agent-tree path never contains .w0m/work/",
              "/.w0m/work/" not in _href and "/.w0m/work/" not in _hot_tree and _href.endswith("/.tasks/T468.md"),
              f"got {_href}")
    # RED proof: a mutation that uses TICKETS directly as the link base leaks .w0m/work/
    _mutant_href = (_fake_tree_tickets / "T468.md").as_posix()
    check("T548 AC2 RED: using TICKETS directly as link base leaks .w0m/work/ and is caught",
          "/.w0m/work/" in _mutant_href)

print()
if failures:
    print(f"❌ {len(failures)} failure(s):")
    for f in failures:
        print(f"   · {f}")
    sys.exit(1)
print("✅ tasks renders for a terminal: aligned, linked, and markdown-clean where it must be")
