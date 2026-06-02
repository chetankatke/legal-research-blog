"""Retranslate long deep research reports by chunking into sections."""
import json, re, urllib.request, sys, time
from pathlib import Path

BLOG_DIR = Path.home() / "legal-research-system" / "blog" / "src" / "content" / "blog"
MODEL = "MiniMax-M3"
API_BASE = "https://api.minimax.io/v1"

def get_api_key():
    for line in (Path.home() / ".hermes" / ".env").read_text().splitlines():
        if line.startswith("MINIMAX_API_KEY") and "=" in line:
            return line.split("=", 1)[1].strip()

def call_llm(prompt: str, max_tokens: int = 4000) -> str:
    api_key = get_api_key()
    payload = json.dumps({
        "model": MODEL, "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
    }).encode()
    req = urllib.request.Request(
        f"{API_BASE}/chat/completions", data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        content = json.loads(resp.read().decode())["choices"][0]["message"]["content"]
    content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
    content = re.sub(r'^```(?:[a-z]*)?\s*\n?', '', content)
    content = re.sub(r'\n?```$', '', content)
    return content.strip()

SLUG = sys.argv[1]
LANG = sys.argv[2]
LANG_NAME = {
    "mr": "Marathi (मराठी)", "hi": "Hindi (हिन्दी)", "ta": "Tamil (தமிழ்)",
    "bn": "Bengali (বাংলা)", "te": "Telugu (తెలుగు)", "kn": "Kannada (ಕನ್ನಡ)",
    "ml": "Malayalam (മലയാളം)", "gu": "Gujarati (ગુજરાતી)", "pa": "Punjabi (ਪੰਜਾਬੀ)",
}[LANG]

# Read English source
source = (BLOG_DIR / "en" / f"{SLUG}.md").read_text()
match = re.match(r'^---\s*\n(.*?)\n---\s*\n?(.*)', source, re.DOTALL)
fm_lines = match.group(1)
body = match.group(2).strip()

# Parse frontmatter
fm = {}
for line in fm_lines.splitlines():
    line = line.strip()
    if ":" in line:
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if value.startswith("[") and value.endswith("]"):
            fm[key] = [t.strip().strip('"').strip("'") for t in value[1:-1].split(",")]
        else:
            fm[key] = value

# Split by ## headings
sections = re.split(r'(?=^## )', body, flags=re.MULTILINE)
print(f"Source: {len(body):,} chars in {len(sections)} sections")

# Translate each section
translated_sections = []
for i, section in enumerate(sections):
    section = section.strip()
    if not section:
        continue
    print(f"  Section {i+1}: {len(section):,} chars...", end=" ", flush=True)
    
    prompt = (
        f"Translate the following English legal/research text into {LANG_NAME}. "
        f"Preserve ALL legal terminology, case names, citations, numbers, and proper nouns "
        f"in their original form. Keep ALL markdown formatting (headings ##, ###, bold **, "
        f"lists, --- rules) exactly as-is. This is part {i+1} of {len(sections)}. "
        f"Do NOT summarize or abbreviate — translate EVERY word. "
        f"Output ONLY the translation.\n\n{section}"
    )
    
    try:
        result = call_llm(prompt, max_tokens=4000)
        translated_sections.append(result)
        print(f"→ {len(result):,} chars ✓")
    except Exception as e:
        print(f"→ FAILED: {e}")
        # Use original as fallback
        translated_sections.append(section)
    
    time.sleep(2)

# Combine
full_translation = "\n\n".join(translated_sections)
print(f"\nTotal translation: {len(full_translation):,} chars")

# Build output
new_fm = dict(fm)
new_fm["lang"] = LANG
new_fm["title"] = fm.get("title", SLUG.replace("-", " ").title())

lines = ["---"]
for key, value in new_fm.items():
    if isinstance(value, list):
        items = ", ".join(f'"{v}"' for v in value)
        lines.append(f'{key}: [{items}]')
    elif isinstance(value, str) and (":" in value or "'" in value):
        lines.append(f'{key}: "{value}"')
    else:
        lines.append(f"{key}: {value}")
lines.append("---")
result = "\n".join(lines) + "\n\n" + full_translation

target = BLOG_DIR / LANG / f"{SLUG}.md"
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(result)
print(f"Written: {target} ({len(result):,} chars)")
