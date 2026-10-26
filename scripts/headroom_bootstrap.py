#!/usr/bin/env python3
"""Headroom provisioning + status for the w0m estate.

Three modes, matching the house convention (cf. discovery.py, deps_sync.py):

    headroom_bootstrap.py            advisory status report, exit 0
    headroom_bootstrap.py --enforce  same checks, exit 1 on any FAIL
    headroom_bootstrap.py --apply    provision what is missing, then re-check
    headroom_bootstrap.py --json     machine-readable (grounding)

Why this is a script and not a justfile blob: provisioning Headroom means stepping
around four traps that a one-liner cannot express, every one of them found the hard
way on 2026-08-03 (see the `headroom-context-compression` memory):

  1. `install apply --providers auto` ABORTED THE WHOLE DEPLOYMENT when it found the
     retired openclaw binary at /opt/homebrew/bin. That binary was uninstalled on
     2026-08-10, so this specific trigger is gone — but the flags stay
     `--providers manual --target claude`, because the failure mode is auto-detection
     of ANY stray provider on the host, not openclaw in particular.
  2. `--memory` leaves the backend at initialized:false, which pins /readyz at 503,
     which makes `install apply` fail outright. Never pass it until the missing
     sentence_transformers backend is fixed.
  3. Headroom installs serena as its default code-memory MCP, and serena refuses to
     boot unless ~/.serena/serena_config.yml has a `projects` key.
  4. A custom ANTHROPIC_BASE_URL silently disables Claude Code's on-demand tool
     loading (#746) and the 1M context window (#1158). ENABLE_TOOL_SEARCH must be
     set; the 1M window is reported, not auto-enabled — that is the owner's call.

NO VACUOUS GREEN: a check whose evidence is missing reports FAIL, never PASS. An
empty corpus is a failure, not a pass — that rule is the estate's most-repeated
lesson and this script is not exempt from it.
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

PORT = 8787
PROXY = f"http://127.0.0.1:{PORT}"
SETTINGS = Path.home() / ".claude" / "settings.json"
SERENA_CFG = Path.home() / ".serena" / "serena_config.yml"
CLAUDE_JSON = Path.home() / ".claude.json"
HEADROOM_LEDGER = Path.home() / ".headroom" / "mcp_installs.json"

PASS, WARN, FAIL = "pass", "warn", "fail"
MARK = {PASS: "✅", WARN: "⚠️ ", FAIL: "❌"}


class Report:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def add(self, check: str, status: str, detail: str, fix: str = "") -> None:
        self.rows.append({"check": check, "status": status, "detail": detail, "fix": fix})

    @property
    def failed(self) -> bool:
        return any(r["status"] == FAIL for r in self.rows)

    def render(self) -> str:
        width = max((len(r["check"]) for r in self.rows), default=10)
        lines = [f"Headroom · w0m provisioning status (port {PORT})", ""]
        for r in self.rows:
            lines.append(f"  {MARK[r['status']]} {r['check']:<{width}}  {r['detail']}")
            if r["fix"] and r["status"] != PASS:
                lines.append(f"     {'':<{width}}  → {r['fix']}")
        n_fail = sum(1 for r in self.rows if r["status"] == FAIL)
        n_warn = sum(1 for r in self.rows if r["status"] == WARN)
        lines += ["", f"{n_fail} failure(s), {n_warn} warning(s)"]
        return "\n".join(lines)


def headroom_bin() -> str | None:
    return shutil.which("headroom")


def run(args: list[str], timeout: int = 180) -> tuple[int, str]:
    """Run a command and return (rc, combined output).

    Uses subprocess timeout deliberately: the `timeout` binary on PATH here is a
    pyenv shim that raises ModuleNotFoundError, not GNU coreutils.
    """
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout}s"
    except FileNotFoundError as e:
        return 127, str(e)


def http_json(path: str, timeout: int = 5) -> dict | None:
    """GET a JSON endpoint on the local proxy. Returns None on any failure.

    Deliberately `http.client`, not `urllib`: the host and port are fixed
    constants and HTTPConnection speaks only HTTP, so no value of `path` can
    redirect this at a `file://` URL to read an arbitrary file. urllib.urlopen
    *does* honour file:// — that is a real footgun for a helper taking a dynamic
    path, and semgrep flags it correctly. Answered by construction rather than
    suppressed with a nosemgrep comment.
    """
    conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=timeout)
    try:
        conn.request("GET", "/" + path.lstrip("/"))
        resp = conn.getresponse()
        if resp.status != 200:
            return None
        return json.loads(resp.read())
    except (OSError, http.client.HTTPException, json.JSONDecodeError, TimeoutError):
        return None
    finally:
        conn.close()


# ── individual checks ───────────────────────────────────────────────────────────

def check_cli(rep: Report) -> bool:
    exe = headroom_bin()
    if not exe:
        rep.add("cli", FAIL, "headroom not on PATH",
                'pip install "headroom-ai[all]"  (or: uv tool install --python 3.13 "headroom-ai[all]")')
        return False
    rc, out = run([exe, "--version"], timeout=60)
    ver = out.strip().split()[-1] if rc == 0 and out.strip() else "unknown"
    rep.add("cli", PASS if rc == 0 else FAIL, f"headroom {ver} at {exe}")
    return rc == 0


def check_serena(rep: Report, apply: bool) -> None:
    """Serena was originally installed as Headroom's code-memory MCP dependency (T162/T166).

    Under T170 it is w0m-governed as a maintained fork (`v1.7.0-w0m.1`) with native .astro
    support. We must ensure:
      1. ~/.serena/serena_config.yml has `projects:` key so Serena can boot.
      2. ~/.headroom/mcp_installs.json does NOT claim ownership of `serena` for `claude`,
         which would allow Headroom's auto-installer to overwrite w0m's fork with stock
         unpinned serena-agent on re-wrap.
      3. ~/.claude.json has `serena` registered pointing to the w0m-pinned fork.
    """
    # 1. Config projects key
    if not SERENA_CFG.exists():
        rep.add("serena cfg", WARN, "no ~/.serena/serena_config.yml (serena not installed yet)")
    else:
        text = SERENA_CFG.read_text()
        has_projects = any(
            line.split("#", 1)[0].strip().startswith("projects:") for line in text.splitlines()
        )
        if has_projects:
            rep.add("serena cfg", PASS, "`projects` key present — serena can boot")
        elif apply:
            SERENA_CFG.write_text(text.rstrip("\n") + "\nprojects: []\n")
            rep.add("serena cfg", PASS, "added `projects: []` (serena self-populates the rest)")
        else:
            rep.add("serena cfg", FAIL, "`projects` key MISSING — serena will refuse to boot",
                    "just headroom-bootstrap  (adds `projects: []`)")

    # 2. Headroom install ledger ownership (T170: decoupled from Headroom auto-ownership)
    if HEADROOM_LEDGER.exists():
        try:
            ledger = json.loads(HEADROOM_LEDGER.read_text(encoding="utf-8"))
            claude_installs = (ledger.get("agents") or {}).get("claude") or {}
            if "serena" in claude_installs:
                if apply:
                    del claude_installs["serena"]
                    if not claude_installs:
                        (ledger.get("agents") or {}).pop("claude", None)
                    if not ledger.get("agents"):
                        ledger.pop("agents", None)
                    HEADROOM_LEDGER.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                    rep.add("serena ledger", PASS, "cleared serena from headroom ledger (governed by w0m T170)")
                else:
                    rep.add("serena ledger", FAIL, "headroom ledger claims serena ownership — will overwrite fork on wrap",
                            "run `headroom-bootstrap --apply` or remove serena from ~/.headroom/mcp_installs.json")
            else:
                rep.add("serena ledger", PASS, "headroom ledger unentangled (user-managed, w0m T170)")
        except Exception as e:
            rep.add("serena ledger", WARN, f"failed to read headroom ledger: {e}")

    # 3. Claude Code MCP registration
    if CLAUDE_JSON.exists():
        try:
            cfg = json.loads(CLAUDE_JSON.read_text(encoding="utf-8"))
            mcp = (cfg.get("mcpServers") or {}).get("serena")
            if not mcp:
                rep.add("serena spec", WARN, "serena missing from ~/.claude.json")
            else:
                args = " ".join(mcp.get("args") or [])
                if "v1.7.0-w0m.1" in args:
                    rep.add("serena spec", PASS, "pinned to fork v1.7.0-w0m.1 with .astro LSP")
                else:
                    rep.add("serena spec", WARN, f"not pointing to w0m fork v1.7.0-w0m.1: {args[:60]}...")
        except Exception as e:
            rep.add("serena spec", WARN, f"failed to read ~/.claude.json: {e}")


def check_daemon(rep: Report, exe: str, apply: bool) -> None:
    # Check Homebrew service first (T456)
    lrc, lout = run(["launchctl", "list"], timeout=10)
    if lrc == 0 and ("sh.brew.headroom" in lout or "homebrew.mxcl.headroom" in lout):
        rep.add("daemon", PASS, "managed Homebrew service (sh.brew.headroom) running")
        return

    rc, out = run([exe, "install", "status"], timeout=90)
    installed = rc == 0 and "Profile:" in out

    if not installed and apply:
        rep.add("daemon", WARN, "no deployment — installing (manual/claude, no --memory)…")
        irc, iout = run([
            exe, "install", "apply",
            "--preset", "persistent-service", "--runtime", "python", "--scope", "user",
            "--providers", "manual", "--target", "claude",   # trap 1: NOT --providers auto
            "--port", str(PORT), "--mode", "cache", "--no-telemetry",  # trap 2: NO --memory
        ], timeout=420)
        if irc != 0:
            rep.add("daemon", FAIL, f"install failed: {iout.strip().splitlines()[-1][:160] if iout.strip() else 'no output'}")
            return
        rc, out = run([exe, "install", "status"], timeout=90)
        installed = rc == 0 and "Profile:" in out

    if not installed:
        rep.add("daemon", FAIL, "no persistent deployment installed",
                "just headroom-bootstrap")
        return

    healthy = "Healthy:    yes" in out or "Healthy: yes" in out
    running = "Status:     running" in out or "Status: running" in out
    rep.add("daemon", PASS if (healthy and running) else FAIL,
            f"deployment 'default' {'running + healthy' if healthy and running else 'INSTALLED BUT NOT HEALTHY'}",
            "" if healthy and running else f"{exe} install restart")


def check_proxy(rep: Report) -> None:
    """Live reachability. Missing evidence is a FAIL, not a pass."""
    health = http_json("/health")
    if health is None:
        rep.add("proxy", FAIL, f"not reachable at {PROXY}", "headroom install restart")
        return
    ready = bool(health.get("ready"))
    rep.add("proxy", PASS if ready else FAIL,
            f"{PROXY} ready={ready} v{health.get('version', '?')}")
    mem = (health.get("checks") or {}).get("memory") or {}
    if mem.get("enabled") and not mem.get("ready"):
        rep.add("memory backend", WARN,
                f"enabled but initialized={mem.get('initialized')} — known broken",
                "leave --memory OFF; needs the sentence_transformers vector store")


def check_routing(rep: Report) -> None:
    if not SETTINGS.exists():
        rep.add("routing", FAIL, "no ~/.claude/settings.json")
        return
    try:
        env = (json.loads(SETTINGS.read_text()).get("env") or {})
    except json.JSONDecodeError as e:
        rep.add("routing", FAIL, f"settings.json is not valid JSON: {e}")
        return

    base = env.get("ANTHROPIC_BASE_URL", "")
    routed = base.startswith("http://127.0.0.1") or base.startswith("http://localhost")
    # Deliberately labelled "routing cfg", not "routing": this row proves only what the
    # FILE says. Whether anything honours it is `check_observed`'s job — see its docstring.
    rep.add("routing cfg", PASS if routed else WARN,
            f"settings.json env ANTHROPIC_BASE_URL={base or '<unset>'} (config only — see `observed`)",
            "" if routed else f"headroom init --global --port {PORT} claude")

    if routed:
        # trap 4: a custom base URL silently disables on-demand tool loading (#746).
        tool_search = str(env.get("ENABLE_TOOL_SEARCH", "")).lower() in ("1", "true")
        rep.add("tool-search", PASS if tool_search else FAIL,
                f"ENABLE_TOOL_SEARCH={env.get('ENABLE_TOOL_SEARCH', '<unset>')}"
                + ("" if tool_search else " — every tool schema will eager-load (#746)"),
                "" if tool_search else 'add "ENABLE_TOOL_SEARCH": "true" to settings.json env')
        # trap 4b: the 1M window is lost behind a custom base URL. Owner's call, so WARN.
        rep.add("1M context", WARN,
                "disabled behind a custom base URL unless opted in (#1158)",
                "headroom wrap claude --1m, or drop routing to get it back")


def check_observed(rep: Report) -> None:
    """Did traffic ACTUALLY reach the proxy? Config is not behaviour.

    `check_routing` only proves ANTHROPIC_BASE_URL is written into settings.json.
    That is not the same as the running client using it, and on 2026-08-04 the two
    disagreed: settings.json said 127.0.0.1:8787, `headroom doctor` said "routed",
    and the proxy had served ZERO requests from the live session — because the
    caller's own environment already had ANTHROPIC_BASE_URL set, which wins over
    settings.json. A green built only on the config file is a vacuous green, which
    is this estate's most-repeated defect. So: report what the proxy actually saw.
    """
    env_url = os.environ.get("ANTHROPIC_BASE_URL", "")
    local = env_url.startswith("http://127.0.0.1") or env_url.startswith("http://localhost")
    rep.add("caller env", PASS if local else WARN,
            f"this process sees ANTHROPIC_BASE_URL={env_url or '<unset>'}"
            + ("" if local else " — overrides settings.json, so THIS caller bypasses the proxy"),
            "" if local else "a client that sets its own base URL cannot be routed from settings.json")

    stats = http_json("/stats")
    if stats is None:
        rep.add("observed", FAIL, "proxy /stats unreachable — cannot confirm any traffic")
        return
    lifetime = (stats.get("persistent_savings") or {}).get("lifetime") or {}
    by_model = (stats.get("persistent_savings") or {}).get("by_model") or {}
    total = lifetime.get("requests", 0)
    models = ", ".join(f"{m} ×{v.get('requests', 0)}" for m, v in sorted(by_model.items())) or "none"
    # No traffic ever, while routing is configured, means the routing does not work.
    rep.add("observed", PASS if total else FAIL,
            f"{total:,} request(s) served lifetime  |  {models}"
            + ("" if total else " — configured but NEVER used; the routing is not effective"),
            "" if total else "check whether the client overrides ANTHROPIC_BASE_URL itself")


def check_shell_exports(rep: Report) -> None:
    """`headroom init --global` edits ~/.zshrc, ~/.profile AND ~/.bashrc — every shell."""
    hit = [
        p.name for p in (Path.home() / ".zshrc", Path.home() / ".profile", Path.home() / ".bashrc")
        if p.exists() and "ANTHROPIC_BASE_URL" in p.read_text()
    ]
    if hit:
        rep.add("shell exports", WARN,
                f"proxy URL exported machine-wide in: {', '.join(hit)}",
                "any shell-launched Anthropic caller now routes through the proxy — re-check "
                "blast radius before adding one")
    else:
        rep.add("shell exports", PASS, "no machine-wide ANTHROPIC_BASE_URL export")


def check_savings(rep: Report) -> None:
    """Report Headroom's OWN compression separately from Anthropic's prompt cache.

    Conflating them is exactly how this tool flatters itself: it credits the 90%
    cache-read discount (which accrues with or without the proxy) as its own saving.
    """
    stats = http_json("/stats")
    if stats is None:
        rep.add("savings", WARN, "proxy /stats unreachable — no measurement")
        return
    comp = (stats.get("summary") or {}).get("compression") or {}
    removed = comp.get("total_tokens_removed", 0)
    reqs = (stats.get("summary") or {}).get("api_requests", 0)
    cache = ((stats.get("prefix_cache") or {}).get("by_provider") or {}).get("anthropic") or {}
    cache_read = cache.get("cache_read_tokens", 0)
    rep.add("savings", PASS,
            f"headroom compression: {removed:,} tok over {reqs:,} req  |  "
            f"anthropic prefix cache: {cache_read:,} read tok (NOT headroom's)")


# ── main ────────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="provision what is missing")
    ap.add_argument("--enforce", action="store_true", help="exit 1 on any FAIL")
    ap.add_argument("--json", action="store_true", dest="as_json", help="machine-readable")
    args = ap.parse_args()

    rep = Report()
    if check_cli(rep):
        exe = headroom_bin()
        assert exe  # check_cli returned True
        check_serena(rep, args.apply)
        check_daemon(rep, exe, args.apply)
        check_proxy(rep)
        check_routing(rep)
        check_observed(rep)
        check_shell_exports(rep)
        check_savings(rep)

    if args.as_json:
        print(json.dumps({"rows": rep.rows, "failed": rep.failed}, indent=2))
    else:
        print(rep.render())
        if args.apply:
            print("\nRestart Claude Code for routing changes to take effect.")

    return 1 if (args.enforce and rep.failed) else 0


if __name__ == "__main__":
    sys.exit(main())
