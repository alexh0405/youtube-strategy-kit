---
name: youtube-strategie
description: >
  Führt datenbasiert von einer Video-Idee zu einer konkreten YouTube-Strategie-Empfehlung,
  spezialisiert auf den KI-Space (KI/AI-Content, deutschsprachig). Startet mit einem
  Onboarding-Fragenkatalog (was kann der Skill, was braucht er, welche Metriken), schlägt dann
  konkrete, suchbare Keywords vor (abgeleitet aus erfolgreichen KI-Kanälen), übergibt das gewählte
  Keyword an den youtube-outlier Skill, wertet die Outlier strategisch aus (Hook, Pairing, Search
  vs. Browse, Expectations-vs-Reality) und liefert eine umsetzbare Video-Empfehlung. Kann das
  Ergebnis als verlinkte Notiz in einen Obsidian-Vault schreiben.

  USE THIS SKILL whenever the user wants to:
  - Eine Idee oder ein Thema für ihr nächstes YouTube-Video (besonders KI-Content) finden
  - Wissen, welches Video sie als nächstes machen sollten
  - YouTube-Strategie, Content-Planung oder Themen-Recherche für ihren Kanal
  - Keyword-Vorschläge für YouTube im KI-Bereich
  - "/youtube-strategie" explizit aufrufen

  Trigger u.a.: "welches Video soll ich machen", "YouTube-Strategie", "Video-Idee finden",
  "Content-Idee KI", "was soll ich als nächstes posten", "Keyword-Vorschläge YouTube".
---

# YouTube-Strategie (KI-Space)

Dieser Skill bringt den Nutzer von "ich will ein Video machen" zu einer konkreten, datenbasierten
Empfehlung. Er kombiniert eine kuratierte KI-Keyword-Bibliothek, den **youtube-outlier** Skill
(echte YouTube-Daten) und ein destilliertes Strategie-Wissen.

> **Pfad-Hinweis:** Setze einmal am Anfang die Skill-Verzeichnisse, damit die Befehle portabel sind:
> ```bash
> STRAT="$HOME/.claude/skills/youtube-strategie"     # ggf. anpassen
> OUTLIER="$HOME/.claude/skills/youtube-outlier"     # ggf. anpassen
> ```
> Liegen die Skills direkt im geklonten Repo, zeige stattdessen auf `skills/youtube-strategie` etc.

---

## Schritt 0 — Onboarding-Fragenkatalog (PFLICHT beim ersten Mal)

Der Nutzer kennt den Skill nicht. Beginne IMMER mit der Eröffnung und dem Fragenkatalog aus
`references/question-catalog.md`. Lies diese Datei und folge ihr:

- Zeige die **Eröffnung** (was der Skill kann, die 5 Schritte).
- Stelle **Frage 1** ("Welches Video möchtest du machen? Hast du schon eine Idee — oder sollen
  wir gemeinsam eine finden?").
- Stelle die **Kontext-Fragen** (Unterthema, Zielgruppe, Ziel) und die **Such-Parameter**
  (Zeitraum → `--days`, Strenge → `--multiplier`, Sprache, Kanalgröße, ggf. eigener Referenz-Kanal-Modus).

Stelle die Fragen gebündelt, ruhig, kein Verhör. Überspringt der Nutzer etwas → nimm die Defaults
(90 Tage, 1.5×, Deutsch, globaler Keyword-Modus) und mach transparent weiter.

**Wenn AskUserQuestion verfügbar ist:** bündele die Kernfragen in einem strukturierten Abfrage-Schritt.

---

## Schritt 1 — Keyword-Vorschläge

Basierend auf Unterthema, Zielgruppe und Ziel (Browse=Reichweite schnell / Search=Autorität
nachhaltig) lass `suggest_keywords.py` passende, suchbare Keywords vorschlagen:

```bash
python3 "$STRAT/scripts/suggest_keywords.py" \
  --intent INTENT \
  --topic "UNTERTHEMA" \
  --limit 8
```

- `--intent` = `search` | `browse` | `both` | `all` (aus dem Ziel des Nutzers ableiten).
- `--topic` = das Unterthema (z.B. "claude code", "automatisierung", "vibe coding"). Leer = alle Cluster.
- Optional `--client-dir clients/<slug>` für Kanal-Kontext, falls der Nutzer eigene Peers pflegt.

Präsentiere dem Nutzer die Cluster + Keywords mit der jeweiligen Begründung ("Warum zieht das?").
Prüfe jeden Vorschlag still gegen das **Topic-+-Format-Prinzip** (`references/strategy-knowledge.md`,
Abschnitt 3): ein Keyword ist nur dann gut, wenn sich daraus ein klares Topic *und* ein Format denken lässt.

**Hat der Nutzer schon eine eigene Idee** (aus Frage 1): nimm sie als Ausgangspunkt und schlage
1–2 verwandte Keyword-Varianten daneben vor, damit der Outlier-Lauf breit genug ansetzt.

Lass den Nutzer **ein Keyword wählen** (oder wähle das stärkste und schlage es vor).

---

## Schritt 2 — Outlier-Suche (echte YouTube-Daten)

Übergib das gewählte Keyword + die Parameter an den **youtube-outlier** Skill. Baue den Aufruf aus
den Onboarding-Antworten:

**Globaler Keyword-Modus (Standard):**
```bash
# 1. Fetch (API wenn YOUTUBE_API_KEY gesetzt, sonst yt-dlp-Fallback)
python3 "$OUTLIER/scripts/fetch_youtube.py" \
  --query "GEWÄHLTES_KEYWORD" --days DAYS \
  --api-key "$YOUTUBE_API_KEY" --order relevance --output /tmp/youtube_raw.json
# (Fällt der API-Call aus → fetch_youtube_ytdlp.py, siehe youtube-outlier SKILL.md)

# 2. Outlier berechnen
python3 "$OUTLIER/scripts/analyze_outliers.py" \
  --input /tmp/youtube_raw.json --multiplier MULTIPLIER --top 30 \
  --metric combined --output /tmp/youtube_outliers.json
```

**Eigener Referenz-Kanal-Modus** (wenn der Nutzer `clients/<slug>/` pflegt):
```bash
python3 "$OUTLIER/scripts/research_pipeline.py" \
  --keyword "GEWÄHLTES_KEYWORD" --client-dir "clients/SLUG" \
  --api-key "$YOUTUBE_API_KEY" --days DAYS --multiplier MULTIPLIER
```

Folge bei der genauen Mechanik (Methodenwahl, Fallback, Report-Format) der `youtube-outlier/SKILL.md`.

---

## Schritt 3 — Strategische Auswertung

Lies das Outlier-Ergebnis und werte es gegen `references/strategy-knowledge.md` aus. Für die
**Top 3–5 Outlier** jeweils:

- **EVR-Check** (Abschnitt 1): Welche Erwartung weckt Titel+Thumbnail, wie wird sie übertroffen?
- **Hook-Muster** (Abschnitt 6/7): Welcher der 4-Stufen-Hook / welcher First-Liner-Typ steckt dahinter?
- **Pairing** (Abschnitt 10): Was macht der Titel (Kontext/Keyword), was das Thumbnail (Neugier)?
- **Search vs. Browse** (Abschnitt 5): Ist das ein evergreen Search-Play oder ein Momentum-Browse-Play?

Leite daraus **eine konkrete Video-Empfehlung** ab:

```
## Empfehlung: Dein nächstes Video

**Topic + Format:** [worüber] + [wie präsentiert]  (Abschnitt 3)
**Intent:** Search / Browse — und warum YouTube es ausspielt
**Titel-Richtung:** [Kontext/Keyword, kein fertiger Titel]
**Thumbnail-Wort(e):** [1–3 Wörter, Neugier — überlappt NICHT mit dem Titel]
**Hook-Richtung:** [Climax-first Einstieg, Abschnitt 11 + First-Liner-Typ]
**Warum das zieht:** [Bezug auf die konkreten Outlier-Befunde]
```

Optional, wenn der Nutzer über das einzelne Video hinaus will: Kanal-Bausteine aus Abschnitt 12
anbieten (Leitsatz, USP, 70/30-Split, 1-Fokus-Funnel).

---

## Schritt 4 — Obsidian (optional)

Frage, ob das Ergebnis in den Obsidian-Vault soll. Wenn ja (und `OBSIDIAN_VAULT_PATH` gesetzt ist),
schreibe die Empfehlung + die Outlier-Kernbefunde als Notiz. Schreibe den Body vorher nach
`/tmp/strategie_body.md`, dann:

```bash
python3 "$STRAT/scripts/write_to_obsidian.py" \
  --title "KI-Video-Strategie: KEYWORD" \
  --keyword "GEWÄHLTES_KEYWORD" \
  --body-file /tmp/strategie_body.md \
  --tags youtube,ki,strategie \
  --links "Strategie-Wissen,Outlier-Reports" \
  --folder "YouTube/Strategie"
```

Details und der optionale obsidian-cli-Weg: `references/obsidian-integration.md`.

---

## Referenzen (bei Bedarf laden)

- `references/question-catalog.md` — der vollständige Onboarding-Fragenkatalog (Schritt 0)
- `references/strategy-knowledge.md` — das Strategie-Wissen (Schritt 1 & 3)
- `references/ki-space-keyword-library.json` — die Keyword-Cluster (Schritt 1)
- `references/obsidian-integration.md` — Vault-Anbindung (Schritt 4)

## Wichtige Regeln

- **Reihenfolge ist fest:** erst Onboarding → dann Keywords → dann Outlier → dann Auswertung → dann Obsidian.
- **Keyword-Vorschläge müssen suchbar sein** und das Topic-+-Format-Prinzip erfüllen — keine vagen Themen.
- **Titel ≠ Thumbnail** in jeder Empfehlung (Pairing-Prinzip).
- **Echte Daten:** Die Outlier-Befunde kommen immer aus dem youtube-outlier Skill, nie aus dem Bauch.
- **Defaults nutzen**, wenn der Nutzer Parameter überspringt — den Flow nie blockieren.
