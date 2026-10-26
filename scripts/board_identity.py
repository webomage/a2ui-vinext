#!/usr/bin/env python3
"""The Projects v2 board's identity, read from `.w0m/sdlc.json → board`. One fact, one reader.

🔴 Why this module exists (T242). One board had **three** resolution strategies and no declared
identity:

  * `sync_github.py` resolved it by *(owner, title)* — and took the FIRST title match.
  * `populate_project_fields.py` and `sync_project_fields.py` each hardcoded
    `OWNER, PROJECT = "casualuser", 2`, i.e. *(owner, number)*.
  * Both field scripts additionally hardcoded the owner TYPE into their GraphQL root as
    `user(login:…)`. An organization-owned project is not reachable through that root at all.

Every one of those failure modes **exits 0**. `gh project copy` leaves a second board with the same
title, so a stale owner finds a real, live-looking board: items land, the command succeeds, and
nothing arrives where it was meant to. A `projectV2(number:2)` under the wrong root returns `null`,
which reads as "no such board" rather than "you asked the wrong question".

⚠️ The board owner is NOT the acting principal. `vcs.gh_account` is the account `gh auth switch`
pins (isolated via `GH_CONFIG_DIR`); `board.owner` is who owns the board. `sync_github.py` used to
hold `OWNER = ACCOUNT`, and that single line is what makes the migration to an org unsafe: set it
to the org and the auth switch fails, leave it and the board half writes to the old board.
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "w0m-web" / "project" / "scripts"))
from authz_blanket_gate import strip_jsonc as _strip_jsonc  # noqa: E402  (one JSONC reader, not two)

CONFIG = pathlib.Path(__file__).resolve().parents[1] / ".w0m" / "sdlc.json"

_VALID_OWNER_TYPES = ("user", "organization")


class BoardIdentityError(RuntimeError):
    """The declaration is missing or malformed. Named, so a caller can exit 2 rather than crash."""


def load(config: pathlib.Path | None = None) -> dict:
    """Return the declared board identity, validated.

    Raises `BoardIdentityError` rather than returning a partial dict: a board identity that is
    half-declared is the state this module exists to make impossible, and defaulting the missing
    half is how it would come back.
    """
    path = config or CONFIG
    try:
        doc = json.loads(_strip_jsonc(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as exc:
        raise BoardIdentityError(f"cannot read {path}: {exc}") from exc

    board = doc.get("board")
    if not isinstance(board, dict):
        raise BoardIdentityError(
            f"{path} declares no `board` block — the three board scripts have nothing to agree on")

    missing = [k for k in ("owner", "owner_type", "number", "title") if k not in board]
    if missing:
        raise BoardIdentityError(f"`board` is missing {', '.join(missing)} in {path}")

    if board["owner_type"] not in _VALID_OWNER_TYPES:
        raise BoardIdentityError(
            f"board.owner_type is {board['owner_type']!r}; expected one of {_VALID_OWNER_TYPES}. "
            "This value picks the GraphQL root, and the wrong one resolves to null, not an error.")

    try:
        number = int(board["number"])
    except (TypeError, ValueError) as exc:
        raise BoardIdentityError(f"board.number is not an integer: {board['number']!r}") from exc

    return {
        "owner": str(board["owner"]),
        "owner_type": str(board["owner_type"]),
        "number": number,
        "title": str(board["title"]),
    }


def graphql_root(board: dict) -> str:
    """The GraphQL owner root for this board — `user(login:"x")` or `organization(login:"x")`.

    ⚠️ Built from the DECLARED type, never guessed from the login. There is no way to tell a user
    from an organization by name, and asking the wrong root returns `null` rather than an error.
    """
    return f'{board["owner_type"]}(login:"{board["owner"]}")'


def describe(board: dict) -> str:
    """One line naming which board a run is about to touch. Printed by every consumer, because
    'it succeeded' is not informative when the risk is succeeding against the wrong board."""
    return (f'board {board["owner"]}/#{board["number"]} "{board["title"]}" '
            f'({board["owner_type"]}-owned)')


def load_board_projection_config(config: pathlib.Path | None = None) -> dict:
    """T141 AC1, AC3, AC7 — Load the declared board field & status vocabulary mapping from
    `.w0m/sdlc.json → board` (or a client project's `sdlc.json`).

    Enforces:
      - `status_map` is a non-empty dict mapping ticket statuses to board `Status` options
      - `paused` and `done` map to DISTINCT board statuses (AC3)
      - `fields` declares the sortable/filterable board fields (`Status`, `Priority`, `Epic`, etc.)
    """
    path = config or CONFIG
    identity = load(path)
    doc = json.loads(_strip_jsonc(path.read_text(encoding="utf-8")))
    board = doc["board"]

    status_map = board.get("status_map")
    if not isinstance(status_map, dict) or not status_map:
        raise BoardIdentityError(
            f"`board.status_map` is missing or empty in {path} (T141 AC1: status vocabulary must be declared)"
        )

    paused_val = status_map.get("paused")
    done_val = status_map.get("done")
    if not paused_val or not done_val or paused_val == done_val:
        raise BoardIdentityError(
            f"`board.status_map` in {path} must map `paused` ({paused_val!r}) and `done` ({done_val!r}) "
            "to distinct board options (T141 AC3)"
        )

    lifecycle_map = board.get("lifecycle_map") or {}
    if not isinstance(lifecycle_map, dict):
        raise BoardIdentityError(f"`board.lifecycle_map` must be a dict in {path}")

    fields = board.get("fields")
    if not isinstance(fields, dict) or "Status" not in fields:
        raise BoardIdentityError(
            f"`board.fields` in {path} must declare at least `Status` (T141 AC4)"
        )

    return {
        **identity,
        "schema_version": int(board.get("schema_version", 1)),
        "status_map": {str(k): str(v) for k, v in status_map.items()},
        "lifecycle_map": {str(k): str(v) for k, v in lifecycle_map.items()},
        "fields": {str(k): str(v) for k, v in fields.items()},
    }

