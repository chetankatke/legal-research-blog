"""Batch translate one post to remaining languages - run as background process."""
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

LANG_INFO = {
    "mr": "मराठी", "hi": "हिन्दी", "ta": "தமிழ்", "bn": "বাংলা",
    "te": "తెలుగు", "kn": "ಕನ್ನಡ", "ml": "മലയാളം", "gu": "ગુજરાતી", "pa": "ਪੰਜਾਬੀ",
}

SLUG = sys.argv[1] if len(sys.argv) > 1 else ""
TARGETS = sys.argv[2].split(",") if len(sys.argv) > 2 else []

def get_api_key():
    for line in Path(os.path.expanduser("~/.hermes/.env")).read_text().splitlines():
        if line.startswith("MINIMAX_API_KEY") and "=" in line:
            return line.split("=", 1)[1].strip()
    return None

def call_llm(prompt: str, max_tokens: int = 4000) -> str:
    api_key = get_api_key()
    payload = json.dumps({"model": MODEL, "messages": [{"role": "user", "content": prompt}],
                          "max_tokens": max_tokens}).encode()
    req = urllib.request.Request(
        f"{API_BASE}/chat/completions", data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        content = json.loads(resp.read().decode())["choices"][0]["message"]["content"]
    content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
    content = re.sub(r'^```(?:json|markdown)?\s*\n?', '', content)
    content = re.sub(r'\n?```$', '', content)
    return content.strip()

def parse_frontmatter(text: str):
    match = re.match(r'^---\s*\n(.*?)\n---\s*\n?(.*)', text, re.DOTALL)
    if not match:
        return {}, text
    fm = {}
    for line in match.group(1).splitlines():
        line = line.strip()
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if value.startswith("[") and value.endswith("]"):
                fm[key] = [t.strip().strip('"').strip("'") for t in value[1:-1].split(",")]
            else:
                fm[key] = value
    return fm, match.group(2).strip()

def compose_frontmatter(fm: dict) -> str:
    lines = ["---"]
    for key, value in fm.items():
        if isinstance(value, list):
            items = ", ".join(f'"{v}"' for v in value)
            lines.append(f'{key}: [{items}]')
        elif isinstance(value, str) and (":" in value or "'" in value):
            lines.append(f'{key}: "{value}"')
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)

source_path = BLOG_DIR / "en" / f"{SLUG}.md"
if not source_path.exists():
    print(f"ERROR: Source not found: en/{SLUG}.md")
    sys.exit(1)

text = source_path.read_text()
fm, body = parse_frontmatter(text)
source_title = fm.get("title", SLUG.replace("-", " ").title())
source_desc = fm.get("description", "")

success = 0
fail = 0
skip = 0

for lang_code, native_name in LANG_INFO.items():
    if lang_code not in TARGETS:
        continue
    target_path = BLOG_DIR / lang_code / f"{SLUG}.md"
    if target_path.exists():
        print(f"[SKIP] {lang_code}/{SLUG}.md — already exists")
        skip += 1
        continue

    print(f"[{lang_code}] Translating {SLUG} to {native_name}...", flush=True)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        # Title
        title_prompt = (
            f"Translate this English blog post title into {native_name} ({lang_code}). "
            f"Keep proper nouns (case names, legal terms) as-is. "
            f"Output ONLY the translation.\n\nTitle: {source_title}"
        )
        translated_title = call_llm(title_prompt, max_tokens=200)
        if not translated_title:
            translated_title = source_title

        # Body
        body_prompt = (
            f"Translate the following {native_name} ({lang_code}). "
            f"This is legal/research content about Indian Supreme Court judgments. "
            f"Preserve all legal terminology, proper nouns, case names, article references "
            f"in their original form. Keep markdown formatting (headings, bold, lists) intact. "
            f"Output ONLY the translation.\n\nTEXT:\n{body}"
        )
        translated_body = call_llm(body_prompt, max_tokens=4000)
        if not translated_body:
            print(f"  [FAIL] {lang_code} — empty translation")
            fail += 1
            time.sleep(2)
            continue

        # Description
        translated_desc = source_desc
        if source_desc:
            desc_prompt = (
                f"Translate this English description into {native_name} ({lang_code}). "
                f"Keep proper nouns as-is. Output ONLY the translation.\n\n{source_desc}"
            )
            translated_desc = call_llm(desc_prompt, max_tokens=200)
            if not translated_desc:
                translated_desc = source_desc

        new_fm = dict(fm)
        new_fm["title"] = translated_title
        new_fm["lang"] = lang_code
        new_fm["description"] = translated_desc
        if "caseSlug" in fm:
            new_fm["caseSlug"] = fm["caseSlug"]

        result = compose_frontmatter(new_fm) + "\n\n" + translated_body
        target_path.write_text(result)
        print(f"  ✓ {lang_code}/{SLUG}.md ({len(translated_body)} chars)", flush=True)
        success += 1
    except Exception as e:
        print(f"  [FAIL] {lang_code} — {e}", flush=True)
        fail += 1

    time.sleep(2)  # polite delay

print(f"\nDone: {success} OK, {skip} skip, {fail} fail", flush=True)
sys.exit(0 if fail == 0 else 1)
