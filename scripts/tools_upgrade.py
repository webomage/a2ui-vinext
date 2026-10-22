#!/usr/bin/env python3
"""Promote host CLI tool updates — but ONLY the safe, gated subset, with a compatibility check.

For each policy tool whose bump level is within its `auto` allowance, using the right upgrade
mechanism for its `source`:

🔻 **Corrected 2026-08-14.** This line read *"patch/minor, never major, never `auto:none`"*, and
the "never major" half was **false**: `ALLOW_RANK` admits `major: 2`, so a tool configured
`auto: "major"` IS auto-upgraded. **`gcloud` is configured exactly that way**, and
`just tools-outdated` duly offers `577.0.0 → 580.0.0 [major] AUTO` — a three-major-version jump
this docstring claimed could not happen. `auto` is a CEILING per tool, not a global cap:
  patch → patch only · minor → patch+minor · major → anything · none → never
⚠️ Whether `gcloud` SHOULD sit at `major` is an owner decision and is left alone here; this comment
only stops the code from being read as stricter than it is.

    brew upgrade <formula>   (source: brew)
    gcloud components update  (source: gcloud — self-updater, not brew)
        ->  run its `smoke` command  ->  on PASS: PROPOSE the bump (T546)
                                     ->  on FAIL: report loudly, stop, do NOT propose

🔴 T546 (owner decision 2026-10-06): the scheduled run no longer writes `tools-policy.json`. It ran in the live checkout and never committed, so that
checkout sat dirty and `git merge --ff-only` aborted. It records what it verified in a machine-level state file (`tools_check.PROPOSED`); `--promote`
lists it and `--promote --apply` re-verifies each proposal now (installed == proposed, at least `min`, smoke passes) and writes `known_good` into THIS
tree, only inside an agent tree (`just agent-tree <name>`), ready to commit and land. This file has exactly one policy write, inside `promote()`.

`auto:none` tools (supabase/deno/aws/az/…) are NEVER touched in normal runs — a bump to a
prod-gating or system CLI needs a human + a real deploy/hook smoke. Dry-run by default; `--apply`
performs the upgrades.

`--force` is the deliberate escape hatch: it also considers `auto:none` upgradable tools (and
lifts the per-tool level cap), still smoke-gated — a tool with a `smoke` must pass it to be
promoted, and one WITHOUT a smoke is upgraded but flagged UNVERIFIED (verify it by hand). Tools
whose `source` has no upgrade path here (node/python via nvs/pyenv, terraform via tfenv, graphify
via uv, codegraph via npm) are listed with their real update command instead.

Usage (from wom7web/):
    python3 project/scripts/tools_upgrade.py                   # plan only (auto subset)
    python3 project/scripts/tools_upgrade.py --apply           # upgrade the auto subset, verify, PROPOSE (no policy write)
    python3 project/scripts/tools_upgrade.py --promote         # list the proposals (dry run)
    python3 project/scripts/tools_upgrade.py --promote --apply # re-verify and write known_good (agent tree only)
    python3 project/scripts/tools_upgrade.py --force           # plan incl. auto:none brew tools
    python3 project/scripts/tools_upgrade.py --apply --force   # upgrade all brew tools, smoke, promote
"""
from __future__ import annotations

import datetime
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tools_check import (  # noqa: E402
    BREW_FORMULA, PROPOSED, STATUS, brew_latest, bump_level, gcloud_latest, installed_version,
    load_proposals, report_outdated, save_proposals, ver_tuple,
)

UPGRADABLE = {"brew", "gcloud"}  # sources this script knows how to upgrade in-place

ROOT = Path(__file__).resolve().parent.parent
POLICY = ROOT / "project" / "policies" / "tools-policy.json"
WEB = ROOT / "wom7web"  # wom7web dir — smokes run here
RANK = {"patch": 0, "minor": 1, "major": 2}
ALLOW_RANK = {"none": -1, "patch": 0, "minor": 1, "major": 2}  # max bump a tool's `auto` permits


def smoke_argv(smoke: str) -> list[str]:
    if any(tok in smoke for tok in ("&&", "|", ">", "'", '"', "$")):
        return ["sh", "-c", smoke]
    return smoke.split()


def run(cmd: list[str], cwd: Path | None = None, timeout: int = 300):
    try:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(cmd, 1, "", str(exc))


def is_agent_tree(root: Path) -> bool:
    """Is `root` inside an agent tree (`~/.w0m/work/<name>/w0m`)? The live checkout is the owner's and the deploy's: nothing here may dirty it."""
    base = (Path.home() / ".w0m" / "work").resolve()
    try:
        Path(root).resolve().relative_to(base)
    except ValueError:
        return False
    return True


def record_proposal(proposals: dict, name: str, spec: dict, frm: str, to: str, smoke_passed: bool) -> None:
    """One proposal per tool: a later run replaces an earlier one, so the file always says what the NEWEST verified version is."""
    proposals[name] = {
        "tool": name, "from": frm, "to": to, "smoke": "passed" if smoke_passed else "none",
        "source": spec.get("source"), "proposed_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }


def _clear_held_status(cleared_tools: set[str]) -> None:
    """Remove tools that subsequently passed smoke in reconcile/promote from STATUS['held']."""
    if not cleared_tools or not STATUS.exists():
        return
    try:
        st = json.loads(STATUS.read_text(encoding="utf-8"))
        held = [t for t in (st.get("held") or []) if t not in cleared_tools]
        if held != list(st.get("held") or []):
            st["held"] = held
            st["ok"] = not held
            STATUS.write_text(json.dumps(st, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError):
        pass


def promote(policy: dict, apply: bool) -> int:
    """Re-verify every recorded proposal NOW and, with `apply`, write the ones that hold into THIS tree's policy.

    Exit 0 = nothing blocked, 1 = something stayed blocked, 2 = refused (not an agent tree, or an unreadable state file).
    A proposal is a claim about a past moment; each one is checked again so a stale or since-broken one cannot land:
    installed must still equal the proposed version, sit at or above `min`, and pass its smoke. A tool with no smoke is never promoted silently.
    """
    try:
        proposals = load_proposals(PROPOSED)
    except (OSError, ValueError) as exc:
        print(f"❌ cannot read the proposals file {PROPOSED}: {exc}", file=sys.stderr)
        return 2
    print("▶ known_good promotion (re-verified)" + ("" if apply else " — DRY RUN, re-run with --apply in an agent tree"))
    if not proposals:
        print("  nothing proposed (the weekly run records smoke-verified upgrades here)")
        return 0
    if apply and not is_agent_tree(ROOT):
        print(f"❌ refusing to write {POLICY} outside an agent tree: the live checkout is the owner's and the deploy's. "
              "Run `just agent-tree <name>`, work from the tree it creates, then `just tools-promote --apply`, commit, and `just agent-tree-land`.",
              file=sys.stderr)
        return 2
    tools = policy["tools"]
    promoted, blocked = [], []
    for name, prop in sorted(proposals.items()):
        spec = tools.get(name)
        frm, to = prop.get("from"), prop.get("to")
        if spec is None:
            blocked.append(f"{name}: no longer in tools-policy.json")
            continue
        cur = installed_version(name, spec.get("version_arg", "--version"), spec)
        if cur is None:
            blocked.append(f"{name}: not installed any more")
        elif ver_tuple(cur) < ver_tuple(to):
            blocked.append(f"{name}: installed {cur} is BEHIND the proposed {to} (downgrade or failed upgrade)")
        elif cur != to:
            blocked.append(f"{name}: proposal is stale — proposed {to} but {cur} is installed; run the weekly job again")
        elif ver_tuple(to) < ver_tuple(spec["min"]):
            blocked.append(f"{name}: {to} is below min {spec['min']}")
        elif not spec.get("smoke"):
            blocked.append(f"{name}: {frm} → {to} has NO smoke declared — verify by hand")
        else:
            print(f"  → {name}: {frm} → {to}, smoking `{spec['smoke']}`...")
            sr = run(smoke_argv(spec["smoke"]), cwd=WEB, timeout=180)
            if sr.returncode != 0:
                blocked.append(f"{name}: smoke FAILED for {to} — {(sr.stderr or sr.stdout).strip()[-160:]}")
            else:
                print("    \u2713 smoke ok")
                promoted.append((name, frm, to))
    for name, frm, to in promoted:
        if apply:
            tools[name]["known_good"] = to
    if apply and promoted:
        POLICY.write_text(json.dumps(policy, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        for name, _frm, _to in promoted:
            proposals.pop(name, None)
        save_proposals(PROPOSED, proposals)
        _clear_held_status({name for name, _frm, _to in promoted})
    print(f"\n  {'promoted' if apply else 'would promote'}: {', '.join(f'{n} {f}→{t}' for n, f, t in promoted) or 'none'}")
    if blocked:
        print(f"  \u26a0 {len(blocked)} NOT promoted (they stay proposed, so they stay visible):")
        for b in blocked:
            print(f"    - {b}")
    if apply and promoted:
        print("\n  next: review the diff, `git commit -m \"chore(T112): bump tools baseline known_good\" -- project/policies/tools-policy.json`, `just agent-tree-land`.")
    elif not apply and promoted:
        print("\n  re-run with --apply in an agent tree to write them.")
    return 1 if blocked else 0


def reconcile(tools: dict, policy: dict, apply: bool) -> tuple[list[str], list[str]]:
    """Find installed versions AHEAD of `known_good` that pass their smoke, and (with `apply`) PROPOSE them (T546: this no longer writes the policy).

    T247 AC3. This closes a hole that `tools-upgrade` structurally cannot: once installed is AHEAD
    of `known_good` there is nothing left to upgrade, so the upgrade path can never reconcile it and
    the drift is permanent. Measured 2026-08-21: four tools sat in that state, `osv-scanner` among
    them — a scanner that runs in the pre-commit hook of every repo here — because the 2026-08-17
    run upgraded it and then held the promotion when its smoke failed.

    🔴 Smoke-gated, unlike the pre-existing `tools_check.py --update-known-good`, which promotes
    every present tool to whatever is installed with **no verification at all**. That flag is the
    reason this drift looked cheap to close and was not: promoting an unsmoked version does not
    verify anything, it just stops the gate complaining. Reconciliation without a smoke would
    launder exactly the state this ticket exists to surface.

    A tool with no `smoke` declared is NOT promoted silently — it is returned as unverifiable, so
    "we never checked" cannot be spelled the same way as "we checked and it passed".
    """
    promoted, blocked = [], []
    proposals = load_proposals(PROPOSED) if apply else {}
    for name, spec in sorted(tools.items()):
        if name.startswith("_"):
            continue
        cur = installed_version(name, spec.get("version_arg", "--version"), spec)
        kg = spec.get("known_good")
        if cur is None or kg is None or cur == kg:
            continue
        if ver_tuple(cur) < ver_tuple(kg):
            # Installed is BEHIND known_good — a downgrade or a failed upgrade, not a reconcile
            # candidate. Promoting here would silently lower the bar.
            blocked.append(f"{name}: installed {cur} is BEHIND known_good {kg} — not a reconcile")
            continue
        if ver_tuple(cur) < ver_tuple(spec["min"]):
            blocked.append(f"{name}: installed {cur} is below min {spec['min']}")
            continue
        smoke = spec.get("smoke")
        if not smoke:
            blocked.append(f"{name}: {kg} → {cur} has NO smoke declared — verify by hand")
            continue
        print(f"  → {name}: {kg} → {cur}, smoking `{smoke}`...")
        sr = run(smoke_argv(smoke), cwd=WEB, timeout=180)
        if sr.returncode != 0:
            blocked.append(f"{name}: smoke FAILED for {cur} — {(sr.stderr or sr.stdout).strip()[-160:]}")
            continue
        print(f"    \u2713 smoke ok")
        if apply:
            record_proposal(proposals, name, spec, kg, cur, True)
        promoted.append(f"{name} {kg}→{cur}")
    if apply and promoted:
        save_proposals(PROPOSED, proposals)
        _clear_held_status({p.split()[0] for p in promoted})
    return promoted, blocked


def main() -> int:
    apply = "--apply" in sys.argv

    if "--promote" in sys.argv:
        return promote(json.loads(POLICY.read_text(encoding="utf-8")), apply)

    # T247 AC3 — reconcile mode is its own operation, not a side effect of upgrading.
    if "--reconcile" in sys.argv:
        policy = json.loads(POLICY.read_text(encoding="utf-8"))
        print("▶ known_good reconciliation (smoke-gated)"
              + ("" if apply else " — DRY RUN, re-run with --apply"))
        promoted, blocked = reconcile(policy["tools"], policy, apply)
        print(f"\n  {'proposed' if apply else 'would propose'}: {', '.join(promoted) or 'none'}"
              + ("  — `just tools-promote` re-verifies and lands them" if apply and promoted else ""))
        if blocked:
            print(f"  \u26a0 {len(blocked)} NOT proposed:")
            for b in blocked:
                print(f"    - {b}")
        # Blocked entries are the finding, so they must move the exit code — otherwise this
        # reconciler becomes another thing that reports and changes nothing.
        return 1 if blocked else 0
    force = "--force" in sys.argv
    # --only <tool>[,<tool>] — upgrade a NAMED subset instead of every auto-eligible tool.
    # Added 2026-08-10 for a real ask ("keep infisical auto-updated") that the all-or-nothing
    # interface could not express: the auto batch that day also carried `just` (this toolchain's
    # own command interface) and a MAJOR gcloud bump, so "update one tool" meant "update eight".
    # An interface that makes the safe request impossible pushes people to the unsafe one.
    only: set[str] = set()
    if "--only" in sys.argv:
        i = sys.argv.index("--only")
        if i + 1 >= len(sys.argv):
            print("❌ --only needs a tool name (comma-separated for several)", file=sys.stderr)
            return 2
        only = {n.strip() for n in sys.argv[i + 1].split(",") if n.strip()}
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    tools = policy["tools"]
    if only:
        unknown = only - set(tools)
        if unknown:
            # Fail rather than silently upgrading nothing — a no-op that reports success is how a
            # "scheduled auto-update" quietly stops updating anything.
            print(f"❌ --only names tool(s) not in tools-policy.json: {', '.join(sorted(unknown))}",
                  file=sys.stderr)
            return 2
        tools = {k: v for k, v in tools.items() if k in only}
    brew = brew_latest()

    plan = []
    skipped = []  # (name, source, note) — has an update but no in-place upgrade path here
    gcloud_ver = None  # cached (current, latest), resolved at most once
    for name, spec in tools.items():
        if name.startswith("_"):
            continue
        src = spec.get("source")
        allow = spec.get("auto", "none")
        if src not in UPGRADABLE:
            # nvs / pyenv / tfenv / uv / npm — can't upgrade here; surface under --force.
            if force:
                skipped.append((name, src or "manual", spec.get("note", "")))
            continue
        if allow == "none" and not force:
            continue
        if src == "gcloud":
            # gcloud self-updates via `gcloud components update`. Its versions are rolling (not
            # semver), so the level cap is nominal — `auto` acts as a boolean (non-none = on).
            if gcloud_ver is None:
                gcloud_ver = gcloud_latest() or (None, None)
            cur, latest = gcloud_ver
        else:  # brew
            latest = brew.get(BREW_FORMULA.get(name, name))
            cur = installed_version(name, spec.get("version_arg", "--version"))
        if not latest or not cur or ver_tuple(latest) <= ver_tuple(cur):
            continue
        lvl = bump_level(ver_tuple(cur), ver_tuple(latest))
        # Normal runs honor the per-tool level cap (gcloud is level-exempt: auto:major);
        # --force lifts it everywhere (smoke is the real gate).
        if force or RANK[lvl] <= RANK[allow]:
            plan.append((name, spec, cur, latest, lvl))

    if not plan:
        print("  nothing auto-eligible to upgrade (run `just tools-check --outdated` for the full list)")
        if skipped:
            print("\n  no in-place upgrade here (update with their own tool):")
            for name, src, note in skipped:
                print(f"    {name:12} via {src} — {note}")
        return 0

    label = "UPGRADING" if apply else "PLAN (dry-run)"
    scope = " incl. auto:none (--force)" if force else " auto-eligible"
    print(f"  {label} — {len(plan)}{scope} tool(s):")
    for name, spec, cur, latest, lvl in plan:
        forced = force and RANK[lvl] > ALLOW_RANK.get(spec.get("auto", "none"), -1)
        nosmoke = force and not spec.get("smoke")
        flags = "".join([" ⚠forced" if forced else "", " ⚠no-smoke" if nosmoke else ""])
        print(f"    {name:12} {cur} → {latest} [{lvl}]{flags}")
    if skipped:
        print("\n  no in-place upgrade here (update with their own tool):")
        for name, src, note in skipped:
            print(f"    {name:12} via {src} — {note}")

    if not apply:
        hint = "--apply --force" if force else "--apply"
        print(f"\n  re-run with {hint} to upgrade, smoke-test, and promote known_good.")
        return 0

    promoted, failed, unverified = [], [], []
    proposals = load_proposals(PROPOSED)
    for name, spec, cur, latest, lvl in plan:
        src = spec.get("source")
        if src == "gcloud":
            print(f"\n  → gcloud components update --quiet ({cur} → {latest})...")
            up = run(["gcloud", "components", "update", "--quiet"], timeout=900)
        else:  # brew
            formula = BREW_FORMULA.get(name, name)
            print(f"\n  → brew upgrade {formula} ({cur} → {latest})...")
            up = run(["brew", "upgrade", formula])
        new = installed_version(name, spec.get("version_arg", "--version"))
        # Don't trust the exit code alone: `brew upgrade` returns non-zero on a spurious "Already
        # linked" warning even though the bottle upgraded. Judge by the resulting version.
        if new is None or ver_tuple(new) < ver_tuple(latest):
            print(f"    ✗ upgrade did not take (version still {new}):\n{(up.stderr or up.stdout)[-300:]}")
            failed.append(name)
            continue
        if ver_tuple(new) < ver_tuple(spec["min"]):
            print(f"    ✗ post-upgrade version {new} is below min {spec['min']} — NOT promoting")
            failed.append(name)
            continue
        if up.returncode != 0:
            print(f"    · {src} returned {up.returncode} but version advanced to {new} (likely a link/notice warning) — continuing to smoke")
        smoke = spec.get("smoke")
        if smoke:
            sr = run(smoke_argv(smoke), cwd=WEB, timeout=180)
            if sr.returncode != 0:
                print(f"    ✗ smoke FAILED (`{smoke}`) — NOT proposing a known_good bump; review/rollback:\n{(sr.stderr or sr.stdout)[-400:]}")
                failed.append(name)
                continue
            print(f"    ✓ smoke ok (`{smoke}`)")
        else:
            # Reachable only under --force (auto tools all carry a smoke). Upgrade took, but nothing
            # verified it — promote so known_good tracks reality, but flag it loudly.
            print(f" [WARN] no smoke defined for {name} — upgraded to {new} UNVERIFIED; verify by hand "
                  f"({spec.get('note', 'see policy note')})")
            unverified.append(f"{name}→{new}")
        record_proposal(proposals, name, spec, spec.get("known_good", cur), new, bool(smoke))
        promoted.append(f"{name} {spec.get('known_good', cur)}→{new}")

    if promoted:
        save_proposals(PROPOSED, proposals)
    print(f"\n  proposed: {', '.join(promoted) or 'none'}"
          + ("  — `just tools-promote` re-verifies and lands them in an agent tree" if promoted else ""))
    if unverified:
        print(f" [WARN] proposed UNVERIFIED (no smoke — `tools-promote` will not land these; verify by hand): {', '.join(unverified)}")
    if failed:
        print(f"  ✗ failed/held (needs review): {', '.join(failed)}")

    # Refresh the pre-push snapshot after actually changing something. Without this the cache keeps
    # describing the PRE-upgrade world until the next scheduled run — measured 2026-08-21, an apply
    # that upgraded four tools left the cache still naming `gcloud` as pending, so the pre-push warn
    # advertised work that was already done. A snapshot nobody refreshes after acting is a snapshot
    # that teaches people to ignore it.
    # T247 AC1 — record the OUTCOME so a failed run is visible without opening a launchd log.
    # Written on every apply, pass or fail: an outcome file that only appears on success cannot
    # distinguish "succeeded" from "never ran".
    if apply:
        try:
            import datetime
            STATUS.write_text(json.dumps({
                "ran": datetime.datetime.now().isoformat(timespec="seconds"),
                "ok": not failed,
                "proposed": promoted,
                "unverified": unverified,
                "held": failed,
            }, indent=2) + "\n", encoding="utf-8")
        except OSError as exc:
            print(f" [WARN] could not write the run-status file ({exc})")

    if apply and (promoted or unverified):
        try:
            report_outdated(json.loads(POLICY.read_text(encoding="utf-8"))["tools"], cache=True)
        except Exception as exc:  # never fail an otherwise-successful upgrade on a cache write
            print(f" [WARN] could not refresh the outdated cache ({exc}) — run `just tools-weekly`")

    # T247 AC6 — a partial run and a total failure must not report the same thing. Both stay
    # non-zero so a scheduler still sees failure, but they are distinguishable:
    #   0  nothing failed
    #   2  PARTIAL — something was promoted AND something was held
    #   1  TOTAL   — something was held and nothing was promoted
    # The 2026-08-17 run promoted four tools and held two, and reported the same `1` as a run that
    # achieved nothing — an exit code that cannot tell those apart is one people learn to ignore.
    if not failed:
        return 0
    if promoted or unverified:
        print(f"  ⇒ PARTIAL: {len(promoted) + len(unverified)} proposed, {len(failed)} held (exit 2)")
        return 2
    print(f"  ⇒ TOTAL FAILURE: 0 proposed, {len(failed)} held (exit 1)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
