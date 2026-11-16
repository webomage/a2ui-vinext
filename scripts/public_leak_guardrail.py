#!/usr/bin/env python3
"""Shared fail-closed internal-tech leak policy & scanner (`T749`).

Prevents accidental disclosure of internal estate technologies (`w0m`, `.w0m/`,
`-w0m`, `wom7*`, `k7*`, private client names such as `bridgeroad`, personal
workstation paths, internal `T##`/`AgDR-####` ticket IDs, and unallowlisted
brand handles) across:
1. Third-party upstream OSS PRs (`profile="upstream-pr"`):
   - PR titles and rendered Markdown bodies
   - Git commit messages (`git log`)
   - Git unified diff added/modified paths and `+` content lines
2. Public-facing web/CV surfaces (`profile="public-cv"`):
   - `w0m-web/apps/*/public/**` (including PDFs via `pdftotext`)
   - `w0m-web/apps/*/src/content/**/*.{md,mdx}`

Standard library only. Designed for fail-closed import by `scripts/w0m_prs.py`
and `w0m-web/project/scripts/cv_public.py`, plus standalone CLI verification.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable, Sequence

ESTATE_ROOT = Path(os.environ.get("W0M_ESTATE_ROOT") or Path(__file__).resolve().parents[1])

BINARY_SUFFIXES = frozenset({
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico", ".woff", ".woff2",
    ".ttf", ".otf", ".mp4", ".webm", ".zip", ".avif", ".wasm",
})
PDF_SUFFIX = ".pdf"
CV_SERVED_GLOBS = (
    "apps/*/public/**/*",
    "apps/*/src/content/**/*.md",
    "apps/*/src/content/**/*.mdx",
)

# Optional external JSON rules override; hardcoded rules below stay authoritative
# and fail-closed even when no policy file is passed.
UPSTREAM_PR_RULES: tuple[tuple[str, str, re.Pattern[str], str], ...] = (
    (
        "internal-w0m-dotdir",
        "w0m",
        re.compile(r"(?:^|[^A-Za-z0-9_])\.w0m(?:/|\\|\b)", re.IGNORECASE),
        "Internal `.w0m` governance directory or config reference",
    ),
    (
        "internal-w0m-suffix",
        "w0m",
        re.compile(r"[A-Za-z0-9_]+-w0m\b|\bw0m-[a-z0-9-]+\b", re.IGNORECASE),
        "Internal `w0m-*` or `*-w0m` wrapper/repo naming",
    ),
    (
        "internal-w0m-token",
        "w0m",
        re.compile(r"\bw0m\b|@wom\b|\bwom7[a-z0-9-]*\b", re.IGNORECASE),
        "Internal `w0m` / `@wom` / `wom7*` estate identifier",
    ),
    (
        "internal-k7-token",
        "k7",
        re.compile(r"\bk7(?:hub|env|lab|board|cli|web|api|infra)?\b|@k7\b", re.IGNORECASE),
        "Internal `k7` tech/repo identifier",
    ),
    (
        "internal-client-bridgeroad",
        "bridgeroad",
        re.compile(r"\bbridgeroad(?:[-_][a-z0-9-]+)?\b", re.IGNORECASE),
        "Private client repository/project identifier (`bridgeroad`)",
    ),
    (
        "personal-workstation-path",
        "workstation_path",
        re.compile(r"/home/aleksei\b|/Users/(?:aleksei|me)\b|Projects/!self", re.IGNORECASE),
        "Personal workstation path (`!self` or user home directory)",
    ),
    (
        "personal-handle-or-email",
        "casualuser",
        re.compile(r"\bcasualuser\b|casualuser@gmail\.com", re.IGNORECASE),
        "Personal GitHub handle or private email (`casualuser`)",
    ),
    (
        "internal-ticket-or-agdr",
        "ticket_id",
        re.compile(
            r"(?<![A-Za-z0-9_./-])(?:T[1-9]\d{2,3}|AgDR-\d{3,4}|ADR-\d{3,4})(?![A-Za-z0-9_-])(?!:\d)"
        ),
        "Internal ticket or architectural decision ID (`T###`/`AgDR-####`/`ADR-####`)",
    ),
    (
        "unallowlisted-webomage",
        "webomage",
        re.compile(r"\bwebomage\b", re.IGNORECASE),
        "Organization name `webomage` in upstream PR without explicit ecosystem allowlist",
    ),
)

PUBLIC_CV_RULES: tuple[tuple[str, str, re.Pattern[str], str], ...] = (
    (
        "internal-w0m-dotdir",
        "w0m_private",
        re.compile(r"(?:^|[^A-Za-z0-9_.])\.w0m(?:/|\\|\b)(?!\.xyz\b)|\bw0m-pr\b|\bwom7board\b", re.IGNORECASE),
        "Internal `.w0m/`, `w0m-pr`, or `wom7board` reference on public CV/web surface",
    ),
    (
        "internal-k7-token",
        "k7",
        re.compile(r"\bk7(?:hub|env|lab|board|cli|web|api|infra)?\b|@k7\b", re.IGNORECASE),
        "Internal `k7` tech/repo identifier on public CV/web surface",
    ),
    (
        "internal-client-bridgeroad",
        "bridgeroad",
        re.compile(r"\bbridgeroad(?:[-_][a-z0-9-]+)?\b", re.IGNORECASE),
        "Private client identifier (`bridgeroad`) on public CV/web surface",
    ),
    (
        "personal-workstation-path",
        "workstation_path",
        re.compile(r"/home/aleksei\b|/Users/(?:aleksei|me)\b|Projects/!self", re.IGNORECASE),
        "Personal workstation path on public CV/web surface",
    ),
    (
        "internal-ticket-or-agdr",
        "ticket_id",
        re.compile(
            r"(?<![A-Za-z0-9_./-])(?:T[1-9]\d{1,3}|AgDR-\d{3,4}|ADR-\d{3,4}|AC[1-9]\d?)(?![A-Za-z0-9_-])(?!:\d)"
        ),
        "Internal ticket, AgDR, or AC identifier on public CV/web surface",
    ),
)

PROFILE_RULES: dict[str, tuple[tuple[str, str, re.Pattern[str], str], ...]] = {
    "upstream-pr": UPSTREAM_PR_RULES,
    "public-cv": PUBLIC_CV_RULES,
}


@dataclasses.dataclass(frozen=True)
class LeakFinding:
    """Single deterministic internal-tech or PII leak match."""

    profile: str
    rule: str
    token_group: str
    location: str
    match: str
    message: str
    context: str

    def to_dict(self) -> dict[str, str]:
        return dataclasses.asdict(self)


def normalize_allow_tokens(allow_tokens: Sequence[str] | None) -> frozenset[str]:
    if not allow_tokens:
        return frozenset()
    return frozenset(str(tok).strip().lower() for tok in allow_tokens if str(tok).strip())


def _is_allowlisted(rule_id: str, token_group: str, matched_text: str, allow: frozenset[str]) -> bool:
    if not allow:
        return False
    low_match = matched_text.strip().lower()
    return (
        rule_id.lower() in allow
        or token_group.lower() in allow
        or low_match in allow
        or any(tok in low_match for tok in allow if len(tok) >= 4)
    )


def strip_cloudflare_control_comments(text: str, location: str) -> str:
    """Drop `#` comment lines only in Cloudflare Pages control files (`_headers`/`_redirects`)."""
    basename = Path(location).name
    if basename not in {"_headers", "_redirects"}:
        return text
    return "\n".join("" if line.lstrip().startswith("#") else line for line in text.splitlines())


def scan_text(
    text: str,
    *,
    profile: str = "upstream-pr",
    location: str = "<input>",
    allow_tokens: Sequence[str] = (),
) -> list[LeakFinding]:
    """Scan plain text (PR title, body, commit message, or served file content)."""
    if profile not in PROFILE_RULES:
        raise ValueError(f"Unknown leak guardrail profile: {profile!r}")
    rules = PROFILE_RULES[profile]
    allow = normalize_allow_tokens(allow_tokens)
    findings: list[LeakFinding] = []
    if not text:
        return findings

    effective_text = strip_cloudflare_control_comments(text, location) if profile == "public-cv" else text
    for idx, line in enumerate(effective_text.splitlines(), start=1):
        loc = f"{location}:{idx}"
        for rule_id, token_group, pattern, desc in rules:
            for m in pattern.finditer(line):
                matched = m.group(0).strip()
                if _is_allowlisted(rule_id, token_group, matched, allow):
                    continue
                findings.append(
                    LeakFinding(
                        profile=profile,
                        rule=rule_id,
                        token_group=token_group,
                        location=loc,
                        match=matched,
                        message=desc,
                        context=line.strip()[:220],
                    )
                )
    return findings


def extract_added_diff_lines(diff_text: str) -> list[tuple[str, str]]:
    """Extract `(location, line_text)` from unified git diff additions only.

    Scans:
    - Added/modified destination path headers (`+++ b/<path>`) so adding internal
      filenames/directories like `.w0m/` or `w0m-*` fails closed.
    - Added/modified content lines (`+...`), skipping diff removal lines (`-...`)
      and unchanged context lines so cleanup PRs removing leaked symbols pass.
    """
    entries: list[tuple[str, str]] = []
    current_file = "<diff>"
    new_line_no = 0
    for raw in (diff_text or "").splitlines():
        if raw.startswith("+++ "):
            path_part = raw[4:].strip()
            if path_part == "/dev/null":
                current_file = "/dev/null"
            elif path_part.startswith("b/"):
                current_file = path_part[2:]
                entries.append((f"diff-path:{current_file}", current_file))
            else:
                current_file = path_part
                entries.append((f"diff-path:{current_file}", current_file))
            continue
        if raw.startswith("--- ") or raw.startswith("diff --git "):
            continue
        if raw.startswith("@@ "):
            m = re.search(r"\+(\d+)(?:,\d+)?", raw)
            new_line_no = int(m.group(1)) - 1 if m else 0
            continue
        if raw.startswith("+"):
            new_line_no += 1
            entries.append((f"{current_file}:{max(1, new_line_no)}", raw[1:]))
        elif raw.startswith(" "):
            new_line_no += 1
    return entries


_PR_ASSETS_IMAGE_RE = re.compile(
    r"https://raw\.githubusercontent\.com/webomage/[A-Za-z0-9._-]+/pr-assets/[^\s)\"\]]+",
    re.IGNORECASE,
)


def scan_upstream_pr_bundle(
    *,
    title: str = "",
    body: str = "",
    commit_messages: str = "",
    diff_text: str = "",
    allow_tokens: Sequence[str] = (),
) -> list[LeakFinding]:
    """Scan all public surfaces of an upstream OSS PR together (fail-closed)."""
    findings: list[LeakFinding] = []
    if title:
        findings.extend(scan_text(title, profile="upstream-pr", location="pr-title", allow_tokens=allow_tokens))
    if body:
        # Ignore canonical fork visual-proof asset image URLs when scanning markdown bodies;
        # prose, titles, commits, and code diffs still fail closed on `webomage`.
        sanitized_body = _PR_ASSETS_IMAGE_RE.sub("<pr-asset-url>", body)
        findings.extend(
            scan_text(sanitized_body, profile="upstream-pr", location="pr-body", allow_tokens=allow_tokens)
        )
    if commit_messages:
        findings.extend(
            scan_text(commit_messages, profile="upstream-pr", location="commit-msg", allow_tokens=allow_tokens)
        )
    if diff_text:
        rules = PROFILE_RULES["upstream-pr"]
        allow = normalize_allow_tokens(allow_tokens)
        for loc, line_text in extract_added_diff_lines(diff_text):
            for rule_id, token_group, pattern, desc in rules:
                for m in pattern.finditer(line_text):
                    matched = m.group(0).strip()
                    if _is_allowlisted(rule_id, token_group, matched, allow):
                        continue
                    findings.append(
                        LeakFinding(
                            profile="upstream-pr",
                            rule=rule_id,
                            token_group=token_group,
                            location=loc,
                            match=matched,
                            message=desc,
                            context=line_text.strip()[:220],
                        )
                    )
    return findings


def _git_output(cwd: Path, args: list[str], timeout: float = 20.0) -> tuple[int, str, str]:
    try:
        cp = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return cp.returncode, cp.stdout, cp.stderr
    except (OSError, subprocess.SubprocessError) as exc:
        return 2, "", str(exc)


def scan_git_branch_upstream_pr(
    repo_path: Path,
    head_ref: str,
    base_ref: str,
    *,
    title: str = "",
    body: str = "",
    allow_tokens: Sequence[str] = (),
) -> dict[str, Any]:
    """Inspect a local git branch PR delta (`base_ref...head_ref`) + optional PR metadata.

    Uses three-dot `base_ref...head_ref` for `git diff` (the exact merge-base PR diff,
    never upstream commits merged after branch creation) and two-dot `base_ref..head_ref`
    for `git log` commit messages. Fail-closed if `git diff` or `git log` fails.
    """
    rc_diff, diff_out, diff_err = _git_output(repo_path, ["diff", "--unified=0", f"{base_ref}...{head_ref}"])
    if rc_diff != 0:
        return {
            "ok": False,
            "error": f"Unable to compute git diff {base_ref}...{head_ref} in {repo_path}: {diff_err.strip()}",
            "findings": [],
        }
    rc_log, log_out, log_err = _git_output(repo_path, ["log", "--format=%H%n%B", f"{base_ref}..{head_ref}"])
    if rc_log != 0:
        return {
            "ok": False,
            "error": f"Unable to read commit messages {base_ref}..{head_ref} in {repo_path}: {log_err.strip()}",
            "findings": [],
        }

    findings = scan_upstream_pr_bundle(
        title=title,
        body=body,
        commit_messages=log_out,
        diff_text=diff_out,
        allow_tokens=allow_tokens,
    )
    return {
        "ok": len(findings) == 0,
        "error": "",
        "findings": [f.to_dict() for f in findings],
    }


def _extract_pdf_text(path: Path) -> str | None:
    if not shutil.which("pdftotext"):
        return None
    try:
        cp = subprocess.run(["pdftotext", "-q", str(path), "-"], capture_output=True, text=True, timeout=30)
        return cp.stdout if cp.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def scan_cv_root(web_root: Path, *, allow_tokens: Sequence[str] = ()) -> dict[str, Any]:
    """Scan all served `w0m-web` surfaces (including CV PDFs) for internal-tech leaks."""
    if not web_root.exists():
        return {"ok": False, "error": f"w0m-web root does not exist: {web_root}", "findings": [], "unreadable": []}

    seen: set[Path] = set()
    for g in CV_SERVED_GLOBS:
        for p in web_root.glob(g):
            if p.is_file():
                seen.add(p)

    text_files = sorted(p for p in seen if p.suffix.lower() not in BINARY_SUFFIXES and p.suffix.lower() != PDF_SUFFIX)
    pdf_files = sorted(p for p in seen if p.suffix.lower() == PDF_SUFFIX)
    if not text_files:
        return {
            "ok": False,
            "error": f"Zero served text surfaces discovered under {web_root}",
            "findings": [],
            "unreadable": [],
        }

    findings: list[dict[str, str]] = []
    unreadable: list[str] = []

    for path in text_files:
        rel = str(path.relative_to(web_root))
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            unreadable.append(rel)
            continue
        for hit in scan_text(content, profile="public-cv", location=rel, allow_tokens=allow_tokens):
            findings.append(hit.to_dict())

    for path in pdf_files:
        rel = str(path.relative_to(web_root))
        pdf_body = _extract_pdf_text(path)
        if pdf_body is None:
            unreadable.append(rel)
            continue
        for hit in scan_text(pdf_body, profile="public-cv", location=rel, allow_tokens=allow_tokens):
            findings.append(hit.to_dict())

    return {
        "ok": len(findings) == 0 and len(unreadable) == 0,
        "error": f"{len(unreadable)} unreadable served file(s)" if unreadable else "",
        "scannedTextCount": len(text_files),
        "scannedPdfCount": len(pdf_files) - len([u for u in unreadable if u.endswith(".pdf")]),
        "unreadable": unreadable,
        "findings": findings,
    }


def scan_all_prepared_upstream_prs(
    estate_root: Path = ESTATE_ROOT,
    *,
    include_local_git: bool = True,
) -> dict[str, Any]:
    """Audit active upstream PR proposals (and optionally local fork git diffs/commits) via `w0m_prs`."""
    scripts_dir = estate_root / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    import w0m_prs  # local script in same directory

    superseded: set[str] = set(getattr(w0m_prs, "INTERNAL_OR_SUPERSEDED_BRANCHES", ()))
    forks_dir = w0m_prs.resolve_forks_dir() if include_local_git else None
    proposals = w0m_prs.build_pr_proposals(forks_dir=forks_dir)

    results: list[dict[str, Any]] = []
    total_findings = 0
    for item in sorted(proposals, key=lambda p: str(p.get("key") or "")):
        key = str(item.get("key") or "")
        branch = str(item.get("branch") or "")
        if not key or branch in superseded:
            continue
        enriched = w0m_prs.get_enriched_proposal(key)
        allow = tuple(enriched.get("allow_public_leak_tokens") or ())
        body = str(item.get("body") or "")
        title = str(item.get("title") or "")
        bundle_findings = scan_upstream_pr_bundle(title=title, body=body, allow_tokens=allow)

        local_checked = False
        local_error = ""
        fork_name = str(item.get("fork") or "")
        base_branch = str(item.get("base_branch") or "main")
        repo_path = (forks_dir / fork_name) if include_local_git and forks_dir is not None and fork_name else None
        if repo_path is not None and (repo_path / ".git").exists():
            local_verify = subprocess.run(
                ["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}^{{commit}}"],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
            )
            if local_verify.returncode == 0:
                local_checked = True
                res = scan_git_branch_upstream_pr(
                    repo_path,
                    f"refs/heads/{branch}",
                    f"upstream/{base_branch}",
                    title=title,
                    body=body,
                    allow_tokens=allow,
                )
                local_error = str(res.get("error") or "")
                all_findings = list(res.get("findings") or [])
            else:
                all_findings = [f.to_dict() for f in bundle_findings]
        else:
            all_findings = [f.to_dict() for f in bundle_findings]

        total_findings += len(all_findings) + (1 if local_error else 0)
        results.append(
            {
                "proposal": key,
                "localChecked": local_checked,
                "error": local_error,
                "findingCount": len(all_findings),
                "findings": all_findings[:10],
            }
        )

    return {
        "ok": total_findings == 0,
        "proposalCount": len(results),
        "totalFindings": total_findings,
        "proposals": results,
    }


def _print_findings(label: str, findings: Iterable[dict[str, str]]) -> None:
    items = list(findings)
    if not items:
        return
    print(f"🔴 {label}: {len(items)} public-leak violation(s):")
    for f in items[:25]:
        print(f"  - [{f.get('rule')}] {f.get('location')}: {f.get('match')!r} — {f.get('message')}")
        ctx = f.get("context") or ""
        if ctx:
            print(f"    context: {ctx[:140]}")
    if len(items) > 25:
        print(f"  ... ({len(items) - 25} more)")


def main() -> int:
    ap = argparse.ArgumentParser(description="Fail-closed internal-tech leak guardrail across upstream PRs and public CV surfaces.")
    ap.add_argument(
        "--mode",
        choices=("all", "cv", "proposals", "upstream-pr", "git-range"),
        default="all",
        help="all=cv+proposals (estate repo gates); upstream-pr=proposals+local fork git diffs; git-range=single repo range",
    )
    ap.add_argument("--web-root", default=str(ESTATE_ROOT / "w0m-web"), help="w0m-web root for --mode cv/all")
    ap.add_argument("--repo-path", help="Local git repo path for --mode git-range")
    ap.add_argument("--base-ref", default="upstream/main", help="Base ref for --mode git-range")
    ap.add_argument("--head-ref", default="HEAD", help="Head ref for --mode git-range")
    ap.add_argument("--allow-token", action="append", default=[], help="Explicitly allowlisted token")
    ap.add_argument("--json", action="store_true", help="Emit JSON summary")
    args = ap.parse_args()

    payload: dict[str, Any] = {"mode": args.mode, "ok": True}
    exit_code = 0

    if args.mode in ("cv", "all"):
        cv_res = scan_cv_root(Path(args.web_root), allow_tokens=args.allow_token)
        payload["cv"] = cv_res
        if not cv_res.get("ok"):
            exit_code = 1

    if args.mode in ("proposals", "all", "upstream-pr"):
        pr_res = scan_all_prepared_upstream_prs(
            ESTATE_ROOT,
            include_local_git=(args.mode == "upstream-pr"),
        )
        payload["upstream_pr"] = pr_res
        if not pr_res.get("ok"):
            exit_code = 1

    if args.mode == "git-range":
        if not args.repo_path:
            print("public-leak-guardrail: --repo-path is required for --mode git-range", file=sys.stderr)
            return 2
        git_res = scan_git_branch_upstream_pr(
            Path(args.repo_path),
            args.head_ref,
            args.base_ref,
            allow_tokens=args.allow_token,
        )
        payload["git_range"] = git_res
        if not git_res.get("ok"):
            exit_code = 1

    payload["ok"] = exit_code == 0

    if args.json:
        print(json.dumps(payload, indent=2))
        return exit_code

    if "cv" in payload:
        cv_res = payload["cv"]
        if cv_res.get("ok"):
            print(
                f"✅ public-leak-guardrail [cv]: clean "
                f"({cv_res.get('scannedTextCount', 0)} text + {cv_res.get('scannedPdfCount', 0)} PDF)"
            )
        else:
            if cv_res.get("error"):
                print(f"🔴 public-leak-guardrail [cv]: {cv_res['error']}")
            _print_findings("cv", cv_res.get("findings") or [])

    if "upstream_pr" in payload:
        pr_res = payload["upstream_pr"]
        if pr_res.get("ok"):
            print(
                f"✅ public-leak-guardrail [upstream-pr]: clean across {pr_res.get('proposalCount', 0)} proposal(s)"
            )
        else:
            for item in pr_res.get("proposals") or []:
                if item.get("error"):
                    print(f"🔴 upstream-pr [{item['proposal']}]: {item['error']}")
                if item.get("findings"):
                    _print_findings(f"upstream-pr:{item['proposal']}", item["findings"])

    if "git_range" in payload:
        gr: dict[str, Any] = payload["git_range"]
        if gr.get("ok"):
            print(f"✅ public-leak-guardrail [git-range]: clean ({args.base_ref}..{args.head_ref})")
        else:
            if gr.get("error"):
                print(f"🔴 git-range: {gr['error']}")
            _print_findings(f"git-range:{args.head_ref}", gr.get("findings") or [])

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
