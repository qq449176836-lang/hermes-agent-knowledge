#!/usr/bin/env python3
"""
Explorer — Information Source Crawler & Value Scoring Engine
=============================================================
Companion script for: EVOLUTION-ENGINE.md

Purpose:
    Crawls external information sources (GitHub Trending, Hacker News)
    and scores each item using a weighted multi-dimensional algorithm to
    determine its evolutionary value for the knowledge base.

Scoring Algorithm:
    Novelty (30%)  + Utility (40%) + Feasibility (20%) + Vitality (10%)
    Score range: 1-10.
    Thresholds: >= 8  → RECOMMEND (recommend)
                 >= 7  → REVIEW   (pending)
                 <  7  → ARCHIVE  (archived)

Usage:
    python explorer.py --source github --top 20
    python explorer.py --source hn --top 10
    python explorer.py --source all --top 15
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class ScoredItem:
    """A single information item with its source metadata and value scores."""

    source: str
    title: str
    url: str
    description: str
    stars: int
    language: Optional[str]
    created_at: Optional[str]
    scores: Dict[str, float] = field(default_factory=dict)
    total_score: float = 0.0
    verdict: str = "archived"


# ---------------------------------------------------------------------------
# API Clients
# ---------------------------------------------------------------------------

def fetch_github_trending(top_n: int = 25) -> List[Dict[str, Any]]:
    """Fetch trending repositories from the GitHub API.

    Uses the public search endpoint sorted by stars, filtered to repos
    created/pushed in the last 7 days for a rough "trending" heuristic.
    """
    # GitHub search: repos with >50 stars, sorted by stars, created in last 7 days
    from datetime import timedelta

    seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    query = f"stars:>50+created:>={seven_days_ago}"
    url = f"https://api.github.com/search/repositories?q={query}&sort=stars&order=desc&per_page={top_n}"

    req = Request(url, headers={
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Evolution-Explorer/1.0"
    })

    try:
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except URLError as e:
        print(f"[WARN] GitHub API unreachable: {e}", file=sys.stderr)
        return []

    items = data.get("items", [])
    results: List[Dict[str, Any]] = []
    for repo in items:
        results.append({
            "title": repo.get("full_name", repo.get("name", "")),
            "url": repo.get("html_url", ""),
            "description": (repo.get("description") or ""),
            "stars": repo.get("stargazers_count", 0),
            "language": repo.get("language"),
            "created_at": repo.get("created_at"),
            "forks": repo.get("forks_count", 0),
            "open_issues": repo.get("open_issues_count", 0),
        })
    return results


def fetch_hacker_news_top(top_n: int = 30) -> List[Dict[str, Any]]:
    """Fetch top stories from the Hacker News API (Firebase).

    Retrieves story IDs from /v0/topstories then fetches each story detail.
    """
    base = "https://hacker-news.firebaseio.com/v0"

    try:
        with urlopen(f"{base}/topstories.json", timeout=10) as resp:
            story_ids = json.loads(resp.read().decode())
    except URLError as e:
        print(f"[WARN] Hacker News API unreachable: {e}", file=sys.stderr)
        return []

    results: List[Dict[str, Any]] = []
    for sid in story_ids[:top_n]:
        try:
            with urlopen(f"{base}/item/{sid}.json", timeout=10) as resp:
                item = json.loads(resp.read().decode())
        except URLError:
            continue

        if item is None or item.get("type") != "story":
            continue

        results.append({
            "title": item.get("title", ""),
            "url": item.get("url", f"https://news.ycombinator.com/item?id={sid}"),
            "description": "",
            "stars": item.get("score", 0),
            "language": None,
            "created_at": datetime.fromtimestamp(
                item.get("time", 0), tz=timezone.utc
            ).isoformat(),
            "descendants": item.get("descendants", 0),
        })
    return results


# ---------------------------------------------------------------------------
# Scoring Engine
# ---------------------------------------------------------------------------

def score_novelty(item: Dict[str, Any], source: str) -> float:
    """Estimate novelty (0-10) based on signals like title length,
    description distinctiveness, and source freshness."""
    score = 5.0  # baseline

    title = item.get("title", "")
    desc = item.get("description", "")

    # Longer titles often indicate more specific/novel topics
    title_words = len(title.split())
    if title_words >= 7:
        score += 1.5
    elif title_words >= 4:
        score += 0.8

    # Presence of a meaningful description helps novelty assessment
    if len(desc) > 80:
        score += 1.5
    elif len(desc) > 30:
        score += 0.7

    # Very new items (last 48h) get a slight novelty boost
    created = item.get("created_at")
    if created:
        try:
            dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            age_hours = (datetime.now(timezone.utc) - dt).total_seconds() / 3600
            if age_hours < 24:
                score += 1.5
            elif age_hours < 72:
                score += 0.5
        except (ValueError, TypeError):
            pass

    return min(10.0, max(1.0, score))


def score_utility(item: Dict[str, Any], source: str) -> float:
    """Estimate practical utility (0-10). Higher star counts and
    community engagement correlate with usefulness."""
    score = 5.0

    stars = item.get("stars", 0)
    if stars > 5000:
        score += 3.0
    elif stars > 1000:
        score += 2.0
    elif stars > 100:
        score += 1.0

    # Forks imply reuse / practical adoption
    forks = item.get("forks", 0)
    if forks > 1000:
        score += 1.5
    elif forks > 100:
        score += 0.7

    # Discussion depth (HN descendants) signals practical relevance
    descendants = item.get("descendants", 0)
    if descendants > 200:
        score += 1.5
    elif descendants > 50:
        score += 0.7

    return min(10.0, max(1.0, score))


def score_feasibility(item: Dict[str, Any], source: str) -> float:
    """Estimate feasibility of adoption (0-10). Smaller, focused projects
    with fewer open issues and active maintenance are more feasible."""
    score = 5.0

    # Language diversity — popular languages are more feasible to adopt
    lang = item.get("language")
    feasible_langs = {
        "Python", "JavaScript", "TypeScript", "Go", "Rust",
        "Java", "Kotlin", "Ruby", "Shell", "HTML",
    }
    if lang in feasible_langs:
        score += 1.5

    # Open issues count (lower is more feasible)
    open_issues = item.get("open_issues", -1)
    if 0 <= open_issues < 20:
        score += 1.5
    elif 20 <= open_issues < 100:
        score += 0.5

    # Clear, concise description = better documented = more feasible
    desc = item.get("description", "")
    if len(desc) > 120:
        score += 1.0

    return min(10.0, max(1.0, score))


def score_vitality(item: Dict[str, Any], source: str) -> float:
    """Estimate community vitality (0-10). Recent updates, active discussions,
    and engagement velocity indicate a healthy living project."""
    score = 5.0

    stars = item.get("stars", 0)
    # High star velocity (stars gained recently) hints at active community
    if stars > 2000:
        score += 2.0
    elif stars > 200:
        score += 1.0

    # Comments/descendants show active discussion
    descendants = item.get("descendants", 0)
    if descendants > 100:
        score += 2.0
    elif descendants > 30:
        score += 1.0

    # Recent creation signals current relevance
    created = item.get("created_at")
    if created:
        try:
            dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - dt).total_seconds() / 86400
            if age_days < 3:
                score += 2.0
            elif age_days < 14:
                score += 1.0
        except (ValueError, TypeError):
            pass

    return min(10.0, max(1.0, score))


def compute_total_score(scores: Dict[str, float]) -> float:
    """Compute weighted total from individual dimension scores.

    Weights: Novelty=0.30, Utility=0.40, Feasibility=0.20, Vitality=0.10
    """
    weights = {
        "novelty": 0.30,
        "utility": 0.40,
        "feasibility": 0.20,
        "vitality": 0.10,
    }
    total = sum(scores.get(k, 5.0) * v for k, v in weights.items())
    return round(total, 2)


def classify_verdict(total_score: float) -> str:
    """Map total score to a verdict label."""
    if total_score >= 8.0:
        return "recommend"
    elif total_score >= 7.0:
        return "review"
    else:
        return "archived"


def score_items(
    raw_items: List[Dict[str, Any]], source: str
) -> List[ScoredItem]:
    """Apply the full scoring pipeline to a list of raw items."""
    results: List[ScoredItem] = []
    for item in raw_items:
        scores = {
            "novelty": round(score_novelty(item, source), 2),
            "utility": round(score_utility(item, source), 2),
            "feasibility": round(score_feasibility(item, source), 2),
            "vitality": round(score_vitality(item, source), 2),
        }
        total = compute_total_score(scores)
        verdict = classify_verdict(total)

        results.append(ScoredItem(
            source=source,
            title=item.get("title", ""),
            url=item.get("url", ""),
            description=item.get("description", ""),
            stars=item.get("stars", 0),
            language=item.get("language"),
            created_at=item.get("created_at"),
            scores=scores,
            total_score=total,
            verdict=verdict,
        ))
    return results


# ---------------------------------------------------------------------------
# Output Formatting
# ---------------------------------------------------------------------------

def format_output(items: List[ScoredItem], fmt: str = "json") -> str:
    """Format scored items as JSON (pretty) or a plain-text summary."""
    if fmt == "json":
        output = []
        for item in items:
            output.append({
                "source": item.source,
                "title": item.title,
                "url": item.url,
                "description": item.description,
                "stars": item.stars,
                "language": item.language,
                "created_at": item.created_at,
                "scores": item.scores,
                "total_score": item.total_score,
                "verdict": item.verdict,
            })
        return json.dumps(output, indent=2, ensure_ascii=False)

    # Plain-text summary
    lines: List[str] = []
    for item in items:
        emoji = {"recommend": "⭐", "review": "📋", "archived": "📦"}.get(item.verdict, "❓")
        lines.append(
            f"{emoji} [{item.verdict.upper()}] {item.title}  "
            f"({item.total_score}/10)  {item.url}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """Construct the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Evolution Explorer — crawl sources and score items for knowledge value.",
    )
    parser.add_argument(
        "--source", "-s",
        choices=["github", "hn", "all"],
        default="all",
        help="Information source to crawl (default: all)",
    )
    parser.add_argument(
        "--top", "-n",
        type=int,
        default=25,
        help="Number of top items to fetch per source (default: 25)",
    )
    parser.add_argument(
        "--format", "-f",
        choices=["json", "text"],
        default="json",
        help="Output format (default: json)",
    )
    parser.add_argument(
        "--filter", "-v",
        choices=["recommend", "review", "archived", "all"],
        default="all",
        help="Filter results by verdict (default: all)",
    )
    return parser


def main() -> None:
    """Entry point: crawl sources, score items, and print results."""
    parser = build_parser()
    args = parser.parse_args()

    all_items: List[ScoredItem] = []

    if args.source in ("github", "all"):
        print(f"[INFO] Fetching GitHub trending (top {args.top})...", file=sys.stderr)
        gh_raw = fetch_github_trending(args.top)
        print(f"[INFO] GitHub returned {len(gh_raw)} items", file=sys.stderr)
        all_items.extend(score_items(gh_raw, source="github"))

    if args.source in ("hn", "all"):
        print(f"[INFO] Fetching Hacker News top stories (top {args.top})...", file=sys.stderr)
        hn_raw = fetch_hacker_news_top(args.top)
        print(f"[INFO] Hacker News returned {len(hn_raw)} items", file=sys.stderr)
        all_items.extend(score_items(hn_raw, source="hackernews"))

    # Sort by total score descending
    all_items.sort(key=lambda x: x.total_score, reverse=True)

    # Apply verdict filter
    if args.filter != "all":
        all_items = [i for i in all_items if i.verdict == args.filter]

    print(format_output(all_items, fmt=args.format))


if __name__ == "__main__":
    main()
