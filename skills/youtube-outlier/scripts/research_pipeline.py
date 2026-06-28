#!/usr/bin/env python3
"""
Full research pipeline for client-based YouTube outlier research.

Steps:
  1. Channel Search: Find top videos for keyword across reference channels
  2. Keyword Extraction: Pull recurring phrases from those top videos
  3. Related Videos: For each top video, find what YouTube suggests alongside it
  4. Outlier Analysis: Run outlier detection on the combined dataset
  5. Output: Unified report saved to client's reports/ folder

Usage:
  python3 research_pipeline.py \
    --keyword "ai agents" \
    --client-dir clients/mein-kanal \
    --api-key "$YOUTUBE_API_KEY" \
    --days 90 \
    --output-dir clients/mein-kanal/reports
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
from collections import Counter
from datetime import datetime, timezone, timedelta

MAX_RETRIES = 3
RETRY_BACKOFF = [2, 4, 8]


def _ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


class QuotaExhausted(Exception):
    """Raised when YouTube API returns 403 quota exceeded."""
    pass


def yt_get(url, params):
    full_url = url + "?" + urllib.parse.urlencode(params)
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            with urllib.request.urlopen(full_url, timeout=20, context=_ssl_ctx()) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            if e.code == 403 and "quota" in body.lower():
                raise QuotaExhausted("API-Quota erschoepft")
            if 400 <= e.code < 500:
                print(f"    API Fehler {e.code}: {body[:150]}", file=sys.stderr)
                return None
            last_error = f"HTTP {e.code}"
        except QuotaExhausted:
            raise
        except Exception as e:
            last_error = str(e)
        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_BACKOFF[attempt])
    print(f"    Abbruch: {last_error}", file=sys.stderr)
    return None


def parse_duration_seconds(iso_duration):
    if not iso_duration:
        return 0
    match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', iso_duration)
    if not match:
        return 0
    return int(match.group(1) or 0) * 3600 + int(match.group(2) or 0) * 60 + int(match.group(3) or 0)


def is_short(title, duration_str="", duration_secs=0):
    if "#shorts" in title.lower() or "#short" in title.lower():
        return True
    secs = duration_secs or parse_duration_seconds(duration_str)
    return 0 < secs < 90


def days_since(published_at):
    if not published_at:
        return None
    try:
        pub = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        return max((datetime.now(timezone.utc) - pub).total_seconds() / 86400.0, 0.1)
    except Exception:
        return None


def enrich_video(vid_id, snippet, stats, content_details):
    """Build a standardized video dict from API data."""
    title = snippet.get("title", "")
    duration = content_details.get("duration", "")
    dur_secs = parse_duration_seconds(duration)

    if is_short(title, duration, dur_secs):
        return None

    views = int(stats.get("viewCount", 0))
    likes = int(stats.get("likeCount", 0))
    comments = int(stats.get("commentCount", 0))
    engagement = f"{(likes + comments) / views * 100:.2f}%" if views > 0 else "0%"
    d = days_since(snippet.get("publishedAt", ""))
    vpd = round(views / d, 1) if d else None

    return {
        "videoId": vid_id,
        "title": title,
        "channelTitle": snippet.get("channelTitle", ""),
        "channelId": snippet.get("channelId", ""),
        "publishedAt": snippet.get("publishedAt", ""),
        "url": f"https://www.youtube.com/watch?v={vid_id}",
        "viewCount": views,
        "likeCount": likes,
        "commentCount": comments,
        "engagementRate": engagement,
        "duration": duration,
        "durationSeconds": dur_secs,
        "daysSincePublish": round(d, 1) if d else None,
        "viewsPerDay": vpd,
    }


def fetch_video_stats(video_ids, api_key):
    """Fetch statistics + contentDetails for a batch of video IDs. Raises QuotaExhausted."""
    results = []
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        data = yt_get("https://www.googleapis.com/youtube/v3/videos", {
            "part": "snippet,statistics,contentDetails",
            "id": ",".join(batch),
            "key": api_key,
        })
        if data:
            for v in data.get("items", []):
                enriched = enrich_video(
                    v["id"],
                    v.get("snippet", {}),
                    v.get("statistics", {}),
                    v.get("contentDetails", {}),
                )
                if enriched:
                    results.append(enriched)
        time.sleep(0.05)
    return results


# ── Step 1: Channel Search ──────────────────────────────────────────────────

def prioritize_channels(channels, max_channels):
    """Sort channels by priority score (explicit priority > subscribers) and return top N."""
    for ch in channels:
        # priority field in channels.json overrides; fallback to subscriber-based score
        ch["_score"] = ch.get("priority", 0) * 1_000_000 + ch.get("subscribers", 0)
    ranked = sorted(channels, key=lambda c: c["_score"], reverse=True)
    selected = ranked[:max_channels]
    skipped = ranked[max_channels:]
    # Clean up temp field
    for ch in channels:
        del ch["_score"]
    return selected, skipped


def channel_to_uploads_playlist(channel_id):
    """Convert channel ID (UC...) to uploads playlist ID (UU...)."""
    if channel_id.startswith("UC"):
        return "UU" + channel_id[2:]
    return channel_id


def keyword_matches_title(keyword, title):
    """Check if keyword (or its parts) appear in the video title."""
    kw_lower = keyword.lower()
    title_lower = title.lower()
    # Full keyword match
    if kw_lower in title_lower:
        return True
    # All individual words of keyword appear in title
    kw_words = kw_lower.split()
    if len(kw_words) > 1 and all(w in title_lower for w in kw_words):
        return True
    # At least 2/3 of keyword words match (fuzzy for 3+ word keywords)
    if len(kw_words) >= 3:
        matches = sum(1 for w in kw_words if w in title_lower)
        if matches >= len(kw_words) * 2 / 3:
            return True
    return False


def step_channel_search(keyword, channels, api_key, published_after, top_per_channel=3):
    """
    Fetch recent uploads from each channel via playlistItems.list (1 Unit)
    instead of search.list (100 Units). Filter by keyword match in title.
    """
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"STEP 1: Channel Uploads — '{keyword}' in {len(channels)} Kanaelen", file=sys.stderr)
    print(f"  (via playlistItems.list — 1 Unit/Kanal statt 100)", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)

    all_video_ids = []
    channel_map = {}  # vid_id -> channel name
    quota_hit = False

    for i, ch in enumerate(channels):
        ch_id = ch.get("channelId", "")
        ch_name = ch.get("name", ch.get("handle", "?"))
        playlist_id = channel_to_uploads_playlist(ch_id)
        print(f"  [{i+1}/{len(channels)}] {ch_name}...", file=sys.stderr, end=" ")

        try:
            data = yt_get("https://www.googleapis.com/youtube/v3/playlistItems", {
                "part": "snippet",
                "playlistId": playlist_id,
                "maxResults": 50,
                "key": api_key,
            })
        except QuotaExhausted:
            print("QUOTA ERSCHOEPFT", file=sys.stderr)
            quota_hit = True
            break

        if not data:
            print("Fehler", file=sys.stderr)
            continue

        # Filter: only videos published after cutoff AND matching keyword
        matched_ids = []
        for item in data.get("items", []):
            snip = item.get("snippet", {})
            vid_id = snip.get("resourceId", {}).get("videoId")
            title = snip.get("title", "")
            pub = snip.get("publishedAt", "")

            if not vid_id or pub < published_after:
                continue
            if keyword_matches_title(keyword, title):
                matched_ids.append(vid_id)
                channel_map[vid_id] = ch_name

        if matched_ids:
            print(f"{len(matched_ids)} Treffer", file=sys.stderr)
            all_video_ids.extend(matched_ids)
        else:
            print("keine Treffer", file=sys.stderr)

    # Fetch stats for ALL matched videos in one batch (1 Unit per 50 videos)
    if all_video_ids:
        try:
            all_videos = fetch_video_stats(all_video_ids, api_key)
        except QuotaExhausted:
            print("  QUOTA bei Stats-Abruf erschoepft", file=sys.stderr)
            quota_hit = True
            all_videos = []
    else:
        all_videos = []

    # Tag source + channel, sort, pick top per channel
    for v in all_videos:
        v["source"] = "channel_search"
        v["sourceChannel"] = channel_map.get(v["videoId"], "?")

    # Pick top N per channel to keep diversity
    from collections import defaultdict
    by_channel = defaultdict(list)
    for v in all_videos:
        by_channel[v["sourceChannel"]].append(v)

    unique = []
    for ch_name, vids in by_channel.items():
        vids.sort(key=lambda v: v["viewCount"], reverse=True)
        unique.extend(vids[:top_per_channel])

    unique.sort(key=lambda v: v["viewCount"], reverse=True)

    searched = len(channels) if not quota_hit else i
    print(f"  → {len(unique)} Videos aus {searched} Kanaelen (Top {top_per_channel}/Kanal)", file=sys.stderr)
    if quota_hit:
        print(f"  ⚠ Quota nach {searched}/{len(channels)} Kanaelen erschoepft", file=sys.stderr)
    return unique, quota_hit


# ── Step 2: Keyword Extraction ──────────────────────────────────────────────

def step_extract_keywords(videos, max_keywords=10):
    """Extract recurring keyword phrases from top video titles."""
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"STEP 2: Keyword Extraction aus {len(videos)} Top-Videos", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)

    noise = {
        "the", "a", "an", "i", "my", "you", "your", "this", "that", "it",
        "is", "was", "are", "will", "do", "don't", "how", "to", "for",
        "in", "on", "at", "of", "and", "or", "but", "with", "from",
        "if", "not", "no", "so", "be", "can", "all", "just", "here",
        "get", "got", "has", "had", "have", "been", "would", "could",
        "use", "using", "why", "what", "when", "where", "who", "which",
        "ich", "du", "wir", "er", "sie", "es", "und", "oder", "aber",
        "mit", "von", "den", "das", "die", "der", "ein", "eine",
        "ist", "sind", "hat", "wird", "kann", "jetzt", "noch", "nur",
        "auch", "hier", "so", "mehr", "alle", "gerade", "einfach", "video",
    }

    bigrams = Counter()
    trigrams = Counter()

    for v in videos:
        title = v.get("title", "")
        title = title.replace("&#39;", "'").replace("&amp;", "&").replace("&quot;", '"')
        title = re.sub(r'[^\w\s\'-]', ' ', title)
        words = [w for w in title.lower().split() if w not in noise and len(w) > 1]

        for j in range(len(words) - 1):
            bigrams[f"{words[j]} {words[j+1]}"] += 1
        for j in range(len(words) - 2):
            trigrams[f"{words[j]} {words[j+1]} {words[j+2]}"] += 1

    keywords = []
    for phrase, count in trigrams.most_common(10):
        if count >= 2:
            keywords.append({"phrase": phrase, "count": count, "type": "trigram"})
    for phrase, count in bigrams.most_common(20):
        if count >= 2 and not any(phrase in k["phrase"] for k in keywords):
            keywords.append({"phrase": phrase, "count": count, "type": "bigram"})

    keywords = keywords[:max_keywords]
    for kw in keywords:
        print(f"  → \"{kw['phrase']}\" (x{kw['count']})", file=sys.stderr)

    if not keywords:
        print("  → Keine wiederkehrenden Phrasen gefunden", file=sys.stderr)

    return keywords


# ── Step 3: Related Videos ──────────────────────────────────────────────────

def step_related_videos(seed_videos, api_key, published_after, known_ids, max_seeds=3):
    """Find related videos by searching for title-derived queries of top videos."""
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"STEP 3: Related Videos fuer Top {min(max_seeds, len(seed_videos))} Seed-Videos", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)

    noise = {
        "the", "a", "an", "i", "my", "you", "your", "this", "that", "it",
        "is", "was", "are", "will", "do", "how", "to", "for", "in", "on",
        "at", "of", "and", "or", "but", "with", "from", "just", "here",
        "get", "got", "use", "using", "why", "what", "when", "where",
    }

    queries = []
    for v in seed_videos[:max_seeds]:
        title = v.get("title", "")
        title = title.replace("&#39;", "'").replace("&amp;", "&").replace("&quot;", '"')
        title = re.sub(r'[^\w\s\'-]', ' ', title)
        words = [w for w in title.split() if w.lower() not in noise and len(w) > 1]
        if len(words) >= 3:
            queries.append(" ".join(words[:5]))
        elif words:
            queries.append(" ".join(words))

    # Deduplicate queries
    seen_q = set()
    unique_queries = []
    for q in queries:
        ql = q.lower()
        if ql not in seen_q:
            seen_q.add(ql)
            unique_queries.append(q)

    all_new_ids = set()

    for i, query in enumerate(unique_queries):
        print(f"  [{i+1}/{len(unique_queries)}] \"{query[:50]}\"...", file=sys.stderr, end=" ")
        try:
            data = yt_get("https://www.googleapis.com/youtube/v3/search", {
                "part": "snippet",
                "q": query,
                "order": "relevance",
                "type": "video",
                "maxResults": 15,
                "publishedAfter": published_after,
                "key": api_key,
            })
        except QuotaExhausted:
            print("QUOTA ERSCHOEPFT — stoppe Related Search", file=sys.stderr)
            break

        if not data:
            print("Fehler", file=sys.stderr)
            continue

        found = 0
        for item in data.get("items", []):
            vid_id = item.get("id", {}).get("videoId")
            if vid_id and vid_id not in known_ids and vid_id not in all_new_ids:
                all_new_ids.add(vid_id)
                found += 1
        print(f"{found} neue", file=sys.stderr)
        time.sleep(0.1)

    if not all_new_ids:
        print("  → Keine neuen Related Videos", file=sys.stderr)
        return []

    # Fetch stats for new videos
    try:
        videos = fetch_video_stats(list(all_new_ids), api_key)
    except QuotaExhausted:
        print("  ⚠ Quota bei Stats-Abruf erschoepft — nutze gefundene IDs ohne Stats", file=sys.stderr)
        return []

    for v in videos:
        v["source"] = "related"

    videos.sort(key=lambda v: v["viewCount"], reverse=True)
    print(f"  → {len(videos)} Related Videos nach Filter", file=sys.stderr)
    return videos


# ── Step 4: Outlier Analysis ────────────────────────────────────────────────

def step_outlier_analysis(all_videos, multiplier=1.5):
    """Compute outliers from the combined video pool."""
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"STEP 4: Outlier-Analyse ueber {len(all_videos)} Videos (Schwelle: {multiplier}x)", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)

    if not all_videos:
        return {"outliers": [], "stats": {}}

    views = [v["viewCount"] for v in all_videos]
    views_sorted = sorted(views)
    n = len(views_sorted)
    median = views_sorted[n // 2] if n % 2 else (views_sorted[n // 2 - 1] + views_sorted[n // 2]) / 2
    avg = sum(views) // n
    threshold = median * multiplier

    velocities = [v["viewsPerDay"] for v in all_videos if v.get("viewsPerDay")]
    if velocities:
        vel_sorted = sorted(velocities)
        vn = len(vel_sorted)
        median_vel = vel_sorted[vn // 2] if vn % 2 else (vel_sorted[vn // 2 - 1] + vel_sorted[vn // 2]) / 2
        threshold_vel = median_vel * multiplier
    else:
        median_vel = 0
        threshold_vel = 0

    # Combined: outlier in views OR velocity
    outlier_ids = set()
    for v in all_videos:
        if v["viewCount"] >= threshold:
            outlier_ids.add(v["videoId"])
        if v.get("viewsPerDay") and v["viewsPerDay"] >= threshold_vel:
            outlier_ids.add(v["videoId"])

    outliers = [v for v in all_videos if v["videoId"] in outlier_ids]

    # Rank by combined: avg of views-rank + velocity-rank
    by_views = sorted(all_videos, key=lambda v: v["viewCount"], reverse=True)
    rank_v = {v["videoId"]: i for i, v in enumerate(by_views)}
    by_vel = sorted(all_videos, key=lambda v: (v.get("viewsPerDay") or 0), reverse=True)
    rank_vel = {v["videoId"]: i for i, v in enumerate(by_vel)}

    outliers.sort(key=lambda v: (rank_v.get(v["videoId"], 999) + rank_vel.get(v["videoId"], 999)) / 2)

    for v in outliers:
        v["outlierMultiple"] = f"{v['viewCount'] / median:.1f}x" if median > 0 else "N/A"
        if v.get("viewsPerDay") and median_vel > 0:
            v["velocityMultiple"] = f"{v['viewsPerDay'] / median_vel:.1f}x"
        else:
            v["velocityMultiple"] = "N/A"

    stats = {
        "totalVideosAnalyzed": n,
        "median": int(median),
        "medianFormatted": f"{int(median):,}",
        "average": avg,
        "averageFormatted": f"{avg:,}",
        "medianVelocity": int(median_vel),
        "outlierThreshold": int(threshold),
        "velocityThreshold": int(threshold_vel),
        "multiplier": multiplier,
        "outlierCount": len(outliers),
    }

    print(f"  Median Views: {int(median):,} | Median Velocity: {int(median_vel):,}/Tag", file=sys.stderr)
    print(f"  Outlier gefunden: {len(outliers)}", file=sys.stderr)

    return {"outliers": outliers, "stats": stats}


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Full YouTube research pipeline for a client")
    parser.add_argument("--keyword", required=True)
    parser.add_argument("--client-dir", required=True, help="Path to client folder (e.g. clients/mein-kanal)")
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--multiplier", type=float, default=1.5)
    parser.add_argument("--top-per-channel", type=int, default=3)
    parser.add_argument("--max-channels", type=int, default=10, help="Only search top N channels by priority/subscribers (default: 10)")
    parser.add_argument("--max-seeds", type=int, default=3, help="How many top videos to use as seed for related search (each = 100 quota units)")
    parser.add_argument("--output-dir", help="Override output directory (default: client-dir/reports)")
    args = parser.parse_args()

    # Load channels
    channels_file = os.path.join(args.client_dir, "reference-channels", "channels.json")
    if not os.path.exists(channels_file):
        print(f"Fehler: {channels_file} nicht gefunden", file=sys.stderr)
        sys.exit(1)

    with open(channels_file) as f:
        ch_data = json.load(f)
    all_channels = ch_data.get("channels", ch_data) if isinstance(ch_data, dict) else ch_data

    # Prioritize: only search top N channels
    selected, skipped = prioritize_channels(all_channels, args.max_channels)

    output_dir = args.output_dir or os.path.join(args.client_dir, "reports")
    os.makedirs(output_dir, exist_ok=True)

    published_after = (
        datetime.now(timezone.utc) - timedelta(days=args.days)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    today = datetime.now().strftime("%Y-%m-%d")
    slug = re.sub(r'[^a-z0-9]+', '-', args.keyword.lower()).strip('-')

    print(f"\n{'#'*60}", file=sys.stderr)
    print(f"  RESEARCH PIPELINE: '{args.keyword}'", file=sys.stderr)
    print(f"  Client: {os.path.basename(args.client_dir)}", file=sys.stderr)
    print(f"  Kanaele: {len(selected)}/{len(all_channels)} (Top by priority+subs) | Zeitraum: {args.days} Tage", file=sys.stderr)
    if skipped:
        skipped_names = ", ".join(c.get("name", c.get("handle", "?"))[:20] for c in skipped[:5])
        print(f"  Uebersprungen: {skipped_names}{'...' if len(skipped) > 5 else ''}", file=sys.stderr)
    print(f"{'#'*60}", file=sys.stderr)

    # Step 1: Channel Search
    channel_videos, quota_hit = step_channel_search(
        args.keyword, selected, args.api_key, published_after, args.top_per_channel
    )

    # Step 2: Keyword Extraction
    extracted_keywords = step_extract_keywords(channel_videos[:30])

    # Step 3: Related Videos (skip if quota already hit)
    related_videos = []
    if not quota_hit:
        known_ids = {v["videoId"] for v in channel_videos}
        related_videos = step_related_videos(
            channel_videos[:args.max_seeds], args.api_key, published_after, known_ids, args.max_seeds
        )
    else:
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"STEP 3: UEBERSPRUNGEN — Quota bereits erschoepft", file=sys.stderr)
        print(f"{'='*60}", file=sys.stderr)

    # Combine all videos
    all_videos = channel_videos + related_videos
    # Deduplicate again
    seen = set()
    unique_all = []
    for v in all_videos:
        if v["videoId"] not in seen:
            seen.add(v["videoId"])
            unique_all.append(v)

    # Step 4: Outlier Analysis
    result = step_outlier_analysis(unique_all, args.multiplier)

    # Build final output
    output = {
        "keyword": args.keyword,
        "client": os.path.basename(args.client_dir),
        "searchedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "days": args.days,
        "multiplier": args.multiplier,
        "channelsSearched": len(selected),
        "channelsTotal": len(all_channels),
        "quotaExhausted": quota_hit,
        "totalVideosFromChannels": len(channel_videos),
        "totalRelatedVideos": len(related_videos),
        "totalUniqueVideos": len(unique_all),
        "extractedKeywords": extracted_keywords,
        "outliers": result["outliers"],
        "stats": result["stats"],
    }

    output_file = os.path.join(output_dir, f"research-{slug}-{today}.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # Summary
    print(f"\n{'#'*60}", file=sys.stderr)
    print(f"  FERTIG!", file=sys.stderr)
    print(f"  Kanaele durchsucht:  {len(selected)}/{len(all_channels)}", file=sys.stderr)
    print(f"  Videos aus Kanaelen: {len(channel_videos)}", file=sys.stderr)
    print(f"  Related Videos:      {len(related_videos)}", file=sys.stderr)
    print(f"  Gesamt unique:       {len(unique_all)}", file=sys.stderr)
    print(f"  Outlier gefunden:    {result['stats'].get('outlierCount', 0)}", file=sys.stderr)
    print(f"  Keywords extrahiert: {len(extracted_keywords)}", file=sys.stderr)
    if quota_hit:
        print(f"  ⚠ API-Quota erschoepft — Ergebnisse unvollstaendig", file=sys.stderr)
    print(f"  Report: {output_file}", file=sys.stderr)
    print(f"{'#'*60}", file=sys.stderr)


if __name__ == "__main__":
    main()
