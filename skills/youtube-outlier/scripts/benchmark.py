#!/usr/bin/env python3
"""
Autoresearch-style benchmark for the YouTube Outlier Finder.

Inspired by karpathy/autoresearch: run a fixed set of keyword tests,
compute a quality score for each, aggregate, and log to an iteration file.

Run every 2 minutes (e.g. via cron) to track skill improvement over time.

Quality score per keyword (0–10):
  - video_coverage:    min(total_videos / 150, 1.0) * 3   (want as many as possible)
  - outlier_ratio:     clamp(outlier_count / total * 10, 0, 3)  (10-30% ideal)
  - top_multiple:      min(top_views_multiple, 20) / 20 * 2     (how extreme the best outlier is)
  - velocity_signal:   min(top_velocity_multiple, 20) / 20 * 2  (are there velocity outliers?)
  Max total: 10

Usage:
  python3 benchmark.py [--api-key KEY] [--days 90] [--output-dir /tmp/youtube-outlier-bench]
"""
import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

SKILLS_DIR = os.path.dirname(os.path.abspath(__file__))

# Diverse keywords: mix of broad and medium-specificity topics
TEST_KEYWORDS = [
    "artificial intelligence",
    "personal finance",
    "fitness",
    "cooking",
    "home automation",
]


def run_cmd(cmd, timeout=120):
    """Run a subprocess, return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"Timeout nach {timeout}s"
    except Exception as e:
        return -1, "", str(e)


def score_result(stats: dict) -> dict:
    """Compute quality score 0-10 from analyze_outliers.py stats output."""
    total = stats.get("totalVideosAnalyzed", 0)
    outlier_count = stats.get("outlierCount", 0)
    median_views = stats.get("median", 0)
    threshold = stats.get("outlierThreshold", 0)
    median_velocity = stats.get("medianVelocity", 0)
    vel_threshold = stats.get("velocityThreshold", 0)

    if total == 0:
        return {"score": 0.0, "breakdown": {}}

    # Top outlier multiple (from outlier list in parent result)
    outlier_ratio = outlier_count / total if total > 0 else 0
    top_views_multiple = threshold / median_views if median_views > 0 else 0
    top_vel_multiple = vel_threshold / median_velocity if median_velocity > 0 else 0

    coverage = min(total / 150, 1.0) * 3
    ratio_score = min(outlier_ratio * 10, 1.0) * 3
    views_sig = min(top_views_multiple, 20) / 20 * 2
    vel_sig = min(top_vel_multiple, 20) / 20 * 2

    total_score = round(coverage + ratio_score + views_sig + vel_sig, 2)

    return {
        "score": total_score,
        "breakdown": {
            "coverage": round(coverage, 2),
            "outlier_ratio": round(ratio_score, 2),
            "views_signal": round(views_sig, 2),
            "velocity_signal": round(vel_sig, 2),
        },
        "stats_summary": {
            "total_videos": total,
            "outlier_count": outlier_count,
            "outlier_pct": round(outlier_ratio * 100, 1),
            "median_views": median_views,
            "median_velocity": median_velocity,
        }
    }


def run_keyword(keyword, api_key, days, use_ytdlp=False):
    """Fetch + analyze one keyword. Returns scored result dict."""
    raw_file = f"/tmp/yt_bench_{keyword.replace(' ', '_')}.json"
    out_file = f"/tmp/yt_bench_{keyword.replace(' ', '_')}_outliers.json"

    fetch_start = time.time()

    # API key validation: real keys are ≥30 chars (typically 39, starting with "AIza")
    api_key_valid = len(api_key) >= 30 if api_key else False

    if use_ytdlp or not api_key_valid:
        if api_key and not api_key_valid:
            print(f"  API-Key ungültig ({len(api_key)} Zeichen, erwartet ≥30) — yt-dlp Fallback", file=sys.stderr)
        fetch_cmd = [
            "python3", os.path.join(SKILLS_DIR, "fetch_youtube_ytdlp.py"),
            "--query", keyword,
            "--days", str(days),
            "--count", "30",   # 30 for benchmark speed; production uses 50
            "--timeout", "120",
            "--output", raw_file,
        ]
    else:
        # API: 1 page = 50 videos, costs ~101 API units (vs 303 for 3 pages).
        # For Dauerload benchmark runs, 1 page keeps quota under 10k/day even at 5-min intervals.
        fetch_cmd = [
            "python3", os.path.join(SKILLS_DIR, "fetch_youtube.py"),
            "--query", keyword,
            "--days", str(days),
            "--api-key", api_key,
            "--order", "relevance",
            "--pages", "1",
            "--output", raw_file,
        ]

    rc, stdout, stderr = run_cmd(fetch_cmd, timeout=60)
    fetch_time = round(time.time() - fetch_start, 1)

    if rc != 0:
        # Show the actual API error before falling back
        if not use_ytdlp and api_key_valid:
            err_snippet = stderr.strip().splitlines()[-1] if stderr.strip() else "unbekannt"
            print(f"  API-Fehler bei '{keyword}': {err_snippet[:100]} → yt-dlp Fallback", file=sys.stderr)
            return run_keyword(keyword, api_key, days, use_ytdlp=True)
        return {
            "keyword": keyword,
            "status": "error",
            "error": stderr.strip()[-200:],
            "fetch_time_s": fetch_time,
            "score": 0.0,
        }

    # Check raw data exists
    if not os.path.exists(raw_file):
        return {"keyword": keyword, "status": "no_data", "score": 0.0}

    # Analyze
    analyze_cmd = [
        "python3", os.path.join(SKILLS_DIR, "analyze_outliers.py"),
        "--input", raw_file,
        "--multiplier", "1.5",
        "--top", "30",
        "--metric", "combined",
        "--output", out_file,
    ]
    rc2, _, stderr2 = run_cmd(analyze_cmd, timeout=30)

    if rc2 != 0 or not os.path.exists(out_file):
        return {
            "keyword": keyword,
            "status": "analyze_error",
            "error": stderr2.strip()[-200:],
            "fetch_time_s": fetch_time,
            "score": 0.0,
        }

    with open(out_file, encoding="utf-8") as f:
        analysis = json.load(f)

    stats = analysis.get("stats", {})
    scored = score_result(stats)

    return {
        "keyword": keyword,
        "status": "ok",
        "fetch_time_s": fetch_time,
        "method": "ytdlp" if (use_ytdlp or not api_key_valid) else "api",
        **scored,
    }


def main():
    parser = argparse.ArgumentParser(description="YouTube Outlier Finder — Benchmark Runner")
    parser.add_argument("--api-key", default=os.environ.get("YOUTUBE_API_KEY", ""))
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--output-dir", default="/tmp/youtube-outlier-bench")
    parser.add_argument("--keywords", nargs="+", default=TEST_KEYWORDS,
                        help="Override test keywords (default: 5 built-in topics)")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    # Find next iteration number
    existing = [
        int(f.replace("iteration-", "").replace(".json", ""))
        for f in os.listdir(args.output_dir)
        if f.startswith("iteration-") and f.endswith(".json")
    ]
    iteration = max(existing, default=0) + 1

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"\n=== YouTube Outlier Benchmark — Iteration {iteration} ({ts}) ===\n")

    # Run keywords with limited parallelism (3 workers) to avoid yt-dlp rate limiting.
    # 3 parallel workers at ~60s each = ~60-90s total, fits in the 2-minute benchmark window.
    results_map = {}
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(run_keyword, kw, args.api_key, args.days): kw for kw in args.keywords}
        for i, future in enumerate(as_completed(futures), 1):
            kw = futures[future]
            r = future.result()
            status_str = f"score={r['score']:.2f}" if r["status"] == "ok" else f"FEHLER: {r.get('error','?')[:60]}"
            print(f"[{i}/{len(args.keywords)}] '{kw}' → {status_str}")
            results_map[kw] = r

    # Preserve original keyword order in output
    results = [results_map[kw] for kw in args.keywords]

    # Aggregate
    ok_results = [r for r in results if r["status"] == "ok"]
    avg_score = round(sum(r["score"] for r in ok_results) / len(ok_results), 2) if ok_results else 0.0
    avg_fetch = round(sum(r.get("fetch_time_s", 0) for r in ok_results) / len(ok_results), 1) if ok_results else 0.0

    summary = {
        "iteration": iteration,
        "timestamp": ts,
        "keywords_tested": len(args.keywords),
        "keywords_ok": len(ok_results),
        "avg_score": avg_score,
        "avg_fetch_time_s": avg_fetch,
        "results": results,
    }

    out_path = os.path.join(args.output_dir, f"iteration-{iteration}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # Compare with previous iteration if available
    prev_score = None
    if iteration > 1:
        prev_path = os.path.join(args.output_dir, f"iteration-{iteration-1}.json")
        if os.path.exists(prev_path):
            with open(prev_path) as f:
                prev = json.load(f)
            prev_score = prev.get("avg_score")

    api_key_valid = len(args.api_key) >= 30 if args.api_key else False
    method_used = "api" if api_key_valid else "yt-dlp"
    quota_note = f" (~{len(ok_results) * 101} API-Units verbraucht)" if method_used == "api" else " (kein API-Key, kein Quota-Verbrauch)"

    print(f"\n--- Ergebnis Iteration {iteration} ---")
    print(f"Keywords getestet:  {len(args.keywords)} ({len(ok_results)} erfolgreich)")
    print(f"Methode:            {method_used}{quota_note}")
    print(f"Avg Quality Score:  {avg_score}/10")
    print(f"Avg Fetch-Zeit:     {avg_fetch}s")
    if prev_score is not None:
        delta = round(avg_score - prev_score, 2)
        sign = "+" if delta >= 0 else ""
        print(f"vs. Iteration {iteration-1}:  {sign}{delta} ({prev_score} → {avg_score})")
    print(f"Log gespeichert:    {out_path}")
    print()

    # Per-keyword summary
    for r in results:
        kw = r["keyword"]
        if r["status"] == "ok":
            s = r.get("stats_summary", {})
            print(f"  {kw:<30} score={r['score']:.2f}  videos={s.get('total_videos',0)}  "
                  f"outliers={s.get('outlier_count',0)} ({s.get('outlier_pct',0):.0f}%)  "
                  f"method={r.get('method','?')}  fetch={r.get('fetch_time_s',0)}s")
        else:
            print(f"  {kw:<30} FEHLER [{r['status']}]")


if __name__ == "__main__":
    main()
