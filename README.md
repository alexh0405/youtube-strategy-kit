# YouTube Strategy Kit — Outlier + Strategie

Zwei zusammenarbeitende Claude-Code-Skills für YouTube im **KI-Space** (KI/AI-Content, deutschsprachig):

1. **`youtube-strategie`** — führt dich von einer Idee zu einer konkreten, datenbasierten
   Video-Empfehlung. Stellt dir erst ein paar Fragen, schlägt dann passende **Keywords** vor,
   findet damit die erfolgreichsten Videos und sagt dir, **welches Video du als nächstes machen
   solltest** — inkl. Titel-Richtung, Thumbnail-Wort und Hook.
2. **`youtube-outlier`** — der Motor darunter: durchsucht YouTube nach einem Keyword und findet
   **Outlier** — Videos, die im Vergleich zum Durchschnitt überproportional viele Views haben.
   Einstellbar nach Zeitraum, Strenge, Sprache und Kanalgröße.

Du kannst beide einzeln nutzen oder den Strategie-Skill den Outlier automatisch ansteuern lassen.
Optional schreibt der Strategie-Skill seine Ergebnisse direkt als verlinkte Notiz in deinen
**Obsidian-Vault**.

---

## Was kann ich damit erreichen?

- **Nie wieder aus dem Bauch entscheiden, welches Video kommt.** Du siehst, was in deiner Nische
  gerade nachweislich performt — und bekommst eine konkrete Empfehlung daraus abgeleitet.
- **Erfolgreiche Muster erkennen und adaptieren** (Themen, Formate, Titel-/Thumbnail-Muster),
  statt sie zu erraten.
- **Echte YouTube-Daten** über die offizielle YouTube Data API v3 (mit deinem eigenen Key) —
  oder ganz ohne Key über einen yt-dlp-Fallback.
- **Dein Wissen wächst mit**: jede Recherche kann als Notiz in Obsidian landen und sich vernetzen.

---

## Installation

### 1. Repo klonen

```bash
git clone https://github.com/alexh0405/youtube-strategy-kit.git
cd youtube-strategy-kit
```

### 2. Skills für Claude Code verfügbar machen

Kopiere (oder verlinke) die beiden Skill-Ordner in dein Claude-Code-Skills-Verzeichnis:

```bash
cp -R skills/youtube-outlier   ~/.claude/skills/youtube-outlier
cp -R skills/youtube-strategie ~/.claude/skills/youtube-strategie
```

> Tipp: Du kannst die Skills auch direkt im geklonten Repo lassen und in den Befehlen auf
> `skills/...` zeigen — die SKILL.md-Dateien erklären, wie du den Pfad setzt.

### 3. Voraussetzungen

- **Python 3.7+** (die Skripte nutzen nur die Standardbibliothek — nichts zu installieren).
- **Optional: yt-dlp** als Fallback, falls du keinen API-Key nutzen willst:
  ```bash
  pip install yt-dlp
  ```

### 4. API-Key & Vault konfigurieren

```bash
cp .env.example .env
```

Trage in `.env` deine Werte ein (siehe nächste Abschnitte). Die `.env` ist über `.gitignore`
geschützt und landet **nie** im Repo.

---

## YouTube API Key (empfohlen)

Echte, schnelle Daten + Abo-Zahlen bekommst du mit einem eigenen, kostenlosen YouTube-Key:

1. Geh zur [Google Cloud Console](https://console.cloud.google.com/).
2. Erstelle ein Projekt (oder nimm ein bestehendes).
3. Aktiviere **"YouTube Data API v3"** (APIs & Dienste → Bibliothek).
4. **Anmeldedaten → API-Schlüssel erstellen.** Kopiere den Key (beginnt mit `AIza...`).
5. Trage ihn in deine `.env` ein:
   ```bash
   YOUTUBE_API_KEY=AIza...dein-key...
   ```
   Oder dauerhaft in der Shell:
   ```bash
   echo 'export YOUTUBE_API_KEY="AIza...dein-key..."' >> ~/.zshrc && source ~/.zshrc
   ```

**Kein Key?** Dann nutzt der Skill automatisch den **yt-dlp-Fallback** — langsamer und ohne
zuverlässige Abo-Zahlen, aber komplett ohne Anmeldung.

> Das tägliche Gratis-Kontingent (10.000 Units) reicht für rund 30 vollständige Recherche-Läufe pro Tag.

---

## Obsidian-Anbindung (optional)

Damit der Strategie-Skill Ergebnisse als Notiz in deinen Vault schreibt, setze den Pfad:

```bash
OBSIDIAN_VAULT_PATH=/Users/deinname/Documents/MeinVault
```

Mehr ist nicht nötig — geschrieben wird mit Bordmitteln. Wer mag, kann zusätzlich
[obsidian-cli](https://github.com/Yakitrak/obsidian-cli) installieren, um Notizen automatisch zu
öffnen. Details: [`skills/youtube-strategie/references/obsidian-integration.md`](skills/youtube-strategie/references/obsidian-integration.md).

---

## Nutzung

### In Claude Code

Sag einfach, was du brauchst — die Skills triggern selbst:

- **Strategie / Idee finden:**
  > "Ich will ein neues KI-Video machen — welches Thema lohnt sich?"
  > "/youtube-strategie"

  Der Skill stellt dir ein paar Fragen, schlägt Keywords vor, findet die Outlier und gibt dir eine
  konkrete Video-Empfehlung.

- **Direkt Outlier suchen:**
  > "Finde Outlier für 'Claude Code Tutorial' der letzten 60 Tage"
  > "/youtube-outlier claude code tutorial --days 60 --multiplier 2"

### Direkt über die Skripte (ohne Claude)

```bash
# Keyword-Vorschläge für den KI-Space
python3 skills/youtube-strategie/scripts/suggest_keywords.py --intent search --topic "claude code"

# Outlier-Analyse (yt-dlp-Fallback, kein Key nötig)
python3 skills/youtube-outlier/scripts/fetch_youtube_ytdlp.py --query "ai agents" --days 90 --count 50 --output /tmp/raw.json
python3 skills/youtube-outlier/scripts/analyze_outliers.py --input /tmp/raw.json --multiplier 1.5 --top 20 --output /tmp/out.json
```

---

## Parameter (Outlier)

| Flag | Default | Bedeutung |
|------|---------|-----------|
| `--days N` | 90 | Zeitraum: wie weit zurück gesucht wird (30 = was JETZT zündet, 180 = breite Sicht). |
| `--multiplier X` | 1.5 | Outlier-Schwelle als Vielfaches des Medians (2.0 = nur klare Überflieger). |
| `--top N` | 30 | Wie viele Outlier maximal im Report. |
| `--client SLUG` | — | Referenz-Kanal-Modus: sucht gezielt über deine Peer-Kanäle statt global. |
| `--metric` | combined | `views` / `velocity` / `combined` (Standard, balanciert groß vs. im Aufwind). |

**Sprache** und **Kanalgröße** steuerst du über die Keyword-Formulierung bzw. die Auswahl der
Outlier (Abo-Zahlen liefert der yt-dlp-Modus).

---

## Metriken — was bedeutet was?

- **Median Views** — der mittlere View-Wert aller gefundenen Videos. Robuster als der Durchschnitt.
  Die Outlier-Schwelle ist ein Vielfaches davon.
- **Outlier-Multiple** — wie weit ein Video über dem Median liegt (z.B. `3.2x`). Hoch = das Thema
  + die Verpackung zünden überdurchschnittlich.
- **Velocity (Views/Tag)** — Views geteilt durch Tage seit Upload. Findet, was *gerade* Fahrt aufnimmt.
- **Combined** — Durchschnitt aus Views-Rang und Velocity-Rang. Empfohlen.

> Shorts werden automatisch herausgefiltert (sie folgen anderen Viralitäts-Mustern).

---

## Eigene Referenz-Kanäle pflegen

Für den gezielten Client-Research-Modus kopierst du die Vorlage und trägst deine Kanäle ein:

```bash
cp -R clients/_template clients/mein-kanal
# dann clients/mein-kanal/reference-channels/channels.json bearbeiten
```

Die mitgelieferte Vorlage enthält drei erfolgreiche KI-Kanäle als Beispiel — **alle austauschbar**.

---

## Repo-Struktur

```
youtube-strategy-kit/
├── README.md · INSTALL.md · .env.example · LICENSE · .gitignore
├── skills/
│   ├── youtube-outlier/      # Outlier-Motor (SKILL.md + scripts/)
│   └── youtube-strategie/    # Strategie-Flow (SKILL.md + scripts/ + references/)
└── clients/
    └── _template/            # editierbare Vorlage für Referenz-Kanäle
```

## Troubleshooting

- **"API_VALID=False"** → kein/zu kurzer Key. Entweder Key in `.env` eintragen oder `pip install yt-dlp`.
- **yt-dlp findet nichts** → YouTube rate-limitet manchmal; später erneut versuchen oder API-Key nutzen.
- **Obsidian-Notiz erscheint nicht** → prüfe `OBSIDIAN_VAULT_PATH` (muss auf einen existierenden Ordner zeigen).

## Lizenz

MIT — siehe [LICENSE](LICENSE).
