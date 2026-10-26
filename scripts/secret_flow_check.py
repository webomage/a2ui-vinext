#!/usr/bin/env python3
"""secret-flow-check — T244 AC3/AC4. Every secret a sync recipe pushes must be READ somewhere, and every credential in the vault must be
what it claims to be.

    just secret-flow-check                 # static half: what is pushed, where is it read, who else uses the source key
    just secret-flow-check --vault         # + the vault half (run under infisical): source key present? empty? live?
    just secret-flow-check --enforce       # exit 1 on any finding not in project/secret-flow-baseline.json (pre-push runs this, static only)
    just secret-flow-check --test          # red probes on the ticket's own three cases

Two halves that fail differently (ticket wording): an UNREAD secret is residue (pushed to production, no code reads it), and an
UNVERIFIABLE credential is a lie (the vault says it is a token; the provider says otherwise). Findings, each its own state:

  UNREAD           a pushed target name that nothing in that worker's source reads (a `NAME: string` declaration is not a read).
  PUSHER-ONLY      a vault key whose ONLY consumer is the recipe that pushes it (`CF_RUNTIME_API_TOKEN`: T244's second real shape).
  ALIASED          the vault key and the worker secret have different names (`CF_RUNTIME_API_TOKEN` -> `CLOUDFLARE_API_TOKEN`): informational,
                   reported because a rename on push is how "which credential is this?" gets lost.
  ABSENT / EMPTY   the vault has no such key, or holds an empty string (`TELEGRAM_BOT_TOKEN` was absent: syncing would push "" and destroy
                   the working worker token, T231). Reported only with --vault.
  DEAD             a provider liveness probe answered "invalid" (--vault with a probe for that credential).
  NOT MEASURABLE   the check could not be made (no vault injected, no probe exists for that credential, unknown worker). NEVER a pass and
                   never printed as a violation (T242): most credentials have no cheap liveness call, so "unverified" is the honest state.

Static analysis limits, stated: readers are found by NAME in the worker's source (env.X, process.env.X, import.meta.env.X, Deno.env.get,
getCfEnv("X"), destructuring); a secret read through a computed name is invisible and shows as UNREAD. The baseline file records each
accepted finding WITH A REASON, and the gate fails on a baseline entry that is no longer a finding (a list of things that used to be true).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ESTATE = Path(__file__).resolve().parents[1]
JUSTFILE = ESTATE / "w0m-api" / "justfile"
JUSTFILES = (ESTATE / "justfile", ESTATE / "just" / "estate.just", ESTATE / "w0m-api" / "justfile")
BASELINE = ESTATE / "w0m-web" / "project" / "secret-flow-baseline.json"

# worker (as named in `--name`) -> the source trees that can read its secrets. `webomage` is the sync-cf-secrets default (apps/web).
WORKER_SOURCES: dict[str, list[str]] = {
    "wom7func": ["w0m-cf/src"],  # pinned worker
    "wom7api": ["w0m-api/src"],  # pinned worker
    "webomage": ["w0m-web/apps/web/src", "w0m-web/packages/lib/src"],
    "webomage-cp": ["w0m-web/apps/cp/src", "w0m-web/packages/lib/src"],
    "webomage-join": ["w0m-web/apps/join/src", "w0m-web/apps/cp/src", "w0m-web/packages/lib/src"],
    "webomage-job": ["w0m-web/apps/job/src", "w0m-web/apps/cp/src", "w0m-web/packages/lib/src"],
    "webomage-demo": ["w0m-web/apps/demo/src", "w0m-web/packages/lib/src"],
}

ECHO_PUSH = re.compile(
    r'echo\s+"\$\{?(?P<src>[A-Z][A-Z0-9_]*)\}?"\s*\|\s*(?:pnpm exec )?wrangler secret put\s+(?P<dst>[A-Z][A-Z0-9_]*)\s+--name\s+(?P<worker>\S+)')
LOOP_PUSH = re.compile(r'for\s+(?P<var>\w+)\s+in\s+(?P<names>[A-Z][A-Z0-9_ ]*?);\s*do\b(?P<body>.*?)\bdone', re.S)
LOOP_PUT = re.compile(r'wrangler secret put\s+\$\{?(?P<var>\w+)\}?\s+--name\s+(?P<worker>\S+)')
RECIPE_HEAD = re.compile(r'^(?P<name>[a-z][a-z0-9-]*)\b[^\n:]*:(?!=)', re.M)
DEFAULT_PROJECT = re.compile(r'^sync-cf-secrets\s+project="(?P<p>[^"]+)"', re.M)


@dataclass(frozen=True)
class Push:
    recipe: str
    src: str  # vault key
    dst: str  # worker secret name
    worker: str


def _recipe_at(text: str, pos: int) -> str:
    name = "?"
    for m in RECIPE_HEAD.finditer(text, 0, pos):
        name = m.group("name")
    return name


def parse_pushes(justfile_text: str) -> list[Push]:
    """Every `wrangler secret put` in a sync recipe: the echo shape and the `for n in A B C` loop shape."""
    found = DEFAULT_PROJECT.search(justfile_text)
    default = found.group("p") if found else "webomage"
    out: list[Push] = []
    for m in ECHO_PUSH.finditer(justfile_text):
        worker = m.group("worker").strip("'\"")
        if worker.startswith("{{"):
            worker = default
        out.append(Push(_recipe_at(justfile_text, m.start()), m.group("src"), m.group("dst"), worker.rstrip("'\\&;")))
    for m in LOOP_PUSH.finditer(justfile_text):
        put = LOOP_PUT.search(m.group("body"))
        if not put or put.group("var") != m.group("var"):
            continue
        for n in m.group("names").split():
            out.append(Push(_recipe_at(justfile_text, m.start()), n, n, put.group("worker").rstrip("'\\&;")))
    return out


# ── readers ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
def _is_read_line(line: str, name: str) -> bool:
    if not re.search(rf"\b{re.escape(name)}\b", line):
        return False
    s = line.strip()
    if s.startswith(("//", "*", "/*", "#")):
        return False
    if re.match(rf"^{re.escape(name)}\??\s*:\s*[\w\[\]|<> '\"]+[;,]?\s*(//.*)?$", s):  # `NAME: string;` / `NAME?: string`
        return False
    return True


# The gate's own files name credentials as DATA (a liveness-probe table, fixtures, the baseline), so they can never be evidence that
# a secret is USED. Found the hard way: the moment this script was tracked it counted as the only "consumer" of CF_RUNTIME_API_TOKEN
# and the very case the ticket names stopped being reported (the audit tool committed the defect it hunts).
SELF_FILES = ("scripts/secret_flow_check.py", "project/secret-flow-baseline.json")


def readers_in(files: dict[str, str], name: str) -> list[str]:
    """Files (path -> text) with a line that READS `name`. `.d.ts` declarations and tests do not count."""
    hits = []
    for path, text in files.items():
        base = path.rsplit("/", 1)[-1]
        if path.endswith(SELF_FILES):
            continue
        if (path.endswith(".d.ts") or re.search(r"\.(test|spec)\.[jt]sx?$", path) or "/__tests__/" in path or "/tests/" in path
                or base.startswith("test_") or base.endswith("_test.py")):
            continue
        if any(_is_read_line(line, name) for line in text.splitlines()):
            hits.append(path)
    return sorted(hits)


def load_tree(rel_dirs: list[str], root: Path = ESTATE) -> dict[str, str]:
    files: dict[str, str] = {}
    for rel in rel_dirs:
        base = root / rel
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            if p.suffix in (".ts", ".tsx", ".js", ".mjs", ".astro", ".svelte") and "node_modules" not in p.parts and p.is_file():
                try:
                    files[str(p.relative_to(root))] = p.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    pass
    return files


def estate_consumers(name: str, root: Path = ESTATE) -> list[str]:
    """Files anywhere in the estate that use `name` other than recipes, docs and records (those describe or push it, they do not consume it)."""
    hits: list[str] = []
    for repo in ("w0m-web", "w0m-api", "w0m-cf", "w0m-ext", "w0m-sec", "w0m-skills"):
        candidates: list[str] = []
        d = root / repo
        if not (d / ".git").exists():
            continue
        git_env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        git_env["LC_ALL"] = "C"
        out = subprocess.run(["git", "--no-pager", "grep", "-lw", "-e", name, "--", ".", ":!*.md", ":!*.json", ":!*.jsonc", ":!*.html",
                              ":!justfile", ":!*.lock", ":!graphify-out", ":!.tasks"],
                             cwd=d, capture_output=True, text=True, env=git_env).stdout
        candidates = [x for x in out.splitlines() if x]
        # A MENTION is not a use: comments, `.d.ts` declarations (generated from the secret list itself) and test fixtures are filtered
        # by the same rule the worker-side reader uses. The first version counted them, so `CF_RUNTIME_API_TOKEN` (a comment, a fixture and a
        # generated declaration) looked consumed and PUSHER-ONLY never fired on the very case the ticket names.
        texts = {}
        for rel in candidates:
            try:
                texts[rel] = (d / rel).read_text(encoding="utf-8", errors="ignore")
            except OSError:
                pass
        hits += [f"{repo}/{x}" for x in readers_in(texts, name)]
    return hits


# ── verdicts ──────────────────────────────────────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Finding:
    state: str  # UNREAD | PUSHER-ONLY | ALIASED | ABSENT | EMPTY | DEAD | NOT MEASURABLE
    key: str  # stable id used by the baseline: "<worker>:<dst>" or "vault:<src>"
    detail: str


def evaluate(pushes: list[Push], trees: dict[str, dict[str, str]], consumers, vault: dict[str, int] | None,
             probes: dict[str, str] | None = None) -> list[Finding]:
    """Pure. `trees[worker]` = that worker's source; `consumers(src)` = estate files using the vault key; `vault` = key -> value length
    (None = no vault injected); `probes` = key -> "live" | "dead" | "error" for the credentials that have a liveness probe."""
    out: list[Finding] = []
    seen_src: set[str] = set()
    for p in pushes:
        if p.worker not in WORKER_SOURCES:
            out.append(Finding("NOT MEASURABLE", f"{p.worker}:{p.dst}", f"worker `{p.worker}` has no source mapping in WORKER_SOURCES (recipe {p.recipe})"))
            continue
        if not readers_in(trees.get(p.worker, {}), p.dst):
            out.append(Finding("UNREAD", f"{p.worker}:{p.dst}", f"`{p.recipe}` pushes it (from vault key {p.src}) and nothing in {', '.join(WORKER_SOURCES[p.worker])} reads it"))
        if p.src != p.dst:
            out.append(Finding("ALIASED", f"{p.worker}:{p.dst}", f"vault key {p.src} is pushed as {p.dst}: two names for one credential"))
        if p.src not in seen_src:
            seen_src.add(p.src)
            if not consumers(p.src):
                out.append(Finding("PUSHER-ONLY", f"vault:{p.src}", f"no code in the estate reads {p.src}; its only consumer is the recipe that pushes it"))
            if vault is None:
                out.append(Finding("NOT MEASURABLE", f"vault:{p.src}", "no vault injected (run under `infisical run`): presence, emptiness and liveness unchecked"))
            elif p.src not in vault:
                out.append(Finding("ABSENT", f"vault:{p.src}", f"{p.src} is not in the vault: syncing would push an empty string over the worker's working value"))
            elif vault[p.src] == 0:
                out.append(Finding("EMPTY", f"vault:{p.src}", f"{p.src} is present but EMPTY: syncing would overwrite the worker's value with nothing"))
            else:
                verdict = (probes or {}).get(p.src)
                if verdict == "dead":
                    out.append(Finding("DEAD", f"vault:{p.src}", f"{p.src} is well-formed but the provider rejects it"))
                elif verdict is None:
                    out.append(Finding("NOT MEASURABLE", f"vault:{p.src}", f"{p.src}: no liveness probe exists for this credential (reported, not passed)"))
                elif verdict == "error":
                    out.append(Finding("NOT MEASURABLE", f"vault:{p.src}", f"{p.src}: the liveness probe could not reach the provider"))
    return out


STATIC_STATES = {"UNREAD", "PUSHER-ONLY"}  # what a run WITHOUT the vault can measure; vault-half states are advisory, never baselined


def against_baseline(findings: list[Finding], baseline: dict, vault_measured: bool = False) -> tuple[list[str], list[str]]:
    """(violations, notes). A finding is accepted only if the baseline lists `state|key` with a reason; a stale entry is itself a violation."""
    accepted = baseline.get("accepted", {})
    bad: list[str] = []
    notes: list[str] = []
    judged = STATIC_STATES if not vault_measured else STATIC_STATES | {"ABSENT", "EMPTY", "DEAD"}
    live = {f"{f.state}|{f.key}" for f in findings if f.state in judged}
    for f in findings:
        if f.state not in judged:
            continue
        entry = accepted.get(f"{f.state}|{f.key}")
        if entry is None:
            bad.append(f"{f.state} {f.key}: {f.detail}")
        elif not str(entry.get("reason", "")).strip():
            bad.append(f"{f.state} {f.key}: accepted in the baseline WITHOUT a reason")
    for k in sorted(k for k in set(accepted) - live if k.split("|", 1)[0] in judged):
        bad.append(f"baseline entry `{k}` is no longer a finding: remove it (a list of things that used to be true)")
    return bad, notes


# ── live probes (vault half). Values are used in-process only, never printed. ─────────────────────────────────────────────
def _http(url: str, headers: dict[str, str]) -> int | None:
    if not url.startswith("https://"):
        return None
    req = urllib.request.Request(url, headers={"User-Agent": "w0m-secret-flow/1", **headers})
    try:
        # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected -- https enforced above; fixed provider hosts
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return None


def probe(key: str, value: str) -> str | None:
    """'live' | 'dead' | 'error' for the few credentials with a cheap liveness call, else None (NOT MEASURABLE)."""
    if key in ("CLOUDFLARE_API_TOKEN", "CF_RUNTIME_API_TOKEN", "CF_API_TOKEN"):
        s = _http("https://api.cloudflare.com/client/v4/user/tokens/verify", {"Authorization": f"Bearer {value}"})
    elif key == "TELEGRAM_BOT_TOKEN":
        s = _http(f"https://api.telegram.org/bot{value}/getMe", {})
    else:
        return None
    return "live" if s == 200 else "dead" if s in (400, 401, 403) else "error"


# ── selftest: the ticket's own three shapes, none invented (AC4) ──────────────────────────────────────────────────────────
def selftest() -> int:
    recipe = (
        'sync-cfworkers-secrets: (_confirm "x")\n'
        "    @infisical run --env=beta -- sh -c ' \\\n"
        '      echo "$CF_RUNTIME_API_TOKEN" | pnpm exec wrangler secret put CLOUDFLARE_API_TOKEN --name wom7func && \\\n'
        '      echo "$TELEGRAM_BOT_TOKEN" | pnpm exec wrangler secret put TELEGRAM_BOT_TOKEN --name wom7func && \\\n'
        '      echo "$GEMINI_API_KEY" | pnpm exec wrangler secret put GEMINI_API_KEY --name wom7func\'\n'
        'sync-api-secrets: (_confirm "y")\n'
        "    @infisical run --env=beta -- sh -c ' \\\n"
        '      for n in ADZUNA_APP_ID JOOBLE_API_KEY; do \\\n'
        '        printenv $n | pnpm exec wrangler secret put $n --name wom7api || exit 1; \\\n'
        '      done\'\n'
        'sync-cf-secrets project="webomage": (_confirm "z")\n'
        "    @x sh -c ' \\\n"
        '      echo "$PUBLIC_SUPABASE_URL" | pnpm exec wrangler secret put PUBLIC_SUPABASE_URL --name {{ project }}\'\n'
    )
    pushes = parse_pushes(recipe)
    tree = {"w0m-cf": {"w0m-cf/src/index.ts": "const t = env.TELEGRAM_BOT_TOKEN;\nconst g = env.GEMINI_API_KEY;\n",  # pinned worker
                         "w0m-cf/worker-configuration.d.ts": "  CLOUDFLARE_API_TOKEN: string;\n"},
            "w0m-api": {"w0m-api/src/a.ts": "const k = env.ADZUNA_APP_ID; const j = env.JOOBLE_API_KEY;"},  # pinned worker
            "webomage": {"w0m-web/apps/web/src/x.ts": "import.meta.env.PUBLIC_SUPABASE_URL"}}
    def consumers(k: str) -> list[str]:
        return [] if k == "CF_RUNTIME_API_TOKEN" else ["somewhere.ts"]
    checks: list[tuple[str, bool]] = []

    def has(fs: list[Finding], state: str, key: str) -> bool:
        return any(f.state == state and f.key == key for f in fs)

    def ok(name: str, cond: object) -> None:
        checks.append((name, bool(cond)))
    ok("parses the echo shape, the loop shape and the {{ project }} default",
       {(p.src, p.dst, p.worker) for p in pushes} == {
           ("CF_RUNTIME_API_TOKEN", "CLOUDFLARE_API_TOKEN", "wom7func"), ("TELEGRAM_BOT_TOKEN", "TELEGRAM_BOT_TOKEN", "wom7func"),  # pinned worker
           ("GEMINI_API_KEY", "GEMINI_API_KEY", "wom7func"), ("ADZUNA_APP_ID", "ADZUNA_APP_ID", "wom7api"),  # pinned worker
           ("JOOBLE_API_KEY", "JOOBLE_API_KEY", "wom7api"), ("PUBLIC_SUPABASE_URL", "PUBLIC_SUPABASE_URL", "webomage")})  # pinned worker
    vault_full = {"CF_RUNTIME_API_TOKEN": 53, "TELEGRAM_BOT_TOKEN": 46, "GEMINI_API_KEY": 39, "ADZUNA_APP_ID": 8, "JOOBLE_API_KEY": 36, "PUBLIC_SUPABASE_URL": 40}
    fs = evaluate(pushes, tree, consumers, vault_full, {"CF_RUNTIME_API_TOKEN": "dead"})
    ok("SHAPE 1 - pushed but unread: CLOUDFLARE_API_TOKEN on wom7func (a `.d.ts` declaration is not a reader)", has(fs, "UNREAD", "wom7func:CLOUDFLARE_API_TOKEN"))  # pinned worker
    ok("SHAPE 2 - the vault key's only consumer is the pusher: CF_RUNTIME_API_TOKEN", has(fs, "PUSHER-ONLY", "vault:CF_RUNTIME_API_TOKEN"))
    ok("...and the rename on push is reported (ALIASED)", has(fs, "ALIASED", "wom7func:CLOUDFLARE_API_TOKEN"))  # pinned worker
    ok("...and a well-formed vault key the provider rejects is DEAD", has(fs, "DEAD", "vault:CF_RUNTIME_API_TOKEN"))
    fs3 = evaluate(pushes, tree, consumers, {k: v for k, v in vault_full.items() if k != "TELEGRAM_BOT_TOKEN"}, {})
    ok("SHAPE 3 - absent from the vault but pushed to the worker: TELEGRAM_BOT_TOKEN", has(fs3, "ABSENT", "vault:TELEGRAM_BOT_TOKEN"))
    ok("an EMPTY vault value is its own state (the empty-secret digest trap)",
       has(evaluate(pushes, tree, consumers, {**vault_full, "GEMINI_API_KEY": 0}, {}), "EMPTY", "vault:GEMINI_API_KEY"))
    ok("positive control: a read secret with a present vault key is NOT unread/absent/empty",
       not any(f.key in ("wom7func:GEMINI_API_KEY", "vault:GEMINI_API_KEY") and f.state in ("UNREAD", "ABSENT", "EMPTY", "PUSHER-ONLY") for f in fs))  # pinned worker
    ok("no vault injected -> NOT MEASURABLE, never a pass and never a violation",
       has(evaluate(pushes, tree, consumers, None, {}), "NOT MEASURABLE", "vault:GEMINI_API_KEY"))
    ok("no probe for a credential -> NOT MEASURABLE (reported, not passed)", has(fs, "NOT MEASURABLE", "vault:GEMINI_API_KEY"))
    ok("an unmapped worker is NOT MEASURABLE, not silently skipped",
       has(evaluate([Push("r", "A_KEY", "A_KEY", "mystery")], {}, consumers, {"A_KEY": 3}, {}), "NOT MEASURABLE", "mystery:A_KEY"))
    ok("a fixture file, a generated .d.ts and a comment do not make a key 'consumed' (the estate-wide filter)",
       readers_in({"project/scripts/ast_grep_test.py": "x = Deno.env.get('K_TOKEN')",
                   "w/worker-configuration.d.ts": "K_TOKEN: string;", "s/a.ts": "// uses K_TOKEN"}, "K_TOKEN") == [])
    ok("the gate's own source never counts as a consumer (it names credentials as data)",
       readers_in({"scripts/secret_flow_check.py": "if key in ('K_TOKEN',): v = os.environ.get('K_TOKEN')"}, "K_TOKEN") == [])
    ok("...but a real read in an ordinary source file still counts", readers_in({"s/real.ts": "const t = process.env.K_TOKEN;"}, "K_TOKEN") == ["s/real.ts"])
    ok("comments and declarations are not readers",
       readers_in({"a.ts": "// env.X_TOKEN was here\n  X_TOKEN?: string;\n"}, "X_TOKEN") == [])
    bad, _ = against_baseline([Finding("UNREAD", "w:X", "d")], {"accepted": {}})
    ok("baseline: an unaccepted finding is a violation", len(bad) == 1)
    bad, _ = against_baseline([Finding("UNREAD", "w:X", "d")], {"accepted": {"UNREAD|w:X": {"reason": "  "}}})
    ok("baseline: an accepted entry WITHOUT a reason is a violation", len(bad) == 1)
    bad, _ = against_baseline([], {"accepted": {"UNREAD|w:GONE": {"reason": "r"}}})
    ok("baseline: an entry that is no longer a finding is a violation (stale)", len(bad) == 1)
    bad, _ = against_baseline([], {"accepted": {"DEAD|vault:K": {"reason": "r"}}})
    ok("baseline: a vault-half entry is NOT judged stale by a run that could not measure the vault", bad == [])
    bad, _ = against_baseline([Finding("UNREAD", "w:X", "d")], {"accepted": {"UNREAD|w:X": {"reason": "kept on purpose"}}})
    ok("baseline: an accepted, reasoned finding passes", bad == [])
    for name, passed in checks:
        print(f"  {'✅' if passed else '🔴'} {name}")
    n = sum(1 for _, p in checks if p)
    print(f"\n── {n}/{len(checks)} probes behaved as specified.")
    return 0 if n == len(checks) else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vault", action="store_true", help="also check the vault (run under infisical): presence, emptiness, liveness")
    ap.add_argument("--enforce", action="store_true")
    ap.add_argument("--test", action="store_true")
    a = ap.parse_args(argv)
    if a.test:
        return selftest()

    justfile_corpus = "\n".join(
        p.read_text(encoding="utf-8") for p in JUSTFILES if p.is_file()
    )
    pushes = parse_pushes(justfile_corpus)
    if not pushes:
        print("❌ parsed 0 secret pushes from the justfile: the parser no longer matches it (fail closed).", file=sys.stderr)
        return 2
    trees = {w: load_tree(WORKER_SOURCES[w]) for w in {p.worker for p in pushes} if w in WORKER_SOURCES}
    empty = [w for w, t in trees.items() if not t]
    if empty:
        print(f"❌ no source files found for worker(s) {empty}: a moved directory would make every secret look UNREAD (fail closed).", file=sys.stderr)
        return 2
    vault: dict[str, int] | None = None
    probes: dict[str, str] = {}
    if a.vault:
        srcs = {p.src for p in pushes}
        vault = {k: len(os.environ[k]) for k in srcs if k in os.environ}
        if not os.environ.get("INFISICAL_TOKEN") and not vault:
            print("⚠️ --vault but no secrets are injected (run `infisical run --env=beta -- just secret-flow-check --vault`).", file=sys.stderr)
            vault = None
        else:
            for k in sorted(vault):
                v = probe(k, os.environ[k]) if vault[k] else None
                if v:
                    probes[k] = v
    cache: dict[str, list[str]] = {}
    findings = evaluate(pushes, trees, lambda k: cache.setdefault(k, estate_consumers(k)), vault, probes)

    print(f"▶ secret-flow: {len(pushes)} push(es) across {len({p.worker for p in pushes})} worker(s), {len({p.src for p in pushes})} vault key(s)"
          f"{'' if vault is not None else '  (vault half NOT MEASURED: --vault under infisical)'}\n")
    order = ["UNREAD", "PUSHER-ONLY", "ABSENT", "EMPTY", "DEAD", "ALIASED", "NOT MEASURABLE"]
    for st in order:
        rows = [f for f in findings if f.state == st]
        if not rows:
            continue
        print(f"── {st} ({len(rows)})")
        for f in rows[:40]:
            print(f"   {f.key:44} {f.detail[:118]}")
        if len(rows) > 40:
            print(f"   … {len(rows) - 40} more")
    if not any(f.state not in ("NOT MEASURABLE", "ALIASED") for f in findings):
        print("✅ no unread, absent, empty or dead secret in the measured set")

    if a.enforce:
        base = json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.exists() else {"accepted": {}}
        bad, _ = against_baseline(findings, base, vault_measured=vault is not None)
        if bad:
            print(f"\n❌ {len(bad)} secret-flow violation(s) not accepted in project/secret-flow-baseline.json:", file=sys.stderr)
            for b in bad:
                print(f"   🔴 {b}", file=sys.stderr)
            return 1
        print("✅ secret-flow: every finding is accepted with a reason; no stale acceptance")
    return 0


if __name__ == "__main__":
    sys.exit(main())
