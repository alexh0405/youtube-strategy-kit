#!/usr/bin/env python3
"""
write_to_obsidian.py — Schreibt eine Strategie-Notiz in einen Obsidian-Vault.

Zwei Wege, in dieser Reihenfolge:
  1. obsidian-cli (falls installiert UND --use-cli gesetzt): nutzt die CLI, um die Notiz
     anzulegen/zu oeffnen — gut fuer Vaults, die ueber die CLI verwaltet werden.
  2. Direktes Schreiben (Default, immer verfuegbar): legt eine .md-Datei mit YAML-Frontmatter
     und Wikilinks direkt im Vault-Ordner ab. Funktioniert ohne jede Abhaengigkeit.

Der Vault-Pfad kommt aus --vault oder der Env-Var OBSIDIAN_VAULT_PATH.
Nur Python-Standardbibliothek.

Beispiel:
  python3 write_to_obsidian.py \
    --title "KI-Video-Strategie: Claude Code Tutorial" \
    --keyword "Claude Code Tutorial deutsch" \
    --body-file /tmp/strategie_body.md \
    --tags youtube,ki,strategie \
    --links "Strategie-Wissen,Outlier-Reports" \
    --folder "YouTube/Strategie"
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
from datetime import date


def slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-") or "notiz"


def build_frontmatter(title, keyword, tags, today):
    lines = ["---", f'title: "{title}"']
    if keyword:
        lines.append(f'keyword: "{keyword}"')
    lines.append(f"datum: {today}")
    if tags:
        taglist = [t.strip() for t in tags.split(",") if t.strip()]
        if taglist:
            lines.append("tags:")
            for t in taglist:
                lines.append(f"  - {t}")
    lines.append("---")
    return "\n".join(lines)


def build_links_block(links):
    if not links:
        return ""
    items = [l.strip() for l in links.split(",") if l.strip()]
    if not items:
        return ""
    block = ["", "## Verknüpfte Notizen", ""]
    block += [f"- [[{item}]]" for item in items]
    return "\n".join(block)


def main():
    p = argparse.ArgumentParser(description="Schreibt eine Strategie-Notiz in einen Obsidian-Vault.")
    p.add_argument("--title", required=True, help="Titel der Notiz")
    p.add_argument("--keyword", default="", help="Das analysierte Keyword (fuer Frontmatter)")
    p.add_argument("--body", default="", help="Notiz-Inhalt als String (Markdown)")
    p.add_argument("--body-file", default="", help="Pfad zu einer Datei mit dem Notiz-Inhalt (Markdown)")
    p.add_argument("--tags", default="youtube,ki,strategie", help="Kommagetrennte Tags")
    p.add_argument("--links", default="", help="Kommagetrennte Notiz-Namen fuer Wikilinks")
    p.add_argument("--folder", default="YouTube/Strategie", help="Unterordner im Vault")
    p.add_argument("--vault", default=os.environ.get("OBSIDIAN_VAULT_PATH", ""),
                   help="Pfad zum Obsidian-Vault (Default: $OBSIDIAN_VAULT_PATH)")
    p.add_argument("--use-cli", action="store_true",
                   help="obsidian-cli nutzen, falls installiert (sonst direktes Schreiben)")
    args = p.parse_args()

    vault = args.vault.strip()
    if not vault:
        print("Fehler: Kein Vault-Pfad. Setze OBSIDIAN_VAULT_PATH oder nutze --vault.", file=sys.stderr)
        sys.exit(1)
    vault = os.path.expanduser(vault)
    if not os.path.isdir(vault):
        print(f"Fehler: Vault-Ordner existiert nicht: {vault}", file=sys.stderr)
        sys.exit(1)

    today = date.today().isoformat()

    body = args.body
    if args.body_file:
        if not os.path.exists(args.body_file):
            print(f"Fehler: body-file nicht gefunden: {args.body_file}", file=sys.stderr)
            sys.exit(1)
        with open(args.body_file, encoding="utf-8") as f:
            body = f.read()
    if not body.strip():
        body = "_(Noch kein Inhalt — Notiz-Geruest.)_"

    frontmatter = build_frontmatter(args.title, args.keyword, args.tags, today)
    links_block = build_links_block(args.links)
    note = f"{frontmatter}\n\n# {args.title}\n\n{body.rstrip()}\n{links_block}\n"

    filename = f"{slugify(args.title)}-{today}.md"
    target_dir = os.path.join(vault, args.folder)
    os.makedirs(target_dir, exist_ok=True)
    target_path = os.path.join(target_dir, filename)

    # Weg 1: obsidian-cli (optional)
    if args.use_cli and shutil.which("obsidian-cli"):
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(note)
        try:
            subprocess.run(
                ["obsidian-cli", "open", os.path.join(args.folder, filename)],
                cwd=vault, check=False, timeout=20,
            )
        except Exception as e:  # noqa: BLE001
            print(f"Hinweis: obsidian-cli open fehlgeschlagen ({e}) — Datei wurde aber geschrieben.",
                  file=sys.stderr)
        print(target_path)
        return

    # Weg 2: direktes Schreiben (Default, robust)
    with open(target_path, "w", encoding="utf-8") as f:
        f.write(note)
    print(target_path)


if __name__ == "__main__":
    main()
