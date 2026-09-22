<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ## ⭐ PICK UP HERE — 2026-08-29 (LATEST) — **the first authorization policy in the estate is off POSSESSION, and the hat  -->

## ⭐ PICK UP HERE — 2026-08-29 (LATEST) — **the first authorization policy in the estate is off POSSESSION, and the hat you wear now decides what you can do.**

**Shipped and live:** [[T102]] ✅ **DONE 8/8** — the office/capability axis is built *and exercised*.
`hats` (profile × unit × project), `worn_hats`, `resource_grants`, `is_capable()`,
`wom_effective_capabilities()`, `wom_my_hats/wear_hat/take_off_hat`. `office-axis-check` measures
**WIRED** — 1 subject table, 3 readers — and the declaration moved to match the measurement, which
is the one direction its DoD forbids doing backwards. [[T198]] ✅ **DONE 11/11** — `blueprints` moved
from possession (`EXISTS user_roles role='admin'`) to `is_capable('blueprint.publish') AND
wom_acting_is('admin')`. [[T94]] AC5 landed too: `connections` registry, **11/11**, a *blocking*
suite that had been sitting at exit 2 UNMEASURABLE.

**The model, as the owner stated it:** a person may hold PM *and* Developer on one engagement and
**wear one at a time**; switching must visibly change the CP. Held ≠ worn is the whole thing — if
rights were the union of every hat held, removing `deploy.approve` from the Developer hat would
still deploy through the PM hat and the switcher would be decoration. Enforced by a **composite FK**
to `hats(id, profile_id, project_id)`, not a trigger: you cannot wear a hat you do not hold.

🔴 **Two defects I introduced and caught, both the same shape — an arm that looks like enforcement:**
(1) `is_capable()` was worn-scoped while `wom_effective_capabilities()` still counted every held
hat; the CP renders menus from the second and is enforced by the first, so it would have offered
what the database refuses. (2) The first draft of the possession fix dropped possession but left the
hat arm beside a *new* capability arm — two permissive arms are OR'd, so the **capability** became
the decorative one. A mutation test caught it: grant deleted, admin still wrote. **Neither showed up
on a happy path.** Every authz assertion here now deletes the grant and re-asks.

**Also fixed, found by using them:** 12 undeclared SECURITY DEFINER functions (now 44/44 declared,
all pinning `search_path`); 5 declarations stale since T289's deliberate 08-26 revoke; anon revoked
on `profile_claim_conflicts` + `project_repos`; and `spec_drift_gate.tickets_by_spec` did
`split("openspec/changes/")[-1]`, so a ticket could own exactly **one** change — every earlier one
read as an orphan, and orphan is a WARN, so it never blocked. `2026-07-22-rbac-unified-axes` had
been invisible.

**Next, in order:**
1. **Phase 3 of T102 — the CP switcher.** RPCs are live, so it is now verifiable rather than merely
   writable. This is the half the owner actually asked for: *"not make a user guess what role/hat he
   has active right now."*
2. **The other 68 possession policies.** One table proves the pattern; the sweep is the work.
   `office-axis-policy.json` records `rls_policy_readers` — it is 1, and that number is the honest
   measure of how far this has actually got.
3. 🔑 **Owner call: `project/authz-grants.json` is baselined 2026-08-12** and prints 7 aged findings
   every run, so a *new* eighth would hide in them. Refreshing accepts T69's gamification posture
   (`authenticated` gained SELECT on 14 tables, 8 of them `USING true`) — a T69 decision. It also
   stores only a **count** per role, never the table list, which is why it could say "97 → 99" but
   never *which two*.
