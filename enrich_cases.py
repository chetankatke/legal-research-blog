#!/usr/bin/env python3
"""enrich_cases.py — Backfill LLM summaries + holdings into existing case READMEs.

Reads metadata.json for each Cases/<slug>/, calls MiniMax if summary/holdings
are missing, and rewrites README.md + metadata.json.
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from datetime import datetime, timezone


VAULT_DEFAULT = os.path.expanduser("~/Obsidian/legal-research")
MODEL = "MiniMax-M3"
API_BASE = "https://api.minimax.io/v1"


def get_api_key() -> str | None:
    env_path = Path(os.path.expanduser("~/.hermes/.env"))
    if not env_path.exists():
        return None
    for line in env_path.read_text().splitlines():
        if line.startswith("MINIMAX_API_KEY") and "=" in line:
            return line.split("=", 1)[1].strip()
    return None


def call_llm(prompt: str, max_tokens: int = 500) -> str:
    key = get_api_key()
    if not key:
        return ""
    import urllib.request, urllib.error
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
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.loads(r.read())
            content = data["choices"][0]["message"]["content"]
            content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
            if len(content) > 20:
                return content
        except Exception:
            time.sleep(1)
    return ""


def update_readme_summary(readme_text: str, summary: str, holdings: list[str]) -> str:
    """Patch Summary and Key Holdings sections in an existing README."""
    # Replace Summary section
    if "## Summary" in readme_text:
        # Find the Summary section boundary
        sm = re.search(r"^(## Summary\n)(.*?)(\n## )", readme_text, re.DOTALL | re.MULTILINE)
        if sm:
            block = sm.group(2).strip()
            if not block or block == "_No LLM summary available. See full text below._":
                readme_text = readme_text[:sm.start(2)] + summary + readme_text[sm.end(2):]
    # Replace Key Holdings section
    if "## Key Holdings" in readme_text:
        hm = re.search(r"^(## Key Holdings\n)(.*?)(\n## )", readme_text, re.DOTALL | re.MULTILINE)
        if hm:
            block = hm.group(2).strip()
            if not block or block == "- _Not yet summarized_" or "- _Not yet summarized_" in block:
                holdings_md = "\n".join(f"- {h}" for h in holdings) if holdings else "- _Pending enriched LLM pass._"
                readme_text = readme_text[:hm.start(2)] + holdings_md + readme_text[hm.end(2):]
    return readme_text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=VAULT_DEFAULT)
    ap.add_argument("--limit", type=int, default=0, help="Max cases to enrich (0=all)")
    ap.add_argument("--delay", type=float, default=0.3, help="Seconds between API calls")
    args = ap.parse_args()

    vault = Path(args.vault).expanduser()
    cases_dir = vault / "Cases"
    if not cases_dir.exists():
        print("Cases dir not found.", file=sys.stderr)
        return 2

    case_dirs = sorted([d for d in cases_dir.iterdir() if d.is_dir()])
    if args.limit:
        case_dirs = case_dirs[:args.limit]

    enriched = 0
    skipped = 0
    failed = 0

    for idx, case in enumerate(case_dirs, 1):
        meta_path = case / "metadata.json"
        readme_path = case / "README.md"
        if not meta_path.exists() or not readme_path.exists():
            skipped += 1
            continue

        try:
            meta = json.loads(meta_path.read_text())
        except Exception:
            skipped += 1
            continue

        excerpt = (meta.get("full_text_excerpt") or "").strip()
        if len(excerpt) < 200:
            skipped += 1
            continue

        # Check if already enriched
        current_readme = readme_path.read_text()
        has_summary = "## Summary" in current_readme and "_No LLM summary_" not in current_readme
        has_holdings = "## Key Holdings" in current_readme and "_Not yet summarized_" not in current_readme
        already_done = has_summary and has_holdings
        if already_done:
            skipped += 1
            continue

        title = meta.get("case_title") or case.name.replace("-", " ").title()
        summary_prompt = (
            "Provide a concise 3-4 sentence summary of this Indian court judgment. "
            "Focus on the legal question and the court's holding.\n\n"
            f"Case: {title}\n\nText excerpt:\n{excerpt[:3500]}"
        )
        holdings_prompt = (
            "Return ONLY valid JSON (no prose, no markdown) with a key 'holdings' "
            "that is an array of 3-5 short strings, each describing one key legal holding. "
            "Each string should be one sentence.\n\n"
            f"Case: {title}\n\nText excerpt:\n{excerpt[:3500]}"
        )

        summary = call_llm(summary_prompt, max_tokens=400)
        holdings_raw = call_llm(holdings_prompt, max_tokens=500)
        holdings = []
        if holdings_raw:
            try:
                data = json.loads(holdings_raw)
                holdings = data.get("holdings", [])
            except json.JSONDecodeError:
                m = re.search(r"\{.*\}", holdings_raw, re.DOTALL)
                if m:
                    try:
                        data = json.loads(m.group(0))
                        holdings = data.get("holdings", [])
                    except Exception:
                        pass

        if not summary and not holdings:
            failed += 1
            continue

        # Update README
        if summary or holdings:
            updated = update_readme_summary(current_readme, summary, holdings)
            readme_path.write_text(updated)
            meta["summary"] = summary
            meta["holdings"] = holdings
            meta_path.write_text(json.dumps(meta, indent=2))
            enriched += 1

        # Rate-limit
        if args.delay:
            time.sleep(args.delay)

        if idx % 50 == 0:
            print(f"... enriched {idx}/{len(case_dirs)}", flush=True)

    print(f"\n=== Enrichment complete ===")
    print(f"Enriched: {enriched}")
    print(f"Skipped:  {skipped}")
    print(f"Failed:   {failed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
