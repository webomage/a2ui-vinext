#!/usr/bin/env python3
"""
w0m full audit / status — T96 (ROADMAP §28).

One authoritative read-only sweep:
  • DRIFT   — git cleanliness / ahead-behind, spec-drift gate, OpenSpec validity
  • CONFORM — design-system drift (hardcoded #0a84ff, native <select>) + decommission drift
  • DIFF    — local HEAD vs what is actually DEPLOYED (per-app /api/health commit+version)
             + partial-deploy detector (apps on differing deployed versions)
  • HEALTH  — every app + the edge-fn gateway + the worker respond OK

Composes the existing knowledge/guardrail recipes rather than re-implementing them:
DB-dependent checks (lexicon-lint) are optional and only run with
`--deep` (they need infisical/DATABASE_URL); everything else needs only git + network.

Usage:
  python3 scripts/w0m_audit.py            # full sweep, writes a report, prints summary
  python3 scripts/w0m_audit.py --quick    # skip network (diff/health) — fast git+spec only
  python3 scripts/w0m_audit.py --deep      # + markers/lexicon + migrations drift + unused-secrets (infisical; DB needs WARP)
  python3 scripts/w0m_audit.py --no-report # don't write the md report

Exit code: non-zero if any check FAILs (so a fast subset can gate a git hook); WARN never fails.
Manual: `just audit`. Fast subset intended for the pre-push hook.
"""
import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path


def _redact_pg(s):
    """Strip any postgres connection string (carries the DB password) from a message."""
    return re.sub(r"(postgres(?:ql)?://[^:@\s/]+:)[^@\s/]+@", r"\1<redacted>@", str(s))

# ── repo layout (self-locating: this file is @wom/scripts/w0m_audit.py) ──
MONO_ROOT = Path(__file__).resolve().parents[1]         # …/@wom
WEB_ROOT = MONO_ROOT / "wom7web"                        # wom7web/
SDLC_JSON = MONO_ROOT / ".w0m" / "sdlc.json"
API_ROOT = MONO_ROOT / "wom7api"

APPS = {  # app → public host serving /api/health
    "web": "https://webomage.com",
    "cp": "https://cp.webomage.com",
    "join": "https://join.webomage.com",
    "job": "https://job.webomage.com",
    "demo": "https://demo.webomage.com",
}
WORKER_HEALTH = "https://wom7func.webomage.workers.dev/health"

PASS, WARN, FAIL, SKIP, INFO = "✅ PASS", "⚠️  WARN", "❌ FAIL", "⏭️  SKIP", "ℹ️  INFO"
results: list[tuple[str, str, str, str]] = []  # (level, section, name, detail)


def add(level, section, name, detail=""):
    results.append((level, section, name, detail))
    print(f"  {level}  [{section}] {name}" + (f" — {detail}" if detail else ""))


def git(*args, cwd=None):
    return subprocess.run(["git", *args], cwd=cwd or WEB_ROOT, capture_output=True, text=True)


def http_json(url, timeout=10):
    # URLs are hardcoded internal health endpoints (APPS / WORKER_HEALTH) — no user
    # input, so the dynamic-urllib SSRF audit rule is a reviewed false positive here.
    req = urllib.request.Request(url, headers={"User-Agent": "w0m-audit"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
        return r.status, json.loads(r.read().decode("utf-8"))


# ── DIFF: local HEAD vs deployed ────────────────────────────────────────────────
def check_diff(head):
    print("\n▶ DIFF — local vs deployed")
    versions = {}
    for app, host in APPS.items():
        try:
            status, body = http_json(f"{host}/api/health")
            dep_commit = str(body.get("commit", "?"))
            ver = body.get("version", "?")
            versions[app] = ver
            if dep_commit != "?" and head.startswith(dep_commit):
                add(PASS, "diff", f"{app}", f"deployed = HEAD ({dep_commit}, {ver})")
            else:
                ahead = git("rev-list", "--count", f"{dep_commit}..HEAD")
                n = ahead.stdout.strip() if ahead.returncode == 0 else "?"
                add(WARN, "diff", f"{app}",
                    f"deployed {dep_commit} ({ver}) is {n} commit(s) behind HEAD {head[:8]}")
        except Exception as e:  # noqa: BLE001
            add(WARN, "diff", f"{app}", f"health unreachable ({type(e).__name__})")
    # Partial-deploy detector: all apps ship in one `just deploy`, so a version spread
    # means a deploy landed some apps but not others.
    uniq = set(versions.values())
    if len(uniq) > 1:
        add(WARN, "diff", "version consistency",
            "apps on different deployed versions: " +
            ", ".join(f"{a}={v}" for a, v in sorted(versions.items())))
    elif uniq:
        add(PASS, "diff", "version consistency", f"all apps on {next(iter(uniq))}")


# ── CONFORM: design-system + decommission drift (grep, no deps) ──────────────────
def _grep_count(pattern, *pathspecs):
    """Total matching lines from `git grep -oiE` across the given pathspecs (0 if none)."""
    r = git("grep", "-oiE", pattern, "--", *pathspecs)
    return len([l for l in r.stdout.splitlines() if l.strip()]) if r.returncode == 0 else 0


def _grep_files(pattern, *pathspecs):
    r = git("grep", "-liE", pattern, "--", *pathspecs)
    return len([l for l in r.stdout.splitlines() if l.strip()]) if r.returncode == 0 else 0


CODE_PATHS = ("apps", "packages")  # git grep recurses; dist/node_modules are gitignored


def _load_decommission():
    """Module loaded by path — project/scripts is not an importable package."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "decommission_check", WEB_ROOT / "project" / "scripts" / "decommission_check.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_decommission = _load_decommission()


def check_conform():
    print("\n▶ CONFORM — design-system + decommission drift")
    # Design-system drift (baseline for T91/T92): hardcoded macOS-blue hex + native <select>.
    hex_hits = _grep_count(r"#0a84ff", *CODE_PATHS)
    add(WARN if hex_hits else PASS, "ds", "hardcoded #0a84ff",
        f"{hex_hits} occurrence(s) — should be a DS token (T92)" if hex_hits else "none")
    sel_files = _grep_files(r"<select[ >]", *CODE_PATHS)
    add(WARN if sel_files else PASS, "ds", "native <select>",
        f"{sel_files} file(s) — should use the DS Select (T92)" if sel_files else "none")
    # Decommission drift — READ from DECOMMISSIONED.md, not hardcoded here.
    # This block used to name two terms, `openrouter` and `SWARM_URL`, while the tombstone log
    # declared five retirements. Only SWARM_URL was in both: four tombstones had no check, and
    # `openrouter` was checked while appearing nowhere in the log — a real owner decision that
    # stayed invisible because the reader and the declaration never met. Each tombstone now
    # carries its own `absent` block and this reads them.
    try:
        assertions, unasserted = _decommission.load_assertions()
    except Exception as exc:  # a log we cannot parse is UNMEASURABLE, never silently clean
        add(FAIL, "decommission", "tombstone log", f"cannot read DECOMMISSIONED.md — {exc}")
    else:
        if not assertions:
            add(FAIL, "decommission", "tombstone log", "no `absent` blocks — cannot measure")
        for a in assertions:
            head = a["tombstone"].split("—")[0].strip()
            for ok, label, detail in _decommission.check(a):
                add(PASS if ok else WARN, "decommission", f"{head}: {label}", detail)
        for name in unasserted:
            add(WARN, "decommission", name.split("—")[0].strip(),
                "retired, but no `absent` block proves it stayed gone")

    bp_check = WEB_ROOT / "project" / "scripts" / "blueprint_catalog_check.py"
    if bp_check.is_file():
        r_bp = subprocess.run([sys.executable, str(bp_check)], cwd=WEB_ROOT, capture_output=True, text=True)
        bp_msg = (r_bp.stdout or r_bp.stderr).strip().splitlines()
        add(PASS if r_bp.returncode == 0 else FAIL, "conform", "blueprint-catalog",
            bp_msg[-1] if bp_msg else ("ok" if r_bp.returncode == 0 else "blueprint catalog drift"))

    obs_check = WEB_ROOT / "project" / "scripts" / "check_observability_map.py"
    if obs_check.is_file():
        r_obs = subprocess.run([sys.executable, str(obs_check)], cwd=WEB_ROOT, capture_output=True, text=True)
        obs_msg = (r_obs.stdout or r_obs.stderr).strip().splitlines()
        add(PASS if r_obs.returncode == 0 else FAIL, "conform", "observability-map",
            obs_msg[-1] if obs_msg else ("ok" if r_obs.returncode == 0 else "observability_map.md drift"))


# ── DRIFT: git + spec ────────────────────────────────────────────────────────────
def _openspec_scope_plan(scope_diff: str) -> tuple[list[str], int, int]:
    """Compute (touched_tracked_items, skipped_tracked_count, untracked_disk_count) for scoped OpenSpec validation.

    Uses the same `--scope-diff` reachability basis as `spec_drift_gate.py`:
      - tracked active changes (`openspec/changes/<id>/...`, excluding `archive/`) and specs (`openspec/specs/<id>/...`)
        modified in `<scope_diff>...HEAD`, `<scope_diff> HEAD`, or staged (`--cached`) in `WEB_ROOT`;
      - tracked active changes/specs linked via `spec:` frontmatter from `.tasks/T*.md` tickets modified in `MONO_ROOT`.
    Untracked OpenSpec directories on disk are never validated in scoped mode and are counted separately.
    """
    changes_root = Path(WEB_ROOT) / "openspec" / "changes"
    specs_root = Path(WEB_ROOT) / "openspec" / "specs"
    disk_changes = (
        {d.name for d in changes_root.iterdir() if d.is_dir() and d.name != "archive"}
        if changes_root.is_dir() else set()
    )
    disk_specs = (
        {d.name for d in specs_root.iterdir() if d.is_dir()}
        if specs_root.is_dir() else set()
    )

    ls_res = git("ls-files", "openspec/changes", "openspec/specs", cwd=WEB_ROOT)
    tracked_changes: set[str] = set()
    tracked_specs: set[str] = set()
    if ls_res.returncode == 0:
        for line in ls_res.stdout.splitlines():
            p = line.strip()
            mc = re.match(r"^openspec/changes/([^/]+)/", p)
            if mc and mc.group(1) != "archive" and mc.group(1) in disk_changes:
                tracked_changes.add(mc.group(1))
            ms = re.match(r"^openspec/specs/([^/]+)/", p)
            if ms and ms.group(1) in disk_specs:
                tracked_specs.add(ms.group(1))
    else:
        tracked_changes = set(disk_changes)
        tracked_specs = set(disk_specs)

    untracked_count = len(disk_changes - tracked_changes) + len(disk_specs - tracked_specs)
    total_tracked = len(tracked_changes) + len(tracked_specs)

    d_three = git("diff", "--name-only", f"{scope_diff}...HEAD", cwd=WEB_ROOT)
    d_two = git("diff", "--name-only", scope_diff, "HEAD", cwd=WEB_ROOT)
    d_cached = git("diff", "--name-only", "--cached", cwd=WEB_ROOT)
    changed_paths: set[str] = set()
    for res in (d_three, d_two, d_cached):
        if res.returncode == 0:
            changed_paths.update(p.strip() for p in res.stdout.splitlines() if p.strip())
    if d_three.returncode != 0 and d_two.returncode != 0:
        d_fallback = git("diff", "--name-only", "HEAD~1...HEAD", cwd=WEB_ROOT)
        if d_fallback.returncode == 0:
            changed_paths.update(p.strip() for p in d_fallback.stdout.splitlines() if p.strip())

    touched_changes: set[str] = set()
    touched_specs: set[str] = set()
    for path in changed_paths:
        mc = re.match(r"^openspec/changes/([^/]+)/", path)
        if mc and mc.group(1) in tracked_changes:
            touched_changes.add(mc.group(1))
        ms = re.match(r"^openspec/specs/([^/]+)/", path)
        if ms and ms.group(1) in tracked_specs:
            touched_specs.add(ms.group(1))

    tasks_dir = Path(MONO_ROOT) / ".tasks"
    if tasks_dir.is_dir():
        m_three = git("diff", "--name-only", f"{scope_diff}...HEAD", cwd=MONO_ROOT)
        m_two = git("diff", "--name-only", scope_diff, "HEAD", cwd=MONO_ROOT)
        m_cached = git("diff", "--name-only", "--cached", cwd=MONO_ROOT)
        mono_paths: set[str] = set()
        for res in (m_three, m_two, m_cached):
            if res.returncode == 0:
                mono_paths.update(p.strip() for p in res.stdout.splitlines() if p.strip())
        for path in mono_paths:
            if re.match(r"^\.tasks/T[^/]+\.md$", path):
                tfile = Path(MONO_ROOT) / path
                if tfile.is_file():
                    txt = tfile.read_text(encoding="utf-8", errors="ignore")
                    fm_spec = re.search(r"^spec:\s*[\"']?(.*?)[\"']?\s*$", txt, re.M)
                    if fm_spec:
                        spec_val = fm_spec.group(1)
                        for cid in re.findall(r"openspec/changes/([^/\s\"',]+)", spec_val):
                            if cid != "archive" and cid in tracked_changes:
                                touched_changes.add(cid)
                        for sid in re.findall(r"openspec/specs/([^/\s\"',]+)", spec_val):
                            if sid in tracked_specs:
                                touched_specs.add(sid)

    touched_items = sorted(touched_changes) + [s for s in sorted(touched_specs) if s not in touched_changes]
    skipped_count = max(0, total_tracked - len(touched_items))
    return touched_items, skipped_count, untracked_count


def check_drift(scope_diff: str | None = None) -> None:
    print("\n▶ DRIFT — git + specs")
    porcelain = git("status", "--porcelain")
    dirty = [l for l in porcelain.stdout.splitlines() if l.strip()]
    add(WARN if dirty else PASS, "git", "working tree",
        f"{len(dirty)} uncommitted change(s)" if dirty else "clean")

    branch = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    git("fetch", "--quiet", "origin", branch)
    ab = git("rev-list", "--left-right", "--count", f"origin/{branch}...HEAD")
    if ab.returncode == 0 and ab.stdout.strip():
        behind, ahead = ab.stdout.split()
        lvl = WARN if (ahead != "0" or behind != "0") else PASS
        add(lvl, "git", f"branch {branch}", f"{ahead} ahead / {behind} behind origin")

    # spec-drift gate (hard-fails on completed-not-archived / done-ticket-active drift).
    # --scope-diff <ref> scopes it to what a push touches (pre-existing backlog stays
    # advisory) — the pre-push hook passes origin/<branch> so it matches historic behavior.
    sd_cmd = [sys.executable, str(MONO_ROOT / "scripts" / "spec_drift_gate.py")]
    if scope_diff:
        sd_cmd += ["--scope-diff", scope_diff]
    sd = subprocess.run(sd_cmd, cwd=WEB_ROOT, capture_output=True, text=True)
    add(PASS if sd.returncode == 0 else FAIL, "spec", "spec-drift gate",
        "clean" if sd.returncode == 0 else (sd.stdout.strip().splitlines() or ["drift"])[-1][:120])

    # OpenSpec validity (real CLI = @fission-ai/openspec). Prefer modern global version
    # over outdated local node_modules pinned binaries. Skip if not found.
    candidates = [
        os.path.join(WEB_ROOT, "node_modules/.bin/openspec"),
        os.path.expanduser("~/Library/pnpm/openspec"),
        shutil.which("openspec"),
        os.path.expanduser("~/.local/share/pnpm/openspec"),
        "/opt/homebrew/bin/openspec",
        "/usr/local/bin/openspec",
    ]
    openspec_bin = next((c for c in candidates if c and os.path.isfile(c) and os.access(c, os.X_OK)), None)
    if not openspec_bin:
        add(SKIP, "spec", "openspec validate", "openspec CLI not on PATH")
    elif scope_diff:
        touched_items, skipped_count, untracked_count = _openspec_scope_plan(scope_diff)
        validated_count = len(touched_items)
        scope_summary = (
            f"validated {validated_count} touched item(s), "
            f"skipped {skipped_count} untouched item(s) (scope: {scope_diff}); "
            f"{untracked_count} untracked ignored"
        )
        if not touched_items:
            add(PASS, "spec", "openspec validate (scoped)", scope_summary)
        else:
            all_valid = True
            first_fail = ""
            for cid in touched_items:
                res = subprocess.run([openspec_bin, "validate", cid, "--strict"],
                                     cwd=WEB_ROOT, capture_output=True, text=True)
                if res.returncode != 0:
                    all_valid = False
                    tail = (res.stdout + res.stderr).strip().splitlines()
                    first_fail = f"{cid}: {tail[-1] if tail else 'invalid'} ({scope_summary})"
                    break
            if all_valid:
                add(PASS, "spec", "openspec validate (scoped)", scope_summary)
            else:
                add(FAIL, "spec", "openspec validate (scoped)", first_fail[:200])
    else:
        ov = subprocess.run([openspec_bin, "validate", "--all", "--strict"],
                            cwd=WEB_ROOT, capture_output=True, text=True)
        if ov.returncode == 0:
            totals = [l.strip() for l in (ov.stdout + ov.stderr).splitlines() if l.strip().startswith("Totals:")]
            detail = f"all valid ({totals[-1]})" if totals else "all valid"
            add(PASS, "spec", "openspec validate --all --strict", detail)
        else:
            tail = (ov.stdout + ov.stderr).strip().splitlines()
            add(FAIL, "spec", "openspec validate --all --strict", (tail[-1] if tail else "invalid")[:120])


# ── HEALTH ───────────────────────────────────────────────────────────────────────
def check_health():
    print("\n▶ HEALTH — apps + worker")
    for app, host in APPS.items():
        try:
            status, body = http_json(f"{host}/api/health")
            ok = status == 200 and str(body.get("status", "")).lower() in ("ok", "healthy")
            add(PASS if ok else FAIL, "health", app, f"HTTP {status} status={body.get('status')}")
        except Exception as e:  # noqa: BLE001
            add(FAIL, "health", app, f"unreachable ({type(e).__name__})")
    try:
        status, _ = http_json(WORKER_HEALTH)
        add(PASS if status == 200 else FAIL, "health", "wom7func", f"HTTP {status}")
    except Exception as e:  # noqa: BLE001
        add(FAIL, "health", "wom7func", f"unreachable ({type(e).__name__})")


# ── SECURITY: browser-reputation state (T120 AC6) ──────────────────────────────────
# WHY THIS EXISTS: on 2026-07-22 a Google Safe Browsing "Deceptive pages" flag was found
# on webomage.com by opening Search Console by hand. It had been live for TWELVE DAYS —
# Chrome warning real visitors the whole time — because nothing watched for it. The code
# fix had shipped; only the ops step was missed, and nothing noticed the miss.
#
# The authoritative check is the Safe Browsing Lookup API, which needs a Google Cloud API
# key with that API enabled (SAFE_BROWSING_API_KEY). We do not hold one yet, so this
# degrades to a STALENESS check: it warns when nobody has confirmed the reputation state
# recently. That is deliberately weaker, but it is exactly the failure that happened —
# a staleness nudge would have surfaced the flag on day 1 instead of day 12.
SECURITY_STATE = WEB_ROOT / "project" / "security-state.json"
SECURITY_STALE_DAYS = 7
SAFE_BROWSING_URL = "https://safebrowsing.googleapis.com/v4/threatMatches:find"
REPUTATION_DOMAINS = ("https://webomage.com", "https://cp.webomage.com",
                      "https://join.webomage.com", "https://demo.webomage.com")


def _safe_browsing_lookup(api_key):
    """Returns the list of flagged URLs, or None when the API could not be consulted."""
    payload = {
        "client": {"clientId": "w0m-audit", "clientVersion": "1.0"},
        "threatInfo": {
            "threatTypes": ["MALWARE", "SOCIAL_ENGINEERING", "UNWANTED_SOFTWARE",
                            "POTENTIALLY_HARMFUL_APPLICATION"],
            "platformTypes": ["ANY_PLATFORM"],
            "threatEntryTypes": ["URL"],
            "threatEntries": [{"url": u} for u in REPUTATION_DOMAINS],
        },
    }
    req = urllib.request.Request(
        f"{SAFE_BROWSING_URL}?key={api_key}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "w0m-audit"},
    )
    try:
        # Fixed vendor endpoint, no user input in the URL path.
        with urllib.request.urlopen(req, timeout=15) as r:  # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
            body = json.loads(r.read().decode("utf-8"))
        return [m.get("threat", {}).get("url", "?") for m in body.get("matches", [])]
    except Exception:  # noqa: BLE001
        return None


def check_security():
    print("\n▶ SECURITY — browser reputation (T120)")
    key = os.environ.get("SAFE_BROWSING_API_KEY") or os.environ.get("GOOGLE_SAFE_BROWSING_KEY")

    if key:
        flagged = _safe_browsing_lookup(key)
        if flagged is None:
            add(WARN, "security", "safe-browsing", "API unreachable — state unconfirmed")
        elif flagged:
            add(FAIL, "security", "safe-browsing",
                f"{len(flagged)} URL(s) FLAGGED: {', '.join(flagged[:3])}")
        else:
            add(PASS, "security", "safe-browsing",
                f"{len(REPUTATION_DOMAINS)} domains clean per Safe Browsing")
        return

    # No key: fall back to "when did a human last confirm this?"
    try:
        state = json.loads(SECURITY_STATE.read_text())
        last = datetime.fromisoformat(state["reputation_checked"].replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - last).days
        note = state.get("note", "")
        if age > SECURITY_STALE_DAYS:
            add(WARN, "security", "reputation-staleness",
                f"last confirmed {age}d ago (>{SECURITY_STALE_DAYS}d) — check Search Console "
                f"→ Security issues. {note}")
        else:
            add(PASS, "security", "reputation-staleness", f"confirmed {age}d ago. {note}")
    except FileNotFoundError:
        add(WARN, "security", "reputation-staleness",
            f"no {SECURITY_STATE.name} — run the check and record it")
    except Exception as e:  # noqa: BLE001
        add(WARN, "security", "reputation-staleness", f"unreadable state ({type(e).__name__})")
    add(INFO, "security", "safe-browsing",
        "set SAFE_BROWSING_API_KEY for an authoritative check instead of a staleness nudge")


def check_exposure():
    """Host MCP/network exposure vs the declared baseline — T154 AC6's standing cadence.

    ⚠️ WHY IT LIVES HERE AND NOT IN A HOOK. AC6 is explicit that this must not be a pre-push
    gate: these are HOST facts that change when a desktop app launches or a container starts,
    not when code is pushed, so a commit-time check would be both noisy and blind. `--quick` is
    the pre-push subset, so placing this outside it makes that constraint structural rather than
    a comment somebody deletes.

    WHY NOT A SCHEDULED TASK. Considered and rejected: a launchd/cron run that fires at 03:00 has
    nobody reading it, this estate has already been bitten by a scheduler surface where runs
    silently did not fire, and CI is not an option (GitHub Actions is dead on this account). The
    audit is run deliberately, writes a dated report, and its output is read — which is the whole
    definition of a cadence that works.

    A regression FAILs the sweep. A known-open finding WARNs every single run: recording an
    exposure is not fixing it, and a finding that stops being printed stops being true.
    """
    print("\n▶ EXPOSURE — host MCP/network surfaces vs the declared baseline (T154)")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import mcp_ratchet
        rep = mcp_ratchet.evaluate()
    except Exception as e:  # noqa: BLE001
        # Never silently pass: an exposure check that cannot run is an unknown, not a clean host.
        add(WARN, "exposure", "mcp-ratchet", f"could not run ({type(e).__name__}: {e})")
        return
    if "error" in rep:
        add(WARN, "exposure", "mcp-ratchet", rep["error"])
        return

    for r in rep["regressions"]:
        add(FAIL, "exposure", f"{r['key']} [{r['kind']}]", r["detail"])
    for k in rep["known_open"]:
        add(WARN, "exposure", f"{k['key']} known-open", k["reason"].split(". ")[0][:200])
    if not rep["regressions"]:
        add(PASS, "exposure", "mcp-ratchet",
            f"{len(rep['tracked'])} tracked surface(s), none newly exposed "
            f"(baseline {rep['measured']})")
    if rep["improvements"]:
        add(INFO, "exposure", "improved",
            f"{len(rep['improvements'])} surface(s) tightened — lock in with `just mcp-ratchet --save`")


# ── HOST: macOS security posture, network exposure & startup (T233) ───────────────
def check_host():
    """T233 AC1/AC2/AC3/AC4/AC6 — macOS host security posture and startup surface."""
    print("\n▶ HOST — macOS security controls & startup surface (T233)")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import host_posture
        report = host_posture.evaluate_host_posture()
    except Exception as e:
        add(WARN, "host", "host-posture", f"could not run ({type(e).__name__}: {e})")
        return

    for c in report.get("checks", []):
        add(c["status"], "host", c["name"], c["detail"])

    for key, item in report.get("unmeasured", {}).items():
        add(item["status"], "host", item["name"], item["reason"])


# ── AUTHZ: database & client authorization core (T233) ─────────────────────────────
def check_authz():
    """T233 AC1 — Compose existing database and client authorization gates."""
    print("\n▶ AUTHZ — database & client authorization core (T233)")
    # 1. Admin client downward ratchet (T327)
    triage_script = WEB_ROOT / "project" / "scripts" / "authz_admin_client_triage.py"
    if triage_script.exists():
        try:
            r = subprocess.run(
                [sys.executable, str(triage_script), "--enforce"],
                capture_output=True, text=True, check=False
            )
            if r.returncode == 0:
                tail = [l.strip() for l in r.stdout.splitlines() if l.strip().startswith("✅")]
                detail = tail[-1] if tail else "within baseline limits and zero unregistered importers"
                add(PASS, "authz", "admin-client-ratchet", detail)
            else:
                tail = [l.strip() for l in r.stdout.splitlines() if l.strip()]
                detail = tail[-1] if tail else "authz-admin-client ratchet failed"
                add(FAIL, "authz", "admin-client-ratchet", detail)
        except Exception as e:
            add(FAIL, "authz", "admin-client-ratchet", f"could not execute ({type(e).__name__}: {e})")
    else:
        add(SKIP, "authz", "admin-client-ratchet", "authz_admin_client_triage.py not found")

    # 2. Database authorization probes (T198/T200/T329) — requires infisical / DB connection
    probe_script = WEB_ROOT / "project" / "scripts" / "authz_probe_suite.py"
    if not probe_script.exists():
        add(SKIP, "authz", "authz-probe-suite", "authz_probe_suite.py not found")
    elif shutil.which("infisical") is None:
        add(SKIP, "authz", "authz-probe-suite", "infisical not on PATH")
    else:
        try:
            r = subprocess.run(
                ["infisical", "run", "--env=beta", "--silent", "--", sys.executable, str(probe_script), "--quiet"],
                cwd=WEB_ROOT, capture_output=True, text=True, timeout=120
            )
            if r.returncode == 0:
                summary_lines = [l.strip() for l in r.stdout.splitlines() if "probes passed" in l or "18/18" in l or l.startswith("✅")]
                add(PASS, "authz", "authz-probes", summary_lines[-1] if summary_lines else "all authorization probes passed")
            else:
                tail = [l.strip() for l in (r.stderr or r.stdout).splitlines() if l.strip()]
                if any("connection refused" in t.lower() or "timeout" in t.lower() or "could not connect" in t.lower() for t in tail):
                    add(SKIP, "authz", "authz-probes", f"DB unreachable (WARP down?): {tail[-1][:80]}")
                else:
                    add(FAIL, "authz", "authz-probes", tail[-1][:120] if tail else "authz probes failed")
        except Exception as e:
            add(SKIP, "authz", "authz-probes", f"could not run ({type(e).__name__}: {e})")


# ── PLATFORM: leakage, limits & exposure (T233) ────────────────────────────────────
def check_platform_security():
    """T233 AC1 — Compose platform security and credential leak checks."""
    print("\n▶ PLATFORM — leakage, limits & exposure (T233)")
    cv_script = WEB_ROOT / "project" / "scripts" / "cv_public.py"
    if cv_script.exists():
        try:
            r = subprocess.run([sys.executable, str(cv_script), "--check"], capture_output=True, text=True, check=False)
            if r.returncode == 0:
                add(PASS, "platform", "cv-leak-check", "clean: no private data in served CV public surfaces")
            else:
                tail = [l.strip() for l in r.stdout.splitlines() if l.strip()]
                add(FAIL, "platform", "cv-leak-check", tail[-1] if tail else "cv-leak-check failed")
        except Exception as e:
            add(WARN, "platform", "cv-leak-check", f"could not run ({type(e).__name__}: {e})")
    else:
        add(SKIP, "platform", "cv-leak-check", "cv_public.py not found")

    limits_script = API_ROOT / "scripts" / "supabase_limits.py"
    if limits_script.exists() and shutil.which("infisical"):
        try:
            r = subprocess.run(
                ["infisical", "run", "--env=beta", "--silent", "--", sys.executable, str(limits_script), "--summary"],
                cwd=API_ROOT, capture_output=True, text=True, timeout=60
            )
            if r.returncode == 0:
                tail = [l.strip() for l in r.stdout.splitlines() if l.strip()]
                add(PASS, "platform", "supabase-limits", tail[-1] if tail else "within operational limits")
            else:
                tail = [l.strip() for l in (r.stderr or r.stdout).splitlines() if l.strip()]
                add(WARN if "warn" in "".join(tail).lower() else SKIP, "platform", "supabase-limits", tail[-1][:100] if tail else "limits check skipped")
        except Exception as e:
            add(SKIP, "platform", "supabase-limits", f"could not run ({type(e).__name__}: {e})")
    else:
        add(SKIP, "platform", "supabase-limits", "supabase_limits.py or infisical not available")


# ── DEEP (DB / infisical-backed, optional) ─────────────────────────────────────────
REPOS = ("wom7web", "wom7api", "wom7func", "wom7ext")


def check_migrations():
    """On-disk migration files vs what's applied in supabase_migrations.schema_migrations.
    The applied query needs the IPv6 DB (WARP up) — degrades to a WARN when unreachable."""
    mig = API_ROOT / "supabase" / "migrations"
    on_disk = sorted(p.name.split("_", 1)[0] for p in mig.glob("*.sql") if p.name[:8].isdigit())
    if shutil.which("infisical") is None:
        add(SKIP, "migrations", "applied-vs-on-disk", f"{len(on_disk)} on disk; infisical not on PATH")
        return
    q = ('psql "$DATABASE_URL" -tAc '
         '"select version from supabase_migrations.schema_migrations order by version"')
    r = subprocess.run(["infisical", "run", "--env=beta", "--silent", "--", "sh", "-c", q],
                       cwd=API_ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        tail = ((r.stderr or r.stdout).strip().splitlines() or ["psql failed"])[-1]
        add(WARN, "migrations", "applied-vs-on-disk",
            f"{len(on_disk)} on disk; DB unreachable — needs WARP/IPv6 ({_redact_pg(tail)[:70]})")
        return
    applied = {l.strip() for l in r.stdout.splitlines() if l.strip()}
    pending = [v for v in on_disk if v not in applied]
    extra = [v for v in applied if v not in on_disk]
    detail = f"{len(on_disk)} on disk / {len(applied)} applied"
    if pending:
        detail += f"; {len(pending)} PENDING (e.g. {pending[:3]})"
    if extra:
        detail += f"; {len(extra)} applied-not-on-disk"
    add(WARN if (pending or extra) else PASS, "migrations", "applied-vs-on-disk", detail)


# Names-only probe (T135 §6 / AC10). It prints the child's environment KEYS as JSON and nothing
# else, so no secret VALUE is ever serialised.
#
# WHY NOT `infisical export --format=json`: that is what this used to do, and it materialised every
# secret VALUE into our captured stdout. The docstring claimed "values never read"; they were in the
# buffer regardless — a claim in a comment is not a control. `--format=json` IS supported by
# `export` (the recorded "unsupported" gotcha is about `infisical secrets`, a different
# subcommand), so the call worked and really did leak.
#
# WHY NOT `env | cut -d= -f1`: a secret whose value contains a newline emits extra lines that
# `cut` reports as bogus KEY names. Dumping `os.environ` keys from Python is newline-safe.
_ENV_KEYS_PROBE = "import json,os,sys; sys.stdout.write(json.dumps(sorted(os.environ)))"


def _declared_secret_names() -> list[str] | None:
    """Declared secret NAMES via injection, never materialising a value. None ⇒ unavailable.

    Names are recovered by differencing the injected child environment against our own. A declared
    secret whose name collides with an ambient env var is therefore subtracted and drops out of the
    set — an UNDER-report, so it can only ever cause a secret to go unexamined, never a false
    "unused" alarm. Measured 2026-07-26: 3 ambient names are secret-shaped
    (`ANTHROPIC_BASE_URL`, `API_TIMEOUT_MS`, `XPC_SERVICE_NAME`) and none is a w0m secret.
    """
    r = subprocess.run(
        ["infisical", "run", "--env=beta", "--silent", "--", sys.executable, "-c", _ENV_KEYS_PROBE],
        cwd=API_ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        return None
    try:
        injected = set(json.loads(r.stdout))
    except Exception:  # noqa: BLE001
        return None
    return sorted(injected - set(os.environ))


# T95 AC3 — human login passwords + a vault-file passphrase, used manually outside any repo.
# No script ever reads these, so they can never show up in a code reference — accepted by
# declaration (see docs/CONNECTOR-MAP.md §9), not because a grep happened to find one.
ACCEPTED_UNUSED_SECRETS = {
    "ALEKSEI_LOGIN_PASSWORD",
    "ELENA_LOGIN_PASSWORD",
    "INFISICAL_VAULT_FILE_PASSPHRASE",
}


def check_secrets():
    """Secrets declared in infisical (names only — values never read) that are referenced
    nowhere across the repos → candidates to retire (attack-surface hygiene)."""
    if shutil.which("infisical") is None:
        add(SKIP, "secrets", "declared-vs-used", "infisical not on PATH")
        return
    keys = _declared_secret_names()
    if keys is None:
        add(SKIP, "secrets", "declared-vs-used", "infisical injection failed (session?)")
        return
    if not keys:
        add(SKIP, "secrets", "declared-vs-used",
            "injected 0 secret names — refusing to report 'all referenced' on an empty set")
        return
    used = set()
    keyset = set(keys)
    # No \b — git grep -E is POSIX ERE where \b is not a word boundary (matches nothing).
    # Plain alternation may over-match a name that is a substring of another; that only
    # ever marks a secret USED, so the "unused" verdict stays conservative (no false alarms).
    alt = "|".join(re.escape(k) for k in keys)
    for repo in REPOS:
        d = MONO_ROOT / repo
        if not (d / ".git").exists():
            continue
        g = subprocess.run(["git", "grep", "-hoE", rf"({alt})"], cwd=d, capture_output=True, text=True)
        used.update(t for t in g.stdout.split() if t in keyset)
    unused_all = [k for k in keys if k not in used]
    accepted = [k for k in unused_all if k in ACCEPTED_UNUSED_SECRETS]
    unused = [k for k in unused_all if k not in ACCEPTED_UNUSED_SECRETS]
    if unused:
        shown = ", ".join(unused[:12]) + (f" +{len(unused) - 12} more" if len(unused) > 12 else "")
        add(WARN, "secrets", "declared-vs-used",
            f"{len(unused)}/{len(keys)} declared secrets referenced in no repo (advisory — some are "
            f"deploy/runtime-only): {shown}")
    else:
        add(PASS, "secrets", "declared-vs-used", f"all {len(keys)} declared secrets referenced or accepted")
    if accepted:
        add(PASS, "secrets", "accepted-ops-only",
            f"{len(accepted)} accepted (ops-only, never read by code): {', '.join(sorted(accepted))}")


# ── SECURITY: database grants (T122 AC6 / T123 AC4) ───────────────────────────────────
# WHY: two P0s in one day came from database CONFIGURATION that no gate watched — a public
# storage bucket serving client contracts, and 15 SECURITY DEFINER functions executable by
# anon. Both were found by chance while ranking a queue.
#
# It also catches a subtler failure: a REVOKE that does nothing. `REVOKE ... FROM anon`
# leaves a grant made to PUBLIC intact, so the migration succeeds, raises no error, and
# changes nothing. Reading the SQL will not tell you; asserting the end state will.
#
# The allowlist is the RLS helper set: policies call these while executing AS the querying
# role, so they MUST stay callable or anon-visible tables break.
DEFINER_ANON_ALLOWED = {
    "is_admin", "has_role", "get_user_roles", "wom_role_set",
    "wom_acting_is", "wom_acting_in", "wom_acting_role",
}
PUBLIC_BUCKETS_ALLOWED = {"assets", "blueprints", "cv", "news", "post-images",
                          "public-images", "snapshots"}

# T123 AC3: `authenticated` is a bigger allowlist than `anon` because a definer function CAN be
# safely reachable by signed-in users — but only when the function authorizes IN ITS BODY. Each
# name here is on the list for a stated reason, not because it happened to be granted:
#   * archive_*/restore_* raise 42501 unless public.is_admin() (T68)
#   * get_provider_quotas got the same guard in T123 AC3
#   * the RLS helper set reads the caller's own claims and must stay callable
# Adding a name here without an in-body guard is the mistake this check exists to prevent.
DEFINER_AUTHENTICATED_ALLOWED = DEFINER_ANON_ALLOWED | {"get_provider_quotas"} | {
    f"{verb}_{ent}"
    for verb in ("archive", "restore")
    for ent in ("blueprint", "contract", "interview", "job_application",
                "post", "profile", "project", "proposal")
}


def _psql_rows(sql):
    """One column, one row per line — same access path as check_migrations (psql via infisical).
    Returns None when the DB cannot be reached, so callers can WARN rather than pass silently."""
    if shutil.which("infisical") is None:
        return None
    q = f'psql "$DATABASE_URL" -tAc "{sql}"'
    r = subprocess.run(["infisical", "run", "--env=beta", "--silent", "--", "sh", "-c", q],
                       cwd=WEB_ROOT, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        return None
    return [l.strip() for l in r.stdout.splitlines() if l.strip()]


def check_db_grants(psql=_psql_rows):
    print("\n▶ DB GRANTS — definer functions + public buckets")

    # An ACL entry is `grantee=PRIVS/grantor`. A grant to PUBLIC has an EMPTY grantee, so the
    # entry STARTS with '='. Matching '%=X/%' instead — as a first attempt here did — matches
    # every entry ever written (`postgres=X/postgres` contains it) and flagged 25 healthy
    # functions. A check that cries wolf gets ignored, so the pattern has to be exact.
    # proacl IS NULL means the default applies, and the default for a function is EXECUTE to
    # PUBLIC — so NULL is a real finding, not an absence of one.
    q_fn = ("SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
            "WHERE n.nspname='public' AND p.prosecdef AND ("
            "  p.proacl IS NULL"
            "  OR EXISTS (SELECT 1 FROM unnest(p.proacl) a WHERE a::text LIKE '=%')"
            "  OR EXISTS (SELECT 1 FROM unnest(p.proacl) a WHERE a::text LIKE 'anon=%'))")
    rows = psql(q_fn)
    if rows is None:
        add(WARN, "grants", "definer functions", "could not query (DB unreachable?)")
    else:
        offenders = sorted({r for r in rows if r and r not in DEFINER_ANON_ALLOWED})
        if offenders:
            add(FAIL, "grants", "anon-executable SECURITY DEFINER",
                f"{len(offenders)}: {', '.join(offenders[:6])}"
                f"{' …' if len(offenders) > 6 else ''} — revoke FROM PUBLIC (not from anon)")
        else:
            add(PASS, "grants", "definer functions", "none anon-executable outside the allowlist")

    # T123 AC3 — the same assertion one role out. `anon` and `authenticated` are separate checks
    # rather than one, because they have different allowlists: an in-body is_admin() guard makes a
    # function safe for signed-in callers and still says nothing about anonymous ones.
    q_auth = ("SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
              "WHERE n.nspname='public' AND p.prosecdef AND ("
              "  p.proacl IS NULL"
              "  OR EXISTS (SELECT 1 FROM unnest(p.proacl) a WHERE a::text LIKE '=%')"
              "  OR EXISTS (SELECT 1 FROM unnest(p.proacl) a WHERE a::text LIKE 'authenticated=%'))")
    rows = psql(q_auth)
    if rows is None:
        add(WARN, "grants", "definer functions (authenticated)", "could not query (DB unreachable?)")
    else:
        offenders = sorted({r for r in rows if r and r not in DEFINER_AUTHENTICATED_ALLOWED})
        if offenders:
            add(FAIL, "grants", "authenticated-executable SECURITY DEFINER",
                f"{len(offenders)}: {', '.join(offenders[:6])}"
                f"{' …' if len(offenders) > 6 else ''} — add an in-body guard, or revoke "
                f"FROM PUBLIC *and* FROM authenticated")
        else:
            add(PASS, "grants", "definer functions (authenticated)",
                "none authenticated-executable outside the allowlist")

    # T49 — mutable search_path. A function with no search_path setting resolves unqualified names
    # against the CALLER's path; for a SECURITY DEFINER function that is a privilege-escalation
    # primitive. This is a standing check for the same reason AC4 is: T49 was filed against a list
    # of five names, four of which were already fixed and one of which no longer exists, while
    # nine real offenders sat unlisted. Assert the property, never the roster.
    q_path = ("SELECT n.nspname||'.'||p.proname FROM pg_proc p "
              "JOIN pg_namespace n ON n.oid=p.pronamespace "
              "WHERE n.nspname IN ('public','gamification') AND p.prokind='f' AND ("
              "  p.proconfig IS NULL"
              "  OR NOT EXISTS (SELECT 1 FROM unnest(p.proconfig) c WHERE c LIKE 'search_path=%'))")
    rows = psql(q_path)
    if rows is None:
        add(WARN, "grants", "function search_path", "could not query")
    else:
        offenders = sorted({r for r in rows if r})
        if offenders:
            add(FAIL, "grants", "mutable search_path",
                f"{len(offenders)}: {', '.join(offenders[:6])}"
                f"{' …' if len(offenders) > 6 else ''} — ALTER FUNCTION … SET search_path = ''")
        else:
            add(PASS, "grants", "function search_path", "all public/gamification functions pinned")

    rows = psql("SELECT name FROM storage.buckets WHERE public")
    if rows is None:
        add(WARN, "grants", "public buckets", "could not query")
    else:
        offenders = sorted({r for r in rows if r and r not in PUBLIC_BUCKETS_ALLOWED})
        if offenders:
            add(FAIL, "grants", "unexpected public bucket",
                f"{', '.join(offenders)} — public buckets serve objects to the open internet")
        else:
            add(PASS, "grants", "public buckets", "all public buckets are on the allowlist")


def check_iac_drift():
    """T125: is the infrastructure-as-code state still describing reality?

    WHY: the Cloudflare stack silently diverged for months — it could not even
    authenticate, so nobody noticed the config still described the retired Pages
    architecture. The first authenticated plan wanted to create 7 records that already
    existed, two of them pointing at Pages projects that no longer exist.

    `plan`/`drift` are READ-ONLY. This never applies anything — and it must not, because
    the stack still runs deploy scripts via local-exec null_resources (TECH-DEBT D22).
    """
    print("\n▶ IAC — terraform drift")
    try:
        iac = json.loads(SDLC_JSON.read_text()).get("iac") if SDLC_JSON.is_file() else None
    except (OSError, ValueError) as e:  # config missing/unparseable — NOT a bug in this script
        add(WARN, "iac", "config", f"cannot read {SDLC_JSON.name} ({type(e).__name__})")
        return
    if not iac:
        add(SKIP, "iac", "declared", "no `iac` block in .w0m/sdlc.json")
        return
    if not shutil.which(iac.get("tool", "terraform")):
        add(WARN, "iac", iac.get("tool", "terraform"), "not installed — drift unchecked")
        return

    cmd = iac.get("drift")
    if not cmd:
        add(SKIP, "iac", "drift", "no drift command configured")
        return
    # shell=False + shlex: the command comes from .w0m/sdlc.json, not from user input, but a
    # shell here would propagate ambient settings for no benefit — the configured commands are
    # plain recipes (`just tf-drift`). Keeps the SAST gate honest instead of suppressed.
    r = subprocess.run(shlex.split(cmd), cwd=WEB_ROOT, capture_output=True, text=True, timeout=600)
    out = (r.stdout or "") + (r.stderr or "")
    # `-refresh-only` speaks a different dialect from a normal plan: drift shows up as
    # "Objects have changed outside of Terraform", NOT as a "Plan: N to add" line. Matching
    # only the latter reported "indeterminate" on a run that had plenty to say.
    changed = out.count("has changed") + out.count("Objects have changed outside")
    if "No changes" in out and not changed:
        add(PASS, "iac", "terraform", "state matches reality")
    elif changed:
        add(WARN, "iac", "terraform drift",
            f"{changed} object(s) changed outside Terraform — review with `{iac.get('plan')}` "
            f"(NEVER apply from a gate)")
    elif re.search(r"Plan:\s*(\d+) to add,\s*(\d+) to change,\s*(\d+) to destroy", out):
        m = re.search(r"Plan:\s*(\d+) to add,\s*(\d+) to change,\s*(\d+) to destroy", out)
        a, c, dstr = m.groups()
        add(WARN, "iac", "terraform drift",
            f"{a} to add / {c} to change / {dstr} to destroy — review with `{iac.get('plan')}` "
            f"(NEVER apply from a gate)")
    elif "Error" in out:
        first = next((l.strip() for l in out.splitlines() if l.strip().startswith("Error")), "error")
        add(WARN, "iac", "terraform", f"could not evaluate — {first[:90]}")
    else:
        add(WARN, "iac", "terraform", "drift indeterminate (unrecognised output)")


# ── KNOWLEDGE: is the code graph a current answer or a stale one? ───────────────
def check_knowledge():
    """T96 AC1's fourth family — knowledge/docs freshness.

    `CLAUDE.md` makes `just ask` the DEFAULT first action for any where-is-X question, so a
    stale graph does not merely inconvenience: it answers confidently from an old commit.
    Composes the existing `graph_health.py` rather than re-deriving freshness here.
    """
    print("\n▶ KNOWLEDGE — code-graph freshness")
    script = WEB_ROOT / "project" / "scripts" / "graph_health.py"
    if not script.exists():
        add(SKIP, "knowledge", "graph freshness", "graph_health.py not found")
        return
    try:
        r = subprocess.run([sys.executable, str(script), "--json"],
                           cwd=WEB_ROOT, capture_output=True, text=True, timeout=120)
        data = json.loads(r.stdout)
    except Exception as e:
        add(SKIP, "knowledge", "graph freshness", f"graph_health unreadable ({type(e).__name__})")
        return

    rows = data.get("rows", [])
    if not rows:
        # An empty corpus is a FAIL, not a green: it is the shape this estate keeps re-finding.
        add(FAIL, "knowledge", "graph freshness", "graph_health returned zero repos")
        return

    missing = [x["tag"] for x in rows if not x.get("graph")]
    stale = [(x["tag"], x["stale_commits"]) for x in rows
             if isinstance(x.get("stale_commits"), int) and x["stale_commits"] > 0]
    unknown = [x["tag"] for x in rows if x.get("graph") and x.get("stale_commits") is None]
    out_of_union = [x["tag"] for x in rows if not x.get("in_union")]

    add(WARN if missing else PASS, "knowledge", "per-repo graph present",
        f"{len(rows) - len(missing)}/{len(rows)} indexed" + (f"; missing: {', '.join(missing)}" if missing else ""))
    add(WARN if stale else PASS, "knowledge", "graph vs HEAD",
        "; ".join(f"{t} {n} commit(s) behind" for t, n in stale) if stale else "every graph at HEAD")
    add(WARN if out_of_union else PASS, "knowledge", "union coverage",
        f"not in union: {', '.join(out_of_union)}" if out_of_union else
        f"all {len(rows)} repos in the union")
    if unknown:
        # Not measurable is not the same as fresh — say so rather than counting it as a pass.
        add(SKIP, "knowledge", "graph vs HEAD (unmeasured)",
            f"staleness not computable for: {', '.join(unknown)}")


def check_backups():
    """T229 AC2 — a missed backup run must be VISIBLE on the standing surface, not only to whoever
    remembers to run the recipe.

    ⚠️ Deliberately OUTSIDE --quick, i.e. not on every push. The reasoning is the one check_knowledge
    already states: once a backup ages past its limit it stays past it until someone acts, so a
    pre-push placement would warn on every push for days and train people to scroll past it — which
    is how the warning that matters gets missed. The full audit runs when someone is actually
    looking, and `just backup-freshness` is there for a direct answer.

    Reported as WARN rather than FAIL: this audit is advisory, and the blocking judgement about
    backup cadence belongs to T229's own gate, not to a status sweep.
    """
    print("\n▶ BACKUPS — is there a recent artefact on disk")
    r = subprocess.run(["just", "backup-freshness"], cwd=API_ROOT, capture_output=True, text=True)
    detail = (r.stdout + r.stderr).strip().splitlines()
    # T257 AC2 — text markers summarise a probe exactly as the glyphs do; both accepted while
    # producers convert. A probe that switched to [OK]/[FAIL] before this line existed would have
    # produced a BLANK summary, which reads as "the probe said nothing" rather than as a break.
    _MARKERS = ("✅", "❌", "✗", "[OK]", "[FAIL]", "[PASS]", "[WARN]")
    summary = "; ".join(l.strip() for l in detail if l.strip().startswith(_MARKERS))[:300]
    add(PASS if r.returncode == 0 else WARN, "backups", "freshness",
        summary or ("ok" if r.returncode == 0 else "backup-freshness failed"))


def check_upwork_sync():
    """T155 AC7 — standing Upwork sync health gate: deduplication, cover letters, room ceiling, message coverage."""
    if shutil.which("infisical") is None:
        add(SKIP, "upwork-sync", "coverage-and-health", "infisical not on PATH")
        return
    r = subprocess.run(
        ["infisical", "run", "--env=beta", "--silent", "--", sys.executable, str(WEB_ROOT / "project" / "scripts" / "upwork_sync_health.py")],
        cwd=API_ROOT, capture_output=True, text=True
    )
    if r.returncode != 0:
        tail = ((r.stderr or r.stdout).strip().splitlines() or ["health probe failed"])[-1]
        add(FAIL if "FAIL" in r.stdout else WARN, "upwork-sync", "coverage-and-health", tail[:120])
        return
    summary_lines = [l.strip() for l in r.stdout.splitlines() if l.strip().startswith(("✅", "❌", "⚠️"))]
    summary = "; ".join(summary_lines[-2:]) if summary_lines else "ok"
    add(PASS, "upwork-sync", "coverage-and-health", summary)


def check_connectors() -> None:
    """T95 AC4 + T99 AC8 — services-policy.json services[] vs docs/backend/connectors/, plus live token encryption & column_privileges."""
    r = subprocess.run(["just", "connector-check"], cwd=API_ROOT, capture_output=True, text=True)
    detail = (r.stdout + r.stderr).strip().splitlines()
    _MARKERS = ("✅", "❌", "✗", "[OK]", "[FAIL]", "[PASS]", "[WARN]", "--")
    summary = "; ".join(l.strip() for l in detail if l.strip().startswith(_MARKERS))[:300]
    add(PASS if r.returncode == 0 else FAIL, "connectors", "doc-coverage",
        summary or ("ok" if r.returncode == 0 else "connector-check failed"))

    if shutil.which("infisical") is None:
        add(SKIP, "connectors", "token-encryption-and-grants", "infisical not on PATH")
        return
    probe = WEB_ROOT / "project" / "scripts" / "t506_security_pii_probe.py"
    r_tok = subprocess.run(
        ["infisical", "run", "--env=beta", "--silent", "--", sys.executable, str(probe), "--live"],
        cwd=API_ROOT, capture_output=True, text=True,
    )
    tok_lines = (r_tok.stdout + r_tok.stderr).strip().splitlines()
    tok_summary = "; ".join(l.strip() for l in tok_lines if l.strip().startswith(_MARKERS))[:300]
    add(PASS if r_tok.returncode == 0 else FAIL, "connectors", "token-encryption-and-grants",
        tok_summary or ("ok" if r_tok.returncode == 0 else "connector token encryption/grant check failed"))


def check_deep():
    print("\n▶ DEEP — DB / infisical-backed drift")
    # `tech-debt` is no longer a DB census (retired 2026-07-21) — it is a scoped grep and
    # needs neither infisical nor the DB. Kept here so the deep sweep still surfaces markers.
    for name, recipe in (("tech-debt markers", "tech-debt"), ("lexicon-lint", "lexicon-lint")):
        r = subprocess.run(["just", recipe], cwd=API_ROOT, capture_output=True, text=True)
        add(PASS if r.returncode == 0 else WARN, "deep", name,
            "ok" if r.returncode == 0 else "failed (DB/infisical?)")
    check_migrations()
    check_secrets()
    check_upwork_sync()
    check_connectors()


def write_report(head, args):
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = WEB_ROOT / "docs" / "audit_and_research" / f"W0M-STATUS-{day}.md"
    counts = {lvl: sum(1 for r in results if r[0] == lvl) for lvl in (PASS, WARN, FAIL, SKIP)}
    # T96 AC3 — SKIP is part of the headline, never folded into the pass count. A check that did
    # not run is NOT a check that passed, and an aggregate that hides its skipped members
    # manufactures the confidence it exists to provide (the T160 lesson, restated).
    lines = [f"# w0m Status / Audit — {stamp}", "",
             f"HEAD `{head[:8]}` · mode `{'quick' if args.quick else ('deep' if args.deep else 'full')}`", "",
             f"**{counts[FAIL]} fail · {counts[WARN]} warn · {counts[SKIP]} NOT RUN · {counts[PASS]} pass**", ""]
    if counts[SKIP]:
        lines += [f"> ⏭️ **{counts[SKIP]} check(s) DID NOT RUN** — this report covers less than it "
                  "appears to. Each is listed below with the reason.", ""]
        lines += [f"> · `{section}` / {name} — {detail}"
                  for lvl, section, name, detail in results if lvl == SKIP]
        lines += [""]
    lines += ["| Level | Section | Check | Detail |", "|---|---|---|---|"]
    for lvl, section, name, detail in results:
        lines.append(f"| {lvl} | {section} | {name} | {detail} |")
    lines.append("")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n")
    print(f"\n[NOTE] report → {out.relative_to(MONO_ROOT)}")


def main():
    ap = argparse.ArgumentParser(description="w0m full audit/status (T96)")
    ap.add_argument("--quick", action="store_true", help="git+spec only (no network)")
    ap.add_argument("--deep", action="store_true", help="+ markers/lexicon + migrations drift (lexicon needs infisical)")
    ap.add_argument("--no-report", action="store_true", help="don't write the md report")
    ap.add_argument("--scope-diff", metavar="REF", default=None,
                    help="scope spec-drift and openspec validate to changes vs REF (e.g. origin/beta) — used by the pre-push hook")
    args = ap.parse_args()

    head = git("rev-parse", "HEAD").stdout.strip()
    print(f"w0m audit — HEAD {head[:8]} — {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}")

    # T96 AC4 — two tiers, each honest about its coverage. The fast tier is the pre-push subset;
    # it must state what it does NOT cover, because a gate that is silent about its blind spot is
    # read as a full sweep by the next person.
    tier = "quick" if args.quick else ("deep" if args.deep else "full")
    NOT_COVERED = {
        "quick": ["conform (DS + decommission drift)", "diff (local vs deployed)",
                  "health (apps + edge fns + worker)", "exposure (MCP)",
                  "host (macOS controls, startup baseline, TCC)",
                  "authz (DB probes & admin-client ratchet)",
                  "platform (cv-leak-check, supabase-limits)",
                  "backups (freshness of the newest dump/storage copy)",
                  "knowledge (code-graph freshness)",
                  "deep (migrations, secrets, db-grants, iac, connectors)"],
        "full":  ["deep (migrations, secrets, db-grants, iac, connectors) — run `--deep`"],
        "deep":  [],
    }
    missing = NOT_COVERED[tier]
    print(f"   tier `{tier}` — " + (
        "covers every family" if not missing
        else "DOES NOT COVER: " + "; ".join(missing)))
    if missing:
        add(INFO, "tier", f"{tier} coverage", "does not cover: " + "; ".join(missing))

    check_drift(scope_diff=args.scope_diff)
    # Runs even in --quick: without an API key this is a local staleness read, and the pre-push
    # hook is the most frequent place a stale reputation state should be surfaced.
    check_security()
    if not args.quick:
        check_conform()
        check_diff(head)
        check_health()
        # T229 AC2 — local and cheap, but out of --quick for the same reason as check_knowledge:
        # a stale backup stays stale, so a per-push warning becomes wallpaper.
        check_backups()
        # T96 AC1's fourth family. Local and cheap, but kept OUT of --quick deliberately: the
        # graph is routinely a commit or two behind between pushes, and a WARN on every
        # pre-push would train people to ignore the one that matters.
        check_knowledge()
        # Outside --quick BY DESIGN — see check_exposure(): T154 AC6 forbids a pre-push gate, and
        # --quick is the pre-push subset, so the constraint is enforced by the call site.
        check_exposure()
        check_host()
        check_authz()
        check_platform_security()
    if args.deep:
        check_deep()
        check_db_grants()
        check_iac_drift()

    if not args.no_report:
        write_report(head, args)

    fails = sum(1 for r in results if r[0] == FAIL)
    warns = sum(1 for r in results if r[0] == WARN)
    skips = sum(1 for r in results if r[0] == SKIP)
    # T96 AC3 — a run with skipped members must NOT render as a bare ✅. The exit code is
    # deliberately unchanged (FAIL still gates; the pre-push hook depends on that), but the
    # verdict line can no longer read green while checks silently did not run.
    verdict = "❌" if fails else ("⚠️ " if warns else ("⏭️ " if skips else "✅"))
    print(f"\n{verdict} audit: {fails} fail · {warns} warn · {skips} NOT RUN · "
          f"{sum(1 for r in results if r[0] == PASS)} pass")
    if skips:
        print(f" [SKIP] {skips} check(s) DID NOT RUN — this audit covers less than it appears to:")
        for lvl, section, name, detail in results:
            if lvl == SKIP:
                print(f"      · {section}/{name} — {detail}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
