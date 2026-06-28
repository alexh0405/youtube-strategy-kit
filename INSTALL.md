# Installation für Claude Code

Kurzanleitung, um beide Skills in Claude Code einsatzbereit zu machen.

## Schnellweg

```bash
# 1. Repo holen
git clone https://github.com/alexh0405/youtube-strategy-kit.git
cd youtube-strategy-kit

# 2. Skills ins Claude-Code-Verzeichnis kopieren
mkdir -p ~/.claude/skills
cp -R skills/youtube-outlier   ~/.claude/skills/youtube-outlier
cp -R skills/youtube-strategie ~/.claude/skills/youtube-strategie

# 3. Konfiguration anlegen
cp .env.example .env
# .env öffnen und YOUTUBE_API_KEY (optional) + OBSIDIAN_VAULT_PATH (optional) eintragen

# 4. Optionaler Fallback ohne API-Key
pip install yt-dlp
```

Danach in Claude Code z.B.:

> "Ich will ein neues KI-Video machen — welches Thema lohnt sich?"

oder explizit:

> /youtube-strategie

## Per Claude Code installieren lassen

Du kannst Claude Code auch direkt bitten:

> "Installier mir die Skills aus https://github.com/alexh0405/youtube-strategy-kit —
>  klone das Repo und kopiere die beiden Ordner aus `skills/` nach `~/.claude/skills/`."

## Umgebungsvariablen

| Variable | Pflicht? | Zweck |
|----------|----------|-------|
| `YOUTUBE_API_KEY` | optional | Echte YouTube-Daten über die API v3. Ohne → yt-dlp-Fallback. |
| `OBSIDIAN_VAULT_PATH` | optional | Zielordner für Strategie-Notizen im Obsidian-Vault. |

Setze sie über die `.env` im Repo **oder** dauerhaft in deiner Shell (`~/.zshrc` / `~/.bashrc`):

```bash
export YOUTUBE_API_KEY="AIza...dein-key..."
export OBSIDIAN_VAULT_PATH="/Users/deinname/Documents/MeinVault"
```

## Verifizieren

```bash
# Keyword-Vorschläge (braucht keinen Key)
python3 ~/.claude/skills/youtube-strategie/scripts/suggest_keywords.py --topic "claude code"

# Outlier-Pipeline trockenlaufen lassen (yt-dlp-Fallback)
python3 ~/.claude/skills/youtube-outlier/scripts/fetch_youtube_ytdlp.py \
  --query "ai agents" --days 90 --count 20 --output /tmp/raw.json
python3 ~/.claude/skills/youtube-outlier/scripts/analyze_outliers.py \
  --input /tmp/raw.json --multiplier 1.5 --top 10 --output /tmp/out.json
```

Wenn beide Befehle ohne Fehler durchlaufen, ist alles startklar.
