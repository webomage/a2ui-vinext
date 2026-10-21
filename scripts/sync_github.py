#!/usr/bin/env python3
"""Sync local per-ticket markdown → GitHub Issues + a Projects v2 board.

Markdown frontmatter (project/tickets/*.md) is the source of truth — the ticket LIST is built
directly from the .md files, so a ticket is mirrored the moment its file exists (no manual
manifest step). project/tickets.json is a DERIVED snapshot, rewritten each run for inspection/diff
— do not hand-edit it (before 2026-07-21 it was the hand-maintained source and silently drifted:
5 tickets incl. T105 never synced because nobody added them to it).

T150 — the mirror is INDEXED and it pushes the WHOLE projection:

  * The recorded `gh_issue:` is the idempotency key (AC1). The title-prefix search is a fallback
    for tickets that have no number yet, answered from the one in-memory index — never per ticket.
  * ONE issue-list fetch per run (AC4), covering open AND closed.
  * On update we push title, body, closed-state AND labels (AC2b). Before T150 the reuse branch
    sent `--add-label` alone, so the mirror did not mirror: bodies were frozen at creation, 7 of 19
    `done` tickets still had open issues, and 2 of 137 titles had drifted.
  * Labels RECONCILE within the namespaces we own (AC3c). `--add-label` only ever adds, which is
    how 21 of 145 issues came to carry `status:done` AND `status:in-progress` AND `status:queued`
    at once. Labels outside our namespaces are never touched.
  * A committed projection index (AC2) lets an unchanged ticket be skipped entirely.

WHY THE INDEX IS NARROW — read before "optimising" it. The single issue-list fetch already returns
title, labels and state for free, so those are compared against the DESIRED projection directly and
the mirror self-heals when someone edits an issue by hand. The index therefore only has to cover
the **body**, which is the one projected field a list fetch cannot see and which would otherwise
cost one API call per ticket. Trusting the index for title/labels/state instead would make external
drift permanent — the exact freeze this design avoids.

`projection_version` invalidates the whole index when the projected field set changes. T141 will add
board fields; without the bump its new fields would ship into an index reporting everything synced.

Usage:
    python3 project/scripts/sync_github.py            # indexed sync (skips unchanged)
    python3 project/scripts/sync_github.py --all      # force a full sweep
    python3 project/scripts/sync_github.py --dry-run  # print planned actions only, mutate nothing
    python3 project/scripts/sync_github.py --verify    # audit recorded gh_issue numbers, no mutation

Exit codes: 0 ok · 1 one or more tickets failed to sync · 2 configuration/auth error.

Requires: gh CLI authenticated as an account that can resolve REPO, with 'repo' +
'project' scopes. The script re-pins the active account to ACCOUNT at start.
"""
from __future__ import annotations
import hashlib
import json
import pathlib
import re
import subprocess
import sys

import yaml

def find_workspace_root(start_path: pathlib.Path | None = None) -> pathlib.Path:
    """Find the workspace root containing .tasks and .w0m/sdlc.json."""
    cur = (start_path or pathlib.Path(__file__)).resolve()
    for parent in [cur] + list(cur.parents):
        if (parent / ".tasks").is_dir() and (parent / ".w0m").is_dir():
            return parent
        if (parent / ".git").exists() and (parent / "wom7web").is_dir():
            return parent
    return pathlib.Path(__file__).resolve().parents[1]


WORKSPACE_ROOT = find_workspace_root()
WEB_ROOT = WORKSPACE_ROOT / "wom7web" if (WORKSPACE_ROOT / "wom7web").is_dir() else WORKSPACE_ROOT

sys.path.insert(0, str(WORKSPACE_ROOT / "scripts"))
sys.path.insert(0, str(WEB_ROOT / "project" / "scripts"))

from authz_blanket_gate import strip_jsonc as _strip_jsonc  # noqa: E402  (one JSONC reader, not two)

_sdlc_file = (WORKSPACE_ROOT / ".w0m" / "sdlc.json") if (WORKSPACE_ROOT / ".w0m" / "sdlc.json").is_file() else (WEB_ROOT / ".w0m" / "sdlc.json")
_VCS = json.loads(_strip_jsonc(_sdlc_file.read_text()))["vcs"]
REPO = _VCS["repo"]
BRANCH = _VCS.get("default_branch", "beta")
ACCOUNT = _VCS.get("gh_account", REPO.split("/", 1)[0])

# 🔴 The board's identity is a SEPARATE fact from the acting principal, and this line used to
# collapse them: `OWNER = ACCOUNT`. `ACCOUNT` feeds `gh auth switch --user` and must stay the
# account whose `GH_CONFIG_DIR` this estate isolates; `OWNER` feeds `gh project --owner` and
# becomes the org when the tracker moves (T242). One value cannot be both, and getting it wrong
# is silent in BOTH directions: set it to the org and the auth switch fails, leave it and the
# board half keeps writing to the old board. Both exit 0.
from board_identity import (  # noqa: E402
    BoardIdentityError,
    describe as _describe_board,
    load as _load_board,
    load_board_projection_config as _load_board_config,
)

try:
    BOARD = _load_board()
    BOARD_CONFIG = _load_board_config()
except BoardIdentityError as _exc:
    sys.exit(f"FATAL: {_exc}")
OWNER = BOARD["owner"]
PROJECT_TITLE = BOARD["title"]
PROJECT_NUMBER = BOARD["number"]
ROOT = WEB_ROOT
TICKETS_DIR = WORKSPACE_ROOT / ".tasks"
if not TICKETS_DIR.is_dir():
    sys.exit(f"FATAL: Canonical tickets directory not found at {TICKETS_DIR} (AgDR-0025: zero silent fallbacks)")
MANIFEST = ROOT / "project" / "tickets.json"
INDEX = ROOT / "project" / "tickets-sync-index.json"

DRY = "--dry-run" in sys.argv
FORCE_ALL = "--all" in sys.argv
VERIFY = "--verify" in sys.argv

# Bump when the projected field set changes (e.g. T141 adds board fields). Invalidates every entry.
# 2 — T228 (2026-08-16): the label projection changed shape. `area:` is now built from `area`
# instead of `repos`, `repo:` was introduced for what `area:` used to carry, and `queue:` was
# retired. Every cached hash describes the old projection and must be treated as stale.
PROJECTION_VERSION = 2

# How many issues a single list fetch will pull. `gh issue list` paginates internally up to this.
# If a run ever returns exactly this many we cannot tell a full page from a truncation, so we fail
# loudly rather than mirror against a silently truncated view (there are already ~145 issues).
ISSUE_FETCH_LIMIT = 1000

# status -> whether the issue should be CLOSED. `paused` deliberately stays OPEN: T141 measured that
# closing a paused issue makes the board display it as Done, destroying the very nuance T32 was set
# to `paused` to preserve. Do not add to this set without re-reading that finding.
CLOSED_STATES = {"done"}

# The label namespaces THIS script owns. Reconciliation removes only within these, so a hand-added
# label (`good-first-issue`, a milestone tag) survives a sync.
# ── the label projection is DECLARED, not hardcoded (T228 AC1) ──────────────────────
# This tuple used to be the only statement of which namespaces w0m publishes, and it sat here while
# `ticket_schema_check.py` held its own copy of the vocabularies. That split is what hid the
# defect below for the life of the mirror.
#
# 🔴 `area:` IS BUILT FROM `repos`, NOT FROM `area`. So GitHub's `area:web` (170 issues) and
# `area:api` (129) are REPOSITORY names, while a ticket's real thematic `area` (sdlc 48, product 39,
# security 28, …) is published nowhere. The namespace and its source have never agreed. The schema
# now records that mismatch as a `defect:` on the namespace, so renaming it to `repo:` is a data
# edit here rather than an archaeology exercise — tracked as T228 AC2, which also has to REMOVE the
# stale labels, since `reconcile_labels()` only prunes inside namespaces we own.
_SCHEMA_PATH = ROOT / "project" / "tickets-schema.jsonc"
_SCHEMA = json.loads(_strip_jsonc(_SCHEMA_PATH.read_text()))
_GH = _SCHEMA["github"]
# T239 AC7 — our `closed_as` value -> the string `gh issue close --reason` accepts. Read from the
# schema so the projection cannot drift from the vocabulary the way `area:` did (T228 AC2).
_CLOSE_REASON: dict[str, str] = dict(_SCHEMA["vocabularies"]["closed_as"]["gh_reason"])

#: prefix -> source frontmatter field, e.g. {"status:": "status", "repo:": "repos"}
NAMESPACE_SOURCE: dict[str, str] = {
    prefix: spec["from"] for prefix, spec in _GH["owned_label_namespaces"].items()
}
#: the frontmatter field published as a bare label (priority: `P1`, not `priority:P1`)
BARE_LABEL_SOURCE: str = _GH["bare_labels"]["from"]

#: Retired namespaces — OWNED (so reconciliation can prune them) but never DESIRED.
#: 🔴 They must stay in OWNED_PREFIXES. Dropping a namespace from the schema instead of retiring it
#: does not clean the labels up — it strands them, because `reconcile_labels()` only removes inside
#: namespaces we own. Retiring is how a label namespace actually gets deleted.
RETIRED_PREFIXES: tuple[str, ...] = tuple(_GH.get("retired_label_namespaces", {}))

OWNED_PREFIXES = ("P", *NAMESPACE_SOURCE, *RETIRED_PREFIXES)

LABELS = {
    # name: (color, description)
    "P0": ("b60205", "Priority 0 — drop-everything"),
    "P1": ("d93f0b", "Priority 1"),
    "P2": ("fbca04", "Priority 2"),
    "status:queued": ("ededed", "Queued"),
    "status:in-progress": ("0e8a16", "In progress"),
    "status:blocked": ("b60205", "Blocked / regression-shaped"),
    "status:done": ("5319e7", "Done"),
    "status:paused": ("c5def5", "Paused"),
    "queue:now": ("0e8a16", "NOW"),
    "queue:next": ("1d76db", "NEXT"),
    "queue:p1": ("d93f0b", "P1 platform/tooling"),
    "queue:backlog-ai": ("5319e7", "Backlog — AI engine"),
    "queue:backlog-platform": ("5319e7", "Backlog — platform"),
    "queue:security": ("b60205", "Security / ops"),
}
AREA_COLOR = "c2e0c6"


# ── the shell seam ───────────────────────────────────────────────────────────────────
# Every subprocess call goes through RUN so the test suite can substitute a recording double.
# Without this seam the tests would need the network and would prove nothing offline.

def _real_run(args: list[str]) -> tuple[int, str, str]:
    r = subprocess.run(args, capture_output=True, text=True)
    return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()


RUN = _real_run


def sh(args: list[str], check=True) -> str:
    code, out, err = RUN(args)
    if check and code != 0:
        raise RuntimeError(f"$ {' '.join(args)}\n{err}")
    return out


# ── pure core (no I/O — this is what the unit tests drive) ───────────────────────────

def is_owned(label: str) -> bool:
    """True if `label` lives in a namespace this script maintains.

    `P` is matched as `P<digit>` rather than as a bare prefix, or it would swallow any hand-added
    label starting with a capital P and silently delete it.
    """
    if re.fullmatch(r"P\d+", label):
        return True
    return any(label.startswith(p) for p in OWNED_PREFIXES if p != "P")


def desired_labels(ticket: dict) -> set[str]:
    """Project a ticket's fields onto labels, per `tickets-schema.jsonc → github`.

    Behaviour is byte-identical to the hardcoded version it replaces; what changes is that the
    prefix→field mapping is now DATA, so the `area:`-built-from-`repos` mismatch is visible in a
    file instead of only in this function body.

    ⚠️ A falsy value publishes nothing. That is why four issues carry the literal label
    `queue:None` today — those came from a path that stringified an empty field before this guard
    existed. Removing them is a migration step, not a code change: reconciliation only ADDS what is
    desired and removes what is owned-but-unwanted, and `queue:None` is owned, so a plain re-sync
    does clear it once the source field is fixed.
    """
    out: set[str] = set()
    bare = ticket.get(BARE_LABEL_SOURCE)
    if bare:
        out.add(str(bare))
    for prefix, field in NAMESPACE_SOURCE.items():
        val = ticket.get(field)
        if not val:
            continue
        for v in (val if isinstance(val, list) else [val]):
            if v:
                out.add(f"{prefix}{v}")
    return out


def reconcile_labels(current: set[str], desired: set[str]) -> tuple[list[str], list[str]]:
    """Return (to_add, to_remove). Removal is confined to the namespaces we own."""
    to_add = sorted(desired - current)
    to_remove = sorted({c for c in current if is_owned(c)} - desired)
    return to_add, to_remove


def desired_board_fields(ticket: dict, board_cfg: dict | None = None) -> dict[str, str]:
    """T141 AC1, AC2, AC3, AC4, AC7 — Map a ticket's frontmatter (and optional SDLC lifecycle stage)
    onto Projects v2 board fields (`Status`, `Priority`, `Area`, `Epic`, `Repo`) using the versioned
    mapping declared in `.w0m/sdlc.json → board`.
    """
    cfg = board_cfg or BOARD_CONFIG
    status_map: dict[str, str] = cfg.get("status_map") or {}
    lifecycle_map: dict[str, str] = cfg.get("lifecycle_map") or {}
    fields_map: dict[str, str] = cfg.get("fields") or {}

    raw_status = str(ticket.get("status") or "").strip().replace("_", "-")
    stage = str(ticket.get("lifecycle_stage") or "").strip()

    # Explicit ticket status (`paused`, `blocked`, `done`, `in-progress`, `queued`) takes precedence;
    # if an active gate stage is supplied and status is generic, `lifecycle_map` refines it.
    if raw_status in status_map:
        mapped_status = status_map[raw_status]
    elif stage and stage in lifecycle_map:
        mapped_status = lifecycle_map[stage]
    else:
        mapped_status = status_map.get("queued", raw_status or "queued")

    out: dict[str, str] = {}
    for board_field, source_key in fields_map.items():
        if board_field == "Status":
            out["Status"] = mapped_status
            continue
        val = ticket.get(source_key)
        if isinstance(val, list):
            joined = ",".join(str(x).strip() for x in val if x)
            if joined:
                out[board_field] = joined
        elif val is not None and str(val).strip():
            out[board_field] = str(val).strip()
    return out


def sync_board_item_fields(
    proj_id: str,
    item_id: str,
    ticket: dict,
    board_fields_meta: dict[str, dict],
    board_cfg: dict | None = None,
) -> int:
    """T141 AC2, AC4, AC5 — Write `Status`, `Priority`, `Area`, `Epic`, `Repo` onto a Projects v2
    board item. Returns the count of field mutations executed.
    """
    if not proj_id or not item_id or not board_fields_meta:
        return 0
    desired = desired_board_fields(ticket, board_cfg)
    writes = 0
    for field_name, want_val in desired.items():
        if not want_val:
            continue
        fmeta = board_fields_meta.get(field_name)
        if not fmeta or not fmeta.get("id"):
            continue
        field_id = str(fmeta["id"])
        options = fmeta.get("options")
        if isinstance(options, dict):
            opt_id = options.get(want_val)
            if not opt_id:
                continue
            sh(
                [
                    "gh",
                    "project",
                    "item-edit",
                    "--id",
                    item_id,
                    "--project-id",
                    proj_id,
                    "--field-id",
                    field_id,
                    "--single-select-option-id",
                    str(opt_id),
                ],
                check=True,
            )
            writes += 1
        else:
            sh(
                [
                    "gh",
                    "project",
                    "item-edit",
                    "--id",
                    item_id,
                    "--project-id",
                    proj_id,
                    "--field-id",
                    field_id,
                    "--text",
                    want_val,
                ],
                check=True,
            )
            writes += 1
    return writes


def check_board_drift(
    tickets: list[dict],
    board_items: list[dict],
    board_cfg: dict | None = None,
) -> list[str]:
    """T141 AC6 & AC8 — Compare Projects v2 board state against ticket frontmatter and return
    human-readable mismatch descriptions.

    🔴 AC6 / AC8 anti-vacuity discipline: MUST FAIL on an empty ticket list or empty board item list,
    never pass vacuously.
    """
    if not tickets or not board_items:
        return [
            f"board drift: empty input set (tickets={len(tickets)}, board_items={len(board_items)}) — "
            "refusing to report 0 mismatches over an empty set (T141 AC6/AC8)"
        ]

    cfg = board_cfg or BOARD_CONFIG
    by_issue: dict[int, dict] = {}
    for item in board_items:
        num = item.get("issue_number") or (item.get("content") or {}).get("number")
        if isinstance(num, int):
            by_issue[num] = item

    if not by_issue:
        return [
            "board drift: 0 board items carry an issue number — refusing to pass on unmapped board set"
        ]

    mismatches: list[str] = []
    compared = 0
    for t in tickets:
        gh_num = t.get("gh_issue")
        if not isinstance(gh_num, int):
            continue
        b_item = by_issue.get(gh_num)
        if b_item is None:
            mismatches.append(f"{t['id']} (#{gh_num}): missing from Project board")
            continue
        compared += 1
        desired = desired_board_fields(t, cfg)
        live_fields = b_item.get("fields") or {}
        want_status = desired.get("Status")
        have_status = live_fields.get("Status", b_item.get("status"))
        if want_status and have_status != want_status:
            mismatches.append(
                f"{t['id']} (#{gh_num}): board Status is {have_status!r}, ticket requires {want_status!r}"
            )
        for fname in ("Priority", "Area", "Epic", "Repo"):
            want_val = desired.get(fname)
            if want_val and fname in live_fields and live_fields[fname] != want_val:
                mismatches.append(
                    f"{t['id']} (#{gh_num}): board {fname} is {live_fields[fname]!r}, ticket requires {want_val!r}"
                )

    if compared == 0 and not mismatches:
        return [
            "board drift: 0 tickets with gh_issue matched against board — refusing vacuous pass"
        ]
    return mismatches


REPO_BLOB = f"https://github.com/{REPO}/blob/{BRANCH}"
AC_LINE = re.compile(r"^\s*-\s*\[([ x~])\]\s*\*{0,2}AC\d", re.M | re.I)


def ticket_meta(ticket_id: str) -> dict:
    """AC counts + whether the summary hit the truncation cap — facts the body must state."""
    f = TICKETS_DIR / f"{ticket_id}.md"
    if not f.exists():
        return {}
    txt = f.read_text()
    marks = AC_LINE.findall(txt)
    m = re.search(r"^## Summary\s*\n(.*?)(?=\n## )", txt, re.S | re.M)
    raw = (m.group(1).strip() if m else "")
    return {"ac_total": len(marks), "ac_done": sum(1 for x in marks if x.lower() == "x"),
            "truncated": len(raw) > 4000}


def ticket_diagrams(ticket_id: str) -> list[tuple[str, str]]:
    """Discover all sibling `.tasks/T{id}*.mmd` files for a ticket (T211 AC1).

    Returns a list of (title, raw_mermaid_content) sorted by filename.
    Matches:
      - T211.mmd -> title: "Architecture Diagram"
      - T211-arch-flow.mmd -> title: "Arch Flow"
      - T211_state_machine.mmd -> title: "State Machine"
    """
    if not TICKETS_DIR.is_dir():
        return []
    pat = re.compile(rf"^{re.escape(ticket_id)}(?:[-_](.+))?\.mmd$")
    diagrams = []
    def sort_key(p: pathlib.Path) -> tuple[int, str]:
        if p.name == f"{ticket_id}.mmd":
            return (0, "")
        return (1, p.name)

    for f in sorted(TICKETS_DIR.glob(f"{ticket_id}*.mmd"), key=sort_key):
        m = pat.match(f.name)
        if not m:
            continue
        suffix = m.group(1)
        if suffix:
            title = suffix.replace("-", " ").replace("_", " ").strip().title()
        else:
            title = "Architecture Diagram"
        try:
            content = f.read_text(encoding="utf-8").strip()
            # If the file accidentally includes a markdown ```mermaid code fence, unwrap it
            if content.startswith("```"):
                content = re.sub(r"^```(?:mermaid)?\s*", "", content)
                content = re.sub(r"\s*```$", "", content)
                content = content.strip()
            if content:
                diagrams.append((title, content))
        except OSError:
            continue
    return diagrams


def build_body(ticket: dict, summary: str, meta: dict | None = None) -> str:
    """T228 AC7 — the body must DECLARE that it is a partial projection.

    🔴 The previous version put *"Mirror of the markdown ticket"* in a FOOTER, below the prose. Two
    problems, and both make an issue read as the whole ticket: the word *mirror* implies
    completeness, and the disclaimer arrives after a reader has already formed an impression. What
    is actually sent is the **`## Summary` section only** — no acceptance criteria, no status notes,
    no history — and it is **silently truncated at 4,000 characters**.

    ⇒ The declaration moves to the TOP, names what is missing, and carries the AC count so the gap
    is a number rather than a feeling. Truncation is stated where it happens instead of being
    invisible.
    """
    m = meta or {}
    tid = ticket["id"]
    done, total = m.get("ac_done", 0), m.get("ac_total", 0)
    ac = (f"**{done}/{total} acceptance criteria** — not shown here" if total
          else "no acceptance criteria recorded")
    cut = "\n\n> ⚠️ **Summary truncated at 4,000 characters.**" if m.get("truncated") else ""
    base = (f'> ⚠️ **PARTIAL PROJECTION — not the ticket.** This issue carries the `## Summary` '
            f'section only. {ac}; status notes, decisions and history live in the source file.\n'
            f'> **Source of truth:** [`.tasks/{tid}.md`]'
            f'({REPO_BLOB}/.tasks/{tid}.md) — edit there and re-run the sync; '
            f'hand-edits here are overwritten.{cut}\n\n'
            f'{summary}\n\n---\n'
            f'**Epic:** {ticket.get("epic") or "—"} · **Spec:** {ticket.get("spec") or "—"}\n'
            f'**Status:** {ticket.get("status")} · **Priority:** {ticket.get("priority") or "—"} '
            f'· **Repos:** {", ".join(ticket.get("repos", [])) or "—"}')

    diagrams = ticket_diagrams(tid)
    if not diagrams:
        return base

    blocks = [
        f"<details open><summary>📊 {title}</summary>\n\n```mermaid\n{content}\n```\n</details>"
        for title, content in diagrams
    ]
    return f"{base}\n\n---\n### Architecture Diagrams\n\n" + "\n\n".join(blocks)


def projection_of(ticket: dict, summary: str) -> dict:
    """The exact set of facts this script pushes to GitHub. Hash THIS, never the .md file.

    A ticket file changes constantly in prose the mirror never sends; hashing the file would make
    the index useless. (Same lesson as T131's content hash, which had to exclude the stamp it
    certified.)
    """
    out = {
        "title": f'{ticket["id"]} — {ticket.get("title", "")}',
        "body": build_body(ticket, summary, ticket_meta(ticket["id"])),
        "labels": sorted(desired_labels(ticket)),
        "closed": ticket.get("status") in CLOSED_STATES,
    }
    # 🔴 T239 AC7. Until this existed the projection said only THAT a ticket was closed, so GitHub
    # applied its own default and every one of 76 closed issues read COMPLETED — including the ones
    # that were not.
    # ⚠️ The key is OMITTED rather than set to None when nothing is declared, and that is load-
    # bearing for two reasons. (1) `projection_hash` hashes this dict, so emitting `reason: None`
    # on every ticket changed all 235 hashes and a dry run demanded 235 API updates to say nothing
    # new. (2) It matches the decision that absence is not a correction: a ticket that declares
    # nothing must project nothing, not an assertion of `completed`.
    reason = _CLOSE_REASON.get(str(ticket.get("closed_as") or ""))
    if reason:
        out["reason"] = reason
    return out


def projection_hash(projection: dict) -> str:
    canon = json.dumps(projection, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def load_index() -> dict:
    """Read the committed index. A version mismatch discards every entry."""
    if not INDEX.exists():
        return {}
    try:
        data = json.loads(INDEX.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print(" [WARN] sync index unreadable — treating every ticket as stale")
        return {}
    if data.get("projection_version") != PROJECTION_VERSION:
        print(f" [INFO] projection_version moved "
              f"({data.get('projection_version')} → {PROJECTION_VERSION}) — full re-sync")
        return {}
    return data.get("tickets", {}) or {}


def save_index(hashes: dict[str, str]):
    """Stable key order: an index that reorders every run is a permanent merge conflict against
    the parallel Antigravity agent."""
    payload = {
        "_comment": ("Generated by scripts/sync_github.py (T150). Records the hash of the "
                     "projection last pushed to GitHub, so an unchanged ticket costs zero calls. "
                     "Do not hand-edit; delete the file to force a full re-sync."),
        "projection_version": PROJECTION_VERSION,
        "tickets": {k: hashes[k] for k in sorted(hashes, key=lambda t: int(re.sub(r"[^0-9]", "", t) or 0))},
    }
    INDEX.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def needs_sync(ticket_id: str, projection: dict, index: dict, live: dict | None) -> bool:
    """Decide whether a ticket must be pushed.

    `live` is what the single issue-list fetch already told us (title/labels/state). Comparing
    against it makes the mirror self-heal when an issue is edited by hand; the index then only has
    to cover the body, which the list fetch cannot see.
    """
    if FORCE_ALL or live is None:
        return True
    if index.get(ticket_id) != projection_hash(projection):
        return True                                   # body (or anything else) moved
    if live["title"] != projection["title"]:
        return True
    if live["closed"] != projection["closed"]:
        return True
    add, remove = reconcile_labels(live["labels"], set(projection["labels"]))
    return bool(add or remove)


# ── I/O layer ────────────────────────────────────────────────────────────────────────

def ensure_account():
    """Pin the acting principal, and REFUSE to continue if the pin did not take.

    🔴 This ran with `check=False` and nothing read the result. A failing `gh auth switch` was
    therefore swallowed whole: the sync carried on as whatever account happened to be active,
    defeating the `GH_CONFIG_DIR` isolation the estate maintains for exactly this reason, and
    exited 0. The repo-resolution check below did not cover it — another account with access to
    the same repo resolves it perfectly well.
    """
    switched = subprocess.run(["gh", "auth", "switch", "--user", ACCOUNT],
                              capture_output=True, text=True, check=False)
    if switched.returncode != 0:
        sys.exit(f"FATAL: gh auth switch --user {ACCOUNT} failed "
                 f"({switched.stderr.strip()[:200] or 'no stderr'}). Refusing to sync as whoever "
                 f"is active — that is how the account isolation gets defeated silently.")
    active = sh(["gh", "api", "user", "-q", ".login"], check=False)
    if active and active != ACCOUNT:
        sys.exit(f"FATAL: active gh account is '{active}', expected '{ACCOUNT}'.")
    who = sh(["gh", "repo", "view", REPO, "--json", "nameWithOwner", "-q", ".nameWithOwner"], check=False)
    if who != REPO:
        sys.exit(f"FATAL: gh cannot resolve {REPO} (got '{who}'). Active account wrong or no access.")


def ensure_labels(tickets: list[dict]):
    """Upsert every label ANY ticket actually uses — not just the hardcoded set — so a later
    `gh issue create --label <x>` can never fail on a missing label (that would abort the sync)."""
    used: set[str] = set()
    for t in tickets:
        used |= desired_labels(t)
    for name in sorted(used):
        color, desc = LABELS.get(
            name, (AREA_COLOR if name.startswith("area:") else "ededed", name))
        if DRY:
            print(f"  [dry] label {name}")
            continue
        # --force upserts (create or update color/description) without erroring if it exists
        sh(["gh", "label", "create", name, "--color", color, "--description", desc,
            "--force", "--repo", REPO], check=False)


def get_or_create_project() -> tuple[str, str]:
    """Return (project_number, project_url) for the DECLARED board.

    🔴 Resolution is by NUMBER, with the title used as a guard — not the other way round. Taking
    the first board whose title matches is what `gh project copy` defeats: the copy leaves two
    boards called "w0m Delivery", one under each owner, and a stale owner then finds a real,
    live-looking board. Items land on it, every command succeeds, and nothing reaches the board
    the run was for.

    A title mismatch is fatal rather than a warning. It means the declaration and the live board
    have diverged, and the whole point of declaring an identity is that we stop guessing which of
    the two is right.
    """
    out = sh(["gh", "project", "list", "--owner", OWNER, "--format", "json"], check=False)
    try:
        items = json.loads(out).get("projects", []) if out else []
    except json.JSONDecodeError:
        items = []

    by_number = {int(p["number"]): p for p in items if str(p.get("number", "")).isdigit()}
    live = by_number.get(PROJECT_NUMBER)
    if live is not None:
        if live.get("title") != PROJECT_TITLE:
            sys.exit(f"FATAL: {_describe_board(BOARD)} is declared, but #{PROJECT_NUMBER} under "
                     f"{OWNER} is titled '{live.get('title')}'. Fix `.w0m/sdlc.json → board` or the "
                     f"board — do not let a run pick which one is right.")
        return str(live["number"]), live.get("url", "")

    same_title = [p for p in items if p.get("title") == PROJECT_TITLE]
    if same_title:
        found = ", ".join(f"#{p['number']}" for p in same_title)
        sys.exit(f"FATAL: no board #{PROJECT_NUMBER} under {OWNER}, but {found} carry the declared "
                 f"title '{PROJECT_TITLE}'. This is the `gh project copy` shape — update "
                 f"`.w0m/sdlc.json → board.number` deliberately rather than adopting a lookalike.")

    if DRY:
        print(f"  [dry] create project '{PROJECT_TITLE}' under {OWNER}")
        return "", ""
    out = sh(["gh", "project", "create", "--owner", OWNER, "--title", PROJECT_TITLE, "--format", "json"])
    p = json.loads(out)
    print(f"  created board #{p['number']} — update `.w0m/sdlc.json → board.number` to match")
    return str(p["number"]), p.get("url", "")


def load_tickets() -> list[dict]:
    """Build the ticket list from the .md frontmatter (the source of truth), sorted by numeric id.

    Replaces the old hand-maintained tickets.json (which drifted — new tickets never synced).
    Also refreshes MANIFEST as a derived snapshot so its git diff shows what the sync will mirror.
    """
    tickets: list[dict] = []
    for f in sorted(TICKETS_DIR.glob("T*.md")):
        parts = f.read_text(encoding="utf-8").split("---", 2)
        if len(parts) < 3:
            continue  # no frontmatter block
        try:
            fm = yaml.safe_load(parts[1]) or {}
        except yaml.YAMLError:
            print(f" [WARN] skipping {f.name}: unparseable frontmatter")
            continue
        # gh_issue is the recorded idempotency key (AC1). Validated as an int here so a corrupted
        # value can never reach a `gh` argument list.
        raw_issue = fm.get("gh_issue")
        try:
            # `is None or == ""` rather than `not in (None, "")`: same runtime meaning, but the
            # membership form does not narrow the type, so `int()` was being handed `Any | None`
            # with only the except clause standing between it and a TypeError (T188).
            gh_issue = None if raw_issue is None or raw_issue == "" else int(raw_issue)
        except (TypeError, ValueError):
            print(f" [WARN] {f.name}: gh_issue is not an integer ({raw_issue!r}) — ignoring it")
            gh_issue = None
        tickets.append({
            "id": str(fm.get("id") or f.stem),
            "title": fm.get("title", ""),
            # normalize stray underscores to the canonical hyphen (e.g. in_progress → in-progress)
            # so a frontmatter typo maps onto the real label instead of minting an ugly duplicate.
            "status": str(fm.get("status", "")).replace("_", "-"),
            "queue": str(fm.get("queue", "")).replace("_", "-"),
            "priority": fm.get("priority", ""),
            "repos": fm.get("repos") or [],
            # 🔴 `area` was ABSENT from this projection until 2026-08-16, and that absence is half
            # of why the `area:` label namespace could be built from `repos` without anyone
            # noticing: the real field never reached this function, so there was nothing for the
            # projection to disagree with. Adding the namespace to the schema alone produced ZERO
            # labels — the dry run caught it, which is the only reason it is not shipped broken.
            "area": str(fm.get("area", "")).strip(),
            "epic": fm.get("epic", ""),
            "spec": fm.get("spec", ""),
            "tags": fm.get("tags") or [],
            "gh_issue": gh_issue,
            # 🔴 T239 AC7 — and this line was MISSING on the first cut, reproducing the `area`
            # failure documented 12 lines above verbatim: the schema declared the vocabulary, the
            # projection read `ticket.get("closed_as")`, and the loader never put it in the dict, so
            # every reason resolved to None and a dry run reported "nothing to sync" while two
            # tickets demonstrably disagreed with GitHub. The dry run caught it, exactly as that
            # comment says it did last time. ⇒ **A field is not wired until the LOADER carries it.**
            "closed_as": str(fm.get("closed_as", "")).strip(),
            "file": f".tasks/{f.name}",
        })
    # Every field the schema publishes MUST exist in this projection, or that namespace silently
    # emits nothing. That is not hypothetical: `area:` was added to the schema and produced 0
    # labels because `area` was missing from the dict above, and a sync reporting "226 updated"
    # looked entirely successful while publishing none of them. A namespace that cannot fire is
    # the same vacuous-green shape as a probe that cannot fire.
    if tickets:
        needed = set(NAMESPACE_SOURCE.values()) | {BARE_LABEL_SOURCE}
        missing = sorted(needed - set(tickets[0]))
        if missing:
            raise SystemExit(
                f"❌ tickets-schema.jsonc publishes {missing} but load_tickets() does not project "
                f"{'them' if len(missing) > 1 else 'it'} — that namespace would emit nothing. "
                f"Add the field to the ticket dict in load_tickets()."
            )

    tickets.sort(key=lambda t: int(re.sub(r"[^0-9]", "", t["id"]) or 0))
    if not DRY:
        snapshot = [{k: v for k, v in t.items() if k != "gh_issue"} for t in tickets]
        MANIFEST.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return tickets


def summary_of(ticket_id: str) -> str:
    """Extract the '## Summary' section body from the ticket .md, for the issue body."""
    f = TICKETS_DIR / f"{ticket_id}.md"
    if not f.exists():
        return ""
    txt = f.read_text()
    # 🔴 The heading may carry a SUFFIX — `## Summary — what was measured, 2026-08-16`. The original
    # pattern required the line to be exactly `## Summary`, so 11 of 228 tickets matched nothing and
    # pushed an **EMPTY body** to GitHub. T228's own issue was one of them: blank, then `---`, then
    # the metadata footer. ⚠️ Found 2026-08-18 while building AC7's banner — the projection was not
    # merely partial for those, it was empty, and nothing said so because an empty match returns "".
    m = re.search(r"^## Summary\b[^\n]*\n(.*?)(?=\n## )", txt, re.S | re.M)
    body = (m.group(1).strip() if m else "")
    if not body:
        # An empty summary must be VISIBLE, not silently published as blank prose.
        return ("_This ticket's `## Summary` section is empty or could not be parsed — read the "
                "source file._")
    return body[:4000]


def fetch_issues() -> dict[int, dict]:
    """ONE list fetch for the whole run (AC4), open AND closed — a `done` ticket's issue is closed,
    so an open-only fetch would re-create it."""
    out = sh(["gh", "issue", "list", "--repo", REPO, "--state", "all",
              "--limit", str(ISSUE_FETCH_LIMIT),
              "--json", "number,title,labels,state,stateReason,id"], check=True)
    try:
        rows = json.loads(out or "[]")
    except json.JSONDecodeError:
        raise RuntimeError("could not parse the issue list — refusing to sync against an unknown state")
    if len(rows) >= ISSUE_FETCH_LIMIT:
        raise RuntimeError(
            f"issue list hit the {ISSUE_FETCH_LIMIT} cap — a truncated view is indistinguishable "
            f"from a complete one, so the sync is refusing to run. Raise ISSUE_FETCH_LIMIT.")
    return {
        int(r["number"]): {
            "title": r["title"],
            "labels": {lb["name"] for lb in (r.get("labels") or [])},
            "closed": str(r.get("state", "")).lower() == "closed",
            # GitHub reports the enum (`NOT_PLANNED`); the CLI takes prose ("not planned"). Normalise
            # to the CLI's spelling here so exactly one comparison is needed downstream.
            "reason": (str(r.get("stateReason") or "").lower().replace("_", " ") or None),
            "node_id": r.get("id"),
        }
        for r in rows
    }


def resolve_by_title(ticket_id: str, issues: dict[int, dict]) -> int | None:
    """Fallback for a ticket with no recorded number — answered from the ONE fetch, not the network."""
    prefix = f"{ticket_id} — "
    for num, meta in issues.items():
        if meta["title"].startswith(prefix):
            return num
    return None


def backfill(ticket_id: str, number: int | None):
    """Record (or clear) the issue number in the ticket frontmatter.

    🔴 It must INSERT the field when it is absent, not only replace it. The original implementation
    was a bare `re.sub` on `^gh_issue:`, which silently did nothing for a ticket that never had the
    key — so 8 tickets (T66, T119-T125) went on re-resolving by title forever while the mirror
    reported success. AC1 is "the recorded number is the idempotency key"; a backfill that cannot
    create the record makes that contract quietly unenforceable.
    """
    f = TICKETS_DIR / f"{ticket_id}.md"
    txt = f.read_text()
    line = f"gh_issue: {number if number is not None else ''}".rstrip()

    if re.search(r"^gh_issue:", txt, re.M):
        new = re.sub(r"^gh_issue:.*$", line, txt, count=1, flags=re.M)
    else:
        parts = txt.split("---", 2)
        if len(parts) < 3:
            return                      # no frontmatter block — nothing safe to edit
        new = "---" + parts[1].rstrip("\n") + "\n" + line + "\n---" + parts[2]

    if new != txt and not DRY:
        f.write_text(new)


def push_issue(num: int, projection: dict, live: dict) -> None:
    """Push the WHOLE projection to an existing issue (AC2b) with reconciled labels (AC3c)."""
    args = ["gh", "issue", "edit", str(num), "--repo", REPO]
    if live["title"] != projection["title"]:
        args += ["--title", projection["title"]]
    args += ["--body", projection["body"]]
    add, remove = reconcile_labels(live["labels"], set(projection["labels"]))
    if add:
        args += ["--add-label", ",".join(add)]
    if remove:
        args += ["--remove-label", ",".join(remove)]
    sh(args, check=True)

    # Closed-state is symmetric: done closes, un-done reopens. Before T150 this fired only on
    # create, which is why 7 of 19 done tickets still had open issues.
    want_reason = projection.get("reason")
    if projection["closed"] and not live["closed"]:
        args = ["gh", "issue", "close", str(num), "--repo", REPO]
        if want_reason:
            args += ["--reason", want_reason]
        sh(args, check=False)
    elif not projection["closed"] and live["closed"]:
        sh(["gh", "issue", "reopen", str(num), "--repo", REPO], check=False)
    elif (projection["closed"] and live["closed"] and want_reason
          and live.get("reason") != want_reason):
        # Already closed, and the reason on GitHub disagrees with what the ticket now declares.
        # `gh issue close` will not re-close an issue, so this goes through the mutation that can
        # amend a closed issue's reason. ⚠️ Only fires when the ticket DECLARES one: absence must
        # never overwrite a value already on GitHub, because "we have not said" is not a correction.
        enum = want_reason.upper().replace(" ", "_")
        if live.get("node_id"):
            sh(["gh", "api", "graphql", "-f",
                "query=mutation($i:ID!){updateIssue(input:{id:$i,stateInput:"
                "{value:CLOSED,stateReason:" + enum + "}}){issue{number stateReason}}}",
                "-f", f"i={live['node_id']}"], check=False)


def run_verify(tickets: list[dict], issues: dict[int, dict]) -> int:
    """Audit recorded gh_issue numbers against reality. Mutates nothing."""
    bad = 0
    for t in tickets:
        tid, rec = t["id"], t["gh_issue"]
        actual = resolve_by_title(tid, issues)
        if rec is None:
            if actual is not None:
                print(f" [WARN] {tid}: no recorded number, but #{actual} matches by title")
                bad += 1
            continue
        if rec not in issues:
            print(f"  ✗ {tid}: recorded #{rec} does not exist")
            bad += 1
        elif not issues[rec]["title"].startswith(f"{tid} — "):
            print(f"  ✗ {tid}: recorded #{rec} is '{issues[rec]['title'][:50]}…'")
            bad += 1
    print(f"\n{'✓ every recorded number checks out' if not bad else f'✗ {bad} mismatch(es)'}")
    return 1 if bad else 0


def main() -> int:
    # Line-buffer stdout. This script's normal home is a DETACHED background run whose stdout is a
    # file, and Python block-buffers to a file: a ~10-minute sweep writes under one buffer's worth
    # of progress lines, so the log stays EMPTY until the process exits. STATE.md records exactly
    # that confusion — an empty log "is indistinguishable from the hang it has actually suffered
    # before". AC6 says a failure must surface where a human looks, and an unflushed log cannot.
    try:
        # `reconfigure` exists on TextIOWrapper, not on the TextIO the stub declares — this is
        # deliberately a runtime capability probe, which is why it sits in a try/except.
        # Narrow ignore, not a blanket: `warn_unused_ignores` will flag it if it stops
        # being needed (T188).
        sys.stdout.reconfigure(line_buffering=True)  # type: ignore[union-attr]
    except (AttributeError, OSError):
        pass                                    # older/odd streams — progress logging is not critical

    ensure_account()
    tickets = load_tickets()
    print(f"→ {len(tickets)} tickets. Repo={REPO} "
          f"dry={DRY} all={FORCE_ALL} verify={VERIFY}")

    print("→ fetching issues (one call)…")
    issues = fetch_issues()
    print(f"   {len(issues)} issues")

    if VERIFY:
        return run_verify(tickets, issues)

    index = load_index()
    hashes: dict[str, str] = dict(index)
    created = updated = skipped = failed = 0

    # ── phase 1: decide the work set BEFORE any mutation ─────────────────────────────
    # Nothing that writes may run before this. `ensure_labels` upserts a label per namespace and
    # `get_or_create_project` can create a project — both are mutations, so calling them
    # unconditionally would mean a no-op sync still wrote to GitHub, and AC5's "a no-op run makes
    # ZERO mutating calls" would be false while appearing true in the summary line.
    # `found` pairs the resolved number with the live issue it came from, or is None for "create".
    # They are ONE fact, not two: after the re-resolution below, `num` is either None or a key of
    # `issues`, so a number without a live issue is not a state this loop can produce. Carrying
    # them as separate values let phase 2 claim it could — see the note there.
    work: list[tuple[dict, dict, str, tuple[int, dict] | None]] = []
    for t in tickets:
        tid = t["id"]
        projection = projection_of(t, summary_of(tid))
        phash = projection_hash(projection)

        num = t["gh_issue"]
        if num is not None and num not in issues:
            print(f" [WARN] {tid}: recorded #{num} is gone — re-resolving")
            num = None
        if num is None:
            num = resolve_by_title(tid, issues)

        # Indexed, not `.get()`: `num` is here only because it was found in `issues`, so a KeyError
        # would mean the re-resolution above stopped holding — which should be loud, and is safe to
        # be loud about in this phase because nothing has been mutated yet.
        found = (num, issues[num]) if num is not None else None

        # Record the resolved number even when nothing needs pushing. The key is LOCAL state, so
        # gating it on "does GitHub need an update" would leave a ticket resolving by title forever
        # once the index says it is current — which is exactly how 8 tickets stayed unrecorded.
        if num is not None and t["gh_issue"] != num:
            backfill(tid, num)

        if found is not None and not needs_sync(tid, projection, index, found[1]):
            skipped += 1
            hashes[tid] = phash
            continue
        work.append((t, projection, phash, found))

    if not work:
        if not DRY:
            live_ids = {t["id"] for t in tickets}
            save_index({k: v for k, v in hashes.items() if k in live_ids})
        print(f"\n✓ nothing to sync. skipped={skipped} (zero mutating calls)")
        return 0

    print(f"→ {len(work)} ticket(s) to sync, {skipped} unchanged")
    print("→ ensuring labels…")
    ensure_labels([t for t, *_ in work])
    print("→ ensuring project…")
    proj_num, proj_url = get_or_create_project()
    print(f"   project #{proj_num} {proj_url}")

    # ── phase 2: mutate ──────────────────────────────────────────────────────────────
    for t, projection, phash, found in work:
        tid = t["id"]
        try:
            if DRY:
                print(f"  [dry] {'update' if found else 'create'} {tid} → "
                      f"{('#' + str(found[0])) if found else '(new)'}")
                continue

            # A recorded number pointing at an issue that no longer exists is NOT handled here —
            # it is handled in phase 1, which drops the dead number and re-resolves by title,
            # falling through to this create when nothing matches. T188 first added a third
            # branch for it (`num is not None and live is None`, raising a diagnosis); a test
            # written to exercise that branch proved it never runs, because phase 1 has already
            # made the state unreachable. The pairing above now says so in the type.
            if found is None:
                url = sh(["gh", "issue", "create", "--repo", REPO,
                          "--title", projection["title"], "--body", projection["body"],
                          "--label", ",".join(projection["labels"])])
                num = int(url.rstrip("/").split("/")[-1])
                created += 1
                if projection["closed"]:
                    sh(["gh", "issue", "close", str(num), "--repo", REPO], check=False)
            else:
                num, live = found
                push_issue(num, projection, live)
                updated += 1

            backfill(tid, num)
            if proj_num:
                # T141 AC8 & AC9: `check=True` so a failing `item-add` is never silently swallowed.
                item_out = sh(["gh", "project", "item-add", proj_num, "--owner", OWNER,
                               "--url", f"https://github.com/{REPO}/issues/{num}"], check=True)
                if item_out and item_out.lstrip().startswith("{"):
                    try:
                        item_data = json.loads(item_out)
                    except json.JSONDecodeError:
                        item_data = {}
                    if item_data.get("id") and item_data.get("project_id") and item_data.get("fields_meta"):
                        sync_board_item_fields(
                            str(item_data["project_id"]),
                            str(item_data["id"]),
                            t,
                            item_data["fields_meta"],
                        )
            hashes[tid] = phash
            print(f"  {tid} → #{num}")
        except Exception as e:                                    # noqa: BLE001 — see below
            # A single bad ticket must not stop the mirror, but it must NEVER be silent: this ran
            # detached for months and a TypeError on one malformed cell stopped the whole sync with
            # an empty log. Count it, name it, and exit non-zero at the end.
            failed += 1
            print(f"  ✗ {tid}: {type(e).__name__}: {e}")

    if not DRY:
        # Drop index entries for tickets that no longer exist, or the index grows forever.
        live_ids = {t["id"] for t in tickets}
        save_index({k: v for k, v in hashes.items() if k in live_ids})

    print(f"\n{'✗' if failed else '✓'} done. created={created} updated={updated} "
          f"skipped={skipped} failed={failed} project=#{proj_num}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
