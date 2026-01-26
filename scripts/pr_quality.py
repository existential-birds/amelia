#!/usr/bin/env python3
"""Measure PR quality over time by counting coderabbitai review comments.

Requires the `gh` CLI to be installed and authenticated.

Usage:
    python scripts/pr_quality.py                  # all merged PRs
    python scripts/pr_quality.py --state all       # all PRs regardless of state
    python scripts/pr_quality.py --limit 50        # last 50 PRs
    python scripts/pr_quality.py --csv             # output as CSV
    python scripts/pr_quality.py --summary         # weekly summary only
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any

REPO = "existential-birds/amelia"
BOT_LOGIN = "coderabbitai[bot]"


@dataclass
class PRStats:
    number: int
    title: str
    author: str
    state: str
    merged_at: str | None
    created_at: str
    review_comments: int  # inline code comments
    issue_comments: int  # general PR conversation comments
    reviews: int  # review submissions (approve/request changes/comment)
    additions: int
    deletions: int
    changed_files: int
    thumbs_up: int  # +1 reactions on bot inline comments
    thumbs_down: int  # -1 reactions on bot inline comments

    @property
    def total_bot_comments(self) -> int:
        return self.review_comments + self.issue_comments + self.reviews

    @property
    def diff_size(self) -> int:
        """Total lines changed (additions + deletions)."""
        return self.additions + self.deletions

    @property
    def comments_per_100_lines(self) -> float | None:
        """Inline review comments normalized per 100 lines of diff. None if no diff."""
        if self.diff_size == 0:
            return None
        return self.review_comments / self.diff_size * 100

    @property
    def triaged(self) -> int:
        """Inline comments that have been triaged (reacted to)."""
        return self.thumbs_up + self.thumbs_down

    @property
    def untriaged(self) -> int:
        """Inline comments with no reaction yet."""
        return self.review_comments - self.triaged

    @property
    def valuable_pct(self) -> float | None:
        """Percentage of triaged inline comments marked valuable. None if none triaged."""
        if self.triaged == 0:
            return None
        return self.thumbs_up / self.triaged * 100

    @property
    def date(self) -> str:
        """Return the most relevant date (merged_at if available, else created_at)."""
        raw = self.merged_at or self.created_at
        return raw[:10] if raw else "unknown"

    @property
    def week(self) -> str:
        """ISO year-week string for grouping."""
        raw = self.merged_at or self.created_at
        if not raw:
            return "unknown"
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        iso = dt.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"


def gh_api(endpoint: str) -> Any:
    """Call the GitHub API via gh CLI, handling pagination."""
    result = subprocess.run(
        ["gh", "api", "--paginate", endpoint],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def gh_api_paginated_list(endpoint: str) -> list[Any]:
    """Call a list endpoint with pagination. gh --paginate concatenates JSON arrays."""
    result = subprocess.run(
        ["gh", "api", "--paginate", endpoint],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"  Warning: failed to fetch {endpoint}: {result.stderr.strip()}", file=sys.stderr)
        return []

    # gh --paginate concatenates JSON arrays, which produces invalid JSON
    # like [{...}][{...}]. We handle this by wrapping in an array.
    raw = result.stdout.strip()
    if not raw:
        return []

    # Try direct parse first (single page)
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else [data]
    except json.JSONDecodeError:
        pass

    # Multi-page: gh concatenates arrays like [a,b][c,d] -> parse each
    items: list[Any] = []
    decoder = json.JSONDecoder()
    pos = 0
    while pos < len(raw):
        if raw[pos] in " \t\n\r":
            pos += 1
            continue
        obj, end = decoder.raw_decode(raw, pos)
        if isinstance(obj, list):
            items.extend(obj)
        else:
            items.append(obj)
        pos = end
    return items


def count_bot_items(items: list[dict[str, Any]], login: str = BOT_LOGIN) -> int:
    """Count items authored by the given login."""
    return sum(1 for item in items if item.get("user", {}).get("login") == login)


@dataclass
class ReactionCounts:
    """Aggregate reaction counts across bot comments."""
    thumbs_up: int = 0
    thumbs_down: int = 0


def count_bot_reactions(items: list[dict[str, Any]], login: str = BOT_LOGIN) -> ReactionCounts:
    """Sum +1/-1 reactions on comments authored by the given login."""
    counts = ReactionCounts()
    for item in items:
        if item.get("user", {}).get("login") != login:
            continue
        reactions = item.get("reactions", {})
        counts.thumbs_up += reactions.get("+1", 0)
        counts.thumbs_down += reactions.get("-1", 0)
    return counts


def fetch_pr_stats(pr: dict[str, Any]) -> PRStats:
    """Fetch coderabbitai comment counts and diff stats for a single PR."""
    number = pr["number"]
    print(f"  Fetching PR #{number}...", file=sys.stderr, end="", flush=True)

    # The list endpoint doesn't include diff stats — fetch the PR detail
    detail = gh_api(f"repos/{REPO}/pulls/{number}")

    review_comments = gh_api_paginated_list(
        f"repos/{REPO}/pulls/{number}/comments?per_page=100"
    )
    issue_comments = gh_api_paginated_list(
        f"repos/{REPO}/issues/{number}/comments?per_page=100"
    )
    reviews = gh_api_paginated_list(
        f"repos/{REPO}/pulls/{number}/reviews?per_page=100"
    )

    # Reactions only matter on inline review comments (the actionable ones)
    reactions = count_bot_reactions(review_comments)

    stats = PRStats(
        number=number,
        title=pr["title"],
        author=pr.get("user", {}).get("login", "unknown"),
        state="merged" if pr.get("merged_at") else pr["state"],
        merged_at=pr.get("merged_at"),
        created_at=pr["created_at"],
        review_comments=count_bot_items(review_comments),
        issue_comments=count_bot_items(issue_comments),
        reviews=count_bot_items(reviews),
        additions=detail.get("additions", 0) or 0,
        deletions=detail.get("deletions", 0) or 0,
        changed_files=detail.get("changed_files", 0) or 0,
        thumbs_up=reactions.thumbs_up,
        thumbs_down=reactions.thumbs_down,
    )
    print(
        f" {stats.total_bot_comments} comments, +{stats.additions}/-{stats.deletions} lines"
        f", triage: {stats.thumbs_up}↑ {stats.thumbs_down}↓ {stats.untriaged}?",
        file=sys.stderr,
    )
    return stats


def fetch_all_prs(state: str = "closed", limit: int | None = None) -> list[dict[str, Any]]:
    """Fetch PRs from the repo."""
    per_page = min(limit or 100, 100)
    endpoint = f"repos/{REPO}/pulls?state={state}&sort=created&direction=desc&per_page={per_page}"

    if limit and limit <= 100:
        # Single page is enough
        return gh_api_paginated_list(endpoint)[:limit]

    prs = gh_api_paginated_list(endpoint)
    if limit:
        prs = prs[:limit]
    return prs


def fmt_density(val: float | None) -> str:
    """Format comments_per_100_lines, handling None."""
    return f"{val:.2f}" if val is not None else "n/a"


def fmt_pct(val: float | None) -> str:
    """Format a percentage, handling None."""
    return f"{val:.0f}%" if val is not None else "-"


def print_table(stats_list: list[PRStats]) -> None:
    """Print results as a formatted table."""
    if not stats_list:
        print("No PRs found.")
        return

    # Header
    print(
        f"{'PR':>5}  {'Date':10}  {'State':8}  "
        f"{'Diff':>7}  {'Files':>5}  "
        f"{'Inline':>6}  {'Per 100L':>8}  "
        f"{'Up':>3}  {'Down':>4}  {'?':>3}  {'Val%':>5}  "
        f"Title"
    )
    print("-" * 120)

    for s in stats_list:
        title = s.title[:35] + "..." if len(s.title) > 38 else s.title
        print(
            f"#{s.number:<4}  {s.date}  {s.state:8}  "
            f"{s.diff_size:>7}  {s.changed_files:>5}  "
            f"{s.review_comments:>6}  {fmt_density(s.comments_per_100_lines):>8}  "
            f"{s.thumbs_up:>3}  {s.thumbs_down:>4}  {s.untriaged:>3}  {fmt_pct(s.valuable_pct):>5}  "
            f"{title}"
        )

    # Summary
    total_comments = sum(s.total_bot_comments for s in stats_list)
    total_inline = sum(s.review_comments for s in stats_list)
    total_diff = sum(s.diff_size for s in stats_list)
    total_up = sum(s.thumbs_up for s in stats_list)
    total_down = sum(s.thumbs_down for s in stats_list)
    total_triaged = total_up + total_down
    total_untriaged = total_inline - total_triaged
    overall_density = total_inline / total_diff * 100 if total_diff else 0
    valuable_pct = total_up / total_triaged * 100 if total_triaged else 0
    print("-" * 120)
    print(
        f"{len(stats_list)} PRs, {total_diff} lines changed, "
        f"{total_inline} inline comments ({overall_density:.2f}/100L)  |  "
        f"Triage: {total_up} valuable, {total_down} noise, "
        f"{total_untriaged} untriaged"
        f"{f'  ({valuable_pct:.0f}% valuable)' if total_triaged else ''}"
    )


def print_csv(stats_list: list[PRStats]) -> None:
    """Print results as CSV."""
    writer = csv.writer(sys.stdout)
    writer.writerow([
        "pr_number", "date", "week", "author", "state", "title",
        "additions", "deletions", "diff_size", "changed_files",
        "inline_comments", "issue_comments", "reviews", "total_comments",
        "inline_per_100_lines",
        "thumbs_up", "thumbs_down", "untriaged", "valuable_pct",
    ])
    for s in stats_list:
        writer.writerow([
            s.number, s.date, s.week, s.author, s.state, s.title,
            s.additions, s.deletions, s.diff_size, s.changed_files,
            s.review_comments, s.issue_comments, s.reviews, s.total_bot_comments,
            f"{s.comments_per_100_lines:.4f}" if s.comments_per_100_lines is not None else "",
            s.thumbs_up, s.thumbs_down, s.untriaged,
            f"{s.valuable_pct:.2f}" if s.valuable_pct is not None else "",
        ])


def print_weekly_summary(stats_list: list[PRStats]) -> None:
    """Print a weekly summary of comment trends."""
    if not stats_list:
        print("No PRs found.")
        return

    weeks: dict[str, list[PRStats]] = defaultdict(list)
    for s in stats_list:
        weeks[s.week].append(s)

    print(
        f"{'Week':10}  {'PRs':>4}  {'Diff':>8}  "
        f"{'Inline':>6}  {'Per 100L':>8}  "
        f"{'Up':>4}  {'Down':>4}  {'?':>4}  {'Val%':>5}"
    )
    print("-" * 75)

    for week in sorted(weeks.keys()):
        prs = weeks[week]
        total_inline = sum(s.review_comments for s in prs)
        total_diff = sum(s.diff_size for s in prs)
        total_up = sum(s.thumbs_up for s in prs)
        total_down = sum(s.thumbs_down for s in prs)
        total_untriaged = total_inline - total_up - total_down
        density = total_inline / total_diff * 100 if total_diff else 0
        triaged = total_up + total_down
        val_pct = fmt_pct(total_up / triaged * 100 if triaged else None)
        print(
            f"{week:10}  {len(prs):>4}  {total_diff:>8}  "
            f"{total_inline:>6}  {density:>8.2f}  "
            f"{total_up:>4}  {total_down:>4}  {total_untriaged:>4}  {val_pct:>5}"
        )

    # Overall
    inline_all = sum(s.review_comments for s in stats_list)
    diff_all = sum(s.diff_size for s in stats_list)
    up_all = sum(s.thumbs_up for s in stats_list)
    down_all = sum(s.thumbs_down for s in stats_list)
    untriaged_all = inline_all - up_all - down_all
    density_all = inline_all / diff_all * 100 if diff_all else 0
    triaged_all = up_all + down_all
    val_pct_all = fmt_pct(up_all / triaged_all * 100 if triaged_all else None)
    print("-" * 75)
    print(
        f"{'Overall':10}  {len(stats_list):>4}  {diff_all:>8}  "
        f"{inline_all:>6}  {density_all:>8.2f}  "
        f"{up_all:>4}  {down_all:>4}  {untriaged_all:>4}  {val_pct_all:>5}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure PR quality via coderabbitai comment counts")
    parser.add_argument("--state", default="closed", choices=["open", "closed", "all"],
                        help="PR state filter (default: closed)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Max number of PRs to analyze")
    parser.add_argument("--merged-only", action="store_true",
                        help="Only include merged PRs (ignored if --state=open)")
    parser.add_argument("--csv", action="store_true", dest="csv_output",
                        help="Output as CSV")
    parser.add_argument("--summary", action="store_true",
                        help="Show weekly summary instead of per-PR table")
    args = parser.parse_args()

    print(f"Fetching PRs from {REPO} (state={args.state})...", file=sys.stderr)
    prs = fetch_all_prs(state=args.state, limit=args.limit)

    if args.merged_only and args.state != "open":
        prs = [pr for pr in prs if pr.get("merged_at")]

    if not prs:
        print("No PRs found matching criteria.", file=sys.stderr)
        sys.exit(0)

    print(f"Analyzing {len(prs)} PRs...", file=sys.stderr)
    stats_list = [fetch_pr_stats(pr) for pr in prs]

    # Sort by date ascending for trend visibility
    stats_list.sort(key=lambda s: s.date)

    print(file=sys.stderr)  # blank line separator

    if args.csv_output:
        print_csv(stats_list)
    elif args.summary:
        print_weekly_summary(stats_list)
    else:
        print_table(stats_list)


if __name__ == "__main__":
    main()
