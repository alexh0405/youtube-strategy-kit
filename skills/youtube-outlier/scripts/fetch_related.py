#!/usr/bin/env python3
"""
Fetch related/similar videos for top outlier videos.

Since YouTube's relatedToVideoId API parameter was deprecated in 2023,
this script uses an alternative approach:
  1. Extract key phrases from outlier video titles
  2. Search YouTube for those phrases to find algorithmically similar videos
  3. Deduplicate against already-known videos
  4. Return enriched results with statistics, filtered for Shorts

This finds videos that YouTube's algorithm groups together topically,
which closely mirrors what appears in the sidebar/suggestions.

Usage:
  python3 fetch_related.py --input /tmp/outliers.json --api-key KEY --days 60 --output /tmp/related.json
"""
import argparse
import json
import os
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

MAX_RETRIES = 3
RETRY_BACKOFF = [2, 4, 8]


def _make_ssl_context():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def youtube_get(url, params):
    full_url = url + "?" + urllib.parse.urlencode(params)
    last_error = None

    for attempt in range(MAX_RETRIES):
        try:
            with urllib.request.urlopen(full_url, timeout=20, context=_make_ssl_context()) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            try:
                err = json.loads(body)
                msg = err.get("error", {}).get("message", body)
                code = err.get("error", {}).get("code", e.code)
            except Exception:
                msg = body
                code = e.code
            if 400 <= e.code < 500:
                print(f"  API Fehler {code}: {msg}", file=sys.stderr)
                return None
            last_error = f"API Fehler {code}: {msg}"
        except Exception as e:
            last_error = f"Netzwerkfehler: {e}"

        if attempt < MAX_RETRIES - 1:
            wait = RETRY_BACKOFF[attempt]
            time.sleep(wait)

    print(f"  Abbruch nach {MAX_RETRIES} Versuchen: {last_error}", file=sys.stderr)
    return None


def parse_duration_seconds(iso_duration: str) -> int:
    if not iso_duration:
        return 0
    match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', iso_duration)
    if not match:
        return 0
    h = int(match.group(1) or 0)
    m = int(match.group(2) or 0)
    s = int(match.group(3) or 0)
    return h * 3600 + m * 60 + s


def extract_search_queries(outlier_videos: list, max_queries: int = 5) -> list:
    """
    Extract search queries from outlier video titles.

    Strategy: Use the most distinctive 3-5 word phrases from each title.
    Remove common filler words and combine with channel name for specificity.
    """
    noise_words = {
        "the", "a", "an", "i", "my", "you", "your", "this", "that", "it",
        "is", "was", "are", "will", "do", "don't", "how", "to", "for",
        "in", "on", "at", "of", "and", "or", "but", "with", "from",
        "if", "not", "no", "so", "be", "can", "all", "just", "here",
        "get", "got", "has", "had", "have", "been", "would", "could",
        "should", "must", "need", "want", "like", "make", "made",
        "every", "ever", "never", "only", "even", "also", "very",
        "new", "best", "most", "real", "full", "step", "by",
    }

    queries = []
    for video in outlier_videos[:max_queries]:
        title = video.get("title", "")
        # Clean HTML entities
        title = title.replace("&#39;", "'").replace("&amp;", "&").replace("&quot;", '"')
        # Remove emojis and special chars
        title = re.sub(r'[^\w\s\'-]', ' ', title)
        # Split and filter
        words = [w for w in title.split() if w.lower() not in noise_words and len(w) > 1]

        if len(words) >= 3:
            # Take the core phrase (first 4-5 meaningful words)
            query = " ".join(words[:5])
        elif words:
            query = " ".join(words)
        else:
            continue

        queries.append(query)

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for q in queries:
        q_lower = q.lower()
        if q_lower not in seen:
            seen.add(q_lower)
            unique.append(q)

    return unique


def main():
    parser = argparse.ArgumentParser(description="Fetch related videos via title-based search")
    parser.add_argument("--input", required=True, help="JSON file with outlier videos")
    parser.add_argument("--top", type=int, default=5, help="Use top N outliers as seed (default: 5)")
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    with open(args.input) as f:
        data = json.load(f)

    if isinstance(data, dict) and "outliers" in data:
        outliers = data["outliers"]
    elif isinstance(data, list):
        outliers = data
    else:
        print("Unbekanntes JSON-Format", file=sys.stderr)
        sys.exit(1)

    seed_videos = outliers[:args.top]
    if not seed_videos:
        print("Keine Seed-Videos gefunden", file=sys.stderr)
        sys.exit(1)

    # Collect all known video IDs to exclude
    known_ids = set(v.get("videoId", "") for v in outliers)

    # Extract search queries from outlier titles
    queries = extract_search_queries(seed_videos, max_queries=args.top)
    print(f"Generated {len(queries)} search queries from top {len(seed_videos)} outliers:", file=sys.stderr)
    for q in queries:
        print(f"  → \"{q}\"", file=sys.stderr)

    published_after = (
        datetime.now(timezone.utc) - timedelta(days=args.days)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Search for each query
    all_found_ids = set()
    search_results = {}

    for i, query in enumerate(queries):
        params = {
            "part": "snippet",
            "q": query,
            "order": "relevance",
            "type": "video",
            "maxResults": 15,
            "publishedAfter": published_after,
            "key": args.api_key,
        }
        data = youtube_get("https://www.googleapis.com/youtube/v3/search", params)
        if data is None:
            print(f"  [{i+1}/{len(queries)}] \"{query}\" — Fehler", file=sys.stderr)
            continue

        found = 0
        for item in data.get("items", []):
            vid_id = item.get("id", {}).get("videoId")
            if vid_id and vid_id not in known_ids and vid_id not in all_found_ids:
                all_found_ids.add(vid_id)
                snippet = item.get("snippet", {})
                search_results[vid_id] = {
                    "title": snippet.get("title", ""),
                    "channelTitle": snippet.get("channelTitle", ""),
                    "channelId": snippet.get("channelId", ""),
                    "publishedAt": snippet.get("publishedAt", ""),
                }
                found += 1

        print(f"  [{i+1}/{len(queries)}] \"{query}\" — {found} neue Videos", file=sys.stderr)
        time.sleep(0.1)

    if not all_found_ids:
        print("Keine neuen related Videos gefunden", file=sys.stderr)
        with open(args.output, "w") as f:
            json.dump([], f)
        return

    print(f"\nGesamt neue Video-IDs: {len(all_found_ids)}", file=sys.stderr)

    # Fetch statistics + contentDetails in batches of 50
    all_ids = list(all_found_ids)
    enriched = []

    for batch_start in range(0, len(all_ids), 50):
        batch = all_ids[batch_start:batch_start + 50]
        params = {
            "part": "snippet,statistics,contentDetails",
            "id": ",".join(batch),
            "key": args.api_key,
        }
        data = youtube_get("https://www.googleapis.com/youtube/v3/videos", params)
        if data is None:
            continue

        for video in data.get("items", []):
            vid_id = video["id"]
            snippet = video.get("snippet", {})
            stats = video.get("statistics", {})
            content = video.get("contentDetails", {})

            # Shorts filter
            duration_str = content.get("duration", "")
            duration_secs = parse_duration_seconds(duration_str)
            if 0 < duration_secs < 90:
                continue
            title = snippet.get("title", "")
            if "#shorts" in title.lower() or "#short" in title.lower():
                continue

            views = int(stats.get("viewCount", 0))
            likes = int(stats.get("likeCount", 0))
            comments = int(stats.get("commentCount", 0))
            engagement = f"{(likes + comments) / views * 100:.2f}%" if views > 0 else "0%"

            enriched.append({
                "videoId": vid_id,
                "title": title,
                "channelTitle": snippet.get("channelTitle", ""),
                "channelId": snippet.get("channelId", ""),
                "publishedAt": snippet.get("publishedAt", ""),
                "thumbnail": (
                    snippet.get("thumbnails", {}).get("high", {}).get("url")
                    or snippet.get("thumbnails", {}).get("default", {}).get("url", "")
                ),
                "url": f"https://www.youtube.com/watch?v={vid_id}",
                "viewCount": views,
                "likeCount": likes,
                "commentCount": comments,
                "engagementRate": engagement,
                "duration": duration_str,
                "durationSeconds": duration_secs,
                "source": "related",
            })

        time.sleep(0.05)

    print(f"Related Videos nach Filter: {len(enriched)} (Shorts entfernt)", file=sys.stderr)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(enriched, f, ensure_ascii=False, indent=2)

    print(f"Gespeichert: {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
