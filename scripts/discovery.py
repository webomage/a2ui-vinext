#!/usr/bin/env python3
"""discovery.py — per-stack tech/tools drift + just-automation enforcement (T130).

The per-stack, tech-aware companion to `sdlc-doctor`. Reads the registry at
`project/stacks-policy.json` (referenced from `.w0m/sdlc.json -> stacks`, validated
against `project/stacks-policy.schema.json`) and answers two questions:

  DRIFT (AC3, default `just discovery`) — for each enabled, non-exempt stack, diff the
      DECLARED techs/tools against what the code actually uses:
        used-not-declared : a significant tech present in deps/config but absent from
                            the registry (the registry is stale/behind).
        declared-not-used : a declared tech whose `detect` signal has no code evidence
                            (a phantom / removed tech still in the registry).
      Advisory: exit 0.

  ENFORCEMENT (AC2, `--enforce`) — additionally:
        (a) every DECLARED command (role → recipe) must resolve to a real `just` recipe
            in the stack's justfile (`just --summary` membership). A command bound to a
            missing recipe is a broken registry → HARD FAIL, exit non-zero ALWAYS.
        (b) raw `pnpm`/`npx`/`tsc`/`deno`/`wrangler`/`mlx_*` invocations in tracked
            git hooks (`.husky/`) where a `just` recipe exists → advisory always,
            BLOCK under --enforce only when the registry sets `enforce_raw`.

Severity: registry-integrity errors (invalid registry, tool-without-recipe) are `✗`
problems that exit non-zero in any mode. Drift + raw-invocations are `⚠` notes: exit 0
by default, exit non-zero under --enforce (the gate). Honors the registry `exempt` set
and per-stack `enabled`. Reuses sdlc_doctor's report shape.

Usage:
    python3 scripts/discovery.py            # drift report, advisory (exit 0)
    python3 scripts/discovery.py --enforce  # gate: drift + raw-invocations block
    python3 scripts/discovery.py --json      # machine-readable summary (grounding)
    python3 scripts/discovery.py --quiet     # only problems
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parent.parent                   # …/@wom
CANONICAL = ROOT / "wom7web"                 # …/wom7web
SDLC_JSON = ROOT / ".w0m" / "sdlc.json"

# ── project scoping (T182) ────────────────────────────────────────────────────
# `--project <dir>` resolves the declaration AND the stacks registry relative to another project,
# so the profile's `stacks` key is enforceable at a client. The command→recipe contract is the
# estate's strongest gate and it is entirely project-relative — each stack names its own justfile
# and its own recipes — so unlike `preflight`/`sdlc-doctor` this one needs no reduced client mode:
# the same checks simply run against the client's own registry. A client that declares no `stacks`
# gets the same "cannot read" problem w0m would, which is the correct answer rather than a skip.
PROJECT: Path | None = None          # set in main(); None ⇒ w0m itself


def project_root() -> Path:
    return PROJECT if PROJECT is not None else ROOT


def sdlc_json() -> Path:
    return project_root() / ".w0m" / "sdlc.json"


def stack_base() -> Path:
    """Where a stack's `repo` / `justfile` paths resolve from.

    For w0m that is the workspace root (`repo: "wom7web"` ⇒ `@wom/wom7web`). For a scoped client
    it is the client's OWN root, so a single-repo client declares `repo: "."` and `justfile:
    "justfile"` and means its own. Leaving this at ROOT was the remaining reason `stacks` could
    not really be enforced at a client: the registry would validate and then every path in it
    would point into the estate.
    """
    return project_root() if PROJECT is not None else ROOT

# Framework / runtime / ORM / platform-CLI names that DEFINE a stack's IDENTITY. A dep in
# this set that a stack uses but does not declare is worth surfacing (used-not-declared).
# Universal dev tooling (typescript, tsx, vite, vitest, jest, esbuild, rollup, webpack,
# playwright) is deliberately EXCLUDED — it lives in most node repos, so flagging it per
# stack is pure noise. Such tooling may still be declared in a stack's `techs` where it is
# the point (e.g. `typescript`/`tsx` for the skills subsystem) — it just never triggers
# used-not-declared. Extend deliberately.
FRAMEWORKS = {
    "astro", "svelte", "@astrojs/svelte", "vue", "react", "next", "nuxt", "solid-js",
    "hono", "express", "fastify", "koa",
    "tailwindcss",
    "drizzle-orm", "prisma", "@supabase/supabase-js", "postgres",
    "wrangler", "ai", "mlx-rs", "mlx-sys",
}

# Raw tool tokens that should run through `just`, and the regex that spots a real
# invocation (a subcommand/flag follows, not a bare word in prose).
RAW_TOOLS = ["pnpm", "npx", "tsc", "deno", "wrangler"]
# `mlx_[\w.]+`, not `mlx_\w+`: mlx ships DOTTED console scripts, and `mlx_lm.generate --model …`
# is the documented entry point. `mlx_\w+` stopped at `mlx_lm` and then demanded whitespace, which
# the `.` is not — so the single most common real invocation could never match. Caught 2026-07-31
# by a test that finally exercised each token instead of relying on one live example.
RAW_RE = re.compile(r"(?<![\w./-])(" + "|".join(RAW_TOOLS) + r"|mlx_[\w.]+)\b[ \t]+[\w@./-]")

# Vendored / VCS trees never scanned for the import surface.
SKIP_DIRS = {"node_modules", ".git", "dist", "build", ".astro", ".svelte-kit", "target", ".venv"}


def sh(*args: str) -> tuple[int, str]:
    """Run a command with LIST args (never shell=True) and return (code, output)."""
    try:
        r = subprocess.run(args, capture_output=True, text=True)
    except (OSError, ValueError) as e:  # binary missing from PATH, bad args
        return 127, str(e)
    return r.returncode, (r.stdout or r.stderr).strip()


def read_text(path: Path) -> str | None:
    """Read a text file, or None if missing/unreadable/not UTF-8.

    `UnicodeDecodeError` is a **ValueError, not an OSError** — catching only OSError would
    crash the whole gate on a binary or non-UTF-8 file sitting in a scanned directory
    (a `.husky/` hook, a source tree, a manifest). Every file read here goes through this.
    """
    try:
        return path.read_text()
    except (OSError, UnicodeDecodeError):
        return None


def _arg_value(flag: str) -> str | None:
    """Read `--flag value` from argv (used by --policy for fixture-testing)."""
    if flag in sys.argv:
        i = sys.argv.index(flag)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return None


def load_registry(problems: list[str]) -> dict:
    """Load + schema-validate the registry. A malformed registry is a hard problem.
    `--policy <path>` overrides the registry file (schema is taken as its sibling) — used
    to prove the checks against fixtures without touching the live registry."""
    override = _arg_value("--policy")
    sdlc = sdlc_json()
    raw_sdlc = read_text(sdlc)
    if raw_sdlc is None:
        problems.append(f"cannot read {sdlc}")
        return {}
    try:
        stacks_ref = json.loads(raw_sdlc).get("stacks", {})
    except json.JSONDecodeError as e:
        problems.append(f"{sdlc} is not valid JSON: {e}")
        return {}
    if not stacks_ref and PROJECT is not None:
        problems.append(f"{sdlc} declares no `stacks` — there is no registry to enforce, which is "
                        "a finding, not a clean run")
        return {}
    if override:
        policy_path = Path(override).resolve()
        schema_path = policy_path.parent / "stacks-policy.schema.json"
    else:
        policy_path = project_root() / stacks_ref.get("policy", "project/policies/stacks-policy.json")
        schema_path = project_root() / stacks_ref.get("schema",
                                                      "project/policies/stacks-policy.schema.json")
    raw_reg = read_text(policy_path)
    if raw_reg is None:
        problems.append(f"cannot read stacks registry {policy_path}")
        return {}
    try:
        reg = json.loads(raw_reg)
    except json.JSONDecodeError as e:
        problems.append(f"stacks registry is not valid JSON: {e}")
        return {}
    if not isinstance(reg, dict):
        problems.append("stacks registry is not a JSON object")
        return {}
    try:
        import jsonschema  # noqa: I001

        schema = json.loads(read_text(schema_path) or "")
        try:
            jsonschema.validate(reg, schema)
        except jsonschema.ValidationError as e:
            loc = "/".join(str(p) for p in e.absolute_path) or "<root>"
            problems.append(f"stacks registry fails schema at {loc}: {e.message}")
    except (ImportError, OSError, json.JSONDecodeError):
        pass  # jsonschema/schema unavailable — the structural check below still runs
    check_structure(reg, problems)
    return reg


# Fields main() indexes directly. Validated ALWAYS (not only when jsonschema is importable)
# so a malformed registry reports a clean `✗` instead of a KeyError traceback.
REQUIRED_STACK_FIELDS = ("repo", "path", "runtime", "justfile", "enabled")

# T135: mirrors stacks-policy.schema.json -> definitions. Duplicated on purpose — schema
# validation is skipped entirely when `jsonschema` is not importable (see load_registry's
# `except ImportError: pass`), and a rule that silently stops applying is the exact vacuous-gate
# failure mode AC7 exists to prevent. These checks always run.
COMMAND_ROLES = frozenset({
    "check", "typecheck", "lint", "test", "test-e2e", "build",
    "dev", "deploy", "fmt", "scan", "serve",
    "fmt-check", "docs-check", "license-check", "secrets-check",
    # T135 AC6 — `dep-licenses-check` is a SEPARATE role from `license-check` on purpose:
    # that one audits the repos' OWN manifests and vendored trees, this one audits the
    # TRANSITIVE dependency graph via `pnpm licenses list --prod`. They fail for unrelated
    # reasons, so merging them would hide which half went red.
    "dep-licenses-check",
    # T145/T146 — handoff & queue roles. `state-check` is a gate; `state-save` and `tasks` are a
    # writer and a query, declared so the registry knows their recipes exist. This vocabulary is
    # CLOSED on purpose: adding a role here and to stacks-policy.schema.json is the deliberate step
    # that stops ad-hoc recipe names accumulating outside the contract.
    "state-check", "state-save", "tasks",
    # T174 — `state-rotate` completes that trio: check verifies, save regenerates the managed block,
    # rotate MOVES superseded history into project/state-archive/. Also `manual` by policy for the
    # same reason as `state-save` (it mutates a tracked file), with `state-check`'s size budget as
    # the gate that makes it run. ⚠️ The closed vocabulary means this list and
    # stacks-policy.schema.json's enum must BOTH be updated — two copies by design, and the gate
    # failed loudly on the second one, which is the deliberate step working as intended.
    "state-rotate", "sdlc-trace",
    # T131 — the same verify/write split one level down, over the canonical skill corpus rather
    # than the handoff file: `version-check` is a gate, `version-stamp` writes tracked SKILL.md
    # files and is therefore `manual` by policy, never a hook.
    "version-check", "version-stamp",
    # T149 AC4 — the COMPOSED status surface over the other checks (queue/stacks/skills/state/
    # toolchain). `manual` by DESIGN rather than by deferral: its children already run at
    # pre-commit/pre-push, so gating on the composite would run each of them twice and roughly
    # double push time for no information the individual gates did not already give.
    "toolset-status",
    # T149 AC3 + T150 AC3b — hook-layer conformance: declared gate phases must actually be wired,
    # and exactly ONE sanctioned forge call site may exist across the hook layer.
    "hooks-check",
    # T149 / D6 — type-error ratchet for apps not yet gated at zero. The count may fall, never rise.
    "typecheck-ratchet",
    # T278 — downward-only .svelte type-error ratchet across all 5 wom7web apps via svelte-check.
    "svelte-typecheck-ratchet",
    # T154 — HOST exposure, not stack build: `mcp-exposure` inventories every listening socket and
    # asks whether it is usable WITHOUT credentials; `mcp-ratchet` gates that against the declared
    # baseline (may shrink, never grow); `mcp-ratchet-test` is its fixture-only regression proof.
    # All three `manual`, and `mcp-ratchet` is the first role here that is manual because an AC
    # REQUIRES it rather than because it is slow: T154 AC6 rules out a pre-push gate, since these
    # facts change when a desktop app launches, not when code is pushed. Cadence is `just audit`.
    "mcp-exposure", "mcp-ratchet", "mcp-ratchet-test",
    # T151 AC2/AC4 — the code-knowledge-graph pair, and the same writer/reporter split as
    # state-save/state-check one level out: `graph-global` FOLDS every repo's graph into the
    # united graph, `graph-health` only REPORTS (coverage, staleness, hook state, union sync).
    # Both `manual` by design: a full re-extract is minutes per repo, and graphify's own
    # post-commit hook already keeps each repo's individual graph fresh asynchronously.
    "graph-global", "graph-health",
    # T151: doc/semantic extraction via a LOCAL model. `graph-docs` is a full rebuild (minutes);
    # `graph-docs-inc` reuses graphify's cache — UNVERIFIED, see the recipe comment. Both `manual`:
    # an LLM pass measured at ~47s per document must never sit in a hook.
    "graph-docs", "graph-docs-inc",
})
GATE_PHASES = frozenset({"pre-commit", "pre-push", "manual"})
MIN_REASON_LEN = 25


def _gate_phase(spec: object) -> tuple[str | None, str | None]:
    """Normalise a `gates` value to (phase, reason). Accepts the shorthand string or the
    long object form. Returns (None, None) when the shape is unusable."""
    if isinstance(spec, str):
        return spec, None
    if isinstance(spec, dict):
        phase = spec.get("phase")
        return (phase if isinstance(phase, str) else None), spec.get("reason")
    return None, None


def check_exemptions(reg: dict, problems: list[str]) -> None:
    """T135 task 1.3: every exemption carries a substantive reason.

    An exemption is a decision. Recorded as a bare name it cannot be re-evaluated, so it
    outlives the condition that justified it — which is exactly how the stale
    wom7ext/wom7sec standing condition survived. The reason must also say something the key
    does not, so a prose-only repo mapped to itself fails rather than technically satisfying the rule.
    """
    exempt = reg.get("exempt")
    if exempt is None:
        return
    if not isinstance(exempt, dict):
        # A bare list of names is the shape this rule exists to reject.
        problems.append(
            "`exempt` must be an object mapping each exempt stack/repo to a reason, "
            f"not {type(exempt).__name__} — a bare name records no decision"
        )
        return
    for key, reason in exempt.items():
        if not isinstance(reason, str) or not reason.strip():
            problems.append(f"exempt `{key}`: missing a reason — an exemption without a cause cannot be re-evaluated")
        elif reason.strip().strip(".").lower() == key.strip().lower():
            problems.append(f"exempt `{key}`: the reason merely restates the key — say WHY it is exempt")
        elif len(reason.strip()) < MIN_REASON_LEN:
            problems.append(
                f"exempt `{key}`: reason is {len(reason.strip())} chars, needs >= {MIN_REASON_LEN} — "
                "record the condition a successor would re-check"
            )


def check_gates(sid: str, stack: dict, problems: list[str]) -> None:
    """T135 task 1.2 (AC4): every declared command role carries an explicit phase.

    No implicit default, in either direction: an unphased role is a schema failure (nobody can
    tell whether it is enforced), and a phase for an undeclared role is an orphan that reads as
    coverage while gating nothing. `manual` is a deferral and must carry a cause (AC8).
    """
    commands = stack.get("commands")
    gates = stack.get("gates")
    if not isinstance(commands, dict):
        return  # absence of `commands` is reported by the required-field check
    if not isinstance(gates, dict):
        problems.append(
            f"stack `{sid}`: missing required field `gates` — "
            f"{len(commands)} declared command role(s) have no phase, so none is mechanically enforced"
        )
        return

    for role in commands:
        if role not in gates:
            problems.append(
                f"stack `{sid}`: command role `{role}` has no phase in `gates` — "
                "declare pre-commit / pre-push / manual explicitly (there is no default)"
            )
    for role, spec in gates.items():
        if role not in commands:
            problems.append(
                f"stack `{sid}`: `gates` phases role `{role}`, which is not in `commands` — "
                "an orphan phase gates nothing"
            )
        phase, reason = _gate_phase(spec)
        if phase not in GATE_PHASES:
            problems.append(
                f"stack `{sid}`: role `{role}` has invalid phase {phase!r} "
                f"(expected one of {', '.join(sorted(GATE_PHASES))})"
            )
            continue
        if phase == "manual":
            if not isinstance(reason, str) or len(reason.strip()) < MIN_REASON_LEN:
                problems.append(
                    f"stack `{sid}`: role `{role}` is deferred to `manual` without a reason — "
                    "AC8: record the cause, and a re-measure trigger, or gate it"
                )


def check_structure(reg: dict, problems: list[str]) -> None:
    """Minimum structural contract, independent of jsonschema availability."""
    check_exemptions(reg, problems)
    stacks = reg.get("stacks")
    if not isinstance(stacks, dict):
        problems.append("stacks registry has no `stacks` object")
        return
    for sid, stack in stacks.items():
        if not isinstance(stack, dict):
            problems.append(f"stack `{sid}`: entry is not an object")
            continue
        for field in REQUIRED_STACK_FIELDS:
            if field not in stack:
                problems.append(f"stack `{sid}`: missing required field `{field}`")
        for role in stack.get("commands") or {}:
            if role not in COMMAND_ROLES:
                problems.append(
                    f"stack `{sid}`: unknown command role `{role}` "
                    f"(expected one of {', '.join(sorted(COMMAND_ROLES))})"
                )
        check_gates(sid, stack, problems)
        for tech in stack.get("techs") or []:
            if not isinstance(tech, dict) or "name" not in tech or "detect" not in tech:
                problems.append(f"stack `{sid}`: a `techs` entry lacks `name`/`detect`")
                break


def enabled_mcp() -> list[str]:
    """The MCP servers declared enabled for the project (.w0m/sdlc.json -> mcp.servers).
    Declarative surface only — live connection is a harness fact, not verified here."""
    try:
        servers = json.loads(read_text(SDLC_JSON) or "{}").get("mcp", {}).get("servers", {})
    except json.JSONDecodeError:
        return []
    return sorted(k for k, v in servers.items() if isinstance(v, dict) and v.get("enabled"))


def just_recipes(justfile: Path) -> set[str]:
    """The recipe names exposed by a justfile (`just --summary`)."""
    code, out = sh("just", "--justfile", str(justfile), "--summary")
    return set(out.split()) if code == 0 else set()


# ── code-side detectors ────────────────────────────────────────────────────────
def node_deps(repo: Path) -> set[str]:
    try:
        p = json.loads(read_text(repo / "package.json") or "{}")
        return set({**p.get("dependencies", {}), **p.get("devDependencies", {})})
    except (json.JSONDecodeError, AttributeError, TypeError):
        return set()


def load_jsonc(f: Path) -> dict:
    """Parse JSON or JSONC (line comments + trailing commas), as used by deno.jsonc /
    wrangler.jsonc. Strict json.loads rejects those, which would silently empty a dep set."""
    text = read_text(f) or ""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)      # block comments
    # line comments — including trailing ones; `(?<!:)` keeps `https://` intact, and the
    # even-quote guard avoids cutting a `//` that sits inside a string value.
    text = re.sub(r'(?<!:)//(?=(?:[^"]*"[^"]*")*[^"]*$).*$', "", text, flags=re.MULTILINE)
    text = re.sub(r",(\s*[}\]])", r"\1", text)                  # trailing commas
    return json.loads(text)


def deno_deps(stack_root: Path) -> set[str]:
    for name in ("deno.json", "deno.jsonc"):
        f = stack_root / name
        if f.exists():
            try:
                imports = load_jsonc(f).get("imports", {})
                # strip trailing '/' subpath keys ("drizzle-orm/" -> "drizzle-orm")
                return {k.rstrip("/") for k in imports}
            except (OSError, json.JSONDecodeError):
                return set()
    return set()


def rust_deps(repo: Path) -> set[str]:
    try:
        import tomllib

        data = tomllib.loads(read_text(repo / "Cargo.toml") or "")
        return set(data.get("dependencies", {})) | set(data.get("dev-dependencies", {}))
    except Exception:  # noqa: BLE001
        # missing tomllib (pre-3.11) or a TOML parse error → cheap line scan of [dependencies]
        names, in_deps = set(), False
        for line in (read_text(repo / "Cargo.toml") or "").splitlines():
            s = line.strip()
            if s.startswith("["):
                in_deps = s in ("[dependencies]", "[dev-dependencies]")
            elif in_deps and "=" in s and not s.startswith("#"):
                names.add(s.split("=")[0].strip())
        return names


def python_deps(stack_root: Path, repo: Path) -> set[str]:
    """Best-effort python deps: pyproject [project].dependencies / requirements*.txt.
    Names only (strip version specifiers/extras)."""
    names: set[str] = set()
    for base in dict.fromkeys((stack_root, repo)):
        pyproject = base / "pyproject.toml"
        if pyproject.exists():
            try:
                import tomllib

                data = tomllib.loads(read_text(pyproject) or "")
                for spec in data.get("project", {}).get("dependencies", []) or []:
                    names.add(re.split(r"[<>=!~\[; ]", spec, maxsplit=1)[0].strip())
            except Exception:  # noqa: BLE001
                pass
        for req in base.glob("requirements*.txt"):
            for line in (read_text(req) or "").splitlines():
                s = line.strip()
                if s and not s.startswith(("#", "-")):
                    names.add(re.split(r"[<>=!~\[; ]", s, maxsplit=1)[0].strip())
    return {n for n in names if n}


def dep_set(stack: dict) -> set[str]:
    """The stack's dependency names. Manifests are read from the stack path FIRST, then the
    repo root — a monorepo hoists shared deps to the root, while a nested stack may carry its
    own manifest; the union avoids both false-empty and cross-stack blindness."""
    repo = stack_base() / stack["repo"]
    stack_root = repo / stack["path"] if stack["path"] != "." else repo
    runtime = stack["runtime"]
    if runtime == "deno":
        return deno_deps(stack_root) | deno_deps(repo)
    if runtime == "rust":
        return rust_deps(stack_root) | rust_deps(repo)
    if runtime == "python":
        return python_deps(stack_root, repo)
    return node_deps(stack_root) | node_deps(repo)  # node


def detect_present(stack: dict, detect: str, deps: set[str] | None = None) -> bool:
    """Is a `<kind>:<value>` detect signal present in the stack's code? `deps` may be the
    stack's precomputed dep set (avoids re-reading package.json per tech)."""
    kind, _, value = detect.partition(":")
    repo = stack_base() / stack["repo"]
    stack_root = repo / stack["path"] if stack["path"] != "." else repo
    if kind == "dep":
        return value in (deps if deps is not None else dep_set(stack))
    if kind == "config":
        return (stack_root / value).exists() or (repo / value).exists()
    if kind == "import":
        # light scan of the stack surface for an import of `value`
        pat = re.compile(r"""(from|import)\s+['"]""" + re.escape(value))
        for ext in ("*.ts", "*.tsx", "*.js", "*.svelte", "*.astro"):
            scanned = 0
            for f in stack_root.rglob(ext):
                # skip vendored/VCS trees — for a `path: "."` stack these dwarf real source
                # and would exhaust the scan budget before reaching it
                if any(part in SKIP_DIRS for part in f.parts):
                    continue
                if pat.search(read_text(f) or ""):
                    return True
                scanned += 1
                if scanned >= 400:
                    break
        return False
    return False


# ── enforcement ─────────────────────────────────────────────────────────────────
def scan_raw_invocations(recipes_by_justfile: dict[str, set[str]]) -> list[str]:
    """Flag raw tool calls in tracked git hooks (each repo's `.husky/`), where a covering
    `just` recipe exists. Justfiles are EXCLUDED — they are the sanctioned wrapper where
    tools are legitimately invoked. Heuristic: comments and echo/quoted strings are skipped."""
    findings: list[str] = []
    all_recipes = set().union(*recipes_by_justfile.values()) if recipes_by_justfile else set()
    targets: list[Path] = []
    for repo in sorted(ROOT.glob("wom7*")):
        if not (repo / ".git").exists():
            continue
        husky = repo / ".husky"
        if husky.is_dir():
            targets += [p for p in husky.iterdir() if p.is_file() and p.name != "_"]
    for f in targets:
        content = read_text(f)
        if content is None:      # binary or unreadable hook — not a text scan target
            continue
        for n, line in enumerate(content.splitlines(), 1):
            s = line.strip()
            # skip comments and echo/print lines (the token is advice text, not a call)
            if not s or s.startswith("#") or re.match(r"@?(echo|printf|print)\b", s):
                continue
            m = RAW_RE.search(s)
            if not m or not all_recipes:
                continue
            # skip a match that sits inside a quoted string (advice/message text)
            before = s[: m.start()]
            if before.count('"') % 2 or before.count("'") % 2:
                continue
            findings.append(f"{f.relative_to(ROOT)}:{n} raw `{m.group(1)}` — route via a `just` recipe")
    return findings


# ── main ──────────────────────────────────────────────────────────────────────
def main() -> int:
    enforce = "--enforce" in sys.argv or "--check" in sys.argv
    quiet = "--quiet" in sys.argv
    as_json = "--json" in sys.argv

    proj = _arg_value("--project")
    if proj:
        global PROJECT
        PROJECT = Path(proj).resolve()
        if not sdlc_json().is_file():
            print(f"  ✗ {PROJECT} has no .w0m/sdlc.json — nothing to enforce against")
            return 2

    problems: list[str] = []   # ✗ — exit non-zero in ANY mode (registry integrity)
    drift: list[str] = []      # ⚠ — advisory; blocks only under --enforce
    raw: list[str] = []        # ⚠ — advisory; blocks only under --enforce

    reg = load_registry(problems)
    stacks = reg.get("stacks", {})
    exempt = set(reg.get("exempt", {}))
    # raw-invocation blocking is OPT-IN (registry `enforce_raw`, default false): the scan is a
    # heuristic that can false-positive, and pre-existing raw-tool debt must not wall off the
    # gate. It is always REPORTED (advisory); it only blocks when enforce_raw AND --enforce.
    enforce_raw = bool(reg.get("enforce_raw", False))
    recipes_by_justfile: dict[str, set[str]] = {}
    summary: dict[str, dict] = {}

    # A structurally broken registry is reported, not iterated — indexing it would raise
    # KeyError and lose the diagnostic.
    if problems:
        stacks = {}

    for sid, stack in sorted(stacks.items()):
        if sid in exempt or stack.get("repo") in exempt:
            continue
        jf = stack["justfile"]
        if jf not in recipes_by_justfile:
            recipes_by_justfile[jf] = just_recipes(stack_base() / jf)
        recipes = recipes_by_justfile[jf]

        # (a) declared command role -> real recipe (HARD FAIL, any mode)
        for role, recipe in stack.get("commands", {}).items():
            if stack.get("enabled") and recipe not in recipes:
                problems.append(
                    f"stack `{sid}`: command `{role}` binds recipe `{recipe}` "
                    f"which does not exist in {jf}"
                )

        if not stack.get("enabled"):
            continue

        # compute the stack's dep set once; detect_present reuses it for `dep:` checks
        deps = dep_set(stack)
        declared_names = {t["name"] for t in stack.get("techs", [])}
        # drift: declared-not-used / used-not-declared (defining FRAMEWORKS only)
        dnu = [t["name"] for t in stack.get("techs", []) if not detect_present(stack, t["detect"], deps)]
        und = sorted((deps & FRAMEWORKS) - declared_names)
        for name in dnu:
            drift.append(f"stack `{sid}`: declared-not-used `{name}` (no code evidence)")
        for name in und:
            drift.append(f"stack `{sid}`: used-not-declared `{name}` (in deps, absent from registry)")
        # T135 task 2.3: echo the command contract, not just the drift. `--json` is the
        # grounding surface, and a role that is declared but invisible here cannot be
        # confirmed as wired — which is how a "declared" gate gets assumed rather than checked.
        # `gates` is normalised to role -> phase so a consumer need not handle both forms.
        summary[sid] = {
            "declared_not_used": dnu,
            "used_not_declared": und,
            "commands": stack.get("commands", {}),
            "gates": {
                role: _gate_phase(spec)[0]
                for role, spec in (stack.get("gates") or {}).items()
            },
        }

    # Scanned in EVERY mode, blocking in one. Both this file's docstring ("advisory always") and
    # the comment above say the raw scan is always reported — but until 2026-07-31 it ran only
    # under `--enforce`, so plain `just discovery` could never surface a raw invocation no matter
    # what was in the hooks. Invisible while the hook layer happened to be clean, which is exactly
    # how a rule that cannot fire survives: nothing distinguishes it from a rule with nothing to say.
    raw = scan_raw_invocations(recipes_by_justfile)

    raw_blocks = enforce and enforce_raw and bool(raw)
    drift_blocks = enforce and bool(drift)

    if as_json:
        print(json.dumps({
            "problems": problems, "drift": drift, "raw_invocations": raw,
            "stacks": summary, "mcp_enabled": enabled_mcp(),
            "enforced": enforce, "enforce_raw": enforce_raw,
        }, indent=2))
        return 1 if problems or drift_blocks or raw_blocks else 0

    if not quiet:
        for d in drift:
            print(f" [WARN] {d}")
        for r in raw:
            print(f" [WARN] {r}")
    if problems:
        print("❌ stacks registry / just-automation enforcement failed:")
        for p in problems:
            print(f"  ✗  {p}")
        return 1
    if drift_blocks or raw_blocks:
        bits = []
        if drift_blocks:
            bits.append(f"{len(drift)} drift")
        if raw_blocks:
            bits.append(f"{len(raw)} raw-invocation")
        print(f"❌ stack enforcement blocks the gate ({', '.join(bits)}) — "
              f"reconcile project/stacks-policy.json or route the tool through `just`")
        return 1
    if not quiet:
        n = len(summary)
        adv = []
        if drift:
            adv.append(f"{len(drift)} drift")
        if raw:
            adv.append(f"{len(raw)} raw-invocation")
        tail = f" ({', '.join(adv)} advisory)" if adv else ""
        print(f"✅ stacks registry conformant — {n} stacks, every declared command → a real `just` recipe{tail}")
        # T235 AC3 — surface the RUNTIME split. `runtime` is a required stack field but was never
        # reported, so "which stacks are Rust?" could only be answered by opening every entry. That
        # is not hypothetical: T235 was filed claiming Rust was undeclared, because the stack NAMES
        # (cf, edge, ext, mlx, …) carry no runtime and nobody opened `mlx` to find `runtime: "rust"`.
        by_rt: dict[str, list[str]] = {}
        for st_name, st in sorted(stacks.items()):
            if st_name.startswith("_"):
                continue
            by_rt.setdefault(st.get("runtime", "?"), []).append(st_name)
        print("   runtimes: " + " · ".join(
            f"{rt} ({len(names)}): {', '.join(names)}" for rt, names in sorted(by_rt.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
