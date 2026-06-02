"""translate_all_posts.py — Translate all English blog posts to 9 Indian languages.

Reads each .md file from src/content/blog/en/, translates body + title to
each target language, preserves frontmatter, and writes to src/content/blog/{lang}/.
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BLOG_DIR = Path(os.path.expanduser("~/legal-research-system/blog/src/content/blog"))
MODEL = "MiniMax-M3"
API_BASE = "https://api.minimax.io/v1"

# Language config: all target languages (excluding English, which is source)
TARGET_LANGUAGES = {
    "mr": {"name": "Marathi", "native": "मराठी"},
    "hi": {"name": "Hindi", "native": "हिन्दी"},
    "ta": {"name": "Tamil", "native": "தமிழ்"},
    "bn": {"name": "Bengali", "native": "বাংলা"},
    "te": {"name": "Telugu", "native": "తెలుగు"},
    "kn": {"name": "Kannada", "native": "ಕನ್ನಡ"},
    "ml": {"name": "Malayalam", "native": "മലയാളം"},
    "gu": {"name": "Gujarati", "native": "ગુજરાતી"},
    "pa": {"name": "Punjabi", "native": "ਪੰਜਾਬੀ"},
}


def get_api_key() -> str | None:
    """Read MINIMAX_API_KEY from ~/.hermes/.env."""
    env_path = Path(os.path.expanduser("~/.hermes/.env"))
    if not env_path.exists():
        return None
    for line in env_path.read_text().splitlines():
        if line.startswith("MINIMAX_API_KEY") and "=" in line:
            return line.split("=", 1)[1].strip()
    return None


def call_llm(prompt: str, max_tokens: int = 4000) -> str:
    """Call MiniMax API and return the assistant content."""
    api_key = get_api_key()
    if not api_key:
        raise RuntimeError("MINIMAX_API_KEY not found in ~/.hermes/.env")

    payload = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
    }).encode()

    req = urllib.request.Request(
        f"{API_BASE}/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode())
            content = data["choices"][0]["message"]["content"]
    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError,
            KeyError, IndexError) as e:
        raise RuntimeError(f"API call failed: {e}") from e

    # Strip <think> blocks (MiniMax sometimes emits them)
    content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
    # Strip markdown code block fences if present
    content = re.sub(r'^```(?:json|markdown)?\s*\n?', '', content)
    content = re.sub(r'\n?```$', '', content)
    return content.strip()


def parse_frontmatter(text: str):
    """Parse YAML frontmatter from a markdown file. Returns (frontmatter_dict, body)."""
    match = re.match(r'^---\s*\n(.*?)\n---\s*\n?(.*)', text, re.DOTALL)
    if not match:
        return {}, text

    # Simple line-based YAML parsing (no nested structures, just key: value)
    fm = {}
    for line in match.group(1).splitlines():
        line = line.strip()
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            # Handle arrays: [tag1, tag2]
            if value.startswith("[") and value.endswith("]"):
                fm[key] = [t.strip().strip('"').strip("'") for t in value[1:-1].split(",")]
            else:
                fm[key] = value
    return fm, match.group(2).strip()


def compose_frontmatter(fm: dict) -> str:
    """Write frontmatter dict back to YAML string."""
    lines = ["---"]
    for key, value in fm.items():
        if isinstance(value, list):
            items = ", ".join(f'"{v}"' for v in value)
            lines.append(f'{key}: [{items}]')
        elif isinstance(value, str) and ("\n" in value or ":" in value or "#" in value):
            lines.append(f'{key}: "{value}"')
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)


def translate_text(text: str, source_lang: str, target_lang: str, target_native: str) -> str:
    """Translate text to the target language via MiniMax."""
    prompt = (
        f"Translate the following {source_lang} text accurately into {target_lang} "
        f"({target_native}). This is legal/research content about Indian Supreme Court "
        f"judgments. Preserve all legal terminology, case names, article references, "
        f"and proper nouns (names, places, court names) in their original form. "
        f"Keep markdown formatting (headings, bold, lists, links) intact. "
        f"Output ONLY the translation, no commentary or explanations.\n\n"
        f"TEXT:\n{text}"
    )
    return call_llm(prompt, max_tokens=4000)


def needs_translation(blog_dir: Path, slug: str, lang: str) -> bool:
    """Check if a translation already exists."""
    target = blog_dir / lang / f"{slug}.md"
    return not target.exists()


def translate_post(slug: str, lang: str, lang_info: dict) -> bool:
    """Translate a single English post to one target language. Returns True on success."""
    source_path = BLOG_DIR / "en" / f"{slug}.md"
    if not source_path.exists():
        print(f"[SKIP] Source not found: en/{slug}.md")
        return False

    target_path = BLOG_DIR / lang / f"{slug}.md"
    text = source_path.read_text()

    # Parse frontmatter
    fm, body = parse_frontmatter(text)
    if not body:
        print(f"[SKIP] {lang}/{slug}.md — no body content found")
        return False

    source_title = fm.get("title", slug.replace("-", " ").title())
    source_desc = fm.get("description", "")

    # Translate title
    try:
        title_prompt = (
            f"Translate this English blog post title into {lang_info['name']} "
            f"({lang_info['native']}). Keep proper nouns (case names, legal terms) "
            f"as-is. Output ONLY the translation, no quotes or commentary.\n\n"
            f"Title: {source_title}"
        )
        translated_title = call_llm(title_prompt, max_tokens=200)
        if not translated_title:
            translated_title = source_title
    except Exception as e:
        print(f"  [WARN] Title translation failed: {e}")
        translated_title = source_title

    # Translate description
    try:
        if source_desc:
            desc_prompt = (
                f"Translate this English blog post description/summary into "
                f"{lang_info['name']} ({lang_info['native']}). Keep proper nouns as-is. "
                f"Output ONLY the translation.\n\nDescription: {source_desc}"
            )
            translated_desc = call_llm(desc_prompt, max_tokens=200)
            if not translated_desc:
                translated_desc = source_desc
        else:
            translated_desc = ""
    except Exception:
        translated_desc = source_desc

    # Translate body
    try:
        print(f"  Translating body ({len(body)} chars)...")
        translated_body = translate_text(body, "English", lang_info["name"], lang_info["native"])
        if not translated_body:
            print(f"  [FAIL] {lang}/{slug}.md — empty translation")
            return False
    except Exception as e:
        print(f"  [FAIL] {lang}/{slug}.md — {e}")
        return False

    # Compose new frontmatter
    new_fm = dict(fm)
    new_fm["title"] = translated_title
    new_fm["lang"] = lang
    if translated_desc:
        new_fm["description"] = translated_desc
    # Wrap title in quotes if it contains special chars
    if ":" in new_fm.get("title", "") or "'" in new_fm.get("title", ""):
        new_fm["title"] = f'"{new_fm["title"]}"'
    if ":" in new_fm.get("description", "") or "'" in new_fm.get("description", ""):
        new_fm["description"] = f'"{new_fm["description"]}"'

    # For non-research posts, ensure caseSlug is preserved
    if "caseSlug" in fm:
        new_fm["caseSlug"] = fm["caseSlug"]

    result = compose_frontmatter(new_fm) + "\n\n" + translated_body

    # Write
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(result)
    print(f"  ✓ {lang}/{slug}.md ({len(translated_body)} chars)")
    return True


def main():
    # Discover English source posts
    en_dir = BLOG_DIR / "en"
    if not en_dir.exists():
        print(f"ERROR: {en_dir} does not exist")
        return 1

    source_posts = sorted(en_dir.glob("*.md"))
    print(f"Found {len(source_posts)} English source posts:\n")
    for post in source_posts:
        print(f"  - en/{post.name}")

    # Determine what needs translating
    total = 0
    success = 0
    skipped = 0
    failed = 0

    for post in source_posts:
        slug = post.stem
        fm, _ = parse_frontmatter(post.read_text())
        title = fm.get("title", slug)
        print(f"\n{'='*60}")
        print(f"Source: {title}")
        print(f"{'='*60}\n")

        for lang, lang_info in TARGET_LANGUAGES.items():
            if not needs_translation(BLOG_DIR, slug, lang):
                print(f"[SKIP] {lang}/{slug}.md — already exists")
                skipped += 1
                continue

            total += 1
            target_path = BLOG_DIR / lang / f"{slug}.md"
            print(f"[{lang}] {lang_info['name']} ({lang_info['native']}) → {target_path}")

            if translate_post(slug, lang, lang_info):
                success += 1
            else:
                failed += 1

            # Polite delay between API calls
            time.sleep(1.5)

    print(f"\n{'='*60}")
    print(f"Done. {success} translated, {skipped} skipped, {failed} failed (of {total + skipped} total).")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
