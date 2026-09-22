<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ### 0q. 🆕 OWNER ASK 2026-07-25 (late) — two new SDLC skills + a STATE.md schema + STATE settings in `sdlc.json`. GROUNDE -->

### 0q. 🆕 OWNER ASK 2026-07-25 (late) — two new SDLC skills + a STATE.md schema + STATE settings in `sdlc.json`. GROUNDED, unbuilt.

> *"let's add to w0m sdlc skills 2 more — save everything to STATE.md to let another local (by
> default) or remote agent to pickup and continue works … and second command is literally reading
> STATE.md and continue works"*
> *"add also STATE.md behaviour settings in sdlc settings and let's develop effective schema for
> STATE.md itself"*

**Not ticketed.** Four deliverables:
1. **A handoff skill** — writes everything a successor needs into STATE.md. Local pickup is the
   **default**, remote is the other option.
2. **A continue skill** — reads STATE.md and resumes the work. *(This session was that skill, executed
   by hand: read STATE.md → orient → verify claims → continue. Worth mining the transcript for the
   steps that mattered, chiefly **verify before trusting**.)*
3. **`state` behaviour settings in `.w0m/sdlc.json`** — path, who writes it, when a refresh is
   mandatory, retention/pruning of resolved sections, local-vs-remote pickup default.
4. **A schema for STATE.md itself.**

🔎 **Grounding for deliverable 4 — this file is the evidence.** STATE.md is **~1,250 lines** of
hand-maintained prose. Its section ids run **§0 · §0a · §0b … §0s** in **no stable order** (§0j and §0k
precede §0g/§0h/§0i; §0r sits between §0i and §0), because each session prepends. **Resolved records
are interleaved with live work** (§0r is explicitly *"a RESOLVED record, not a to-do"*, §0b/§0c are
history), so a reader cannot tell live from archive without reading every section. The one navigational
aid, the **⭐ PICK UP HERE** block, is found only by scrolling. There is **no validation** — nothing
checks that a handoff records the branch, unpushed state, blocked-on-owner items, or perishable data.
**That is what makes handoff quality depend on the writing agent**, which is the actual problem to
solve. Any schema should make at least these machine-checkable: live-vs-resolved status, an explicit
owner-action list, freshness, and "is the tree clean / what is unpushed".

Ties [[T127]] (skills are governed — canonical in `wom7skills/skills/`, declared in `.w0m/skills.json`
with fully-qualified provenance, hashed into `.w0m/skills.lock.json`, synced by `just skills-sync`) and
[[T131]] (**16 of 27 canonical skills carry no version at all** — do not add two more unversioned).
