#!/usr/bin/env python3
"""
Search for top-performing videos across a list of reference channels for a given keyword.

Workflow:
  1. Load reference channels from a client config (channels.json)
  2. For each channel, search for videos matching the keyword
  3. Collect stats, filter Shorts, rank by views & velocity
  4. Output: JSON with top videos per channel + aggregated top list

Usage:
  python3 channel_search.py \
    --keyword "claude code" \
    --channels /path/to/channels.json \
    --api-key "$YOUTUBE_API_KEY" \
    --days 90 \
    --top-per-channel 5 \
    --output /tmp/channel_search.json
"""
import argparse
import json
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

MAX_RETRIES = 3
RETRY_BACKOFF = [2, 4, 8]


def _ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def yt_get(url, params):
    full_url = url + "?" + urllib.parse.urlencode(params)
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            with urllib.request.urlopen(full_url, timeout=20, context=_ssl_ctx()) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            if 400 <= e.code < 500:
                print(f"  API Fehler {e.code}: {body[:200]}", file=sys.stderr)
                return None
            last_error = f"HTTP {e.code}"
        except Exception as e:
            last_error = str(e)
        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_BACKOFF[attempt])
    print(f"  Abbruch nach {MAX_RETRIES} Versuchen: {last_error}", file=sys.stderr)
    return None


def parse_duration_seconds(iso_duration):
    if not iso_duration:
        return 0
    match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', iso_duration)
    if not match:
        return 0
    h = int(match.group(1) or 0)
    m = int(match.group(2) or 0)
    s = int(match.group(3) or 0)
    return h * 3600 + m * 60 + s


def is_short(title, duration_str):
    if "#shorts" in title.lower() or "#short" in title.lower():
        return True
    secs = parse_duration_seconds(duration_str)
    if 0 < secs < 90:
        return True
    return False


def compute_days_since(published_at):
    if not published_at:
        return None
    try:
        dt_str = published_at.replace("Z", "+00:00")
        pub = datetime.fromisoformat(dt_str)
        delta = (datetime.now(timezone.utc) - pub).total_seconds() / 86400.0
        return max(delta, 0.1)
    except Exception:
        return None


def search_channel_videos(channel_id, keyword, api_key, published_after):
    """Search a single channel for videos matching the keyword."""
    params = {
        "part": "snippet",
        "channelId": channel_id,
        "q": keyword,
        "order": "relevance",
        "type": "video",
        "maxResults": 20,
        "publishedAfter": published_after,
        "key": api_key,
    }
    data = yt_get("https://www.googleapis.com/youtube/v3/search", params)
    if not data:
        return []

    video_ids = []
    snippets = {}
    for item in data.get("items", []):
        vid_id = item.get("id", {}).get("videoId")
        if vid_id:
            video_ids.append(vid_id)
            s = item.get("snippet", {})
            snippets[vid_id] = {
                "title": s.get("title", ""),
                "channelTitle": s.get("channelTitle", ""),
                "channelId": s.get("channelId", ""),
                "publishedAt": s.get("publishedAt", ""),
            }

    if not video_ids:
        return []

    # Fetch stats
    params = {
        "part": "statistics,contentDetails",
        "id": ",".join(video_ids),
        "key": api_key,
    }
    stats_data = yt_get("https://www.googleapis.com/youtube/v3/videos", params)
    if not stats_data:
        return []

    results = []
    for v in stats_data.get("items", []):
        vid_id = v["id"]
        snip = snippets.get(vid_id, {})
        title = snip.get("title", "")
        duration = v.get("contentDetails", {}).get("duration", "")

        if is_short(title, duration):
            continue

        st = v.get("statistics", {})
        views = int(st.get("viewCount", 0))
        likes = int(st.get("likeCount", 0))
        comments = int(st.get("commentCount", 0))
        engagement = f"{(likes + comments) / views * 100:.2f}%" if views > 0 else "0%"
        days = compute_days_since(snip.get("publishedAt", ""))
        vpd = round(views / days, 1) if days else None

        results.append({
            "videoId": vid_id,
            "title": title,
            "channelTitle": snip.get("channelTitle", ""),
            "channelId": snip.get("channelId", ""),
            "publishedAt": snip.get("publishedAt", ""),
            "url": f"https://www.youtube.com/watch?v={vid_id}",
            "viewCount": views,
            "likeCount": likes,
            "commentCount": comments,
            "engagementRate": engagement,
            "duration": duration,
            "durationSeconds": parse_duration_seconds(duration),
            "daysSincePublish": round(days, 1) if days else None,
            "viewsPerDay": vpd,
        })

    return results


def extract_keywords_from_videos(videos, max_keywords=15):
    """Extract recurring keyword phrases from top video titles."""
    noise = {
        "the", "a", "an", "i", "my", "you", "your", "this", "that", "it",
        "is", "was", "are", "will", "do", "don't", "how", "to", "for",
        "in", "on", "at", "of", "and", "or", "but", "with", "from",
        "if", "not", "no", "so", "be", "can", "all", "just", "here",
        "get", "got", "has", "had", "have", "been", "would", "could",
        "should", "must", "need", "want", "like", "make", "made",
        "every", "ever", "never", "only", "even", "also", "very",
        "new", "best", "most", "real", "full", "step", "by", "use",
        "using", "why", "what", "when", "where", "who", "which",
        "ich", "du", "wir", "er", "sie", "es", "und", "oder", "aber",
        "mit", "fuer", "von", "den", "das", "die", "der", "ein", "eine",
        "ist", "sind", "hat", "haben", "wird", "werden", "kann", "muss",
        "jetzt", "noch", "schon", "nur", "auch", "hier", "da", "so",
        "mehr", "alle", "gerade", "einfach", "wirklich", "video",
    }

    from collections import Counter
    bigrams = Counter()
    trigrams = Counter()

    for v in videos:
        title = v.get("title", "")
        title = title.replace("&#39;", "'").replace("&amp;", "&").replace("&quot;", '"')
        title = re.sub(r'[^\w\s\'-]', ' ', title)
        words = [w for w in title.lower().split() if w not in noise and len(w) > 1]

        for i in range(len(words) - 1):
            bigrams[f"{words[i]} {words[i+1]}"] += 1
        for i in range(len(words) - 2):
            trigrams[f"{words[i]} {words[i+1]} {words[i+2]}"] += 1

    keywords = []
    for phrase, count in trigrams.most_common(10):
        if count >= 2:
            keywords.append({"phrase": phrase, "count": count, "type": "trigram"})
    for phrase, count in bigrams.most_common(20):
        if count >= 2 and not any(phrase in k["phrase"] for k in keywords):
            keywords.append({"phrase": phrase, "count": count, "type": "bigram"})

    return keywords[:max_keywords]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--keyword", required=True, help="Search keyword/topic")
    parser.add_argument("--channels", required=True, help="Path to channels.json")
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--top-per-channel", type=int, default=5)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    with open(args.channels) as f:
        data = json.load(f)

    channels = data.get("channels", data) if isinstance(data, dict) else data

    published_after = (
        datetime.now(timezone.utc) - timedelta(days=args.days)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    print(f"Suche '{args.keyword}' in {len(channels)} Referenzkanaelen (letzte {args.days} Tage)", file=sys.stderr)

    all_videos = []
    channel_results = []

    for i, ch in enumerate(channels):
        ch_id = ch.get("channelId", "")
        ch_name = ch.get("name", ch.get("handle", "?"))
        print(f"  [{i+1}/{len(channels)}] {ch_name}...", file=sys.stderr, end=" ")

        videos = search_channel_videos(ch_id, args.keyword, args.api_key, published_after)
        videos.sort(key=lambda v: v["viewCount"], reverse=True)
        top = videos[:args.top_per_channel]

        if top:
            print(f"{len(videos)} Videos, Top: {top[0]['viewCount']:,} views", file=sys.stderr)
        else:
            print("keine Treffer", file=sys.stderr)

        channel_results.append({
            "channelId": ch_id,
            "channelName": ch_name,
            "handle": ch.get("handle", ""),
            "subscribers": ch.get("subscribers", 0),
            "videosFound": len(videos),
            "topVideos": top,
        })

        all_videos.extend(top)
        time.sleep(0.1)

    # Deduplicate
    seen = set()
    unique = []
    for v in all_videos:
        if v["videoId"] not in seen:
            seen.add(v["videoId"])
            unique.append(v)

    # Global ranking by combined views + velocity
    for v in unique:
        v["_sort"] = v["viewCount"] + (v["viewsPerDay"] or 0) * 10

    unique.sort(key=lambda v: v["_sort"], reverse=True)
    for v in unique:
        del v["_sort"]

    # Extract keywords from top videos
    extracted_keywords = extract_keywords_from_videos(unique[:30])

    result = {
        "keyword": args.keyword,
        "searchedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "days": args.days,
        "channelsSearched": len(channels),
        "totalVideosFound": len(unique),
        "topVideos": unique[:30],
        "extractedKeywords": extracted_keywords,
        "channelBreakdown": channel_results,
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\nGesamt: {len(unique)} unique Videos aus {len(channels)} Kanaelen", file=sys.stderr)
    print(f"Top-Video: {unique[0]['title'][:60]} ({unique[0]['viewCount']:,} views)" if unique else "Keine Videos gefunden", file=sys.stderr)
    print(f"Keywords extrahiert: {len(extracted_keywords)}", file=sys.stderr)
    print(f"Gespeichert: {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
