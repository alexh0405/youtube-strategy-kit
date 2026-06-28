# Obsidian-Integration

Der Strategie-Skill kann seine Ergebnisse direkt in deinen Obsidian-Vault schreiben — als
verlinkte Markdown-Notiz mit Frontmatter. So wächst aus jeder Recherche ein durchsuchbares,
vernetztes Wissensnetz statt loser Dateien.

## Voraussetzung

Setze den Vault-Pfad in deiner `.env` (oder als Umgebungsvariable):

```bash
OBSIDIAN_VAULT_PATH=/Users/deinname/Documents/MeinVault
```

Mehr ist nicht nötig. Das Schreiben läuft über die Python-Standardbibliothek — keine Plugins,
keine externen Abhängigkeiten.

## Zwei Wege

Das Skript `scripts/write_to_obsidian.py` schreibt auf zwei Arten:

1. **Direktes Schreiben (Standard, immer verfügbar):** Legt eine `.md`-Datei mit YAML-Frontmatter
   (`title`, `keyword`, `datum`, `tags`) und `[[Wikilinks]]` im Vault-Ordner ab. Obsidian erkennt
   die Notiz beim nächsten Öffnen automatisch. Funktioniert auf jedem System.

2. **obsidian-cli (optional, mit `--use-cli`):** Wenn du
   [obsidian-cli](https://github.com/Yakitrak/obsidian-cli) installiert hast, kann das Skript die
   Notiz zusätzlich direkt in Obsidian öffnen. Fällt automatisch auf direktes Schreiben zurück,
   falls die CLI nicht da ist.

   Installation (optional):
   ```bash
   brew install yakitrak/yakitrak/obsidian-cli   # macOS
   # danach einmalig den Standard-Vault setzen:
   obsidian-cli set-default "MeinVault"
   ```

## Was geschrieben wird

```markdown
---
title: "KI-Video-Strategie: Claude Code Tutorial"
keyword: "Claude Code Tutorial deutsch"
datum: 2026-06-28
tags:
  - youtube
  - ki
  - strategie
---

# KI-Video-Strategie: Claude Code Tutorial

[... der Strategie-Output: Outlier-Befunde, empfohlenes Topic+Format, Hook-Richtung, Packaging ...]

## Verknüpfte Notizen

- [[Strategie-Wissen]]
- [[Outlier-Reports]]
```

## Aufruf (macht der Skill für dich)

```bash
python3 skills/youtube-strategie/scripts/write_to_obsidian.py \
  --title "KI-Video-Strategie: Claude Code Tutorial" \
  --keyword "Claude Code Tutorial deutsch" \
  --body-file /tmp/strategie_body.md \
  --tags youtube,ki,strategie \
  --links "Strategie-Wissen,Outlier-Reports" \
  --folder "YouTube/Strategie"
```

Der Standard-Zielordner im Vault ist `YouTube/Strategie/` — über `--folder` änderbar.

## Tipp: Wissensnetz aufbauen

Vergib bei jeder Notiz konsistente Tags (`#youtube`, `#ki`, `#strategie`) und verlinke auf eine
zentrale Übersichtsnotiz (z.B. `[[YouTube-Strategie MOC]]`). So entsteht über die Zeit eine
Map of Content, in der du alle recherchierten Themen, Outlier-Muster und Video-Ideen an einem
Ort siehst.
