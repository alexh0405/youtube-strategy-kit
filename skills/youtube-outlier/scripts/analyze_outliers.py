#!/usr/bin/env python3
"""
Analyze YouTube video data to find outliers.

Supports three metrics:
  views    - outliers by total view count (original behavior)
  velocity - outliers by views-per-day since publish (normalizes for video age)
  combined - average rank from both metrics (default, best for broad keywords)

Views-per-day (velocity) is the key improvement for broad keywords:
a 1-week-old video with 500k views outranks a 5-year-old video with 2M views,
because it's clearly blowing up *right now*.
"""
import argparse
import json
import re
import sys
from datetime import datetime, timezone


def format_number(n):
    return f"{n:,}"


def compute_days_since(published_at: str) -> float:
    """Return days elapsed since publishedAt (ISO 8601). Falls back to None."""
    if not published_at:
        return None
    try:
        # Handle both 'Z' and '+00:00' suffixes
        dt_str = published_at.replace("Z", "+00:00")
        pub = datetime.fromisoformat(dt_str)
        now = datetime.now(timezone.utc)
        delta = (now - pub).total_seconds() / 86400.0
        return max(delta, 0.1)  # avoid div-by-zero for very new videos
    except Exception:
        return None


def parse_duration_seconds(iso_duration: str) -> int:
    """Parse ISO 8601 duration (PT1H2M3S) to seconds."""
    if not iso_duration:
        return 0
    match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', iso_duration)
    if not match:
        return 0
    h = int(match.group(1) or 0)
    m = int(match.group(2) or 0)
    s = int(match.group(3) or 0)
    return h * 3600 + m * 60 + s


def is_short(video: dict) -> bool:
    """Return True if video is a YouTube Short (< 90s or #shorts in title)."""
    title = video.get("title", "").lower()
    if "#shorts" in title or "#short" in title:
        return True
    duration = video.get("duration", "")
    if duration:
        secs = parse_duration_seconds(duration)
        if 0 < secs < 90:
            return True
    duration_secs = video.get("durationSeconds", 0)
    if duration_secs and 0 < duration_secs < 90:
        return True
    return False


def compute_median(values: list):
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2 == 1:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2.0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--multiplier", type=float, default=1.5)
    parser.add_argument("--top", type=int, default=30)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--metric",
        default="combined",
        choices=["views", "velocity", "combined"],
        help=(
            "Outlier detection metric. "
            "'views': total view count (legacy). "
            "'velocity': views/day since publish — best for finding what's blowing up now. "
            "'combined': ranks by both and averages (default)."
        ),
    )
    args = parser.parse_args()

    with open(args.input, encoding="utf-8") as f:
        videos = json.load(f)

    # Filter out Shorts (< 90s or #shorts in title)
    shorts_count = sum(1 for v in videos if is_short(v))
    videos = [v for v in videos if not is_short(v)]
    if shorts_count > 0:
        print(f"Shorts gefiltert: {shorts_count} entfernt, {len(videos)} verbleibend", file=sys.stderr)

    if not videos:
        result = {
            "outliers": [],
            "stats": {
                "totalVideosAnalyzed": 0,
                "median": 0,
                "average": 0,
                "outlierThreshold": 0,
                "multiplier": args.multiplier,
                "outlierCount": 0,
                "noOutliersFound": True,
                "metric": args.metric,
            }
        }
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2)
        print("Keine Videos zum Analysieren.", file=sys.stderr)
        return

    # Enrich each video with velocity
    for v in videos:
        days = compute_days_since(v.get("publishedAt", ""))
        v["daysSincePublish"] = round(days, 1) if days is not None else None
        if days is not None and v.get("viewCount", 0) > 0:
            v["viewsPerDay"] = round(v["viewCount"] / days, 1)
        else:
            v["viewsPerDay"] = None

    # --- Metric: views ---
    view_counts = [v["viewCount"] for v in videos]
    median_views = compute_median(view_counts)
    avg_views = sum(view_counts) // len(view_counts)
    threshold_views = median_views * args.multiplier
    outliers_views = {v["videoId"] for v in videos if v["viewCount"] >= threshold_views}

    # --- Metric: velocity ---
    videos_with_velocity = [v for v in videos if v["viewsPerDay"] is not None]
    if videos_with_velocity:
        velocities = [v["viewsPerDay"] for v in videos_with_velocity]
        median_velocity = compute_median(velocities)
        threshold_velocity = median_velocity * args.multiplier
        outliers_velocity = {v["videoId"] for v in videos_with_velocity if v["viewsPerDay"] >= threshold_velocity}
    else:
        median_velocity = 0
        threshold_velocity = 0
        outliers_velocity = set()

    # --- Select outlier set based on metric ---
    if args.metric == "views":
        outlier_ids = outliers_views
        sort_key = lambda v: v["viewCount"]
        primary_median = int(median_views)
        primary_threshold = int(threshold_views)
    elif args.metric == "velocity":
        outlier_ids = outliers_velocity
        sort_key = lambda v: (v["viewsPerDay"] or 0)
        primary_median = int(median_velocity)
        primary_threshold = int(threshold_velocity)
    else:  # combined
        # Union: outlier in either metric gets included
        outlier_ids = outliers_views | outliers_velocity
        # Sort by combined rank: average of views-rank and velocity-rank
        sorted_by_views = sorted(videos, key=lambda v: v["viewCount"], reverse=True)
        rank_views = {v["videoId"]: i for i, v in enumerate(sorted_by_views)}
        sorted_by_vel = sorted(videos, key=lambda v: (v["viewsPerDay"] or 0), reverse=True)
        rank_vel = {v["videoId"]: i for i, v in enumerate(sorted_by_vel)}
        sort_key = lambda v: (rank_views.get(v["videoId"], 999) + rank_vel.get(v["videoId"], 999)) / 2.0
        primary_median = int(median_views)
        primary_threshold = int(threshold_views)

    # Filter and sort
    outlier_videos = [v for v in videos if v["videoId"] in outlier_ids]
    no_outliers_found = len(outlier_videos) == 0

    if no_outliers_found:
        # Fallback: top 10 by view count
        display_videos = sorted(videos, key=lambda v: v["viewCount"], reverse=True)[:10]
    else:
        if args.metric == "combined":
            display_videos = sorted(outlier_videos, key=sort_key)[:args.top]
        else:
            display_videos = sorted(outlier_videos, key=sort_key, reverse=True)[:args.top]

    enriched = []
    for i, v in enumerate(display_videos):
        view_multiple = f"{v['viewCount'] / median_views:.1f}x" if median_views > 0 else "N/A"
        if v["viewsPerDay"] is not None and median_velocity > 0:
            vel_multiple = f"{v['viewsPerDay'] / median_velocity:.1f}x"
        else:
            vel_multiple = "N/A"
        enriched.append({
            **v,
            "rank": i + 1,
            "outlierMultiple": view_multiple,
            "velocityMultiple": vel_multiple,
            "viewsPerDayFormatted": format_number(int(v["viewsPerDay"])) if v["viewsPerDay"] is not None else "N/A",
        })

    result = {
        "outliers": enriched,
        "stats": {
            "totalVideosAnalyzed": len(videos),
            "median": int(median_views),
            "medianFormatted": format_number(int(median_views)),
            "medianVelocity": int(median_velocity),
            "medianVelocityFormatted": format_number(int(median_velocity)),
            "average": avg_views,
            "averageFormatted": format_number(avg_views),
            "outlierThreshold": int(threshold_views),
            "outlierThresholdFormatted": format_number(int(threshold_views)),
            "velocityThreshold": int(threshold_velocity),
            "velocityThresholdFormatted": format_number(int(threshold_velocity)),
            "multiplier": args.multiplier,
            "metric": args.metric,
            "outlierCount": len(outlier_videos),
            "noOutliersFound": no_outliers_found,
        }
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"Metric: {args.metric}", file=sys.stderr)
    print(f"Median Views: {format_number(int(median_views))} | Median Velocity: {format_number(int(median_velocity))} Views/Tag", file=sys.stderr)
    print(f"Outlier gefunden: {len(outlier_videos)} (Schwelle: {args.multiplier}x)", file=sys.stderr)


if __name__ == "__main__":
    main()
