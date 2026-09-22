<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ### 0i. 🔥 The ranked "hot 10" (owner asked 2026-07-25) — grounded against the live queue -->

### 0i. 🔥 The ranked "hot 10" (owner asked 2026-07-25) — grounded against the live queue

| # | Ticket | Prio | Why hot / next action | Blocked? |
|---|---|---|---|---|
| 1 | **T117** RBAC unified-axes | — | THE active thread; spec 53/0, owner additions folded → **build, schema first** (§1) | no |
| 2 | **T99(c)+(d)** connector creds | P0 🔒 | tokens plaintext at rest + dead 7-table identity subsystem holds a credential | (c) owner sign-off |
| 3 | **T100** Google auth + 2FA | P1 | owner ask; TOTP enabled project-wide, **no enrolment UI**; dormant providers | no |
| 4 | **T88** agent streaming+tools | P2 | spec written; closes the 🔴 streaming↔tools gap (`2026-07-19-agent-streaming-tool-loop`) | no |
| 5 | **T131** version-schema enforce | P2 | owner ask; audit done (§0e); 1 owner Q (package.json exempt?) | 1 owner Q |
| 6 | **T87** unified identity/agent surface | P2 | spec written, T86 task-0 shipped; pairs w/ T88+T92 | no |
| 7 | **T91→T92→T93** DS program | P1 | audit→unify→sync; CP ~85% off DS; T92 unblocks T87 → **spec T91 first** | needs spec |
| 8 | **T132** pixel-clone skill | P2 | owner ask; research in-ticket (§0g) → `w0m-sdlc-start T132`, 6 owner Qs | 6 owner Qs |
| 9 | **T133** recover DS proposals | P2 | owner ask; grounding done (§0h) → `w0m-sdlc-start T133` | no |
| 10 | **T21** WebMCP agent tools | P1 | spec written, awaiting approval; ties T88 | needs approval |

**Plus the status-truth cleanup** (see the ⭐ caveat): flip T121/T122/T123/T124/T126 → ✅ and archive
the T79 change — they're shipped+live per §1b but the rows still read red/queued.
