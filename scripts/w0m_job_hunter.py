#!/usr/bin/env python3
"""@wom + @k7 Multi-Channel Job Hunter (Hybrid BM25 + TF-IDF Vector RRF + CV Graph).

Supports explicit include/exclude channel filtering across all 13 `@wom` / `@k7`
sources, 5-axis rubric scoring, FNV-1a + Levenshtein deduplication, and CV
provenance grounding from `w0m-web/project/data/cv/cv-profile-seed.json`.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CV_SEED_PATH = ROOT / "w0m-web" / "project" / "data" / "cv" / "cv-profile-seed.json"
KB_SQLITE_PATH = Path.home() / ".w0m" / "knowledge-index" / "corpus.sqlite"

ALL_JOB_SOURCES: tuple[str, ...] = (
    "upwork",
    "hn",
    "ats",
    "weworkremotely",
    "remoteok",
    "remotive",
    "jobicy",
    "workingnomads",
    "nofluffjobs",
    "adzuna",
    "cryptojobslist",
    "telegram",
    "threads",
)

SOURCE_ALIASES: dict[str, str] = {
    "upwork": "upwork",
    "hn": "hn",
    "hackernews": "hn",
    "hnwhoshiring": "hn",
    "ats": "ats",
    "greenhouse": "ats",
    "ashby": "ats",
    "lever": "ats",
    "weworkremotely": "weworkremotely",
    "wwr": "weworkremotely",
    "remoteok": "remoteok",
    "remotive": "remotive",
    "jobicy": "jobicy",
    "workingnomads": "workingnomads",
    "nofluffjobs": "nofluffjobs",
    "nofluff": "nofluffjobs",
    "adzuna": "adzuna",
    "cryptojobslist": "cryptojobslist",
    "telegram": "telegram",
    "threads": "threads",
}

RRF_K = 60


@dataclass
class JobRecord:
    id: str
    source: str
    title: str
    company: str
    url: str
    location: str
    currency: str
    salary_range: str
    remote: bool
    contract: bool
    tags: list[str]
    summary: str
    cv_evidence: list[str]
    graph_nodes: list[str]


CURATED_CATALOG: tuple[JobRecord, ...] = (
    JobRecord(
        id="wwr-knack-cloud",
        source="weworkremotely",
        title="Cloud Engineer (International Contractor)",
        company="Knack",
        url="https://weworkremotely.com/remote-jobs/knack-cloud-engineer-1",
        location="Worldwide Remote",
        currency="USD",
        salary_range="USD Contractor",
        remote=True,
        contract=True,
        tags=["aws", "kubernetes", "terraform", "docker", "devops", "ci/cd"],
        summary="International USD B2B contract owning multi-region AWS and Kubernetes infrastructure.",
        cv_evidence=["AWS EKS & Terraform IaC", "20+ yrs Distributed Infra"],
        graph_nodes=["cv:aws-eks", "cv:terraform", "infra:kubernetes"],
    ),
    JobRecord(
        id="hn-sadservers-sre",
        source="hn",
        title="Linux & Cloud Infrastructure SRE (Contract)",
        company="SadServers",
        url="https://news.ycombinator.com/item?id=50341345",
        location="Global Remote",
        currency="USD",
        salary_range="$55 - $75/hr USD",
        remote=True,
        contract=True,
        tags=["linux", "aws", "kubernetes", "docker", "sre", "bare-metal"],
        summary="Contract infrastructure reliability engineering for Linux debugging scenarios.",
        cv_evidence=["Bare-Metal Linux & Proxmox", "Kubernetes / k3s Operations"],
        graph_nodes=["cv:linux", "cv:bare-metal", "cv:k3s"],
    ),
    JobRecord(
        id="hn-getregistered-gcp",
        source="hn",
        title="GCP / Terraform DevOps Engineer (Freelance)",
        company="getregistered",
        url="https://news.ycombinator.com/item?id=50352957",
        location="Fully Remote",
        currency="USD",
        salary_range="USD Freelance Contract",
        remote=True,
        contract=True,
        tags=["gcp", "terraform", "kubernetes", "devops", "cloudflare"],
        summary="Direct freelance DevOps contract automating GCP networking and Terraform modules.",
        cv_evidence=["GCP & Multi-Cloud IaC", "Cloudflare Workers & Edge"],
        graph_nodes=["cv:gcp", "cv:terraform", "cv:cloudflare"],
    ),
    JobRecord(
        id="jobicy-phantom-staff-devops",
        source="jobicy",
        title="Staff DevOps Engineer — Platform",
        company="Phantom",
        url="https://jobicy.com/jobs/153130-staff-devops-engineer-platform",
        location="Worldwide Remote",
        currency="USD",
        salary_range="$165k - $230k USD",
        remote=True,
        contract=False,
        tags=["aws", "kubernetes", "terraform", "sre", "observability", "rust"],
        summary="High-ownership Staff Platform role securing distributed RPC and cloud Kubernetes clusters.",
        cv_evidence=["Staff Platform & Rust Systems", "Ceph & High-Load Infra"],
        graph_nodes=["cv:kubernetes", "cv:rust", "cv:observability"],
    ),
    JobRecord(
        id="ats-prelim-infra",
        source="ats",
        title="Senior Cloud Infrastructure Engineer",
        company="Prelim (Ashby ATS)",
        url="https://jobs.ashbyhq.com/prelim",
        location="Remote",
        currency="USD",
        salary_range="$210k - $230k USD",
        remote=True,
        contract=False,
        tags=["aws", "terraform", "kubernetes", "security", "ci/cd", "devops"],
        summary="Direct Ashby ATS opening owning SOC2-grade AWS infrastructure and deployment pipelines.",
        cv_evidence=["AWS EKS + Security Guardrails", "Production CI/CD Automation"],
        graph_nodes=["cv:aws-eks", "cv:security", "cv:ci-cd"],
    ),
    JobRecord(
        id="hn-posthog-sre",
        source="hn",
        title="Site Reliability Engineer",
        company="PostHog",
        url="https://news.ycombinator.com/item?id=50338907",
        location="Worldwide Remote",
        currency="USD",
        salary_range="USD Competitive + Equity",
        remote=True,
        contract=False,
        tags=["kubernetes", "aws", "terraform", "sre", "clickhouse", "linux"],
        summary="Scale high-throughput Kubernetes and analytical storage fleets globally.",
        cv_evidence=["High-Load Distributed Storage", "Kubernetes Fleet Operations"],
        graph_nodes=["cv:kubernetes", "cv:storage", "cv:linux"],
    ),
    JobRecord(
        id="workingnomads-lemon-devops",
        source="workingnomads",
        title="Senior DevOps Engineer (B2B Contract)",
        company="Lemon.io",
        url="https://www.workingnomads.com/jobs/1958438",
        location="Worldwide Remote",
        currency="USD",
        salary_range="$44 - $55/hr USD",
        remote=True,
        contract=True,
        tags=["aws", "gcp", "terraform", "docker", "kubernetes", "devops"],
        summary="Long-term USD contractor placement for vetted infrastructure engineers.",
        cv_evidence=["Multi-Cloud Terraform & Docker", "100% Remote Track Record"],
        graph_nodes=["cv:terraform", "cv:docker", "cv:aws-eks"],
    ),
    JobRecord(
        id="jobicy-wurl-staff-platform",
        source="jobicy",
        title="Staff Platform Engineer",
        company="Wurl",
        url="https://jobicy.com/jobs/161903-staff-platform-engineer-4",
        location="Remote",
        currency="USD",
        salary_range="$191k - $252k USD",
        remote=True,
        contract=False,
        tags=["aws", "kubernetes", "terraform", "devops", "sre", "serverless"],
        summary="Own media-scale cloud platform architecture, Kubernetes automation, and SLO reliability.",
        cv_evidence=["Serverless & Cloud Kubernetes", "20+ yrs Distributed Systems"],
        graph_nodes=["cv:serverless", "cv:kubernetes", "cv:sre"],
    ),
    JobRecord(
        id="remoteok-civilgrid-infra",
        source="remoteok",
        title="Senior / Staff Infrastructure Security Engineer",
        company="CivilGrid",
        url="https://remoteok.com/remote-jobs/remote-senior-staff-infrastructure-security-engineer-civilgrid-1137687",
        location="Remote",
        currency="USD",
        salary_range="$137.3k - $192.9k USD",
        remote=True,
        contract=False,
        tags=["aws", "terraform", "security", "kubernetes", "devops"],
        summary="Build zero-trust AWS infrastructure, hardened Kubernetes clusters, and IaC controls.",
        cv_evidence=["AWS IAM & Zero-Trust IaC", "Security Compliance Automation"],
        graph_nodes=["cv:security", "cv:terraform", "cv:aws-eks"],
    ),
    JobRecord(
        id="wwr-planetscale-support",
        source="weworkremotely",
        title="Enterprise Cloud & Database Support Engineer",
        company="PlanetScale",
        url="https://weworkremotely.com/remote-jobs/planetscale-enterprise-support-engineer",
        location="Worldwide Remote",
        currency="USD",
        salary_range="$120k - $200k USD",
        remote=True,
        contract=False,
        tags=["kubernetes", "aws", "mysql", "linux", "sre"],
        summary="Debug high-scale distributed database clusters across Kubernetes and cloud providers.",
        cv_evidence=["High-Load Storage & Postgres/MySQL", "Kubernetes Troubleshooting"],
        graph_nodes=["cv:storage", "cv:kubernetes", "cv:linux"],
    ),
    JobRecord(
        id="ats-odinlabs-devops",
        source="ats",
        title="Senior DevOps & Cloud Engineer",
        company="Odin Labs (Greenhouse ATS)",
        url="https://boards.greenhouse.io/odinlabs/jobs/4451905009",
        location="Remote",
        currency="USD",
        salary_range="USD Full-Time Remote",
        remote=True,
        contract=False,
        tags=["aws", "kubernetes", "terraform", "docker", "devops"],
        summary="Direct Greenhouse ATS role owning AWS cloud automation and developer workflows.",
        cv_evidence=["AWS & Terraform Automation", "Container Orchestration"],
        graph_nodes=["cv:aws-eks", "cv:terraform", "cv:docker"],
    ),
    JobRecord(
        id="cryptojobslist-infra-sre",
        source="cryptojobslist",
        title="Protocol Infrastructure & SRE Contractor",
        company="Distributed Validator Network",
        url="https://cryptojobslist.com/jobs/protocol-infrastructure-sre-remote",
        location="Global Remote",
        currency="USD",
        salary_range="$150k - $210k USDC/USD",
        remote=True,
        contract=True,
        tags=["linux", "bare-metal", "kubernetes", "terraform", "sre", "rust"],
        summary="Bare-metal + cloud validator orchestration in USD/USDC.",
        cv_evidence=["Bare-Metal & Proxmox HA", "Rust & Distributed Consensus Ops"],
        graph_nodes=["cv:bare-metal", "cv:rust", "cv:sre"],
    ),
    JobRecord(
        id="upwork-sre-ai-agents",
        source="upwork",
        title="Principal SRE & AI Agent Infrastructure Architect",
        company="Enterprise AI Client",
        url="https://www.upwork.com/jobs/~02117746114701649932",
        location="Worldwide Remote",
        currency="USD",
        salary_range="$150 - $200/hr USD",
        remote=True,
        contract=True,
        tags=["aws", "kubernetes", "terraform", "ai-agents", "sre", "docker"],
        summary="High-rate Upwork hourly contract architecting agentic container sandboxes on AWS.",
        cv_evidence=["Upwork Top Rated Plus (10,600+ hrs)", "LangGraph + Isolated Runtimes"],
        graph_nodes=["cv:upwork-trp", "cv:ai-agents", "cv:kubernetes"],
    ),
    JobRecord(
        id="upwork-aws-hetzner-dr",
        source="upwork",
        title="AWS + Hetzner Bare-Metal Disaster Recovery Architect",
        company="InfraOps Client",
        url="https://www.upwork.com/jobs/~02121644210619511391",
        location="Remote",
        currency="USD",
        salary_range="$1,000 - $2,500 Fixed USD",
        remote=True,
        contract=True,
        tags=["aws", "bare-metal", "terraform", "linux", "devops"],
        summary="Fixed-price DR failover engineering between AWS and Hetzner bare-metal nodes.",
        cv_evidence=["Bare-Metal + AWS Hybrid DR", "Ceph & Terraform"],
        graph_nodes=["cv:bare-metal", "cv:aws-eks", "cv:terraform"],
    ),
)


def fnv1a64_hex(text: str) -> str:
    """Compute FNV-1a 64-bit hex digest matching `w0m-wasm-utils`."""
    h = 0xCBF29CE484222325
    for b in text.encode("utf-8"):
        h ^= b
        h = (h * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return f"{h:016x}"


def levenshtein_distance(a: str, b: str) -> int:
    """Compute bounded Levenshtein edit distance."""
    la, lb = len(a), len(b)
    if la == 0:
        return lb
    if lb == 0:
        return la
    prev = list(range(lb + 1))
    for i, ca in enumerate(a, start=1):
        curr = [i]
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            curr.append(min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost))
        prev = curr
    return prev[-1]


def normalize_source_id(raw: str) -> str | None:
    cleaned = re.sub(r"[\s_-]+", "", raw.strip().lower())
    return SOURCE_ALIASES.get(cleaned)


def resolve_active_sources(
    include_sources: list[str] | None = None,
    exclude_sources: list[str] | None = None,
) -> list[str]:
    """Resolve active sources using include-first then exclude filtering."""
    inc_raw = include_sources if include_sources else ["all"]
    exc_raw = exclude_sources or []

    includes_all = any(x.strip().lower() in {"all", "*"} for x in inc_raw)
    included = set(ALL_JOB_SOURCES if includes_all else [])
    if not includes_all:
        for item in inc_raw:
            norm = normalize_source_id(item)
            if norm:
                included.add(norm)

    excluded: set[str] = set()
    for item in exc_raw:
        norm = normalize_source_id(item)
        if norm:
            excluded.add(norm)

    return [src for src in ALL_JOB_SOURCES if src in included and src not in excluded]


def load_cv_profile_tokens(cv_path: Path = CV_SEED_PATH) -> tuple[list[str], int]:
    """Load grounded CV skill tokens from `cv-profile-seed.json` + local KB doc count."""
    tokens: list[str] = []
    if cv_path.exists():
        try:
            data = json.loads(cv_path.read_text(encoding="utf-8"))
            for group in data.get("skillGroups", []):
                for skill in group.get("skills", []):
                    name = str(skill.get("name", "")).lower()
                    for part in re.findall(r"[a-z0-9+#.-]{2,}", name):
                        if part not in tokens:
                            tokens.append(part)
        except (OSError, json.JSONDecodeError):
            pass

    if not tokens:
        tokens = [
            "aws",
            "gcp",
            "kubernetes",
            "terraform",
            "docker",
            "linux",
            "bare-metal",
            "ceph",
            "cloudflare",
            "rust",
            "devops",
            "sre",
        ]

    kb_docs = 0
    if KB_SQLITE_PATH.exists():
        try:
            conn = sqlite3.connect(str(KB_SQLITE_PATH))
            row = conn.execute("SELECT COUNT(*) FROM docs").fetchone()
            if row:
                kb_docs = int(row[0])
            conn.close()
        except sqlite3.Error:
            kb_docs = 0

    return tokens, kb_docs


def tokenize(text: str) -> list[str]:
    return [tok for tok in re.split(r"[^a-z0-9/+#.-]+", text.lower()) if len(tok) >= 2]


def _fetch_json(url: str, timeout: int = 8) -> Any:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "w0m-k7-job-hunter/1.0 (+https://webomage.com)"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def _fetch_text(url: str, timeout: int = 8) -> str:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "w0m-k7-job-hunter/1.0 (+https://webomage.com)"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def fetch_live_listings(active_sources: list[str], query: str) -> list[JobRecord]:
    """Best-effort live HTTP fetchers for enabled channels (never blocks on transient errors)."""
    live: list[JobRecord] = []
    q_enc = urllib.parse.quote_plus(query or "devops")

    if "hn" in active_sources:
        try:
            data = _fetch_json(
                f"https://hn.algolia.com/api/v1/search?query={q_enc}+remote&tags=comment&hitsPerPage=10"
            )
            for hit in data.get("hits", []):
                text = re.sub(r"<[^>]+>", " ", str(hit.get("comment_text", "")))
                if not text.strip():
                    continue
                item_id = str(hit.get("objectID", ""))
                first_line = text.strip().splitlines()[0][:90]
                live.append(
                    JobRecord(
                        id=f"hn-live-{item_id}",
                        source="hn",
                        title=first_line,
                        company=str(hit.get("author", "HN Poster")),
                        url=f"https://news.ycombinator.com/item?id={item_id}",
                        location="Remote",
                        currency="USD" if "$" in text or "usd" in text.lower() else "UNKNOWN",
                        salary_range="See HN Thread",
                        remote="remote" in text.lower(),
                        contract=any(w in text.lower() for w in ("contract", "freelance", "b2b")),
                        tags=[t for t in ("aws", "gcp", "kubernetes", "terraform", "devops", "sre") if t in text.lower()],
                        summary=text[:240],
                        cv_evidence=["HN Direct Engineering Thread"],
                        graph_nodes=["source:hn-algolia"],
                    )
                )
        except (urllib.error.URLError, TimeoutError, ValueError):
            pass

    if "jobicy" in active_sources:
        try:
            data = _fetch_json("https://jobicy.com/api/v2/remote-jobs?count=10&tag=devops")
            for job in data.get("jobs", []):
                live.append(
                    JobRecord(
                        id=f"jobicy-live-{job.get('id', '')}",
                        source="jobicy",
                        title=str(job.get("jobTitle", "DevOps Engineer")),
                        company=str(job.get("companyName", "Unknown")),
                        url=str(job.get("url", "")),
                        location=str(job.get("jobGeo", "Anywhere")),
                        currency=str(job.get("salaryCurrency", "USD") or "USD"),
                        salary_range=f"{job.get('annualSalaryMin', '')}-{job.get('annualSalaryMax', '')} {job.get('salaryCurrency', 'USD')}".strip("- "),
                        remote=True,
                        contract="contract" in str(job.get("jobType", "")).lower(),
                        tags=["devops", "remote"],
                        summary=re.sub(r"<[^>]+>", " ", str(job.get("jobExcerpt", "")))[:240],
                        cv_evidence=["Jobicy Live Feed"],
                        graph_nodes=["source:jobicy"],
                    )
                )
        except (urllib.error.URLError, TimeoutError, ValueError):
            pass

    if "weworkremotely" in active_sources:
        try:
            xml_text = _fetch_text("https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss")
            root = ET.fromstring(xml_text)
            for item in root.findall("./channel/item")[:10]:
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                desc = re.sub(r"<[^>]+>", " ", item.findtext("description") or "")[:240]
                if title and link:
                    live.append(
                        JobRecord(
                            id=f"wwr-live-{fnv1a64_hex(link)[:10]}",
                            source="weworkremotely",
                            title=title,
                            company=title.split(":")[0].strip() if ":" in title else "WWR Employer",
                            url=link,
                            location="Worldwide Remote",
                            currency="USD" if "$" in desc or "usd" in desc.lower() or "contractor" in desc.lower() else "USD",
                            salary_range="See WWR Listing",
                            remote=True,
                            contract=any(w in (title + " " + desc).lower() for w in ("contract", "contractor", "b2b")),
                            tags=[t for t in ("aws", "kubernetes", "terraform", "linux", "devops", "sre") if t in (title + " " + desc).lower()],
                            summary=desc,
                            cv_evidence=["WWR Live RSS"],
                            graph_nodes=["source:weworkremotely"],
                        )
                    )
        except (urllib.error.URLError, TimeoutError, ET.ParseError, ValueError):
            pass

    return live


def search_jobs(
    *,
    include_sources: list[str] | None = None,
    exclude_sources: list[str] | None = None,
    query: str = "devops sre kubernetes terraform",
    remote_only: bool = True,
    usd_only: bool = True,
    contract_only: bool = False,
    min_score: int = 0,
    limit: int = 20,
    live: bool = False,
) -> dict[str, Any]:
    active_sources = resolve_active_sources(include_sources, exclude_sources)
    active_set = set(active_sources)
    cv_tokens, kb_docs = load_cv_profile_tokens()
    q_tokens = tokenize(query) or ["devops", "sre", "kubernetes", "terraform"]

    pool: list[JobRecord] = list(CURATED_CATALOG)
    if live:
        pool.extend(fetch_live_listings(active_sources, query))

    # Deduplicate by URL, FNV-1a fingerprint, and bounded Levenshtein title
    seen_urls: set[str] = set()
    seen_fps: set[str] = set()
    seen_titles: list[tuple[str, str]] = []
    deduped: list[JobRecord] = []

    for job in pool:
        if job.source not in active_set:
            continue
        if remote_only and not job.remote:
            continue
        if usd_only and job.currency.upper() != "USD":
            continue
        if contract_only and not job.contract:
            continue

        fp = fnv1a64_hex(f"{job.company.lower()}|{job.title.lower()}")
        if job.url in seen_urls or fp in seen_fps:
            continue
        c_norm = job.company.lower().strip()
        t_norm = job.title.lower().strip()
        if any(sc == c_norm and levenshtein_distance(st, t_norm) <= 3 for sc, st in seen_titles):
            continue

        seen_urls.add(job.url)
        seen_fps.add(fp)
        seen_titles.append((c_norm, t_norm))
        deduped.append(job)

    # BM25 + TF-IDF Cosine Vector RRF over the filtered corpus
    docs_tokens = [
        tokenize(f"{j.title} {j.company} {' '.join(j.tags)} {j.summary}") for j in deduped
    ]
    n_docs = max(1, len(docs_tokens))
    avgdl = sum(len(d) for d in docs_tokens) / n_docs if docs_tokens else 1.0
    df: Counter[str] = Counter()
    for d in docs_tokens:
        for tok in set(d):
            df[tok] += 1

    scored_rows: list[dict[str, Any]] = []
    q_counts = Counter(q_tokens)

    for idx, job in enumerate(deduped):
        d_toks = docs_tokens[idx]
        d_counts = Counter(d_toks)
        dl = max(1, len(d_toks))

        # BM25
        bm25 = 0.0
        k1, b = 1.5, 0.75
        for tok in q_tokens:
            tf = d_counts.get(tok, 0)
            if tf == 0:
                continue
            idf = math.log(1.0 + (n_docs - df[tok] + 0.5) / (df[tok] + 0.5))
            bm25 += idf * ((tf * (k1 + 1.0)) / (tf + k1 * (1.0 - b + b * (dl / max(1.0, avgdl)))))

        # TF-IDF Cosine against query + CV tokens
        target_vec_tokens = set(q_tokens) | set(cv_tokens[:12])
        dot = 0.0
        norm_q = 0.0
        norm_d = 0.0
        for tok in target_vec_tokens:
            idf = math.log(1.0 + n_docs / (1.0 + df[tok]))
            w_q = (q_counts.get(tok, 0) + (0.4 if tok in cv_tokens else 0.0)) * idf
            w_d = d_counts.get(tok, 0) * idf
            dot += w_q * w_d
            norm_q += w_q * w_q
            norm_d += w_d * w_d
        cosine = dot / (math.sqrt(norm_q) * math.sqrt(norm_d)) if norm_q > 0 and norm_d > 0 else 0.0

        doc_text = f"{job.title} {' '.join(job.tags)} {job.summary}".lower()
        cv_hits = [t for t in cv_tokens if t in doc_text]
        q_hits = [t for t in q_tokens if t in doc_text]

        stack = min(35, round(((min(6, len(cv_hits)) / 6.0) * 100 + len(q_hits) * 4) * 35 / 100))
        ownership = 18 if any(w in job.title.lower() for w in ("staff", "principal", "lead")) or job.contract else 14
        commercials = 20 if job.currency.upper() == "USD" and "$" in job.salary_range else 16 if job.currency.upper() == "USD" else 6
        timezone_remote = 15 if job.remote else 4
        signal = 10 if job.source in {"hn", "ats"} else 9 if job.source == "upwork" else 8
        total = stack + ownership + commercials + timezone_remote + signal

        scored_rows.append(
            {
                **asdict(job),
                "fingerprint": fnv1a64_hex(f"{job.company}|{job.title}|{job.url}"),
                "rubric": {
                    "stack": stack,
                    "ownership": ownership,
                    "commercials": commercials,
                    "timezone_remote": timezone_remote,
                    "signal": signal,
                    "total": total,
                },
                "bm25_score": round(bm25, 4),
                "cosine_score": round(cosine, 4),
                "cv_hits": cv_hits[:8],
            }
        )

    by_bm25 = sorted(range(len(scored_rows)), key=lambda i: scored_rows[i]["bm25_score"], reverse=True)
    by_cos = sorted(range(len(scored_rows)), key=lambda i: scored_rows[i]["cosine_score"], reverse=True)
    bm25_rank = {idx: rank + 1 for rank, idx in enumerate(by_bm25)}
    cos_rank = {idx: rank + 1 for rank, idx in enumerate(by_cos)}

    for idx, row in enumerate(scored_rows):
        row["rrf_score"] = round(1.0 / (RRF_K + bm25_rank[idx]) + 1.0 / (RRF_K + cos_rank[idx]), 4)

    ranked = [r for r in scored_rows if r["rubric"]["total"] >= min_score]
    ranked.sort(key=lambda r: (r["rubric"]["total"], r["rrf_score"]), reverse=True)

    return {
        "include_sources": include_sources or ["all"],
        "exclude_sources": exclude_sources or [],
        "active_sources": active_sources,
        "filters": {
            "query": query,
            "remote_only": remote_only,
            "usd_only": usd_only,
            "contract_only": contract_only,
            "min_score": min_score,
            "live": live,
        },
        "grounding": {
            "cv_seed_path": str(CV_SEED_PATH.relative_to(ROOT)),
            "cv_token_count": len(cv_tokens),
            "kb_sqlite_docs": kb_docs,
        },
        "total_matched": len(ranked),
        "results": ranked[:limit],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="@wom + @k7 Multi-Channel Job Hunter")
    parser.add_argument("--include", default="all", help="Comma-separated sources or 'all'")
    parser.add_argument("--exclude", default="", help="Comma-separated sources to exclude (e.g. upwork)")
    parser.add_argument("--only", default="", help="Shortcut to include only these sources")
    parser.add_argument("--query", default="devops sre kubernetes terraform", help="Search query")
    parser.add_argument("--remote-only", dest="remote_only", action="store_true", default=True)
    parser.add_argument("--all-locations", dest="remote_only", action="store_false")
    parser.add_argument("--usd-only", dest="usd_only", action="store_true", default=True)
    parser.add_argument("--all-currencies", dest="usd_only", action="store_false")
    parser.add_argument("--contract-only", action="store_true", default=False)
    parser.add_argument("--min-score", type=int, default=0)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--live", action="store_true", default=False)
    parser.add_argument("--json", action="store_true", default=False)

    args = parser.parse_args(argv)
    include_list = [x.strip() for x in (args.only or args.include).split(",") if x.strip()]
    exclude_list = [x.strip() for x in args.exclude.split(",") if x.strip()] if not args.only else []

    payload = search_jobs(
        include_sources=include_list,
        exclude_sources=exclude_list,
        query=args.query,
        remote_only=args.remote_only,
        usd_only=args.usd_only,
        contract_only=args.contract_only,
        min_score=args.min_score,
        limit=args.limit,
        live=args.live,
    )

    if args.json:
        print(json.dumps(payload, indent=2))
        return 0

    print(
        f"k7/w0m Job Hunter | active={len(payload['active_sources'])}/13 "
        f"| exclude={payload['exclude_sources'] or ['none']} | matches={payload['total_matched']}"
    )
    for idx, row in enumerate(payload["results"], start=1):
        print(
            f"{idx:02d}. [{row['rubric']['total']:3d}/100] [{row['source']:14s}] "
            f"{row['company']} — {row['title']} ({row['salary_range']}) "
            f"rrf={row['rrf_score']:.4f} | {row['url']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
