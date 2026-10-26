#!/usr/bin/env python3
"""T228 AC5 — carry ticket facts in Projects v2 FIELDS, from the declared vocabularies.

The board models the estate's facts badly today. `Status` is a single-select holding GitHub's
defaults — `Todo` / `In Progress` / `Done` — while the schema declares five: queued, in-progress,
blocked, done, paused. So "Todo" covers four distinct states, and `paused` and `blocked` are
invisible. `Priority`, `Area` and `Epic` have no field at all and live only as labels.

⚠️ AC5's warning is the point: **do not keep the label encoding for the same field.** `P1` as a
label and `Priority: P1` as a field are two encodings of one fact, and the `queue:p1` duplication
already showed where that ends.

🔑 Vocabularies come from `project/tickets-schema.jsonc`, never from what the board happens to
contain — the schema is the authority and the board is a projection of it.

Order matters and is deliberate:

  1. **RENAME** GitHub's three defaults onto the declared names — `Todo`→`queued`,
     `In Progress`→`in-progress`, `Done`→`done`. Renaming an option **preserves every item's
     value**, so 100 already-set items stay set and no near-identical pair (`Done` beside `done`)
     is ever created. Replacing the options wholesale would blank 234 items instead.
     ⚠️ `Todo` is broader than `queued` — it also covered `blocked` and `paused` — so the rename is
     an approximation that step 3 corrects from the tickets, not a claim that they were equivalent.
  2. **ADD** the two states GitHub never had: `blocked`, `paused`.
  3. **POPULATE** every item from its ticket's frontmatter, which is the authority.

Dry run unless `--apply`.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "w0m-web"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from tasks_query import resolve_tickets_dir  # noqa: E402 — canonical .tasks/ resolver (T411)
TICKETS = resolve_tickets_dir()
# 🔴 Read, never hardcoded (T242). This line used to be `OWNER, PROJECT = "casualuser", 2` — a
# THIRD encoding of one board, differing from `sync_github.py`'s (owner, title) lookup. The org
# copy gets a NEW number, so `projectV2(number:2)` under a different owner resolves to something
# else or to null. The GraphQL root below is built from the declared owner_type for the same
# reason: an organization-owned project is not reachable through `user(login:…)` at all.
from board_identity import BoardIdentityError, graphql_root, load as _load_board  # noqa: E402

try:
    BOARD = _load_board()
except BoardIdentityError as _exc:
    print(f"  [FAIL] {_exc}")
    raise SystemExit(2) from None
OWNER, PROJECT = BOARD["owner"], BOARD["number"]
OWNER_ROOT = graphql_root(BOARD)
FIELDS = {"Priority": "priority", "Area": "area"}   # single-selects sourced from the schema


def gql(query: str, **vars_: str) -> dict:
    args = ["gh", "api", "graphql", "-f", f"query={query}"]
    for k, v in vars_.items():
        args += ["-f", f"{k}={v}"]
    r = subprocess.run(args, capture_output=True, text=True, check=False)
    if r.returncode != 0:
        return {"_error": r.stderr.strip()[:300]}
    return json.loads(r.stdout or "{}")


def vocab() -> dict[str, list[str]]:
    s = re.sub(r"//[^\n]*", "", (WEB / "project" / "tickets-schema.jsonc").read_text(encoding="utf-8"))
    s = re.sub(r",(\s*[}\]])", r"\1", s)
    v = (json.loads(s).get("vocabularies") or {})
    return {k: v[k]["values"] for k in ("status", "priority", "area") if k in v}


def ticket_facts() -> dict[int, dict[str, str]]:
    """issue number → the facts its ticket declares. The ticket is the source; the board projects."""
    out: dict[int, dict[str, str]] = {}
    for p in sorted(TICKETS.glob("T*.md")):
        head = p.read_text(encoding="utf-8", errors="replace")[:1200]
        def g(k: str) -> str:
            # `[ \t]*` and NOT `\s*`: \s matches newlines, so an empty value walks into
            # the next line. Trailing inline comments (`area: sdlc  # meta · how: …`) are stripped.
            m = re.search(rf"^{k}:[ \t]*(.*)$", head, re.M)
            if not m:
                return ""
            return re.sub(r"\s+#.*$", "", m.group(1)).strip().strip('"').strip()
        num = g("gh_issue")
        if not num.isdigit():
            continue
        out[int(num)] = {"status": g("status"), "priority": g("priority"),
                         "area": g("area"), "epic": g("epic"), "id": p.stem}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    voc = vocab()
    if not voc.get("status"):
        print("  ❌ no vocabularies read from the schema — the reader is broken, not the schema empty.")
        return 2
    facts = ticket_facts()
    if not facts:
        print("  ❌ 0 tickets carry a gh_issue — cannot map anything.")
        return 2
    print(f"  schema vocabularies: status {len(voc['status'])} · priority {len(voc['priority'])} "
          f"· area {len(voc['area'])}")
    print(f"  tickets with a gh_issue: {len(facts)}")

    q = """{ %s { projectV2(number:%d) { id
        fields(first:40){ nodes{
          ... on ProjectV2FieldCommon { id name dataType }
          ... on ProjectV2SingleSelectField { id name options{ id name } } } } } } }""" % (OWNER_ROOT, PROJECT)
    d = gql(q)
    if "_error" in d:
        print(f"  ❌ {d['_error']}"); return 2
    proj = d["data"][BOARD["owner_type"]]["projectV2"]
    by_name = {f["name"]: f for f in proj["fields"]["nodes"] if f}

    # GitHub's defaults map onto declared names; renaming keeps the values already set.
    RENAME = {"Todo": "queued", "In Progress": "in-progress", "Done": "done"}

    # 1. Status — the declared values that the field does not yet offer
    st = by_name.get("Status", {})
    have = {o["name"] for o in st.get("options", [])}
    missing = [v for v in voc["status"] if v not in have]
    extra = [o for o in have if o not in voc["status"]]
    print(f"\n  Status: {len(have)} option(s) — {sorted(have)}")
    print(f"    + declared but absent: {missing or 'none'}")
    renamable = [o for o in extra if o in RENAME]
    print(f"    ↻ renamable onto declared names: {[(o, RENAME[o]) for o in renamable] or 'none'}")
    print(f" [WARN] present, undeclared, NOT renamable: {[o for o in extra if o not in RENAME] or 'none'}")

    # 2. fields that do not exist at all
    for fname, vkey in FIELDS.items():
        print(f"  {fname}: {'exists' if fname in by_name else f'MISSING — would create with {len(voc[vkey])} option(s)'}")
    print(f"  Epic: {'exists' if 'Epic' in by_name else 'MISSING — would create as TEXT'}")

    if not a.apply:
        print("\n  Dry run. --apply creates the fields and adds the declared options; populating\n"
              "  items and pruning the defaults are separate, deliberate steps.")
        return 0

    # 1+2. one updateProjectV2Field carries the whole option list: renamed defaults (by OPTION ID,
    # which is what preserves the item values) plus the states GitHub never had.
    if st.get("options") is not None:
        opts = []
        for o in st["options"]:
            opts.append({"id": o["id"], "name": RENAME.get(o["name"], o["name"]),
                         "color": "GRAY", "description": ""})
        for v in voc["status"]:
            if v not in {x["name"] for x in opts}:
                opts.append({"name": v, "color": "GRAY", "description": ""})
        body = ", ".join(
            "{" + (f'id:"{o["id"]}", ' if "id" in o else "") +
            f'name:"{o["name"]}", color:GRAY, description:""' + "}" for o in opts)
        r = subprocess.run(["gh","api","graphql","-f", f"""query=
            mutation {{ updateProjectV2Field(input:{{
              fieldId:"{st['id']}", singleSelectOptions:[{body}] }})
              {{ projectV2Field {{ ... on ProjectV2SingleSelectField {{ options{{ name }} }} }} }} }}"""],
            capture_output=True, text=True, check=False)
        ok = r.returncode == 0 and '"errors"' not in r.stdout
        print(f"    {'✅' if ok else '❌'} Status options → {[o['name'] for o in opts]}"
              + ("" if ok else f"\n        {(r.stderr or r.stdout)[:200]}"))

    created = 0
    for fname, vkey in FIELDS.items():
        if fname in by_name:
            continue
        # Built as a GraphQL literal, not json.dumps with the quotes patched out: `color` is an
        # ENUM (GRAY), so a quoted "GRAY" is rejected. The first version string-replaced its way
        # from JSON to GraphQL and produced exactly that.
        literal = ", ".join(f'{{name:"{v}", color:GRAY, description:""}}' for v in voc[vkey])
        r = subprocess.run(
            ["gh", "api", "graphql", "-f", f"""query=
              mutation {{ createProjectV2Field(input:{{
                projectId:"{proj['id']}", dataType:SINGLE_SELECT, name:"{fname}",
                singleSelectOptions:[{literal}]
              }}) {{ projectV2Field {{ ... on ProjectV2SingleSelectField {{ id name }} }} }} }}"""],
            capture_output=True, text=True, check=False)
        ok = r.returncode == 0 and "errors" not in r.stdout
        print(f"    {'✅' if ok else '❌'} create {fname}" + ("" if ok else f" — {(r.stderr or r.stdout)[:140]}"))
        created += ok
    if "Epic" not in by_name:
        r = subprocess.run(["gh","api","graphql","-f", f"""query=
            mutation {{ createProjectV2Field(input:{{
              projectId:"{proj['id']}", dataType:TEXT, name:"Epic" }})
              {{ projectV2Field {{ ... on ProjectV2FieldCommon {{ id name }} }} }} }}"""],
            capture_output=True, text=True, check=False)
        ok = r.returncode == 0 and '"errors"' not in r.stdout
        print(f"    {'✅' if ok else '❌'} create Epic (TEXT)" + ("" if ok else f" — {(r.stderr or r.stdout)[:140]}"))
        created += ok

    print(f"\n  created {created} field(s). Populating items is the next step, not this one.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
