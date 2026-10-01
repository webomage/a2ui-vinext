#!/usr/bin/env python3
"""T23 spec-drift-gate — deterministic spec↔code/ticket drift detection for a hook.

The `openspec-verify-change` skill is LLM-driven and interactive; a pre-push/deploy gate needs a
fast, offline, deterministic check. This is that check. It reconciles three surfaces:

  openspec/changes/<name>/   (active design changes: proposal.md + tasks.md)
  .tasks/T*.md               (tickets; frontmatter `status:` + `spec:`)
  openspec/changes/archive/  (where a finished change belongs)

Drift classes:
  HARD  completed-not-archived  — a change whose tasks are 100% checked but still under changes/.
  HARD  done-ticket-active-spec — a ticket with status:done whose `spec:` points to an ACTIVE
        (un-archived) change. This is the "spec-only change that was actually built" bug.
  HARD  orphan-change           — an active change no ticket references. All active changes must
        have an owning ticket in .tasks/T*.md (graduated 2026-10-01, T77).
  WARN  structural              — a change missing proposal.md or tasks.md.
  INFO  in-flight-multi-ticket  — a change with multiple owning tickets, some done, some open.
        Normal progressive delivery; do NOT archive.

Modes:
  (default / --all)        Audit every active change. Exit 1 on any HARD drift. Used by
                           `just spec-drift` and CI.
  --scope-diff <base-ref>  Pre-push mode. Only HARD-fail on drift in changes/tickets that DIFFER
                           from <base-ref> (i.e. touched by this push); report the pre-existing
                           backlog as advisory so unrelated pushes aren't blocked.

Offline + stdlib only. Python per convention. Exit 1 on blocking drift, else 0.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
WEB = os.path.join(ROOT, "wom7web")
CHANGES = os.path.join(WEB, "openspec/changes")
TICKETS = os.path.join(ROOT, ".tasks")

TASK_ANY = re.compile(r"^\s*- \[[ xX]\]", re.M)
TASK_DONE = re.compile(r"^\s*- \[[xX]\]", re.M)
FM_FIELD = re.compile(r"^(status|spec):\s*[\"']?(.*?)[\"']?\s*$", re.M)
# Every change a `spec:` field names — a ticket may legitimately own more than one.
SPEC_CHANGE = re.compile(r"openspec/changes/([^/\s\"',]+)")


def _run(args, cwd=ROOT):
    try:
        out = subprocess.run(args, capture_output=True, text=True, cwd=cwd, timeout=30)
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    return out.stdout if out.returncode == 0 else None


def active_changes():
    if not os.path.isdir(CHANGES):
        return []
    return sorted(
        d for d in os.listdir(CHANGES)
        if d != "archive" and os.path.isdir(os.path.join(CHANGES, d))
    )


def task_ratio(change_dir):
    """(#done, #total) from tasks.md, or (0, 0) if none."""
    t = os.path.join(change_dir, "tasks.md")
    if not os.path.isfile(t):
        return 0, 0
    txt = open(t, encoding="utf-8", errors="ignore").read()
    return len(TASK_DONE.findall(txt)), len(TASK_ANY.findall(txt))


def tickets_by_spec():
    """spec-dir-name -> list of (ticket_id, status) referencing it via the `spec:` field."""
    out = {}
    if not os.path.isdir(TICKETS):
        return out
    for fn in os.listdir(TICKETS):
        if not (fn.startswith("T") and fn.endswith(".md")):
            continue
        fields = dict(FM_FIELD.findall(open(os.path.join(TICKETS, fn), encoding="utf-8", errors="ignore").read()))
        spec = fields.get("spec", "")
        # 🔴 ALL of them, not the last. This was `split("openspec/changes/")[-1]`, which sees
        # exactly ONE change per ticket: a `spec:` naming two changes had every earlier one read
        # as an orphan, and "orphan" is a WARN, so the loss was silent. Found 2026-08-29 when
        # T117 declared two and only the trailing one attributed — the fix worked only because
        # the new path happened to be appended last.
        for name in SPEC_CHANGE.findall(spec):
            out.setdefault(name, []).append((fn[:-3], fields.get("status", "")))
    return out


def changed_paths(base_ref):
    """Set of repo-relative paths that differ from base_ref (three-dot: since merge-base)."""
    paths = set()
    for repo_dir in (ROOT, WEB):
        out = _run(["git", "diff", "--name-only", f"{base_ref}...HEAD"], cwd=repo_dir)
        if out is None:
            out = _run(["git", "diff", "--name-only", "HEAD~1...HEAD"], cwd=repo_dir) or ""
        for p in out.splitlines():
            if p.strip():
                paths.add(p.strip())
    return paths


def ownership_verdict(name, refs, done, total):
    """Is an active change spec-only-actually-built, or just partially closed?

    Pure, so it can be PROVEN to fire — the gate had **no test at all** before 2026-08-22, and this
    is the rule that was wrong.

    🔴 **The original fired HARD on ANY done owner, and its remedy was dangerous.**
    `2026-07-11-client-conversion-and-contracts` is owned via `spec:` by FIVE tickets and sits at
    **0/25 tasks**; closing [[T2]] legitimately at 6/6 made the gate demand *"archive the change"* —
    which would have archived a change with four open owners and no work done, purely to unblock a
    push. A gate whose remedy is worse than its finding still gets obeyed, because the push is what
    the person came for.

    ⚠️ The intent is preserved, not weakened: a change whose owners are **all** done really is
    spec-only-actually-built and still blocks. Partial closure is the normal mid-flight state, so it
    reports — with an explicit *do NOT archive* — instead of blocking.
    """
    done_tickets = [tid for tid, st in refs if st == "done"]
    open_tickets = [tid for tid, st in refs if st != "done"]
    if done_tickets and not open_tickets:
        return [("HARD", f"change `{name}` is active but ALL owning ticket(s) "
                         f"{', '.join(done_tickets)} are done — spec-only-actually-built drift")]
    if done_tickets:
        return [("WARN", f"change `{name}` has done owner(s) {', '.join(done_tickets)} alongside "
                         f"open {', '.join(open_tickets)} (tasks {done}/{total}) — partially "
                         f"closed, not drift; do NOT archive")]
    return []


def main(argv):
    scope_base = None
    if "--scope-diff" in argv:
        i = argv.index("--scope-diff")
        scope_base = argv[i + 1] if i + 1 < len(argv) else "origin/beta"

    by_spec = tickets_by_spec()
    touched = changed_paths(scope_base) if scope_base else None

    def in_scope(change_name):
        if touched is None:
            return True
        if any(change_name in p for p in touched):
            return True
        for tid, _ in by_spec.get(change_name, []):
            if any(f"{tid}.md" in p for p in touched):
                return True
        return False

    hard: list[tuple[str, str | None]] = []
    advisory: list[tuple[str, str | None]] = []
    warn: list[tuple[str, str | None]] = []
    info: list[str] = []

    for name in active_changes():
        d = os.path.join(CHANGES, name)
        done, total = task_ratio(d)
        refs = by_spec.get(name, [])
        scoped = in_scope(name)

        findings: list[tuple[str, str, str | None]] = []
        if total > 0 and done == total:
            findings.append(("HARD", f"change `{name}` is 100% complete ({done}/{total}) but not archived — archive it",
                             f"openspec archive {name} --yes"))
        for level, msg in ownership_verdict(name, refs, done, total):
            if level == "HARD":
                findings.append(("HARD", msg, f"Archive change `{name}` or reopen/update ticket status in .tasks/"))
            elif "partially closed, not drift; do NOT archive" in msg:
                # Normal in-flight multi-ticket delivery: classify as INFO rather than confusing WARN
                findings.append(("INFO", msg, None))
            else:
                findings.append((level, msg, None))
        if not os.path.isfile(os.path.join(d, "proposal.md")) or not os.path.isfile(os.path.join(d, "tasks.md")):
            findings.append(("WARN", f"change `{name}` missing proposal.md or tasks.md",
                             f"Ensure proposal.md and tasks.md exist under openspec/changes/{name}/, or remove directory"))
        if not refs:
            # Graduated to HARD (2026-10-01, T77): every active change must have an owning ticket in .tasks/T*.md
            findings.append(("HARD", f"change `{name}` has no owning ticket (orphan; tasks {done}/{total})",
                             f"Assign an owning ticket in .tasks/T*.md (spec: openspec/changes/{name}) or archive via 'openspec archive {name} --skip-specs'"))

        for level, msg, rec in findings:
            if level == "HARD":
                (hard if scoped else advisory).append((msg, rec))
            elif level == "INFO":
                info.append(msg)
            else:
                warn.append((msg, rec))

    print(f"spec-drift-gate: {len(active_changes())} active changes, "
          f"{sum(len(v) for v in by_spec.values())} spec-linked tickets"
          + (f" (scoped to diff vs {scope_base})" if scope_base else " (full audit)"))

    if info:
        print("\n── In-Flight Multi-Ticket Changes (Normal In-Progress State) ────")
        for m in info:
            print(f" [INFO] {m}")

    if warn:
        print("\n── Actionable Warnings & Recommendations ───────────────────────")
        for m, rec in warn:
            print(f" [WARN] {m}")
            if rec:
                print(f"        ↳ Recommendation: {rec}")

    if advisory:
        print("\n── Advisory Pre-Existing Drift (Not Blocking This Push) ────────")
        for m, rec in advisory:
            print(f"  • {m}")
            if rec:
                print(f"    ↳ Remedy: {rec}")

    if hard:
        print("\n── Critical Blocking Drift ────────────────────────────────────")
        for m, rec in hard:
            print(f"  ❌ {m}")
            if rec:
                print(f"     ↳ Remedy: {rec}")

    if hard:
        print(f"\nspec-drift-gate FAILED ({len(hard)} blocking drift) — archive the change "
              f"(openspec archive / w0m-sdlc-archive) or fix the ticket status.")
        return 1
    if advisory:
        print(f"\nspec-drift-gate OK for this push; {len(advisory)} pre-existing drift item(s) remain "
              f"— run `just spec-drift` to see them all.")
    else:
        print("\nspec-drift-gate OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
