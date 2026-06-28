---
name: youtube-outlier
description: >
  Searches YouTube for videos matching a keyword and identifies outliers — videos that have
  received disproportionately many views compared to the median of all found videos in a given
  time window (default: last 90 days). Uses the YouTube Data API v3 (if API key available) or
  yt-dlp as a fallback (no API key needed) to collect up to 150 results, computes the median,
  and marks anything above 1.5x the median as an outlier. Outputs a formatted Markdown report file.

  Supports two modes:
  - **Keyword mode** (default): Search YouTube globally for a keyword
  - **Client research mode**: Search across a set of reference channels, extract keywords
    from top videos, find related videos YouTube suggests alongside them, and run outlier
    analysis on the combined dataset. Much more targeted than blind keyword search.

  USE THIS SKILL whenever the user wants to:
  - Find viral or over-performing YouTube videos for a topic or keyword
  - Discover YouTube outliers, content opportunities, or trending videos
  - Analyze which videos in a niche perform unusually well
  - Run "/youtube-outlier [keyword]" explicitly
  - Understand what content is blowing up on YouTube for a given subject
  - Research video ideas using a set of reference channels

  Do NOT wait for the user to say "outlier" specifically — if they want to know which YouTube
  videos are performing exceptionally, trending, or getting far more views than normal for a
  keyword, invoke this skill.
---

# YouTube Outlier Finder

This skill searches YouTube for videos matching a keyword and surfaces the ones that are
dramatically outperforming the median — the hidden gems or viral content for that niche.

> **Pfad-Hinweis:** Alle Befehle gehen davon aus, dass dieser Skill unter
> `~/.claude/skills/youtube-outlier/` installiert ist. Liegt er woanders (z.B. direkt im
> geklonten Repo unter `skills/youtube-outlier/`), passe den Skript-Pfad entsprechend an.
> Der `SKILLDIR` lässt sich am Anfang einmal setzen:
> ```bash
> SKILLDIR="$HOME/.claude/skills/youtube-outlier"   # ggf. anpassen
> ```

## Step 0 — Parse arguments & detect mode

Args come in as a string like: `"claude code tutorial --days 60 --multiplier 2"`

Parse them:
- First non-flag token(s) = the keyword/query (can be multiple words, collect until first `--`)
- `--days N` → how far back to search (default: 90)
- `--multiplier X` → outlier threshold as multiple of median (default: 1.5)
- `--top N` → maximum outliers to show (default: 30)
- `--client NAME` → client slug (e.g. `mein-kanal`) to use client research mode

If the keyword is empty, ask the user: "Welches Keyword soll ich auf YouTube analysieren?"

**Mode detection:**
- If `--client` is provided OR the conversation references a configured client → **Client Research Mode** (Step 1B)
- Otherwise → **Keyword Mode** (Step 1A)

Client directories live in: `clients/<slug>/` (relative to the repo root). Copy `clients/_template/`
to create a new one.

## Step 1A — Keyword Mode (global search)

### Determine fetch method

Run these checks in one go:

```bash
python3 - <<'EOF'
import os, shutil, sys

key = os.environ.get("YOUTUBE_API_KEY", "").strip()
ytdlp = shutil.which("yt-dlp") is not None
api_valid = len(key) >= 30

if key and not api_valid:
    print(f"API_ERROR: Key zu kurz ({len(key)} Zeichen, erwartet >=30).", file=sys.stderr)

print(f"API_VALID={api_valid}")
print(f"YTDLP={ytdlp}")
EOF
```

**Decision logic (in order):**
- If `API_VALID=True` → use **Method A** (YouTube Data API)
- If `API_VALID=False` and `YTDLP=True` → use **Method B** (yt-dlp)
- If both unavailable → stop and tell the user how to set up either option (siehe README)

### Search YouTube

**Method A — YouTube Data API:**

```bash
python3 "$SKILLDIR/scripts/fetch_youtube.py" \
  --query "KEYWORD" \
  --days DAYS \
  --api-key "$YOUTUBE_API_KEY" \
  --order relevance \
  --output /tmp/youtube_raw.json
```

**Method B — yt-dlp** (fallback):

```bash
python3 "$SKILLDIR/scripts/fetch_youtube_ytdlp.py" \
  --query "KEYWORD" \
  --days DAYS \
  --count 50 \
  --timeout 120 \
  --output /tmp/youtube_raw.json
```

If Method A fails, fall back to Method B without asking.

### Compute outliers

```bash
python3 "$SKILLDIR/scripts/analyze_outliers.py" \
  --input /tmp/youtube_raw.json \
  --multiplier MULTIPLIER \
  --top TOP \
  --metric combined \
  --output /tmp/youtube_outliers.json
```

Then proceed to **Step 2 — Write the report**.

## Step 1B — Client Research Mode (reference channel pipeline)

This is the preferred mode when researching for a specific channel. It searches across the
configured reference channels, extracts keywords from their top videos, finds what YouTube
suggests alongside them, and runs outlier analysis on the combined dataset.

**Run the full pipeline in one command:**

```bash
python3 "$SKILLDIR/scripts/research_pipeline.py" \
  --keyword "KEYWORD" \
  --client-dir "clients/CLIENT_SLUG" \
  --api-key "$YOUTUBE_API_KEY" \
  --days DAYS \
  --multiplier MULTIPLIER \
  --max-channels 10 \
  --top-per-channel 3 \
  --max-seeds 3
```

**Quota budget: ~321 Units per run → ~31 runs/day** (10k daily limit).

**What the pipeline does internally (4 steps):**

1. **Channel Prioritization + Upload Scan** — Sorts reference channels by `priority` field
   (if set) then `subscribers`. Only scans the top N channels (`--max-channels`, default 10).
   Uses `playlistItems.list` (1 Unit) instead of `search.list` (100 Units) to fetch recent
   uploads, then filters by keyword match in title. Collects top 3 per channel.
   Stops immediately on API quota exhaustion (403).

2. **Keyword Extraction** — Analyzes titles of the top 30 videos, extracts recurring
   bigrams and trigrams (filters noise words in EN + DE). These are the phrases the
   algorithm is currently clustering around.

3. **Related Videos** — Takes the top 10 seed videos and derives search queries from
   their titles (first 5 meaningful words). Searches YouTube for each query to find what
   the algorithm suggests alongside these top performers. Deduplicates against known IDs.

4. **Outlier Analysis** — Combines channel videos + related videos, computes median views
   and median velocity (views/day), marks anything above multiplier×median as outlier.
   Ranks by combined average of views-rank + velocity-rank.

**Output:** JSON file saved to `clients/<slug>/reports/research-<keyword>-<date>.json`

The JSON contains:
- `topVideos` — global top 30 from channel search
- `extractedKeywords` — recurring phrases from titles
- `outliers` — all videos above the threshold, ranked
- `stats` — median, average, thresholds, counts

After the pipeline finishes, read the JSON output and proceed to **Step 2**.

### Client directory structure

```
clients/<slug>/
├── config.json                    ← Channel + search defaults
├── reference-channels/
│   └── channels.json              ← Reference channels with IDs + metadata
└── reports/
    └── research-<keyword>-<date>.json
```

To add a new client:
1. Copy `clients/_template/` to `clients/<slug>/`
2. Edit `reference-channels/channels.json` — add the channels you want to track
3. Edit `config.json` with your defaults

## Step 2 — Write the report

Read the output JSON and use the Write tool to create the report.

**For Keyword Mode:** Read `/tmp/youtube_outliers.json`
**For Client Research Mode:** Read the pipeline output JSON

**Filename:** `youtube-outlier-{keyword-slug}-{YYYY-MM-DD}.md`
Save in the **current working directory** (Keyword Mode) or `clients/<slug>/reports/` folder (Client Mode).

**Report format** (use this exact structure):

```markdown
# YouTube Outlier Report: {keyword}

**Analysezeitraum:** Letzte {days} Tage
**Analysiert am:** {date}
**Videos analysiert:** {totalVideosAnalyzed}
**Median Views:** {median} ({median_formatted})
**Durchschnitt Views:** {average} ({average_formatted})
**Outlier-Schwelle:** {threshold} ({multiplier}x Median)
**Outlier gefunden:** {count}

---

## Outlier-Videos

### {rank}. {title}

- **Kanal:** {channelTitle}
- **Views:** {viewCount_formatted} | **Views/Tag:** {viewsPerDayFormatted} ({velocityMultiple} Median)
- **Outlier-Multiple:** {outlierMultiple}
- **Veroeffentlicht:** {publishedAt_formatted} ({daysSincePublish} Tage her)
- **Likes:** {likeCount} | **Kommentare:** {commentCount} | **Engagement:** {engagementRate}
- **Kanal-Abonnenten:** {subscriberCount} *(nur bei yt-dlp verfügbar)*
- **Link:** {url}

[... repeat for each outlier ...]

---
*Generiert mit YouTube Outlier Finder | {totalVideosAnalyzed} Videos analysiert*
```

**For Client Research Mode**, add these extra sections after the header:

```markdown
**Modus:** Client Research ({client})
**Referenzkanaele:** {channelsSearched}
**Videos aus Kanaelen:** {totalVideosFromChannels}
**Related Videos:** {totalRelatedVideos}

## Extrahierte Keywords
{list of extracted keyword phrases with counts}
```

Format numbers with thousand separators (e.g. `1,234,567`). Format dates as `DD.MM.YYYY`.

**Edge cases:**
- If no outliers found, show top 10 by view count with a note
- If fewer than 5 videos found, warn about small sample size

## Step 3 — Summary output

After writing the file, print a concise summary to the user:

```
Analyse abgeschlossen!

Videos analysiert:  {total}
Median Views:       {median_formatted}
Outlier gefunden:   {count} ({multiplier}x Median-Schwelle)
Bericht gespeichert: {filepath}
```

For Client Research Mode, also include:
```
Referenzkanaele:    {channelsSearched}
Videos aus Kanaelen: {fromChannels}
Related Videos:     {related}
Top-Keywords:       {comma-separated list of top 5 extracted keywords}
```

## Metriken — was bedeutet was?

- **Median Views:** Der mittlere View-Wert aller gefundenen Videos. Robuster als der Durchschnitt,
  weil einzelne Mega-Videos ihn nicht verzerren. Die Outlier-Schwelle ist ein Vielfaches davon.
- **Outlier-Multiple:** Wie oft über dem Median ein Video liegt (z.B. `3.2x` = 3,2-fache Median-Views).
  Je höher, desto stärker schlägt das Video aus der Reihe — ein Signal, dass Thema + Verpackung zünden.
- **Velocity (Views/Tag):** Views geteilt durch Tage seit Veröffentlichung. Findet, was GERADE
  Fahrt aufnimmt — wichtig, weil ein altes Video mit vielen Views nicht heißt, dass das Thema heute zieht.
- **Combined-Metrik (Standard):** Durchschnitt aus Views-Rang und Velocity-Rang. Balanciert "absolut groß"
  gegen "gerade im Aufwind". Empfohlen für breite Keywords.
- **Shorts werden gefiltert** (Titel mit #shorts oder Dauer < 90s), weil sie anderen Viralitäts-Mustern
  folgen und die Outlier-Erkennung verzerren würden.
