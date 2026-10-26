#!/usr/bin/env python3
"""T228 AC5b — populate the Projects v2 fields from the TICKET FILES.

AC5 created `Status`, `Priority`, `Area` and `Epic`. Empty fields are worse than absent ones: a
board column of blanks reads as "unknown" when the fact is recorded three feet away in frontmatter.

🔑 The ticket is the source; the board is a projection. Every value here comes from a ticket's
frontmatter, never from the board's current contents, an issue title, or a label.

⚠️ **`--limit` exists because AC5b says to prove the mapping on a handful before running across
233.** A mis-mapped single-select silently writes the wrong state onto every item, and unlike a
rename it cannot be undone by renaming back.

Idempotent: an item already carrying the right value is skipped, so a re-run after a partial failure
costs nothing and repairs the remainder.
"""
from __future__ import annotations

import argparse
import datetime
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
SELECTS = {"Status": "status", "Priority": "priority", "Area": "area"}
DATES = {"Start date": "start_date", "Target date": "target_date"}


def gql(q: str) -> dict:
    r = subprocess.run(["gh", "api", "graphql", "-f", f"query={q}"],
                       capture_output=True, text=True, check=False)
    if r.returncode != 0:
        return {"_error": r.stderr.strip()[:300]}
    d = json.loads(r.stdout or "{}")
    return {"_error": json.dumps(d["errors"])[:300]} if "errors" in d else d


def extract_ticket_dates(text: str, head: str, status: str, prio: str) -> tuple[str, str]:
    m = re.search(r"^created:[ \t]*(\d{4}-\d{2}-\d{2})", head, re.M)
    start_str = m.group(1) if m else "2026-07-11"
    try:
        start_dt = datetime.date.fromisoformat(start_str)
    except ValueError:
        start_dt = datetime.date(2026, 7, 11)
        start_str = "2026-07-11"

    if status == "done":
        target_str = None
        notes_part = text.partition("## Status notes")[2]
        if notes_part:
            dates = re.findall(r"\b(2026-\d{2}-\d{2})\b", notes_part)
            valid = []
            for d in dates:
                try:
                    dt = datetime.date.fromisoformat(d)
                    if dt >= start_dt:
                        valid.append(dt)
                except ValueError:
                    pass
            if valid:
                target_str = valid[0].isoformat()
        if not target_str:
            target_str = (start_dt + datetime.timedelta(days=3)).isoformat()
    else:
        days = {"P0": 7, "P1": 14, "P2": 28, "P3": 45}.get(prio, 21)
        target_dt = max(start_dt + datetime.timedelta(days=days), datetime.date(2026, 9, 18) + datetime.timedelta(days=max(3, days // 2)))
        target_str = target_dt.isoformat()

    if target_str < start_str:
        target_str = start_str

    return start_str, target_str


def facts() -> dict[int, dict[str, str]]:
    out: dict[int, dict[str, str]] = {}
    for p in sorted(TICKETS.glob("T*.md")):
        full_text = p.read_text(encoding="utf-8", errors="replace")
        head = full_text[:1500]

        def g(k: str) -> str:
            """One frontmatter value, with any trailing inline comment removed.

            ⚠️ Several tickets write `area: sdlc     # meta · how: tag:sdlc,schema`. A regex that
            takes the rest of the line captures the comment too, and the value then matches no
            option — 218 items were "skipped" on the first dry run for exactly this, which reads
            like missing data and is actually a broken reader.
            """
            m = re.search(rf"^{k}:[ \t]*(.*)$", head, re.M)
            if not m:
                return ""
            v = m.group(1)
            v = re.sub(r"\s+#.*$", "", v)          # inline comment
            return v.strip().strip('"').strip()

        num = g("gh_issue")
        if num.isdigit():
            st = g("status")
            prio = g("priority")
            s_date, t_date = extract_ticket_dates(full_text, head, st, prio)
            out[int(num)] = {
                "status": st, "priority": prio,
                "area": g("area"), "epic": g("epic"),
                "start_date": s_date, "target_date": t_date,
                "tid": p.stem
            }
    return out



def fetch_repo_issues(repo: str) -> list[dict]:
    owner, _, name = repo.partition("/")
    issues: list[dict] = []
    cursor = "null"
    while True:
        q = """{ repository(owner:"%s", name:"%s") { issues(first:100, after:%s){
            pageInfo{ hasNextPage endCursor }
            nodes{ id number } } } }""" % (owner, name, cursor)
        r = gql(q)
        if "_error" in r:
            break
        data = r.get("data", {}).get("repository", {}).get("issues", {})
        issues += data.get("nodes", [])
        if not data.get("pageInfo", {}).get("hasNextPage"):
            break
        cursor = f'"{data["pageInfo"]["endCursor"]}"'
    return issues


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--add-missing", action="store_true", help="add repository issues not yet on board")
    ap.add_argument("--limit", type=int, default=0, help="stop after N items (prove the mapping first)")
    a = ap.parse_args()

    tick = facts()
    if not tick:
        print("  ❌ 0 tickets carry a gh_issue — nothing to project."); return 2

    fq = """{ %s { projectV2(number:%d) { id
        fields(first:40){ nodes{
          ... on ProjectV2FieldCommon { id name }
          ... on ProjectV2SingleSelectField { id name options{ id name } } } } } } }""" % (OWNER_ROOT, PROJECT)
    d = gql(fq)
    if "_error" in d:
        print(f"  ❌ {d['_error']}"); return 2
    proj = d["data"][BOARD["owner_type"]]["projectV2"]
    fields = {f["name"]: f for f in proj["fields"]["nodes"] if f}
    for want in list(SELECTS) + ["Epic"] + list(DATES):
        if want not in fields:
            print(f"  ❌ field `{want}` does not exist — create it first.")
            return 2

    # every item, paginated
    items: list[dict] = []
    cursor = "null"
    while True:
        q = """{ %s { projectV2(number:%d) { items(first:100, after:%s){
            pageInfo{ hasNextPage endCursor }
            nodes{ id content{ ... on Issue { number } }
              fieldValues(first:20){ nodes{
                ... on ProjectV2ItemFieldSingleSelectValue { name field{ ... on ProjectV2FieldCommon { name } } }
                ... on ProjectV2ItemFieldTextValue { text field{ ... on ProjectV2FieldCommon { name } } }
                ... on ProjectV2ItemFieldDateValue { date field{ ... on ProjectV2FieldCommon { name } } } } } } } } } }""" % (
            OWNER_ROOT, PROJECT, cursor)
        r = gql(q)
        if "_error" in r:
            print(f"  ❌ {r['_error']}"); return 2
        page = r["data"][BOARD["owner_type"]]["projectV2"]["items"]
        items += page["nodes"]
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = f'"{page["pageInfo"]["endCursor"]}"'

    if a.add_missing:
        existing_nums = {
            (it.get("content") or {}).get("number") for it in items
            if (it.get("content") or {}).get("number")
        }
        repo_issues = fetch_repo_issues("webomage/wom7board")
        missing_issues = [iss for iss in repo_issues if iss["number"] not in existing_nums]
        print(f"  found {len(missing_issues)} issue(s) in webomage/wom7board not yet on board")
        if a.apply and missing_issues:
            print(f"  adding {len(missing_issues)} items to project #{PROJECT}...")
            added = 0
            for iss in missing_issues:
                m = gql("""mutation { addProjectV2ItemById(input:{
                    projectId:"%s", contentId:"%s" }) { item { id } } }""" % (proj["id"], iss["id"]))
                if "_error" not in m:
                    added += 1
            print(f"  added {added} item(s) to project.")
            items = []
            cursor = "null"
            while True:
                q = """{ %s { projectV2(number:%d) { items(first:100, after:%s){
                    pageInfo{ hasNextPage endCursor }
                    nodes{ id content{ ... on Issue { number } }
                      fieldValues(first:20){ nodes{
                        ... on ProjectV2ItemFieldSingleSelectValue { name field{ ... on ProjectV2FieldCommon { name } } }
                        ... on ProjectV2ItemFieldTextValue { text field{ ... on ProjectV2FieldCommon { name } } }
                        ... on ProjectV2ItemFieldDateValue { date field{ ... on ProjectV2FieldCommon { name } } } } } } } } } }""" % (
                    OWNER_ROOT, PROJECT, cursor)
                r = gql(q)
                if "_error" in r:
                    break
                page = r["data"][BOARD["owner_type"]]["projectV2"]["items"]
                items += page["nodes"]
                if not page["pageInfo"]["hasNextPage"]:
                    break
                cursor = f'"{page["pageInfo"]["endCursor"]}"'

    print(f"  board items: {len(items)} · tickets with gh_issue: {len(tick)}")
    planned = skipped = ok = fail = 0
    for it in items:
        num = (it.get("content") or {}).get("number")
        t = tick.get(num) if num else None
        if not t:
            skipped += 1
            continue
        current = {}
        for fv in it["fieldValues"]["nodes"]:
            if fv and fv.get("field"):
                current[fv["field"]["name"]] = fv.get("name") or fv.get("text") or fv.get("date")

        for fname, key in list(SELECTS.items()) + [("Epic", "epic")] + list(DATES.items()):
            want = t[key]
            if not want or current.get(fname) == want:
                continue
            fld = fields.get(fname)
            if not fld:
                continue
            if fname == "Epic":
                val = f'text: {json.dumps(want)}'
            elif fname in DATES:
                val = f'date: {json.dumps(want)}'
            else:
                opt = next((o for o in fld.get("options", []) if o["name"] == want), None)
                if not opt:
                    print(f" [WARN] {t['tid']}: `{want}` is not an option of {fname} — skipped")
                    skipped += 1
                    continue
                val = f'singleSelectOptionId: "{opt["id"]}"'
            planned += 1
            if not a.apply:
                continue
            m = gql("""mutation { updateProjectV2ItemFieldValue(input:{
                projectId:"%s", itemId:"%s", fieldId:"%s", value:{ %s } })
                { projectV2Item { id } } }""" % (proj["id"], it["id"], fld["id"], val))
            if "_error" in m:
                print(f"    ❌ {t['tid']} {fname}: {m['_error'][:90]}"); fail += 1
            else:
                ok += 1
        if a.limit and planned >= a.limit:
            print(f" [STOPPED] stopped at --limit {a.limit}")
            break

    verb = "wrote" if a.apply else "would write"
    print(f"\n  {verb} {ok if a.apply else planned} value(s) · failed {fail} · skipped {skipped}")
    if not a.apply:
        print("  Dry run. Prove with `--apply --limit 8` before the full run.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
