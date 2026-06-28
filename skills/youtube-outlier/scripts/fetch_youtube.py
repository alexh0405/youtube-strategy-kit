#!/usr/bin/env python3
"""
Fetch YouTube videos for a keyword and collect their statistics.
Paginates up to 3 pages (50 results each) and fetches stats in batches of 50.
"""
import argparse
import json
import ssl
import sys
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta

MAX_RETRIES = 3
RETRY_BACKOFF = [2, 4, 8]  # seconds between retries


def _make_ssl_context():
    """Return an unverified SSL context (workaround for macOS missing certs)."""
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
            # 4xx errors are permanent — no retry
            if 400 <= e.code < 500:
                print(f"YouTube API Fehler {code}: {msg}", file=sys.stderr)
                sys.exit(1)
            last_error = f"YouTube API Fehler {code}: {msg}"
        except Exception as e:
            last_error = f"Netzwerkfehler: {e}"

        if attempt < MAX_RETRIES - 1:
            wait = RETRY_BACKOFF[attempt]
            print(f"  Retry {attempt+1}/{MAX_RETRIES-1} in {wait}s... ({last_error})", file=sys.stderr)
            time.sleep(wait)

    print(f"Abbruch nach {MAX_RETRIES} Versuchen: {last_error}", file=sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", required=True)
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--order",
        default="relevance",
        choices=["relevance", "viewCount", "date", "rating"],
        help="Search result ordering. 'relevance' (default) gives a representative sample "
             "for velocity-based outlier detection. 'viewCount' returns most-viewed first.",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=3,
        choices=[1, 2, 3],
        help="Number of search result pages to fetch (50 results each). "
             "Default 3 = 150 videos. Use 1 for quota-efficient benchmark runs (100 API units vs 300).",
    )
    args = parser.parse_args()

    published_after = (
        datetime.now(timezone.utc) - timedelta(days=args.days)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    all_search_results = []
    page_token = None

    print(f"Suche nach: '{args.query}' (letzte {args.days} Tage, {args.pages} Seite(n), order={args.order})", file=sys.stderr)

    for page in range(args.pages):
        params = {
            "part": "snippet",
            "q": args.query,
            "order": args.order,
            "type": "video",
            "maxResults": 50,
            "publishedAfter": published_after,
            "key": args.api_key,
        }
        if page_token:
            params["pageToken"] = page_token

        data = youtube_get("https://www.googleapis.com/youtube/v3/search", params)
        items = data.get("items", [])

        for item in items:
            video_id = item.get("id", {}).get("videoId")
            if not video_id:
                continue
            snippet = item.get("snippet", {})
            all_search_results.append({
                "videoId": video_id,
                "title": snippet.get("title", ""),
                "channelTitle": snippet.get("channelTitle", ""),
                "publishedAt": snippet.get("publishedAt", ""),
                "thumbnail": (
                    snippet.get("thumbnails", {}).get("high", {}).get("url")
                    or snippet.get("thumbnails", {}).get("default", {}).get("url", "")
                ),
            })

        print(f"  Seite {page+1}: {len(items)} Videos gefunden", file=sys.stderr)
        page_token = data.get("nextPageToken")
        if not page_token:
            break

    if not all_search_results:
        print("Keine Videos gefunden.", file=sys.stderr)
        with open(args.output, "w") as f:
            json.dump([], f)
        sys.exit(0)

    # Deduplicate by videoId
    seen = set()
    unique = []
    for r in all_search_results:
        if r["videoId"] not in seen:
            seen.add(r["videoId"])
            unique.append(r)
    all_search_results = unique

    print(f"Gesamt eindeutige Videos: {len(all_search_results)}", file=sys.stderr)

    # Fetch statistics in batches of 50
    search_by_id = {r["videoId"]: r for r in all_search_results}
    all_ids = list(search_by_id.keys())
    enriched = []

    for i in range(0, len(all_ids), 50):
        batch = all_ids[i:i+50]
        params = {
            "part": "statistics,snippet,contentDetails",
            "id": ",".join(batch),
            "key": args.api_key,
        }
        data = youtube_get("https://www.googleapis.com/youtube/v3/videos", params)
        for video in data.get("items", []):
            vid_id = video["id"]
            stats = video.get("statistics", {})
            views = int(stats.get("viewCount", 0))
            likes = int(stats.get("likeCount", 0))
            comments = int(stats.get("commentCount", 0))
            engagement = f"{(likes + comments) / views * 100:.2f}%" if views > 0 else "0%"
            search_data = search_by_id.get(vid_id, {})
            enriched.append({
                "videoId": vid_id,
                "title": search_data.get("title") or video.get("snippet", {}).get("title", ""),
                "channelTitle": search_data.get("channelTitle") or video.get("snippet", {}).get("channelTitle", ""),
                "publishedAt": search_data.get("publishedAt") or video.get("snippet", {}).get("publishedAt", ""),
                "thumbnail": search_data.get("thumbnail") or "",
                "url": f"https://www.youtube.com/watch?v={vid_id}",
                "viewCount": views,
                "likeCount": likes,
                "commentCount": comments,
                "engagementRate": engagement,
                "duration": video.get("contentDetails", {}).get("duration", ""),
            })

    print(f"Statistiken geladen fuer {len(enriched)} Videos.", file=sys.stderr)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(enriched, f, ensure_ascii=False, indent=2)

    print(f"Daten gespeichert: {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
