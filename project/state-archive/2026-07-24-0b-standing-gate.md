<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ### 0b. ✅ DONE 2026-07-24 — T130 (per-stack registry + `just discovery`) — **STANDING GATE** -->

### 0b. ✅ DONE 2026-07-24 — T130 (per-stack registry + `just discovery`) — **STANDING GATE**

`project/tickets/T130.md` (GH **#90 CLOSED**). Full lifecycle spec→build→review→security→verify→
archive. Spec archived to `openspec/changes/archive/2026-07-25-2026-07-24-stack-registry-and-discovery`;
deltas synced into the **new main spec `openspec/specs/sdlc_toolchain/spec.md`** (5 requirements).

**What every future agent must know — this is now wired into the gates:**
```
just discovery            # per-stack drift report (advisory, exit 0)
just discovery --enforce  # gate: declared command with no recipe = HARD FAIL (any mode);
                          #       drift blocks; raw tool-invocations advisory (enforce_raw)
just discovery --json     # machine surface (also lists enabled MCP servers)
just discovery-test       # 16-assertion regression proof
```
- **`project/stacks-policy.json`** (+ `stacks-policy.schema.json`) declares **8 stacks** —
  `web`/`worker`/`edge`/`skills`/`cf`/`mlx`/`ext`/`sec` (`wom7md` exempt) — each with `runtime`,
  `justfile`, `techs` (`detect: dep:|config:|import:`) and a **`commands` contract** = SDLC canonical
  role → the `just` recipe that fulfils it. **Adding a stack tool = add the recipe AND the registry
  entry**; a raw `pnpm`/`npx`/`tsc`/`deno`/`wrangler` call in tracked automation is drift.
- **`.w0m/sdlc.json` gained two keys** (both owner-requested mid-build): `stacks` (points at the
  policy) and **`mcp`** — the project's enabled MCP servers (names + `purpose` + `scope` only,
  **never credentials**; a listed server is NOT proof it's connected).
- Runs inside **`just sdlc-doctor`**, as a **pre-push advisory**, and in `w0m-sdlc-research` grounding.
- **`enforce_raw: false`** for now — the one real raw call left is `.husky/pre-push:25`
  (`pnpm --filter … astro check`). Route it through `just` to flip the flag on.
- **mlx is modeled as the Rust port at `wom7mlx/wom7mlx`** (Cargo), not the outer dir.
- **Open (non-blocking):** owner-confirm whether `skills` leaves the *secrets* `exempt`; a `cf`
  `typecheck` role once wom7cfworkers gets a recipe. **[[T64]] is now UNBLOCKED** — this registry is
  its catalog data model.
Memory: `[[stack-registry-discovery]]`. Commits: wom7web `dc670e64`→`1cd96736`, wom7api
`733a47e`→`83449dc`, wom7skills `b4fbd9d`.
