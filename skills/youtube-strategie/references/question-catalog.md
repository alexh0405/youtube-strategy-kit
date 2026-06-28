# Onboarding-Fragenkatalog

Der Strategie-Skill kennt seinen Nutzer beim ersten Mal nicht. Bevor irgendein Output kommt,
führt er durch diesen Katalog. Ziel: erklären, was der Skill kann, was er vom Nutzer braucht,
und welche Parameter die spätere Outlier-Suche steuern.

Stelle die Fragen **gebündelt und in einem ruhigen Ton** — nicht als Verhör. Wenn der Nutzer
Antworten überspringt, nimm die Defaults und mach transparent weiter.

---

## Eröffnung (immer zuerst zeigen)

> **YouTube-Strategie ist aktiv.**
>
> Ich helfe dir, dein nächstes YouTube-Video datenbasiert zu finden — nicht aus dem Bauch,
> sondern aus dem, was im KI-Space gerade nachweislich performt.
>
> So läuft es:
> 1. Ich frage kurz, worum es gehen soll und für wen.
> 2. Ich schlage dir konkrete, suchbare **Keywords** vor (abgeleitet aus erfolgreichen KI-Kanälen).
> 3. Du wählst eins → ich finde damit die **Outlier-Videos** (überdurchschnittlich erfolgreiche Videos).
> 4. Ich werte sie strategisch aus → du bekommst eine **konkrete Video-Empfehlung** (Thema + Format + Hook + Verpackung).
> 5. Auf Wunsch schreibe ich das Ergebnis als Notiz in deinen **Obsidian-Vault**.
>
> Lass uns starten.

---

## Die Kernfrage (immer Frage 1)

**1. Welches Video möchtest du machen? Hast du schon eine Idee — oder sollen wir gemeinsam eine finden?**

- Hat eine Idee → die Idee als Ausgangspunkt nehmen, passende Keywords drumherum vorschlagen.
- Hat keine Idee → breiter in die Keyword-Bibliothek einsteigen, vom Cluster her vorschlagen.

---

## Kontext-Fragen (gebündelt stellen)

**2. In welchem KI-Unterthema bewegst du dich?**
*(z.B. Coding Agents / Automatisierung / KI fürs Business / KI-Tools & Vergleiche / Vibe Coding / KI-News)*
→ Mappt auf die Cluster in `ki-space-keyword-library.json`.

**3. Für wen ist das Video?**
*(z.B. Entwickler, Solo-Unternehmer, Firmen-Entscheider, KI-Einsteiger)*
→ Beeinflusst Tonalität, Format und ob Search- oder Browse-Keywords besser passen.

**4. Was ist dein Ziel?**
*(Reichweite schnell aufbauen / nachhaltig in der Nische ranken / Leads & Autorität / Kanal starten)*
→ Reichweite-schnell = **Browse**-Keywords. Nachhaltig/Autorität = **Search**-Keywords.

---

## Such-Parameter (steuern die Outlier-Analyse direkt)

Diese Antworten werden 1:1 zu den Flags des youtube-outlier Skills.

**5. Welcher Zeitraum?** → `--days` (Default **90**)
*Letzte 30 Tage = was JETZT zündet · 90 Tage = stabileres Bild · 180 Tage = breite Evergreen-Sicht.*

**6. Wie streng sollen die Outlier sein?** → `--multiplier` (Default **1.5**)
*1.5× Median = solide Ausreißer · 2.0× = nur klare Überflieger · 3.0× = nur die echten Raketen.*

**7. Welche Sprache?**
*Deutsch (Standard im KI-DACH-Raum) / Englisch / egal.* → Fließt in die Keyword-Formulierung ein.

**8. Welche Kanalgröße interessiert dich?** *(optional)*
*Kleine Kanäle (< 10k Abos), die ausschlagen, sind oft kopierbarer als große. Abo-Zahlen liefert nur
der yt-dlp-Modus zuverlässig — bei Bedarf darauf hinweisen.*

**9. Eigener Referenz-Kanal-Modus?** *(optional)* → `--client <slug>`
*Wenn der Nutzer eigene Peer-Kanäle pflegt (in `clients/<slug>/`), läuft die Suche gezielt über
diese statt global. Sonst: globaler Keyword-Modus.*

---

## Default-Set (wenn der Nutzer nichts/wenig sagt)

| Parameter | Default |
|-----------|---------|
| Zeitraum | 90 Tage |
| Multiplier | 1.5 |
| Sprache | Deutsch |
| Modus | Globaler Keyword-Modus |
| Metrik | combined |

Mit diesen Defaults kann der Skill auch sofort loslegen, wenn jemand einfach nur "find mir ein
gutes KI-Video-Thema" sagt.
