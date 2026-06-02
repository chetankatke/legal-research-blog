#!/usr/bin/env python3
"""
Run deep-research CLI wrapper.

Usage:
    run_deep_research.py "<research question>" [--case SLUG] [--breadth 4] [--depth 2] [--dry-run]
"""

import argparse
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# --- Paths ---
DEEP_RESEARCH_DIR = Path(os.path.expanduser("~/legal-research-system/deep-research"))
OBSIDIAN_RESEARCH_DIR = Path(os.path.expanduser("~/Obsidian/legal-research/Research"))
OBSIDIAN_INDEX_DIR = Path(os.path.expanduser("~/Obsidian/legal-research/Indexes"))
OBSIDIAN_INDEX_FILE = OBSIDIAN_INDEX_DIR / "Research Index.md"

RESEARCH_TIMEOUT = 300  # 5 minutes

# --- Helpers ---


def slugify(text: str) -> str:
    """Convert text to a URL-friendly slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "-", text)
    return text[:80].rstrip("-")


def log(msg: str):
    print(f"[run_deep_research] {msg}", file=sys.stderr)


def run_research(question: str, breadth: int, depth: int) -> tuple[bool, str]:
    """
    Run deep-research via `npm run cli` with env vars.
    Returns (success, report_content).
    """
    env = os.environ.copy()
    env["QUERY"] = question
    env["BREADTH"] = str(breadth)
    env["DEPTH"] = str(depth)
    env["TYPE"] = "report"

    cmd = ["npm", "run", "cli"]
    log(f"Running: cd {DEEP_RESEARCH_DIR} && npm run cli")
    log(f"  question: {question[:80]}...")
    log(f"  breadth: {breadth}, depth: {depth}")

    start = time.time()
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(DEEP_RESEARCH_DIR),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        stdout, stderr = proc.communicate(timeout=RESEARCH_TIMEOUT)
        elapsed = time.time() - start
        log(f"Process completed in {elapsed:.1f}s (exit code: {proc.returncode})")

        if proc.returncode != 0:
            log(f"STDERR:\n{stderr[:2000]}")
            return False, f"Process exited with code {proc.returncode}\n\nSTDERR:\n{stderr[:2000]}"

        # Log stderr (useful for debugging)
        if stderr.strip():
            log(f"STDERR:\n{stderr[:1000]}")

        # Try to read report.md or answer.md
        report_content = ""
        for fname in ["report.md", "answer.md"]:
            fpath = DEEP_RESEARCH_DIR / fname
            if fpath.exists():
                report_content = fpath.read_text(encoding="utf-8")
                log(f"Read {fname} ({len(report_content)} chars)")
                break

        if not report_content:
            log(f"No report.md or answer.md found. STDOUT:\n{stdout[:2000]}")
            return False, stdout[:2000] if stdout.strip() else "No output produced"

        return True, report_content

    except subprocess.TimeoutExpired:
        elapsed = time.time() - start
        log(f"Process TIMED OUT after {elapsed:.1f}s")
        return False, f"Research timed out after {RESEARCH_TIMEOUT}s"
    except Exception as e:
        log(f"Error: {e}")
        return False, f"Error: {e}"


def write_obsidian_note(
    question: str,
    content: str,
    slug: str,
    case_slug: str | None,
) -> str:
    """
    Write research result to Obsidian.
    Returns the output file path.
    """
    OBSIDIAN_RESEARCH_DIR.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc).isoformat()

    tags = ["research", "deep-research"]
    if case_slug:
        tags.append(f"case/{case_slug}")

    # Build frontmatter
    frontmatter = [
        "---",
        f"type: research",
        f'question: "{question}"',
        f"generated_at: {now}",
        "model: MiniMax-M3",
    ]
    if case_slug:
        frontmatter.append(f"case: {case_slug}")
    frontmatter.append(f"tags: [{', '.join(tags)}]")
    frontmatter.append("---")
    frontmatter.append("")

    # Build body
    body_parts = []

    if case_slug:
        body_parts.append(f"Related to: [[{case_slug}]]")
        body_parts.append("")

    body_parts.append(f"## Question\n\n{question}\n")
    body_parts.append(f"## Research Results\n\n{content}\n")

    full_content = "\n".join(frontmatter) + "\n".join(body_parts)

    out_path = OBSIDIAN_RESEARCH_DIR / f"{slug}.md"
    out_path.write_text(full_content, encoding="utf-8")
    log(f"Written to {out_path}")
    return str(out_path)


def update_research_index(slug: str, question: str, case_slug: str | None):
    """Append entry to Research Index.md."""
    OBSIDIAN_INDEX_DIR.mkdir(parents=True, exist_ok=True)

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    entry = f"- [[{slug}]] — {question[:100]} — {now_str}"
    if case_slug:
        entry += f" (case: [[{case_slug}]])"
    entry += "\n"

    if OBSIDIAN_INDEX_FILE.exists():
        existing = OBSIDIAN_INDEX_FILE.read_text(encoding="utf-8")
        # Only append if not already present
        if slug not in existing:
            with OBSIDIAN_INDEX_FILE.open("a", encoding="utf-8") as f:
                f.write(entry)
            log(f"Appended to index: {OBSIDIAN_INDEX_FILE}")
        else:
            log(f"Entry already exists in index, skipping")
    else:
        OBSIDIAN_INDEX_FILE.write_text(
            f"# Research Index\n\n## All Research\n\n{entry}", encoding="utf-8"
        )
        log(f"Created index: {OBSIDIAN_INDEX_FILE}")


def dry_run_print(question: str, slug: str, case_slug: str | None, breadth: int, depth: int):
    """Print what would be done without executing."""
    print("=== DRY RUN ===")
    print(f"Question: {question}")
    print(f"Slug: {slug}")
    print(f"Case: {case_slug or '(none)'}")
    print(f"Breadth: {breadth}, Depth: {depth}")
    print(f"Command: cd {DEEP_RESEARCH_DIR} && QUERY='...' npm run cli")
    print(f"Output would be written to: {OBSIDIAN_RESEARCH_DIR / f'{slug}.md'}")
    if case_slug:
        print(f"Wikilink to case: [[{case_slug}]]")
    print(f"Index updated: {OBSIDIAN_INDEX_FILE}")
    print("=== END DRY RUN ===")


# --- Main ---


def main():
    parser = argparse.ArgumentParser(description="Run deep-research for legal research")
    parser.add_argument("question", type=str, help="Research question")
    parser.add_argument("--case", type=str, default=None, help="Case slug for wikilink")
    parser.add_argument("--breadth", type=int, default=4, help="Research breadth (default: 4)")
    parser.add_argument("--depth", type=int, default=2, help="Research depth (default: 2)")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without executing")

    args = parser.parse_args()

    if not args.question.strip():
        print("Error: Question cannot be empty", file=sys.stderr)
        sys.exit(1)

    slug = slugify(args.question)
    log(f"Starting research: {args.question[:60]}...")
    log(f"Slug: {slug}")

    if args.dry_run:
        dry_run_print(args.question, slug, args.case, args.breadth, args.depth)
        sys.exit(0)

    # Run the research
    success, result = run_research(args.question, args.breadth, args.depth)

    if not success:
        print(f"Research failed:\n{result}", file=sys.stderr)
        sys.exit(1)

    # Write to Obsidian
    output_path = write_obsidian_note(args.question, result, slug, args.case)

    # Update index
    update_research_index(slug, args.question, args.case)

    print(f"\nResearch complete! File: {output_path}")
    print(f"Index updated: {OBSIDIAN_INDEX_FILE}")


if __name__ == "__main__":
    main()
