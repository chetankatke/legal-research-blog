"""publish_to_blog.py — Sync Obsidian vault → Astro blog content.

Reads vault notes (Translations, Cases, Research) and writes Astro-compatible
markdown to the blog content collection.

Usage:
  python3 publish_to_blog.py [--watch] [--dry-run]

Behavior:
  - Walks ~/Obsidian/legal-research/Translations/<lang>/<slug>.md
  - Writes to ~/legal-research-system/blog/src/content/blog/<lang>/<slug>.md
  - Also publishes English case notes (Cases/<slug>/README.md)
  - Also publishes Research notes (Research/<slug>.md)
  - Strips Obsidian wikilinks → plain text marks
  - Only writes if content or mtime changed
  - --watch: re-run every 30s (for dev)
"""
import argparse
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


VAULT_DEFAULT = os.path.expanduser("~/Obsidian/legal-research")
BLOG_DIR = Path(os.path.expanduser("~/legal-research-system/blog"))
CONTENT_DIR = BLOG_DIR / "src" / "content" / "blog"


def get_vault() -> Path:
    return Path(os.environ.get("OBSIDIAN_VAULT_PATH", VAULT_DEFAULT)).expanduser()


def strip_wikilinks(text: str) -> str:
    """Convert Obsidian [[wikilinks]] to plain text."""
    # [[Cases/slug/README|alias]] → alias (or slug if no alias)
    text = re.sub(r"\[\[([^]|]+)\|([^]]+)\]\]", r"\2", text)
    # [[Cases/slug/README]] → slug
    text = re.sub(r"\[\[([^]]+)\]\]", r"\1", text)
    return text


def extract_frontmatter(text: str) -> dict:
    """Parse frontmatter from markdown, returning dict with case-insensitive keys."""
    result = {}
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                key, _, val = line.partition(":")
                key = key.strip().lower()
                val = val.strip().strip('"').strip("'")
                result[key] = val
    return result


def build_astro_frontmatter(case_title: str, lang: str, slug: str, pub_date: str | None = None,
                            tags: list | None = None, description: str | None = None) -> dict:
    """Build standard Astro frontmatter for a blog post."""
    return {
        "title": case_title,
        "description": description or f"Legal analysis of {case_title}",
        "pubDate": pub_date or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "lang": lang,
        "tags": tags or ["legal", "judgment"],
        "caseSlug": slug,
    }


def sync_vault_to_blog(vault: Path, dry_run: bool = False):
    """Walk vault and sync content to the blog."""
    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    written = 0
    skipped = 0

    # 1. Sync Translations/<lang>/<slug>.md
    trans_dir = vault / "Translations"
    if trans_dir.exists():
        for lang_dir in sorted(trans_dir.iterdir()):
            lang = lang_dir.name
            for note_file in sorted(lang_dir.glob("*.md")):
                slug = note_file.stem
                content = note_file.read_text()
                fm = extract_frontmatter(content)
                case_title = fm.get("title", fm.get("case_title", ""))
                if not case_title:
                    heading_m = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
                    if heading_m:
                        case_title = heading_m.group(1).strip()
                if not case_title:
                    case_title = slug.replace("-", " ").title()
                pub_date = fm.get("translated_at", fm.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d")))[:10]
                tags = ["legal", "judgment", lang]

                # Build Astro-compatible content
                body = strip_wikilinks(content)
                astro_fm = build_astro_frontmatter(case_title, lang, slug, pub_date, tags)
                astro_content = f"---\ntitle: {astro_fm['title']}\ndescription: {astro_fm['description']}\npubDate: {astro_fm['pubDate']}\nlang: {lang}\ntags: {tags}\ncaseSlug: {slug}\n---\n\n{body}"

                out_dir = CONTENT_DIR / lang
                out_dir.mkdir(parents=True, exist_ok=True)
                out_path = out_dir / f"{slug}.md"

                if out_path.exists() and out_path.read_text() == astro_content:
                    skipped += 1
                    continue
                if not dry_run:
                    out_path.write_text(astro_content)
                written += 1

    # 2. Sync English case notes (Cases/<slug>/README.md)
    cases_dir = vault / "Cases"
    if cases_dir.exists():
        for case_dir in sorted(cases_dir.iterdir()):
            readme = case_dir / "README.md"
            if not readme.exists():
                continue
            slug = case_dir.name
            content = readme.read_text()
            fm = extract_frontmatter(content)
            case_title = fm.get("title", fm.get("case_title", ""))
            if not case_title:
                heading_m = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
                if heading_m:
                    case_title = heading_m.group(1).strip()
            if not case_title:
                case_title = slug
            date = fm.get("date", fm.get("ingested_at", ""))[:10]
            tags_str = fm.get("tags", "")

            body = strip_wikilinks(content)
            out_dir = CONTENT_DIR / "en"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"case-{slug}.md"

            astro_content = f"---\ntitle: {case_title}\ndescription: Full case analysis of {case_title}\npubDate: {date or datetime.now(timezone.utc).strftime('%Y-%m-%d')}\nlang: en\ntags: [legal, judgment, case]\ncaseSlug: {slug}\n---\n\n{body}"

            if out_path.exists() and out_path.read_text() == astro_content:
                skipped += 1
                continue
            if not dry_run:
                out_path.write_text(astro_content)
            written += 1

    # 3. Sync Research notes
    research_dir = vault / "Research"
    if research_dir.exists():
        for note_file in sorted(research_dir.glob("*.md")):
            slug = note_file.stem
            content = note_file.read_text()
            fm = extract_frontmatter(content)
            title = fm.get("title", fm.get("question", slug))
            pub_date = fm.get("generated_at", "")[:10]

            body = strip_wikilinks(content)
            out_dir = CONTENT_DIR / "en"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"research-{slug}.md"

            astro_content = f"---\ntitle: {title}\ndescription: Deep research report\npubDate: {pub_date or datetime.now(timezone.utc).strftime('%Y-%m-%d')}\nlang: en\ntags: [research, legal]\n---\n\n{body}"

            if out_path.exists() and out_path.read_text() == astro_content:
                skipped += 1
                continue
            if not dry_run:
                out_path.write_text(astro_content)
            written += 1

    return written, skipped


def main():
    parser = argparse.ArgumentParser(description="Sync vault → Astro blog content")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be done")
    parser.add_argument("--watch", action="store_true", help="Watch mode (re-run every 30s)")
    args = parser.parse_args()

    vault = get_vault()
    if not vault.exists():
        print(f"ERROR: Vault not found: {vault}", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"  [Dry run — scanning vault: {vault}]")

    written, skipped = sync_vault_to_blog(vault, args.dry_run)
    print(f"  ✓ {written} file(s) written, {skipped} skipped")

    if args.watch:
        import time
        try:
            while True:
                time.sleep(30)
                written, skipped = sync_vault_to_blog(vault, False)
                if written:
                    print(f"  [{datetime.now().isoformat()}] {written} new, {skipped} unchanged")
                    # Auto-rebuild the blog
                    subprocess.run(["npm", "run", "build"], cwd=BLOG_DIR,
                                   capture_output=True, timeout=120)
                    print(f"  → Blog rebuilt")
        except KeyboardInterrupt:
            print("\n  Watch stopped.")

    return 0


if __name__ == "__main__":
    import subprocess
    sys.exit(main())
