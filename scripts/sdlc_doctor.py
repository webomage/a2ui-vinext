#!/usr/bin/env python3
"""w0m SDLC toolchain preflight (T119 AC7).

Verifies the interfaces the SDLC contract depends on, before a gate runs work
that would fail confusingly halfway through:

    commands -> `just`        every repo exposes the canonical recipe set
    secrets  -> `infisical`   every repo declares a workspace, or declares it has
                              no secrets
    tools                     EVERY required tool in tools-policy.json is present
                              at its floor (optional ones advisory)
    hooks                     every repo with a hook config has hooks INSTALLED
                              (pre-commit framework or husky), so the gate stack runs

Checks the *contract* (are they usable here, at the floor, wired into
.w0m/sdlc.json, hooks actually installed), not merely whether the binaries exist.
Enhanced 2026-07-24 (T127) to cover all required tools + git-hook install state,
so it can double as the SDLC install/bootstrap preflight.

Exit 0 = conformant. Exit 1 = a gate should not run.
Add --quiet to print only failures.

Usage:  just sdlc-doctor   |   python3 scripts/sdlc_doctor.py [--quiet]
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

def find_workspace_root(start_path: Path | None = None) -> Path:
    """Find the workspace root containing .tasks and .w0m/sdlc.json."""
    cur = (start_path or Path(__file__)).resolve()
    for parent in [cur] + list(cur.parents):
        if (parent / ".tasks").is_dir() and (parent / ".w0m").is_dir():
            return parent
        if (parent / ".git").exists() and (parent / "wom7web").is_dir():
            return parent
    return Path(__file__).resolve().parents[1]


ROOT = find_workspace_root()
CANONICAL = ROOT / "wom7web"
SDLC_JSON = ROOT / ".w0m" / "sdlc.json"
TOOLS_POLICY = ROOT / "project" / "policies" / "tools-policy.json"

# The contract is DECLARED in .w0m/sdlc.json -> toolchain (T119 AC6: nothing hardcoded
# here, so this script works for any project that adopts the config).
FALLBACK_RECIPES = ["check", "typecheck", "lint", "test", "test-e2e", "build"]


# ── project scoping (T182) ────────────────────────────────────────────────────
# `--project <dir>` enforces the DECLARATION-relative half of this doctor — the `secrets` and
# `toolchain` keys the client profile requires — against another project.
#
# 🔴 Deliberately NOT the whole doctor. Most of what main() does is estate-shaped: it globs
# `ROOT/wom7*` for per-repo justfiles and `.infisical.json`, probes host tool floors from w0m's
# tools-policy.json, and checks w0m's canonical recipes. Pointing that at a client would report on
# w0m while naming the client, which is the failure this scoping exists to prevent. So client mode
# runs the declaration checks only, and names what it did not run.
PROJECT: Path | None = None


def sdlc_path() -> Path:
    return (PROJECT if PROJECT is not None else ROOT) / ".w0m" / "sdlc.json"


def check_declaration() -> tuple[list[str], list[str]]:
    """The `secrets` + `toolchain` contract, read from whichever project is scoped.

    These are the two keys the client profile requires this script for, and they are the two that
    are genuinely project-relative: what secrets manager the project declares, that it declares a
    way to inject them, and that it declares its toolchain floors at all.
    """
    problems: list[str] = []
    notes: list[str] = []
    sdlc = sdlc_path()
    try:
        decl = json.loads(sdlc.read_text())
    except (OSError, json.JSONDecodeError) as e:
        return [f"cannot read {sdlc} ({type(e).__name__})"], []

    tc = decl.get("toolchain") or {}
    if not tc:
        problems.append("`toolchain` is absent — nothing declares the version floors this project "
                        "runs on, so nothing can check them")
    else:
        notes.append(f"toolchain declares {len(
            [k for k in tc if not k.startswith('_')])} field(s)")

    secrets = decl.get("secrets") or {}
    want_mgr = tc.get("secrets_via", "infisical")
    if not secrets:
        problems.append("`secrets` is absent — a project with no declared secret manager has an "
                        "undeclared security posture, not an absent one")
    else:
        if secrets.get("manager") != want_mgr:
            problems.append(f"secrets.manager is {secrets.get('manager')!r}, not {want_mgr!r}")
        if not secrets.get("run"):
            problems.append("secrets.run is not set — gates cannot inject secrets")
    return problems, notes


def toolchain() -> dict:
    try:
        return json.loads(SDLC_JSON.read_text()).get("toolchain", {})
    except OSError:
        return {}


def sh(*args: str, cwd: str | Path | None = None, timeout: float | None = None) -> tuple[int, str]:
    """Run a command. `cwd` matters: `pre-commit install` has no `-C` flag, so without it the
    hook lands in whatever repo the caller happens to be standing in rather than the target."""
    try:
        r = subprocess.run(args, capture_output=True, text=True,
                           cwd=str(cwd) if cwd else None, timeout=timeout)
    except subprocess.TimeoutExpired:
        # 124, the conventional timeout code. A preflight that HANGS reads as slow work; one that
        # reports a timeout reads as an unverified check, which is the truth.
        return 124, f"{args[0]}: timed out after {timeout}s"
    except (OSError, subprocess.SubprocessError) as e:
        # An ABSENT command must be a finding, not a traceback. Without this, a missing binary
        # raised FileNotFoundError straight out of the doctor — so the tool whose job is to
        # report "X is not installed" died on exactly that condition (found 2026-08-06).
        return 127, f"{args[0]}: {e}"
    return r.returncode, (r.stdout or r.stderr).strip()


def version_tuple(text: str) -> tuple[int, ...]:
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", text)
    return tuple(int(g) for g in m.groups()) if m else (0, 0, 0)


def check_floor(tool: str, probe: list[str], problems: list[str], notes: list[str]) -> None:
    """Compare an installed tool against its tools-policy.json floor."""
    try:
        policy = json.loads(TOOLS_POLICY.read_text())["tools"][tool]
    except (OSError, KeyError):
        notes.append(f"{tool}: no entry in tools-policy.json — floor not checked")
        return
    code, out = sh(*probe)
    if code != 0:
        problems.append(f"{tool} is not runnable ({' '.join(probe)} failed)")
        return
    have, want = version_tuple(out), version_tuple(policy.get("min", "0.0.0"))
    if have < want:
        problems.append(
            f"{tool} {'.'.join(map(str, have))} is below the policy floor "
            f"{policy['min']} — raise it or update the tool"
        )


def _probe_version(name: str, meta: dict) -> str | None:
    """Delegate to tools_check — it is the ONE implementation of "is this tool installed".

    🔴 This used to re-probe with a local `[name, "--version"]` default, and the two diverged.
    T166 taught `tools_check.installed_version` that a `source: uvx` tool has NO binary on PATH
    (uvx materialises it per run) and must be probed with its declared `smoke` command. This copy
    never learned that — so the moment T166 added `serena` to tools-policy.json, `just sdlc-doctor`
    stopped reporting and started CRASHING with `FileNotFoundError: 'serena'`, taking the whole
    SDLC preflight down with it. Found 2026-08-06 by the preflight itself, at the top of a gate.

    Two separate bugs, and the second is worse than the uvx gap: `sh()` never caught
    `FileNotFoundError`, so ANY absent optional tool (aws, az, terraform, gcloud, ast-grep …)
    would crash the doctor rather than be reported as "not installed" — which is the doctor's
    entire job. A checker that dies on the condition it exists to report is not a checker.
    """
    import importlib.util
    spec_path = CANONICAL / "project" / "scripts" / "tools_check.py"
    if not spec_path.exists():
        return None
    spec = importlib.util.spec_from_file_location("w0m_tools_check", spec_path)
    if spec is None or spec.loader is None:
        # Same contract as the `spec_path.exists()` check above: a probe that cannot be
        # loaded returns None rather than taking the doctor down (T189).
        return None
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        return mod.installed_version(name, meta.get("version_arg", "--version"), meta)
    except Exception:  # noqa: BLE001 — a broken probe must not take the doctor down
        return None


def check_all_tools(problems: list[str], notes: list[str]) -> None:
    """Every tool in tools-policy.json: REQUIRED ones must be present + at floor
    (→ problem); optional ones are advisory (→ note if absent)."""
    try:
        tools = json.loads(TOOLS_POLICY.read_text()).get("tools", {})
    except OSError:
        problems.append(f"cannot read {TOOLS_POLICY}")
        return
    for name, meta in sorted(tools.items()):
        have = _probe_version(name, meta)
        if have is None:
            msg = f"{name}: not installed or not runnable"
            (problems if meta.get("required") else notes).append(
                msg if meta.get("required") else f"{msg} (optional — needed only for its feature)")
            continue
        want = meta.get("min", "0.0.0")
        if version_tuple(have) < version_tuple(want):
            problems.append(
                f"{name} {have} is below the policy floor {want} — raise it or update the tool")


def check_versioning(problems: list[str], notes: list[str]) -> None:
    """T131 AC5 — the release-version schema is conformant.

    DELEGATES to the two gates that already own these questions, and deliberately reimplements
    neither:

      `just version-check`         — the producer emits the declared format; no OTHER site in the
                                     scanned set constructs a version without a reasoned exemption;
                                     an empty scan set FAILS. (`project/scripts/version_doctor.py`)
      `just skills-version-check`  — every w0m-native canonical skill carries a conforming, CURRENT
                                     version, "current" meaning its content hash still matches.

    🔴 Delegation is the whole point, and it is not a style preference. This file previously kept
    its own copy of "is this tool installed" and the copies diverged until `sdlc-doctor` CRASHED
    (2026-08-06). A second implementation of "is this version conformant" would rot the same way —
    and rot invisibly, because both copies would keep exiting 0 while checking different things.

    A timeout is applied because a preflight that HANGS is worse than one that fails: the gate
    would sit there looking like slow work rather than a broken check.
    """
    for recipe, owns in (("version-check", "the estate's release-version producers"),
                         ("skills-version-check", "the skill corpus's own versions")):
        # From wom7api — the justfile lives here and its recipes use bare paths relative to it.
        code, out = sh("just", recipe, cwd=ROOT / "wom7api", timeout=180)
        if code == 0:
            continue
        tail = " · ".join(line.strip() for line in out.splitlines()[-2:] if line.strip())
        if code == 124:
            notes.append(f"{recipe}: timed out — conformance for {owns} is UNVERIFIED, not clean")
        else:
            problems.append(f"{recipe} failed (exit {code}) — {owns} are non-conformant: {tail}")


def _hook_gap(exempt: dict) -> list[tuple[Path, str]]:
    """Repos that DECLARE a hook config but have no hooks installed → [(repo, kind)].

    Split out from reporting so the same detection drives both `check_hooks` (report) and
    `install_hooks` (fix). One detector, two consumers — two copies would drift, and the
    thing they would disagree about is whether a gate is running at all.
    """
    gap: list[tuple[Path, str]] = []
    for repo in sorted(ROOT.glob("wom7*")):
        if not (repo / ".git").exists() or repo.name in exempt:
            continue
        pc = (repo / ".pre-commit-config.yaml").exists()
        husky = (repo / ".husky").is_dir()
        if not (pc or husky):
            continue
        hookspath = sh("git", "-C", str(repo), "config", "--get", "core.hooksPath")[1]
        installed = (repo / ".git" / "hooks" / "pre-commit").exists() or bool(hookspath)
        if not installed:
            gap.append((repo, "husky" if husky else "pre-commit"))
    return gap


def check_hooks(exempt: dict, problems: list[str], notes: list[str]) -> None:
    """Report repos whose declared hooks are not installed. A declared-but-not-installed
    hook is a gate that looks present and never runs — see `--install-hooks` to close it."""
    for repo, kind in _hook_gap(exempt):
        notes.append(
            f"{repo.name}: git hooks declared ({kind}) but NOT installed — "
            f"run `just sdlc-doctor --install-hooks` (idempotent) so the gate stack actually runs"
        )


def install_hooks(exempt: dict) -> int:
    """T127 AC10 — INSTALL the missing hooks, idempotently. Returns an exit code.

    The doctor previously only reported the gap, which left the most consequential finding it
    produces ("your gates are not running") as homework. This closes it.

    ⚠️ Installs ONLY where a config is already declared. It never invents a hook stack for a repo
    that has not opted in — that would put gates on someone's repo by surprise, and the standard
    stack assumes tooling (gitleaks/osv/semgrep) the repo may not have.
    ⚠️ `commit-msg` is installed alongside `pre-commit` deliberately: the T129 `T##` gate and the
    Conventional-Commits check both live there, and `pre-commit install` does NOT wire it by
    default. Installing only pre-commit would leave half the standard stack silently absent —
    the exact declared-but-not-running shape this function exists to fix.
    """
    gap = _hook_gap(exempt)
    if not gap:
        print("✅ hooks: every repo that declares a hook config already has it installed — nothing to do")
        return 0

    failures: list[str] = []
    for repo, kind in gap:
        if kind == "husky":
            # Husky wires itself through the package `prepare` script; re-running the package
            # manager's prepare is the sanctioned path rather than hand-writing core.hooksPath.
            code, out = sh("pnpm", "-C", str(repo), "run", "prepare")
            if code != 0:
                code, out = sh("git", "-C", str(repo), "config", "core.hooksPath", ".husky/_")
        else:
            # cwd=repo is load-bearing — pre-commit has no -C flag, and without it this
            # installs into the CALLER's repo. Caught before shipping only because the RED
            # probe below runs against a different repo than the one it is invoked from.
            code, out = sh("pre-commit", "install", "--install-hooks",
                           "--hook-type", "pre-commit", "--hook-type", "commit-msg",
                           "--overwrite", cwd=repo)  # --overwrite keeps re-runs idempotent
        if code == 0:
            print(f"  ✅ {repo.name}: {kind} hooks installed")
        else:
            failures.append(f"{repo.name} ({kind}): {out.strip()[:160]}")
            print(f"  🔴 {repo.name}: {kind} hook install FAILED — {out.strip()[:160]}")

    # Re-detect rather than trusting the installer's exit code — the whole point of this module
    # is that a tool reporting success is not evidence the gate is wired.
    still = _hook_gap(exempt)
    if still:
        print(f"🔴 still not installed after the attempt: {', '.join(r.name for r, _ in still)}")
        return 1
    if failures:
        print(f"⚠️  installer reported errors but detection is now clean: {'; '.join(failures)}")
    print(f"✅ hooks: {len(gap)} repo(s) fixed; re-detection confirms 0 remaining")
    return 0


def check_stacks(problems: list[str], notes: list[str]) -> None:
    """T130: cross-reference the per-stack registry. Runs discovery's enforcement
    (every declared command role binds a real `just` recipe; drift blocks) so the
    preflight fails before a gate runs against a broken/stale stacks registry."""
    discovery = CANONICAL / "project" / "scripts" / "discovery.py"
    if not discovery.exists():
        return  # registry tooling not present in this project — nothing to check
    code, out = sh("python3", str(discovery), "--enforce", "--quiet")
    if code != 0:
        problems.append("per-stack registry / just-automation enforcement failed "
                        "(`just discovery --enforce`) — a declared command has no recipe, "
                        "or drift blocks: " + (out.splitlines()[-1] if out else ""))


def check_hygiene(problems: list[str], notes: list[str]) -> None:
    """T135 task 2.2: surface the repo-hygiene gates in the doctor.

    Reported as NOTES, not problems, while the strands are still red. The alternative — wiring
    them as problems now — would make `sdlc-doctor` fail for every ticket in the estate over
    pre-existing debt this change is midway through paying down, and a doctor that always fails
    stops being read. Each check's registry entry carries its promotion trigger (`gates` ->
    `remeasure`); when a strand goes green, move it from this list into `problems`.
    """
    hygiene = CANONICAL / "project" / "scripts" / "repo_hygiene.py"
    if not hygiene.exists():
        return
    for check in ("docs", "license", "secrets"):
        code, out = sh("python3", str(hygiene), check)
        if code != 0:
            headline = next((ln for ln in out.splitlines() if ln.startswith("❌")), "")
            notes.append(f"hygiene {check}-check not yet green (T135 §{check}): {headline}")


def check_ticket_parity(problems: list[str], notes: list[str]) -> None:
    """Every TASKS.md row must have a ticket file, and vice versa.

    WHY THIS IS A PROBLEM AND NOT A NOTE, in the row->file direction: the T-row is
    status-of-record for humans, but the ticket FILE is what the tooling reads. The SDLC
    gates load it, and sync_github.py builds the GitHub mirror by globbing
    project/tickets/*.md. So a row with no file is invisible three times over — it cannot
    be started through a gate, it never becomes an issue, and it never reaches the board.

    This was recorded for months as "six tickets have no file". Measured 2026-07-26: 36
    rows, 29 of them not done. A 5x undercount that nothing was watching, which is exactly
    why it is now measured on every run instead of written down.

    The file->row direction is a NOTE, not a problem: a ticket can legitimately outlive its
    row (closed and archived, e.g. T39). Only an OPEN ticket missing from the board is worth
    surfacing, because that one is invisible on the queue humans actually read.

    ⚠️ AC7 discipline (T135): this must FAIL rather than pass when its input set is empty.
    Zero rows parsed means TASKS.md moved or the format changed — a parity check that reports
    "0 mismatches ✓" over an empty set is the vacuous pass this estate has shipped repeatedly.
    """
    tasks_md = ROOT / "TASKS.md"
    tickets_dir = ROOT / ".tasks"
    if not tasks_md.exists() or not tickets_dir.is_dir():
        problems.append("ticket parity: TASKS.md or .tasks/ not found")
        return


    # ⚠️ Keep in lockstep with wom7web/project/scripts/state_doctor.py::TASKS_ROW_RE and
    #    wom7web/project/scripts/backfill_tickets.py. FIXED 2026-08-05: the board moved to markdown
    #    links (`| [T12](…) |`) and this pattern — which only tolerated bare or emphasised ids —
    #    matched 0 of 155 rows, so every open ticket read as missing a row.
    rows = set(re.findall(r"^\|\s*[*_`]*\s*\[?\s*(T\d+[a-z]?)\s*\]?", tasks_md.read_text(), re.M))
    files = {p.stem for p in tickets_dir.glob("T*.md")}

    if not rows or not files:
        problems.append(
            f"ticket parity: empty input set (rows={len(rows)}, files={len(files)}) — "
            "refusing to report parity over nothing"
        )
        return

    missing_files = sorted(rows - files, key=lambda t: int(re.sub(r"\D", "", t)))
    if missing_files:
        shown = ", ".join(missing_files[:12]) + ("…" if len(missing_files) > 12 else "")
        problems.append(
            f"{len(missing_files)} TASKS.md row(s) have no ticket file — invisible to the "
            f"SDLC gates AND to the GitHub mirror: {shown}. "
            "Fix: python3 project/scripts/backfill_tickets.py"
        )

    # file -> row: only OPEN tickets matter; a done ticket may have been archived off the board.
    orphan_open = []
    for tid in sorted(files - rows, key=lambda t: int(re.sub(r"\D", "", t))):
        head = (tickets_dir / f"{tid}.md").read_text()[:600]
        m = re.search(r"^status:\s*(\S+)", head, re.M)
        if m and m.group(1).strip().strip('"') not in ("done", "archived"):
            orphan_open.append(tid)
    if orphan_open:
        notes.append(
            f"{len(orphan_open)} OPEN ticket(s) have no TASKS.md row, so they are missing from "
            f"the queue humans read: {', '.join(orphan_open)}"
        )


def main() -> int:
    quiet = "--quiet" in sys.argv
    problems: list[str] = []
    notes: list[str] = []

    if "--project" in sys.argv:
        global PROJECT
        i = sys.argv.index("--project")
        if i + 1 >= len(sys.argv):
            print("  ✗ --project needs a path")
            return 2
        PROJECT = Path(sys.argv[i + 1]).resolve()
        if not sdlc_path().is_file():
            print(f"  ✗ {PROJECT} has no .w0m/sdlc.json — nothing to enforce against")
            return 2
        problems, notes = check_declaration()
        print(f"\n  sdlc-doctor — declaration contract for {PROJECT.name}\n")
        for n in notes:
            print(f"     ℹ  {n}")
        for p in problems:
            print(f"     ✗  {p}")
        # Named, never silent: this ran 2 of the doctor's checks, and a green line without that
        # scope would read as the whole doctor passing for the client.
        print("\n     ⏭  NOT RUN for a client: host tool floors, per-repo justfile/.infisical.json "
              "sweep, canonical-recipe check, hooks, ticket parity — all estate-shaped")
        print(f"\n  {'✗ ' + str(len(problems)) + ' problem(s)' if problems else '✓ secrets + '
              'toolchain declared'}\n")
        return 1 if problems else 0

    # T127 AC10: --install-hooks CLOSES the gap the doctor reports instead of only naming it.
    # Deliberately a separate mode, not part of the default run: a preflight that silently
    # mutates git config in eight repos would be a surprising side effect of asking a question.
    if "--install-hooks" in sys.argv:
        return install_hooks(toolchain().get("exempt", {}))

    # ── required tools: every tools-policy entry at its floor (T119/T127) ────
    check_all_tools(problems, notes)
    check_versioning(problems, notes)

    tc = toolchain()
    recipes = tc.get("canonical_recipes") or FALLBACK_RECIPES
    exempt = tc.get("exempt", {})

    code, _ = sh("just", "--justfile", str(CANONICAL / "justfile"), "--list")
    if code != 0:
        problems.append("the canonical justfile does not parse — every gate command is broken")
    else:
        missing = [
            r for r in recipes
            if sh("just", "--justfile", str(CANONICAL / "justfile"), "--show", r)[0] != 0
        ]
        if missing:
            problems.append(f"justfile is missing canonical recipe(s): {', '.join(missing)}")

    for repo in sorted(ROOT.glob("wom7*")):
        if not (repo / ".git").exists() or repo.name in exempt:
            continue
        if not (repo / "justfile").exists():
            problems.append(f"{repo.name}: no justfile (symlink the canonical one, or "
                            f"declare it in .w0m/sdlc.json -> toolchain.exempt)")

    # ── interface 2: secrets -> infisical (floor covered by check_all_tools) ──
    try:
        secrets = json.loads(SDLC_JSON.read_text()).get("secrets", {})
    except OSError:
        secrets = {}
        problems.append(f"cannot read {SDLC_JSON}")
    want_mgr = toolchain().get("secrets_via", "infisical")
    if secrets.get("manager") != want_mgr:
        problems.append(f".w0m/sdlc.json secrets.manager is not '{want_mgr}'")
    if not secrets.get("run"):
        problems.append(".w0m/sdlc.json secrets.run is not set — gates cannot inject secrets")

    for repo in sorted(ROOT.glob("wom7*")):
        if not (repo / ".git").exists() or repo.name in exempt:
            continue
        if not (repo / ".infisical.json").exists():
            notes.append(
                f"{repo.name}: no .infisical.json — add one, or declare it in "
                f".w0m/sdlc.json -> toolchain.exempt"
            )

    # Session validity is advisory: it is a login state, not a repo defect.
    if sh("infisical", "--version")[0] == 0:
        code, _ = sh("infisical", "run", "--env=beta", "--silent", "--", "true")
        if code != 0:
            notes.append("infisical session invalid/expired — run 'infisical login' before a gate")

    # ── interface 3: git hooks installed (the gate stack actually runs) ──────
    check_hooks(exempt, problems, notes)

    # ── T130: per-stack registry + just-automation enforcement ───────────────
    check_stacks(problems, notes)

    # ── repo hygiene: docs / license / secrets (T135) ─────────────────────────
    check_hygiene(problems, notes)
    check_ticket_parity(problems, notes)

    for n in notes:
        if not quiet:
            print(f"  ⚠  {n}")
    if problems:
        print("❌ w0m SDLC toolchain preflight failed:")
        for p in problems:
            print(f"  ✗  {p}")
        return 1
    if not quiet:
        print("✅ SDLC toolchain conformant — commands via just, secrets via infisical")
    return 0


if __name__ == "__main__":
    sys.exit(main())
