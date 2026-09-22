<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ## ⭐ PICK UP HERE — 2026-08-30 (LATEST) — **the rules agents actually READ: openspec 1.11.0, Antigravity consolidated on -->

## ⭐ PICK UP HERE — 2026-08-30 (LATEST) — **the rules agents actually READ: openspec 1.11.0, Antigravity consolidated onto `.agents/`, and a new gate for what a worktree loses.**

**The question that started it (owner):** we run Antigravity and Orca as well as Claude — *"make a
test measuring if other agents read all the same rules as Claude."*

🔑 **Orca is a RUNNER, not an ADE.** It provisions a git worktree and executes a CLI agent inside it,
unmodified. So the question is mechanically testable: **what survives into a worktree?**
**`just ade-rules-parity`** (+ `ade-rules-parity-test`, 12 probes, **BLOCKING**) answers it, and found
**10 surfaces Claude reads that a worktree-run agent does not** — dangling `../wom7web` symlinks in
wom7api, and five repos delegating to `../wom7web/CLAUDE.md`, a path absent from any worktree.
`ide-trace` counts that delegation as satisfied, and it IS — in the checkout only.
**THREE states, not two:** an escaping symlink is `fragile` (resolves only if the worktree lands
beside its target), never simply broken.

**openspec 1.6.0 → 1.11.0**, and it was UNGOVERNED (no `tools-policy.json` entry) for the one tool
that writes agent surfaces into every repo. Now floored at 1.11.0. On wom7web the upgrade was a
CONTENT refresh — 40 files, no new dirs, no duplication — and it declined to migrate Antigravity by
itself. ⚠️ On a scratch repo `update --force` DID copy to `.agents/` and leave `.agent/` behind, and
generated for an undeclared `codex`. Behaviour depends on what is already on disk; measure per repo.

**Rules moved `.agent/rules.md` → `.agents/rules/`** (Antigravity's documented default; `.agent/` is
now backward-compat only). wom7web antigravity went **partial → 6/6** non-negotiables. wom7api hit
**0/6** until it got a `.agents` symlink — exactly what its own rules file's *"ONE FILE, TWO REPOS"*
warning predicts.

**Gates caught every wrong step**, which is the story here: `ide-trace` refused to run three times
(exit 2, UNMEASURABLE — *"the registry moved; fix the policy rather than scan a path that no longer
exists"*), then rejected an out-of-schema key. One real gate defect fixed: a dropped openspec target
(`windsurf`, renamed `devin`) was fatal like a typo; it is now a NOTE.

**AGENTS.md — verified, not assumed.** LF/Agentic AI Foundation standard, nested files, nearest
wins. 🔴 **Claude Code reads CLAUDE.md, NOT AGENTS.md** (Anthropic's docs) — official bridge is
`@AGENTS.md` import or symlink, and the import is relative, so a per-repo bridge survives a worktree
where the cross-repo delegation does not. opencode reads it natively; Antigravity's support is
**unverified** (a blog claims 1.20.5; the vendor docs do not mention it). openspec never writes or
touches AGENTS.md or CLAUDE.md — measured on `init`, `update`, and `update --force`.

**Next:** (1) the AGENTS.md wrapper per repo — canonical rules + `@AGENTS.md` in CLAUDE.md, which
also closes the delegation half of the parity findings; (2) **wom7skills two modes** (owner) — w0m
itself vs managed projects; note `wom7skills/plugin.json` sits at the repo root, which is
**Antigravity's** manifest location, not Claude's `.claude-plugin/plugin.json`; (3) **personaje0**
still parked at 1 of 8 required client-profile keys.
