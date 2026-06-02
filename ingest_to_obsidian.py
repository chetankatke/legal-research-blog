"""ingest_to_obsidian.py — Ingest a srchigh-downloaded judgment into the Obsidian vault.

Usage:
  python3 ingest_to_obsidian.py <pdf_path> [--case-slug SLUG] [--language en] [--dry-run]

Examples:
  python3 ingest_to_obsidian.py ~/myJud/scr/dk_basu/judgment_bb62e8d8973ab277.pdf
  python3 ingest_to_obsidian.py /path/to/judgment.pdf --case-slug dk-basu-1996 --dry-run

Behavior:
  1. Extract text from PDF (pypdf)
  2. Extract metadata heuristically (case title, court, date, judges, citation)
  3. Optionally call MiniMax API for summary + key holdings (best-effort)
  4. Write Cases/<slug>/README.md and metadata.json
  5. Update Indexes/Cases Index.md with a wikilink

Environment:
  OBSIDIAN_VAULT_PATH  — path to vault (default: ~/Obsidian/legal-research)
  MINIMAX_API_KEY      — for LLM summarization (optional)
  MINIMAX_OFFLINE=1    — skip LLM calls (used by tests)
"""
import argparse
import json
import os
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
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
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
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


def extract_pdf_text(pdf_path: Path) -> str:
    """Extract text from a PDF using PyMuPDF (fitz). Returns "" on failure."""
    try:
        import fitz
    except ImportError:
        return ""
    try:
        doc = fitz.open(str(pdf_path))
        return "\n".join(page.get_text() or "" for page in doc)
    except Exception:
        return ""


def extract_metadata(pdf_path: Path, full_text: str) -> dict:
    """Heuristically extract case metadata from the first page of text."""
    # Use first ~3000 chars to find the title (it's usually on the first page)
    first_page = full_text[:3000] if full_text else ""

    # Case title: look for the first line that looks like a case caption
    # Patterns: "X v. Y", "X vs Y", "X Vs Y"
    case_title = ""
    title_m = re.search(r"([A-Z][A-Za-z.\s&,'-]{3,80}?\s+v[s\.]?\.?\s+[A-Z][A-Za-z.\s&,'-]{3,80})", first_page)
    if title_m:
        case_title = title_m.group(1).strip()
        # Clean up: collapse multiple spaces
        case_title = re.sub(r"\s+", " ", case_title)
        # Trim trailing punctuation
        case_title = case_title.rstrip(",.;")

    # Court
    court = ""
    if re.search(r"Supreme\s+Court\s+of\s+India", first_page, re.IGNORECASE):
        court = "Supreme Court of India"
    else:
        hc_m = re.search(r"High\s+Court\s+of\s+([A-Za-z\s&]+?)(?:\s+at\s+|\s*,|\s*$|\n)", first_page, re.IGNORECASE)
        if hc_m:
            court = f"High Court of {hc_m.group(1).strip()}"

    # Date — look for "DD Month YYYY" or "Month DD, YYYY"
    date = ""
    date_patterns = [
        r"\b(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})\b",
        r"\b((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4})\b",
        r"\b(\d{1,2}[-/.]\d{1,2}[-/.]\d{4})\b",
    ]
    for pat in date_patterns:
        date_m = re.search(pat, first_page)
        if date_m:
            date = date_m.group(1)
            break

    # Judges — multiple patterns to handle different PDF formats
    judges = []
    judge_patterns = [
        # Pattern 1: "[NAME1 AND NAME2, JJ.]" (SCR / Indian format)
        r"\[([A-Z][A-Z\.\s,'-]{2,80}?(?:AND|,)\s*[A-Z][A-Z\.\s,'-]{2,80}?),\s*JJ\.?\s*\]",
        # Pattern 2: "JUSTICE [NAME]"
        r"(?:HON'?BLE\s+)?JUSTICE\s+([A-Z][A-Z\.\s,'-]{2,50}?)(?:\s*[,;.]|\s+and\s+|\s*$|\n)",
        # Pattern 3: Bench header like "[AFTAB ALAM AND R.M. LODHA, JJ.]"
        r"\[([A-Z][A-Z\.\s,'-]{2,80}?),\s*JJ\.?\s*\]",
    ]
    for pat in judge_patterns:
        for jm in re.finditer(pat, first_page, re.MULTILINE):
            full = jm.group(1).strip()
            # Split "NAME1 AND NAME2" or "NAME1, NAME2"
            parts = re.split(r"\s+AND\s+|\s*,\s*", full)
            for p in parts:
                p = re.sub(r"\s+", " ", p).strip().rstrip(".,;")
                # Filter out short or non-name tokens
                if len(p) >= 3 and not re.match(r"^(JJ|JJ\.|DR|DR\.|HON|HON\.)$", p, re.IGNORECASE):
                    if p not in judges:
                        judges.append(p)
        if judges:
            break  # use the first pattern that matched
    judges = judges[:10]

    # Citation — look for [YYYY] N S.C.R. P or AIR YYYY SC N
    citation = ""
    cit_m = re.search(r"\[(\d{4})\]\s*(\d+)\s+S\.?C\.?R\.?\s+(\d+)", full_text)
    if cit_m:
        citation = f"[{cit_m.group(1)}] {cit_m.group(2)} S.C.R. {cit_m.group(3)}"

    return {
        "case_title": case_title,
        "court": court,
        "date": date,
        "judges": judges,
        "citation": citation,
    }


def derive_slug(pdf_path: Path, explicit: str | None) -> str:
    """Derive a case slug from the PDF filename or use the explicit one."""
    if explicit:
        return explicit
    # Strip extension, take basename
    name = pdf_path.stem
    # Lowercase, replace non-alphanumeric with hyphen, collapse
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", name).strip("-").lower()
    # Trim to reasonable length
    return slug[:60] or "untitled-case"


def unique_slug(cases_dir: Path, base: str) -> str:
    """If Cases/<base>/ exists, append -2, -3, etc."""
    candidate = base
    n = 2
    while (cases_dir / candidate).exists():
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def summarize_with_llm(case_title: str, full_text: str) -> dict:
    """Use MiniMax to produce a 200-word summary + 3-7 key holdings."""
    excerpt = full_text[:4000] if full_text else ""
    if not excerpt:
        return {"summary": "", "holdings": []}
    summary_prompt = (
        f"Summarize this Indian court judgment in 200 words or less. "
        f"Be specific about what the court held and why it matters.\n\n"
        f"Case: {case_title}\n\nText excerpt:\n{excerpt}"
    )
    summary = call_llm(summary_prompt, max_tokens=400)

    holdings_prompt = (
        f"Return ONLY valid JSON (no prose, no markdown) with a key 'holdings' "
        f"that is an array of 3-5 short strings, each describing one key legal "
        f"holding from this Indian court judgment. Each string should be one sentence.\n\n"
        f"Case: {case_title}\n\nText excerpt:\n{excerpt}"
    )
    holdings_raw = call_llm(holdings_prompt, max_tokens=500)
    holdings = []
    if holdings_raw:
        # Try to parse JSON; if it fails, try to extract a JSON block
        try:
            data = json.loads(holdings_raw)
            holdings = data.get("holdings", [])
        except json.JSONDecodeError:
            json_m = re.search(r"\{.*\}", holdings_raw, re.DOTALL)
            if json_m:
                try:
                    data = json.loads(json_m.group(0))
                    holdings = data.get("holdings", [])
                except json.JSONDecodeError:
                    pass

    return {"summary": summary, "holdings": holdings}


def compose_readme(slug: str, metadata: dict, summary: str, holdings: list,
                   source_pdf: Path, language: str) -> str:
    """Build the markdown content for the case README."""
    ingested_at = datetime.now(timezone.utc).isoformat()
    case_title = metadata.get("case_title") or slug.replace("-", " ").title()
    court = metadata.get("court", "Unknown")
    date = metadata.get("date", "Unknown")
    judges = metadata.get("judges", [])
    citation = metadata.get("citation", "Unknown")

    holdings_md = "\n".join(f"- {h}" for h in holdings) if holdings else "- _Not yet summarized_"
    judges_md = ", ".join(judges) if judges else "_Unknown_"

    return f"""---
type: case
citation: {citation}
court: {court}
date: {date}
judges: [{", ".join(judges)}]
tags: []
language: {language}
source_pdf: {source_pdf}
ingested_at: {ingested_at}
slug: {slug}
---

# {case_title}

## Citation
- **Court:** {court}
- **Date:** {date}
- **Judges:** {judges_md}
- **Citation:** {citation}

## Summary

{summary or "_No LLM summary available. See full text below._"}

## Key Holdings

{holdings_md}

## Full Text

_See PDF: [{source_pdf.name}]({source_pdf})_

<details>
<summary>Click to expand raw text excerpt</summary>

{metadata.get("full_text_excerpt", "_empty_")}

</details>

## Related

- [[../../Indexes/Cases Index|Back to Cases Index]]
- [[../../Translations/mr/{slug}|मराठी अनुवाद (Marathi)]]

## Metadata

```json
{json.dumps({"citation": citation, "court": court, "date": date, "judges": judges, "source_pdf": str(source_pdf)}, indent=2)}
```
"""


def update_cases_index(vault: Path, slug: str, case_title: str, court: str, date: str) -> None:
    """Append a wikilink entry to the Cases Index file."""
    idx_path = vault / "Indexes" / "Cases Index.md"
    if not idx_path.exists():
        idx_path.parent.mkdir(parents=True, exist_ok=True)
        idx_path.write_text("# Cases Index\n\n_Auto-populated by `ingest_to_obsidian.py`._\n\n")

    content = idx_path.read_text()
    # Skip if already indexed
    if f"Cases/{slug}/" in content:
        return
    entry = f"- [[Cases/{slug}/README|{case_title}]] — {court} ({date})\n"
    idx_path.write_text(content + entry)


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest a PDF judgment into the Obsidian vault.")
    parser.add_argument("pdf_path", help="Path to the judgment PDF")
    parser.add_argument("--case-slug", help="Override the auto-derived case slug")
    parser.add_argument("--language", default="en", help="Primary language of the note (default: en)")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be done without writing files")
    args = parser.parse_args()

    pdf_path = Path(args.pdf_path).expanduser()
    if not pdf_path.exists():
        print(f"ERROR: PDF not found: {pdf_path}", file=sys.stderr)
        return 2

    vault = get_vault()
    if not vault.exists():
        print(f"ERROR: Vault path does not exist: {vault}", file=sys.stderr)
        print("Set OBSIDIAN_VAULT_PATH or create the vault first.", file=sys.stderr)
        return 3

    # Extract
    full_text = extract_pdf_text(pdf_path)
    metadata = extract_metadata(pdf_path, full_text)
    # Add an excerpt for the raw text section
    metadata["full_text_excerpt"] = full_text[:2000]

    # Derive slug
    base_slug = derive_slug(pdf_path, args.case_slug)
    case_dir = vault / "Cases"
    case_dir.mkdir(parents=True, exist_ok=True)
    slug = unique_slug(case_dir, base_slug)

    # LLM summary (best-effort)
    llm_out = {"summary": "", "holdings": []}
    if not args.dry_run:
        llm_out = summarize_with_llm(metadata.get("case_title") or slug, full_text)

    # Compose
    readme = compose_readme(slug, metadata, llm_out["summary"], llm_out["holdings"],
                            pdf_path, args.language)
    sidecar = {
        "case_title": metadata.get("case_title"),
        "citation": metadata.get("citation"),
        "court": metadata.get("court"),
        "date": metadata.get("date"),
        "judges": metadata.get("judges"),
        "source_pdf": str(pdf_path),
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "language": args.language,
        "slug": slug,
    }

    if args.dry_run:
        print(f"[DRY RUN] Would create:")
        print(f"  {case_dir / slug / 'README.md'}")
        print(f"  {case_dir / slug / 'metadata.json'}")
        print(f"  Update: {vault / 'Indexes' / 'Cases Index.md'}")
        print(f"")
        print(f"Case title: {metadata.get('case_title') or '(not detected)'}")
        print(f"Court: {metadata.get('court') or '(not detected)'}")
        print(f"Date: {metadata.get('date') or '(not detected)'}")
        print(f"Judges: {metadata.get('judges') or '(not detected)'}")
        print(f"Citation: {metadata.get('citation') or '(not detected)'}")
        print(f"Slug: {slug}")
        return 0

    # Write
    out_dir = case_dir / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "README.md").write_text(readme)
    (out_dir / "metadata.json").write_text(json.dumps(sidecar, indent=2))
    update_cases_index(vault, slug, metadata.get("case_title") or slug,
                       metadata.get("court") or "Unknown",
                       metadata.get("date") or "Unknown")

    # Summary
    title = metadata.get("case_title") or slug
    print(f"✓ Ingested: {title}")
    print(f"  → {out_dir / 'README.md'}")
    print(f"  → {out_dir / 'metadata.json'}")
    print(f"  Slug: {slug}")
    if llm_out["summary"]:
        print(f"  Summary: {llm_out['summary'][:80]}...")
    if llm_out["holdings"]:
        print(f"  Holdings: {len(llm_out['holdings'])} items")
    return 0


if __name__ == "__main__":
    sys.exit(main())
