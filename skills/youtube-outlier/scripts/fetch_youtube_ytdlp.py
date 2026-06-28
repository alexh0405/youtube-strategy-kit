#!/usr/bin/env python3
"""
Fetch YouTube videos via yt-dlp (no API key required).
Outputs the same JSON format as fetch_youtube.py for compatibility with analyze_outliers.py.
"""
import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timedelta


def get_cutoff_date(days):
    cutoff = datetime.now() - timedelta(days=days)
    return cutoff.strftime("%Y%m%d")


def format_duration(info):
    if info.get("duration_string"):
        return info["duration_string"]
    dur = info.get("duration")
    if dur is None:
        return ""
    dur = int(dur)
    hours, remainder = divmod(dur, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def parse_upload_date(raw):
    """Convert YYYYMMDD to ISO 8601 string."""
    if not raw or len(raw) != 8:
        return ""
    try:
        dt = datetime.strptime(raw, "%Y%m%d")
        return dt.strftime("%Y-%m-%dT00:00:00Z")
    except ValueError:
        return ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", required=True)
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--count", type=int, default=50)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    if not shutil.which("yt-dlp"):
        print("Error: yt-dlp not found. Install with: pip install yt-dlp", file=sys.stderr)
        sys.exit(1)

    # Fetch 2x the requested count to survive date filtering.
    # Standard ytsearch (relevance-sorted) — yt-dlp does not support date-sorted search.
    fetch_count = int(args.count * 2)
    search_query = f"ytsearch{fetch_count}:{args.query}"
    cmd = [
        "yt-dlp",
        search_query,
        "--dump-json",
        "--no-download",
        "--no-warnings",
        "--quiet",
    ]

    print(f"Suche via yt-dlp: '{args.query}' (letzte {args.days} Tage)", file=sys.stderr)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=args.timeout)
    except subprocess.TimeoutExpired:
        print(f"Error: yt-dlp timed out after {args.timeout} seconds.", file=sys.stderr)
        sys.exit(1)

    if result.returncode != 0 and not result.stdout.strip():
        print(f"Error: yt-dlp failed: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)

    videos = []
    for line in result.stdout.strip().splitlines():
        if not line.strip():
            continue
        try:
            videos.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    if not videos:
        print("Keine Videos gefunden.", file=sys.stderr)
        with open(args.output, "w") as f:
            json.dump([], f)
        sys.exit(0)

    # Date filter
    cutoff = get_cutoff_date(args.days)
    filtered = [v for v in videos if (v.get("upload_date") or "00000000") >= cutoff]
    skipped = len(videos) - len(filtered)
    if skipped > 0:
        print(f"  {skipped} Videos älter als {args.days} Tage gefiltert.", file=sys.stderr)
    videos = filtered[:args.count]

    print(f"  {len(videos)} Videos nach Filterung", file=sys.stderr)

    # Convert to the same format as fetch_youtube.py output
    enriched = []
    for info in videos:
        video_id = info.get("id", "")
        view_count = info.get("view_count") or 0
        enriched.append({
            "videoId": video_id,
            "title": info.get("title", ""),
            "channelTitle": info.get("channel") or info.get("uploader", ""),
            "publishedAt": parse_upload_date(info.get("upload_date", "")),
            "thumbnail": info.get("thumbnail", ""),
            "url": f"https://www.youtube.com/watch?v={video_id}" if video_id else "",
            "viewCount": view_count,
            "likeCount": info.get("like_count") or 0,
            "commentCount": info.get("comment_count") or 0,
            "engagementRate": "N/A",
            "duration": format_duration(info),
            "subscriberCount": info.get("channel_follower_count"),
        })

    print(f"Daten gesammelt: {len(enriched)} Videos.", file=sys.stderr)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(enriched, f, ensure_ascii=False, indent=2)

    print(f"Daten gespeichert: {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
