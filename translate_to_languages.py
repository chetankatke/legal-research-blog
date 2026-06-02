"""translate_to_languages.py — Translate a case to multiple Indian languages.

CLI:
  translate_to_languages.py <case-slug> [--languages mr,hi,en,ta,bn,te,kn,ml,gu,pa]
                                      [--force] [--dry-run]

Behavior:
  - Reads English case at Cases/<slug>/README.md
  - For each target language: prompt MiniMax to translate
  - Write to Translations/<lang>/<slug>.md
  - Cache: skip if file exists < 30 days, unless --force
  - Sequential calls with 1s sleep between languages (be polite)
  - If one language fails, continue with others
  - Updates Indexes/Translations Index.md
  - Also updates the case's README to add wikilink back to each translation

Reuses call_llm() from translate_to_marathi.py.
"""
import argparse
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Shared LLM infrastructure
from translate_to_marathi import call_llm, get_vault, get_case_title, MODEL

VAULT_DEFAULT = os.path.expanduser("~/Obsidian/legal-research")

# Language code -> display name mapping
LANGUAGE_LABELS = {
    "mr": "मराठी",
    "hi": "हिन्दी",
    "en": "English",
    "ta": "தமிழ்",
    "bn": "বাংলা",
    "te": "తెలుగు",
    "kn": "ಕನ್ನಡ",
    "ml": "മലയാളം",
    "gu": "ગુજરાતી",
    "pa": "ਪੰਜਾਬੀ",
}

DEFAULT_LANGUAGES = ["mr", "hi", "en", "ta", "bn", "te", "kn", "ml", "gu", "pa"]


def is_cached(translation_path: Path, force: bool = False) -> bool:
    """Check if a translation exists and is fresh (< 30 days old)."""
    if force:
        return False
    if not translation_path.exists():
        return False
    age = datetime.now(timezone.utc) - datetime.fromtimestamp(
        translation_path.stat().st_mtime, tz=timezone.utc
    )
    return age < timedelta(days=30)


def translate_text(text: str, case_title: str, target_lang: str) -> str:
    """Translate the case text to the target language via MiniMax."""
    lang_name = LANGUAGE_LABELS.get(target_lang, target_lang.upper())
    prompt = (
        f"You are a legal translator. Translate the following Indian court case "
        f"from English to {lang_name} ({target_lang}). Preserve all legal terminology "
        f"accurately. Keep proper nouns (names, places, court names) in their original "
        f"form. Output only the {lang_name} translation, no commentary.\n\n"
        f"Case: {case_title}\n\n"
        f"Text:\n{text}"
    )
    return call_llm(prompt, max_tokens=500)


def compose_translation(
    slug: str, translated_text: str, case_title: str, lang: str
) -> str:
    """Build the markdown content for a translation file."""
    now = datetime.now(timezone.utc).isoformat()
    lang_name = LANGUAGE_LABELS.get(lang, lang.upper())
    return f"""---
type: translation
language: {lang}
source: Cases/{slug}/README.md
translated_at: {now}
model: {MODEL}
---

# {case_title} ({lang_name} अनुवाद)

{translated_text}

---

[[../Cases/{slug}/README|English source]]
"""


def update_translations_index(
    vault: Path, slug: str, lang: str, label: str | None = None
) -> None:
    """Append a wikilink entry to the Translations Index file."""
    idx_path = vault / "Indexes" / "Translations Index.md"
    if not idx_path.exists():
        idx_path.parent.mkdir(parents=True, exist_ok=True)
        idx_path.write_text(
            "# Translations Index\n\n_Auto-populated by translation scripts._\n\n"
        )

    content = idx_path.read_text()
    entry_line = f"Translations/{lang}/{slug}.md"
    if entry_line in content:
        return

    lang_display = label or LANGUAGE_LABELS.get(lang, lang.upper())
    case_title = get_case_title(vault, slug)
    entry = f"- [[Translations/{lang}/{slug}|{case_title} ({lang_display})]]\n"
    idx_path.write_text(content + entry)


def update_case_readme(vault: Path, slug: str, lang: str) -> None:
    """Add a wikilink from the case README to a new translation."""
    readme_path = vault / "Cases" / slug / "README.md"
    if not readme_path.exists():
        return

    content = readme_path.read_text()
    label = LANGUAGE_LABELS.get(lang, lang.upper())
    # Relative wikilink from Cases/<slug>/README.md to Translations/<lang>/<slug>.md
    link = f"[[../../Translations/{lang}/{slug}|{label} translation]]"

    # Don't add duplicates
    if link in content:
        return

    # Append to the "Related" section, or create one
    if "## Related\n" in content:
        # Insert before any trailing content after the Related section
        content = content.rstrip() + f"\n- {link}\n"
    else:
        content = content.rstrip() + f"\n\n## Related\n\n- {link}\n"

    readme_path.write_text(content)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Translate a case to multiple Indian languages."
    )
    parser.add_argument("case_slug", help="Slug of the case to translate")
    parser.add_argument(
        "--languages",
        default=",".join(DEFAULT_LANGUAGES),
        help="Comma-separated language codes (default: all 10 languages)",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Force re-translation even if cached (< 30 days old)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would be done without writing files"
    )
    args = parser.parse_args()

    vault = get_vault()
    if not vault.exists():
        print(f"ERROR: Vault path does not exist: {vault}", file=sys.stderr)
        return 3

    slug = args.case_slug
    case_path = vault / "Cases" / slug / "README.md"
    if not case_path.exists():
        print(
            f"ERROR: Case not found: Cases/{slug}/README.md",
            file=sys.stderr,
        )
        return 1

    languages = [lang.strip() for lang in args.languages.split(",") if lang.strip()]

    case_text = case_path.read_text()
    case_title = get_case_title(vault, slug)

    if args.dry_run:
        print(f"[DRY RUN] Would translate '{case_title}' to {len(languages)} languages:")
        for lang in languages:
            label = LANGUAGE_LABELS.get(lang, lang.upper())
            target = vault / "Translations" / lang / f"{slug}.md"
            cached = ""
            if is_cached(target):
                cached = " [CACHED — would skip]"
            print(f"  {lang:4s} ({label:10s}) → {target}{cached}")
        print(f"  Update: {vault / 'Indexes' / 'Translations Index.md'}")
        print(f"  Update: {case_path} (wikilinks)")
        return 0

    success_count = 0
    skip_count = 0
    fail_count = 0

    for i, lang in enumerate(languages):
        # Skip English — source is already English
        if lang == "en":
            print(f"[SKIP] en (English) — source is already in English")
            skip_count += 1
            continue

        translation_dir = vault / "Translations" / lang
        translation_path = translation_dir / f"{slug}.md"
        label = LANGUAGE_LABELS.get(lang, lang.upper())

        # Check cache
        if is_cached(translation_path, force=args.force):
            print(f"[SKIP] {lang} ({label}) — translation exists and is < 30 days old")
            skip_count += 1
            continue

        # Polite delay between API calls (skip delay before first call)
        if i > 0 and success_count > 0:
            time.sleep(1)

        # Translate
        try:
            translated = translate_text(case_text, case_title, lang)
            if not translated:
                print(
                    f"[FAIL] {lang} ({label}) — LLM returned empty response",
                    file=sys.stderr,
                )
                fail_count += 1
                continue
        except Exception as e:
            print(
                f"[FAIL] {lang} ({label}) — {e}",
                file=sys.stderr,
            )
            fail_count += 1
            continue

        # Write translation
        translation_dir.mkdir(parents=True, exist_ok=True)
        content = compose_translation(slug, translated, case_title, lang)
        translation_path.write_text(content)

        # Update index
        update_translations_index(vault, slug, lang)

        # Update case README with wikilink
        update_case_readme(vault, slug, lang)

        print(f"  ✓ {lang} ({label}) → {translation_path}")
        success_count += 1

    total = len(languages) - (1 if "en" in languages else 0)  # countable (non-English)
    print(
        f"\nDone. {success_count} translated, {skip_count} skipped, "
        f"{fail_count} failed (of {total} non-English languages)."
    )
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
