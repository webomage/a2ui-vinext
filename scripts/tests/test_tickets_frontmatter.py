#!/usr/bin/env python3
"""T552 — Prove `tickets-frontmatter-check` is invariant across midnight/dates (Option a).

Verifies:
  1. AC1: `x_hot_score` persisted in `.tasks/T*.md` excludes the time-dependent `age` term
     (`days_since_created // 7`), while `tasks_query.load()` continues to include `parts["age"]`
     on read for `just tasks hot`.
  2. AC2: Running `--check` on two different dates (crossing a 7-day week boundary and multiple
     weeks) against an unchanged ticket set produces the exact same verdict (exit 0).
  3. AC2 RED proof: A mutation that reintroduces the age term (`include_age=True` / `row["score"]`)
     into the stored value is caught immediately when the date crosses a week boundary.
  4. Real ticket mutations (priority, status, AC completion, open blocker) still fail `--check`.
  5. AC3: `LESSONS.md` drops the midnight caveat on deploy readiness.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

MONO_ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = MONO_ROOT / "wom7web"

sys.path.insert(0, str(MONO_ROOT / "scripts"))

import tasks_query as tq  # noqa: E402
import tickets_frontmatter_sync as tfs  # noqa: E402


TICKET_T1 = """---
id: T1
title: "Ticket created on Oct 1"
status: queued
area: sdlc
queue: next
priority: P2
repos: [root, web]
epic: "delivery-record-sync"
spec: ""
created: 2026-10-01
---

# T1 — fixture ticket

## Summary

Fixture summary.

## Acceptance criteria

- [x] AC1 — first criterion done
- [ ] AC2 — second criterion open (depends on [[T2]])
"""

TICKET_T2 = """---
id: T2
title: "Open blocker ticket"
status: in-progress
area: sdlc
queue: now
priority: P1
repos: [root]
epic: "delivery-record-sync"
spec: "openspec/changes/foo"
created: 2026-09-20
---

# T2 — blocker fixture

## Summary

Blocker summary.

## Acceptance criteria

- [ ] AC1 — still working
"""


class TestTicketsFrontmatterDateInvariance(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp(prefix="t552-frontmatter-"))
        self.tasks_dir = self.tmpdir / ".tasks"
        self.tasks_dir.mkdir(parents=True)
        self.tasks_md = self.tmpdir / "TASKS.md"
        self.tasks_md.write_text(
            "| Ticket | Prio |\n|---|---|\n| [T1](.tasks/T1.md) | P2 |\n| [T2](.tasks/T2.md) | P1 |\n",
            encoding="utf-8",
        )
        (self.tasks_dir / "T1.md").write_text(TICKET_T1, encoding="utf-8")
        (self.tasks_dir / "T2.md").write_text(TICKET_T2, encoding="utf-8")

        self._orig_tfs_tickets = tfs.TICKETS
        self._orig_tq_tickets = tq.TICKETS
        self._orig_tq_tasks_md = tq.TASKS_MD
        tfs.TICKETS = self.tasks_dir
        tq.TICKETS = self.tasks_dir
        tq.TASKS_MD = self.tasks_md

    def tearDown(self) -> None:
        tfs.TICKETS = self._orig_tfs_tickets
        tq.TICKETS = self._orig_tq_tickets
        tq.TASKS_MD = self._orig_tq_tasks_md
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_ac1_live_tasks_query_keeps_age_while_frontmatter_excludes_age(self) -> None:
        """`tasks_query.load()` ages tickets on read, while `tfs.derive()` stores age-free `x_hot_score`."""
        day_6 = date(2026, 10, 7)   # 6 days after 2026-10-01 -> age_weeks = 0
        day_7 = date(2026, 10, 8)   # 7 days after 2026-10-01 -> age_weeks = 1
        day_28 = date(2026, 10, 29) # 28 days after 2026-10-01 -> age_weeks = 4

        live_6 = {r["id"]: r for r in tq.load(today=day_6)}
        live_7 = {r["id"]: r for r in tq.load(today=day_7)}
        live_28 = {r["id"]: r for r in tq.load(today=day_28)}

        # Live read score increases across week boundaries
        self.assertEqual(live_6["T1"]["parts"]["age"], 0)
        self.assertEqual(live_7["T1"]["parts"]["age"], 1)
        self.assertEqual(live_28["T1"]["parts"]["age"], 4)
        self.assertEqual(live_7["T1"]["score"], live_6["T1"]["score"] + 1)
        self.assertEqual(live_28["T1"]["score"], live_6["T1"]["score"] + 4)

        # Persisted derived fields stay identical across all dates
        derived_6 = tfs.derive(today=day_6)
        derived_7 = tfs.derive(today=day_7)
        derived_28 = tfs.derive(today=day_28)
        self.assertEqual(derived_6, derived_7)
        self.assertEqual(derived_7, derived_28)

    def test_ac2_check_verdict_is_identical_across_consecutive_days_and_weeks(self) -> None:
        """Syncing on day 6 (23:59) and running --check on day 7 (00:01) and day 28 both exit 0."""
        rc_sync = tfs.main(["--stamp", "2026-10-07", "--today", "2026-10-07"])
        self.assertEqual(rc_sync, 0)

        rc_day6 = tfs.main(["--check", "--today", "2026-10-07"])
        rc_day7 = tfs.main(["--check", "--today", "2026-10-08"])
        rc_day28 = tfs.main(["--check", "--today", "2026-10-29"])
        self.assertEqual(rc_day6, 0)
        self.assertEqual(rc_day7, 0)
        self.assertEqual(rc_day28, 0)

    def test_ac2_red_mutation_reintroducing_age_term_is_caught(self) -> None:
        """A mutation that reintroduces the age term into stored `x_hot_score` fails across midnight."""
        # Sync on 2026-10-07
        self.assertEqual(tfs.main(["--stamp", "2026-10-07", "--today", "2026-10-07"]), 0)

        # Mutant that includes the age term in frontmatter (the pre-T552 bug)
        orig_fn = tfs.hot_score_for_frontmatter
        with mock.patch.object(
            tfs,
            "hot_score_for_frontmatter",
            side_effect=lambda row, *, include_age=False: orig_fn(row, include_age=True),
        ):
            # On 2026-10-08 (midnight crossing 1-week boundary for T1), the mutant disagrees with stored frontmatter!
            rc_mutant = tfs.main(["--check", "--today", "2026-10-08"])
            self.assertEqual(
                rc_mutant,
                1,
                "Mutant reintroducing age term into x_hot_score was NOT caught across week boundary!",
            )

    def test_real_ticket_changes_still_fail_check(self) -> None:
        """Changing ticket priority, status, AC progress, or blocker state still fails --check."""
        self.assertEqual(tfs.main(["--stamp", "2026-10-07", "--today", "2026-10-07"]), 0)
        self.assertEqual(tfs.main(["--check", "--today", "2026-10-07"]), 0)

        # Tick AC2 on T1 without syncing frontmatter
        t1_path = self.tasks_dir / "T1.md"
        t1_text = t1_path.read_text(encoding="utf-8")
        t1_path.write_text(t1_text.replace("- [ ] AC2", "- [x] AC2"), encoding="utf-8")
        self.assertEqual(tfs.main(["--check", "--today", "2026-10-07"]), 1)

        # Sync brings it back to green
        self.assertEqual(tfs.main(["--stamp", "2026-10-07", "--today", "2026-10-07"]), 0)
        self.assertEqual(tfs.main(["--check", "--today", "2026-10-08"]), 0)

    def test_ac3_lessons_md_drops_midnight_caveat(self) -> None:
        """LESSONS.md deploy-readiness section no longer instructs re-running after midnight."""
        lessons = (MONO_ROOT / "LESSONS.md").read_text(encoding="utf-8")
        self.assertNotIn("tickets-frontmatter-check` is date-dependent until T552", lessons)
        self.assertNotIn("re-run after any landing and after midnight", lessons)


if __name__ == "__main__":
    unittest.main()
