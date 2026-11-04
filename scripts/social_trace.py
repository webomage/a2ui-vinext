#!/usr/bin/env python3
"""social_trace.py — On-demand multi-platform social & developer signal CLI (T624 AC1/AC2/AC3/AC5).

Supports tracing, reading, and searching across:
  - GitHub (`github`): outbound stars & forks (`--target <user>`), inbound stargazers & forks (`--repo owner/repo`), or repo search (`--query <q>`)
  - LinkedIn (`linkedin`): official Member Data Export CSV parsing (`--linkedin-csv <path>`) — zero scraping (T98)
  - Telegram (`telegram`): public channel preview & search (`t.me/s/<channel>?q=<query>`)
  - Reddit (`reddit`): structured `.json?raw_json=1` subreddit & keyword search
  - X (`x`): public oEmbed extraction (`publish.twitter.com/oembed`) for tweet URLs
  - Threads / Web (`threads`, `web`): optional delegation via ToS-aware Cloudflare Edge Reader (`--cf-reader`)

Outputs structured JSON (`--json`, `jq`-ready) or a scannable terminal table + synthesized Todo/Task/Project insight recommendations.
"""

from __future__ import annotations

import argparse
import csv
from html.parser import HTMLParser
import io
import json
import os
from pathlib import Path
import re
import sys
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "WebomageSocialConnector/1.0 (+https://webomage.com)"
PROJECT_CUES = ("sdk", "framework", "template", "boilerplate", "agent", "mcp", "starter", "toolkit")
TASK_CUES = ("bug", "fix", "issue", "cve", "migration", "benchmark", "performance", "security", "upgrade")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data:
            self.parts.append(data)

    def get_text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self.parts)).strip()


def strip_html(raw: str) -> str:
    parser = _TextExtractor()
    parser.feed(raw)
    return parser.get_text()


def _http_get_json(url: str, headers: dict[str, str] | None = None) -> Any:
    req_headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_get_text(url: str, headers: dict[str, str] | None = None) -> str:
    req_headers = {"User-Agent": USER_AGENT}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8", errors="replace")


def delegate_cf_reader(url: str, endpoint_base: str, bearer: str, respect_robots: bool = True) -> dict[str, Any]:
    trimmed = endpoint_base.rstrip("/")
    api_url = trimmed if trimmed.endswith("/api/reader/extract") else f"{trimmed}/api/reader/extract"
    payload = json.dumps({"url": url, "respectRobots": respect_robots}).encode("utf-8")
    req = urllib.request.Request(
        api_url,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {bearer}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {"ok": False, "status": exc.code, "error": body[:300]}


def trace_github(
    username: str | None = None,
    repo: str | None = None,
    query: str | None = None,
    limit: int = 10,
    token: str | None = None,
) -> list[dict[str, Any]]:
    headers = {"Accept": "application/vnd.github.star+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    signals: list[dict[str, Any]] = []
    per_page = max(1, min(limit, 30))

    if query:
        q = urllib.parse.quote(query)
        data = _http_get_json(
            f"https://api.github.com/search/repositories?q={q}&sort=stars&order=desc&per_page={per_page}",
            {"Accept": "application/vnd.github+json", **({"Authorization": f"Bearer {token}"} if token else {})},
        )
        for item in data.get("items", []):
            full = item.get("full_name", "")
            if not full:
                continue
            signals.append(
                {
                    "platform": "github",
                    "signal_kind": "search_hit",
                    "direction": "discovered",
                    "source_url": item.get("html_url", f"https://github.com/{full}"),
                    "title": full,
                    "excerpt": (item.get("description") or "")[:300],
                    "repo_full_name": full,
                    "metrics": {
                        "stars": int(item.get("stargazers_count") or 0),
                        "forks": int(item.get("forks_count") or 0),
                    },
                }
            )
        return signals

    if username:
        clean_user = username.lstrip("@")
        starred = _http_get_json(
            f"https://api.github.com/users/{urllib.parse.quote(clean_user)}/starred?per_page={per_page}",
            headers,
        )
        for entry in starred:
            r = entry.get("repo", entry)
            full = r.get("full_name", "")
            if not full:
                continue
            signals.append(
                {
                    "platform": "github",
                    "signal_kind": "star",
                    "direction": "outbound",
                    "source_url": r.get("html_url", f"https://github.com/{full}"),
                    "title": f"Starred {full}",
                    "excerpt": (r.get("description") or "")[:300],
                    "repo_full_name": full,
                    "metrics": {
                        "stars": int(r.get("stargazers_count") or 0),
                        "forks": int(r.get("forks_count") or 0),
                    },
                }
            )

    if repo and "/" in repo:
        clean_repo = repo.strip().removeprefix("https://github.com/").strip("/")
        stargazers = _http_get_json(
            f"https://api.github.com/repos/{clean_repo}/stargazers?per_page={per_page}",
            headers,
        )
        for sg in stargazers:
            actor = (sg.get("user") or sg).get("login", "")
            if not actor:
                continue
            signals.append(
                {
                    "platform": "github",
                    "signal_kind": "star",
                    "direction": "inbound",
                    "source_url": f"https://github.com/{clean_repo}",
                    "title": f"@{actor} starred {clean_repo}",
                    "excerpt": f"Inbound star from @{actor}",
                    "repo_full_name": clean_repo,
                    "metrics": {"stars": 1},
                }
            )
    return signals


def parse_linkedin_export_csv(csv_text: str) -> list[dict[str, Any]]:
    lines = [ln for ln in csv_text.splitlines() if ln.strip()]
    known = {"date", "link", "saveditem", "sharelink", "sharedurl", "url", "sharecommentary", "type"}
    header_idx = 0
    for idx, ln in enumerate(lines[:5]):
        row_cells = [c.strip().lower() for c in next(csv.reader([ln]))]
        if len(row_cells) >= 2 and any(c in known for c in row_cells):
            header_idx = idx
            break

    reader = csv.DictReader(io.StringIO("\n".join(lines[header_idx:])))
    signals: list[dict[str, Any]] = []
    for row in reader:
        norm = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        url = (
            norm.get("saveditem")
            or norm.get("sharelink")
            or norm.get("link")
            or norm.get("url")
            or "https://www.linkedin.com/feed/"
        )
        commentary = norm.get("sharecommentary") or norm.get("description") or norm.get("title") or ""
        rtype = norm.get("type", "").upper()
        if not commentary and url == "https://www.linkedin.com/feed/" and not rtype:
            continue
        kind = "share" if "sharelink" in norm or "sharecommentary" in norm else ("like" if rtype else "bookmark")
        signals.append(
            {
                "platform": "linkedin",
                "signal_kind": kind,
                "direction": "outbound",
                "source_url": url,
                "title": commentary[:120] or f"LinkedIn {kind}",
                "excerpt": commentary[:300],
                "repo_full_name": None,
                "metrics": {"reactions": 1} if rtype else {},
            }
        )
    return signals


def trace_reddit(subreddit: str | None = None, query: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
    lim = max(1, min(limit, 25))
    sub = (subreddit or "").strip().removeprefix("r/").strip("/")
    if sub and query:
        url = f"https://www.reddit.com/r/{urllib.parse.quote(sub)}/search.json?q={urllib.parse.quote(query)}&restrict_sr=1&sort=new&limit={lim}&raw_json=1"
    elif sub:
        url = f"https://www.reddit.com/r/{urllib.parse.quote(sub)}/hot.json?limit={lim}&raw_json=1"
    elif query:
        url = f"https://www.reddit.com/search.json?q={urllib.parse.quote(query)}&sort=new&limit={lim}&raw_json=1"
    else:
        raise ValueError("Reddit trace requires --subreddit or --query")

    listing = _http_get_json(url)
    out: list[dict[str, Any]] = []
    for child in listing.get("data", {}).get("children", []):
        d = child.get("data", {})
        permalink = d.get("permalink")
        out.append(
            {
                "platform": "reddit",
                "signal_kind": "search_hit" if query else "post",
                "direction": "discovered",
                "source_url": f"https://www.reddit.com{permalink}" if permalink else d.get("url", "https://www.reddit.com"),
                "title": (d.get("title") or "Reddit post")[:160],
                "excerpt": (d.get("selftext") or "")[:300],
                "repo_full_name": None,
                "metrics": {"upvotes": int(d.get("ups") or 0), "comments": int(d.get("num_comments") or 0)},
            }
        )
    return out


def trace_telegram(channel: str, query: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
    handle = channel.strip().lstrip("@").removeprefix("https://t.me/s/").removeprefix("https://t.me/").split("/")[0]
    url = f"https://t.me/s/{urllib.parse.quote(handle)}"
    if query:
        url += f"?q={urllib.parse.quote(query)}"
    html = _http_get_text(url)
    out: list[dict[str, Any]] = []
    for block in html.split("tgme_widget_message_wrap")[1 : max(2, limit + 1)]:
        post_match = re.search(r'data-post=["\']([^"\']+)["\']', block)
        text_match = re.search(r'class=["\'][^"\']*tgme_widget_message_text[^"\']*["\'][^>]*>([\s\S]*?)</div>', block)
        if not post_match or not text_match:
            continue
        post_id = post_match.group(1)
        txt = strip_html(text_match.group(1))
        if not txt:
            continue
        out.append(
            {
                "platform": "telegram",
                "signal_kind": "search_hit" if query else "post",
                "direction": "discovered",
                "source_url": f"https://t.me/{post_id}",
                "title": txt[:120],
                "excerpt": txt[:300],
                "repo_full_name": None,
                "metrics": {},
            }
        )
    return out


def synthesize_recommendations(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    recs: list[dict[str, Any]] = []
    for sig in signals:
        hay = f"{sig.get('title', '')} {sig.get('excerpt', '')} {sig.get('repo_full_name', '')}".lower()
        kind = "todo"
        if sig.get("platform") == "github" and sig.get("direction") == "inbound":
            kind = "task"
        elif sig.get("signal_kind") == "fork" or (
            sig.get("platform") == "github" and any(cue in hay for cue in PROJECT_CUES)
        ):
            kind = "project"
        elif any(cue in hay for cue in TASK_CUES):
            kind = "task"
        recs.append(
            {
                "suggested_kind": kind,
                "title": sig.get("title"),
                "source_url": sig.get("source_url"),
                "platform": sig.get("platform"),
            }
        )
    return recs


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Multi-platform social & GitHub signal tracer (T624)")
    p.add_argument(
        "--platform",
        choices=["github", "linkedin", "telegram", "threads", "reddit", "x", "web"],
        default="github",
    )
    p.add_argument("--target", help="Account handle, channel, subreddit, or URL")
    p.add_argument("--repo", help="Watched GitHub repository (owner/repo) for inbound stars")
    p.add_argument("--query", help="Search keyword query")
    p.add_argument("--linkedin-csv", type=Path, help="Path to official LinkedIn Data Export CSV")
    p.add_argument("--cf-reader", action="store_true", help="Delegate extraction via ToS-aware Cloudflare Edge Reader")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--json", action="store_true", help="Emit structured JSON output")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    signals: list[dict[str, Any]] = []

    if args.linkedin_csv:
        csv_text = args.linkedin_csv.read_text(encoding="utf-8")
        signals.extend(parse_linkedin_export_csv(csv_text))
    elif args.cf_reader and args.target and args.target.startswith(("http://", "https://")):
        bearer = (
            os.environ.get("WORKERS_WEBHOOK_SECRET")
            or os.environ.get("WEBHOOK_SECRET")
            or os.environ.get("W0M_MCP_BEARER_SECRET")
            or ""
        ).strip()
        endpoint = (
            os.environ.get("WORKERS_WEBHOOK_URL")
            or os.environ.get("CF_EDGE_READER_URL")
            or ""
        ).strip()
        if not bearer or not endpoint:
            print(
                "error: WORKERS_WEBHOOK_URL and WORKERS_WEBHOOK_SECRET are required when --cf-reader is set",
                file=sys.stderr,
            )
            return 2
        res = delegate_cf_reader(args.target, endpoint, bearer)
        if not res.get("ok"):
            print(json.dumps(res, indent=2), file=sys.stderr)
            return 1
        signals.append(
            {
                "platform": args.platform,
                "signal_kind": "post",
                "direction": "discovered",
                "source_url": res.get("resolvedUrl", args.target),
                "title": (res.get("metadata") or {}).get("title") or args.target,
                "excerpt": (res.get("markdown") or "")[:300],
                "repo_full_name": None,
                "metrics": (res.get("metadata") or {}).get("metrics") or {},
            }
        )
    elif args.platform == "github":
        signals.extend(
            trace_github(
                username=args.target,
                repo=args.repo,
                query=args.query,
                limit=args.limit,
                token=os.environ.get("GITHUB_TOKEN"),
            )
        )
    elif args.platform == "reddit":
        signals.extend(trace_reddit(subreddit=args.target, query=args.query, limit=args.limit))
    elif args.platform == "telegram":
        if not args.target:
            print("error: --target <channel> is required for --platform telegram", file=sys.stderr)
            return 2
        signals.extend(trace_telegram(channel=args.target, query=args.query, limit=args.limit))
    elif args.platform == "x" and args.target and args.target.startswith(("http://", "https://")):
        oembed_url = f"https://publish.twitter.com/oembed?omit_script=true&dnt=true&url={urllib.parse.quote(args.target)}"
        data = _http_get_json(oembed_url)
        txt = strip_html(data.get("html") or "")
        signals.append(
            {
                "platform": "x",
                "signal_kind": "post",
                "direction": "discovered",
                "source_url": args.target,
                "title": txt[:140] or "X post",
                "excerpt": txt[:300],
                "repo_full_name": None,
                "metrics": {},
            }
        )
    else:
        print(
            f"error: unsupported unauthenticated invocation for platform={args.platform}; pass --linkedin-csv, --cf-reader URL, or valid --target/--query.",
            file=sys.stderr,
        )
        return 2

    recommendations = synthesize_recommendations(signals)
    output = {"ok": True, "count": len(signals), "signals": signals, "recommendations": recommendations}
    if args.json:
        print(json.dumps(output, indent=2))
    else:
        print(f"Traced {len(signals)} signal(s) -> {len(recommendations)} candidate insight(s):")
        for rec in recommendations:
            print(f"  [{rec['suggested_kind'].upper():7s}] ({rec['platform']}) {rec['title']} -> {rec['source_url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
