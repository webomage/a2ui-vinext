#!/usr/bin/env python3
"""T242 — probes for the declared board identity.

The three silent breaks this guards against all EXIT 0, which is why they survived. Each probe
below is written against the specific way the old code succeeded while doing the wrong thing:

  1. `sync_github.py` held `OWNER = ACCOUNT`, collapsing the board owner into the acting
     principal. Set it to the org and `gh auth switch` fails — swallowed by `check=False`, so the
     sync ran as whatever account was active and exited 0. Leave it and the board half keeps
     writing to the old board, also exiting 0.
  2. The board was resolved by TITLE and took the first match. `gh project copy` leaves two boards
     with the same title, one per owner, so a stale owner finds a real, live-looking board.
  3. Three scripts, three strategies, no declaration — and two of them hardcoded the owner TYPE
     into their GraphQL root, which an organization-owned project is not reachable through.

⚠️ Output uses the TEXT dialect (`[PASS]`/`[FAIL]`), which `run_suites.py` counts alongside the
glyph dialects. A new suite has no reason to add emoji the estate is currently removing (T257).

Run: `just board-identity-test`
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "w0m-web"
SCRIPTS = ROOT / "scripts"
ROOT_SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(ROOT_SCRIPTS))

import board_identity as bi  # noqa: E402

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        failures.append(f"{label} — {detail}")


def with_board(board) -> Path:
    """A throwaway sdlc.json carrying `board`, so probes never depend on the live declaration."""
    d = Path(tempfile.mkdtemp())
    doc = {"vcs": {"repo": "x/y"}}
    if board is not None:
        doc["board"] = board
    (d / "sdlc.json").write_text(json.dumps(doc), encoding="utf-8")
    return d / "sdlc.json"


print("T242 — board identity\n")

# ── the declaration exists and is complete ──────────────────────────────────────────────────
try:
    LIVE = bi.load()
    loaded = True
except bi.BoardIdentityError as exc:
    LIVE, loaded = {}, False
    print(f"[FAIL] the live .w0m/sdlc.json declares a usable board — {exc}")
    failures.append("live board declaration")

if loaded:
    check("the live declaration carries all four facts",
          set(LIVE) == {"owner", "owner_type", "number", "title"},
          f"got {sorted(LIVE)}")
    check("the live board is the one the estate actually uses",
          LIVE["owner"] == "webomage" and LIVE["owner_type"] == "organization" and LIVE["number"] == 2 and LIVE["title"] == "w0m Delivery",
          f"declared {bi.describe(LIVE)} — if this changed deliberately, change this probe with it")

# ── a HALF declaration must fail, not default ───────────────────────────────────────────────
# The failure mode being prevented: a missing owner_type silently defaulting to "user" is exactly
# the org break, reintroduced by a convenience.
for missing in ("owner", "owner_type", "number", "title"):
    partial = {"owner": "casualuser", "owner_type": "user", "number": 2, "title": "w0m Delivery"}
    partial.pop(missing)
    try:
        bi.load(with_board(partial))
        ok = False
    except bi.BoardIdentityError:
        ok = True
    check(f"a declaration missing `{missing}` is rejected", ok,
          "a half-declared identity is the state this module exists to make impossible")

try:
    bi.load(with_board(None))
    ok = False
except bi.BoardIdentityError:
    ok = True
check("no `board` block at all is rejected", ok, "three scripts would have nothing to agree on")

try:
    bi.load(with_board({"owner": "w", "owner_type": "org", "number": 2, "title": "t"}))
    ok = False
except bi.BoardIdentityError:
    ok = True
check("an owner_type outside {user, organization} is rejected", ok,
      "`org` is the plausible typo; it picks no GraphQL root and would resolve to null, not error")

# ── the GraphQL root follows the DECLARED type ──────────────────────────────────────────────
check("a user-owned board yields the user root",
      bi.graphql_root({"owner": "casualuser", "owner_type": "user"}) == 'user(login:"casualuser")')
check("an org-owned board yields the organization root",
      bi.graphql_root({"owner": "webomage", "owner_type": "organization"})
      == 'organization(login:"webomage")',
      "this is the line the migration turns over; a hardcoded `user(` root returns null under an org")

# ── the load-bearing probes: no script may hold its own copy of the fact ────────────────────
CONSUMERS = [
    ("sync_github.py", ROOT_SCRIPTS / "sync_github.py"),
    ("populate_project_fields.py", SCRIPTS / "populate_project_fields.py"),
    ("sync_project_fields.py", SCRIPTS / "sync_project_fields.py"),
]

for name, script_path in CONSUMERS:
    src = script_path.read_text(encoding="utf-8")
    body = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
    check(f"{name} reads the declared identity",
          "board_identity" in body,
          "a script that does not read the declaration is a fourth encoding of one fact")
    check(f"{name} hardcodes no board owner/number pair",
          not re.search(r'OWNER\s*,\s*PROJECT\s*=\s*["\']', body),
          "this is the literal line that made the org copy unreachable")
    check(f"{name} hardcodes no GraphQL owner root",
          'user(login:"' not in body and 'organization(login:"' not in body,
          "the root must come from board.owner_type; an org project is not reachable via user(…)")

# ── break 1: the two identities must not be the same expression ─────────────────────────────
sync_src = (ROOT_SCRIPTS / "sync_github.py").read_text(encoding="utf-8")
check("sync_github.py no longer collapses the board owner into the acting principal",
      not re.search(r"^OWNER\s*=\s*ACCOUNT\s*$", sync_src, re.M),
      "`OWNER = ACCOUNT` is break 1 — one value cannot be both, and both directions exit 0")
check("sync_github.py still pins the acting principal from vcs.gh_account",
      re.search(r'ACCOUNT\s*=\s*_VCS\.get\("gh_account"', sync_src) is not None,
      "the GH_CONFIG_DIR isolation depends on this staying the account, not the board owner")
# 🔴 BEHAVIOURAL, not a text match. The first version of this probe grepped for `check=False` and
# failed the fixed code — `check=False` is CORRECT here, because the point is to inspect the return
# code rather than raise. The property that matters is whether the result is READ, and only running
# the function can answer that. (A probe asserting the presence of a string is a probe about the
# source, not about the behaviour; that confusion is what it was written to catch in the first
# place.)
import subprocess as _sp  # noqa: E402

sys.argv = [sys.argv[0]]           # sync_github reads flags off argv at import
import sync_github as sg           # noqa: E402

_real_run = sg.subprocess.run


def _switch_fails(cmd, *a, **kw):
    if cmd[:3] == ["gh", "auth", "switch"]:
        return _sp.CompletedProcess(cmd, 1, stdout="", stderr="no such user")
    return _sp.CompletedProcess(cmd, 0, stdout="", stderr="")


sg.subprocess.run = _switch_fails
try:
    sg.ensure_account()
    switch_fatal = False
except SystemExit:
    switch_fatal = True
except Exception:                  # noqa: BLE001 — any other exception is also "did not continue"
    switch_fatal = True
finally:
    sg.subprocess.run = _real_run

check("a failed `gh auth switch` STOPS the run", switch_fatal,
      "it ran with the result unread: the sync continued as whoever was active, defeating the "
      "GH_CONFIG_DIR isolation, and exited 0")


def _switch_ok_wrong_account(cmd, *a, **kw):
    if cmd[:3] == ["gh", "auth", "switch"]:
        return _sp.CompletedProcess(cmd, 0, stdout="", stderr="")
    if cmd[:3] == ["gh", "api", "user"]:
        return _sp.CompletedProcess(cmd, 0, stdout="someone-else\n", stderr="")
    return _sp.CompletedProcess(cmd, 0, stdout="", stderr="")


sg.subprocess.run = _switch_ok_wrong_account
try:
    sg.ensure_account()
    wrong_account_fatal = False
except SystemExit:
    wrong_account_fatal = True
except Exception:                  # noqa: BLE001
    wrong_account_fatal = True
finally:
    sg.subprocess.run = _real_run

# The CONTROL. Both probes above accept "any exception" as evidence the run stopped, which would
# also pass if `ensure_account` were broken for an unrelated reason — a probe that fires on
# everything discriminates nothing. This asserts the happy path does NOT stop.
def _all_ok(cmd, *a, **kw):
    if cmd[:3] == ["gh", "api", "user"]:
        return _sp.CompletedProcess(cmd, 0, stdout=sg.ACCOUNT + "\n", stderr="")
    if cmd[:3] == ["gh", "repo", "view"]:
        return _sp.CompletedProcess(cmd, 0, stdout=sg.REPO + "\n", stderr="")
    return _sp.CompletedProcess(cmd, 0, stdout="", stderr="")


sg.subprocess.run = _all_ok
try:
    sg.ensure_account()
    happy_path_ok = True
except BaseException as _e:        # noqa: BLE001
    happy_path_ok, _why = False, repr(_e)[:120]
finally:
    sg.subprocess.run = _real_run

check("CONTROL: a correct switch onto the right account does NOT stop the run", happy_path_ok,
      "if this fails, the two probes above prove nothing — they would fire on any exception")

check("a switch that SUCCEEDS onto the wrong account still stops the run", wrong_account_fatal,
      "the old repo-resolution check could not catch this — another account with access to the "
      "same repo resolves it perfectly well")

# ── break 2: resolution is by number, with the title as a guard ─────────────────────────────
check("the board is resolved by NUMBER",
      "PROJECT_NUMBER" in sync_src and "by_number" in sync_src,
      "taking the first title match is what `gh project copy` defeats")
check("a title that disagrees with the declaration is fatal",
      "is titled" in sync_src,
      "a mismatch means declaration and board have diverged; a run must not pick which is right")

# ── break 3 (T650): a failed `gh project list` must NEVER fall through to `gh project create` ─
_project_create_called = False
_saved_sg_run = sg.RUN


def _project_list_fails(args: list[str]) -> tuple[int, str, str]:
    global _project_create_called
    if args[:3] == ["gh", "project", "list"]:
        return 1, "", "error: your authentication token is missing required scopes [read:project]"
    if args[:3] == ["gh", "project", "create"]:
        _project_create_called = True
        return 0, '{"number": 99, "url": "https://example/99"}', ""
    return 0, "", ""


sg.RUN = _project_list_fails
try:
    sg.get_or_create_project()
    _project_list_stopped = False
except SystemExit:
    _project_list_stopped = True
finally:
    sg.RUN = _saved_sg_run

check("a failed `gh project list` STOPS the run without calling `gh project create` (T650)",
      _project_list_stopped and not _project_create_called,
      "ignoring `gh project list` exit code mistook missing read:project scope for an absent board")

print()
if failures:
    print(f"{len(failures)} failure(s):")
    for f in failures:
        print(f"   - {f}")
    print("board identity: FAILED")
    sys.exit(1)
print("board identity: OK — one declaration, three readers, and both silent breaks guarded")
