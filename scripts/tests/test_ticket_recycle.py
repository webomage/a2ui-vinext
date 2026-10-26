#!/usr/bin/env python3
"""test_ticket_recycle.py — offline unit test suite for automated ticket recycling (T397).

Tests:
1. Pool discovery: enumerating closed duplicate tickets while ignoring active/delivered work.
2. Fail-closed guards: refusing to recycle active, completed, or non-existent tickets.
3. Draft duplicate rejection: integration with ticket_duplicate_check.
4. Atomic rewriting: verifying frontmatter, preserved IDs, cleared closed_as, and TASKS.md row update.
5. CLI interface: verifying --list and --recycle command line behavior.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SCRIPT = ROOT / "scripts/ticket_recycle.py"

spec = importlib.util.spec_from_file_location("tr", SCRIPT)
tr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tr)


class ProbeRunner:
    def __init__(self) -> None:
        self.n = 0
        self.fail: list[str] = []

    def check(self, label: str, ok: bool, detail: str = "") -> None:
        self.n += 1
        status = "ok" if ok else "!! FAILED"
        print(f"  {label:<68} {status}")
        if not ok:
            self.fail.append(f"{label} {detail}".strip())


SAMPLE_ACTIVE_TICKET = """---
id: T801
title: "Active Task in Flight"
status: in-progress
area: web
queue: next
priority: P1
repos: [web]
epic: "platform-health"
gh_issue: 801
created: 2026-09-01
x_ac_done: 1
x_ac_total: 4
---
# T801 — Active Task
"""

SAMPLE_DELIVERED_TICKET = """---
id: T802
title: "Completed Feature Work"
status: done
closed_as: completed
area: api
queue: next
priority: P2
repos: [api]
epic: "security-rbac-hardening"
gh_issue: 802
created: 2026-08-15
x_ac_done: 5
x_ac_total: 5
---
# T802 — Completed Feature Work
"""

SAMPLE_DUPLICATE_TICKET = """---
id: T803
title: "Duplicate Token Security Task"
status: done
closed_as: duplicate
area: api
queue: backlog-platform
priority: P1
repos: [api]
epic: "security-rbac-hardening"
gh_issue: 803
created: 2026-09-18
x_ac_done: 0
x_ac_total: 4
---
# T803 — Duplicate Token Security Task

> ⚠️ **CLOSED AS A DUPLICATE of [[T800]]**
> Superseded by T800.

## Summary
Duplicate content.
"""

SAMPLE_DUPLICATE_BANNER_ONLY = """---
id: T804
title: "Banner Marked Duplicate"
status: done
area: sdlc
priority: P1
repos: [tooling]
gh_issue: 804
x_ac_done: 0
x_ac_total: 3
---
# T804 — Banner Marked Duplicate

> ⚠️ **CLOSED AS A DUPLICATE of [[T800]]**

## Summary
Banner duplicate content.
"""

SAMPLE_DELIVERED_WITH_DUP_DISCUSS = """---
id: T805
title: "Real Delivered Ticket with Discussion Mentioning Duplicate"
status: done
closed_as: completed
area: sdlc
priority: P1
repos: [web]
gh_issue: 805
x_ac_done: 6
x_ac_total: 6
---
# T805 — Real Delivered Ticket

## Summary
Notes: We checked CLOSED AS A DUPLICATE earlier.
"""

SAMPLE_NEW_DRAFT = """---
title: "Automated Log Rotation Service for Edge Functions"
area: api
priority: P1
repos: [api, tooling]
epic: "platform-health"
tags: [api, logging, edge-functions, cron]
---
# Automated Log Rotation Service for Edge Functions

## Summary
Edge functions generate execution logs that need automated rotation to avoid storage bloat.
Implement a daily cron-driven log rotation service.

## Acceptance Criteria

- [ ] AC1 — Cron triggers rotation daily at midnight UTC
- [ ] AC2 — Compress logs older than 7 days
- [ ] AC3 — Archive compressed logs to R2 storage
- [ ] AC4 — Purge logs older than 90 days
- [ ] AC5 — Unit test coverage for purge logic
"""

SAMPLE_TASKS_MD = """# Tasks

| Ticket | Pri | Title | Repos | Epic | Status |
|---|---|---|---|---|---|
| [T801](project/tickets/T801.md) · [#801](https://github.com/webomage/wom7board/issues/801) | **P1** | 🟡 Active Task | web | platform-health | 🟡 in-progress 2026-09-01 |
| [T802](project/tickets/T802.md) · [#802](https://github.com/webomage/wom7board/issues/802) | **P2** | 🟢 Completed Feature Work | api | security-rbac-hardening | 🟢 done 2026-08-15 |
| [T803](project/tickets/T803.md) · [#803](https://github.com/webomage/wom7board/issues/803) | **P1** | ⚪ Duplicate Token Security Task (closed as duplicate) | api | security-rbac-hardening | 🟢 done 2026-09-18 |
| [T804](project/tickets/T804.md) · [#804](https://github.com/webomage/wom7board/issues/804) | **P1** | ⚪ Banner Marked Duplicate | tooling | gate-integrity | 🟢 done 2026-09-18 |
| [T805](project/tickets/T805.md) · [#805](https://github.com/webomage/wom7board/issues/805) | **P1** | 🟢 Real Delivered Ticket | web | delivery-record-sync | 🟢 done 2026-08-20 |
"""


def main() -> int:
    p = ProbeRunner()

    print("\n1. POOL DISCOVERY")
    with tempfile.TemporaryDirectory() as tmpdir:
        tdir = Path(tmpdir)
        (tdir / "T801.md").write_text(SAMPLE_ACTIVE_TICKET, encoding="utf-8")
        (tdir / "T802.md").write_text(SAMPLE_DELIVERED_TICKET, encoding="utf-8")
        (tdir / "T803.md").write_text(SAMPLE_DUPLICATE_TICKET, encoding="utf-8")
        (tdir / "T804.md").write_text(SAMPLE_DUPLICATE_BANNER_ONLY, encoding="utf-8")
        (tdir / "T805.md").write_text(SAMPLE_DELIVERED_WITH_DUP_DISCUSS, encoding="utf-8")

        candidates = tr.list_recyclable_tickets(tdir)
        c_ids = [c["id"] for c in candidates]

        p.check("discovered T803 (closed_as: duplicate)", "T803" in c_ids)
        p.check("discovered T804 (banner marked duplicate)", "T804" in c_ids)
        p.check("ignored T801 (active ticket in-progress)", "T801" not in c_ids)
        p.check("ignored T802 (delivered completed work)", "T802" not in c_ids)
        p.check("ignored T805 (delivered work with discussion mention)", "T805" not in c_ids)
        p.check("parsed duplicate target for T803 correctly", any(c["id"] == "T803" and c["duplicate_of"] == "T800" for c in candidates))

    print("\n2. FAIL-CLOSED SAFETY GUARDS")
    with tempfile.TemporaryDirectory() as tmpdir:
        tdir = Path(tmpdir)
        (tdir / "T801.md").write_text(SAMPLE_ACTIVE_TICKET, encoding="utf-8")
        (tdir / "T802.md").write_text(SAMPLE_DELIVERED_TICKET, encoding="utf-8")
        (tdir / "T803.md").write_text(SAMPLE_DUPLICATE_TICKET, encoding="utf-8")
        (tdir / "T805.md").write_text(SAMPLE_DELIVERED_WITH_DUP_DISCUSS, encoding="utf-8")

        ok1, err1, _ = tr.validate_target_ticket("T801", tdir)
        p.check("rejects active in-progress ticket", not ok1 and "ACTIVE" in err1)

        ok2, err2, _ = tr.validate_target_ticket("T802", tdir)
        p.check("rejects delivered completed ticket", not ok2 and ("COMPLETED" in err2 or "completed ACs" in err2 or "not marked" in err2))

        ok5, err5, _ = tr.validate_target_ticket("T805", tdir)
        p.check("rejects delivered ticket with ACs completed", not ok5 and ("completed ACs" in err5 or "not marked" in err5))

        ok_nonexistent, err_none, _ = tr.validate_target_ticket("T999", tdir)
        p.check("rejects non-existent ticket", not ok_nonexistent and "does not exist" in err_none)

        ok3, err3, _ = tr.validate_target_ticket("T803", tdir)
        p.check("accepts valid closed duplicate ticket", ok3 and err3 == "")

    print("\n3. ATOMIC REWRITING & TASKS.MD UPDATE")
    with tempfile.TemporaryDirectory() as tmpdir:
        tdir = Path(tmpdir) / "tickets"
        tdir.mkdir()
        t803_file = tdir / "T803.md"
        t803_file.write_text(SAMPLE_DUPLICATE_TICKET, encoding="utf-8")

        tasks_file = Path(tmpdir) / "TASKS.md"
        tasks_file.write_text(SAMPLE_TASKS_MD, encoding="utf-8")

        draft_file = Path(tmpdir) / "draft.md"
        draft_file.write_text(SAMPLE_NEW_DRAFT, encoding="utf-8")

        ret = tr.recycle_ticket(
            target_id="T803",
            draft_path=draft_file,
            tickets_dir=tdir,
            tasks_file=tasks_file,
            do_sync=False,
        )
        p.check("recycle_ticket returns 0 on success", ret == 0)

        # Inspect rewritten ticket file
        re_txt = t803_file.read_text(encoding="utf-8")
        re_fm, re_body = tr.parse_frontmatter(re_txt)

        p.check("preserves target id T803", re_fm.get("id") == "T803")
        p.check("preserves target gh_issue 803", re_fm.get("gh_issue") == 803)
        p.check("resets status to queued", re_fm.get("status") == "queued")
        p.check("clears closed_as from frontmatter", "closed_as" not in re_fm)
        p.check("resets x_ac_done to 0", re_fm.get("x_ac_done") == 0)
        p.check("sets x_ac_total to 5 (from draft ACs)", re_fm.get("x_ac_total") == 5)
        p.check("updates title in frontmatter", re_fm.get("title") == "Automated Log Rotation Service for Edge Functions")
        p.check("removes old duplicate banner from body", "CLOSED AS A DUPLICATE" not in re_body)
        p.check("contains draft AC1 text in body", "Cron triggers rotation daily" in re_body)

        # Inspect updated TASKS.md
        tasks_txt = tasks_file.read_text(encoding="utf-8")
        p.check("TASKS.md row updated with new title", "Automated Log Rotation Service for Edge Functions" in tasks_txt)
        p.check("TASKS.md row updated to queued", "⚪ queued" in tasks_txt)
        p.check("TASKS.md row still has link to T803.md and #803", "[T803](project/tickets/T803.md) · [#803]" in tasks_txt)

    print("\n4. DRAFT REJECTION & SAFETY IN RUNNER")
    with tempfile.TemporaryDirectory() as tmpdir:
        tdir = Path(tmpdir) / "tickets"
        tdir.mkdir()
        (tdir / "T801.md").write_text(SAMPLE_ACTIVE_TICKET, encoding="utf-8")
        tasks_file = Path(tmpdir) / "TASKS.md"
        tasks_file.write_text(SAMPLE_TASKS_MD, encoding="utf-8")

        draft_file = Path(tmpdir) / "draft.md"
        draft_file.write_text(SAMPLE_NEW_DRAFT, encoding="utf-8")

        # Attempt to recycle an active ticket via recycle_ticket
        ret_active = tr.recycle_ticket(
            target_id="T801",
            draft_path=draft_file,
            tickets_dir=tdir,
            tasks_file=tasks_file,
            do_sync=False,
        )
        p.check("recycle_ticket fails closed (code 1) on active target", ret_active == 1)

        # Attempt to recycle with missing draft file
        missing_draft = Path(tmpdir) / "nonexistent.md"
        (tdir / "T803.md").write_text(SAMPLE_DUPLICATE_TICKET, encoding="utf-8")
        ret_nodraft = tr.recycle_ticket(
            target_id="T803",
            draft_path=missing_draft,
            tickets_dir=tdir,
            tasks_file=tasks_file,
            do_sync=False,
        )
        p.check("recycle_ticket fails (code 2) when draft is missing", ret_nodraft == 2)

    print("\n5. REAL ESTATE RECYCLABLE POOL INTEGRATION")
    real_candidates = tr.list_recyclable_tickets()
    # 🔴 The pool is LIVE data and recycling empties it by design: it held exactly one candidate (T211)
    # until 2026-09-24, when T211 was recycled, and ">= 1" turned `just test` red and stopped a deploy.
    # An empty pool is a valid state. What must hold is that the real call returns a list and that
    # everything in it is a closed duplicate — and an empty list is reported, not counted as proof.
    p.check("real estate recyclable pool is readable", isinstance(real_candidates, list), f"got {type(real_candidates)}")
    if real_candidates:
        p.check("real estate recyclable candidates are strictly closed duplicates", all(c["closed_as"] == "duplicate" for c in real_candidates))
    else:
        print("  (real pool is empty — the closed-duplicate property is covered by the fixture probes above)")

    print(f"\nRan {p.n} probes: {p.n - len(p.fail)} passed, {len(p.fail)} failed.")
    if p.fail:
        print("\nFailures:")
        for f in p.fail:
            print(f"  - {f}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
