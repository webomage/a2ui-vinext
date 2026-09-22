<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ## ⭐ PICK UP HERE — 2026-08-29 (LATER) — **TASKS.md was rotated for the first time: 95 done rows archived, and the bound -->

## ⭐ PICK UP HERE — 2026-08-29 (LATER) — **TASKS.md was rotated for the first time: 95 done rows archived, and the bound it was never tested against turned out to be 2,528 B away, not 37%.**

**[[T228]] ✅ DONE 15/15.** AC8b was a BUILD, not a run — `state-rotate` and
`deploy-logs-rotate` existed, `tasks-rotate` did not. `just tasks-rotate` (+ `tasks-rotate-test`,
17 red probes, **BLOCKING**) moved 95 done rows into `project/tickets/archive/` **verbatim**, with
an `INDEX.md` and `project/tasks-rotation.json`.

| | before | after |
|---|---|---|
| bytes | 663,866 (162%) | **412,128 (100%)** — 2,528 B over |
| lines | 440 (110%) | **345 (86%)** ✅ green |
| rows over 4,096 B | 32 | 19 |

Links preserved exactly — ticket 397 → 258 + 139 archived, issue 159 → 112 + 47 — verified after
the write, with a rollback that fires on any loss.

🔬 **AC8b's own arithmetic was wrong and is corrected in the ticket.** It recorded rotation as
recovering 100,647 B and leaving the file *"still 37% over"*. That counted only the done rows above
`max_row_bytes`; all 95 are **251,738 B**. The residual is **2,528 B**. The AC was right that this
is not a green `tasks-bounds` — wrong about the margin by two orders of magnitude. The DoD's own
line predicted this: *"a limit nobody has hit is a limit nobody has tested."*

🔑 **Clearance is EVIDENCE-based, and that was a deliberate reversal.** The first draft demanded a
written disposition for all 95 rows — in practice 95 auto-generated `sole_record_of: null` lines,
i.e. a gate that always says yes. A row clears when its **ticket file exists** ([[T228]] AC5b: the
ticket is the source, the board a projection) and rotation **moves** rather than deletes. What
fails closed is a done row with **no ticket file** — [[T174]]'s shape, where the row is the only
record. All 95 had ticket files, every one larger than its row.

**Three gates caught me on the way in, all correctly:** the red probes hit a real `KeyError` in the
index generator (it indexed `disp[i]` for rows the new rule clears without paperwork); **mypy**
rejected two missing annotations at commit; the **emoji ratchet** blocked the push over one
decorative warning sign on a print line, `script_output` being held at zero since T257.

**Next:** [[T117]] is stage-3's only remaining ticket and is **owner-gated, not
engineering-blocked** — its own notes say *"the taxonomy lock is a business decision"*. The concrete
call: the `user_roles` CHECK allows **12** values, **7** are held by anyone, and five —
`anon`, `gladiator`, `legioner`, `ai-admin`, `editor` — are allowed but held by nobody. T117 also
blocks [[T207]], and its Phase 1 (`role_capabilities` + `wom_can`, both measured ABSENT) is what
capability-aware CP nav waits on.
