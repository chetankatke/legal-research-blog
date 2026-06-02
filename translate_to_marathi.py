"""translate_to_marathi.py — Translate a case to Marathi.

CLI:
  translate_to_marathi.py <case-slug> [--force] [--dry-run]

Behavior:
  - Reads OBSIDIAN_VAULT_PATH env var (default ~/Obsidian/legal-research/)
  - Reads Case from Cases/<slug>/README.md
  - Translates to Marathi via MiniMax-M3
  - Writes to Translations/mr/<slug>.md with frontmatter
  - Adds wikilink [[../Cases/<slug>/README|English source]] at bottom
  - Skips if Translations/mr/<slug>.md exists and is < 30 days old, unless --force
  - Updates Indexes/Translations Index.md

call_llm(prompt, max_tokens=500) is a top-level importable function.
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

VAULT_DEFAULT = os.path.expanduser("~/Obsidian/legal-research")
MODEL = "MiniMax-M3"
API_BASE = "https://api.minimax.io/v1"


def get_vault() -> Path:
    """Resolve the vault path from env or default."""
    return Path(os.environ.get("OBSIDIAN_VAULT_PATH", VAULT_DEFAULT)).expanduser()


def get_api_key() -> str | None:
    """Read MINIMAX_API_KEY from ~/.hermes/.env."""
    env_path = Path(os.path.expanduser("~/.hermes/.env"))
    if not env_path.exists():
        return None
    for line in env_path.read_text().splitlines():
        if line.startswith("MINIMAX_API_KEY") and "=" in line:
            return line.split("=", 1)[1].strip()
    return None


def call_llm(prompt: str, max_tokens: int = 500) -> str:
    """Call MiniMax API and return the assistant content (without thinking block)."""
    if os.environ.get("MINIMAX_OFFLINE") == "1":
        return ""
    key = get_api_key()
    if not key:
        return ""
    req = urllib.request.Request(
        f"{API_BASE}/chat/completions",
        data=json.dumps({
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
        }).encode(),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
        content = data["choices"][0]["message"]["content"]
        # Strip <think>...</think> block (MiniMax-M3 emits reasoning before the answer)
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
        return content
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, json.JSONDecodeError):
        return ""


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


def get_case_title(vault: Path, slug: str) -> str:
    """Get the case title from metadata.json, falling back to slug."""
    meta_path = vault / "Cases" / slug / "metadata.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
            return meta.get("case_title", slug.replace("-", " ").title())
        except (json.JSONDecodeError, OSError):
            pass
    return slug.replace("-", " ").title()


def translate_text(text: str, case_title: str) -> str:
    """Translate the case text to Marathi via MiniMax."""
    prompt = (
        "You are a legal translator. Translate the following Indian court case "
        "from English to Marathi. Preserve all legal terminology accurately. "
        "Keep proper nouns (names, places, court names) in their original form. "
        "Output only the Marathi translation, no commentary.\n\n"
        f"Case: {case_title}\n\n"
        f"Text:\n{text}"
    )
    return call_llm(prompt, max_tokens=500)


def compose_translation(slug: str, translated_text: str, case_title: str) -> str:
    """Build the markdown content for the translation file."""
    now = datetime.now(timezone.utc).isoformat()
    return f"""---
type: translation
language: mr
source: Cases/{slug}/README.md
translated_at: {now}
model: {MODEL}
---

# {case_title} (मराठी अनुवाद)

{translated_text}

---

[[../Cases/{slug}/README|English source]]
"""


def update_translations_index(vault: Path, slug: str, lang: str, label: str | None = None) -> None:
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

    lang_display = label or lang.upper()
    case_title = get_case_title(vault, slug)
    entry = f"- [[Translations/{lang}/{slug}|{case_title} ({lang_display})]]\n"
    idx_path.write_text(content + entry)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Translate a case's README to Marathi."
    )
    parser.add_argument("case_slug", help="Slug of the case to translate")
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

    translation_dir = vault / "Translations" / "mr"
    translation_path = translation_dir / f"{slug}.md"

    # Check cache
    if is_cached(translation_path, force=args.force):
        print(
            f"[SKIP] {translation_path} exists and is < 30 days old. "
            "Use --force to re-translate."
        )
        return 0

    case_text = case_path.read_text()
    case_title = get_case_title(vault, slug)

    if args.dry_run:
        print(f"[DRY RUN] Would translate '{case_title}' to Marathi")
        print(f"  Source: {case_path}")
        print(f"  Target: {translation_path}")
        print(f"  Update: {vault / 'Indexes' / 'Translations Index.md'}")
        return 0

    # Translate
    translated = translate_text(case_text, case_title)

    # Write translation
    translation_dir.mkdir(parents=True, exist_ok=True)
    content = compose_translation(slug, translated, case_title)
    translation_path.write_text(content)

    # Update index
    update_translations_index(vault, slug, "mr", "मराठी")

    print(f"✓ Translated '{case_title}' to Marathi")
    print(f"  → {translation_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
