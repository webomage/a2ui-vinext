#!/usr/bin/env python3
"""Red probes for `ade-rules-parity`.

The gate's whole claim is that it predicts, WITHOUT creating one, what a git worktree will contain.
So each probe builds a real temp repo, makes a real worktree, and checks the static verdict against
what is actually on disk there. A prediction that is never compared to the thing predicted is a
guess with a percentage sign.
"""
import pathlib, subprocess, sys, tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import ade_rules_parity as a  # noqa: E402

failures: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(("  ✅ " if cond else "  ❌ ") + label + ("" if cond else f"  — {detail}"))
    if not cond:
        failures.append(label)


def sh(*args, cwd=None):
    subprocess.run(args, cwd=cwd, capture_output=True, check=True)


with tempfile.TemporaryDirectory() as d:
    root = pathlib.Path(d)
    sibling = root / "sibling"; sibling.mkdir()
    (sibling / "rules").mkdir(); (sibling / "rules" / "r.md").write_text("rule")
    repo = root / "repo"; repo.mkdir()
    sh("git", "init", "-q", str(repo))
    sh("git", "-C", str(repo), "config", "user.email", "t@t"); sh("git", "-C", str(repo), "config", "user.name", "t")

    (repo / "CLAUDE.md").write_text("# rules")                    # tracked real file
    (repo / "inside").mkdir(); (repo / "inside" / "s.md").write_text("s")
    (repo / "link_in").symlink_to("inside")                       # symlink INSIDE the repo
    (repo / "link_out").symlink_to("../sibling/rules")            # symlink ESCAPING the repo
    (repo / "untracked").mkdir(); (repo / "untracked" / "u.md").write_text("u")   # never added
    sh("git", "-C", str(repo), "add", "CLAUDE.md", "inside", "link_in", "link_out")
    sh("git", "-C", str(repo), "commit", "-qm", "init")

    wt = root / "wt"
    sh("git", "-C", str(repo), "worktree", "add", "-q", "--detach", str(wt), "HEAD")

    for surface, want in [("CLAUDE.md", "reach"), ("link_in", "reach"), ("link_out", "fragile"),
                          ("untracked", "no"), ("missing", "no")]:
        state, why = a.reachable_in_worktree(repo, surface)
        check(f"{surface:<10} -> {want}", state == want, f"got {state}: {why}")

    # 🔑 FRAGILE means placement-dependent, and both halves are asserted. This worktree sits BESIDE
    # the target, so the escaping link resolves; a worktree elsewhere is where it dangles.
    check("fragile link RESOLVES when the worktree is beside its target", (wt / "link_out").exists())
    import shutil
    far = root / "far"; far.mkdir()
    sh("git", "-C", str(repo), "worktree", "add", "-q", "--detach", str(far / "wt2"), "HEAD")
    check("...and DANGLES when the worktree is placed anywhere else",
          not (far / "wt2" / "link_out").exists(),
          "this is the w0m-api case: ../w0m-web/ does not exist beside a scratch worktree")

    state, why = a.reachable_in_worktree(repo, "link_out")
    check("...and the message says it is placement-dependent, not simply broken",
          "ONLY if" in why and "OUTSIDE" in why, why)
    state, why = a.reachable_in_worktree(repo, "untracked")
    check("an on-disk-but-untracked surface says it reaches no clone", "never reaches" in why, why)

    # A tracked dir that gains an untracked, NOT-ignored file is partial delivery.
    (repo / "inside" / "stray.md").write_text("stray")
    state, why = a.reachable_in_worktree(repo, "inside")
    check("a tracked dir with an untracked, unignored file is flagged", state == "no" and "untracked and NOT ignored" in why, why)

    # ...but an IGNORED file is a decision, not a failure. This is the false finding that shipped
    # in the first draft: .agent/deployments build logs read as 'only 31% delivered'.
    (repo / ".gitignore").write_text("inside/stray.md\n")
    sh("git", "-C", str(repo), "add", ".gitignore"); sh("git", "-C", str(repo), "commit", "-qm", "ignore")
    state, why = a.reachable_in_worktree(repo, "inside")
    check("MUTATION: once that file is IGNORED, the dir is clean again", state == "reach", why)

    # MUTATION: the naive rule (count files on disk) would still call it incomplete.
    on_disk = sum(1 for f in (repo / "inside").rglob("*") if f.is_file())
    tracked = a.tracked(repo, "inside")
    check("MUTATION: the OLD on-disk rule would still flag it, so the fix is real",
          on_disk > tracked and state == "reach", f"on_disk={on_disk} tracked={tracked}")

print()
if failures:
    print(f"❌ {len(failures)} failure(s):")
    for f in failures:
        print(f"   · {f}")
    sys.exit(1)
print("✅ static reachability matches real worktrees, and ignored files are not a finding")
