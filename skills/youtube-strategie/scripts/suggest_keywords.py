#!/usr/bin/env python3
"""
suggest_keywords.py — Schlaegt suchbare KI-Space-Keywords vor.

Liest die kuratierte Keyword-Bibliothek (references/ki-space-keyword-library.json) und —
optional — die Referenz-Kanaele eines Clients (clients/<slug>/reference-channels/channels.json),
um die Vorschlaege zu kontextualisieren.

Gibt eine menschenlesbare Liste UND (mit --json) ein maschinenlesbares Objekt aus, das der
Strategie-Skill direkt weiterverarbeiten kann.

Nur Python-Standardbibliothek.

Beispiele:
  # Alle Cluster
  python3 suggest_keywords.py

  # Nur Search-Intent, gefiltert auf ein Thema, mit Client-Kontext
  python3 suggest_keywords.py --intent search --topic "claude code" \
    --client-dir clients/_template --limit 10 --json
"""
import argparse
import json
import os
import sys


def load_library(path):
    if not os.path.exists(path):
        print(f"Fehler: Keyword-Bibliothek nicht gefunden: {path}", file=sys.stderr)
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_channels(client_dir):
    if not client_dir:
        return []
    cf = os.path.join(client_dir, "reference-channels", "channels.json")
    if not os.path.exists(cf):
        return []
    try:
        with open(cf, encoding="utf-8") as f:
            data = json.load(f)
        chs = data.get("channels", data) if isinstance(data, dict) else data
        return [c for c in chs if isinstance(c, dict) and c.get("name")]
    except Exception:  # noqa: BLE001
        return []


def match_topic(cluster, topic):
    """True, wenn das Cluster zum Topic passt (Substring in Label/Keywords/Why/Id)."""
    if not topic:
        return True
    t = topic.lower()
    hay = " ".join([
        cluster.get("label", ""),
        cluster.get("id", ""),
        cluster.get("why", ""),
        " ".join(cluster.get("keywords", [])),
    ]).lower()
    return all(word in hay for word in t.split())


def collect(library, intent, topic, limit):
    clusters = library.get("clusters", [])
    results = []
    for cl in clusters:
        if intent and intent != "all" and cl.get("intent") not in (intent, "both"):
            continue
        if not match_topic(cl, topic):
            continue
        kws = cl.get("keywords", [])
        results.append({
            "cluster": cl.get("label", cl.get("id", "")),
            "intent": cl.get("intent", ""),
            "why": cl.get("why", ""),
            "keywords": kws[:limit] if limit else kws,
        })
    return results


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    default_lib = os.path.normpath(os.path.join(here, "..", "references", "ki-space-keyword-library.json"))

    p = argparse.ArgumentParser(description="Schlaegt suchbare KI-Space-Keywords vor.")
    p.add_argument("--library", default=default_lib, help="Pfad zur Keyword-Bibliothek (JSON)")
    p.add_argument("--intent", choices=["all", "search", "browse", "both"], default="all",
                   help="Nur Keywords mit diesem Intent (search=evergreen, browse=momentum)")
    p.add_argument("--topic", default="", help="Auf ein Unterthema filtern (z.B. 'claude code')")
    p.add_argument("--client-dir", default="", help="Optionaler Client-Ordner fuer Kanal-Kontext")
    p.add_argument("--limit", type=int, default=0, help="Max. Keywords pro Cluster (0 = alle)")
    p.add_argument("--json", action="store_true", help="Maschinenlesbares JSON ausgeben")
    args = p.parse_args()

    library = load_library(args.library)
    channels = load_channels(args.client_dir)
    results = collect(library, args.intent, args.topic, args.limit)

    if args.json:
        out = {
            "niche": library.get("niche", ""),
            "language": library.get("language", ""),
            "intent_filter": args.intent,
            "topic_filter": args.topic,
            "reference_channels": [c.get("name") for c in channels],
            "suggestions": results,
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    # Menschenlesbar
    print("=== KI-Space Keyword-Vorschlaege ===")
    if args.topic:
        print(f"Thema-Filter: {args.topic}")
    print(f"Intent-Filter: {args.intent}")
    if channels:
        print("Referenz-Kanaele: " + ", ".join(c.get("name", "") for c in channels))
    print()

    if not results:
        print("Keine passenden Cluster gefunden. Versuche einen breiteren --topic oder --intent all.")
        return

    for r in results:
        print(f"## {r['cluster']}  [{r['intent']}]")
        print(f"   Warum: {r['why']}")
        for kw in r["keywords"]:
            print(f"   - {kw}")
        print()

    print("Tipp: Waehle ein Keyword und uebergib es an den youtube-outlier Skill, z.B.")
    print('  "<keyword>" --days 90 --multiplier 1.5')


if __name__ == "__main__":
    main()
