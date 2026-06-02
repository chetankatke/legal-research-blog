"""Tests for ingest_to_obsidian.py.

These tests use a temporary vault (set via env var) so they don't touch
the real Obsidian vault.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "ingest_to_obsidian.py"


def run_script(*args, vault=None, expect_success=True):
    """Run the ingest script as a subprocess and return (returncode, stdout, stderr)."""
    env = os.environ.copy()
    if vault is not None:
        env["OBSIDIAN_VAULT_PATH"] = str(vault)
    env["MINIMAX_OFFLINE"] = "1"  # disable LLM calls in tests
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, env=env, timeout=60,
    )
    if expect_success and result.returncode != 0:
        raise AssertionError(
            f"Script failed (rc={result.returncode}):\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )
    return result


@pytest.fixture
def fresh_vault(tmp_path, monkeypatch):
    """Create an empty vault in a tmp dir and point the env at it."""
    vault = tmp_path / "vault"
    (vault / "Cases").mkdir(parents=True)
    (vault / "Translations" / "mr").mkdir(parents=True)
    (vault / "Indexes").mkdir(parents=True)
    (vault / "Templates").mkdir(parents=True)
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(vault))
    return vault


FIXTURES = Path(__file__).parent / "fixtures"


class TestIngestBasics:
    def test_writes_note_to_correct_path(self, fresh_vault):
        result = run_script(str(FIXTURES / "sample_dk_basu.pdf"), vault=fresh_vault)
        # The script should have created a Cases/<slug>/ folder
        cases = list((fresh_vault / "Cases").iterdir())
        assert len(cases) == 1
        slug = cases[0].name
        assert (cases[0] / "README.md").exists()
        assert (cases[0] / "metadata.json").exists()

    def test_metadata_sidecar_is_valid_json(self, fresh_vault):
        run_script(str(FIXTURES / "sample_dk_basu.pdf"), vault=fresh_vault)
        cases = list((fresh_vault / "Cases").iterdir())
        meta = json.loads((cases[0] / "metadata.json").read_text())
        assert "ingested_at" in meta
        assert "source_pdf" in meta
        assert meta["source_pdf"] == str(FIXTURES / "sample_dk_basu.pdf")

    def test_readme_has_frontmatter(self, fresh_vault):
        run_script(str(FIXTURES / "sample_dk_basu.pdf"), vault=fresh_vault)
        cases = list((fresh_vault / "Cases").iterdir())
        readme = (cases[0] / "README.md").read_text()
        assert readme.startswith("---")
        assert "type: case" in readme
        assert "ingested_at" in readme
        assert "source_pdf" in readme

    def test_extracts_case_title_from_pdf(self, fresh_vault):
        run_script(str(FIXTURES / "sample_dk_basu.pdf"), vault=fresh_vault)
        cases = list((fresh_vault / "Cases").iterdir())
        readme = (cases[0] / "README.md").read_text()
        # The actual D.K. Basu case title should be extracted
        assert "D.K. BASU" in readme.upper() or "DK BASU" in readme.upper()

    def test_extracts_judges_from_pdf(self, fresh_vault):
        run_script(str(FIXTURES / "sample_dk_basu.pdf"), vault=fresh_vault)
        cases = list((fresh_vault / "Cases").iterdir())
        meta = json.loads((cases[0] / "metadata.json").read_text())
        # The D.K. Basu bench was Kuldip Singh and A.S. Anand
        # At minimum one of them should be extracted
        judges = meta.get("judges", [])
        assert len(judges) > 0, f"Expected judges, got {judges!r}"

    def test_updates_cases_index(self, fresh_vault):
        # Pre-create the index file
        idx = fresh_vault / "Indexes" / "Cases Index.md"
        idx.write_text("# Cases Index\n\n")
        run_script(str(FIXTURES / "sample_dk_basu.pdf"), vault=fresh_vault)
        content = idx.read_text()
        assert "Cases/" in content
        # Should have a wikilink to the new case
        assert "[[Cases/" in content

    def test_dry_run_creates_no_files(self, fresh_vault):
        before = set(fresh_vault.rglob("*"))
        result = run_script(str(FIXTURES / "sample_dk_basu.pdf"),
                           "--dry-run", vault=fresh_vault)
        after = set(fresh_vault.rglob("*"))
        # No new files
        assert before == after, f"Dry run created files: {after - before}"
        # But should mention what it would do
        assert "D.K." in result.stdout.upper() or "would" in result.stdout.lower() or "dry" in result.stdout.lower()

    def test_handles_missing_pdf(self, fresh_vault):
        result = run_script("/nonexistent/file.pdf", vault=fresh_vault, expect_success=False)
        assert result.returncode != 0
        assert "not found" in result.stderr.lower() or "no such" in result.stderr.lower()

    def test_handles_corrupt_pdf_gracefully(self, fresh_vault):
        result = run_script(str(FIXTURES / "corrupt.pdf"), vault=fresh_vault)
        # Should still create a note (with empty text + warning) — best-effort behavior
        cases = list((fresh_vault / "Cases").iterdir())
        assert len(cases) == 1
        readme = (cases[0] / "README.md").read_text()
        assert "ingested_at" in readme
        # No crash

    def test_explicit_slug_overrides_derived(self, fresh_vault):
        run_script(str(FIXTURES / "sample_dk_basu.pdf"),
                   "--case-slug", "my-custom-name-1996", vault=fresh_vault)
        assert (fresh_vault / "Cases" / "my-custom-name-1996" / "README.md").exists()


class TestIngestConcurrency:
    """Multiple PDFs in one directory get unique slugs."""

    def test_duplicate_slug_doesnt_overwrite(self, fresh_vault):
        # Ingest the same PDF twice
        run_script(str(FIXTURES / "sample_dk_basu.pdf"), vault=fresh_vault)
        run_script(str(FIXTURES / "sample_dk_basu.pdf"), vault=fresh_vault)
        cases = list((fresh_vault / "Cases").iterdir())
        # Should be 2 different folders (one might be a duplicate slug with a -2 suffix)
        assert len(cases) == 2
