#!/usr/bin/env python3
"""automation_health.py (T652, T653) — Bounded staleness ceilings, hook guard & Free-Tier quota gate.

Prevents background syncs, knowledge-graph union merges, deploy static-snapshot producers, and
Cloudflare Free-Tier zone Single Redirect caps (`AgDR-0055`) from silently drifting or failing only
during live `cf-apply` (`AgDR-0025`).

Five fast offline checks (<0.5s, zero network I/O):
  1. `no-detached-git-log-hooks`: No `.husky/*` or `*pre_push*` hook launches `nohup` or redirects
     daemon errors into an unmonitored `.git/*.log` file.
  2. `no-swallowed-deploy-producers`: `justfile` never appends `|| true` to `snapshot-*.mjs` in
     `deploy-*` recipes and `_post-deploy-knowledge` refreshes canonical root instead of skipping
     under `W0M_RELEASE_WORKTREE` or swallowing failures with `|| true`.
  3. `bounded-ticket-mirror-lag`: Pending GitHub ticket mirror count (`tickets-sync-index.json` vs
     `.tasks/T*.md`) stays `<= automation_health.max_pending_ticket_mirror` (default 25).
  4. `bounded-graph-union-lag`: When `graphify` is installed (or `--union-manifest` is supplied),
     `~/.graphify/w0m-union-manifest.json` exists and every declared estate repo's commit distance
     from `merged_at` (and `graph.json -> built_at_commit`) to `HEAD` stays `<= max_graph_union_commit_lag`.
  5. `cf-free-tier-redirect-quota`: Every `cloudflare_ruleset` in `w0m-api/cloudflare/*.tf` targeting
     `phase = "http_request_dynamic_redirect"` declares `<= max_cf_single_redirect_rules_per_zone`
     (`10` on Cloudflare Free Tier, error `50001`) and uses zero Business-only regex operators.

Exit codes: 0 all checks passed · 1 one or more findings · 2 configuration error.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ESTATE_ROOT = Path(__file__).resolve().parents[1]

GRAPH_REPOS: dict[str, str] = {
    "w0m-web": "w0m-web",
    "w0m-api": "w0m-api",
    "w0m-cf": "w0m-cf",
    "w0m-skills": "w0m-skills",
    "w0m-ext": "w0m-ext",
    "w0m-sec": "w0m-sec",
    "w0m-mlx": "w0m-mlx/w0m-mlx",
}

NOHUP_RE = re.compile(r"(?:^|[;&|]\s*)nohup\b")
GIT_LOG_REDIRECT_RE = re.compile(r">+\s*[\"']?[^#\n]*\.git/[^\s\"']*\.log")
SNAPSHOT_SWALLOW_RE = re.compile(r"snapshot-[a-z0-9_-]+\.mjs[^\n]*\|\|\s*true")
KNOWLEDGE_SWALLOW_RE = re.compile(r"(?:knowledge-light|graph_global\.py)[^\n]*\|\|\s*true")


def load_policy(estate_root: Path) -> dict[str, Any]:
    sdlc_path = estate_root / ".w0m" / "sdlc.json"
    if not sdlc_path.is_file():
        raise ValueError(f"missing {sdlc_path}")
    raw: Any = json.loads(sdlc_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{sdlc_path} root must be a JSON object")
    block = raw.get("automation_health")
    if not isinstance(block, dict):
        return {
            "max_pending_ticket_mirror": 25,
            "max_graph_union_commit_lag": 25,
            "max_cf_single_redirect_rules_per_zone": 10,
            "forbid_detached_git_log_hooks": True,
            "forbid_swallowed_deploy_snapshots": True,
        }
    return dict(block)


def check_detached_git_log_hooks(estate_root: Path) -> list[str]:
    """Return violations where hook files use `nohup` or write background output to `.git/*.log`."""
    candidates: list[Path] = []
    for husky_dir in sorted(estate_root.glob("*/.husky")):
        if husky_dir.is_dir():
            for child in sorted(husky_dir.iterdir()):
                if child.is_file():
                    candidates.append(child)
    root_husky = estate_root / ".husky"
    if root_husky.is_dir():
        for child in sorted(root_husky.iterdir()):
            if child.is_file():
                candidates.append(child)
    scripts_dir = estate_root / "scripts"
    if scripts_dir.is_dir():
        for name in ("root_pre_push.py", "install_hooks.py"):
            p = scripts_dir / name
            if p.is_file():
                candidates.append(p)

    findings: list[str] = []
    for path in candidates:
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        rel = path.relative_to(estate_root)
        for idx, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            code_part = stripped.split("#", 1)[0]
            if NOHUP_RE.search(code_part):
                findings.append(f"{rel}:{idx}: detached `nohup` in hook (`{code_part.strip()[:90]}`)")
            elif GIT_LOG_REDIRECT_RE.search(code_part) and code_part.rstrip().endswith("&"):
                findings.append(f"{rel}:{idx}: background redirect to `.git/*.log` (`{code_part.strip()[:90]}`)")
    return findings


def _extract_recipe_body(justfile_text: str, recipe_name: str) -> list[tuple[int, str]]:
    lines = justfile_text.splitlines()
    header_re = re.compile(rf"^{re.escape(recipe_name)}(?:\s+[^:]*)?:")
    in_body = False
    out: list[tuple[int, str]] = []
    for idx, line in enumerate(lines, start=1):
        if not in_body:
            if header_re.match(line):
                in_body = True
            continue
        if line and not line[0].isspace():
            break
        out.append((idx, line))
    return out


def check_justfile_producers(estate_root: Path) -> list[str]:
    """Verify `justfile` neither swallows `snapshot-*.mjs` failures nor skips `_post-deploy-knowledge`."""
    jf = estate_root / "justfile"
    if not jf.is_file():
        return ["missing root justfile"]
    text = jf.read_text(encoding="utf-8", errors="replace")
    findings: list[str] = []

    for idx, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if SNAPSHOT_SWALLOW_RE.search(stripped):
            findings.append(f"justfile:{idx}: `snapshot-*.mjs` swallows failure with `|| true`")
        if KNOWLEDGE_SWALLOW_RE.search(stripped):
            findings.append(f"justfile:{idx}: knowledge/graph producer swallows failure with `|| true`")

    pdk = _extract_recipe_body(text, "_post-deploy-knowledge")
    if not pdk:
        findings.append("justfile: missing `_post-deploy-knowledge` recipe")
    else:
        body_non_comment = "\n".join(
            ln.strip() for _, ln in pdk if ln.strip() and not ln.strip().startswith("#")
        )
        if "knowledge refresh skipped in a release worktree" in body_non_comment:
            findings.append(
                "justfile:_post-deploy-knowledge: unconditionally skips refresh when W0M_RELEASE_WORKTREE is set"
            )
        if "graph_global.py" not in body_non_comment:
            findings.append(
                "justfile:_post-deploy-knowledge: does not invoke `graph_global.py` to keep global union fresh"
            )
    return findings


def compute_pending_mirror(estate_root: Path) -> tuple[int, int] | None:
    """Return `(pending, total)` ticket projections differing from `tickets-sync-index.json`."""
    web_root = estate_root / "w0m-web" if (estate_root / "w0m-web").is_dir() else estate_root
    idx_path = web_root / "project" / "tickets-sync-index.json"
    tickets_dir = estate_root / ".tasks"
    if not idx_path.is_file() or not tickets_dir.is_dir():
        return None

    scripts_dir = str(ESTATE_ROOT / "scripts")
    web_scripts_dir = str((ESTATE_ROOT / "w0m-web" / "project" / "scripts"))
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    if web_scripts_dir not in sys.path and Path(web_scripts_dir).is_dir():
        sys.path.insert(0, web_scripts_dir)

    import sync_github as sg  # noqa: PLC0415

    orig_dry = sg.DRY
    orig_tickets_dir = sg.TICKETS_DIR
    orig_index = sg.INDEX
    try:
        sg.DRY = True
        sg.TICKETS_DIR = tickets_dir
        sg.INDEX = idx_path
        recorded = sg.load_index()
        tickets = sg.load_tickets()
        pending = sum(
            1
            for t in tickets
            if recorded.get(t["id"]) != sg.projection_hash(sg.projection_of(t, sg.summary_of(t["id"])))
        )
        return pending, len(tickets)
    finally:
        sg.DRY = orig_dry
        sg.TICKETS_DIR = orig_tickets_dir
        sg.INDEX = orig_index


def check_ticket_mirror_ceiling(estate_root: Path, max_pending: int) -> tuple[bool, str]:
    res = compute_pending_mirror(estate_root)
    if res is None:
        return False, "tickets-sync-index.json or .tasks/ missing — refusing vacuous pass"
    pending, total = res
    if total == 0:
        return False, "0 tickets enumerated in .tasks/ — refusing vacuous pass"
    if pending > max_pending:
        return (
            False,
            f"{pending}/{total} ticket(s) pending GitHub mirror exceeds ceiling {max_pending} "
            "(run `just sync-tickets`)",
        )
    return True, f"ticket mirror lag within ceiling ({pending}/{total} <= {max_pending})"


def _git_distance(repo: Path, base_commit: str) -> int | None:
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("GIT_")
    }
    env["LC_ALL"] = "C"
    proc = subprocess.run(
        ["git", "-C", str(repo), "rev-list", "--count", f"{base_commit}..HEAD"],
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    txt = proc.stdout.strip()
    if proc.returncode == 0 and txt.isdigit():
        return int(txt)
    return None


def _built_at_commit(repo: Path) -> str | None:
    graph_json = repo / "graphify-out" / "graph.json"
    if not graph_json.is_file():
        return None
    try:
        # Read only first 4KB if Built_at_commit is near top? No, JSON key order puts built_at_commit anywhere;
        # use regex on raw bytes first to avoid parsing 29MB graph.json in <20ms!
        raw_bytes = graph_json.read_bytes()
    except OSError:
        return None
    m = re.search(rb'"built_at_commit"\s*:\s*"([0-9a-fA-F]{7,64})"', raw_bytes)
    if m:
        return m.group(1).decode("ascii")
    return None


def check_graph_union_ceiling(
    estate_root: Path,
    max_lag: int,
    *,
    manifest_path: Path | None = None,
    require_graphify: bool | None = None,
) -> tuple[bool, str]:
    has_graphify = (shutil.which("graphify") is not None) if require_graphify is None else require_graphify
    mpath = manifest_path or (Path.home() / ".graphify" / "w0m-union-manifest.json")
    if not has_graphify and manifest_path is None:
        return True, "graphify CLI absent on host — union lag check skipped cleanly"
    if not mpath.is_file():
        return False, f"missing graph union manifest at {mpath} (run `just graph-global --auto-rebuild-stale`)"
    try:
        raw_manifest: Any = json.loads(mpath.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"unreadable graph union manifest {mpath}: {exc}"
    if not isinstance(raw_manifest, dict) or not raw_manifest:
        return False, f"empty graph union manifest at {mpath} — refusing vacuous pass"

    checked = 0
    worst_lag = 0
    offenders: list[str] = []
    for tag, rel in GRAPH_REPOS.items():
        repo = estate_root / rel
        if not (repo / ".git").exists():
            continue
        checked += 1
        rec = raw_manifest.get(tag)
        if not isinstance(rec, dict):
            offenders.append(f"{tag}: missing from union manifest")
            continue
        merged_basis = rec.get("built_at_commit") or rec.get("head_at_merge")
        if not isinstance(merged_basis, str) or not merged_basis:
            offenders.append(f"{tag}: null merge basis in union manifest")
            continue
        lag = _git_distance(repo, merged_basis)
        if lag is None:
            # In shallow or rebased clones where merged_basis is unreachable, check built_at_commit if present
            built = _built_at_commit(repo)
            lag = _git_distance(repo, built) if built else None
        if lag is None:
            offenders.append(f"{tag}: recorded merge commit {merged_basis[:7]} unreachable from HEAD")
            continue
        worst_lag = max(worst_lag, lag)
        if lag > max_lag:
            offenders.append(f"{tag}: +{lag} commits behind union (ceiling {max_lag})")

        built = _built_at_commit(repo)
        if built:
            repo_lag = _git_distance(repo, built)
            if repo_lag is not None:
                worst_lag = max(worst_lag, repo_lag)
                if repo_lag > max_lag and not any(o.startswith(f"{tag}:") for o in offenders):
                    offenders.append(f"{tag}: graph.json +{repo_lag} commits behind HEAD (ceiling {max_lag})")

    if checked == 0:
        return False, "0 graph repos found on disk — refusing vacuous pass"
    if offenders:
        return (
            False,
            f"graph lag exceeded ceiling ({'; '.join(offenders)}) — run `just graph-global --auto-rebuild-stale`",
        )
    return True, f"graph union lag within ceiling across {checked} repo(s) (max lag +{worst_lag} <= {max_lag})"


CF_RULESET_HEADER_RE = re.compile(r'\bresource\s+"cloudflare_ruleset"\s+"([^"]+)"\s*\{')
CF_MASKED_HEADER_RE = re.compile(r'\bresource\s+"_+?"\s+"_+?"\s*\{')
CF_RULES_BLOCK_RE = re.compile(r"\brules\s*\{")
CF_DYNAMIC_REDIRECT_PHASE_RE = re.compile(r'\bphase\s*=\s*"http_request_dynamic_redirect"')
CF_BUSINESS_REGEX_OP_RE = re.compile(r"\bregex_replace\s*\(|\bhttp\.[a-z0-9_.]+\s+matches\b")


def _mask_hcl(text: str) -> tuple[str, str]:
    """Return `(structural_mask, no_comments)` with exact 1:1 character index alignment to `text`.

    - `structural_mask` replaces comments with spaces and string interiors with `_` so `{` / `}` depth
      and block headers never false-match inside HCL comments or escaped Wirefilter strings.
    - `no_comments` replaces only comments with spaces while preserving string literals intact.
    """
    n = len(text)
    mask_out = [" "] * n
    clean_out = [" "] * n
    i = 0
    state = "code"
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if state == "code":
            if ch == "#" or (ch == "/" and nxt == "/"):
                step = 2 if ch == "/" else 1
                state = "line_comment"
                i += step
                continue
            if ch == "/" and nxt == "*":
                state = "block_comment"
                i += 2
                continue
            if ch == '"':
                mask_out[i] = '"'
                clean_out[i] = '"'
                state = "string"
                i += 1
                continue
            mask_out[i] = ch
            clean_out[i] = ch
            i += 1
        elif state == "line_comment":
            if ch == "\n":
                mask_out[i] = "\n"
                clean_out[i] = "\n"
                state = "code"
            i += 1
        elif state == "block_comment":
            if ch == "*" and nxt == "/":
                state = "code"
                i += 2
                continue
            if ch == "\n":
                mask_out[i] = "\n"
                clean_out[i] = "\n"
            i += 1
        else:  # string
            if ch == "\\" and i + 1 < n:
                mask_out[i] = "_"
                mask_out[i + 1] = "_"
                clean_out[i] = ch
                clean_out[i + 1] = nxt
                i += 2
                continue
            if ch == '"':
                mask_out[i] = '"'
                clean_out[i] = '"'
                state = "code"
                i += 1
                continue
            mask_out[i] = "\n" if ch == "\n" else "_"
            clean_out[i] = ch
            i += 1
    return "".join(mask_out), "".join(clean_out)


def _find_matching_brace(mask: str, open_idx: int) -> int:
    depth = 0
    for idx in range(open_idx, len(mask)):
        c = mask[idx]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return idx
    return -1


def _count_direct_rules_blocks(body_mask: str) -> int:
    count = 0
    depth = 0
    idx = 0
    n = len(body_mask)
    while idx < n:
        if depth == 0:
            m = CF_RULES_BLOCK_RE.match(body_mask, idx)
            if m:
                count += 1
                brace_pos = m.end() - 1
                close_pos = _find_matching_brace(body_mask, brace_pos)
                if close_pos == -1:
                    break
                idx = close_pos + 1
                continue
        c = body_mask[idx]
        if c == "{":
            depth += 1
        elif c == "}":
            depth = max(0, depth - 1)
        idx += 1
    return count


def check_cloudflare_free_tier_redirect_quota(
    estate_root: Path,
    max_rules: int = 10,
) -> tuple[bool, str]:
    """Enforce Cloudflare Free-Tier cap (`<= 10` rules, zero Business regex) on `http_request_dynamic_redirect`."""
    cf_dir = estate_root / "w0m-api" / "cloudflare"
    if not cf_dir.is_dir():
        return False, "missing w0m-api/cloudflare directory — refusing vacuous pass"
    tf_files = sorted(cf_dir.glob("*.tf"))
    if not tf_files:
        return False, "0 Terraform (*.tf) files in w0m-api/cloudflare — refusing vacuous pass"

    rulesets_seen: list[str] = []
    findings: list[str] = []
    for tf_path in tf_files:
        raw = tf_path.read_text(encoding="utf-8", errors="replace")
        mask, no_comments = _mask_hcl(raw)
        rel = tf_path.relative_to(estate_root)
        for m in CF_MASKED_HEADER_RE.finditer(mask):
            header_raw = no_comments[m.start() : m.end()]
            hm = CF_RULESET_HEADER_RE.search(header_raw)
            if not hm:
                continue
            rname = hm.group(1)
            open_idx = m.end() - 1
            close_idx = _find_matching_brace(mask, open_idx)
            if close_idx == -1:
                findings.append(f"{rel}:cloudflare_ruleset.{rname}: unbalanced `{{` in HCL block")
                continue
            body_mask = mask[open_idx + 1 : close_idx]
            body_clean = no_comments[open_idx + 1 : close_idx]
            if not CF_DYNAMIC_REDIRECT_PHASE_RE.search(body_clean):
                continue
            rule_count = _count_direct_rules_blocks(body_mask)
            rulesets_seen.append(f"{rname}={rule_count}/{max_rules}")
            if rule_count > max_rules:
                findings.append(
                    f"{rel}:cloudflare_ruleset.{rname} declares {rule_count} rules > Free-Tier cap {max_rules} "
                    "(error 50001)"
                )
            regex_hit = CF_BUSINESS_REGEX_OP_RE.search(body_clean)
            if regex_hit:
                findings.append(
                    f"{rel}:cloudflare_ruleset.{rname} uses Business/Enterprise-only regex operator "
                    f"`{regex_hit.group(0).strip()}` on a Free-Tier zone"
                )

    if not rulesets_seen and not findings:
        return (
            False,
            "0 `http_request_dynamic_redirect` rulesets parsed in w0m-api/cloudflare/*.tf — refusing vacuous pass",
        )
    if findings:
        return False, "; ".join(findings)
    return (
        True,
        f"Cloudflare Free-Tier Single Redirect quota respected across {len(rulesets_seen)} zone ruleset(s) "
        f"({', '.join(rulesets_seen)})",
    )


def run_checks(
    estate_root: Path,
    *,
    manifest_path: Path | None = None,
    require_graphify: bool | None = None,
) -> tuple[bool, list[dict[str, Any]]]:
    policy = load_policy(estate_root)
    max_pending = int(policy.get("max_pending_ticket_mirror", 25))
    max_graph_lag = int(policy.get("max_graph_union_commit_lag", 25))
    max_cf_rules = int(policy.get("max_cf_single_redirect_rules_per_zone", 10))

    results: list[dict[str, Any]] = []

    if policy.get("forbid_detached_git_log_hooks", True):
        hook_findings = check_detached_git_log_hooks(estate_root)
        results.append(
            {
                "name": "no-detached-git-log-hooks",
                "ok": len(hook_findings) == 0,
                "detail": "0 detached `nohup` / `.git/*.log` background hooks"
                if not hook_findings
                else "; ".join(hook_findings),
            }
        )

    if policy.get("forbid_swallowed_deploy_snapshots", True):
        jf_findings = check_justfile_producers(estate_root)
        results.append(
            {
                "name": "no-swallowed-deploy-producers",
                "ok": len(jf_findings) == 0,
                "detail": "`deploy-web` snapshots and `_post-deploy-knowledge` fail closed"
                if not jf_findings
                else "; ".join(jf_findings),
            }
        )

    tm_ok, tm_detail = check_ticket_mirror_ceiling(estate_root, max_pending)
    results.append({"name": "bounded-ticket-mirror-lag", "ok": tm_ok, "detail": tm_detail})

    gr_ok, gr_detail = check_graph_union_ceiling(
        estate_root,
        max_graph_lag,
        manifest_path=manifest_path,
        require_graphify=require_graphify,
    )
    results.append({"name": "bounded-graph-union-lag", "ok": gr_ok, "detail": gr_detail})

    cf_ok, cf_detail = check_cloudflare_free_tier_redirect_quota(estate_root, max_cf_rules)
    results.append({"name": "cf-free-tier-redirect-quota", "ok": cf_ok, "detail": cf_detail})

    all_ok = all(bool(r["ok"]) for r in results)
    return all_ok, results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=None, help="Override estate root directory")
    ap.add_argument("--union-manifest", type=Path, default=None, help="Override w0m-union-manifest.json path")
    ap.add_argument("--json", action="store_true", help="Emit JSON output")
    args = ap.parse_args(argv)

    estate_root = args.root.resolve() if args.root is not None else ESTATE_ROOT
    try:
        all_ok, results = run_checks(estate_root, manifest_path=args.union_manifest)
    except ValueError as exc:
        print(f"  [FAIL] configuration error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps({"ok": all_ok, "checks": results}, indent=2))
    else:
        for r in results:
            tag = "PASS" if r["ok"] else "FAIL"
            print(f"  [{tag}] {r['name']}: {r['detail']}")
        if all_ok:
            print(f"✅ automation-health passed ({len(results)} check(s))")
        else:
            failed = [r["name"] for r in results if not r["ok"]]
            print(f"❌ automation-health FAILED: {', '.join(failed)}", file=sys.stderr)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
