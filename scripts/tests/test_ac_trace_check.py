#!/usr/bin/env python3
"""T245 — Unit tests and red probes for `scripts/ac_trace_check.py`."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "w0m-web"
sys.path.insert(0, str(ROOT / "scripts"))

import ac_trace_check as atc  # noqa: E402


def _make_ticket(
    tid: str,
    status: str,
    acs: list[str],
    *,
    priority: str = "P2",
    closed_as: str = "",
    pending_closure: str = "",
    blocked_by: str = "[]",
    extra_body: str = "",
) -> str:
    fm_lines = [
        "---",
        f"id: {tid}",
        f'title: "Fixture {tid}"',
        f"status: {status}",
        f"priority: {priority}",
        f"blocked_by: {blocked_by}",
    ]
    if closed_as:
        fm_lines.append(f"closed_as: {closed_as}")
    if pending_closure:
        fm_lines.append(f'pending_closure: "{pending_closure}"')
    fm_lines.append("---")
    ac_block = "\n".join(acs) if acs else "Not yet written."
    return (
        "\n".join(fm_lines)
        + f"\n\n# {tid} — Fixture\n\n## Acceptance criteria\n\n{ac_block}\n\n{extra_body}\n"
    )


class TestAcTraceCheck(unittest.TestCase):
    def test_ac1_red_complete_not_done_fails(self) -> None:
        """AC1 + AC2: 100% ticked ACs with status not in {done, archived} and no escape fails (RED)."""
        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td)
            (tdir / "T901.md").write_text(
                _make_ticket(
                    "T901",
                    "queued",
                    ["- [x] **AC1** — first done", "- [x] **AC2** — second done"],
                ),
                encoding="utf-8",
            )
            res = atc.audit_tickets(tdir)
            self.assertEqual(res["exit_code"], 1)
            self.assertEqual(len(res["complete_not_done"]), 1)
            self.assertEqual(res["complete_not_done"][0][0], "T901")
            report = atc.format_report(res)
            self.assertIn("[COMPLETE-NOT-DONE]", report)
            self.assertIn("[FAIL] ac-trace-check FAILED", report)

    def test_ac1b_pending_closure_escape_does_not_fail(self) -> None:
        """AC1b: 100% ticked ACs with declared pending_closure / blocked_by / paused reports [PENDING-CLOSURE] and exits 0."""
        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td)
            (tdir / "T902.md").write_text(
                _make_ticket(
                    "T902",
                    "in-progress",
                    ["- [x] **AC1** — code landed", "- [x] **AC2** — tests green"],
                    pending_closure="awaiting production deploy",
                ),
                encoding="utf-8",
            )
            (tdir / "T903.md").write_text(
                _make_ticket(
                    "T903",
                    "in-progress",
                    ["- [x] **AC1** — ready"],
                    blocked_by="[T999]",
                ),
                encoding="utf-8",
            )
            (tdir / "T904.md").write_text(
                _make_ticket(
                    "T904",
                    "paused",
                    ["- [x] **AC1** — parked for owner sign-off"],
                ),
                encoding="utf-8",
            )
            res = atc.audit_tickets(tdir)
            self.assertEqual(res["exit_code"], 0)
            self.assertEqual(len(res["complete_not_done"]), 0)
            self.assertEqual(len(res["pending_closure"]), 3)
            report = atc.format_report(res)
            self.assertIn("[PENDING-CLOSURE]", report)
            self.assertIn("awaiting production deploy", report)
            self.assertIn("[OK] ac-trace-check", report)

    def test_ac3_queued_with_progress_detected(self) -> None:
        """AC3: status: queued with 0 < done < total is flagged as [QUEUED-WITH-PROGRESS] and fails."""
        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td)
            (tdir / "T905.md").write_text(
                _make_ticket(
                    "T905",
                    "queued",
                    ["- [x] **AC1** — started", "- [ ] **AC2** — remaining"],
                ),
                encoding="utf-8",
            )
            res = atc.audit_tickets(tdir)
            self.assertEqual(res["exit_code"], 1)
            self.assertEqual(len(res["queued_with_progress"]), 1)
            self.assertEqual(res["queued_with_progress"][0][0], "T905")
            report = atc.format_report(res)
            self.assertIn("[QUEUED-WITH-PROGRESS]", report)
            self.assertNotIn("T905   P2  queued       1/2 ?", report)

    def test_ac4_in_progress_zero_ac_reported_as_question(self) -> None:
        """AC4: status: in-progress with 0 ticked ACs is reported distinctly as [IN-PROGRESS-ZERO-AC] question."""
        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td)
            (tdir / "T906.md").write_text(
                _make_ticket(
                    "T906",
                    "in-progress",
                    ["- [ ] **AC1** — not ticked yet", "- [ ] **AC2** — second"],
                ),
                encoding="utf-8",
            )
            res = atc.audit_tickets(tdir)
            self.assertEqual(res["exit_code"], 0)
            self.assertEqual(len(res["in_progress_zero_ac"]), 1)
            self.assertEqual(len(res["queued_with_progress"]), 0)
            report = atc.format_report(res)
            self.assertIn("[IN-PROGRESS-ZERO-AC]", report)
            self.assertIn("question: optimistic status or unticked progress?", report)
            self.assertIn("T906", report)

    def test_ac5_closed_as_duplicate_exemption_preserved(self) -> None:
        """AC5: status: done with unticked ACs is exempt when superseded/closed_as duplicate, and fails otherwise."""
        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td)
            (tdir / "T209.md").write_text(
                _make_ticket("T209", "done", ["- [x] **AC1** — canonical ticket"]),
                encoding="utf-8",
            )
            (tdir / "T211.md").write_text(
                _make_ticket(
                    "T211",
                    "done",
                    ["- [ ] **AC1** — unticked on duplicate"],
                    closed_as="duplicate",
                    extra_body="CLOSED AS A DUPLICATE of [[T209]]",
                ),
                encoding="utf-8",
            )
            res = atc.audit_tickets(tdir)
            self.assertEqual(res["exit_code"], 0)
            self.assertEqual(len(res["stale"]), 0)
            self.assertEqual(len(res["exempt"]), 1)
            self.assertEqual(res["exempt"][0][0], "T211")
            self.assertEqual(res["exempt"][0][4], "T209")

            # Without exemption, done + unticked AC must fail as stale-done
            (tdir / "T907.md").write_text(
                _make_ticket("T907", "done", ["- [ ] **AC1** — forgotten box"]),
                encoding="utf-8",
            )
            res_stale = atc.audit_tickets(tdir)
            self.assertEqual(res_stale["exit_code"], 1)
            self.assertEqual(len(res_stale["stale"]), 1)
            self.assertEqual(res_stale["stale"][0][0], "T907")

    def test_ac2_empty_corpus_vacuity_guard_fails_closed(self) -> None:
        """AC2: An empty directory or a corpus with 0 measurable tickets must exit 2, never pass."""
        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td)
            res_empty = atc.audit_tickets(tdir)
            self.assertEqual(res_empty["exit_code"], 2)
            self.assertIn("refusing to certify tracing over an empty set", atc.format_report(res_empty))

            # Corpus with a ticket that has 0 ACs (0 measurable tickets) must also exit 2
            (tdir / "T908.md").write_text(
                _make_ticket("T908", "queued", []),
                encoding="utf-8",
            )
            res_no_counted = atc.audit_tickets(tdir)
            self.assertEqual(res_no_counted["exit_code"], 2)

    def test_live_corpus_passes_with_denominator(self) -> None:
        """Live .tasks/ corpus passes with 0 blocking disagreements and prints denominator."""
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "ac_trace_check.py")],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + "\n" + proc.stderr)
        self.assertRegex(proc.stdout, r"searched \d+ measurable ticket\(s\) across \d+ total")
        self.assertIn("[OK] ac-trace-check:", proc.stdout)


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestAcTraceCheck)
    failures = 0
    for test in suite:
        result = unittest.TestResult()
        test.run(result)
        name = test.id().split(".")[-1]
        if result.wasSuccessful():
            print(f"  [OK] {name}")
        else:
            failures += 1
            details = (result.failures + result.errors)[0][1]
            print(f"  [FAIL] {name}\n{details}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
