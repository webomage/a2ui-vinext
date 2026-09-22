<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ### ⭐ (was) PICK UP HERE — 2026-08-08 — **[[T188]] 7/7 DONE and ARCHIVED — Python, the language that implements every ga -->

### ⭐ (was) PICK UP HERE — 2026-08-08 — **[[T188]] 7/7 DONE and ARCHIVED — Python, the language that implements every gate, is now type-checked and gated at ZERO. 🔴 The review gate caught T188's OWN build shipping a non-bug: a "fix" for a failure that cannot happen. Read that story before you fix anything a type checker flags.**

> **Written for an agent with none of my context. Everything below is measured, 2026-08-08.**
>
> ### ✅ What shipped
> - **[[T188]] — `just py-typecheck`, gated at ZERO over 44 files**, wired into pre-commit and
>   `just test` (now **25 suites / 238 checks**). All 27 findings **fixed** — not ratcheted, not
>   suppressed, no category disabled; exactly **one** narrow `# type: ignore`, with
>   `warn_unused_ignores` set to flag it when it stops being needed.
> - **A new `tooling` stack in `project/stacks-policy.json`** — the estate's own gate language finally
>   has a home in the registry. This is the durable half: **132 of 145 tracked `.py` files sat inside
>   stacks declared `runtime: node`**, so [[T135]] AC2's *checks must match the stack* rule could never
>   fire on the language implementing every check. Not overlooked — structurally invisible (D37's shape).
> - **Proven to BLOCK, not merely to run.** An injected `-> str` returning `int` failed
>   `just py-typecheck` **and** was refused by the pre-commit hook (HEAD did not move). Re-proven at the
>   verify gate rather than trusted from the build note.
>
> ### 🔴 The thing worth your attention — I "fixed" a bug that does not exist
> The build claimed **three real defects** behind the mypy findings. Two were real (a function falling
> off the end while declared `-> int`; a duplicated `return 0`). **The third was invented.** mypy
> flagged a possibly-`None` value passed where a `dict` was required, and the fix wrote the runtime
> story to match: an error branch raising a diagnosis for *"the GitHub issue was deleted upstream"*.
> **A test written to exercise that branch proved it can never run** — an earlier phase already drops a
> dead issue number and re-resolves by title, so the state the branch described is unreachable.
> - ⇒ A **non-bug shipped as a bugfix**, wrapped in **untestable code**, and the false story then
>   propagated into the commit message, the ticket AC **and** `stacks-policy.json`. All three corrected;
>   the registry correction was found by the *verify* gate, not the review one.
> - ⇒ **The rule: a type error tells you an annotation is UNPROVABLE. It does not tell you the failure
>   it implies is REACHABLE.** Before writing the failure story a type error suggests, write the test
>   that reaches it. If the test cannot reach it, the fix belongs in the **type** — make the bad state
>   unrepresentable — not in a guard. **An error path with no test is not defensive; it is unfalsifiable.**
>
> ### ⚠️ Two traps I hit that will catch you too
> - **`pre-commit run --all-files` MUTATES the working tree** — the hook set includes auto-formatters.
>   It rewrote **412 files**, a reflexive `git add -A` staged all of them, and gitleaks/semgrep then
>   blocked the commit on *those* files rather than the real change. All discarded; nothing churned was
>   committed. **Scope gate runs to the change, and never `git add -A` after a full-repo hook run.**
>   A big-bang reformat is also what [[D12]]/[[D20]] decided against.
> - **A probe value the fixture can also produce proves nothing.** A test used issue `999` as the "dead"
>   number — and the `gh` test double returns `999` from `issue create`, so the assertion could not tell
>   *touched the dead issue* from *created the new one*.
>
> ### 🔴 Filed, not fixed: [[D42]] — the security gate's own review skill is missing
> `.w0m/sdlc.json` names `security_review_skill: security-guardrails`. It is canonical in `wom7skills`
> but is **not installed** in `wom7web/.agents/skills/` and **undeclared** in `.w0m/skills.json`. So the
> gate step that says *invoke security-guardrails* has had nothing to invoke — and a gate step naming a
> missing tool does not fail, it gets improvised or skipped while the run reports green. Closing it is
> **governed** (declare with provenance → `just skills-sync` → `just skill relock`), never a file copy.
> 🔎 Related: `just skill check` now reports several **installed-but-unmanaged** skills, so the
> 2026-07-25 "0 unmanaged" state has drifted — re-measure rather than assume.
>
> ### ▶ Next
> ⚠️ **This block was written when T188 archived; the three items below it were SUPERSEDED later the
> same day. Corrected in place rather than left to mislead.**
> - ~~Next Python increment: `wom7api/scripts` (48 files)~~ → **DONE: [[T189]] shipped and archived
>   2026-08-08**, 7/7, 36/36 files gated at zero. ⚠️ The "48 files" figure was wrong (it counted
>   `archive/` + `tests/`); the real scope was **36**.
> - ~~T135 is blocked on the owner (tinybird licence)~~ → **RESOLVED 2026-08-08 by owner decision:
>   accept the risk, record it, ask upstream.** `just license-check` **PASSES**; `just test` has **no
>   advisory-red suite left**. The four skills are exempted in `hygiene-policy.json` with the full
>   reasoning, and an upstream issue is **drafted, unsent**, at
>   `project/drafts/tinybird-licence-request.md` — sending it is the owner's, and a reply should
>   DELETE the exemption rather than amend it. 🔴 **AC6 is still `[~]`, not done:** `fact-checker`'s
>   provenance and the copyleft/transitive half were never built, and a green gate is not a finished AC.
> - **Still blocked on the OWNER:** **[[T110]]** (4/5) AC5 needs the generic SDLC set installed
>   *against a real client repo* (**1945** or **Artemio**, owner-write-only) — permission, not effort.
>   Also **[[T8]] and [[T20]] have no `priority:`**, and T8's absence is what blocks **[[T22]]** (P1).
> - **Filed 2026-08-08, both queued:** **[[T190]]** (skills governance blind in two directions —
>   `relock` invents manifests; `check` never looks at canonical, 12 of 33 installed nowhere) and
>   **[[T191]]** (local LLM runtime evaluation — and the prerequisite finding that **no local serve
>   path works**: `just model-serve` points at a script that exists nowhere). **[[D42]] RESOLVED** —
>   `security-guardrails` is installed and governed.
> - ⚠️ **`mypy` resolves through a pyenv shim**, so it vanishes on an interpreter switch — the exact
>   failure that forced `ast-grep` off pip-inside-pyenv onto brew. Recorded in `tools-policy.json`; move
>   to brew if it bites.
