#!/usr/bin/env python3
"""Translate D.K. Basu case to Punjabi and write to blog content."""
import json, re, urllib.request, sys
from pathlib import Path

BLOG_DIR = Path.home() / "legal-research-system" / "blog" / "src" / "content" / "blog"

# Read API key
env_path = Path.home() / ".hermes" / ".env"
api_key = None
for line in env_path.read_text().splitlines():
    if line.startswith("MINIMAX_API_KEY") and "=" in line:
        api_key = line.split("=", 1)[1].strip()
        break

# Read English source
text = (BLOG_DIR / "en" / "case-dk-basu-1996.md").read_text()
match = re.match(r'^---\s*\n(.*?)\n---\s*\n?(.*)', text, re.DOTALL)
fm_lines = match.group(1) if match else ""
body = match.group(2).strip() if match else text

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

# Translate to Punjabi
prompt = (
    "Translate the following English legal case text into Punjabi (ਪੰਜਾਬੀ). "
    "Use Gurmukhi (ਗੁਰਮੁਖੀ) script ONLY. Preserve legal terminology, case names, "
    "citations, and proper nouns exactly as-is. Keep markdown formatting. "
    "Output ONLY the translation without any commentary.\n\n" + body
)

payload = json.dumps({
    "model": "MiniMax-M3",
    "messages": [{"role": "user", "content": prompt}],
    "max_tokens": 4000,
}).encode()

req = urllib.request.Request(
    "https://api.minimax.io/v1/chat/completions", data=payload,
    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=180) as resp:
    data = json.loads(resp.read().decode())
content = data["choices"][0]["message"]["content"]

# Clean
content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
content = re.sub(r'^```(?:[a-z]*)?\s*\n?', '', content)
content = re.sub(r'\n?```$', '', content)
content = content.strip()

# Check Gurmukhi
has_gurmukhi = bool(re.search(r'[\u0A00-\u0A7F]', content))
print(f"Translation length: {len(content)} chars")
print(f"Contains Gurmukhi: {has_gurmukhi}")

if not has_gurmukhi or len(content) < 100:
    print(f"ERROR: Translation appears invalid")
    print(f"Content: {content[:200]}")
    sys.exit(1)

# Build new frontmatter
new_fm = dict(fm)
new_fm["lang"] = "pa"
new_fm["title"] = fm.get("title", "Case")

result = "---\n"
for key, value in new_fm.items():
    if isinstance(value, list):
        items = ", ".join(f'"{v}"' for v in value)
        result += f'{key}: [{items}]\n'
    elif isinstance(value, str) and (":" in value or "'" in value):
        result += f'{key}: "{value}"\n'
    else:
        result += f"{key}: {value}\n"
result += "---\n\n" + content

# Write
target = BLOG_DIR / "pa" / "case-dk-basu-1996.md"
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(result)
print(f"Written: {target}")
print(f"Total size: {len(result)} chars")
sys.exit(0)
