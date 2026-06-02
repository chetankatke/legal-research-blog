"""post_download.py — Orchestrator for srchigh → Obsidian vault ingestion.

Usage:
  python3 post_download.py --latest                    # most recent srchigh dir
  python3 post_download.py --dir ~/myJud/scr/dk_basu/  # specific dir
  python3 post_download.py --file path/to/judgment.pdf # single file
  python3 post_download.py --latest --translate         # ingest + translate all 10 langs
  python3 post_download.py --latest --lang mr,hi        # translate to specific langs only

Behavior:
  - Finds target PDFs
  - Calls ingest_to_obsidian.py for each
  - If --translate, calls translate_to_languages.py for each ingested case
  - Prints summary table
"""
import argparse
import re
import subprocess
import sys
import os
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parent
INGEST_SCRIPT = SCRIPTS_DIR / "ingest_to_obsidian.py"
TRANSLATE_SCRIPT = SCRIPTS_DIR / "translate_to_languages.py"
PYTHON = "/usr/bin/python3"
MY_JUD = Path(os.path.expanduser("~/myJud"))


def find_latest_dir(base: Path) -> Path | None:
    """Find the most recently modified subdirectory under base/ containing PDFs."""
    candidates = sorted(base.rglob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        return None
    return candidates[0].parent


def derive_slug_from_path(pdf_path: Path) -> str | None:
    """Try to extract a meaningful slug, return None to let ingest_to_obsidian handle it."""
    name = pdf_path.stem
    # If it looks like a hash or citation number, let the ingester figure it out
    if re.match(r"^[a-f0-9]{16,}$", name, re.IGNORECASE):
        return None
    if re.match(r"^\[\d{4}\]", name):
        return None
    # Try to return something meaningful
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", name).strip("-").lower()
    if len(slug) < 5:
        return None
    return slug[:60]


def run_ingest(pdf_path: Path, slug: str | None = None) -> bool:
    """Run ingest_to_obsidian.py for a single PDF. Returns True on success."""
    cmd = [PYTHON, str(INGEST_SCRIPT), str(pdf_path)]
    if slug:
        cmd += ["--case-slug", slug]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        print(f"  ✗ Ingest failed: {pdf_path.name}", file=sys.stderr)
        print(f"    {result.stderr[:300]}", file=sys.stderr)
        return False
    print(f"  ✓ {result.stdout.strip()}")
    return True


def run_translate(slug: str, languages: list[str] | None = None) -> bool:
    """Run translate_to_languages.py for a single case slug."""
    cmd = [PYTHON, str(TRANSLATE_SCRIPT), slug]
    if languages:
        cmd += ["--languages", ",".join(languages)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        print(f"  ✗ Translation failed for {slug}", file=sys.stderr)
        print(f"    {result.stderr[:300]}", file=sys.stderr)
        return False
    print(f"  ✓ {result.stdout.strip().split(chr(10))[0]}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Post-download orchestrator for srchigh → Obsidian vault")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--latest", action="store_true", help="Process the most recent srchigh download dir")
    group.add_argument("--dir", help="Process all PDFs in a specific directory")
    group.add_argument("--file", help="Process a single PDF file")
    parser.add_argument("--translate", action="store_true", help="Also translate to languages")
    parser.add_argument("--lang", help="Comma-separated language codes (for --translate, default: all 10)")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be done without doing it")
    args = parser.parse_args()

    # Resolve target PDFs
    if args.latest:
        target = find_latest_dir(MY_JUD)
        if not target:
            print("ERROR: No srchigh downloads found under ~/myJud/", file=sys.stderr)
            return 1
        print(f"→ Latest download dir: {target}")
        pdfs = sorted(target.glob("*.pdf"))
    elif args.dir:
        target = Path(args.dir).expanduser()
        if not target.is_dir():
            print(f"ERROR: Not a directory: {target}", file=sys.stderr)
            return 1
        pdfs = sorted(target.glob("*.pdf"))
    elif args.file:
        target = Path(args.file).expanduser()
        if not target.is_file():
            print(f"ERROR: Not a file: {target}", file=sys.stderr)
            return 1
        pdfs = [target]

    if not pdfs:
        print("No PDFs found.", file=sys.stderr)
        return 1

    print(f"\nFound {len(pdfs)} PDF(s) to process:\n")
    for pdf in pdfs:
        print(f"  • {pdf.name} ({pdf.stat().st_size / 1024:.0f} KB)")

    if args.dry_run:
        print("\n[Dry run — no files written]")
        return 0

    # Ingest each PDF
    success_count = 0
    ingested_slugs = []
    for pdf in pdfs:
        slug = derive_slug_from_path(pdf)
        print(f"\n── {pdf.name} ──")
        if run_ingest(pdf, slug):
            success_count += 1
            ingested_slugs.append(slug)

    # Translate if requested
    if args.translate and ingested_slugs:
        langs = args.lang.split(",") if args.lang else None
        print(f"\n── Translating {len(ingested_slugs)} case(s) ──")
        for slug in ingested_slugs:
            run_translate(slug, langs)

    print(f"\n✔ Done. {success_count}/{len(pdfs)} PDFs ingested.")
    if ingested_slugs:
        print(f"  Cases: {', '.join(ingested_slugs)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
